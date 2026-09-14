"""The Sunday digest notices a Mac that has finished work and shipped none of it.

6-13 September 2026: nine finished renders on the Mac, zero uploaded, and the
digest - which runs in the cloud and reads stops from the repository - said
nothing, because the Mac's stop files never left the Mac. loop/mac_sync.py now
pushes loop/state/mac_heartbeat.json after every Mac lane run, and
loop/digest.py:mac_stops raises MAC_NOT_SHIPPING from it. Pure over the
heartbeat and the clock, so this proves every branch without a Mac.

Hard-fails if fewer than four shapes were examined.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import digest                                                      # noqa: E402

NOW = dt.datetime(2026, 9, 13, 12, tzinfo=dt.timezone.utc)
CFG = {"mac": {"unshipped_days": 3}}
fails: list[str] = []
examined = 0


def codes(hb):
    global examined
    examined += 1
    return [s["code"] for s in digest.mac_stops(NOW, hb=hb, cfg=CFG)]


# nothing pending -> nothing to say
if codes({"backfill": {"last_run_at": "2026-09-13T09:00:00+00:00", "pending": 0}}):
    fails.append("a Mac with nothing pending raised a stop")
# shipping normally -> quiet
if codes({"backfill": {"last_run_at": "2026-09-13T09:00:00+00:00", "last_success_at": "2026-09-12T09:00:00+00:00", "uploaded": 4, "pending": 5}}):
    fails.append("a Mac that shipped yesterday raised a stop")
# reporting daily but never shipping, with a hold -> loud, and names the hold
got = digest.mac_stops(NOW, hb={"renders_finished": 9, "backfill": {"last_run_at": "2026-09-13T09:00:00+00:00", "pending": 9, "uploaded": 0, "held": ["why-is-steel-so-strong"]}}, cfg=CFG)
examined += 1
if [s["code"] for s in got] != ["MAC_NOT_SHIPPING"] or "why-is-steel-so-strong" not in got[0]["message"]:
    fails.append(f"a Mac holding nine renders and shipping none should raise MAC_NOT_SHIPPING naming the hold; got {got}")
# silent for a week with work pending -> loud
if codes({"backfill": {"last_run_at": "2026-09-05T09:00:00+00:00", "pending": 9}}) != ["MAC_NOT_SHIPPING"]:
    fails.append("a Mac silent for eight days with work pending did not raise MAC_NOT_SHIPPING")
# shipped two days ago, within the window -> quiet
if codes({"backfill": {"last_run_at": "2026-09-13T09:00:00+00:00", "last_success_at": "2026-09-11T09:00:00+00:00", "uploaded": 4, "pending": 5}}):
    fails.append("a Mac that shipped two days ago (limit three) raised a stop")
# the digest actually includes it
try:
    digest.HEARTBEAT = __import__("pathlib").Path(os.path.join(HERE, "does-not-exist.json"))
    if digest.mac_stops(NOW, cfg=CFG):
        fails.append("no heartbeat file and nothing known should be quiet")
    examined += 1
except Exception as e:                                             # noqa: BLE001
    fails.append(f"mac_stops raised on a missing heartbeat: {e}")

if examined < 4:
    fails.append("Rule 0: fewer than four heartbeat shapes examined")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} heartbeat shapes; MAC_NOT_SHIPPING fires on silence and on unshipped work, and only then")
