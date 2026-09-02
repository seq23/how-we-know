#!/usr/bin/env bash
# THE ONLY THING THIS MAC IS FOR.
#
#   bin/batch-session.sh            # narrate + render everything pending, then push
#   bin/batch-session.sh --dry-run  # say what it would do
#
# Run this roughly every 7.5 weeks, when the Sunday rank lane emails a RUNWAY
# warning. It narrates every script that has no audio, renders every episode
# that has audio but no video, pushes the results to R2 for the cloud upload
# lane, and stops. Nothing else on this machine is scheduled.
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
DRY=""
[ "${1:-}" = "--dry-run" ] && DRY=1

pending_audio=$($PY - <<'PYEOF'
import json, glob, os
# THE PUBLISH QUEUE, not plans/*.json. The demand gate kills saturated topics -
# four so far - and their plan files stay on disk. Scanning the directory asked
# for 3.5 hours of narration for three episodes that can never publish.
order = json.load(open("research/publish_order.json"))
queue = [q["slug"] for q in order["queue"]]
out = []
for slug in queue:
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
pending_render=$($PY - <<'PYEOF'
import json, glob, os
order = json.load(open("research/publish_order.json"))
out = []
for q in order["queue"]:
    slug = q["slug"]; plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    if len(json.load(open(plan))) == len(glob.glob(f"audio/{slug}/*.wav")) \
       and not os.path.exists(f"renders/{slug}-final.mp4"):
        out.append(slug)
print(" ".join(out))
PYEOF
)

echo "=== batch session $(date '+%Y-%m-%d %H:%M') ==="
echo "  to narrate : ${pending_audio:-none}"
echo "  to render  : ${pending_render:-none}"

if [ -z "${pending_audio// }" ] && [ -z "${pending_render// }" ]; then
  echo
  echo "NAMED STOP: nothing to do. Every script is narrated and every narrated"
  echo "episode is rendered. If the runway is still low the shortfall is SCRIPTS,"
  echo "not audio - the authoring lane writes those in the cloud on Mondays."
  exit 0
fi

if [ -n "$DRY" ]; then echo; echo "DRY RUN - nothing done."; exit 0; fi

# Hold the machine awake for the whole batch. -dimsu covers display, idle, disk,
# system and user-idle sleep; without it a long narration run dies on lid close.
echo "  holding the Mac awake for the duration"
caffeinate -dimsu -w $$ &

if [ -n "${pending_audio// }" ]; then
  echo; echo "--- narration (~1.2 h per episode) ---"
  $PY voice/narrate_all.py || echo "  narration exited $? - rendering will cover what completed"
fi

echo; echo "--- render ---"
for slug in $pending_render $( $PY - <<'PYEOF'
import json, glob, os
order = json.load(open("research/publish_order.json"))
out = []
for q in order["queue"]:
    slug = q["slug"]; plan = f"plans/{slug}.json"
    if not os.path.exists(plan):
        continue
    if len(json.load(open(plan))) == len(glob.glob(f"audio/{slug}/*.wav")) \
       and not os.path.exists(f"renders/{slug}-final.mp4"):
        out.append(slug)
print(" ".join(out))
PYEOF
); do
  [ -e "renders/${slug}-final.mp4" ] && continue
  echo "  === $slug $(date +%H:%M:%S)"
  $PY visuals/assemble.py "plans/$slug.json" "renders/${slug}-final.mp4" \
      --audio-dir "audio/$slug" --burn-captions \
      > "/tmp/asm-$slug.log" 2>&1 \
    && echo "    ok" || { echo "    FAILED"; tail -8 "/tmp/asm-$slug.log"; }
done

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
