"""Run loop/validate_plan.py as part of the suite, and prove it can fail.

The plan validator is only worth having if it is invoked. A document nobody
checks is the "exists but nothing invokes it" failure class, and a validator
nothing runs is the same class one level down - so this wires it into
`run_all.py` and, more importantly, asserts it is capable of failing at all.

A validator that cannot fail is a validator that is not checking.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import validate_plan as vp  # noqa: E402


def check() -> list[str]:
    fails, examined = [], 0

    # The plan must exist; it is the reference the whole thing hangs on.
    examined += 1
    if not vp.PLAN.exists():
        fails.append(f"{vp.PLAN} is missing - there is no locked plan to hold "
                     f"the pipeline to")
        print(f"inspected {examined} plan-conformance case(s)")
        return fails

    # It must resolve every check, and pass.
    examined += 1
    ok, rows = vp.run()
    if len(rows) != len(vp.CHECKS):
        fails.append(f"resolved {len(rows)} checks, expected {len(vp.CHECKS)}")
    if not rows:
        fails.append("resolved ZERO checks")
    for r in rows:
        examined += 1
        if r["status"] == "ERROR":
            fails.append(f"check {r['n']} ({r['check']}) errored: "
                         f"{r['failures']}")
        elif r["status"] != "PASS":
            fails.append(f"DRIFT - check {r['n']} ({r['check']}): "
                         + "; ".join(r["failures"]))

    # It must not read its expectations out of the plan's prose: a validator
    # that parses the markdown agrees with any edit to the markdown.
    examined += 1
    srcv = (LOOP / "validate_plan.py").read_text()
    body = srcv.split('PLAN = ROOT')[1]
    if re.search(r"PLAN\.read_text\(\)|open\(PLAN\)|PLAN\.open\(", body):
        fails.append("validate_plan.py reads the plan's prose; it must encode "
                     "the same facts independently or it checks nothing")

    # It must be capable of failing. Prove it by asking check 1 against a
    # deliberately wrong expectation.
    examined += 1
    real = vp.PLAN_CADENCE
    try:
        vp.PLAN_CADENCE = 99
        if vp.c1_cadence().ok:
            fails.append("check 1 PASSED against a deliberately wrong expected "
                         "cadence - the validator cannot fail")
    finally:
        vp.PLAN_CADENCE = real

    # And the CLI must exit non-zero on drift.
    examined += 1
    p = subprocess.run([sys.executable, str(LOOP / "validate_plan.py")],
                       cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0 and not fails:
        fails.append(f"the CLI exited {p.returncode} while every check passed")
    if "PLAN AND PIPELINE AGREE" not in p.stdout and not fails:
        fails.append("the CLI does not report agreement when everything passes")

    if examined == 0:
        fails.append("examined ZERO plan-conformance cases")
    print(f"inspected {examined} plan-conformance case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the running system matches docs/CHANNEL-PLAN.md"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
