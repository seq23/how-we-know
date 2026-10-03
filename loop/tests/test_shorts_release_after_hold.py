"""A Short parked behind the render gate comes back by itself when the hold lifts.

WHAT HAPPENED. 2026-10-03 12:46 UTC: the cloud Shorts lane was dispatched
against main minutes before #138 (pending() skipping render_gate.held_slugs())
landed, and it uploaded and scheduled Shorts for two episodes the gate was
holding under the 10-minute floor - qPnBKYAR3ps and 5JErm9uFsFw, due public
that night, pointing into episodes that were not on the channel. Both were
unscheduled by hand (private, publishAt cleared, read back) and their ledger
rows flagged `held_by: render_hold` with no scheduled time. The rows stay:
dropping them would make pending() upload the same cuts again.

WHAT THIS PROVES, against a planted hold file, a planted ledger and a fake
YouTube client that records every status write:
  1. a parked row whose episode is STILL held is left alone - no API call, no
     schedule, flag intact - and is named in a note, not a stop;
  2. a parked row whose hold has LIFTED gets exactly one publishAt write, the
     next evening slot, its flag cleared and the ledger saved;
  3. a run with nothing to release records no work, so Rule 0 still trips;
  4. loop/shorts_cloud.py actually invokes the release pass: with nothing new
     on the shelf and one hold lifted, run() exits 0 with that release as its
     work; with nothing to release it still takes NO_SHORTS_SHELVED.
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

tmp = Path(tempfile.mkdtemp(prefix="shorts-release-test-"))
HOLD = tmp / "render_hold.json"
LEDGER = tmp / "shorts_ledger.json"
(tmp / "stops").mkdir()
os.environ["LOOP_RENDER_HOLD"] = str(HOLD)
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")
os.environ["LOOP_DRY_RUN"] = "1"          # never a real write, never a credential

import arming  # noqa: E402
import batch_queue  # noqa: E402
import publish as P  # noqa: E402
import quota  # noqa: E402
import r2  # noqa: E402
import render_gate  # noqa: E402
import shorts_cloud as SC  # noqa: E402
import shorts_lane as SL  # noqa: E402
import upload as up  # noqa: E402

assert render_gate.HOLD == HOLD
SL.LEDGER = LEDGER
SL.time.sleep = lambda s: None


# ---- the fake YouTube client -------------------------------------------------
class FakeTube:
    """Records every status write; read_status_full echoes what was written."""
    def __init__(self):
        self.calls: list[tuple] = []
        self.state: dict[str, dict] = {}

    def set_privacy(self, token, vid, privacy, publish_at=None):
        self.calls.append((vid, privacy, publish_at))
        self.state[vid] = {"found": True,
                           "privacy": "private" if publish_at else privacy,
                           "publishAt": publish_at}

    def read_status_full(self, token, vid):
        return self.state.get(vid, {"found": True, "privacy": "private",
                                    "publishAt": None})


tube = FakeTube()
P.set_privacy = tube.set_privacy
P.read_status_full = tube.read_status_full
SPENT: list[tuple] = []
quota.spend = lambda units, lane: SPENT.append((units, lane))


class FakeStage:
    def __init__(self):
        self.units, self.notes = [], []

    def work(self, what):
        self.units.append(what)

    def note(self, what):
        self.notes.append(what)

    def named_stop(self, code, message, detail=None, unblock="", held_items=None):
        raise AssertionError(f"unexpected named stop {code}: {message}")


def plant(held: dict):
    HOLD.write_text(json.dumps({"held": held, "week": "2026-W40",
                                "at": "2026-10-03T10:54:49+00:00"}))
    LEDGER.write_text(json.dumps({"published": [
        {"slug": "aired-normally", "video_id": "vidA", "privacy": "private",
         "scheduled_publish_at": "2026-10-02T00:00:00Z", "rank": 1, "lane": "shorts-cloud"},
        {"slug": "still-held", "video_id": "vidH", "privacy": "private",
         "scheduled_publish_at": None, "held_by": "render_hold", "rank": 1, "lane": "shorts-cloud"},
        {"slug": "hold-lifted", "video_id": "vidL", "privacy": "private",
         "scheduled_publish_at": None, "held_by": "render_hold", "rank": 1, "lane": "shorts-cloud"},
    ], "updated": None}, indent=2))


fails: list[str] = []

# ---- 1 + 2: one row still held, one row whose hold has lifted ---------------
plant({"still-held": ["still-held: rendered 9.87 min, under the 10.0-minute hard floor"]})
st = FakeStage()
n = SL.release_held(st, "fake-token", lane="shorts-cloud")
led = json.loads(LEDGER.read_text())
rows = {r["slug"]: r for r in led["published"]}

if n != 1:
    fails.append(f"1/2: release_held returned {n}, expected 1")
if tube.calls != [("vidL", "private", tube.calls[0][2] if tube.calls else None)]:
    fails.append(f"2: expected exactly one private+publishAt write for vidL, got {tube.calls}")
stamp = tube.calls[0][2] if tube.calls else None
if not stamp or not stamp.endswith("Z"):
    fails.append(f"2: publishAt must be an RFC3339 UTC stamp, got {stamp!r}")
if rows["hold-lifted"].get("scheduled_publish_at") != stamp:
    fails.append(f"2: ledger row not rescheduled to {stamp}: {rows['hold-lifted']}")
if "held_by" in rows["hold-lifted"] or not rows["hold-lifted"].get("released_at"):
    fails.append(f"2: flag must be cleared and released_at set: {rows['hold-lifted']}")
if stamp and SL._stamp(stamp) <= SL._stamp("2026-10-02T00:00:00Z"):
    fails.append(f"2: the released slot must be the NEXT evening slot after the ledger's last, got {stamp}")
if rows["still-held"].get("held_by") != "render_hold" or rows["still-held"].get("scheduled_publish_at") is not None:
    fails.append(f"1: a still-held row was touched: {rows['still-held']}")
if any(c[0] == "vidH" for c in tube.calls):
    fails.append("1: YouTube was called for a still-held Short")
if not any("still-held" in note for note in st.notes):
    fails.append(f"1: the still-held row must be named in a note: {st.notes}")
if len(st.units) != 1 or "hold-lifted" not in st.units[0]:
    fails.append(f"2: the release is exactly one unit of work: {st.units}")
if SPENT != [(SL.FLIP_UNITS, "shorts-cloud")]:
    fails.append(f"2: the flip must be charged to quota once: {SPENT}")

# ---- 3: nothing to release is not work ---------------------------------------
tube.calls.clear()
st2 = FakeStage()
n2 = SL.release_held(st2, "fake-token", lane="shorts-cloud")
if n2 != 0 or st2.units or tube.calls:
    fails.append(f"3: a second pass must release nothing and record no work: n={n2} units={st2.units} calls={tube.calls}")
if not any("still-held" in note for note in st2.notes):
    fails.append(f"3: the still-held row is still named: {st2.notes}")

# ---- 4: shorts_cloud.run() invokes the pass ---------------------------------
shelf = r2.LocalBackend(tmp / "shelf")                  # empty shelf: nothing new
SC.r2.require = lambda: shelf
SC.arming.gate = lambda st, lane: None
batch_queue.queued_entries = lambda: []
up.load_credentials = lambda cfg: {"access_token": "fake", "source": "test"}
up.access_token = lambda creds: "fake-token"

plant({"still-held": ["still-held: under the floor"]})  # hold-lifted is releasable again
tube.calls.clear()
try:
    rc = SC.run(limit=2)
except SystemExit as e:
    fails.append(f"4: run() must finish on a release alone, it exited {e.code}")
else:
    if rc != 0:
        fails.append(f"4: run() returned {rc}")
    if [c[0] for c in tube.calls] != ["vidL"]:
        fails.append(f"4: run() must release exactly vidL: {tube.calls}")
    row = {r["slug"]: r for r in json.loads(LEDGER.read_text())["published"]}["hold-lifted"]
    if "held_by" in row or not row.get("scheduled_publish_at"):
        fails.append(f"4: run() left the released row unflagged/unscheduled: {row}")

tube.calls.clear()
try:
    SC.run(limit=2)                                     # nothing new, nothing to release
    fails.append("4: with nothing to release and nothing shelved, run() must take NO_SHORTS_SHELVED")
except SystemExit:
    stops = list((tmp / "stops").glob("*shorts-cloud.json"))
    rec = json.loads(stops[0].read_text()) if stops else {}
    if rec.get("code") != "NO_SHORTS_SHELVED":
        fails.append(f"4: expected NO_SHORTS_SHELVED, stop record says {rec.get('code')!r} ({stops})")
    if tube.calls:
        fails.append(f"4: YouTube was written to on a run with nothing to do: {tube.calls}")

if fails:
    print("FAIL test_shorts_release_after_hold:")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("OK  test_shorts_release_after_hold: a parked Short is left alone while held, "
      "rescheduled exactly once when the hold lifts, and nothing-to-release is not work")
