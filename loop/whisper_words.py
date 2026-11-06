#!/usr/bin/env python3
"""The Whisper Almanac plain-words check: behaviour, not wording.

    python loop/whisper_words.py check scripts/whisper/<slug>.md
    python loop/whisper_words.py --self-test

Her ruling, 6 Nov 2026 (spry brain, Settled decisions): plain everyday words
by default; keep a real name when it IS the topic (Andromeda,
photosynthesis), said once softly and explained in plain words; cut
acronyms, long numbers, units, equations and jargon strings; never dumb down
the facts. WHY: hard words make a sleepy listener work.

Every rule below is a thing a sleepy ear trips on, measured in the text the
voice will SAY (loop/whisper_lane.spoken_text), never in headings:

  ACRONYM          NASA, DNA, MRI ... two or more capitals in a row
  LETTER_DIGIT     CO2, 3D, H2O, 10km - letters and digits in one word
  LONG_NUMBER      a numeral of more than 3 digits (1908, 10,000, 2,500,000)
  DECIMAL          2.5, 0.01 - a decimal said aloud
  UNIT             km, kg, nm, psi, %, degree signs, and metric-prefix unit
                   words (nanometres, megapascals) or kelvin, joules, pascals
  NUMBER_STRING    four or more number words in a row ("two hundred and
                   fifty three thousand")
  EQUATION         = + x ^ / between terms, "squared", "divided by" ...
  BRACKETS         ( ) [ ] { } - asides a voice cannot say
  JARGON_STRING    three hard words (4+ syllables, not a named topic word,
                   not a plain long word) inside any five-word window
  HARD_WORDS       more than 2.5% hard words in one segment
  NAMED_REPEAT     a declared topic name said more than once in a segment

And two fact guards against a rewrite that invents rather than simplifies
(scripts come from free models):

  INVENTED_NAME    a capitalised name in the rewrite that is not in its
                   fact-checked source script
  INVENTED_NUMBER  a numeral in the rewrite that is not in its source

`problems()` returns a list of named problems; empty means it passes. A
check that examined zero words is itself a problem (Rule 0).
"""
from __future__ import annotations

import re
import sys

ACRONYM = re.compile(r"\b[A-Z]{2,}s?\b")
LETTER_DIGIT = re.compile(r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{2,}\b")
NUMERAL = re.compile(r"\d[\d,]*(?:\.\d+)?")
DECIMAL = re.compile(r"\b\d+\.\d+\b")
UNIT_ABBR = re.compile(
    r"\d\s*(?:km|cm|mm|nm|µm|um|kg|mg|lbs?|psi|mph|kph|km/h|hz|khz|mhz|ghz|"
    r"mpa|gpa|kpa|kw|mw|gw|kwh|m|g|k|ft|in|oz)\b|[%°℃℉µ]", re.I)
UNIT_WORD = re.compile(
    r"\b(?:kilo|centi|milli|micro|nano|mega|giga|tera|pico)"
    r"(?:met(?:er|re)s?|grams?|pascals?|watts?|joules?|hertz|seconds?|liters?|litres?|volts?|amps?)\b"
    r"|\b(?:pascals?|kelvin|joules?|newtons|watts|hertz|atmospheres)\b", re.I)
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "million", "billion", "trillion", "point", "and",
}
EQUATION = re.compile(
    r"[=+×÷^]|\w\s*/\s*\w|\b\d+\s*[x*]\s*\d+\b|\bsquared\b|\bcubed\b|"
    r"\bto the power of\b|\bdivided by\b|\bmultiplied by\b|\bequals\b", re.I)
BRACKETS = re.compile(r"[()\[\]{}]")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

# Long words a tired ear knows without effort. Only words a child or a
# grandparent says every week: this list widens the plain, never the jargon.
PLAIN_LONG = {
    "everything", "everyone", "everybody", "anything", "anyone", "anybody",
    "something", "somebody", "nothing", "nobody", "everywhere", "anywhere",
    "television", "comfortable", "beautiful", "beautifully", "usually",
    "actually", "really", "already", "especially", "naturally", "finally",
    "gradually", "eventually", "particularly", "probably", "definitely",
    "completely", "absolutely", "certainly", "slowly", "gently", "quietly",
    "carefully", "easily", "visible", "invisible", "remarkable", "incredible",
    "unusual", "material", "materials", "experiment", "experiments",
    "temperature", "temperatures", "electricity", "information", "ordinary",
    "extraordinary", "imagine", "imagining", "american", "america",
    "necessary", "interesting", "different", "differently", "energy",
    "animal", "animals", "ocean", "oceans", "history", "important",
    "underneath", "however", "together", "community", "laboratory",
    "discovery", "discoveries", "observatory", "generation", "generations",
    "continue", "continues", "particular", "family", "families", "nobody's",
    "january", "february", "february's", "anniversary", "evidence",
    "relaxation", "relaxing", "melatonin", "mysterious", "military",
    "vegetables", "telescope", "telescopes", "photograph", "photographs",
    "microscope", "microscopes", "machinery", "submarine", "submarines",
    "creature", "creatures", "variety", "society", "university", "universe",
    "elevator", "dictionary", "librarian", "library", "january's", "abundance",
    "affirmation", "affirmations", "appreciated", "appreciate", "possibility",
    "possibilities", "opportunity", "opportunities", "gratitude", "generously",
    "generous", "deliberately", "ultimately", "immediately", "experience",
    "experiences", "originally", "original", "mineral", "minerals",
    "invisibly", "unbelievable", "comfortably", "beautifully", "security",
    "celebration", "nourishing", "considering", "considered", "consider",
    "electrical", "electronic", "electronics", "intelligent", "everyday",
    "underwater", "accidentally", "accident", "medieval", "industrial",
    "industry", "technology", "scientific", "scientifically", "scientist",
    "scientists", "illuminated", "delicious", "delicately", "delicate",
}

VOWELS = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    """A plain vowel-group estimate; good enough to find 4-syllable words."""
    w = word.lower().strip("'’-")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(VOWELS.findall(w)))


def _norm(w: str) -> str:
    return w.lower().strip("'’-").replace("’", "'")


def _named_forms(named: list[str]) -> set[str]:
    out = set()
    for n in named or []:
        for part in re.findall(r"[A-Za-z]+", n):
            p = part.lower()
            out |= {p, p + "s", p + "es"}
    return out


def is_hard(word: str, named: set[str]) -> bool:
    n = _norm(word)
    if n in named or n in PLAIN_LONG or n.rstrip("s") in PLAIN_LONG:
        return False
    return syllables(n) >= 4


def _numerals(text: str) -> list[str]:
    return [m.group(0).rstrip(",") for m in NUMERAL.finditer(text)]


def text_problems(text: str, named: list[str] | None = None,
                  where: str = "") -> list[str]:
    """Every plain-words problem in one stretch of spoken text."""
    tag = f"{where}: " if where else ""
    out: list[str] = []
    words = WORD.findall(text)
    if not words:
        return [f"{tag}EMPTY no spoken words examined"]
    nf = _named_forms(named or [])

    for m in ACRONYM.finditer(text):
        if m.group(0) not in {"I", "OK"}:
            out.append(f"{tag}ACRONYM {m.group(0)!r}")
    for m in LETTER_DIGIT.finditer(text):
        out.append(f"{tag}LETTER_DIGIT {m.group(0)!r}")
    for n in _numerals(text):
        digits = re.sub(r"\D", "", n)
        if len(digits) > 3:
            out.append(f"{tag}LONG_NUMBER {n!r} (more than 3 digits; say it in plain words)")
    for m in DECIMAL.finditer(text):
        out.append(f"{tag}DECIMAL {m.group(0)!r}")
    for m in UNIT_ABBR.finditer(text):
        out.append(f"{tag}UNIT {m.group(0).strip()!r}")
    for m in UNIT_WORD.finditer(text):
        out.append(f"{tag}UNIT {m.group(0)!r}")
    run: list[str] = []
    for w in words + ["."]:
        if _norm(w) in NUMBER_WORDS and not (_norm(w) == "and" and not run):
            run.append(w)
            continue
        while run and _norm(run[-1]) == "and":
            run.pop()
        if len(run) >= 4:
            out.append(f"{tag}NUMBER_STRING {' '.join(run)!r}")
        run = []
    for m in EQUATION.finditer(text):
        out.append(f"{tag}EQUATION {m.group(0).strip()!r}")
    for m in BRACKETS.finditer(text):
        out.append(f"{tag}BRACKETS {m.group(0)!r}")

    hard = [is_hard(w, nf) for w in words]
    for i in range(len(words)):
        win = hard[i:i + 5]
        if sum(win) >= 3:
            out.append(f"{tag}JARGON_STRING {' '.join(words[i:i + 5])!r}")
            break
    share = sum(hard) / len(words)
    if len(words) >= 200 and share > 0.025:
        hw = sorted({_norm(w) for w, h in zip(words, hard) if h})[:8]
        out.append(f"{tag}HARD_WORDS {share:.1%} of {len(words)} words are 4+ syllables "
                   f"(at most 2.5%): {', '.join(hw)}")
    for n in named or []:
        hits = len(re.findall(rf"\b{re.escape(n)}s?\b", text, re.I))
        if hits > 1 and syllables(n.split()[-1]) >= 4:
            out.append(f"{tag}NAMED_REPEAT {n!r} said {hits} times (once, softly, then plain words)")
    return out


def fact_problems(rewrite: str, source: str, where: str = "") -> list[str]:
    """A rewrite may only simplify its fact-checked source, never add to it."""
    tag = f"{where}: " if where else ""
    out = []
    src_low = source.lower()
    src_nums = {re.sub(r"\D", "", n) for n in _numerals(source)}
    for n in _numerals(rewrite):
        if re.sub(r"\D", "", n) not in src_nums:
            out.append(f"{tag}INVENTED_NUMBER {n!r} is not in the source script")
    for sent in re.split(r"(?<=[.!?])\s+|\n+", rewrite):
        toks = WORD.findall(sent)
        for w in toks[1:]:
            if w[0].isupper() and w not in {"I", "I'm", "I'll", "I've"} \
                    and w.lower() not in src_low:
                out.append(f"{tag}INVENTED_NAME {w!r} is not in the source script")
    return sorted(set(out), key=out.index)


def shingles(text: str, n: int = 8) -> set[tuple[str, ...]]:
    w = [x.lower() for x in WORD.findall(text)]
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def overlap(a: str, b: str) -> float:
    """Share of `a`'s eight-word runs that also occur in `b` (0..1)."""
    sa, sb = shingles(a), shingles(b)
    return len(sa & sb) / len(sa) if sa else 1.0


# ------------------------------------------------------------------ self-test
GOOD = (
    "Far below the waves, the water is dark and still. A small fish drifts by, "
    "glowing softly along its belly. The light it makes is cold, like the glow "
    "of a firefly. Scientists call this glow bioluminescence, which simply means "
    "living light. It helps the fish hide, and find food, and find each other. "
    "About a hundred years ago, people first lowered lights into the deep and saw it.")

BROKEN = [
    ("acronym", "Scientists at NASA watched the sky for many quiet nights."),
    ("letter-digit", "The air holds CO2, and the water holds it too, quietly."),
    ("long number", "In 1908 a woman at a quiet observatory found a pattern."),
    ("long number with commas", "The fish lives about 10,000 feet down in the dark."),
    ("decimal", "The galaxy is about 2.5 million light years away from us."),
    ("unit abbreviation", "The trench is about 11 km deep, and very dark."),
    ("unit word", "The light has a wavelength of about four hundred nanometers."),
    ("percent", "Nearly 90% of the deep sea animals make their own light."),
    ("number string", "It sits two hundred and fifty three thousand feet below."),
    ("equation", "Energy = mass times the speed of light, squared, they say."),
    ("brackets", "The fish (a kind of anglerfish) waits in the dark."),
    ("jargon string", "Its bathypelagic chemiluminescent hydrostatic adaptation was observed."),
    ("named repeat", "Andromeda is a galaxy. Andromeda is far. Andromeda is old and quiet."),
]


def self_test() -> int:
    good = text_problems(GOOD, ["bioluminescence"])
    if good:
        print(f"NAMED STOP [SELF_TEST_BLIND] the good passage fails: {good}", file=sys.stderr)
        return 1
    missed = []
    for name, text in BROKEN:
        if not text_problems(text, ["Andromeda"] if name == "named repeat" else []):
            missed.append(name)
    fact_cases = [
        ("invented number", fact_problems("It was found in 1902.", "It was found in 1908.")),
        ("invented name", fact_problems("A man named Carter saw it.", "A woman named Leavitt saw it.")),
        ("empty", text_problems("", [])),
    ]
    missed += [n for n, p in fact_cases if not p]
    if overlap(GOOD, GOOD) < 0.99 or overlap(GOOD, BROKEN[0][1]) > 0.1:
        missed.append("overlap")
    if missed:
        print(f"NAMED STOP [SELF_TEST_BLIND] not caught: {', '.join(missed)}", file=sys.stderr)
        return 1
    print(f"SELF-TEST OK - {len(BROKEN) + len(fact_cases) + 1} broken shapes caught")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        return self_test()
    if len(argv) == 2 and argv[0] == "check":
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import whisper_lane as WL                           # noqa: PLC0415
        probs = WL.script_problems(argv[1])
        for p in probs:
            print(p)
        print(f"OUTPUT {len(probs)} plain-words problems in {argv[1]}")
        return 1 if probs else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
