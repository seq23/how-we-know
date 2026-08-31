#!/usr/bin/env bash
# Render every script to silent video. Catches visual defects across the whole
# set - rendering ONE video today surfaced three bugs that no amount of reading
# the plan JSON revealed.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
mkdir -p renders plans
# RENDER LOCK: two concurrent batches raced through the same loop and wrote the
# same output paths. One render at a time, always.
LOCK="renders/.render.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "ANOTHER RENDER IS ALREADY RUNNING (lock: $LOCK). Refusing to start a second."
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
ok=0; fail=0
for f in scripts/*.md; do
  n=$(basename "$f" .md)
  # SKIP EXISTING: a crashed batch must resume, not restart from zero. Only a
  # non-empty final mp4 counts as done; a leftover .work dir does not.
  if [ -s "renders/$n.mp4" ]; then echo "SKIP $n (already rendered)"; ok=$((ok+1)); continue; fi
  .venv/bin/python -c "
import sys,json; sys.path.insert(0,'visuals')
import planner
json.dump(planner.plan('$f'), open('plans/$n.json','w'), indent=2)
" || { echo "PLAN FAIL $n"; fail=$((fail+1)); continue; }
  if caffeinate -i -m .venv/bin/python visuals/assemble.py "plans/$n.json" "renders/$n.mp4" --no-music >/dev/null 2>&1; then
    d=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "renders/$n.mp4" 2>/dev/null)
    printf "OK   %-52s %5.1f min\n" "$n" "$(echo "$d/60" | bc -l)"
    ok=$((ok+1))
  else
    echo "RENDER FAIL $n"; fail=$((fail+1))
  fi
done
echo "---"; echo "rendered $ok, failed $fail"
