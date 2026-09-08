#!/usr/bin/env bash
# Run one loop stage inside GitHub Actions, and make its outcome visible.
#
# Every Actions-side stage goes through here so that the three outcomes are
# handled identically, once:
#
#   exit 0  real work happened, OR a    → commit, push, green
#           SELF-RESOLVING named stop,
#           OR a HELD one
#   exit 3  NAMED STOP that needs a     → commit, push, open/update an issue,
#           human                         then FAIL the job so the owner is
#                                         emailed. A stop nobody sees is a
#                                         silent no-op wearing a label.
#   other   genuine failure             → commit anything salvageable, open an
#                                         issue, fail.
#
# THE HELD CASE. A halt only the OWNER can clear is exit 3 the first time and
# must not be exit 3 every morning after, on an unchanged fact, in an issue that
# is already open. loop/held.py decides that; the stage writes "held" into the
# same `disposition` field, so this wrapper treats it exactly like the
# self-resolving case: commit, push, green, no second issue. The difference is
# entirely in the banner, which says HELD STOP and lists what is held.
#
# Two things below exist only for it:
#   * the `loop-stop` LABEL is created if it does not exist. It never did, so
#     `gh issue list --label loop-stop` matched nothing and every single stop
#     opened a BRAND NEW issue instead of commenting on the open one - issues
#     #17 and #20 (cloud-upload) and #26 and #29 (mon-draft) are the same stop
#     twice, hours apart. "Already reported" is meaningless while that is true.
#   * the issue number is written back into the hold, because a held run has to
#     be able to say WHERE it is tracked; a hold with no issue pages instead.
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
# LOOP_STOPS_DIR is how loop/common.py lets a test watch a real stage take a
# real stop without writing the loop's own state. This has to honour it too, or
# the wrapper reads an empty disposition under test and the two halves of the
# contract can never be exercised together.
STOPS_DIR="${LOOP_STOPS_DIR:-loop/state/stops}"
STOPFILE="$STOPS_DIR/$WEEK-$STAGE.json"
DISPOSITION=""
STOP_CODE=""
ISSUE_NUMBER=""
# Read the code on EVERY stop, not only the green ones. It used to be read only
# when RC was 0, because nothing downstream needed it otherwise; the issue-number
# write-back below needs it precisely when the stop PAGED (RC=3).
if [ -f "$STOPFILE" ]; then
  DISPOSITION="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('disposition',''))" "$STOPFILE" 2>/dev/null || echo "")"
  STOP_CODE="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('code',''))" "$STOPFILE" 2>/dev/null || echo "")"
  if [ "$DISPOSITION" = "self_resolving" ]; then
    echo "self-resolving named stop [$STOP_CODE] — recorded, committed, and NOT"
    echo "escalated. It is in the job summary above. Exiting 0 on purpose."
  fi
  # THE THIRD DISPOSITION. Owner instruction, 2026-09-08: a named stop must
  # never arrive as a red build. A condition only she can clear (a revoked
  # consent, a platform-side account flag) cannot self-heal and cannot be
  # retried away -- but failing this job every day until she gets to it is the
  # alarm nobody reads. It stays GREEN here and is carried in
  # loop/state/owner_action.json, which the Sunday digest prints at the top.
  # loop/common.py escalates it to exit 3 if it outlives its max_consecutive,
  # so a forgotten block still becomes loud eventually.
  if [ "$DISPOSITION" = "owner_action" ]; then
    echo "named stop [$STOP_CODE] is WAITING ON THE OWNER — recorded in"
    echo "loop/state/owner_action.json and surfaced in the Sunday digest."
    echo "Green on purpose: she cannot act on a failed build any faster than"
    echo "she can act on the digest, and a daily red run is how a real alarm"
    echo "gets tuned out."
  fi
  if [ "$DISPOSITION" = "held" ]; then
    echo "HELD named stop [$STOP_CODE] — this is NOT resolved. It is waiting on"
    echo "the owner, she has already been told, and the item list has not"
    echo "changed since, so this run does not report it a second time. The full"
    echo "HELD STOP banner above names every item and the issue tracking it."
  fi
fi


# ------------------------------------------------------- push, with retries
# A FUNCTION because it is now needed twice: once for the stage's own work,
# and once more to write the issue number back into a held stop (see THE HELD
# CASE at the top). Duplicating a retry loop whose every line encodes a
# separately-learned lesson is how one copy silently loses them.
#
# Sets PUSHED=1 only when a push actually LANDED. Never infers it.
push_with_retries() {
  PUSHED=0
  for i in 1 2 3; do
    if git pull --rebase -q && git push -q; then
      echo "pushed"
      PUSHED=1
      return 0
    fi
    echo "push attempt $i failed; retrying"
    # A failed `git pull --rebase` can leave a rebase in progress (a real
    # conflict the merge driver did not or could not resolve). The NEXT
    # `git pull --rebase` in this same loop then fails for a completely
    # different, confusing reason ("Please specify which branch you want to
    # rebase against") because git refuses to start a new rebase on top of an
    # unfinished one - so every attempt after the first was guaranteed to
    # fail regardless of whether the conflict itself was resolvable. Clear it
    # before retrying.
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      CONFLICTED="$(git diff --name-only --diff-filter=U 2>/dev/null | tr '\n' ' ')"
      echo "aborting an unresolved rebase before retrying (conflicted: ${CONFLICTED:-unknown})"
      if ! git rebase --abort 2>/dev/null; then
        git merge --abort 2>/dev/null
      fi
    fi
    sleep 5
  done
  return 1
}

# ---------------------------------------------------------------- commit
git config user.name  "how-we-know loop"
git config user.email "loop@users.noreply.github.com"
# research/ is another agent's directory and the loop never edits it - but the
# weekly scoring stage RUNS that agent's entrypoint, which rewrites
# publish_order.json. Committing the result is how the ranking reaches the Mac.
git add loop docs 2>/dev/null
# EVERY domain's queue file, not just deep sea's. Naming publish_order.json
# alone left research/publish_order_materials.json uncommitted after a
# weekly score, so the Mac scored a queue the repo never recorded.
if [ "$STAGE" = "weekly-score" ]; then git add research/publish_order*.json 2>/dev/null; fi
# The footage/imagery harvest writes the cleared manifests and the assets they
# describe. Without this line the lane would run every week, harvest correctly,
# and throw the result away on the runner - "runs but inert" with a green tick.
if [ "$STAGE" = "imagery-harvest" ]; then git add channel/imagery 2>/dev/null; fi
if git diff --cached --quiet; then
  echo "no repo changes to commit"
else
  case $RC in
    0) if [ "$DISPOSITION" = "self_resolving" ]; then
         MSG="loop($WEEK): $STAGE — self-resolving stop ($STOP_CODE)"
       elif [ "$DISPOSITION" = "owner_action" ]; then
         MSG="loop($WEEK): $STAGE — waiting on the owner ($STOP_CODE)"
       elif [ "$DISPOSITION" = "held" ]; then
         MSG="loop($WEEK): $STAGE — held stop ($STOP_CODE), already reported"
       else
         MSG="loop($WEEK): $STAGE"
       fi ;;
    3) MSG="loop($WEEK): $STAGE — named stop" ;;
    *) MSG="loop($WEEK): $STAGE — failed (rc=$RC)" ;;
  esac
  git commit -q -m "$MSG"

  # loop/state/quota.json can be written by two lanes within the same minute
  # (confirmed 2026-09-03: loop-upload-cloud and loop-reach both spent quota
  # and both rebased onto main seconds apart). It is derived accounting, so a
  # textual conflict on it is a false positive - the merge driver sums both
  # sides' real spends instead of picking one. Registered here, not only in
  # .gitattributes, because git will not run a merge driver COMMAND from a
  # committed file - only local config can supply that.
  git config merge.quota-union.driver \
    "python3 $ROOT/loop/tools/merge_quota_json.py %O %A %B"

  # Another stage, or the Mac, may have pushed while this ran. Rebase, never
  # force. PUSHED tracks whether a push actually landed - it is not safe to
  # infer that from "the loop exited" the way this used to: on 2026-09-03 a
  # conflict on quota.json left a rebase stuck mid-way, all three attempts
  # failed, and the loop fell through silently. Because $RC (the STAGE's own
  # exit code) is what decided the job's final exit status, a stage that had
  # itself succeeded would have gone green with its commit never pushed -
  # work silently lost the moment the runner was torn down. It also left the
  # working tree mid-rebase for whatever step runs next in the same job: the
  # captions step hitting this is what made the LOCALIZE step fail with
  # "Please specify which branch you want to rebase against" a few seconds
  # later, on an unrelated piece of work.
  PUSHED=0
  push_with_retries

  if [ "$PUSHED" -ne 1 ]; then
    # Leave the working tree clean for whatever runs next in this job, and
    # fail loudly and specifically - "push failed" alone is what a human
    # learns to ignore; naming the file is what lets them act on it without
    # reading a log.
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      git rebase --abort 2>/dev/null || true
    fi
    echo "FAIL: could not push loop($WEEK): $STAGE after 3 attempts." >&2
    echo "  The commit exists locally on this runner and nowhere else - it" >&2
    echo "  will be lost when the job ends." >&2
    if [ "$RC" -eq 0 ]; then
      # The silent case: the stage itself succeeded, so nothing else would
      # have failed this job and the lost commit would never have been seen.
      # $STOP_CODE/$DISPOSITION describe the STAGE's own outcome (rc=0), which
      # no longer matches reality once the push failed - do not let the issue
      # below claim a clean run.
      echo "  The stage itself (rc=0) would otherwise have gone green with" >&2
      echo "  this work never reaching origin. Failing the job on that" >&2
      echo "  basis alone." >&2
      RC=1
      DISPOSITION=""
    fi
  fi
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

  # THE LABEL HAS TO EXIST BEFORE IT CAN DEDUPE.
  # CONFIRMED 2026-09-07: `gh label list` on this repo returned only the ten
  # GitHub defaults. `loop-stop` was never created, so `gh issue create
  # --label loop-stop` failed every time and fell through to the unlabelled
  # fallback below - and the lookup that decides "have I already reported
  # this?" filtered on that same absent label, so it matched NOTHING and every
  # stop opened a brand new issue. #17 and #20 are one cloud-upload stop
  # reported twice in six hours; #26 and #29 are one mon-draft stop. Creating
  # the label is what makes "already reported" answerable at all.
  if ! gh label list --limit 200 --json name --jq '.[].name' \
       | grep -qx "loop-stop"; then
    echo "creating the loop-stop label (it did not exist)"
    gh label create loop-stop --color d73a4a \
      --description "A loop stage took a named stop and needs the owner"
  fi

  # DEDUPE ON THE TITLE, NOT THE LABEL. The title is the stop's identity
  # (stage + week); the label is only how a human filters the list. Matching
  # exactly, through jq's `env`, rather than GitHub's fuzzy `in:title` search:
  # the title contains a colon and an em dash, and a search that tokenises
  # them is a search that can miss its own issue and open a duplicate.
  EXISTING="$(TITLE="$TITLE" gh issue list --state open --limit 200 \
      --json number,title --jq '.[] | select(.title == env.TITLE) | .number' \
      2>/dev/null | head -1)"
  if [ -n "$EXISTING" ] && [ "$EXISTING" != "null" ]; then
    ISSUE_NUMBER="$EXISTING"
    gh issue comment "$EXISTING" --body-file "$BODY_FILE" >/dev/null \
      && echo "commented on issue #$EXISTING"
  else
    ISSUE_URL="$(gh issue create --title "$TITLE" --body-file "$BODY_FILE" \
      --label loop-stop 2>/dev/null)"
    if [ -z "$ISSUE_URL" ]; then
      ISSUE_URL="$(gh issue create --title "$TITLE" --body-file "$BODY_FILE")"
    fi
    ISSUE_NUMBER="${ISSUE_URL##*/}"
    echo "opened a stop issue: ${ISSUE_URL:-unknown}"
  fi

  # WRITE THE ISSUE NUMBER BACK INTO THE HOLD.
  # A held stop exits 0 and prints "tracked by issue #N". It can only do that
  # if it knows N, and only this wrapper ever learns it. A hold with no issue
  # number recorded deliberately PAGES on the next run rather than claim a
  # tracker it cannot name - so failing to write this is loud, not silent.
  if [ "$RC" -eq 3 ] && [ -n "$STOP_CODE" ] \
     && printf '%s' "$ISSUE_NUMBER" | grep -qE '^[0-9]+$'; then
    if "$PY" loop/held.py --record-issue "$STAGE" "$STOP_CODE" "$ISSUE_NUMBER"; then
      # Always the REPO path: when LOOP_STOPS_DIR points a test somewhere
      # else there is nothing here to add, `git diff --cached` stays clean,
      # and no commit is attempted. That is the intended no-op.
      git add loop/state/stops 2>/dev/null
      if ! git diff --cached --quiet; then
        git commit -q -m "loop($WEEK): $STAGE — hold tracked by #$ISSUE_NUMBER"
        push_with_retries
      fi
    fi
  fi
fi

# A named stop that needs a human fails the job on purpose: a failed run is the
# one notification that reaches the owner for $0. A self-resolving one already
# exited 0 above and is green by design — see THE SELF-RESOLVING CASE.
exit $RC
