"""Every scheduled lane has a runner (V73), proved on the real files and broken on copies.

THE INCIDENT (2026-10-25). Food (How We Know: Food, owner-approved 13 Oct)
had its Wednesday and Saturday rotation slots, its pipeline
(visuals/food_episode.py) and its upload contract (backfill.food_hold) - and
nothing that ran it. Its first episode was made by a session by hand; five
food topics then waited with no episode and the rotation's food days stayed
empty. Defect class: "exists but nothing invokes it".

WHAT THIS PROVES
  1. The real repository passes V73 (loop/lanes.py vs the workflow YAML and
     the plists bin/loop-install-launchd.sh writes), with every launchd agent
     taken as loaded - and, on this Mac, against the real `launchctl list`.
  2. The food lane is a real runner: com.howweknow.food is in the installer,
     fires Tuesday and Thursday at 22:58, runs bin/food-session.sh, and the
     cloud half (loop-food-author.yml) has an uncommented cron invoking
     loop/food_author.py.
  NEGATIVE PROOFS - each break must fail V73, naming the right thing:
  3. drop the food render lane -> food-science has no lane that renders it
     (and the installed agent is no longer a listed lane);
  4. drop the food author lane -> food-science has no lane that authors it;
  5. a lane whose workflow file does not exist;
  6. a workflow whose cron is commented out;
  7. a launchd agent that is not loaded on the Mac;
  8. a rotation domain with no lanes at all;
  9. an empty lane list is a hard fail, never a pass.
"""
from __future__ import annotations

import copy
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import lanes as L                                          # noqa: E402
import validate as V                                       # noqa: E402

fails: list[str] = []
examined = 0
ALL = {x["agent"] for x in L.LANES.values() if x["runner"] == "launchd"}


def run(**kw):
    kw.setdefault("loaded", set(ALL))
    return V.v73_every_lane_has_a_runner(**kw)


def expect_fail(label: str, r, needle: str) -> None:
    global examined
    examined += 1
    if not r.failures:
        fails.append(f"{label}: V73 passed a broken state")
    elif not any(needle in f for f in r.failures):
        fails.append(f"{label}: failed, but not naming {needle!r}: {r.failures[:3]}")


# 1. the real repository
r = run()
examined += 1
if r.failures or r.examined == 0:
    fails.append(f"real repository fails V73: {r.failures[:4]} (examined {r.examined})")
if sys.platform == "darwin" and os.environ.get("CI") != "true" \
        and (Path.home() / "Library" / "LaunchAgents").exists():
    real = V.v73_every_lane_has_a_runner()
    examined += 1
    if real.failures:
        fails.append(f"on this Mac, against launchctl: {real.failures[:3]}")

# 2. the food lane's two runners, read from what schedules them
raw = subprocess.run(["bash", str(ROOT / "bin" / "loop-install-launchd.sh"), "--plist", "food"],
                     capture_output=True, text=True).stdout
pl = plistlib.loads(raw.encode())
cal = pl.get("StartCalendarInterval") or []
examined += 1
if sorted((c.get("Weekday"), c.get("Hour"), c.get("Minute")) for c in cal) != [(2, 22, 58), (4, 22, 58)]:
    fails.append(f"com.howweknow.food does not fire Tue + Thu 22:58: {cal}")
if "bin/food-session.sh" not in " ".join(pl.get("ProgramArguments") or []):
    fails.append("com.howweknow.food does not run bin/food-session.sh")
# 2a. a food night that dies is resumed: com.howweknow.food-resume (2026-10-25)
raw = subprocess.run(["bash", str(ROOT / "bin" / "loop-install-launchd.sh"), "--plist", "food-resume"],
                     capture_output=True, text=True).stdout
rp = plistlib.loads(raw.encode())
examined += 1
if rp.get("StartInterval") != 300 or rp.get("RunAtLoad") is not True \
        or "bin/food-session.sh --resume-if-interrupted" not in " ".join(rp.get("ProgramArguments") or []):
    fails.append(f"com.howweknow.food-resume is not every 300 s + at login running "
                 f"food-session.sh --resume-if-interrupted: {rp}")
expect_fail("food-resume agent not loaded", run(loaded=ALL - {"food-resume"}),
            "com.howweknow.food-resume is not loaded")
wf = (ROOT / ".github" / "workflows" / "loop-food-author.yml").read_text()
if "- cron:" not in wf or "loop/food_author.py" not in wf:
    fails.append("loop-food-author.yml has no cron invoking loop/food_author.py")

# 2b. the session script survives the shell launchd gives it: /bin/bash
# (3.2 on macOS) under `set -u`. Its first fired run died on an empty array
# ("SLUG_ARGS[@]: unbound variable", 2026-10-25) before doing anything.
for args in ([], ["--slug", "some-episode"], ["--resume-if-interrupted"]):
    examined += 1
    out = subprocess.run(["/bin/bash", str(ROOT / "bin" / "food-session.sh"), *args],
                         capture_output=True, text=True, env={**os.environ, "FOOD_SESSION_DRY": "1"})
    if out.returncode != 0 or "DRY: " not in out.stdout or "unbound" in out.stderr:
        fails.append(f"food-session.sh {args} under /bin/bash: rc={out.returncode} "
                     f"{out.stderr.strip()[-120:]!r}")
    elif args[:1] == ["--slug"] and "--slug some-episode" not in out.stdout:
        fails.append("food-session.sh drops --slug")
    elif args == ["--resume-if-interrupted"] and "DRY: resume gate, then" not in out.stdout:
        fails.append(f"food-session.sh --resume-if-interrupted skips the gate: {out.stdout!r}")
    elif not args and "food_lane.py run --until 07:00" not in out.stdout:
        fails.append(f"food-session.sh runs the wrong lane command: {out.stdout!r}")
if "[@]" in (ROOT / "bin" / "food-session.sh").read_text():
    fails.append("food-session.sh uses a bash array again (empty arrays are unbound under "
                 "set -u in /bin/bash 3.2)")

# 3. no food render lane
lanes = copy.deepcopy(L.LANES)
lanes.pop("food", None)
expect_fail("food render lane removed", run(lanes=lanes), "no scheduled lane that renders it")
expect_fail("food agent unlisted", run(lanes=lanes), "'food' is installed and is not a lane")

# 4. no food author lane
lanes = copy.deepcopy(L.LANES)
lanes.pop("food-author", None)
expect_fail("food author lane removed", run(lanes=lanes), "no scheduled lane that authors it")

# 5. a runner that does not exist
lanes = copy.deepcopy(L.LANES)
lanes["food-author"]["file"] = "loop-food-author-gone.yml"
expect_fail("missing workflow", run(lanes=lanes), "does not exist - a lane nothing invokes")

# 6. a commented-out cron, on a copy of the workflows
with tempfile.TemporaryDirectory() as td:
    d = Path(td) / "workflows"
    shutil.copytree(ROOT / ".github" / "workflows", d)
    p = d / "loop-food-author.yml"
    p.write_text(p.read_text().replace("    - cron: '0 19 * * 1'", "    # - cron: '0 19 * * 1'"))
    expect_fail("commented cron", run(workflows_dir=d), "has no uncommented schedule cron")

# 7. an agent nothing loaded
expect_fail("agent not loaded", run(loaded=ALL - {"food"}), "com.howweknow.food is not loaded")

# 8. a rotation domain with no lanes
cfg = copy.deepcopy(V.read_json(ROOT / "loop" / "config.json"))
cfg["cadence"]["rotation"]["weekdays"]["sun"] = "space-science"
expect_fail("uncovered domain", run(config=cfg), "space-science has rotation days")

# 9. nothing to examine
expect_fail("empty lane list", run(lanes={}), "lists no lanes")

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} lane-runner case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - every scheduled lane has a runner, and every rotation domain is made")
