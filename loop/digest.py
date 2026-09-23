"""The Sunday digest — one email a week that says what the channel did.

    .venv/bin/python loop/digest.py            # write and print
    .venv/bin/python loop/digest.py --print    # print only, write nothing

WHY THIS EXISTS. Everything the loop decides is already recorded — the ledger,
the breaker, the stop files, the monthly review. None of it reaches the owner.
The only things that email her today are a NAMED STOP and the monthly review,
which means the channel is silent in every week where nothing goes wrong. Her
instruction is that the system decides and she is told at intervals; a system
that only speaks when it is in trouble does not satisfy the second half.

WHAT IT IS NOT. It carries no decisions and asks for none. Every number in it
was already decided and applied by the lane that owns it. If the digest stops
being sent, nothing about the channel changes — which is exactly the property
that lets it be read in thirty seconds and ignored in a busy week.

RULE 0. A digest is a stage like any other. It hard-fails if it renders with no
episodes, no schedule and no queue — that combination means it read nothing,
and a reassuring weekly email built on a file it failed to open is worse than
no email at all.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import breaker                                             # noqa: E402
import cadence                                             # noqa: E402
import domains                                             # noqa: E402
import ledger                                              # noqa: E402
import ypp                                                 # noqa: E402
from common import Stage, config, week_id                  # noqa: E402
from common import owner_actions as common_owner_actions  # noqa: E402

OUT_DIR = ROOT / "loop" / "state" / "digest"
STOPS = ROOT / "loop" / "state" / "stops"


def _when(stamp: str | None) -> dt.datetime | None:
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def aired(led: dict, since: dt.datetime, until: dt.datetime) -> list[dict]:
    """Episodes that went public in the window, newest first.

    Reads `published_at` where the ledger has it and falls back to
    `scheduled_publish_at` in the past, because an episode uploaded private and
    flipped by YouTube on a schedule has only the second one.
    """
    out = []
    for row in led["published"]:
        if row.get("retired_at"):
            continue
        when = _when(row.get("published_at")) or _when(
            row.get("scheduled_publish_at"))
        if when and since <= when <= until:
            out.append({**row, "_when": when})
    return sorted(out, key=lambda r: r["_when"], reverse=True)


def upcoming(led: dict, after: dt.datetime, limit: int = 8) -> list[dict]:
    out = []
    for row in led["published"]:
        if row.get("retired_at"):
            continue
        when = _when(row.get("scheduled_publish_at"))
        if when and when > after:
            out.append({**row, "_when": when})
    return sorted(out, key=lambda r: r["_when"])[:limit]


# ─── WHAT WENT INTO THE QUEUE, AND WHETHER THE PIPELINE IS HEALTHY ───────────
#
# Added 2026-09-14. The digest showed what would AIR and never what had been
# PUT IN THE QUEUE, so a week in which nine finished episodes shipped nothing
# (6-13 September) read as a healthy week: "Next up" was full for a month
# because the deep-sea run was already scheduled. The owner's ask: a Sunday
# email that says what was placed in the YouTube queue this week, if anything,
# and whether the pipeline is well - with the verdict in the subject line so
# the inbox is the dashboard. Every function here is pure over its inputs so
# loop/tests/test_digest_queue_and_health.py can prove each verdict.

EMPTY_SLOT_RED_DAYS = 14      # her decision, 2026-09-14: an empty slot inside two weeks is red
CALENDAR_WEEKS = 4
WAIT_YELLOW_DAYS = 3          # finished work waiting longer than this is yellow...
WAIT_RED_DAYS = 7             # ...and longer than this is red


def queued_this_week(led: dict, since: dt.datetime, until: dt.datetime) -> list[dict]:
    """Every episode UPLOADED AND DATED inside the window: the thing the old
    digest never showed. `uploaded_at` is the moment a lane put it on YouTube;
    the note's prefix ("backfill:", "cloud-upload:") names which lane."""
    out = []
    for row in led["published"]:
        if row.get("retired_at"):
            continue
        up = _when(row.get("uploaded_at"))
        if up and since <= up <= until:
            lane = (row.get("note") or "").split(":", 1)[0].strip() or "?"
            out.append({**row, "_uploaded": up, "_lane": lane,
                        "_airs": _when(row.get("scheduled_publish_at"))})
    return sorted(out, key=lambda r: r["_uploaded"])


def calendar(led: dict, cfg: dict, now: dt.datetime, weeks: int = CALENDAR_WEEKS) -> list[dict]:
    """Every publish slot in the next `weeks` weeks, filled or EMPTY.

    A slot is a (date, domain) the cadence would publish on - the weekday
    ladder split between the live domains, the same split loop/backfill.py
    schedules with - and it is filled when a ledger row is dated that day.
    Empty slots are the number she cares about; they were invisible before.
    """
    import backfill                                        # noqa: PLC0415
    per_week = int(cfg["cadence"]["videos_per_week"])
    days_by_domain = backfill.domain_weekdays(cfg, per_week)
    dated: dict[str, dict] = {}
    for row in led["published"]:
        if row.get("retired_at"):
            continue
        w = _when(row.get("scheduled_publish_at"))
        if w:
            dated[w.date().isoformat()] = row
    out = []
    start = now.date()
    for i in range(1, weeks * 7 + 1):
        d = start + dt.timedelta(days=i)
        for domain, wds in days_by_domain.items():
            if d.weekday() in wds:
                row = dated.get(d.isoformat())
                out.append({"date": d, "domain": domain, "days_away": i,
                            "slug": row["slug"] if row else None})
    return out


def pipeline(led: dict, depth: dict, hb: dict, now: dt.datetime) -> dict:
    """The funnel, one number per stage, from what the cloud can read.

    queued  - topics in the publish orders not yet uploaded
    scripted / narrated - files in the repository for those topics
    finished - the Mac's heartbeat: renders on disk that are not yet uploaded
    scheduled - ledger rows dated in the future
    waiting_days - how long the oldest finished-but-unshipped work has waited,
                   from the Mac's last successful ship (None if nothing waits)
    """
    done = {r["slug"] for r in led["published"] if not r.get("retired_at")}
    try:
        import batch_queue                                 # noqa: PLC0415
        queued = [q["slug"] for q in batch_queue.queued_entries() if q["slug"] not in done]
    except Exception:                                      # noqa: BLE001
        queued = []
    scripted = [s for s in queued if (ROOT / "scripts" / f"{s}.md").exists()]
    narrated = []
    for s_ in scripted:
        b = ROOT / "audio" / s_ / "beats.json"
        try:
            beats = json.loads(b.read_text())
            if beats and all(x.get("seconds") for x in beats):
                narrated.append(s_)
        except (OSError, ValueError):
            pass
    lanes = {k: v for k, v in hb.items() if isinstance(v, dict)}
    pending = max([int(v.get("pending") or 0) for v in lanes.values()] or [0])
    held = sorted({x for v in lanes.values() for x in (v.get("held") or [])})
    last_ship = max([_when(v.get("last_success_at")) for v in lanes.values()
                     if v.get("uploaded") and _when(v.get("last_success_at"))] or [None],
                    key=lambda d: d or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    last_seen = max([_when(v.get("last_run_at")) for v in lanes.values()
                     if _when(v.get("last_run_at"))] or [None],
                    key=lambda d: d or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    waiting_days = None
    if pending:
        waiting_days = (now - last_ship).days if last_ship else (now - last_seen).days if last_seen else None
    scheduled = [r for r in led["published"] if not r.get("retired_at")
                 and (_when(r.get("scheduled_publish_at")) or now) > now]
    return {"queued": len(queued), "scripted": len(scripted), "narrated": len(narrated),
            "finished_waiting": pending, "held": held, "scheduled": len(scheduled),
            "waiting_days": waiting_days, "mac_last_seen": last_seen,
            "mac_silent_days": (now - last_seen).days if last_seen else None}


def verdict(queued_rows: list[dict], cal: list[dict], pipe: dict,
            loud_stops: list[str],
            waiting: dict | None = None) -> tuple[str, str, list[str]]:
    """(emoji, one-line verdict, reasons). The rules, in words:

    🔴  a stop that needed a human; or an empty slot inside EMPTY_SLOT_RED_DAYS;
        or finished work waiting more than WAIT_RED_DAYS; or the Mac silent
        that long with work pending.
    🟡  an item waiting on her (`owner_action`); or an empty slot inside the
        calendar; or finished work waiting more than WAIT_YELLOW_DAYS; or
        nothing queued this week while something is finished.
    🟢  otherwise.

    `loud_stops` is the STAGE NAME of every stop this week whose disposition
    was needs_human — the ones that already opened their own GitHub issue.
    THIS CHECK RUNS FIRST. Before 2026-09-22 it ran last, so the subject line
    (`reasons_red[0]`, below) named whichever ROUTINE pipeline observation —
    an empty slot two weeks out, work waiting on the Mac — happened to be
    checked earlier in this function, even in a week that also had a real
    named stop with its own open issue. That is exactly backwards: a
    needs_human stop IS the "NEEDS YOU" content and the other reasons are
    not, so the subject must name the lane that actually needs her, not
    whichever lane this function happens to check first. (The 2026-09-22
    audit: cloud-upload's NOTHING_SHELVED stop — its 8th consecutive day,
    issue #105 — is exactly the kind of reason this used to be able to
    bury behind an unrelated calendar note.)

    `waiting` is `loop/common.py:owner_actions()` — everything with
    disposition `owner_action`, the "## ⚠️ Waiting on you" section below,
    the ONE thing in this whole email actually addressed to her. It was
    never passed into this function at all: a week with an owner_action
    item and nothing else red or yellow rendered "🟢 Healthy" as BOTH the
    headline and the subject line, while the body's very first section said
    something needed her — the subject named no lane, or whichever
    unrelated calendar/pipeline note this function happened to check next,
    instead of the lane actually carrying the NEEDS-YOU content. Checked
    second, right after `loud_stops` and before any routine reason, for the
    same priority reason: it out-ranks a calendar note, never a genuine
    needs_human failure. It stays 🟡, not 🔴 — her own instruction was that
    an owner_action stop keeps its run green, and this only fixes the
    SUBJECT, not that disposition.
    """
    reasons_red, reasons_yellow = [], []
    if loud_stops:
        reasons_red.append(f"{len(loud_stops)} stop(s) needed a human this week "
                           f"({', '.join(sorted(set(loud_stops)))})")
    if waiting:
        reasons_yellow.append(
            f"{len(waiting)} item(s) waiting on you: "
            + ", ".join(f"{rec.get('code')} ({stage})"
                        for stage, rec in sorted(waiting.items())))
    empty = [c for c in cal if not c["slug"]]
    soon = [c for c in empty if c["days_away"] <= EMPTY_SLOT_RED_DAYS]
    if soon:
        reasons_red.append(f"{len(soon)} empty slot(s) inside {EMPTY_SLOT_RED_DAYS} days "
                           f"(first {soon[0]['date']:%a %d %b}, {soon[0]['domain']})")
    elif empty:
        reasons_yellow.append(f"{len(empty)} empty slot(s) inside {CALENDAR_WEEKS} weeks "
                              f"(first {empty[0]['date']:%a %d %b}, {empty[0]['domain']})")
    wd = pipe.get("waiting_days")
    if pipe.get("finished_waiting"):
        if wd is not None and wd > WAIT_RED_DAYS:
            reasons_red.append(f"{pipe['finished_waiting']} finished episode(s) waiting {wd} days on the Mac")
        elif wd is not None and wd > WAIT_YELLOW_DAYS:
            reasons_yellow.append(f"{pipe['finished_waiting']} finished episode(s) waiting {wd} days on the Mac")
        elif not queued_rows:
            reasons_yellow.append(f"nothing queued this week while {pipe['finished_waiting']} finished episode(s) wait")
    ms = pipe.get("mac_silent_days")
    if pipe.get("finished_waiting") and ms is not None and ms > WAIT_RED_DAYS:
        reasons_red.append(f"the Mac has not reported for {ms} days with work pending")
    if pipe.get("held"):
        reasons_yellow.append(f"held by the render gate: {', '.join(pipe['held'])}")

    n_q, n_s = len(queued_rows), pipe.get("scheduled", 0)
    if reasons_red:
        return "🔴", f"Stalled: {n_q} queued this week, {n_s} scheduled — {reasons_red[0]}", reasons_red + reasons_yellow
    if reasons_yellow:
        return "🟡", f"Watch: {n_q} queued this week, {n_s} scheduled — {reasons_yellow[0]}", reasons_yellow
    return "🟢", f"Healthy: {n_q} queued this week, {n_s} scheduled, every slot filled for {CALENDAR_WEEKS} weeks", []


def stops_in(week: str) -> list[dict]:
    """Named stops this week, from the files the stages themselves wrote."""
    out = []
    if not STOPS.exists():
        return out
    for path in sorted(STOPS.glob(f"{week}-*.json")):
        try:
            blob = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        # THE STOP FILE ALREADY CARRIES ITS OWN CLASSIFICATION. common.py's
        # disposition() decided it at the moment the stop was taken, against
        # loop/stop_policy.json and the stage's consecutive-run streak, and
        # wrote the answer here. Re-deriving it in the digest would be a second
        # copy of that rule that could disagree with the one that actually
        # decided whether to page a human.
        out.append({
            "stage": blob.get("stage") or path.stem[len(week) + 1:],
            "code": blob.get("code") or "?",
            "message": blob.get("message") or "",
            "why": blob.get("disposition_why") or "",
            "unblock": blob.get("unblock") or "",
            "disposition": blob.get("disposition") or "needs_human",
            "self_resolving": blob.get("disposition") == "self_resolving",
        })
    return out


HEARTBEAT = ROOT / "loop" / "state" / "mac_heartbeat.json"


def mac_stops(now: dt.datetime, hb: dict | None = None, cfg: dict | None = None) -> list[dict]:
    """The cloud noticing the Mac's silence. Pure over (heartbeat, now).

    WHY. Every stop a cloud lane takes is committed and read back here. The
    Mac's lanes wrote theirs to loop/state/stops/ ON THE MAC, so from 6 to 13
    September 2026 nine finished renders shipped nothing and this digest said
    nothing about it. The Mac now pushes loop/state/mac_heartbeat.json after
    every lane run (loop/mac_sync.py); this reads it and raises MAC_NOT_SHIPPING
    when finished work has waited longer than `mac.unshipped_days` - or when the
    heartbeat itself is that old while work is pending, which is the same
    silence wearing a different shape.
    """
    cfg = cfg or config()
    hb = hb if hb is not None else json.loads(HEARTBEAT.read_text()) if HEARTBEAT.exists() else {}
    limit = int((cfg.get("mac") or {}).get("unshipped_days", 3))
    lanes = {k: v for k, v in hb.items() if isinstance(v, dict)}
    pending = max([int(v.get("pending") or 0) for v in lanes.values()] or [0])
    latest = max([_when(v.get("last_run_at")) for v in lanes.values()
                  if _when(v.get("last_run_at"))] or [None], key=lambda d: d or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    last_ship = max([_when(v.get("last_success_at")) for v in lanes.values()
                     if v.get("uploaded") and _when(v.get("last_success_at"))] or [None],
                    key=lambda d: d or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    out = []
    if not lanes:
        if hb.get("renders_finished"):
            out.append(_mac_stop("no lane has ever reported a heartbeat, yet the "
                                 f"heartbeat file counts {hb['renders_finished']} finished render(s)"))
        return out
    if pending == 0:
        return out
    silent_days = (now - latest).days if latest else None
    shipped_days = (now - last_ship).days if last_ship else None
    if silent_days is not None and silent_days > limit:
        out.append(_mac_stop(f"{pending} finished episode(s) are pending on the Mac and "
                             f"no Mac lane has reported for {silent_days} days"))
    elif shipped_days is None or shipped_days > limit:
        held = sorted({s for v in lanes.values() for s in (v.get("held") or [])})
        out.append(_mac_stop(f"{pending} finished episode(s) are pending on the Mac and "
                             f"nothing has shipped for "
                             f"{'ever' if shipped_days is None else f'{shipped_days} days'}"
                             + (f"; held by the render gate: {', '.join(held)}" if held else "")))
    return out


def _mac_stop(message: str) -> dict:
    return {"stage": "mac", "code": "MAC_NOT_SHIPPING", "message": message,
            "why": "The Mac's lanes report through loop/state/mac_heartbeat.json; "
                   "finished work has waited longer than mac.unshipped_days.",
            "unblock": "On the Mac: ~/Library/Logs/how-we-know/backfill.log names the "
                       "stop; bin/loop-backfill-daily.sh re-runs it by hand.",
            "disposition": "needs_human", "self_resolving": False}


def render(week: str, now: dt.datetime) -> tuple[str, dict]:
    """The digest, and the counts it was built from."""
    cfg = config()
    led = ledger.load()
    per_week = cadence.effective()
    alloc = domains.allocation(cfg)
    live = domains.live_slots(cfg)
    runway = domains.domain_runway(cfg)
    depth = domains.queue_depth()
    br = breaker.load()
    gates = ypp.progress(cfg)
    week_ago = now - dt.timedelta(days=7)
    out_rows = aired(led, week_ago, now)
    next_rows = upcoming(led, now)
    stops = stops_in(week) + mac_stops(now)
    by_slug = domains.by_slug()
    hb = json.loads(HEARTBEAT.read_text()) if HEARTBEAT.exists() else {}
    queued_rows = queued_this_week(led, week_ago, now)
    cal = calendar(led, cfg, now)
    pipe = pipeline(led, depth, hb, now)
    loud_stages = sorted({s["stage"] for s in stops if s["disposition"] == "needs_human"})
    # Computed here, not where it used to be (just below, right before the
    # "## Waiting on you" section) — verdict() needs it too, so the subject
    # line can name it. See verdict()'s own docstring for the incident.
    waiting = common_owner_actions()
    mark, headline, reasons = verdict(queued_rows, cal, pipe, loud_stages, waiting)

    def dom(slug: str) -> str:
        return by_slug.get(slug, "—")

    L = [f"# How We Know — week of {week}", "",
         f"## {mark} {headline}", ""]
    for r in reasons[1:]:
        L.append(f"- {r}")
    if len(reasons) > 1:
        L.append("")

    # --- THE ONLY THING IN THIS EMAIL THAT IS ADDRESSED TO HER --------------
    #
    # Added 2026-09-08 with the `owner_action` disposition. Her instruction was
    # that a named stop must never arrive as a red CI run; the trade is that
    # something must still carry the handful of conditions only she can clear -
    # a revoked consent, a locked channel - or "green" would just mean
    # "invisible". This block is that something, and it is deliberately the
    # first thing in the digest, above the week's numbers. `waiting` itself
    # is computed above, before verdict(), which now reads it too.
    if waiting:
        L += ["## ⚠️ Waiting on you", "",
              "These are the only things in this system that a machine cannot "
              "do. Everything else healed itself or is not blocking. No run "
              "went red for any of them — that is on purpose.", "",
              "| Stage | What is blocked | What clears it |", "|---|---|---|"]
        for stage, rec in sorted(waiting.items()):
            L.append(f"| {stage} | `{rec.get('code')}` — "
                     f"{(rec.get('message') or '')[:140]} "
                     f"| {(rec.get('unblock') or '')[:220]} |")
        L += ["", "Each has been in this state for "
              + ", ".join(f"{rec.get('consecutive', 1)} run(s) ({stage})"
                          for stage, rec in sorted(waiting.items()))
              + ". They go red on their own if they outlive the limit in "
                "loop/stop_policy.json.", ""]

    # --- the one line that matters first
    tripped = br.get("state") != "closed"
    L += [f"**{len(out_rows)} episode(s) aired** · **{per_week}/week** · "
          f"breaker **{'TRIPPED' if tripped else 'closed'}** · "
          f"**{len(stops)} named stop(s)**", ""]
    if tripped:
        L += [f"> The circuit breaker is OPEN since {br.get('tripped_at')} "
              f"— cause `{br.get('cause')}`. Publishing is halted until it is "
              f"reset. {br.get('detail') or ''}", ""]

    L += ["## Queued this week", "",
          "What a lane put on YouTube in the last seven days, dated and waiting to air.", ""]
    if queued_rows:
        L += ["| Uploaded | Episode | Airs | Domain | Lane |", "|---|---|---|---|---|"]
        for r in queued_rows:
            airs = f"{r['_airs']:%a %d %b}" if r["_airs"] else "undated"
            L.append(f"| {r['_uploaded']:%a %d %b} | [{r['slug']}]"
                     f"(https://youtu.be/{r.get('video_id', '')}) | {airs} "
                     f"| {dom(r['slug'])} | {r['_lane']} |")
    elif pipe["finished_waiting"]:
        L.append(f"**Nothing was queued — and {pipe['finished_waiting']} finished episode(s) "
                 f"are waiting on the Mac.** That is the pipeline health line below, not a quiet week.")
    else:
        L.append("Nothing was queued: nothing new was finished this week. The calendar below says "
                 "whether that matters yet.")
    L.append("")

    L += ["## Pipeline health", "",
          "| Stage | Count | |", "|---|---|---|",
          f"| Topics queued, not yet uploaded | {pipe['queued']} | |",
          f"| …of which scripted | {pipe['scripted']} | |",
          f"| …of which narrated | {pipe['narrated']} | |"]
    wd = pipe["waiting_days"]
    wait_mark = ("🔴" if wd is not None and wd > WAIT_RED_DAYS else
                 "🟡" if wd is not None and wd > WAIT_YELLOW_DAYS else
                 "🟢" if pipe["finished_waiting"] else "")
    L.append(f"| Finished on the Mac, waiting to upload | {pipe['finished_waiting']} "
             f"| {wait_mark}{f' waiting {wd} days' if wd is not None and pipe['finished_waiting'] else ''} |")
    if pipe["held"]:
        L.append(f"| …of which held by the render gate | {len(pipe['held'])} | 🟡 {', '.join(pipe['held'])} |")
    L.append(f"| Uploaded and dated on YouTube | {pipe['scheduled']} | |")
    seen = pipe["mac_last_seen"]
    L.append(f"| Mac last reported | {seen:%a %d %b %H:%M} UTC | "
             f"{'🔴 silent' if (pipe['mac_silent_days'] or 0) > WAIT_RED_DAYS else ''} |"
             if seen else "| Mac last reported | never | 🟡 no heartbeat yet |")
    L.append("")

    empties = [c for c in cal if not c["slug"]]
    L += [f"## The calendar — next {CALENDAR_WEEKS} weeks", ""]
    if empties:
        soon = [c for c in empties if c["days_away"] <= EMPTY_SLOT_RED_DAYS]
        L.append(f"**{len(empties)} empty slot(s)**"
                 + (f", **{len(soon)} inside {EMPTY_SLOT_RED_DAYS} days**" if soon else "")
                 + ". Empty means no episode is dated for a day the cadence publishes on.")
    else:
        L.append(f"Every slot for the next {CALENDAR_WEEKS} weeks has an episode dated.")
    L += ["", "| Date | Domain | Episode |", "|---|---|---|"]
    for c in cal:
        cell = c["slug"] or ("**— EMPTY —** 🔴" if c["days_away"] <= EMPTY_SLOT_RED_DAYS else "**— empty —** 🟡")
        L.append(f"| {c['date']:%a %d %b} | {c['domain']} | {cell} |")
    L.append("")

    L += ["## Aired this week", ""]
    if out_rows:
        L += ["| Date | Episode | Domain |", "|---|---|---|"]
        for r in out_rows:
            L.append(f"| {r['_when']:%a %d %b} | [{r['slug']}]"
                     f"(https://youtu.be/{r.get('video_id', '')}) "
                     f"| {dom(r['slug'])} |")
    else:
        L.append("Nothing aired in the last seven days.")
    L.append("")

    L += ["## Runway", "",
          "| Domain | Slots/wk | Queued | Weeks left | |",
          "|---|---|---|---|---|"]
    for name in sorted(set(alloc) | set(runway)):
        r = runway.get(name, {})
        weeks = r.get("weeks")
        mark = {"critical": "🔴", "warn": "🟠", "ok": "🟢",
                "not_active": "⚪"}.get(r.get("level"), "")
        L.append(f"| {name} | {live.get(name, 0)} of {alloc.get(name, 0)} "
                 f"| {depth.get(name, 0)} "
                 f"| {'—' if weeks is None else f'{weeks:.1f}'} | {mark} |")
    L.append("")

    loud = [s for s in stops if s["disposition"] == "needs_human"]
    quiet = [s for s in stops if s["disposition"] == "self_resolving"]
    waited = [s for s in stops if s["disposition"] == "owner_action"]
    L += ["## Named stops", ""]
    if not stops:
        L += ["None. Every lane that ran, ran to completion.", ""]
    else:
        if loud:
            L += [f"**{len(loud)} stop(s) needed a human** and each opened its "
                  f"own issue when it happened:", "",
                  "| Stage | Code | What it said |", "|---|---|---|"]
            for s in loud:
                L.append(f"| {s['stage']} | `{s['code']}` "
                         f"| {s['message'][:110]} |")
            L.append("")
        if waited:
            L += [f"{len(waited)} stop(s) are waiting on YOU and are listed at "
                  f"the top of this email: "
                  + ", ".join(f"`{s['code']}` ({s['stage']})" for s in waited)
                  + ". None of them failed a run.", ""]
        if quiet:
            L += [f"{len(quiet)} self-resolving stop(s) — a lane halting "
                  f"deliberately in a state that clears itself. These are "
                  f"normal operation and page nobody: "
                  + ", ".join(f"`{s['code']}` ({s['stage']})" for s in quiet)
                  + ".", ""]

    near = (gates.get("gates") or [{}])[0]
    L += ["## Monetisation", "",
          f"Nearest gate is **{near.get('name', '?')}** — "
          f"{gates.get('long_form_watch_hours', 0)}h of long-form watch time, "
          f"{gates.get('subscribers', 0)} subscriber(s). "
          f"{(gates.get('deadline') or {}).get('days_remaining', '?')} days to "
          f"{(gates.get('deadline') or {}).get('date', '?')}, when the "
          f"long-form bar doubles for channels admitted after it.", ""]

    L += ["---", "",
          "Nothing here needs a reply. Every number above was decided and "
          "applied by the lane that owns it; this is a report, not a request. "
          "A decision that needs you opens its own issue.", ""]

    counts = {"aired": len(out_rows), "scheduled": len(next_rows),
              "queued": sum(depth.values()), "stops": len(stops),
              "tripped": tripped, "verdict": f"{mark} {headline}",
              "queued_this_week": len(queued_rows), "empty_slots": len(empties)}
    return "\n".join(L), counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="print_only", action="store_true")
    a = ap.parse_args()

    week = week_id()
    now = dt.datetime.now(dt.timezone.utc)
    with Stage("weekly-digest", week,
               zero_work_hint="The digest rendered with no episodes, no "
                              "schedule and no queue. That is not a quiet "
                              "week, it is a digest that read nothing - and a "
                              "reassuring weekly email built on files it "
                              "failed to open is worse than no email.") as st:
        body, counts = render(week, now)

        # RULE 0. A quiet week is legitimate; reading nothing is not. The three
        # together can only mean the ledger and the publish order were both
        # unreadable, because a channel with no queue AND no calendar AND no
        # episode in seven days has already stopped.
        if not (counts["aired"] or counts["scheduled"] or counts["queued"]):
            st.named_stop(
                "DIGEST_READ_NOTHING",
                "the digest found no episode aired in seven days, nothing "
                "scheduled ahead, and no queued topic in any domain. Every "
                "source it reads would have to be empty at once for that to "
                "be true.",
                detail=counts,
                unblock="Check loop/state/ledger.json and "
                        "research/publish_order*.json are readable and "
                        "committed. This is far more likely to be a read "
                        "failure than a stopped channel.")

        st.note(f"{counts['aired']} aired, {counts['scheduled']} scheduled, "
                f"{counts['queued']} queued, {counts['stops']} named stop(s)")
        if counts["tripped"]:
            st.note("the circuit breaker is OPEN - the digest says so first")

        if a.print_only:
            print(body)
            st.work("rendered the weekly digest (not written)")
            return 0

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"{week}.md"
        path.write_text(body + "\n", encoding="utf-8")
        st.work(f"wrote {path.relative_to(ROOT)}")
        # THE SUBJECT LINE. The workflow reads this one line into the issue
        # title, so the verdict is visible in her inbox without opening it.
        (OUT_DIR / f"{week}.subject").write_text(
            digest_subject(counts["verdict"], week) + "\n", encoding="utf-8")
        st.work(f"subject: {counts['verdict']}")
        print(body)
    return 0


def digest_subject(verdict_text: str, week: str, max_len: int = 180) -> str:
    """The one line the workflow puts in the issue title (`loop-sun-digest.yml`).

    `verdict_text` is `counts["verdict"]` — `f"{mark} {headline}"`. Until
    2026-09-23 this function's whole body was
    `counts['verdict'].split(' — ')[0]`, which keeps only the mark and the
    queued/scheduled counts and THROWS AWAY everything after the first
    " — " — exactly the `reasons_red[0]` / `reasons_yellow[0]` text
    `verdict()`'s own docstring says the subject names. Every subject read
    "Weekly digest — 🟡 Watch: N queued this week, N scheduled — 2026-W39"
    with no reason and no lane at all, whatever the actual cause — a real
    named stop, an owner_action item waiting on her, or a routine calendar
    note. `verdict()`'s ordering (`loud_stops`, then `owner_action`, then
    routine reasons) was therefore invisible in her inbox the whole time;
    only opening the email ever showed it — the exact "Shorts lane" subject
    on a long-form NEEDS YOU incident `test_digest_queue_and_health.py`
    already guards `verdict()`'s own ordering against, one layer up from
    this bug.

    Fixed by keeping the FULL verdict — mark, counts, AND the reason —
    capped only so one runaway reason cannot produce an unreadable subject.
    """
    if len(verdict_text) > max_len:
        verdict_text = verdict_text[:max_len - 3] + "..."
    return f"Weekly digest — {verdict_text} — {week}"


if __name__ == "__main__":
    raise SystemExit(main())
