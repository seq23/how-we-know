#!/usr/bin/env bash
# Run one loop stage inside GitHub Actions, and make its outcome visible.
#
# Every Actions-side stage goes through here so that the three outcomes are
# handled identically, once:
#
#   exit 0  real work happened          → commit, push, green
#   exit 3  NAMED STOP                  → commit, push, open/update an issue,
#                                         then FAIL the job so the owner is
#                                         emailed. A stop nobody sees is a
#                                         silent no-op wearing a label.
#   other   genuine failure             → commit anything salvageable, open an
#                                         issue, fail.
#
#   bin/loop-stage.sh <stage-name> <python-file> [args…]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="${LOOP_PYTHON:-python3}"

STAGE="${1:?usage: loop-stage.sh <stage> <file.py> [args…]}"; shift
FILE="${1:?usage: loop-stage.sh <stage> <file.py> [args…]}"; shift

echo "::group::$STAGE"
"$PY" "$FILE" "$@"
RC=$?
echo "::endgroup::"

WEEK="$("$PY" -c "import sys;sys.path.insert(0,'loop');from common import week_id;print(week_id())")"

# ---------------------------------------------------------------- commit
git config user.name  "how-we-know loop"
git config user.email "loop@users.noreply.github.com"
# research/ is another agent's directory and the loop never edits it - but the
# weekly scoring stage RUNS that agent's entrypoint, which rewrites
# publish_order.json. Committing the result is how the ranking reaches the Mac.
git add loop docs 2>/dev/null
if [ "$STAGE" = "weekly-score" ]; then git add research/publish_order.json 2>/dev/null; fi
if git diff --cached --quiet; then
  echo "no repo changes to commit"
else
  case $RC in
    0) MSG="loop($WEEK): $STAGE" ;;
    3) MSG="loop($WEEK): $STAGE — named stop" ;;
    *) MSG="loop($WEEK): $STAGE — failed (rc=$RC)" ;;
  esac
  git commit -q -m "$MSG"
  # Another stage, or the Mac, may have pushed while this ran. Rebase, never force.
  for i in 1 2 3; do
    git pull --rebase -q && git push -q && { echo "pushed"; break; }
    echo "push attempt $i failed; retrying"
    sleep 5
  done
fi

# ---------------------------------------------------------------- surface
if [ "$RC" -ne 0 ] && command -v gh >/dev/null 2>&1 && [ -n "${GITHUB_TOKEN:-}" ]; then
  STOPFILE="loop/state/stops/$WEEK-$STAGE.json"
  TITLE="loop: $STAGE needs you — $WEEK"
  BODY_FILE="$(mktemp)"
  {
    if [ "$RC" -eq 3 ]; then
      echo "The **$STAGE** stage took a NAMED STOP for week \`$WEEK\`."
      echo
      echo "This is a legitimate, named halt — not a crash and not a silent skip."
    else
      echo "The **$STAGE** stage FAILED for week \`$WEEK\` with exit code $RC."
    fi
    echo
    if [ -f "$STOPFILE" ]; then
      echo '```json'; cat "$STOPFILE"; echo '```'
    fi
    echo
    echo "Run: <${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}>"
  } > "$BODY_FILE"

  EXISTING="$(gh issue list --state open --label loop-stop \
      --search "$TITLE in:title" --json number --jq '.[0].number' 2>/dev/null)"
  if [ -n "$EXISTING" ] && [ "$EXISTING" != "null" ]; then
    gh issue comment "$EXISTING" --body-file "$BODY_FILE" >/dev/null \
      && echo "commented on issue #$EXISTING"
  else
    gh issue create --title "$TITLE" --body-file "$BODY_FILE" \
      --label loop-stop >/dev/null 2>&1 \
      || gh issue create --title "$TITLE" --body-file "$BODY_FILE" >/dev/null
    echo "opened a stop issue"
  fi
fi

# A named stop fails the job on purpose: a failed run is the one notification
# that reaches the owner for $0.
exit $RC
