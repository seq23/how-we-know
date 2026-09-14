"""The Sunday digest says what went into the queue and whether the pipeline is well.

Her ask, 2026-09-14: "a weekly email letting me know what videos are being
placed in the youtube queue to be published if any and letting me know the
health of this" - Sunday only, an empty slot inside two weeks is red, and the
verdict goes in the subject line. Every rule here is pure over synthetic
inputs, so each verdict is proven rather than described.

Hard-fails if fewer than six verdicts were examined.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
import digest                                                      # noqa: E402

fails: list[str] = []
examined = 0
NOW = dt.datetime(2026, 9, 14, 12, tzinfo=dt.timezone.utc)
WEEK_AGO = NOW - dt.timedelta(days=7)
# The real config: the calendar is split by the real domain allocation, and a
# synthetic one would test a split the loop never uses.
from common import config                                          # noqa: E402
CFG = config()
CFG["cadence"]["videos_per_week"] = 4


def row(slug, airs, uploaded, lane="backfill"):
    return {"slug": slug, "video_id": "x", "scheduled_publish_at": airs,
            "uploaded_at": uploaded, "note": f"{lane}: scheduled, not yet public"}


# ---- queued this week: only uploads inside the window, with their lane ---------
led = {"published": [
    row("a", "2026-10-09T15:00:00Z", "2026-09-13T03:00:00+00:00", "backfill"),
    row("b", "2026-10-12T15:00:00Z", "2026-09-08T03:00:00+00:00", "cloud-upload"),
    row("old", "2026-09-20T15:00:00Z", "2026-09-01T03:00:00+00:00"),
    {**row("retired", "2026-09-21T15:00:00Z", "2026-09-13T03:00:00+00:00"), "retired_at": "2026-09-13T04:00:00+00:00"},
]}
q = digest.queued_this_week(led, WEEK_AGO, NOW)
examined += 1
if [r["slug"] for r in q] != ["b", "a"] or {r["_lane"] for r in q} != {"backfill", "cloud-upload"}:
    fails.append(f"queued_this_week: expected b (cloud-upload) then a (backfill); got {[(r['slug'], r['_lane']) for r in q]}")

# ---- calendar: a full fortnight, then the slot that is not dated ---------------
def full_ledger(days=28, skip=()):
    import backfill
    wds = backfill.domain_weekdays(CFG, 4)
    rows = []
    for i in range(1, days + 1):
        d = NOW.date() + dt.timedelta(days=i)
        for dom, ws in wds.items():
            if d.weekday() in ws and i not in skip:
                rows.append(row(f"ep-{i}", f"{d.isoformat()}T15:00:00Z", "2026-09-01T00:00:00+00:00"))
    return {"published": rows}

cal = digest.calendar(full_ledger(), CFG, NOW)
examined += 1
if not cal or any(not c["slug"] for c in cal):
    fails.append(f"calendar: a fully dated month should show no empty slot; got {[c for c in cal if not c['slug']]}")
if len(cal) != 16:
    fails.append(f"calendar: 4 weeks at 4/week should be 16 slots, got {len(cal)}")

# an empty slot on the first publish day inside 14 days -> red
first_slot_day = cal[0]["days_away"]
cal_red = digest.calendar(full_ledger(skip=(first_slot_day,)), CFG, NOW)
pipe_ok = {"queued": 0, "scripted": 0, "narrated": 0, "finished_waiting": 0, "held": [],
           "scheduled": 15, "waiting_days": None, "mac_last_seen": NOW, "mac_silent_days": 0}
mark, head, _ = digest.verdict([], cal_red, pipe_ok, 0)
examined += 1
if mark != "🔴" or "empty slot" not in head:
    fails.append(f"verdict: an empty slot inside 14 days must be red; got {mark} {head}")

# an empty slot only in week 4 -> yellow
late_day = cal[-1]["days_away"]
cal_yel = digest.calendar(full_ledger(skip=(late_day,)), CFG, NOW)
mark, head, _ = digest.verdict([], cal_yel, pipe_ok, 0)
examined += 1
if mark != "🟡":
    fails.append(f"verdict: an empty slot in week four must be yellow; got {mark} {head}")

# everything full, nothing waiting -> green, with the counts in the headline
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, 0)
examined += 1
if mark != "🟢" or "2 queued this week" not in head or "28 scheduled" not in head:
    fails.append(f"verdict: full calendar and nothing waiting must be green with counts; got {mark} {head}")

# finished work waiting 8 days on the Mac -> red, even with a full calendar
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 8}, 0)
examined += 1
if mark != "🔴" or "waiting 8 days" not in head:
    fails.append(f"verdict: nine finished episodes waiting eight days must be red; got {mark} {head}")

# nothing queued this week while something is finished -> yellow (the 6-13 Sep shape, day 2)
mark, head, _ = digest.verdict([], cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 2}, 0)
examined += 1
if mark != "🟡" or "nothing queued this week while 9" not in head:
    fails.append(f"verdict: finished work and nothing queued must be yellow; got {mark} {head}")

# a stop that needed a human -> red
mark, head, _ = digest.verdict(q, cal, pipe_ok, 1)
examined += 1
if mark != "🔴":
    fails.append(f"verdict: a needs_human stop must be red; got {mark}")

# ---- the subject line reaches the issue title ----------------------------------
wf = open(os.path.join(ROOT, ".github", "workflows", "loop-sun-digest.yml")).read()
examined += 1
if ".subject" not in wf or '--title "$TITLE"' not in wf:
    fails.append("workflow: loop-sun-digest.yml does not put the digest's .subject line in the issue title")
src = open(os.path.join(LOOP, "digest.py")).read()
if '.subject").write_text' not in src:
    fails.append("digest.py does not write the .subject file the workflow reads")

if examined < 6:
    fails.append("Rule 0: fewer than six verdicts examined")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} checks - queued-this-week, 16-slot calendar, red inside 14 days, yellow beyond, green with counts, red on waiting work and on a human stop, verdict in the subject")
