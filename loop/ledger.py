"""The published ledger — the loop's memory of what has already shipped.

Two jobs:
  * enforce "never repeat a published question"
  * tell the ranking stage how much authored inventory is still unspent

Every row is appended by a stage that has a receipt behind it. Nothing is
written here on intent; only on evidence.
"""
from __future__ import annotations

import glob
import os
import re

from common import LOOP, ROOT, now, read_json, write_json

LEDGER = LOOP / "state" / "ledger.json"

EMPTY = {"published": [], "queued": [], "updated": None}


def load() -> dict:
    d = read_json(LEDGER, default=dict(EMPTY))
    for k in EMPTY:
        d.setdefault(k, EMPTY[k])
    return d


def save(d: dict) -> None:
    d["updated"] = now()
    write_json(LEDGER, d)


def published_slugs() -> set[str]:
    return {r["slug"] for r in load()["published"]}


def published_questions() -> set[str]:
    return {normalise(r.get("question", "")) for r in load()["published"]}


def normalise(q: str) -> str:
    q = q.lower().strip().rstrip("?").strip()
    q = re.sub(r"[^a-z0-9 ]+", " ", q)
    q = re.sub(r"\b(the|a|an|is|are|do|does|of|in|to)\b", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def script_title(path) -> str:
    with open(path) as fh:
        for line in fh:
            if line.startswith("# "):
                return line[2:].strip()
    return os.path.basename(path)


def all_scripts() -> list[dict]:
    rows = []
    for p in sorted(glob.glob(str(ROOT / "scripts" / "*.md"))):
        slug = os.path.basename(p)[:-3]
        rows.append({"slug": slug, "path": os.path.relpath(p, ROOT),
                     "question": script_title(p)})
    return rows


def inventory() -> list[dict]:
    """Authored scripts that have not been published yet.

    This is the loop's runway. While it is non-empty the weekly queue is drawn
    from it and no LLM authoring — and no competition score — is required to
    ship a week.
    """
    done = published_slugs()
    return [s for s in all_scripts() if s["slug"] not in done]


def record_published(slug: str, question: str, video_id: str,
                     receipt: str) -> None:
    d = load()
    if slug in {r["slug"] for r in d["published"]}:
        return
    d["published"].append({"slug": slug, "question": question,
                           "video_id": video_id, "receipt": receipt,
                           "published_at": now()})
    save(d)


if __name__ == "__main__":
    inv = inventory()
    print(f"published : {len(published_slugs())}")
    print(f"inventory : {len(inv)} unpublished authored script(s)")
    for s in inv[:12]:
        print(f"   {s['slug']}")
    if len(inv) > 12:
        print(f"   … and {len(inv) - 12} more")
