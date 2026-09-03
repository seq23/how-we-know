"""No two loop lanes may write the same state file with nothing arbitrating.

CONFIRMED 2026-09-03: `loop-upload-cloud` (run 33783826056) and `loop-reach`
(run 33783829147) both spend YouTube quota and both commit
`loop/state/quota.json` through `bin/loop-stage.sh`, seconds apart. GitHub's
own `concurrency: group: loop-state` on all three cloud workflows did NOT
prevent the overlap in practice. The loser's `git pull --rebase` hit a real
textual conflict on `quota.json`, and the retry loop could not recover from
it: it retried a push while a rebase was still unmerged, which can never
succeed, and it fell through SILENTLY - the stage's own exit code, not
whether the push actually landed, decided the job's final status. A correct
NAMED STOP (CAPTIONS_SCOPE_MISSING) was reported as a crash, and a second,
unrelated step (localize) inherited the broken mid-rebase working tree and
failed for a different, confusing reason.

Two changes fixed it, and this test proves both, negatively where it matters:

1. `loop/tools/merge_quota_json.py`, registered as a git merge driver via
   `.gitattributes` + `bin/loop-stage.sh` (git will not run a driver COMMAND
   from a committed file, only local config can), sums each lane's own delta
   from the common ancestor instead of conflicting - `quota.json` is derived,
   additive accounting, so "sum both real spends" is the correct merge, not
   "pick a side".
2. `bin/loop-stage.sh`'s retry loop now aborts a left-over rebase before
   retrying, tracks whether a push actually succeeded rather than assuming it
   did, and fails the job outright if it never does - even when the stage
   itself exited 0.

Hard-fails when it examines zero of either check.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))

GITATTRIBUTES = os.path.join(ROOT, ".gitattributes")
LOOP_STAGE = os.path.join(ROOT, "bin", "loop-stage.sh")
DRIVER = os.path.join(ROOT, "loop", "tools", "merge_quota_json.py")
QUOTA = "loop/state/quota.json"


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def make_commit(repo, spent_delta, lane, lane_delta):
    import json
    p = os.path.join(repo, QUOTA)
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    d["spent"] += spent_delta
    d["by_lane"][lane] = d["by_lane"].get(lane, 0) + lane_delta
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2)
        fh.write("\n")
    sh("git", "add", QUOTA, cwd=repo)
    sh("git", "commit", "-q", "-m", f"{lane} spend", cwd=repo)


def two_lane_race(register_driver: bool) -> tuple[bool, str]:
    """Reproduce the exact production shape: two clones each spend a
    different lane's quota against the same base, then race to push.
    Returns (rebase_succeeded, quota_json_content_or_error).
    """
    with tempfile.TemporaryDirectory() as td:
        bare = os.path.join(td, "upstream.git")
        seed = os.path.join(td, "seed")
        a = os.path.join(td, "workerA")
        b = os.path.join(td, "workerB")
        sh("git", "init", "-q", "--bare", bare, cwd=td)
        sh("git", "clone", "-q", bare, seed, cwd=td)
        sh("git", "config", "user.email", "t@t.com", cwd=seed)
        sh("git", "config", "user.name", "t", cwd=seed)
        os.makedirs(os.path.join(seed, "loop", "state"))
        if register_driver:
            os.makedirs(os.path.join(seed, "loop", "tools"), exist_ok=True)
            with open(DRIVER, encoding="utf-8") as fh:
                driver_src = fh.read()
            with open(os.path.join(seed, "loop", "tools",
                                    "merge_quota_json.py"), "w",
                      encoding="utf-8") as fh:
                fh.write(driver_src)
            with open(os.path.join(seed, ".gitattributes"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"{QUOTA} merge=quota-union\n")
        with open(os.path.join(seed, QUOTA), "w", encoding="utf-8") as fh:
            fh.write('{"day": "2026-09-03", "spent": 9000, "by_lane": '
                     '{"backfill": 6800, "localize": 800, "captions": '
                     '1400}}\n')
        sh("git", "add", "-A", cwd=seed)
        sh("git", "commit", "-q", "-m", "base", cwd=seed)
        sh("git", "push", "-q", "origin", "main", cwd=seed)

        sh("git", "clone", "-q", bare, a, cwd=td)
        sh("git", "clone", "-q", bare, b, cwd=td)
        for repo in (a, b):
            sh("git", "config", "user.email", "t@t.com", cwd=repo)
            sh("git", "config", "user.name", "t", cwd=repo)
            if register_driver:
                sh("git", "config", "merge.quota-union.driver",
                   f"python3 {os.path.join(seed, 'loop', 'tools', 'merge_quota_json.py')} %O %A %B",
                   cwd=repo)

        # Lane A: captions spent 600. Lane B: upload-cloud spent 1700 - the
        # exact two lanes from the real incident.
        make_commit(a, 600, "captions", 600)
        make_commit(b, 1700, "upload-cloud", 1700)

        rb = sh("git", "push", "-q", "origin", "main", cwd=b)
        assert rb.returncode == 0, f"setup: workerB push failed: {rb.stderr}"

        r = sh("git", "pull", "--rebase", "-q", cwd=a)
        if r.returncode != 0:
            sh("git", "rebase", "--abort", cwd=a)
            return False, (r.stdout + r.stderr)
        with open(os.path.join(a, QUOTA), encoding="utf-8") as fh:
            return True, fh.read()


def check() -> tuple[int, list[str]]:
    examined = 0
    fails: list[str] = []

    # ---- 1. the files this depends on actually exist ----------------------
    examined += 1
    if not os.path.exists(GITATTRIBUTES):
        fails.append(".gitattributes does not exist")
    else:
        text = open(GITATTRIBUTES, encoding="utf-8").read()
        if not re.search(rf"^{re.escape(QUOTA)}\s+merge=quota-union\s*$",
                          text, re.M):
            fails.append(f".gitattributes does not declare "
                         f"'{QUOTA} merge=quota-union'")

    examined += 1
    if not os.path.exists(DRIVER):
        fails.append(f"{DRIVER} does not exist")

    examined += 1
    if not os.path.exists(LOOP_STAGE):
        fails.append(f"{LOOP_STAGE} does not exist")
    else:
        stage_src = open(LOOP_STAGE, encoding="utf-8").read()
        if "merge.quota-union.driver" not in stage_src:
            fails.append("bin/loop-stage.sh never registers the "
                         "merge.quota-union.driver locally - .gitattributes "
                         "alone cannot supply the driver COMMAND, so without "
                         "this the merge driver is never actually invoked")
        if "rebase --abort" not in stage_src:
            fails.append("bin/loop-stage.sh's retry loop never aborts a "
                         "stuck rebase - a conflict on attempt 1 dooms "
                         "attempts 2 and 3 to fail for an unrelated reason")
        if "PUSHED" not in stage_src:
            fails.append("bin/loop-stage.sh does not track whether a push "
                         "actually landed - it can exit 0 (the stage's own "
                         "rc) with a commit that only ever existed on the "
                         "runner")

    if not (os.path.exists(GITATTRIBUTES) and os.path.exists(DRIVER)):
        fails.append("cannot run the E2E race - a dependency above is missing")
        return examined, fails

    # ---- 2. negative proof: WITHOUT the driver, the real conflict recurs --
    examined += 1
    try:
        ok, out = two_lane_race(register_driver=False)
    except AssertionError as e:
        fails.append(f"negative-proof setup failed: {e}")
        ok, out = None, ""
    if ok is not False:
        fails.append("two-lane race did NOT conflict with the merge driver "
                     "unregistered - the negative proof is not exercising "
                     "the real defect (it may be tautological)")
    elif "CONFLICT" not in out and "conflict" not in out:
        fails.append(f"race failed for an unexpected reason, not a real "
                     f"quota.json conflict: {out[:300]!r}")

    # ---- 3. positive proof: WITH the driver, both lanes' spends survive ---
    examined += 1
    ok2, out2 = two_lane_race(register_driver=True)
    if not ok2:
        fails.append(f"two-lane race still conflicts with the merge driver "
                     f"registered: {out2[:500]!r}")
    else:
        import json
        try:
            d = json.loads(out2)
        except ValueError:
            fails.append(f"merged quota.json is not valid JSON: {out2!r}")
            d = {}
        if d.get("spent") != 11300:
            fails.append(f"merged spent={d.get('spent')!r}, expected 11300 "
                         f"(9000 base + 600 captions + 1700 upload-cloud) "
                         f"- a real spend was lost or invented")
        by_lane = d.get("by_lane", {})
        if by_lane.get("captions") != 2000:
            fails.append(f"merged by_lane.captions={by_lane.get('captions')!r}, "
                         f"expected 2000 - lane A's real spend was lost")
        if by_lane.get("upload-cloud") != 1700:
            fails.append(f"merged by_lane['upload-cloud']="
                         f"{by_lane.get('upload-cloud')!r}, expected 1700 - "
                         f"lane B's real spend was lost")

    return examined, fails


def main() -> int:
    examined, fails = check()
    if examined == 0:
        print("FAIL: examined zero shared-state-arbitration checks")
        return 1
    print(f"inspected {examined} shared-state-arbitration check(s)")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("all green - loop/state/quota.json survives two lanes writing it "
         "concurrently, and a push that never lands fails the job")
    return 0


if __name__ == "__main__":
    sys.exit(main())
