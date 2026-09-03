"""Competition scoring for candidate topics. READY TO RUN, KEY MISSING.

THE MISSING HALF OF THE SIGNAL
------------------------------
research/topic_backlog.json and research/broad_mined.json carry DEMAND evidence
only. research/trends.py adds DIRECTION. Neither says whether the video already
exists. The selection rule in pov/topic-taxonomy.json is:

    "Rank candidates by (search demand / competition)."

The denominator has never been measured. This module is that denominator.

WHAT IT MEASURES, PER CANDIDATE QUERY
-------------------------------------
  1. view_profile      median / p90 view count of the top ~20 search results
  2. incumbent_size    median subscriber count of the channels that rank
  3. recency           median age of the ranking videos, and how many are <365d
  4. title_match       THE IMPORTANT ONE. What share of the top results have a
                       title that actually covers the query's content words?

(4) is the real low-competition signal. A query whose top results are only
loosely related means YouTube has nothing squarely on it -- nobody has made the
definitive video. A query returning twenty exact-match titles from million-sub
channels is answered, and entering it is buying a fight.

WHAT IT REQUIRES
----------------
A YouTube Data API v3 key. There is no free keyless substitute: scraping search
result pages violates YouTube's Terms of Service and returns unstable markup, so
this module does not do it and will not silently fall back to it.

Supply the key in any ONE of:
    export YOUTUBE_API_KEY=...
    python competition.py --key AIza...
    a file  research/.youtube_api_key  (single line; keep it out of git)

WITHOUT A KEY this script takes a NAMED STOP: it prints exactly what is missing
and who must supply it, writes a stop record, and exits 0. It never crashes,
never skips silently, and never emits a fabricated score.

QUOTA
-----
The default free quota is 10,000 units/day. search.list costs 100 units, so a
run costs roughly 100 units + 2 per candidate: about 95 candidates/day maximum.
--limit defaults to 40 to leave headroom. The script refuses to start a run it
cannot finish inside the stated budget.

Usage:
  python competition.py --selftest                  # proves scoring logic, no key
  python competition.py --from-backlog --limit 40
  python competition.py --queries "how do we know how deep the ocean is"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "competition.json")
STOP_OUT = os.path.join(HERE, "competition_stop.json")
KEY_FILE = os.path.join(HERE, ".youtube_api_key")
API = "https://www.googleapis.com/youtube/v3"

SEARCH_COST, LIST_COST, DAILY_QUOTA = 100, 1, 10_000

# ---------------------------------------------------------------------------
# THE NAMED STOP
# ---------------------------------------------------------------------------
STOP = {
    "status": "NAMED_STOP",
    "name": "YOUTUBE_API_KEY_ABSENT",
    "what_is_missing": "A YouTube Data API v3 key.",
    "why_it_cannot_be_worked_around": (
        "Competition scoring needs the top ~20 search results for each query "
        "with their view counts, channel subscriber counts and publish dates. "
        "The only permitted source is the YouTube Data API. Scraping the search "
        "page violates YouTube's Terms of Service and returns unstable markup, "
        "so no keyless fallback is implemented and none will be."
    ),
    "who_must_supply_it": (
        "The owner. The key comes with the Google Cloud project already needed "
        "for channel uploads -- enable 'YouTube Data API v3' on that project and "
        "create an API key. Free tier, 10,000 quota units/day, no card required."
    ),
    "how_to_supply_it": [
        "export YOUTUBE_API_KEY=AIza...",
        "or write the key as a single line into research/.youtube_api_key",
        "or pass --key on the command line",
    ],
    "what_stays_unknown_until_then": [
        "Whether any candidate query is actually under-served.",
        "The competition denominator in the taxonomy's own selection rule, "
        "'rank candidates by (search demand / competition)'.",
        "Whether high-demand domains are high-demand because they are already "
        "saturated with good videos.",
    ],
    "this_script_is": "written, self-tested, and ready to run unchanged the "
                      "moment a key exists.",
}


def named_stop(out_path: str) -> int:
    rec = dict(STOP)
    rec["checked_utc"] = datetime.now(timezone.utc).isoformat()
    rec["locations_checked"] = ["env YOUTUBE_API_KEY", "env YT_API_KEY",
                                "--key argument", KEY_FILE]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print("=" * 72)
    print("NAMED STOP: " + rec["name"])
    print("=" * 72)
    print(f"Missing : {rec['what_is_missing']}")
    print(f"Owner   : {rec['who_must_supply_it']}")
    print("Supply  : " + "\n          ".join(rec["how_to_supply_it"]))
    print("Why no workaround:\n  " + rec["why_it_cannot_be_worked_around"])
    print("\nUnknown until supplied:")
    for line in rec["what_stays_unknown_until_then"]:
        print("  - " + line)
    print(f"\nStop recorded at {out_path}. No score was written, because no "
          "score was measured.")
    print("Exit 0: this is a declared stop, not a failure.")
    return 0


SECRETS_KEY = os.path.abspath(
    os.path.join(HERE, "..", ".secrets", "youtube_api_key.txt"))


def find_key(cli_key: str | None) -> tuple[str | None, str]:
    """Returns (key, where_it_came_from). The key itself is NEVER printed,
    logged, or written into any output file -- only the source label is."""
    if cli_key:
        return cli_key.strip(), "--key argument"
    for var in ("YOUTUBE_API_KEY", "YT_API_KEY"):
        v = os.environ.get(var, "").strip()
        if v:
            return v, f"environment ${var}"
    for path, label in ((SECRETS_KEY, ".secrets/youtube_api_key.txt"),
                        (KEY_FILE, "research/.youtube_api_key")):
        if os.path.exists(path):
            v = open(path, encoding="utf-8").read().strip()
            if v:
                return v, label
    return None, "not found"


# ---------------------------------------------------------------------------
# Scoring -- pure functions, unit-testable without a key (see --selftest)
# ---------------------------------------------------------------------------
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "is", "are", "do", "does", "did",
    "how", "why", "what", "when", "where", "who", "which", "can", "we", "you",
    "they", "it", "its", "and", "or", "for", "at", "by", "so", "that", "this",
    "with", "from", "be", "was", "were", "has", "have", "there", "really",
}
WORD = re.compile(r"[a-z0-9']+")


def content_tokens(text: str) -> set[str]:
    """Content words of a query or title, crudely de-pluralised."""
    toks = set()
    for w in WORD.findall(text.lower()):
        if w in STOPWORDS or len(w) < 3:
            continue
        if len(w) > 4 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        toks.add(w)
    return toks


def title_coverage(query: str, title: str) -> float:
    """Share of the query's content words present in the title. 0.0-1.0."""
    q = content_tokens(query)
    if not q:
        return 0.0
    return len(q & content_tokens(title)) / len(q)


def title_match_profile(query: str, titles: list[str],
                        strong: float = 0.75, weak: float = 0.4) -> dict:
    """The headline competition signal.

    strong_match_rate high  -> the definitive video exists; hard to displace.
    strong_match_rate low   -> results are loosely related; the gap is real.
    """
    if not titles:
        return {"status": "no_results", "n": 0}
    cov = [title_coverage(query, t) for t in titles]
    strong_n = sum(c >= strong for c in cov)
    weak_n = sum(c < weak for c in cov)
    return {
        "status": "ok",
        "n": len(cov),
        "mean_coverage": round(statistics.fmean(cov), 3),
        "max_coverage": round(max(cov), 3),
        "strong_match_count": strong_n,
        "strong_match_rate": round(strong_n / len(cov), 3),
        "loose_match_rate": round(weak_n / len(cov), 3),
        "gap_signal": round(1 - (strong_n / len(cov)), 3),
        "interpretation": (
            "nobody has made the definitive video on this query"
            if strong_n == 0 else
            f"{strong_n} of {len(cov)} ranking titles squarely answer the query"
        ),
    }


def _age_days(iso: str, now: datetime) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (now - dt).total_seconds() / 86400


def score_candidate(query: str, videos: list[dict], now: datetime | None = None) -> dict:
    """videos: [{title, views, subs, published_at, channel_id, video_id}]"""
    now = now or datetime.now(timezone.utc)
    if not videos:
        return {"query": query, "status": "no_results",
                "note": "YouTube returned no videos; treat as unmeasured, "
                        "not as zero competition."}
    views = [v["views"] for v in videos if v.get("views") is not None]
    subs = [v["subs"] for v in videos if v.get("subs") is not None]
    ages = [_age_days(v["published_at"], now) for v in videos if v.get("published_at")]
    titles = [v["title"] for v in videos]

    tm = title_match_profile(query, titles)
    med_views = statistics.median(views) if views else None
    med_subs = statistics.median(subs) if subs else None

    # --- composite, with every component stated -------------------------
    # Each sub-score is 0..1, higher = MORE opportunity for a new entrant.
    def inv_log(x, cap):
        if x is None:
            return None
        import math
        return max(0.0, min(1.0, 1 - math.log10(max(x, 1)) / math.log10(cap)))

    s_gap = tm["gap_signal"] if tm["status"] == "ok" else None
    s_subs = inv_log(med_subs, 10_000_000)      # small incumbents = opportunity
    s_views = inv_log(med_views, 10_000_000)
    s_stale = None
    if ages:
        fresh = sum(a < 365 for a in ages) / len(ages)
        s_stale = 1 - fresh                      # stale results = opportunity

    parts = {"title_gap": (s_gap, 0.50), "incumbent_subs": (s_subs, 0.20),
             "view_ceiling": (s_views, 0.15), "staleness": (s_stale, 0.15)}
    usable = {k: (v, w) for k, (v, w) in parts.items() if v is not None}
    total_w = sum(w for _, w in usable.values())
    opportunity = (round(sum(v * w for v, w in usable.values()) / total_w, 3)
                   if total_w else None)

    return {
        "query": query,
        "status": "ok",
        "results_examined": len(videos),
        "title_match": tm,
        "view_profile": {
            "median": med_views,
            "p90": (sorted(views)[int(len(views) * 0.9) - 1] if views else None),
            "max": max(views) if views else None,
            "n": len(views),
        },
        "incumbents": {
            "median_subscribers": med_subs,
            "max_subscribers": max(subs) if subs else None,
            "under_100k_subs": sum(s < 100_000 for s in subs) if subs else None,
            "n": len(subs),
        },
        "recency": {
            "median_age_days": round(statistics.median(ages)) if ages else None,
            "published_last_365d": sum(a < 365 for a in ages) if ages else None,
            "n": len(ages),
        },
        "opportunity_score": opportunity,
        "opportunity_components": {k: round(v, 3) for k, (v, w) in usable.items()},
        "opportunity_weights": {k: w for k, (v, w) in usable.items()},
        "score_definition": (
            "0-1, higher = more room for a new entrant. 50% title gap (share of "
            "top results whose title does NOT squarely answer the query), 20% "
            "small incumbent channels, 15% low view ceiling, 15% stale results. "
            "Log-scaled against a 10M cap for views and subscribers."
        ),
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class YouTube:
    def __init__(self, key: str, pause: float = 0.2):
        self.key, self.pause, self.units = key, pause, 0

    def _get(self, path: str, params: dict, cost: int) -> dict:
        params = dict(params, key=self.key)
        url = f"{API}/{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:400]
            # The YouTube Data API signals a spent daily quota with 429
            # ("Quota exceeded for quota metric 'Search Queries'"), and with
            # 403 quotaExceeded in other conditions. Treating 429 as a generic
            # error meant a spent quota surfaced as an unexplained failure
            # instead of firing the named stop, and a scheduled run would keep
            # hammering a quota that cannot recover until the PT midnight reset.
            if e.code == 429 or (e.code == 403 and "quota" in detail.lower()):
                raise QuotaExhausted(detail) from None
            raise ApiError(f"HTTP {e.code} on {path}: {detail}") from None
        self.units += cost
        time.sleep(self.pause)
        return body

    def search(self, query: str, n: int = 20) -> list[dict]:
        d = self._get("search", {"part": "snippet", "q": query, "type": "video",
                                 "maxResults": min(n, 50), "order": "relevance",
                                 "relevanceLanguage": "en", "regionCode": "US"},
                      SEARCH_COST)
        return [{"video_id": it["id"]["videoId"],
                 "title": it["snippet"]["title"],
                 "channel_id": it["snippet"]["channelId"],
                 "published_at": it["snippet"]["publishedAt"]}
                for it in d.get("items", []) if it.get("id", {}).get("videoId")]

    def video_stats(self, ids: list[str]) -> dict[str, int]:
        if not ids:
            return {}
        d = self._get("videos", {"part": "statistics", "id": ",".join(ids[:50])},
                      LIST_COST)
        return {it["id"]: int(it.get("statistics", {}).get("viewCount", 0))
                for it in d.get("items", [])}

    def channel_stats(self, ids: list[str]) -> dict[str, int | None]:
        ids = sorted(set(ids))
        if not ids:
            return {}
        out: dict[str, int | None] = {}
        for i in range(0, len(ids), 50):
            d = self._get("channels", {"part": "statistics",
                                       "id": ",".join(ids[i:i + 50])}, LIST_COST)
            for it in d.get("items", []):
                st = it.get("statistics", {})
                out[it["id"]] = (None if st.get("hiddenSubscriberCount")
                                 else int(st.get("subscriberCount", 0)))
        return out


class ApiError(RuntimeError):
    pass


class QuotaExhausted(RuntimeError):
    pass


def measure(api: YouTube, query: str, n: int = 20) -> dict:
    vids = api.search(query, n)
    if not vids:
        return {"query": query, "status": "no_results"}
    views = api.video_stats([v["video_id"] for v in vids])
    subs = api.channel_stats([v["channel_id"] for v in vids])
    for v in vids:
        v["views"] = views.get(v["video_id"])
        v["subs"] = subs.get(v["channel_id"])
    rec = score_candidate(query, vids)
    rec["provenance"] = {
        "endpoint": API,
        "calls": ["search.list", "videos.list", "channels.list"],
        "region": "US", "language": "en", "order": "relevance",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }
    rec["top_results"] = [{"title": v["title"], "views": v["views"],
                           "subs": v["subs"], "published_at": v["published_at"],
                           "coverage": round(title_coverage(query, v["title"]), 3)}
                          for v in vids]
    return rec


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Deliberate quota allocation
# ---------------------------------------------------------------------------
# search.list costs 100 units of a 10,000/day allowance: about 95 searches a
# day, total. Spreading them evenly over 20 domains would buy 4-5 queries each
# and answer nothing decisively. They are spent instead where they can actually
# move the ranking.
# Sized to the 7,959 units left after the 20 existing scripts took 2,040 of the
# day's 10,000: 6*6 + 6*4 + 8*2 = 76 searches = 7,752 units.
TIERS = [
    ((1, 6), 6, "Decides the top of the table. These six are the ones the "
                "owner would actually commission, and the open question -- is "
                "space-astronomy #1 only because it is saturated? -- lives "
                "here. Deepest sampling."),
    ((7, 12), 4, "Live challengers. Enough queries to detect a wide-open "
                 "domain that demand alone under-rates, not enough to spend "
                 "the budget on positions nobody will act on."),
    ((13, 20), 2, "Long tail. Two probes each is a smoke test: it can reveal "
                  "an unexpectedly empty field worth a second look, and "
                  "nothing more is claimed from it."),
]


def tier_for(rank: int) -> tuple[int, str]:
    for (lo, hi), n, why in TIERS:
        if lo <= rank <= hi:
            return n, why
    return 0, "unallocated"


# Franchise / fiction markers that filter.py's NOISE list does not carry.
# Used ONLY to decide which queries are worth 100 quota units each. It changes
# no metric and removes nothing from the mined data -- "how does gravity work
# on the death star" is a real autocomplete string, it is simply not a query
# whose competition tells us anything about physics as a channel domain.
SELECTION_SKIP = re.compile(
    r"\b(death star|star wars|final stand|remastered|roblox|minecraft|"
    r"fortnite|skyrim|terraria|elden|gta|subnautica|hogwarts|osrs|"
    r"season \d|episode|lyrics?)\b"
    # Found by auditing the selected 88 before spending. "How Deep Is the
    # Ocean" is an Irving Berlin standard, so the deep-sea seeds pull in jazz
    # recordings. Left in, they would return music results for a science query,
    # score as a huge title gap, and INFLATE deep sea's opportunity -- biasing
    # the exact comparison this run exists to make.
    r"|\bhow deep is the ocean (evans|nowak|tag)\b"
    r"|\bzero gravity ride\b|\bkhan sir\b", re.I)


def select_domain_queries(domain: str, n: int, mined: dict, method: dict,
                          seed_tokens: set[str], taken: set[str]) -> list[str]:
    """Pick a domain's strongest, ON-DOMAIN candidate queries.

    Ordering: method-shaped first (the channel's premise), then breadth of
    probe confirmation, then specificity. Queries are required to contain a
    token from the domain's own seeds, because the method-stem pass drifts --
    'how do scientists know about other galaxies' surfaced under deep sea and
    would otherwise pollute that domain's competition score.
    """
    pool: dict[str, dict] = {}
    for src in (method.get(domain), mined.get(domain)):
        if not src:
            continue
        for r in src["queries"]:
            q = r["query"]
            if r["noise"] or r["excluded"] or r["words"] < 4:
                continue
            if SELECTION_SKIP.search(q):
                continue
            # Only question- or method-shaped queries. This channel makes
            # explainers; the competition that matters is competition for the
            # answer, not for a noun. Without this the backfill reached
            # "ocean skin science perfume review".
            if not (r["question"] or r["method"]):
                continue
            if q in taken:
                continue
            if not (content_tokens(q) & seed_tokens):
                continue
            prev = pool.get(q)
            if not prev or (r["method"], r["probe_hits"]) > (prev["method"],
                                                            prev["probe_hits"]):
                pool[q] = r
    ranked = sorted(pool.values(),
                    key=lambda r: (-int(r["method"]), -r["probe_hits"],
                                   -r["words"], r["query"]))
    # Diversity gate. Near-duplicates cost 100 quota units each and buy the
    # same answer: "what is quantum entanglement", "what is quantum
    # entanglement simple explanation" and "explanation of quantum
    # entanglement" return substantially the same top 20. Keep one.
    out: list[str] = []
    chosen: list[set[str]] = []
    for r in ranked:
        if len(out) >= n:
            break
        toks = content_tokens(r["query"])
        if any(toks <= c or c <= toks                       # one refines the other
               or len(toks & c) / max(1, len(toks | c)) > 0.6
               for c in chosen):
            continue
        out.append(r["query"])
        chosen.append(toks)
        taken.add(r["query"])
    return out


def build_allocation(args) -> tuple[list[tuple[str, str]], dict]:
    """-> ([(domain, query)], plan_record)"""
    prop = json.load(open(os.path.join(HERE, "proposed-taxonomy.json"),
                          encoding="utf-8"))
    mined = json.load(open(os.path.join(HERE, "broad_mined.json"),
                           encoding="utf-8"))["domains"]
    mpath = os.path.join(HERE, "broad_method.json")
    method = (json.load(open(mpath, encoding="utf-8"))["domains"]
              if os.path.exists(mpath) else {})
    seeds = json.load(open(os.path.join(HERE, "seeds_broad.json"),
                           encoding="utf-8"))["domains"]

    pairs: list[tuple[str, str]] = []
    plan, taken = [], set()
    for rec in sorted(prop["ranked_domains"], key=lambda r: r["demand_side_rank"]):
        d, rank = rec["domain"], rec["demand_side_rank"]
        n, why = tier_for(rank)
        if n == 0:
            continue
        toks: set[str] = set()
        for s in seeds[d]["seeds"]:
            toks |= content_tokens(s)
        qs = select_domain_queries(d, n, mined, method, toks, taken)
        if not qs:
            plan.append({"domain": d, "rank": rank, "allocated": 0,
                         "status": "no on-domain candidate query survived "
                                   "filtering; domain left unmeasured"})
            continue
        pairs += [(d, q) for q in qs]
        plan.append({"domain": d, "rank": rank, "tier_rationale": why,
                     "allocated_searches": len(qs), "queries": qs})
    return pairs, {
        "rule": "search.list = 100 units; 10,000 units/day = ~95 searches.",
        "tiers": [{"ranks": f"{lo}-{hi}", "searches_per_domain": n,
                   "rationale": why} for (lo, hi), n, why in TIERS],
        "total_searches": len(pairs),
        "estimated_units": len(pairs) * (SEARCH_COST + 2 * LIST_COST),
        "per_domain": plan,
    }


SCRIPTS_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))


def script_questions() -> list[tuple[str, str, str]]:
    """-> [(slug, h1_title, query)] for every scripts/*.md. READ ONLY."""
    if not os.path.isdir(SCRIPTS_DIR):
        sys.exit(f"FATAL: {SCRIPTS_DIR} not found.")
    out = []
    for fn in sorted(os.listdir(SCRIPTS_DIR)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(SCRIPTS_DIR, fn)
        title = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        if not title:
            sys.exit(f"FATAL: no H1 question found in {fn}; refusing to guess "
                     "an episode's query.")
        # The query is the question as a searcher would type it.
        query = title.rstrip("?").strip().lower()
        out.append((fn[:-3], title, query))
    if not out:
        sys.exit(f"FATAL: no .md scripts in {SCRIPTS_DIR}.")
    return out


def load_queries(args) -> list[str]:
    if args.queries:
        return [q.strip() for q in args.queries.split(",") if q.strip()]
    if args.from_backlog:
        path = os.path.join(HERE, args.backlog)
        if not os.path.exists(path):
            sys.exit(f"FATAL: {path} not found.")
        d = json.load(open(path, encoding="utf-8"))
        rows = d.get("queries", [])
        rows = [r for r in rows if r.get("is_question") or r.get("question")]
        rows.sort(key=lambda r: -(r.get("seed_hits") or r.get("probe_hits") or 0))
        return [r["query"] for r in rows[:args.limit]]
    return []


def selftest() -> int:
    """Proves the scoring logic runs and discriminates, with zero network and
    zero key. A scorer nobody has ever executed is not 'ready to run'."""
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    q = "how do we know how deep the ocean is"

    saturated = [{"title": f"How We Know How Deep The Ocean Is (part {i})",
                  "views": 4_000_000, "subs": 8_000_000,
                  "published_at": "2026-04-01T00:00:00Z",
                  "video_id": f"v{i}", "channel_id": "c1"} for i in range(20)]
    wide_open = [{"title": f"Relaxing whale sounds for sleep {i}",
                  "views": 900, "subs": 400,
                  "published_at": "2018-01-01T00:00:00Z",
                  "video_id": f"w{i}", "channel_id": "c2"} for i in range(20)]

    a = score_candidate(q, saturated, now)
    b = score_candidate(q, wide_open, now)
    checks = [
        ("saturated detected as answered", a["title_match"]["strong_match_rate"] == 1.0),
        ("open detected as unanswered", b["title_match"]["strong_match_rate"] == 0.0),
        ("gap signal inverts", a["title_match"]["gap_signal"] == 0.0
         and b["title_match"]["gap_signal"] == 1.0),
        ("opportunity ranks open above saturated",
         b["opportunity_score"] > a["opportunity_score"]),
        ("saturated scores low", a["opportunity_score"] < 0.2),
        ("open scores high", b["opportunity_score"] > 0.8),
        ("empty result set is not scored as zero competition",
         score_candidate(q, [], now)["status"] == "no_results"),
        ("coverage is partial-credit",
         0 < title_coverage(q, "how deep is the ocean, really") < 1.0),
        ("stopwords ignored", content_tokens("how do we know") == {"know"}),
    ]
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    if not ok:
        print("\nSELFTEST FAILED"); return 1
    print(f"\nSELFTEST PASSED ({len(checks)} checks). Scoring logic is live; "
          "only the API key is missing.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", default=None)
    ap.add_argument("--queries", default=None, help="comma-separated")
    ap.add_argument("--from-backlog", action="store_true")
    ap.add_argument("--from-scripts", action="store_true",
                    help="score the episode questions in scripts/*.md")
    ap.add_argument("--from-proposal", action="store_true",
                    help="allocate quota across domains by demand-side rank")
    ap.add_argument("--budget", type=int, default=DAILY_QUOTA,
                    help="max quota units this run may plan to spend")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the allocation and spend nothing")
    ap.add_argument("--backlog", default="topic_backlog.json")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--results", type=int, default=20)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-run even if the output is within its staleness "
                         "window (research/staleness.py)")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.dry_run:
        import staleness  # noqa: PLC0415
        staleness.guard(args.out, staleness.WINDOWS_DAYS["competition.py"],
                        "research/competition.py", force=args.force)

    if args.dry_run:
        pairs, plan = build_allocation(args)
        print(json.dumps({k: v for k, v in plan.items() if k != "per_domain"},
                         indent=2))
        for p in plan["per_domain"]:
            print(f"\n  rank {p['rank']:>2}  {p['domain']}  "
                  f"-> {p.get('allocated_searches', 0)} searches")
            for q in p.get("queries", []):
                print(f"        {q}")
        print(f"\nTOTAL {plan['total_searches']} searches, "
              f"{plan['estimated_units']} units. Nothing spent (--dry-run).")
        return 0

    key, key_source = find_key(args.key)
    if not key:
        return named_stop(STOP_OUT)
    # The source label is safe to print. The key itself never is.
    print(f"API key loaded from: {key_source}")

    plan = None
    if args.from_scripts:
        trips = script_questions()
        queries = [q for _, _, q in trips]
        domain_of = {q: "existing-script" for q in queries}
        plan = {"mode": "from_scripts",
                "rationale": ("Scoring the 20 scripts that already exist. The "
                              "publish order is decided this week, so these "
                              "queries outrank domains nobody will touch for "
                              "months."),
                "episodes": [{"slug": s, "title": t, "query": q}
                             for s, t, q in trips],
                "total_searches": len(queries),
                "estimated_units": len(queries) * (SEARCH_COST + 2 * LIST_COST)}
    elif args.from_proposal:
        pairs, plan = build_allocation(args)
        if not pairs:
            sys.exit("FATAL: allocation produced no queries.")
        queries = [q for _, q in pairs]
        domain_of = {q: d for d, q in pairs}
    else:
        queries = load_queries(args)
        domain_of = {}
    if not queries:
        sys.exit("FATAL: no candidate queries. Pass --from-proposal, "
                 "--queries or --from-backlog.")

    budget = (SEARCH_COST + 2 * LIST_COST) * len(queries)
    print(f"{len(queries)} candidates, estimated {budget} quota units "
          f"of a {DAILY_QUOTA}/day free allowance.")
    if budget > args.budget:
        sys.exit(f"FATAL: {budget} units exceeds the {args.budget} unit budget. "
                 "Refusing to start a run that will die half-scored.")

    api = YouTube(key)
    rows, failures = [], []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] [{domain_of.get(q, '-')}] {q!r}", flush=True)
        try:
            rec = measure(api, q, args.results)
        except QuotaExhausted as e:
            print(f"\nNAMED STOP: YOUTUBE_QUOTA_EXHAUSTED after {len(rows)} of "
                  f"{len(queries)} candidates ({api.units} units spent). The "
                  "remainder is recorded as UNMEASURED, not as zero "
                  f"competition. Detail: {str(e)[:200]}")
            failures += [{"query": x, "domain": domain_of.get(x),
                          "status": "unmeasured_quota_exhausted"}
                         for x in queries[i - 1:]]
            break
        except ApiError as e:
            print(f"      ERROR: {e}")
            failures.append({"query": q, "domain": domain_of.get(q),
                             "status": "error", "detail": str(e)})
            continue
        rec["domain"] = domain_of.get(q)
        rows.append(rec)
        if rec["status"] == "ok":
            tm = rec["title_match"]
            print(f"      opportunity {rec['opportunity_score']:.2f}  "
                  f"gap {tm['gap_signal']:.2f}  "
                  f"med views {rec['view_profile']['median']:,}  "
                  f"med subs {rec['incumbents']['median_subscribers']:,}")

    scored = [r for r in rows if r["status"] == "ok"]
    if not scored:
        sys.exit("FATAL: zero candidates scored. Not writing an empty result "
                 "file that would read as 'no competition found'.")

    # ---- domain-level aggregation -----------------------------------
    by_domain: dict[str, list[dict]] = {}
    for r in scored:
        if r.get("domain"):
            by_domain.setdefault(r["domain"], []).append(r)
    domains = {}
    for d, rs in by_domain.items():
        opp = [r["opportunity_score"] for r in rs if r["opportunity_score"] is not None]
        gap = [r["title_match"]["gap_signal"] for r in rs
               if r["title_match"]["status"] == "ok"]
        mv = [r["view_profile"]["median"] for r in rs if r["view_profile"]["median"]]
        ms = [r["incumbents"]["median_subscribers"] for r in rs
              if r["incumbents"]["median_subscribers"] is not None]
        domains[d] = {
            "queries_scored": len(rs),
            "mean_opportunity": round(statistics.fmean(opp), 4) if opp else None,
            "median_opportunity": round(statistics.median(opp), 4) if opp else None,
            "mean_title_gap": round(statistics.fmean(gap), 4) if gap else None,
            "median_of_median_views": int(statistics.median(mv)) if mv else None,
            "median_of_median_subs": int(statistics.median(ms)) if ms else None,
            "queries": [r["query"] for r in rs],
            "sample_caveat": (
                f"{len(rs)} query sample. Deliberately unequal across domains: "
                "quota was concentrated where it could move the ranking. Treat "
                "a 2-query domain as a smoke test, not a measurement."),
        }

    out = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "generator": "research/competition.py",
        "source": "YouTube Data API v3 (search.list, videos.list, channels.list)",
        "key_source": key_source,
        "key_handling": "The API key is never printed, logged, or written here.",
        "quota_units_spent": api.units,
        "quota_budget": args.budget,
        "allocation_plan": plan,
        "candidates_scored": len(scored),
        "candidates_unmeasured": failures,
        "unmeasured_note": (
            "Anything listed here has NO competition value. It is not scored "
            "as zero and must not be ranked as if it were measured."),
        "domain_summary": domains,
        "results": sorted(scored, key=lambda r: -(r["opportunity_score"] or 0)),
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {args.out}: {len(scored)} scored, {len(failures)} unmeasured, "
          f"{api.units} quota units spent")
    print(f"\n{'domain':<32}{'n':>3}{'opp':>7}{'gap':>7}{'medViews':>11}{'medSubs':>11}")
    for d, v in sorted(domains.items(), key=lambda x: -(x[1]["mean_opportunity"] or 0)):
        print(f"{d:<32}{v['queries_scored']:>3}{v['mean_opportunity']:>7.3f}"
              f"{v['mean_title_gap']:>7.3f}{v['median_of_median_views']:>11,}"
              f"{v['median_of_median_subs']:>11,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
