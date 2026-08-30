#!/usr/bin/env bash
# Approve the week from the terminal, when the approval page is not to hand.
#
# The page's own button is the normal path — it opens a prefilled GitHub issue,
# which a workflow ingests. This is the same approval, expressed locally.
#
#   bin/loop-approve.sh                 # this week, every row, POV bank line
#   bin/loop-approve.sh 2026-W36        # a named week
#   bin/loop-approve.sh 2026-W36 -      # read the approval block from stdin
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="$ROOT/.venv/bin/python"

WEEK="${1:-$($PY -c "import sys;sys.path.insert(0,'loop');from common import week_id;print(week_id())")}"

if [ "${2:-}" = "-" ]; then
  exec "$PY" loop/approve.py --week "$WEEK" --by "$(git config user.name || echo owner)"
fi

"$PY" loop/approve.py --week "$WEEK" --all --by "$(git config user.name || echo owner)"

git add loop/render_queue.json loop/state
git diff --cached --quiet || {
  git commit -q -m "loop($WEEK): approved locally"
  git push -q && echo "pushed — the Mac renders at Tuesday 02:00"
}
