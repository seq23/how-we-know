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
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

WEEK="$(date -u +%G-W%V)"
STOPDIR="loop/state/stops"

# A NAMED STOP NOBODY SEES IS NOT A NAMED STOP. This script exited 3 with only
# an echo, so the failure below repeated silently from 2026-09-03 to 09-05 while
# `launchctl list` showed a bare "3" and nothing else. loop/digest.py reads
# loop/state/stops/<week>-<stage>.json, so writing one here puts the failure in
# the Sunday email like every other lane's.
named_stop() {   # named_stop CODE MESSAGE UNBLOCK
  mkdir -p "$STOPDIR"
  python3 - "$STOPDIR/$WEEK-backfill.json" "$1" "$2" "$3" <<'PYEOF'
import json, sys, datetime
path, code, message, unblock = sys.argv[1:5]
json.dump({"stage": "backfill", "week": path.split("/")[-1].split("-backfill")[0],
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "code": code, "message": message, "unblock": unblock,
           "disposition": "needs_human",
           "disposition_why": f"'{code}' is not in loop/stop_policy.json, so it "
                              f"is treated as needing a human. That is the "
                              f"default on purpose.",
           "exit_code": 3, "work_done_before_stop": [], "notes": []},
          open(path, "w"), indent=2)
PYEOF
  echo "NAMED STOP [$1]: $2"
  echo "  unblock: $3"
  echo "  recorded -> $STOPDIR/$WEEK-backfill.json (the Sunday digest reports it)"
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
    exit 3
  fi
done

if ! git pull --rebase --autostash origin main 2>&1 | tail -2; then
  named_stop "PULL_FAILED" \
    "could not pull before uploading. Refusing to act on a possibly stale ledger - a duplicate public video is worse than a skipped day." \
    "Run 'git pull --rebase origin main' here and resolve what it reports. The next run picks this up unchanged."
  exit 3
fi

# THE SAME GATE THE R2 PATH GOT, ON THE PATH THAT ACTUALLY UPLOADS FROM HERE.
# bin/batch-session.sh checks V13 and V24 before pushing to R2. This script is
# the OTHER upload lane out of this Mac and had no check at all, so a clipped or
# under-length render could go straight to YouTube from here while the R2 path
# was carefully refusing it.
if ! .venv/bin/python -c "
import sys; sys.path.insert(0,'loop')
import validate
bad = []
for f in (validate.v13_render_not_clipped, validate.v24_render_duration_floor):
    d = f().as_dict()
    bad += d.get('failures') or []
if bad:
    print('\n'.join('  ' + b for b in bad[:6]))
    sys.exit(1)
"; then
  named_stop "RENDER_GATE_FAILED" \
    "a finished render is clipped or under the runtime floor, so nothing was uploaded this run." \
    "Run loop/extend.py for a short script, or re-render a clipped one. The listed episodes must not reach YouTube."
  exit 3
fi

.venv/bin/python loop/backfill.py --limit 4
rc=$?

if ! git diff --quiet -- loop/state/ledger.json loop/state/quota.json 2>/dev/null; then
  git add loop/state/ledger.json loop/state/quota.json
  git commit -m "backfill: uploads from the Mac $(date +%Y-%m-%d)" >/dev/null
  git push origin main 2>&1 | tail -1 || echo "  push failed; next run rebases"
  echo "  ledger pushed so the cloud lane sees these uploads"
fi
exit $rc
