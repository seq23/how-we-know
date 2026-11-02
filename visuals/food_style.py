"""The food lane's style (config/food_style.json): calm, mesmerising, limited talk.

    from food_style import STYLE, for_lane

ONE reader for the file. visuals/food.py (PRESET), voice/food_voice.py (voice
settings, imagery-only holds, narration share), visuals/food_sound.py (bed
level), visuals/food_episode.py (runtime window, holds in the voice plan) and
loop/food_author.py (length aim, kit queries) take their values from here.
Only the food-science lane reads it: for_lane() returns None for every other
domain, and the batch renderer never imports this module
(loop/tests/test_food_calm_style.py).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "config" / "food_style.json"


def load(path: Path | None = None) -> dict:
    return json.loads((path or PATH).read_text())


STYLE = load()


def for_lane(domain: str | None) -> dict | None:
    """The style a lane renders with, or None (the lane's own defaults)."""
    return STYLE if domain in STYLE.get("lanes", []) else None


# WHICH EPISODES. The style is per episode, never retroactive: an episode is
# calm when its script carries the stamp (loop/food_author.assemble writes it
# from 2 Nov 2026), and a rendered episode is judged by the preset its spec
# records. The 13 Oct and chili/coffee/honey renders stay judged as made.
STAMP = "**Style:**"


def stamp() -> str:
    return f"{STAMP} {STYLE['id']} (config/food_style.json)"


def style_of_text(text: str) -> dict | None:
    """The style a food script asks for (its **Style:** line), or None."""
    for ln in (text or "").splitlines():
        if ln.startswith(STAMP) and STYLE["id"] in ln:
            return for_lane("food-science")
    return None


def style_of_spec(spec: dict) -> dict | None:
    """The style a rendered piece or episode was made in (its preset id)."""
    return for_lane("food-science") if STYLE["id"] in str((spec or {}).get("preset") or "") else None
