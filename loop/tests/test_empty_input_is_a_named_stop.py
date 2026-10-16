#!/usr/bin/env python3
"""A legitimately empty input set is a NAMED, visible N/A - never a pass,
and never an excuse for a reader that reached nothing.

THE DEFECT THIS GUARDS (CONFIRMED 2026-10-16, main 30e1d54, loop-tests run
38912564718). The Mac backfill uploaded the last queued script that carried a
[HUMAN] beat; the six queued slugs left had no script authored yet. V71 had
nothing to govern and went `FAIL(examined 0)`, turning main red on a correct
channel. The same class hit V5, V9-V15 and V32 before, each answered with its
own hand-set `exempt = True`, which cannot tell "nothing to govern" from "a
reader that reached nothing".

Result.nothing_to_examine() is the one door. This test pins both directions:
  A. an empty ACCOUNT (the reader reached no inputs) stays a hard FAIL;
  B. a full account is N/A(EMPTY:<code>), ok, and names every item;
  C. it cannot follow real work or a failure;
  D. V71 on an empty queue FAILS; on a queue of published / unauthored slugs
     it is N/A(EMPTY:NO_QUEUED_HUMAN_BEAT) naming them; and with a beat-carrying
     script back in the queue it still EXAMINES it (not an always-empty guard).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"
HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import ledger  # noqa: E402
import pov_repair  # noqa: E402
import validate  # noqa: E402
from validate import Result  # noqa: E402

cases = 0
fails: list[str] = []


def expect(cond: bool, label: str, detail: str = "") -> None:
    global cases
    cases += 1
    print(f"  {'ok ' if cond else 'NOT'} {cases}: {label}")
    if not cond:
        fails.append(f"{label} {detail}".strip())


# A. an empty account is a reader that reached nothing
r = Result("probe")
r.nothing_to_examine("PROBE_EMPTY", "nothing queued", {})
expect(not r.ok and r.status.startswith("FAIL"),
       "an empty account stays a hard FAIL", r.status)

# B. a full account is a named, visible N/A
r = Result("probe")
r.nothing_to_examine("PROBE_EMPTY", "nothing queued",
                     {"b-slug": "published", "a-slug": "no script yet"})
expect(r.ok and r.status == "N/A(EMPTY:PROBE_EMPTY)",
       "a full account is ok and reads N/A(EMPTY:<code>)", r.status)
expect(bool(r.stops) and r.stops[0]["items"] == ["a-slug", "b-slug"]
       and "1 published" in r.stops[0]["message"],
       "the stop names every item and the reason counts", str(r.stops))

# C. it cannot follow real work or a failure
r = Result("probe")
r.examined = 1
r.nothing_to_examine("PROBE_EMPTY", "x", {"a": "published"})
expect(not r.ok, "after real work it is a failure", r.status)
r = Result("probe")
r.fail("a real defect")
r.nothing_to_examine("PROBE_EMPTY", "x", {"a": "published"})
expect(not r.ok and r.status.startswith("FAIL"),
       "it never hides an earlier failure", r.status)

# D. V71
r = validate.v71_queued_pov_traced(slugs=[])
expect(not r.ok and r.status.startswith("FAIL"),
       "V71 on an EMPTY queue hard-fails", r.status)

published = [e["slug"] for e in ledger.load()["published"]
             if pov_repair.human_beat(e["slug"]) is not None]
expect(bool(published), "fixture premise: a published script with a [HUMAN] beat")
beat_slug = published[0]
ghost = "zz-queued-but-never-authored"
r = validate.v71_queued_pov_traced(slugs=[beat_slug, ghost])
expect(r.ok and r.status == "N/A(EMPTY:NO_QUEUED_HUMAN_BEAT)",
       "V71 on published + unauthored slugs is a named N/A", r.status)
expect(bool(r.stops) and r.stops[0]["items"] == sorted([beat_slug, ghost]),
       "V71's stop accounts for every queued slug", str(r.stops))

_real = ledger.load


def _without_beat_slug(*a, **k):
    d = dict(_real(*a, **k))
    d["published"] = [e for e in d.get("published") or []
                      if e.get("slug") != beat_slug]
    return d


ledger.load = _without_beat_slug
try:
    r = validate.v71_queued_pov_traced(slugs=[beat_slug, ghost])
finally:
    ledger.load = _real
expect(r.examined == 1 and not r.stops,
       "V71 still EXAMINES a queued, unpublished [HUMAN] beat",
       f"examined {r.examined} status {r.status}")

print(f"examined {cases} case(s), {len(fails)} failed")
if cases == 0:
    sys.exit("examined ZERO cases")
for f in fails:
    print(f"  ✗ {f}")
sys.exit(1 if fails else 0)
