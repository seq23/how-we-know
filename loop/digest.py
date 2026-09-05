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
            "self_resolving": blob.get("disposition") == "self_resolving",
        })
    return out


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
    stops = stops_in(week)
    by_slug = domains.by_slug()

    def dom(slug: str) -> str:
        return by_slug.get(slug, "—")

    L = [f"# How We Know — week of {week}", ""]

    # --- the one line that matters first
    tripped = br.get("state") != "closed"
    L += [f"**{len(out_rows)} episode(s) aired** · **{per_week}/week** · "
          f"breaker **{'TRIPPED' if tripped else 'closed'}** · "
          f"**{len(stops)} named stop(s)**", ""]
    if tripped:
        L += [f"> The circuit breaker is OPEN since {br.get('tripped_at')} "
              f"— cause `{br.get('cause')}`. Publishing is halted until it is "
              f"reset. {br.get('detail') or ''}", ""]

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

    L += ["## Next up", ""]
    if next_rows:
        L += ["| Date | Episode | Domain |", "|---|---|---|"]
        for r in next_rows:
            L.append(f"| {r['_when']:%a %d %b %H:%M} UTC | {r['slug']} "
                     f"| {dom(r['slug'])} |")
    else:
        L.append("**Nothing is scheduled.** That is the one line in this "
                 "digest worth acting on — the calendar is empty ahead.")
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

    loud = [s for s in stops if not s["self_resolving"]]
    quiet = [s for s in stops if s["self_resolving"]]
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
              "tripped": tripped}
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
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
