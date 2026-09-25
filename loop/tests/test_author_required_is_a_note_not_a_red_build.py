"""AUTHOR_REQUIRED is a green, self-resolving stop - red only when it repeats.

Owner instruction, 2026-09-25, on run 36164079633 going red because one of
four slots could not be auto-authored while the week still shipped three:
"why does it have to turn red on main because of the stop? why can't it skip
with a note?" The taxonomy already had the answer (self_resolving: green,
banner, job summary, committed record, capped) and AUTHOR_REQUIRED had simply
never been classified, so it fell to the default and paged.

Pinned here, through loop/common.py disposition() - the function the stage
wrapper actually consults - never by reading the JSON alone:

  1. first occurrence, briefs named        -> self_resolving (exit 0, no issue)
  2. second consecutive Monday             -> needs_human (the same lane
                                              falling short twice is a topic
                                              the generator cannot write)
  3. a stop that names no briefs           -> needs_human (it cannot say what
                                              it left for the next run)

Hard-fails on zero examined cases.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent

os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="author-required-"))
sys.path.insert(0, str(LOOP))
import common  # noqa: E402

DETAIL = {"briefs": ["what lives in the deep"],
          "stops": ["DRAFT_FAILED_VALIDATION"]}


def check() -> list[str]:
    fails, examined = [], 0

    examined += 1
    d, why = common.disposition("mon-draft", "AUTHOR_REQUIRED", DETAIL, 1)
    if d != "self_resolving":
        fails.append(f"first AUTHOR_REQUIRED is {d!r}, not self_resolving: a "
                     f"week that shipped its other slots and left a brief for "
                     f"next Monday is a note, not a red build ({why})")

    examined += 1
    d, why = common.disposition("mon-draft", "AUTHOR_REQUIRED", DETAIL, 2)
    if d != "needs_human":
        fails.append(f"second consecutive AUTHOR_REQUIRED is {d!r}, not "
                     f"needs_human: the same lane falling short two Mondays "
                     f"running is a topic the generator cannot write ({why})")

    examined += 1
    d, why = common.disposition("mon-draft", "AUTHOR_REQUIRED",
                                {"briefs": [], "stops": []}, 1)
    if d != "needs_human":
        fails.append(f"an AUTHOR_REQUIRED naming no briefs is {d!r}, not "
                     f"needs_human: a stop that cannot say what it left for "
                     f"the next run must not be waved through ({why})")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} AUTHOR_REQUIRED disposition case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - a slot the generator misses is a note, and only a "
          "repeat pages" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
