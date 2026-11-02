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
# The OLD style (unstamped scripts: 13 Oct, chili/coffee/honey) keeps its own
# window and rate; new episodes are calm (config/food_style.json, 2 Nov 2026).
(OLD_MIN, OLD_AIM, OLD_WPM) = A.length_of(None)
# 1. pinned to the slower measured rate (within 1 wpm)
check(abs(OLD_WPM - MEASURED["chili-coffee-honey (26 Oct)"]) <= 1.0,
      f"the old style's FOOD_WPM {OLD_WPM} is not the measured 158.0")
# 2. the aimed word count lands inside the window at EVERY measured rate
aim_words = OLD_AIM * OLD_WPM
for name, rate in MEASURED.items():
    mins = aim_words / rate
    check(OLD_MIN[0] <= mins <= OLD_MIN[1],
          f"aim of {aim_words:.0f} words runs {mins:.1f} min at {name}'s {rate:.1f} wpm")
check(tuple(OLD_MIN) == (28.0, 32.0), f"the old style's window moved: {OLD_MIN}")
# ...and the calm style's: aim 15 min inside its own 10-18 window at its rate
if A.STYLE:
    L = A.STYLE["length"]
    check(tuple(A.MINUTES) == tuple(L["minutes"]) and A.AIM_MINUTES == L["aim_minutes"],
          f"new episodes are not authored in the calm window: {A.MINUTES}, aim {A.AIM_MINUTES}")
    check(A.MINUTES[0] <= A.AIM_MINUTES <= A.MINUTES[1], "the calm aim is outside its window")

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
