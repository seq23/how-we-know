"""Food kits: what one food needs to be a segment of a food episode.

The first food episode (Bread, Steak, Chocolate, 13 Oct 2026) was built by
hand: its shot list (research/food_footage.SHOTS), its word->footage table
(visuals/food.WORD_USES_*), its composite clips (WALL_CLIPS_BY,
KALEIDO_CLIPS_BY) and its diagram stills were all typed into the modules after
a session looked at contact sheets. That made the food pipeline a pipeline for
ONE episode: a chili, coffee or honey segment had nowhere to come from, and the
scheduled food lane (bin/food-session.sh, 2026-10-25) could not run.

A kit is the same information as DATA, one file per food, written by the food
author lane (loop/food_author.py) and read by the footage chain and the render:

    channel/food_kits/<food>.json
      food        the segment key ("chili"), also the script's section prefix
      label       the on-screen credit label ("CHILI")
      words       subject words; a clip's own first tag must name one
      queries     [{query, uses, take, sound}] - footage searches; `take`
                  distinct clips per query (needs <food>-<n>)
      off         words that mark a clip as off-subject for this food
      word_uses   [[narration word, [uses]]] - the paragraph's words pick clips
      diagram     {key, subject, prompt} - the one AI still under
                  {{cross_section}} (flagged altered content), optional

The three hand-built foods keep their hand-built tables; a kit never overrides
them. Hands for a kit clip are measured, not guessed: Apple Vision's hand-pose
detector on five frames (research/food_footage.vision_hands), recorded on the
clip's manifest row with its basis.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KITS = ROOT / "channel" / "food_kits"
BUILT_IN = ("chocolate", "bread", "steak")
KIT_FIELDS = ("food", "label", "words", "queries", "word_uses")
MIN_TAKE_TOTAL = 12          # >= food_episode.MIN_CLIPS_PER_SEGMENT (10) with room for misses


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def problems(kit: dict) -> list[str]:
    """[] when a kit can drive a segment; each line names what is missing."""
    p = [f"missing {k}" for k in KIT_FIELDS if not kit.get(k)]
    food = str(kit.get("food") or "")
    if food and not re.fullmatch(r"[a-z]+", food):
        p.append(f"food {food!r} must be one lowercase word (it is the section prefix)")
    if food in BUILT_IN:
        p.append(f"{food} is a built-in segment; its tables live in the modules")
    take = sum(int(q.get("take") or 1) for q in kit.get("queries") or [])
    if take < MIN_TAKE_TOTAL:
        p.append(f"queries take {take} clips, fewer than {MIN_TAKE_TOTAL}")
    for q in kit.get("queries") or []:
        if not q.get("query") or not q.get("uses"):
            p.append(f"query row {q!r} needs query and uses")
    for row in kit.get("word_uses") or []:
        if not (isinstance(row, list) and len(row) == 2 and isinstance(row[1], list)):
            p.append(f"word_uses row {row!r} is not [word, [uses]]")
    return p


def load_all() -> dict[str, dict]:
    """food -> kit, for every valid kit on disk. An invalid kit is skipped here
    and reported by the author lane and V73's sibling checks, never half-used."""
    out: dict[str, dict] = {}
    if not KITS.exists():
        return out
    for p in sorted(KITS.glob("*.json")):
        try:
            kit = json.loads(p.read_text())
        except ValueError:
            continue
        if not problems(kit):
            out[kit["food"]] = kit
    return out


def segments() -> tuple[str, ...]:
    return BUILT_IN + tuple(k for k in load_all() if k not in BUILT_IN)


def shots(kit: dict) -> list[dict]:
    """The kit's footage needs, in research/food_footage.SHOTS form."""
    food, out = kit["food"], []
    for q in kit["queries"]:
        for n in range(1, int(q.get("take") or 1) + 1):
            out.append({
                "segment": food, "need": f"{food}-{_slug(q['query'])}-{n}",
                "query": q["query"], "label": kit["label"],
                "must": [list(kit["words"])], "uses": list(q["uses"]),
                "sound": q.get("sound"), "off": list(kit.get("off") or []),
                "basis": f"{q['query']} (kit {food}, search take {n})",
                "kit": food,
            })
    return out


def word_uses(kit: dict) -> list[tuple[str, list[str]]]:
    return [(str(w).lower(), list(u)) for w, u in kit["word_uses"]]
