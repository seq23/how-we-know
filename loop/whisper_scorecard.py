#!/usr/bin/env python3
"""WHISPER ALMANAC, PER LANE: views, watch hours and subscribers, read from YouTube.

    python loop/whisper_scorecard.py run      # read the channel, write loop/state/whisper_channel.json
    python loop/whisper_scorecard.py report   # the lanes, this week's mix and the click rates, from the last read

Her plan 9 Nov 2026: reach monetisation fastest (1,000 subscribers and 4,000
watch hours). Four lanes (history, neville, money, rotating; config `lanes`).
This step reads the channel's OWN numbers with the @whisperalmanac grant
(auth/whisper_youtube_auth.py; its scopes include yt-analytics.readonly) and
writes them where the weekly mix reads them (loop/whisper_lane.weekly_mix):

  * channel: subscribers, total views, watch hours over the last 365 days;
  * per lane, over the last 28 days: videos public, views, watch hours,
    subscribers gained, watch hours per video;
  * THE WEEKLY RE-WEIGHTING (her yes 11 Nov 2026, replacing the single 30-day
    check): at the first read on or after each Monday (Central), from 14 days
    after the first public upload, the lane with the most watch hours per
    video gets the next week's spare nights (decide; loop/whisper_lane.reweight);
  * THE 48-HOUR CLICK-RATE CHECK (same yes): a video public 48+ hours whose
    thumbnail click rate is under 4% on 100+ impressions gets ONE line in her
    morning email's Notices - swap the thumbnail in Test & Compare
    (click_rates, click_notices). Impressions come from the YouTube Reporting
    API (loop/reach.py's report); the Analytics API does not serve them.

Nothing here is ever estimated: a number YouTube did not return is null and
reads "not read". Runs on the Mac in the nightly batch, right after the
upload step (bin/batch-session.sh phase_whisper_upload): no new job.
Under LOOP_DRY_RUN the grant is refused (WHISPER_ANALYTICS_NOT_READ, a note).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import whisper_lane as WL                                   # noqa: E402

STAGE = "whisper-scorecard"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA = "https://www.googleapis.com/youtube/v3"
LANES = ("food", "ocean", "neville", "money", "rotating")   # her decision 9 Nov 2026
WINDOW = 28                        # config mix.reweight.window_days
CT = ZoneInfo("America/Chicago")


def _get(url: str, token: str, **q) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(q)}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _rows(d: dict) -> list[dict]:
    cols = [h["name"] for h in d.get("columnHeaders", [])]
    return [dict(zip(cols, r)) for r in d.get("rows") or []]


def _public(k: dict, now: _dt.datetime) -> _dt.datetime | None:
    t = k.get("scheduled_publish_at") or k.get("uploaded_at")
    if not (k.get("video_id") and t):
        return None
    t = _dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    return t if t <= now else None


def lane_videos(now: _dt.datetime, c: dict) -> dict[str, list[tuple[str, _dt.datetime]]]:
    out: dict[str, list] = {ln: [] for ln in LANES}
    for f in WL.all_scripts():
        k = WL.KITS / f.stem / "kit.json"
        if not k.exists():
            continue
        kit = json.loads(k.read_text())
        when = _public(kit, now)
        if when:
            out[kit.get("lane") or WL.lane_of(WL.parse(f), c)].append((kit["video_id"], when))
    return out


def summarise(per_video: dict[str, dict], lanes: dict[str, list], now: _dt.datetime) -> dict:
    """Lane totals from per-video rows. A lane with no public video is all
    nulls; a video YouTube returned no row for counts as zero views only
    because YouTube reports no row for a video nobody watched."""
    out = {}
    for ln, vids in lanes.items():
        if not vids:
            out[ln] = {"videos_28d": 0, "views_28d": None, "watch_hours_28d": None,
                       "subscribers_28d": None, "watch_hours_per_video": None,
                       "first_public": None}
            continue
        rows = [per_video.get(v, {}) for v, _ in vids]
        hours = sum(float(r.get("estimatedMinutesWatched") or 0) for r in rows) / 60
        first = min(t for _, t in vids)
        out[ln] = {"videos_28d": len(vids),
                   "views_28d": int(sum(float(r.get("views") or 0) for r in rows)),
                   "watch_hours_28d": round(hours, 2),
                   "subscribers_28d": int(sum(float(r.get("subscribersGained") or 0) for r in rows)),
                   "watch_hours_per_video": round(hours / len(vids), 2),
                   "first_public": first.strftime("%Y-%m-%d")}
    return out


def read(token: str, now: _dt.datetime, c: dict) -> dict:
    lanes = lane_videos(now, c)
    ids = [v for vids in lanes.values() for v, _ in vids]
    end = now.strftime("%Y-%m-%d")
    per_video: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        d = _get(ANALYTICS, token, ids="channel==MINE", startDate=(now - _dt.timedelta(days=WINDOW)).strftime("%Y-%m-%d"),
                 endDate=end, metrics="views,estimatedMinutesWatched,subscribersGained",
                 dimensions="video", filters="video==" + ",".join(ids[i:i + 50]))
        per_video.update({r["video"]: r for r in _rows(d)})
    year = _rows(_get(ANALYTICS, token, ids="channel==MINE",
                      startDate=(now - _dt.timedelta(days=365)).strftime("%Y-%m-%d"), endDate=end,
                      metrics="views,estimatedMinutesWatched"))
    stats = (_get(f"{DATA}/channels", token, part="statistics", mine="true").get("items") or [{}])[0].get("statistics", {})
    subs = int(stats["subscriberCount"]) if "subscriberCount" in stats else None
    views = int(stats["viewCount"]) if "viewCount" in stats else None
    firsts = [t for vids in lanes.values() for _, t in vids]
    return {"first_upload_at": min(firsts).strftime("%Y-%m-%dT%H:%M:%SZ") if firsts else None,
            "views": views, "subscribers": subs,
            "subs_per_1000_views": round(subs / views * 1000, 2) if subs is not None and views else None,
            "watch_hours_365d": round(float(year[0].get("estimatedMinutesWatched") or 0) / 60, 1) if year else 0.0,
            "lanes": summarise(per_video, lanes, now),
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}


def decide(nums: dict, c: dict, now: _dt.datetime) -> str:
    """The Monday re-weighting, once per week (weeks start Monday, Central):
    written into nums["reweight"] at the first read on or after Monday, from
    week 3 after the first public upload. Returns the line that says what
    happened; a week with no measured lane is decided at the next read."""
    today = now.astimezone(CT).date()
    week = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    start = WL.reweight_from(nums, c)
    if start is None or today < start:
        return ("re-weighting: not yet - the planned mix stands until "
                + (f"{start:%a %d %b %Y} (14 days of numbers)" if start else "14 days after the first public upload"))
    if (nums.get("reweight") or {}).get("week") == week:
        return f"re-weighting: week {week} already decided on {nums['reweight']['decided_on']}"
    base = WL.base_mix(c, nums)
    got = WL.reweight(base, nums.get("lanes") or {}, c)
    if got is None:
        return f"re-weighting: week {week} NOT decided - no lane has a measured video yet; the next read tries again"
    mix, why = got
    nums["reweight"] = {"week": week, "decided_on": today.isoformat(), "base": base, "mix": mix, "why": why}
    return f"re-weighting: week {week} decided - {why}: " + ", ".join(f"{k} {v}" for k, v in mix.items() if v)


def click_rates(api, state: dict) -> dict[str, dict]:
    """video id -> {impressions, ctr_pct} over every day YouTube has reported
    (the Reporting API's channel_reach_basic_a1; its job is created on the
    first run and the first reports arrive up to 48 hours later). `state`
    caches each report's per-video sums so no report is downloaded twice."""
    import csv                                              # noqa: PLC0415
    import io                                               # noqa: PLC0415
    import reach as RE                                      # noqa: PLC0415
    jobs = [j for j in api.jobs() if j.get("reportTypeId") == RE.REPORT_TYPE]
    job = jobs[0] if jobs else api.create()
    state["job_id"] = job["id"]
    cache = state.setdefault("reports", {})
    for r in sorted(api.reports(job["id"]), key=lambda r: (r["createTime"], r["id"])):
        if r["id"] in cache:
            continue
        per: dict[str, list] = {}
        for row in csv.DictReader(io.StringIO(api.download(r["downloadUrl"]))):
            n, pct = int(row["video_thumbnail_impressions"]), float(row["video_thumbnail_impressions_ctr"])
            agg = per.setdefault(row["video_id"], [0, 0.0])
            agg[0] += n
            agg[1] += n * pct
        cache[r["id"]] = {"start": r["startTime"], "end": r["endTime"], "created": r["createTime"], "videos": per}
    latest: dict[tuple, tuple] = {}        # a reissued report replaces its interval
    for rid, r in cache.items():
        key = (r["start"], r["end"])
        if key not in latest or (r["created"], rid) > latest[key][0]:
            latest[key] = ((r["created"], rid), r)
    out: dict[str, list] = {}
    for _, r in latest.values():
        for vid, (n, w) in r["videos"].items():
            agg = out.setdefault(vid, [0, 0.0])
            agg[0] += n
            agg[1] += w
    return {vid: {"impressions": n, "ctr_pct": round(w / n, 2)} for vid, (n, w) in out.items() if n}


def click_notices(nums: dict, rates: dict[str, dict], kits: dict[str, dict], c: dict,
                  now: _dt.datetime) -> list[str]:
    """One line per video, once ever: public `after_hours`+, at least
    `min_impressions`, click rate under `floor_pct`. A video with no reported
    impressions is not judged (never read as 0%)."""
    cr = c["click_rate"]
    told = nums.setdefault("click_rate", {}).setdefault("noticed", {})
    lines = []
    for slug, k in sorted(kits.items()):
        when, vid = _public(k, now), k.get("video_id")
        r = rates.get(vid)
        if (not when or vid in told or r is None or (now - when).total_seconds() < cr["after_hours"] * 3600
                or r["impressions"] < cr["min_impressions"] or r["ctr_pct"] >= cr["floor_pct"]):
            continue
        told[vid] = now.strftime("%Y-%m-%d")
        lines.append(f"Whisper Almanac: \"{k.get('title')}\" has a {r['ctr_pct']:.1f}% click rate after "
                     f"{(now - when).days} days ({r['impressions']} impressions; the bar is "
                     f"{cr['floor_pct']}%). Swap the thumbnail in YouTube Studio's Test & Compare.")
    return lines


def report_lines(nums: dict, c: dict, now: _dt.datetime | None = None) -> list[str]:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    mix, why = WL.weekly_mix(c, nums)
    out = [f"read {nums.get('at') or 'never'}: {WL._or_unread(nums.get('subscribers'))} subscribers, "
           f"{WL._or_unread(nums.get('watch_hours_365d'))} watch hours in 365 days (YPP: 1,000 and 4,000)"]
    for ln in LANES:
        v = (nums.get("lanes") or {}).get(ln) or {}
        out.append(f"{ln:9} {v.get('videos_28d') or 0} videos · views {WL._or_unread(v.get('views_28d'))} · "
                   f"watch hours {WL._or_unread(v.get('watch_hours_28d'))} · subscribers "
                   f"{WL._or_unread(v.get('subscribers_28d'))} · "
                   f"{'no public video yet' if not v.get('videos_28d') else 'last 28 days'} · {mix.get(ln, 0)} a week")
    cr = nums.get("click_rate") or {}
    out.append("click rate: " + (f"not read ({cr['not_read']})" if cr.get("not_read") else
                                 f"{len(cr.get('videos') or {})} video(s) with reported impressions, "
                                 f"{len(cr.get('noticed') or {})} told to swap a thumbnail so far"))
    return out + [f"mix: {w}" for w in why]


def run(now: _dt.datetime | None = None, token: str | None = None, reach=None, notify=None) -> int:
    import common as C                                      # noqa: PLC0415
    import whisper_upload as U                              # noqa: PLC0415
    notify = notify or U.morning_line
    c = WL.cfg()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    with C.Stage(STAGE, zero_work_hint="the channel's numbers were not read") as st:
        if token is None:
            creds = U.credentials(c)
            if creds is None:
                st.named_stop("WHISPER_ANALYTICS_NOT_READ",
                              "no usable @whisperalmanac grant"
                              + (" (LOOP_DRY_RUN refuses it)" if U.dry_run() else "")
                              + "; the lane numbers stay as last read",
                              unblock="Nothing to do: the next nightly batch reads them.")
            try:
                token = U.YouTube(creds).token
            except Exception as e:                          # noqa: BLE001
                st.named_stop("WHISPER_ANALYTICS_NOT_READ", f"Google refused the sign-in: {str(e)[:160]}",
                              unblock="Nothing to do: the next nightly batch reads them.")
        try:
            got = read(token, now, c)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            st.named_stop("WHISPER_ANALYTICS_NOT_READ", f"YouTube Analytics did not answer: {str(e)[:160]}",
                          unblock="Nothing to do: the next nightly batch reads them.")
        old = WL.channel_numbers()
        new = {"_why": old.get("_why", ""),
               **{k: old.get(k) for k in old if k.startswith("median") or k in ("reweight", "click_rate")},
               **got}
        st.work(f"read the channel: {sum((v.get('videos_28d') or 0) for v in got['lanes'].values())} public videos")
        st.note(decide(new, c, now))
        # the 48-hour click-rate check: never fails the read above
        cr = new.setdefault("click_rate", {})
        told = 0
        try:
            import reach as RE                              # noqa: PLC0415
            rates = click_rates(reach or RE.Reporting(token), cr)
            cr["videos"], cr["at"] = rates, got["at"]
            cr.pop("not_read", None)
            for line in click_notices(new, rates, U.kits(), c, now):
                told += 1
                st.work(f"click rate under the bar: {notify(line)} - {line}")
        except Exception as e:                              # noqa: BLE001
            cr["not_read"] = f"{type(e).__name__}: {str(e)[:140]}"
        WL.CHANNEL_STATE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
        for ln in report_lines(new, c, now):
            print(f"  {ln}")
        if cr.get("not_read"):
            st.named_stop("WHISPER_ANALYTICS_NOT_READ",
                          f"the lane numbers were read and written, but the click rates were not "
                          f"({cr['not_read']}); no video was judged on a missing number",
                          unblock="Nothing to do: the next nightly batch reads them.")
    print(f"OUTPUT whisper scorecard written: {len(cr.get('videos') or {})} video(s) with a click rate read, "
          f"{told} told to swap a thumbnail tonight")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["run"]:
        return run()
    if argv[:1] == ["report"]:
        for ln in report_lines(WL.channel_numbers(), WL.cfg()):
            print(ln)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
