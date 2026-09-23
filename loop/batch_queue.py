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
    """
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
            refused[s] = ("held awaiting the owner's promotion decision "
                          f"(loop/promotion_holds.json: "
                          f"{holds[s].get('awaiting', 'promotion')})")
        elif s not in queued:
            refused[s] = ("not in any research/publish_order*.json - the Monday "
                          "lane writes only topics already in the publish queue")
        else:
            allowed.append(s)
    return allowed, refused


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


if __name__ == "__main__":
    for s in queued_slugs():
        print(s)
