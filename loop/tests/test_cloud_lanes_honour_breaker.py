"""Every lane that publishes honours the circuit breaker - proven, not asserted.

THE DEFECT (2026-10-12). The breaker is documented as halting publishing and
the Sunday digest says "Publishing is halted" when it trips, but the two daily
cloud lanes that actually upload - loop/cloud_upload.py (09:00) and
loop/shorts_cloud.py (18:00) - never called breaker.guard(), and neither did
the Mac's daily backfill (loop/backfill.py) or Shorts (loop/shorts_lane.py)
uploads. A guard that cannot reach what it governs.

WHAT IS PROVEN

  1. STATIC. Every lane in breaker.GUARDED (the one list) really calls
     guard() with its own stage name: an AST call `breaker.guard(<stage>)`
     (or `breaker.guard(LANE)` with LANE == stage) in the .py, or
     `breaker.py guard --stage <stage>` in the .sh. The four upload lanes
     above must be in the list. Hard-fails on zero lanes examined.
  2. BEHAVIOUR. Each of the four lanes is run as its own process (the exit
     code is the contract) against a scratch breaker flag and stops dir:
       tripped (cause manual, and cause retention) -> exit 3, a stop record
         coded BREAKER_TRIPPED for that lane, and NOTHING reached: no R2
         shelf, no credential load, no upload, and the lane's own work never
         started;
       closed -> the lane proceeds past the breaker to its own work.
  3. RUNBOOK.md "## The circuit breaker" names every guarded stage, so the
     digest's "Publishing is halted" sentence is honest about what it halts.

NOTHING HERE CAN REACH YOUTUBE, R2 OR THE LIVE FLAG: every entry point is
replaced with a recorder before the lane runs, and LOOP_BREAKER_FLAG /
LOOP_STOPS_DIR point at a temp dir.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
PY = sys.executable
sys.path.insert(0, str(LOOP))

import breaker  # noqa: E402

MUST_GUARD = {"cloud-upload", "shorts-cloud", "backfill", "shorts",
              "fri-publish", "thu-upload"}


def _calls_guard(path: Path, stage: str) -> bool:
    src = path.read_text()
    if path.suffix == ".sh":
        return re.search(rf"breaker\.py guard --stage {re.escape(stage)}\b",
                         src) is not None
    tree = ast.parse(src)
    consts = {t.id: n.value.value for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
              for t in n.targets if isinstance(t, ast.Name)}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "guard"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "breaker" and n.args):
            a = n.args[0]
            val = (a.value if isinstance(a, ast.Constant)
                   else consts.get(a.id) if isinstance(a, ast.Name) else None)
            if val == stage:
                return True
    return False


def check_static(fails: list[str]) -> int:
    examined = 0
    missing = MUST_GUARD - set(breaker.GUARDED)
    if missing:
        fails.append(f"1: breaker.GUARDED omits publishing lane(s) {sorted(missing)}")
    for stage, rel in breaker.GUARDED.items():
        examined += 1
        p = ROOT / rel
        if not p.exists():
            fails.append(f"1: {stage}: {rel} does not exist")
        elif not _calls_guard(p, stage):
            fails.append(f"1: {stage}: {rel} never calls breaker.guard({stage!r}) "
                         f"- a guard that cannot reach what it governs")
    return examined


def check_runbook(fails: list[str]) -> int:
    text = (ROOT / "RUNBOOK.md").read_text()
    m = re.search(r"^## The circuit breaker\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        fails.append("3: RUNBOOK.md has no '## The circuit breaker' section")
        return 0
    body = m.group(1)
    n = 0
    for stage in breaker.GUARDED:
        n += 1
        if f"`{stage}`" not in body:
            fails.append(f"3: RUNBOOK's breaker section does not list `{stage}`")
    if "BREAKER_TRIPPED" not in body:
        fails.append("3: RUNBOOK's breaker section does not name BREAKER_TRIPPED")
    return n


HARNESS = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, %(loop)r)
MARK = Path(os.environ["TEST_MARK"])
def hit(what):
    with MARK.open("a") as fh:
        fh.write(what + "\n")

import r2, upload as up, arming, backfill, shorts_lane
# Every irreversible entry point records and refuses.
def _shelf():
    hit("r2.require"); os._exit(41)
r2.require = _shelf
def _creds(cfg):
    hit("load_credentials"); os._exit(41)
up.load_credentials = _creds
def _upload(*a, **k):
    hit("resumable_upload"); os._exit(41)
up.resumable_upload = _upload

LANE_MOD = %(mod)r
sys.argv = [LANE_MOD + ".py"]
if LANE_MOD in ("cloud_upload", "shorts_cloud"):
    # The first thing each cloud lane does after the breaker, inside its own
    # Stage. Reaching it = the lane got past the guard.
    def _gate(st, lane):
        hit("lane-work"); os._exit(42)
    arming.gate = _gate
    import importlib
    mod = importlib.import_module(LANE_MOD)
else:
    mod = backfill if LANE_MOD == "backfill" else shorts_lane
    def _run(*a, **k):
        hit("lane-work"); os._exit(42)
    mod.run = _run
rc = mod.main()
sys.exit(rc)
'''

LANES = {  # module -> stage
    "cloud_upload": "cloud-upload",
    "shorts_cloud": "shorts-cloud",
    "backfill": "backfill",
    "shorts_lane": "shorts",
}


def run_lane(mod: str, flag_state: dict | None) -> tuple[int, list[str], dict, str]:
    tmp = Path(tempfile.mkdtemp(prefix="brk-lane-"))
    flag, stops, mark = tmp / "breaker.json", tmp / "stops", tmp / "mark"
    stops.mkdir()
    if flag_state is not None:
        flag.write_text(json.dumps(flag_state))
    script = tmp / "h.py"
    script.write_text(HARNESS % {"loop": str(LOOP), "mod": mod})
    env = dict(os.environ, LOOP_BREAKER_FLAG=str(flag), LOOP_STOPS_DIR=str(stops),
               TEST_MARK=str(mark), LOOP_NO_DOTENV="1",
               GITHUB_EVENT_NAME="workflow_dispatch")
    env.pop("LOOP_DRY_RUN", None)
    env.pop("GITHUB_STEP_SUMMARY", None)
    r = subprocess.run([PY, str(script)], capture_output=True, text=True,
                       cwd=ROOT, env=env, timeout=300)
    hits = mark.read_text().split() if mark.exists() else []
    recs = list(stops.glob(f"*-{LANES[mod]}.json"))
    rec = json.loads(recs[0].read_text()) if recs else {}
    return r.returncode, hits, rec, (r.stdout + r.stderr)[-600:]


def tripped(cause: str) -> dict:
    return {"state": "tripped", "tripped_at": "2026-10-12T05:00:00Z",
            "cause": cause, "detail": f"TEST: fixture {cause} trip",
            "history": []}


def check_behaviour(fails: list[str]) -> int:
    examined = 0
    for mod, stage in LANES.items():
        for cause in ("manual", "retention"):
            examined += 1
            rc, hits, rec, tail = run_lane(mod, tripped(cause))
            if rc != 3:
                fails.append(f"2: {stage} with a {cause} trip exited {rc}, not 3 "
                             f"(the named-stop code): {tail}")
            if rec.get("code") != "BREAKER_TRIPPED":
                fails.append(f"2: {stage} with a {cause} trip recorded "
                             f"{rec.get('code')!r}, not BREAKER_TRIPPED")
            if hits:
                fails.append(f"2: {stage} with a {cause} trip still reached "
                             f"{hits} - it published (or began to) against a "
                             f"live breaker")
        examined += 1
        rc, hits, rec, tail = run_lane(mod, None)
        if hits[:1] != ["lane-work"] or rc != 42:
            fails.append(f"2: {stage} with the breaker CLOSED did not proceed "
                         f"to its own work (rc={rc}, reached {hits}): {tail}")
        if rec:
            fails.append(f"2: {stage} with the breaker CLOSED took a stop: "
                         f"{rec.get('code')}")
    return examined


def main() -> int:
    fails: list[str] = []
    n = check_static(fails) + check_runbook(fails) + check_behaviour(fails)
    if n < 20:
        fails.append(f"Rule 0: only {n} checks ran; at least 20 expected")
    for f in fails:
        print(f"FAIL {f}")
    if fails:
        return 1
    print(f"all green - {n} checks: every publishing lane stops on a tripped "
          f"breaker, proceeds on a closed one, and the RUNBOOK lists them all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
