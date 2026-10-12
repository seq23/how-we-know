"""The monthly email: what was published, what the data says, and whether to pivot.

Owner, 2026-10-12: *"when u do the data and research about whether or not to
pivot i need an email about that stuff too... and i think we need an overall
email sent to me monthly about what was published (# of shorts, # of long
form, what niches, and what the data suggests)"*.

loop/monthly.py DECIDES (bounded changes to loop/config.json). This module
REPORTS, in plain words, numbers first, four sections in a fixed order:

  1. Published this month - long-form and Shorts by domain, titles listed,
     and what is scheduled ahead.
  2. What the data says - channel_verdict.json and measurement_history.jsonl.
  3. Keep, change or pivot - every existing rule with its numbers, triggered
     or not, then ONE advisory paragraph from the model (loop/advise.py's
     route: her subscription first). The paragraph is advisory; the rules
     decide. A failed or off-brief model answer prints a named stop line,
     never a crash and never a paragraph made up here.
  4. What needs you - owner_action records, else "Nothing."

Output: loop/state/monthly/<YYYY-MM>-email.md, .subject, .json. The workflow
(.github/workflows/loop-monthly-review.yml) delivers it the same way the
Sunday digest is delivered: a new issue that @-mentions the owner, titled by
the .subject line.

    python3 loop/monthly_email.py           # the month just ended (the 1st)
    python3 loop/monthly_email.py --now     # this month to date, on demand
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

import advise  # noqa: E402
import common  # noqa: E402
import domains  # noqa: E402
import opening  # noqa: E402
from common import Stage, config, read_json, write_json  # noqa: E402

STATE = ROOT / "loop" / "state"
LEDGER = STATE / "ledger.json"
SHORTS_LEDGER = STATE / "shorts_ledger.json"
VERDICT = STATE / "channel_verdict.json"
HISTORY = STATE / "measurement_history.jsonl"
OUTDIR = STATE / "monthly"
RESEARCH_DOC = "docs/research/how-we-know-numbers.md"
PUBLISH_ORDERS = ROOT / "research"
DECISION_LOG = ROOT / "docs" / "DECISION-LOG.md"

HISTORY_STARTS = "2026-10-12"
CADENCE_OWNER_DECISION = "2 Sep 2026"
CADENCE_RESEARCH = ("reviewed 12 Oct 2026: 4 a week holds (education channels "
                    "posting 2-20 a month sit in the same flat zone; the cliff "
                    f"is past 20 a month) - {RESEARCH_DOC}, section 5")

LABEL = {"deep-sea-ocean-science": "deep sea",
         "materials-and-manufacturing": "materials"}
ORDER = ["deep sea", "materials", "other"]
NO_PIVOT = "no pivot rule has triggered; the data is too thin to pivot on"
ADVICE_STOP = "MONTHLY_ADVICE_UNAVAILABLE"


# ----------------------------------------------------------------- helpers

def label(domain: str | None) -> str:
    return LABEL.get(domain or "", "other")


def month_bounds(mid: str) -> tuple[dt.date, dt.date]:
    y, m = int(mid[:4]), int(mid[5:])
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def prev_month(mid: str) -> str:
    y, m = int(mid[:4]), int(mid[5:])
    return f"{y-1:04d}-12" if m == 1 else f"{y:04d}-{m-1:02d}"


def month_name(mid: str) -> str:
    return calendar.month_name[int(mid[5:])]


def air_date(e: dict) -> dt.date | None:
    """When an upload went (or goes) public; None if it never will."""
    if e.get("schedule_cancelled_at"):
        return None
    s = e.get("published_at") or e.get("scheduled_publish_at")
    if not s:
        return None
    d = dt.date.fromisoformat(s[:10])
    if e.get("retired_at") and e["retired_at"][:10] < s[:10]:
        return None
    return d


def plain(text: str) -> str:
    """Domain ids read as code in an email; print the plain names."""
    for k, v in LABEL.items():
        text = text.replace(k, v)
    return text


def question_of(slug: str, questions: dict[str, str]) -> str:
    if slug in questions:
        return questions[slug]
    return re.sub(r"^\d+-", "", slug).replace("-", " ")


def load_history(path: Path | None = None) -> list[dict]:
    p = path or HISTORY
    out = []
    try:
        for line in p.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    except OSError:
        pass
    return out


def latest_per_video(rows: list[dict], kind: str, upto: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") != kind or (r.get("date") or "") > upto:
            continue
        v = r.get("video_id")
        if v and (v not in out or r.get("date", "") >= out[v].get("date", "")):
            out[v] = r
    return out


def _arrow(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return ""
    return " ↑" if now > before else (" ↓" if now < before else " →")


def _n(x) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return f"{x:,}" if isinstance(x, int) else f"{x:,.1f}"


# ------------------------------------------------------------------ gather

def gather(mid: str, today: dt.date, partial: bool, cfg: dict) -> dict:
    """Every number the email prints, in one dict (also written as .json)."""
    first, last = month_bounds(mid)
    end = min(last, today) if partial else last
    long_pub = read_json(LEDGER, default={}).get("published", [])
    short_pub = read_json(SHORTS_LEDGER, default={}).get("published", [])
    questions = {e["slug"]: e.get("question") or e["slug"] for e in long_pub
                 if e.get("slug")}

    def published(entries):
        out = []
        for e in entries:
            d = air_date(e)
            if d and first <= d <= end and d <= today:
                out.append({**e, "_air": d.isoformat(),
                            "_domain": label(domains.domain_of_slug(e["slug"]))})
        return out

    def ahead(entries):
        ds = [air_date(e) for e in entries]
        ds = [d for d in ds if d and d > today]
        return {"count": len(ds), "last": max(ds).isoformat() if ds else None}

    lf, sh = published(long_pub), published(short_pub)
    by = {"long_form": {}, "shorts": {}}
    for kind, rows in (("long_form", lf), ("shorts", sh)):
        for e in sorted(rows, key=lambda e: e["_air"]):
            by[kind].setdefault(e["_domain"], []).append(
                {"slug": e["slug"], "question": question_of(e["slug"], questions),
                 "video_id": e.get("video_id"), "aired": e["_air"]})

    # ---- data
    hist = load_history()
    upto = end.isoformat()
    lrows = latest_per_video(hist, "long", upto)
    srows = latest_per_video(hist, "short", upto)
    ids_lf = {e.get("video_id") for e in lf}
    ids_sh = {e.get("video_id") for e in sh}
    title = {e.get("video_id"): question_of(e["slug"], questions)
             for e in long_pub + short_pub}

    def top(rows: dict[str, dict], ids: set) -> list[dict]:
        mine = [r for v, r in rows.items() if v in ids]
        mine.sort(key=lambda r: (-(r.get("views") or 0), r.get("video_id")))
        return [{"video_id": r["video_id"], "views": r.get("views") or 0,
                 "title": title.get(r["video_id"], r["video_id"])}
                for r in mine[:5]]

    def views_of(rows, ids):
        return sum((r.get("views") or 0) for v, r in rows.items() if v in ids)

    v = read_json(VERDICT, default={})
    v28 = v.get("views_28d") or {}
    target = int(cfg.get("cadence", {}).get("shorts_per_week", 9))
    weeks = []
    d = first
    while d <= end:
        iso = d.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        days = [x for x in (d + dt.timedelta(n) for n in range(7 - d.weekday()))
                if x <= end]
        n = sum(1 for e in sh if days[0].isoformat() <= e["_air"] <= days[-1].isoformat())
        weeks.append({"week": wk, "from": days[0].isoformat(),
                      "to": days[-1].isoformat(), "shorts": n, "target": target,
                      "full_week": len(days) == 7})
        d = days[-1] + dt.timedelta(1)

    data = {
        "views_28d_long_form": v28.get("long_form"),
        "views_28d_shorts": v28.get("shorts"),
        "views_month_long_form": views_of(lrows, ids_lf),
        "views_month_shorts": views_of(srows, ids_sh),
        "median_views_per_episode": v.get("median_views_per_long_form_video"),
        "median_views_per_short": v.get("median_views_per_short"),
        "top_episodes": top(lrows, ids_lf),
        "top_shorts": top(srows, ids_sh),
        "avd_s": v.get("avd_s"),
        "avd_floor_s": v.get("avd_floor_s") or float(cfg["retention"]["floor_avd_seconds"]),
        "subscribers_28d_net": v.get("subscribers_28d_net"),
        "subscribers_total": v.get("subscribers_total"),
        "watch_hours": v.get("watch_hours_long_form"),
        "watch_hours_floor": v.get("watch_hours_floor") or 3000.0,
        "watch_hours_pct": v.get("watch_hours_pct"),
        "verdict_as_of": v.get("as_of"),
        "shorts_weeks": weeks,
    }

    prev = read_json(OUTDIR / f"{prev_month(mid)}-email.json", default={})
    return {
        "month": mid, "partial": partial, "from": first.isoformat(),
        "to": end.isoformat(), "today": today.isoformat(),
        "published": {
            "long_form": len(lf), "shorts": len(sh), "by_domain": by,
            "ahead": {"long_form": ahead(long_pub), "shorts": ahead(short_pub)},
        },
        "data": data,
        "previous": prev.get("data") if prev else None,
        "rules": rules(cfg, lrows, long_pub, first, end, today),
        "needs_you": needs_you(end),
    }


def rules(cfg: dict, lrows: dict[str, dict], long_pub: list[dict],
          first: dt.date, end: dt.date, today: dt.date) -> dict:
    """Every existing keep/change/pivot rule, with its numbers, triggered or not."""
    rows = list(lrows.values())
    split = domains.split_rows(rows, long_pub)
    ev = {name: domains.evidence(split.get(name, []), cfg)
          for name in domains.allocation(cfg)}
    need = domains.min_episodes_to_judge(cfg)
    floor_q = domains.queue_exhausted_below(cfg)
    depth = domains.queue_depth()
    life = domains.lifecycle(cfg, ev)
    realloc = domains.reallocate(cfg, ev)
    spread_need = float(domains.config_domains(cfg).get("reallocate_avd_spread_s", 30))
    avds = {d: e["avd_s"] for d, e in ev.items() if e.get("avd_s") is not None}
    spread = (round(max(avds.values()) - min(avds.values()), 1)
              if len(avds) >= 2 else None)

    aired: dict[str, list[str]] = {}
    for e in long_pub:
        d = air_date(e)
        if d and d <= today:
            aired.setdefault(opening.variant_of(e["slug"]), []).append(d.isoformat())
    op = opening.evaluate(rows, now=dt.datetime.combine(
        today, dt.time(12), tzinfo=dt.timezone.utc), write=False, aired=aired)
    eligible = len(aired.get(op["active"], []))

    return {
        "domain_swap": {
            "triggered": bool(life.get("applied")),
            "retired": life.get("retired"), "promoted": life.get("promoted"),
            "need_measured": need, "queue_floor": floor_q,
            "domains": {label(d): {"measured": e["measured"],
                                   "queue": depth.get(d, 0),
                                   "avd_s": e.get("avd_s")}
                        for d, e in ev.items()},
            "why": life.get("why", ""),
        },
        "slot_move": {
            "triggered": bool(realloc.get("applied")),
            "moved": realloc.get("moved"), "spread_s": spread,
            "need_spread_s": spread_need, "need_measured": need,
            "why": realloc.get("why", ""),
        },
        "opening": {
            "triggered": op.get("action") == "switch",
            "active": op["active"], "eligible": eligible,
            "need": opening.MIN_COHORT, "compare_on": op.get("compare_on"),
            "action": op.get("action"), "why": op.get("why", ""),
        },
        "topic_kills": topic_kills(first, end),
        "cadence": {"per_week": cfg["cadence"]["videos_per_week"],
                    "owner_decision": CADENCE_OWNER_DECISION,
                    "research": CADENCE_RESEARCH, "triggered": False},
    }


def topic_kills(first: dt.date, end: dt.date) -> list[dict]:
    """Topics the demand/competition gate killed in a scoring pass run this month,
    plus held scripts the Saturday gate declined (docs/DECISION-LOG.md)."""
    out = []
    for p in sorted(PUBLISH_ORDERS.glob("publish_order*.json")):
        doc = read_json(p, default={})
        when = (doc.get("generated_utc") or doc.get("generated_at") or "")[:10]
        if not when or not (first.isoformat() <= when <= end.isoformat()):
            continue
        for k in doc.get("killed") or []:
            out.append({"slug": k.get("slug"), "on": when,
                        "why": k.get("reason") or ", ".join(k.get("failed_axes") or [])})
    try:
        log = DECISION_LOG.read_text(encoding="utf-8")
    except OSError:
        log = ""
    day = None
    for line in log.splitlines():
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if m:
            day = m.group(1)
        elif day and first.isoformat() <= day <= end.isoformat():
            m = re.match(r"^- \*\*DECLINED\*\* `([^`]+)` — (.*?)(?: Moved to.*)?$", line)
            if m:
                out.append({"slug": m.group(1), "on": day, "why": m.group(2)})
    return out


def needs_you(end: dt.date) -> list[dict]:
    out = []
    for stage, rec in sorted((common.owner_actions() or {}).items()):
        if not isinstance(rec, dict):
            continue
        if (rec.get("at") or "")[:10] > end.isoformat():
            continue
        out.append({"stage": stage, "message": rec.get("message") or "",
                    "unblock": rec.get("unblock") or ""})
    return out


def triggered(r: dict) -> list[str]:
    """Plain clauses for every rule that fired. Empty = nothing fired."""
    out = []
    ds = r["domain_swap"]
    if ds["triggered"]:
        out.append(f"domain swap rule triggered for {label(ds['retired'])}")
    sm = r["slot_move"]
    if sm["triggered"] and sm.get("moved"):
        out.append(f"slot move rule triggered: one slot from "
                   f"{label(sm['moved']['from'])} to {label(sm['moved']['to'])}")
    if r["opening"]["triggered"]:
        out.append("opening line rule triggered a switch")
    return out


# ------------------------------------------------------------------ render

def subject(f: dict) -> str:
    p = f["published"]
    when = month_name(f["month"])
    if f["partial"]:
        when += f" so far (to {int(f['to'][8:])} {when[:3]})"
    fired = triggered(f["rules"])
    clause = "; ".join(fired) if fired else "no pivot rule triggered"
    return (f"Monthly: {p['long_form']} episodes + {p['shorts']} Shorts "
            f"published in {when}; {clause}")


def section_published(f: dict) -> list[str]:
    p = f["published"]
    L = ["## 1. Published this month", ""]
    L.append(f"**{p['long_form']} long-form episodes and {p['shorts']} Shorts** "
             f"went public between {f['from']} and {f['to']}.")
    L.append("")
    for kind, name in (("long_form", "Long-form"), ("shorts", "Shorts")):
        groups = p["by_domain"][kind]
        counts = ", ".join(f"{d} {len(groups.get(d, []))}" for d in ORDER)
        L += [f"### {name}: {counts}", ""]
        for d in ORDER:
            items = groups.get(d) or []
            if not items:
                continue
            L.append(f"**{d}** ({len(items)})")
            for it in items:
                L.append(f"- {it['aired']} · {it['slug']} → {it['question']}")
            L.append("")
        if not any(groups.values()):
            L += ["None this month.", ""]
    a = p["ahead"]
    L.append(f"**Scheduled ahead:** {a['long_form']['count']} episodes "
             f"(last dated day {a['long_form']['last'] or 'none'}) and "
             f"{a['shorts']['count']} Shorts (last dated day "
             f"{a['shorts']['last'] or 'none'}).")
    L.append("")
    return L


def section_data(f: dict) -> list[str]:
    d, prev = f["data"], f.get("previous")
    L = ["## 2. What the data says", ""]
    if not prev:
        L += [f"_First month of history: measurement history starts "
              f"{HISTORY_STARTS}, so there is no previous month to compare "
              f"with and no trend arrows yet._", ""]

    def tr(key):
        return _arrow(d.get(key), (prev or {}).get(key)) if prev else ""

    L += [
        f"- **Views, 28 days:** long-form {_n(d['views_28d_long_form'])}"
        f"{tr('views_28d_long_form')}, Shorts {_n(d['views_28d_shorts'])}"
        f"{tr('views_28d_shorts')} (channel report as of {d['verdict_as_of'] or 'n/a'}).",
        f"- **Views on this month's uploads (to date):** long-form "
        f"{_n(d['views_month_long_form'])}{tr('views_month_long_form')}, Shorts "
        f"{_n(d['views_month_shorts'])}{tr('views_month_shorts')}.",
        f"- **Median views:** {_n(d['median_views_per_episode'])} per episode"
        f"{tr('median_views_per_episode')}, {_n(d['median_views_per_short'])} per Short"
        f"{tr('median_views_per_short')}.",
        f"- **Average view duration (long-form):** {_n(d['avd_s'])} s against the "
        f"{_n(d['avd_floor_s'])} s floor"
        + ("" if d["avd_s"] is None else
           (" - above" if d["avd_s"] >= d["avd_floor_s"] else " - below"))
        + f"{tr('avd_s')}.",
        f"- **Subscribers:** {_n(d['subscribers_28d_net'])} net in 28 days"
        f"{tr('subscribers_28d_net')}, {_n(d['subscribers_total'])} total.",
        f"- **Watch hours (long-form):** {_n(d['watch_hours'])} of "
        f"{_n(d['watch_hours_floor'])} ({_n(d['watch_hours_pct'])}%)"
        f"{tr('watch_hours')}.",
        "",
    ]
    for key, name in (("top_episodes", "Top episodes this month"),
                      ("top_shorts", "Top Shorts this month")):
        L.append(f"**{name}**")
        rows = d[key]
        if not rows:
            L.append("- none measured yet")
        for i, r in enumerate(rows, 1):
            L.append(f"{i}. {r['title']} - {_n(r['views'])} "
                     f"view{'' if r['views'] == 1 else 's'}")
        L.append("")
    L += ["**Shorts published vs the target, by week**", "",
          "| week | days | Shorts | target |", "|---|---|---|---|"]
    for w in d["shorts_weeks"]:
        days = f"{w['from'][5:]}–{w['to'][5:]}" + ("" if w["full_week"] else " (part)")
        L.append(f"| {w['week']} | {days} | {w['shorts']} | {w['target']} |")
    L.append("")
    return L


def section_rules(f: dict) -> list[str]:
    r = f["rules"]
    L = ["## 3. Keep, change or pivot - what the rules say", ""]
    ds = r["domain_swap"]
    L.append(f"- **Domain swap rule** (a domain is swapped out when its topic "
             f"queue falls below {ds['queue_floor']} after {ds['need_measured']} "
             f"measured episodes): "
             + ("**TRIGGERED** - " + plain(ds["why"]) if ds["triggered"] else "not triggered."))
    for d, e in sorted(ds["domains"].items()):
        L.append(f"  - {d}: {e['measured']} measured episodes (needs "
                 f"{ds['need_measured']}); queue {e['queue']} topics (floor {ds['queue_floor']}); "
                 f"average view duration {_n(e['avd_s'])} s.")
    sm = r["slot_move"]
    L.append(f"- **Slot move rule** (one weekly slot moves when both domains have "
             f"{sm['need_measured']} measured episodes and one leads by "
             f"{_n(sm['need_spread_s'])} s of average view duration): "
             + ("**TRIGGERED** - " if sm["triggered"] else "not triggered - ")
             + f"spread now {_n(sm['spread_s'])} s. {plain(sm['why'])}")
    op = r["opening"]
    L.append(f"- **Opening-line experiment** (payoff in the first 30 seconds; "
             f"decided 28 days after the {op['need']}rd episode under it airs): "
             + ("**TRIGGERED** - " if op["triggered"] else "not triggered - ")
             + f"{op['eligible']} of {op['need']} eligible episodes aired; "
             f"decision date {op['compare_on'] or 'not set yet'}.")
    kills = r["topic_kills"]
    L.append(f"- **Topic kills** (a topic is killed at title gap 0.3 or below, or "
             f"demand under 0.16): {len(kills)} this month.")
    for k in kills:
        L.append(f"  - {k['on']} · {k['slug']}: {k['why']}")
    c = r["cadence"]
    L.append(f"- **Cadence:** {c['per_week']} episodes a week, the owner's decision "
             f"of {c['owner_decision']}; {c['research']}. Not a trigger rule.")
    L.append("")
    fired = triggered(r)
    L.append("**Rules that triggered:** " + ("; ".join(fired) if fired else "none."))
    L.append("")
    return L


def section_advice(f: dict) -> list[str]:
    a = f.get("advice") or {}
    L = ["### What the data suggests (advisory; the rules decide)", ""]
    if a.get("ok"):
        via = ("her Claude subscription" if a.get("route") == "claude-subscription"
               else f"the $0 route ({a.get('model') or 'unknown model'})")
        L += [a["text"], "", f"_Written by the model via {via}._", ""]
    else:
        L += [f"_Named stop {ADVICE_STOP}: {a.get('why') or 'not run'}. No "
              f"paragraph is printed rather than one the model did not write; "
              f"the rules above stand on their own._", ""]
    return L


def section_needs(f: dict) -> list[str]:
    L = ["## 4. What needs you", ""]
    if not f["needs_you"]:
        return L + ["Nothing.", ""]
    for n in f["needs_you"]:
        L.append(f"- **{n['stage']}:** {n['message']}"
                 + (f" To clear it: {n['unblock']}" if n["unblock"] else ""))
    return L + [""]


def sections_without_advice(f: dict) -> str:
    return "\n".join(section_published(f) + section_data(f) + section_rules(f))


def render(f: dict) -> str:
    head = [f"# Monthly email - {month_name(f['month'])} {f['month'][:4]}", ""]
    if f["partial"]:
        head += [f"**Partial month, produced on demand:** {f['from']} to "
                 f"{f['to']} (month to date). The full month is sent on the 1st.",
                 ""]
    return "\n".join(head + section_published(f) + section_data(f)
                     + section_rules(f) + section_advice(f)
                     + section_needs(f)).rstrip() + "\n"


def write(f: dict) -> Path:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    base = OUTDIR / f"{f['month']}-email"
    Path(f"{base}.md").write_text(render(f), encoding="utf-8")
    Path(f"{base}.subject").write_text(subject(f) + "\n", encoding="utf-8")
    write_json(Path(f"{base}.json"), f)
    return Path(f"{base}.md")


def build(today: dt.date, partial: bool, cfg: dict | None = None,
          ask_model: bool = True) -> dict:
    cfg = cfg or config()
    if partial:
        mid = f"{today.year:04d}-{today.month:02d}"
    else:
        mid = prev_month(f"{today.year:04d}-{today.month:02d}")
    f = gather(mid, today, partial, cfg)
    if ask_model:
        f["advice"] = advise.monthly_paragraph(sections_without_advice(f),
                                               triggered(f["rules"]))
    else:
        f["advice"] = {"ok": False, "why": "the model was not asked (--no-model)"}
    return f


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true",
                    help="this month to date, instead of the month just ended")
    ap.add_argument("--no-model", action="store_true")
    a = ap.parse_args(argv)
    with Stage("monthly-email") as st:
        f = build(dt.date.today(), a.now, ask_model=not a.no_model)
        path = write(f)
        adv = f["advice"]
        if adv.get("ok"):
            st.note(f"advisory paragraph via {adv.get('route') or adv.get('model')}")
        else:
            st.note(f"{ADVICE_STOP}: {adv.get('why', '')[:160]}")
        st.work(f"wrote {path.relative_to(ROOT)}: {subject(f)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
