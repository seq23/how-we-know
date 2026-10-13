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
# Every rotation day of an ungated domain is a slot: deep sea, materials and
# (since its sample gate cleared on 13 Oct 2026) food - six days, 24 slots in
# four weeks. A sample-gated domain's days would not count (domains.sample_gate).
import domains as _D                                               # noqa: E402
_gated = set(_D.sample_gated(CFG))
_rot = {d for d in (CFG["cadence"]["rotation"]["weekdays"] or {}).values() if d}
_live_days = sum(1 for d in CFG["cadence"]["rotation"]["weekdays"].values()
                 if d and d not in _gated)
if len(cal) != 4 * _live_days or _live_days != 6:
    fails.append(f"calendar: 4 weeks of the {_live_days} ungated rotation days should be "
                 f"{4 * _live_days} slots (six since food cleared), got {len(cal)}")
examined += 1
if any(c["domain"] in _gated for c in cal):
    fails.append(f"calendar: a sample-gated domain's days were counted as slots: {sorted({c['domain'] for c in cal} & _gated)}")

# an empty slot on the first publish day inside 14 days -> red
first_slot_day = cal[0]["days_away"]
cal_red = digest.calendar(full_ledger(skip=(first_slot_day,)), CFG, NOW)
pipe_ok = {"queued": 0, "scripted": 0, "narrated": 0, "finished_waiting": 0, "held": [],
           "scheduled": 15, "waiting_days": None, "mac_last_seen": NOW, "mac_silent_days": 0}
mark, head, _ = digest.verdict([], cal_red, pipe_ok, [])
examined += 1
if mark != "🔴" or "empty day(s) in the next two weeks" not in head or not head.endswith("— not fixed yet"):
    fails.append(f"verdict: an empty slot inside 14 days must be red; got {mark} {head}")

# an empty slot only in week 4 -> yellow
late_day = cal[-1]["days_away"]
cal_yel = digest.calendar(full_ledger(skip=(late_day,)), CFG, NOW)
mark, head, _ = digest.verdict([], cal_yel, pipe_ok, [])
examined += 1
if mark != "🟡" or "Episode calendar has gaps" not in head or not head.endswith("— watching") or "needs you" in head:
    fails.append(f"verdict: an empty slot in week four must be yellow, plain, and 'watching'; got {mark} {head}")

# everything full, nothing waiting -> green, with the counts in the headline
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [])
examined += 1
if mark != "🟢" or not head.startswith("All lanes ran: 2 episodes queued") or "28 scheduled" not in head:
    fails.append(f"verdict: full calendar and nothing waiting must be green with counts; got {mark} {head}")

# finished work waiting 8 days on the Mac -> red, even with a full calendar
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 8}, [])
examined += 1
if mark != "🔴" or "Uploads stuck: 9 finished episode(s) waiting 8 days on the Mac" not in head:
    fails.append(f"verdict: nine finished episodes waiting eight days must be red; got {mark} {head}")

# nothing queued this week while something is finished -> yellow (the 6-13 Sep shape, day 2)
mark, head, _ = digest.verdict([], cal, {**pipe_ok, "finished_waiting": 9, "waiting_days": 2}, [])
examined += 1
if mark != "🟡" or "No episode uploaded this week while 9 finished episode(s) wait" not in head:
    fails.append(f"verdict: finished work and nothing queued must be yellow; got {mark} {head}")

# a stop that needed a human -> red, AND the subject says in plain words what
# happened and what to do (2026-10-12: a lane name in brackets was not read as
# a problem). The stop arrives as its record, the way render() passes it.
UPLOAD_STOP = {"stage": "cloud-upload", "code": "UPLOAD_FAILED",
               "disposition": "needs_human", "consecutive": 1}
UPLOAD_PLAIN = digest.plain("UPLOAD_FAILED")
mark, head, _ = digest.verdict(q, cal, pipe_ok, [UPLOAD_STOP])
examined += 1
if (mark != "🔴" or not head.lower().startswith(UPLOAD_PLAIN.lower())
        or not head.endswith("— needs you: read the stop issue on GitHub")):
    fails.append(f"verdict: a needs_human stop must be red, say what happened in "
                 f"its plain words and end with what to do; got {mark} {head}")

# THE 2026-09-22 BUG, negative proof: a week with BOTH a red empty-slot reason
# AND a needs_human stop must lead with the needs_human stop - the one with an
# actual open GitHub issue behind it - not with the empty slot.
mark, head, reasons = digest.verdict([], cal_red, pipe_ok, [UPLOAD_STOP])
examined += 1
if mark != "🔴" or not head.lower().startswith(UPLOAD_PLAIN.lower()) or "needs you" not in head:
    fails.append(f"verdict: a needs_human stop must win the headline over a routine "
                 f"empty-slot reason from the same week; got {mark} {head}")
if head.startswith("Episode calendar"):
    fails.append(f"verdict: the empty-slot reason must not lead the headline when a "
                 f"needs_human stop exists this week; got {head}")
if not any(r.startswith("Episode calendar has gaps") for r in reasons[1:]):
    fails.append(f"verdict: the empty slot must still be listed under the headline; got {reasons}")

# THE 2026-09-23 GAP: an owner_action ("needs your key or account") item was
# never passed into verdict(). Now it is yellow, in plain words, with its action.
WAITING_ONE = {"cloud-upload": {"code": "OAUTH_EXPIRED",
                                "message": "refresh token rejected",
                                "unblock": "re-consent",
                                "consecutive": 2}}
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [], WAITING_ONE)
examined += 1
if (mark != "🟡" or not head.lower().startswith(digest.plain("OAUTH_EXPIRED").lower())
        or not head.endswith("— needs you: sign in to YouTube again")):
    fails.append(f"verdict: an owner_action item with nothing else red/yellow must "
                 f"be yellow, plain, and name her action; got {mark} {head}")

# owner_action must not outrank a real needs_human stop.
mark, head, _ = digest.verdict(q, cal, pipe_ok, [UPLOAD_STOP], WAITING_ONE)
examined += 1
if mark != "🔴" or not head.lower().startswith(UPLOAD_PLAIN.lower()):
    fails.append(f"verdict: a needs_human stop must still win over an owner_action "
                 f"item in the same week; got {mark} {head}")

# owner_action must outrank a routine calendar note.
mark, head, _ = digest.verdict([], cal_yel, pipe_ok, [], WAITING_ONE)
examined += 1
if not head.lower().startswith(digest.plain("OAUTH_EXPIRED").lower()) or "needs you" not in head:
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
full_verdict = "🔴 Shorts stopped: 1 of 9 published this week, 1 of 9 the week before — needs you: check the Mac's nightly batch"
subject = digest.digest_subject(full_verdict, "2026-W39")
if "needs you: check the Mac's nightly batch" not in subject or "1 of 9" not in subject:
    fails.append(f"digest_subject() drops the reason text - the exact 2026-09-23 "
                 f"bug (subject named no problem at all): {subject!r}")
if not subject.startswith("🔴 Shorts stopped"):
    fails.append(f"digest_subject() does not lead with the mark and the problem: {subject!r}")
if not subject.endswith("2026-W39"):
    fails.append(f"digest_subject() drops the week: {subject!r}")

# a runaway reason must still cap, never produce an unbounded subject
examined += 1
huge = "🔴 Stalled: 1 queued this week, 1 scheduled — " + ("x" * 500)
capped = digest.digest_subject(huge, "2026-W39")
if len(capped) > 220:
    fails.append(f"digest_subject() does not cap a runaway reason: {len(capped)} chars")

# ---- SHORTS CADENCE (owner, 2026-10-12: "why did the Shorts lane emails
# never tell me"). Shorts fell from 14 a week to 1 while this verdict counted
# long-form slots only and NO_SHORTS_SHELVED sat under self-resolving stops.
# Under target one week -> yellow; two consecutive weeks -> red; it outranks
# the calendar notes and names the numbers in the subject.
import verdict as CV                                               # noqa: E402

SNOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone.utc)


def shorts_rows(per_day_last: int, per_day_prev: int, ahead: int = 0) -> list[dict]:
    out = []
    for d in range(7):
        for _ in range(per_day_last):
            out.append({"scheduled_publish_at": (SNOW - dt.timedelta(days=d, hours=1)).isoformat()})
        for _ in range(per_day_prev):
            out.append({"scheduled_publish_at": (SNOW - dt.timedelta(days=7 + d, hours=1)).isoformat()})
    for i in range(ahead):
        out.append({"scheduled_publish_at": (SNOW + dt.timedelta(days=1 + i)).isoformat()})
    return out


examined += 1
sc = CV.shorts_cadence(shorts_rows(2, 2, ahead=3), 9, SNOW, 6, "fixture")
if (sc["published_7d"], sc["published_prev_7d"], sc["shelf"], sc["shelf_weeks"]) != (14, 14, 9, 1.0):
    fails.append(f"shorts_cadence() miscounts the trailing weeks or the shelf: {sc}")
examined += 1
if digest.shorts_flag(sc) != (None, None):
    fails.append(f"Shorts on target raised a flag: {digest.shorts_flag(sc)}")
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [], None, sc)
if mark != "🟢":
    fails.append(f"Shorts on target turned a green week {mark}: {head}")

examined += 1
one = CV.shorts_cadence(shorts_rows(0, 2)
                        + [{"scheduled_publish_at": (SNOW - dt.timedelta(days=2)).isoformat()}],
                        9, SNOW, 0, "fixture")
flag, why = digest.shorts_flag(one)
if flag != "yellow" or "1 vs 9" not in why:
    fails.append(f"one week under the Shorts target is not yellow: {flag} {why}")
mark, head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [], None, one)
if mark != "🟡" or not head.startswith("Shorts under target: 1 of 9") or not head.endswith("— watching"):
    fails.append(f"a green week with Shorts under target did not go yellow: {mark} {head}")

examined += 1
two = CV.shorts_cadence([{"scheduled_publish_at": (SNOW - dt.timedelta(days=2)).isoformat()},
                         {"scheduled_publish_at": (SNOW - dt.timedelta(days=9)).isoformat()}],
                        9, SNOW, 0, "fixture")
flag, why = digest.shorts_flag(two)
if flag != "red" or f"{digest.SHORTS_RED_WEEKS} weeks running" not in why:
    fails.append(f"two consecutive weeks under the Shorts target is not red: {flag} {why}")
mark, head, _ = digest.verdict(q, cal_yel, {**pipe_ok, "scheduled": 28}, [], None, two)
if mark != "🔴" or not head.startswith("Shorts stopped: 1 of 9 published this week, 1 of 9"):
    fails.append(f"two Shorts-short weeks did not lead a red subject over a "
                 f"calendar note: {mark} {head}")
examined += 1
if digest.shorts_flag(None) != (None, None) or digest.shorts_flag({}) != (None, None):
    fails.append("an unmeasured Shorts cadence raised a flag")
examined += 1
src = open(os.path.join(os.path.dirname(digest.__file__), "digest.py")).read()
if "verdict(queued_rows, cal, pipe, loud_stops,\n                                      waiting, sc, quiet_stops, per_week, br)" not in src:
    fails.append("render() does not pass the stops, Shorts cadence, episode target and breaker into verdict()")

# ---- PLAIN WORDS (owner, 2026-10-12): "make sure it tells me plainly what is
# honestly going on if something needs work it should say it in the subject".
# W40/W41 read "🔴 Stalled: 1 queued this week, 16 scheduled — 1 stop(s) needed
# a human this week (mac)" while Shorts fell from 14 a week to 1.
import re                                                          # noqa: E402
CODE_TOKEN = re.compile(r"[A-Z]{3,}_[A-Z_]+")
MAC_STOP = {"stage": "mac", "code": "MAC_NOT_SHIPPING", "disposition": "needs_human",
            "consecutive": 1}
QUIET_SUPPLY = {"stage": "shorts-cloud", "code": "NO_SHORTS_SHELVED",
                "disposition": "self_resolving", "consecutive": 6}
QUIET_OTHER = {"stage": "localize", "code": "LOCALIZATIONS_UP_TO_DATE",
               "disposition": "self_resolving", "consecutive": 1}
seen_lines: list[str] = []

# (a) Shorts shortfall + a needs_human Mac stop -> 🔴, Shorts first with X of Y.
#     The Shorts line has no action of its own, so the subject must NOT borrow
#     the Mac stop's ("needs you: check the Mac's nightly batch" under a Shorts
#     lead is the W42 defect's shape): it says "not fixed yet" and counts the
#     Mac stop as "+1 more needs you"; the body carries the Mac line WITH its
#     own action.
examined += 1
a_mark, a_head, a_reasons = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [MAC_STOP],
                                           None, two, [QUIET_SUPPLY, QUIET_OTHER], 2)
seen_lines += [a_head] + a_reasons
if (a_mark != "🔴" or not a_head.startswith("Shorts") or "1 of 9" not in a_head
        or not a_head.endswith("— not fixed yet — +1 more needs you")
        or "check the Mac" in a_head):
    fails.append(f"(a) Shorts shortfall with a Mac stop: {a_mark} {a_head}")
if not any(r.startswith(digest.plain("MAC_NOT_SHIPPING")[:1].upper()) and "Mac" in r
           and r.endswith("— check the Mac's nightly batch") for r in a_reasons[1:]):
    fails.append(f"(a) the Mac stop is not listed, with its own action, under the subject line: {a_reasons}")
subj = digest.digest_subject(f"{a_mark} {a_head}", "2026-W41")
seen_lines.append(subj)
if not subj.startswith("🔴 Shorts") or not subj.endswith(" — 2026-W41"):
    fails.append(f"(a) the subject file line is not the plain sentence plus the week: {subj!r}")

# (b) under target one week, no stop -> 🟡, no "needs you".
examined += 1
b_mark, b_head, b_reasons = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [],
                                           None, one, [], 2)
seen_lines += [b_head] + b_reasons
if b_mark != "🟡" or "needs you" in b_head or "1 of 9" not in b_head or not b_head.endswith("— watching"):
    fails.append(f"(b) one Shorts-short week: {b_mark} {b_head}")

# (c) all green -> 🟢 with the counts.
examined += 1
c_mark, c_head, c_reasons = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [],
                                           None, sc, [QUIET_OTHER], 2)
seen_lines += [c_head] + c_reasons
if c_mark != "🟢" or c_head != "All lanes ran: 2 of 2 episodes queued, 28 scheduled, Shorts 14 of 9" or c_reasons:
    fails.append(f"(c) a green week: {c_mark} {c_head} {c_reasons}")

# episodes under target -> yellow, plain, and its supply stop listed, not hidden
examined += 1
EP_QUIET = {"stage": "cloud-upload", "code": "NOTHING_SHELVED",
            "disposition": "self_resolving", "consecutive": 7}
e_mark, e_head, e_reasons = digest.verdict([], cal, {**pipe_ok, "scheduled": 16}, [],
                                           None, sc, [EP_QUIET], 4)
seen_lines += [e_head] + e_reasons
if (e_mark != "🟡" or not e_head.startswith("Episodes under target: 0 of 4")
        or f"Still happening: {digest.plain('NOTHING_SHELVED')} (7 runs in a row)" not in e_reasons):
    fails.append(f"episodes under target must be a yellow problem with its supply stop "
                 f"listed, not filed as cleared: {e_mark} {e_head} {e_reasons}")

# breaker tripped -> red, first, plain
examined += 1
k_mark, k_head, k_reasons = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [MAC_STOP],
                                           None, two, [], 2,
                                           {"state": "tripped", "cause": "validator",
                                            "tripped_at": "2026-10-12T15:53:50+00:00"})
seen_lines += [k_head] + k_reasons
if k_mark != "🔴" or not k_head.startswith("Publishing is halted") or "Mon 12 Oct" not in k_head:
    fails.append(f"a tripped breaker must lead a red subject in plain words: {k_mark} {k_head}")
# THE W42 SUBJECT (2026-10-12), negative proof: the breaker led, a Mac stop was
# also present, and the subject read "Publishing is halted … — needs you: check
# the Mac's nightly batch" - an action that does not clear the switch. The
# subject's action must be the breaker's own, in stop_policy.json's words, and
# the Mac stop is counted, not named; the body lists each with its own action.
examined += 1
import json as _json                                               # noqa: E402
_pol = _json.load(open(os.path.join(LOOP, "stop_policy.json")))
BREAKER_ACTION = (_pol["needs_human"]["BREAKER_TRIPPED"] or {}).get("action")
if not BREAKER_ACTION:
    fails.append("stop_policy.json: BREAKER_TRIPPED has no `action` for the subject to use")
elif (not k_head.endswith(f"— needs you: {BREAKER_ACTION} — +1 more needs you")
        or "check the Mac" in k_head):
    fails.append(f"(W42) the breaker leads but the subject's action is not the "
                 f"breaker's own plus '+1 more needs you': {k_head}")
if not (any(r.startswith("Publishing is halted") and r.endswith(f"— {BREAKER_ACTION}")
            for r in k_reasons)
        and any("Mac" in r and r.endswith("— check the Mac's nightly batch") for r in k_reasons[1:])):
    fails.append(f"(W42) the body must list the breaker and the Mac stop each with its "
                 f"own action: {k_reasons}")
# breaker alone: its action, no "+N more".
examined += 1
k1_mark, k1_head, k1_reasons = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [],
                                              None, sc, [], 2,
                                              {"state": "tripped", "cause": "validator",
                                               "tripped_at": "2026-10-12T15:53:50+00:00"})
seen_lines += [k1_head] + k1_reasons
if k1_mark != "🔴" or not k1_head.endswith(f"— needs you: {BREAKER_ACTION}") or "more needs you" in k1_head:
    fails.append(f"(W42) a breaker alone must end with its own action and no count: {k1_head}")
# a retention trip is cleared by the weekly measurement: no action of hers.
examined += 1
_, k2_head, _ = digest.verdict(q, cal, {**pipe_ok, "scheduled": 28}, [MAC_STOP],
                               None, sc, [], 2,
                               {"state": "tripped", "cause": "retention",
                                "tripped_at": "2026-10-12T15:53:50+00:00"})
seen_lines.append(k2_head)
if not k2_head.endswith("— not fixed yet — +1 more needs you") or "check the Mac" in k2_head:
    fails.append(f"(W42) a retention trip must not borrow another stop's action: {k2_head}")

# (e) a self-resolving stop never reaches the subject when a shortfall exists.
examined += 1
for code in (QUIET_SUPPLY["code"], QUIET_OTHER["code"]):
    if digest.plain(code).lower() in a_head.lower():
        fails.append(f"(e) self-resolving {code} reached the subject: {a_head}")
if not any(r.startswith("Still happening: " + digest.plain("NO_SHORTS_SHELVED")) for r in a_reasons):
    fails.append(f"(e) the Shorts supply stop was dropped instead of listed under the shortfall: {a_reasons}")
if any(digest.plain("LOCALIZATIONS_UP_TO_DATE") in r for r in a_reasons):
    fails.append(f"(e) an unrelated self-resolving stop was listed as a problem: {a_reasons}")
rsrc = open(os.path.join(LOOP, "digest.py")).read()
if 'page nobody: "' in rsrc or "Cleared on their own this week: " not in rsrc:
    fails.append("(e) the 'page nobody' footnote is back, or 'Cleared on their own' is gone")

# (d) no stop code ever appears in a subject or a first-line problem.
examined += 1
if len(seen_lines) < 10:
    fails.append(f"(d) examined only {len(seen_lines)} subject/problem lines")
leaks = [ln for ln in seen_lines if CODE_TOKEN.search(ln)]
if leaks:
    fails.append(f"(d) a stop code reached the subject or its problem lines: {leaks[:3]}")
if 'f"## {mark} {headline}", ""]' not in rsrc or 'for r in reasons[1:]:' not in rsrc:
    fails.append("(d) the body's first line is no longer the subject sentence")

# The subject's emoji is the verdict's, not the last runway row's. Until
# 2026-10-12 render() rebound `mark` in the Runway table, so W39-W42 subjects
# read "🟢 Stalled…" / "🟢 Publishing is halted…" under a 🔴 body.
examined += 1
_body, _counts = digest.render("2026-W99", dt.datetime.now(dt.timezone.utc))
_first = next((ln for ln in _body.splitlines() if ln.startswith("## ")), "")
if _first[3:] != _counts["verdict"]:
    fails.append(f"render(): the subject's verdict {_counts['verdict'][:60]!r} is not "
                 f"the body's first line {_first[:60]!r}")
if CODE_TOKEN.search(_first):
    fails.append(f"(d) a stop code reached the body's first line: {_first}")

if examined < 6:
    fails.append("Rule 0: fewer than six verdicts examined")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} checks - queued-this-week, 16-slot calendar, red inside 14 days, yellow beyond, green with counts, red on waiting work and on a human stop, verdict in the subject")
