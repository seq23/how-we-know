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
import verdict as channel_verdict                          # noqa: E402
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
# SHORTS CADENCE (owner, 2026-10-12: "why did the Shorts lane emails never tell
# me"). Shorts went from 14 a week to 1 while this verdict counted long-form
# slots only. One week under config shorts_per_week is yellow; this week AND
# the week before under it is red.
SHORTS_RED_WEEKS = 2
SHORTS_LEDGER = ROOT / "loop" / "state" / "shorts_ledger.json"


def shorts_flag(shorts: dict | None) -> tuple[str | None, str | None]:
    """("red" | "yellow" | None, reason) from a verdict.shorts_cadence() dict.

    Pure. Red when the trailing 7 days AND the 7 before them were both under
    target (SHORTS_RED_WEEKS consecutive weeks); yellow when only the
    trailing 7 days were; None when on target or unmeasured.
    """
    if not shorts or not shorts.get("target_per_week"):
        return None, None
    want = int(shorts["target_per_week"])
    now_n, prev_n = int(shorts.get("published_7d") or 0), int(shorts.get("published_prev_7d") or 0)
    if now_n >= want:
        return None, None
    shelf = (f"; shelf {shorts.get('shelf')} verified unpublished "
             f"({shorts.get('shelf_weeks')} wk)" if shorts.get("shelf") is not None else "")
    if prev_n < want:
        return "red", (f"Shorts under target {SHORTS_RED_WEEKS} weeks running: "
                       f"{now_n} then {prev_n} vs {want}/week{shelf}")
    return "yellow", f"Shorts under target this week: {now_n} vs {want}/week{shelf}"


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
    import domains as _dom                                 # noqa: PLC0415
    per_week = int(cfg["cadence"]["videos_per_week"])
    # A domain held behind its owner-review sample (domains.sample_gate) has
    # days that are EMPTY BY DESIGN until the sample clears; counting them as
    # gaps would turn a decided hold into a red digest every week.
    gated = _dom.sample_gated(cfg)
    days_by_domain = {d: w for d, w in
                      backfill.domain_weekdays(cfg, per_week).items()
                      if d not in gated}
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


# PLAIN WORDS (owner, 2026-10-12, verbatim: "make sure the shorts lane email is
# honest. make sure it tells me plainly what is honestly going on if something
# needs work it should say it in the subject"). The W40 and W41 subjects read
# "🔴 Stalled: 1 queued this week, 16 scheduled — 1 stop(s) needed a human this
# week (mac)": a lane name in brackets, no mention of Shorts (which had fallen
# from 14 a week to 1), and no action. She did not read them as a problem. So
# every problem is now ONE plain sentence, the subject is the worst of them,
# and a stop code never reaches the subject or the first line - each code's
# `plain` sentence in loop/stop_policy.json does (test_every_stop_is_classified
# fails a code without one).
POLICY = ROOT / "loop" / "stop_policy.json"
_PLAIN: dict | None = None
PLAIN_FALLBACK = "a lane stopped on something it could not fix by itself"


def plain(code: str | None) -> str:
    """The owner-readable sentence for a stop code, from loop/stop_policy.json.

    Exact key first, then a `PREFIX*` wildcard family, across every section
    (and held.codes). A code with no `plain` gets PLAIN_FALLBACK - never the
    code itself.
    """
    global _PLAIN
    if _PLAIN is None:
        _PLAIN = {}
        try:
            pol = json.loads(POLICY.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pol = {}
        secs = [pol.get(k) or {} for k in ("self_resolving", "owner_action", "needs_human")]
        secs.append((pol.get("held") or {}).get("codes") or {})
        for sec in secs:
            for c, rule in sec.items():
                if isinstance(rule, dict) and rule.get("plain") and c not in _PLAIN:
                    _PLAIN[c] = rule["plain"]
    code = code or ""
    if code in _PLAIN:
        return _PLAIN[code]
    best = max((c for c in _PLAIN if c.endswith("*") and code.startswith(c[:-1])),
               key=len, default=None)
    return _PLAIN[best] if best else PLAIN_FALLBACK


# Stops the Mac raises (or the cloud raises about the Mac). Their fix is on the
# Mac, so the subject's action says so.
MAC_STAGES = {"mac", "mac-batch", "backfill", "render-gate", "batch"}
MAC_CODES = {"MAC_NOT_SHIPPING", "PULL_FAILED", "REBASE_IN_PROGRESS",
             "MAC_NOT_ON_MAIN", "MAC_BEHIND_MAIN",
             "RENDER_GATE_EMPTY", "RENDER_HELD", "SHORTS_UNVERIFIED",
             "SHORTS_SHELVED_BUT_UNVERIFIED", "HARVESTER_TOOLING_ABSENT",
             "DELEGATED_HARVEST_FAILING", "DELEGATED_HARVEST_STALE"}
# Self-resolving codes that ARE a supply shortfall when output is under target.
# W39-W41 filed NOTHING_SHELVED under "page nobody" three weeks running while
# Shorts and episodes fell; when a shortfall exists these join its problem line.
SHORTS_SUPPLY = {"NO_SHORTS_SHELVED", "SHORTS_SHELF_DRY", "SHORTS_INVENTORY_EXHAUSTED"}
EPISODE_SUPPLY = {"NOTHING_SHELVED", "NOTHING_RENDERED", "RUNWAY_WARN"}


def policy_action(code: str) -> str | None:
    """The `action` text loop/stop_policy.json gives a needs_human code, if any."""
    try:
        pol = json.loads(POLICY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rule = (pol.get("needs_human") or {}).get(code)
    return rule.get("action") if isinstance(rule, dict) else None


def breaker_action(breaker_state: dict) -> str | None:
    """What clears a tripped safety switch, by its cause. Pure but for the policy.

    A validator trip closes itself once every quality check passes, so the
    action is the policy's own words for BREAKER_TRIPPED. A manual trip or a
    strike has a stop issue; a retention or domain trip is cleared by the next
    weekly measurement, so it has no action of hers (None - "not fixed yet").
    """
    cause = breaker_state.get("cause")
    if cause == "validator":
        return policy_action("BREAKER_TRIPPED") or "fix the failing quality check"
    if cause in ("retention", "domain"):
        return None
    return "read the stop issue on GitHub"


def _stop(s) -> dict:
    return {"stage": s, "code": None} if isinstance(s, str) else dict(s)


def action_for(stop: dict) -> str:
    """What she does about a needs-you stop, in six words or fewer."""
    code, stage = stop.get("code") or "", stop.get("stage") or ""
    if stop.get("disposition") == "owner_action" or stop.get("_owner"):
        if code.startswith("OAUTH") or code in {"CAPTIONS_SCOPE_MISSING", "WRONG_CHANNEL"}:
            return "sign in to YouTube again"
        if code == "UPLOADS_LOCKED_PRIVATE":
            return "clear the lock in YouTube Studio"
        return "add the missing key or login"
    if stage in MAC_STAGES or code in MAC_CODES:
        return "check the Mac's nightly batch"
    return "read the stop issue on GitHub"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _repeat(s: dict) -> str:
    n = int(s.get("consecutive") or 1)
    return f" ({n} runs in a row)" if n > 1 else ""


def shorts_problem(shorts: dict | None) -> tuple[str | None, str | None]:
    """(flag, one plain sentence) for the Shorts cadence. Pure."""
    flag, _ = shorts_flag(shorts)
    if not flag:
        return None, None
    want = int(shorts["target_per_week"])
    now_n = int(shorts.get("published_7d") or 0)
    prev_n = int(shorts.get("published_prev_7d") or 0)
    if flag == "red":
        head = ("Shorts stopped" if now_n * 4 < want else
                f"Shorts under target {SHORTS_RED_WEEKS} weeks running")
        text = f"{head}: {now_n} of {want} published this week, {prev_n} of {want} the week before"
    else:
        text = f"Shorts under target: {now_n} of {want} published this week"
    if shorts.get("shelf") is not None:
        text += ("; none waiting on the shelf" if not shorts.get("shelf") else
                 f"; shelf {shorts['shelf']} ({shorts.get('shelf_weeks')} weeks)")
    return flag, text


def verdict(queued_rows: list[dict], cal: list[dict], pipe: dict,
            loud_stops: list,
            waiting: dict | None = None,
            shorts: dict | None = None,
            quiet_stops: list[dict] | None = None,
            episodes_target: int | None = None,
            breaker_state: dict | None = None) -> tuple[str, str, list[str]]:
    """(emoji, subject sentence, every problem line worst-first). Pure.

    Each problem is one plain sentence naming WHAT (Shorts, episodes, the Mac,
    uploads) with numbers as "X of Y". Worst first:

      🔴 publishing halted by the circuit breaker (`breaker_state` not
         closed) - nothing airs at all until it resets;
      🔴 Shorts under target two weeks running (shorts_flag red) - Shorts carry
         most of the channel's views, and W40-W41 hid exactly this;
      🔴 a stop that needed a human (`loud_stops`, needs_human) - each in its
         `plain` words; it out-ranks every routine pipeline note (2026-09-22:
         an unrelated calendar note used to lead over a real stop);
      🔴 an empty slot inside EMPTY_SLOT_RED_DAYS, finished work waiting more
         than WAIT_RED_DAYS, the Mac silent that long with work pending;
      🟡 an item waiting on her key or account (`waiting`, owner_action) - it
         out-ranks a routine note, never a needs_human failure;
      🟡 Shorts or episodes under target this week, an empty slot in the
         calendar, finished work waiting more than WAIT_YELLOW_DAYS, nothing
         queued while work waits, renders held by the quality check.

    The subject is the worst sentence, then:
      "— needs you: <action in ≤6 words>" ONLY when the LEAD problem has an
         action of hers (its own - never another problem's), then
         "— +N more needs you" counting every other problem with an action;
      "— not fixed yet" for red with no such stop; "— watching" for yellow.
    🟢 names the counts: "All lanes ran: X of Y episodes queued, N scheduled,
    Shorts A of B".

    `quiet_stops` are the week's self_resolving stops. They never reach the
    subject on their own; but when Shorts or episodes are under target the
    supply codes among them (SHORTS_SUPPLY, EPISODE_SUPPLY) are listed as
    "Still happening: …" lines right under the shortfall, because a stop that "cleared itself" for three weeks
    while output fell did not clear.
    """
    loud = [_stop(s) for s in loud_stops or []]
    owners = [{"stage": st_, "code": rec.get("code"), "disposition": "owner_action",
               "consecutive": rec.get("consecutive")}
              for st_, rec in sorted((waiting or {}).items())]
    quiet = [_stop(s) for s in quiet_stops or []]
    red: list[tuple[str, str | None]] = []       # (plain sentence, action or None)
    yellow: list[tuple[str, str | None]] = []

    if breaker_state and breaker_state.get("state") not in (None, "closed"):
        when = _when(breaker_state.get("tripped_at"))
        cause = {"validator": "a quality check failed"}.get(
            breaker_state.get("cause"), "a safety check failed")
        red.append((f"Publishing is halted: the safety switch tripped"
                    f"{f' {when:%a %d %b}' if when else ''} because {cause}",
                    breaker_action(breaker_state)))
    sflag, stext = shorts_problem(shorts)
    # A supply stop that kept "clearing itself" while output fell is listed
    # right under the shortfall it explains, as its own line - never in the
    # subject, never as "cleared on their own".
    still = lambda codes: [(f"Still happening: {plain(s.get('code'))}{_repeat(s)}", None)  # noqa: E731
                           for s in quiet if s.get("code") in codes]
    if sflag == "red":
        red.append((stext, None))
        red += still(SHORTS_SUPPLY)
    for s in loud:
        red.append((f"{_cap(plain(s.get('code')))}{_repeat(s)}", action_for(s)))
    empty = [c for c in cal if not c["slug"]]
    soon = [c for c in empty if c["days_away"] <= EMPTY_SLOT_RED_DAYS]
    if soon:
        red.append((f"Episode calendar has gaps: {len(soon)} empty day(s) in the next "
                    f"two weeks, first {soon[0]['date']:%a %d %b} ({soon[0]['domain']})", None))
    wd = pipe.get("waiting_days")
    n_wait = pipe.get("finished_waiting") or 0
    if n_wait and wd is not None and wd > WAIT_RED_DAYS:
        red.append((f"Uploads stuck: {n_wait} finished episode(s) waiting {wd} days on the Mac", None))
    ms = pipe.get("mac_silent_days")
    if n_wait and ms is not None and ms > WAIT_RED_DAYS:
        red.append((f"The Mac has not reported for {ms} days with {n_wait} episode(s) waiting", None))

    for s in owners:
        yellow.append((_cap(plain(s.get("code"))), action_for(s)))
    if sflag == "yellow":
        yellow.append((stext, None))
        yellow += still(SHORTS_SUPPLY)
    n_q, n_s = len(queued_rows), pipe.get("scheduled", 0)
    if episodes_target and n_q < episodes_target:
        yellow.append((f"Episodes under target: {n_q} of {episodes_target} uploaded "
                       f"this week, {n_s} scheduled ahead", None))
        yellow += still(EPISODE_SUPPLY)
    if empty and not soon:
        yellow.append((f"Episode calendar has gaps: {len(empty)} empty day(s) in the next "
                       f"{CALENDAR_WEEKS} weeks, first {empty[0]['date']:%a %d %b} ({empty[0]['domain']})", None))
    if n_wait and wd is not None and WAIT_YELLOW_DAYS < wd <= WAIT_RED_DAYS:
        yellow.append((f"Uploads slow: {n_wait} finished episode(s) waiting {wd} days on the Mac", None))
    elif n_wait and not queued_rows and not (wd is not None and wd > WAIT_RED_DAYS):
        yellow.append((f"No episode uploaded this week while {n_wait} finished episode(s) wait on the Mac", None))
    if pipe.get("held"):
        yellow.append((f"Held back by the Mac's quality check: {', '.join(pipe['held'])}", None))

    problems = red + yellow
    if problems:
        mark = "🔴" if red else "🟡"
        # THE ACTION BELONGS TO THE LEAD (2026-10-12, W42). The tail used to be
        # the action of the FIRST needs-you stop, whatever led the subject:
        # "Publishing is halted: the safety switch tripped … — needs you: check
        # the Mac's nightly batch", and checking the Mac does not clear the
        # switch. Now the action is the lead problem's own, and every OTHER
        # problem with an action is counted ("+1 more needs you"); the body
        # lists each with its own action.
        lead, lead_action = problems[0]
        more = sum(1 for _, a in problems[1:] if a)
        tail = (f"needs you: {lead_action}" if lead_action else
                "not fixed yet" if red else "watching")
        if more:
            tail += f" — +{more} more needs you"
        reasons = [t + (f" — {a}" if a else "") for t, a in problems]
        return mark, f"{lead} — {tail}", reasons
    shorts_part = ""
    if shorts and shorts.get("target_per_week"):
        shorts_part = f", Shorts {int(shorts.get('published_7d') or 0)} of {int(shorts['target_per_week'])}"
    eps = f"{n_q} of {episodes_target}" if episodes_target else f"{n_q}"
    return "🟢", f"All lanes ran: {eps} episodes queued, {n_s} scheduled{shorts_part}", []


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
            "consecutive": blob.get("consecutive") or 1,
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
            "disposition": "needs_human", "consecutive": 1, "self_resolving": False}


def r2_shelf_now(prev_sc: dict, now: dt.datetime) -> tuple[int | None, str, str | None]:
    """(verified Shorts on R2 not yet uploaded, basis, as-of) at render time.

    WHY (2026-10-12, W42). The digest printed "shelf 2 verified unpublished,
    0 on R2" at 16:44 UTC while 38 verified cuts sat on R2: it reused the
    measure lane's 15:54:16 count, and the Mac pushed all 40 rank-2/3 cuts
    between 15:54:34 and 16:00:39 (R2 last_modified). The count was true when
    taken and stale when mailed, with nothing on the page saying when it was
    taken. So the digest reads the shelf itself - measure.r2_shelf_count(),
    the same listing and the same verified test the Shorts lane applies - and
    falls back to the measured count only when the live read is unavailable,
    stamped with the time it was measured. Never a guessed zero.
    """
    try:
        import measure                                     # noqa: PLC0415
        n, basis = measure.r2_shelf_count()
    except Exception as e:                                 # noqa: BLE001
        n, basis = None, f"live R2 read failed: {str(e)[:100]}"
    if n is not None:
        return n, f"{basis} (read live)", now.isoformat(timespec="seconds")
    measured = prev_sc.get("r2_verified_unpublished")
    if measured is None:
        return None, basis, None
    as_of = prev_sc.get("r2_as_of") or prev_sc.get("as_of")
    return (measured, f"measured {as_of}: {prev_sc.get('r2_basis')} "
                      f"(live read unavailable: {basis})", as_of)


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
    loud_stops = [s for s in stops if s["disposition"] == "needs_human"]
    quiet_stops = [s for s in stops if s["disposition"] == "self_resolving"]
    # Computed here, not where it used to be (just below, right before the
    # "## Waiting on you" section) — verdict() needs it too, so the subject
    # line can name it. See verdict()'s own docstring for the incident.
    waiting = common_owner_actions()
    # Shorts cadence, live at render time from the shorts ledger AND the R2
    # shelf (r2_shelf_now); the measure lane's count is only the fallback.
    cv = channel_verdict.read() or {}
    prev_sc = cv.get("shorts_cadence") or {}
    try:
        sl = json.loads(SHORTS_LEDGER.read_text()).get("published", [])
    except (OSError, ValueError):
        sl = None
    r2_n, r2_basis, r2_as_of = r2_shelf_now(prev_sc, now)
    sc = (channel_verdict.shorts_cadence(
              sl, cadence.shorts_effective(), now, r2_n, r2_basis,
              r2_as_of=r2_as_of)
          if sl is not None else None)
    if sc is not None:
        cv["shorts_cadence"] = sc
    mark, headline, reasons = verdict(queued_rows, cal, pipe, loud_stops,
                                      waiting, sc, quiet_stops, per_week, br)
    verdict_line = f"{mark} {headline}"     # frozen here; the subject reads this

    def dom(slug: str) -> str:
        return by_slug.get(slug, "—")

    L = [f"# How We Know — week of {week}", "",
         f"## {mark} {headline}", ""]
    for r in reasons[1:]:
        L.append(f"- {r}")
    if len(reasons) > 1:
        L.append("")

    # IS THIS WORKING - the channel's numbers with their floors beside them,
    # written each Friday by loop/measure.py into channel_verdict.json
    # (loop/verdict.py). Second on the page, under the pipeline verdict.
    L += channel_verdict.digest_block(cv)

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
        L += ["## 🔑 Needs your key or account", "",
              "These are the only things in this system that a machine cannot "
              "do. Everything else healed itself or is not blocking. No run "
              "went red for any of them — that is on purpose.", "",
              "| Stage | What is blocked | What clears it |", "|---|---|---|"]
        for stage, rec in sorted(waiting.items()):
            L.append(f"| {stage} | {plain(rec.get('code'))} — "
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
        # `rmark`, never `mark`: until 2026-10-12 this loop rebound the
        # verdict's `mark`, so the SUBJECT carried the last runway row's 🟢
        # while the body said 🔴 ("🟢 Stalled: …", W39-W41).
        rmark = {"critical": "🔴", "warn": "🟠", "ok": "🟢",
                 "not_active": "⚪"}.get(r.get("level"), "")
        L.append(f"| {name} | {live.get(name, 0)} of {alloc.get(name, 0)} "
                 f"| {depth.get(name, 0)} "
                 f"| {'—' if weeks is None else f'{weeks:.1f}'} | {rmark} |")
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
                  "| Stage | What happened | What it said |", "|---|---|---|"]
            for s in loud:
                L.append(f"| {s['stage']} | {plain(s['code'])} "
                         f"| {s['message'][:110]} |")
            L.append("")
        if waited:
            L += [f"{len(waited)} stop(s) are needing YOUR key or account and are listed at "
                  f"the top of this email: "
                  + "; ".join(plain(s['code']) for s in waited)
                  + ". None of them failed a run.", ""]
        # NEVER A FOOTNOTE FOR A SHORTFALL. This line used to read "These
        # are normal operation and page nobody", and W39-W41 filed
        # NOTHING_SHELVED and NO_SHORTS_SHELVED here while Shorts fell from
        # 14 a week to 1. When output is under target, the supply stops are
        # already on the shortfall's problem line at the top (verdict()), so
        # they are left out of "cleared on their own" - they did not clear.
        # Same two conditions verdict() uses to absorb them.
        hide = set()
        if shorts_flag(sc)[0]:
            hide |= SHORTS_SUPPLY
        if per_week and len(queued_rows) < per_week:
            hide |= EPISODE_SUPPLY
        cleared = [s for s in quiet if s["code"] not in hide]
        if cleared:
            L += ["Cleared on their own this week: "
                  + "; ".join(sorted({plain(s['code']) for s in cleared}))
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
              "tripped": tripped, "verdict": verdict_line,
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

    2026-10-12: the "Weekly digest — " prefix is gone so the inbox shows the
    problem first ("🔴 Shorts stopped: 1 of 9 … — needs you: … — 2026-W42");
    verdict() now writes that sentence in plain words. The workflow finds last
    week's issue by label and week instead of the prefix.
    """
    if len(verdict_text) > max_len:
        verdict_text = verdict_text[:max_len - 3] + "..."
    return f"{verdict_text} — {week}"


if __name__ == "__main__":
    raise SystemExit(main())
