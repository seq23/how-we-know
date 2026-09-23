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
mark, head, _ = digest.verdict([], cal_red, pipe_ok, [])
examined += 1
if mark != "🔴" or "empty slot" not in head:
    fails.append(f"verdict: an empty slot inside 14 days must be red; got {mark} {head}")

# an empty slot only in week 4 -> yellow
late_day = cal[-1]["days_away"]
cal_yel = digest.calendar(full_ledger(skip=(late_day,)), CFG, NOW)
mark, head, _ = digest.verdict([], cal_yel, pipe_ok, [])
examined += 1
if mark != "🟡":
    fails.append(f"verdict: an empty slot in week four must be yellow; got {mark} {head}")

# everything full, nothing waiting -> green, with the counts in the headline
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [])
examined += 1
if mark != "🟢" or "2 queued this week" not in head or "28 scheduled" not in head:
    fails.append(f"verdict: full calendar and nothing waiting must be green with counts; got {mark} {head}")

# finished work waiting 8 days on the Mac -> red, even with a full calendar
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 8}, [])
examined += 1
if mark != "🔴" or "waiting 8 days" not in head:
    fails.append(f"verdict: nine finished episodes waiting eight days must be red; got {mark} {head}")

# nothing queued this week while something is finished -> yellow (the 6-13 Sep shape, day 2)
mark, head, _ = digest.verdict([], cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 2}, [])
examined += 1
if mark != "🟡" or "nothing queued this week while 9" not in head:
    fails.append(f"verdict: finished work and nothing queued must be yellow; got {mark} {head}")

# a stop that needed a human -> red, AND the subject names the lane that
# actually needs her, not just an emoji
mark, head, _ = digest.verdict(q, cal, pipe_ok, ["cloud-upload"])
examined += 1
if mark != "🔴" or "cloud-upload" not in head or "needed a human" not in head:
    fails.append(f"verdict: a needs_human stop must be red and name its stage in the "
                 f"headline; got {mark} {head}")

# THE 2026-09-22 BUG, negative proof: a week with BOTH a routine empty-slot
# reason (red on its own, proven above via cal_red) AND a needs_human stop
# must lead with the needs_human stop — the one with an actual open GitHub
# issue behind it — not with the empty slot. Before the fix, this function
# checked the empty slot first and the subject would have named that instead,
# exactly the "Shorts lane" subject on a long-form NEEDS YOU incident this
# guards against.
mark, head, _ = digest.verdict([], cal_red, pipe_ok, ["cloud-upload"])
examined += 1
if mark != "🔴" or "cloud-upload" not in head or "needed a human" not in head:
    fails.append(f"verdict: a needs_human stop must win the headline over a routine "
                 f"empty-slot reason from the same week; got {mark} {head}")
if head.split(" — ", 1)[-1].startswith(("1 empty slot", "empty slot")):
    fails.append(f"verdict: the empty-slot reason must not lead the headline when a "
                 f"needs_human stop exists this week; got {head}")

# THE 2026-09-23 GAP: an owner_action ("waiting on you") item was never
# passed into verdict() at all. A week with nothing else red or yellow and
# one owner_action item rendered "🟢 Healthy" as both headline and subject,
# while the digest body's very first section ("## ⚠️ Waiting on you") said
# something needed her — the subject named no lane, or an unrelated one.
WAITING_ONE = {"cloud-upload": {"code": "SCRIPTS_AWAITING_PROMOTION",
                                "message": "four scripts await promotion",
                                "unblock": "promote or decline",
                                "consecutive": 2}}
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [], WAITING_ONE)
examined += 1
if mark != "🟡" or "waiting on you" not in head or "cloud-upload" not in head:
    fails.append(f"verdict: an owner_action item with nothing else red/yellow must "
                 f"be yellow and name the lane waiting on her; got {mark} {head}")

# owner_action must not outrank a real needs_human stop — she said the run
# STAYS GREEN for owner_action; it must never look more urgent than a
# genuine failure that already opened its own issue.
mark, head, _ = digest.verdict(q, cal, pipe_ok, ["cloud-upload"], WAITING_ONE)
examined += 1
if mark != "🔴" or "needed a human" not in head:
    fails.append(f"verdict: a needs_human stop must still win over an owner_action "
                 f"item in the same week; got {mark} {head}")

# owner_action must outrank a routine reason from an unrelated lane —
# the actual "Shorts lane subject, cloud-upload content" shape: nothing
# needed a human, but the calendar happens to be thin (a routine, unrelated
# reason) in the same week a real owner_action item is open elsewhere.
mark, head, _ = digest.verdict([], cal_yel, pipe_ok, [], WAITING_ONE)
examined += 1
if "waiting on you" not in head or "cloud-upload" not in head:
    fails.append(f"verdict: an owner_action item must lead the headline over an "
                 f"unrelated routine calendar reason; got {mark} {head}")

# ---- the subject line reaches the issue title ----------------------------------
wf = open(os.path.join(ROOT, ".github", "workflows", "loop-sun-digest.yml")).read()
examined += 1
if ".subject" not in wf or '--title "$TITLE"' not in wf:
    fails.append("workflow: loop-sun-digest.yml does not put the digest's .subject line in the issue title")
src = open(os.path.join(LOOP, "digest.py")).read()
if '.subject").write_text' not in src:
    fails.append("digest.py does not write the .subject file the workflow reads")

# THE 2026-09-23 BUG, negative proof against the subject text itself: not
# just that a `.subject` file gets written (checked above since before this
# fix existed), but that it actually CARRIES the reason, not only the mark
# and the counts. `counts['verdict'].split(' — ')[0]` used to be the whole
# subject and would have passed every check above while silently dropping
# every reason computed above — this is the check that would have caught it.
examined += 1
full_verdict = "🔴 Stalled: 3 queued this week, 5 scheduled — 2 stop(s) needed a human this week (cloud-upload, weekly-score)"
subject = digest.digest_subject(full_verdict, "2026-W39")
if "cloud-upload" not in subject or "weekly-score" not in subject:
    fails.append(f"digest_subject() drops the reason text - the exact 2026-09-23 "
                 f"bug (subject named no lane at all): {subject!r}")
if not subject.startswith("Weekly digest — 🔴 Stalled"):
    fails.append(f"digest_subject() does not lead with the mark and headline: {subject!r}")
if not subject.endswith("2026-W39"):
    fails.append(f"digest_subject() drops the week: {subject!r}")

# a runaway reason must still cap, never produce an unbounded subject
examined += 1
huge = "🔴 Stalled: 1 queued this week, 1 scheduled — " + ("x" * 500)
capped = digest.digest_subject(huge, "2026-W39")
if len(capped) > 220:
    fails.append(f"digest_subject() does not cap a runaway reason: {len(capped)} chars")

if examined < 6:
    fails.append("Rule 0: fewer than six verdicts examined")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} checks - queued-this-week, 16-slot calendar, red inside 14 days, yellow beyond, green with counts, red on waiting work and on a human stop, verdict in the subject")
