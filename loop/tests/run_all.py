"""Run every loop test. Hard-fails if it finds no tests to run.

    python loop/tests/run_all.py

Each test file is a plain script that exits non-zero on failure — the same
convention as `tests/` in this repo, so no test runner has to be installed.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
VENV = os.path.join(ROOT, ".venv", "bin", "python")
PY = VENV if os.path.exists(VENV) else sys.executable


def main() -> int:
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if not files:
        print("FAIL: no loop tests found — this runner examined zero tests")
        return 1

    # THE SUITE MUST NOT WRITE THE LOOP'S OWN STATE.
    #
    # Several tests launch real lanes so they can watch a real stage take a
    # real named stop. Those lanes write loop/state/stops/ and bump
    # _streaks.json - which are TRACKED and are also written by the cloud
    # lanes. On 2026-09-04 a local suite run left `captions: OAUTH_MISSING,
    # count 4` in the committed streaks; the next cloud-upload run then could
    # not rebase its own state commit onto main and the workflow failed on
    # `error: could not apply ... cloud-upload — self-resolving stop`, three
    # retries deep, with nothing actually wrong with the lane.
    #
    # loop/common._stops_dir() already reads LOOP_STOPS_DIR for exactly this
    # reason; nothing was setting it. One temp directory per suite run, thrown
    # away afterwards, so a test can still assert on stop records while the
    # repo's own state is untouched.
    import tempfile                                        # noqa: PLC0415
    stops = tempfile.mkdtemp(prefix="loop-test-stops-")
    env = dict(os.environ, LOOP_STOPS_DIR=stops)

    failed = []
    for f in files:
        name = os.path.basename(f)
        print(f"\n──── {name}")
        # Each test picks its OWN interpreter needs: test_workflows re-execs
        # into the system python3 for pyyaml, while the validators need the
        # venv's numpy and Pillow. Launching every test from the venv lets each
        # one do that, and stops a missing package from being reported as a
        # failing validator - which happened twice, once for PIL and once for
        # numpy, each time sending someone after a content bug that did not
        # exist. An unrun validator is not a failing one.
        r = subprocess.run([PY, f], cwd=ROOT, env=env)
        if r.returncode != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    print(f"ran {len(files)} loop test file(s), {len(failed)} failed")
    for n in failed:
        print(f"  ✗ {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
