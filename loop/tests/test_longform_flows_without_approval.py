"""Long-forms flow without her approval (18 Nov 2026).

No ruling of hers requires approving every long-form (docs/CHANNEL-PLAN.md:
"Runs without the owner. No approval step"). The gate had been re-armed by
breaker.lift_longform and starved the channel once her 3 Nov cuts were out.

  1. the committed setting has the gate off;
  2. a hold then lift does not switch it back on;
  3. with the gate off, an unapproved render is eligible in
     backfill.library_pending (with it on, the same render is HELD: the
     gate still works if she ever sets it);
  4. the switch-off gets the 48h dating grace, and not after 48h.
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
TMP = tempfile.mkdtemp(prefix="gate-off-")
os.environ["LOOP_BREAKER_FLAG"] = os.path.join(TMP, "breaker.json")
os.environ.setdefault("LOOP_STOPS_DIR", os.path.join(TMP, "stops"))
sys.path.insert(0, str(LOOP))
import breaker  # noqa: E402

fails = []

# 1. the committed setting
live = json.loads((LOOP / "state" / "breaker.json").read_text())
if live.get("longform_owner_approval_required"):
    fails.append("loop/state/breaker.json has the long-form approval gate on again")

# 2. a hold then lift does not re-arm it
Path(breaker.FLAG).write_text(json.dumps(dict(breaker.CLOSED)))
breaker.hold_longform("test hold")
b = breaker.lift_longform("test lift")
if b.get("longform_owner_approval_required"):
    fails.append("lift_longform switched the approval gate on by itself")

# 3. eligibility with the gate off and on
import backfill  # noqa: E402
import batch_queue  # noqa: E402
import render_gate  # noqa: E402
import lengthen  # noqa: E402
import ledger  # noqa: E402
import approved_renders  # noqa: E402

with patch.object(batch_queue, "queued_entries", return_value=[{"slug": "unapproved-ready"}]), \
     patch.object(render_gate, "held_slugs", return_value=set()), \
     patch.object(lengthen, "upload_hold", return_value=None), \
     patch.object(ledger, "published_slugs", return_value=set()), \
     patch.object(approved_renders, "load", return_value={}), \
     patch.object(backfill, "food_hold", return_value=None):
    for gate, want in ((False, ["unapproved-ready"]), (True, [])):
        with patch.object(breaker, "load", return_value={"state": "closed",
                                                         "longform_owner_approval_required": gate}), \
             patch.object(breaker, "blocked_domains", return_value=set()):
            got = [s for s, *_ in backfill.library_pending(assets=lambda s: (Path("r"), Path("t")))]
        if got != want:
            fails.append(f"gate {'on' if gate else 'off'}: eligible {got}, want {want}")

# 4. the dating grace
now = dt.datetime(2026, 11, 18, 18, 0, tzinfo=dt.timezone.utc)
rec = {"state": "tripped", "longform_owner_approval_required": False,
       "history": [{"event": "longform_approval_off", "at": now.isoformat()}]}
if breaker.longform_dating_pending(rec, at=now + dt.timedelta(hours=20)) != "LONGFORM_DATING_PENDING":
    fails.append("no dating grace within 48h of the gate going off")
if breaker.longform_dating_pending(rec, at=now + dt.timedelta(hours=49)):
    fails.append("the dating grace outlived 48h")
if breaker.longform_dating_pending(dict(rec, longform_owner_approval_required=True), at=now):
    fails.append("a dating grace while the gate is still on")

if fails:
    print("FAIL test_longform_flows_without_approval")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_longform_flows_without_approval: gate off, a lift never re-arms it, "
      "an unapproved render is eligible, 48h dating grace")
