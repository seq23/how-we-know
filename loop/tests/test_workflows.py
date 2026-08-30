"""Every workflow must parse AND declare at least one job.

A workflow with a YAML error produces a run with **zero jobs** and no error
message anywhere in the Actions logs — the single most expensive failure mode
in this setup, because it looks like nothing happened rather than like
something broke. This test is the only thing standing between that and a silent
week.

It hard-fails when it finds zero workflows.
"""
from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WF = os.path.join(ROOT, ".github", "workflows")

REQUIRED_STAGES = {
    "loop-sun-rank.yml": "loop/rank.py",
    "loop-mon-draft.yml": "loop/draft.py",
    "loop-approve.yml": "loop/approve.py",
    "loop-fri-publish.yml": "loop/publish.py",
    "loop-fri-measure.yml": "loop/measure.py",
}


def load_yaml():
    """Get pyyaml, or re-exec under an interpreter that has it.

    The repo's `.venv` deliberately carries no test dependencies, and adding one
    to a venv four other jobs are using is not this test's business. macOS ships
    pyyaml with the Command Line Tools python3, and CI installs it. If neither
    exists the test EXITS NONZERO — it never passes without checking, because a
    YAML error is exactly the failure that leaves no trace anywhere else.
    """
    try:
        import yaml
        return yaml
    except ImportError:
        pass
    if not os.environ.get("_LOOP_YAML_REEXEC"):
        import subprocess
        for cand in ("/usr/bin/python3", "/usr/local/bin/python3", "python3"):
            env = dict(os.environ, _LOOP_YAML_REEXEC="1")
            try:
                probe = subprocess.run([cand, "-c", "import yaml"],
                                       capture_output=True)
            except (FileNotFoundError, OSError):
                continue
            if probe.returncode == 0:
                print(f"(re-running under {cand}, which has pyyaml)")
                sys.exit(subprocess.run([cand, os.path.abspath(__file__)],
                                        env=env).returncode)
    sys.exit("FAIL: pyyaml is not available anywhere, so YAML validity cannot "
             "be asserted. This test refuses to pass without checking — a "
             "workflow with a YAML error runs zero jobs and says nothing. "
             "Install pyyaml: pip install pyyaml")


def check() -> list[str]:
    yaml = load_yaml()
    fails, seen = [], 0
    files = sorted(glob.glob(os.path.join(WF, "*.yml")) +
                   glob.glob(os.path.join(WF, "*.yaml")))
    for path in files:
        seen += 1
        name = os.path.basename(path)
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError as e:
            fails.append(f"{name}: YAML does not parse — {e}")
            continue
        if not isinstance(doc, dict):
            fails.append(f"{name}: top level is not a mapping")
            continue
        jobs = doc.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            fails.append(f"{name}: declares ZERO jobs — this run would appear "
                         f"in Actions with nothing in it and no error")
            continue
        # `on:` parses as the boolean True in YAML 1.1. Either key is fine;
        # neither is not.
        if "on" not in doc and True not in doc:
            fails.append(f"{name}: has no trigger (`on:`)")
        for jname, job in jobs.items():
            if "runs-on" not in job:
                fails.append(f"{name}:{jname}: no runs-on")
            steps = job.get("steps")
            if not steps:
                fails.append(f"{name}:{jname}: no steps — a job that does "
                             f"nothing is Rule 0's failure mode in YAML form")

    for wf, stage in REQUIRED_STAGES.items():
        path = os.path.join(WF, wf)
        if not os.path.exists(path):
            fails.append(f"{wf}: missing — the weekly cadence is incomplete")
            continue
        if stage not in open(path).read():
            fails.append(f"{wf}: does not invoke {stage}")

    if seen == 0:
        fails.append("examined ZERO workflow files — this test cannot reach "
                     "what it governs")
    print(f"inspected {seen} workflow file(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every workflow parses and declares jobs" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
