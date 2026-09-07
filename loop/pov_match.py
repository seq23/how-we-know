"""Automatic POV selection. Matching, not approving.

`pov/pov-bank.json` holds the lines drawn from the owner's own interviews --
`answers.txt` (2026-08-30, deep sea) and `answers-3.txt` (2026-09-05, eleven
domains). **That bank is her approved voice.** There is no per-script
question about whether a line is really hers — every line in the bank already
is. So this is a matching problem, and it runs unattended.

Selection, in order:
  1. an existing entry in `pov/pov-assignments.json` wins — a human already
     matched that script by hand
  2. otherwise the best tag match against the script's subject
  3. a `tier: specific` line fits only ITS OWN domain -- deep sea's, materials'
     or whichever domain the interview it came from was about
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
# THE VOCABULARY IS PER TAG, AND IT HAD ONLY EVER SEEN ONE NICHE. Every
# pattern below was written against deep-sea subjects, so a materials, space or
# energy subject fired NOTHING and every such episode fell through to the
# transferable fallback -- silently, because the fallback always answers. The
# 2026-09-05 additions are marked, and every added word is taken from a real
# queued slug in research/publish_order*.json or research/broad_mined.json.
TAG_SIGNALS = {
    "scale": r"deep|depth|trench|challenger|mariana|hadal|kilometre|kilometer|"
             r"metre|meter|how (?:deep|big|far|large)|size|vast|enormous|huge|"
             r"colossal|giant|"
             # 2026-09-05:
             r"light[- ]year|universe|galaxy|nanometre|nanometer|micron|"
             r"atom|molecul|megaproject|tunnel|dam\b|span",
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
    # NEW TAG SIGNAL, not a new tag: "evidence-limit" was already in the bank
    # on three lines and had no entry here at all, so score() returned 0.0 for
    # every one of them. A tag with no vocabulary is a line that can never be
    # selected.
    "evidence-limit": r"unknown|unclear|not known|no one knows|nobody knows|"
                      r"estimat|uncertain|limit|incomplete|missing|"
                      r"how (?:do|did) (?:we|they|scientists) know|"
                      r"fossil|preserv|record|sample|measured|inferred",
    "instruments": r"sonar|measure|measured|measurement|instrument|sensor|"
                   r"camera|rov\b|submersible|submarine|dive|expedition|"
                   r"explor|map|mapping|survey|probe|vehicle|trieste|"
                   r"echo ?sound|multibeam|"
                   # 2026-09-05:
                   r"telescope|microscope|spectro|x-?ray|scan|calibrat|"
                   r"radiometric|carbon dating|dating|detector|assay|"
                   r"metrolog|test method",
    "uncertainty": r"uncertain|estimate|approximat|about|roughly|margin|"
                   r"error|range|confiden|precise|accuracy|disput|"
                   # 2026-09-05:
                   r"forecast|probabilit|likelihood|error bar|scatter|variance",
    "numbers": r"how many|how much|number|count|percent|figure|statistic|"
               r"\d|"
               # 2026-09-05:
               r"how (?:hot|strong|fast|thin|thick|heavy)|degrees|celsius|"
               r"fahrenheit|kelvin|psi\b|pascal|gpa\b|mpa\b|watt|volt|"
               r"tonne|ton\b",
    "unknown": r"unknown|unexplored|never seen|undiscovered|mystery|"
               r"how little|unmapped|rare|first ever|only.*times|"
               # 2026-09-05:
               r"hidden|invisible|underneath|behind the|inside a|"
               r"takes for granted",
    "systems": r"system|ecosystem|food web|cycle|chain|network|"
               r"whale fall|vent|seep|community|interact|"
               # 2026-09-05:
               r"manufactur|fabricat|factory|foundry|refin|assembly|process|"
               r"supply chain|logistic|container|port\b|freight|grid\b|"
               r"infrastructure|bridge|canal|pipeline|reactor|plant\b|"
               r"production|made\b|built|construct",
    "earth": r"volcan|tectonic|plate|geolog|seafloor|crust|mineral|"
             r"hydrothermal|vent|smoker|earthquake|ridge|magma|"
             r"ocean floor|planet|climate|current|"
             # 2026-09-05:
             r"erup|lava|sediment|strata|fault line|glacier|storm|"
             r"hurricane|tornado|weather",
    "deeptime": r"million years|billion years|ancient|prehistor|fossil|"
                r"evolution|era|epoch|deep time|"
                # 2026-09-05:
                r"dinosaur|permian|cretaceous|triassic|jurassic|"
                r"mass extinction|geologic time",
    "ancient": r"ancient|prehistor|fossil|extinct|primitive|living fossil|"
               r"survived from",
    "failure": r"fail|failure|implod|collapse|accident|disaster|wreck|"
               r"sank|sink|lost at sea|malfunction|went wrong|"
               # 2026-09-05:
               r"fractur|shatter|crack|fatigue|rust|corro|brittle|defect|"
               r"wear\b|explod|melt|buckl|creep|delaminat|weld",
    "risk": r"risk|danger|safe|safety|hazard|pressure|survive|deadly|"
            r"fatal|threat|what happens if|"
            # 2026-09-05:
            r"blackout|outage|failure mode|tolerance|margin of safety|"
            r"catastroph|incident",
    "media": r"documentar|footage|video|photo|image|viral|headline|"
             r"news|reported|clickbait|shown|film",
    "authority": r"expert|scientist|researcher|noaa|mbari|institute|"
                 r"official|agency|according to|who decides|authority|"
                 # 2026-09-05:
                 r"nist|iso\b|astm|standards body|nasa|usgs|esa\b|"
                 r"national laborator",
    "trust": r"trust|believ|reliable|credib|honest|misleading|"
             r"true|fake|myth|misconception",
    "confidence": r"sure|certain|know for sure|confiden|how sure|"
                  r"definit|best guess|"
                  # 2026-09-05:
                  r"how strong|strength|stronger|strongest|toughest|hardest|"
                  r"record|claim|magic|miracle|breakthrough",
    "thesis": r"why|what is|what are|how does|how do|explain|"
              r"the point|matters|meaning",
    "policy": r"protect|conservation|regulat|law|treaty|mining|"
              r"fishing|manage|govern|"
              # 2026-09-05:
              r"energy|power grid|nuclear|renewable|fossil fuel|emission|"
              r"subsid|tariff",
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


def untraced_pov(slugs) -> list[str]:
    """Of `slugs`, those whose script has a [HUMAN] beat with no assignment.

    THE SAME QUESTION V32 ASKS, ASKED BEFORE THE UPLOAD INSTEAD OF AFTER IT.

    `[HUMAN]` marks the one beat where the owner speaks as herself. V32
    (loop/validate.py) checks that every SCHEDULED episode's beat traces to an
    entry in pov/pov-assignments.json - correctly, and it caught three. But it
    runs on the ledger, and an episode only reaches the ledger by being
    uploaded, so by the time V32 can see a problem the video is already on
    YouTube, private, with a publishAt. That is a guard standing downstream of
    the thing it governs: it can report the harm, it cannot prevent it.

    `pov/pov-assignments.json` is hand-curated (its own header says "generated
    2026-08-30", "owner's own words only") and NOTHING in this repo writes it.
    `hand_assignments()` above reads it; `select()` below picks a bank line for
    a new script and the choice is never recorded back. So every episode
    authored after 2026-08-30 arrives with an untraced first-person beat by
    default, and the only thing standing between that and the channel was a
    validator that fires one step too late. Three episodes got through:
    how-does-tempered-glass-shatter (airs 2026-09-18), how-strong-is-titanium
    (2026-09-21) and how-is-damascus-steel-made (2026-09-25).

    This is the same check, one step earlier, where refusing is still free.
    """
    assigned = set(hand_assignments())
    out = []
    for slug in slugs:
        script = ROOT / "scripts" / f"{slug}.md"
        if not script.exists():
            continue
        if "[HUMAN]" not in script.read_text():
            continue                      # no POV beat is a different rule
        if slug not in assigned:
            out.append(slug)
    return out


# A tier:specific line with no `domain` came from the first interview, which
# was entirely about deep sea. It is not "domain-less" -- it is deep sea's, and
# saying so here is what lets the rule below be about domains rather than about
# one hardcoded niche.
LEGACY_SPECIFIC_DOMAIN = "deep-sea-ocean-science"


def line_domain(line: dict) -> str:
    return line.get("domain") or LEGACY_SPECIFIC_DOMAIN


def score(line: dict, subject: str, domain: str | None = None) -> float:
    """How well a bank line fits this subject. Zero means no fit.

    THE SPECIFIC RULE IS ABOUT DOMAINS, NOT ABOUT DEEP SEA. This multiplied
    every `tier: specific` line by zero unless the subject text matched a
    deep-sea vocabulary -- correct while the bank held one interview about one
    niche, and wrong the moment a second domain's lines existed. Three
    materials lines and twenty-one from the eleven-domain interview would every
    one of them have scored 0.0 for their own subject: present in the bank,
    impossible to select, and invisible, because the transferable fallback
    always answers.

    `domain` is the episode's domain, resolved from its slug by select(). A
    specific line fits when it is the SAME domain. Where no domain can be
    resolved the deep-sea text signal is still honoured, so an unattributed
    script behaves exactly as it did before.
    """
    pat = _COMPILED.get(line["tag"])
    if pat is None:
        return 0.0
    hits = len(pat.findall(subject))
    if not hits:
        return 0.0
    s = float(hits)
    if line["tier"] == "specific":
        if domain:
            s *= 1.4 if line_domain(line) == domain else 0.0
        else:
            s *= (1.4 if (line_domain(line) == LEGACY_SPECIFIC_DOMAIN
                          and DEEP_SEA.search(subject)) else 0.0)
    return s


def select(slug: str, subject: str, used_ids: list[str] | None = None,
           domain: str | None = None) -> dict:
    """Pick one POV line. Raises NoPovMatch rather than inventing one.

    `used_ids` is the recent history, most recent last.
    """
    used = list(used_ids or [])
    window = rotation_window()
    recent = set(used[-window:])

    # The episode's domain comes from its script -- the one join this repo uses
    # everywhere else. An unresolvable slug leaves it None, and score() falls
    # back to the deep-sea text signal exactly as before.
    if domain is None:
        try:
            import domains as _dom                          # noqa: PLC0415
            domain = _dom.domain_of_slug(slug)
        except Exception:                                   # never break a match
            domain = None

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
        s = score(l, subject, domain)
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
