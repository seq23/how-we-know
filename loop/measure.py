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
from common import (LOOP, Stage, config, now, read_json, summary,  # noqa: E402
                    week_id, write_json)

MEASURE = LOOP / "state" / "measurement.json"
FINDING = LOOP / "state" / "retention_finding.md"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
STATUS_API = "https://www.googleapis.com/youtube/v3/videos"


def load() -> dict:
    return read_json(MEASURE, default={"videos": [], "weeks": [], "updated": None})


def retention_checkpoint(rows: list[dict], cfg: dict) -> dict:
    """Average view DURATION against the ~7.5 minute runtime.

    This is the single piece of evidence that could invalidate the whole
    content design rather than one topic. Average view *percentage* hides it: a
    30% retention on a 7.5 minute video is 2m15s, which sounds survivable and
    is not - it means viewers are leaving before the first real explanation
    lands, and no amount of better topic selection fixes a format problem.

    So this is computed as seconds, compared against the runtime, and written
    to `loop/state/retention_finding.md` as prose the owner actually reads.
    """
    runtime_min = float(cfg["retention"].get("runtime_minutes", 7.5))
    early_min = float(cfg["retention"].get("early_exit_minutes", 2.0))
    measured = [r for r in rows if r.get("average_view_duration_s")]
    if not measured:
        return {"status": "no_data", "measured": 0,
                "runtime_minutes": runtime_min}

    durations = [float(r["average_view_duration_s"]) for r in measured]
    mean_s = sum(durations) / len(durations)
    early = [r for r in measured
             if float(r["average_view_duration_s"]) < early_min * 60]
    return {
        "status": "measured",
        "measured": len(measured),
        "runtime_minutes": runtime_min,
        "early_exit_threshold_minutes": early_min,
        "mean_view_duration_s": round(mean_s, 1),
        "mean_view_duration_mm_ss": f"{int(mean_s // 60)}m{int(mean_s % 60):02d}s",
        "mean_pct_of_runtime": round(mean_s / (runtime_min * 60) * 100, 1),
        "videos_losing_viewers_in_first_2min": len(early),
        "format_verdict": (
            "FORMAT PROBLEM" if len(early) >= max(2, len(measured) * 0.6)
            else "acceptable"),
    }


def write_finding(cp: dict, cfg: dict) -> None:
    """Prose, in a file, that says what the number means. Not buried JSON."""
    if cp["status"] != "measured":
        FINDING.write_text(
            "# Retention checkpoint\n\nNo view-duration data yet. This fills "
            "in once the first videos have been public long enough to "
            "accumulate analytics.\n")
        return
    verdict = cp["format_verdict"]
    lines = [
        "# Retention checkpoint",
        "",
        f"**{cp['mean_view_duration_mm_ss']} average view duration** against a "
        f"{cp['runtime_minutes']} minute runtime "
        f"({cp['mean_pct_of_runtime']}% of the video), across "
        f"{cp['measured']} measured video(s).",
        "",
    ]
    if verdict == "FORMAT PROBLEM":
        lines += [
            "## The format is wrong, not the topics",
            "",
            f"{cp['videos_losing_viewers_in_first_2min']} of {cp['measured']} "
            f"videos lose the average viewer inside the first "
            f"{cp['early_exit_threshold_minutes']} minutes.",
            "",
            "Viewers are leaving before the first real explanation lands. That "
            "is not a topic-selection problem and better ranking will not fix "
            "it - the same thing will happen to the next four videos.",
            "",
            "**What this invalidates:** the cold-open-then-method structure, "
            "the ~7.5 minute runtime, or both. Consider a much shorter cut, or "
            "moving the concrete payoff into the first 30 seconds.",
            "",
            "This is the one finding that should stop the content design being "
            "treated as settled.",
        ]
    else:
        lines += [
            "## Format is holding",
            "",
            f"{cp['videos_losing_viewers_in_first_2min']} of {cp['measured']} "
            f"videos lose the average viewer inside the first "
            f"{cp['early_exit_threshold_minutes']} minutes, which is below the "
            f"threshold that would indicate a structural problem.",
        ]
    FINDING.write_text("\n".join(lines) + "\n")


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
        "metrics": "views,estimatedMinutesWatched,averageViewDuration,"
                   "averageViewPercentage,estimatedRevenue",
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
                "average_view_duration_s": d.get("averageViewDuration"),
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

        # ---- the retention checkpoint, reported prominently ---------------
        cp = retention_checkpoint(m["videos"], cfg)
        m["retention_checkpoint"] = cp
        write_finding(cp, cfg)
        if cp["status"] == "measured":
            st.work(f"retention checkpoint: {cp['mean_view_duration_mm_ss']} "
                    f"average view duration vs {cp['runtime_minutes']}min "
                    f"runtime ({cp['mean_pct_of_runtime']}%)")
            summary(
                f"## Retention checkpoint\n\n"
                f"**{cp['mean_view_duration_mm_ss']}** average view duration "
                f"against a **{cp['runtime_minutes']} minute** runtime "
                f"({cp['mean_pct_of_runtime']}%).\n\n"
                f"{cp['videos_losing_viewers_in_first_2min']} of "
                f"{cp['measured']} video(s) lose the average viewer inside the "
                f"first {cp['early_exit_threshold_minutes']} minutes.\n")
            if cp["format_verdict"] == "FORMAT PROBLEM":
                st.note("FORMAT PROBLEM - see loop/state/retention_finding.md")

        m["weeks"].append({"week": week, "at": now(), "measured": True,
                           "videos": len(m["videos"]),
                           "retention_streak_below_floor": streak,
                           "retention_checkpoint": cp})
        m["updated"] = now()
        write_json(MEASURE, m)
        st.work("wrote loop/state/measurement.json — Sunday's ranking reads this")

        # A finding this consequential is not left as a number in a file. A
        # named stop opens an issue and emails her, which is the point.
        if cp.get("format_verdict") == "FORMAT PROBLEM":
            st.named_stop(
                "FORMAT_PROBLEM",
                f"{cp['videos_losing_viewers_in_first_2min']} of "
                f"{cp['measured']} videos lose the average viewer inside the "
                f"first {cp['early_exit_threshold_minutes']} minutes "
                f"({cp['mean_view_duration_mm_ss']} average against a "
                f"{cp['runtime_minutes']} minute runtime). This invalidates the "
                f"format, not the topic selection.",
                detail=cp,
                unblock="Read loop/state/retention_finding.md. Better ranking "
                        "will not fix this - the runtime or the structure has "
                        "to change.")


if __name__ == "__main__":
    main()
