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
import json, glob, os, sys
sys.path.insert(0, "loop")
import batch_queue
out = []
for slug in batch_queue.queued_slugs():
    plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    if len(json.load(open(plan))) == len(glob.glob(f"audio/{slug}/*.wav")) \
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
    have = len(glob.glob(f"audio/{slug}/*.wav"))
    if have < want:
        out.append(f"{slug}:{have}/{want}")
print(" ".join(out))
PYEOF
)

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

if [ -z "${pending_audio// }" ] && [ -z "${pending_render// }" ]; then
  echo
  if [ -n "${pending_plan// }" ]; then
    echo "NAMED STOP: nothing THIS MAC can do. Every script that has a shot plan is"
    echo "narrated and rendered. The queued topics listed above as 'no plan yet' are"
    echo "blocked one stage earlier: they have no plans/<slug>.json, so there is"
    echo "nothing for the voice model to read. Build those plans first"
    echo "(visuals/plan_species.py), then re-run this."
    echo "  blocked: $(echo $pending_plan | wc -w | tr -d ' ') queued topic(s)"
  else
    echo "NAMED STOP: nothing to do. Every script is narrated and every narrated"
    echo "episode is rendered. If the runway is still low the shortfall is SCRIPTS,"
    echo "not audio - the authoring lane writes those in the cloud on Mondays."
  fi
  exit 0
fi

if [ -n "$DRY" ]; then echo; echo "DRY RUN - nothing done."; exit 0; fi

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
    && { echo "    ok"; RENDERED=$((RENDERED+1)); } \
    || { echo "    FAILED"; tail -8 "/tmp/asm-$slug.log"; }
  return 0
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
    $PY_TTS voice/narrate_all.py &
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
    $PY_TTS voice/narrate_all.py || echo "  narration exited $? - rendering covers what completed"
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

echo; echo "--- verify nothing is clipped ---"
$PY -c "
import sys; sys.path.insert(0,'loop')
import validate
d = validate.v13_render_not_clipped().as_dict()
fs = d.get('failures') or d.get('fails') or []
print('  V13 examined', d.get('examined'), '- CLEAN' if not fs else '- FAILING:')
[print('   ',f) for f in fs]"

echo; echo "--- push to R2 for the cloud upload lane ---"
if [ -x bin/push-to-r2.sh ]; then
  bin/push-to-r2.sh
else
  echo "  bin/push-to-r2.sh does not exist yet - the cloud upload lane is still"
  echo "  being built. Until it lands, uploading stays on this Mac."
fi

echo; echo "=== batch complete $(date '+%H:%M') ==="
