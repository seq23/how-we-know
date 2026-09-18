"""The format breaker fires only on JUDGEABLE domains - proven, not asserted.

WHAT HAPPENED. 18 September 2026, 21:14 UTC: the Friday measure lane tripped
the circuit breaker on `retention` - "every measured domain is below the
duration floor for 3 consecutive videos. A problem in all of them at once is
the format." - and halted every upload and public flip on the channel. The
evidence was eight videos with 2, 2, 3, 3, 4, 7, 12 and 40 views each, one of
them at 0s average view duration on two views.

docs/CHANNEL-PLAN.md says the format breaker fires when retention fails in
EVERY *judgeable* domain, and loop/config.json `domains.min_episodes_to_judge`
says judgeable means 8 measured episodes. loop/monthly.py honoured that.
loop/measure.py:breaker_cause() said "every domain that HAS enough measured
videos" in its docstring and checked nothing of the kind. A specification no
code read.

WHAT THIS PROVES, against planted rows on the real domain map:

  1. Two domains, each below the judgeability floor, every video below the
     duration floor: judgeable_domains() is empty and breaker_cause() is None.
     The 2026-09-18 shape does not trip.
  2. One domain at the floor with a full streak, the other under it: the trip
     is `format` on that one judgeable domain - the plan's "every judgeable
     domain" - and the unjudgeable one is neither holding nor breaching.
  3. Both judgeable, one breaching: `domain`, naming the right one. The niche
     path still works.
  4. Both judgeable, both breaching: `format`. The trip still fires when it
     should - this change narrows the evidence, it does not disarm the breaker.
  5. Both call sites in loop/measure.py pass the judgeable set. Restore the
     old two-argument call and this fails whatever breaker_cause() does.

Negative proof, recorded in the PR that introduced this: with `judgeable=`
dropped from breaker_cause(), assertion 1 returns a `format` trip on the
2026-09-18 rows. Hard-fails if the repo maps fewer than two domains.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import domains  # noqa: E402
import measure  # noqa: E402

fails: list[str] = []
cfg = json.load(open(os.path.join(LOOP, "config.json")))
FLOOR = float(cfg["retention"]["floor_avd_seconds"])
NEED = int(cfg["retention"]["breach_streak_to_trip"])
JUDGE = domains.min_episodes_to_judge(cfg)

# Real slugs, grouped by the domain the repo actually assigns them.
by_domain: dict[str, list[str]] = {}
for slug, d in domains.by_slug().items():
    by_domain.setdefault(d, []).append(slug)
names = sorted(d for d, s in by_domain.items() if len(s) >= JUDGE)
if len(names) < 2:
    print(f"FAIL Rule 0: need two domains with >= {JUDGE} scripts each, have {names}")
    sys.exit(1)
A, B = names[0], names[1]


def plant(spec: dict[str, list[float | None]]):
    """{domain: [avd, avd, ...]} -> (rows, ledger_published), oldest first."""
    rows, pub = [], []
    for d, avds in spec.items():
        for i, avd in enumerate(avds):
            slug = by_domain[d][i]
            vid = f"{d[:4]}-{i:02d}"
            pub.append({"slug": slug, "video_id": vid})
            rows.append({"video_id": vid, "views": 3,
                         "average_view_duration_s": avd})
    return rows, pub


def cause_for(spec):
    rows, pub = plant(spec)
    streaks = measure.domain_streaks(rows, pub, FLOOR)
    judgeable = measure.judgeable_domains(rows, pub, cfg)
    return measure.breaker_cause(streaks, NEED, judgeable), judgeable


bad = [FLOOR - 100.0] * NEED           # a full breach streak
good = [FLOOR + 100.0]
pad_bad = [FLOOR - 100.0] * (JUDGE - NEED)

# ---- 1: the 2026-09-18 shape: nobody judgeable, everybody "breaching" ---------
cause, judgeable = cause_for({A: bad + [FLOOR - 50.0], B: bad})
if judgeable:
    fails.append(f"1: {judgeable} judgeable with fewer than {JUDGE} measured each")
if cause is not None:
    fails.append(f"1: tripped {cause['cause']} on unjudgeable domains: {cause['why'][:90]}")

# ---- 2: one judgeable domain breaching, the other under the floor ------------
cause, judgeable = cause_for({A: pad_bad + bad, B: bad})
if set(judgeable) != {A}:
    fails.append(f"2: judgeable should be exactly {{{A}}}, got {judgeable}")
if not cause or cause["cause"] != "format":
    fails.append(f"2: one judgeable domain breaching should be `format`, got {cause}")
elif B in cause.get("domains", []):
    fails.append(f"2: the unjudgeable domain {B} was counted as breaching")

# ---- 3: both judgeable, one breaching -> that niche ----------------------------
cause, judgeable = cause_for({A: pad_bad + bad, B: pad_bad + bad[:-1] + good})
if set(judgeable) != {A, B}:
    fails.append(f"3: both should be judgeable, got {judgeable}")
if not cause or cause["cause"] != "domain" or cause.get("domain") != A:
    fails.append(f"3: expected `domain` trip naming {A}, got {cause}")

# ---- 4: both judgeable, both breaching -> the format -------------------------
cause, judgeable = cause_for({A: pad_bad + bad, B: pad_bad + bad})
if not cause or cause["cause"] != "format" or sorted(cause.get("domains", [])) != sorted([A, B]):
    fails.append(f"4: both judgeable and breaching should be `format` naming both, got {cause}")

# ---- 5: measure.py's call sites pass the judgeable set -------------------------
src = open(os.path.join(LOOP, "measure.py")).read()
# Real call sites assign the result; prose says "breaker_cause()" and defs
# say "def breaker_cause(".
calls = re.findall(r"cause = breaker_cause\(([^)]*)\)", src)
if len(calls) < 2:
    fails.append(f"5: expected two breaker_cause() call sites in measure.py, found {len(calls)}")
for c in calls:
    if "judgeable" not in c:
        fails.append(f"5: a breaker_cause() call site does not pass judgeable: ({c})")
if src.count("judgeable_domains(m[\"videos\"], pub, cfg)") < 2:
    fails.append("5: measure.py does not compute judgeable_domains() before each trip decision")

if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"OK breaker honours judgeability: {A} / {B}, floor {FLOOR}s, "
      f"streak {NEED}, judgeable at {JUDGE}; four shapes decided correctly, "
      f"both call sites pass the set")
