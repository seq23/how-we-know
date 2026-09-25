"""FORMAT_PROBLEM is a finding for the owner, never a red main.

THE INCIDENT. The Friday 17:00 measure run on main (5cf1335, 2026-09-25) went
red on one thing only: the named stop FORMAT_PROBLEM, raised after the
measurement was written. The repo rule is that a named stop is green and
self-explaining; a red build is for real errors. FORMAT_PROBLEM is a content
decision only she can make, so it is `owner_action`: exit 0, recorded in the
owner-action file, carried to the top of the Sunday digest, and shown on the
run page as a GitHub warning annotation that names the finding file.

WHAT THIS PROVES, in a scratch stops dir (never loop/state/):
  1. loop/stop_policy.json classifies FORMAT_PROBLEM as owner_action, and NOT
     as needs_human (it must be in exactly one section);
  2. a real Stage raising it with measure.py's own message and unblock text
     exits 0, disposition owner_action, prints a `::warning` annotation whose
     text names loop/state/retention_finding.md, and records it in the
     owner-action file;
  3. a real error in the same stage (an exception) still fails the run, and
     an unclassified stop still exits 3 - the green path is not a blanket one;
  4. the warning annotation escapes newlines, so a multi-line message cannot
     truncate the annotation.
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

# ------------------------------------------------------------ 1. the policy
pol = json.loads((LOOP / "stop_policy.json").read_text())
examined += 1
if "FORMAT_PROBLEM" not in (pol.get("owner_action") or {}):
    fails.append("FORMAT_PROBLEM is not owner_action in loop/stop_policy.json")
if "FORMAT_PROBLEM" in (pol.get("needs_human") or {}):
    fails.append("FORMAT_PROBLEM is still listed as needs_human")

# The message and unblock measure.py really raises with, read from source so
# the test cannot drift from the lane.
msrc = (LOOP / "measure.py").read_text()
examined += 1
if 'unblock="Read loop/state/retention_finding.md.' not in msrc:
    fails.append("measure.py's FORMAT_PROBLEM unblock no longer names "
                 "loop/state/retention_finding.md")


def stage_run(body: str) -> subprocess.CompletedProcess:
    scratch = tempfile.mkdtemp(prefix="format-problem-stops-")
    env = dict(os.environ, LOOP_STOPS_DIR=scratch, LOOP_DRY_RUN="1",
               GITHUB_STEP_SUMMARY=os.path.join(scratch, "summary.md"))
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
    "    st.named_stop('FORMAT_PROBLEM', '6 of 10 videos lose the average "
    "viewer inside the first 2.0 minutes\\n(1:53 against a 146s floor).',\n"
    "                  detail={'measured': 10},\n"
    "                  unblock='Read loop/state/retention_finding.md. Better "
    "ranking will not fix this.')\n")
examined += 1
out = r.stdout + r.stderr
if r.returncode != 0:
    fails.append(f"FORMAT_PROBLEM exited {r.returncode}, not 0: a finding "
                 f"turned main red. {out.strip()[-300:]}")
warn = [ln for ln in r.stdout.splitlines() if ln.startswith("::warning ")]
examined += 1
if len(warn) != 1:
    fails.append(f"expected exactly one ::warning annotation, got {warn!r}")
elif ("FORMAT_PROBLEM" not in warn[0]
      or "loop/state/retention_finding.md" not in warn[0]):
    fails.append(f"the annotation does not name the code and the finding "
                 f"file: {warn[0]!r}")
elif "\n" in warn[0] or "%0A" not in warn[0]:
    fails.append("the annotation did not escape the message's newline")
rec_path = Path(r.scratch) / "2099-W01-fri-measure.json"
examined += 1
rec = json.loads(rec_path.read_text()) if rec_path.exists() else {}
if rec.get("disposition") != "owner_action" or rec.get("exit_code") != 0:
    fails.append(f"stop record is not owner_action/exit 0: "
                 f"{rec.get('disposition')}/{rec.get('exit_code')}")
oa = Path(r.scratch) / "owner_action.json"
examined += 1
if not oa.exists() or "FORMAT_PROBLEM" not in oa.read_text():
    fails.append("FORMAT_PROBLEM was not written to the owner-action file, so "
                 "the Sunday digest would never carry it")

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
