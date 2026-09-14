#!/usr/bin/env bash
# Upload finished episodes from this Mac, sharing one ledger with the cloud lane.
#
# WHY THE PULL AND PUSH MATTER MORE THAN THE UPLOAD. Two lanes can now upload:
# this one and .github/workflows/loop-upload-cloud.yml. They decide what is left
# by reading loop/state/ledger.json. If this Mac reads a stale local copy it will
# re-upload episodes the cloud already published - duplicate public videos, the
# same two-lists-no-link failure this repo keeps hitting.
#
# So: PULL before deciding, PUSH after acting. Then whichever lane runs first
# does the work and the other simply finds nothing pending. Neither has to know
# the other exists, and neither has to be disarmed.
#
# It ends by itself: when every queued episode is uploaded, backfill.py finds
# nothing and exits 0 having said so.
#
# ─── 2026-09-13: what a week of silence taught this script ─────────────────
#
# From 6 September, nine finished materials episodes shipped nothing. Three
# things conspired, and each is answered below, in the step that answers it:
#
#   1. The render gate was ALL-OR-NOTHING. One episode six seconds under the
#      floor and the script refused every other one. -> loop/render_gate.py
#      holds the failing slug and lets the rest ship.
#   2. The short episode's self-heal (loop/extend.py) existed and nothing
#      invoked it from here. -> the gate runs it (--heal) for each held slug.
#   3. The pull failed every morning on loop-state files the cloud had started
#      tracking, PULL_FAILED was not classified, and the stop file never left
#      this Mac - so the Sunday digest, which runs in the cloud, never saw it.
#      -> loop/mac_sync.py takes upstream for loop-state, PULL_FAILED is in
#      loop/stop_policy.json, and every run ends by pushing its stop file and
#      a heartbeat the digest reads.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=.venv/bin/python
WEEK="$(date -u +%G-W%V)"
STOPDIR="loop/state/stops"
LANE=backfill

# A NAMED STOP NOBODY SEES IS NOT A NAMED STOP. This script exited 3 with only
# an echo, so the failure below repeated silently from 2026-09-03 to 09-05 while
# `launchctl list` showed a bare "3" and nothing else. loop/digest.py reads
# loop/state/stops/<week>-<stage>.json, so writing one here puts the failure in
# the Sunday email like every other lane's - PROVIDED it reaches the repository,
# which `report` below guarantees.
named_stop() {   # named_stop CODE MESSAGE UNBLOCK
  mkdir -p "$STOPDIR"
  python3 - "$STOPDIR/$WEEK-$LANE.json" "$1" "$2" "$3" <<'PYEOF'
import json, sys, datetime
path, code, message, unblock = sys.argv[1:5]
json.dump({"stage": "backfill", "week": path.split("/")[-1].split("-backfill")[0],
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "code": code, "message": message, "unblock": unblock,
           "disposition": "needs_human",
           "disposition_why": f"'{code}' is classified needs_human in "
                              f"loop/stop_policy.json: a defect, not a wait.",
           "exit_code": 3, "work_done_before_stop": [], "notes": []},
          open(path, "w"), indent=2)
PYEOF
  echo "NAMED STOP [$1]: $2"
  echo "  unblock: $3"
  echo "  recorded -> $STOPDIR/$WEEK-$LANE.json (the Sunday digest reports it)"
}

# EVERY EXIT REPORTS. Whatever happened above, the heartbeat and this week's
# stop files are committed and pushed, so a Mac that is stuck says so in the
# repository the cloud digest reads - never only in a log on this disk.
report() {   # report OK UPLOADED HELD PENDING
  $PY loop/mac_sync.py heartbeat --lane $LANE --ok "$1" --uploaded "$2" \
      --held "$3" --pending "$4" 2>&1 | tail -1
  $PY loop/mac_sync.py push --lane $LANE loop/state/ledger.json loop/state/quota.json 2>&1 | tail -1
}

# A LEFT-OVER REBASE BLOCKS EVERY FUTURE RUN, FOR EVER. `git pull --rebase`
# leaves .git/rebase-merge behind when it conflicts, and every subsequent pull
# then fails the same way with no signal. That is exactly what happened: a
# rebase from a deleted branch sat there from 09:00 on 2026-09-05 and three
# finished episodes went un-uploaded.
#
# Only cleared when it is SAFE to: HEAD attached, no unmerged files, and the
# state older than 30 minutes so an interactive rebase a human is in the middle
# of is never stomped. `--quit` rather than `--abort` because abort would check
# out whatever branch the stale rebase named and move HEAD off main.
for d in .git/rebase-merge .git/rebase-apply; do
  [ -d "$d" ] || continue
  if [ -n "$(find "$d" -maxdepth 0 -mmin +30 2>/dev/null)" ] \
     && git symbolic-ref -q HEAD >/dev/null \
     && [ -z "$(git diff --name-only --diff-filter=U)" ]; then
    echo "  clearing a stale rebase left in $d (older than 30 min, HEAD attached)"
    git rebase --quit 2>/dev/null || rm -rf "$d"
  else
    named_stop "REBASE_IN_PROGRESS" \
      "a rebase is in progress in $d and it is recent or has unmerged files, so this run will not touch it." \
      "Finish or abort it by hand: git rebase --continue, or git rebase --abort."
    report 0 0 "" ""
    exit 3
  fi
done

# THE PULL TAKES UPSTREAM FOR LOOP-STATE. See loop/mac_sync.py for the week
# this failed every morning on files the cloud authors and this Mac only reads.
if ! $PY loop/mac_sync.py pull; then
  named_stop "PULL_FAILED" \
    "could not pull before uploading, even after taking upstream for loop-state. Refusing to act on a possibly stale ledger - a duplicate public video is worse than a skipped day." \
    "Run 'git pull --rebase origin main' here and resolve what it reports; it is a conflict in something a person edited, not loop state. The next run picks this up unchanged."
  report 0 0 "" ""
  exit 3
fi

# THE GATE HOLDS, IT DOES NOT HALT. loop/render_gate.py runs V13 and V24, writes
# the failing slugs to loop/state/render_hold.json - which loop/backfill.py
# skips by name - and asks loop/extend.py to heal each one under the floor.
# Its exit code is the hold's own reporting (loud on first report, quiet while
# unchanged) and is deliberately NOT this script's: the passing episodes ship
# either way. Only RENDER_GATE_EMPTY - the gate looked at nothing - stops here.
$PY loop/render_gate.py --heal
gate_rc=$?
if [ "$gate_rc" -ne 0 ] && grep -q '"code": "RENDER_GATE_EMPTY"' "$STOPDIR/$WEEK-render-gate.json" 2>/dev/null; then
  report 0 0 "" ""
  exit 3
fi
held=$($PY -c "import sys; sys.path.insert(0,'loop'); import render_gate; print(','.join(sorted(render_gate.held_slugs())))")

before=$($PY -c "import sys,json; sys.path.insert(0,'loop'); import ledger; print(len([r for r in ledger.load()['published'] if not r.get('retired_at')]))")
$PY loop/backfill.py --limit 4
rc=$?
after=$($PY -c "import sys,json; sys.path.insert(0,'loop'); import ledger; print(len([r for r in ledger.load()['published'] if not r.get('retired_at')]))")
uploaded=$(( after - before ))
pending=$($PY -c "import sys; sys.path.insert(0,'loop'); import backfill; print(len(backfill.library_pending()))" 2>/dev/null || echo "")

ok=1; [ "$rc" -eq 0 ] || ok=0
[ "$uploaded" -gt 0 ] && echo "  ledger pushed so the cloud lane sees these uploads"
echo "  $uploaded uploaded, ${held:+held: $held}${held:-nothing held}, $pending still to ship"
report "$ok" "$uploaded" "$held" "$pending"
exit $rc
