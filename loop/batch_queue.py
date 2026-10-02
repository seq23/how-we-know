"""The publish queue as ONE list, across every domain.

`bin/batch-session.sh` used to open `research/publish_order.json` by name. That
was correct while the channel published one subject and became wrong the moment
it published two: the sixteen materials-and-manufacturing topics that
`research/publish_order_materials.json` had already gated and ranked were
invisible to the Mac, and the batch printed "nothing to do" with a queue that
was not empty. That is the defect class this repo keeps producing — two
components each keeping their own list with nothing linking them.

`loop/domains.py` had already solved it for the monthly review by globbing
`research/publish_order*.json` instead of naming one file. This module is that
same rule, in one place, so the batch and the review cannot drift apart.

Order is preserved: each file's queue in its own ranked order, files in sorted
filename order, a slug counted once however many files mention it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISH_ORDER_GLOB = "publish_order*.json"


class NoPublishOrder(Exception):
    """No publish-order file was found at all.

    A hard failure, never an empty list. A glob that matches nothing looks
    exactly like a queue that is finished, and the batch would print its
    "everything is narrated" named stop over a repo whose research directory
    had been renamed or moved out from under it.
    """


def publish_order_files() -> list[Path]:
    return sorted(ROOT.glob(f"research/{PUBLISH_ORDER_GLOB}"))


def queued_entries() -> list[dict]:
    """Every gated, surviving topic ROW, best first, deduplicated.

    The row, not just the slug, because the schedulers need what the ranking
    recorded alongside it - `query` is the episode's question and becomes its
    title. `loop/backfill.py` read the deep-sea file directly for exactly that
    and so could not schedule a materials episode at all.

    Each row carries `_domain_file`, the publish-order file it came from, so a
    caller can say which domain queued a topic without keeping a second map.

    DEDUPLICATED BY QUESTION, NOT ONLY BY SLUG (2026-09-25). A row that asks
    the same question as an episode already made, or as a row kept ahead of
    it, or that names another channel, is not in the queue - see
    `refused_entries()` for each one and why. This is the ONE place the rule
    is applied on read, so rank.py (Sunday), draft.py (Monday), the Mac's
    batch and the upload lane cannot disagree about it. The queue FILES are
    left as written: loop/score.py regenerates a domain's file only when its
    queue is empty, so a rule applied only at generation would leave every
    duplicate already on disk selectable for ever.
    """
    return _screened()[0]


def refused_entries() -> list[dict]:
    """Queue rows `queued_entries()` refused, each with `killed_by`, `matched`
    and `why`. Never silent: a refused topic is a named decision."""
    return _screened()[1]


def _question_of(row: dict) -> str:
    """The row's question: `query`, else `title`, else its slug spelled out -
    a title with no words in it ("?") is not a question to judge."""
    for q in (row.get("query"), row.get("title")):
        if q and any(c.isalpha() for c in q):
            return q.strip()
    return str(row.get("slug") or "").replace("-", " ").strip()


def _script_question(slug: str) -> str | None:
    """scripts/<slug>.md's H1, lowered, without its '?', or None."""
    path = ROOT / "scripts" / f"{slug}.md"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip().rstrip("?.!").strip().lower()
    return None


def made_questions(exclude: set | frozenset = frozenset()
                   ) -> list[tuple[str, frozenset]]:
    """[(question, question key)] for every episode already made or written:
    the ledger's published questions and every scripts/*.md H1, minus the
    slugs in `exclude`. The ONE list of "questions this channel has already
    answered" - research/publish_order_domain.py (generation) and
    loop/score.py (the Saturday hold gate) both read it."""
    import topic_identity as T                             # noqa: PLC0415
    qs = [q for s, q in _published_questions().items() if s not in exclude]
    for path in sorted((ROOT / "scripts").glob("*.md")):
        if path.stem not in exclude:
            q = _script_question(path.stem)
            if q:
                qs.append(q)
    out, seen = [], set()
    for q in qs:
        n = q.strip().rstrip("?").strip().lower()
        if n and n not in seen:
            seen.add(n)
            out.append((n, T.question_key(n)))
    return out


def _published_questions() -> dict[str, str]:
    """slug -> question for every episode already uploaded (the ledger)."""
    import ledger                                          # noqa: PLC0415
    return {r["slug"]: (r.get("question") or r["slug"].replace("-", " "))
            for r in ledger.load()["published"] if r.get("slug")}


def _screened() -> tuple[list[dict], list[dict]]:
    """(kept rows in queue order, refused rows).

    Precedence, so the thing already made always wins: episodes in the ledger
    first, then queued rows that already have scripts/<slug>.md, then the
    unwritten rows, each in queue order. A published row is never refused.
    """
    import topic_identity as T                             # noqa: PLC0415
    rows = _raw_entries()
    published = _published_questions()
    kept_keys: list[tuple[str, frozenset]] = [
        (q, T.question_key(q)) for q in published.values()]
    refused: dict[str, dict] = {}

    def written(r: dict) -> bool:
        return (ROOT / "scripts" / f"{r['slug']}.md").exists()

    passes = ([r for r in rows if r["slug"] not in published and written(r)],
              [r for r in rows if r["slug"] not in published
               and not written(r)])
    for group in passes:
        for r in group:
            # A written row is judged on its queue question AND on the
            # question its script actually asks: the held
            # why-deep-sea-creatures row is queued as "why deep sea
            # creatures" but its script is "Why do deep sea creatures look
            # so strange?" - episode 01 again.
            qs = [_question_of(r)]
            h1 = _script_question(r["slug"]) if written(r) else None
            if h1 and h1 != qs[0]:
                qs.append(h1)
            ch = next((c for c in map(T.names_other_channel, qs) if c), None)
            if ch:
                refused[r["slug"]] = {
                    **r, "killed_by": "OTHER_CHANNEL", "matched": ch,
                    "why": f"names another channel ({ch}); the searcher wants "
                           f"that channel's video, not ours"}
                continue
            keys = [(q, T.question_key(q)) for q in qs]
            if all(T.is_vague(k) for _, k in keys):
                refused[r["slug"]] = {
                    **r, "killed_by": "VAGUE", "matched": qs[-1],
                    "why": "names no subject beyond the domain's own core "
                           "words; there is nothing to answer about"}
                continue
            hit = next((h for _, k in keys
                        for h in [T.first_same(k, kept_keys)] if h), None)
            if hit:
                refused[r["slug"]] = {
                    **r, "killed_by": "NEAR_DUPLICATE", "matched": hit[0],
                    "why": f"same question as {hit[0]!r}: {hit[1]}"}
                continue
            kept_keys.extend(keys)
    kept = [r for r in rows if r["slug"] not in refused]
    return kept, [refused[r["slug"]] for r in rows if r["slug"] in refused]


def _raw_entries() -> list[dict]:
    """Every row of every publish-order file, one per slug, BEFORE the
    same-question rule. Only `_screened()` and the V43 validator read this."""
    files = publish_order_files()
    if not files:
        raise NoPublishOrder(
            f"no research/{PUBLISH_ORDER_GLOB} found under {ROOT} - refusing to "
            "report an empty queue, which is indistinguishable from a finished one"
        )
    out: list[dict] = []
    seen: set[str] = set()
    for path in files:
        for row in json.loads(path.read_text()).get("queue") or []:
            row = dict(row) if isinstance(row, dict) else {"slug": row}
            slug = row.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            row["_domain_file"] = path.name
            out.append(row)
    return out


def queued_slugs() -> list[str]:
    """Every gated, surviving topic slug, best first, deduplicated."""
    return [r["slug"] for r in queued_entries()]


# ---------------------------------------------------------------- the rule
#
# THE MONDAY LANE WRITES ONLY TOPICS ALREADY IN THE PUBLISH QUEUE. Owner
# decision, 2026-09-23. On 2026-09-21 loop/rank.py picked four mined-demand
# topics that were in no research/publish_order*.json and loop/draft.py
# authored them. The Mac's batch reads only the publish queue, so they could
# never be narrated, and the channel's shelf ran dry while the lane reported
# work done. The two functions below are the one place that rule lives;
# rank.py (selection) and draft.py (authoring) both call them, so the two
# stages cannot disagree about what "in the queue" means.

# Scripts held OUTSIDE the queue on purpose, awaiting the owner's promotion
# decision. Module level so a test can point it at a fixture.
PROMOTION_HOLDS = ROOT / "loop" / "promotion_holds.json"


def promotion_holds() -> dict[str, dict]:
    """slug -> hold row, for every script held awaiting promotion.

    A missing file means no holds. A file that exists but does not parse, or a
    row with no slug, raises: a hold register that silently reads as empty
    would turn a green, named hold back into a daily page, or worse, let a held
    slug be selected.
    """
    if not PROMOTION_HOLDS.exists():
        return {}
    doc = json.loads(PROMOTION_HOLDS.read_text())
    out: dict[str, dict] = {}
    for row in doc.get("holds") or []:
        slug = row.get("slug") if isinstance(row, dict) else None
        if not slug:
            raise ValueError(f"{PROMOTION_HOLDS.name}: a hold row has no slug: "
                             f"{row!r}")
        out[slug] = row
    return out


def publish_queue_gate(slugs: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split `slugs` into (allowed, refused{slug: why}) under the rule.

    Allowed means: in research/publish_order*.json AND not held for promotion.
    Order is preserved. Every refusal carries its reason, so a caller can print
    it by name - a refused topic is never a silent skip.
    """
    queued = set(queued_slugs())
    holds = promotion_holds()
    allowed, refused = [], {}
    for s in slugs:
        if s in holds:
            refused[s] = ("held awaiting the Saturday gate's promotion decision "
                          f"(loop/promotion_holds.json: "
                          f"{holds[s].get('awaiting', 'promotion')})")
        elif s not in queued:
            refused[s] = ("not in any research/publish_order*.json - the Monday "
                          "lane writes only topics already in the publish queue")
        else:
            allowed.append(s)
    return allowed, refused


# THE FLOOR EVERY ALLOCATED DOMAIN'S QUEUE IS MINED UP TO (2026-09-25).
# Below this many unwritten, non-duplicate, non-held topics a domain is
# refilled on Saturday (loop/score.py missing_queues), and the miner keeps
# widening its sources until it clears it or names DOMAIN_QUEUE_THIN. Four
# is two weeks of a domain's two weekly slots.
MIN_UNWRITTEN_TOPICS = 4


def unwritten_by_domain() -> dict[str, int]:
    """Domain -> count of unwritten_entries() rows, by the row's `domain` or
    its publish-order file's."""
    out: dict[str, int] = {}
    docs: dict[str, dict] = {}
    for r in unwritten_entries():
        d = r.get("domain")
        if not d:
            f = r["_domain_file"]
            if f not in docs:
                docs[f] = json.loads((ROOT / "research" / f).read_text())
            d = docs[f].get("domain")
        if d:
            out[d] = out.get(d, 0) + 1
    return out


def unwritten_entries() -> list[dict]:
    """Publish-queue rows that have no script at scripts/<slug>.md yet.

    These are the ONLY topics the Monday lane may author. Best first. An empty
    list is a real state (every queued topic is written) and callers must name
    it, never read it as "nothing happened".
    """
    holds = promotion_holds()
    return [r for r in queued_entries()
            if r["slug"] not in holds
            and not (ROOT / "scripts" / f"{r['slug']}.md").exists()]


def written_entries() -> list[dict]:
    """Publish-queue rows that HAVE a script at scripts/<slug>.md. Best first.

    THE ONLY ROWS THE MAC'S BATCH MAY PLAN, NARRATE, RENDER OR CAPTION. The
    queue deliberately carries unwritten topics - they are what the Monday
    lane authors (`unwritten_entries()`) - and from 2026-09-25 (a107efd) it
    carried thirty of them at once. `loop/captions_build.py` read the whole
    queue, asked the planner for a beat list for the first unwritten row,
    and the planner's `open(scripts/<slug>.md)` raised FileNotFoundError:
    every nightly batch from 26 Sep crashed at the captions stage and no
    Short reached R2 for a week. This is the counterpart of
    `unwritten_entries()` and the ONE definition of "the batch's queue", so
    the writer (draft.py) and the batch cannot disagree about whose row a
    slug is: unwritten rows belong to Monday, written rows to the Mac, and
    every queued row is exactly one or the other (or held).
    """
    return [r for r in queued_entries()
            if (ROOT / "scripts" / f"{r['slug']}.md").exists()]


def written_slugs() -> list[str]:
    """`written_entries()` as slugs."""
    return [r["slug"] for r in written_entries()]


if __name__ == "__main__":
    for s in queued_slugs():
        print(s)
