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


def queued_slugs() -> list[str]:
    """Every gated, surviving topic slug, best first, deduplicated."""
    files = publish_order_files()
    if not files:
        raise NoPublishOrder(
            f"no research/{PUBLISH_ORDER_GLOB} found under {ROOT} - refusing to "
            "report an empty queue, which is indistinguishable from a finished one"
        )
    out: list[str] = []
    seen: set[str] = set()
    for path in files:
        for row in json.loads(path.read_text()).get("queue") or []:
            slug = row.get("slug") if isinstance(row, dict) else row
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(slug)
    return out


if __name__ == "__main__":
    for s in queued_slugs():
        print(s)
