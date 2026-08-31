"""Mine replacement questions for the saturated "what is a ..." episodes.

THE FINDING THIS ACTS ON
------------------------
Across every measurement in this repo, the openings are "why does ..." and
"how does ..." questions, and the dead ends are "what is a ...". The three
worst-scoring episodes are all the same shape:

    what is a frilled shark    title gap 0.00   20/20 top titles answer it
    what is a yeti crab        title gap 0.00   20/20 top titles answer it
    what is a dumbo octopus    title gap 0.10   18/20 top titles answer it

An identification question has exactly one answer, so the first decent video
ends the query forever. A mechanism question does not: "why does it have hairy
claws" can be answered better. That is why the openings all sit there.

So the subjects are kept and the QUESTIONS are reshaped -- toward mechanism.
The replacements are MINED from autocomplete the same way everything else was,
never invented, then put through the same demand gate.

WHAT THIS FILE DOES NOT DO
--------------------------
It does not write or edit anything in scripts/. It produces the researched
question and its evidence; the authoring lane writes the script later.

Usage:  python rework.py [--pause 0.4]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from competition import content_tokens  # noqa: E402
from mine import ENDPOINT, QUESTION, suggest  # noqa: E402
from mine_broad import classify  # noqa: E402
from publish_order import (DEMAND_FIRM_BELOW, DEMAND_FLOOR,  # noqa: E402
                           demand_index, demand_probe)

OUT = os.path.join(HERE, "rework_candidates.json")

# Same template for every subject, so the three are comparable to each other.
# Mechanism shapes only -- "what is" is the shape being replaced.
TEMPLATES = [
    "why do {plural}", "why does a {singular}", "why are {plural}",
    "how do {plural}", "how does a {singular}", "what makes {plural}",
]
ALPHABET = "abcdefghijklmnopqrstuvwxyz"

SUBJECTS = [
    {"subject": "dumbo octopus", "singular": "dumbo octopus",
     "plural": "dumbo octopuses", "killed_query": "what is a dumbo octopus",
     "killed_slug": "11-what-is-a-dumbo-octopus"},
    {"subject": "yeti crab", "singular": "yeti crab", "plural": "yeti crabs",
     "killed_query": "what is a yeti crab", "killed_slug": "17-what-is-a-yeti-crab"},
    {"subject": "frilled shark", "singular": "frilled shark",
     "plural": "frilled sharks", "killed_query": "what is a frilled shark",
     "killed_slug": "12-what-is-a-frilled-shark"},
]

# A mechanism question asks why/how something WORKS. "how to ..." is an
# instructional shape, not a mechanism shape, and it was letting through
# "how to get dumbo octopus easily in fisch" (a Roblox fishing game) and
# "how to draw a frilled shark". Both start with "how" and neither is remotely
# the question this channel answers. The shape test is therefore a prefix
# whitelist, not a bare startswith("how").
MECHANISM = (
    "why do ", "why does ", "why did ", "why are ", "why is ",
    "how do ", "how does ", "how did ", "how are ", "how is ",
    "what makes ", "what causes ",
)
# Entertainment and craft vocabulary that filter.py's NOISE list does not
# carry. Found by inspecting the first run's output rather than guessed.
REWORK_NOISE = re.compile(
    r"\b(fisch|find the fish|roblox|minecraft|fortnite|draw|drawing|"
    r"colou?ring|origami|drawing|plush|toy|costume|craft|"
    r"how to get|how to catch|how to make|in game|gacha)\b", re.I)


def mine_subject(s: dict, pause: float) -> dict:
    """Autocomplete only. No API quota consumed."""
    found: dict[str, set[str]] = {}
    requests = 0
    probes = []
    for t in TEMPLATES:
        base = t.format(singular=s["singular"], plural=s["plural"])
        probes.append(base)
        probes += [f"{base} {ch}" for ch in ALPHABET]
    for p in probes:
        for r in suggest(p):
            found.setdefault(r.lower().strip(), set()).add(p)
        requests += 1
        time.sleep(pause)
    return {"found": found, "requests": requests, "probes": len(probes)}


CANARY = "why do octopuses"


def canary_ok(pause: float) -> tuple[bool, int]:
    """Proves the endpoint answers mechanism-shaped probes at all.

    Without this, "no mechanism candidates for any subject" is ambiguous: it
    could mean these animals genuinely have no mechanism questions, or it
    could mean the suggest endpoint stopped answering. Those two demand
    opposite actions, so the difference is established rather than assumed.
    """
    n = 0
    for probe in (CANARY, CANARY + " h", "why does a shark"):
        n += len(suggest(probe))
        time.sleep(pause)
    return n > 0, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=0.4)
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args()

    corpus = [r["query"] for r in
              json.load(open(os.path.join(HERE, "mined_queries.json"),
                             encoding="utf-8"))["queries"]]
    corpus_tokens = [content_tokens(c) for c in corpus]

    po = json.load(open(os.path.join(HERE, "publish_order.json"),
                        encoding="utf-8"))
    killed_by_slug = {k["slug"]: k for k in po["killed"]}

    subjects_out = []
    for s in SUBJECTS:
        print(f"mining replacements for {s['subject']!r} …", flush=True)
        m = mine_subject(s, args.pause)
        subj_toks = content_tokens(s["subject"])

        cands = []
        for q, probes in m["found"].items():
            c = classify(q)
            if c["noise"] or c["excluded"]:
                continue
            if not q.lower().startswith(MECHANISM):
                continue                    # mechanism shapes only
            if REWORK_NOISE.search(q):
                continue                    # games, crafts, merchandise
            if not subj_toks <= content_tokens(q):
                continue                    # must actually be about the subject
            if c["words"] < 4:
                continue
            cands.append({"query": q, "probe_hits": len(probes),
                          "words": c["words"]})
        if not cands:
            subjects_out.append({
                **{k: s[k] for k in ("subject", "killed_query", "killed_slug")},
                "status": "NO_CANDIDATES",
                "requests_made": m["requests"],
                "recommendation": (
                    "KILL THE SUBJECT. A comparable mechanism-shaped probe of "
                    f"{m['requests']} autocomplete requests produced no "
                    "mechanism question about this animal that anyone types. "
                    "There is no rework here, only a different way to make the "
                    "same unwatched video."),
            })
            continue

        cands.sort(key=lambda c: (-c["probe_hits"], -c["words"]))
        shortlist = cands[:args.top]
        print(f"   {len(cands)} mechanism candidates, probing top "
              f"{len(shortlist)} for demand…", flush=True)

        scored = []
        for c in shortlist:
            d = demand_probe(c["query"], corpus, args.pause, corpus_tokens)
            di = demand_index(d)
            passes = di >= DEMAND_FLOOR
            scored.append({
                "candidate_query": c["query"],
                "probe_hits": c["probe_hits"],
                "demand_index": di,
                "demand_gate": ("passed" if passes else
                                "killed" if di < DEMAND_FIRM_BELOW
                                else "killed_provisional"),
                "autocomplete_completions": d["autocomplete_completions"],
                "exact_in_autocomplete": d["exact_in_autocomplete"],
                "corpus_breadth": d["corpus_breadth"],
                "sample_completions": d["sample_completions"],
                "competition": None,
                "competition_status": "NAMED_STOP_QUOTA_EXHAUSTED",
            })
        scored.sort(key=lambda r: -r["demand_index"])
        winners = [c for c in scored if c["demand_gate"] == "passed"]

        if winners:
            best = winners[0]
            rec = (f"REWORK as: \"{best['candidate_query']}\". It clears the "
                   f"{DEMAND_FLOOR} demand floor at {best['demand_index']:.3f}, "
                   "where the identification question it replaces was killed "
                   "for saturation. The saturation half of the gate CANNOT be "
                   "confirmed until quota resets -- see competition_status.")
        else:
            rec = (f"KILL THE SUBJECT. {len(scored)} mined mechanism questions "
                   "were probed and none clears the demand floor of "
                   f"{DEMAND_FLOOR} (best {scored[0]['demand_index']:.3f}). "
                   "A rework that fails the gate is not a rework. The animal "
                   "is searched for by name, not by mechanism.")

        subjects_out.append({
            **{k: s[k] for k in ("subject", "killed_query", "killed_slug")},
            "status": "CANDIDATES_FOUND",
            "why_the_original_was_killed": killed_by_slug.get(
                s["killed_slug"], {}).get("reason", "see publish_order.json"),
            "original_measurement": {
                k: killed_by_slug.get(s["killed_slug"], {}).get(k)
                for k in ("title_gap", "demand_index", "opportunity_score")},
            "mining": {"endpoint": ENDPOINT, "surface": "youtube_autocomplete",
                       "templates": TEMPLATES, "requests_made": m["requests"],
                       "mechanism_candidates_found": len(cands)},
            "candidates": scored,
            "recommendation": rec,
        })

    if not subjects_out:
        sys.exit("FATAL: no subjects processed.")
    if all(s["status"] == "NO_CANDIDATES" for s in subjects_out):
        ok, n = canary_ok(args.pause)
        if not ok:
            sys.exit("FATAL: every subject produced zero candidates AND the "
                     "canary probe returned nothing either. That is an "
                     "endpoint failure, not a finding; refusing to recommend "
                     "killing three subjects on it.")
        print(f"canary returned {n} completions: the endpoint is live, so the "
              "empty result for all three subjects is a real finding.")
        for so in subjects_out:
            so["canary"] = {
                "probe": CANARY, "completions": n,
                "meaning": ("The suggest endpoint answers mechanism-shaped "
                            "probes normally. Zero candidates for this subject "
                            "is therefore a property of the subject, not a "
                            "failed request.")}

    out = {
        "_status": "RESEARCH OUTPUT. No file in scripts/ was created or edited.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/rework.py",
        "the_pattern": (
            "Every opening in this dataset is a 'why does...' or 'how does...' "
            "question and every dead end is a 'what is a...'. An identification "
            "question has one answer, so the first decent video closes it "
            "permanently; a mechanism question can always be answered better. "
            "These three subjects are kept and their questions reshaped."),
        "method": (
            "Replacements are MINED from Google autocomplete using one "
            "identical mechanism-shaped template set per subject, then put "
            "through the same demand gate as every other candidate. Nothing "
            "here is invented."),
        "demand_floor": DEMAND_FLOOR,
        "competition_named_stop": {
            "name": "YOUTUBE_QUOTA_EXHAUSTED",
            "what_is_missing": (
                "The saturation half of the gate for these candidates. "
                "search.list costs 100 units and the 10,000/day allowance was "
                "spent scoring the 20 existing episodes (2,040) and 74 domain "
                "queries (7,548)."),
            "consequence": (
                "Every candidate below carries competition: null. A "
                "recommendation to rework rests on demand evidence ALONE and "
                "is not final until the replacement question is shown to be "
                "unsaturated."),
            "how_it_clears": (
                "Quota resets at midnight Pacific. Re-run "
                "`python weekly.py` and the candidates are scored "
                "automatically; no code change is needed."),
        },
        "subjects": subjects_out,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {OUT}\n")
    for s in subjects_out:
        print(f"== {s['subject']}  (was: {s['killed_query']})")
        for c in s.get("candidates", [])[:4]:
            print(f"   {c['demand_index']:.3f} {c['demand_gate']:<19} "
                  f"{c['candidate_query']}")
        print(f"   -> {s['recommendation']}\n")


if __name__ == "__main__":
    main()
