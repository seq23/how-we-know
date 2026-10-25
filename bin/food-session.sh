#!/usr/bin/env bash
# THE FOOD LANE'S MAC NIGHT (launchd com.howweknow.food, Tue and Thu 22:58).
#
#   bin/food-session.sh            # render the in-flight food episode, then shelve it
#   bin/food-session.sh --slug S   # a named episode (a hand proof)
#
# Food (How We Know: Food, niche #3) was approved by the owner on 13 Oct 2026
# and then nothing made its episodes: the first was rendered by a session by
# hand. This is the scheduled Mac half of the lane; loop/food_author.py
# (loop-food-author.yml, Mondays in the cloud, $0) writes the script and kits.
# loop/lanes.py lists both; V73 holds each to a runner.
#
# ONE NARRATOR. The food voice and the nightly batch's narrator both want the
# ~4 cores Chatterbox takes on this 8 GB Mac, so they never run together. This
# script takes THE SAME pid lock bin/batch-session.sh takes
# (loop/state/_local/batch.lock); it fires at 22:58, two minutes before the
# 23:00 batch, so on a food night the batch finds the lock held, says so and
# exits, and batch-resume does the same every 300 s while this runs.
#
# CADENCE, AND WHY (2026-10-25). One food episode a week, rendered over two
# nights. The long-form target is 4 a week across three niches (memory,
# docs/CHANNEL-PLAN.md), so food's share is about one; the rotation's
# Wednesday and Saturday food slots take it as it comes. A 30-minute episode
# is ~25-30 minutes of new narration - most of one 23:00-07:00 window on this
# Mac - plus five pieces to render, so it needs TWO nights, and the other five
# nights a week stay the batch's (deep sea and materials). Tuesday and
# Thursday: Monday's cloud author lane has the script ready for Tuesday, and
# Thursday's finish is shelved Friday morning, at least 24 hours ahead of
# Saturday's food slot. Everything resumes from disk, so a night that runs
# out of window is continued by the next food night.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY=.venv/bin/python
PYP="$PY"; [ -x "$PYP" ] || PYP=python3
NARRATION_UNTIL="${NARRATION_UNTIL:-07:00}"
BATCH_LOCK="${BATCH_LOCK:-$ROOT/loop/state/_local/batch.lock}"
# No bash arrays: launchd runs /bin/bash 3.2, where an EMPTY array under
# `set -u` is an "unbound variable" and kills the night (2026-10-25, the first
# fired run). A plain string, tested in loop/tests/test_every_lane_has_a_runner.py.
SLUG_OPT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --slug) SLUG_OPT="--slug $2"; shift ;;
    *) echo "usage: bin/food-session.sh [--slug SLUG]"; exit 2 ;;
  esac
  shift
done

LANE_CMD="$PY loop/food_lane.py run --until $NARRATION_UNTIL $SLUG_OPT"
echo "=== food night $(date '+%F %H:%M') ==="
if [ -n "${FOOD_SESSION_DRY:-}" ]; then echo "DRY: $LANE_CMD"; exit 0; fi

# the batch's lock, the batch's rule: a live holder that is either session
lock_holder() {
  local pid cmd
  pid=$(cat "$BATCH_LOCK" 2>/dev/null) || return 1
  [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null || return 1
  cmd=$(ps -p "$pid" -o command= 2>/dev/null) || return 1
  case "$cmd" in *batch-session*|*food-session*) echo "$pid"; return 0 ;; esac
  return 1
}
if holder=$(lock_holder); then
  echo "NAMED STOP: a batch or food session is running (pid $holder); one narrator at a time."
  exit 0
fi
mkdir -p "$(dirname "$BATCH_LOCK")"
rm -f "$BATCH_LOCK"
if ! ( set -o noclobber; echo "$$" > "$BATCH_LOCK" ) 2>/dev/null; then
  echo "NAMED STOP: lost the race for $BATCH_LOCK; one narrator at a time."
  exit 0
fi
trap '[ "$(cat "$BATCH_LOCK" 2>/dev/null)" = "$$" ] && rm -f "$BATCH_LOCK"' EXIT

# on main and current, or not at all (the batch's guard, the same named stops)
if ! "$PYP" loop/mac_sync.py guard --lane food; then
  echo "  the food night is refused; nothing was rendered."
  exit 3
fi
caffeinate -dimsu -w $$ &

echo "--- stage 1/3: render the in-flight food episode (loop/food_lane.py) ---"
$LANE_CMD
RC=$?
SLUG=$($PY -c "import json;print(json.load(open('loop/state/_local/food_lane.json')).get('slug',''))" 2>/dev/null || echo "")

if [ "$RC" -eq 0 ] && [ -n "$SLUG" ]; then
  echo "--- stage 2/3: shelve to R2 for the cloud upload lane (private, dated) ---"
  export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-8d147e242033699dd37c6f5a451f48d2}"
  $PY loop/r2.py push "$SLUG" 2>&1 | tail -20
fi

echo "--- stage 3/3: report to the repository ---"
OK=1; [ "$RC" -eq 0 ] || [ "$RC" -eq 4 ] || OK=0
$PY loop/mac_sync.py heartbeat --lane food --ok "$OK" 2>&1 | tail -1
PATHS="channel/imagery/food_clips.json channel/imagery/food_ai.json"
if [ -n "$SLUG" ]; then
  PATHS="$PATHS channel/specs/$SLUG.json channel/specs/$SLUG.proof.npz"
  PATHS="$PATHS captions/$SLUG.srt captions/$SLUG.chapters.txt"
fi
# shellcheck disable=SC2086  # word-split on purpose: paths have no spaces
$PY loop/mac_sync.py push --lane food $PATHS 2>&1 | tail -1
case $RC in
  0) echo "=== food night complete: $SLUG ready for upload $(date '+%H:%M') ===" ;;
  4) echo "=== food night ended at the window ($NARRATION_UNTIL); the next food night resumes $SLUG ===" ;;
  *) echo "=== food night stopped (rc=$RC); the named stop is above ===" ;;
esac
[ "$RC" -eq 4 ] && exit 0
exit "$RC"
