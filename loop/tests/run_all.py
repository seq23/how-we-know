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


def main() -> int:
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if not files:
        print("FAIL: no loop tests found — this runner examined zero tests")
        return 1

    failed = []
    for f in files:
        name = os.path.basename(f)
        print(f"\n──── {name}")
        r = subprocess.run([sys.executable, f], cwd=ROOT)
        if r.returncode != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    print(f"ran {len(files)} loop test file(s), {len(failed)} failed")
    for n in failed:
        print(f"  ✗ {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
