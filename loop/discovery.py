"""Tags and hashtags, derived per episode from its own domain and subject.

Owner instruction, 2026-09-21: every video on the channel carried the same
seven deep-sea tags and no hashtags at all — including the 18
materials-and-manufacturing episodes, tagged "marine biology" like everything
else. Nothing here is invented: a tag is either the episode's own subject
(pulled from its title, the way `loop/upload.py` already treats the title as
the question), a real autocomplete-mined phrase that actually occurs in the
episode's own narration, or a name from the one per-domain / per-channel list
in `loop/config.json`'s `discovery` block.

## Ordering, and why it is load-bearing

YouTube displays the first three hashtags in a video's description above its
title. `hashtags_for` orders subject, then domain, then channel, so those
three are always the episode's own subject, its domain, and the channel —
never three domain or channel hashtags with the subject pushed off-screen.

## Refuses an unknown domain

`domains.require_known` is the one place a domain name is validated in this
repo; every function here goes through it rather than trusting a caller's
string, for the same reason `loop/domains.py` itself refuses one: a domain
that is not in `research/proposed-taxonomy.json` was invented by someone who
did not read the twenty that were scored, and every tag drawn from it would be
about nothing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import domains                                     # noqa: E402
from common import config                          # noqa: E402

SCRIPTS = ROOT / "scripts"

# YouTube ignores every hashtag past 60 and shows only the first 3 above the
# title; 6 leaves headroom while keeping the three that matter (subject,
# domain, channel) always inside it.
HASHTAG_MAX = 6
# YouTube's own tags-field limit (loop/upload.py:TAG_TOTAL_MAX), duplicated
# here rather than imported: loop/upload.py imports this module, so importing
# back would be circular. V41 asserts the two stay equal.
TAG_TOTAL_MAX = 400
# Real, mined phrases considered per episode. Capped so one episode's tag list
# cannot be dominated by autocomplete noise.
MINED_TAG_MAX = 8

# Each live domain's OWN mined-autocomplete corpus, the same file its
# research/publish_order*.py module already cites as its CORPUS — not
# regenerated here. A domain with no file mapped simply contributes no
# mined-query tags; it still gets its own and the channel's, never nothing.
MINED_QUERIES_FILE = {
    "deep-sea-ocean-science": "mined_queries.json",
    "materials-and-manufacturing": "mined_queries_materials.json",
}

_QUESTION_STEM = re.compile(r"^(why|how|what|when|where|which|who)\b\s*")
# Leading words that carry no subject of their own — auxiliaries, articles,
# and the adjective half of "how big/hot/strong/old ...". Stripped from the
# FRONT only, and only up to the first word that is not one of them, so a
# subject that legitimately contains one of these later ("old iron", "iron
# not rust" before trailing-strip runs) is untouched.
_LEADING_FILL = {"is", "are", "does", "do", "did", "can", "could", "would",
                 "will", "has", "have", "big", "hot", "strong", "much",
                 "many", "old", "so", "a", "an", "the"}
# Trailing words that are the question's own scaffolding ("... made OF",
# "... so STRONG", "... not RUST"), stripped from the BACK only, one at a
# time, so a real closing noun is never touched.
_TRAILING_FILL = {"made", "of", "get", "not", "rust", "strong", "weird",
                  "scary", "red", "transparent", "so"}


def _script_path(slug: str) -> Path:
    return SCRIPTS / f"{slug}.md"


def _script_title(slug: str, script_text: str | None = None) -> str:
    """The script's own H1 — the question, by the same rule the title is."""
    text = script_text
    if text is None:
        p = _script_path(slug)
        text = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    return m.group(1).strip() if m else slug.replace("-", " ")


def subject_of(title: str) -> str:
    """The episode's subject, with the question stem stripped.

    "How strong is titanium?" -> "titanium". Never empty and never leads with
    a question word — `loop/tests/test_discovery.py` asserts both across
    every real script in the repository. Precision beyond that is not the
    job: this feeds one tag and one hashtag among several, never the title.
    """
    q = title.strip().rstrip("?").strip()
    lower = q.lower()
    m = _QUESTION_STEM.match(lower)
    rest = lower[m.end():] if m else lower

    words = rest.split()
    i = 0
    while i < len(words) - 1 and words[i] in _LEADING_FILL:
        i += 1
    words = words[i:]
    while len(words) > 1 and words[-1] in _TRAILING_FILL:
        words.pop()

    subject = " ".join(words).strip()
    return subject or rest.strip() or lower.strip()


def _narration_text(script_text: str) -> str:
    m = re.search(r"## Narration\s*\n(.*)", script_text, re.S)
    return (m.group(1) if m else script_text).lower()


def _mined_candidates(domain: str) -> list[dict]:
    name = MINED_QUERIES_FILE.get(domain)
    if not name:
        return []
    path = ROOT / "research" / name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in (data.get("queries") or []) if r.get("query")]
    return sorted(rows, key=lambda r: -(r.get("seed_hits") or 0))


def _discovery_block(cfg: dict, domain: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """(domain tags, domain hashtags, channel tags, channel hashtags)."""
    disc = cfg.get("discovery") or {}
    if not disc:
        raise KeyError("loop/config.json has no `discovery` block")
    dom = (disc.get("domains") or {}).get(domain) or {}
    chan = disc.get("channel") or {}
    return (list(dom.get("tags") or []), list(dom.get("hashtags") or []),
            list(chan.get("tags") or []), list(chan.get("hashtags") or []))


def _mined_tags(domain: str, narration_lower: str) -> list[str]:
    out = []
    for row in _mined_candidates(domain):
        if len(out) >= MINED_TAG_MAX:
            break
        q = row["query"].strip()
        if q and q.lower() in narration_lower:
            out.append(q)
    return out


def tags_for(slug: str, script_text: str, domain: str) -> list[str]:
    """Ordered, de-duplicated tags for one episode: subject, mined phrases
    actually in its narration, the domain's tags, the channel's tags —
    capped at YouTube's own `TAG_TOTAL_MAX` characters.
    """
    domains.require_known(domain)
    cfg = config()
    domain_tags, _, channel_tags, _ = _discovery_block(cfg, domain)
    subject = subject_of(_script_title(slug, script_text))
    mined = _mined_tags(domain, _narration_text(script_text))

    seen: set[str] = set()
    out: list[str] = []
    total = 0
    for t in [subject, *mined, *domain_tags, *channel_tags]:
        t = t.strip()
        key = t.lower()
        if not t or key in seen:
            continue
        if total + len(t) + 1 > TAG_TOTAL_MAX:
            continue
        seen.add(key)
        out.append(t)
        total += len(t) + 1
    return out


def _hashtag_word(phrase: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", phrase)
    return "#" + "".join(w.capitalize() for w in words) if words else ""


def hashtags_for(slug: str, script_text: str, domain: str) -> list[str]:
    """Ordered, de-duplicated hashtags: subject, domain, channel — capped at
    `HASHTAG_MAX` so the first three (what YouTube shows above the title) are
    always the episode's own subject, its domain, and the channel.
    """
    domains.require_known(domain)
    cfg = config()
    _, domain_hashtags, _, channel_hashtags = _discovery_block(cfg, domain)
    subject_tag = _hashtag_word(subject_of(_script_title(slug, script_text)))

    seen: set[str] = set()
    out: list[str] = []
    for h in [subject_tag, *domain_hashtags, *channel_hashtags]:
        h = h.strip()
        key = h.lower()
        if not h or not h.startswith("#") or key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= HASHTAG_MAX:
            break
    return out


# --------------------------------------------------- the description's line

def is_hashtag_line(line: str) -> bool:
    line = line.strip()
    return bool(line) and all(tok.startswith("#") for tok in line.split())


def hashtag_line(hashtags: list[str]) -> str:
    return " ".join(h for h in hashtags if h)


def add_hashtag_line(description: str, hashtags: list[str]) -> str:
    """Append the hashtag line as the LAST line, one blank line above it."""
    line = hashtag_line(hashtags)
    if not line:
        return description
    return description.rstrip("\n") + "\n\n" + line


def strip_hashtag_line(description: str) -> str:
    """The inverse of `add_hashtag_line` — used by V41 and the tests to prove
    the two round-trip, and by the backfill lane to compare a live
    description against one with no hashtag line yet.
    """
    lines = description.split("\n")
    if not lines or not is_hashtag_line(lines[-1]):
        return description
    lines = lines[:-1]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
