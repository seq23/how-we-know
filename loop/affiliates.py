"""Affiliate links in NEW episode descriptions, from ONE config file.

    .venv/bin/python loop/affiliates.py scripts/how-hot-does-a-welding-arc-get.md

Owner-approved build, 2026-10-08: the audit found nothing to buy or follow in
any description. This adds a short block naming the books and gear an episode
ALREADY CITES, linked to Amazon (and Bookshop.org where an ISBN is verified).

THE ONE FILE is channel/affiliates.json. Its two IDs ship EMPTY: until the
owner has an Amazon Associates tag or a Bookshop.org affiliate ID, every link
is a plain store link with no tracking parameter. Filling an ID in that file
is the only change needed to turn tracking on.

ONLY WHAT THE EPISODE CITES. An item is listed when one of its `cited_as`
strings appears in the episode's own `## Sources` section. No topic guessing:
a deep-sea episode that cites NOAA web pages gets no block at all, which is
correct — recommending a book the episode never used would be the description
equivalent of an invented figure.

The FTC disclosure line is always printed with the block (it says links "may
be" affiliate links, true in both states); the Amazon Associates sentence is
added only once an Amazon tag is set, because only then is it true.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "channel" / "affiliates.json"

AMAZON_SIGNUP = "https://affiliate-program.amazon.com/"
BOOKSHOP_SIGNUP = "https://bookshop.org/affiliates"


def load(path: Path | None = None) -> dict:
    return json.loads((path or CONFIG).read_text(encoding="utf-8"))


def sources_section(script_text: str) -> str:
    m = re.search(r"## Sources\s*\n(.*?)(\n## |\Z)", script_text or "", re.S)
    return m.group(1) if m else ""


def cited_items(script_text: str, cfg: dict) -> list[dict]:
    src = sources_section(script_text).lower()
    if not src:
        return []
    return [it for it in cfg.get("items", [])
            if any(c.lower() in src for c in it.get("cited_as", []) if c)]


def amazon_url(item: dict, tag: str) -> str | None:
    q = item.get("amazon_search")
    if not q:
        return None
    url = "https://www.amazon.com/s?k=" + urllib.parse.quote_plus(q)
    return url + ("&tag=" + urllib.parse.quote(tag) if tag else "")


def bookshop_url(item: dict, aid: str) -> str | None:
    isbn = (item.get("bookshop_isbn13") or "").replace("-", "")
    if not re.fullmatch(r"97[89]\d{10}", isbn):
        return None
    if aid:
        return f"https://bookshop.org/a/{urllib.parse.quote(aid)}/{isbn}"
    return "https://bookshop.org/search?keywords=" + isbn


def block_for(script_text: str, cfg: dict | None = None) -> str:
    """The description block for one episode, or "" when it cites nothing."""
    cfg = cfg if cfg is not None else load()
    items = cited_items(script_text, cfg)
    if not items:
        return ""
    tag = (cfg.get("amazon_associates_tag") or "").strip()
    aid = (cfg.get("bookshop_affiliate_id") or "").strip()
    # The disclosure goes ABOVE the links: the FTC wants it seen before the
    # click, not after it.
    lines = [cfg.get("heading") or "Books and references cited in this episode:",
             cfg["disclosure"]]
    if tag:
        lines.append(cfg["amazon_disclosure"])
    for it in items:
        a, b = amazon_url(it, tag), bookshop_url(it, aid)
        if a:
            lines.append(f"• {it['label']} — Amazon: {a}")
        if b:
            lines.append(f"• {it['label']} — Bookshop.org: {b}")
    if not any(l.startswith("• ") for l in lines):
        return ""
    return "\n".join(lines)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(block_for(Path(p).read_text(encoding="utf-8")) or f"{p}: cites no listed book or gear")
