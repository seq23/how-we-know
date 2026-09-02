"""The runtime target must mean the same thing in every place that has one.

On 2026-09-01 the owner asked whether new episodes were being authored at 12
minutes. They were not — and the reason is the defect this repo keeps finding:
**two components each keeping their own number with no link between them.**

    loop/config.json   retention.runtime_minutes = 7.5   what retention is judged against
    loop/author.py     TARGET_WORDS = 2100               what scripts are actually written to
    loop/monthly.py    CHANGE_BOUNDS min = 4.0           how far the review may move it

Setting `runtime_minutes` alone changed nothing, because the authoring lane never
reads it. Someone could raise the measured target to 12 and keep shipping
eight-minute videos indefinitely, with every stage green.

The conversion is MEASURED, not assumed: across all 16 finished episodes, ~1,200
narration words render to 8.1 minutes — an effective 150 words per minute once
beat pacing and pauses are counted. TARGET_WORDS counts the whole script, which
runs about 1.75x the narration.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WPM = 150.0            # measured across 16 rendered episodes
SCRIPT_RATIO = 1.75    # whole script : narration
TOLERANCE_MIN = 1.0    # authored runtime must land within a minute of the target
OWNER_FLOOR = 10.0     # owner decision 2026-09-01: 10-11 minutes, every batch


def check() -> list[str]:
    fails, examined = [], 0
    cfg = json.loads((ROOT / "loop" / "config.json").read_text())
    author = (ROOT / "loop" / "author.py").read_text()
    monthly = (ROOT / "loop" / "monthly.py").read_text()

    target = float(cfg["retention"]["runtime_minutes"])

    # 1 - the authored length must actually produce the measured target
    examined += 1
    m = re.search(r"^TARGET_WORDS = (\d+)", author, re.M)
    if not m:
        fails.append("loop/author.py has no TARGET_WORDS; the authored length "
                     "cannot be checked against the runtime target")
    else:
        implied = int(m.group(1)) / SCRIPT_RATIO / WPM
        if abs(implied - target) > TOLERANCE_MIN:
            fails.append(
                f"TARGET_WORDS={m.group(1)} implies {implied:.1f} min at "
                f"{WPM:.0f} wpm, but retention.runtime_minutes is {target}. "
                f"Scripts would be written to one length and judged against "
                f"another.")

    # 2 - the hard floor must sit below the target but not absurdly below
    examined += 1
    f = re.search(r"if words < (\d+)", author)
    if not f:
        fails.append("loop/author.py has no narration word floor")
    else:
        floor_min = int(f.group(1)) / WPM
        if floor_min > target:
            fails.append(f"the {f.group(1)}-word floor ({floor_min:.1f} min) is "
                         f"above the {target} min target; every draft fails")
        if floor_min < target - 2.5:
            fails.append(f"the {f.group(1)}-word floor is {floor_min:.1f} min "
                         f"against a {target} min target — too slack to catch a "
                         f"short draft")

    # 3 - the monthly review must not be able to undo the owner's floor
    examined += 1
    b = re.search(r'"retention\.runtime_minutes":\s*\{"min":\s*([\d.]+),\s*"max":\s*([\d.]+)', monthly)
    if not b:
        fails.append("loop/monthly.py CHANGE_BOUNDS no longer names "
                     "retention.runtime_minutes; the fence cannot be checked")
    else:
        lo, hi = float(b.group(1)), float(b.group(2))
        if lo < OWNER_FLOOR:
            fails.append(f"the monthly review may shorten runtime to {lo} min, "
                         f"below the owner's {OWNER_FLOOR} min floor. Two thin "
                         f"months would silently reverse a decision she made.")
        if not (lo <= target <= hi):
            fails.append(f"runtime_minutes {target} is outside the review's own "
                         f"bounds {lo}-{hi}")

    if examined == 0:
        fails.append("examined 0 runtime facts — this test cannot see what it "
                     "is meant to govern")
    print(f"inspected {examined} runtime-coherence fact(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print(f"{len(f)} failure(s)" if f else
          "all green - authored length, measured runtime and the review fence agree")
    raise SystemExit(1 if f else 0)
