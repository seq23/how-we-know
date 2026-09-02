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
        r = subprocess.run([PY, f], cwd=ROOT)
        if r.returncode != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    print(f"ran {len(files)} loop test file(s), {len(failed)} failed")
    for n in failed:
        print(f"  ✗ {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
