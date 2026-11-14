"""One breaker trip pages once, not every day (2026-11-14, issue #378).

THE DEFECT. breaker.guard() gives the alarm for a trip to the first lane that
hits it. That lane then raised BREAKER_TRIPPED on EVERY later run with no
held_items, so loop/held.py could never tell "the same trip, already reported
in an open issue" from a new one. The trip of 2026-11-13 22:05 UTC (cause
domain) turned shorts-cloud red, and it would have stayed red each evening
until the next weekly measurement cleared it.

WHAT IS PROVEN, each as its own process against a scratch flag and stops dir:
  1. a new trip pages: exit 3, stop coded BREAKER_TRIPPED;
  2. the SAME trip on the next run, with its issue recorded: exit 0 (held),
     and the lane is still halted, so the code is still BREAKER_TRIPPED;
  3. a NEW trip (different tripped_at) pages again: exit 3.
Hard-fails on zero cases examined. Nothing here reaches GitHub, R2 or the
live flag.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import held  # noqa: E402

STAGE = "shorts-cloud"
tmp = Path(tempfile.mkdtemp(prefix="breaker-held-"))
flag, stops = tmp / "breaker.json", tmp / "stops"
stops.mkdir()
env = {**os.environ, "LOOP_BREAKER_FLAG": str(flag), "LOOP_STOPS_DIR": str(stops),
       "LOOP_DRY_RUN": "1", "GITHUB_REPOSITORY": "", "GITHUB_STEP_SUMMARY": ""}
env.pop("GITHUB_REPOSITORY")
fails: list[str] = []
examined = 0


def trip(at: str) -> None:
    # cause manual: autoreset() never heals it, so the guard really halts.
    flag.write_text(json.dumps({"state": "tripped", "tripped_at": at,
                                "cause": "manual", "detail": "test trip",
                                "history": []}))


def guard() -> int:
    r = subprocess.run([sys.executable, "-c",
                        f"import breaker; breaker.guard({STAGE!r})"],
                       cwd=tmp, env={**env, "PYTHONPATH": str(LOOP)},
                       capture_output=True, text=True, timeout=120)
    return r.returncode


def code() -> str:
    recs = sorted(stops.glob(f"*-{STAGE}.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(recs[-1].read_text()).get("code") if recs else ""


def case(name: str, want_rc: int) -> None:
    global examined
    examined += 1
    rc = guard()
    if rc != want_rc or code() != "BREAKER_TRIPPED":
        fails.append(f"{name}: exit {rc} code {code()!r}, wanted exit "
                     f"{want_rc} code 'BREAKER_TRIPPED'")


trip("2026-11-13T22:05:54+00:00")
case("first report of a trip", 3)
if not held.record_issue(stops, STAGE, "BREAKER_TRIPPED", 378):
    fails.append("record_issue found no hold row: the guard named no item")
case("same trip, issue open", 0)
trip("2026-11-20T09:00:00+00:00")
case("a new trip", 3)

if examined == 0:
    fails.append("examined 0 cases")
for f in fails:
    print("FAIL", f)
print(f"breaker same-trip hold: {examined} case(s), {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
