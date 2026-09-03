"""Audience geography per candidate domain -- a PROXY for YouTube RPM.

WHY THIS EXISTS
---------------
`research/proposed-taxonomy.json` ranks 20 candidate domains on demand-side
signals. It says nothing about money. The honest position on money is:

  **YouTube RPM is not publicly measurable per niche at this granularity.**
  The only published figure that covers this material is a coarse
  "Education & Science" bucket whose internal spread is 8.4x. Any per-domain
  RPM number is invented.

What DOES set RPM, and what this module measures instead, is one of its two
real inputs:

  AUDIENCE GEOGRAPHY. A view from the United States and a view from India are
  sold to different advertisers at very different prices. A domain whose
  interest is Tier-1-weighted is worth materially more per view than one that
  is globally diffuse, and this effect can outweigh the niche label entirely.

The other input -- advertiser bid density (CPC) -- is NOT measured here,
because no keyword-cost source exists on this machine. See
`research/commercial-axis.md` for that finding. This module does not guess it.

WHAT THE NUMBER IS, EXACTLY -- READ BEFORE QUOTING IT
------------------------------------------------------
Google Trends' "Interest by region" returns, for each country, that country's
interest in the term **normalised against that country's own total search
volume**, then rescaled 0-100 across countries. It is a PER-SEARCHER
PROPENSITY, not a headcount.

Consequences you must not forget:

  * A score of 100 for a small country does NOT mean most searchers are there.
    It means the term is an unusually large share of that country's searches.
  * Therefore this module CANNOT produce "% of the audience that is Tier 1".
    That would need per-country search volumes, which Trends does not expose.
  * What it CAN produce, and all it claims, is a COMPARATIVE skew: is this
    domain more Tier-1-leaning than that domain, measured identically.

The metric reported is:

    tier1_skew = mean(index over Tier-1 basket) / mean(index over Tier-3 basket)

Both baskets are FIXED across all domains, so the comparison between domains
is fair even though the absolute value has no audience-share meaning.

  tier1_skew > 1  -> the term is disproportionately searched in high-RPM markets
  tier1_skew ~ 1  -> globally diffuse
  tier1_skew < 1  -> disproportionately searched in low-RPM markets

The BASKET MEMBERSHIP is a stated convention, not a measurement. It encodes the
widely-reported ordering of YouTube ad rates by market. It is recorded in the
output so a reader can disagree with it and recompute.

FAIRNESS
--------
Every domain is probed with exactly the 8 seeds that produced its demand-side
record in `research/broad_mined.json` -- the same 8, in the same way, no
substitutions. Unequal probing would manufacture a winner, which is the exact
failure mode `proposed-taxonomy.json` calls out.

RULE 0
------
A domain with fewer than MIN_USABLE_SEEDS usable seeds is recorded
`measured: false` with the reason, and its cell is left EMPTY. It is never
filled by extrapolating from the seeds that did work. If NO domain could be
measured at all, this script exits 2 rather than writing an empty pass.

SOURCE
------
  https://trends.google.com/trends/api/explore
  https://trends.google.com/trends/api/widgetdata/comparedgeo
Free, keyless, undocumented -- the endpoints behind the Trends web UI. The
transport, cookie bootstrap and 429 backoff are reused from `trends.py`; this
module adds only the GEO_MAP widget, which that module never requested.

Usage:
  python geography.py                 # all 20 domains, resumable
  python geography.py --domains deep-sea-ocean-science,physics-fundamentals
  python geography.py --pause 5
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trends as T  # noqa: E402  -- transport, backoff and cookie bootstrap

MINED = os.path.join(HERE, "broad_mined.json")
OUT = os.path.join(HERE, "geography.json")
CACHE = os.path.join(HERE, ".geography.cache.json")

COMPAREDGEO = "https://trends.google.com/trends/api/widgetdata/comparedgeo"

# A seed must return usable region data; below this a domain is NOT reported.
MIN_USABLE_SEEDS = 3
# A single seed's region response must name at least this many countries with
# data, or the seed is too thin to say anything about geography.
MIN_COUNTRIES = 8

# --------------------------------------------------------------------------
# The baskets. THIS IS A CONVENTION, NOT A MEASUREMENT.
# --------------------------------------------------------------------------
# Markets consistently reported at the top of YouTube ad rates: the
# English-speaking advertising markets plus Western/Northern Europe and the
# advanced Asian markets.
TIER1 = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom",
    "AU": "Australia", "NZ": "New Zealand", "IE": "Ireland",
    "DE": "Germany", "NL": "Netherlands", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "FI": "Finland", "CH": "Switzerland", "AT": "Austria",
    "BE": "Belgium", "JP": "Japan", "KR": "South Korea", "SG": "Singapore",
}
# Large-population markets consistently reported at the bottom of YouTube ad
# rates. Chosen for population weight, so that a diffuse global term lands
# here rather than nowhere.
TIER3 = {
    "IN": "India", "PK": "Pakistan", "BD": "Bangladesh", "ID": "Indonesia",
    "PH": "Philippines", "VN": "Vietnam", "NG": "Nigeria", "EG": "Egypt",
    "KE": "Kenya", "MA": "Morocco", "DZ": "Algeria", "LK": "Sri Lanka",
    "NP": "Nepal", "MM": "Myanmar", "TZ": "Tanzania", "UG": "Uganda",
}
BASKET_NOTE = (
    "Basket membership is a stated convention encoding the widely-reported "
    "ordering of YouTube ad rates by market. It is NOT measured here and a "
    "reader may disagree with it; the per-country indices are retained in "
    "full so the ratio can be recomputed against a different basket."
)


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------
def region_index(api: "T.Trends", keyword: str) -> tuple[dict | None, str | None]:
    """Per-country interest index for `keyword`, worldwide, last 12 months.

    Returns {geoCode: index} for countries Google reports data for, or an
    error string. Never returns a partial dict silently -- a failure is an
    error, not an empty result.
    """
    req = {"comparisonItem": [{"keyword": keyword, "geo": "", "time": "today 12-m"}],
           "category": 0, "property": ""}
    d, err = api._get(T.EXPLORE, {"hl": api.hl, "tz": api.tz, "req": json.dumps(req)})
    if err:
        return None, f"explore: {err}"
    widgets = {w["id"]: w for w in d.get("widgets", [])}
    gm = widgets.get("GEO_MAP")
    if gm is None:
        return None, "explore returned no GEO_MAP widget (no region data for this term)"

    request = dict(gm["request"])
    request["resolution"] = "COUNTRY"
    g, err = api._get(COMPAREDGEO, {"hl": api.hl, "tz": api.tz,
                                    "req": json.dumps(request),
                                    "token": gm["token"]})
    if err:
        return None, f"comparedgeo: {err}"

    rows = g.get("default", {}).get("geoMapData", [])
    out = {}
    for r in rows:
        has = r.get("hasData") or [False]
        if not has[0]:
            continue
        vals = r.get("value") or []
        if not vals:
            continue
        code = r.get("geoCode")
        if not code:
            continue
        out[code] = vals[0]
    if len(out) < MIN_COUNTRIES:
        return None, (f"only {len(out)} countries returned data "
                      f"(minimum {MIN_COUNTRIES}); term too thin to locate")
    return out, None


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def skew(index: dict) -> dict:
    """Tier-1 propensity relative to Tier-3, for one keyword.

    Countries absent from the response are countries Google reports no data
    for. They are EXCLUDED, not treated as zero: absence of data is not
    absence of interest, and zero-filling would silently reward terms that
    Google simply cannot resolve in poorer markets.
    """
    t1 = {c: index[c] for c in TIER1 if c in index}
    t3 = {c: index[c] for c in TIER3 if c in index}
    if len(t1) < 4 or len(t3) < 4:
        return {"usable": False,
                "reason": (f"basket coverage too thin: {len(t1)} Tier-1 and "
                           f"{len(t3)} Tier-3 countries returned data "
                           f"(minimum 4 each)"),
                "tier1_countries": len(t1), "tier3_countries": len(t3)}
    m1 = statistics.mean(t1.values())
    m3 = statistics.mean(t3.values())
    if m3 <= 0:
        # Every Tier-3 country reported zero interest: a maximally Tier-1
        # term. Recorded honestly rather than dividing by zero.
        return {"usable": True, "tier1_mean": round(m1, 2), "tier3_mean": 0.0,
                "tier1_skew": None,
                "note": "Tier-3 basket mean is 0; ratio undefined but the "
                        "term is maximally Tier-1 weighted",
                "tier1_countries": len(t1), "tier3_countries": len(t3),
                "top_country": max(index, key=index.get)}
    return {"usable": True,
            "tier1_mean": round(m1, 2),
            "tier3_mean": round(m3, 2),
            "tier1_skew": round(m1 / m3, 3),
            "tier1_countries": len(t1), "tier3_countries": len(t3),
            "top_country": max(index, key=index.get)}


def verdict(sk: float | None) -> str:
    if sk is None:
        return "unmeasured"
    if sk >= 2.0:
        return ("strongly Tier-1 weighted -- searched far more per head in "
                "high-ad-rate markets")
    if sk >= 1.3:
        return "Tier-1 leaning"
    if sk >= 0.77:
        return ("globally diffuse -- no meaningful Tier-1 premium from the "
                "topic itself")
    return ("Tier-3 weighted -- searched more per head in low-ad-rate "
            "markets")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domains", default="",
                    help="comma-separated subset; default is all 20")
    ap.add_argument("--pause", type=float, default=2.5,
                    help="seconds between seeds (Trends rate-limits hard)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    mined = json.load(open(MINED, encoding="utf-8"))["domains"]
    wanted = [d.strip() for d in args.domains.split(",") if d.strip()] or list(mined)
    missing = [d for d in wanted if d not in mined]
    if missing:
        print(f"unknown domain(s): {missing}", file=sys.stderr)
        sys.exit(2)

    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}

    api = T.Trends(pause=max(args.pause, 4.0))
    print(f"Geography: {len(wanted)} domains x 8 seeds, worldwide, "
          f"COUNTRY resolution, today 12-m", file=sys.stderr, flush=True)

    results = []
    for dom in wanted:
        seeds = mined[dom]["provenance"]["seeds"]
        print(f"\n{dom}  ({len(seeds)} seeds)", file=sys.stderr, flush=True)
        per_seed = []
        for kw in seeds:
            if kw in cache:
                idx, err = cache[kw].get("index"), cache[kw].get("error")
            else:
                idx, err = region_index(api, kw)
                cache[kw] = {"index": idx, "error": err,
                             "fetched_utc": datetime.now(timezone.utc).isoformat()}
                json.dump(cache, open(CACHE, "w", encoding="utf-8"))
                time.sleep(args.pause)
            rec = {"seed": kw}
            if err or not idx:
                rec.update({"usable": False, "reason": err or "no data"})
            else:
                rec.update(skew(idx))
                rec["countries_with_data"] = len(idx)
            per_seed.append(rec)
            mark = (f"skew {rec['tier1_skew']}" if rec.get("tier1_skew")
                    else rec.get("reason", rec.get("note", "?"))[:60])
            print(f"   {kw!r:45} {mark}", file=sys.stderr, flush=True)

        usable = [s for s in per_seed if s.get("usable") and s.get("tier1_skew")]
        # Seeds where every Tier-3 country returned zero interest have an
        # UNDEFINED ratio, not a missing one: they are the most Tier-1-weighted
        # terms in the set. They cannot enter a median, so dropping them
        # silently would bias a Tier-1-heavy domain DOWNWARDS. They are counted
        # and reported instead, and the verdict is escalated when they dominate.
        maxed = [s for s in per_seed
                 if s.get("usable") and s.get("tier1_skew") is None]
        # Rule 0: too thin is UNMEASURED, never extrapolated.
        if len(usable) + len(maxed) < MIN_USABLE_SEEDS:
            results.append({
                "domain": dom,
                "measured": False,
                "reason": (f"only {len(usable) + len(maxed)} of {len(seeds)} seeds returned "
                           f"usable region data (minimum {MIN_USABLE_SEEDS}); "
                           f"cell left empty rather than extrapolated"),
                "seeds": per_seed,
            })
            print(f"   -> UNMEASURED ({len(usable)}/{len(seeds)} seeds usable)",
                  file=sys.stderr, flush=True)
            continue

        if not usable:
            # Every usable seed had an undefined (maximal) ratio.
            results.append({
                "domain": dom, "measured": True,
                "seeds_usable": 0, "seeds_undefined_max_tier1": len(maxed),
                "seeds_total": len(seeds), "tier1_skew_median": None,
                "verdict": ("strongly Tier-1 weighted -- every usable seed had "
                            "zero measured interest across the whole Tier-3 "
                            "basket, so the ratio is undefined rather than "
                            "large. No number is quoted."),
                "seeds": per_seed,
            })
            continue

        skews = [s["tier1_skew"] for s in usable]
        med = statistics.median(skews)
        v = verdict(med)
        if maxed and len(maxed) >= len(usable):
            v += (f" -- and {len(maxed)} of {len(usable) + len(maxed)} usable "
                  f"seeds had NO measured Tier-3 interest at all, so this "
                  f"median UNDERSTATES the domain's Tier-1 weighting")
        results.append({
            "domain": dom,
            "measured": True,
            "seeds_usable": len(usable),
            "seeds_undefined_max_tier1": len(maxed),
            "seeds_total": len(seeds),
            "tier1_skew_median": round(med, 3),
            "tier1_skew_mean": round(statistics.mean(skews), 3),
            "tier1_skew_min": round(min(skews), 3),
            "tier1_skew_max": round(max(skews), 3),
            "spread_max_over_min": round(max(skews) / min(skews), 2) if min(skews) else None,
            "verdict": v,
            "seeds": per_seed,
        })
        print(f"   -> median skew {med:.2f}  ({verdict(med)})",
              file=sys.stderr, flush=True)

    measured = [r for r in results if r.get("measured")]
    if not measured:
        print("\nRULE 0: no domain could be measured. Writing nothing and "
              "exiting 2 rather than reporting an empty pass.", file=sys.stderr)
        sys.exit(2)

    doc = {
        "_status": "PROPOSAL / measurement. pov/topic-taxonomy.json is unchanged.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/geography.py",
        "source": {
            "explore": T.EXPLORE,
            "comparedgeo": COMPAREDGEO,
            "window": "today 12-m",
            "geo": "worldwide",
            "resolution": "COUNTRY",
        },
        "what_this_measures": (
            "PER-SEARCHER PROPENSITY by country, not audience share. Google "
            "Trends normalises each country's interest against that country's "
            "own total search volume. This file therefore CANNOT say what "
            "fraction of an audience is Tier 1; it can only say which domains "
            "lean more Tier-1 than which others, measured identically."
        ),
        "why_it_is_a_proxy_for_money": (
            "Audience geography is one of the two real inputs to RPM. It is "
            "NOT RPM. The gap between this and realised revenue includes "
            "advertiser bid density, ad load, seasonality, video length and "
            "watch time -- none of which are measured here."
        ),
        "not_measured_here": (
            "Advertiser bid density (CPC). No keyword-cost source exists on "
            "this machine; see research/commercial-axis.md. It is left "
            "unmeasured rather than estimated."
        ),
        "fairness": (
            "Every domain probed with exactly the 8 seeds that produced its "
            "record in research/broad_mined.json -- same seeds, same window, "
            "same resolution, no substitutions."
        ),
        "baskets": {"tier1": TIER1, "tier3": TIER3, "note": BASKET_NOTE},
        "thresholds": {"min_usable_seeds": MIN_USABLE_SEEDS,
                       "min_countries_per_seed": MIN_COUNTRIES,
                       "min_countries_per_basket": 4},
        "requests_made": api.requests,
        "throttle_events": api.throttles,
        "domains_measured": len(measured),
        "domains_unmeasured": len(results) - len(measured),
        "results": sorted(results,
                          key=lambda r: -(r.get("tier1_skew_median") or -1)),
    }
    json.dump(doc, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {args.out}: {len(measured)} measured, "
          f"{len(results) - len(measured)} unmeasured, "
          f"{api.requests} requests, {api.throttles} throttles",
          file=sys.stderr)


if __name__ == "__main__":
    main()
