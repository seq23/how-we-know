"""Google Trends signal for candidate topics and domains.

WHAT TRENDS ACTUALLY IS -- READ THIS BEFORE QUOTING ANY NUMBER
--------------------------------------------------------------
Google Trends returns a RELATIVE, NORMALISED INTEREST INDEX on a 0-100 scale.
100 is the peak of the requested series for the requested window and geography.
It is **not** a search count, not a view count, and not comparable across two
separately-fetched series. A keyword scoring 80 is not "80 searches" and is not
"twice as popular" as one scoring 40 in a different request.

What the index IS good for, and all this module claims:
  * DIRECTION of travel within one series (up, flat, down)
  * SEASONALITY within one series (is the rise a summer bump that repeats?)
  * RISING / BREAKOUT related queries, which are Google's own comparison of a
    query's recent period against its previous period

"Breakout" in the rising list means Google measured a growth it reports as
>5000%; it is usually a query with a very small prior base. It is a lead, not
a verdict.

SOURCE
------
The public trends.google.com widget endpoints that back the Trends web UI:
  https://trends.google.com/trends/api/explore
  https://trends.google.com/trends/api/widgetdata/multiline
  https://trends.google.com/trends/api/widgetdata/relatedsearches
These are unofficial and undocumented but free and keyless. `pytrends` (PyPI,
4.9.2, last released 2023) wraps exactly these same endpoints; it is effectively
unmaintained and drags in requests/pandas/lxml, so this module calls the
endpoints directly with the standard library. Same data, no dependency.

The endpoints rate-limit aggressively (HTTP 429). This module bootstraps the
NID cookie the UI uses, paces itself, and backs off exponentially. If a keyword
still cannot be fetched it is recorded with status "unavailable" and its error;
it is NEVER given an invented number and never silently dropped from the count.

Usage:
  python trends.py --from-seeds              # one probe per candidate domain
  python trends.py --keywords "whale fall,roman concrete"
  python trends.py --from-seeds --geo US --pause 4
  python trends.py --resume                  # continue after a throttle

Exit 0 with results. Exit 2 if NOTHING could be fetched (hard fail, never an
empty pass).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "trends.json")
CACHE = os.path.join(HERE, ".trends.cache.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
EXPLORE = "https://trends.google.com/trends/api/explore"
MULTILINE = "https://trends.google.com/trends/api/widgetdata/multiline"
RELATED = "https://trends.google.com/trends/api/widgetdata/relatedsearches"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------
class Trends:
    def __init__(self, hl: str = "en-US", tz: str = "0", pause: float = 4.0,
                 max_retries: int = 5):
        self.hl, self.tz, self.pause, self.max_retries = hl, tz, pause, max_retries
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.op.addheaders = [
            ("User-Agent", UA),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Accept", "application/json, text/plain, */*"),
            ("Referer", "https://trends.google.com/"),
        ]
        self.requests = 0
        self.throttles = 0
        self._bootstrap()

    def _bootstrap(self) -> None:
        """Pick up the NID cookie the Trends UI sets. Failure is non-fatal --
        the API sometimes answers without it -- but it is recorded."""
        self.cookies_ok = False
        for url in ("https://www.google.com/",
                    "https://trends.google.com/trends/?geo=US"):
            try:
                with self.op.open(url, timeout=20) as r:
                    r.read(2048)
            except Exception:
                pass
            time.sleep(1.0)
        self.cookies_ok = any(c.name == "NID" for c in self.jar)

    def _get(self, url: str, params: dict) -> tuple[dict | None, str | None]:
        full = url + "?" + urllib.parse.urlencode(params)
        for attempt in range(self.max_retries):
            try:
                self.requests += 1
                with self.op.open(full, timeout=30) as r:
                    body = r.read().decode("utf-8", "ignore")
                brace = body.find("{")
                if brace < 0:
                    return None, "unparseable response (no JSON body)"
                return json.loads(body[brace:]), None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503):
                    self.throttles += 1
                    wait = self.pause * (2 ** attempt)
                    print(f"      HTTP {e.code}; backing off {wait:.0f}s",
                          file=sys.stderr, flush=True)
                    time.sleep(wait)
                    continue
                if e.code == 400:
                    return None, "HTTP 400 (no Trends data for this term)"
                return None, f"HTTP {e.code}"
            except Exception as e:
                return None, f"{type(e).__name__}: {e}"
        return None, f"HTTP 429 after {self.max_retries} attempts (rate limited)"

    def widgets(self, keyword: str, geo: str, window: str):
        req = {"comparisonItem": [{"keyword": keyword, "geo": geo,
                                   "time": window}],
               "category": 0, "property": ""}
        d, err = self._get(EXPLORE, {"hl": self.hl, "tz": self.tz,
                                     "req": json.dumps(req)})
        if err:
            return None, err
        return {w["id"]: w for w in d.get("widgets", [])}, None

    def timeseries(self, widget) -> tuple[list[dict] | None, str | None]:
        d, err = self._get(MULTILINE, {"hl": self.hl, "tz": self.tz,
                                       "req": json.dumps(widget["request"]),
                                       "token": widget["token"]})
        if err:
            return None, err
        return d.get("default", {}).get("timelineData", []), None

    def related(self, widget) -> tuple[dict | None, str | None]:
        d, err = self._get(RELATED, {"hl": self.hl, "tz": self.tz,
                                     "req": json.dumps(widget["request"]),
                                     "token": widget["token"]})
        if err:
            return None, err
        lists = d.get("default", {}).get("rankedList", [])
        # rankedList[0] = TOP (share of searches), [1] = RISING (growth)
        def rows(i):
            if len(lists) <= i:
                return []
            return [{"query": k["query"],
                     "value": k.get("value"),
                     "formatted": k.get("formattedValue"),
                     "breakout": k.get("formattedValue") == "Breakout"}
                    for k in lists[i].get("rankedKeyword", [])]
        return {"top": rows(0), "rising": rows(1)}, None


# --------------------------------------------------------------------------
# Analysis -- every function below operates on real fetched points only
# --------------------------------------------------------------------------
def _points(timeline: list[dict]) -> list[tuple[int, int]]:
    """(unix_seconds, index_value), dropping the current partial bucket."""
    out = []
    for p in timeline:
        if p.get("isPartial"):
            continue          # partial week reads as a fake decline
        vals = p.get("value") or []
        if not vals:
            continue
        out.append((int(p["time"]), int(vals[0])))
    return out


def _slope(vals: list[int]) -> float:
    """OLS slope per step. Plain least squares, no smoothing."""
    n = len(vals)
    if n < 3:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(vals) / n
    num = sum((i - xm) * (v - ym) for i, v in enumerate(vals))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def direction(points: list[tuple[int, int]]) -> dict:
    """Direction of travel within ONE normalised series. Relative only."""
    vals = [v for _, v in points]
    if len(vals) < 12:
        return {"status": "insufficient_points", "points": len(vals)}
    mean = statistics.fmean(vals) or 1.0
    slope = _slope(vals)
    # Slope expressed as % of the series mean per step -- unit-free, so it can
    # be compared between series even though the raw index cannot.
    pct_per_step = slope / mean * 100

    recent = vals[-13:]
    prior = vals[-26:-13]
    delta = None
    if len(prior) == 13 and statistics.fmean(prior):
        delta = (statistics.fmean(recent) / statistics.fmean(prior) - 1) * 100

    if pct_per_step > 0.25:
        label = "rising"
    elif pct_per_step < -0.25:
        label = "declining"
    else:
        label = "flat"
    return {
        "status": "ok",
        "points": len(vals),
        "slope_pct_of_mean_per_step": round(pct_per_step, 3),
        "last13_vs_prior13_pct": round(delta, 1) if delta is not None else None,
        "series_mean_index": round(mean, 1),
        "series_max_index": max(vals),
        "label": label,
    }


def reliability(points: list[tuple[int, int]]) -> dict:
    """Is this series precise enough to reason about at all?

    The index is an INTEGER 0-100 normalised to the series maximum. If one
    event spikes the series, every other week is quantised into 0,1,2,3 and
    ratios computed on it are rounding noise, not measurement. "submersible"
    is the worked example: the June 2023 Titan implosion pins the max at 100
    and drags the five-year mean to 1.6, which made a naive year-over-year
    read +15300%. That number is an artefact and must never be quoted.
    """
    vals = [v for _, v in points]
    if not vals:
        return {"status": "no_data", "usable": False}
    mean = statistics.fmean(vals)
    mx = max(vals)
    zero_share = sum(v == 0 for v in vals) / len(vals)
    spike_ratio = (mx / mean) if mean else float("inf")
    flags = []
    if mean < 10:
        flags.append("low_resolution: series mean index < 10, so most weeks "
                     "quantise to 0-3 and percentage changes are rounding noise")
    if spike_ratio > 10:
        flags.append("spike_dominated: series max is >10x its mean, so one "
                     "event sets the scale for the whole series")
    if zero_share > 0.25:
        flags.append("sparse: more than a quarter of weeks report zero interest")
    return {
        "status": "ok",
        "series_mean_index": round(mean, 2),
        "series_max_index": mx,
        "max_over_mean": round(spike_ratio, 1),
        "zero_week_share": round(zero_share, 3),
        "flags": flags,
        "usable": not flags,
        "note": ("If usable is false, direction and year-over-year figures for "
                 "this series are not quotable. The rising/breakout related "
                 "queries remain valid -- Google computes those itself."),
    }


def seasonality(points: list[tuple[int, int]]) -> dict:
    """Month-of-year profile from a multi-year series.

    Two things are deliberately guarded against:
      * a GROWING series faking a peak in its most recent months -- handled by
        removing the linear trend first;
      * a ONE-OFF EVENT faking a season -- handled by taking the MEDIAN per
        month rather than the mean, and by requiring the same month to be the
        peak in more than one year before the pattern is called seasonal.
    Without the second guard the Titan implosion made "submersible" look like
    it had a strong June season. One June is not a season.
    """
    if len(points) < 104:                       # need ~2 years of weeks
        return {"status": "insufficient_history", "points": len(points)}
    vals = [v for _, v in points]
    slope = _slope(vals)
    centre = statistics.median(vals) or statistics.fmean(vals) or 1.0
    detrended = [v - slope * i for i, v in enumerate(vals)]

    by_month: dict[int, list[float]] = defaultdict(list)
    by_year_month: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    for (ts, _), d in zip(points, detrended):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        by_month[dt.month].append(d)
        by_year_month[dt.year][dt.month].append(d)
    if len(by_month) < 12:
        return {"status": "incomplete_year", "months_covered": len(by_month)}

    # Median per month: one extraordinary week cannot move it.
    prof = {MONTHS[m - 1]: round(statistics.median(v) / centre * 100, 1)
            for m, v in sorted(by_month.items())}
    peak, trough = max(prof, key=prof.get), min(prof, key=prof.get)
    amplitude = round(prof[peak] - prof[trough], 1)

    # Does the same month peak in more than one year? That is what makes it
    # a season rather than an event.
    yearly_peaks = []
    for yr, months in sorted(by_year_month.items()):
        if len(months) < 10:                    # partial year, skip
            continue
        yearly_peaks.append((yr, MONTHS[max(
            months, key=lambda m: statistics.median(months[m])) - 1]))
    peak_counts: dict[str, int] = defaultdict(int)
    for _, m in yearly_peaks:
        peak_counts[m] += 1
    full_years = len(yearly_peaks)
    consistency = (max(peak_counts.values()) / full_years) if full_years else 0.0
    modal_peak = (max(peak_counts, key=peak_counts.get) if peak_counts else None)

    if consistency < 0.5 or full_years < 2:
        strength = "not_seasonal_one_off"
    elif amplitude >= 40:
        strength = "strong"
    elif amplitude >= 20:
        strength = "moderate"
    else:
        strength = "weak"

    return {
        "status": "ok",
        "full_years_used": full_years,
        "monthly_index_pct_of_median": prof,
        "peak_month": peak,
        "trough_month": trough,
        "amplitude_pct_points": amplitude,
        "per_year_peak_month": dict(yearly_peaks),
        "modal_peak_month": modal_peak,
        "peak_month_consistency": round(consistency, 2),
        "strength": strength,
        "summer_peaking": (strength in ("strong", "moderate")
                           and modal_peak in ("Jun", "Jul", "Aug")),
        "note": ("Detrended, median-per-month profile; 100 = series median. "
                 "strength is 'not_seasonal_one_off' when the peak month does "
                 "not repeat across years -- that is an event, not a season, "
                 "and a rise near it is not a seasonal rise."),
    }


def year_over_year(points: list[tuple[int, int]]) -> dict:
    if len(points) < 104:
        return {"status": "insufficient_history"}
    vals = [v for _, v in points]
    last, prev = vals[-52:], vals[-104:-52]
    pm = statistics.fmean(prev)
    if not pm:
        return {"status": "prior_year_all_zero"}
    if pm < 5:
        # The index is an integer 0-100. A prior-year mean under 5 means the
        # ratio is dominated by rounding, not by change. Report the levels and
        # refuse the percentage rather than publish a number like +15300%.
        return {"status": "prior_year_base_too_small",
                "last_52w_mean_index": round(statistics.fmean(last), 1),
                "prior_52w_mean_index": round(pm, 2),
                "yoy_change_pct": None,
                "why": ("prior-year mean index < 5; a percentage on that base "
                        "is quantisation noise and is not reported")}
    return {"status": "ok",
            "last_52w_mean_index": round(statistics.fmean(last), 1),
            "prior_52w_mean_index": round(pm, 1),
            "yoy_change_pct": round((statistics.fmean(last) / pm - 1) * 100, 1)}


# --------------------------------------------------------------------------
# Per-keyword fetch
# --------------------------------------------------------------------------
def measure(api: Trends, keyword: str, geo: str) -> dict:
    rec = {
        "keyword": keyword,
        "geo": geo or "WORLDWIDE",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "explore_endpoint": EXPLORE,
            "timeseries_endpoint": MULTILINE,
            "related_endpoint": RELATED,
            "windows": ["today 5-y (seasonality, YoY)", "today 12-m (direction, rising queries)"],
            "scale": "relative normalised interest index 0-100, NOT search volume",
        },
        "status": "ok",
        "errors": [],
    }

    # ---- 5 year window: seasonality + year over year -------------------
    ws, err = api.widgets(keyword, geo, "today 5-y")
    if err:
        rec["status"] = "unavailable"
        rec["errors"].append(f"explore 5y: {err}")
        return rec
    time.sleep(api.pause)
    if "TIMESERIES" not in ws:
        rec["errors"].append("explore 5y: no TIMESERIES widget")
        pts5: list[tuple[int, int]] = []
    else:
        tl, err = api.timeseries(ws["TIMESERIES"])
        time.sleep(api.pause)
        if err:
            rec["errors"].append(f"timeseries 5y: {err}")
            pts5 = []
        else:
            pts5 = _points(tl)
    rec["five_year"] = {
        "observations": len(pts5),
        "reliability": reliability(pts5),
        "seasonality": seasonality(pts5) if pts5 else {"status": "no_data"},
        "year_over_year": year_over_year(pts5) if pts5 else {"status": "no_data"},
        "long_direction": direction(pts5) if pts5 else {"status": "no_data"},
        "series": [{"t": t, "v": v} for t, v in pts5],
    }

    # ---- 12 month window: direction + rising queries -------------------
    ws, err = api.widgets(keyword, geo, "today 12-m")
    if err:
        rec["errors"].append(f"explore 12m: {err}")
        if not pts5:
            rec["status"] = "unavailable"
        return rec
    time.sleep(api.pause)

    pts12: list[tuple[int, int]] = []
    if "TIMESERIES" in ws:
        tl, err = api.timeseries(ws["TIMESERIES"])
        time.sleep(api.pause)
        if err:
            rec["errors"].append(f"timeseries 12m: {err}")
        else:
            pts12 = _points(tl)
    rec["twelve_month"] = {
        "observations": len(pts12),
        "reliability": reliability(pts12),
        "direction": direction(pts12) if pts12 else {"status": "no_data"},
        "series": [{"t": t, "v": v} for t, v in pts12],
    }

    if "RELATED_QUERIES" in ws:
        rel, err = api.related(ws["RELATED_QUERIES"])
        time.sleep(api.pause)
        if err:
            rec["errors"].append(f"related_queries: {err}")
            rec["related_queries"] = None
        else:
            rec["related_queries"] = rel
            rec["breakout_count"] = sum(1 for r in rel["rising"] if r["breakout"])
    else:
        rec["related_queries"] = None
        rec["errors"].append("no RELATED_QUERIES widget (too little data)")

    if not pts5 and not pts12:
        rec["status"] = "unavailable"
    return rec


def verdict(rec: dict) -> str:
    """One honest sentence combining direction with seasonality."""
    if rec.get("status") != "ok":
        return "unavailable"
    rel5 = rec.get("five_year", {}).get("reliability", {})
    rel12 = rec.get("twelve_month", {}).get("reliability", {})
    d = rec.get("twelve_month", {}).get("direction", {})
    if d.get("status") != "ok":
        d = rec.get("five_year", {}).get("long_direction", {})
    if d.get("status") != "ok":
        return "insufficient data"

    if not rel12.get("usable", True):
        # A no-data series carries no flags at all, so this must not index
        # blindly into an empty list.
        flags = rel12.get("flags") or []
        why = flags[0].split(":")[0] if flags else rel12.get("status", "no data")
        return (f"direction NOT QUOTABLE - {why}"
                "; only the rising/breakout queries are usable here")

    lab = d["label"]
    s = rec.get("five_year", {}).get("seasonality", {})
    if s.get("status") == "ok" and s.get("strength") == "not_seasonal_one_off":
        lab += " (series shaped by a one-off event, not a season)"
    elif lab == "rising" and s.get("strength") in ("strong", "moderate"):
        lab += (f" - but peaks in {s.get('modal_peak_month')} in "
                f"{s.get('peak_month_consistency'):.0%} of years; check the "
                "month before calling it growth")
    yoy = rec.get("five_year", {}).get("year_over_year", {})
    if yoy.get("status") == "ok" and rel5.get("usable", True):
        return f"{lab}; YoY {yoy['yoy_change_pct']:+.1f}%"
    if yoy.get("status") == "prior_year_base_too_small":
        return f"{lab}; YoY suppressed (prior-year base too small to divide by)"
    return lab


# --------------------------------------------------------------------------
def load_probes(args) -> list[tuple[str, str]]:
    """-> [(domain_or_'', keyword)]"""
    probes: list[tuple[str, str]] = []
    if args.keywords:
        probes += [("", k.strip()) for k in args.keywords.split(",") if k.strip()]
    if args.from_seeds:
        spec = json.load(open(args.seedfile, encoding="utf-8"))["domains"]
        for name, cfg in spec.items():
            # The generic domain nouns are the first two seeds by construction.
            for kw in cfg["seeds"][:args.per_domain]:
                probes.append((name, kw))
    return probes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-seeds", action="store_true",
                    help="probe one or more keywords per candidate domain")
    ap.add_argument("--seedfile", default=os.path.join(HERE, "seeds_broad.json"))
    ap.add_argument("--per-domain", type=int, default=1)
    ap.add_argument("--keywords", default=None, help="comma-separated")
    ap.add_argument("--geo", default="US",
                    help="two-letter geo, or empty string for worldwide")
    ap.add_argument("--pause", type=float, default=4.0)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--resume", action="store_true",
                    help="reuse anything already in the cache file")
    args = ap.parse_args()

    probes = load_probes(args)
    if not probes:
        sys.exit("FATAL: nothing to measure. Pass --from-seeds or --keywords.")

    cache: dict[str, dict] = {}
    if args.resume and os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
        print(f"resuming with {len(cache)} cached keyword(s)")

    print(f"Google Trends: {len(probes)} probe(s), geo={args.geo or 'WORLDWIDE'}, "
          f"pause={args.pause}s")
    api = Trends(pause=args.pause)
    print(f"  NID cookie acquired: {api.cookies_ok}")

    results: dict[str, dict] = {}
    for i, (domain, kw) in enumerate(probes, 1):
        key = f"{args.geo}|{kw}"
        if key in cache and cache[key].get("status") == "ok":
            rec = cache[key]
            print(f"[{i}/{len(probes)}] {kw!r} (cached)")
        else:
            print(f"[{i}/{len(probes)}] {kw!r} …", flush=True)
            rec = measure(api, kw, args.geo)
            cache[key] = rec
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
        rec = dict(rec)
        rec["domain"] = domain
        rec["verdict"] = verdict(rec)
        results[key] = rec
        print(f"      {rec['status']}: {rec['verdict']}"
              + (f"  | breakouts: {rec.get('breakout_count', 0)}"
                 if rec.get("related_queries") else ""), flush=True)
        time.sleep(args.pause)

    ok = [r for r in results.values() if r["status"] == "ok"]
    if not ok:
        sys.exit("FATAL: Google Trends returned nothing usable for any probe "
                 f"({api.throttles} throttles across {api.requests} requests). "
                 "Not writing a results file -- an empty pass would look like a "
                 "measurement. Re-run later with --resume and a longer --pause.")

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/trends.py",
        "source": "trends.google.com public widget endpoints (keyless, free)",
        "geo": args.geo or "WORLDWIDE",
        "scale_caveat": (
            "Every value in this file is a RELATIVE NORMALISED INTEREST INDEX "
            "(0-100 within its own series). It is not a search count and two "
            "separately-fetched series are not directly comparable in level. "
            "Only direction, seasonal shape, and Google's own rising/breakout "
            "ranking may be quoted."
        ),
        "requests_made": api.requests,
        "throttle_events": api.throttles,
        "probes_attempted": len(results),
        "probes_ok": len(ok),
        "probes_unavailable": [r["keyword"] for r in results.values()
                               if r["status"] != "ok"],
        "results": list(results.values()),
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {args.out}: {len(ok)}/{len(results)} probes measured, "
          f"{api.throttles} throttle events")

    print(f"\n{'keyword':<28}{'12m':<11}{'YoY%':>9}{'season':>22}{'peak':>6}"
          f"{'brk':>5}  reliability")
    for r in sorted(ok, key=lambda r: -(r.get("twelve_month", {})
                                        .get("direction", {})
                                        .get("slope_pct_of_mean_per_step") or -99)):
        d = r.get("twelve_month", {}).get("direction", {})
        s = r.get("five_year", {}).get("seasonality", {})
        y = r.get("five_year", {}).get("year_over_year", {})
        rel = r.get("twelve_month", {}).get("reliability", {})
        yv = y.get("yoy_change_pct")
        print(f"{r['keyword'][:27]:<28}"
              f"{(d.get('label', '?') if rel.get('usable', True) else 'unquotable'):<11}"
              f"{(f'{yv:+.1f}' if yv is not None else 'n/a'):>9}"
              f"{s.get('strength', '?'):>22}{s.get('modal_peak_month') or '-':>6}"
              f"{r.get('breakout_count', 0):>5}  "
              f"{'ok' if rel.get('usable') else ','.join(f.split(':')[0] for f in rel.get('flags', []))}")


if __name__ == "__main__":
    main()
