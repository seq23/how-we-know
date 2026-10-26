#!/usr/bin/env bash
# THE FOOD LANE'S MAC NIGHT (launchd com.howweknow.food, Tue and Thu 22:58).
#
#   bin/food-session.sh            # render the in-flight food episode, then shelve it
#   bin/food-session.sh --slug S   # a named episode (a hand proof)
#   bin/food-session.sh --resume-if-interrupted
#                                  # launchd com.howweknow.food-resume, every 300 s
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
#
# A NIGHT THAT DIES IS RESUMED THE SAME NIGHT (2026-10-25). The Mac went down
# at 19:25-19:56 mid-narration and the night ended with no line at all; nothing
# re-ran it until a session kickstarted it by hand. Now this script keeps the
# RUN RECORD (loop/state/_local/food_run.json, loop/food_lane.py run-begin /
# run-end): "running" once it holds the lock, "exited" on every exit it sees.
# com.howweknow.food-resume runs --resume-if-interrupted every 300 s: a
# "running" record whose session is gone is written to the food log as a death
# (FOOD_RUN_DIED, with the boot time when the Mac restarted) and resumed while
# its window lasts - through the SAME lock, so still one narrator. A signal
# names itself (FOOD_SESSION_KILLED); a lane killed by one, FOOD_LANE_KILLED.
# The network is waited for (bounded backoff) before the pull and the pushes.
# A deliberate stop that must not resume: loop/food_lane.py resume-cancel.
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
RESUME_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --slug) SLUG_OPT="--slug $2"; shift ;;
    --resume-if-interrupted) RESUME_ONLY=1 ;;
    *) echo "usage: bin/food-session.sh [--slug SLUG] [--resume-if-interrupted]"; exit 2 ;;
  esac
  shift
done

LANE_CMD="$PY loop/food_lane.py run --until $NARRATION_UNTIL $SLUG_OPT"
# FOOD_TEST_STUBS: loop/tests/test_food_resume_on_death.py drives this script
# with a stub lane and no git, R2 or report pushes.
STUBS="${FOOD_TEST_STUBS:-}"
[ -n "$STUBS" ] && LANE_CMD="${FOOD_TEST_LANE:-true}"
FL() { "$PYP" loop/food_lane.py "$@"; }
if [ -n "${FOOD_SESSION_DRY:-}" ]; then
  echo "=== food night $(date '+%F %H:%M') ==="
  [ -n "$RESUME_ONLY" ] && echo "DRY: resume gate, then $LANE_CMD" || echo "DRY: $LANE_CMD"
  exit 0
fi

# the batch's lock, the batch's rule: a live holder that is either session
lock_holder() {
  local pid cmd
  pid=$(cat "$BATCH_LOCK" 2>/dev/null) || return 1
  [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null || return 1
  cmd=$(ps -p "$pid" -o command= 2>/dev/null) || return 1
  case "$cmd" in *batch-session*|*food-session*) echo "$pid"; return 0 ;; esac
  return 1
}

if [ -n "$RESUME_ONLY" ]; then
  if holder=$(lock_holder); then
    echo "$(date '+%F %H:%M') food-resume: a narrator is running (pid $holder) - nothing to do"
    exit 0
  fi
  gate_line=$(FL resume-gate); gate_rc=$?
  echo "$(date '+%F %H:%M') food-resume: $gate_line"
  [ "$gate_rc" -eq 0 ] || exit 0
  # the resumed night writes where every food night writes
  FOOD_LOG="${FOOD_LOG:-$HOME/Library/Logs/how-we-know/food.log}"
  exec >>"$FOOD_LOG" 2>>"${FOOD_ERR:-${FOOD_LOG%.log}.err}"
  echo "=== food night RESUMED $(date '+%F %H:%M'): $gate_line ==="
else
  echo "=== food night $(date '+%F %H:%M') ==="
fi

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
on_exit() {
  local rc=$?
  FL run-end --rc "$rc" >/dev/null 2>&1 \
    || echo "  could not write the run record (rc $rc); food-resume may misread this exit"
  [ "$(cat "$BATCH_LOCK" 2>/dev/null)" = "$$" ] && rm -f "$BATCH_LOCK"
}
on_signal() {
  echo "NAMED STOP [FOOD_SESSION_KILLED]: received SIG$1 at $(date '+%F %H:%M'); the run" \
       "record says so and com.howweknow.food-resume resumes it while the window lasts"
  exit "$2"
}
trap on_exit EXIT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP
trap 'on_signal INT 130' INT
FL run-begin --pid "$$" --until "$NARRATION_UNTIL" \
  || echo "  could not write the run record; an interruption tonight would not be resumed"

# network first: a pull refused because the router is down is a wait, not a stop
net_wait() { # budget-seconds
  [ -n "$STUBS" ] && return 0
  FL net-wait --budget "$1" --until "$NARRATION_UNTIL"
}
if ! net_wait 1800; then
  echo "  the food night waited 30 min for the network; food-resume tries again."
  exit 5
fi
# on main and current, or not at all (the batch's guard, the same named stops);
# a refusal while the network is down waits and tries again, twice
if [ -z "$STUBS" ]; then
  tries=0
  until "$PYP" loop/mac_sync.py guard --lane food; do
    tries=$((tries + 1))
    if [ "$tries" -ge 3 ] || FL net-up; then
      echo "  the food night is refused; nothing was rendered."
      exit 3
    fi
    net_wait 900 || exit 5
  done
fi
caffeinate -dimsu -w $$ &

echo "--- stage 1/3: render the in-flight food episode (loop/food_lane.py) ---"
$LANE_CMD
RC=$?
if [ "$RC" -gt 128 ]; then
  echo "NAMED STOP [FOOD_LANE_KILLED]: loop/food_lane.py died of signal $((RC - 128))" \
       "(9 = SIGKILL: out of memory or a forced kill); food-resume resumes it"
fi
if [ -n "$STUBS" ]; then
  echo "=== food night (stubbed) ended rc=$RC ==="
  [ "$RC" -eq 4 ] && exit 0
  exit "$RC"
fi
SLUG=$($PY -c "import json;print(json.load(open('loop/state/_local/food_lane.json')).get('slug',''))" 2>/dev/null || echo "")

if [ "$RC" -eq 0 ] && [ -n "$SLUG" ]; then
  echo "--- stage 2/3: shelve to R2 for the cloud upload lane (private, dated) ---"
  export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-8d147e242033699dd37c6f5a451f48d2}"
  net_wait 900
  $PY loop/r2.py push "$SLUG" 2>&1 | tail -20
  if [ "${PIPESTATUS[0]}" -ne 0 ] && ! FL net-up; then
    net_wait 1800 && $PY loop/r2.py push "$SLUG" 2>&1 | tail -20
  fi
fi

echo "--- stage 3/3: report to the repository ---"
OK=1; [ "$RC" -eq 0 ] || [ "$RC" -eq 4 ] || OK=0
$PY loop/mac_sync.py heartbeat --lane food --ok "$OK" 2>&1 | tail -1
PATHS="channel/imagery/food_clips.json channel/imagery/food_ai.json"
if [ -n "$SLUG" ]; then
  PATHS="$PATHS channel/specs/$SLUG.json channel/specs/$SLUG.proof.npz"
  PATHS="$PATHS captions/$SLUG.srt captions/$SLUG.chapters.txt"
fi
net_wait 900
# shellcheck disable=SC2086  # word-split on purpose: paths have no spaces
$PY loop/mac_sync.py push --lane food $PATHS 2>&1 | tail -1
if [ "${PIPESTATUS[0]}" -ne 0 ] && ! FL net-up; then
  # shellcheck disable=SC2086
  net_wait 1800 && $PY loop/mac_sync.py push --lane food $PATHS 2>&1 | tail -1
fi
case $RC in
  0) echo "=== food night complete: $SLUG ready for upload $(date '+%H:%M') ===" ;;
  4) echo "=== food night ended at the window ($NARRATION_UNTIL); the next food night resumes $SLUG ===" ;;
  *) echo "=== food night stopped (rc=$RC); the named stop is above ===" ;;
esac
[ "$RC" -eq 4 ] && exit 0
exit "$RC"
