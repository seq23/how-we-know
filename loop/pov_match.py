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

import datetime as _dt
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


# ------------------------------------------------- assignment integrity
#
# WHY THIS EXISTS. `select()` treats a hand assignment as authoritative and
# returns it WITHOUT applying any of the rules it applies to every other line.
# `score()` refuses to let a `tier: specific` line cross domains - that rule is
# the whole reason the materials interview was needed - and a hand assignment
# skipped it entirely, because it is checked before scoring rather than by it.
#
# CONFIRMED, commit 581feec (2026-09-07). The owner's three approved MATERIALS
# lines were written into pov/pov-assignments.json under pov-102, pov-103 and
# pov-104 — ids that in the bank are `tier: transferable` lines about being
# wrong and about distrusting complexity, with COMPLETELY DIFFERENT TEXT. So
# each row was wrong twice over:
#
#   tier: "specific"   the bank says transferable
#   line: <her real materials words>   the bank's text for that id is other
#                                      words entirely
#
# The second is the serious one. The words that went into the script and onto
# YouTube traced to NOTHING: the id named one line and the row carried another,
# which is the channel asserting she said something her bank does not record —
# the exact thing pov/pov-assignments.json's "owner's own words only" exists to
# prevent. Every presence check in the pipeline called those episodes traced.
#
# The single thing that caught it was one hardcoded end-to-end case in
# loop/tests/test_pov_domains.py naming ONE slug (`how-strong-is-titanium`),
# which noticed only because `select()` returns the BANK's tier and the case
# asserted `tier == "specific"`. Had the same mistake been made on any of the
# other twenty-eight rows, nothing anywhere would have said a word. The
# follow-up commit re-pointed them at pov-139/140/141, so the instance is
# closed and the hole is not.
#
# The cross-domain rule below is the same hole's other half: `score()` refuses
# to let a tier:specific line cross domains, and a hand assignment skipped
# scoring entirely, so nothing enforced it on the one path a human writes.
#
# THE HOLE IS NOT V32'S. It is that `pov/pov-assignments.json` is the one input
# in this pipeline that is trusted absolutely and validated for nothing, while
# four separate code paths read or write it:
#
#   select()            honours it, unchecked
#   untraced_pov()      counts its mere presence as a trace
#   record_assignment() appends to it
#   validate.py V32     counts its mere presence as a trace
#
# So the rule lives HERE, once, and all four consult it. Fixing V32 alone is
# the per-validator patch that has left this repo hitting the same wall four
# times in eight days.

# Each defect is a (code, human sentence) pair. The codes are stable so a stop
# can name one; the sentences are what a person actually reads.
DEFECT_CODES = (
    "POV_ID_NOT_IN_BANK",
    "TIER_DISAGREES_WITH_BANK",
    "LINE_TEXT_DISAGREES_WITH_BANK",
    "SPECIFIC_LINE_WRONG_DOMAIN",
    "POV_ID_REUSED",
)


def _domain_of(slug: str):
    try:
        import domains as _dom                              # noqa: PLC0415
        return _dom.domain_of_slug(slug)
    except Exception:                       # noqa: BLE001 - never break a match
        return None


def assignment_defects(rows=None, slugs=None) -> list[dict]:
    """Every way an entry in pov/pov-assignments.json can be wrong.

    Returns a list of {video, pov_id, code, why}. Empty means the file says
    only things the bank agrees with.

    `rows` lets a guard hand in a doctored file without writing one to disk.
    `slugs`, when given, narrows the report to those videos - the reuse check
    still looks at the WHOLE file, because reuse is a property of the file and
    not of any one row.

    NOT A STYLE CHECK. Every rule here is one the automatic path already
    enforces on itself, or one the file states in its own `rule` field:

      * the line must EXIST in the bank. `select()` silently ignores a hand
        assignment naming an unknown id and matches automatically instead, so
        the file claims one line and the script carries another.
      * the recorded `tier` and `line` must be the bank's. The file duplicates
        both, and two copies of a fact with nothing joining them is this
        repo's named recurring defect. A drifted `line` is the channel
        asserting she said words her bank does not record.
      * a `tier: specific` line fits only its own domain. This is `score()`'s
        rule, applied to the path that skips `score()`.
      * `pov/pov-assignments.json` states its own rule in its own header:
        "one POV per video, no reuse".
    """
    if rows is None:
        rows = read_json(ASSIGNMENTS)["assignments"] if ASSIGNMENTS.exists() \
            else []
    lines = {l["id"]: l for l in bank()}
    seen: dict = {}
    out = []
    for a in rows:
        video, pid = a.get("video"), a.get("pov_id")
        seen.setdefault(pid, []).append(video)
    for a in rows:
        video, pid = a.get("video"), a.get("pov_id")
        if slugs is not None and video not in set(slugs):
            continue

        def add(code, why):
            out.append({"video": video, "pov_id": pid,
                        "code": code, "why": why})

        line = lines.get(pid)
        if line is None:
            add("POV_ID_NOT_IN_BANK",
                f"{video} is assigned {pid!r}, which is not in "
                f"pov/pov-bank.json. select() cannot honour it, so it "
                f"silently matches a DIFFERENT line automatically and the "
                f"script carries words this file does not name.")
            continue
        if a.get("tier") and a["tier"] != line["tier"]:
            add("TIER_DISAGREES_WITH_BANK",
                f"{video} records {pid} as tier {a['tier']!r}; the bank says "
                f"{line['tier']!r}. Two copies of one fact, and the domain "
                f"rule below is decided by the tier.")
        if a.get("line") and a["line"].strip() != line["line"].strip():
            add("LINE_TEXT_DISAGREES_WITH_BANK",
                f"{video} records text for {pid} that is not the bank's text "
                f"for {pid}. The bank is her approved voice; a copy that has "
                f"drifted is the channel asserting she said something no "
                f"interview records.")
        if line["tier"] == "specific":
            dom = _domain_of(video)
            if dom and line_domain(line) != dom:
                add("SPECIFIC_LINE_WRONG_DOMAIN",
                    f"{video} is a {dom} episode assigned {pid}, a "
                    f"tier:specific line from {line_domain(line)}. "
                    f"score() gives that pairing 0.0 and would never make "
                    f"it; a hand assignment skips score(), so it is the only "
                    f"way this can happen.")
        others = [v for v in seen.get(pid, []) if v != video]
        if others:
            add("POV_ID_REUSED",
                f"{pid} is assigned to {video} and also to "
                f"{', '.join(sorted(others))}. pov/pov-assignments.json's own "
                f"header states the rule: \"one POV per video, no reuse\".")
    return out


def defective_assignments(slugs=None) -> dict:
    """video -> the defects against it. The form the callers actually want."""
    out: dict = {}
    for d in assignment_defects(slugs=slugs):
        out.setdefault(d["video"], []).append(d)
    return out


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
    return sorted(untraced_reasons(slugs))


def untraced_reasons(slugs) -> dict:
    """slug -> WHY its [HUMAN] beat does not trace to the owner's bank.

    Split out from `untraced_pov()` so the upload lane can print the actual
    reason. "No entry in pov/pov-assignments.json" was the only reason there
    was until an entry could be WRONG as well as absent, and a refusal that
    misnames its cause sends someone to add a row that is already there.
    """
    assigned = hand_assignments()
    # AN ENTRY THAT IS WRONG IS NOT AN ENTRY. Presence used to be the whole
    # test, so a row naming a deep-sea line for a titanium episode counted as
    # a trace - commit 581feec. The gate and V32 now ask the same, stronger
    # question, from the same predicate, so they cannot drift apart again.
    defective = defective_assignments(slugs)
    out = {}
    for slug in slugs:
        script = ROOT / "scripts" / f"{slug}.md"
        if not script.exists():
            continue
        if "[HUMAN]" not in script.read_text():
            continue                      # no POV beat is a different rule
        if slug not in assigned:
            out[slug] = ("its [HUMAN] Producer POV has no entry in "
                         "pov/pov-assignments.json")
        elif slug in defective:
            out[slug] = "; ".join(f"[{d['code']}] {d['why']}"
                                  for d in defective[slug])
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

    # A HAND ASSIGNMENT IS AUTHORITATIVE, NOT EXEMPT. It skips score(), which
    # is where the domain rule lives, so the same rule is applied here instead.
    # Raising is the bank's own rule ("never invent a line") applied to the
    # honest alternative: silently ignoring her recorded choice and matching a
    # different line, while pov/pov-assignments.json goes on naming the first.
    # loop/draft.py and loop/rank.py both turn this into a NAMED STOP.
    if hand:
        bad = assignment_defects(rows=[hand])
        if bad:
            raise NoPovMatch(
                f"pov/pov-assignments.json assigns {slug!r} a line this repo "
                f"cannot honour: "
                + "; ".join(f"[{d['code']}] {d['why']}" for d in bad))

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
        # EVERY FITTING LINE IS INSIDE THE ROTATION WINDOW. Automated policy
        # (owner's rule, 2026-09-25: nothing waits on her): the window
        # yields rather than the week stopping. The transferable line used
        # LONGEST AGO is taken - still her own words from the bank, never an
        # invented one - and never a line already used this week.
        history = list(used_ids or [])
        pool = [l for l in bank() if l["tier"] == "transferable"]
        if pool:
            last = {l["id"]: max((i for i, u in enumerate(history)
                                  if u == l["id"]), default=-1) for l in pool}
            l = min(pool, key=lambda x: (last[x["id"]], x["id"]))
            return {"pov_id": l["id"], "line": l["line"], "tag": l["tag"],
                    "tier": l["tier"], "source_answer": l.get("source_answer"),
                    "matched_by": f"least-recently-used transferable line "
                                  f"(every fitting line was inside the "
                                  f"{window}-video rotation window)"}
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


def read_json(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, doc) -> None:
    Path(p).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def record_assignment(slug: str, pov: dict, *, source: str = "matched by author") -> bool:
    """Write down which bank line an authored episode borrowed.

    THE MISSING HALF OF A LOOP THAT WAS OTHERWISE COMPLETE. `select()` picks a
    line from the owner's approved bank and the author writes it into the
    script — citing it, "matched from POV BANK pov-027 before rewriting". Then
    nothing recorded the choice, and every reference to
    `pov/pov-assignments.json` in this repo was a READ.

    So V32 later asked which bank line the episode's [HUMAN] beat traces to,
    found no entry, and correctly refused to let it air. The remedy it offers is
    that the owner reads the line and approves it — which happened six times on
    2026-09-07 for six episodes whose lines had ALREADY been selected from her
    own interviews. Her bank had 115 unused lines at the time. The gap was never
    a missing line or a missing interview; it was a missing write.

    RECORDING IS BOOKKEEPING, NOT CONSENT. This does not approve anything: the
    line came from her interview bank, and this only writes down which one. A
    hand assignment already present is never overwritten — `select()` treats one
    as authoritative, and a run that silently replaced it would be deciding
    something she decided.

    Returns True when a row was added.
    """
    doc = read_json(ASSIGNMENTS)
    rows = doc["assignments"]
    if any(a["video"] == slug for a in rows):
        return False

    row = {
        "video": slug,
        "pov_id": pov["pov_id"],
        "tier": pov.get("tier", "transferable"),
        # Distinguishable at a glance from `owner-approved <date>`, which is a
        # line she read and claimed. This one she said in an interview and the
        # author borrowed; both are hers, and they are not the same act.
        "source": source,
        "line": pov["line"],
    }
    # REFUSE TO WRITE THE DEFECT IN THE FIRST PLACE. This is the only
    # automatic writer of the file, so a rule enforced only on READ would let
    # the loop manufacture the very row every reader then has to reject. The
    # reuse check needs the rows already on file, hence rows + [row].
    bad = assignment_defects(rows=rows + [row], slugs=[slug])
    if bad:
        print(f"  REFUSE to record {slug}: "
              + "; ".join(f"[{d['code']}] {d['why']}" for d in bad))
        return False
    rows.append(row)
    doc["generated"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(ASSIGNMENTS, doc)
    return True
