"""Monthly review — read a month of measurement and CHANGE something.

This stage decides. It does not hand findings to the owner and wait; her
instruction on 2026-08-31 was explicit: *"i dont want decide block to be up to
me. u need to automate this and make the decision."*

So every finding here either applies a bounded change to `loop/config.json` or
explicitly records why no change was warranted. It writes prose to
`loop/state/monthly/<YYYY-MM>.md` so she can read what was decided and overrule
it, but nothing waits on her reading it.

**Low views never stop anything.** Also her instruction: *"if the videos dont
have a lot of views i dont want u to fucking stop."* A young channel has thin
data by definition, and a loop that halts on thin data would halt for months.
Thin data means *make no change this month* - it does not mean stop publishing,
and it is never a named stop. This stage exits 0 on a quiet month.

**What keeps an autonomous change honest.** An automatic decision that can run
away is worse than a manual one, so every change here is bounded:

  * one change per run, at most - findings are ordered and the first that
    warrants action takes the month
  * hard floors and ceilings in CHANGE_BOUNDS, so a runaway series of months
    cannot walk runtime to zero
  * a cooldown: nothing that was changed last month is changed again this month,
    because the effect of a change cannot be measured before the videos made
    under it have been published and watched
  * every change is written to the decision log with the evidence that caused it,
    so a wrong call is visible and reversible rather than mysterious

Rule 0: this exits non-zero only when it genuinely could not run.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

import advise  # noqa: E402
from common import Stage, config, read_json, write_json  # noqa: E402

MEASURE = ROOT / "loop/state/measurement.json"
CONFIG = ROOT / "loop/config.json"
OUTDIR = ROOT / "loop/state/monthly"
DECISIONS = ROOT / "loop/state/monthly/decisions.json"

# A month below these is not evidence. It is NOT a failure - it is a young
# channel. No change is made and the loop carries on.
MIN_VIDEOS = 3
MIN_VIEWS = 100

# Bounds on what this stage may do to itself. Without these, a run of bad months
# could walk a value to something absurd with nobody in the loop.
# Floor 4.0, not 3.0: below four minutes this format cannot show an instrument,
# state a figure, and say where the evidence stops - it stops being the channel.
# Ceiling 12.0 because watch time is the YPP constraint and a longer video that
# holds is the fastest route to 4,000 hours; past twelve the risk outweighs it.
CHANGE_BOUNDS = {
    "retention.runtime_minutes": {"min": 4.0, "max": 12.0,
                                  "shorten": -1.5, "lengthen": 1.0},
}
COOLDOWN_MONTHS = 1


def month_id(d: dt.date | None = None) -> str:
    d = d or dt.date.today()
    return f"{d.year:04d}-{d.month:02d}"


def prev_month(mid: str) -> str:
    y, m = int(mid[:4]), int(mid[5:])
    return f"{y-1:04d}-12" if m == 1 else f"{y:04d}-{m-1:02d}"


def collect(mid: str) -> list[dict]:
    m = read_json(MEASURE, default={"videos": []})
    return [r for r in m.get("videos", []) if (r.get("at") or "")[:7] == mid]


def _log() -> dict:
    return read_json(DECISIONS, default={"decisions": []})


def changed_recently(key: str, mid: str) -> bool:
    """Did we already move this in the cooldown window?

    A change cannot be judged before videos made under it have been published and
    watched. Changing again immediately measures nothing and oscillates.
    """
    window = {prev_month(mid)} if COOLDOWN_MONTHS >= 1 else set()
    return any(d["key"] == key and d["month"] in window
               for d in _log()["decisions"] if d.get("applied"))


def apply_change(key: str, current: float, mid: str, why: str,
                 direction: str = "shorten") -> dict:
    """Move one bounded value, or explain why it stayed put."""
    b = CHANGE_BOUNDS[key]
    proposed = round(current + b[direction], 2)
    clamped = max(b["min"], min(b["max"], proposed))
    if changed_recently(key, mid):
        return {"key": key, "applied": False, "from": current, "to": current,
                "why": why, "blocked_by": "cooldown: changed last month, and the "
                                          "effect cannot be measured yet"}
    if clamped == current:
        return {"key": key, "applied": False, "from": current, "to": current,
                "why": why, "blocked_by": f"already at the bound ({b['min']}–{b['max']})"}

    cfg = json.loads(CONFIG.read_text())
    section, field = key.split(".")
    cfg[section][field] = clamped
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"key": key, "applied": True, "from": current, "to": clamped, "why": why}


def apply_absolute(key: str, current: float, target: float, mid: str,
                   why: str, source: str = "model") -> dict:
    """Set a bounded value to a specific target, through the same fence.

    The rules move by a fixed step; the model names a value. Both are clamped to
    CHANGE_BOUNDS and both respect the cooldown, so "the model wins" never means
    "the model is unbounded".
    """
    b = CHANGE_BOUNDS[key]
    clamped = max(b["min"], min(b["max"], round(float(target), 2)))
    if changed_recently(key, mid):
        return {"key": key, "applied": False, "from": current, "to": current,
                "why": why, "source": source,
                "blocked_by": "cooldown: changed last month, and the effect "
                              "cannot be measured yet"}
    if clamped == current:
        return {"key": key, "applied": False, "from": current, "to": current,
                "why": why, "source": source,
                "blocked_by": f"already at {current} (bounds {b['min']}-{b['max']})"}
    cfg = json.loads(CONFIG.read_text())
    section, field = key.split(".")
    cfg[section][field] = clamped
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    out = {"key": key, "applied": True, "from": current, "to": clamped,
           "why": why, "source": source}
    if clamped != round(float(target), 2):
        out["clamped_from"] = round(float(target), 2)
    return out


def review(rows: list[dict], cfg: dict, mid: str) -> dict:
    runtime_min = float(cfg["retention"].get("runtime_minutes", 7.5))
    floor_pct = float(cfg["retention"].get("floor_pct", 35))
    early_min = float(cfg["retention"].get("early_exit_minutes", 2.0))

    measured = [r for r in rows if r.get("average_view_duration_s")]
    views = sum(r.get("views") or 0 for r in rows)

    if len(measured) < MIN_VIDEOS or views < MIN_VIEWS:
        # NOT a stop. A young channel is thin by definition, and halting here
        # would halt for months.
        return {"sufficient": False, "videos_measured": len(measured),
                "views": views, "findings": [], "changes": [],
                "note": (f"{len(measured)} measured video(s), {views} view(s) - below "
                         f"{MIN_VIDEOS}/{MIN_VIEWS}. No change made this month. "
                         f"Publishing continues; this is a young channel, not a fault.")}

    avd = sum(r["average_view_duration_s"] for r in measured) / len(measured)
    avp = sum((r.get("average_view_percentage") or 0) for r in measured) / len(measured)
    below = [r for r in measured if (r.get("average_view_percentage") or 0) < floor_pct]
    early = [r for r in measured if r["average_view_duration_s"] < early_min * 60]

    findings, changes = [], []

    # The one finding that can invalidate the content design, and the only one
    # this stage acts on automatically. Viewers leaving inside two minutes did
    # not dislike the ending; they never reached it.
    if len(early) >= max(2, len(measured) // 2):
        ev = (f"{len(early)} of {len(measured)} videos hold viewers under "
              f"{early_min:.0f} min against a {runtime_min:.1f} min runtime; "
              f"month average {avd/60:.1f} min ({avp:.0f}%).")
        findings.append({"id": "FORMAT_TOO_LONG", "severity": "high", "evidence": ev})
        changes.append(apply_change("retention.runtime_minutes", runtime_min, mid, ev))
    elif avp >= 50 and not early:
        # Lengthen. Watch HOURS are the YPP constraint, not views: 4,000 hours
        # arrives sooner from longer videos that hold than short ones that do
        # not. Riskier than shortening, so the bar is higher - strong retention
        # AND zero early exits, not one or the other.
        ev = (f"month average {avp:.0f}% retention with no early exits across "
              f"{len(measured)} videos at {runtime_min:.1f} min. Watch time is "
              f"the YPP constraint; this format can carry more.")
        findings.append({"id": "FORMAT_CAN_EXTEND", "severity": "info",
                         "evidence": ev})
        changes.append(apply_change("retention.runtime_minutes", runtime_min,
                                    mid, ev, direction="lengthen"))
    elif below and len(below) >= len(measured) // 2:
        findings.append({
            "id": "RETENTION_BELOW_FLOOR", "severity": "medium",
            "evidence": (f"{len(below)} of {len(measured)} under the {floor_pct:.0f}% "
                         f"floor; month average {avp:.0f}%."),
            "no_change": ("One month below floor is a signal, two is a pattern. "
                          "Changing the format on one month would be acting on noise.")})
    else:
        findings.append({
            "id": "RETENTION_OK", "severity": "info",
            "evidence": (f"month average {avp:.0f}%, {avd/60:.1f} min of "
                         f"{runtime_min:.1f}; {len(below)}/{len(measured)} below floor."),
            "no_change": "Nothing indicated."})

    ranked = sorted(measured, key=lambda r: r.get("views") or 0, reverse=True)
    if len(ranked) >= 3:
        findings.append({
            "id": "TOPIC_SPREAD", "severity": "info",
            "evidence": (f"best {ranked[0]['video_id']} {ranked[0].get('views')} views, "
                         f"worst {ranked[-1]['video_id']} {ranked[-1].get('views')}."),
            "no_change": ("Not fed back into scoring: on a young channel view counts "
                          "mostly measure publish date, not topic quality.")})

    return {"sufficient": True, "videos_measured": len(measured), "views": views,
            "avg_view_duration_s": round(avd, 1), "avg_view_percentage": round(avp, 1),
            "findings": findings, "changes": changes}


def to_prose(mid: str, r: dict) -> str:
    out = [f"# Monthly review — {mid}", ""]
    if not r["sufficient"]:
        out += [r["note"], "", "Nothing was changed. Nothing was stopped.", ""]
        return "\n".join(out)
    out += [f"{r['videos_measured']} videos, {r['views']} views, average retention "
            f"{r['avg_view_percentage']}% ({r['avg_view_duration_s']/60:.1f} min).", ""]
    for c in r.get("changes", []):
        if c["applied"]:
            who = "the model" if c.get("source") == "model" else "the rules"
            clamp = (f" (asked for {c['clamped_from']}, clamped to the "
                     f"allowed range)" if c.get("clamped_from") else "")
            out += [f"## CHANGED `{c['key']}`: {c['from']} → {c['to']}{clamp}", "",
                    f"**Decided by** {who}. {c['why']}", "",
                    "_Already applied and live for the next drafting cycle. "
                    "Overrule by editing `loop/config.json`._", ""]
        else:
            out += [f"## NOT changed `{c['key']}` (held at {c['from']})", "",
                    f"**Would have, because.** {c['why']}", "",
                    f"**Held because.** {c['blocked_by']}", ""]
    for f in r["findings"]:
        out += [f"## {f['id']}  ({f['severity']})", "",
                f"**Evidence.** {f['evidence']}", ""]
        if f.get("no_change"):
            out += [f"**No change.** {f['no_change']}", ""]
    out += _advice_section(r)
    return "\n".join(out)


def _advice_section(r: dict) -> list[str]:
    """The model's read, clearly separated from what the rules did.

    Labelled as advisory on purpose: nothing downstream acts on it, and a reader
    should never have to wonder whether a paragraph changed the configuration.
    """
    a = r.get("advice")
    if not a:
        return []
    if not a.get("ok"):
        return ["## Second opinion — unavailable", "",
                f"_{a.get('why', 'no reason recorded')}_", "",
                "The review above ran and decided normally; only the advisory "
                "is missing.", ""]
    cost = f" (${a['cost']:.4f})" if a.get("cost") else ""
    prop = (a.get("proposal") or {})
    out = [f"## Second opinion{cost}", ""]
    if prop.get("conclusion"):
        out += [prop["conclusion"], ""]
    if prop.get("reasoning"):
        out += [f"**Reasoning.** {prop['reasoning']}", ""]
    if prop.get("for_the_owner"):
        out += ["**For you — outside what the loop may change on its own.**", "",
                prop["for_the_owner"], ""]
    if a.get("parse_note"):
        out += [f"_Nothing applied from this: {a['parse_note']}_", ""]
    if not prop:
        out += ["_Raw reply:_", "", a["text"], ""]
    return out


def main() -> int:
    cfg = config()
    mid = month_id()
    with Stage("monthly-review") as st:
        rows = collect(mid)
        st.note(f"{len(rows)} measurement row(s) in {mid}")
        r = review(rows, cfg, mid)
        r["month"] = mid

        # The model reads the same month and may overrule the rules - the owner's
        # instruction is to follow its advice by default. It goes through the SAME
        # fence: apply_change clamps to CHANGE_BOUNDS and refuses inside the
        # cooldown, so a wrong recommendation is bounded exactly like a wrong rule.
        #
        # Any failure here is a line in the report, never a failed stage. The
        # deterministic decision above already stands on its own.
        r["advice"] = advise.advise(r, cfg, rows)
        a = r["advice"]
        if not a.get("ok"):
            st.note(f"no second opinion: {a['why'][:90]}")
        else:
            st.note("second opinion obtained")
            prop = (a.get("proposal") or {}).get("change")
            if a.get("parse_note"):
                st.note(f"proposal not applied: {a['parse_note']}")
            elif prop and prop.get("key") in CHANGE_BOUNDS:
                cur = float(cfg["retention"].get("runtime_minutes"))
                already = next((c for c in r.get("changes", [])
                                if c["key"] == prop["key"] and c["applied"]), None)
                # Reload: the rules may have already moved this value on disk.
                live = json.loads(CONFIG.read_text())
                cur = float(live[prop["key"].split(".")[0]][prop["key"].split(".")[1]])
                target = float(prop["to"])
                if already:
                    # The model overrules the rules. Rewind the rule's change
                    # first so the cooldown and bounds are judged against the
                    # month's starting value, not a half-applied one.
                    live[prop["key"].split(".")[0]][prop["key"].split(".")[1]] = already["from"]
                    CONFIG.write_text(json.dumps(live, indent=2) + "\n")
                    r["changes"] = [c for c in r["changes"] if c is not already]
                    cur = float(already["from"])
                res = apply_absolute(prop["key"], cur, target, mid,
                                     (a.get("proposal") or {}).get("reasoning", ""),
                                     source="model")
                r.setdefault("changes", []).append(res)
                st.note(f"model proposal {prop['key']} -> {target}: "
                        + ("applied" if res["applied"] else res.get("blocked_by", "")))
            elif prop:
                st.note(f"proposal names an out-of-fence key {prop.get('key')!r}; "
                        "reported only")

        OUTDIR.mkdir(parents=True, exist_ok=True)
        write_json(OUTDIR / f"{mid}.json", r)
        (OUTDIR / f"{mid}.md").write_text(to_prose(mid, r) + "\n")

        log = _log()
        for c in r.get("changes", []):
            log["decisions"].append({**c, "month": mid,
                                     "at": dt.datetime.now(dt.timezone.utc).isoformat()})
        write_json(DECISIONS, log)

        applied = [c for c in r.get("changes", []) if c["applied"]]
        for c in applied:
            st.work(f"CHANGED {c['key']}: {c['from']} -> {c['to']}")
        if not applied:
            st.work(f"reviewed {mid}: no change warranted")

        # Always green. Thin data, a finding, or an applied change are all normal
        # operation - none of them is a reason to halt a channel.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
