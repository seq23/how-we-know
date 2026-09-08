"""Repairing one sentence may not invalidate the narration of a whole episode.

THE DEFECT THIS GUARDS, which cost the repair itself a rebuild on the day it
was written. `loop/pov_repair.py` first edited the script AND patched
`plans/<slug>.json` in place. Those are two different plans:
`voice/narrate_all.py` narrates from `planner.plan(script)`, not from the
frozen file, and the planner re-splits the paragraph that was just rewritten. A
bank line one sentence shorter than the invented one merged two beats into one,
every index after it shifted by one, and every wav past that point silently
belonged to different words.

Measured on the eight materials episodes: four of them shifted, 167 beats — of
the order of twenty hours of narration — to repair one sentence. Nothing would
have reported it except `visuals/captions.py` refusing to write, hours later,
for two of the eight.

So the properties, and all three are behavioural:

  A. `_confined()` accepts a replacement only when the beat COUNT is unchanged
     and every differing index sits in one short contiguous run containing the
     replaced beat.
  B. It rejects the real regressions: a changed count, a diff that reaches the
     end of the episode, a diff that does not contain the replaced beat.
  C. `loop/pov_repair.py` never writes `plans/<slug>.json` from anything but
     `planner.plan()`, so the frozen plan and the narrated plan cannot diverge
     again.
  D. `voice/narrate_all.py` preserves the measured `seconds` it finds — one
     batch stripped the timings from all 35 episodes at once, and a caption
     track is only missed weeks later, at upload.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import pov_repair                                              # noqa: E402

fails: list[str] = []
examined = 0


def plan(words: list[str]) -> list[dict]:
    return [{"narration": w, "segment": "text_beat"} for w in words]


BASE = plan([f"beat {i}" for i in range(20)])

CASES = [
    # (name, trial plan, replaced index, should be accepted)
    ("only the replaced beat changed",
     plan([f"beat {i}" if i != 7 else "her line" for i in range(20)]), 7, True),
    ("the replaced beat and the one after it",
     plan([f"beat {i}" if i not in (7, 8) else "her line" for i in range(20)]),
     7, True),
    ("one beat fewer — every later index shifted",
     plan([f"beat {i}" for i in range(19)]), 7, False),
    ("one beat more — every later index shifted",
     plan([f"beat {i}" for i in range(21)]), 7, False),
    ("a diff running to the end of the episode",
     plan([f"beat {i}" if i < 7 else "changed" for i in range(20)]), 7, False),
    ("a diff that does not contain the replaced beat",
     plan([f"beat {i}" if i != 2 else "changed" for i in range(20)]), 7, False),
    ("two separate runs of change",
     plan([f"beat {i}" if i not in (7, 15) else "changed" for i in range(20)]),
     7, False),
    ("nothing changed at all — the repair did not happen",
     plan([f"beat {i}" for i in range(20)]), 7, False),
]

for name, trial, idx, want in CASES:
    examined += 1
    got = pov_repair._confined(BASE, trial, idx)              # noqa: SLF001
    if got != want:
        fails.append(f"A/B: `{name}` was "
                     f"{'accepted' if got else 'rejected'}, expected "
                     f"{'accepted' if want else 'rejected'}")

# ---- C. the frozen plan comes from the planner, never from a patch ---------
src = open(os.path.join(LOOP, "pov_repair.py")).read()
tree = ast.parse(src)
examined += 1
if "planner.plan(" not in src:
    fails.append("C: loop/pov_repair.py no longer re-freezes the plan from "
                 "planner.plan(). A hand-patched plan diverges from the one "
                 "voice/narrate_all.py actually narrates, which is the bug.")
examined += 1
# The in-place patch that caused it, in any spelling.
if any(f"plan[{v}][\"narration\"] =" in src for v in ("idx", "i")):
    fails.append("C: loop/pov_repair.py assigns into a loaded plan's narration "
                 "again. The plan is the planner's to produce; patching it is "
                 "how the frozen copy and the narrated copy diverged.")

# ---- D. narration preserves the measured timings --------------------------
nsrc = open(os.path.join(ROOT, "voice", "narrate_all.py")).read()
examined += 1
if '"seconds"' not in nsrc:
    fails.append("D: voice/narrate_all.py no longer mentions the `seconds` "
                 "field, so it is writing beats.json fresh from the plan and "
                 "deleting every measured duration the cloud needs to build a "
                 "caption track.")
examined += 1
if 'row["seconds"] = was[1]' not in nsrc:
    fails.append("D: voice/narrate_all.py does not carry a previously measured "
                 "duration forward into the manifest it rewrites.")

# The committed corpus must actually carry timings, or the whole mechanism is
# a no-op that every other test would still pass.
examined += 1
complete = 0
audio = os.path.join(ROOT, "audio")
for slug in sorted(os.listdir(audio)) if os.path.isdir(audio) else []:
    mf = os.path.join(audio, slug, "beats.json")
    if not os.path.exists(mf):
        continue
    try:
        rows = json.load(open(mf))
    except ValueError:
        continue
    if rows and all("seconds" in r for r in rows):
        complete += 1
if complete == 0:
    fails.append("D: NO episode's audio/<slug>/beats.json carries a complete "
                 "set of measured durations. Every caption track in this repo "
                 "would then be buildable only on the Mac that voiced it — "
                 "which is the state this whole mechanism exists to leave.")

if examined == 0:
    print("FAIL: examined zero cases")
    raise SystemExit(1)

print(f"inspected {examined} case(s); {complete} episode(s) carry a complete "
      f"set of measured beat durations")
if fails:
    print("\nFAIL:")
    for f in fails:
        print(f"  - {f}")
    raise SystemExit(1)
print("all green - a POV repair costs the beats it replaces and no others")
