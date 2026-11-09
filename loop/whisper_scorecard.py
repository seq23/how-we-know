#!/usr/bin/env python3
"""WHISPER ALMANAC, PER LANE: views, watch hours and subscribers, read from YouTube.

    python loop/whisper_scorecard.py run      # read the channel, write loop/state/whisper_channel.json
    python loop/whisper_scorecard.py report   # the 30-day check per lane, from the last read

Her plan 9 Nov 2026: reach monetisation fastest (1,000 subscribers and 4,000
watch hours). Four lanes (history, neville, money, rotating; config `lanes`).
This step reads the channel's OWN numbers with the @whisperalmanac grant
(auth/whisper_youtube_auth.py; its scopes include yt-analytics.readonly) and
writes them where the weekly mix reads them (loop/whisper_lane.weekly_mix):

  * channel: subscribers, total views, watch hours over the last 365 days;
  * per lane, over the last 30 days: videos public, views, watch hours,
    subscribers gained, watch hours per video;
  * the 30-day check per lane: due 30 days after the lane's first public
    video; before that it reads "too early", never a number.

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

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import whisper_lane as WL                                   # noqa: E402

STAGE = "whisper-scorecard"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA = "https://www.googleapis.com/youtube/v3"
LANES = ("history", "neville", "money", "rotating")
WINDOW = 30


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
            out[ln] = {"videos_30d": 0, "views_30d": None, "watch_hours_30d": None,
                       "subscribers_30d": None, "watch_hours_per_video": None,
                       "first_public": None, "check_30d_due": None}
            continue
        rows = [per_video.get(v, {}) for v, _ in vids]
        hours = sum(float(r.get("estimatedMinutesWatched") or 0) for r in rows) / 60
        first = min(t for _, t in vids)
        out[ln] = {"videos_30d": len(vids),
                   "views_30d": int(sum(float(r.get("views") or 0) for r in rows)),
                   "watch_hours_30d": round(hours, 2),
                   "subscribers_30d": int(sum(float(r.get("subscribersGained") or 0) for r in rows)),
                   "watch_hours_per_video": round(hours / len(vids), 2),
                   "first_public": first.strftime("%Y-%m-%d"),
                   "check_30d_due": (first + _dt.timedelta(days=WINDOW)).strftime("%Y-%m-%d")}
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
    stats = (_get(DATA, token, part="statistics", mine="true").get("items") or [{}])[0].get("statistics", {})
    subs = int(stats["subscriberCount"]) if "subscriberCount" in stats else None
    views = int(stats["viewCount"]) if "viewCount" in stats else None
    firsts = [t for vids in lanes.values() for _, t in vids]
    return {"first_upload_at": min(firsts).strftime("%Y-%m-%dT%H:%M:%SZ") if firsts else None,
            "views": views, "subscribers": subs,
            "subs_per_1000_views": round(subs / views * 1000, 2) if subs is not None and views else None,
            "watch_hours_365d": round(float(year[0].get("estimatedMinutesWatched") or 0) / 60, 1) if year else 0.0,
            "lanes": summarise(per_video, lanes, now),
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}


def report_lines(nums: dict, c: dict, now: _dt.datetime | None = None) -> list[str]:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    mix, why = WL.weekly_mix(c, nums)
    out = [f"read {nums.get('at') or 'never'}: {WL._or_unread(nums.get('subscribers'))} subscribers, "
           f"{WL._or_unread(nums.get('watch_hours_365d'))} watch hours in 365 days (YPP: 1,000 and 4,000)"]
    for ln in LANES:
        v = (nums.get("lanes") or {}).get(ln) or {}
        due = v.get("check_30d_due")
        state = ("no public video yet" if not v.get("videos_30d") else
                 f"30-day check due {due}" if due and due > now.strftime("%Y-%m-%d") else "30-day check: read")
        out.append(f"{ln:9} {v.get('videos_30d') or 0} videos · views {WL._or_unread(v.get('views_30d'))} · "
                   f"watch hours {WL._or_unread(v.get('watch_hours_30d'))} · subscribers "
                   f"{WL._or_unread(v.get('subscribers_30d'))} · {state} · {mix.get(ln, 0)} a week")
    return out + [f"mix: {w}" for w in why]


def run(now: _dt.datetime | None = None, token: str | None = None) -> int:
    import common as C                                      # noqa: PLC0415
    import whisper_upload as U                              # noqa: PLC0415
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
        new = {"_why": old.get("_why", ""), **{k: old.get(k) for k in old if k.startswith("median")}, **got}
        WL.CHANNEL_STATE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
        st.work(f"read the channel: {sum((v.get('videos_30d') or 0) for v in got['lanes'].values())} public videos")
        for ln in report_lines(new, c, now):
            print(f"  {ln}")
    print("OUTPUT whisper scorecard written")
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
