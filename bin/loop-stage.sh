#!/usr/bin/env bash
# Run one loop stage inside GitHub Actions, and make its outcome visible.
#
# Every Actions-side stage goes through here so that the three outcomes are
# handled identically, once:
#
#   exit 0  real work happened, OR a    → commit, push, green
#           SELF-RESOLVING named stop
#   exit 3  NAMED STOP that needs a     → commit, push, open/update an issue,
#           human                         then FAIL the job so the owner is
#                                         emailed. A stop nobody sees is a
#                                         silent no-op wearing a label.
#   other   genuine failure             → commit anything salvageable, open an
#                                         issue, fail.
#
# THE SELF-RESOLVING CASE. `loop/stop_policy.json` decides; the stage writes the
# verdict into loop/state/stops/<week>-<stage>.json as "disposition". A daily
# lane that finds the day's YouTube quota spent has nothing for a human to do
# and says so — failing that job (and commenting on the issue again) every day
# is how a real alert gets tuned out. It stays green here, and the banner plus
# the job summary still carry the stop. It is NOT a silent skip: the record is
# committed, and the policy escalates to exit 3 if it keeps happening.
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

# ------------------------------------------------------------- disposition
# Exit 0 now has two meanings, and the commit message and the issue policy have
# to tell them apart. The stage already wrote the verdict down; read it rather
# than re-deriving it here, so there is exactly one classifier.
STOPFILE="loop/state/stops/$WEEK-$STAGE.json"
DISPOSITION=""
STOP_CODE=""
if [ "$RC" -eq 0 ] && [ -f "$STOPFILE" ]; then
  DISPOSITION="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('disposition',''))" "$STOPFILE" 2>/dev/null || echo "")"
  STOP_CODE="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('code',''))" "$STOPFILE" 2>/dev/null || echo "")"
  if [ "$DISPOSITION" = "self_resolving" ]; then
    echo "self-resolving named stop [$STOP_CODE] — recorded, committed, and NOT"
    echo "escalated. It is in the job summary above. Exiting 0 on purpose."
  fi
fi

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
    0) if [ "$DISPOSITION" = "self_resolving" ]; then
         MSG="loop($WEEK): $STAGE — self-resolving stop ($STOP_CODE)"
       else
         MSG="loop($WEEK): $STAGE"
       fi ;;
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
  TITLE="loop: $STAGE needs you — $WEEK"
  BODY_FILE="$(mktemp)"
  {
    # @-mention the owner. GitHub's DEFAULT notification setting for your own
    # repositories is "Participating and @mentions" - an issue opened by Actions
    # is neither, so without this line the issue appears silently in the repo
    # and no email is ever sent. This is the only thing that makes a named stop
    # reach a human who is not looking at GitHub, which is the entire point of
    # a named stop.
    echo "@${OWNER_HANDLE:-seq23}"
    echo
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

# A named stop that needs a human fails the job on purpose: a failed run is the
# one notification that reaches the owner for $0. A self-resolving one already
# exited 0 above and is green by design — see THE SELF-RESOLVING CASE.
exit $RC
