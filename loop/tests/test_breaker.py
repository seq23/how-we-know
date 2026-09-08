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


# THE SUITE MUST NOT WRITE THE LOOP'S OWN STATE. `breaker.py guard` takes a
# real named stop, and a named stop writes loop/state/stops/ and bumps
# _streaks.json - both tracked, both written by the cloud lanes. A local run of
# this file used to leave stop records for tue-render, thu-upload and
# fri-publish in the committed state; the same leak through _streaks.json cost
# a day on 2026-09-04 when a cloud lane could not rebase its own state commit.
# run_all.py already exports LOOP_STOPS_DIR; this honours it when the file is
# run on its own too.
_STOPS = os.environ.get("LOOP_STOPS_DIR") or tempfile.mkdtemp(
    prefix="breaker-test-stops-")


def run(*args):
    return subprocess.run([PY, os.path.join(LOOP, "breaker.py"), *args],
                          capture_output=True, text=True, cwd=ROOT,
                          env=dict(os.environ, LOOP_STOPS_DIR=_STOPS))


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

        # -- publishing must halt, and page exactly ONCE -----------------
        #
        # EVERY guarded stage still halts. What changed on 2026-09-08 is who
        # wakes the owner: one flag guards four lanes, so a tripped breaker
        # used to produce four red jobs and four issue comments a day and read
        # as four separate problems. The FIRST stage to stop on a given trip
        # owns the alarm and exits 3; the rest name the stage that already
        # raised it and exit 0. The halt is asserted independently of the exit
        # code below - `breaker.py guard` prints "may proceed" only when it
        # lets a lane through, and that string must appear for none of them.
        for i, stage in enumerate(PUBLISHING):
            examined += 1
            r = run("guard", "--stage", stage)
            out = r.stdout + r.stderr
            if "may proceed" in out:
                fails.append(f"tripped breaker let {stage} through — "
                             f"publishing did NOT halt")
            if "NAMED STOP" not in out:
                fails.append(f"{stage} halted as a crash rather than a named stop")
            if "BREAKER_TRIPPED" not in out:
                fails.append(f"{stage} halted without naming BREAKER_TRIPPED")
            if i == 0:
                if r.returncode != 3:
                    fails.append(
                        f"the FIRST stage to hit the tripped breaker "
                        f"({stage}) exited {r.returncode}; it owns the alarm "
                        f"and must be the one red job")
                if "ALREADY_REPORTED" in out:
                    fails.append(f"{stage} deferred to an earlier report that "
                                 f"does not exist")
            else:
                if r.returncode != 0:
                    fails.append(
                        f"{stage} exited {r.returncode} for the SAME trip "
                        f"{PUBLISHING[0]} already raised — one flag is one "
                        f"problem, and four red jobs for it is how a real "
                        f"alarm gets tuned out")
                if "BREAKER_TRIPPED_ALREADY_REPORTED" not in out:
                    fails.append(f"{stage} exited 0 without saying the trip was "
                                 f"already reported by another lane")

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
