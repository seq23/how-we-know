"""Commercial-intent surface per candidate domain -- a PROXY, not RPM.

WHAT THIS IS NOT
----------------
This is **not** RPM, not CPC, and not revenue. It must never be quoted as any
of those. The thing an advertiser actually pays -- cost per click, and through
it the ad rate on a video -- **could not be measured**, because no keyword-cost
source exists on this machine. That negative finding, and the three routes
tested to establish it, are written up in `research/commercial-axis.md`. This
module does not paper over that gap with a guess.

WHAT IT IS
----------
Of the two real inputs to RPM -- advertiser bid density, and audience
geography -- geography is measured in `research/geography.py`. Bid density is
unavailable. What remains measurable, from data already on disk and at zero
new API cost, is the question one step upstream of a bid:

    **Does the audience for this domain express any commercial intent at all,
    in their own words?**

Advertisers bid where buying, hiring and enrolling language appears. A domain
whose searchers only ever ask "why" and "how" is a domain with an audience but
no product behind it -- "curiosity with no product behind it" is a legitimate
and important verdict, and this module is built to be able to return it.

So it counts, across each domain's mined queries, the share carrying a
commercial modifier, broken out by the advertiser category that modifier
implies: purchase, career, education, tooling, or local service.

THE HONEST GAP BETWEEN THIS AND MONEY
-------------------------------------
Three gaps, all of which stay open:

 1. Intent language is not a bid. A query can carry "course" and still have no
    advertiser bidding on it. This measures the SURFACE an advertiser could
    want, not any advertiser wanting it.
 2. The corpus is YOUTUBE autocomplete, not Google web search. Commercial
    intent is systematically UNDER-represented on YouTube relative to web
    search -- people buy on Google and browse on YouTube. Absolute rates here
    are therefore low across the board; only the ORDERING between domains,
    which is measured identically, carries information.
 3. The viewer of an explainer video is not the searcher of a commercial
    query, even when they are the same person in different moods. The link is
    an inference, not an observation.

THE MODIFIER LIST IS A STATED CONVENTION
----------------------------------------
It is not measured or learned. It is recorded in full in the output so a
reader can disagree with it and recount. Terms were chosen to be
unambiguously commercial in isolation; deliberately excluded are broad words
like "best" and "top", which dominate curiosity queries ("best deep sea
documentary") and would manufacture a signal.

FAIRNESS
--------
Every domain contributed exactly 216 autocomplete requests and 8 seeds to
`research/broad_mined.json`; this module reads all 20 identically and applies
the identical modifier list. Rates are computed over each domain's CLEAN
queries (noise and policy-excluded queries removed), which is the same
denominator the demand-side ranking used.

RULE 0
------
A domain whose clean query set is empty is not scored 0 -- it is recorded
unmeasured. If no domain could be read, the script exits 2 rather than
writing an empty pass.

Usage:
  python commercial.py
  python commercial.py --out commercial.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MINED = os.path.join(HERE, "broad_mined.json")
OUT = os.path.join(HERE, "commercial.json")

# --------------------------------------------------------------------------
# The modifier list. A STATED CONVENTION, NOT A MEASUREMENT.
# Each entry is matched on word boundaries against the lowercased query.
# Multi-word entries are matched as phrases.
# --------------------------------------------------------------------------
CATEGORIES: dict[str, dict] = {
    "purchase": {
        "advertiser": "retailers, marketplaces, consumer brands",
        "terms": [
            "buy", "price", "prices", "cost of", "how much does", "how much is",
            "for sale", "cheap", "cheapest", "discount", "deal on", "worth it",
            "worth buying", "amazon", "ebay", "order online",
            "unboxing", "review of",
        ],
    },
    "career": {
        "advertiser": "employers, recruiters, trade bodies, licensing boards",
        "terms": [
            "job", "jobs", "salary", "salaries", "career", "careers", "hiring",
            "apprenticeship", "internship", "how to become", "become a",
            "requirements to become", "licence", "license exam", "certification",
            "certified", "qualification", "resume", "cv for", "interview questions",
        ],
    },
    "education": {
        "advertiser": "course platforms, universities, publishers, ed-tech",
        "terms": [
            "course", "courses", "tutorial", "training",
            "degree", "masters", "phd", "university", "college",
            "syllabus", "curriculum", "textbook", "book on", "study guide",
            "revision", "exam", "gcse", "a level", "learn",
            "for beginners", "crash course", "lecture", "lectures",
        ],
    },
    "tooling": {
        "advertiser": "software vendors, instrument makers, equipment suppliers",
        "terms": [
            "software", "app", "apps", "simulation software",
            "calculator", "toolkit", "equipment", "camera for",
            "telescope for", "microscope for", "kit for",
            "plugin", "cad",
        ],
    },
    "local_service": {
        "advertiser": "contractors, installers, insurers, local suppliers",
        "terms": [
            "near me", "contractor", "repair", "installation",
            "rental", "rent a", "insurance", "quote for", "supplier",
            "manufacturer", "consultant",
        ],
    },
}

# Two kinds of exclusion are recorded here. The first block was excluded before
# any counting, on the reasoning given. The second block was REMOVED AFTER a
# first pass, because inspecting its matches showed them to be false positives;
# the observed false positive is quoted so the removal can be checked rather
# than taken on trust. Removing them lowered the measured rate for deep sea and
# ocean technology in particular -- i.e. the correction cut against the
# comfortable answer, not toward it.
EXCLUDED_ON_PURPOSE = {
    "best": "dominates curiosity queries ('best deep sea documentary'); would "
            "manufacture a signal in every domain",
    "top": "same -- 'top 10' is the commonest explainer title on YouTube",
    "how to": "instructional, not commercial; 'how to' is the base grammar of "
              "the whole explainer category",
    "free": "signals the ABSENCE of a purchase as often as the presence of a "
            "market",
}

REMOVED_AFTER_INSPECTION = {
    "vs / versus / comparison":
        "the commonest explainer format on YouTube, not a purchase "
        "comparison. Observed: 'angler fish vs shark', 'damascus steel vs "
        "bullet', 'container ship vs pirates'. Was 20 of deep sea's 42 hits.",
    "company / companies / service / services":
        "brand and institution collisions, not local demand. Observed: "
        "'anglerfish in animal company' (a VR game), and 'service' collides "
        "with 'national weather service' and 'postal service'.",
    "class / classes":
        "the biological rank. Observed risk across paleontology and natural "
        "history ('what class is a shark'), not enrolment intent.",
    "simulator":
        "games, not professional software. Observed: 'goat simulator 3', "
        "'animal simulator underwater robot octopus parts'.",
    "kit (bare) / gear / store / shop / download / sensor / microscope (bare)":
        "each matched curiosity or unrelated senses. Observed: \"how it's "
        "made kit kat\", 'material science gear institute', 'how does radar "
        "sensor work', 'bioluminescence under microscope'. Retained only in "
        "phrase forms that carry intent ('kit for', 'microscope for').",
    "school":
        "'old school', 'school of fish'. The genuine enrolment signal is "
        "already carried by course / degree / university / exam.",
}


def build_matchers() -> dict[str, list[tuple[str, re.Pattern]]]:
    out = {}
    for cat, spec in CATEGORIES.items():
        pats = []
        for t in spec["terms"]:
            # \b at both ends; a trailing space in a term (e.g. "ap ") is kept
            # meaningful by anchoring the left boundary only.
            if t.endswith(" "):
                pats.append((t, re.compile(r"\b" + re.escape(t.strip()) + r"\b\s")))
            else:
                pats.append((t, re.compile(r"\b" + re.escape(t) + r"\b")))
        out[cat] = pats
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    mined = json.load(open(MINED, encoding="utf-8"))
    domains = mined["domains"]
    matchers = build_matchers()

    results = []
    for dom, rec in domains.items():
        clean = [q for q in rec["queries"]
                 if not q.get("noise") and not q.get("excluded")]
        if not clean:
            results.append({"domain": dom, "measured": False,
                            "reason": "no clean queries in broad_mined.json"})
            continue

        cat_hits: dict[str, list] = {c: [] for c in CATEGORIES}
        any_hit = 0
        term_counts: dict[str, int] = {}
        for q in clean:
            text = q["query"].lower()
            hit_here = False
            for cat, pats in matchers.items():
                for term, pat in pats:
                    if pat.search(text):
                        cat_hits[cat].append(q["query"])
                        term_counts[term] = term_counts.get(term, 0) + 1
                        hit_here = True
                        break  # one hit per category per query
            if hit_here:
                any_hit += 1

        n = len(clean)
        by_cat = {
            c: {"queries": len(v),
                "rate": round(len(v) / n, 4),
                "advertiser": CATEGORIES[c]["advertiser"],
                "examples": v[:6]}
            for c, v in cat_hits.items()
        }
        named = [c for c in CATEGORIES if by_cat[c]["queries"] >= 10]
        results.append({
            "domain": dom,
            "measured": True,
            "clean_queries": n,
            "commercial_queries": any_hit,
            "commercial_rate": round(any_hit / n, 4),
            "zero_commercial_share": round(1 - any_hit / n, 4),
            "by_category": by_cat,
            "named_advertiser_categories": named,
            "top_terms": dict(sorted(term_counts.items(),
                                     key=lambda kv: -kv[1])[:12]),
        })

    measured = [r for r in results if r.get("measured")]
    if not measured:
        print("RULE 0: no domain had any clean query to examine. Exiting 2 "
              "rather than writing an empty pass.", file=sys.stderr)
        sys.exit(2)

    total_examined = sum(r["clean_queries"] for r in measured)
    if total_examined == 0:
        print("RULE 0: examined zero queries. Exiting 2.", file=sys.stderr)
        sys.exit(2)

    doc = {
        "_status": "PROPOSAL / measurement. pov/topic-taxonomy.json is unchanged.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/commercial.py",
        "derived_from": "research/broad_mined.json (no new network requests)",
        "THIS_IS_NOT_RPM": (
            "This file contains no RPM, no CPC and no revenue figure. RPM per "
            "niche is not publicly measurable at this granularity and CPC "
            "could not be measured on this machine at all -- see "
            "research/commercial-axis.md. What is here is the share of a "
            "domain's mined queries that carry commercial-intent language: the "
            "SURFACE an advertiser could want, not evidence that any "
            "advertiser wants it."
        ),
        "known_gaps": [
            "Intent language is not a bid. No bid is observed anywhere in this file.",
            "The corpus is YouTube autocomplete, where commercial intent is "
            "systematically under-represented relative to Google web search. "
            "Absolute rates are therefore low across the board; only the "
            "ordering between domains carries information.",
            "The explainer viewer and the commercial searcher are linked by "
            "inference, not observation.",
        ],
        "fairness": (
            "All 20 domains contributed an identical 8 seeds and 216 "
            "autocomplete requests to broad_mined.json, and all 20 are read "
            "here with the identical modifier list over the identical "
            "denominator (clean queries: noise and policy exclusions removed)."
        ),
        "modifier_list_is_a_convention": (
            "Not measured, not learned. Recorded in full below so a reader may "
            "disagree and recount."
        ),
        "categories": CATEGORIES,
        "deliberately_excluded_terms": EXCLUDED_ON_PURPOSE,
        "removed_after_inspecting_their_matches": REMOVED_AFTER_INSPECTION,
        "queries_examined": total_examined,
        "domains_measured": len(measured),
        "results": sorted(results, key=lambda r: -(r.get("commercial_rate") or -1)),
    }
    json.dump(doc, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"wrote {args.out}: {len(measured)} domains, "
          f"{total_examined} clean queries examined", file=sys.stderr)


if __name__ == "__main__":
    main()
