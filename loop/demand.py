"""PHASE 4 - the DEMAND verdict: do strangers click, and do they stay?

    python loop/demand.py pull [--dry-run]          # daily: measure, judge, repackage
    python loop/demand.py verdict                   # re-judge the snapshot, no network
    python loop/demand.py ingest-studio <csv> [--as-of YYYY-MM-DD]
    python loop/demand.py mark-test <video_id> --start|--end [--variants A B C]
    python loop/demand.py email                     # the Monday email (refuses untraced numbers)

WHY THIS EXISTS. Until 13 Oct 2026 the loop measured SUPPLY (did it publish)
and never DEMAND. The owner's day-30 gate (docs/CHANNEL-PLAN.md, "The
long-form program of 2026-10-13") is three floors: click-through above 4 %,
30-second retention above 70 %, average view percentage above 40 %; a video
under all of them after seven days gets a second title and thumbnail
automatically.

WHAT THE PULL MEASURES (long-form only: loop/state/ledger.json rows; any id
in loop/state/shorts_ledger.json is dropped). Public status, live title,
publish time and runtime come from the Data API (videos.list, 1 unit per 50,
recorded in loop/state/quota.json under lane "demand"). From the Analytics
API (separate quota; every call counted in the snapshot):
  * views, average view percentage, average view duration, watch minutes,
    subscribers gained - lifetime AND since the current packaging went up;
  * the traffic-source split (browse / suggested / search / external / other);
  * 30-second retention from the audience-retention report
    (audienceWatchRatio by elapsedVideoTimeRatio, one call per video), read at
    30 s / runtime. When YouTube returns no rows (it withholds the curve on
    low-view videos) the value is the STRING "insufficient", never 0.
Click-through and impressions are NOT in the Analytics API (measure.py:
HTTP 400 for every shape); they arrive from Studio's CSV export through
`ingest-studio`, and are "unknown" until one has.

THE VERDICT judges the CURRENT packaging: metrics since the later of the
video's public date, the packaging pass (titles.json applied_at) and this
lane's last automatic round. Under MIN_VIEWS views in that window it is
INSUFFICIENT; otherwise PASS (every available floor passes), FAIL (every
available floor fails) or WATCH (mixed).

MIN_VIEWS = 30, from the data. At the first pull (13 Oct 2026, 24 public
long-form videos) the median video had 8 lifetime views, the best 87 and the
second 45. The brief's example,
50 views in 7 days, is a number no long-form video here has ever reached, so
every verdict would read INSUFFICIENT forever and the second packaging could
never fire - a lane that runs but is inert. Thirty is the smallest sample at
which a mean of per-view percentages stops swinging by tens of points on one
viewer (the standard-error rule of thumb), and two of the channel's videos
had already crossed it lifetime - so the bar is reachable, not decorative. It is recorded in the snapshot.

THE SECOND PACKAGING. A FAIL video whose current packaging is at least seven
days old and that is public for seven days gets a NEW title from the
long-form proposer (loop/longform_title.py propose: the locked title rule and
truth guard; never the current or an earlier title) and the next unused
contract thumbnail variant (B, then C), written through the repackage lane's
own client, quota reserve and arming gate (loop/repackage.py). A video with an
ACTIVE Studio Test & Compare gets the title only - a thumbnail change cancels
the test. At most MAX_ROUNDS rounds; a video still failing after the last is
marked NEEDS_REVIEW in the Monday email (no stop, no block).

Guarded by validator V70 (loop/validate.py -> problems()) and
loop/tests/test_demand.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

from common import Stage, config, now, read_json, week_id, write_json  # noqa: E402

SNAPSHOT = LOOP / "state" / "demand.json"
HISTORY = LOOP / "state" / "demand_history.jsonl"
OUTDIR = LOOP / "state" / "demand"
SHORTS_LEDGER = LOOP / "state" / "shorts_ledger.json"
SCRIPTS = ROOT / "scripts"

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
LANE = "demand"
LIFETIME_START = "2020-01-01"
CHUNK = 50

# The owner's floors (docs/CHANNEL-PLAN.md, 13 Oct 2026). Strictly above.
FLOORS = {"ctr_pct": 4.0, "retention_30s_pct": 70.0, "avp_pct": 40.0}
RETENTION_AT_S = 30
MIN_VIEWS = 30            # see the module docstring: picked from the data
MIN_JUDGED = 3            # fewer judged videos than this -> "too early"
RANK_MIN_VIEWS = 10       # best/worst by watch minutes per view
REPACKAGE_AFTER_DAYS = 7
MAX_ROUNDS = 2
GATE_DAYS = 30
VARIANT_ORDER = ("B", "C")
INSUFFICIENT = "insufficient"
UNKNOWN = "unknown"
HOOKED = "stake-then-payoff"
FOOD = "food-science"
STATES = ("PASS", "WATCH", "FAIL", "INSUFFICIENT")

# insightTrafficSourceType -> the four buckets the owner reads.
TRAFFIC = {"SUBSCRIBER": "browse", "RELATED_VIDEO": "suggested",
           "YT_SEARCH": "search", "EXT_URL": "external",
           "NO_LINK_EMBEDDED": "external"}


# ------------------------------------------------------------------ helpers
def today() -> date:
    return datetime.now(timezone.utc).date()


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def iso_duration_s(s: str | None) -> float | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m or not s or s == "P":
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return float(d * 86400 + h * 3600 + mi * 60 + se)


def load(path: Path | None = None) -> dict:
    d = read_json(path or SNAPSHOT, default={}) or {}
    d.setdefault("videos", {})
    return d


def save(doc: dict, path: Path | None = None) -> None:
    doc["updated"] = now()
    write_json(path or SNAPSHOT, doc)


def history(path: Path | None = None) -> list[dict]:
    p = path or HISTORY
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_history(rows: list[dict], path: Path | None = None) -> int:
    """Append-only. A (date, video_id, source) already on file is not
    written twice; returns how many rows were added."""
    p = path or HISTORY
    have = {(r.get("date"), r.get("video_id"), r.get("source"))
            for r in history(p)}
    new = [r for r in rows
           if (r.get("date"), r.get("video_id"), r.get("source")) not in have]
    if new:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(new)


def short_ids() -> set[str]:
    led = read_json(SHORTS_LEDGER, default={"published": []}) or {}
    return {x.get("video_id") for x in led.get("published", []) if x.get("video_id")}


def longform_rows() -> list[dict]:
    """Live long-form ledger rows (never a Short, never retired)."""
    import ledger                                          # noqa: PLC0415
    shorts = short_ids()
    seen, out = set(), []
    for r in ledger.load().get("published") or []:
        vid = r.get("video_id")
        if not vid or r.get("retired_at") or vid in shorts or vid in seen:
            continue
        seen.add(vid)
        out.append(r)
    return out


def variant_of(slug: str) -> str:
    import opening                                         # noqa: PLC0415
    return opening.variant_of(slug)


def domain_of(slug: str) -> str:
    import domains                                         # noqa: PLC0415
    return domains.domain_of_slug(slug) or "deep-sea-ocean-science"


def packaging_pass_at(slug: str, vid: str) -> str | None:
    """When the packaging pass put this video's current title up (titles.json)."""
    import longform_title as LT                            # noqa: PLC0415
    row = LT.load()["titles"].get(slug) or {}
    # A re-proposed row (a new rule, 13 Oct 2026 #206) resets applied_at to
    # None and keeps the live title's stamp under "previous" - the title on
    # the video is still the one applied then, so that is when it went up.
    stamps = [row.get("applied_at"), (row.get("previous") or {}).get("applied_at")]
    if row.get("applied_video_id") not in (vid, None):
        return None
    stamps = [x for x in stamps if x]
    return max(stamps) if stamps else None


def packaging_since(v: dict) -> str | None:
    """The day the CURRENT packaging went up: the latest of public date,
    packaging pass and this lane's last round."""
    cands = [_d(v.get("public_since")), _d(v.get("packaging_pass_at"))]
    cands += [_d(r.get("at")) for r in v.get("repackages") or []]
    cands = [c for c in cands if c]
    return max(cands).isoformat() if cands else None


# --------------------------------------------------------------- the calls
class Analytics:
    """Every Analytics/Data call this lane makes. Tests pass a fixture."""

    def __init__(self, token: str):
        self.token = token
        self.analytics_calls = 0
        self.data_units = 0

    def _get(self, url: str, params: dict) -> dict:
        req = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def report(self, metrics: str, dimensions: str, ids: list[str],
               start: str, extra_filter: str = "") -> list[dict]:
        out = []
        for i in range(0, len(ids), CHUNK):
            chunk = ids[i:i + CHUNK]
            p = {"ids": "channel==MINE", "startDate": start,
                 "endDate": today().isoformat(), "metrics": metrics,
                 "dimensions": dimensions,
                 "filters": "video==" + ",".join(chunk) + extra_filter}
            self.analytics_calls += 1
            d = self._get(ANALYTICS, p)
            cols = [h["name"] for h in d.get("columnHeaders", [])]
            out += [dict(zip(cols, row)) for row in d.get("rows") or []]
        return out

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), CHUNK):
            self.data_units += 1
            d = self._get(VIDEOS_API, {"part": "snippet,status,contentDetails",
                                       "id": ",".join(ids[i:i + CHUNK])})
            out += d.get("items") or []
        return out


CORE = ("views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,subscribersGained")


def _core(row: dict | None) -> dict:
    row = row or {}
    return {"views": int(row.get("views") or 0),
            "watch_minutes": float(row.get("estimatedMinutesWatched") or 0),
            "avd_s": (float(row["averageViewDuration"])
                      if row.get("views") else None),
            "avp_pct": (round(float(row["averageViewPercentage"]), 2)
                        if row.get("views") else None),
            "subscribers_gained": int(row.get("subscribersGained") or 0)}


def retention_at(curve: list[tuple[float, float]], duration_s: float | None,
                 at_s: float = RETENTION_AT_S):
    """Percent of starting viewers still watching at `at_s`, from the
    audience-retention curve. "insufficient" when YouTube returned no curve
    or the runtime is unknown - NEVER 0."""
    if not curve or not duration_s:
        return INSUFFICIENT
    x = min(1.0, at_s / duration_s)
    pts = sorted(curve)
    if x <= pts[0][0]:
        return round(pts[0][1] * 100, 1)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            y = y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0)
            return round(y * 100, 1)
    return round(pts[-1][1] * 100, 1)


def fetch_retention(api, vid: str, start: str, duration_s):
    try:
        rows = api.report("audienceWatchRatio", "elapsedVideoTimeRatio",
                          [vid], start)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) or e.code >= 500:
            raise
        return f"unavailable: HTTP {e.code}"
    curve = [(float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"]))
             for r in rows]
    return retention_at(curve, duration_s)


# ---------------------------------------------------------------- the pull
def pull(api, doc: dict | None = None, day: date | None = None) -> dict:
    """Measure every public long-form video. Returns the updated snapshot and
    writes nothing; the caller saves it and appends the history rows in
    doc['_rows']."""
    day = day or today()
    doc = doc if doc is not None else load()
    rows = longform_rows()
    by_id = {r["video_id"]: r for r in rows}
    live = {it["id"]: it for it in api.videos(list(by_id))}
    public = [vid for vid in by_id
              if (live.get(vid) or {}).get("status", {}).get("privacyStatus") == "public"]
    vids = doc.setdefault("videos", {})
    for vid in public:
        r, it = by_id[vid], live[vid]
        v = vids.setdefault(vid, {"video_id": vid, "repackage_round": 0,
                                  "repackages": []})
        sn, cd = it.get("snippet") or {}, it.get("contentDetails") or {}
        slug = r["slug"]
        v.update({"slug": slug, "title": sn.get("title") or r.get("title"),
                  "domain": domain_of(slug), "variant_of": variant_of(slug),
                  "public_since": (sn.get("publishedAt") or r.get("scheduled_publish_at")
                                   or r.get("published_at") or "")[:10] or None,
                  "duration_s": iso_duration_s(cd.get("duration")),
                  # Never forgets: the latest packaging stamp ever seen.
                  "packaging_pass_at": max([x for x in (v.get("packaging_pass_at"),
                                                        packaging_pass_at(slug, vid)) if x],
                                           default=None)})
        v["hooked"] = v["variant_of"] == HOOKED
        v.setdefault("thumbnail_test", {"active": False, "started": None,
                                        "variants": []})
        if "thumbnails_used" not in v:
            import longform_title as LT                    # noqa: PLC0415
            trow = LT.load()["titles"].get(slug) or {}
            v["thumbnails_used"] = ["A"] if trow.get("thumbnail_applied") else []
        v["packaging_since"] = packaging_since(v)
        ps = _d(v["public_since"])
        v["days_public"] = (day - ps).days if ps else None
        pk = _d(v["packaging_since"])
        v["days_since_packaging"] = (day - pk).days if pk else None
    for vid in [k for k in vids if k not in public]:
        vids[vid]["public"] = False
    for vid in public:
        vids[vid]["public"] = True

    life = {x["video"]: x for x in api.report(CORE, "video", public, LIFETIME_START)}
    traffic: dict[str, dict] = {vid: {"browse": 0, "suggested": 0, "search": 0,
                                      "external": 0, "other": 0} for vid in public}
    for x in api.report("views", "video,insightTrafficSourceType", public,
                        LIFETIME_START):
        b = TRAFFIC.get(x.get("insightTrafficSourceType"), "other")
        if x.get("video") in traffic:
            traffic[x["video"]][b] += int(x.get("views") or 0)
    windows: dict[str, list[str]] = {}
    for vid in public:
        v = vids[vid]
        if v["packaging_since"] and v["public_since"] and \
                v["packaging_since"] > v["public_since"]:
            windows.setdefault(v["packaging_since"], []).append(vid)
    cur: dict[str, dict] = {}
    for start, ids in windows.items():
        for x in api.report(CORE, "video", ids, start):
            cur[x["video"]] = x
    out_rows = []
    for vid in public:
        v = vids[vid]
        v["lifetime"] = _core(life.get(vid))
        v["lifetime"]["traffic"] = traffic[vid]
        v["lifetime"]["retention_30s_pct"] = (
            fetch_retention(api, vid, LIFETIME_START, v["duration_s"])
            if v["lifetime"]["views"] else INSUFFICIENT)
        in_window = vid in [i for ids in windows.values() for i in ids]
        if in_window:
            c = _core(cur.get(vid))
            c["retention_30s_pct"] = (fetch_retention(api, vid, v["packaging_since"],
                                                      v["duration_s"])
                                      if c["views"] else INSUFFICIENT)
            c["since"] = v["packaging_since"]
        else:
            c = {k: v["lifetime"][k] for k in v["lifetime"] if k != "traffic"}
            c["since"] = v["public_since"]
        v["current"] = c
        v["measured_on"] = day.isoformat()
    doc["as_of"] = day.isoformat()
    doc["config"] = {"floors": FLOORS, "retention_at_s": RETENTION_AT_S,
                     "min_views": MIN_VIEWS, "min_judged": MIN_JUDGED,
                     "rank_min_views": RANK_MIN_VIEWS,
                     "repackage_after_days": REPACKAGE_AFTER_DAYS,
                     "max_rounds": MAX_ROUNDS, "gate_days": GATE_DAYS}
    judge(doc, day)
    for vid in public:
        v = vids[vid]
        out_rows.append({
            "date": day.isoformat(), "video_id": vid, "slug": v["slug"],
            "source": "analytics", "variant_of": v["variant_of"],
            "domain": v["domain"], "verdict": v["verdict"],
            "repackage_round": v.get("repackage_round", 0),
            "lifetime": v["lifetime"], "current": v["current"],
            "ctr": v.get("ctr", UNKNOWN)})
    doc["pull"] = {"at": now(), "date": day.isoformat(),
                   "public_ids": sorted(public),
                   "ledger_longform": len(by_id),
                   "analytics_calls": getattr(api, "analytics_calls", 0),
                   "data_api_units": getattr(api, "data_units", 0),
                   "retention": {
                       "returned": sum(isinstance(vids[x]["lifetime"]["retention_30s_pct"],
                                                  (int, float)) for x in public),
                       "insufficient": sum(vids[x]["lifetime"]["retention_30s_pct"]
                                           == INSUFFICIENT for x in public)}}
    doc["_rows"] = out_rows
    return doc


# ------------------------------------------------------------- the verdict
def floor_state(value, floor: float) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return UNKNOWN
    return "pass" if value > floor else "fail"


def judge_video(v: dict) -> str:
    c = v.get("current") or {}
    ctr = v.get("ctr")
    ctr_pct = ctr.get("pct") if isinstance(ctr, dict) else None
    v["floors"] = {"ctr": floor_state(ctr_pct, FLOORS["ctr_pct"]),
                   "retention_30s": floor_state(c.get("retention_30s_pct"),
                                                FLOORS["retention_30s_pct"]),
                   "avp": floor_state(c.get("avp_pct"), FLOORS["avp_pct"])}
    if int(c.get("views") or 0) < MIN_VIEWS:
        return "INSUFFICIENT"
    avail = [s for s in v["floors"].values() if s != UNKNOWN]
    if not avail:
        return "INSUFFICIENT"
    if all(s == "pass" for s in avail):
        return "PASS"
    if all(s == "fail" for s in avail):
        return "FAIL"
    return "WATCH"


def _median(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return round(statistics.median(xs), 1) if xs else None


def judge(doc: dict, day: date | None = None) -> dict:
    """Verdict per public video and the channel summary, written INTO the
    snapshot - the Monday email reads nothing else."""
    day = day or today()
    vids = [v for v in doc.get("videos", {}).values() if v.get("public")]
    for v in vids:
        v["verdict"] = judge_video(v)
        v["needs_review"] = bool(v.get("repackage_round", 0) >= MAX_ROUNDS
                                 and v["verdict"] == "FAIL"
                                 and (v.get("days_since_packaging") or 0)
                                 >= REPACKAGE_AFTER_DAYS)
    counts = {s: sum(v["verdict"] == s for v in vids) for s in STATES}
    judged = [v for v in vids if v["verdict"] != "INSUFFICIENT"]

    def meds(group):
        return {"n": len(group),
                "ctr_pct": _median([(v.get("ctr") or {}).get("pct")
                                    if isinstance(v.get("ctr"), dict) else None
                                    for v in group]),
                "retention_30s_pct": _median([v["lifetime"].get("retention_30s_pct")
                                              for v in group]),
                "avp_pct": _median([v["lifetime"].get("avp_pct") for v in group])}
    cohorts: dict[str, list] = {}
    for v in vids:
        cohorts.setdefault(v.get("variant_of") or "pre-rule", []).append(v)
    judged_meds = {"n": len(judged),
                   "ctr_pct": _median([(v.get("ctr") or {}).get("pct")
                                       if isinstance(v.get("ctr"), dict) else None
                                       for v in judged]),
                   "retention_30s_pct": _median([v["current"].get("retention_30s_pct")
                                                 for v in judged]),
                   "avp_pct": _median([v["current"].get("avp_pct") for v in judged])}
    if len(judged) < MIN_JUDGED:
        verdict = "too early"
    else:
        keys = (("ctr_pct", "ctr_pct"), ("retention_30s_pct", "retention_30s_pct"),
                ("avp_pct", "avp_pct"))
        avail = [(judged_meds[k], FLOORS[f]) for k, f in keys if judged_meds[k] is not None]
        verdict = "yes" if avail and all(m > f for m, f in avail) else "no"

    def wmpv(v):
        lt = v["lifetime"]
        return round(lt["watch_minutes"] / lt["views"], 2) if lt["views"] else None
    ranked = sorted([v for v in vids if v["lifetime"]["views"] >= RANK_MIN_VIEWS],
                    key=lambda v: (-(wmpv(v) or 0), v["video_id"]))
    rank_row = lambda v: {"video_id": v["video_id"], "title": v.get("title"),  # noqa: E731
                          "views": v["lifetime"]["views"],
                          "watch_minutes_per_view": wmpv(v)}
    week_ago = (day - timedelta(days=7)).isoformat()
    repack = [{"video_id": v["video_id"], "round": r["round"], "at": r["at"][:10],
               "old_title": r["old_title"], "new_title": r["new_title"],
               "thumbnail": r.get("thumbnail"),
               "title_only_reason": r.get("title_only_reason")}
              for v in vids for r in v.get("repackages") or []
              if r.get("at", "")[:10] >= week_ago]
    import longform_title as LT                            # noqa: PLC0415
    applied = sorted(r["applied_at"][:10] for r in LT.load()["titles"].values()
                     if r.get("applied_at") and r.get("applied_video_id")
                     in {v["video_id"] for v in doc.get("videos", {}).values()})
    first = applied[0] if applied else None
    gate = {"first_repackaged": first,
            "gate_date": ((_d(first) + timedelta(days=GATE_DAYS)).isoformat()
                          if first else None),
            "days_left": ((_d(first) + timedelta(days=GATE_DAYS) - day).days
                          if first else None)}
    food = [rank_row(v) | {"ctr_pct": (v.get("ctr") or {}).get("pct")
                           if isinstance(v.get("ctr"), dict) else None,
                           "verdict": v["verdict"]}
            for v in vids if v.get("domain") == FOOD]
    doc["channel"] = {
        "week": week_id(day), "date": day.isoformat(), "public_longform": len(vids),
        "packaging_working": verdict, "counts": counts,
        "judged_medians": judged_meds,
        "cohorts": {k: meds(g) for k, g in sorted(cohorts.items())},
        "best3": [rank_row(v) for v in ranked[:3]],
        "worst3": [rank_row(v) for v in list(reversed(ranked))[:3]],
        "repackaged_this_week": repack,
        "needs_review": [{"video_id": v["video_id"], "title": v.get("title")}
                         for v in vids if v.get("needs_review")],
        "tests_active": [{"video_id": v["video_id"], "title": v.get("title"),
                          "started": v["thumbnail_test"].get("started")}
                         for v in vids if (v.get("thumbnail_test") or {}).get("active")],
        "gate": gate, "food": food}
    return doc


# ----------------------------------------------------- the second packaging
def repackage_candidates(doc: dict) -> list[dict]:
    shorts = short_ids()
    out = []
    for v in doc.get("videos", {}).values():
        if not v.get("public") or v.get("video_id") in shorts:
            continue
        if v.get("verdict") != "FAIL":
            continue
        if int(v.get("repackage_round") or 0) >= MAX_ROUNDS:
            continue
        if (v.get("days_public") or 0) < REPACKAGE_AFTER_DAYS:
            continue
        if (v.get("days_since_packaging") or 0) < REPACKAGE_AFTER_DAYS:
            continue
        out.append(v)
    return sorted(out, key=lambda v: (v.get("public_since") or "", v["video_id"]))


def next_variant(v: dict) -> str | None:
    used = set(v.get("thumbnails_used") or [])
    return next((x for x in VARIANT_ORDER if x not in used), None)


def variant_path(slug: str, variant: str) -> Path | None:
    import domains                                         # noqa: F401,PLC0415
    # APPEND, never prepend: visuals/ has its own domains.py, and putting it
    # first would shadow loop/domains.py for every later import.
    if str(ROOT / "visuals") not in sys.path:
        sys.path.append(str(ROOT / "visuals"))
    import thumb_contract                                  # noqa: PLC0415
    p = Path(thumb_contract.VARIANTS_DIR) / slug / f"{variant}.jpg"
    if not p.exists() or thumb_contract.verify(slug):
        return None
    return p


def _norm(t: str | None) -> str:
    return re.sub(r"\W+", " ", (t or "").lower()).strip()


def new_title_for(v: dict, propose=None, tries: int = 2) -> tuple[str | None, str]:
    """A passing title different from the current one and from every earlier
    one, from the long-form proposer. (None, why) when there is none."""
    import longform_title as LT                            # noqa: PLC0415
    slug = v["slug"]
    sp = SCRIPTS / f"{slug}.md"
    if not sp.exists():
        return None, f"no scripts/{slug}.md"
    script = sp.read_text(encoding="utf-8")
    q = LT._question_for(slug, script)
    old = {_norm(v.get("title"))} | {_norm(r.get("old_title"))
                                     for r in v.get("repackages") or []}
    old |= {_norm(r.get("new_title")) for r in v.get("repackages") or []}
    import longform_title                                  # noqa: PLC0415
    why = "the proposer returned no passing title"
    for _ in range(tries):
        # Named call (not an alias) so the route test's call graph sees this
        # lane reach llm_router (loop/tests/test_claude_subscription_route.py).
        r = (propose(slug, script, q) if propose
             else longform_title.propose(slug, script, q))
        t = r.get("new_title")
        if not r.get("checks_passed") or not t:
            why = "; ".join(r.get("problems") or [])[:160] or why
            continue
        if _norm(t) in old:
            why = f"the proposer repeated an earlier title {t!r}"
            continue
        if LT.title_problems(t, script, q):
            why = "the proposed title failed the title rule on re-check"
            continue
        return t, ""
    return None, why


def run_repackage(doc: dict, st, dry_run: bool = False, yt=None,
                  propose=None, day: date | None = None) -> list[dict]:
    import quota                                           # noqa: PLC0415
    import repackage as RP                                 # noqa: PLC0415
    import ytmeta                                          # noqa: PLC0415
    day = day or today()
    cands = repackage_candidates(doc)
    if not cands:
        st.note("second packaging: no video is FAIL on every available floor "
                f"after {REPACKAGE_AFTER_DAYS} days of its current packaging")
        return []
    fit = RP.affordable(RP.APPLY_UNITS, len(cands))
    if fit < len(cands):
        st.note(f"second packaging: quota fits {fit} of {len(cands)} today; the "
                f"rest wait for tomorrow, in order. {quota.report()}")
    cands = cands[:fit]
    if not cands:
        return []
    if dry_run:
        for v in cands:
            st.work(f"DRY RUN would repackage {v['video_id']} ({v['slug']}) "
                    f"round {int(v.get('repackage_round') or 0) + 1}")
        return []
    import arming                                          # noqa: PLC0415
    arming.gate(st, RP.LANE)
    yt = yt or RP.client(st, dry_run)
    done = []
    for v in cands:
        title, why = new_title_for(v, propose)
        if not title:
            st.note(f"{v['slug']}: no second packaging today - {why}")
            continue
        live = yt.video(v["video_id"])
        if not live:
            quota.spend(quota.VIDEO_READ, LANE)
            st.note(f"{v['slug']}: {v['video_id']} not found on the channel")
            continue
        snippet = ytmeta.merge_snippet(live.get("snippet"), title=title)
        yt.update_snippet(v["video_id"], snippet)
        spent = quota.VIDEO_READ + quota.VIDEO_UPDATE
        test_active = bool((v.get("thumbnail_test") or {}).get("active"))
        thumb, reason = None, None
        if test_active:
            reason = ("a Studio Test & Compare is running; a thumbnail change "
                      "would cancel it")
        else:
            var = next_variant(v)
            img = variant_path(v["slug"], var) if var else None
            if img:
                yt.set_thumbnail(v["video_id"], img)
                spent += quota.THUMBNAIL
                thumb = var
                v.setdefault("thumbnails_used", []).append(var)
            else:
                reason = (f"no contract-holding variant {var} on disk" if var
                          else "variants B and C are both used")
        quota.spend(spent, LANE)
        rnd = int(v.get("repackage_round") or 0) + 1
        rec = {"round": rnd, "at": f"{day.isoformat()}T{now()[11:]}", "old_title": v.get("title"),
               "new_title": title, "thumbnail": thumb,
               "title_only_reason": reason, "test_active_at_change": test_active,
               "verdict_before": v.get("verdict"),
               "days_public": v.get("days_public"),
               "days_since_packaging": v.get("days_since_packaging"),
               "units": spent}
        v.setdefault("repackages", []).append(rec)
        v["repackage_round"] = rnd
        v["title"] = title
        v["packaging_since"] = day.isoformat()
        v["days_since_packaging"] = 0
        done.append(rec | {"video_id": v["video_id"]})
        st.work(f"{v['video_id']} ({v['slug']}) second packaging round {rnd}: "
                f"{rec['old_title']!r} -> {title!r}"
                + (f" + thumbnail {thumb}" if thumb else f" (title only: {reason})"))
    if done:
        arming.record_success(RP.LANE, detail=f"demand: {len(done)} second packaging(s)")
    return done


# --------------------------------------------------------------- studio CSV
def _num(s) -> float | None:
    s = str(s or "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_studio_csv(path: Path) -> list[dict]:
    """Studio -> Content -> Advanced mode -> export (Table data.csv).
    Columns used: Content (the video id), Impressions, Impressions
    click-through rate (%). The 'Total' row is skipped."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        idc = next((c for c in cols if c.strip().lower() in
                    ("content", "video id", "video")), None)
        imp = next((c for c in cols if c.strip().lower().startswith("impressions")
                    and "click" not in c.lower()), None)
        ctr = next((c for c in cols if "click-through" in c.lower()
                    or "click through" in c.lower()), None)
        if not (idc and imp and ctr):
            raise ValueError(f"not a Studio content export: need Content, "
                             f"Impressions and Impressions click-through rate "
                             f"columns, found {cols}")
        out = []
        for row in rd:
            vid = (row.get(idc) or "").strip()
            if not vid or vid.lower() == "total":
                continue
            out.append({"video_id": vid, "impressions": _num(row.get(imp)),
                        "ctr_pct": _num(row.get(ctr))})
        return out


def ingest_studio(path: Path, as_of: str, doc: dict | None = None) -> dict:
    doc = doc if doc is not None else load()
    rows = parse_studio_csv(path)
    vids = doc.setdefault("videos", {})
    longform = {r["video_id"] for r in longform_rows()} | set(vids)
    merged, skipped, hist = 0, 0, []
    for r in rows:
        if r["video_id"] not in longform or r["video_id"] in short_ids() \
                or r["ctr_pct"] is None:
            skipped += 1
            continue
        v = vids.setdefault(r["video_id"], {"video_id": r["video_id"],
                                            "repackage_round": 0, "repackages": []})
        v["ctr"] = {"pct": r["ctr_pct"], "impressions": r["impressions"],
                    "as_of": as_of, "source": "studio"}
        hist.append({"date": as_of, "video_id": r["video_id"], "source": "studio",
                     "impressions": r["impressions"], "ctr_pct": r["ctr_pct"]})
        merged += 1
    doc["studio"] = {"as_of": as_of, "file": Path(path).name, "merged": merged,
                     "skipped": skipped}
    if doc.get("as_of"):
        judge(doc)
    doc["_rows"] = hist
    return doc


# --------------------------------------------------------- the Monday email
def _n(x) -> str:
    if isinstance(x, bool) or x is None:
        return "-"
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer()):
        return f"{int(x):,}"
    return f"{x:,.1f}"


def _p(x) -> str:
    return "not known yet" if x is None else f"{_n(x)} %"


def _q(t) -> str:
    return f"“{t}”"


def render_email(doc: dict) -> tuple[str, str]:
    ch, cfg = doc["channel"], doc["config"]
    fl = cfg["floors"]
    c = ch["counts"]
    word = {"yes": "Yes", "no": "No", "too early": "Too early to say"}[ch["packaging_working"]]
    subj = (f"Demand {ch['week']}: is packaging working? {word}. "
            f"PASS {_n(c['PASS'])} · WATCH {_n(c['WATCH'])} · FAIL {_n(c['FAIL'])} "
            f"· too few views {_n(c['INSUFFICIENT'])}")
    L = [f"# Demand - {ch['week']}", "",
         f"**Is packaging working? {word}.**", ""]
    jm = ch["judged_medians"]
    if ch["packaging_working"] == "too early":
        L += [f"Fewer than {_n(cfg['min_judged'])} videos have {_n(cfg['min_views'])} "
              f"views since their new title went up, so the medians cannot be trusted yet.", ""]
    else:
        L += [f"Across the {_n(jm['n'])} videos with enough views: click-through "
              f"{_p(jm['ctr_pct'])}, 30-second hold {_p(jm['retention_30s_pct'])}, "
              f"watched {_p(jm['avp_pct'])} on average.", ""]
    L += ["## Counts", "",
          f"- **PASS** {_n(c['PASS'])} · **WATCH** {_n(c['WATCH'])} · "
          f"**FAIL** {_n(c['FAIL'])} · **too few views** {_n(c['INSUFFICIENT'])} "
          f"(of {_n(ch['public_longform'])} public long-form videos)",
          f"- The bar: click-through above {_p(fl['ctr_pct'])}, "
          f"{_n(cfg['retention_at_s'])}-second hold above {_p(fl['retention_30s_pct'])}, "
          f"watched above {_p(fl['avp_pct'])}. Under {_n(cfg['min_views'])} views "
          f"since the current title = too few to judge.", ""]
    L += ["## New titles this week", ""]
    if ch["repackaged_this_week"]:
        for r in ch["repackaged_this_week"]:
            thumb = (f"thumbnail {r['thumbnail']}" if r.get("thumbnail")
                     else f"title only ({r.get('title_only_reason')})")
            L.append(f"- {_q(r['old_title'])} → {_q(r['new_title'])}, {thumb}")
    else:
        L.append("- None. No video failed every bar after a full week.")
    if ch["tests_active"]:
        L.append("- A thumbnail test is running on: "
                 + ", ".join(_q(t["title"]) for t in ch["tests_active"])
                 + ". Those videos get new titles only, never a new thumbnail.")
    if ch["needs_review"]:
        L.append("- **NEEDS_REVIEW** (two new titles did not help): "
                 + ", ".join(_q(t["title"]) for t in ch["needs_review"]))
    L += ["", "## Hooked openings vs older ones (lifetime medians)", "",
          "| Opening | Videos | Click-through | 30-second hold | Watched |",
          "|---|---|---|---|---|"]
    for k, m in ch["cohorts"].items():
        name = "hooked" if k == HOOKED else k
        L.append(f"| {name} | {_n(m['n'])} | {_p(m['ctr_pct'])} | "
                 f"{_p(m['retention_30s_pct'])} | {_p(m['avp_pct'])} |")
    if HOOKED not in ch["cohorts"]:
        L.append("| hooked | none public yet | | | |")
    L += ["", "## Best and worst by watch minutes per view", ""]
    for head, rows in (("Best", ch["best3"]), ("Worst", ch["worst3"])):
        if rows:
            L.append(f"- **{head}:** " + "; ".join(
                f"{_q(r['title'])} {_n(r['watch_minutes_per_view'])} min "
                f"({_n(r['views'])} views)" for r in rows))
    if not ch["best3"]:
        L.append(f"- No video has {_n(cfg['rank_min_views'])} views yet.")
    g = ch["gate"]
    L += ["", f"## The day-{_n(cfg['gate_days'])} check", ""]
    if g["gate_date"]:
        L.append(f"- First new title went live {g['first_repackaged']}; the check is "
                 f"{g['gate_date']} ({_n(g['days_left'])} days left).")
        L.append(f"- Where it stands now: click-through {_p(jm['ctr_pct'])}, "
                 f"30-second hold {_p(jm['retention_30s_pct'])}, watched "
                 f"{_p(jm['avp_pct'])} (judged videos only).")
    else:
        L.append("- No new title has gone live yet, so the clock has not started.")
    if ch["food"]:
        L += ["", "## Food (judged by watch minutes per view)", "",
              "| Video | Views | Minutes per view | Click-through | Verdict |",
              "|---|---|---|---|---|"]
        for r in ch["food"]:
            L.append(f"| {_q(r['title'])} | {_n(r['views'])} | "
                     f"{_n(r['watch_minutes_per_view'])} | {_p(r['ctr_pct'])} | "
                     f"{r['verdict']} |")
    studio = doc.get("studio") or {}
    L += ["", f"Click-through comes from YouTube Studio"
          + (f" (as of {studio['as_of']})." if studio.get("as_of")
             else "; none read yet, so it shows as -.")]
    return subj, "\n".join(L).rstrip() + "\n"


_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_WEEK = re.compile(r"\b\d{4}-W\d{2}\b")
_QUOTED = re.compile(r"“([^”]*)”")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _walk(x, nums: set, strs: set):
    if isinstance(x, dict):
        for v in x.values():
            _walk(v, nums, strs)
    elif isinstance(x, list):
        for v in x:
            _walk(v, nums, strs)
    elif isinstance(x, bool) or x is None:
        return
    elif isinstance(x, (int, float)):
        nums.add(_n(x))
    elif isinstance(x, str):
        strs.add(x)
        for m in _DATE.findall(x) + _WEEK.findall(x):
            strs.add(m)


def untraced(text: str, doc: dict) -> list[str]:
    """Every number, date and quoted title in `text` that the snapshot does
    not hold. [] = the email may go."""
    nums, strs = set(), set()
    _walk({k: v for k, v in doc.items() if k != "_rows"}, nums, strs)
    bad = []
    for m in _QUOTED.findall(text):
        if m not in strs:
            bad.append(f"title {m!r}")
    t = _QUOTED.sub(" ", text)
    for rx in (_DATE, _WEEK):
        for m in rx.findall(t):
            if m not in strs:
                bad.append(f"date {m}")
        t = rx.sub(" ", t)
    for m in _NUM.findall(t):
        if m not in nums:
            bad.append(f"number {m}")
    return bad


def write_email(doc: dict, st) -> Path:
    if not doc.get("channel"):
        st.named_stop("DEMAND_EMAIL_UNTRACED",
                      "the demand snapshot has no channel summary, so the "
                      "Monday email has nothing it may print",
                      unblock="Run `python loop/demand.py pull` (the daily "
                              "workflow does); the next email run uses it.")
    subj, body = render_email(doc)
    bad = untraced(subj + "\n" + body, doc)
    if bad:
        st.named_stop("DEMAND_EMAIL_UNTRACED",
                      f"the Monday email printed {len(bad)} value(s) the "
                      f"snapshot does not hold; it was NOT written or sent",
                      detail={"untraced": bad[:20]},
                      unblock="A render bug in loop/demand.py render_email: "
                              "every number must come from loop/state/demand.json.")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    wk = doc["channel"]["week"]
    (OUTDIR / f"{wk}.md").write_text(body, encoding="utf-8")
    (OUTDIR / f"{wk}.subject").write_text(subj + "\n", encoding="utf-8")
    write_json(OUTDIR / f"{wk}.json", {k: v for k, v in doc.items() if k != "_rows"})
    return OUTDIR / f"{wk}.md"


# --------------------------------------------------------------- the guards
def problems(doc: dict | None = None, hist: list[dict] | None = None,
             email_dir: Path | None = None) -> list[str]:
    """Everything V70 holds. [] = the demand books are sound."""
    doc = doc if doc is not None else load()
    hist = hist if hist is not None else history()
    p: list[str] = []
    pull_ = doc.get("pull") or {}
    ids = pull_.get("public_ids") or []
    if not ids:
        return ["the demand pull recorded no public long-form video - zero rows "
                "is a failure, not an empty week (Rule 0)"]
    day = pull_.get("date")
    have = {r["video_id"] for r in hist
            if r.get("date") == day and r.get("source") == "analytics"}
    missing = [i for i in ids if i not in have]
    if missing:
        p.append(f"the {day} pull wrote no history row for {len(missing)} public "
                 f"long-form video(s): {missing[:5]}")
    shorts = short_ids()
    for vid in ids:
        v = doc["videos"].get(vid)
        if not v:
            p.append(f"{vid}: public in the pull but absent from the snapshot")
            continue
        if vid in shorts:
            p.append(f"{vid}: a Short is in the demand snapshot")
        for scope in ("lifetime", "current"):
            r30 = (v.get(scope) or {}).get("retention_30s_pct")
            if r30 is None or (isinstance(r30, (int, float))
                               and not isinstance(r30, bool) and r30 == 0):
                p.append(f"{vid}: {scope} 30-second retention reads {r30!r} - "
                         f"an empty curve is '{INSUFFICIENT}', never 0 or blank")
        if not isinstance((v.get("current") or {}).get("retention_30s_pct"),
                          (int, float)) and (v.get("floors") or {}).get(
                              "retention_30s") != UNKNOWN:
            p.append(f"{vid}: retention is insufficient but its floor reads "
                     f"{v['floors'].get('retention_30s')!r}")
        if not isinstance(v.get("ctr"), dict) and (v.get("floors") or {}).get(
                "ctr") != UNKNOWN:
            p.append(f"{vid}: no Studio click-through but its floor reads "
                     f"{v['floors'].get('ctr')!r}")
    for vid, v in doc.get("videos", {}).items():
        reps = v.get("repackages") or []
        if len(reps) > MAX_ROUNDS or int(v.get("repackage_round") or 0) > MAX_ROUNDS:
            p.append(f"{vid}: {len(reps)} automatic packaging rounds (max {MAX_ROUNDS})")
        if reps and vid in shorts:
            p.append(f"{vid}: the second packaging touched a Short")
        for r in reps:
            if (r.get("days_public") or 0) < REPACKAGE_AFTER_DAYS or \
                    (r.get("days_since_packaging") or 0) < REPACKAGE_AFTER_DAYS:
                p.append(f"{vid}: round {r.get('round')} repackaged a video under "
                         f"{REPACKAGE_AFTER_DAYS} days (public "
                         f"{r.get('days_public')}, packaging {r.get('days_since_packaging')})")
            if r.get("thumbnail") and r.get("test_active_at_change"):
                p.append(f"{vid}: round {r.get('round')} changed the thumbnail "
                         f"during an active Studio test")
        t = v.get("thumbnail_test") or {}
        if t.get("active") and not t.get("started"):
            p.append(f"{vid}: an active thumbnail test with no start date")
    d = email_dir or OUTDIR
    emails = sorted(d.glob("*.md")) if d.exists() else []
    if emails:
        last = emails[-1]
        side = last.with_suffix(".json")
        subj = last.with_suffix(".subject")
        if not side.exists():
            p.append(f"{last.name}: sent without its snapshot {side.name}")
        else:
            text = last.read_text(encoding="utf-8")
            if subj.exists():
                text = subj.read_text(encoding="utf-8") + "\n" + text
            bad = untraced(text, json.loads(side.read_text()))
            if bad:
                p.append(f"{last.name}: {len(bad)} value(s) not in its snapshot: {bad[:5]}")
    return p


# ---------------------------------------------------------------------- CLI
def _api(st):
    import upload as up                                    # noqa: PLC0415
    creds = up.load_credentials(config())
    if not creds or creds.get("unusable"):
        code, msg, unblock = up.credential_stop(creds, config())
        st.named_stop(code, msg, unblock=unblock)
    return Analytics(up.access_token(creds))


def cmd_pull(dry_run: bool, api=None, yt=None, propose=None) -> int:
    import quota                                           # noqa: PLC0415
    with Stage("demand-pull", week_id(),
               zero_work_hint="No public long-form video to measure.") as st:
        if not longform_rows():
            st.named_stop("NOTHING_PUBLISHED", "no long-form video is in the "
                          "ledger, so there is no demand to measure",
                          unblock="Clears itself after the first upload.")
        try:
            api = api or _api(st)
            doc = pull(api)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                st.named_stop("OAUTH_REJECTED",
                              f"Google rejected the stored credentials with HTTP "
                              f"{e.code}; no demand was measured today",
                              unblock="Re-run auth/youtube_auth.py; it needs the "
                                      "yt-analytics.readonly scope.")
            st.named_stop(f"ANALYTICS_HTTP_{e.code}",
                          f"the YouTube API returned HTTP {e.code}; today is "
                          f"unmeasured and tomorrow re-reads the same numbers",
                          unblock="Usually transient. Two weeks running means "
                                  "the project or quota needs looking at.")
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            st.named_stop("NETWORK_UNREACHABLE",
                          f"could not reach the YouTube API ({e.reason})",
                          unblock="Transient. No action unless it repeats.")
        ids = doc["pull"]["public_ids"]
        if not ids:
            st.named_stop("NOTHING_PUBLISHED", "no long-form video is public yet",
                          unblock="Clears itself after the first public video.")
        rows = doc.pop("_rows")
        if getattr(api, "data_units", 0):
            quota.spend(api.data_units, LANE)
        added = append_history(rows)
        st.work(f"measured {len(ids)} public long-form video(s): {added} new "
                f"history row(s), {doc['pull']['analytics_calls']} Analytics "
                f"call(s); 30-second retention returned for "
                f"{doc['pull']['retention']['returned']}, insufficient for "
                f"{doc['pull']['retention']['insufficient']}")
        st.work(f"verdict: {doc['channel']['counts']} - packaging working: "
                f"{doc['channel']['packaging_working']}")
        save(doc)
        done = run_repackage(doc, st, dry_run=dry_run, yt=yt, propose=propose)
        if done:
            judge(doc)
            save(doc)
        missing = problems(doc)
        if missing:
            st.named_stop("DEMAND_PULL_INCOMPLETE",
                          f"the demand books fail their own check: {missing[0]}",
                          detail={"problems": missing[:10]},
                          unblock="Read loop/demand.py problems(); a pull that "
                                  "skips a public video is a bug, not a quiet day.")
    return 0


def cmd_email() -> int:
    with Stage("demand-email", week_id()) as st:
        doc = load()
        path = write_email(doc, st)
        st.work(f"wrote {path.relative_to(ROOT)}: "
                f"{(path.with_suffix('.subject')).read_text().strip()}")
    return 0


def cmd_mark_test(vid: str, start: bool, variants: list[str] | None,
                  doc: dict | None = None, day: date | None = None) -> dict:
    keep = doc is None
    doc = doc if doc is not None else load()
    v = doc.get("videos", {}).get(vid)
    if v is None:
        raise SystemExit(f"{vid} is not a long-form video in loop/state/demand.json")
    d = (day or today()).isoformat()
    t = v.setdefault("thumbnail_test", {"active": False, "started": None,
                                        "variants": []})
    if start:
        t.update({"active": True, "started": d, "ended": None,
                  "variants": variants or ["A", "B", "C"]})
    else:
        t.update({"active": False, "ended": d})
    if keep:
        save(doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("verdict")
    sub.add_parser("email")
    p = sub.add_parser("ingest-studio")
    p.add_argument("csv")
    p.add_argument("--as-of", default=None)
    p = sub.add_parser("mark-test")
    p.add_argument("video_id")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--start", action="store_true")
    g.add_argument("--end", action="store_true")
    p.add_argument("--variants", nargs="*")
    a = ap.parse_args(argv)
    if a.cmd == "pull":
        return cmd_pull(a.dry_run)
    if a.cmd == "email":
        return cmd_email()
    if a.cmd == "verdict":
        doc = judge(load())
        save(doc)
        print(json.dumps(doc["channel"]["counts"]), doc["channel"]["packaging_working"])
        return 0
    if a.cmd == "ingest-studio":
        doc = ingest_studio(Path(a.csv), a.as_of or today().isoformat())
        rows = doc.pop("_rows")
        if not rows:
            print(f"REFUSED: no long-form row in {a.csv} carried a click-through "
                  f"rate ({doc['studio']['skipped']} skipped); nothing merged")
            return 1
        append_history(rows)
        save(doc)
        print(f"merged Studio click-through for {len(rows)} video(s) as of "
              f"{doc['studio']['as_of']} ({doc['studio']['skipped']} skipped)")
        return 0
    if a.cmd == "mark-test":
        cmd_mark_test(a.video_id, a.start, a.variants)
        print(f"{a.video_id}: thumbnail test {'started' if a.start else 'ended'}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
