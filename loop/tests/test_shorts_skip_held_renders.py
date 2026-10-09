"""A Short is never published for an episode the render gate is holding.

WHAT HAPPENED. 2026-10-03: after six nights on which bin/batch-session.sh died
at the captions step before reaching shelve_shorts (fixed in #137), the first
batch to get through cut and shelved four Shorts. Three of the four were cut
from episodes loop/render_gate.py was HOLDING under the 10-minute floor
(9.86-9.90 min). Both episode upload routes consult loop/state/render_hold.json
and refuse a held slug; shorts_lane.pending() did not, so the cloud Shorts lane
would have published a Short pointing back at an episode that was not on the
channel - the held render reaching YouTube by the one route nobody had closed.

WHAT THIS PROVES, against a planted hold file rather than live state:
  1. a held slug is absent from pending() even though its cut is on the shelf;
  2. a slug that is not held, with a cut on the shelf, is present;
  3. the hold is a DEFERRAL: once the hold file names nothing, the slug returns.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))

tmp = Path(tempfile.mkdtemp(prefix="shorts-held-test-"))
HOLD = tmp / "render_hold.json"
os.environ["LOOP_RENDER_HOLD"] = str(HOLD)

import batch_queue  # noqa: E402
import render_gate  # noqa: E402
import shorts_lane as SL  # noqa: E402

assert render_gate.HOLD == HOLD, "LOOP_RENDER_HOLD must point the gate at the planted file"

rows = [{"slug": "held-under-floor"}, {"slug": "finished-and-clear"},
        {"slug": "already-published"}]
batch_queue.queued_entries = lambda: rows
SL.load_ledger = lambda: {"published": [{"slug": "already-published"}], "updated": None}
on_shelf = lambda slug, rank=1: True   # every cut and receipt is on the shelf   # noqa: E731

HOLD.write_text(json.dumps({
    "held": {"held-under-floor": ["held-under-floor: rendered 9.87 min, under the 10.0-minute hard floor"]},
    "week": "2026-W40", "at": "2026-10-03T10:54:49+00:00"}), encoding="utf-8")

got = SL.pending(have=on_shelf)
assert "held-under-floor" not in [p.slug for p in got], f"a held render reached the Shorts lane: {got}"
assert got == [SL.Pick("finished-and-clear", 1)], f"the clear episode must still publish: {got}"

# The hold lifts: the slug comes back in publish order, nothing was dropped.
HOLD.write_text(json.dumps({"held": {}, "week": "2026-W40", "at": None}), encoding="utf-8")
got = SL.pending(have=on_shelf)
assert got == [SL.Pick("held-under-floor", 1), SL.Pick("finished-and-clear", 1)], f"deferred, not dropped: {got}"

# No hold file at all is "nothing held", as the gate itself promises.
HOLD.unlink()
assert SL.pending(have=on_shelf) == [SL.Pick("held-under-floor", 1), SL.Pick("finished-and-clear", 1)]
print("OK  test_shorts_skip_held_renders: a held render is deferred by the Shorts lane and returns when the hold lifts")
