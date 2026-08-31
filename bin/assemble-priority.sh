#!/usr/bin/env bash
# Assemble each priority episode as soon as its narration is complete.
# Runs unattended: the coordinator may be disconnected when voice finishes,
# and a video that only exists if someone types a command is not a deliverable.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY=.venv/bin/python
for slug in 14-how-big-is-a-colossal-squid \
            10-what-is-the-deepest-part-of-the-ocean \
            05-why-many-deep-sea-creatures-are-red; do
  out="renders/${slug}-final.mp4"
  [ -s "$out" ] && { echo "SKIP $slug (already assembled)"; continue; }
  want=$($PY -c "import sys;sys.path.insert(0,'visuals');import planner;print(len(planner.plan('scripts/$slug.md')))" 2>/dev/null)
  # Wait for narration. The beat count must match the plan exactly: assemble.py
  # muxes audio only when they are equal, and a short directory yields a SILENT
  # video rather than an error. That is how episode 1 nearly shipped mute.
  while :; do
    have=$(find "audio/$slug" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
    [ "$have" -ge "$want" ] && break
    sleep 60
  done
  echo "ASSEMBLING $slug ($have/$want beats)"
  $PY visuals/assemble.py "plans/$slug.json" "$out" --audio-dir "audio/$slug" >"/tmp/claude-501/asm-$slug.log" 2>&1 \
    && echo "OK $out" || echo "FAIL $slug"
done
echo "ALL PRIORITY EPISODES ASSEMBLED"
