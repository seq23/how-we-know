"""Broad, comparably-seeded autocomplete mining across CANDIDATE domains.

Extends research/mine.py — it reuses that module's `suggest()` and `QUESTION`
rather than reimplementing the endpoint, so there is exactly one place where a
network call to Google's suggest service is made.

WHY THIS EXISTS
---------------
research/topic_backlog.json was mined from 20 deep-sea seeds. It can only tell
you about deep sea. It cannot say whether deep sea was a good CHOICE, because
nothing else was measured. This miner seeds every candidate domain with an
IDENTICAL budget and an identical seed shape, so the per-domain numbers are
comparable to each other.

WHAT THE NUMBERS ARE AND ARE NOT
--------------------------------
Autocomplete is a DEMAND-SHAPE signal, not a volume signal. A returned string
means Google has seen enough of that query to suggest it. It is NOT a search
count, and this module never presents it as one.

  requests            how many suggest calls this domain got (equal by design)
  raw_completions     total strings returned, duplicates included
  unique_queries      distinct strings
  depth               unique_queries / requests -- how much surface a domain has
  question_rate       share of queries in interrogative form (explainer fit)
  method_rate         share matching "how do we/they/scientists know", "how is X
                      measured", "how do we know" -- the channel's actual shape
  noise_rate          share killed by filter.py NOISE (songs, games, shopping)
  exclusion_rate      share colliding with an owner hard exclusion
  clean_unique        distinct queries surviving noise + exclusion + >=3 words

Provenance (endpoint, timestamp, seed, request count) is recorded for every
domain, the way mine.py already does it.

Usage:
  python mine_broad.py [seeds_broad.json] [--pause 0.4] [--out broad_mined.json]
  python mine_broad.py --resume     # continue an interrupted run

Hard-fails (exit 2) rather than emitting an empty or partial-looking result.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Single source of truth for the network call and the question test.
from mine import ENDPOINT, QUESTION, suggest  # noqa: E402

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
DEFAULT_OUT = os.path.join(HERE, "broad_mined.json")
CHECKPOINT = os.path.join(HERE, ".broad_mined.checkpoint.json")
TAXONOMY = os.path.abspath(os.path.join(HERE, "..", "pov", "topic-taxonomy.json"))


# --------------------------------------------------------------------------
# Filter patterns are read OUT OF filter.py rather than copied, so the two
# files cannot drift apart. If filter.py is restructured this hard-fails
# instead of silently scoring with an empty pattern list.
# --------------------------------------------------------------------------
def load_filter_patterns() -> tuple[list[str], list[str]]:
    path = os.path.join(HERE, "filter.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    found: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id in ("NOISE", "BARRED"):
                found[tgt.id] = ast.literal_eval(node.value)
    missing = {"NOISE", "BARRED"} - set(found)
    if missing:
        sys.exit(f"FATAL: could not read {sorted(missing)} out of filter.py; "
                 "refusing to score with an empty pattern list.")
    for k, v in found.items():
        if not v:
            sys.exit(f"FATAL: {k} in filter.py is empty; refusing to score.")
    return found["NOISE"], found["BARRED"]


NOISE_SRC, BARRED_SRC = load_filter_patterns()
NOISE = [re.compile(p, re.I) for p in NOISE_SRC]
BARRED = [re.compile(p, re.I) for p in BARRED_SRC]

# Additional probes for owner hard exclusions that filter.py's BARRED list does
# not cover. Each maps to the exact exclusion string in pov/topic-taxonomy.json.
# These MEASURE exclusion pressure per domain; they do not change the boundary.
EXCLUSION_PROBES: list[tuple[str, str]] = [
    (r"\b(symptom|treatment|diagnos|medicine|medication|dosage|therapy|mental health|depress|anxiety)\b",
     "Medical, health, dietary, supplement or mental-health advice"),
    (r"\b(invest|stock|portfolio|tax|lawsuit|sue|attorney|lawyer|legal advice|settlement)\b",
     "Financial, investment, tax or legal advice"),
    (r"\b(gun|rifle|pistol|ammo|ammunition|bomb|explosive|grenade)\b",
     "Firearms, weapons, explosives"),
    (r"\b(bet|betting|odds|casino|gambl|lottery)\b",
     "Gambling, betting, trading signals"),
    (r"\b(murder|killer|serial killer|victim|homicide|kidnap|missing person)\b",
     "True crime involving identifiable victims or perpetrators"),
    (r"\b(election|president|senator|democrat|republican|liberal|conservative)\b",
     "Active political controversy, elections, partisan framing"),
    (r"\b(god|bible|quran|jesus|religio|creationis)\b",
     "Religion framed as true or false"),
    (r"\b(conspiracy|hoax|flat earth|illuminati|nephilim|paranormal|haunted|ghost|psychic)\b",
     "Conspiracy, cryptid, paranormal, or pseudoscience framed as real"),
    (r"\b(for kids|for children|nursery|toddler|baby shark|cocomelon|preschool)\b",
     "Content directed at children (COPPA exposure)"),
    (r"\b(how to make|diy|at home|challenge|prank|stunt)\b",
     "Dangerous acts, stunts, or anything replicable and harmful"),
    (r"\b(porn|nude|nsfw|sexy|onlyfans)\b",
     "Adult or sexual content"),
    (r"\b(weed|cannabis|cocaine|meth|vape|drug)\b",
     "Drugs, substances, or paraphernalia"),
]
EXCLUSION = [(re.compile(p, re.I), name) for p, name in EXCLUSION_PROBES]

METHOD = re.compile(
    r"how (?:do|did|does|can) (?:we|they|you|scientists|researchers|historians|"
    r"archaeologists|geologists|astronomers) know"
    r"|how do we know"
    r"|how (?:is|are|was|were) .{2,40} (?:measured|calculated|dated|detected|estimated|discovered)"
    r"|how (?:do|did) (?:they|we|scientists) (?:measure|calculate|date|find out|figure out|discover)"
    r"|what (?:is the )?evidence"
    r"|how accurate",
    re.I,
)


def classify(q: str) -> dict:
    noise = any(p.search(q) for p in NOISE)
    hits = [name for p, name in EXCLUSION if p.search(q)]
    if any(p.search(q) for p in BARRED):
        hits.append("filter.py BARRED")
    return {
        "noise": noise,
        "excluded": bool(hits),
        "exclusions": sorted(set(hits)),
        "question": bool(QUESTION.match(q)),
        "method": bool(METHOD.search(q)),
        "words": len(q.split()),
    }


# --------------------------------------------------------------------------
# Mining
# --------------------------------------------------------------------------
def mine_domain(name: str, seeds: list[str], pause: float, alphabet: bool) -> dict:
    """One domain. Equal request budget per domain is the caller's job."""
    started = datetime.now(timezone.utc).isoformat()
    found: dict[str, set[str]] = {}
    requests = 0
    raw = 0
    empty_responses = 0

    probes: list[str] = []
    for seed in seeds:
        probes.append(seed)
        if alphabet:
            probes.extend(f"{seed} {ch}" for ch in ALPHABET)

    for probe in probes:
        res = suggest(probe)
        requests += 1
        if not res:
            empty_responses += 1
        raw += len(res)
        for s in res:
            found.setdefault(s.lower().strip(), set()).add(probe)
        time.sleep(pause)

    queries = []
    for q, srcs in sorted(found.items()):
        c = classify(q)
        queries.append({
            "query": q,
            "probe_hits": len(srcs),
            "probes": sorted(srcs)[:4],
            **c,
        })

    n = len(queries)
    clean = [r for r in queries
             if not r["noise"] and not r["excluded"] and r["words"] >= 3]
    excl_counter: Counter[str] = Counter()
    for r in queries:
        for e in r["exclusions"]:
            excl_counter[e] += 1

    def rate(x: int) -> float:
        return round(x / n, 4) if n else 0.0

    return {
        "domain": name,
        "provenance": {
            "endpoint": ENDPOINT,
            "surface": "youtube_autocomplete (ds=yt, client=firefox, hl=en, gl=us)",
            "method": "each seed probed bare, then suffixed with each letter a-z",
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "pause_seconds": pause,
            "seeds": seeds,
        },
        "metrics": {
            "seed_count": len(seeds),
            "requests": requests,
            "empty_responses": empty_responses,
            "raw_completions": raw,
            "unique_queries": n,
            "depth_per_request": round(n / requests, 3) if requests else 0.0,
            "questions": sum(r["question"] for r in queries),
            "question_rate": rate(sum(r["question"] for r in queries)),
            "method_queries": sum(r["method"] for r in queries),
            "method_rate": rate(sum(r["method"] for r in queries)),
            "noise": sum(r["noise"] for r in queries),
            "noise_rate": rate(sum(r["noise"] for r in queries)),
            "excluded": sum(r["excluded"] for r in queries),
            "exclusion_rate": rate(sum(r["excluded"] for r in queries)),
            "long_tail_4plus_words": sum(r["words"] >= 4 for r in queries),
            "clean_unique": len(clean),
            "clean_rate": rate(len(clean)),
            "multi_probe_confirmed": sum(r["probe_hits"] >= 2 for r in queries),
        },
        "exclusion_breakdown": dict(excl_counter.most_common()),
        "queries": queries,
    }


def reclassify(path: str) -> None:
    """Re-apply classify() to an already-mined file. No network calls.

    Needed because the noise/exclusion patterns live in filter.py and can be
    corrected after a 50-minute mining run. Re-mining to pick up a one-line
    regex fix would be absurd, and re-deriving by hand would not be traceable.
    """
    d = json.load(open(path, encoding="utf-8"))
    for name, dom in d["domains"].items():
        queries = []
        for r in dom["queries"]:
            queries.append({"query": r["query"], "probe_hits": r["probe_hits"],
                            "probes": r["probes"], **classify(r["query"])})
        n = len(queries)
        if n == 0:
            sys.exit(f"FATAL: {name} has zero queries; refusing to reclassify "
                     "an empty domain.")
        clean = [r for r in queries
                 if not r["noise"] and not r["excluded"] and r["words"] >= 3]
        exc: Counter[str] = Counter()
        for r in queries:
            for e in r["exclusions"]:
                exc[e] += 1

        def rate(x: int) -> float:
            return round(x / n, 4)

        m = dom["metrics"]
        m.update({
            "unique_queries": n,
            "questions": sum(r["question"] for r in queries),
            "question_rate": rate(sum(r["question"] for r in queries)),
            "method_queries": sum(r["method"] for r in queries),
            "method_rate": rate(sum(r["method"] for r in queries)),
            "noise": sum(r["noise"] for r in queries),
            "noise_rate": rate(sum(r["noise"] for r in queries)),
            "excluded": sum(r["excluded"] for r in queries),
            "exclusion_rate": rate(sum(r["excluded"] for r in queries)),
            "long_tail_4plus_words": sum(r["words"] >= 4 for r in queries),
            "clean_unique": len(clean),
            "clean_rate": rate(len(clean)),
            "multi_probe_confirmed": sum(r["probe_hits"] >= 2 for r in queries),
        })
        dom["exclusion_breakdown"] = dict(exc.most_common())
        dom["queries"] = queries
    d["reclassified_at"] = datetime.now(timezone.utc).isoformat()
    d["reclassified_note"] = ("Query strings are the ORIGINAL mined responses; "
                              "only the noise/exclusion labels derived from "
                              "filter.py were recomputed. No new network calls.")
    json.dump(d, open(path, "w", encoding="utf-8"), indent=2)
    print(f"reclassified {len(d['domains'])} domains in {path}")


def selftest() -> int:
    """Guards the noise/exclusion patterns against over-matching.

    Exists because r"\\binvest" -- intended for financial advice -- also matched
    "investigation", barring all 270 air-crash-investigation queries and making
    incident-analysis look like the riskiest domain measured. A pattern that
    silently over-matches quietly deletes a whole candidate domain.
    """
    must_exclude = [
        "how to invest in stocks", "best investment 2026",
        "investing for beginners", "stock market crash",
        "bermuda triangle conspiracy", "megalodon is alive",
        "flat earth proof", "cure for cancer",
    ]
    must_survive = [
        "air crash investigation", "ntsb investigation",
        "how do investigators find the cause",
        "forensic investigation of a bridge collapse",
        "how do we know how old the earth is",
        "why do bridges collapse", "how does sonar work",
        "what killed the dinosaurs",
    ]
    if not must_exclude or not must_survive:
        sys.exit("FATAL: selftest has no cases to examine.")
    ok = True
    for q in must_exclude:
        c = classify(q)
        hit = c["excluded"] or c["noise"]
        ok &= hit
        print(f"  [{'PASS' if hit else 'FAIL'}] excluded : {q}")
    for q in must_survive:
        c = classify(q)
        hit = not (c["excluded"] or c["noise"])
        ok &= hit
        print(f"  [{'PASS' if hit else 'FAIL'}] survives : {q}"
              + ("" if hit else f"   <- {c['exclusions']} noise={c['noise']}"))
    n = len(must_exclude) + len(must_survive)
    print(f"\n{'SELFTEST PASSED' if ok else 'SELFTEST FAILED'} "
          f"({n} cases examined)")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seedfile", nargs="?",
                    default=os.path.join(HERE, "seeds_broad.json"))
    ap.add_argument("--pause", type=float, default=0.4,
                    help="seconds between requests (be a good citizen)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-alphabet", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="skip domains already in the checkpoint file")
    ap.add_argument("--only", default=None, help="comma-separated domain names")
    ap.add_argument("--selftest", action="store_true",
                    help="check the filter patterns do not over-match; no network")
    ap.add_argument("--reclassify", metavar="FILE", default=None,
                    help="re-label an existing mined file after a filter.py "
                         "change; no network")
    ap.add_argument("--force", action="store_true",
                    help="re-run even if the output is within its staleness "
                         "window (research/staleness.py)")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())
    if args.reclassify:
        reclassify(args.reclassify)
        return

    import staleness  # noqa: PLC0415
    staleness.guard(args.out, staleness.WINDOWS_DAYS["mine_broad.py"],
                    "research/mine_broad.py", force=args.force)

    spec = json.load(open(args.seedfile, encoding="utf-8"))["domains"]
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        spec = {k: v for k, v in spec.items() if k in want}
        if not spec:
            sys.exit("FATAL: --only matched no domains.")

    # Fairness gate: equal seeding is the whole point. Refuse otherwise.
    sizes = {k: len(v["seeds"]) for k, v in spec.items()}
    if len(set(sizes.values())) != 1:
        sys.exit("FATAL: unequal seeding would produce a fake winner. "
                 f"Seed counts per domain: {sizes}")

    done: dict[str, dict] = {}
    if args.resume and os.path.exists(CHECKPOINT):
        done = json.load(open(CHECKPOINT, encoding="utf-8"))
        print(f"resuming; {len(done)} domain(s) already mined", flush=True)

    todo = [d for d in spec if d not in done]
    per_domain = sizes[next(iter(sizes))] * (1 if args.no_alphabet else 27)
    print(f"{len(todo)} domain(s) to mine, {per_domain} requests each, "
          f"{args.pause}s pause -> ~{len(todo) * per_domain * args.pause / 60:.0f} min",
          flush=True)

    for i, name in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {name} …", flush=True)
        res = mine_domain(name, spec[name]["seeds"], args.pause,
                          alphabet=not args.no_alphabet)
        res["in_current_taxonomy"] = spec[name].get("in_current_taxonomy", False)
        m = res["metrics"]
        if m["unique_queries"] == 0:
            sys.exit(f"FATAL: {name} returned zero completions across "
                     f"{m['requests']} requests. Endpoint is blocked or the "
                     "seeds are dead. Refusing to record an empty domain.")
        print(f"      {m['unique_queries']:>5} unique  "
              f"depth {m['depth_per_request']:.2f}  "
              f"Q {m['question_rate']:.0%}  method {m['method_queries']}  "
              f"noise {m['noise_rate']:.0%}  clean {m['clean_unique']}", flush=True)
        done[name] = res
        json.dump(done, open(CHECKPOINT, "w", encoding="utf-8"))

    if not done:
        sys.exit("FATAL: nothing mined.")

    # A run where most domains came back empty-handed is a blocked endpoint,
    # not a finding. Refuse to emit it.
    empties = sum(1 for d in done.values()
                  if d["metrics"]["empty_responses"] > d["metrics"]["requests"] * 0.5)
    if empties > len(done) * 0.25:
        sys.exit(f"FATAL: {empties}/{len(done)} domains had >50% empty responses. "
                 "The suggest endpoint is throttling. Results would be an "
                 "artefact of rate limiting, not of demand.")

    out = {
        "mined_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
        "surface": "youtube_autocomplete",
        "generator": "research/mine_broad.py (extends research/mine.py)",
        "signal_caveat": (
            "Autocomplete presence is a demand-SHAPE signal. It is not search "
            "volume and no number here may be presented as a search count."
        ),
        "seedfile": os.path.basename(args.seedfile),
        "seeds_per_domain": sizes[next(iter(sizes))],
        "requests_per_domain": per_domain,
        "domain_count": len(done),
        "domains": done,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {args.out}  ({len(done)} domains)")

    rows = sorted(done.values(),
                  key=lambda d: -d["metrics"]["clean_unique"])
    print(f"\n{'domain':<32}{'clean':>7}{'uniq':>7}{'depth':>7}"
          f"{'Q%':>6}{'meth':>6}{'noise%':>8}{'excl%':>7}  tax")
    for d in rows:
        m = d["metrics"]
        print(f"{d['domain']:<32}{m['clean_unique']:>7}{m['unique_queries']:>7}"
              f"{m['depth_per_request']:>7.2f}{m['question_rate']*100:>6.0f}"
              f"{m['method_queries']:>6}{m['noise_rate']*100:>8.1f}"
              f"{m['exclusion_rate']*100:>7.1f}  "
              f"{'current' if d['in_current_taxonomy'] else 'NEW'}")


if __name__ == "__main__":
    main()
