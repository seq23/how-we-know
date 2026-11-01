"""The runway refills itself: the miner grows its own seeds, and the Monday
rebuild authors toward runway.target_weeks with a cap that counts scripts
added, not attempts.

WHY (2026-11-01, RUNWAY_CRITICAL, run 41300341725). Two defects held the
runway at ~3 weeks with nothing able to lift it:

  1. research/publish_order_domain.py mined the SAME fixed seed list every
     Saturday. Deep sea's corpus was exhausted (every surviving question a
     repeat or junk), so each week ended DOMAIN_QUEUE_THIN whose only unblock
     was "a person adds seeds". The publish queue ran dry.
  2. loop/draft.py rebuild_runway_if_short() fired only at warn and walked
     candidates[:3]: two validation failures spent two of the three slots
     (run 40310147557 added 1), and the week's own selection only replaces
     what the week consumes.

Part 1 drives the real loop/score.py grow_thin_domain_seeds() (free route
stubbed) and the real candidates() on a fixture catalogue whose every mined
question is already made: the grown subjects are persisted, mined once
(stubbed autocomplete) and their questions become candidates. It also proves a dead route grows nothing.
Part 2 drives the real rebuild with runway ok but under target: two failing
drafts must not stop it reaching its cap of validated scripts.
Part 4 (2026-11-01): grown seeds let "how deep are pools" and "how to get
brine pool exotic" into the deep-sea queue and the Monday lane authored
both. The real build() must hand the gate only on-domain candidates: a game
phrasing is refused before any model call, the $0 route's "no" is obeyed
against the domain's taxonomy definition, an unanswered row is refused, no
route at all is the RELEVANCE_UNCHECKED stop, and a grown seed naming a game
is never kept.
No network. Writes only to temp dirs. Hard-fails on zero items.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("LOOP_DRY_RUN", "1")
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="stops-"))
HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))

import ledger                                              # noqa: E402
import publish_order_domain as pod                         # noqa: E402
import topic_identity as T                                 # noqa: E402

fails: list[str] = []
DOM = "deep-sea-ocean-science"
MADE = [("08-what-creatures-live-in-the-deep-sea",
         "what creatures live in the deep sea"),
        ("10-what-is-the-deepest-part-of-the-ocean",
         "what is the deepest part of the ocean")]
EXHAUSTED = ["what lives in the deep sea", "what creatures live in the deep sea",
             "what is the deepest part of the ocean"]
GROWN = ["giant isopod", "vampire squid", "gulper eel", "sea pig",
         "barreleye fish", "goblin shark", "sea cucumber", "tube worm"]
GROWN_QS = ["how big is a giant isopod", "how does a vampire squid survive",
            "what does a gulper eel eat", "why is a sea pig pink",
            "how does a barreleye fish see", "why does a goblin shark jaw",
            "how does a sea cucumber breathe", "how do tube worm colonies live"]


def rows(qs):
    return [{"query": q, "question": True, "noise": False, "excluded": False,
             "probe_hits": 100 - i} for i, q in enumerate(qs)]


def fixture() -> Path:
    d = Path(tempfile.mkdtemp(prefix="grow-fixture-"))
    (d / "broad_mined.json").write_text(json.dumps({"domains": {DOM: {
        "queries": rows(EXHAUSTED),
        "provenance": {"seeds": ["deep sea", "ocean"]}}}}))
    (d / pod.DEEP_MINE_OVERRIDE[DOM]).write_text(
        json.dumps({"queries": rows(EXHAUSTED)}))
    (d / pod.DEDICATED_SEEDS[DOM]).write_text(
        json.dumps({"seeds": ["hydrothermal vent"]}))
    return d


@contextlib.contextmanager
def catalogue(d: Path):
    mined: list[list] = []

    def deep_mine(domain, seeds, out_path):
        mined.append(list(seeds))
        # The grown subjects' own autocomplete: only seeds it was given.
        qs = [q for q, s in zip(GROWN_QS, GROWN) if s in seeds]
        return rows(qs or EXHAUSTED)

    saved = (pod.HERE, pod.BROAD, pod.made_question_keys, ledger.load,
             pod.deep_mine)
    pod.HERE, pod.BROAD = str(d), str(d / "broad_mined.json")
    pod.made_question_keys = lambda: [(q, T.question_key(q)) for _, q in MADE]
    ledger.load = lambda: {"published": [{"slug": s, "question": q}
                                         for s, q in MADE],
                           "queued": [], "updated": None}
    pod.deep_mine = deep_mine
    try:
        yield mined
    finally:
        (pod.HERE, pod.BROAD, pod.made_question_keys, ledger.load,
         pod.deep_mine) = saved


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


class St:
    def __init__(self):
        self.notes, self.works, self.stops = [], [], []

    def note(self, m): self.notes.append(m)
    def work(self, m): self.works.append(m)
    def named_stop(self, code, msg, **kw): self.stops.append(code)


import llm_router                                          # noqa: E402
import score                                               # noqa: E402

ANSWER = "\n".join(["- " + g for g in GROWN] + ["1. deep sea", "3d sonar",
                                               "a question? no way at all here"])


def grow(d: Path, complete) -> St:
    st = St()
    saved = llm_router.complete
    llm_router.complete = complete
    try:
        with catalogue(d):
            quiet(score.grow_thin_domain_seeds, st, DOM)
    finally:
        llm_router.complete = saved
    return st


# ---------------- 1a. a thin domain grows seeds; the miner turns them into
#                       candidates, once, and keeps them as vocabulary
d = fixture()
grow(d, lambda msgs, key, **kw: {
    "choices": [{"message": {"content": ANSWER}}], "model_used": "stub"})
with catalogue(d) as mined:
    log: list = []
    picked, _ = quiet(pod.candidates, DOM, log=log)
    grown = pod.grown_seeds(DOM)
    pending_after = pod.pending_grown_seeds(DOM)
    later_vocab = pod.dedicated_seeds(DOM)
    _, _ = quiet(pod.candidates, DOM, log=[])
    mined_twice = sum(1 for m in mined if set(GROWN) <= set(m))
if not picked:
    fails.append("an exhausted domain with a working free route produced ZERO "
                 f"candidates - the seed list did not grow. log: {log}")
got = [q for q in GROWN_QS if q in picked]
if len(got) < 4:
    fails.append(f"only {len(got)} grown-seed question(s) became candidates "
                 f"(want >= 4): {picked}")
if sorted(grown) != sorted(GROWN + ["3d sonar"]):
    fails.append(f"grown seeds wrong (new subjects only, '3d' kept, 'deep sea' "
                 f"dropped): {grown}")
if mined_twice != 1:
    fails.append(f"the grown batch was mined {mined_twice} time(s), want once")
if pending_after:
    fails.append(f"grown seeds still pending after the miner ran: {pending_after}")
if not set(GROWN) <= set(later_vocab):
    fails.append("dedicated_seeds() does not carry grown seeds into later runs")

# ------------------------------------------- 1b. a dead route grows nothing


def dead(msgs, key, **kw):
    raise llm_router.LLMStop("NO_ROUTE", "no free route answered")


d2 = fixture()
st2 = grow(d2, dead)
with catalogue(d2):
    wrote = Path(pod.grown_seeds_path(DOM)).exists()
if wrote:
    fails.append("a dead free route still wrote grown seeds")
if not any("could not answer" in n for n in st2.notes):
    fails.append(f"a dead free route was not named: {st2.notes}")

# --------------------- 2. rebuild authors toward target; cap counts successes
import draft                                               # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="rebuild-"))
(tmp / "scripts").mkdir()
(tmp / "loop" / "drafts").mkdir(parents=True)
queue = [{"slug": f"topic-{i}", "query": f"topic {i}",
          "domain": "materials" if i < 3 else "deep-sea"} for i in range(8)]
BAD = {"topic-0", "topic-1"}
validated: list[str] = []


def fake_draft(q, slug, pov, **kw):
    p = tmp / "loop" / "drafts" / f"{slug}.md"
    p.write_text(f"# {q}?\n")
    return {"path": str(p.relative_to(tmp))}


def run_all(items):
    validated.extend(i["slug"] for i in items)
    ok = all(i["slug"] not in BAD for i in items)
    return ok, [{"validator": "stub", "status": "PASS" if ok else "FAIL(1)"}]


saved = (draft.ROOT, draft.cadence.runway, draft.batch_queue.unwritten_entries,
         draft.domains.by_slug, draft.domains.allocation, draft.author.draft,
         draft.validate.run_all, draft.cadence.record_authoring_evidence,
         draft.pov_match.select, draft.pov_match.record_assignment)
try:
    draft.ROOT = tmp
    # ok, but 3 weeks at 6/week against a 6-week target; only materials is
    # short by its own count - deep sea's topics must still be authored.
    draft.cadence.runway = lambda per_week: {
        "level": "ok", "short_domains": ["materials"], "weeks_remaining": 3.0,
        "videos_per_week": 6, "by_domain": {}, "message": "stub 3.0 weeks"}
    draft.batch_queue.unwritten_entries = lambda: list(queue)
    draft.domains.by_slug = lambda: {}
    draft.domains.allocation = lambda cfg: {"materials": 2, "deep-sea": 2}
    draft.author.draft = fake_draft
    draft.validate.run_all = run_all
    draft.cadence.record_authoring_evidence = lambda *a, **k: {"scripts": []}
    draft.pov_match.select = lambda slug, q, used: {"pov_id": "p", "line": "l"}
    draft.pov_match.record_assignment = lambda slug, pov: None
    st = St()
    draft.rebuild_runway_if_short(
        st, {"runway": {"rebuild_max_extra": 4, "target_weeks": 6}}, 6, [], set())
finally:
    (draft.ROOT, draft.cadence.runway, draft.batch_queue.unwritten_entries,
     draft.domains.by_slug, draft.domains.allocation, draft.author.draft,
     draft.validate.run_all, draft.cadence.record_authoring_evidence,
     draft.pov_match.select, draft.pov_match.record_assignment) = saved

promoted = sorted(p.stem for p in (tmp / "scripts").glob("*.md"))
if not validated:
    fails.append("the rebuild validated ZERO drafts at runway ok under target "
                 "- it never ran toward the target")
if len(promoted) != 4:
    fails.append(f"rebuild promoted {len(promoted)} script(s), want the cap of "
                 f"4 despite two failed drafts: {promoted}")
if set(promoted) & BAD:
    fails.append(f"a draft that failed validation was promoted: {promoted}")
if len(validated) > 8:
    fails.append(f"attempts not bounded at twice the cap: {validated}")

# ------- 3. the runway counts what will AIR; food rows count for the miner
import batch_queue                                          # noqa: E402
import cadence                                              # noqa: E402

inv = [{"slug": s} for s in ("deep-a", "food-batch-1", "food-batch-2")]
saved = (cadence.ordered_inventory, cadence.ledger.inventory,
         cadence.ledger.published_slugs, batch_queue.food_batch_made,
         batch_queue.food_entries, batch_queue.queued_entries,
         batch_queue.food_made, batch_queue.is_food)
try:
    cadence.ordered_inventory = lambda: (list(inv), {})
    cadence.ledger.inventory = lambda: list(inv)
    cadence.ledger.published_slugs = lambda: {"food-aired"}
    batch_queue.food_batch_made = lambda slug: slug.startswith("food-batch")
    batch_queue.food_entries = lambda: [{"slug": "food-made"},
                                        {"slug": "food-aired"}]
    rw = cadence.runway(6)
    batch_queue.queued_entries = lambda: [
        {"slug": "food-todo", "domain": "food-science"},
        {"slug": "food-made", "domain": "food-science"},
        {"slug": "food-batch-1", "domain": "food-science"},
        {"slug": "food-aired", "domain": "food-science"}]
    batch_queue.food_made = lambda slug: slug in ("food-made", "food-aired")
    batch_queue.is_food = lambda r: (r.get("domain") if isinstance(r, dict)
                                     else "") == "food-science"
    food_count = len(batch_queue.food_unmade())
finally:
    (cadence.ordered_inventory, cadence.ledger.inventory,
     cadence.ledger.published_slugs, batch_queue.food_batch_made,
     batch_queue.food_entries, batch_queue.queued_entries,
     batch_queue.food_made, batch_queue.is_food) = saved
if rw["publishable"] != 2:
    fails.append(f"runway counted {rw['publishable']} publishable, want 2 "
                 f"(deep-a + the food pipeline's unaired script; batch-made "
                 f"food scripts never air)")
if food_count != 1:
    fails.append(f"food rows the food pipeline has yet to make: {food_count}, "
                 f"want 1 (food-todo)")

# ------------- 4. relevance: grown-seed junk never reaches the scored queue
import re                                                  # noqa: E402

POOLS, EXOTIC = "how deep are pools", "how to get brine pool exotic"
SQUID, SHARK = ("what does a vampire squid look like",
                "how deep can a goblin shark dive")
shown: list[str] = []


def judge(msgs, key, **kw):
    """The $0 route, stubbed: says no to the swimming pool, gives NO verdict
    for the goblin shark (refuse on doubt), yes to everything else."""
    text = msgs[0]["content"]
    shown.append(text)
    out = []
    for m in re.finditer(r"^(\d+)\. (.+)$", text, re.M):
        n, q = m.groups()
        if q == SHARK:
            continue
        out.append(f"{n}. no - a swimming pool" if q == POOLS else f"{n}. yes")
    return {"choices": [{"message": {"content": "\n".join(out)}}],
            "model_used": "stub"}


scored: list = []
saved = (pod.candidates, pod.score_queries, llm_router.complete)
pod.candidates = lambda domain, **kw: ([POOLS, EXOTIC, SQUID, SHARK], [])
pod.score_queries = lambda domain, qs, pause, budget: (
    scored.extend(qs) or ([], []))
llm_router.complete = judge
try:
    blob = quiet(pod.build, DOM, 0, 0)
    llm_router.complete = dead
    try:
        quiet(pod.build, DOM, 0, 0)
        unchecked = None
    except SystemExit as e:
        unchecked = e.code
finally:
    pod.candidates, pod.score_queries, llm_router.complete = saved
refused = {k["query"]: k["killed_by"] for k in blob["refused_before_scoring"]}
if scored != [SQUID]:
    fails.append(f"the gate scored {scored}, want only [{SQUID!r}] "
                 f"(on-domain kept; pools, game phrasing, no-verdict refused)")
if refused.get(POOLS) != "OFF_DOMAIN_RELEVANCE":
    fails.append(f"{POOLS!r} not refused on relevance: {refused}")
if refused.get(EXOTIC) != "OTHER_CHANNEL" or any(EXOTIC in t for t in shown):
    fails.append(f"{EXOTIC!r} must be refused deterministically, before the "
                 f"model sees it: {refused}")
if refused.get(SHARK) != "OFF_DOMAIN_RELEVANCE":
    fails.append(f"a row the model left unanswered was not refused: {refused}")
if not shown or "Deep sea and ocean science" not in shown[0]:
    fails.append("the relevance prompt does not carry the domain's taxonomy "
                 "definition")
if unchecked != pod.NAMED_STOP:
    fails.append(f"a dead route admitted candidates (exit {unchecked}), want "
                 f"the RELEVANCE_UNCHECKED named stop")
if pod.parse_seeds("fisch brine pool\nbrine pool", []) != ["brine pool"]:
    fails.append("a grown seed naming a game was kept")

print(f"examined {len(picked)} candidate(s), {len(validated)} rebuild draft(s)")
for f in fails:
    print(f"  ✗ {f}")
raise SystemExit(1 if fails else 0)
