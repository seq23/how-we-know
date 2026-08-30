#!/usr/bin/env bash
# Thursday 02:00, on the Mac. Upload each rendered video as PRIVATE, capture
# the video IDs, push the receipts.
#
# Upload runs here rather than in Actions for the same reason the render does:
# the MP4 never leaves the machine that made it, and a 200 MB artefact upload
# on the free tier is a bill waiting to happen.
#
#   bin/loop-thursday.sh
#   bin/loop-thursday.sh --dry-run
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="$ROOT/.venv/bin/python"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

log(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

WEEK="$($PY -c "import sys;sys.path.insert(0,'loop');from common import week_id;print(week_id())")"
log "week $WEEK  dry-run=$DRY"

if [ "$DRY" -eq 0 ]; then
  git pull --rebase --autostash || { echo "NAMED STOP [GIT_PULL_FAILED]" >&2; exit 3; }
fi

# The breaker is checked inside upload.py as well; checking here too means a
# tripped breaker costs nothing and reads clearly in the launchd log.
$PY loop/breaker.py guard --stage thu-upload || exit $?

# caffeinate: a four-video upload can outlast the idle-sleep timer.
caffeinate -i -m "$PY" loop/upload.py
rc=$?

if [ "$DRY" -eq 0 ]; then
  git add loop/render_queue.json loop/receipts loop/state 2>/dev/null
  if git diff --cached --quiet; then
    log "nothing to commit"
  else
    git commit -q -m "loop($WEEK): upload lane — receipts" \
      -m "Uploaded PRIVATE. Friday's workflow flips to public only against a receipt." \
      && git push -q && log "pushed receipts"
  fi
fi

# rc 3 is a NAMED STOP (usually OAUTH_MISSING) — surfaced, already committed,
# and deliberately not swallowed.
exit $rc
