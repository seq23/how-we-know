#!/usr/bin/env bash
# THE ONLY THING THIS MAC IS FOR.
#
#   bin/batch-session.sh            # narrate + render everything pending, then push
#   bin/batch-session.sh --dry-run  # say what it would do
#
#   bin/batch-session.sh --max-episodes 4   # one week's worth, then stop
#   bin/batch-session.sh --no-overlap       # render only after narration ends
#
# Run this when the rank lane emails a RUNWAY warning. It narrates every script
# that has no audio, renders every episode that has audio but no video, pushes
# the results to R2 for the cloud upload lane, and stops. Nothing else on this
# machine is scheduled.
#
# THROUGHPUT, and why it changed on 2026-09-02. The owner raised the cadence to
# 4 episodes a week, and this Mac is the physical constraint: narration is
# ~1.2 h an episode and rendering ~12 min, and they used to run as two phases,
# all of the first and then all of the second. Rendering now OVERLAPS narration
# - the moment an episode's audio is complete it is handed to a render while
# the voice model moves on to the next script - so the render phase leaves the
# critical path almost entirely. A sixteen-episode batch drops from about 22
# hours to about 19; a four-episode weekly batch from about 5.6 to 4.9.
#
# TWO INVARIANTS THE OVERLAP DOES NOT TOUCH, and must not:
#
#   * An episode is rendered only when its audio is COMPLETE - the wav count
#     equals the plan's beat count. A half-narrated episode is never handed to
#     the assembler, so overlapping cannot produce a short render.
#   * visuals/assemble.py is called exactly as before. It treats the AUDIO as
#     the timing authority and nothing here passes it a duration, a frame count
#     or any other override. loop/tests/test_render_throughput.py asserts both.
#
# --max-episodes bounds a session so the batch can be run nightly at the higher
# cadence instead of as one long marathon. --no-overlap restores the old two-
# phase behaviour if a render is ever suspected of starving the voice model.
#
# WHY THIS IS A BATCH AND NOT A WEEKLY JOB. Narration is the one stage that
# cannot run in GitHub Actions - the voice model is local, and it is slow:
# measured at 71 minutes for a 67-beat episode, about 1.2 hours each. Two
# episodes a week would be near the whole free Actions allowance and close to
# the 6-hour job ceiling. Rendering could move, but it needs the audio that
# narration just produced, so it rides along. Everything downstream - uploading,
# scheduling, thumbnails, Shorts, publishing, measurement - runs in the cloud
# and never needs this laptop.
#
# It is RESUMABLE. Every step skips what already exists, so an interrupted run
# is re-run, not restarted.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd)"
PY=.venv/bin/python
# VOICE HAS ITS OWN ENVIRONMENT and always did - bin/run-batch.sh has used
# .venv-tts since the voice lane was built. This script called
# `$PY voice/narrate_all.py`, i.e. the RENDER venv, which has no torch and no
# soundfile: narration died on `ModuleNotFoundError: No module named
# 'soundfile'` and read as a broken narrator rather than a missing package -
# the trap CLAUDE.md names first. Rendering keeps .venv (PIL, numpy, ffmpeg);
# only narration uses .venv-tts (torch, chatterbox-tts, soundfile).
PY_TTS=.venv-tts/bin/python

# NARRATION HANDS THE MAC BACK IN THE MORNING. Owner decision 2026-09-05: the
# job starts at 23:00 and stops at 07:00, rather than running until the backlog
# is finished -- which on 2026-09-05 meant it was still generating audio at
# four in the afternoon on a Saturday.
#
# Stopping costs nothing. narrate_all.py checks this BETWEEN beats, never
# during one, and a beat whose wav already exists is skipped on the next run,
# so the following night resumes exactly where this one stopped. What it costs
# is calendar time, and what it buys is a Mac that is hers during the day.
NARRATION_UNTIL="${NARRATION_UNTIL:-07:00}"
DRY=""
OVERLAP=1
MAX_EPISODES=0            # 0 = no bound
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)      DRY=1 ;;
    --no-overlap)   OVERLAP="" ;;
    --max-episodes) MAX_EPISODES="${2:-0}"; shift ;;
    *) echo "unknown option: $1"; echo "usage: bin/batch-session.sh [--dry-run] [--no-overlap] [--max-episodes N]"; exit 2 ;;
  esac
  shift
done

# THE ONE DEFINITION OF "ready to render": every beat in the plan has a wav and
# there is no finished render yet. Both the overlap poll and the final sweep
# call this, so a partially-narrated episode can never reach the assembler by
# one route while being correctly skipped by the other.
renderable() {
  $PY - <<'READYEOF'
import json, glob, os, shutil, sys
sys.path.insert(0, "loop")
import batch_queue
# EVERY BEAT HAS A WAV -- not "the counts are equal".
#
# Counting conflated two different facts, and the difference is a permanent
# stall. what-is-concrete-made-of held 70 wavs (0000..0069) against a 69-beat
# plan: an orphan left behind when the plan shrank. 70 != 69, so this predicate
# said "not ready" and would have said it forever -- the episode could never be
# re-rendered by any route, and nothing anywhere named the reason. Asking
# whether beat i has a wav, for every i the plan actually has, cannot be fooled
# by a file the plan no longer indexes.
#
# The orphan is MOVED, never deleted: assemble.py ignores it, but leaving it
# in place means the next reader of this directory is misled the same way.
out = []
for slug in batch_queue.queued_slugs():
    plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    n = len(json.load(open(plan)))
    have = {os.path.basename(w) for w in glob.glob(f"audio/{slug}/*.wav")}
    orphans = sorted(w for w in have
                     if not w[:-4].isdigit() or int(w[:-4]) >= n)
    if orphans:
        d = f"audio/{slug}/superseded"
        os.makedirs(d, exist_ok=True)
        for w in orphans:
            shutil.move(f"audio/{slug}/{w}", f"{d}/{w}")
            print(f"# moved orphan audio/{slug}/{w} aside (plan has {n} beats)",
                  file=sys.stderr)
        have -= set(orphans)
    if all(f"{i:04d}.wav" in have for i in range(n)) \
       and not os.path.exists(f"renders/{slug}-final.mp4"):
        out.append(slug)
print(" ".join(out))
READYEOF
}

pending_audio=$($PY - <<'PYEOF'
import json, glob, os, sys
sys.path.insert(0, "loop")
# THE PUBLISH QUEUES, not plans/*.json. The demand gate kills saturated topics -
# four so far - and their plan files stay on disk. Scanning the directory asked
# for 3.5 hours of narration for three episodes that can never publish.
# EVERY domain's queue, not just deep sea: loop/batch_queue.py globs
# research/publish_order*.json the way loop/domains.py already does.
import batch_queue
out = []
for slug in batch_queue.queued_slugs():
    plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    want = len(json.load(open(plan)))
    # Per-index, for the reason renderable() explains: an orphan wav from a
    # shrunken plan must not make an unvoiced beat look voiced, and a count
    # cannot tell the difference.
    names = {os.path.basename(w) for w in glob.glob(f"audio/{slug}/*.wav")}
    have = sum(1 for i in range(want) if f"{i:04d}.wav" in names)
    if have < want:
        out.append(f"{slug}:{have}/{want}")
print(" ".join(out))
PYEOF
)

# THE HINT ABOVE NAMED THE WRONG TOOL. It said "visuals/plan_species.py", which is
# the deep-sea image pass, not a plan builder - and every topic that has hit this
# stop since materials went live on 2026-09-03 has been a materials topic, where
# plan_species.py is the wrong lane entirely. Following it produces nothing.
#
# The two real steps are: planner.plan() writes plans/<slug>.json from the script,
# and plan_materials_images.py then places the photographs. Both need .venv, not
# .venv-tts - PIL lives in the render venv, and running the image pass under the
# system python fails on "No module named 'PIL'".
#
# A queued slug with no plan file is SILENTLY SKIPPED by both loops above - it
# is neither narratable nor renderable, so the preview said "none" and the
# reason never reached the operator. Name it instead. Rule 0: this stage does
# not get to exit 0 having done nothing without saying why.
pending_plan=$($PY - <<'PLANEOF'
import os, sys
sys.path.insert(0, "loop")
import batch_queue
print(" ".join(s for s in batch_queue.queued_slugs()
                if not os.path.exists(f"plans/{s}.json")))
PLANEOF
)
# ONE definition of readiness, used by the preview, the overlap poll and the
# final sweep alike. Two copies of "ready to render" is how a component ends up
# skipping an episode by one route while assembling it short by the other.
pending_render=$(renderable)

echo "=== batch session $(date '+%Y-%m-%d %H:%M') ==="
echo "  to narrate : ${pending_audio:-none}"
echo "  to render  : ${pending_render:-none}"
echo "  no plan yet: ${pending_plan:-none}"

if [ -n "$DRY" ]; then echo; echo "DRY RUN - nothing done."; exit 0; fi

# ---------------------------------------------------------------------------
# SELF-HEAL AN UNTRACED PRODUCER POV, BEFORE ANYTHING IS VOICED.
#
# loop/cloud_upload.py refuses to upload an episode whose [HUMAN] beat has no
# entry in pov/pov-assignments.json, and that refusal is right: the authoring
# model composes those beats, and she did not write them. On 2026-09-08 eight
# rendered, captioned, shelved materials episodes were stranded on exactly that
# - a permanent stall, because nothing in the repo ever wrote an assignment.
#
# loop/pov_repair.py swaps the invented sentence for a real line from
# pov/pov-bank.json (her own interviews, her approved voice - matching, not
# approving) and invalidates the audio beat, the caption track and the render
# so the rest of this script rebuilds them. It runs HERE because everything it
# invalidates is rebuilt below, in this same unattended pass.
echo; echo "--- self-heal any untraced producer POV ---"
$PY loop/pov_repair.py || echo "  (see the banner above; nothing was changed for any episode it refused)"

# The repair may have superseded a render, so re-ask what is narratable and
# renderable. Recomputing is the point: the lists above were taken before it ran.
pending_audio=$($PY - <<'PYEOF2'
import json, glob, os, sys
sys.path.insert(0, "loop")
import batch_queue
out = []
for slug in batch_queue.queued_slugs():
    plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    want = len(json.load(open(plan)))
    # Per-index, for the reason renderable() explains: an orphan wav from a
    # shrunken plan must not make an unvoiced beat look voiced, and a count
    # cannot tell the difference.
    names = {os.path.basename(w) for w in glob.glob(f"audio/{slug}/*.wav")}
    have = sum(1 for i in range(want) if f"{i:04d}.wav" in names)
    if have < want:
        out.append(f"{slug}:{have}/{want}")
print(" ".join(out))
PYEOF2
)
echo "  to narrate now: ${pending_audio:-none}"
pending_render=$(renderable)
echo "  to render now : ${pending_render:-none}"

# THE "NOTHING TO DO" GATE LIVES HERE, AFTER THE POV REPAIR, NOT BEFORE IT.
# It used to sit above and exit first, which meant a shelf whose ONLY
# problem was an untraced producer POV reported "nothing to do" and left
# eight episodes stranded -- the repair below could never run, because the
# script had already decided there was nothing to repair.
if [ -z "${pending_audio// }" ] && [ -z "${pending_render// }" ]; then
  echo
  if [ -n "${pending_plan// }" ]; then
    echo "NAMED STOP: nothing THIS MAC can do. Every script that has a shot plan is"
    echo "narrated and rendered. The queued topics listed above as 'no plan yet' are"
    echo "blocked one stage earlier: they have no plans/<slug>.json, so there is"
    echo "nothing for the voice model to read. Build those plans first:"
    echo "  .venv/bin/python -c \"import sys;sys.path.insert(0,'visuals');import planner,json;\\"
    echo "    json.dump(planner.plan('scripts/<slug>.md'),open('plans/<slug>.json','w'),indent=2)\""
    echo "  then, for a materials topic, the image pass:"
    echo "    .venv/bin/python visuals/plan_materials_images.py --apply plans/<slug>.json"
    echo "then re-run this."
    echo "  blocked: $(echo $pending_plan | wc -w | tr -d ' ') queued topic(s)"
  else
    echo "NAMED STOP: nothing to do. Every script is narrated and every narrated"
    echo "episode is rendered. If the runway is still low the shortfall is SCRIPTS,"
    echo "not audio - the authoring lane writes those in the cloud on Mondays."
  fi
  exit 0
fi



# Hold the machine awake for the whole batch. -dimsu covers display, idle, disk,
# system and user-idle sleep; without it a long narration run dies on lid close.
echo "  holding the Mac awake for the duration"
caffeinate -dimsu -w $$ &

RENDERED=0
render_one() {
  local slug="$1"
  [ -e "renders/${slug}-final.mp4" ] && return 0
  if [ "$MAX_EPISODES" -gt 0 ] && [ "$RENDERED" -ge "$MAX_EPISODES" ]; then
    return 1
  fi
  echo "  === $slug $(date +%H:%M:%S)"
  # THE EPISODE'S OWN DOMAIN decides the palette and the structural device.
  # visuals/design.py resolves HWK_DOMAIN at import; unset, it defaults to
  # deep sea, which would have rendered every materials episode in ocean blue
  # and raised "unknown segment type: thermal_ascent" on the first thermal
  # beat - after the narration for it had already been paid for. The domain
  # comes from the script's own **Domain:** line via loop/domains.py, so
  # there is no second list of which slug is which domain.
  local dom
  dom=$($PY -c "
import sys; sys.path.insert(0,'loop')
import domains; print(domains.domain_of_slug('$slug') or 'deep-sea-ocean-science')" 2>/dev/null) \
    || dom=deep-sea-ocean-science
  echo "      domain: $dom"
  # EXACTLY the call the two-phase version made. No duration, no frame count,
  # no timing override: the audio is the authority and assemble.py owns that.
  HWK_DOMAIN="$dom" $PY visuals/assemble.py "plans/$slug.json" "renders/${slug}-final.mp4" \
      --audio-dir "audio/$slug" --burn-captions \
      > "/tmp/asm-$slug.log" 2>&1 \
    && { echo "    ok"; RENDERED=$((RENDERED+1)); thumb_one "$slug" "$dom"; } \
    || { echo "    FAILED"; tail -8 "/tmp/asm-$slug.log"; }
  return 0
}

# A RENDER WITHOUT A THUMBNAIL CANNOT BE UPLOADED, so build it here, in the
# same step that produced the MP4.
#
# backfill.local_assets() requires BOTH renders/<slug>-final.mp4 and
# channel/thumbnails/<slug>.jpg before an episode counts as pending. Nothing
# built the second one. On 2026-09-05 that left nine finished episodes sitting
# un-uploadable while com.howweknow.backfill reported "0 pending" every morning
# at 09:00 - technically true, and useless, because the reason was a missing
# 200 KB JPEG. Rendering and thumbnailing are one unit of work; splitting them
# across a human is what created the stall.
thumb_one() {
  local slug="$1" dom="$2" out="channel/thumbnails/$slug.jpg"
  [ -f "$out" ] && return 0
  case "$dom" in
    materials-and-manufacturing) builder="visuals/thumbs_materials.py" ;;
    *) echo "      thumbnail: $dom has no builder wired here; skipping"; return 0 ;;
  esac
  if HWK_DOMAIN="$dom" $PY "$builder" "$slug" >"/tmp/thumb-$slug.log" 2>&1 && [ -f "$out" ]; then
    echo "      thumbnail ok ($(du -h "$out" | cut -f1))"
  else
    # Loud, and specific about the two things that actually cause it.
    echo "      THUMBNAIL NOT BUILT — this episode cannot be uploaded until it is."
    tail -3 "/tmp/thumb-$slug.log" | sed 's/^/        /'
  fi
}

if [ -n "${pending_audio// }" ] && [ ! -x "$PY_TTS" ]; then
  echo
  echo "NAMED STOP: $PY_TTS does not exist, so nothing can be narrated."
  echo "The voice environment is separate from the render one and holds torch,"
  echo "chatterbox-tts and soundfile (~1.3 GB). Rebuild it with:"
  echo "    /opt/homebrew/bin/python3.12 -m venv .venv-tts"
  echo "    .venv-tts/bin/pip install chatterbox-tts==0.1.7 soundfile 'setuptools<81'"
  echo "The 'setuptools<81' pin is required: resemble-perth imports pkg_resources,"
  echo "which setuptools 84 removed, and chatterbox then fails at model init with"
  echo "TypeError: 'NoneType' object is not callable - not an obvious missing dep."
  echo "Model weights (~3 GB) are cached in ~/.cache/huggingface and are not"
  echo "re-downloaded."
  exit 3
fi

# ONE NARRATOR, ENFORCED HERE TOO, not only by the lockfile.
#
# narrate_all.py takes an exclusive lock at audio/.narrate.lock. That lock is a
# file inside audio/, which means any git operation touching that path can
# delete it - `git stash -u -- audio` did exactly that on 2026-09-05, and the
# 23:00 batch then started a SECOND narrator alongside one that had been
# running for 35 hours. Both survived, both wrote to the same
# audio/<slug>/NNNN.wav, and throughput halved: the voice model wants about
# four cores, so two of them do not go twice as fast.
#
# A process check cannot be deleted by a git command, so it holds where the
# lockfile does not.
if pgrep -f "voice/narrate_all.py" >/dev/null 2>&1; then
  echo
  echo "NAMED STOP: a narrator is already running (pid(s) $(pgrep -f 'voice/narrate_all.py' | tr '\n' ' '))."
  echo "Narration is single-threaded here by design - the voice model takes"
  echo "roughly four cores, so a second one halves both. Not starting another."
  echo "Rendering below still runs against whatever audio is already complete."
  echo
  pending_audio=""
fi

if [ -n "${pending_audio// }" ]; then
  echo; echo "--- narration (~1.2 h per episode) ---"
  if [ -n "$OVERLAP" ]; then
    echo "  rendering overlaps narration: each episode is assembled as soon as"
    echo "  its audio is COMPLETE, while the voice model moves to the next."
    $PY_TTS voice/narrate_all.py --until "$NARRATION_UNTIL" &
    NARRATE_PID=$!
    while kill -0 "$NARRATE_PID" 2>/dev/null; do
      for slug in $(renderable); do
        render_one "$slug" || break
      done
      # Long enough that the poll costs nothing next to a 1.2-hour narration,
      # short enough that a finished episode does not sit waiting.
      sleep 60
    done
    wait "$NARRATE_PID" || echo "  narration exited $? - rendering covers what completed"
  else
    $PY_TTS voice/narrate_all.py --until "$NARRATION_UNTIL" || echo "  narration exited $? - rendering covers what completed"
  fi
fi

echo; echo "--- render (final sweep) ---"
for slug in $(renderable); do
  render_one "$slug" || { echo "  --max-episodes $MAX_EPISODES reached; stopping"; break; }
done

echo; echo "--- can the cloud see everything this batch just used? ---"
# THE MAC IS WHERE UNTRACKED FILES ARE BORN, so this is where the question is
# cheapest to answer. V30 walks every lane entrypoint's import closure and every
# tracked rights manifest, and names anything git cannot see. On 2026-09-04
# three modules that existed only here cost a day: five validators hard-failing
# on zero items, a tripped breaker, a Monday lane red since 31 August, a CI
# suite silently one file short, and a render that died on an argument the
# committed assemble.py had never heard of. Every one of those was this, wearing
# a different face. Asking here means the answer arrives before the push, not
# after the cloud has spent a Monday on it.
$PY -c "
import sys; sys.path.insert(0,'loop')
import validate
d = validate.v30_cloud_visibility().as_dict()
fs = d.get('failures') or d.get('fails') or []
print('  V30 examined', d.get('examined'), '- CLEAN' if not fs else '- FAILING:')
[print('   ', f) for f in fs]
if fs:
    print()
    print('  These files exist on this Mac and nowhere else. Commit them, or the')
    print('  cloud lanes will fail on Monday for reasons that will not name them.')
"

# ---------------------------------------------------------------------------
# SELF-HEAL ANYTHING UNDER THE RUNTIME FLOOR, BEFORE IT IS RENDERED.
#
# Owner decision 2026-09-05: aim for 12 minutes, tolerate 15% either side, and
# anything under 10 minutes heals itself. This runs BEFORE the render sweep so
# an episode that needs more narration gets it, is re-planned and re-narrated
# for only the beats that moved, and is rendered once - rather than being
# rendered short and discovered afterwards.
echo; echo "--- self-heal anything under the runtime floor ---"
$PY loop/extend.py || echo "  (extension refused for at least one episode; those scripts are unchanged)"

echo; echo "--- verify nothing is clipped ---"
$PY -c "
import sys; sys.path.insert(0,'loop')
import validate
d = validate.v13_render_not_clipped().as_dict()
fs = d.get('failures') or d.get('fails') or []
print('  V13 examined', d.get('examined'), '- CLEAN' if not fs else '- FAILING:')
[print('   ',f) for f in fs]"

# THE GATE THAT WAS MISSING. V24 governs the runtime floor and runs where the
# renders are, which is this Mac. The cloud drafting lane that trips the breaker
# on a validator failure cannot see renders/ at all, so V24 exempts itself there
# and passes. The result was a hard floor that nothing on the upload path ever
# consulted: four episodes at 8.6-9.7 minutes were rendered, receipted and
# waiting to ship, and the only thing that had noticed was a validator running
# on a machine with no upload step. Asked here, the answer arrives before the
# push to R2 rather than after YouTube has it.
echo; echo "--- verify nothing is under the runtime floor ---"
$PY -c "
import sys; sys.path.insert(0,'loop')
import validate
d = validate.v24_render_duration_floor().as_dict()
fs = d.get('failures') or d.get('fails') or []
print('  V24 examined', d.get('examined'), '- CLEAN' if not fs else '- FAILING:')
[print('   ',f) for f in fs]
if fs:
    print()
    print('  These renders are under the owner hard floor and must NOT be pushed.')
    print('  loop/extend.py heals a short script; a short RENDER of a healed')
    print('  script just needs re-rendering.')
    sys.exit(1)
" || { echo; echo "  REFUSING to push to R2 while a render is under the floor."; exit 1; }

# ---------------------------------------------------------------------------
# CAPTIONS, IN THE SAME PASS THAT MADE THE AUDIO THEY ARE TIMED FROM.
#
# This wire is what was missing on 2026-09-08. The batch narrated, rendered,
# thumbnailed and pushed to R2 - and never ran visuals/captions.py, which lived
# in a SEPARATE manual command (bin/make-captions.sh) nobody was going to type.
# So every episode after the original sixteen reached the shelf with no caption
# track, and the cloud upload lane refused it and paged the owner
# (CAPTIONS_NOT_READY, run 34236877023) to ask her to run that command.
#
# It runs BEFORE the push for the same reason the runtime floor does: the
# question is cheapest to answer on the machine that holds the inputs, and the
# answer has to exist before the cloud is asked to act on the render.
#
# It also writes each measured wav duration into audio/<slug>/beats.json, which
# git tracks. That is the artifact that lets the CLOUD rebuild a caption track
# with no laptop at all - so even a batch that is interrupted before the commit
# below leaves the loop able to heal itself on the next push.
# A RENDER WITHOUT A THUMBNAIL IS INVISIBLE TO THE UPLOAD LANE.
# backfill.local_assets() requires both, and thumb_one() above only fires for
# an episode this run rendered. Anything rendered by an earlier run, or whose
# thumbnail build failed once, stays un-uploadable forever - five materials
# episodes were in exactly that state on 2026-09-08. Sweep every rendered
# episode, not only this run's.
echo; echo "--- thumbnails for anything rendered without one ---"
for slug in $($PY -c "
import sys, os; sys.path.insert(0,'loop')
import batch_queue
print(' '.join(s for s in batch_queue.queued_slugs()
                if os.path.exists(f'renders/{s}-final.mp4')
                and not os.path.exists(f'channel/thumbnails/{s}.jpg')))"); do
  dom=$($PY -c "
import sys; sys.path.insert(0,'loop')
import domains; print(domains.domain_of_slug('$slug') or 'deep-sea-ocean-science')" 2>/dev/null) \
    || dom=deep-sea-ocean-science
  thumb_one "$slug" "$dom"
done

echo; echo "--- captions (and the measured beat timings the cloud needs) ---"
$PY loop/captions_build.py
CAPRC=$?
case $CAPRC in
  0) ;;
  3) echo "  named stop above - see the banner. The push continues: an episode"
     echo "  that cannot be captioned is refused at the upload gate, not here." ;;
  *) echo "  captions_build FAILED (rc=$CAPRC). Not pushing renders whose caption"
     echo "  tracks are unknown."; exit "$CAPRC" ;;
esac

# COMMIT WHAT ONLY THIS MAC CAN PRODUCE, with explicit pathspecs.
#
# loop/captions_build.py has already `git add`ed exactly the files it wrote.
# Nothing else is staged here: `git add -A` on this machine would sweep in
# renders, work directories and half-written audio.
git add -- pov/pov-assignments.json scripts plans channel/thumbnails 2>/dev/null
if ! git diff --cached --quiet; then
  git commit -q -m "captions: tracks and measured beat timings from the batch

Generated by bin/batch-session.sh in the same pass that produced the narration
they are timed from. audio/<slug>/beats.json now carries each beat's measured
wav duration, which is what lets the cloud upload lane build a missing caption
track without this Mac."
  if git pull --rebase -q && git push -q; then
    echo "  committed and pushed the caption artifacts"
  else
    git rebase --abort 2>/dev/null || true
    echo "  COULD NOT PUSH the caption commit. It exists on this Mac only."
    echo "  The cloud lane will heal what it can from what is already on origin;"
    echo "  re-run this script (or just 'git push') to send the rest."
  fi
else
  echo "  nothing new to commit - every narrated episode already has its track"
  echo "  and its measured timings on origin."
fi

echo; echo "--- push to R2 for the cloud upload lane ---"
if [ -x bin/push-to-r2.sh ]; then
  bin/push-to-r2.sh
else
  echo "  bin/push-to-r2.sh does not exist yet - the cloud upload lane is still"
  echo "  being built. Until it lands, uploading stays on this Mac."
fi

echo; echo "=== batch complete $(date '+%H:%M') ==="
