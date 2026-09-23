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


def state_snapshot() -> dict[str, str]:
    """sha256 of every file git tracks under loop/state/, plus the untracked,
    non-ignored files there.

    WHY. Until 2026-09-23 a full run rewrote three committed state files:
    attribution_gaps.json (V6 fed fixtures), captions_manifest.json and
    measurement.json (lanes run under LOOP_DRY_RUN, which did not cover
    state). Run on its own, a file could also write loop/state/stops/.
    Nothing noticed, because nothing looked. The next loop-stage commit on a
    machine that had run the tests would have shipped test output as the
    channel's state. This is the check that looks.
    """
    import hashlib                                         # noqa: PLC0415
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "loop/state"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout.split("\0")
    extra = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard", "--",
         "loop/state"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout.split("\0")
    snap = {}
    for rel in filter(None, tracked + extra):
        path = os.path.join(ROOT, rel)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                snap[rel] = hashlib.sha256(fh.read()).hexdigest()
        else:
            snap[rel] = "<absent>"
    return snap


def state_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(k for k in set(before) | set(after)
                  if before.get(k) != after.get(k))


def main() -> int:
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if not files:
        print("FAIL: no loop tests found — this runner examined zero tests")
        return 1

    before = state_snapshot()
    if not before:
        print("FAIL: found zero files under loop/state/ to guard. The check "
              "that tests leave committed state alone cannot reach anything")
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

    changed = state_changes(before, state_snapshot())

    print("\n" + "=" * 60)
    print(f"ran {len(files)} loop test file(s), {len(failed)} failed")
    for n in failed:
        print(f"  ✗ {n}")
    print(f"guarded {len(before)} file(s) under loop/state/: "
          f"{len(changed)} changed by the run")
    for rel in changed:
        print(f"  ✗ the test run wrote committed state: {rel}")
    if changed:
        print("  A test must write to a temp dir or a fixture path. Point the "
              "writer's module-level path at scratch (see ATTRIBUTION_GAPS in "
              "loop/validate.py), or run the lane under LOOP_DRY_RUN=1, which "
              "loop/common.py write_json honours for loop/state/.")
    return 1 if (failed or changed) else 0


if __name__ == "__main__":
    sys.exit(main())
