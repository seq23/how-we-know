"""Friday 17:00 — pull retention and RPM, write measurement, feed Sunday.

This stage closes the loop. It is also the stage that can *trip the circuit
breaker on its own*: three consecutive videos below the retention floor is one
of the three named trip causes, and it is the only one a machine can notice
before a human does.

Two APIs, both behind the same missing OAuth:
  * YouTube Analytics  — averageViewPercentage, estimatedRevenue (RPM)
  * YouTube Data       — the strike / status check

Without credentials this takes a NAMED STOP, having first done its real work:
recomputing the retention streak from the measurement history already on disk,
so the breaker logic is exercised every week rather than only after OAuth
lands.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import breaker  # noqa: E402
import ledger  # noqa: E402
import upload as up  # noqa: E402
from common import LOOP, Stage, config, now, read_json, week_id, write_json  # noqa: E402

MEASURE = LOOP / "state" / "measurement.json"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
STATUS_API = "https://www.googleapis.com/youtube/v3/videos"


def load() -> dict:
    return read_json(MEASURE, default={"videos": [], "weeks": [], "updated": None})


def retention_streak(rows: list[dict], floor: float) -> int:
    """How many of the most recent videos, in order, are below the floor."""
    streak = 0
    for r in reversed(rows):
        avp = r.get("average_view_percentage")
        if avp is None:
            break            # unmeasured breaks the streak; it is not evidence
        if avp < floor:
            streak += 1
        else:
            break
    return streak


def fetch_analytics(token: str, video_ids: list[str]) -> dict:
    q = urllib.parse.urlencode({
        "ids": "channel==MINE",
        "startDate": "2020-01-01",
        "endDate": now()[:10],
        "metrics": "views,estimatedMinutesWatched,averageViewPercentage,"
                   "estimatedRevenue",
        "dimensions": "video",
        "filters": "video==" + ",".join(video_ids),
    })
    req = urllib.request.Request(f"{ANALYTICS}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def check_strikes(token: str, video_ids: list[str]) -> list[dict]:
    """A copyright or community strike shows up as a rejected/failed status."""
    q = urllib.parse.urlencode({"part": "status", "id": ",".join(video_ids)})
    req = urllib.request.Request(f"{STATUS_API}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    bad = []
    for item in data.get("items", []):
        s = item.get("status", {})
        if s.get("uploadStatus") == "rejected" or s.get("rejectionReason"):
            bad.append({"video_id": item["id"],
                        "reason": s.get("rejectionReason", "rejected")})
    return bad


def main() -> None:
    cfg = config()
    week = week_id()
    floor = cfg["retention"]["floor_pct"]
    need = cfg["retention"]["breach_streak_to_trip"]

    with Stage("fri-measure", week,
               zero_work_hint="Nothing has published yet, so there is nothing "
                              "to measure. That is expected before the first "
                              "public video.") as st:
        m = load()
        pub = ledger.load()["published"]

        # --- real work that never depends on credentials -------------------
        streak = retention_streak(m["videos"], floor)
        st.work(f"recomputed retention streak from {len(m['videos'])} measured "
                f"video(s): {streak} consecutive below {floor}%")

        if streak >= need:
            breaker.trip("retention",
                         f"{streak} consecutive videos below the {floor}% "
                         f"retention floor")
            st.work("tripped the circuit breaker on retention")

        if not pub:
            st.named_stop(
                "NOTHING_PUBLISHED",
                "no video has published yet, so there is no retention or RPM to "
                "pull. The ranking for Sunday falls back to demand evidence.",
                unblock="This clears itself after the first public video.")

        creds = up.load_credentials(cfg)
        video_ids = [p["video_id"] for p in pub if p.get("video_id")]
        if creds is None:
            m["weeks"].append({"week": week, "at": now(), "measured": False,
                               "reason": "OAUTH_MISSING",
                               "known_videos": len(video_ids)})
            m["updated"] = now()
            write_json(MEASURE, m)
            st.work("recorded an unmeasured week in loop/state/measurement.json")
            st.named_stop(
                "OAUTH_MISSING",
                f"{len(video_ids)} published video(s) cannot be measured without "
                f"OAuth. Retention and RPM are unavailable, so Sunday's ranking "
                f"runs on demand evidence and the retention breaker cannot fire.",
                unblock="Same credentials as the upload lane, plus the "
                        "yt-analytics.readonly scope. See docs/loop.md § OAuth.")

        token = up.access_token(creds)

        strikes = check_strikes(token, video_ids)
        if strikes:
            breaker.trip("strike", json.dumps(strikes)[:400])
            st.work(f"tripped the circuit breaker on {len(strikes)} strike(s)")

        data = fetch_analytics(token, video_ids)
        cols = [h["name"] for h in data.get("columnHeaders", [])]
        for row in data.get("rows", []):
            d = dict(zip(cols, row))
            rec = {
                "video_id": d.get("video"),
                "week_measured": week,
                "at": now(),
                "views": d.get("views"),
                "average_view_percentage": d.get("averageViewPercentage"),
                "estimated_minutes_watched": d.get("estimatedMinutesWatched"),
                "estimated_revenue": d.get("estimatedRevenue"),
                "rpm": (round(d["estimatedRevenue"] / d["views"] * 1000, 2)
                        if d.get("views") else None),
            }
            m["videos"] = [v for v in m["videos"]
                           if v["video_id"] != rec["video_id"]] + [rec]
            st.work(f"measured {rec['video_id']}: "
                    f"{rec['average_view_percentage']}% retention")

        streak = retention_streak(m["videos"], floor)
        if streak >= need:
            breaker.trip("retention",
                         f"{streak} consecutive videos below the {floor}% "
                         f"retention floor")
            st.work("tripped the circuit breaker on retention")

        m["weeks"].append({"week": week, "at": now(), "measured": True,
                           "videos": len(m["videos"]),
                           "retention_streak_below_floor": streak})
        m["updated"] = now()
        write_json(MEASURE, m)
        st.work("wrote loop/state/measurement.json — Sunday's ranking reads this")


if __name__ == "__main__":
    main()
