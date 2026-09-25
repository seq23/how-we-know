"""A format finding is ACTED ON, never a stop; a green stop never turns main red.

THE INCIDENT. The Friday 17:00 measure run on main (5cf1335, 2026-09-25) went
red on one thing only: the named stop FORMAT_PROBLEM, raised after the
measurement was written. #128 made it a green stop; the owner's rule the
same day ("Nothing waits on the owner") removed it as a stop altogether:
the measure lane acts on the finding through loop/opening.py and logs it.

WHAT THIS PROVES, in a scratch stops dir (never loop/state/):
  1. FORMAT_PROBLEM is in no loop/stop_policy.json section and loop/measure.py
     does not raise it; the lane calls opening.evaluate() and logs the action;
  2. a GREEN stop (self-resolving QUOTA_EXHAUSTED, message with a newline)
     exits 0, prints exactly one `::warning` annotation that names the file
     its unblock text points at, escapes the newline, and leaves a
     GITHUB_OUTPUT the runner can parse (PR #128's first CI run failed on an
     unparseable one);
  3. a real error still fails the run, and an unclassified stop still exits
     3 without being dressed as a warning.
Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
PY = sys.executable

fails: list[str] = []
examined = 0

# ------------------------------------------------------------ 1. no stop
pol = json.loads((LOOP / "stop_policy.json").read_text())
examined += 1
for sec in ("self_resolving", "owner_action", "needs_human"):
    if "FORMAT_PROBLEM" in (pol.get(sec) or {}):
        fails.append(f"FORMAT_PROBLEM is still a stop kind ({sec})")
msrc = (LOOP / "measure.py").read_text()
examined += 1
import ast                                                 # noqa: E402
for node in ast.walk(ast.parse(msrc)):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "named_stop" and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "FORMAT_PROBLEM"):
        fails.append("loop/measure.py still raises FORMAT_PROBLEM as a stop")
if "opening.evaluate(" not in msrc or "format finding acted on" not in msrc:
    fails.append("loop/measure.py does not act on the format finding through "
                 "loop/opening.py")


def stage_run(body: str) -> subprocess.CompletedProcess:
    scratch = tempfile.mkdtemp(prefix="green-stop-")
    env = dict(os.environ, LOOP_STOPS_DIR=scratch, LOOP_DRY_RUN="1",
               GITHUB_STEP_SUMMARY=os.path.join(scratch, "summary.md"),
               GITHUB_OUTPUT=os.path.join(scratch, "output.txt"))
    code = ("import sys; sys.path.insert(0, %r)\n" % str(LOOP)
            + "import common\n"
            + "with common.Stage('fri-measure', '2099-W01') as st:\n"
            + "    st.work('wrote loop/state/measurement.json')\n"
            + body)
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                       env=env, cwd=ROOT, timeout=120)
    r.scratch = scratch
    return r


# ------------------------------------------------------------ 2. green stop
r = stage_run(
    "    st.named_stop('QUOTA_EXHAUSTED', 'no YouTube units left today\\n"
    "(10,000 spent).',\n"
    "                  detail={'resets_at': 'midnight Pacific'},\n"
    "                  unblock='Nothing to do; see loop/state/quota.json. It "
    "resets at midnight Pacific.')\n")
examined += 1
out = r.stdout + r.stderr
if r.returncode != 0:
    fails.append(f"a green stop exited {r.returncode}, not 0: "
                 f"{out.strip()[-300:]}")
warn = [ln for ln in r.stdout.splitlines() if ln.startswith("::warning ")]
examined += 1
if len(warn) != 1:
    fails.append(f"expected exactly one ::warning annotation, got {warn!r}")
elif "QUOTA_EXHAUSTED" not in warn[0] or "loop/state/quota.json" not in warn[0]:
    fails.append(f"the annotation does not name the code and the file its "
                 f"unblock points at: {warn[0]!r}")
elif "%0A" not in warn[0]:
    fails.append("the annotation did not escape the message's newline")
examined += 1
lines = (Path(r.scratch) / "output.txt").read_text().splitlines()
i, bad = 0, []
while i < len(lines):
    ln = lines[i]
    if "<<" in ln and ("=" not in ln or ln.index("<<") < ln.index("=")):
        delim = ln.split("<<", 1)[1]
        if delim not in lines[i + 1:]:
            bad.append(ln)
            break
        i = lines.index(delim, i + 1) + 1
    elif "=" in ln:
        i += 1
    else:
        bad.append(ln)
        i += 1
if bad:
    fails.append(f"GITHUB_OUTPUT would not parse: {bad[:2]}")
rec_path = Path(r.scratch) / "2099-W01-fri-measure.json"
examined += 1
rec = json.loads(rec_path.read_text()) if rec_path.exists() else {}
if rec.get("disposition") != "self_resolving" or rec.get("exit_code") != 0:
    fails.append(f"stop record is not self_resolving/exit 0: "
                 f"{rec.get('disposition')}/{rec.get('exit_code')}")

# ------------------------------------------------------------ 3. still red
r = stage_run("    raise RuntimeError('YouTube Analytics returned garbage')\n")
examined += 1
if r.returncode == 0:
    fails.append("a real error in the measure stage exited 0")
r = stage_run("    st.named_stop('SOME_UNCLASSIFIED_DEFECT', 'broken')\n")
examined += 1
if r.returncode != 3:
    fails.append(f"an unclassified stop exited {r.returncode}, not 3")
if any(ln.startswith("::warning ") for ln in r.stdout.splitlines()):
    fails.append("a red stop was also annotated as a mere warning")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
