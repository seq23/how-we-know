"""The episode's SHOT LIST: the concrete, filmable subjects its picture shows.

Picture first (owner 2026-11-03). The old long-form chose a picture per
narration sentence, and an abstract sentence fell back to a card, a diagram or
particle filler - "Why are deep-sea creatures so big?" rendered 82 beats with
no footage on any of them. Now, once per episode, the free model route turns
the TITLE into a short list of things a camera can film ("giant isopod,
sixgill shark, king crab, siphonophore ..."). That list drives the footage and
photo harvest (research/imagery_stock_video.py, research/imagery.py) and the
reel (visuals/longform_picture.py); the narration is laid over the reel.

    .venv/bin/python visuals/shot_list.py make SLUG [SLUG ...]   # free route, once
    .venv/bin/python visuals/shot_list.py show SLUG

Stored in channel/imagery/shot_lists.json (committed). A list is made once and
kept; `make --force` remakes it.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "channel" / "imagery" / "shot_lists.json"
SCRIPTS = ROOT / "scripts"
MIN_SUBJECTS, MAX_SUBJECTS = 4, 12


class ShotListStop(RuntimeError):
    """NAMED STOP SHOT_LIST_UNMADE: the free route gave no usable shot list."""
    code = "SHOT_LIST_UNMADE"


def load() -> dict:
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def subjects(slug: str) -> list[str]:
    return list((load().get(slug) or {}).get("subjects") or [])


def pattern(slug: str) -> str | None:
    subs = subjects(slug)
    if not subs:
        return None
    return "|".join(r"\b" + re.escape(s).replace(r"\ ", r"[\s-]+") + r"s?\b" for s in subs)


def title_of(slug: str) -> str:
    p = SCRIPTS / f"{slug}.md"
    if p.exists():
        m = re.search(r"^#\s+(.+)$", p.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip()
    return slug.replace("-", " ").capitalize() + "?"


def prompt(title: str) -> str:
    return (
        "You are planning the PICTURE for a calm documentary video titled:\n"
        f'  "{title}"\n\n'
        "The picture is ONLY real moving footage or photographs of the subject "
        "the title names - no text, diagrams or graphics. List the concrete "
        "things a camera would show that ARE that subject: specific species, "
        "objects, materials or processes, each a short search phrase of 1-3 "
        "words as a stock-footage library or NOAA would label it (e.g. 'giant "
        "isopod', 'molten steel', 'concrete pour'). Every item must itself fit "
        "the title: for a title about big creatures, only creatures that are "
        "big. No places or settings ('deep sea', 'ocean floor', 'trench'), no "
        "phenomena, no people, no equipment unless the title is about it, no "
        "abstract ideas.\n\n"
        "Also give the plain common names a stock-footage library (Pixabay) tags "
        "such footage with - one or two words, the subject itself, e.g. 'whale', "
        "'concrete', 'steel', 'microchip', 'jellyfish' - only ones that cannot "
        "mean something else.\n\n"
        'Answer with JSON and nothing else: {"subjects": [4-10 phrases], '
        '"library_words": [2-6 words]}, all lowercase.')


def parse(text: str) -> list[str]:
    """Subjects, then library words, from a JSON object (or a bare array)."""
    raw: list = []
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            raw = list(obj.get("subjects") or []) + list(obj.get("library_words") or [])
        except (ValueError, AttributeError):
            raw = []
    if not raw:
        m = re.search(r"\[.*?\]", text or "", re.S)
        try:
            raw = json.loads(m.group(0)) if m else []
        except ValueError:
            raw = []
    out = []
    for s in raw:
        s = re.sub(r"[^a-z0-9 \-']", "", str(s).lower()).strip()
        if s and 1 <= len(s.split()) <= 4 and s not in out and not _generic(s):
            out.append(s)
    return out[:MAX_SUBJECTS + 6]


GENERIC = set("""deep sea seas ocean oceans water underwater floor seafloor bottom
creature creatures life animal animals depth depths surface marine thing things
zone abyss abyssal plain benthic trench organism organisms""".split())


def _generic(phrase: str) -> bool:
    """A phrase made only of setting words ('deep sea', 'ocean floor') names
    no subject; a clip matching it would show anything."""
    return all(w in GENERIC for w in re.split(r"[\s-]+", phrase))


# Words that name something else just as often (a sea cucumber is not a
# cucumber; a vent is a duct; "fish" is any aquarium). Never a subject alone.
AMBIGUOUS = set("""cucumber carbon fiber fabric metal rust vent chimney silicon processor
seal fish shark squid octopus jellyfish crab shrimp knife blade composite aggregate
water sand stone""".split())


def keep(slug: str, subs: list[str]) -> list[str]:
    """Drop ambiguous single words (a sea cucumber is not a cucumber)."""
    return [x for x in subs if " " in x or x not in AMBIGUOUS]


def _domain(slug: str) -> str | None:
    p = SCRIPTS / f"{slug}.md"
    if not p.exists():
        return None
    m = re.search(r"^\*\*Domain:\*\*\s*([a-z-]+)", p.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def _keys() -> str:
    sec = ROOT / ".secrets"
    if not os.environ.get("GEMINI_API_KEY") and (sec / "gemini_key.txt").exists():
        os.environ["GEMINI_API_KEY"] = (sec / "gemini_key.txt").read_text().strip()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key and (sec / "openrouter_key.txt").exists():
        key = (sec / "openrouter_key.txt").read_text().strip()
    return key


def make(slug: str, force: bool = False, complete=None) -> list[str]:
    store = load()
    if store.get(slug, {}).get("subjects") and not force:
        return store[slug]["subjects"]
    if complete is None:
        sys.path.insert(0, str(ROOT / "loop"))
        import llm_router                                   # noqa: PLC0415
        key = _keys()
        complete = lambda msgs: llm_router.complete(msgs, key, timeout=120,  # noqa: E731
                                                     temperature=0.2)
    title = title_of(slug)
    resp = complete([{"role": "user", "content": prompt(title)}])
    text = (((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    raw = parse(text)
    subs = keep(slug, raw)
    if len(subs) < MIN_SUBJECTS:
        raise ShotListStop(f"SHOT_LIST_UNMADE {slug}: the free route answered "
                           f"{len(subs)} usable subject(s) for {title!r}; the next "
                           f"batch asks again")
    store[slug] = {"title": title, "subjects": subs, "free_route_subjects": raw,
                   "made_by": str(resp.get("model_used") or "?"),
                   "made": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    STORE.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n")
    return subs


def main(argv: list[str]) -> int:
    if argv[:2] == ["make", "--pending"]:
        sys.path.insert(0, str(ROOT / "research"))
        import imagery_stock_video as STOCK                 # noqa: PLC0415
        todo = [s for s in STOCK.targets() if not subjects(s)]
        if not todo:
            print("shot lists: every episode waiting for a render has one")
            return 0
        argv = ["make", *todo]
    if len(argv) >= 2 and argv[0] in ("make", "show"):
        bad = 0
        for slug in argv[1:]:
            if slug == "--force":
                continue
            try:
                subs = make(slug, force="--force" in argv) if argv[0] == "make" \
                    else subjects(slug)
                print(f"{slug}: {', '.join(subs) or '(none)'}")
            except ShotListStop as e:
                print(f"NAMED STOP {e}")
                bad += 1
        return 3 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
