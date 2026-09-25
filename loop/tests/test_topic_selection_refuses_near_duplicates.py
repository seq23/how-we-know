"""Topic selection refuses near-duplicate questions and other-channel topics.

THE INCIDENT (2026-09-25 coverage review). Week 2026-W39's four picks were
"how deep mariana trench", "what lives in the depths of the ocean", "what
lives in the deep" and "what lives in the sea" - the last three one question,
and all three episode 08 ("What creatures live in the deep sea?"), aired
weeks earlier. The materials-and-manufacturing queue held ten phrasings of
"how are microchips made" (already made), three naming another channel:
"... veritasium", "... ted", "... branch education".

WHAT THIS PROVES, with the exact strings from the incident:

  1. GENERATION. research/publish_order_domain.py `_screen()` - the one
     screen every mined candidate passes - admits at most one of the three
     "what lives" phrasings on a fresh domain, none of them once episode 08
     is made, no variant of "how are microchips made" once it is made, and
     no candidate naming another channel. Distinct questions still pass.
  2. READ. loop/batch_queue.py, the one list rank.py (Sunday), draft.py
     (Monday), the Mac's batch and the upload lane all read, refuses the
     same rows from a queue FILE that already holds them - loop/score.py
     only regenerates a non-empty queue never, so a generation-only fix
     would leave every duplicate on disk selectable. The week's pick
     (the first four unwritten rows) holds no two phrasings of one question.
  3. THE REAL REPO. Today's real queue, read through batch_queue, contains
     none of the incident's rows, and V43 passes on it; V43 FAILS when the
     read-time rule is bypassed (negative proof).
  4. THE RULE ITSELF (loop/topic_identity.py), both directions: every
     incident pair is the same question, and a panel of genuinely different
     questions from the same queues is not.

Oracles in 1-3 are explicit slug lists, not the module under test, so this
file fails on the pre-fix code rather than agreeing with it.

Hard-fails if it examines zero items. Writes nothing under loop/state/.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))

import batch_queue                                         # noqa: E402
import ledger                                              # noqa: E402

fails: list[str] = []
examined = 0

DEEP_SAME = ["what lives in the depths of the ocean", "what lives in the deep",
             "what lives in the sea"]
CHIP_SAME = ["how microchips are made veritasium",
             "how are microchips made so small", "how are tiny microchips made",
             "how are computer microchips made",
             "how are microchips manufactured", "how are apple microchips made",
             "how microchips are made animation",
             "how are microchips made branch education",
             "how are microchips made cpu manufacturing process steps",
             "how are microchips made ted", "how the microchips are made",
             "how microchips are made in factory"]
OTHER_CHANNEL = ["how microchips are made veritasium",
                 "how are microchips made ted",
                 "how are microchips made branch education"]
DISTINCT = ["how deep mariana trench", "what lives in mariana trench",
            "how are microchips designed", "does damascus steel rust",
            "is aluminum stronger than steel"]
EP08 = ("08-what-creatures-live-in-the-deep-sea",
        "what creatures live in the deep sea")
CHIPS = ("how-are-microchips-made", "how are microchips made")


def slug(q: str) -> str:
    return q.strip().lower().replace("'", "").replace(",", "").replace(" ", "-")


# ------------------------------------------------------ 1. generation
import publish_order_domain as pod                         # noqa: E402

def screen(queries: list[str], seeds: str, made: set,
           anchors: bool) -> tuple[list[str], list[dict]]:
    rows = [{"query": q, "question": True, "noise": False, "excluded": False,
             "probe_hits": 100 - i} for i, q in enumerate(queries)]
    seed_tokens = {pod._stem(t) for t in pod.content_tokens(seeds)} - pod.FRAME
    seen: list = []
    picked: list = []
    kw = {}
    if "made_questions" in inspect.signature(pod._screen).parameters:
        # The real made-question list: the ledger plus every scripts/*.md H1.
        kw["made_questions"] = (pod.made_question_keys() if anchors else [])
    _, killed = pod._screen(rows, seed_tokens, 50, seen, picked,
                            made if anchors else set(), None, **kw)
    return picked, killed


# 1a. A fresh domain, nothing made: one "what lives" survives, not three.
picked, _ = screen(DEEP_SAME + DISTINCT[:2], "deep sea ocean lives mariana trench",
                   set(), anchors=False)
examined += 1
n = sum(1 for q in DEEP_SAME if q in picked)
if n != 1:
    fails.append(f"generation, nothing made: {n} of the three 'what lives' "
                 f"phrasings were admitted (want exactly 1): {picked}")
for q in DISTINCT[:2]:
    examined += 1
    if q not in picked:
        fails.append(f"generation refused a distinct question: {q!r}")

# 1b. Episode 08 made: none of the three survives.
made = {s for s, _ in (EP08, CHIPS)}
picked, killed = screen(DEEP_SAME + DISTINCT[:2],
                        "deep sea ocean lives mariana trench", made,
                        anchors=True)
examined += 1
leaked = [q for q in DEEP_SAME if q in picked]
if leaked:
    fails.append(f"generation admitted a rephrasing of episode 08 "
                 f"('{EP08[1]}'): {leaked}")

# 1c. Microchips made: no variant survives, the channel ones by name.
picked, killed = screen(CHIP_SAME + DISTINCT[2:],
                        "microchip steel damascus aluminum carbon made design "
                        "rust", made, anchors=True)
examined += 1
leaked = [q for q in CHIP_SAME if q in picked]
if leaked:
    fails.append(f"generation admitted {len(leaked)} rephrasing(s) of 'how are "
                 f"microchips made', already made: {leaked}")
by_q = {k["query"]: k for k in killed}
for q in OTHER_CHANNEL:
    examined += 1
    if (by_q.get(q) or {}).get("killed_by") != "OTHER_CHANNEL":
        fails.append(f"generation did not refuse {q!r} as naming another "
                     f"channel (got {(by_q.get(q) or {}).get('killed_by')})")
for q in DISTINCT[2:]:
    examined += 1
    if q not in picked:
        fails.append(f"generation refused a distinct question: {q!r}")


# ------------------------------------------------------ 2. read (fixture)
def with_fixture(queue: list[str], published: list[tuple[str, str]],
                 scripts: dict | None = None):
    tmp = Path(tempfile.mkdtemp(prefix="near-dup-queue-"))
    (tmp / "research").mkdir()
    (tmp / "scripts").mkdir()
    for s_, h1 in (scripts or {}).items():
        (tmp / "scripts" / f"{s_}.md").write_text(f"# {h1}\n\nbody\n")
    rows = [{"slug": slug(q), "query": q} for q in queue]
    (tmp / "research" / "publish_order_fixture.json").write_text(
        json.dumps({"queue": rows}))
    saved = (batch_queue.ROOT, batch_queue.PROMOTION_HOLDS, ledger.load)
    batch_queue.ROOT = tmp
    batch_queue.PROMOTION_HOLDS = tmp / "no-holds.json"
    ledger.load = lambda: {"published": [{"slug": s, "question": q}
                                         for s, q in published],
                           "queued": [], "updated": None}
    return saved


def restore(saved) -> None:
    batch_queue.ROOT, batch_queue.PROMOTION_HOLDS, ledger.load = saved


W39 = ["how deep mariana trench"] + DEEP_SAME + ["what lives in mariana trench"]

# 2a. The W39 queue as it sits on disk, episode 08 and microchips made.
saved = with_fixture(W39 + CHIP_SAME + DISTINCT[2:], [EP08, CHIPS])
try:
    queued = batch_queue.queued_slugs()
    week = [r["slug"] for r in batch_queue.unwritten_entries()[:4]]
finally:
    restore(saved)
examined += 1
bad = [s for s in queued if s in {slug(q) for q in DEEP_SAME + CHIP_SAME}]
if bad:
    fails.append(f"read: the queue still offers {len(bad)} rephrasing(s) of an "
                 f"episode already made: {bad}")
examined += 1
if sum(1 for s in week if s in {slug(q) for q in DEEP_SAME}) > 0:
    fails.append(f"read: the week's pick repeats episode 08: {week}")
for q in ["how deep mariana trench", "what lives in mariana trench"] + DISTINCT[2:]:
    examined += 1
    if slug(q) not in queued:
        fails.append(f"read refused a distinct question: {q!r}")

# 2b. Nothing made yet: the week holds ONE of the three, not three.
saved = with_fixture(W39, [])
try:
    week = [r["slug"] for r in batch_queue.unwritten_entries()[:4]]
    refused = batch_queue.refused_entries() if hasattr(
        batch_queue, "refused_entries") else []
finally:
    restore(saved)
examined += 1
n = sum(1 for s in week if s in {slug(q) for q in DEEP_SAME})
if n != 1:
    fails.append(f"read, nothing made: the week's pick holds {n} phrasings of "
                 f"'what lives in the deep sea' (want 1): {week}")
examined += 1
if any(not (r.get("killed_by") and r.get("why")) for r in refused):
    fails.append("read: a refused row carries no killed_by/why - a refusal "
                 "must be named")


# 2c. A WRITTEN row is judged on the question its script asks, not only on
# its queue string: the held why-deep-sea-creatures row is queued as "why
# deep sea creatures" (a stub that matches nothing) and its script is "Why do
# deep sea creatures look so strange?" - episode 01, "... look so weird".
EP01 = ("01-why-deep-sea-creatures-look-so-weird",
        "why deep sea creatures look so weird")
saved = with_fixture(["why deep sea creatures", "how deep is the ocean"],
                     [EP01], {"why-deep-sea-creatures":
                              "Why do deep sea creatures look so strange?"})
try:
    queued = batch_queue.queued_slugs()
finally:
    restore(saved)
examined += 1
if "why-deep-sea-creatures" in queued:
    fails.append("read: a written row whose script repeats episode 01 is "
                 "still queued (judged on its queue string only)")
if "how-deep-is-the-ocean" not in queued:
    fails.append("read refused 'how deep is the ocean', a distinct question")


# ------------------------------------------------------ 3. the real repo
real = set(batch_queue.queued_slugs())
real_unwritten = {r["slug"] for r in batch_queue.unwritten_entries()}
for q in DEEP_SAME + CHIP_SAME:
    examined += 1
    if slug(q) in real or slug(q) in real_unwritten:
        fails.append(f"real queue: {slug(q)} is still selectable")

import validate                                            # noqa: E402

v43 = getattr(validate, "v43_queue_asks_distinct_questions", None)
examined += 1
if v43 is None:
    fails.append("validate.v43_queue_asks_distinct_questions does not exist")
else:
    r = v43([])
    if not r.ok:
        fails.append(f"V43 fails on the real queue: {r.failures[:3]}")
    # Negative proof: bypass the read-time rule and V43 must fail.
    orig = batch_queue._screened
    batch_queue._screened = lambda: (batch_queue._raw_entries(), [])
    try:
        r = v43([])
    finally:
        batch_queue._screened = orig
    examined += 1
    if r.ok:
        fails.append("V43 PASSED with the read-time rule bypassed - a guard "
                     "that cannot see what it governs")
    # A week that repeats episode 08 fails even if the queue is clean.
    examined += 1
    r = v43([{"slug": slug(DEEP_SAME[2]), "question": DEEP_SAME[2]}])
    if r.ok:
        fails.append("V43 passed a week item that repeats episode 08")

examined += 1
r = validate.v39_queue_depth_is_remaining_not_scored()
if not r.ok:
    fails.append(f"V39 fails with refused rows removed from depth: "
                 f"{r.failures[:2]}")


# ------------------------------------------------------ 4. the rule
try:
    import topic_identity as T                             # noqa: E402
except ImportError as e:
    fails.append(f"loop/topic_identity.py missing: {e}")
    T = None
if T is not None:
    same = [(a, b) for i, a in enumerate(DEEP_SAME) for b in DEEP_SAME[i + 1:]]
    same += [(q, EP08[1]) for q in DEEP_SAME]
    same += [(q, CHIPS[1]) for q in CHIP_SAME if q not in OTHER_CHANNEL]
    same += [("what is carbon fibre made of", "what is carbon fiber made of"),
             ("how strong is steel", "why is steel so strong"),
             ("is damascus steel worth it", "is damascus steel better"),
             ("what lies in the deepest part of the ocean",
              "what is the deepest part of the ocean"),
             # a numbered catalogue slug standing in for its question
             ("10-what-is-the-deepest-part-of-the-ocean",
              "what lives in the deepest part of the ocean")]
    for a, b in same:
        examined += 1
        if not T.same_question(a, b):
            fails.append(f"rule: {a!r} and {b!r} should be one question; keys "
                         f"{sorted(T.question_key(a))} / "
                         f"{sorted(T.question_key(b))}")
    different = [("how deep is the ocean",
                  "how deep sea creatures survive the pressure"),
                 ("how deep is the ocean", "what lives in the sea"),
                 ("how deep mariana trench", "what lives in mariana trench"),
                 ("how are microchips designed", "how are microchips made"),
                 ("does damascus steel rust", "is damascus steel better"),
                 ("is aluminum stronger than steel",
                  "is titanium stronger than steel"),
                 ("what is a semiconductor made of", "how are microchips made"),
                 ("how is a silicon wafer made", "how are microchips made"),
                 ("why many deep sea creatures are red",
                  "why some deep sea creatures are transparent")]
    for a, b in different:
        examined += 1
        if T.same_question(a, b):
            fails.append(f"rule: {a!r} and {b!r} are different questions but "
                         f"were merged: {T.why_same(T.question_key(a), T.question_key(b))}")
    for q in OTHER_CHANNEL:
        examined += 1
        if not T.names_other_channel(q):
            fails.append(f"rule: {q!r} names another channel, not detected")
    for q in ["how does tempered glass shatter", "what is the midnight zone",
              "how hot does a welding arc get", "why is steel so strong"]:
        examined += 1
        if T.names_other_channel(q):
            fails.append(f"rule: {q!r} flagged as naming a channel: "
                         f"{T.names_other_channel(q)}")
    # No two episodes ALREADY MADE may read as one question - if they did,
    # the rule would be merging the channel's own distinct catalogue.
    made_qs = sorted({(r.get("question") or "").strip().lower()
                      for r in ledger.load()["published"] if r.get("question")})
    examined += len(made_qs)
    for i, a in enumerate(made_qs):
        for b in made_qs[i + 1:]:
            if T.same_question(a, b):
                fails.append(f"rule merges two episodes already made: {a!r} / "
                             f"{b!r}")

# ------------------------------------------------------ 5. the upload lane
# W39's render_queue.json hands the Mac "what-lives-in-the-sea" as `queued`.
# Refused on read, it is out of the queue by decision: the upload lane must
# not page a person to re-queue a duplicate, and a genuinely stranded script
# must still page.
os.environ.setdefault("LOOP_DRY_RUN", "1")
import cloud_upload as CU                                  # noqa: E402

dup = slug(DEEP_SAME[2])
handoff = [{"slug": dup, "status": "queued"}]
kw = ({"refused": {dup}} if "refused" in
      inspect.signature(CU.diagnose_empty_shelf).parameters else {})
why = CU.diagnose_empty_shelf(["a"], {"a"}, set(), handoff, promotion_held={},
                              runway={"level": "ok", "message": "ok"}, **kw)
examined += 1
if why["code"] == "AUTHORED_NOT_QUEUED":
    fails.append(f"upload lane pages AUTHORED_NOT_QUEUED for {dup}, a row "
                 f"refused as a repeat of episode 08")
why = CU.diagnose_empty_shelf(["a"], {"a"}, set(),
                              handoff + [{"slug": "stranded", "status": "queued"}],
                              promotion_held={},
                              runway={"level": "ok", "message": "ok"}, **kw)
examined += 1
if why["code"] != "AUTHORED_NOT_QUEUED" or why["held_items"] != ["stranded"]:
    fails.append(f"upload lane stopped paging a genuinely stranded script: "
                 f"{why['code']} {why['held_items']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} item(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
