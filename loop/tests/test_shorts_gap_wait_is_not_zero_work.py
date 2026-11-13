"""A shelf whose every Short waits out the 14-day episode gap is a dated wait,
not Rule 0 (13 Nov 2026, run 43334821894).

The shelf held two verified cuts (hydrothermal-vents cut 3, deep-sea-creatures
cut 3); each episode already had a Short on the calendar inside
EPISODE_GAP_DAYS, so plan() correctly scheduled nothing. The lane then ended
with no work and no stop, Rule 0 turned that into ZERO_WORK, exit 3, an issue.

  a. every waiting cut inside its gap -> SHORTS_WAITING_EPISODE_GAP, exit 0,
     the cuts named in held_items with the day each clears;
  b. the same cut once its gap has passed is planned, so the lane goes on
     past the gap stop (here to the credential stop: no YouTube token);
  c. an empty shelf is still an empty-shelf stop (NO_SHORTS_SHELVED or
     SHORTS_SHELF_DRY), never the gap stop.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable

fails: list[str] = []
examined = 0


def check(ok, msg):
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


HARNESS = '''
import json, os, sys
from pathlib import Path
from types import SimpleNamespace
LOOP = Path(%(loop)r); sys.path.insert(0, str(LOOP))
TMP = Path(os.environ["TEST_TMP"])
import quota, shorts_lane as SL, common, arming, breaker
(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
SL.LEDGER = TMP / "state" / "shorts_ledger.json"
SL.LEDGER.write_text(%(ledger)r)
quota.STATE = TMP / "state" / "quota.json"
common.STOPS = TMP / "state" / "stops"
arming.EVIDENCE = TMP / "state" / "lane_evidence.json"
breaker.guard = lambda lane: None
import shorts_cloud
picks = [SL.Pick(s, r) for s, r in %(todo)s]
shorts_cloud.shelf_lookup = lambda shelf: SimpleNamespace(no_footage=[], unverified=[])
SL.pending = lambda have=None, cfg=None: list(picks)
code = 0
try:
    shorts_cloud.run(limit=2, dry_run=False)
except SystemExit as e:
    code = e.code or 0
recs = [json.loads(p.read_text()) for p in sorted((TMP / "state" / "stops").glob("*-shorts-cloud.json"))]
print("RESULT", json.dumps({"exit": code, "stops": recs}))
'''


def lane_run(ledger: dict, todo: list) -> dict:
    td = Path(tempfile.mkdtemp(prefix="shorts-gap-"))
    (td / "shelf").mkdir()
    env = dict(os.environ, TEST_TMP=str(td), LOOP_NO_DOTENV="1", LOOP_DRY_RUN="1",
               GITHUB_EVENT_NAME="workflow_dispatch", R2_LOCAL_DIR=str(td / "shelf"),
               CLOUDFLARE_ACCOUNT_ID="acct", CLOUDFLARE_API_TOKEN="tok",
               YT_CLIENT_JSON="", YT_REFRESH_TOKEN="")
    f = td / "h.py"
    f.write_text(HARNESS % {"loop": str(LOOP), "ledger": json.dumps(ledger), "todo": repr(todo)})
    r = subprocess.run([PY, str(f)], capture_output=True, text=True, cwd=ROOT, env=env)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT ")]
    if not line:
        return {"exit": "crash", "stops": [], "out": (r.stdout + r.stderr)[-800:]}
    return json.loads(line[-1][len("RESULT "):])


def stamp(days_from_now: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days_from_now)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger(*rows) -> dict:
    return {"published": [{"slug": s, "rank": r, "scheduled_publish_at": t} for s, r, t in rows],
            "updated": None}


# a. both waiting cuts inside their gap
res = lane_run(ledger(("vents", 2, stamp(-1)), ("creepers", 2, stamp(-11))),
               [("vents", 3), ("creepers", 3)])
stop = (res["stops"] or [{}])[-1]
check(res["exit"] == 0, f"(a) a shelf waiting out the episode gap exited {res['exit']}: {res}")
check(stop.get("code") == "SHORTS_WAITING_EPISODE_GAP", f"(a) stop was {stop.get('code')}, not the gap stop")
check(stop.get("disposition") == "self_resolving", f"(a) disposition {stop.get('disposition')}: {stop.get('disposition_why')}")
check(stop.get("held_items") == ["creepers (cut 3)", "vents (cut 3)"], f"(a) held_items {stop.get('held_items')}")
clears = (stop.get("detail") or {}).get("clears_on", {})
check(len(clears) == 2 and all(v > datetime.now(timezone.utc).date().isoformat() for v in clears.values()),
      f"(a) clear dates not both in the future: {clears}")

# b. the gap has passed: the cut is planned, so the lane goes on past the gap stop
res = lane_run(ledger(("vents", 2, stamp(-20))), [("vents", 3)])
codes = [s.get("code") for s in res["stops"]]
check(res["exit"] != "crash" and "SHORTS_WAITING_EPISODE_GAP" not in codes and "ZERO_WORK" not in codes,
      f"(b) a cut clear of its gap did not get past the gap stop: {res}")

# c. empty shelf
res = lane_run(ledger(("vents", 2, stamp(-1))), [])
codes = [s.get("code") for s in res["stops"]]
check(codes and codes[-1] in ("NO_SHORTS_SHELVED", "SHORTS_SHELF_DRY"), f"(c) an empty shelf ended in {codes}")

if examined == 0:
    print("FAIL test_shorts_gap_wait_is_not_zero_work: examined 0")
    sys.exit(1)
if fails:
    print("FAIL test_shorts_gap_wait_is_not_zero_work")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"ok test_shorts_gap_wait_is_not_zero_work: {examined} checks; a shelf inside the episode gap "
      "is a dated self-resolving stop, not ZERO_WORK")
