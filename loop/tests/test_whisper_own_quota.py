"""Whisper Almanac on its own Google Cloud project bills its own quota day.

Her call 16 Nov 2026: the Almanac gets its own 10,000 units (project
whisper-almanac-uploads). Proved both ways:
  1. own-project token: a full How We Know day does not stop an Almanac
     upload, and the spend lands in loop/state/whisper_quota.json, never in
     How We Know's ledger;
  2. a token still on How We Know's client: the shared day and its reserves
     apply, and the spend lands in the shared ledger;
  3. the Almanac's own day still runs out (no unbounded spending).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"
import quota                                                # noqa: E402
import whisper_upload as WU                                 # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="whisper-quota-"))
quota.STATE, quota.WHISPER_STATE = tmp / "quota.json", tmp / "whisper_quota.json"
full = {"day": quota._today(), "spent": 9500, "by_lane": {"cloud-upload": 9500}}
fails: list[str] = []


def ledger(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


quota.STATE.write_text(json.dumps(full))
WU.credentials = lambda c=None: {"client_id": "x", "project": quota.WHISPER_PROJECT}
if not WU.afford():
    fails.append("own project: a full How We Know day stopped the Almanac upload")
WU.spend(1652)
if ledger(quota.WHISPER_STATE).get("spent") != 1652 or ledger(quota.STATE)["spent"] != 9500:
    fails.append(f"own project: spend went to the wrong ledger "
                 f"({ledger(quota.WHISPER_STATE)}, shared {ledger(quota.STATE)['spent']})")

WU.credentials = lambda c=None: {"client_id": "x"}
if WU.afford():
    fails.append("shared client: a full How We Know day did not stop the Almanac upload")
WU.spend(1)
if ledger(quota.STATE)["spent"] != 9501:
    fails.append("shared client: the spend did not land in the shared ledger")

WU.credentials = lambda c=None: {"client_id": "x", "project": quota.WHISPER_PROJECT}
quota.WHISPER_STATE.write_text(json.dumps({"day": quota._today(), "spent": 9000, "by_lane": {}}))
if WU.afford():
    fails.append("own project: the Almanac's own day never runs out")

if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print("PASS: the Almanac bills its own quota day on its own project (5 checks)")
