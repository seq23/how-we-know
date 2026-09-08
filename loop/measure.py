"""Friday 17:00 — pull retention and RPM, write measurement, feed Sunday.

This stage closes the loop. It is also the stage that can *trip the circuit
breaker on its own*: three consecutive videos below the retention floor is one
of the three named trip causes, and it is the only one a machine can notice
before a human does.

**What the floor is, and why it stopped being a percentage.** It was three
videos below a 30% average view PERCENTAGE, computed by dividing average view
duration by `retention.runtime_minutes` — a configured 10.5 while every render
was 8.12 minutes. That reported **77% of the true retention**: a real 39% shown
as 30%, straight into the breaker, on a healthy format. Two independent things
were wrong and both are fixed here:

  * a percentage is now computed against **that video's own measured duration**
    (`loop/durations.py`), never a configured constant. Episodes are about to
    get longer, so a shared constant would have gone wrong again immediately.
  * the trip cause is now average view **DURATION** in seconds. Moving from 8.1
    to 10.5 minute episodes mechanically LOWERS percentage while RAISING watch
    hours — 525 hours per 10k views against 405 — so a percentage floor
    punishes the owner for the decision that helps her. Watch hours are what
    count toward YPP; duration is what multiplies into them. The percentage
    floor survives as the DERIVATION of the duration floor and as display, and
    can no longer trip anything on its own.

Two APIs, both behind the same missing OAuth:
  * YouTube Analytics  — averageViewPercentage, estimatedRevenue (RPM)
  * YouTube Data       — the strike / status check, and the subscriber count
                         the monetisation gates are measured against

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
import domains  # noqa: E402
import durations  # noqa: E402
import ledger  # noqa: E402
import upload as up  # noqa: E402
import ypp  # noqa: E402
from common import (LOOP, Stage, config, now, read_json, summary,  # noqa: E402
                    week_id, write_json)

MEASURE = LOOP / "state" / "measurement.json"
FINDING = LOOP / "state" / "retention_finding.md"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
STATUS_API = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_API = "https://www.googleapis.com/youtube/v3/channels"
CHANNEL_STATS = LOOP / "state" / "channel_stats.json"


def load() -> dict:
    return read_json(MEASURE, default={"videos": [], "weeks": [], "updated": None})


def video_runtime_s(rec: dict, pub: list[dict]) -> float | None:
    """The ACTUAL duration of the video a measurement row describes.

    video_id -> slug (the ledger) -> measured seconds (loop/durations.py, which
    reads the duration recorded at upload, or probes the render). Returns None
    when the video has genuinely never been measured; the caller must exclude
    it from percentage arithmetic rather than substitute a constant, because
    substituting a constant is the bug.
    """
    if rec.get("runtime_s"):
        return float(rec["runtime_s"])
    slug = next((x["slug"] for x in pub
                 if x.get("video_id") == rec.get("video_id")), None)
    return durations.duration_s(slug) if slug else None


def breakeven_pct(cfg: dict, runtime_s: float) -> float:
    """The percentage that carries the SAME watch hours as the floor.

    Below this a video really is losing watch time; above it, a lower
    percentage on a longer video is more watch hours, not fewer. The AVD floor
    is derived so that this can never be crossed from the wrong side.
    """
    floor_s = float(cfg["retention"]["floor_avd_seconds"])
    return round(floor_s / runtime_s * 100, 2) if runtime_s else 0.0


def retention_checkpoint(rows: list[dict], cfg: dict,
                         pub: list[dict] | None = None) -> dict:
    """Average view duration, and a percentage of each video's REAL runtime.

    This is the single piece of evidence that could invalidate the whole
    content design rather than one topic. It is reported in seconds first,
    because seconds are what multiply into watch hours and what survive a
    catalogue holding both 8-minute and 10-minute episodes.
    """
    pub = pub or []
    floor_s = float(cfg["retention"]["floor_avd_seconds"])
    early_min = float(cfg["retention"].get("early_exit_minutes", 2.0))
    measured = [r for r in rows if r.get("average_view_duration_s")]
    if not measured:
        return {"status": "no_data", "measured": 0,
                "floor_avd_seconds": floor_s}

    durations_s, unknown, pcts = [], [], []
    for r in measured:
        d = float(r["average_view_duration_s"])
        durations_s.append(d)
        rt = video_runtime_s(r, pub)
        if rt:
            pcts.append(d / rt * 100)
        else:
            unknown.append(r.get("video_id"))

    mean_s = sum(durations_s) / len(durations_s)
    early = [r for r in measured
             if float(r["average_view_duration_s"]) < early_min * 60]
    cp = {
        "status": "measured",
        "measured": len(measured),
        "floor_avd_seconds": floor_s,
        "early_exit_threshold_minutes": early_min,
        "mean_view_duration_s": round(mean_s, 1),
        "mean_view_duration_mm_ss": f"{int(mean_s // 60)}m{int(mean_s % 60):02d}s",
        "videos_losing_viewers_in_first_2min": len(early),
        "videos_without_a_measured_runtime": unknown,
        "format_verdict": (
            "FORMAT PROBLEM" if len(early) >= max(2, len(measured) * 0.6)
            else "acceptable"),
    }
    if pcts:
        cp["mean_pct_of_actual_runtime"] = round(sum(pcts) / len(pcts), 1)
        cp["pct_basis"] = ("each video's own measured duration "
                           f"({len(pcts)} of {len(measured)} measured)")
    else:
        cp["mean_pct_of_actual_runtime"] = None
        cp["pct_basis"] = ("no video has a measured duration, so no percentage "
                           "is reported. A percentage against a configured "
                           "runtime is not an approximation of this number.")
    return cp


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
        f"**{cp['mean_view_duration_mm_ss']} average view duration** across "
        f"{cp['measured']} measured video(s), against a "
        f"{cp['floor_avd_seconds']}s floor."
        + (f" That is {cp['mean_pct_of_actual_runtime']}% of "
           f"{cp['pct_basis']}." if cp.get('mean_pct_of_actual_runtime')
           else f" No percentage is reported: {cp['pct_basis']}"),
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
            "or the opening - not the runtime. The 10-minute floor is an owner "
            "decision and a longer video that holds is MORE watch time, not "
            "less; the fix is moving the concrete payoff into the first 30 "
            "seconds, never a shorter cut.",
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


def retention_streak(rows: list[dict], floor_avd_s: float) -> int:
    """How many of the most recent videos, in order, are below the DURATION floor.

    Duration, not percentage, and this is the whole point of the change. A
    percentage streak fires on a channel that has just made its videos longer
    and is banking MORE watch time per view — the one metric YPP counts. A
    duration streak fires only when viewers are genuinely watching less, which
    is the thing the breaker was built to notice.

    An unmeasured video breaks the streak rather than continuing it: absence of
    evidence is not three consecutive bad videos.
    """
    streak = 0
    for r in reversed(rows):
        avd = r.get("average_view_duration_s")
        if avd is None:
            break
        if float(avd) < floor_avd_s:
            streak += 1
        else:
            break
    return streak


def domain_streaks(rows: list[dict], pub: list[dict], floor_avd_s: float) -> dict:
    """The same streak, per domain.

    With two domains live, three bad videos in a row is ambiguous: it is a bad
    FORMAT only if it is happening in every domain, and a bad NICHE if it is
    happening in one. `loop/breaker.py` is told which, so it can stop shortening
    every episode on the channel because materials had a bad quarter.
    """
    out = {}
    for name, group in domains.split_rows(rows, pub).items():
        out[name] = retention_streak(group, floor_avd_s)
    return out


def breaker_cause(streaks: dict, need: int) -> dict | None:
    """Format, or niche? Decided from the per-domain streaks, never assumed.

    * every domain that HAS enough measured videos is breaching -> the format
    * one domain of several is breaching                        -> that niche
    * nothing is breaching                                      -> no trip
    """
    breaching = {d: s for d, s in streaks.items()
                 if d != "unattributed" and s >= need}
    scored = {d: s for d, s in streaks.items() if d != "unattributed"}
    if not breaching:
        return None
    if len(scored) > 1 and len(breaching) < len(scored):
        d = sorted(breaching)[0]
        return {"cause": "domain", "domain": d, "streak": breaching[d],
                "why": (f"{breaching[d]} consecutive {d} videos below the "
                        f"duration floor while {len(scored) - len(breaching)} "
                        f"other domain(s) are holding. That is a NICHE that is "
                        f"not working, not a format that is. Shortening every "
                        f"episode on the channel would be the wrong repair.")}
    return {"cause": "format", "domains": sorted(breaching),
            "streak": max(breaching.values()),
            "why": (f"every measured domain ({', '.join(sorted(breaching))}) is "
                    f"below the duration floor for {max(breaching.values())} "
                    f"consecutive videos. A problem in all of them at once is "
                    f"the format.")}


CORE_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage")
MONEY_METRICS = "estimatedRevenue"


def _analytics_call(token: str, video_ids: list[str], metrics: str) -> dict:
    q = urllib.parse.urlencode({
        "ids": "channel==MINE",
        "startDate": "2020-01-01",
        "endDate": now()[:10],
        "metrics": metrics,
        "dimensions": "video",
        "filters": "video==" + ",".join(video_ids),
    })
    req = urllib.request.Request(f"{ANALYTICS}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def fetch_analytics(token: str, video_ids: list[str]) -> dict:
    """Watch-time metrics, with revenue added only if it is actually permitted.

    `estimatedRevenue` is a MONETARY metric. It needs
    yt-analytics-monetary.readonly, which this token deliberately does not
    carry, and asking for it alongside ordinary metrics fails the WHOLE request
    with `401 Insufficient permission to access this report` - not a partial
    result, not a warning. Confirmed 2026-08-31: dropping that one metric turns
    the identical call into a 200.

    So the lane was dead for a reason that had nothing to do with the token, and
    would have stayed dead every week while looking like an auth problem. The
    core metrics are what the loop actually decides on; revenue is zero until
    YPP (1,000 subs and 4,000 watch hours) and is therefore asked for
    SEPARATELY, with its failure downgraded to a note.

    When the channel is monetised, add yt-analytics-monetary.readonly to
    auth/tokens.py SCOPES and re-consent; this function then picks revenue up
    with no other change.
    """
    data = _analytics_call(token, video_ids, CORE_METRICS)
    try:
        money = _analytics_call(token, video_ids, MONEY_METRICS)
    except urllib.error.HTTPError as e:
        data["revenue_unavailable"] = (
            f"HTTP {e.code} - needs yt-analytics-monetary.readonly; "
            f"revenue is zero until YPP anyway")
        return data

    # Merge revenue in by video id, so callers see the same shape as before.
    cols = [h["name"] for h in data.get("columnHeaders", [])]
    mcols = [h["name"] for h in money.get("columnHeaders", [])]
    if "video" in cols and "video" in mcols:
        vi, mi = cols.index("video"), mcols.index("video")
        ri = mcols.index(MONEY_METRICS)
        by_id = {row[mi]: row[ri] for row in money.get("rows", [])}
        data["columnHeaders"].append({"name": MONEY_METRICS})
        for row in data.get("rows", []):
            row.append(by_id.get(row[vi], 0))
    return data


def fetch_channel_stats(token: str) -> dict | None:
    """Subscribers, for the monetisation gates. One quota unit.

    `loop/ypp.py` reports progress toward Expanded and Standard YPP and cannot
    invent a subscriber count; an absent one is reported as unknown, which is a
    different claim from zero. Failure here is a note, never a stop - the
    retention work above is what this stage exists for.
    """
    q = urllib.parse.urlencode({"part": "statistics", "mine": "true"})
    try:
        req = urllib.request.Request(f"{CHANNELS_API}?{q}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    items = data.get("items") or []
    if not items:
        return None
    s = items[0].get("statistics", {})
    rec = {"subscribers": int(s.get("subscriberCount") or 0),
           "views": int(s.get("viewCount") or 0),
           "videos": int(s.get("videoCount") or 0),
           "hidden_subscriber_count": bool(s.get("hiddenSubscriberCount")),
           "at": now()}
    write_json(CHANNEL_STATS, rec)
    return rec


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
    floor_avd = float(cfg["retention"]["floor_avd_seconds"])
    need = cfg["retention"]["breach_streak_to_trip"]

    with Stage("fri-measure", week,
               zero_work_hint="Nothing has published yet, so there is nothing "
                              "to measure. That is expected before the first "
                              "public video.") as st:
        m = load()
        pub = ledger.load()["published"]

        # --- real work that never depends on credentials -------------------
        streak = retention_streak(m["videos"], floor_avd)
        st.work(f"recomputed retention streak from {len(m['videos'])} measured "
                f"video(s): {streak} consecutive below {floor_avd}s average "
                f"view duration")

        per_domain = domain_streaks(m["videos"], pub, floor_avd)
        st.work(f"per-domain duration streaks: {per_domain or 'none measured'}")
        cause = breaker_cause(per_domain, need)
        if cause:
            breaker.trip("retention" if cause["cause"] == "format"
                         else "domain", cause["why"])
            st.work(f"tripped the circuit breaker on {cause['cause']}: "
                    f"{cause['why'][:120]}")
        else:
            # THE OTHER HALF, which never existed. This lane is the only thing
            # in the repo entitled to say retention recovered - it holds the
            # measurement - and it tripped the breaker without ever being able
            # to untrip it. A breaker with a trip path and no reset path halts
            # publishing until a human types a command, which on this channel
            # meant four red lanes a day for a condition that had already
            # passed.
            cleared = breaker.clear_if(
                "retention", f"retention recovered: breaker_cause() sees no "
                             f"breach across {len(per_domain)} measured "
                             f"domain(s) at a {floor_avd}s floor")
            cleared = cleared or breaker.clear_if(
                "domain", f"the breaching domain recovered: breaker_cause() "
                          f"sees no breach across {len(per_domain)} measured "
                          f"domain(s) at a {floor_avd}s floor")
            if cleared:
                st.work("reset the circuit breaker: the retention breach that "
                        "tripped it is no longer present in the measurement")

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

        # Everything from here on talks to Google. A network or auth failure is
        # an ordinary, recurring condition for a scheduled job - not a bug - so
        # it takes a NAMED STOP that says what to do, rather than escaping as a
        # traceback. A stack trace in a cron log is a stop nobody sees.
        #
        # The real work above (the retention streak, the breaker) has already
        # been done and written, which is why the stop is legitimate here and
        # not a Rule 0 violation.
        try:
            token = up.access_token(creds)

            fetch_channel_stats(token)
            st.work("recorded the channel's subscriber count for the "
                    "monetisation gates")

            strikes = check_strikes(token, video_ids)
            if strikes:
                breaker.trip("strike", json.dumps(strikes)[:400])
                st.work(f"tripped the circuit breaker on {len(strikes)} strike(s)")

            data = fetch_analytics(token, video_ids)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:                       # noqa: BLE001
                pass
            m["weeks"].append({"week": week, "at": now(), "measured": False,
                               "reason": f"HTTP_{e.code}",
                               "known_videos": len(video_ids)})
            m["updated"] = now()
            write_json(MEASURE, m)
            st.work("recorded an unmeasured week in loop/state/measurement.json")

            if e.code in (401, 403):
                st.named_stop(
                    "OAUTH_REJECTED",
                    f"Google rejected the stored credentials with HTTP {e.code}. "
                    f"{len(video_ids)} published video(s) went unmeasured this "
                    f"week. Sunday's ranking falls back to demand evidence and "
                    f"the retention breaker cannot fire until this is cleared.",
                    detail={"code": e.code, "body": body},
                    unblock="The refresh token is expired, revoked, or missing "
                            "the yt-analytics.readonly scope. Re-run "
                            "auth/youtube_auth.py to re-consent; it forces a "
                            "fresh grant when the scope set has changed.")
            else:
                st.named_stop(
                    f"ANALYTICS_HTTP_{e.code}",
                    f"the YouTube API returned HTTP {e.code}. This week is "
                    f"unmeasured; nothing is lost, the next run re-reads the "
                    f"same window.",
                    detail={"code": e.code, "body": body},
                    unblock="Usually transient (5xx or quota). If it repeats for "
                            "more than two weeks the quota or the project needs "
                            "looking at.")
        except urllib.error.URLError as e:
            # HTTPError SUBCLASSES URLError. The clause above catches it first
            # today, but that makes clause ORDER load-bearing: reorder these two
            # and every 401 silently becomes "transient, no action required" -
            # the precise opposite of the truth, on the one lane whose failure
            # is otherwise invisible. Re-raise so the ordering cannot decide it.
            if isinstance(e, urllib.error.HTTPError):
                raise
            m["weeks"].append({"week": week, "at": now(), "measured": False,
                               "reason": "NETWORK", "known_videos": len(video_ids)})
            m["updated"] = now()
            write_json(MEASURE, m)
            st.work("recorded an unmeasured week in loop/state/measurement.json")
            st.named_stop(
                "NETWORK_UNREACHABLE",
                f"could not reach the YouTube API ({e.reason}). This week is "
                f"unmeasured; the next run re-reads the same window.",
                unblock="Transient. No action unless it repeats.")
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
                # The video's OWN duration, stored beside its own retention, so
                # no later reader has to find a runtime to divide by and none of
                # them can pick a different one.
                "runtime_s": durations.duration_s(
                    next((x["slug"] for x in pub
                          if x.get("video_id") == d.get("video")), "") or ""),
                "estimated_revenue": d.get("estimatedRevenue"),
                "rpm": (round(d["estimatedRevenue"] / d["views"] * 1000, 2)
                        if d.get("views") else None),
            }
            m["videos"] = [v for v in m["videos"]
                           if v["video_id"] != rec["video_id"]] + [rec]
            st.work(f"measured {rec['video_id']}: "
                    f"{rec['average_view_percentage']}% retention")

        streak = retention_streak(m["videos"], floor_avd)
        per_domain = domain_streaks(m["videos"], pub, floor_avd)
        cause = breaker_cause(per_domain, need)
        if cause:
            breaker.trip("retention" if cause["cause"] == "format"
                         else "domain", cause["why"])
            st.work(f"tripped the circuit breaker on {cause['cause']}")
        else:
            # See the note at the other call site: trip and reset belong to the
            # same lane, because this is where the evidence is.
            if (breaker.clear_if("retention", "retention recovered in this "
                                 "week's measurement")
                    or breaker.clear_if("domain", "the breaching domain "
                                        "recovered in this week's measurement")):
                st.work("reset the circuit breaker: the retention breach that "
                        "tripped it is no longer present in the measurement")

        # ---- the retention checkpoint, reported prominently ---------------
        cp = retention_checkpoint(m["videos"], cfg, pub)
        m["retention_checkpoint"] = cp
        write_finding(cp, cfg)
        if cp["status"] == "measured":
            st.work(f"retention checkpoint: {cp['mean_view_duration_mm_ss']} "
                    f"average view duration against a "
                    f"{cp['floor_avd_seconds']}s floor "
                    f"({cp['mean_pct_of_actual_runtime']}% of actual runtime)")
            summary(
                f"## Retention checkpoint\n\n"
                f"**{cp['mean_view_duration_mm_ss']}** average view duration "
                f"against a **{cp['floor_avd_seconds']}s** floor "
                f"({cp['mean_pct_of_actual_runtime']}% of "
                f"{cp['pct_basis']}).\n\n"
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
                f"({cp['mean_view_duration_mm_ss']} average view duration "
                f"against a {cp['floor_avd_seconds']}s floor). This "
                f"invalidates the format, not the topic selection.",
                detail=cp,
                unblock="Read loop/state/retention_finding.md. Better ranking "
                        "will not fix this - the runtime or the structure has "
                        "to change.")


if __name__ == "__main__":
    main()
