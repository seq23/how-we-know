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
    "loop-sat-score.yml": "loop/score.py",
    "loop-sun-rank.yml": "loop/rank.py",
    "loop-mon-draft.yml": "loop/draft.py",
    "loop-override.yml": "loop/override.py",
    "loop-fri-publish.yml": "loop/publish.py",
    "loop-fri-measure.yml": "loop/measure.py",
    # The daily lane that replaced the Mac's launchd backfill agent. If this
    # file ever stops invoking the stage, uploading silently returns to needing
    # a laptop that is awake — and nothing else would say so.
    "loop-upload-cloud.yml": "loop/cloud_upload.py",
    # Shorts are the discovery half of the strategy and were sitting cut and
    # unpublished. If this stops being invoked they go back to sitting there,
    # and a channel that looks healthy is publishing at half its reach.
    "loop-shorts-cloud.yml": "loop/shorts_cloud.py",
    # Non-English reach. If this stops being invoked, every new episode ships
    # with no caption track — which is what YouTube auto-translates subtitles
    # AND audio from — and no localized metadata, so it exists only for English
    # search. Nothing else would report it; the channel would simply grow more
    # slowly for no visible reason.
    "loop-reach.yml": "loop/captions_lane.py",
    # Footage is the real scarcity at 4 episodes a week. If this stops being
    # invoked the cleared pool stops growing, and NOTHING breaks - every
    # episode past the existing pool is simply illustrated. A shortage that
    # produces no error is exactly the kind this table exists to keep visible.
    "loop-imagery-harvest.yml": "loop/footage_lane.py",
}
# Stages that ride inside another lane's workflow, as a later step. The
# hand-off lane runs after BOTH daily YouTube lanes: the morning upload lane
# (episodes going public are what turn a Short's `pending` into `done`) and the
# evening Shorts lane (a new Short needs its playlist row and, once public, its
# comment). Dropping either step would leave the other half a day stale with
# nothing to say so.
REQUIRED_STEPS = {
    "loop-upload-cloud.yml": ["loop/handoff.py"],
    "loop-shorts-cloud.yml": ["loop/handoff.py"],
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
    fails, seen, dep_jobs = [], 0, 0
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

        # THE DEPENDENCY GUARD. Run 33381208414 (2026-08-31, Mon draft) failed
        # with `ModuleNotFoundError: No module named 'PIL'`: the workflow ran a
        # loop stage having installed nothing, a validator crashed on import,
        # and the circuit breaker read that crash as a content defect and
        # halted publishing. Nobody was looking for a missing wheel — the
        # message said a validator failed. requirements-loop.txt was added the
        # same day, but nothing stopped the next workflow from forgetting it.
        # This does. A job that runs python without installing the pins is a
        # breaker trip waiting for a date.
        for jname, job in (jobs or {}).items():
            steps = job.get("steps") or []
            runs = " ".join(str(st.get("run", "")) for st in steps
                            if isinstance(st, dict))
            if "loop-stage.sh" not in runs and "python loop/" not in runs \
                    and "run_all.py" not in runs:
                continue
            dep_jobs += 1
            if "requirements-loop.txt" not in runs:
                fails.append(f"{name}:{jname}: runs a loop stage but never "
                             f"installs requirements-loop.txt — a missing wheel "
                             f"will surface as a failed validator and trip the "
                             f"breaker for a defect that does not exist")

    for wf, stage in REQUIRED_STAGES.items():
        path = os.path.join(WF, wf)
        if not os.path.exists(path):
            fails.append(f"{wf}: missing — the weekly cadence is incomplete")
            continue
        if stage not in open(path).read():
            fails.append(f"{wf}: does not invoke {stage}")
    for wf, stages in REQUIRED_STEPS.items():
        path = os.path.join(WF, wf)
        if not os.path.exists(path):
            continue                        # already reported above
        text = open(path).read()
        for stage in stages:
            if stage not in text:
                fails.append(f"{wf}: no longer runs {stage} after its lane — "
                             f"the hand-off would go stale for half a day "
                             f"with nothing reporting it")

    if seen == 0:
        fails.append("examined ZERO workflow files — this test cannot reach "
                     "what it governs")
    if dep_jobs == 0:
        fails.append("examined ZERO jobs that run a loop stage — the "
                     "dependency guard matched nothing, so it is asserting "
                     "nothing. Either every lane stopped running python, or "
                     "the way workflows invoke stages changed under it.")
    print(f"inspected {seen} workflow file(s), {dep_jobs} of them running a "
          f"loop stage")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every workflow parses and declares jobs" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
