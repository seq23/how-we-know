#!/usr/bin/env bash
# Assemble every queued episode as soon as its narration completes.
#
# Runs unattended. Rendering is a Mac-side stage the loop cannot do in GitHub
# Actions - the voice model is local - so a video that only exists when someone
# types a command is not a deliverable. This walks the publish queue in order and
# waits per episode.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY=.venv/bin/python
LOCK="renders/.assemble-all.lock"
mkdir "$LOCK" 2>/dev/null || { echo "another assembler holds $LOCK"; exit 0; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

done_n=0
for slug in 10-what-is-the-deepest-part-of-the-ocean \
            05-why-many-deep-sea-creatures-are-red \
            01-why-deep-sea-creatures-look-so-weird \
            14-how-big-is-a-colossal-squid \
            20-what-is-the-midnight-zone \
            06-why-some-deep-sea-creatures-are-transparent \
            07-why-deep-sea-creatures-get-creepier-deeper \
            15-how-do-people-reach-challenger-deep \
            08-what-creatures-live-in-the-deep-sea \
            09-what-is-the-scariest-deep-sea-creature \
            19-what-is-the-deepest-fish-ever-recorded \
            18-why-does-black-smoker-water-not-boil \
            04-why-deep-sea-creatures-are-so-scary \
            16-what-happens-when-a-whale-dies-in-the-deep-ocean \
            13-how-does-bioluminescence-work-in-the-deep-sea \
            02-how-deep-sea-creatures-survive-pressure; do
  out="renders/${slug}-final.mp4"
  [ -s "$out" ] && { echo "SKIP $slug"; done_n=$((done_n+1)); continue; }
  want=$($PY -c "import sys;sys.path.insert(0,'visuals');import planner;print(len(planner.plan('scripts/$slug.md')))" 2>/dev/null)
  [ -z "$want" ] && { echo "NO PLAN $slug"; continue; }
  # The beat count must equal the plan exactly. assemble.py muxes audio only when
  # they match, and a short directory yields a SILENT video rather than an error.
  waited=0
  while :; do
    have=$(find "audio/$slug" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
    [ "$have" -ge "$want" ] && break
    sleep 90; waited=$((waited+90))
    [ "$waited" -gt 43200 ] && { echo "TIMEOUT $slug at $have/$want"; break; }
  done
  have=$(find "audio/$slug" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
  [ "$have" -lt "$want" ] && continue
  echo "ASSEMBLING $slug ($have/$want)"
  if $PY visuals/assemble.py "plans/$slug.json" "$out" --audio-dir "audio/$slug" \
       >"/tmp/claude-501/asm-$slug.log" 2>&1; then
    echo "OK $out"; done_n=$((done_n+1))
  else
    echo "FAIL $slug - see /tmp/claude-501/asm-$slug.log"
  fi
done
echo "---"
echo "assembled or already present: $done_n"
[ "$done_n" -eq 0 ] && { echo "Rule 0: assembled nothing"; exit 1; }
exit 0
