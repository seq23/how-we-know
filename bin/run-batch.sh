#!/usr/bin/env bash
# Local batch runner. Keeps the Mac awake for the duration — an unattended render
# that dies at 03:00 because the display slept is the single most likely way this
# pipeline silently produces nothing.
#
#   bin/run-batch.sh voice   SCRIPT.md OUT.wav
#   bin/run-batch.sh render  PLAN.json OUT.mp4 [AUDIO_DIR]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:?usage: run-batch.sh <voice|render> ...}"; shift

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# caffeinate -i prevents idle sleep; -m keeps disks spinning. It exits with the
# child, so the assertion is released the moment the job ends.
CAF=(caffeinate -i -m)

case "$MODE" in
  voice)
    SCRIPT="${1:?script}"; OUT="${2:?out.wav}"
    [ -x .venv-tts/bin/python ] || { echo "NAMED STOP: .venv-tts missing; voice not installed" >&2; exit 1; }
    log "voice: $SCRIPT -> $OUT (this is slow; ~1.6h per 8min script)"
    "${CAF[@]}" .venv-tts/bin/python voice/synth.py "$SCRIPT" "$OUT" \
        --reference voice/reference_A_clean.wav --auto-window
    ;;
  render)
    PLAN="${1:?plan.json}"; OUT="${2:?out.mp4}"; ADIR="${3:-}"
    log "render: $PLAN -> $OUT"
    if [ -n "$ADIR" ]; then
      "${CAF[@]}" .venv/bin/python visuals/assemble.py "$PLAN" "$OUT" --audio-dir "$ADIR"
    else
      "${CAF[@]}" .venv/bin/python visuals/assemble.py "$PLAN" "$OUT"
    fi
    ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac
log "done: $OUT"
