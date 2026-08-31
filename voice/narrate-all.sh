#!/bin/bash
# Detached, resumable narration for all 20 episodes.
#
#   voice/narrate-all.sh              # start (or resume) the whole run
#   tail -f audio/narrate-all.log     # watch it
#
# `narrate_all.py` holds an exclusive lockfile (audio/.narrate.lock) and skips
# every beat already on disk, so re-running this is always safe: a second
# instance refuses to start, and a resumed instance picks up where it stopped.
#
# caffeinate -i -m: keep the machine awake and the disk spun up for a job that
# runs for many hours.
#
# Detachment: `nohup ... & disown` is NOT sufficient here. It drops the job from
# the shell's job table but leaves it in the shell's process group and session,
# so a harness reaping its background tasks kills the run too - that happened
# twice today, once at beat 23 of 55, silently. macOS has no setsid(1), so
# voice/spawn_detached.py calls os.setsid() via Popen(start_new_session=True)
# and the job lands in its own session where no group signal can reach it.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${TTS_PYTHON:-/Users/sequoiataylor/Misc/Random project files/.venv-tts/bin/python}"
REF="${NARRATION_REF:-voice/reference_A_clean_cond10.wav}"
LOG=audio/narrate-all.log

[ -x "$PY" ] || { echo "no chatterbox interpreter at $PY" >&2; exit 2; }
[ -f "$REF" ] || { echo "no reference wav at $REF" >&2; exit 2; }

mkdir -p audio
PID=$(python3 voice/spawn_detached.py "$LOG" \
        caffeinate -i -m "$PY" -u voice/narrate_all.py --reference "$REF" "$@")
echo "narration started (pid $PID, own session) -> $LOG"
# Prove the detachment rather than assuming it: pid == pgid == sess means the
# job leads its own session and no group-wide kill can reach it.
ps -o pid,pgid,sess,stat -p "$PID" 2>/dev/null || echo "WARNING: pid $PID not running"
