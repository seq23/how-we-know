#!/usr/bin/env bash
# Tuesday 02:00, on the Mac. The muscle half of the loop.
#
#   pull  →  prepare  →  synthesise  →  plan  →  render  →  receipts  →  push
#
# Voice and render live here and nowhere else, for one reason that is not
# negotiable: the owner's voice reference is her biometrics and never leaves
# this machine. The model weights (1–3 GB) would also blow the free tier.
#
# The only input is loop/render_queue.json, pulled from git. There is no server
# and no webhook — git is the message bus, and this script is the subscriber.
#
#   bin/loop-tuesday.sh            # the real run
#   bin/loop-tuesday.sh --dry-run  # everything except voice, render and push
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="$ROOT/.venv/bin/python"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

log(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
stop(){ printf '\n=== NAMED STOP [%s] loop-tuesday ===\n%s\n\n' "$1" "$2" >&2; exit 3; }

WEEK="$($PY -c "import sys;sys.path.insert(0,'loop');from common import week_id;print(week_id())")"
log "week $WEEK  dry-run=$DRY"

# ---------------------------------------------------------------- 1. pull
if [ "$DRY" -eq 0 ]; then
  log "pulling the queue Actions wrote on Monday"
  git pull --rebase --autostash || stop GIT_PULL_FAILED \
    "could not pull. Resolve by hand; the Mac must never render against a stale queue."
fi

# ---------------------------------------------------------------- 2. gates
$PY loop/breaker.py guard --stage tue-render || exit $?

Q="loop/render_queue.json"
[ -f "$Q" ] || stop NO_QUEUE "no $Q. Monday's Actions run did not produce a week."

$PY loop/prepare.py || exit $?

# bash 3.2 on stock macOS has no `mapfile`; read the list the portable way.
SLUGS=()
while IFS= read -r line; do [ -n "$line" ] && SLUGS+=("$line"); done < <($PY - <<'PY'
import json
q = json.load(open("loop/render_queue.json"))
for it in q["items"]:
    if it.get("status") in ("approved", "render-suspect"):
        print(it["slug"])
PY
)
if [ "${#SLUGS[@]}" -eq 0 ]; then
  stop NOTHING_TO_RENDER \
"the queue holds no approved row. This is a real week with zero output — it is
being surfaced, not skipped. Check loop/state/stops/ and the approval page."
fi
log "${#SLUGS[@]} approved video(s) to build"

# ---------------------------------------------------------------- 3. build
ok=0; failed=()
for slug in "${SLUGS[@]}"; do
  log "── $slug"
  SRC="loop/work/$slug.md"
  ADIR="audio/$slug"
  PLAN="loop/plans/$slug.json"
  OUT="renders/$slug.mp4"
  mkdir -p "$ADIR" loop/plans renders

  if [ "$DRY" -eq 1 ]; then
    log "  dry-run: would synthesise $SRC -> $ADIR"
  else
    # Voice: ~1.6 h per 8-minute script. Four scripts finish inside the window
    # between 02:00 Tuesday and Thursday's upload; caffeinate keeps the Mac up.
    if ! bin/run-batch.sh voice "$SRC" "$ADIR/master.wav"; then
      log "  VOICE FAILED"; failed+=("$slug:voice"); continue
    fi
  fi

  # Plan from the *work copy*, so the plan matches exactly what was spoken.
  if ! $PY -c "
import sys, json; sys.path.insert(0, 'visuals')
try: import segments_ext2
except Exception: pass
import planner
json.dump(planner.plan('$SRC'), open('$PLAN', 'w'), indent=2)
"; then
    log "  PLAN FAILED"; failed+=("$slug:plan"); continue
  fi
  log "  planned -> $PLAN"

  if [ "$DRY" -eq 1 ]; then
    log "  dry-run: would render $PLAN -> $OUT"; ok=$((ok+1)); continue
  fi

  if ! bin/run-batch.sh render "$PLAN" "$OUT" "$ADIR"; then
    log "  RENDER FAILED"; failed+=("$slug:render"); continue
  fi

  if ! $PY loop/receipt.py render --slug "$slug" --week "$WEEK" >/dev/null; then
    log "  RECEIPT UNHEALTHY"; failed+=("$slug:receipt"); continue
  fi
  log "  receipt written"
  ok=$((ok+1))
done

# ---------------------------------------------------------------- 4. report
log "built $ok, failed ${#failed[@]}"
if [ ${#failed[@]} -gt 0 ]; then
  printf '  failed: %s\n' "${failed[*]}"
  $PY loop/breaker.py trip --cause validator \
      --detail "tue-render failures: ${failed[*]}"
fi

if [ "$ok" -eq 0 ]; then
  stop RENDERED_NOTHING \
"every approved video failed to build. Publishing is halted by the breaker.
Rule 0: this stage will not exit 0 having produced nothing."
fi

# ---------------------------------------------------------------- 5. push
if [ "$DRY" -eq 1 ]; then log "dry-run complete; nothing pushed"; exit 0; fi

git add loop/render_queue.json loop/receipts loop/state loop/work 2>/dev/null
if git diff --cached --quiet; then
  log "nothing to commit"
else
  git commit -q -m "loop($WEEK): rendered $ok video(s) on the Mac" \
    -m "Receipts in loop/receipts/. Voice and render stay local by design." \
    && git push -q && log "pushed"
fi
log "done"
