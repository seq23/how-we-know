"""A food episode is fitted to the 28-32 minute contract at EVERY rate the voice has shown.

THE INCIDENT (2026-10-26, run 40328601655). loop/food_author.py fitted
what-is-inside-chili-coffee-honey to 30.5 minutes at FOOD_WPM = 169.5 - one
episode's measured rate used as a fact - so it wrote 5,151 words. The same food
voice read them at 158.0 wpm: the stitched render ran 32.6 minutes, outside
visuals/food_episode.EPISODE_MINUTES, and only V55 on main said so, after a
full night of rendering. A rule judged one stage after the point where the
episode could still be fixed.

WHAT THIS PROVES:
  1. food_author's window is food_episode.EPISODE_MINUTES itself (one copy);
  2. measured_rates() reads every stitched food episode, superseded ones too,
     from the render's own spoken words - hard-fails on fewer than two;
  3. word_window() lands inside the contract at the fastest AND slowest rate;
  4. the 5,151-word chili script fails length_problems() at the measured rates
     (and passed at the old single rate - the defect class, reproduced);
  5. fit() trims a synthetic episode to the window's aim, never dropping a
     protected section;
  6. every lane-authored food script on disk passes length_problems();
  7. loop/food_lane.py checks the voiced runtime BEFORE it renders, and keys its
     state on the script, so a trimmed script is re-voiced, never re-stitched
     from the old voice.
Hard-fails on zero examined items.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import food_author as FA   # noqa: E402
import food_episode as FE  # noqa: E402
import food_lane as FL     # noqa: E402

fails: list[str] = []
examined = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    print(f"{'ok ' if ok else '✗  '} {label}" + (f" - {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(f"{label}: {detail}")


# 1. one copy of the window
check("food_author's window IS food_episode.EPISODE_MINUTES",
      tuple(FA.MINUTES) == tuple(FE.EPISODE_MINUTES), f"{FA.MINUTES} vs {FE.EPISODE_MINUTES}")

# 2. the measured rates
rates = FA.measured_rates()
check("measured_rates() reads at least two stitched food episodes", len(rates) >= 2, str(rates))
check("a superseded render still counts (the 158 wpm chili measurement)",
      any(n == "what-is-inside-chili-coffee-honey" and 150 < r < 165 for n, r in rates), str(rates))
rs = [r for _, r in rates] or [FA.FOOD_WPM]

# 3. the window holds at every rate
lo, aim, hi = FA.word_window(rs)
check("the window is not empty at the measured rates", lo <= aim <= hi, f"{lo}, {aim}, {hi}")
for r in rs:
    check(f"the window's floor {lo} runs >= {FA.MINUTES[0]} min at {r:.1f} wpm",
          lo / r >= FA.MINUTES[0], f"{lo / r:.2f}")
    check(f"the window's ceiling {hi} runs <= {FA.MINUTES[1]} min at {r:.1f} wpm",
          hi / r <= FA.MINUTES[1], f"{hi / r:.2f}")

# 4. the incident, reproduced
incident = "**Word count:** 5151\n"
check("the 5,151-word chili script fails length_problems() at the measured rates",
      bool(FA.length_problems(incident, rs)), str(rs))
check("...and passed at the old single rate (the defect class)",
      not FA.length_problems(incident, [169.5]))
check("rates spread wider than the window is a named problem, not a pass",
      bool(FA.length_problems("**Word count:** 4900\n", [140.0, 180.0])))

# 5. fit() reaches the aim without dropping protected sections
body = " ".join(["word"] * 300)
seg = lambda f: [(f"{f}: Why?", body), (f"{f}: A", body), (f"{f}: B", body),  # noqa: E731
                 (f"{f}: C", body), (f"{f}: Evidence limit", body), (f"{f}: Closing", body)]
segs = FA.fit([seg("X"), seg("Y"), seg("Z")], 300, aim=4000)
total = 300 + sum(FA.words(b) for s in segs for _, b in s)
heads = {h for s in segs for h, _ in s}
check("fit() trims to the aim", total <= 4000, str(total))
check("fit() keeps every opening, evidence limit and closing",
      all(f"{f}: {k}" in heads for f in "XYZ" for k in ("Why?", "Evidence limit", "Closing")),
      str(sorted(heads)))

# 6. every lane-authored script on disk
authored = [p for p in sorted(FA.FOOD_DIR.glob("*.md")) if FA.LANE_MARK in p.read_text()]
check("at least one lane-authored food script exists", bool(authored))
for p in authored:
    check(f"{p.name} fits the window at every measured rate",
          not FA.length_problems(p.read_text()), str(FA.length_problems(p.read_text())))

# 7. the Mac lane: runtime gate before render, state keyed on the script
src = inspect.getsource(FL.run)
gate, render = src.find("FOOD_RUNTIME_OFF_CONTRACT"), src.find('"render" not in st["stages"]')
check("food_lane.run checks the voiced runtime before it renders",
      0 <= gate < render, f"gate at {gate}, render at {render}")
check("food_lane.run reads the window from FE.EPISODE_MINUTES", "FE.EPISODE_MINUTES" in src)
check("food_lane.run keys its state and work dir on the script's sha",
      "script_sha" in src and "WORK / ep / sha" in src)

if examined == 0:
    fails.append("examined zero items")
print(f"{examined} check(s), {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
