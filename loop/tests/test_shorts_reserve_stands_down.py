"""The Shorts reserve is released once the Shorts lane has RUN with nothing to
upload, so the repackage apply fits the day (issue #353, 9 Nov 2026).

On 6-9 Nov the episode lane spent 5,100 units a day, the Shorts shelf was
empty, and quota.shorts_reserve() still held 3,400 units for Shorts that the
18:00 CT lane had already looked for. The 18:30 CT repackage apply found 36
usable units and stopped QUOTA_EXHAUSTED five runs in a row.

  a. on that day's numbers, before the Shorts lane runs, the reserve holds
     (the apply fits none: a Short could still come);
  b. once the Shorts lane has run and stood down, all 4 waiting titles fit;
  c. the real lane, run against an EMPTY shelf, stands down (by_lane records
     it) - and a lane that has not run leaves the reserve in place;
  d. a dry run of the Shorts lane releases nothing.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable

import quota  # noqa: E402

fails: list[str] = []
examined = 0


def check(ok, msg):
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


TMP = Path(tempfile.mkdtemp(prefix="shorts-reserve-"))
quota.STATE = TMP / "quota.json"
today = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
NOV8 = {"day": today, "spent": 6164,
        "by_lane": {"cloud-upload": 5100, "handoff": 207, "captions": 601, "localize": 255, "demand": 1}}
quota.STATE.write_text(json.dumps(NOV8))
import repackage as RP  # noqa: E402

# a. before the Shorts lane runs
check(quota.shorts_reserve() == quota.SHORTS_PER_DAY_PEAK * quota.PER_VIDEO,
      f"(a) the Shorts reserve is released before the Shorts lane ran: {quota.shorts_reserve()}")
check(RP.affordable(RP.APPLY_UNITS, 4) == 0, "(a) the apply fits with the Shorts reserve still held")

# b. after it ran with nothing to upload
quota.stand_down("shorts-cloud")
check(quota.shorts_reserve() == 0, "(b) a Shorts lane that ran with nothing to upload still holds 3,400 units")
check(RP.affordable(RP.APPLY_UNITS, 4) == 4,
      f"(b) after the Shorts lane stood down only {RP.affordable(RP.APPLY_UNITS, 4)} of 4 titles fit")
check(json.loads(quota.STATE.read_text())["spent"] == 6164, "(b) standing down changed the units spent")

# c. the real lane on an empty shelf
HARNESS = '''
import json, os, sys
from pathlib import Path
LOOP = Path(%(loop)r); sys.path.insert(0, str(LOOP))
TMP = Path(os.environ["TEST_TMP"])
import quota, shorts_lane as SL, common, arming, breaker
(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
SL.LEDGER = TMP / "state" / "shorts_ledger.json"
SL.LEDGER.write_text(json.dumps({"published": [], "updated": None}))
quota.STATE = TMP / "state" / "quota.json"
quota.STATE.write_text(json.dumps(%(state)s))
common.STOPS = TMP / "state" / "stops"
arming.EVIDENCE = TMP / "state" / "lane_evidence.json"
breaker.guard = lambda lane: None
import shorts_cloud
try:
    shorts_cloud.run(limit=2, dry_run=%(dry)s)
except SystemExit:
    pass
print("BYLANE", json.dumps(json.loads(quota.STATE.read_text())["by_lane"]))
print("RESERVE", quota.shorts_reserve())
'''


def lane_run(dry: bool) -> str:
    td = Path(tempfile.mkdtemp(prefix="shorts-empty-", dir=TMP))
    (td / "shelf").mkdir()
    env = dict(os.environ, TEST_TMP=str(td), LOOP_NO_DOTENV="1", GITHUB_EVENT_NAME="workflow_dispatch",
               R2_LOCAL_DIR=str(td / "shelf"), CLOUDFLARE_ACCOUNT_ID="acct", CLOUDFLARE_API_TOKEN="tok")
    f = td / "h.py"
    f.write_text(HARNESS % {"loop": str(LOOP), "state": json.dumps(NOV8), "dry": dry})
    r = subprocess.run([PY, str(f)], capture_output=True, text=True, cwd=ROOT, env=env)
    return r.stdout + r.stderr


out = lane_run(False)
check('"shorts-cloud": 0' in out and "RESERVE 0" in out,
      f"(c) the Shorts lane ran on an empty shelf and did not release the reserve: {out[-600:]}")
out = lane_run(True)
check("shorts-cloud" not in out.split("BYLANE", 1)[-1].split("\n", 1)[0] and f"RESERVE {quota.SHORTS_PER_DAY_PEAK * quota.PER_VIDEO}" in out,
      f"(d) a dry run released the Shorts reserve: {out[-600:]}")

if fails:
    print("FAIL test_shorts_reserve_stands_down")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"ok test_shorts_reserve_stands_down: {examined} checks; an empty Shorts run frees 3,400 units, "
      "the 4 waiting titles fit")
