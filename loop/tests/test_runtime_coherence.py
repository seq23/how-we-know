"""The runtime target must mean the same thing in every place that has one.

On 2026-09-01 the owner asked whether new episodes were being authored at 12
minutes. They were not — and the reason is the defect this repo keeps finding:
**two components each keeping their own number with no link between them.**

    loop/config.json   retention.runtime_minutes   what retention is judged against
    loop/author.py     NARRATION_TARGET_WORDS       what scripts are actually written to
    loop/monthly.py    CHANGE_BOUNDS min             how far the review may move it

Setting `runtime_minutes` alone changed nothing, because the authoring lane
never read it — until 2026-09-03, when three call sites for a speaking rate
(loop/config.json's old runtime_minutes-as-divisor, author.py's hardcoded 150
wpm, and the FORMAT template's "at 145 WPM") turned out to all be different
guesses that had never been checked against a real render. `loop/durations.py`
is now the ONE place a speaking rate is measured, from real renders via
ffprobe. This test used to regex-match a hardcoded `TARGET_WORDS = <int>`
literal in author.py's source — exactly the "hardcoded number in prose that
nothing checks" trap CLAUDE.md warns about, and it broke the moment that
literal correctly became a DERIVED expression. It now imports the real
modules and checks that the DERIVATION agrees with config, not that a literal
matches a regex — so the next person who changes the measured wpm, or the
target minutes, cannot silently break the agreement this test exists to
protect, and neither can this test file itself go stale the way its
predecessor's docstring did (it still said "16 finished episodes" and "150
wpm" after both had changed).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "loop"))

TOLERANCE_MIN = 0.25   # the derivation is exact math; this only forgives rounding


def check() -> list[str]:
    fails, examined = [], 0
    cfg = json.loads((ROOT / "loop" / "config.json").read_text())
    import durations as D                                 # noqa: PLC0415
    import author as A                                     # noqa: PLC0415
    monthly = (ROOT / "loop" / "monthly.py").read_text()

    target = float(cfg["retention"]["runtime_minutes"])
    floor_min_cfg = float(cfg["retention"]["runtime_floor_minutes"])
    wpm = D.wpm()

    # 1 - author.py's own target constant must equal config's runtime_minutes,
    # and the narration word count it derives must actually imply that many
    # minutes at the MEASURED rate. Two different failure modes, both real:
    # the constant drifting from config, or the arithmetic drifting from wpm.
    examined += 1
    if abs(A.RUNTIME_TARGET_MINUTES - target) > TOLERANCE_MIN:
        fails.append(
            f"loop/author.py RUNTIME_TARGET_MINUTES={A.RUNTIME_TARGET_MINUTES} "
            f"disagrees with loop/config.json retention.runtime_minutes="
            f"{target}. Scripts would be written to one length and judged "
            f"against another.")
    implied = A.NARRATION_TARGET_WORDS / wpm
    if abs(implied - A.RUNTIME_TARGET_MINUTES) > TOLERANCE_MIN:
        fails.append(
            f"loop/author.py NARRATION_TARGET_WORDS={A.NARRATION_TARGET_WORDS} "
            f"implies {implied:.2f} min at the measured {wpm} wpm, but "
            f"RUNTIME_TARGET_MINUTES is {A.RUNTIME_TARGET_MINUTES}. The "
            f"derivation itself has drifted from the rate it claims to use.")

    # 2 - the hard floor must sit below the target but not absurdly below, and
    # must match the owner's floor in config, not a number typed twice.
    examined += 1
    if abs(A.RUNTIME_FLOOR_MINUTES - floor_min_cfg) > TOLERANCE_MIN:
        fails.append(
            f"loop/author.py RUNTIME_FLOOR_MINUTES={A.RUNTIME_FLOOR_MINUTES} "
            f"disagrees with loop/config.json "
            f"retention.runtime_floor_minutes={floor_min_cfg}.")
    floor_min = A.NARRATION_FLOOR_WORDS / wpm
    if floor_min > target:
        fails.append(f"the {A.NARRATION_FLOOR_WORDS}-word floor ({floor_min:.1f} "
                     f"min) is above the {target} min target; every draft "
                     f"fails")
    if floor_min < target - 2.5:
        fails.append(f"the {A.NARRATION_FLOOR_WORDS}-word floor is "
                     f"{floor_min:.1f} min against a {target} min target — "
                     f"too slack to catch a short draft")

    # 3 - the monthly review must not be able to undo the owner's floor
    examined += 1
    b = re.search(r'"retention\.runtime_minutes":\s*\{"min":\s*([\d.]+),\s*"max":\s*([\d.]+)', monthly)
    if not b:
        fails.append("loop/monthly.py CHANGE_BOUNDS no longer names "
                     "retention.runtime_minutes; the fence cannot be checked")
    else:
        lo, hi = float(b.group(1)), float(b.group(2))
        if lo < floor_min_cfg:
            fails.append(f"the monthly review may shorten runtime to {lo} min, "
                         f"below the owner's {floor_min_cfg} min floor "
                         f"(loop/config.json retention.runtime_floor_minutes). "
                         f"Two thin months would silently reverse a decision "
                         f"she made.")
        if not (lo <= target <= hi):
            fails.append(f"runtime_minutes {target} is outside the review's own "
                         f"bounds {lo}-{hi}")

    if examined == 0:
        fails.append("examined 0 runtime facts — this test cannot see what it "
                     "is meant to govern")
    print(f"inspected {examined} runtime-coherence fact(s) at the measured "
          f"{wpm} wpm")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print(f"{len(f)} failure(s)" if f else
          "all green - authored length, measured runtime and the review fence agree")
    raise SystemExit(1 if f else 0)
