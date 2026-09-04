"""The monetisation gates — all three of them, and the date one of them moves.

Until now every reference in `loop/`, `docs/` and `RUNBOOK.md` named exactly one
bar: **1,000 subscribers and 4,000 long-form watch hours.** That is the gate
that unlocks ads, and it is not the first gate this channel will reach.

    Expanded  500 subscribers  +  3,000 valid public long-form watch hours
    Expanded  500 subscribers  +  3,000,000 valid public Shorts views / 90 days
    Standard  1,000 subscribers +  4,000 valid public long-form watch hours
    Standard  1,000 subscribers +  3,000,000 valid public Shorts views / 90 days

Expanded YPP unlocks fan funding — memberships, Super Thanks, Shopping — but
not ad revenue. It is materially nearer on both axes (half the subscribers,
three quarters of the hours), so a progress report that shows only the standard
tier shows the owner the wrong distance.

**The Shorts route is a SEPARATE PATH, not a contribution.** Shorts views do not
accumulate into the long-form watch-hour total; YouTube's own eligibility page
lists them as alternative criteria. Modelling them as one number would tell the
owner she is closer than she is. `alternatives` below is a list of paths and the
report names which path each figure belongs to.

**2027-02-01.** The long-form requirement for the standard tier doubles from
4,000 to 8,000 hours on that date. Channels admitted before it stay on the old
bar. That single fact dominates the next six months: every hour banked before
the deadline is worth two after it, which is why the monthly review is given the
deadline rather than a static target.

Nothing here talks to the network. It reads what the measurement lane already
wrote and says how far there is to go.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

MEASURE = ROOT / "loop" / "state" / "measurement.json"
CHANNEL = ROOT / "loop" / "state" / "channel_stats.json"


def _cfg_ypp(cfg: dict) -> dict:
    y = cfg.get("ypp")
    if not y:
        raise KeyError("loop/config.json has no `ypp` block; the monetisation "
                       "gates have no single owner and every stage would keep "
                       "its own copy of them")
    return y


def deadline(cfg: dict) -> dt.date:
    return dt.date.fromisoformat(_cfg_ypp(cfg)["long_form_bar_doubles_on"])


def long_form_hours_required(cfg: dict, tier: dict,
                             on: dt.date | None = None) -> int:
    """The hours bar for a tier, on a given date.

    Only the standard tier's bar moves. Expanded YPP's 3,000 hours is not part
    of the 2027-02-01 change, so this must not double it — doing so would make
    the nearer gate look further away, which is the exact error this module
    exists to stop.
    """
    on = on or dt.date.today()
    after = tier.get("long_form_hours_after_deadline")
    if after and on >= deadline(cfg):
        return int(after)
    return int(tier["long_form_hours"])


def watch_hours(measure: dict | None = None) -> float:
    """Long-form watch hours accumulated, from the measurement lane's own rows.

    `estimatedMinutesWatched` is a long-form metric here: every row comes from a
    published EPISODE in the ledger. Shorts never enter this total.
    """
    m = measure if measure is not None else _read(MEASURE, {"videos": []})
    mins = sum(float(v.get("estimated_minutes_watched") or 0)
               for v in m.get("videos", []))
    return round(mins / 60.0, 2)


def subscribers() -> int | None:
    """Live subscriber count if the measurement lane has fetched one.

    None means unknown, and unknown is reported as unknown. A zero here would
    read as "no progress" and is a different claim entirely.
    """
    s = _read(CHANNEL, {})
    v = s.get("subscribers")
    return int(v) if v is not None else None


def shorts_views_90d() -> int | None:
    s = _read(CHANNEL, {})
    v = s.get("shorts_views_90d")
    return int(v) if v is not None else None


def _read(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return dict(default)


def _pct(have: float, need: float) -> float:
    return round(min(100.0, have / need * 100.0), 1) if need else 0.0


def progress(cfg: dict, on: dt.date | None = None,
             measure: dict | None = None) -> dict:
    """Every gate, nearest first, with the two routes kept apart."""
    on = on or dt.date.today()
    y = _cfg_ypp(cfg)
    hours = watch_hours(measure)
    subs = subscribers()
    sv = shorts_views_90d()
    dl = deadline(cfg)

    out = []
    for tier in y["tiers"]:
        need_h = long_form_hours_required(cfg, tier, on)
        need_s = int(tier["subscribers"])
        routes = [{
            "route": "long-form watch hours",
            "have": hours, "need": need_h, "unit": "hours",
            "pct": _pct(hours, need_h),
            "remaining": round(max(0.0, need_h - hours), 2),
        }]
        sr = y.get("shorts_route")
        if sr:
            routes.append({
                "route": (f"Shorts views in {sr['window_days']} days "
                          f"(SEPARATE PATH — these views do not count toward "
                          f"the long-form hours above)"),
                "have": sv, "need": int(sr["views"]), "unit": "views",
                "pct": _pct(sv, int(sr["views"])) if sv is not None else None,
                "remaining": (max(0, int(sr["views"]) - sv)
                              if sv is not None else None),
            })
        # The gate is subscribers AND one of the routes. Distance is therefore
        # the WORST of (subscribers, best route) - never their average, which
        # would let a strong axis hide a stalled one.
        best_route = max((r["pct"] for r in routes if r["pct"] is not None),
                         default=0.0)
        sub_pct = _pct(subs, need_s) if subs is not None else None
        out.append({
            "tier": tier["id"],
            "name": tier["name"],
            "unlocks": tier["unlocks"],
            "subscribers": {"have": subs, "need": need_s, "pct": sub_pct,
                            "remaining": (max(0, need_s - subs)
                                          if subs is not None else None)},
            "routes": routes,
            "closest_pct": (min(sub_pct, best_route)
                            if sub_pct is not None else None),
            "long_form_hours_required_now": need_h,
            "bar_moves_on": (dl.isoformat()
                             if tier.get("long_form_hours_after_deadline")
                             else None),
        })

    # Nearest gate FIRST. With no subscriber figure the ordering falls back to
    # the tier's own hours bar, which is still the right order.
    out.sort(key=lambda t: (t["closest_pct"] is None,
                            -(t["closest_pct"] or 0),
                            t["long_form_hours_required_now"]))
    days = (dl - on).days
    return {
        "as_of": on.isoformat(),
        "long_form_watch_hours": hours,
        "subscribers": subs,
        "shorts_views_90d": sv,
        "deadline": {
            "date": dl.isoformat(),
            "days_remaining": days,
            "passed": days < 0,
            "before_bar": int(y["tiers"][-1]["long_form_hours"]),
            "after_bar": int(y["tiers"][-1]["long_form_hours_after_deadline"]),
            "meaning": (
                f"The standard tier's long-form requirement doubles from "
                f"{y['tiers'][-1]['long_form_hours']} to "
                f"{y['tiers'][-1]['long_form_hours_after_deadline']} hours on "
                f"{dl.isoformat()}. Channels admitted before that date stay on "
                f"the old bar."
                if days >= 0 else
                f"The deadline passed on {dl.isoformat()}. The standard tier "
                f"now requires "
                f"{y['tiers'][-1]['long_form_hours_after_deadline']} long-form "
                f"hours unless this channel was admitted before it."),
        },
        "gates": out,
    }


def prose(p: dict) -> list[str]:
    """The section the monthly review prints. Nearest gate first, by construction."""
    out = ["## Monetisation gates", "",
           f"**{p['long_form_watch_hours']} long-form watch hours**"
           + (f", **{p['subscribers']} subscribers**."
              if p["subscribers"] is not None
              else ". Subscriber count not yet fetched."),
           ""]
    for g in p["gates"]:
        s = g["subscribers"]
        out.append(f"### {g['name']} — {g['unlocks']}")
        out.append("")
        have = s["have"] if s["have"] is not None else "unknown"
        out.append(f"- Subscribers: {have} / {s['need']}")
        for r in g["routes"]:
            hv = r["have"] if r["have"] is not None else "unknown"
            out.append(f"- {r['route']}: {hv} / {r['need']}")
        if g["bar_moves_on"]:
            out.append(f"- This tier's hours bar moves on {g['bar_moves_on']}.")
        out.append("")
    d = p["deadline"]
    out += [f"**{d['days_remaining']} days to {d['date']}.** {d['meaning']}", ""]
    return out


def main() -> int:
    from common import config                               # noqa: PLC0415
    p = progress(config())
    print("\n".join(prose(p)))
    print(json.dumps(p, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
