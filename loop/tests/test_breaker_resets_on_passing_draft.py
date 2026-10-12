"""A passing run of the check that tripped the breaker resets it, in that run.

THE DEFECT (2026-10-12). mon-draft tripped the breaker on V21 at 15:53 UTC.
PR #173 fixed V21; the lane re-ran green at 16:35 and 17:08 UTC with all 40
validators passing and `validators_passed: true` in the render queue - and
loop/state/breaker.json still said `tripped`. loop/draft.py had a trip path and
no reset path; the only reset was the lazy re-test inside breaker.guard(), and
no lane that runs Monday-Thursday calls guard(). The switch showed HALTED on
main for days after its cause was gone.

This proves, against a temp breaker file (never the live loop/state):
  1. a failing validator report trips it and does NOT clear it
  2. a passing report with zero rows does NOT clear it (examined nothing)
  3. a passing report clears a validator trip, and records the reset
  4. a validator trip thrown twice (same cause) is cleared by one pass
  5. a validator trip that ALSO holds a retention cause stays tripped
  6. a manual trip and a strike are never cleared by validators passing
  7. loop/draft.py calls clear_after_validation(passed, report) inside main()
     BEFORE it writes the render queue, so the queue records the reset state

Hard-fails on zero examined cases.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="brk-stops-"))
os.environ.pop("GITHUB_STEP_SUMMARY", None)

import breaker  # noqa: E402

PASS = [{"validator": f"V{i} x", "status": "PASS", "examined": 3,
         "failures": []} for i in range(1, 41)]
FAIL = PASS[:20] + [{"validator": "V21 no-boilerplate", "status": "FAIL(1)",
                     "examined": 49, "failures": ["x"]}] + PASS[21:]


def fresh() -> None:
    breaker.FLAG = Path(tempfile.mkdtemp(prefix="brk-")) / "breaker.json"


def state() -> str:
    return breaker.load().get("state", "closed")


def check() -> list[str]:
    fails: list[str] = []
    n = 0
    live = LOOP / "state" / "breaker.json"
    live_before = live.read_bytes() if live.exists() else None

    # 1. failing report: trip, and no clear
    fresh(); n += 1
    breaker.trip("validator", "V21 no-boilerplate=FAIL(1)")
    if breaker.clear_after_validation(False, FAIL) is not None or state() != "tripped":
        fails.append("a FAILING validator run cleared the breaker")

    # 2. zero rows: proves nothing
    n += 1
    if breaker.clear_after_validation(True, []) is not None or state() != "tripped":
        fails.append("a validator run that examined nothing cleared the breaker")
    # passed=True but a row says FAIL: the rows win
    n += 1
    if breaker.clear_after_validation(True, FAIL) is not None or state() != "tripped":
        fails.append("passed=True with a FAIL row cleared the breaker")

    # 3. passing report: cleared, history records it
    n += 1
    out = breaker.clear_after_validation(True, PASS)
    b = breaker.load()
    if out is None or b.get("state") != "closed":
        fails.append("a PASSING run of the check that tripped it left the "
                     "breaker tripped (the 2026-10-12 V21 defect)")
    elif not (b["history"][-1]["event"] == "reset"
              and b["history"][-1]["cleared_cause"] == "validator"):
        fails.append(f"reset not recorded in history: {b['history'][-1]}")

    # 4. tripped twice for the same cause: one pass clears it
    fresh(); n += 1
    breaker.trip("validator", "V21=FAIL(1)")
    breaker.trip("validator", "V21=FAIL(1) again")
    breaker.clear_after_validation(True, PASS)
    if state() != "closed":
        fails.append("a second same-cause trip kept the breaker shut after "
                     "every validator passed")

    # 5. also holds a different cause: stays tripped
    fresh(); n += 1
    breaker.trip("validator", "V21=FAIL(1)")
    breaker.trip("retention", "format below floor")
    breaker.clear_after_validation(True, PASS)
    if state() != "tripped":
        fails.append("validators passing cleared a breaker that also holds a "
                     "retention cause nobody re-tested")

    # 6. manual / strike never cleared by validators
    for cause in ("manual", "strike"):
        fresh(); n += 1
        breaker.trip(cause, "held")
        breaker.clear_after_validation(True, PASS)
        if state() != "tripped":
            fails.append(f"validators passing cleared a {cause} trip")

    # 7. draft.py wiring: called in main(), with (passed, report), before the
    #    render queue is written
    n += 1
    tree = ast.parse((LOOP / "draft.py").read_text())
    main = next((f for f in tree.body
                 if isinstance(f, ast.FunctionDef) and f.name == "main"), None)
    clear_line = queue_line = None
    for node in ast.walk(main) if main else []:
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and fn.attr == "clear_after_validation"
                and isinstance(fn.value, ast.Name) and fn.value.id == "breaker"):
            args = [a.id for a in node.args if isinstance(a, ast.Name)]
            if args == ["passed", "report"]:
                clear_line = node.lineno
        if (isinstance(fn, ast.Name) and fn.id == "write_json" and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "QUEUE"):
            queue_line = node.lineno if queue_line is None else min(queue_line, node.lineno)
    if clear_line is None:
        fails.append("loop/draft.py main() never calls "
                     "breaker.clear_after_validation(passed, report): a "
                     "passing draft cannot reset the validator trip it set")
    elif queue_line is None or clear_line > queue_line:
        fails.append(f"draft.py clears the breaker (line {clear_line}) after "
                     f"writing the render queue (line {queue_line}); the queue "
                     f"would record a stale 'tripped'")

    live_after = live.read_bytes() if live.exists() else None
    if live_before != live_after:
        fails.append("this test wrote the LIVE loop/state/breaker.json")
    if n == 0:
        fails.append("examined zero cases")
    print(f"breaker-resets-on-passing-draft: {n} case(s) examined")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print("FAIL:", x)
    print("PASS" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
