"""The hard programmatic gate on topic selection.

The owner gave **blanket topic approval**: pick whatever the data says will earn
passively, subject only to hard exclusions. So there is no weekly human topic
decision — which means this file now carries her judgement, and it has to be
real rather than decorative.

`pov/topic-taxonomy.json` is the authority. Its 16 `hard_exclusions` are the
list; this module is the enforcement, and `check_authority_coverage()` fails if
the taxonomy ever grows an exclusion this module cannot enforce. Two components
each keeping their own list with no link between them is exactly how a barred
topic gets published.

Her three emphases, in her words — *nothing adult, nothing morally grey, and
nothing with legal exposure: no health/medical, no personal finance, no legal
advice* — map onto taxonomy entries and are weighted accordingly here.

**Design rule: refuse on doubt.** A false refusal costs one topic out of 2,000
candidates. A false admission costs a strike, a demonetisation, or a
defamation letter. The patterns are therefore deliberately broad, and
`decide()` returns the *named* exclusion so a refusal is never mysterious.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "pov" / "topic-taxonomy.json"


def taxonomy() -> dict:
    with TAXONOMY.open() as fh:
        return json.load(fh)


# Every key here MUST match a string in the taxonomy's hard_exclusions list.
# `check_authority_coverage()` enforces that, so the two can never drift.
RULES: dict[str, list[str]] = {
    "Adult or sexual content": [
        r"\b(sex|sexual|porn|pornograph|nude|nudity|nsfw|erotic|fetish|onlyfans|"
        r"orgy|genital|masturbat|aphrodisiac)\b",
        r"\bmating\s+(?:ritual|habits)\b.*\bhuman\b",
    ],
    "Drugs, substances, or paraphernalia": [
        r"\b(cocaine|heroin|meth|methamphetamine|fentanyl|opioid|weed|cannabis|"
        r"marijuana|psychedelic|lsd|shrooms|psilocybin|vape|vaping|bong|"
        r"paraphernalia|overdose|get high|narcotic)\b",
    ],
    "Firearms, weapons, explosives": [
        r"\b(gun|guns|rifle|firearm|pistol|handgun|ammo|ammunition|bullet|"
        r"explosive|bomb|grenade|ied|landmine|detonat|silencer|ghost gun)\b",
        r"\b(torpedo|depth charge)\b.*\b(build|make|how to)\b",
    ],
    "Gambling, betting, trading signals": [
        r"\b(gambl|casino|betting|bet on|sportsbook|poker|roulette|slots|"
        r"lottery|odds of winning|trading signal|day trad|forex)\b",
    ],
    "Medical, health, dietary, supplement or mental-health advice": [
        # Her explicit "no health/medical". Broad on purpose.
        r"\b(cure|cures|treat|treatment|therapy|therapeutic|remedy|symptom|"
        r"diagnos|disease|illness|infection|medicine|medication|drug dosage|"
        r"dosage|supplement|vitamin|nutrition|diet|dieting|weight loss|"
        r"detox|healing|anti-?aging|fertility|pregnan|cancer|diabetes|"
        r"depression|anxiety|adhd|autism|mental health|suicide|self-?harm|"
        r"is .* safe to eat|health benefits?|good for your health)\b",
        r"\b(should you (?:eat|take|drink)|is .* bad for you)\b",
    ],
    "Financial, investment, tax or legal advice": [
        # Her explicit "no personal finance, no legal advice".
        r"\b(invest|investing|investment|stock|stocks|shares|portfolio|crypto|"
        r"bitcoin|ethereum|nft|retirement|401k|pension|mortgage|loan|debt|"
        r"credit score|insurance|tax|taxes|irs|salary|net worth|get rich|"
        r"passive income|side hustle|make money)\b",
        r"\b(lawsuit|sue|suing|attorney|lawyer|legal advice|liability|"
        r"is it legal|against the law|copyright claim|patent)\b",
    ],
    "Named living private individuals as subject matter": [
        r"\b(net worth|wife|husband|girlfriend|boyfriend|divorce|"
        r"where does .* live|address of|phone number)\b",
        r"\b(scandal|affair|arrested|accused)\b",
    ],
    "Named companies framed critically in a way that invites defamation exposure": [
        r"\b(scam|fraud|fraudulent|exposed|lied|cover-?up|corrupt|"
        r"class action|whistleblow|negligence|is a scam|ripoff)\b",
    ],
    "Active political controversy, elections, partisan framing": [
        r"\b(election|elections|vote|voting|ballot|democrat|republican|"
        r"liberal|conservative|president|presidential|senate|congress|"
        r"parliament|prime minister|partisan|left ?wing|right ?wing|"
        r"senator|senators|congressman|governor|mayor|referendum|"
        r"immigration policy|abortion|gun control|protest)\b",
    ],
    "Religion framed as true or false": [
        r"\b(god|gods|bible|biblical|quran|koran|torah|jesus|christ|allah|"
        r"buddha|creationis|intelligent design|noah|noah's ark|"
        r"genesis flood|great flood|prayer|miracle|afterlife|heaven|hell|"
        r"soul|divine)\b",
    ],
    "Conspiracy, cryptid, paranormal, or pseudoscience framed as real": [
        r"\b(conspiracy|coverup|cover-?up|hoax|illuminati|new world order|"
        r"cryptid|mermaid|mermaids|megalodon (?:is )?(?:still )?alive|"
        r"bermuda triangle|atlantis is real|alien|aliens|ufo|uap|"
        r"extraterrestrial|nessie|loch ness|bigfoot|sasquatch|kraken is real|"
        r"ghost|ghosts|haunted|paranormal|supernatural|psychic|telepath|"
        r"flat earth|ancient aliens|simulation theory|manifest)\b",
    ],
    "Recent tragedy involving identifiable victims within 12 months": [
        r"\b(victims? (?:name|list|identified)|last words|final message|"
        r"bodies recovered|death toll|passengers? (?:died|killed)|"
        r"final moments|implosion victims)\b",
    ],
    "True crime involving identifiable victims or perpetrators": [
        r"\b(murder|murdered|killer|serial killer|homicide|manslaughter|"
        r"true crime|kidnap|abduct|missing person|cold case|"
        r"disappearance of|body found|autopsy|crime scene)\b",
    ],
    "Anything requiring third-party footage that is not license-cleared": [
        r"\b(full episode|full movie|watch online|free download|leaked|"
        r"leaked footage|reupload|clip from|scene from)\b",
    ],
    "Content directed at children (COPPA exposure)": [
        r"\b(for kids|for children|kids video|nursery|toddler|preschool|"
        r"baby shark|cocomelon|bedtime story|colou?ring page|"
        r"cartoon for|sing along|abc song|counting song)\b",
    ],
    "Dangerous acts, stunts, or anything replicable and harmful": [
        r"\b(how to make a|diy (?:bomb|weapon|poison)|challenge gone wrong|"
        r"stunt|dare|do not try|try this at home|hold your breath (?:for|"
        r"longer)|free ?dive (?:record|deeper)|breath ?hold)\b",
        r"\b(poison|poisonous|venomous)\b.*\b(eat|touch|handle|survive)\b",
    ],
}

# "Nothing morally grey." Not a taxonomy line of its own — it is the spirit
# behind several of them — so it is enforced as a named refusal in its own
# right rather than being quietly folded into one of the sixteen.
MORALLY_GREY = {
    "Morally grey framing (owner's standing instruction)": [
        r"\b(torture|cruel|cruelty|animal abuse|slaughter|kill(?:ing)? (?:a|an|the) "
        r"(?:whale|shark|dolphin)|poach|poaching|trophy hunt|finning|"
        r"exploit|slavery|trafficking|revenge|hate|butcher|harpoon|"
        r"cull|culling|inhumane|abuse|hunted to|wiped out)\b",
    ],
}

ALL_RULES = {**RULES, **MORALLY_GREY}
# A closing \b does not match an inflection: "\bsupplement\b" misses
# "supplements", "\bslaughter\b" misses "slaughtered", "\bvote\b" misses
# "votes". Three barred topics reached ADMITTED that way. This appends a narrow
# suffix set to every alternation group - narrow on purpose, so "invest" still
# cannot match "investigate".
INFLECT = r"(?:s|es|ed|d|ing|er|ers|or|ors)?"


def _inflect(pattern: str) -> str:
    """Let \b(...)\b also match its alternatives with a common inflection.

    Operates on the OUTERMOST group only. An earlier version used a regex that
    required the group to contain no nested parentheses, which silently skipped
    the morally-grey rule - it contains `kill(?:ing)?` - and left
    "slaughtered" admitted. Anchoring on the ends is simpler and cannot miss.
    """
    if pattern.startswith(r"\b(") and pattern.endswith(r")\b"):
        # r")\b" is THREE characters - ')', '\\', 'b'. Stripping two left the
        # closing paren in place and produced an unbalanced group.
        return pattern[:-3] + ")" + INFLECT + r"\b"
    return pattern


_COMPILED = {name: [re.compile(_inflect(p), re.I) for p in pats]
             for name, pats in ALL_RULES.items()}

# A candidate must also land inside an admitted domain. `research/filter.py`
# already buckets the backlog; these are its bucket names mapped to the
# taxonomy's admitted domains, so an unbucketed topic is refused rather than
# assumed fine.
ADMITTED_BUCKETS = {
    "deep-sea-biology", "depth-and-zones", "light-and-vision",
    "pressure-physics", "exploration-tech", "earth-systems", "space",
    "method-evidence",
}


class Decision:
    def __init__(self, admitted: bool, reason: str = "", rule: str = "",
                 matched: str = ""):
        self.admitted = admitted
        self.reason = reason
        self.rule = rule
        self.matched = matched

    def __bool__(self) -> bool:
        return self.admitted

    def __repr__(self) -> str:
        return ("ADMITTED" if self.admitted
                else f"REFUSED[{self.rule}] matched {self.matched!r}")

    def as_dict(self) -> dict:
        return {"admitted": self.admitted, "rule": self.rule,
                "reason": self.reason, "matched": self.matched}


def decide(text: str, domain: str | None = None) -> Decision:
    """The gate. Returns a Decision naming the exclusion when it refuses.

    `text` should be everything known about the candidate — the query itself,
    and for a drafted script its title and narration too. More text can only
    make the gate stricter, never looser.
    """
    if not text or not text.strip():
        return Decision(False, "empty candidate", "Empty candidate", "")

    for name, patterns in _COMPILED.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                return Decision(False,
                                f"touches hard exclusion: {name}",
                                name, m.group(0))

    if domain is not None and domain not in ADMITTED_BUCKETS:
        return Decision(False,
                        f"domain {domain!r} is not an admitted domain",
                        "Outside admitted domains", domain or "")
    return Decision(True, "admitted")


# ---------------------------------------------------------------------------
# Narration mode.
#
# `decide()` gates TOPIC SELECTION and is deliberately broad: refusing one
# candidate out of 2,000 costs nothing. Applying that same word list to 2,000
# words of science prose does not work - the first real draft was refused for
# the word "supplement" in "satellite altimetry supplements sonar data", and a
# gate that blocks every legitimate script is a gate that gets switched off.
#
# The owner's actual exposure is not vocabulary, it is ADVICE: telling a viewer
# what to take, buy, or do. So narration is gated on advice-shaped and
# claim-shaped constructions, plus the categories that are unsafe at any dose.
# ---------------------------------------------------------------------------

BODY_RULES: dict[str, list[str]] = {
    "Medical, health, dietary, supplement or mental-health advice": [
        r"\byou should (?:take|eat|drink|avoid|try|consider taking)\b",
        r"\b(?:we|I) recommend (?:taking|eating|drinking|a supplement)\b",
        r"\b(?:cures?|treats?|prevents?|heals?) (?:your|the )?"
        r"(?:cancer|disease|illness|depression|anxiety|infection)\b",
        r"\bconsult your (?:doctor|physician)\b",
        r"\b(?:daily|recommended) dose\b",
        r"\bhealth benefits? of taking\b",
    ],
    "Financial, investment, tax or legal advice": [
        r"\byou should (?:invest|buy|sell|short|put your money)\b",
        r"\b(?:we|I) recommend (?:investing|buying|this stock)\b",
        r"\b(?:buy|sell) (?:this|these) (?:stock|shares|coin|token)\b",
        r"\bguaranteed returns?\b",
        r"\b(?:this is|constitutes) legal advice\b",
        r"\byou (?:can|should) sue\b",
    ],
    "Adult or sexual content": [
        r"\b(?:porn|pornograph|erotic|nsfw|explicit sexual)\b",
    ],
    "Conspiracy, cryptid, paranormal, or pseudoscience framed as real": [
        # Framed AS REAL is the test. Debunking a myth is house style.
        r"\b(?:mermaids|megalodons?|aliens|ghosts|bigfoot) (?:are|is) real\b",
        r"\bproves? (?:that )?(?:aliens|mermaids|atlantis)\b",
        r"\bthe government is (?:hiding|covering up)\b",
        r"\bthey don'?t want you to know\b",
    ],
    "Dangerous acts, stunts, or anything replicable and harmful": [
        r"\byou can try this (?:at home|yourself)\b",
        r"\bhow to (?:make|build) (?:a )?(?:bomb|explosive|weapon|poison)\b",
        r"\bhold your breath (?:for|until)\b",
    ],
    "Named companies framed critically in a way that invites defamation exposure": [
        r"\b(?:is|was) (?:a )?(?:scam|fraud|fraudulent|criminal)\b",
        r"\bdeliberately (?:lied|covered up|falsified)\b",
    ],
    "Religion framed as true or false": [
        r"\b(?:proves|disproves) (?:that )?god\b",
        r"\bthe bible is (?:literally )?(?:true|false)\b",
    ],
}
_BODY_COMPILED = {n: [re.compile(p, re.I) for p in pats]
                  for n, pats in BODY_RULES.items()}


# Markers that turn an assertion into a report of someone else's claim, or a
# refutation of it. This channel debunks myths constantly - "Are all deep-sea
# animals ugly? No." is its house move - so an assertion carrying one of these
# within the preceding clause is reporting, not claiming.
DEBUNK = re.compile(
    r"(?:debunk\w*|disproved?|disproven|myth|misconception|no evidence|"
    r"not true|false|claim(?:s|ed)? that|belief that|rumou?r|"
    r"people (?:say|think|believe)|often (?:said|claimed)|"
    r"there is no|never been|do(?:es)? not exist|popular(?:ly)? (?:held|said))",
    re.I)


def decide_body(text: str) -> Decision:
    """Gate GENERATED NARRATION. Targets advice and false framing, not nouns.

    A science script may legitimately say "pressure", "risk", "treatment of the
    data" or "supplements the sonar record". It may not tell a viewer what to
    take, buy or do, and it may not assert a pseudoscientific claim as fact.
    """
    if not text or not text.strip():
        return Decision(False, "empty body", "Empty candidate", "")
    for name, patterns in _BODY_COMPILED.items():
        for pat in patterns:
            for m in pat.finditer(text):
                # Look back one clause. A refutation or an attribution is not
                # an assertion, and refusing those would ban the channel's
                # single most common move.
                lookback = text[max(0, m.start() - 120):m.start()]
                if DEBUNK.search(lookback):
                    continue
                return Decision(False, f"narration gives or asserts: {name}",
                                name, m.group(0))
    return Decision(True, "admitted")


def filter_candidates(rows: list[dict], text_key: str = "query") -> tuple[
        list[dict], list[dict]]:
    """Split candidates into (admitted, refused). Refusals carry their reason."""
    admitted, refused = [], []
    for r in rows:
        d = decide(r.get(text_key, ""), r.get("domain"))
        if d.admitted:
            admitted.append(r)
        else:
            refused.append({**r, "refused": d.as_dict()})
    return admitted, refused


def check_authority_coverage() -> list[str]:
    """The link between the taxonomy and this enforcement.

    Fails if the taxonomy lists a hard exclusion this module cannot enforce, or
    if this module enforces a rule the taxonomy does not list. Without this,
    someone adds a 17th exclusion to the JSON and nothing enforces it.
    """
    problems = []
    tax_list = taxonomy()["hard_exclusions"]
    for entry in tax_list:
        # Match on a distinctive prefix: the taxonomy phrases some entries more
        # fully than a dict key needs to be.
        if not any(entry.startswith(k[:28]) or k.startswith(entry[:28])
                   for k in RULES):
            problems.append(f"taxonomy exclusion is UNENFORCED: {entry!r}")
    for key in RULES:
        if not any(entry.startswith(key[:28]) or key.startswith(entry[:28])
                   for entry in tax_list):
            problems.append(f"rule enforces something the taxonomy does not "
                            f"list: {key!r}")
    return problems


if __name__ == "__main__":
    import sys
    problems = check_authority_coverage()
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(1)
    print(f"{len(RULES)} taxonomy exclusions enforced, "
          f"{len(MORALLY_GREY)} standing instruction(s), "
          f"{len(ADMITTED_BUCKETS)} admitted domains")
    for probe in sys.argv[1:]:
        print(f"  {probe!r} -> {decide(probe)}")
