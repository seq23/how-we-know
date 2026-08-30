"""Prove the circuit breaker negatively: trip it, show publishing halts, reset.

The whole point of a breaker is what it *prevents*, and a breaker nobody has
seen stop anything is a flag, not a guard. So this test:

  1. snapshots the live breaker state and restores it at the end
  2. trips it, and asserts each publishing stage refuses with a NAMED STOP
  3. asserts the non-publishing stages are NOT halted — the breaker halts
     publishing without tearing down the pipeline
  4. resets it, and asserts the publishing guard passes again

Hard-fails if it examines zero stages.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
FLAG = os.path.join(LOOP, "state", "breaker.json")
PY = sys.executable

# Stages that must refuse while the breaker is tripped.
PUBLISHING = ["tue-render", "thu-upload", "fri-publish"]


def run(*args):
    return subprocess.run([PY, os.path.join(LOOP, "breaker.py"), *args],
                          capture_output=True, text=True, cwd=ROOT)


def check() -> list[str]:
    fails, examined = [], 0
    backup = None
    if os.path.exists(FLAG):
        backup = tempfile.mktemp()
        shutil.copy(FLAG, backup)

    try:
        # -- baseline: closed, guard passes -----------------------------
        run("reset", "--note", "test baseline")
        for stage in PUBLISHING:
            examined += 1
            r = run("guard", "--stage", stage)
            if r.returncode != 0:
                fails.append(f"closed breaker refused {stage} (rc={r.returncode})")

        # -- trip it ----------------------------------------------------
        t = run("trip", "--cause", "strike",
                "--detail", "TEST: simulated copyright strike")
        if t.returncode != 0:
            fails.append(f"trip exited {t.returncode}")
        state = json.load(open(FLAG))
        if state.get("state") != "tripped":
            fails.append(f"after trip the flag says {state.get('state')!r}")

        # -- publishing must halt ---------------------------------------
        for stage in PUBLISHING:
            examined += 1
            r = run("guard", "--stage", stage)
            out = r.stdout + r.stderr
            if r.returncode != 3:
                fails.append(f"tripped breaker let {stage} through "
                             f"(rc={r.returncode}) — publishing did NOT halt")
            if "BREAKER_TRIPPED" not in out:
                fails.append(f"{stage} halted without naming BREAKER_TRIPPED")
            if "NAMED STOP" not in out:
                fails.append(f"{stage} halted as a crash rather than a named stop")

        # -- the pipeline must NOT be torn down --------------------------
        # Ranking and drafting read the breaker but are not gated on it: the
        # week's work still accumulates while publishing is halted.
        for f in ("rank.py", "draft.py", "prepare.py"):
            examined += 1
            src = open(os.path.join(LOOP, f)).read()
            if "breaker.guard(" in src:
                fails.append(f"loop/{f} is gated on the breaker; a tripped "
                             f"breaker would tear down the pipeline instead of "
                             f"only halting publishing")

        # -- status reports the halt to a human --------------------------
        s = run("status")
        examined += 1
        if s.returncode != 3 or "TRIPPED" not in s.stdout:
            fails.append("status did not report the tripped breaker as a halt")

        # -- reset restores publishing -----------------------------------
        run("reset", "--note", "TEST: clearing the simulated strike")
        for stage in PUBLISHING:
            examined += 1
            r = run("guard", "--stage", stage)
            if r.returncode != 0:
                fails.append(f"{stage} still refused after reset "
                             f"(rc={r.returncode}) — the breaker does not reset")
        hist = json.load(open(FLAG)).get("history", [])
        if not any(h["event"] == "trip" for h in hist):
            fails.append("the trip left no history entry")
        if not any(h["event"] == "reset" for h in hist):
            fails.append("the reset left no history entry")

    finally:
        if backup:
            shutil.copy(backup, FLAG)
            os.unlink(backup)
        elif os.path.exists(FLAG):
            os.unlink(FLAG)

    if examined == 0:
        fails.append("examined ZERO stages")
    print(f"inspected {examined} breaker interaction(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the breaker halts publishing, spares the pipeline, "
          "and resets" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
