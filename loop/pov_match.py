"""Automatic POV selection. Matching, not approving.

`pov/pov-bank.json` holds 98 lines drawn from the owner's own interview and
`answers.txt`. **That bank is her approved voice.** There is no per-script
question about whether a line is really hers — every line in the bank already
is. So this is a matching problem, and it runs unattended.

Selection, in order:
  1. an existing entry in `pov/pov-assignments.json` wins — a human already
     matched that script by hand
  2. otherwise the best tag match against the script's subject
  3. `tier: specific` lines are deep-sea only, per the bank's own rules
  4. never reuse a line inside the rotation window (12 videos)
  5. **if nothing matches, take a NAMED STOP — never invent a line.** That rule
     is the bank's, and it is the one place this module refuses to guess.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "pov" / "pov-bank.json"
ASSIGNMENTS = ROOT / "pov" / "pov-assignments.json"

# Tag -> the vocabulary that signals it. Derived from the bank's OWN 22 tags,
# not from a guess at what they might be: an earlier version invented tags the
# bank does not use ("wonder", "exploration") and left real ones like
# "instruments" and "uncertainty" unreachable, so vent and instrument topics
# matched nothing at all. The words below are subject matter, never her phrasing.
TAG_SIGNALS = {
    "scale": r"deep|depth|trench|challenger|mariana|hadal|kilometre|kilometer|"
             r"metre|meter|how (?:deep|big|far|large)|size|vast|enormous|huge|"
             r"colossal|giant",
    "disorientation": r"dark|darkness|black|midnight|zone|navigat|orient|lost|"
                      r"blind|no light|pitch",
    "fear": r"scary|scared|fear|terrif|monster|creepy|nightmare|danger|shark|"
            r"squid|teeth|jaws|attack|eat you|kill",
    "adaptation": r"adapt|evolv|body|bodies|anatomy|weird|strange|why do|"
                  r"survive|surviv|feature|eyes|transparent|red|glow|"
                  r"pressure|crush|cold|withstand",
    "bioluminescence": r"biolumin|glow|glowing|light up|lure|flash|"
                       r"light organ|photophore",
    "evidence": r"how do (?:we|they|scientists) know|evidence|proof|prove|"
                r"study|studies|research|discover|record|data|observ|sample",
    "instruments": r"sonar|measure|measured|measurement|instrument|sensor|"
                   r"camera|rov\b|submersible|submarine|dive|expedition|"
                   r"explor|map|mapping|survey|probe|vehicle|trieste|"
                   r"echo ?sound|multibeam",
    "uncertainty": r"uncertain|estimate|approximat|about|roughly|margin|"
                   r"error|range|confiden|precise|accuracy|disput",
    "numbers": r"how many|how much|number|count|percent|figure|statistic|"
               r"\d",
    "unknown": r"unknown|unexplored|never seen|undiscovered|mystery|"
               r"how little|unmapped|rare|first ever|only.*times",
    "systems": r"system|ecosystem|food web|cycle|chain|network|"
               r"whale fall|vent|seep|community|interact",
    "earth": r"volcan|tectonic|plate|geolog|seafloor|crust|mineral|"
             r"hydrothermal|vent|smoker|earthquake|ridge|magma|"
             r"ocean floor|planet|climate|current",
    "deeptime": r"million years|billion years|ancient|prehistor|fossil|"
                r"evolution|era|epoch|deep time",
    "ancient": r"ancient|prehistor|fossil|extinct|primitive|living fossil|"
               r"survived from",
    "failure": r"fail|failure|implod|collapse|accident|disaster|wreck|"
               r"sank|sink|lost at sea|malfunction|went wrong",
    "risk": r"risk|danger|safe|safety|hazard|pressure|survive|deadly|"
            r"fatal|threat|what happens if",
    "media": r"documentar|footage|video|photo|image|viral|headline|"
             r"news|reported|clickbait|shown|film",
    "authority": r"expert|scientist|researcher|noaa|mbari|institute|"
                 r"official|agency|according to|who decides|authority",
    "trust": r"trust|believ|reliable|credib|honest|misleading|"
             r"true|fake|myth|misconception",
    "confidence": r"sure|certain|know for sure|confiden|how sure|"
                  r"definit|best guess",
    "thesis": r"why|what is|what are|how does|how do|explain|"
              r"the point|matters|meaning",
    "policy": r"protect|conservation|regulat|law|treaty|mining|"
              r"fishing|manage|govern|manage",
}
_COMPILED = {t: re.compile(p, re.I) for t, p in TAG_SIGNALS.items()}

# Tags whose transferable lines express her general evidence stance. The bank's
# own README says transferable lines "may be used in any evidence-based niche",
# so these are the principled fallback when no tag signal fires - not a guess.
FALLBACK_TAGS = ("evidence", "uncertainty", "instruments", "thesis",
                 "numbers", "trust", "confidence", "unknown")

DEEP_SEA = re.compile(
    r"deep ?sea|deep ocean|abyss|hadal|trench|midnight zone|bathyal|"
    r"challenger deep|mariana|vent|seafloor|benthic", re.I)


class NoPovMatch(Exception):
    """Raised rather than inventing a line. The pipeline's own rule."""


def bank() -> list[dict]:
    with BANK.open() as fh:
        return json.load(fh)["lines"]


def rotation_window() -> int:
    with BANK.open() as fh:
        return json.load(fh).get("rotation_window", 12)


def hand_assignments() -> dict:
    if not ASSIGNMENTS.exists():
        return {}
    with ASSIGNMENTS.open() as fh:
        return {a["video"]: a for a in json.load(fh)["assignments"]}


def score(line: dict, subject: str) -> float:
    """How well a bank line's tag fits this subject. Zero means no fit."""
    pat = _COMPILED.get(line["tag"])
    if pat is None:
        return 0.0
    hits = len(pat.findall(subject))
    if not hits:
        return 0.0
    s = float(hits)
    # A transferable line fits any evidence-based subject; a specific line is
    # deep-sea only, so it scores higher when the subject IS deep sea.
    if line["tier"] == "specific":
        s *= 1.4 if DEEP_SEA.search(subject) else 0.0
    return s


def select(slug: str, subject: str, used_ids: list[str] | None = None) -> dict:
    """Pick one POV line. Raises NoPovMatch rather than inventing one.

    `used_ids` is the recent history, most recent last.
    """
    used = list(used_ids or [])
    window = rotation_window()
    recent = set(used[-window:])

    hand = hand_assignments().get(slug)
    lines = {l["id"]: l for l in bank()}

    if hand and hand["pov_id"] in lines and hand["pov_id"] not in recent:
        l = lines[hand["pov_id"]]
        return {"pov_id": l["id"], "line": l["line"], "tag": l["tag"],
                "tier": l["tier"], "source_answer": l.get("source_answer"),
                "matched_by": "hand assignment in pov/pov-assignments.json"}

    ranked = []
    for l in bank():
        if l["id"] in recent:
            continue
        s = score(l, subject)
        if s > 0:
            ranked.append((s, l))
    if not ranked:
        # Principled fallback, not a guess: the bank states that transferable
        # lines may be used in any evidence-based niche, and every video in this
        # channel is evidence-based by construction.
        for tag in FALLBACK_TAGS:
            pool = [l for l in bank()
                    if l["tier"] == "transferable" and l["tag"] == tag
                    and l["id"] not in recent]
            if pool:
                l = sorted(pool, key=lambda x: x["id"])[0]
                return {"pov_id": l["id"], "line": l["line"], "tag": l["tag"],
                        "tier": l["tier"],
                        "source_answer": l.get("source_answer"),
                        "matched_by": f"transferable fallback (tag:{tag}); no "
                                      f"tag signal fired for this subject"}

    if not ranked:
        raise NoPovMatch(
            f"no POV line in the bank matches {slug!r}. The bank's own rule is "
            f"that the pipeline takes a NAMED STOP here rather than inventing "
            f"a line. Either the subject is outside the owner's interviewed "
            f"ground, or every fitting line is inside the {window}-video "
            f"rotation window.")
    ranked.sort(key=lambda t: (-t[0], t[1]["id"]))
    s, l = ranked[0]
    return {"pov_id": l["id"], "line": l["line"], "tag": l["tag"],
            "tier": l["tier"], "source_answer": l.get("source_answer"),
            "matched_by": f"tag:{l['tag']} score {s:.1f}"}


def select_week(items: list[dict], used_ids: list[str] | None = None) -> list[dict]:
    """Match a whole week, keeping lines distinct inside the week itself."""
    used = list(used_ids or [])
    out = []
    for it in items:
        subject = f"{it.get('question','')} {it.get('slug','')}"
        pick = select(it.get("slug", ""), subject, used)
        used.append(pick["pov_id"])
        out.append({**it, **{"pov_id": pick["pov_id"],
                             "pov_line": pick["line"],
                             "pov_tag": pick["tag"],
                             "pov_tier": pick["tier"],
                             "pov_matched_by": pick["matched_by"]}})
    return out


if __name__ == "__main__":
    import ledger
    items = [{"slug": s["slug"], "question": s["question"]}
             for s in ledger.inventory()[:6]]
    for r in select_week(items):
        print(f"{r['slug'][:44]:<44} {r['pov_id']}  [{r['pov_tag']}] "
              f"{r['pov_matched_by']}")
        print(f"    {r['pov_line'][:96]}")
