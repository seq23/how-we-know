"""Run every loop test. Hard-fails if it finds no tests to run.

    python loop/tests/run_all.py

Each test file is a plain script that exits non-zero on failure — the same
convention as `tests/` in this repo, so no test runner has to be installed.
"""
from __future__ import annotations

import glob
import os
import subprocess
import time
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


def slow_names() -> list[str]:
    """The long suite, from loop/tests/slow_tests.txt — the ONE list.

    Both halves of the split read this file: --skip-slow (the merge gate) and
    --only-slow (the long suite on main). Two lists would drift, and a file in
    neither set would never run at all.
    """
    path = os.path.join(HERE, "slow_tests.txt")
    with open(path, encoding="utf-8") as fh:
        names = [ln.strip() for ln in fh
                 if ln.strip() and not ln.strip().startswith("#")]
    if not names:
        print(f"FAIL: {path} names no tests — the long suite would be empty "
              f"and --skip-slow would silently mean 'everything'")
        raise SystemExit(1)
    missing = [n for n in names
               if not os.path.isfile(os.path.join(HERE, n))]
    if missing:
        print(f"FAIL: slow_tests.txt names {missing}, which do not exist. A "
              f"renamed test parked here runs in NEITHER set")
        raise SystemExit(1)
    return names


def main() -> int:
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if not files:
        print("FAIL: no loop tests found — this runner examined zero tests")
        return 1
    # --shard K/N runs every Nth file from the K-th (1-based). CI runs N
    # shards in parallel (.github/workflows/loop-tests.yml matrix) so the
    # merge gate stays under its ceiling: the suite had grown to 5-7.5 min
    # against an 8-min fault detector, and on 2026-10-13 the registry gate
    # (test_registry_green_on_main.py) pushed a PR run over it. No argument
    # = every file, as before. test_registry_green_on_main.py asserts the
    # matrix names every shard 1..N, so no file can fall between shards.
    # --skip-slow / --only-slow split the suite into the merge gate and the long
    # suite that runs on main after merge (loop/tests/slow_tests.txt holds the
    # one list; search readiness h5). Five files were 468s of a 625s suite, so
    # sharding alone could not bring the gate under five minutes.
    args = sys.argv[1:]
    mode = None
    for flag in ("--skip-slow", "--only-slow"):
        if flag in args:
            if mode:
                print("FAIL: --skip-slow and --only-slow are mutually exclusive")
                return 1
            mode = flag
            args = [a for a in args if a != flag]
    if mode:
        slow = set(slow_names())
        keep = (lambda name: name not in slow) if mode == "--skip-slow" \
            else (lambda name: name in slow)
        files = [f for f in files if keep(os.path.basename(f))]
        print(f"{mode}: {len(files)} of {len(slow)} slow / "
              f"{len(glob.glob(os.path.join(HERE, 'test_*.py')))} total file(s)")
        if not files:
            print(f"FAIL: {mode} selected zero test files")
            return 1

    if args[:1] == ["--shard"] and len(args) == 2:
        k, n = (int(x) for x in args[1].split("/"))
        if not 1 <= k <= n:
            print(f"FAIL: --shard {args[1]} is not K/N with 1 <= K <= N")
            return 1
        files = files[k - 1::n]
        print(f"shard {k}/{n}: {len(files)} file(s)")
        if not files:
            print("FAIL: this shard holds zero test files")
            return 1
    elif args:
        print(f"FAIL: unknown arguments {args}; usage: "
              f"run_all.py [--shard K/N] [--skip-slow | --only-slow]")
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
    # No test makes a live model call: the Gemini tier (loop/llm_router.py)
    # must never reach the network from a test, whatever the shell exports.
    env.pop("GEMINI_API_KEY", None)

    failed = []
    for f in files:
        name = os.path.basename(f)
        # Same reason for loop/llm_router.py's route ledger (2026-10-12): any
        # test that drives complete() through a fake _post would otherwise
        # write loop/state/llm_route_ledger.json, and the fake outcomes would
        # reorder the real $0 fallback. One fresh, empty ledger per test file,
        # so no test's standing depends on which test ran before it.
        env["LLM_ROUTE_LEDGER"] = os.path.join(stops, f"route-ledger-{name}.json")
        # And for the circuit breaker's flag (2026-10-12): every publishing lane
        # now calls breaker.guard(), which reads the flag and writes
        # `reported_by` into it. A lane test must not stop because the LIVE
        # breaker happens to be tripped, nor write the committed flag. Absent
        # file = closed; a test that wants a trip writes its own.
        env["LOOP_BREAKER_FLAG"] = os.path.join(stops, f"breaker-{name}.json")
        # flush: the header must land in the CI log BEFORE the child's own
        # output, or per-test timing cannot be read off the log timestamps
        # (2026-10-13: every header arrived at the end, so balancing the
        # shards had nothing to go on).
        print(f"\n──── {name}", flush=True)
        t0 = time.monotonic()
        # Each test picks its OWN interpreter needs: test_workflows re-execs
        # into the system python3 for pyyaml, while the validators need the
        # venv's numpy and Pillow. Launching every test from the venv lets each
        # one do that, and stops a missing package from being reported as a
        # failing validator - which happened twice, once for PIL and once for
        # numpy, each time sending someone after a content bug that did not
        # exist. An unrun validator is not a failing one.
        r = subprocess.run([PY, f], cwd=ROOT, env=env)
        print(f"──── {name} took {time.monotonic() - t0:.0f}s", flush=True)
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
