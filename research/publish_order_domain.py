"""Publish order for ANY domain, from the taxonomy's own mining data.

    python research/publish_order_domain.py --domain space-astronomy
    python research/publish_order_domain.py --domain space-astronomy --candidates-only

WHY THIS EXISTS. `publish_order.py` gates deep sea and `publish_order_materials.py`
gates materials — the second one by importing the first one's gate unchanged, which
is the right relationship. But its 24 candidates are a hand-written list. That is
fine for a domain a person decided to start; it is useless for a domain the
MONTHLY REVIEW decides to start, which is what `loop/domains.lifecycle()` now
does. A promoted domain with no queue is a domain holding weekly slots it cannot
fill, and "someone writes a candidate list by hand" is exactly the human step the
lifecycle was closed to remove.

So this is the same gate, applied to candidates the pipeline already mined:

  CANDIDATES   research/broad_mined.json -> domains[<name>].queries, the
               question-form entries that are neither noise nor already excluded.
               All 20 domains were mined with the same 8-seed autocomplete budget
               (research/mine_broad.py), so every domain in the taxonomy has real,
               autocomplete-confirmed questions waiting. Nothing here is invented:
               each candidate is a string Google's own autocomplete returned.

  EXCLUSIONS   loop/exclusions.decide(), the SAME refusal set every other
               candidate passes through. A topic the channel may not cover is
               killed here, named, rather than discovered late.

  CORPUS       the same domain's full mined query list, which is what
               `demand_probe` measures a candidate's breadth against — the role
               mined_queries.json plays for deep sea. It is a shallower mine than
               deep sea's dedicated pass, and the output says so on every record
               rather than quietly presenting the two as equivalent.

  COMPETITION  research/competition_<slug>.json, written by research/competition.py
               against the YouTube Data API. If it is missing this script RUNS
               competition.py to produce it. It will not invent a denominator, and
               it will not fall back to a gate without one: no key or no quota is a
               named stop (exit 3), not a queue.

  GATE         research/publish_order.py's `gate`, `demand_index`, `combined` and
               `trend_factor`, imported unchanged. Same DEMAND_FLOOR, same
               SATURATION_GAP_CEILING, same geometric score. "A topic that fails the
               gate is killed, not waved through" only means something if a new
               domain's topics face the same gate the old ones did.

OUTPUT  research/publish_order_<slug>.json — the schema loop/batch_queue.py and
        loop/domains.queue_depth() already read, so a promoted domain's queue
        becomes visible to the cadence, the runway and the drafting lane with no
        further wiring.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "loop"))

import exclusions                                              # noqa: E402
from competition import content_tokens                         # noqa: E402
from mine import ENDPOINT, suggest                             # noqa: E402
from publish_order import (                                    # noqa: E402
    DEMAND_FIRM_BELOW, DEMAND_FLOOR, SATURATION_FIRM_AT_OR_BELOW,
    SATURATION_GAP_CEILING, combined, demand_index, gate, reason,
)

BROAD = os.path.join(HERE, "broad_mined.json")
MAX_CANDIDATES = 24        # what materials was gated with; enough for ~12 weeks
MIN_WORDS, MAX_WORDS = 3, 9
MIN_CANDIDATES = 12        # ~12 weeks at one slot; below this, mine deeper

# Deep sea's dedicated deep mine predates the mined_queries_<domain>.json
# convention -- it is simply research/mined_queries.json, the file
# research/publish_order.py reads as its corpus. Naming it here means the
# generic runner uses the RICH corpus for deep sea rather than re-mining it,
# and the exception is written down rather than being a silent miss.
DEEP_MINE_OVERRIDE = {
    "deep-sea-ocean-science": "mined_queries.json",
}

# AUTOCOMPLETE TAILS THAT ARE NOT TOPICS. Autocomplete answers "what is quantum
# physics" with the language someone wants it in, the explainer channel they
# watched, the school year they are in, or the video game the word appears in.
# None of those is an episode, and each one costs ~102 quota units to score.
#
# research/filter.py's NOISE patterns already run at mining time (the `noise`
# flag on every row) and catch songs, shopping and the obvious games; these are
# the tails it does not, seen in the top candidates of four separate domains.
# This is a RANKING filter deciding what is worth measuring — the gate that
# decides what survives is research/publish_order.py's, downstream and
# unchanged. Everything killed here is written to the output so the list can be
# audited rather than trusted.
QUALIFIER_NOISE = re.compile(
    r"\b("
    r"hindi|urdu|tamil|telugu|bangla|bengali|malayalam|marathi|kannada|"
    r"in\s+english|dr\s+binocs|khan\s+sir|dhruv\s+rathee|brian\s+cox|"
    r"neil\s+degrasse|ted[\-\s]ed|crash\s+course|kurzgesagt|"
    r"for\s+(beginners|kids|dummies|class\s*\d+|grade\s*\d+)|"
    r"class\s*\d+|grade\s*\d+|gcse|a\s*level|neet|jee|upsc|"
    r"good\s+career|salary|jobs?\b|degree|course|"
    r"minecraft|roblox|fortnite|wobbly\s+life|jurassic\s+world|"
    r"isla\s+sorna|movie|film|episode\s*\d+|season\s*\d+|"
    r"how\s+it'?s\s+made|discovery\s+uk|huggbees|"
    # 2026-09-05, from the deep-sea pass: craft tutorials, media requests and
    # place-name collisions are not episodes.
    r"how\s+to\s+draw|drawing|colou?ring|papercraft|origami|"
    r"\bvideo\b|\bsong\b|\bgame\b|gold\s+city|minecraft|"
    r"where\s+moses|dead\s+sea|north\s+sea|red\s+sea"
    r")\b", re.I)


def _stem(t: str) -> str:
    """Crude singular form, so `telescope` and `telescopes` are one topic.

    Deliberately not a real stemmer: this only has to make the superset rule
    below see through a plural, and a wrong stem costs one duplicate candidate,
    not a wrong episode.
    """
    if len(t) > 3 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("es") and not t.endswith("ses"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    # competition.content_tokens applies a stemmer of its own, and it is not
    # idempotent across a plural: "telescopes" arrives as "telescop" and
    # "telescope" as "telescope". Dropping a trailing "e" makes the two agree,
    # which is the whole point of the key. It over-stems a few words ("core" ->
    # "cor") and that is harmless: the key is only ever compared with other
    # keys built the same way.
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t

# Exit 3 is this repo's named-stop code: a stop a human is shown, not a crash.
NAMED_STOP = 3


def slug_of_domain(domain: str) -> str:
    return domain.replace("-", "_")


def out_path(domain: str) -> str:
    return os.path.join(HERE, f"publish_order_{slug_of_domain(domain)}.json")


def competition_path(domain: str) -> str:
    return os.path.join(HERE, f"competition_{slug_of_domain(domain)}.json")


def slug_of(query: str) -> str:
    return query.strip().lower().replace("'", "").replace(",", "").replace(" ", "-")


def title_of(query: str) -> str:
    return query[0].upper() + query[1:] + "?"


# Interrogative scaffolding. "how do telescopes work" and "how does a telescope
# work" are one episode; keeping do/does/is/are in the key makes them two.
FRAME = {"how", "why", "what", "when", "where", "which", "who", "do", "does",
         "did", "is", "are", "was", "were", "be", "been", "can", "could",
         "will", "would", "a", "an", "the", "of", "in", "on", "to", "for",
         "and", "or", "it", "its", "you", "your", "really", "actually"}


def _canonical(q: str) -> frozenset:
    """The content tokens a candidate is really asking about."""
    return frozenset(_stem(t) for t in content_tokens(q)
                     if _stem(t) not in FRAME and t not in FRAME)


def _is_narrower_ask(key: frozenset, kept: list) -> bool:
    """True when this candidate is an already-picked question plus qualifiers.

    Autocomplete returns "what is a black hole", then "what is a black hole in
    hindi", "what is a black hole dr binocs", "what is a black hole brian cox".
    They are one episode wearing four hats, and scoring all four would spend
    four times the quota to rank the same topic four times.

    A strict SUPERSET of a question already kept is that same question with a
    language, a creator or a platform bolted on. This catches them without a
    blocklist of names and languages, which would need maintaining forever and
    would still miss the next one. Candidates are walked best-first, so the
    bare form -- the one the most autocomplete probes surfaced -- is the one
    that gets kept.
    """
    return any(key > k for k in kept)


def _rows_of(blob: dict) -> list:
    """Query rows from either miner's output.

    research/mine_broad.py labels each row `question` / `noise` / `excluded`;
    research/mine_domain.py labels it `is_question` and leaves the other two to
    the caller, because it is the deeper single-domain pass and screening is
    this script's job either way. Normalising here means the deep pass is
    filtered by exactly the same rules as the broad one rather than by a
    second, looser copy of them.
    """
    out = []
    for r in blob.get("queries", []):
        out.append({
            "query": r.get("query", ""),
            "question": bool(r.get("question", r.get("is_question"))),
            "noise": bool(r.get("noise")),
            "excluded": bool(r.get("excluded")),
            "probe_hits": int(r.get("probe_hits") or r.get("seed_hits") or 0),
        })
    return out


def deep_mine(domain: str, seeds: list, out_path: str) -> list:
    """Run the deeper single-domain autocomplete pass. Free, no API key.

    The broad mine gave every domain the SAME 8-seed budget so the domains
    could be ranked against each other. That is the right budget for choosing a
    domain and the wrong one for stocking it: space-astronomy yields six usable
    candidates from it, which is six weeks of a slot that runs for years. Deep
    sea got research/mined_queries.json, a dedicated pass, and a promoted domain
    has to get the same or it starts life on a queue that cannot hold it.

    Autocomplete is free, so this is not gated on quota — only the competition
    pass downstream is.
    """
    import tempfile                                          # noqa: PLC0415
    seedfile = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"seeds": seeds}, seedfile)
    seedfile.close()
    print(f"deep-mining {len(seeds)} seed(s) for {domain} (free autocomplete)…",
          flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "mine_domain.py"),
                        seedfile.name, out_path], cwd=HERE, text=True)
    os.unlink(seedfile.name)
    if r.returncode != 0 or not os.path.exists(out_path):
        return []
    with open(out_path, encoding="utf-8") as fh:
        return _rows_of(json.load(fh))


# A seed token this common in the domain's own corpus cannot, on its own,
# prove a candidate belongs to the domain.
GENERIC_DF = 0.25


def generic_tokens(rows: list, seed_tokens: set) -> set:
    """Seed tokens too common in this corpus to discriminate.

    "deep" is deep sea's core word and appears in a quarter of everything the
    miner returned for it -- including "how deep are septic tanks buried",
    "how deep is your love" and "how deep bee gees", all of which shared a
    token with the seeds and were admitted as deep-sea episodes. A token that
    frequent is evidence of the mining query, not of the topic.

    Such a token still counts; it just cannot be the ONLY match.
    """
    if not rows:
        return set()
    df = {t: 0 for t in seed_tokens}
    for r in rows:
        toks = {_stem(t) for t in content_tokens(r["query"])}
        for t in seed_tokens & toks:
            df[t] += 1
    n = len(rows)
    return {t for t, c in df.items() if c / n > GENERIC_DF}


def _screen(rows: list, seed_tokens: set, limit: int,
            seen: list, picked: list, made: set | None = None,
            generic: set | None = None) -> tuple[list, list]:
    """Screen mined rows into `picked`/`seen` in place. Returns (added, killed).

    One screening implementation for both the broad pass and the deep one, so
    the deeper mine cannot end up admitting topics the broad mine would have
    refused.
    """
    added, killed = [], []
    for r in sorted(rows, key=lambda r: (-r["probe_hits"], r["query"])):
        if len(picked) >= limit:
            break
        q = r["query"].strip()
        if not q or not r["question"] or r["noise"] or r["excluded"]:
            continue
        if made and slug_of(q) in made:
            killed.append({"query": q, "killed_by": "ALREADY_PUBLISHED",
                           "rule": "this episode already exists",
                           "matched": slug_of(q)})
            continue
        if not (MIN_WORDS <= len(q.split()) <= MAX_WORDS):
            continue
        if QUALIFIER_NOISE.search(q):
            killed.append({"query": q, "killed_by": "QUALIFIER_NOISE",
                           "rule": "autocomplete tail, not a topic",
                           "matched": QUALIFIER_NOISE.search(q).group(0)})
            continue
        toks = {_stem(t) for t in content_tokens(q)} - FRAME
        hits = toks & seed_tokens
        if not hits:
            killed.append({"query": q, "killed_by": "OFF_DOMAIN",
                           "rule": "shares no vocabulary with the domain seeds",
                           "matched": " ".join(sorted(toks))})
            continue
        if generic and not (hits - generic):
            killed.append({"query": q, "killed_by": "GENERIC_MATCH_ONLY",
                           "rule": "its only domain word is one that matches a "
                                   "quarter of everything the miner returned",
                           "matched": " ".join(sorted(hits))})
            continue
        # TEXT ONLY, NO DOMAIN ARGUMENT. exclusions.decide()'s second parameter
        # is a research/filter.py BUCKET name ("space", "deep-sea-biology"),
        # not a taxonomy domain name -- a different vocabulary that happens to
        # look like the same one. Passing the taxonomy domain refuses EVERY
        # candidate with "Outside admitted domains", which reads exactly like
        # the channel banning the niche. What is wanted is the hard exclusion
        # set, which decide() applies on the text alone.
        d = exclusions.decide(q)
        if not d.admitted:
            killed.append({"query": q, "killed_by": "exclusions.decide",
                           **d.as_dict()})
            continue
        key = _canonical(q)
        if not key or key in seen or _is_narrower_ask(key, seen):
            continue
        # THE BROADER QUESTION WINS. "why is outer space dark" is surfaced by
        # more probes than "why is space dark", so it arrives first -- but the
        # shorter question is the better episode, and they are the same
        # episode. A later candidate that is a strict SUBSET of one already
        # kept replaces it rather than being dropped as a duplicate.
        sub = next((i for i, k in enumerate(seen) if key < k), None)
        if sub is not None:
            killed.append({"query": picked[sub], "killed_by": "BROADER_ASK",
                           "rule": "same question, narrower phrasing",
                           "matched": q})
            seen[sub], picked[sub] = key, q
            if picked[sub] not in added:
                added.append(q)
            continue
        seen.append(key)
        picked.append(q)
        added.append(q)
    return added, killed


def candidates(domain: str, limit: int = MAX_CANDIDATES,
               deep: bool = True) -> tuple[list, list]:
    """Question-form, admitted, deduped candidates for `domain`, best first.

    Ranked by probe_hits -- how many separate autocomplete probes surfaced the
    string -- which is the only demand-ish signal available before the paid
    competition pass, and is used ONLY to choose what is worth spending quota
    on. The gate that decides what survives is the real one, downstream.
    """
    with open(BROAD, encoding="utf-8") as fh:
        blob = json.load(fh)
    if domain not in blob["domains"]:
        raise SystemExit(f"FATAL: {domain} is not in {BROAD}. Mine it first "
                         f"with research/mine_broad.py or mine_domain.py; this "
                         f"script does not invent candidates.")
    entry = blob["domains"][domain]
    rows = _rows_of(entry)

    # THE SEEDS ARE THE DOMAIN'S VOCABULARY. Autocomplete collides: mining
    # "logistics / how things move" with the seed "port" returns "how safe is
    # port forwarding" and "what causes congestion in nose", which are
    # networking and sinus questions wearing a logistics word. A candidate that
    # shares no stemmed token with the seeds that produced it is a collision,
    # not a topic -- and on a pipeline that drafts without asking anyone, a
    # collision that survives the gate becomes an episode.
    seeds = list(entry["provenance"]["seeds"])
    seed_tokens = set()
    for seed in seeds:
        seed_tokens |= {_stem(t) for t in content_tokens(seed)}
    seed_tokens |= {_stem(t) for t in domain.replace("-", " ").split()}
    seed_tokens -= FRAME

    # AN EPISODE ALREADY MADE IS NOT A CANDIDATE. The publish-order files keep
    # a slug after its episode is published -- that is where its score and gate
    # verdict live -- so without this the runner cheerfully proposes topics the
    # channel has already aired. The deep-sea pass returned four of them.
    made: set = set()
    try:
        sys.path.insert(0, os.path.join(ROOT, "loop"))
        import ledger as _led                              # noqa: PLC0415
        made = {r["slug"] for r in _led.load()["published"]}
    except Exception:                                      # never break a run
        made = set()

    generic = generic_tokens(rows, seed_tokens)

    seen: list = []
    picked: list = []
    _, killed = _screen(rows, seed_tokens, limit, seen, picked, made, generic)

    if deep and len(picked) < MIN_CANDIDATES:
        deep_path = os.path.join(
            HERE, DEEP_MINE_OVERRIDE.get(
                domain, f"mined_queries_{slug_of_domain(domain)}.json"))
        if os.path.exists(deep_path):
            with open(deep_path, encoding="utf-8") as fh:
                extra = _rows_of(json.load(fh))
        else:
            extra = deep_mine(domain, seeds + picked, deep_path)
        if extra:
            before = len(picked)
            _, more_killed = _screen(extra, seed_tokens, limit, seen,
                                     picked, made,
                                     generic | generic_tokens(extra, seed_tokens))
            killed += more_killed
            print(f"deep mine: {before} -> {len(picked)} candidate(s)")

    return picked, killed


def ensure_competition(domain: str, queries: list[str], budget: int) -> str:
    """Score `queries` with research/competition.py unless it is already done.

    Runs the real measurement rather than reusing another domain's numbers. A
    missing API key or an exhausted quota returns a named stop, never a queue
    scored against an invented denominator.
    """
    path = competition_path(domain)
    if os.path.exists(path):
        have = {r["query"] for r in json.load(open(path, encoding="utf-8"))
                .get("results", []) if r.get("status") == "ok"}
        if have >= set(queries):
            print(f"competition already scored for all {len(queries)} "
                  f"candidate(s) -> {os.path.basename(path)}")
            return path
        queries = [q for q in queries if q not in have]
        print(f"{len(queries)} candidate(s) still unscored; topping up")

    cmd = [sys.executable, os.path.join(HERE, "competition.py"),
           "--queries", ",".join(queries), "--out", path,
           "--budget", str(budget), "--force"]
    print(f"scoring {len(queries)} candidate(s) through competition.py "
          f"(~{len(queries) * 102} quota units)…", flush=True)
    r = subprocess.run(cmd, cwd=HERE, text=True)
    if r.returncode != 0 or not os.path.exists(path):
        raise SystemExit(NAMED_STOP)
    return path


def demand_probe(query: str, corpus_tokens: list[set], pause: float) -> dict:
    """Free autocomplete demand probe — identical to the materials one."""
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


def build(domain: str, pause: float, budget: int) -> dict:
    cands, killed_early = candidates(domain)
    if not cands:
        raise SystemExit(
            f"FATAL: no admitted question-form candidate for {domain} in "
            f"broad_mined.json. RULE 0 — this script will not write an empty "
            f"queue and exit 0. Mine the domain deeper with mine_domain.py.")
    print(f"{len(cands)} candidate(s) for {domain} "
          f"({len(killed_early)} refused by exclusions before any quota spend)")

    comp_path = ensure_competition(domain, cands, budget)
    comp = json.load(open(comp_path, encoding="utf-8"))
    by_query = {r["query"]: r for r in comp["results"] if r["status"] == "ok"}
    if not by_query:
        raise SystemExit(NAMED_STOP)

    with open(BROAD, encoding="utf-8") as fh:
        corpus = [r["query"] for r in
                  json.load(fh)["domains"][domain]["queries"]]
    corpus_tokens = [content_tokens(c) for c in corpus]

    rows, unmeasured = [], []
    for q in cands:
        if q not in by_query:
            unmeasured.append({"query": q, "status": "no_competition_score"})
            continue
        rows.append({"query": q, "_c": by_query[q],
                     "_d": demand_probe(q, corpus_tokens, pause)})
    if not rows:
        raise SystemExit(NAMED_STOP)

    for r in rows:
        r["_demand_index"] = demand_index(r["_d"], r["_c"])

    out_rows = []
    for r in rows:
        c, d, q = r["_c"], r["_d"], r["query"]
        tm = c["title_match"]
        gap = tm["gap_signal"] if tm["status"] == "ok" else None
        g = gate(r["_demand_index"], gap, d)
        rec = {
            "slug": slug_of(q), "domain": domain, "title": title_of(q),
            "query": q, "gate": g,
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
                "corpus_caveat": (
                    "breadth is measured against research/broad_mined.json's "
                    "8-seed pass for this domain, not a dedicated deep mine. "
                    "It is comparable across domains scored this way and is "
                    "NOT directly comparable to deep sea's mined_queries.json."),
                "provenance": d["provenance"],
            },
            "competition": {
                "opportunity_score": c["opportunity_score"],
                "title_gap": gap,
                "title_coverage_mean": tm["mean_coverage"],
                "strong_match_count": tm["strong_match_count"],
                "results_examined": c["results_examined"],
                "median_views": c["view_profile"]["median"],
            },
        }
        rec["combined"] = combined(r["_demand_index"],
                                   c["opportunity_score"], None)
        rec["reason"] = reason(rec)
        out_rows.append(rec)

    queue = sorted([r for r in out_rows if r["gate"]["verdict"] != "kill"],
                   key=lambda r: -(r["combined"]["score"] or 0))
    dead = [r for r in out_rows if r["gate"]["verdict"] == "kill"]
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "generator": f"research/publish_order_domain.py --domain {domain}",
        "domain": domain,
        "gate_source": "research/publish_order.py, imported unchanged",
        "thresholds": {
            "DEMAND_FLOOR": DEMAND_FLOOR,
            "DEMAND_FIRM_BELOW": DEMAND_FIRM_BELOW,
            "SATURATION_GAP_CEILING": SATURATION_GAP_CEILING,
            "SATURATION_FIRM_AT_OR_BELOW": SATURATION_FIRM_AT_OR_BELOW,
        },
        "candidate_source": ("research/broad_mined.json domains[%s].queries — "
                             "question-form, non-noise, admitted by "
                             "loop/exclusions.decide(), deduplicated by content "
                             "tokens" % domain),
        "refused_before_scoring": killed_early,
        "queue": queue,
        "killed": dead,
        "unmeasured": unmeasured,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--pause", type=float, default=0.4)
    ap.add_argument("--budget", type=int, default=3000,
                    help="quota units competition.py may plan to spend")
    ap.add_argument("--candidates-only", action="store_true",
                    help="print the candidates and spend no quota")
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import domains as D                                       # noqa: PLC0415
    D.require_known(a.domain)                                  # refuses a name
                                                               # not in the
                                                               # taxonomy

    if a.candidates_only:
        cands, killed = candidates(a.domain)
        print(f"{len(cands)} candidate(s) for {a.domain}:")
        for q in cands:
            print(f"  {q}")
        for k in killed:
            print(f"  KILLED  {k['query']}  ({k['rule']})")
        return 0

    blob = build(a.domain, a.pause, a.budget)
    path = out_path(a.domain)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2)
        fh.write("\n")
    n = len(blob["queue"])
    print(f"\n{n} topic(s) survived the gate, {len(blob['killed'])} killed "
          f"-> {os.path.relpath(path, ROOT)}")
    if n == 0:
        # RULE 0: a gate that killed everything has produced no queue, and a
        # domain holding weekly slots with an empty queue must be seen.
        print("NAMED STOP: every candidate failed the gate. The domain holds "
              "slots it cannot fill.", file=sys.stderr)
        return NAMED_STOP
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
