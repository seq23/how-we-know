"""Is this working? The measurement history, and the one verdict read from it.

WHY THIS EXISTS (audit, 2026-10-12). The Friday lane kept ONE row per video in
loop/state/measurement.json, replaced every week, and ONE subscriber snapshot
in channel_stats.json. Nothing remembered last week, so no trend could be
computed and the weekly digest could not answer the only question the owner
asks of it. It also measured long-form only, while Shorts carry most of the
channel's views.

Two things live here, both written by the Friday measure lane
(loop/measure.py), both read by the Sunday digest (loop/digest.py):

  * HISTORY - loop/state/measurement_history.jsonl. One row per video per
    ISO week (long-form AND Shorts, lifetime figures as of that Friday), plus
    one `channel` row per week with the trailing 28-day totals split by
    content type and traffic source. A re-run in the same week replaces that
    week's rows instead of duplicating them; rows older than HISTORY_DAYS are
    dropped, so the file is bounded. measurement.json stays the latest view
    for every existing reader.
  * VERDICT - loop/state/channel_verdict.json. Five numbers with the floor
    beside each: 28-day views split long-form vs Shorts, median views per
    long-form video, long-form average view duration against the retention
    floor, net subscribers in 28 days, watch hours against the Expanded YPP
    bar. No kill or pivot action is taken on them - they are the answer to
    "is this working", in one glance, every Sunday.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path

from common import LOOP, _dry_run_refuses, write_json

HISTORY = LOOP / "state" / "measurement_history.jsonl"
VERDICT = LOOP / "state" / "channel_verdict.json"
HISTORY_DAYS = 730          # two years of weekly rows, then the oldest go
WINDOW_DAYS = 28
SHORTS_TYPE = "shorts"      # creatorContentType value for a Short
# Views YouTube cannot attribute to a content type (live channel, 2026-10-12:
# "creatorContentTypeUnspecified"). Reported on their own, never folded into
# long-form, where they would flatter the AVD and the long-form total.
UNSPECIFIED = "creatorContentTypeUnspecified"


def _is_long(t: str) -> bool:
    return t not in (SHORTS_TYPE, UNSPECIFIED)


# ------------------------------------------------------------ the history

def _key(r: dict) -> tuple:
    return (r.get("kind"), r.get("video_id") or "", r.get("week"))


def load_history(path: Path | None = None) -> list[dict]:
    p = path or HISTORY
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def append_history(rows: list[dict], path: Path | None = None,
                   today: dt.date | None = None) -> int:
    """Add this week's rows. Same (kind, video, week) replaces; old rows go.

    Returns the number of rows on file afterwards. Each row must carry
    `kind`, `week` and `date`; `video_id` for a video row.
    """
    p = path or HISTORY
    if not rows:
        return len(load_history(p))
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    new_keys = {_key(r) for r in rows}
    kept = [r for r in load_history(p)
            if _key(r) not in new_keys and (r.get("date") or "") >= cutoff]
    allrows = sorted(kept + list(rows),
                     key=lambda r: (r.get("date") or "", r.get("kind") or "",
                                    r.get("video_id") or ""))
    if _dry_run_refuses(p):
        return len(allrows)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n"
                           for r in allrows), encoding="utf-8")
    tmp.replace(p)
    return len(allrows)


def _latest_per_video(rows: list[dict], kind: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") != kind or not r.get("video_id"):
            continue
        cur = out.get(r["video_id"])
        if cur is None or (r.get("date") or "") >= (cur.get("date") or ""):
            out[r["video_id"]] = r
    return out


def _snapshot_on_or_before(rows: list[dict], kind: str, day: str) -> dict[str, dict]:
    return _latest_per_video([r for r in rows if (r.get("date") or "") <= day],
                             kind)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------ the verdict

def _tier(cfg: dict, tier_id: str = "expanded") -> dict:
    for t in (cfg.get("ypp") or {}).get("tiers", []):
        if t.get("id") == tier_id:
            return t
    return {"subscribers": 500, "long_form_hours": 3000}


def compute(rows: list[dict], cfg: dict, today: dt.date | None = None) -> dict:
    """The channel verdict from history rows. Never raises; unknown is None."""
    today = today or dt.date.today()
    floor_avd = float((cfg.get("retention") or {}).get("floor_avd_seconds", 146))
    tier = _tier(cfg)
    need_h = float(tier.get("long_form_hours", 3000))
    need_subs = int(tier.get("subscribers", 500))

    chan = [r for r in rows if r.get("kind") == "channel"]
    chan = max(chan, key=lambda r: r.get("date") or "") if chan else None
    longs = _latest_per_video(rows, "long")
    shorts = _latest_per_video(rows, "short")
    dates = sorted({r.get("date") for r in rows if r.get("date")})
    as_of = dates[-1] if dates else None

    # 28-day views. The channel row (28-day report by creatorContentType) is
    # the direct figure; without it, the difference between this week's
    # lifetime snapshot and the one 28+ days earlier.
    views = {"long_form": None, "shorts": None, "basis": None}
    lf_minutes_28 = lf_views_28 = None
    subs_28 = None
    if chan and chan.get("by_type"):
        bt = chan["by_type"]
        views["shorts"] = int(_num((bt.get(SHORTS_TYPE) or {}).get("views")))
        views["long_form"] = int(sum(_num(v.get("views")) for k, v in bt.items()
                                     if _is_long(k)))
        views["unattributed"] = int(_num((bt.get(UNSPECIFIED) or {}).get("views")))
        lf_views_28 = views["long_form"]
        lf_minutes_28 = sum(_num(v.get("minutes")) for k, v in bt.items()
                            if _is_long(k))
        subs_28 = int(sum(_num(v.get("subscribers_gained"))
                          - _num(v.get("subscribers_lost")) for v in bt.values()))
        views["basis"] = f"YouTube Analytics 28-day report, {chan.get('date')}"
    elif as_of:
        back = (dt.date.fromisoformat(as_of)
                - dt.timedelta(days=WINDOW_DAYS)).isoformat()
        old_l = _snapshot_on_or_before(rows, "long", back)
        old_s = _snapshot_on_or_before(rows, "short", back)
        if old_l or old_s:
            views["long_form"] = int(sum(_num(r.get("views")) for r in longs.values())
                                     - sum(_num(r.get("views")) for r in old_l.values()))
            views["shorts"] = int(sum(_num(r.get("views")) for r in shorts.values())
                                  - sum(_num(r.get("views")) for r in old_s.values()))
            lf_views_28 = views["long_form"]
            lf_minutes_28 = (sum(_num(r.get("estimated_minutes_watched"))
                                 for r in longs.values())
                             - sum(_num(r.get("estimated_minutes_watched"))
                                   for r in old_l.values()))
            views["basis"] = f"lifetime snapshots {back} -> {as_of}"
        else:
            views["basis"] = (f"not yet computable: history has no snapshot "
                              f"{WINDOW_DAYS} days before {as_of}")
    total = ((views["long_form"] or 0) + (views["shorts"] or 0)
             + (views.get("unattributed") or 0))
    views["total"] = total if views["long_form"] is not None else None
    views["shorts_share_pct"] = (round(views["shorts"] / total * 100, 1)
                                 if total and views["shorts"] is not None else None)

    lf_views = [int(_num(r.get("views"))) for r in longs.values()]
    median_long = statistics.median(lf_views) if lf_views else None
    sh_views = [int(_num(r.get("views"))) for r in shorts.values()]
    median_short = statistics.median(sh_views) if sh_views else None

    if lf_views_28:
        avd = round(lf_minutes_28 * 60 / lf_views_28, 1)
        avd_basis = "long-form, trailing 28 days"
    else:
        lv = sum(_num(r.get("views")) for r in longs.values())
        lm = sum(_num(r.get("estimated_minutes_watched")) for r in longs.values())
        avd = round(lm * 60 / lv, 1) if lv else None
        avd_basis = "long-form, lifetime (no 28-day figure yet)"

    hours = round(sum(_num(r.get("estimated_minutes_watched"))
                      for r in longs.values()) / 60.0, 1)
    pace = round(lf_minutes_28 / 60.0, 1) if lf_minutes_28 is not None else None
    weeks_to_bar = (round((need_h - hours) / (pace / 4.0), 0)
                    if pace and pace > 0 and hours < need_h else None)

    imp = (chan or {}).get("impressions") or {}
    return {
        "as_of": as_of,
        "computed": today.isoformat(),
        "views_28d": views,
        "median_views_per_long_form_video": median_long,
        "long_form_videos_measured": len(lf_views),
        "median_views_per_short": median_short,
        "shorts_measured": len(sh_views),
        "avd_s": avd, "avd_basis": avd_basis, "avd_floor_s": floor_avd,
        "avd_vs_floor": (None if avd is None else
                         "above" if avd >= floor_avd else "below"),
        "subscribers_28d_net": subs_28,
        "subscribers_total": (chan or {}).get("subscribers_total"),
        "subscribers_floor": need_subs,
        "watch_hours_long_form": hours,
        "watch_hours_floor": need_h,
        "watch_hours_pct": round(min(100.0, hours / need_h * 100), 1) if need_h else None,
        "watch_hours_28d": pace,
        "weeks_to_watch_hour_floor_at_28d_pace": weeks_to_bar,
        "impressions": imp,
    }


# ------------------------------------------------------------ Shorts cadence

def _aired(entry: dict) -> dt.datetime | None:
    w = entry.get("published_at") or entry.get("scheduled_publish_at")
    if not w:
        return None
    try:
        d = dt.datetime.fromisoformat(w.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def shorts_cadence(published: list[dict], per_week: int, now: dt.datetime,
                   r2_unpublished: int | None = None,
                   r2_basis: str | None = None,
                   r2_as_of: str | None = None) -> dict:
    """Shorts aired in the trailing 7 days and the 7 before, against target,
    and how many weeks the verified-but-unpublished shelf covers.

    WHY (owner, 2026-10-12: "why did the Shorts lane emails never tell me").
    Shorts fell from 14 a week to 1 while the digest counted long-form slots
    and filed three weeks of NO_SHORTS_SHELVED under self-resolving stops.
    Shorts carry most of the channel's views; their cadence is now a number
    in the verdict and a colour in the subject (digest.shorts_flag).

    `published` is loop/state/shorts_ledger.json's rows. A Short scheduled
    for a future time is uploaded, verified and waiting: it counts toward the
    shelf, as do verified cuts on the R2 shelf not yet uploaded
    (`r2_unpublished`, read by the Friday measure lane; None = not read).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    live = [x for x in published if not x.get("retired_at")]
    times = [t for t in (_aired(x) for x in live) if t is not None]
    wk = dt.timedelta(days=7)
    last7 = sum(1 for t in times if now - wk < t <= now)
    prev7 = sum(1 for t in times if now - 2 * wk < t <= now - wk)
    ahead = sum(1 for t in times if t > now)
    shelf = ahead + (r2_unpublished or 0)
    return {
        "as_of": now.isoformat(timespec="seconds"),
        "target_per_week": per_week,
        "published_7d": last7,
        "published_prev_7d": prev7,
        "scheduled_ahead": ahead,
        "r2_verified_unpublished": r2_unpublished,
        "r2_basis": r2_basis,
        # When the R2 count was TAKEN - not as_of, which is when the cadence
        # was computed. The W42 digest mailed a 15:54 count at 16:44 as if
        # current; the page now prints this beside the number.
        "r2_as_of": r2_as_of if r2_as_of is not None else (
            now.isoformat(timespec="seconds") if r2_unpublished is not None
            else None),
        "shelf": shelf,
        "shelf_weeks": round(shelf / per_week, 1) if per_week else None,
    }


def write(rows: list[dict] | None, cfg: dict, today: dt.date | None = None,
          shorts: dict | None = None) -> dict:
    v = compute(load_history() if rows is None else rows, cfg, today)
    if shorts is not None:
        v["shorts_cadence"] = shorts
    else:
        prev = read() or {}
        if prev.get("shorts_cadence"):
            v["shorts_cadence"] = prev["shorts_cadence"]
    write_json(VERDICT, v)
    return v


def _n(v) -> str:
    return "unknown" if v is None else f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def _hhmm(iso: str | None) -> str:
    """'2026-10-12T15:54:16+00:00' -> '2026-10-12 15:54 UTC'; 'unknown time'."""
    if not iso:
        return "unknown time"
    d = _aired({"scheduled_publish_at": iso})
    return (d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if d else str(iso)[:16])


def digest_block(v: dict | None) -> list[str]:
    """Seven lines, each number with its floor beside it. Markdown lines."""
    sc = (v or {}).get("shorts_cadence") or {}
    if sc:
        r2 = sc.get("r2_verified_unpublished")
        shorts_line = (
            f"- **Shorts:** {sc.get('published_7d')} published in 7 days vs "
            f"{sc.get('target_per_week')}/week target "
            f"({sc.get('published_prev_7d')} the week before) - "
            f"{(('UNDER' if sc.get('published_7d', 0) < sc.get('target_per_week', 0) else 'ON'))}"
            f" target; shelf {sc.get('shelf')} verified unpublished = "
            f"{sc.get('shelf_weeks')} week(s) ({sc.get('scheduled_ahead')} "
            f"scheduled on YouTube, "
            + (f"{r2} on R2 at {_hhmm(sc.get('r2_as_of'))})"
               if r2 is not None else
               f"R2 not read: {(sc.get('r2_basis') or 'unknown')[:60]})"))
    else:
        shorts_line = "- **Shorts:** cadence not measured yet"
    if not v or not v.get("as_of"):
        return ["## Is this working?", "",
                "No measurement history yet - the Friday measure lane writes "
                "loop/state/channel_verdict.json after its first run with "
                "credentials.", "", shorts_line, ""]
    w = v.get("views_28d") or {}
    avd = v.get("avd_s")
    avd_txt = ("unknown" if avd is None else
               f"{int(avd) // 60}m{int(avd) % 60:02d}s ({avd:.0f} s)")
    imp = v.get("impressions") or {}
    if imp.get("unavailable"):
        imp_line = (f"- **Impressions / CTR:** not exposed to this channel by "
                    f"the YouTube Analytics API ({imp['unavailable'][:90]})")
    elif imp.get("impressions") is not None:
        imp_line = (f"- **Impressions / CTR (long-form, 28 d):** "
                    f"{_n(imp.get('impressions'))} at {imp.get('ctr_pct')}%")
    else:
        imp_line = "- **Impressions / CTR:** not measured yet"
    weeks = v.get("weeks_to_watch_hour_floor_at_28d_pace")
    return [
        f"## Is this working? (measured {v['as_of']})", "",
        f"- **28-day views:** {_n(w.get('total'))} - long-form "
        f"{_n(w.get('long_form'))} · Shorts {_n(w.get('shorts'))}"
        + (f" · unattributed {_n(w['unattributed'])}" if w.get("unattributed") else "")
        + f" ({_n(w.get('shorts_share_pct'))}% Shorts)",
        f"- **Median views per long-form video:** "
        f"{_n(v.get('median_views_per_long_form_video'))} across "
        f"{v.get('long_form_videos_measured', 0)} video(s); per Short "
        f"{_n(v.get('median_views_per_short'))} across "
        f"{v.get('shorts_measured', 0)}",
        f"- **Average view duration:** {avd_txt} vs the "
        f"{v.get('avd_floor_s', 146):.0f} s floor - "
        f"{(v.get('avd_vs_floor') or 'unknown').upper()} ({v.get('avd_basis')})",
        f"- **Subscribers:** {'+' if (v.get('subscribers_28d_net') or 0) >= 0 else ''}"
        f"{_n(v.get('subscribers_28d_net'))} in 28 days; "
        f"{_n(v.get('subscribers_total'))} of the "
        f"{_n(v.get('subscribers_floor'))} Expanded YPP needs",
        f"- **Watch hours (long-form):** {v.get('watch_hours_long_form')} of "
        f"{_n(v.get('watch_hours_floor'))} ({v.get('watch_hours_pct')}%); "
        f"{_n(v.get('watch_hours_28d'))} h in 28 days"
        + (f", ~{weeks:.0f} weeks to the bar at that pace" if weeks else ""),
        shorts_line,
        imp_line,
        "",
    ]


def read() -> dict | None:
    try:
        return json.loads(VERDICT.read_text())
    except (OSError, ValueError):
        return None
