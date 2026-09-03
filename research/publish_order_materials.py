"""Publish order for materials-and-manufacturing candidate episodes.

Sibling to `research/publish_order.py`, not a fork of its logic. It imports
the gate, demand_index, combined-score and trend_factor functions from that
module UNCHANGED — same DEMAND_FLOOR, same SATURATION_GAP_CEILING, same
geometric combined score — and applies them to a second domain's candidates
instead of duplicating the rule. "A topic that fails the gate is killed, not
waved through" only means something if the gate is the SAME gate.

INPUTS
  research/mined_queries_materials.json   research/mine_domain.py (free,
                                           autocomplete), the corpus this
                                           domain's demand_probe measures
                                           breadth against -- the materials
                                           equivalent of mined_queries.json
  research/competition_materials.json     research/competition.py
                                           --queries "...", YouTube Data API
                                           v3 -- the same measurement deep
                                           sea's competition_scripts.json is,
                                           just scored for candidates that
                                           are not scripts yet
  CANDIDATES below                        24 real, autocomplete-confirmed
                                           materials questions (see
                                           mined_queries_materials.json and
                                           research/broad_mined.json's
                                           materials-and-manufacturing
                                           top_questions) -- gated down to
                                           however many pass, reported
                                           alongside whatever the gate kills

OUTPUT: research/publish_order_materials.json, same schema as
research/publish_order.json (queue / killed / unmeasured), domain field added
to every record.

Usage: python publish_order_materials.py [--pause 0.4]
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from competition import content_tokens  # noqa: E402
from mine import ENDPOINT, suggest  # noqa: E402
from publish_order import (  # noqa: E402
    DEMAND_FIRM_BELOW, DEMAND_FLOOR, SATURATION_FIRM_AT_OR_BELOW,
    SATURATION_GAP_CEILING, combined, demand_index, gate, reason,
)

DOMAIN = "materials-and-manufacturing"
OUT = os.path.join(HERE, "publish_order_materials.json")
COMPETITION = os.path.join(HERE, "competition_materials.json")
CORPUS = os.path.join(HERE, "mined_queries_materials.json")

# 24 real, autocomplete-confirmed materials-science questions -- see
# mined_queries_materials.json (research/mine_domain.py, free autocomplete,
# 20 seeds) and research/broad_mined.json's materials-and-manufacturing
# top_questions. Every one traces to a query Google's own autocomplete
# returned; none is invented. Scored by research/competition.py --queries on
# 2026-09-03 into competition_materials.json (2,448 quota units).
CANDIDATES = [
    "why is glass transparent",
    "how are microchips made",
    "what is carbon fiber made of",
    "why is steel so strong",
    "why does stainless steel not rust",
    "how strong is titanium",
    "what is kevlar made of",
    "how does tempered glass shatter",
    "how is 3d printed metal made",
    "how is damascus steel made",
    "what is graphene",
    "how do self-healing materials work",
    "what is a superalloy",
    "what is aerogel made of",
    "how does metal fatigue cause failure",
    "how does heat treating steel work",
    "what is a shape memory alloy",
    "how is a silicon wafer made",
    "why is carbon fiber so strong",
    "how strong is graphene",
    "what is concrete made of",
    "why does old iron not rust",
    "how hot does a welding arc get",
    "what is a semiconductor made of",
]


def slug_of(query: str) -> str:
    return query.strip().lower().replace("'", "").replace(",", "") \
        .replace(" ", "-")


def title_of(query: str) -> str:
    return query[0].upper() + query[1:] + "?"


def demand_probe(query: str, corpus_tokens: list[set[str]], pause: float) -> dict:
    sugg = suggest(query)
    time.sleep(pause)
    toks = content_tokens(query)
    breadth = sum(1 for t in corpus_tokens if toks and toks <= t)
    key, ksugg, kbreadth = None, [], 0
    if toks:
        freq = {t: sum(1 for ct in corpus_tokens if t in ct) for t in toks}
        key = min(freq, key=lambda t: (freq[t], t))
        ksugg = suggest(key)
        time.sleep(pause)
        kbreadth = sum(1 for ct in corpus_tokens if key in ct)
    return {
        "autocomplete_completions": len(sugg),
        "exact_in_autocomplete": query in [s.lower().strip() for s in sugg],
        "corpus_breadth": breadth,
        "key_term": key,
        "key_term_completions": len(ksugg),
        "key_term_corpus_breadth": kbreadth,
        "sample_completions": sugg[:5],
        "provenance": {"endpoint": ENDPOINT, "surface": "youtube_autocomplete",
                       "fetched_utc": datetime.now(timezone.utc).isoformat()},
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=0.4)
    args = ap.parse_args()

    if not os.path.exists(COMPETITION):
        sys.exit(f"FATAL: {COMPETITION} missing. Run "
                 "`python competition.py --queries \"...\" --out "
                 "competition_materials.json` first; this script will not "
                 "invent a denominator.")
    comp = json.load(open(COMPETITION, encoding="utf-8"))
    by_query = {r["query"]: r for r in comp["results"] if r["status"] == "ok"}
    if not by_query:
        sys.exit("FATAL: competition_materials.json contains no scored queries.")

    corpus = [r["query"] for r in
              json.load(open(CORPUS, encoding="utf-8"))["queries"]]
    corpus_tokens = [content_tokens(c) for c in corpus]

    print(f"probing autocomplete demand for {len(CANDIDATES)} materials "
          f"candidates (free)…")
    rows, unmeasured = [], []
    for q in CANDIDATES:
        if q not in by_query:
            unmeasured.append({"query": q, "status": "no_competition_score"})
            continue
        rows.append({"query": q, "_c": by_query[q],
                     "_d": demand_probe(q, corpus_tokens, args.pause)})
    if not rows:
        sys.exit("FATAL: nothing to rank.")

    for r in rows:
        r["_demand_index"] = demand_index(r["_d"], r["_c"])

    out_rows = []
    for r in rows:
        c, d, q = r["_c"], r["_d"], r["query"]
        tm = c["title_match"]
        gap = tm["gap_signal"] if tm["status"] == "ok" else None
        g = gate(r["_demand_index"], gap, d)
        rec = {
            "slug": slug_of(q), "domain": DOMAIN, "title": title_of(q), "query": q,
            "gate": g,
            "demand": {
                "demand_index": r["_demand_index"],
                "autocomplete_completions": d["autocomplete_completions"],
                "exact_in_autocomplete": d["exact_in_autocomplete"],
                "corpus_breadth": d["corpus_breadth"],
                "key_term": d["key_term"],
                "key_term_completions": d["key_term_completions"],
                "key_term_corpus_breadth": d["key_term_corpus_breadth"],
                "sample_completions": d["sample_completions"],
                "caveat": "autocomplete presence, NOT search volume",
                "provenance": d["provenance"],
            },
            "competition": {
                "opportunity_score": c["opportunity_score"],
                "title_gap": gap,
                "title_coverage_mean": tm["mean_coverage"],
                "strong_match_count": tm["strong_match_count"],
                "results_examined": c["results_examined"],
                "median_views": c["view_profile"]["median"],
                "p90_views": c["view_profile"]["p90"],
                "median_subscribers": c["incumbents"]["median_subscribers"],
                "channels_under_100k_subs": c["incumbents"]["under_100k_subs"],
                "median_age_days": c["recency"]["median_age_days"],
                "published_last_365d": c["recency"]["published_last_365d"],
                "interpretation": tm["interpretation"],
                "components": c["opportunity_components"],
                "provenance": c["provenance"],
            },
            "trend": {"status": "not_measured"},
        }
        rec.update(combined(r["_demand_index"], c["opportunity_score"], None)
                   if g["verdict"] == "passed"
                   else {"combined_score": 0.0, "trend_multiplier": None,
                         "trend_note": "not scored; killed by the gate",
                         "formula": "not scored; killed by the gate"})
        rec["reason"] = g["reason"] if g["verdict"] != "passed" else reason(rec)
        out_rows.append(rec)

    passed = [r for r in out_rows if r["gate"]["verdict"] == "passed"]
    killed = [r for r in out_rows if r["gate"]["verdict"].startswith("killed")]
    unmeas = [r for r in out_rows if r["gate"]["verdict"] == "unmeasured"]

    if not out_rows:
        sys.exit("FATAL: no candidates examined.")
    if not passed:
        sys.exit(f"FATAL: the gate excluded all {len(out_rows)} materials "
                 "candidates. Refusing to emit an empty publish order -- that "
                 "is a threshold error, not a finding.")

    passed.sort(key=lambda r: -r["combined_score"])
    queue = []
    for i, r in enumerate(passed, 1):
        e = dict(r)
        e["queue_position"] = i
        e["source"] = "COMBINED_SCORE"
        e["pinned"] = False
        e["overridden_gate_verdict"] = None
        e["gate_overridden"] = False
        queue.append(e)

    out = {
        "_status": "PRODUCTION",
        "_authority": (
            "AUTHORITATIVE publish source for materials-and-manufacturing, "
            "sibling to research/publish_order.json for deep sea. Same gate, "
            "same thresholds, imported not reimplemented."),
        "_schema_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/publish_order_materials.py",
        "domain": DOMAIN,
        "rule": ("Same rule as deep sea: rank candidates by (search demand / "
                 "competition), implemented as a hard GATE on both axes "
                 "(publish_order.gate, imported unchanged) then a geometric "
                 "combined score among survivors."),
        "gate": {
            "principle": ("High demand AND low competition. Failing either "
                          "axis kills the topic; it is not ranked low."),
            "demand_floor": DEMAND_FLOOR,
            "demand_firm_below": DEMAND_FIRM_BELOW,
            "saturation_gap_ceiling": SATURATION_GAP_CEILING,
            "saturation_firm_at_or_below": SATURATION_FIRM_AT_OR_BELOW,
            "thresholds_source": ("Unchanged from research/publish_order.py, "
                                  "imported not recomputed -- the 20-episode "
                                  "deep-sea distribution that set them is not "
                                  "re-derived for a second domain; the same "
                                  "bar applies to both."),
            "excluded": len(killed),
            "passed": len(passed),
        },
        "derived_from": {
            "competition": {"file": "competition_materials.json",
                            "source": comp["source"],
                            "measured_at": comp["measured_at"],
                            "quota_units_spent": comp["quota_units_spent"]},
            "demand": {"endpoint": ENDPOINT, "surface": "youtube_autocomplete",
                       "corpus": "research/mined_queries_materials.json"},
            "candidates": ("24 real autocomplete-confirmed materials "
                           "questions, hand-selected for topical spread "
                           "across the domain (not hand-picked for their "
                           "score) from mined_queries_materials.json and "
                           "research/broad_mined.json's "
                           "materials-and-manufacturing.top_questions."),
        },
        "caveats": [
            "demand_index is built from autocomplete presence and the "
            "materials-specific mined-corpus breadth. It is a demand SHAPE "
            "signal, not search volume.",
            "opportunity_score and title_gap are measured from the live top "
            "20 on a single day (2026-09-03), US/English. Rankings move.",
            "No Trends series was pulled for these candidates; "
            "trend_multiplier is neutral (1.0) throughout, same as any "
            "deep-sea episode with an unusable Trends series.",
        ],
        "episodes_examined": len(out_rows),
        "queue_length": len(queue),
        "killed": [
            {"slug": r["slug"], "domain": DOMAIN, "query": r["query"],
             "verdict": r["gate"]["verdict"], "failed_axes": r["gate"].get("failed"),
             "reason": r["gate"]["reason"],
             "measurement": r["gate"].get("measurement"),
             "what_would_settle_it": r["gate"].get("what_would_settle_it"),
             "demand_index": r["demand"]["demand_index"],
             "opportunity_score": r["competition"]["opportunity_score"],
             "title_gap": r["competition"]["title_gap"]}
            for r in sorted(killed, key=lambda r: (r["gate"]["verdict"],
                                                    -r["demand"]["demand_index"]))],
        "unmeasured": unmeas,
        "queue": queue,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {OUT}\n")
    print(f"{'pos':>4} {'slug':<52}{'comb':>6}{'dem':>6}{'opp':>6}{'gap':>6}")
    for e in queue:
        print(f"{e['queue_position']:>4} {e['slug'][:51]:<52}"
              f"{e['combined_score']:>6.3f}{e['demand']['demand_index']:>6.2f}"
              f"{e['competition']['opportunity_score']:>6.2f}"
              f"{(e['competition']['title_gap'] or 0):>6.2f}")
    print(f"\nKILLED {len(killed)}:")
    for r in out["killed"]:
        print(f"   {r['verdict']:<19} {r['slug'][:50]:<51} "
              f"({','.join(r['failed_axes'])})")


if __name__ == "__main__":
    main()
