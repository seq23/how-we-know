"""Publish order for the 20 scripts that already exist.

WHY THIS FILE EXISTS
--------------------
scripts/*.md were chosen on demand signal alone, before any competition data
existed, and partly on `seed_hits` -- a metric that turned out to measure how
short a seed prefix was rather than how much anyone wanted the video (see
research/proposed-taxonomy.json, method.seed_hits_correction). The publish order
is being decided this week, so those 20 questions are re-ranked here on the
taxonomy's own rule:

    rank candidates by (search demand / competition)

Ratio form. `opportunity_score` from research/competition.py is the inverse of
competition -- room for a new entrant -- so demand / competition is expressed as

    publish_score = demand_index * opportunity_score

with both factors on 0..1. Title coverage carries 50% of opportunity, which
makes it the single heaviest term in the whole ordering. That is deliberate: a
query whose top-20 titles do not actually answer it is the strongest available
evidence that nobody has made the definitive video, and it is the one thing raw
view counts cannot tell you.

INPUTS (all real responses, all traceable)
  scripts/*.md                 the episode questions (READ ONLY)
  competition_scripts.json     research/competition.py, YouTube Data API v3
  mined_queries.json           research/mine.py, Google autocomplete
  trends_scripts.json          research/trends.py, optional

DEMAND, HONESTLY
----------------
There is no free source of absolute search volume, so `demand_index` is a blend
of three REAL observations, each stated separately in the output:
  * autocomplete_completions -- how many completions Google returns for the
    exact question. A question Google extends is a question people type.
  * exact_in_autocomplete    -- whether the question comes back as its own
    suggestion. Strong evidence it is a real typed query, not a construction.
  * corpus_breadth           -- how many distinct mined queries share all of
    the question's content words. Breadth of the family behind the question.
None of these is a search count and none is presented as one.

Usage:  python publish_order.py [--pause 0.4]
Hard-fails rather than emitting an empty or partial-looking order.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from competition import content_tokens, script_questions  # noqa: E402
from mine import ENDPOINT, suggest  # noqa: E402

OUT = os.path.join(HERE, "publish_order.json")


def demand_probe(query: str, corpus: list[str], pause: float,
                 corpus_tokens: list[set[str]] | None = None) -> dict:
    """Free autocomplete demand evidence. No API quota is consumed."""
    sugg = suggest(query)
    time.sleep(pause)
    toks = content_tokens(query)
    ctoks = corpus_tokens or [content_tokens(c) for c in corpus]
    breadth = sum(1 for t in ctoks if toks and toks <= t)

    # A low score on the exact phrasing does not mean the SUBJECT is dead --
    # it may only mean this wording is not how anyone asks. Probing the
    # query's rarest content word separates the two, which is the difference
    # between retitling an episode and killing it.
    key = None
    if toks:
        freq = {t: sum(1 for ct in ctoks if t in ct) for t in toks}
        key = min(freq, key=lambda t: (freq[t], t))
    ksugg, kbreadth = [], 0
    if key:
        ksugg = suggest(key)
        time.sleep(pause)
        kbreadth = sum(1 for ct in ctoks if key in ct)
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


def _span(v: float | None, lo_log: float, hi_log: float) -> float:
    """Map a count onto 0..1 across a FIXED absolute log range.

    Fixed anchors, not min-max of the current sample: a threshold that moves
    with the sample cannot be compared between weekly runs, and the weekly
    entrypoint depends on this being stable.
    """
    if not v or v <= 0:
        return 0.0
    lv = math.log10(v)
    return max(0.0, min(1.0, (lv - lo_log) / (hi_log - lo_log)))


def demand_index(d: dict, comp: dict | None = None) -> float:
    """Demand on 0..1. AUDIENCE-LED, not autocomplete-led.

    WHY THIS WAS REBUILT
    --------------------
    The first version of this function was 2/3 autocomplete: how many
    completions the suggest endpoint returned for one exact phrasing, plus
    whether the phrasing came back as its own suggestion. That is not a
    measurement of demand. It measures prefix-matching behaviour at one
    endpoint at one moment, and it killed
    'how do people reach challenger deep' -- a 0.95 title gap, one of the
    strongest openings in the whole dataset -- on the evidence of two
    completions.

    That is exactly the error already diagnosed and killed in `seed_hits`: an
    artefact of the collection method read as a property of the world. Having
    caught it there, repeating it here was the same mistake wearing a
    different hat.

    The primary signal is now AUDIENCE: the view counts of the top 20 results
    that YouTube actually returns for the query. Those are real people
    watching real videos that answer this question, already paid for with
    search quota. A query whose incumbents pull a 333k median and a 13.4M p90
    has a demonstrated audience whatever autocomplete does.

    Weighting, and why:
      0.55 audience        real consumption; the only signal here that counts
                           people rather than endpoint behaviour
      0.30 corpus_breadth  how large the query family is across 2,653 mined
                           queries -- aggregated over many probes, so far less
                           sensitive to one prefix than a single completion
                           count
      0.15 autocomplete    completions and exact self-match. Kept because a
                           phrasing Google echoes back IS weak evidence the
                           phrasing is real, but demoted to a tiebreaker
                           because that is all it can support.

    CAVEAT, stated in the output: incumbent views measure the audience for the
    SUBJECT AREA, not the exact-phrase search volume. Where title_gap is high
    the views partly belong to adjacent videos. That is still evidence the
    topic draws an audience, which is the question the gate asks.
    """
    breadth = min(1.0, math.log10(1 + d["corpus_breadth"]) / math.log10(101))
    ac = (min(1.0, d["autocomplete_completions"] / 10.0)
          + (1.0 if d["exact_in_autocomplete"] else 0.0)) / 2

    if not comp:
        # No competition data: fall back to the weak signals and say so.
        return round(0.65 * breadth + 0.35 * ac, 4)

    v = comp.get("view_profile", {})
    # Anchors: a median top-20 view count near 3k means effectively no
    # audience; 10M means the question is a mass-market one. p90 spans
    # 100k to 50M. Both absolute, both stable across runs.
    audience = (_span(v.get("median"), 3.5, 7.0)
                + _span(v.get("p90"), 5.0, 7.7)) / 2
    return round(0.55 * audience + 0.30 * breadth + 0.15 * ac, 4)


# ---------------------------------------------------------------------------
# The combined score: high demand AND low competition
# ---------------------------------------------------------------------------
# opportunity_score alone measures room for a new entrant, and it does that
# well -- but it is only half the brief. It is why "why does black-smoker water
# not boil" scored the best opportunity of all 20 (0.71) while nobody searches
# it: part of the reason the field is empty is that there is no demand to fight
# over. Low competition on low demand is a winnable video, not a growth video.
#
# WEIGHTING: equal, and GEOMETRIC rather than arithmetic.
#   combined = sqrt(demand * opportunity)
# The brief is "high demand AND low competition". An arithmetic mean scores
# demand 0.1 / opportunity 0.9 as 0.50 -- mid-table, indistinguishable from a
# balanced 0.5/0.5. A geometric mean scores it 0.30. Multiplication is what
# "AND" means: a near-zero on either axis must drag the result down, because a
# topic that fails either test is not a good publish. Equal exponents because
# there is no evidence to justify preferring one axis over the other, and an
# unjustified weight is just a hidden opinion.
# ---------------------------------------------------------------------------
# THE GATE. Both dimensions are pass/fail, run BEFORE ranking.
# ---------------------------------------------------------------------------
# "High demand AND low competition -- both." A topic failing either test is
# killed, not ranked low. Thresholds are taken from the largest natural break
# in the measured distribution of these 20 episodes, not chosen as round
# numbers that feel right.
#
# DEMAND, recalibrated against the AUDIENCE-LED index (see demand_index):
#   0.126 | 0.190 0.269 0.275 0.290 0.290 0.295 0.372 0.391 0.404 0.413 0.427
#   0.464 0.481 0.539 0.558 0.564 0.570 0.723 0.970
#   This distribution is CONTINUOUS. There is no cliff, and that is the
#   finding: on a real demand signal these 20 episodes do not separate into
#   good and bad. The only isolated low outlier is 0.126 -> 0.190, a 0.064
#   break, so the floor sits there and excludes exactly one episode.
#
#   The first floor (0.175 on the autocomplete-led index) excluded 10 of 20 --
#   half the owner's already-rendered inventory, for a channel whose topic the
#   same research ratified as rising and best-in-class. That was a bad
#   threshold on a bad metric, not a bad inventory.
DEMAND_FLOOR = 0.16
#   Nothing in this sample sits below 0.10 on the audience-led index, so a
#   demand kill is provisional by default. Killing a topic outright needs
#   corroboration from the saturation axis.
DEMAND_FIRM_BELOW = 0.10
#
# SATURATION, sorted gap: 0.00 0.00 0.10 | 0.20 | 0.40 0.45 0.45 0.60 ...
#   The widest break is 0.20 -> 0.40 (0.200). The ceiling sits in that gap.
#   Unchanged: this axis is measured directly from 20 real search results and
#   it is the axis that actually discriminates.
SATURATION_GAP_CEILING = 0.30
SATURATION_FIRM_AT_OR_BELOW = 0.10

# FLOORS: yes, in addition to multiplication, and deliberately.
# Pure multiplication already pushes a zero-demand topic to zero, so a floor is
# not needed to rank it last. The floor earns its place for a different reason:
# it makes the exclusion NAMED. A candidate at 0.004 looks like a weak
# candidate; a candidate marked "excluded_below_demand_floor" tells the owner
# something actionable -- that this phrasing draws no searches at all and the
# episode should be retitled rather than merely deferred. A silent tiny number
# communicates nothing and invites someone to publish it anyway because it is
# "only just below the others". The counter-argument -- that a hard floor
# discards a topic a human might still want -- is handled by the pinned head,
# which overrides the floor explicitly and visibly.
TREND_MULTIPLIER = {"rising": 1.15, "flat": 1.0, "declining": 0.90}


def trend_factor(t: dict | None) -> tuple[float, str]:
    """Trends is a modest adjustment, never a driver.

    The index is relative and normalised, it is frequently unavailable for a
    long question string, and a missing series must never be read as a bad
    one. So: bounded to +/-15%, applied ONLY when the series is usable, and
    neutral (1.0) whenever the data is absent or not quotable. It reorders
    neighbours; it cannot promote a topic past one that beats it on substance.
    """
    if not t or t.get("status") != "ok":
        return 1.0, "no Trends data; neutral"
    tw = t.get("twelve_month", {})
    if not tw.get("reliability", {}).get("usable", False):
        return 1.0, "Trends series not quotable; neutral"
    label = tw.get("direction", {}).get("label")
    return TREND_MULTIPLIER.get(label, 1.0), f"Trends 12m {label}"


def gate(demand: float, gap: float | None, d: dict) -> dict:
    """Pass/fail on BOTH axes. Returns a verdict; never a score.

    Both axes are evaluated and BOTH failures reported. An earlier version
    short-circuited on demand, which labelled 'what is a yeti crab' a
    provisional demand kill when it is a firm saturation kill: 20 of 20 top
    titles answer it. Reporting the axis that happened to be tested first is
    not the same as reporting why a topic is dead.
    """
    if gap is None:
        return {"verdict": "unmeasured", "failed": [],
                "reason": "no competition measurement; not gated, not ranked"}

    failures, firm, reasons, settle = [], False, [], []

    if demand < DEMAND_FLOOR:
        failures.append("demand")
        d_firm = demand < DEMAND_FIRM_BELOW
        firm = firm or d_firm
        reasons.append(
            f"demand_index {demand:.3f} is below the {DEMAND_FLOOR} floor "
            f"(audience-led: top-20 median views and query-family breadth, not "
            "autocomplete completions)")
        if not d_firm:
            settle.append(
                "Re-measure the audience signal on another day; a demand kill "
                "this close to the floor should not stand on its own.")

    if gap <= SATURATION_GAP_CEILING:
        failures.append("saturation")
        s_firm = gap <= SATURATION_FIRM_AT_OR_BELOW
        firm = firm or s_firm
        reasons.append(
            f"title gap {gap:.2f} is at or below the {SATURATION_GAP_CEILING} "
            f"saturation ceiling: {int(round((1-gap)*20))} of the top 20 titles "
            "already answer this question squarely")
        if not s_firm:
            settle.append(
                "Re-measure with a larger result set and on a different day; "
                "20 results at one moment is thin evidence to end a topic on.")

    if not failures:
        return {"verdict": "passed", "failed": [],
                "reason": (f"demand {demand:.3f} clears the {DEMAND_FLOOR} "
                           f"floor and title gap {gap:.2f} clears the "
                           f"{SATURATION_GAP_CEILING} saturation ceiling.")}

    return {
        "verdict": "killed" if firm else "killed_provisional",
        "failed": failures,
        "measurement": {
            "demand_index": demand, "demand_floor": DEMAND_FLOOR,
            "title_gap": gap, "saturation_ceiling": SATURATION_GAP_CEILING,
            "autocomplete_completions": d["autocomplete_completions"],
            "corpus_breadth": d["corpus_breadth"],
        },
        "reason": "; ".join(reasons) + ".",
        "what_would_settle_it": " ".join(settle) or None,
    }


def combined(demand: float, opportunity: float, t: dict | None) -> dict:
    """Score for topics that already PASSED the gate."""
    tf, tnote = trend_factor(t)
    score = math.sqrt(max(demand, 0.0) * max(opportunity, 0.0)) * tf
    return {
        "combined_score": round(score, 4),
        "trend_multiplier": tf,
        "trend_note": tnote,
        "formula": "sqrt(demand_index * opportunity_score) * trend_multiplier",
    }


def reason(rec: dict) -> str:
    """One line saying why this episode sits where it does."""
    g = rec["competition"]["title_gap"]
    o = rec["competition"]["opportunity_score"]
    subs = rec["competition"]["median_subscribers"]
    views = rec["competition"]["median_views"]
    d = rec["demand"]["demand_index"]
    if g <= 0.2:
        return (f"SATURATED: {int((1-g)*100)}% of the top 20 titles answer this "
                f"question squarely (median {views:,.0f} views, {subs:,.0f} "
                "subs). The definitive video exists.")
    # Title coverage is LEXICAL. "The Deepest Place on Earth" scores 0.33
    # against "deepest part of the ocean" while being the same video. Where a
    # high gap sits on top of a very high view ceiling, the gap is likely
    # inflated by synonyms and the field is not really empty.
    if g >= 0.7 and views and views > 1_000_000:
        return (f"CONTESTED DESPITE THE GAP: {int(g*100)}% lexical title gap, "
                f"but median {views:,.0f} views and {subs:,.0f} subs in the top "
                "20. Coverage is word-matching, so incumbents answering the "
                "same question in different words score as a miss. Treat the "
                "gap here as overstated.")
    if g >= 0.9 and d >= 0.5:
        return (f"Open field with real demand: {int(g*100)}% of top-20 titles "
                f"do NOT answer the question, and demand index {d:.2f}. Nobody "
                "has made this one.")
    if g >= 0.9:
        return (f"Open field ({int(g*100)}% of top-20 titles miss the question) "
                f"but thin demand ({d:.2f}) -- uncontested because few ask it.")
    if d >= 0.7:
        return (f"Strong demand ({d:.2f}) against partial coverage "
                f"({int(g*100)}% title gap); winnable but contested.")
    return (f"Middle of the field: title gap {g:.2f}, demand {d:.2f}, "
            f"opportunity {o:.2f}.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=0.4)
    ap.add_argument("--competition", default="competition_scripts.json")
    args = ap.parse_args()

    cpath = os.path.join(HERE, args.competition)
    if not os.path.exists(cpath):
        sys.exit(f"FATAL: {cpath} missing. Run competition.py --from-scripts "
                 "first; this script will not invent a denominator.")
    comp = json.load(open(cpath, encoding="utf-8"))
    by_query = {r["query"]: r for r in comp["results"] if r["status"] == "ok"}
    if not by_query:
        sys.exit("FATAL: competition file contains no scored queries.")

    corpus = [r["query"] for r in
              json.load(open(os.path.join(HERE, "mined_queries.json"),
                             encoding="utf-8"))["queries"]]
    corpus_tokens = [content_tokens(c) for c in corpus]

    def _load(name, key, default):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            return default
        return json.load(open(path, encoding="utf-8")).get(key, default)

    pinned_rows = _load("pinned_head.json", "pinned", [])
    pub = {"published": _load("published.json", "published", [])}

    tpath = os.path.join(HERE, "trends_scripts.json")
    trends = {}
    if os.path.exists(tpath):
        td = json.load(open(tpath, encoding="utf-8"))
        trends = {r["keyword"]: r for r in td["results"]}

    eps = script_questions()
    rows, unmeasured = [], []
    print(f"probing autocomplete demand for {len(eps)} episodes (free)…")
    for slug, title, q in eps:
        if q not in by_query:
            unmeasured.append({"slug": slug, "query": q,
                               "status": "no_competition_score"})
            continue
        rows.append({"slug": slug, "title": title, "query": q,
                     "_c": by_query[q],
                     "_d": demand_probe(q, corpus, args.pause, corpus_tokens)})

    if not rows:
        sys.exit("FATAL: nothing to rank.")

    # demand_index: equal blend of three ABSOLUTE real observations.
    for r in rows:
        r["_demand_index"] = demand_index(r["_d"], r["_c"])

    out_rows = []
    for r in rows:
        c, d = r["_c"], r["_d"]
        tm = c["title_match"]
        t = trends.get(r["query"])
        gap = tm["gap_signal"] if tm["status"] == "ok" else None
        g = gate(r["_demand_index"], gap, d)
        rec = {
            "slug": r["slug"],
            "script": f"scripts/{r['slug']}.md",
            "title": r["title"],
            "query": r["query"],
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
            "trend": ({"direction_12m": (t.get("twelve_month", {})
                                         .get("direction", {}).get("label")),
                       "verdict": t.get("verdict"),
                       "breakouts": t.get("breakout_count"),
                       "status": t.get("status")}
                      if t else {"status": "not_measured"}),
        }
        rec.update(combined(r["_demand_index"], c["opportunity_score"], t)
                   if g["verdict"] == "passed"
                   else {"combined_score": 0.0,
                         "trend_multiplier": None,
                         "trend_note": "not scored; killed by the gate",
                         "formula": "not scored; killed by the gate"})
        rec["reason"] = (g["reason"] if g["verdict"] != "passed"
                         else reason(rec))
        out_rows.append(rec)

    published = set(pub.get("published", []))
    slug_of = {r["query"]: r["slug"] for r in out_rows}
    published_queries = {q for q, sl in slug_of.items() if sl in published}
    passed = [r for r in out_rows if r["gate"]["verdict"] == "passed"]
    killed = [r for r in out_rows if r["gate"]["verdict"].startswith("killed")]
    unmeas = [r for r in out_rows if r["gate"]["verdict"] == "unmeasured"]

    # The gate must never quietly empty the queue.
    if not out_rows:
        sys.exit("FATAL: no episodes examined.")
    if not passed and not pinned_rows:
        sys.exit(f"FATAL: the gate excluded all {len(out_rows)} episodes and "
                 "no owner-pinned episode remains. Refusing to emit an empty "
                 "publish order -- that is a threshold error, not a finding. "
                 f"demand floor {DEMAND_FLOOR}, saturation ceiling "
                 f"{SATURATION_GAP_CEILING}.")

    passed.sort(key=lambda r: -r["combined_score"])

    # ---- owner-pinned head ------------------------------------------
    by_q = {r["query"]: r for r in out_rows}
    head, pin_errors = [], []
    for q in pinned_rows:
        if q in published_queries:
            continue                      # expires automatically once published
        r = by_q.get(q)
        if not r:
            pin_errors.append({"pinned_query": q,
                               "error": "matches no episode question in scripts/*.md"})
            continue
        head.append(r)
    head = [r for r in head if r["slug"] not in published]

    tail = [r for r in passed
            if r["slug"] not in published
            and r["query"] not in {x["query"] for x in head}]

    queue = []
    for i, r in enumerate(head, 1):
        e = dict(r)
        e["queue_position"] = i
        e["source"] = "OWNER_PINNED"
        e["pinned"] = True
        e["source_note"] = ("Owner override from research/pinned_head.json. "
                            "NOT a computed result. Expires automatically once "
                            "the slug appears in research/published.json.")
        e["gate_overridden"] = r["gate"]["verdict"] != "passed"
        e["overridden_gate_verdict"] = (r["gate"]["verdict"]
                                        if e["gate_overridden"] else None)
        queue.append(e)
    for i, r in enumerate(tail, len(head) + 1):
        e = dict(r)
        e["queue_position"] = i
        e["source"] = "COMBINED_SCORE"
        e["pinned"] = False
        e["overridden_gate_verdict"] = None
        e["gate_overridden"] = False
        queue.append(e)

    queued_slugs = {e["slug"] for e in queue}
    # A record must never appear in both the queue and the killed list. An
    # owner-pinned episode that failed the gate is IN THE QUEUE, flagged as an
    # override; it is not also reported as killed. The loop reads one list.
    killed_not_queued = [r for r in killed if r["slug"] not in queued_slugs]

    contradictions = [
        {"queue_position": e["queue_position"], "slug": e["slug"],
         "query": e["query"], "gate_verdict": e["gate"]["verdict"],
         "why_the_data_disagrees": e["gate"]["reason"]}
        for e in queue if e["source"] == "OWNER_PINNED" and e["gate_overridden"]]

    out = {
        "_status": "PRODUCTION",
        "_authority": (
            "AUTHORITATIVE publish source. The loop acts on this file directly. "
            "There is no human approval step by design: the owner has given "
            "blanket approval for topic selection, the gate carries her "
            "judgement, and the only standing constraints are the hard "
            "exclusions in pov/topic-taxonomy.json. Read `queue` in order and "
            "publish queue_position 1 next."),
        "_provisional_records": (
            "Provisionality is marked PER RECORD, never on the file. A killed "
            "record with verdict 'killed_provisional' rests on a marginal "
            "measurement and carries what_would_settle_it. Queue records are "
            "not provisional."),
        "_writes_nothing_outside_research": (
            "No file in scripts/ was created, edited or read for anything but "
            "its H1 question."),
        "_schema_version": "1.1.0",
        "_schema": {
            "stability": ("The loop consumes this file. `queue` and the fields "
                          "named here are the stable contract; anything "
                          "prefixed with _ is documentation. Additive changes "
                          "bump the minor version, breaking changes the major."),
            "queue": ("Ordered publish list. Read it in order and publish "
                      "queue_position 1 next."),
            "queue[].queue_position": "1-based publish position.",
            "queue[].source": ("OWNER_PINNED (an owner override, obeyed "
                               "regardless of score) or COMBINED_SCORE."),
            "queue[].gate_overridden": ("true when an OWNER_PINNED episode did "
                                        "not pass the gate. Publish it anyway; "
                                        "the flag exists so the disagreement is "
                                        "visible."),
            "queue[].combined_score": ("sqrt(demand_index * opportunity_score) "
                                       "* trend_multiplier. 0.0 for anything "
                                       "not scored."),
            "queue[].gate.verdict": "passed | killed | killed_provisional | unmeasured",
            "mutual_exclusion": ("An episode appears in EITHER queue OR "
                                 "killed, never both. An owner-pinned episode "
                                 "that failed the gate stays in the queue with "
                                 "pinned=true and overridden_gate_verdict set "
                                 "to what the gate said; it is not repeated in "
                                 "killed."),
            "queue[].pinned": "true if this position comes from pinned_head.json.",
            "queue[].overridden_gate_verdict": (
                "null when the episode passed the gate. Otherwise the verdict "
                "the gate returned, which the owner pin overrode."),
            "killed": ("Episodes excluded by the gate AND not pinned. NOT in the queue. Each "
                       "carries the measurement that killed it so the owner can "
                       "disagree with a number rather than a judgement."),
            "reading_order_for_the_loop": ["queue", "killed", "pin_errors"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/publish_order.py",
        "rule": ("pov/topic-taxonomy.json: 'Rank candidates by (search demand / "
                 "competition).' Implemented as a hard GATE on both axes, then "
                 "a geometric combined score among survivors."),
        "gate": {
            "principle": ("High demand AND low competition. Failing either "
                          "axis kills the topic; it is not ranked low."),
            "demand_floor": DEMAND_FLOOR,
            "demand_firm_below": DEMAND_FIRM_BELOW,
            "saturation_gap_ceiling": SATURATION_GAP_CEILING,
            "saturation_firm_at_or_below": SATURATION_FIRM_AT_OR_BELOW,
            "how_thresholds_were_chosen": (
                "From the largest natural break in the measured distribution "
                "of these 20 episodes, not from round numbers. Demand: the "
                "widest gap in the bottom half is 0.133 -> 0.216, so the floor "
                "is 0.175. Saturation: the widest gap is 0.20 -> 0.40, so the "
                "ceiling is 0.30."),
            "provisional_kills": (
                "A kill resting on a marginal measurement is marked "
                "killed_provisional with what would settle it. Wrongly killing "
                "a good topic is invisible -- nothing ever shows you the video "
                "you did not make."),
            "excluded": len(killed),
            "passed": len(passed),
        },
        "title_coverage_weight": (
            "Title coverage is 50% of opportunity_score and the saturation "
            "axis of the gate. A low gap means the top 20 already answer the "
            "question: the definitive video exists."),
        "derived_from": {
            "competition": {"file": args.competition, "source": comp["source"],
                            "measured_at": comp["measured_at"],
                            "quota_units_spent": comp["quota_units_spent"]},
            "demand": {"endpoint": ENDPOINT, "surface": "youtube_autocomplete",
                       "corpus": "research/mined_queries.json"},
            "trend": ({"file": "research/trends_scripts.json"} if trends
                      else {"status": "not_measured"}),
            "owner_override": "research/pinned_head.json",
            "published_state": "research/published.json",
        },
        "caveats": [
            "demand_index is built from autocomplete presence and mined-corpus "
            "breadth. It is a demand SHAPE signal, not search volume.",
            "opportunity_score and title_gap are measured from the live top 20 "
            "on a single day, US/English. Rankings move.",
            "seed_hits, which helped choose these 20, is not used here at all.",
            "title_gap is LEXICAL. An incumbent answering the same question in "
            "different words ('The Deepest Place on Earth' vs 'deepest part of "
            "the ocean') counts as a miss, so the gap OVERSTATES opportunity "
            "wherever the top 20 carry very high view counts.",
        ],
        "episodes_examined": len(out_rows),
        "queue_length": len(queue),
        "owner_pinned_head": {
            "source": "research/pinned_head.json",
            "queries": pinned_rows,
            "still_pinned": [e["query"] for e in queue if e["source"] == "OWNER_PINNED"],
            "expired_because_published": [q for q in pinned_rows
                                          if q in published_queries],
            "contradicts_the_data": contradictions,
            "note": ("The owner chose these with the opportunity data in front "
                     "of her. Where the gate disagrees it is because the demand "
                     "side was not part of that view. They are published anyway; "
                     "the disagreement is recorded, not silently resolved."),
        },
        "pin_errors": pin_errors,
        "killed": [
            {"slug": r["slug"], "query": r["query"],
             "verdict": r["gate"]["verdict"], "failed_axes": r["gate"].get("failed"),
             "reason": r["gate"]["reason"],
             "measurement": r["gate"].get("measurement"),
             "what_would_settle_it": r["gate"].get("what_would_settle_it"),
             "demand_index": r["demand"]["demand_index"],
             "opportunity_score": r["competition"]["opportunity_score"],
             "title_gap": r["competition"]["title_gap"]}
            for r in sorted(killed_not_queued,
                            key=lambda r: (r["gate"]["verdict"],
                                           -r["demand"]["demand_index"]))],
        "unmeasured": [{"slug": r["slug"], "query": r["query"]} for r in unmeas],
        "episodes_without_competition_score": unmeasured,
        "queue": queue,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {OUT}\n")
    print(f"{'pos':>4} {'src':<7}{'slug':<46}{'comb':>6}{'dem':>6}{'opp':>6}{'gap':>6}")
    for e in queue:
        print(f"{e['queue_position']:>4} "
              f"{'PIN' if e['source'] == 'OWNER_PINNED' else 'score':<7}"
              f"{e['slug'][:45]:<46}{e['combined_score']:>6.3f}"
              f"{e['demand']['demand_index']:>6.2f}"
              f"{e['competition']['opportunity_score']:>6.2f}"
              f"{(e['competition']['title_gap'] or 0):>6.2f}"
              + ("   <- gate says no" if e["gate_overridden"] else ""))
    print(f"\nKILLED {len(killed)}:")
    for r in out["killed"]:
        print(f"   {r['verdict']:<19} {r['slug'][:44]:<45} "
              f"({','.join(r['failed_axes'])})")


if __name__ == "__main__":
    main()
