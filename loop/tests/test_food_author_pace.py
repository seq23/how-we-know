"""The food author's words-per-minute is the MEASURED stitched rate, and the
FOOD_EPISODE_CONTRACT stop line names the episode's own reason.

26 Oct 2026: FOOD_WPM = 169.5 (the first episode) sized chili-coffee-honey at
"about 30 minutes"; it stitched at 32.6 min (5,145 narrated words, 158.0 wpm)
and was held, and the stop said only "fails the episode contract".

Prove-it-fails: put FOOD_WPM back to 169.5 -> cases 1-2 fail; drop
episode_failure() from the stop line -> case 4 fails.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))

import food_author as A                                        # noqa: E402
import food_lane as FL                                         # noqa: E402

fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


MEASURED = {"chili-coffee-honey (26 Oct)": 5145 / (1953.321 / 60), "first episode": 169.5}
# 1. pinned to the slower measured rate (within 1 wpm)
check(abs(A.FOOD_WPM - MEASURED["chili-coffee-honey (26 Oct)"]) <= 1.0,
      f"FOOD_WPM {A.FOOD_WPM} is not the measured 158.0")
# 2. the aimed word count lands inside the window at EVERY measured rate
aim_words = A.AIM_MINUTES * A.FOOD_WPM
for name, rate in MEASURED.items():
    mins = aim_words / rate
    check(A.MINUTES[0] <= mins <= A.MINUTES[1],
          f"aim of {aim_words:.0f} words runs {mins:.1f} min at {name}'s {rate:.1f} wpm")
check(tuple(A.MINUTES) == (28.0, 32.0), f"the window moved: {A.MINUTES}")

# 3-4. the stop line carries the spec's own reason
with tempfile.TemporaryDirectory() as td:
    sp = Path(td) / "s.json"
    sp.write_text(json.dumps({"episode_problems": ["episode runs 32.6 min, outside 28-32"]}))
    check(FL.episode_failure(sp) == "episode runs 32.6 min, outside 28-32",
          f"episode_failure lost the reason: {FL.episode_failure(sp)}")
    check("no readable episode spec" in FL.episode_failure(Path(td) / "missing.json"),
          "episode_failure silent on a missing spec")
src = (ROOT / "loop" / "food_lane.py").read_text()
line = src[src.index("NAMED STOP [FOOD_EPISODE_CONTRACT]"):][:200]
check("episode_failure(spec)" in line, "the FOOD_EPISODE_CONTRACT stop line does not name its reason")

import validate as V                                           # noqa: E402
import backfill as BF                                          # noqa: E402
# 5-6. V55: a failing, unshipped food episode is HELD by name (a note), and a
# failing episode that food_hold would let ship is still a hard failure
spec_p = ROOT / "channel" / "specs" / "what-is-inside-chili-coffee-honey.json"
import food_episode as FE                                      # noqa: E402
if spec_p.exists() and BF.food_problems(spec_p.stem, spec_p)[0]:
    res = V.v55_food_episode().as_dict()
    check(not res["failures"], f"V55 reds main on a held episode: {res['failures']}")
    check(any("HELD by the upload lane" in n for n in res.get("notes") or []),
          f"V55 does not note the held episode: {res.get('notes')}")
    real = BF.food_hold
    BF.food_hold = lambda slug: None
    try:
        res = V.v55_food_episode().as_dict()
        check(any("it would ship" in f for f in res["failures"]),
              "V55 passed a failing episode that food_hold would ship")
    finally:
        BF.food_hold = real

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
