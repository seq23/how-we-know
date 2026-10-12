#!/usr/bin/env bash
# THE ONLY THING THIS MAC IS FOR.
#
#   bin/batch-session.sh            # narrate + render everything pending, then push
#   bin/batch-session.sh --dry-run  # say what it would do
#
#   bin/batch-session.sh --max-episodes 4   # one week's worth, then stop
#   bin/batch-session.sh --no-overlap       # render only after narration ends
#   bin/batch-session.sh --resume-if-interrupted   # launchd, every 300 s: see
#                                           # RESUME ON WAKE below
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
    --resume-if-interrupted) RESUME_ONLY=1 ;;
    *) echo "unknown option: $1"; echo "usage: bin/batch-session.sh [--dry-run] [--no-overlap] [--max-episodes N] [--resume-if-interrupted]"; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# RESUME ON WAKE (owner, 2026-10-12: "no sleep and restart on wake, I need
# both"). Sleep alone never needed this: a sleeping Mac SUSPENDS this process
# and it carries on at wake. What kills a night is a reboot, a battery run
# flat or a kill - and then nothing re-ran the batch until the next 23:00.
#
# So the night is recorded in loop/state/_local/batch_progress.json (ignored
# by git; see loop/batch_progress.py) as each unit completes, and launchd's
# com.howweknow.batch-resume runs this script every 300 s with
# --resume-if-interrupted. That mode exits in well under a second unless the
# gate says GO: an unfinished night from TONIGHT (resume it), or no batch yet
# tonight between 23:00 and 06:00 (the Mac was off at 23:00 - launchd fires a
# missed calendar job on wake from sleep, never after a power-off). Past 09:00
# an unfinished night is reported, not resumed: the day's cloud lanes own the
# Mac's outputs then.
#
# Every step already skips work on disk, so a resume repeats nothing that
# finished. On top of that, whole phases recorded done tonight (narrate,
# render, captions, shelve, harvest) are skipped outright, and a render
# killed mid-mux - which leaves a TRUNCATED renders/<slug>-final.mp4 that
# render_one would otherwise treat as finished - is moved aside and redone.
#
# THE CAPS ARE UNCHANGED. Narration's cap is a WALL CLOCK (--until 07:00), not
# a duration, so a resume at 03:00 stops at the same 07:00 the 23:00 start
# would have; a resumed session never gets a fresh allowance. And a resume (or
# a launchd start fired late) after 07:00 does not narrate at all - otherwise
# --until 07:00 would roll to TOMORROW 07:00 and narrate through her day. What
# a resumed session holds awake (caffeinate -w) is its own process from the
# moment it resumed, which is all it can hold: the interrupted one is gone.
# ---------------------------------------------------------------------------
RESUME_ONLY="${RESUME_ONLY:-}"
BATCH_PROGRESS="${BATCH_PROGRESS:-$ROOT/loop/state/_local/batch_progress.json}"
BATCH_LOCK="${BATCH_LOCK:-$(dirname "$BATCH_PROGRESS")/batch.lock}"
export BATCH_PROGRESS
PYP="$PY"; [ -x "$PYP" ] || PYP=python3       # the progress helper is stdlib only
BP() { "$PYP" loop/batch_progress.py "$@"; }
RESUMED_FROM=""
PROGRESS_BEGUN=""
BATCH_KILLED=""

# THE ONE-BATCH LOCK. A pid file, taken atomically (noclobber), in the ignored
# _local directory so no git operation can delete it - the failure the
# narrator's audio/.narrate.lock had (see ONE NARRATOR below). A pid that is
# dead, or alive but no longer this script (pids are reused after a reboot),
# is stale and is taken over.
lock_holder() {
  local pid
  pid=$(cat "$BATCH_LOCK" 2>/dev/null) || return 1
  [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null     && ps -p "$pid" -o command= 2>/dev/null | grep -q "batch-session"     && { echo "$pid"; return 0; }
  return 1
}
take_lock() {
  mkdir -p "$(dirname "$BATCH_LOCK")"
  local holder
  if holder=$(lock_holder); then echo "$holder"; return 1; fi
  rm -f "$BATCH_LOCK"
  ( set -o noclobber; echo "$$" > "$BATCH_LOCK" ) 2>/dev/null && return 0
  holder=$(lock_holder) && { echo "$holder"; return 1; }
  echo "?"; return 1
}
on_exit() {
  local rc=$1
  # A finished run - including a named stop's exit 3 - is a COMPLETE night,
  # so the resume agent does not re-run a stop every five minutes. Only a
  # kill (TERM/INT/HUP: shutdown, logout, Ctrl-C) or SIGKILL/power loss, which
  # never reaches here, leaves the night open for a resume.
  if [ -n "$PROGRESS_BEGUN" ] && [ -z "$BATCH_KILLED" ]; then
    BP complete "$rc" >/dev/null 2>&1
  fi
  [ "$(cat "$BATCH_LOCK" 2>/dev/null)" = "$$" ] && rm -f "$BATCH_LOCK"
}
report_incomplete_night() {
  $PY loop/batch_progress.py report-incomplete 2>&1 | tail -1
  $PY loop/mac_sync.py push --lane batch "loop/state/stops/$($PY -c "import sys; sys.path.insert(0,'loop'); from common import week_id; print(week_id())")-mac-batch.json" 2>&1 | tail -1
}
# step NAME FN: run a whole phase unless tonight's record says it finished.
step() {
  local name="$1"; shift
  if BP done "$name"; then
    echo; echo "--- $name: already completed tonight - skipped on resume ---"
    return 0
  fi
  "$@"
  BP phase "$name"
}
# Narration may run now? Always for a hand run (unchanged); for a resume or a
# launchd start, only inside the night (see THE CAPS ARE UNCHANGED above).
narration_allowed() {
  [ -n "$RESUMED_FROM" ] || [ -n "$RESUME_ONLY" ]     || case "${XPC_SERVICE_NAME:-}" in com.howweknow.*) false ;; *) true ;; esac     || return 0
  NARRATION_UNTIL="$NARRATION_UNTIL" BP narration-window
}
hold_awake() { caffeinate -dimsu -w $$ & }

[ -n "${BATCH_TEST_STUBS:-}" ] && . "$BATCH_TEST_STUBS"   # tests only
if [ -n "$RESUME_ONLY" ]; then
  if holder=$(lock_holder); then
    echo "$(date '+%F %H:%M') batch-resume: a batch is already running (pid $holder) - nothing to do"
    exit 0
  fi
  gate_line=$(BP gate); gate_rc=$?
  echo "$(date '+%F %H:%M') batch-resume: $gate_line"
  case $gate_rc in
    0) ;;
    11) report_incomplete_night; exit 0 ;;
    *) exit 0 ;;
  esac
fi

# SELF-HEAL FIRST, IN THE SAME PASS. loop/extend.py used to run near the END of
# this script, after narration and rendering, so a script it lengthened was
# not re-voiced until the NEXT night and the short render sat in front of the
# gate below for a day - and then the gate refused to push anything at all.
# Run here, before the pending lists are computed, an extension drops the stale
# plan and the ordinary steps below re-plan, narrate the moved beats and render
# it once, tonight. --dry-run only says what it would do.
phase_selfheal() {
echo; echo "--- self-heal anything under the runtime floor ---"
if [ -n "$DRY" ]; then
  $PY loop/extend.py --dry-run || echo "  (see the banner above)"
else
  $PY loop/extend.py || echo "  (extension refused for at least one episode; those scripts are unchanged and the gate below will HOLD them, not the batch)"
fi
}

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

phase_survey() {
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
#
# WRITTEN rows only (loop/batch_queue.py:written_slugs). The queue also holds
# the Monday lane's unwritten topics - thirty of them from 2026-09-25 - and
# a topic with no script is not "blocked one stage earlier" on this Mac, it
# is simply not written yet. Listing those here sent the operator to run the
# planner hint below on scripts that do not exist (batch.err, 26 Sep).
pending_plan=$($PY - <<'PLANEOF'
import os, sys
sys.path.insert(0, "loop")
import batch_queue
print(" ".join(s for s in batch_queue.written_slugs()
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
}

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
# ---------------------------------------------------------------------------
# BUILD ANY MISSING SHOT PLAN, rather than printing the command for a human.
#
# A queued slug with no plans/<slug>.json is neither narratable nor renderable,
# so both loops above skip it silently and this script printed a NAMED STOP
# with the two commands to type. why-does-old-iron-not-rust sat in exactly that
# state while being FULLY NARRATED -- voice/narrate_all.py plans from the
# script directly, so it voiced 84 beats for an episode nothing downstream
# could see. The commands were already written out here; running them is not a
# judgement call.
phase_prepare() {
echo; echo "--- build any missing shot plan ---"
for slug in ${pending_plan:-}; do
  echo "  planning $slug"
  dom=$($PY -c "
import sys; sys.path.insert(0,'loop')
import domains; print(domains.domain_of_slug('$slug') or 'deep-sea-ocean-science')" 2>/dev/null) \
    || dom=deep-sea-ocean-science
  $PY -c "
import sys, json; sys.path.insert(0,'visuals')
import planner
p = planner.plan('scripts/$slug.md')
json.dump(p, open('plans/$slug.json','w'), indent=2)
print(f'    {len(p)} beat(s)')" || { echo "    FAILED to plan $slug"; continue; }
  case "$dom" in
    materials-and-manufacturing)
      HWK_DOMAIN="$dom" $PY visuals/plan_materials_images.py --apply "plans/$slug.json" \
        >/tmp/plan-img-$slug.log 2>&1 || echo "    (image pass declined; the plan stands)" ;;
  esac
done
pending_plan=""

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
}

# ---------------------------------------------------------------------------
# SHORTS ARE CUT AND SHELVED ON EVERY NIGHT, INCLUDING AN IDLE ONE.
# On 2026-09-18 the cloud Shorts lane stopped NO_SHORTS_SHELVED and called it
# self-resolving "on the Mac's next push". There was no next push: this script
# only reached bin/push-to-r2.sh after a narrate-or-render night, and it never
# ran bin/make-shorts.sh at all -- all 27 published Shorts had been cut by hand.
# Seven rendered episodes sat uncut while the gate below exited 0 with "nothing
# to do". The Mac is the only machine that can cut a Short (V14 reads the
# credit off the pixels; V15 OCRs the crop), so the Mac must cut on its own.
#
# make-shorts.sh is given ONLY the uncut slugs (loop/shorts_lane.py:uncut), so
# an episode is never re-cut. push-to-r2.sh is idempotent and refuses anything
# V14/V15 reject or the render gate holds, so calling it on an idle night shelves
# what is new and skips what is already there.
# Kept beside the progress file, not in $TMPDIR, so a RESUMED night still
# scans the push output its first half produced (an empty file would clear
# the mac-batch stop record). A fresh night truncates it.
PUSH_OUT="$(dirname "$BATCH_PROGRESS")/batch_push.out"
shelve_shorts() {
  echo; echo "--- shorts: cut what is rendered and uncut, then shelve ---"
  # Grouped by how many cuts the episode may publish (shorts_lane.cut_groups):
  # deep sea 3, everything else 1 (owner build 2026-10-08). --keep-existing
  # means a cut already on disk - possibly already on the channel - is never
  # re-rendered; only the missing ranks are cut.
  local groups
  groups=$($PY -c "import sys; sys.path.insert(0,'loop'); import shorts_lane
for n, s in sorted(shorts_lane.cut_groups().items()): print(n, ' '.join(s))") || {
    echo "  shorts_lane.uncut() refused - this machine holds no finished render"; return 0; }
  if [ -n "${groups// }" ]; then
    while read -r n slugs; do
      [ -n "$slugs" ] || continue
      echo "  uncut (x$n): $slugs"
      # shellcheck disable=SC2086
      bin/make-shorts.sh --count "$n" --keep-existing $slugs || echo "  make-shorts.sh rc=$? - whatever it did cut is shelved below; the rest is retried tomorrow"
    done <<< "$groups"
  else
    echo "  every finished render already has its Shorts cut"
  fi
  BP unit shorts_cut
  if [ -x bin/push-to-r2.sh ]; then
    # Teed, so the report step can hand its named stops to
    # loop/mac_batch_stop.py: launchd has no workflow to turn an exit 3 into
    # an issue, and SHORTS_UNVERIFIED went unseen from 21 Sep to 12 Oct 2026.
    bin/push-to-r2.sh 2>&1 | tee "$PUSH_OUT"
    BP unit push
  else
    echo "  bin/push-to-r2.sh does not exist yet - the cloud upload lane is still"
    echo "  being built. Until it lands, uploading stays on this Mac."
  fi
}

# ---------------------------------------------------------------------------
# THE VIDEO HARVEST RUNS ON THIS MAC, ON EVERY NIGHT INCLUDING AN IDLE ONE.
# research/imagery_video.py reads the credit burned into each clip with Apple
# Vision off frames ffmpeg pulls - tooling ubuntu-latest does not have and
# will not get. From 2026-09-12 the Saturday cloud lane held on that fact and
# asked the owner where the work should run (#77, then #91 the week after she
# closed it): a question a hold can only re-ask. The declaration answers it
# now - the harvester says `host: "mac-batch"` - and this is mac-batch.
#
# loop/footage_lane.py --host mac-batch runs exactly the harvesters declared
# for this Mac (re-screening NOAA's index only every harvest.interval_days, so
# an idle night is cheap), VERIFIES the ones the cloud runs through their
# stamps, and writes this Mac's own stamp to loop/state/harvest_runs.json.
# That stamp is the only thing about this harvest that crosses to the cloud:
# the manifest and the clips stay here and in R2 by design (V11 re-hashes every
# record against bytes on disk, so a committed manifest with no clips beside it
# would fail the Monday lane). The push below sends the stamp, the lane's stop
# record if it took one, and the owner-action file if it recorded one, with
# explicit paths - never channel/imagery, which holds 5 GB of clips.
#
# Called on the nothing-to-do path BEFORE its exit 0 and again on the
# narrate-or-render path, for the same reason shelve_shorts is: the batch has
# been idle every night since 2026-09-12, and a step only the busy path
# reaches is a step that does not run.
harvest_footage() {
  echo; echo "--- footage: harvest what is delegated to this Mac, verify the rest ---"
  # The cloud's stamps are read from THIS checkout, so bring it up to date
  # first (loop/mac_sync.py pull takes upstream for loop-state files, the way
  # the 09:00 backfill lane does). A failed pull is said and not fatal: the
  # harvest is still worth doing against yesterday's stamps.
  $PY loop/mac_sync.py pull 2>&1 | tail -1
  # nice: a weekly ~2.3 h OCR pass (measured 2026-09-19: 16 clips in 5m44s,
  # 8 workers, ~190% CPU) that on a busy night lands after 07:00, when the
  # Mac is hers. It yields to anything she is doing rather than competing.
  nice -n 10 $PY loop/footage_lane.py --host mac-batch
  local rc=$?
  case $rc in
    0) ;;
    3) echo "  named stop above - see the banner; the stamp records tonight's outcome" ;;
    *) echo "  footage lane FAILED (rc=$rc) - see above; nothing was stamped for it" ;;
  esac
  $PY loop/mac_sync.py push --lane imagery-harvest-mac \
      loop/state/harvest_runs.json loop/state/owner_action.json 2>&1 | tail -1
}

# THE "NOTHING TO DO" GATE LIVES HERE, AFTER THE POV REPAIR, NOT BEFORE IT.
# It used to sit above and exit first, which meant a shelf whose ONLY
# problem was an untraced producer POV reported "nothing to do" and left
# eight episodes stranded -- the repair below could never run, because the
# script had already decided there was nothing to repair.
phase_idle() {
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
  # Idle for narration and render is NOT idle for Shorts. The cut-and-shelve
  # step runs here too, or an idle week starves the cloud Shorts lane (see
  # shelve_shorts above).
  step shelve shelve_shorts
  # Nor is it idle for footage: the only host with Vision is this one, and
  # the cloud lane is verifying that it harvests (see harvest_footage above).
  step harvest harvest_footage
  exit 0
fi
}



# Hold the machine awake for the whole batch. -dimsu covers display, idle, disk,
# system and user-idle sleep; without it a long narration run dies on lid close.
# (hold_awake, defined above, and called from the main sequence at the end.)

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
  # IN FLIGHT: a kill during the mux leaves a truncated -final.mp4 behind;
  # the progress file names it so a resume sets it aside and renders again.
  BP rendering "$slug"
  # EXACTLY the call the two-phase version made. No duration, no frame count,
  # no timing override: the audio is the authority and assemble.py owns that.
  HWK_DOMAIN="$dom" $PY visuals/assemble.py "plans/$slug.json" "renders/${slug}-final.mp4" \
      --audio-dir "audio/$slug" --burn-captions \
      > "/tmp/asm-$slug.log" 2>&1 \
    && { echo "    ok"; RENDERED=$((RENDERED+1)); BP unit render "$slug"; thumb_one "$slug" "$dom"; } \
    || { echo "    FAILED"; tail -8 "/tmp/asm-$slug.log"; }
  BP rendering ""
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
#
# ONE BUILDER ENTRY POINT FOR EVERY DOMAIN. Until 2026-10-03 this function held
# a `case "$dom"` with one line for materials and a `*)` that printed "<domain>
# has no builder wired here; skipping" - for deep-sea-ocean-science, the
# channel's first domain. The first unnumbered deep-sea episode to render
# (how-do-scientists-know-about-other-galaxies) reached R2 with no thumbnail
# and the cloud lane refused it for a week (#143). visuals/thumbs_for.py owns
# the domain -> builder table now, and a test proves every allocated domain is
# in it, so this script never again keeps a second, shorter list of its own.
thumb_one() {
  local slug="$1" dom="$2" out="channel/thumbnails/$slug.jpg"
  [ -f "$out" ] && return 0
  local builder="visuals/thumbs_for.py"
  if HWK_DOMAIN="$dom" $PY "$builder" "$slug" >"/tmp/thumb-$slug.log" 2>&1 && [ -f "$out" ]; then
    echo "      thumbnail ok ($(du -h "$out" | cut -f1))"
  else
    # Loud, and specific about the two things that actually cause it.
    echo "      THUMBNAIL NOT BUILT — this episode cannot be uploaded until it is."
    tail -3 "/tmp/thumb-$slug.log" | sed 's/^/        /'
  fi
}

phase_narrate() {
if [ -n "${pending_audio// }" ] && ! narration_allowed; then
  echo
  echo "  narration skipped: it is past $NARRATION_UNTIL on a resumed or scheduled"
  echo "  run, and narrating now would run to TOMORROW's $NARRATION_UNTIL. Tonight's"
  echo "  23:00 batch continues it; rendering below still runs."
  pending_audio=""
fi
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
}

phase_render() {
echo; echo "--- render (final sweep) ---"
for slug in $(renderable); do
  render_one "$slug" || { echo "  --max-episodes $MAX_EPISODES reached; stopping"; break; }
done
}

phase_captions() {
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
# THE GATE HOLDS, IT DOES NOT HALT. This used to run V13 and V24 here and
# `exit 1` on any failure - refusing the whole R2 push while a render was under the
# floor" - which refused every finished episode on this Mac because ONE was
# six seconds short (why-is-steel-so-strong, 9.90 min, 6-13 September 2026).
# loop/render_gate.py writes the failing slugs to loop/state/render_hold.json;
# bin/push-to-r2.sh (via loop/r2.py:push) refuses to shelve exactly those and
# shelves the rest. A held render reaches YouTube by no route. The gate's exit
# code is the hold's own loud-once reporting and is not this script's.
echo; echo "--- render gate: hold what fails, ship what passes ---"
$PY loop/render_gate.py
if grep -q '"code": "RENDER_GATE_EMPTY"' "loop/state/stops/$(date -u +%G-W%V)-render-gate.json" 2>/dev/null; then
  echo "  the gate examined no renders on a machine that holds them - nothing is pushed"; exit 3
fi

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
# THE SHORTS LANE DOES NOT DEPEND ON THIS STAGE. From 2026-09-26 to 10-01 the
# failure branch below was `exit "$CAPRC"`, and loop/captions_build.py crashed
# every night on one unwritten queue row (FileNotFoundError from the planner),
# so the script never reached shelve_shorts: no Short reached R2 for a week
# and the cloud Shorts lane named NO_SHORTS_SHELVED seven days running, then
# went red. A caption failure is one episode's caption gap - the upload gate
# refuses THAT episode (captions_lane.uncaptioned, the one shared rule) - and
# must never cost every other episode its Short. The failure stays visible:
# the heartbeat records ok=0 and this script exits with CAPRC at the very end,
# after the Shorts, the harvest and the report have run.
$PY loop/captions_build.py
CAPRC=$?
BP set caprc "$CAPRC"            # a resume that skips this phase still reports it
case $CAPRC in
  0) ;;
  3) echo "  named stop above - see the banner. The push continues: an episode"
     echo "  that cannot be captioned is refused at the upload gate, not here." ;;
  *) echo "  captions_build FAILED (rc=$CAPRC). Whatever it staged before failing"
     echo "  is one healed episode's complete artifacts (it stages per slug) and"
     echo "  is committed below; the Shorts, the harvest and the report still run;"
     echo "  this script exits $CAPRC at the end so launchd and the log see it." ;;
esac

# COMMIT WHAT ONLY THIS MAC CAN PRODUCE, with explicit pathspecs.
#
# loop/captions_build.py has already `git add`ed exactly the files it wrote.
# Nothing else is staged here: `git add -A` on this machine would sweep in
# renders, work directories and half-written audio.
git add -- pov/pov-assignments.json scripts plans channel/thumbnails 2>/dev/null
# ...and the tracked audio/<slug>/beats.json manifests. voice/narrate_all.py
# rebuilds every manifest from the scripts at the START of each run, so a plan
# that grew or shrank (loop/extend.py, loop/pov_repair.py - both committed just
# above) changes manifest CONTENT that captions_build never stages, because it
# stages only the slugs whose durations it recorded. Left unstaged, the `git
# pull --rebase` below refuses with "You have unstaged changes" and the night's
# commit never leaves this Mac (CONFIRMED 2026-10-03). `-u` touches tracked
# files only: a wav can never be swept in by it.
git add -u -- audio 2>/dev/null
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
}

# Cut Shorts from tonight's renders, then push everything (renders, captions,
# Shorts) to R2 for the cloud lanes.
# (step shelve shelve_shorts - in the main sequence below.)

# The video harvest, after the renders are shelved: the cloud lanes need the
# shelf first, and the harvest can take an hour of NOAA range requests.
# (step harvest harvest_footage - in the main sequence below.)

# THE MAC REPORTS. The cloud digest reads loop/state/mac_heartbeat.json and this
# week's stop files from the repository; a Mac that finished renders and shipped
# none of them now says so where it can be seen. See loop/mac_sync.py.
phase_report() {
echo; echo "--- report to the repository ---"
held=$($PY -c "import sys; sys.path.insert(0,'loop'); import render_gate; print(','.join(sorted(render_gate.held_slugs())))")
pending=$($PY -c "import sys; sys.path.insert(0,'loop'); import backfill; print(len(backfill.library_pending()))" 2>/dev/null || echo "")
# ok=1 only when every stage finished; a captions failure is reported, never
# hidden behind a Shorts lane that did shelve.
batch_ok=1; [ "$CAPRC" -eq 0 ] || [ "$CAPRC" -eq 3 ] || batch_ok=0
$PY loop/mac_sync.py heartbeat --lane batch --ok "$batch_ok" --held "$held" --pending "$pending" --resumed-from "$RESUMED_FROM" 2>&1 | tail -1
# Every named stop the push ended on reaches the repository (stop file,
# committed just below) and, when it pages, ONE deduped GitHub issue. Never
# blocks: what passed is already on the shelf. See loop/mac_batch_stop.py.
$PY loop/mac_batch_stop.py scan "$PUSH_OUT" 2>&1 | grep -E "mac-batch" || true
$PY loop/mac_sync.py push --lane batch "loop/state/stops/$($PY -c "import sys; sys.path.insert(0,'loop'); from common import week_id; print(week_id())")-mac-batch.json" 2>&1 | tail -1

if [ "$batch_ok" -eq 0 ]; then
  echo; echo "=== batch complete WITH A CAPTIONS FAILURE (rc=$CAPRC) $(date '+%H:%M') ==="
  exit "$CAPRC"
fi
echo; echo "=== batch complete $(date '+%H:%M') ==="
}

# ---------------------------------------------------------------------------
# THE SEQUENCE. Everything above is a definition; this is the night.
# loop/tests/test_batch_resume_on_wake.py sources BATCH_TEST_STUBS here to
# replace the phases with fakes and drive the resume logic with a fake clock.
# ---------------------------------------------------------------------------
[ -n "${BATCH_TEST_STUBS:-}" ] && . "$BATCH_TEST_STUBS"

if [ -n "$DRY" ]; then
  phase_selfheal; phase_survey
  echo; echo "DRY RUN - nothing done."; exit 0
fi

if ! holder=$(take_lock); then
  echo "NAMED STOP: another batch session is running (pid $holder); not starting a second."
  exit 0
fi
trap 'on_exit $?' EXIT
trap 'BATCH_KILLED=1; exit 143' TERM INT HUP
BP begin
PROGRESS_BEGUN=1
RESUMED_FROM=$(BP resumed-from)
[ -n "$RESUMED_FROM" ] || : > "$PUSH_OUT"
touch "$PUSH_OUT"
CAPRC=$(BP get caprc 0)

phase_selfheal
phase_survey
phase_prepare
phase_idle
echo "  holding the Mac awake for the duration"
hold_awake
step narrate phase_narrate
step render phase_render
step captions phase_captions
# Cut Shorts from tonight's renders, then push everything (renders, captions,
# Shorts) to R2 for the cloud lanes.
step shelve shelve_shorts
# The video harvest, after the renders are shelved.
step harvest harvest_footage
phase_report
