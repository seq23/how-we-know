"""Rule 0: no stage may exit 0 having done nothing.

Proven three ways, all negatively — the state is broken on purpose and the
failure is shown to return.

  1. A `Stage` that records no work exits 3, not 0, and leaves a stop record.
  2. A `Stage` that records work exits 0 and clears any earlier stop record.
  3. Every real loop stage file actually uses `Stage` — a stage that forgot the
     wrapper would be exempt from the rule without anyone noticing.

Hard-fails if it examines zero stage files.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable

STAGE_FILES = ["rank.py", "draft.py", "override.py", "prepare.py",
               "upload.py", "publish.py", "measure.py",
               # The library lanes. Added 2026-09-01 with the move to R2: a new
               # stage that nothing registers here is exempt from Rule 0
               # without anyone noticing, which is the same silence the rule
               # exists to break.
               "backfill.py", "cloud_upload.py",
               "shorts_lane.py", "shorts_cloud.py",
               # The reach lanes, added 2026-09-02. Both run AFTER the upload
               # lane and neither is allowed to fail it, which makes them
               # exactly the kind of stage that could sit inert for months
               # looking green. Registering them here is what stops that.
               "captions_lane.py", "localize.py",
               # The footage harvest, added 2026-09-02 with the cadence raise.
               # It runs weekly and unattended against a pool that degrades
               # GRACEFULLY - a missing clip becomes an illustrated episode,
               # not an error - so it is exactly the lane that could harvest
               # nothing for months and look fine.
               "footage_lane.py"]


def run_snippet(code: str):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     dir=tempfile.gettempdir()) as fh:
        fh.write(f"import sys; sys.path.insert(0, {LOOP!r})\n" + code)
        path = fh.name
    try:
        return subprocess.run([PY, path], capture_output=True, text=True,
                              cwd=ROOT)
    finally:
        os.unlink(path)


def check() -> list[str]:
    fails, examined = [], 0

    # -- 1. zero work must NOT be a green exit ---------------------------
    r = run_snippet(
        "from common import Stage\n"
        "with Stage('rule-zero-probe', '0000-W00') as st:\n"
        "    pass\n")
    examined += 1
    if r.returncode != 3:
        fails.append(f"a Stage that did nothing exited {r.returncode}, "
                     f"expected 3 (NAMED STOP)")
    if "ZERO_WORK" not in (r.stdout + r.stderr):
        fails.append("a Stage that did nothing did not name ZERO_WORK")
    # WHERE the loop actually writes stop records, not where it used to.
    # loop/common._stops_dir() honours LOOP_STOPS_DIR, and the suite now sets
    # it to a temp directory so a test run cannot dirty the repo's tracked
    # state (see loop/tests/run_all.py). Hardcoding the default path here made
    # this probe look for the record in a directory the stage had deliberately
    # not written to.
    stopdir = os.environ.get("LOOP_STOPS_DIR") or os.path.join(LOOP, "state",
                                                               "stops")
    stopfile = os.path.join(stopdir, "0000-W00-rule-zero-probe.json")
    if not os.path.exists(stopfile):
        fails.append("no stop record was written for the zero-work stage")

    # -- 2. real work is green, and clears the stop record ---------------
    r2 = run_snippet(
        "from common import Stage\n"
        "with Stage('rule-zero-probe', '0000-W00') as st:\n"
        "    st.work('did something real')\n")
    examined += 1
    if r2.returncode != 0:
        fails.append(f"a Stage that did work exited {r2.returncode}, expected 0")
    if os.path.exists(stopfile):
        fails.append("the stop record survived a successful re-run; a cleared "
                     "stop must not linger and re-alarm forever")
        os.unlink(stopfile)

    # -- 3. every stage actually uses the wrapper ------------------------
    for f in STAGE_FILES:
        p = os.path.join(LOOP, f)
        if not os.path.exists(p):
            fails.append(f"loop/{f} is missing")
            continue
        examined += 1
        src = open(p).read()
        if "Stage(" not in src:
            fails.append(f"loop/{f} never opens a Stage — it is exempt from "
                         f"Rule 0")
        if "named_stop" not in src and "breaker.guard" not in src:
            fails.append(f"loop/{f} has no named stop path at all")

    if examined == 0:
        fails.append("examined ZERO stages")
    print(f"inspected {examined} Rule 0 subject(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - no stage can exit 0 having done nothing" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
