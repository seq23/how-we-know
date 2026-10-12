"""The Monday lane ends on time; its job ceiling is derived from its budget.

On 2026-10-12 (run 38235183608) the $0 OpenRouter route took 8 and then 18
minutes to run four attempts on two topics, and loop-mon-draft.yml's
31-minute ceiling - calibrated on a paid model's 0.6-minute median - cancelled
the job while the third topic was being drafted. A cancelled job commits
nothing and the lane went red for a slow runner, not a fault.

The fix is a wall-clock budget in code (loop/draft.py AUTHORING_BUDGET_MIN):
no draft attempt starts past it, and the rest of the week becomes briefs,
the same AUTHOR_REQUIRED note DRAFT_FAILED_VALIDATION already produces.

Pinned here, through the code that runs, never by reading prose:

  1. author.draft() with a deadline already passed raises
     AUTHORING_BUDGET_EXHAUSTED before any model call (zero calls made).
  2. With a deadline that passes after the first rejected attempt, the loop
     stops at attempt 2 instead of running out MAX_ATTEMPTS, and the stop
     carries the last rejection.
  3. loop-mon-draft.yml's timeout-minutes == AUTHORING_BUDGET_MIN + 20: the
     ceiling is derived from the budget (one in-flight attempt of ~6 min
     plus ~3 of setup, validation and dashboard, with headroom), so neither
     can drift without the other; the budget is at least 180 and the pair
     ends before 14:00 UTC, when the next loop-state lane queues.
  4. The stop code is classified in loop/stop_policy.json (needs_human,
     beside DRAFT_FAILED_VALIDATION).

Hard-fails on zero examined cases.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

sys.path.insert(0, str(LOOP))
import author  # noqa: E402
import draft  # noqa: E402

WF = ROOT / ".github" / "workflows" / "loop-mon-draft.yml"
CEILING_HEADROOM_MIN = 20


def _fake_router(calls: list[int], clock: dict):
    """A model that always answers an unusably short draft and moves the clock."""
    def call(messages, model, key, timeout=300, temperature=0.4):
        calls.append(1)
        clock["now"] += 60.0
        return {"model_used": model,
                "choices": [{"message": {"content": "too short"},
                             "finish_reason": "stop"}],
                "usage": {}}
    return call


def check() -> list[str]:
    fails, examined = [], 0
    clock = {"now": 1000.0}
    real_monotonic, real_router = author.time.monotonic, author.call_openrouter
    real_record = author.record_spend
    author.time.monotonic = lambda: clock["now"]
    author.record_spend = lambda *a, **k: None
    pov = {"pov_id": "test", "line": "a line"}
    try:
        # 1. deadline already passed -> no model call at all
        examined += 1
        calls: list[int] = []
        author.call_openrouter = _fake_router(calls, clock)
        try:
            author.draft("q?", "slug-a", pov, model=author.DEFAULT_MODEL,
                         key="k", deadline=clock["now"] - 1)
            fails.append("a passed deadline did not raise")
        except author.AuthorStop as e:
            if e.code != "AUTHORING_BUDGET_EXHAUSTED":
                fails.append(f"passed deadline raised {e.code}, not "
                             f"AUTHORING_BUDGET_EXHAUSTED")
        if calls:
            fails.append(f"a passed deadline still made {len(calls)} model "
                         f"call(s); the budget must be checked BEFORE the call")

        # 2. deadline passes after attempt 1 -> stop at attempt 2, not 4
        examined += 1
        calls = []
        author.call_openrouter = _fake_router(calls, clock)
        try:
            author.draft("q?", "slug-b", pov, model=author.DEFAULT_MODEL,
                         key="k", deadline=clock["now"] + 30)
            fails.append("a short draft with a mid-run deadline was accepted")
        except author.AuthorStop as e:
            if e.code != "AUTHORING_BUDGET_EXHAUSTED":
                fails.append(f"mid-run deadline ended as {e.code}, not "
                             f"AUTHORING_BUDGET_EXHAUSTED")
            if "attempt 2 of" not in e.message:
                fails.append(f"stop does not name the attempt it refused: "
                             f"{e.message!r}")
            if "narration is only" not in e.message:
                fails.append("stop does not carry the last rejection")
        if len(calls) != 1:
            fails.append(f"expected exactly 1 attempt before the deadline, "
                         f"made {len(calls)}")

        # control: no deadline -> the loop still runs MAX_ATTEMPTS
        examined += 1
        calls = []
        author.call_openrouter = _fake_router(calls, clock)
        try:
            author.draft("q?", "slug-c", pov, model=author.DEFAULT_MODEL,
                         key="k")
        except author.AuthorStop as e:
            if e.code != "DRAFT_FAILED_VALIDATION":
                fails.append(f"no-deadline control ended as {e.code}")
        if len(calls) != author.MAX_ATTEMPTS:
            fails.append(f"no-deadline control made {len(calls)} attempts, "
                         f"not MAX_ATTEMPTS={author.MAX_ATTEMPTS}")
    finally:
        author.time.monotonic = real_monotonic
        author.call_openrouter = real_router
        author.record_spend = real_record

    # 3. the workflow ceiling is derived from the budget
    examined += 1
    text = WF.read_text()
    m = re.search(r"^\s*timeout-minutes:\s*(\d+)", text, re.M)
    if not m:
        fails.append(f"{WF.name} declares no timeout-minutes")
    else:
        want = draft.AUTHORING_BUDGET_MIN + CEILING_HEADROOM_MIN
        got = int(m.group(1))
        if got != want:
            fails.append(f"{WF.name} timeout-minutes is {got}; the budget is "
                         f"{draft.AUTHORING_BUDGET_MIN} min so the ceiling "
                         f"must be {want} (budget + {CEILING_HEADROOM_MIN}). "
                         f"Change AUTHORING_BUDGET_MIN and the ceiling together.")
    # The budget fills the Monday slot (owner, 2026-10-12: "much longer so
    # this doesn't happen again") but must leave the loop-state queue before
    # loop-upload-cloud.yml joins it at 14:00 UTC: 10:00 start + budget +
    # ceiling headroom < 240 min, and never again a number a slow free model
    # can run out.
    if draft.AUTHORING_BUDGET_MIN < 180:
        fails.append(f"AUTHORING_BUDGET_MIN={draft.AUTHORING_BUDGET_MIN} is "
                     f"under 180: the $0 route needs 8-18 min per topic and "
                     f"the slot is the whole morning")
    if draft.AUTHORING_BUDGET_MIN + CEILING_HEADROOM_MIN >= 240:
        fails.append(f"budget {draft.AUTHORING_BUDGET_MIN} + {CEILING_HEADROOM_MIN} "
                     f"reaches 14:00 UTC, when loop-upload-cloud.yml joins the "
                     f"loop-state queue")
    m2 = re.search(r"cron:\s*'0 (\d+) \* \* 1'", text)
    if not m2 or int(m2.group(1)) != 10:
        fails.append("loop-mon-draft.yml no longer starts at 10:00 UTC; "
                     "re-derive AUTHORING_BUDGET_MIN against the next lane "
                     "in the loop-state group")

    # 4. the code is in the glossary
    examined += 1
    policy = json.loads((LOOP / "stop_policy.json").read_text())
    homes = [k for k in ("self_resolving", "owner_action", "needs_human")
             if "AUTHORING_BUDGET_EXHAUSTED" in (policy.get(k) or {})]
    if homes != ["needs_human"]:
        fails.append(f"AUTHORING_BUDGET_EXHAUSTED is classified in {homes}, "
                     f"not needs_human alone (like DRAFT_FAILED_VALIDATION: "
                     f"only ever raised inside author.draft and folded into "
                     f"AUTHOR_REQUIRED by draft.py)")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} authoring-budget case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the Monday lane ends on time and its ceiling follows "
          "its budget" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
