#!/usr/bin/env bash
# Drop a video from this week. Optional - nothing waits for it.
#
# Topic selection is automatic and POV lines come from the owner's own bank, so
# there is no approval step. This is the veto, for when she looks at the week
# and actively wants one gone. The window closes Tuesday 02:00, when the Mac
# starts rendering.
#
#   bin/loop-override.sh                              # show this week
#   bin/loop-override.sh 2026-W36 --drop <slug>       # drop one
#   bin/loop-override.sh 2026-W36 --drop a --drop b   # drop several
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="$ROOT/.venv/bin/python"

WEEK="${1:-}"
if [ -z "$WEEK" ] || [ "$WEEK" = "--show" ]; then
  WEEK="$($PY -c "import sys;sys.path.insert(0,'loop');from common import week_id;print(week_id())")"
  "$PY" - <<'PYEOF'
import json, pathlib
q = json.loads(pathlib.Path("loop/render_queue.json").read_text())
print(f"\nweek {q['week']} - {len(q['items'])} video(s), picked automatically")
a = q.get("authoring", {})
if a.get("generated_this_week"):
    print(f"  {a['generated_this_week']} authored by {a.get('model')} "
          f"for ${a.get('cost_usd')}")
print()
for i in q["items"]:
    mark = "DROPPED " if i.get("status") == "dropped" else "        "
    origin = "LLM " if i.get("generated") else "human"
    print(f"  {mark}[{origin}] {i['slug']}")
    print(f"            pov {i.get('pov_id')} - {(i.get('pov_line') or '')[:64]}")
print("\nTo drop one:  bin/loop-override.sh %s --drop <slug>\n" % q["week"])
PYEOF
  exit 0
fi
shift

"$PY" loop/override.py --week "$WEEK" "$@" --by "$(git config user.name || echo owner)"

git add loop/render_queue.json loop/state
git diff --cached --quiet || {
  git commit -q -m "loop($WEEK): owner override applied"
  git push -q && echo "pushed"
}
