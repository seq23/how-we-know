"""A stop that fixes itself must not page a human; every other stop must.

THE DEFECT THIS GUARDS. Run 33521586490 (2026-09-01, `loop · daily 09:00 CT ·
upload from R2`) ended with a NAMED STOP whose own unblock text was "Nothing to
do; the allowance resets at midnight Pacific and this lane runs daily" — and
exit code 3. The job went red, an issue was opened, and a daily lane hitting a
daily quota would have done that every single day. The alarm that fires for
something nobody can act on is the one that teaches people to ignore alarms.

So this asserts BEHAVIOUR, not prose, at three levels:

  A. `Stage` exits 0 for a self-resolving stop and 3 for one that needs a
     human — with the NAMED STOP banner printed either way.
  B. A "self-resolving" stop that never resolves stops being self-resolving:
     past `max_consecutive` it escalates back to exit 3, and any successful run
     clears the streak.
  C. `bin/loop-stage.sh`, run for real against a scratch repo, leaves a
     self-resolving stop green and opens NO issue, and still fails the job and
     opens an issue for one that needs a human.
  D. The taxonomy can reach what it governs: every code in
     loop/stop_policy.json is actually raised by a lane, and every call site
     that raises it supplies the detail the policy requires.

Hard-fails if any section examines zero cases.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable
POLICY = json.load(open(os.path.join(LOOP, "stop_policy.json")))

# A real stage, driven by an env var. Not a mock of Stage: the point is to
# watch the actual context manager choose an actual exit code.
HARNESS = r'''
import os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "loop"))
from common import Stage
mode = os.environ["MODE"]
with Stage("guard-stage", "2026-W36", zero_work_hint="nothing to read") as st:
    if mode == "quota_with_reset":
        st.named_stop("QUOTA_EXHAUSTED", "no quota left today",
                      detail={"resets_at": "2026-09-03T00:00:00-07:00"},
                      unblock="Nothing to do.")
    if mode == "quota_no_reset":
        st.named_stop("QUOTA_EXHAUSTED", "no quota left today",
                      unblock="Nothing to do.")
    if mode == "oauth":
        st.named_stop("OAUTH_MISSING", "no credential",
                      detail={"resets_at": "2026-09-03T00:00:00-07:00"},
                      unblock="Run auth/check_auth.py")
    if mode == "validator":
        st.named_stop("VALIDATOR_FAILED", "a validator failed",
                      unblock="Fix it, then reset the breaker.")
    if mode == "zero_work":
        pass
    if mode == "work":
        st.work("did one real thing")
'''


def _run(mode, stops_dir, harness_path):
    env = dict(os.environ, MODE=mode, REPO=ROOT, LOOP_STOPS_DIR=stops_dir)
    r = subprocess.run([PY, harness_path], capture_output=True, text=True,
                       env=env, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def a_exit_codes() -> tuple[list[str], int]:
    """Self-resolving -> 0 and still loud. Needs-a-human -> 3."""
    fails, examined = [], 0
    # mode, expected rc, must be a named stop?
    CASES = [
        ("quota_with_reset", 0, True,
         "a quota stop that says when it resets is self-resolving"),
        ("quota_no_reset", 3, True,
         "a quota stop that cannot say when it resets must stay loud"),
        # CHANGED 2026-09-08 with the owner_action disposition, and the change
        # is the point rather than an accommodation. A missing credential
        # ALWAYS needed a human and still does — nothing in code can mint one —
        # but the owner's instruction is that such a stop must not arrive as a
        # red build she cannot clear any faster for having been paged. It now
        # exits 0, records itself in the owner-action file, and is printed at
        # the top of the Sunday digest; loop/stop_policy.json escalates it to
        # exit 3 after five consecutive runs, which is asserted in
        # b_escalation() and is what stops "green" from meaning "ignored".
        ("oauth", 0, True,
         "a missing credential is hers alone to fix, so it is green and "
         "surfaced rather than red and paging"),
        ("validator", 3, True,
         "a failed validator always needs a human"),
        ("zero_work", 3, True,
         "Rule 0: a stage that did nothing must never be green"),
        ("work", 0, False,
         "a stage that did real work is green with no stop record"),
    ]
    with tempfile.TemporaryDirectory() as td:
        harness = os.path.join(td, "harness.py")
        open(harness, "w").write(HARNESS)
        for mode, want_rc, is_stop, why in CASES:
            examined += 1
            stops = os.path.join(td, mode)          # fresh streak per case
            os.makedirs(stops, exist_ok=True)
            rc, out = _run(mode, stops, harness)
            if rc != want_rc:
                fails.append(f"[{mode}] exited {rc}, expected {want_rc} — {why}"
                             f"\n{out[-500:]}")
                continue
            rec_path = os.path.join(stops, "2026-W36-guard-stage.json")
            if not is_stop:
                if os.path.exists(rec_path):
                    fails.append(f"[{mode}] wrote a stop record for a run that "
                                 f"did real work")
                continue
            # A stop that pages nobody must still be impossible to miss.
            if "NAMED STOP" not in out:
                fails.append(f"[{mode}] took a stop without printing the NAMED "
                             f"STOP banner — nobody would ever see it")
            if "disposition:" not in out:
                fails.append(f"[{mode}] printed no disposition, so a reader "
                             f"cannot tell whether it is theirs to fix")
            if not os.path.exists(rec_path):
                fails.append(f"[{mode}] wrote no stop record to disk")
                continue
            rec = json.load(open(rec_path))
            want_disp = {"quota_with_reset": "self_resolving",
                         "oauth": "owner_action"}.get(mode, "needs_human")
            if rec.get("disposition") != want_disp:
                fails.append(f"[{mode}] recorded disposition "
                             f"{rec.get('disposition')!r}, expected {want_disp!r}")
            if rec.get("exit_code") != want_rc:
                fails.append(f"[{mode}] record claims exit {rec.get('exit_code')} "
                             f"but the process exited {rc}")
            if want_rc == 0 and not ("SELF-RESOLVING" in out
                                     or "WAITING ON THE OWNER" in out):
                fails.append(f"[{mode}] exited 0 without saying WHY it was "
                             f"green — that reads as a silent skip")
    return fails, examined


def b_escalation() -> tuple[list[str], int]:
    """A stop that never resolves is not self-resolving."""
    fails, examined = [], 0
    # Read the cap DEFENSIVELY. This section used to subscript the policy
    # directly, so deleting QUOTA_EXHAUSTED from loop/stop_policy.json - the
    # exact regression this file exists to catch - aborted the run with a
    # KeyError traceback before sections C and D could report anything. The
    # process still exited non-zero, so the guard was never inert, but it
    # reported a crash in the test instead of the defect in the policy, and a
    # guard that misnames what broke is how a five-minute fix becomes an hour.
    # A missing rule is a FINDING here, not an exception.
    rule = (POLICY.get("self_resolving") or {}).get("QUOTA_EXHAUSTED")
    if not rule:
        return ([("loop/stop_policy.json no longer classifies "
                  "QUOTA_EXHAUSTED, so the daily quota stop has reverted to "
                  "exit 3 and pages the owner every day it fires - the defect "
                  "of run 33521586490. Escalation cannot be checked at all "
                  "while the rule is absent.")], 0)
    cap = int(rule["max_consecutive"])
    with tempfile.TemporaryDirectory() as td:
        harness = os.path.join(td, "harness.py")
        open(harness, "w").write(HARNESS)
        stops = os.path.join(td, "streak")
        os.makedirs(stops)
        for i in range(1, cap + 2):
            examined += 1
            rc, out = _run("quota_with_reset", stops, harness)
            want = 0 if i <= cap else 3
            if rc != want:
                fails.append(f"consecutive quota stop #{i} of a {cap}-run limit "
                             f"exited {rc}, expected {want} — "
                             f"{'it must stay quiet' if want == 0 else 'it must escalate: a lane that has been quota-blocked every run is not healing itself'}"
                             f"\n{out[-400:]}")
        # A good run ends the streak, so tomorrow starts from zero.
        examined += 1
        _run("work", stops, harness)
        examined += 1
        rc, _ = _run("quota_with_reset", stops, harness)
        if rc != 0:
            fails.append(f"after a successful run the streak was not cleared: "
                         f"the next quota stop exited {rc}, expected 0")
    return fails, examined


def c_workflow_wrapper() -> tuple[list[str], int]:
    """Run bin/loop-stage.sh for real. Green and silent, or red and an issue."""
    fails, examined = [], 0
    if not shutil.which("git"):
        fails.append("git is not on PATH, so the wrapper cannot be exercised")
        return fails, examined
    CASES = [("quota_with_reset", 0, False), ("validator", 3, True)]
    with tempfile.TemporaryDirectory() as td:
        remote = os.path.join(td, "remote.git")
        work = os.path.join(td, "work")
        subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
        os.makedirs(os.path.join(work, "bin"))
        os.makedirs(os.path.join(work, "loop", "state", "stops"))
        os.makedirs(os.path.join(work, "docs"))
        for src, dst in (("bin/loop-stage.sh", "bin/loop-stage.sh"),
                         ("loop/common.py", "loop/common.py"),
                         ("loop/stop_policy.json", "loop/stop_policy.json")):
            data = open(os.path.join(ROOT, src)).read()
            open(os.path.join(work, dst), "w").write(data)
        os.chmod(os.path.join(work, "bin", "loop-stage.sh"), 0o755)
        # The stage under test, and a `gh` that records rather than posts.
        open(os.path.join(work, "loop", "stage.py"), "w").write(HARNESS)
        binf = os.path.join(td, "fakebin")
        os.makedirs(binf)
        gh = os.path.join(binf, "gh")
        open(gh, "w").write("#!/bin/sh\necho \"$@\" >> \"$GH_CALLS\"\nexit 0\n")
        os.chmod(gh, 0o755)
        env0 = dict(os.environ, PATH=binf + os.pathsep + os.environ["PATH"],
                    REPO=work, LOOP_PYTHON=PY, GITHUB_TOKEN="fake",
                    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "add", "."],
                    ["git", "commit", "-q", "-m", "base"],
                    ["git", "remote", "add", "origin", remote],
                    ["git", "push", "-q", "-u", "origin", "main"]):
            subprocess.run(cmd, cwd=work, check=True, env=env0,
                           capture_output=True)
        for mode, want_rc, want_issue in CASES:
            examined += 1
            calls = os.path.join(td, f"gh-calls-{mode}")
            open(calls, "w").close()
            env = dict(env0, MODE=mode, GH_CALLS=calls)
            r = subprocess.run(["bin/loop-stage.sh", "guard-stage",
                                "loop/stage.py"], cwd=work, env=env,
                               capture_output=True, text=True)
            out = r.stdout + r.stderr
            if r.returncode != want_rc:
                fails.append(f"bin/loop-stage.sh [{mode}] exited {r.returncode}, "
                             f"expected {want_rc}\n{out[-600:]}")
            opened = "issue create" in open(calls).read()
            if opened != want_issue:
                fails.append(
                    f"bin/loop-stage.sh [{mode}] "
                    + ("opened an issue for a stop that resolves itself — the "
                       "same daily page in another channel"
                       if opened else
                       "opened NO issue for a stop that needs a human"))
            if "NAMED STOP" not in out:
                fails.append(f"bin/loop-stage.sh [{mode}] swallowed the NAMED "
                             f"STOP banner")
    return fails, examined


def d_policy_reaches_its_lanes() -> tuple[list[str], int]:
    """Every classified code is really raised, with the detail it promises."""
    fails, examined = [], 0
    # BOTH green sections. `owner_action` joined `self_resolving` on
    # 2026-09-08 and a reachability guard that only walks one of them would go
    # quietly blind to the other.
    rules = {k: v for k, v in ((POLICY.get("self_resolving") or {})
                               | (POLICY.get("owner_action") or {})).items()
             if not k.startswith("_")}
    if not rules:
        fails.append("loop/stop_policy.json classifies ZERO codes — the "
                     "taxonomy exists but governs nothing")
    # Codes the loop BUILDS rather than writes as a literal, and wildcards that
    # match a family. This AST walk sees only literal first arguments, so
    # without this it would report every one of them as unreachable. The
    # authority for what is generated is
    # loop/tests/test_every_stop_is_classified.py, which checks each against the
    # expression that still builds it — one list, not two.
    sys.path.insert(0, HERE)
    import test_every_stop_is_classified as AUDIT     # noqa: PLC0415
    generated = set(AUDIT.GENERATED)
    seen = {code: 0 for code in rules
            if code not in generated and not code.endswith("*")}
    for path in sorted(glob.glob(os.path.join(LOOP, "*.py"))):
        tree = ast.parse(open(path).read(), path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "named_stop"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                continue
            code = node.args[0].value
            rule = rules.get(code)
            if rule is None:
                continue
            examined += 1
            if code in seen:
                seen[code] += 1
            detail = next((k.value for k in node.keywords
                           if k.arg == "detail"), None)
            keys = set()
            if isinstance(detail, ast.Dict):
                keys = {k.value for k in detail.keys
                        if isinstance(k, ast.Constant)}
            for need in rule.get("requires_detail", []):
                if need not in keys:
                    fails.append(
                        f"{os.path.relpath(path, ROOT)}:{node.lineno} raises "
                        f"{code} without detail[{need!r}], so it will be "
                        f"classified as needing a human and page the owner "
                        f"every run — the exact defect this policy fixes")
    for code, n in seen.items():
        if n == 0:
            fails.append(f"loop/stop_policy.json classifies {code}, which no "
                         f"lane raises — a rule that cannot reach anything")
    if examined == 0:
        fails.append("examined ZERO classified stop sites — this guard cannot "
                     "reach what it governs")
    return fails, examined


if __name__ == "__main__":
    total, allf = 0, []
    for name, fn in (("exit codes", a_exit_codes),
                     ("escalation", b_escalation),
                     ("the workflow wrapper", c_workflow_wrapper),
                     ("policy reach", d_policy_reaches_its_lanes)):
        f, n = fn()
        print(f"inspected {n} case(s) — {name}")
        total += n
        allf += f
    if total == 0:
        allf.append("examined ZERO cases in total")
    for x in allf:
        print(f"  ✗ {x}")
    print("all green - self-resolving stops exit 0 and stay visible; every "
          "other stop still reaches a human"
          if not allf else f"{len(allf)} failure(s)")
    sys.exit(1 if allf else 0)
