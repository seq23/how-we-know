"""Derive research/proposed-taxonomy.json from measurements. Nothing reasoned.

INPUTS (all produced by scripts in this directory, all traceable to a real
response from a real endpoint):
    broad_mined.json     research/mine_broad.py   -- comparably-seeded demand
    trends.json          research/trends.py       -- direction + seasonality
    competition.json     research/competition.py  -- OR competition_stop.json

OUTPUT:
    proposed-taxonomy.json

The current pov/topic-taxonomy.json is READ ONLY here. Its ten admitted domains
were reasoned from adjacency, not measured; this file reports what the data says
about each of them and what it says about domains that were never considered.
Its sixteen hard exclusions are the owner's risk boundaries and are copied
through byte-for-byte -- they are not derived, not ranked, and not revisable by
a measurement.

RANKING HONESTY
---------------
The taxonomy's own selection rule is "rank candidates by (search demand /
competition)". Only the numerator is measurable today. The ranking this file
emits is therefore named `demand_side_rank`, and every record carries
`competition: null` with the named stop attached. A domain is never promoted or
demoted on an imagined competition value.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TAX = os.path.abspath(os.path.join(HERE, "..", "pov", "topic-taxonomy.json"))
OUT = os.path.join(HERE, "proposed-taxonomy.json")


def read(path: str, required: bool = True):
    if not os.path.exists(path):
        if required:
            sys.exit(f"FATAL: {path} missing. Run the miner first; this script "
                     "will not invent inputs.")
        return None
    return json.load(open(path, encoding="utf-8"))


def norm(vals: dict[str, float]) -> dict[str, float]:
    """Min-max across MEASURED domains only. Comparable because seeding was."""
    lo, hi = min(vals.values()), max(vals.values())
    if hi == lo:
        return {k: 0.5 for k in vals}
    return {k: (v - lo) / (hi - lo) for k, v in vals.items()}


def main() -> None:
    broad = read(os.path.join(HERE, "broad_mined.json"))
    method_pass = read(os.path.join(HERE, "broad_method.json"), required=False)
    trends = read(os.path.join(HERE, "trends.json"), required=False)
    comp = read(os.path.join(HERE, "competition.json"), required=False)
    stop = read(os.path.join(HERE, "competition_stop.json"), required=False)
    tax = read(TAX)

    domains = broad["domains"]
    if len(domains) < 5:
        sys.exit(f"FATAL: only {len(domains)} domains mined. A comparison needs "
                 "the full comparably-seeded set; refusing to rank a fragment.")

    # Fairness gate: an unequal request budget invalidates every comparison.
    budgets = {d["metrics"]["requests"] for d in domains.values()}
    if len(budgets) != 1:
        sys.exit(f"FATAL: unequal request budgets {budgets}. The comparison "
                 "would be an artefact of seeding, not of demand.")

    # The method pass is a SEPARATE, equally-budgeted run whose seeds are method
    # stems ("how do we know about X") rather than topic nouns. The general pass
    # cannot reach that surface, and this channel's whole premise lives on it.
    mdom: dict[str, dict] = {}
    if method_pass:
        mb = {d["metrics"]["requests"] for d in method_pass["domains"].values()}
        if len(mb) != 1:
            sys.exit(f"FATAL: unequal method-pass request budgets {mb}.")
        if set(method_pass["domains"]) != set(domains):
            sys.exit("FATAL: method pass and general pass cover different "
                     "domain sets; the comparison would not be like-for-like.")
        mdom = method_pass["domains"]

    # Real competition, if research/competition.py has run.
    cpath = os.path.join(HERE, "competition.json")
    comp_dom, comp_meta = {}, None
    if os.path.exists(cpath):
        cj = json.load(open(cpath, encoding="utf-8"))
        comp_dom = cj.get("domain_summary", {})
        comp_meta = {"file": "research/competition.json",
                     "source": cj["source"],
                     "measured_at": cj["measured_at"],
                     "quota_units_spent": cj["quota_units_spent"],
                     "candidates_scored": cj["candidates_scored"],
                     "candidates_unmeasured": cj["candidates_unmeasured"]}

    trend_by_domain: dict[str, dict] = {}
    if trends:
        for r in trends["results"]:
            if r.get("domain") and r["status"] == "ok":
                trend_by_domain.setdefault(r["domain"], r)

    # ---- components, all measured ------------------------------------
    surface = {k: d["metrics"]["clean_unique"] for k, d in domains.items()}
    depth = {k: d["metrics"]["depth_per_request"] for k, d in domains.items()}
    explainer = {k: d["metrics"]["question_rate"] for k, d in domains.items()}
    if mdom:
        method = {k: mdom[k]["metrics"]["method_queries"] for k in domains}
        method_src = ("research/broad_method.json (dedicated method-stem pass, "
                      f"{next(iter(mdom.values()))['metrics']['requests']} "
                      "requests per domain)")
    else:
        method = {k: d["metrics"]["method_queries"] for k, d in domains.items()}
        method_src = "research/broad_mined.json (general pass)"
    purity = {k: 1 - d["metrics"]["noise_rate"] for k, d in domains.items()}
    safety = {k: 1 - d["metrics"]["exclusion_rate"] for k, d in domains.items()}

    n_surface, n_depth = norm(surface), norm(depth)
    n_expl, n_meth = norm(explainer), norm(method)
    n_pure, n_safe = norm(purity), norm(safety)

    WEIGHTS = {
        "demand_surface": 0.30,   # how many distinct usable queries exist
        "depth": 0.15,            # completions per identical request budget
        "explainer_fit": 0.15,    # share in question form
        "method_fit": 0.15,       # "how do we know" shape -- the channel's premise
        "noise_purity": 0.15,     # autocomplete not dominated by songs/games
        "exclusion_safety": 0.10,  # low collision with owner hard exclusions
    }

    _raw_demand = {}
    for k in domains:
        parts = {"demand_surface": n_surface[k], "depth": n_depth[k],
                 "explainer_fit": n_expl[k], "method_fit": n_meth[k],
                 "noise_purity": n_pure[k], "exclusion_safety": n_safe[k]}
        _raw_demand[k] = sum(parts[p] * w for p, w in WEIGHTS.items())
    _lo, _hi = min(_raw_demand.values()), max(_raw_demand.values())
    _demand_norm = {k: ((v - _lo) / (_hi - _lo) if _hi > _lo else 0.5)
                    for k, v in _raw_demand.items()}

    # demand / competition, the taxonomy's own rule, in geometric form.
    # Same reasoning as research/publish_order.py: "high demand AND low
    # competition" is an AND, so a near-zero on either axis must drag the
    # result down. Domains with no competition measurement get None, never an
    # imputed value.
    def _combined(name: str):
        if name not in comp_dom:
            return {"score": None,
                    "status": "unscored_competition_not_measured"}
        opp = comp_dom[name].get("mean_opportunity")
        if opp is None:
            return {"score": None, "status": "unscored_no_opportunity"}
        dem = _demand_norm[name]
        return {"score": round((dem * opp) ** 0.5, 4),
                "demand_component": round(dem, 4),
                "opportunity_component": opp,
                "queries_scored": comp_dom[name]["queries_scored"],
                "formula": "sqrt(demand_side_score_normalised * mean_opportunity)",
                "status": "scored"}

    records = []
    for k, d in domains.items():
        m = d["metrics"]
        parts = {
            "demand_surface": n_surface[k], "depth": n_depth[k],
            "explainer_fit": n_expl[k], "method_fit": n_meth[k],
            "noise_purity": n_pure[k], "exclusion_safety": n_safe[k],
        }
        score = sum(parts[p] * w for p, w in WEIGHTS.items())
        t = trend_by_domain.get(k)
        trend_rec = None
        if t:
            tw = t.get("twelve_month", {}).get("direction", {})
            se = t.get("five_year", {}).get("seasonality", {})
            yo = t.get("five_year", {}).get("year_over_year", {})
            rel = t.get("twelve_month", {}).get("reliability", {})
            trend_rec = {
                "probe_keyword": t["keyword"],
                "geo": t["geo"],
                "series_usable": rel.get("usable"),
                "reliability_flags": rel.get("flags", []),
                "direction_12m": (tw.get("label") if rel.get("usable", True)
                                  else "NOT_QUOTABLE"),
                "slope_pct_of_mean_per_week": tw.get("slope_pct_of_mean_per_step"),
                "last13w_vs_prior13w_pct": tw.get("last13_vs_prior13_pct"),
                "yoy_change_pct": yo.get("yoy_change_pct") if yo.get("status") == "ok" else None,
                "seasonality_strength": se.get("strength"),
                "peak_month": se.get("modal_peak_month") or se.get("peak_month"),
                "peak_month_consistency": se.get("peak_month_consistency"),
                "per_year_peak_month": se.get("per_year_peak_month"),
                "summer_peaking": se.get("summer_peaking"),
                "breakout_related_queries": t.get("breakout_count"),
                "rising_examples": [r["query"] for r in
                                    (t.get("related_queries") or {}).get("rising", [])[:5]],
                "verdict": t.get("verdict"),
                "scale_caveat": "relative normalised index, not search volume",
            }
        records.append({
            "domain": k,
            "in_current_taxonomy": d["in_current_taxonomy"],
            "demand_side_score": round(score, 4),
            "score_components_normalised": {p: round(v, 3) for p, v in parts.items()},
            "measured": {
                "requests": m["requests"],
                "unique_queries": m["unique_queries"],
                "clean_unique": m["clean_unique"],
                "depth_per_request": m["depth_per_request"],
                "question_rate": m["question_rate"],
                "method_queries": method[k],
                "method_queries_source": method_src,
                "method_pass": ({
                    "seeds": mdom[k]["provenance"]["seeds"],
                    "requests": mdom[k]["metrics"]["requests"],
                    "unique_queries": mdom[k]["metrics"]["unique_queries"],
                    "method_queries": mdom[k]["metrics"]["method_queries"],
                    "method_rate": mdom[k]["metrics"]["method_rate"],
                    "clean_unique": mdom[k]["metrics"]["clean_unique"],
                } if mdom else {"status": "not_run"}),
                "noise_rate": m["noise_rate"],
                "exclusion_rate": m["exclusion_rate"],
                "multi_probe_confirmed": m["multi_probe_confirmed"],
            },
            "exclusion_breakdown": d["exclusion_breakdown"],
            "trend": trend_rec or {"status": "not_measured"},
            "competition": (
                {**comp_dom[k],
                 "measured": True,
                 "caveat": ("Sample sizes are deliberately unequal: quota was "
                            "concentrated on the domains that could move the "
                            "ranking. A 1-2 query domain is a smoke test.")}
                if k in comp_dom else
                {"measured": False,
                 "status": "NOT_MEASURED",
                 "why": "quota was spent on higher-ranked domains and the 20 "
                        "existing scripts; not scored as zero"}),
            "demand_over_competition": _combined(k),
            "top_method_queries": [
                q["query"] for q in
                sorted((x for x in (mdom[k] if mdom else d)["queries"]
                        if x["method"] and not x["noise"] and not x["excluded"]),
                       key=lambda x: -x["probe_hits"])][:10],
            "top_questions": [q["query"] for q in
                              sorted((x for x in d["queries"] if x["question"]
                                      and not x["noise"] and not x["excluded"]),
                                     key=lambda x: -x["probe_hits"])][:8],
            "provenance": d["provenance"],
        })

    records.sort(key=lambda r: -r["demand_side_score"])
    for i, r in enumerate(records, 1):
        r["demand_side_rank"] = i

    cur = set(tax["admitted_domains"])
    supported = [r["domain"] for r in records if r["in_current_taxonomy"]
                 and r["demand_side_rank"] <= len(cur)]
    unsupported = [r["domain"] for r in records if r["in_current_taxonomy"]
                   and r["demand_side_rank"] > len(cur)]
    missed = [r["domain"] for r in records if not r["in_current_taxonomy"]
              and r["demand_side_rank"] <= len(cur)]

    out = {
        "_status": "PROPOSAL. Not approved. pov/topic-taxonomy.json is unchanged.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/propose.py",
        "derived_from": {
            "demand": {"file": "research/broad_mined.json",
                       "mined_at": broad["mined_at"],
                       "endpoint": broad["endpoint"],
                       "seeds_per_domain": broad["seeds_per_domain"],
                       "requests_per_domain": broad["requests_per_domain"],
                       "caveat": broad["signal_caveat"]},
            "method_surface": ({"file": "research/broad_method.json",
                                "mined_at": method_pass["mined_at"],
                                "seeds_per_domain": method_pass["seeds_per_domain"],
                                "requests_per_domain": method_pass["requests_per_domain"],
                                "note": "identical method-stem template per domain"}
                               if method_pass else {"status": "not_run"}),
            "trend": ({"file": "research/trends.json",
                       "fetched_at": trends["fetched_at"],
                       "source": trends["source"],
                       "probes_ok": trends["probes_ok"],
                       "probes_unavailable": trends["probes_unavailable"],
                       "caveat": trends["scale_caveat"]}
                      if trends else {"status": "not_measured"}),
            "competition": (
                {"file": "research/competition.json",
                 "candidates_scored": comp["candidates_scored"]} if comp
                else {"status": "NAMED_STOP",
                      "detail": stop or "research/competition_stop.json absent; "
                                        "run research/competition.py"}),
        },
        "method": {
            "fairness": ("Every domain received an identical seed budget "
                         f"({broad['seeds_per_domain']} seeds) and an identical "
                         f"request budget ({broad['requests_per_domain']} "
                         "autocomplete requests: each seed bare, then suffixed "
                         "a-z). Unequal seeding would manufacture a winner."),
            "ranking": ("demand_side_score = weighted sum of min-max normalised "
                        "components across the measured domains."),
            "weights": WEIGHTS,
            "what_this_ranking_is_not": (
                "It is NOT the taxonomy's selection rule. That rule is "
                "(search demand / competition). The denominator is unmeasured "
                "until a YouTube Data API key exists, so every record carries "
                "competition: null. A domain that ranks high here may still be "
                "saturated."
            ),
            "seed_hits_correction": {
                "claim": ("research/topic_backlog.json ranks on `seed_hits`, the "
                          "number of the author's own seed strings that surfaced "
                          "a query. It is not search volume and it is not even "
                          "multi-seed confirmation."),
                "evidence": ("Measured over research/mined_queries.json: 457 "
                             "queries have seed_hits >= 2, and for 372 of them "
                             "(81%) every recorded hit comes from a-z variants "
                             "of ONE base seed. 'how do scientists know so much' "
                             "scores 26 because 26 letter-suffixed forms of the "
                             "single seed 'how do scientists know' each returned "
                             "it. seed_hits therefore measures how short a seed "
                             "prefix was, not how much anyone wants the video. "
                             "(The stored `seeds` list is truncated to 4 entries, "
                             "so 372 is a lower bound.)"),
                "consequence": ("Any backlog ordering built on seed_hits is "
                                "ordered by seed-string length. It should be "
                                "re-ranked."),
                "here": ("Recorded as probe_hits and used only as a weak "
                         "tie-break flag, never as a volume proxy."),
            },
        },
        "summary": {
            "domains_measured": len(records),
            "current_taxonomy_size": len(cur),
            "current_domains_supported_by_data": supported,
            "current_domains_NOT_supported_by_data": unsupported,
            "domains_missed_by_the_current_taxonomy": missed,
        },
        "hard_exclusions": tax["hard_exclusions"],
        "hard_exclusions_note": (
            "Copied verbatim from pov/topic-taxonomy.json. These are the owner's "
            "risk boundaries. No measurement in this file revises them, and a "
            "domain scoring well while colliding with one is a NAMED STOP for "
            "owner review, not an admission."
        ),
        "content_rules": tax["content_rules"],
        "escalation": tax["escalation"],
        "new_niche_requirement": tax["new_niche_requirement"],
        "ranked_domains": records,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"wrote {OUT}\n")
    print(f"{'#':>3} {'domain':<34}{'score':>7}{'clean':>7}{'depth':>7}"
          f"{'Q%':>5}{'meth':>6}{'noise%':>8}{'excl%':>7}{'trend':>11}  tax")
    for r in records:
        m, t = r["measured"], r["trend"]
        print(f"{r['demand_side_rank']:>3} {r['domain']:<34}"
              f"{r['demand_side_score']:>7.3f}{m['clean_unique']:>7}"
              f"{m['depth_per_request']:>7.2f}{m['question_rate']*100:>5.0f}"
              f"{m['method_queries']:>6}{m['noise_rate']*100:>8.1f}"
              f"{m['exclusion_rate']*100:>7.1f}"
              f"{str(t.get('direction_12m', '-')):>11}  "
              f"{'current' if r['in_current_taxonomy'] else 'NEW'}")
    print(f"\ncurrent domains NOT in the top {len(cur)}: {unsupported}")
    print(f"domains missed by the current taxonomy:    {missed}")


if __name__ == "__main__":
    main()
