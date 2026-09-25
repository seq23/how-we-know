"""Is this the same question as one already asked? One definition, everywhere.

THE INCIDENT (2026-09-25, a coverage review). Three of week 2026-W39's four
picks were one question in three phrasings -- "what lives in the depths of
the ocean", "what lives in the deep", "what lives in the sea" -- and all
three are episode 08, "What creatures live in the deep sea?", which aired
weeks ago. The materials-and-manufacturing queue held ten variants of "how
are microchips made", itself an episode already made, three of them naming
another channel ("... veritasium", "... ted", "... branch education").

WHY THE OLD CHECKS MISSED EVERY ONE OF THEM.

  * research/publish_order_domain.py `_screen()` compared EXACT token sets:
    "same set" or "strict superset of one kept". "depths"/"deep"/"sea"/"ocean"
    are four different tokens to it, so "what lives in the deep" and "what
    lives in the sea" share nothing it recognised.
  * A candidate killed as ALREADY_PUBLISHED was never recorded as seen, so
    every variant of a published question was measured against an empty list.
    "how are microchips made" was refused as already made -- and then
    "how are microchips manufactured" sailed through on its own.
  * Published episodes were matched by SLUG ONLY. The deep-sea catalogue is
    numbered ("08-what-creatures-live-in-the-deep-sea"), so no mined slug can
    ever equal one; the ALREADY_PUBLISHED check could not see deep sea at all.
  * QUALIFIER_NOISE named a handful of channels; veritasium, ted and branch
    education were not among them.
  * The queue files were read raw. loop/score.py only regenerates a domain's
    queue when it is EMPTY, so duplicates already written stayed selectable
    forever, whatever the generator later learned.

THE RULE. Two questions are the same when their QUESTION KEYS say so:

  key = the interrogative ("how", "why", "what", or "yn" for is/does/can...)
        + the content words, after
          - other-channel names and brand words are removed,
          - format words ("animation", "explained", "documentary") are removed,
          - synonyms fold to one word (deep/depths/deepest/ocean/sea -> "sea";
            made/manufactured/produced -> "make"; microchip/chip/cpu -> "chip"),
          - placeholder nouns ("creatures", "animals", "things") are dropped:
            "what creatures live in X" asks exactly "what lives in X".

  same_question(a, b) when
     a == b, or
     the content words are identical whatever the interrogative -- "how
         strong is steel" is answered by "why is steel so strong", or
     one key is a strict subset of the other (same interrogative) -- the
         longer one is the same question with qualifiers bolted on, or
     Jaccard(a, b) >= JACCARD_SAME.

  The first two need the smaller key to hold a word outside GENERIC_WORDS:
  "how deep is the ocean" keys to {how, sea}, a subset of half the deep-sea
  catalogue, and is not the same question as "how do deep sea creatures
  survive the pressure".

A topic that NAMES ANOTHER CHANNEL is not ours to make at all: it is someone
else's video with our title on it. `names_other_channel()` refuses it outright.

Deliberately a word list, not an embedding model: this repo has no embedding
path, the loop runs in GitHub Actions with no model in the selection path
("Claude is not part of the running system", RUNBOOK), and every refusal must
be explainable by pointing at the two keys.
"""
from __future__ import annotations

import re

# ------------------------------------------------------------------ channels
#
# Other YouTube channels, creators and shows that autocomplete bolts onto a
# question ("how are microchips made veritasium"). A topic that names one is
# REFUSED, not normalised: the searcher wants that channel's video.
# Multi-word names are matched as phrases; single short words ("ted") only as
# whole words.
OTHER_CHANNELS = (
    "veritasium", "ted", "ted ed", "ted-ed", "tedx", "branch education",
    "kurzgesagt", "vsauce", "smarter every day", "smartereveryday",
    "real engineering", "practical engineering", "mark rober", "tom scott",
    "scishow", "sci show", "minutephysics", "minute physics", "crash course",
    "khan academy", "dr binocs", "khan sir", "dhruv rathee", "brian cox",
    "neil degrasse", "neil degrasse tyson", "bill nye", "discovery channel",
    "discovery uk", "national geographic", "nat geo", "natgeo", "bbc earth",
    "bbc", "pbs", "nova", "pbs eons", "huggbees", "asianometry",
    "the action lab", "action lab", "stuff made here", "applied science",
    "undecided with matt ferrell", "joe scott", "half as interesting",
    "wendover", "wendover productions", "lemmino", "real science",
    "be smart", "sabine hossenfelder", "cleo abram", "johnny harris",
    "mrbeast", "mr beast", "how it's made", "how its made", "how it is made",
    "the b1m", "b1m", "engineerguy", "bill hammack", "ali abdaal",
    "steve mould", "numberphile", "periodic videos", "nilered", "nile red",
    "cody's lab", "codys lab", "thought emporium", "defunctland",
)

# Company and product names. Not refused -- "how are apple microchips made"
# is a real question -- but stripped from the key, because the question is
# the same one without the brand.
BRAND_WORDS = {
    "apple", "intel", "amd", "nvidia", "tsmc", "samsung", "qualcomm", "asml",
    "iphone", "tesla", "spacex", "nasa", "noaa", "mbari", "google", "ikea",
}

# Format and packaging words: they ask for a KIND of video, not a different
# question.
FORMAT_WORDS = {
    "animation", "animated", "explained", "explanation", "explain",
    "simple", "simply", "documentary", "video", "videos", "full", "episode",
    "shorts", "short", "clip", "4k", "hd", "facts", "fact", "easy", "quick",
    "basics", "overview", "guide", "tutorial", "lecture", "english",
}

# Placeholder nouns. "what creatures live in the deep sea" asks exactly what
# "what lives in the deep sea" asks.
PLACEHOLDER_WORDS = {
    "creature", "animal", "thing", "stuff", "organism", "species", "life",
    "lifeform", "lie", "exist",
}

# One concept, several spellings. Keys, not synonyms in the thesaurus sense:
# only words this channel's catalogue has actually produced as variants.
SYNONYMS = {
    # the deep-sea domain's core noun. For this channel "the deep", "the
    # depths", "the sea" and "the ocean" are the same place.
    "deep": "sea", "deeper": "sea", "deepest": "sea", "depth": "sea",
    "ocean": "sea", "sea": "sea", "abyss": "sea", "abyssal": "sea",
    # manufacturing verbs
    "made": "make", "make": "make", "making": "make", "manufacture": "make",
    "manufactured": "make", "manufacturing": "make", "produce": "make",
    "produced": "make", "production": "make", "fabricate": "make",
    "fabricated": "make", "fabrication": "make", "built": "make",
    "build": "make", "created": "make",
    # chips
    "microchip": "chip", "chip": "chip", "microprocessor": "chip",
    "processor": "chip", "cpu": "chip", "ic": "chip",
    # spellings
    "fibre": "fiber", "aluminium": "aluminum", "colour": "color",
    "sulphur": "sulfur",
    # living
    "live": "live", "living": "live", "lived": "live", "inhabit": "live",
    # judgement asks: "is damascus steel better / good / worth it" is one ask
    "better": "good", "best": "good", "worth": "good", "good": "good",
    "stronger": "strong", "strongest": "strong",
    # "why do deep sea creatures look so strange" is episode 01, "... look
    # so weird" (2026-09-25, the held why-deep-sea-creatures script)
    "strange": "weird", "weird": "weird", "odd": "weird", "bizarre": "weird",
    "alien": "weird", "unusual": "weird",
}

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "it",
    "its", "is", "are", "am", "do", "does", "did", "be", "been", "being",
    "was", "were", "can", "could", "will", "would", "should", "so", "really",
    "actually", "exactly", "that", "this", "these", "those", "there", "from",
    "by", "with", "out", "up", "you", "we", "they", "your", "our", "their",
    "i", "me", "my", "like", "look", "looks", "if", "into", "about", "s",
    "get", "gets", "much", "very", "just", "all", "some", "any", "have", "has",
    "than",
}

WH = ("how", "why", "what", "which", "where", "when", "who")
YES_NO = {"is", "are", "does", "do", "did", "can", "could", "will", "would",
          "should", "was", "were", "has", "have"}

# Tuned against the real 2026-09-25 queues (loop/tests/
# test_topic_selection_refuses_near_duplicates.py pins both directions).
JACCARD_SAME = 0.75

# Words that, ALONE, name no subject: a domain's own core noun after folding
# ("sea" is deep/depths/ocean/sea) and the manufacturing verb. "how deep is
# the ocean" keys to {how, sea}; that is a strict subset of "how do deep sea
# creatures survive the pressure" and is not the same question. The subset
# and cross-interrogative rules need at least one word outside this set.
GENERIC_WORDS = {"sea", "make", "work", "material"}

_WORD = re.compile(r"[a-z0-9]+")


def _channel_patterns() -> re.Pattern:
    names = sorted(OTHER_CHANNELS, key=len, reverse=True)
    alts = []
    for n in names:
        parts = [re.escape(p) for p in re.split(r"[\s\-]+", n.strip())]
        alts.append(r"[\s\-]*".join(parts))
    return re.compile(r"(?<![a-z0-9])(" + "|".join(alts) + r")(?![a-z0-9])",
                      re.I)


CHANNEL_RE = _channel_patterns()


def _clean(q: str) -> str:
    q = (q or "").lower().replace("’", "'")
    q = re.sub(r"\bwhat's\b", "what is", q)
    q = re.sub(r"\bhow's\b", "how is", q)
    q = re.sub(r"\bwho's\b", "who is", q)
    q = re.sub(r"'s\b", "", q)
    return q


def names_other_channel(q: str) -> str | None:
    """The other channel/creator/show this topic names, or None."""
    m = CHANNEL_RE.search(_clean(q))
    return m.group(1).strip() if m else None


def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "xes", "sses")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _word(w: str) -> str | None:
    """One raw word -> its key form, or None when it carries no meaning."""
    if w in STOPWORDS or w in BRAND_WORDS or w in FORMAT_WORDS:
        return None
    if w in SYNONYMS:
        return SYNONYMS[w]
    s = _singular(w)
    if s in STOPWORDS or s in BRAND_WORDS or s in FORMAT_WORDS:
        return None
    if s in PLACEHOLDER_WORDS or w in PLACEHOLDER_WORDS:
        return None
    return SYNONYMS.get(s, s)


def interrogative(q: str) -> str:
    words = _WORD.findall(_clean(q))
    if not words:
        return "?none"
    if words[0] in YES_NO:
        return "?yn"
    for w in words:
        if w in WH:
            return "?" + w
    return "?none"


def question_key(q: str) -> frozenset:
    """The question a topic string is really asking. See the module doc."""
    text = CHANNEL_RE.sub(" ", _clean(q))
    toks = {interrogative(q)}
    for w in _WORD.findall(text):
        if w in WH:
            continue
        k = _word(w)
        if k:
            toks.add(k)
    return frozenset(toks)


def _content(key: frozenset) -> frozenset:
    return frozenset(t for t in key if not t.startswith("?"))


def _specific(key: frozenset) -> frozenset:
    return _content(key) - GENERIC_WORDS


def why_same(a: frozenset, b: frozenset) -> str | None:
    """Why two keys are the same question, or None when they are not."""
    if not _content(a) or not _content(b):
        return None
    if a == b:
        return "identical question key"
    # Same content, different interrogative: "how strong is steel" and "why
    # is steel so strong", "what is carbon fiber made of" and "how is carbon
    # fiber made". One episode answers both. Needs a specific word, so "how
    # deep is the ocean" is not "why is the ocean deep".
    if _content(a) == _content(b) and _specific(a):
        return "same content words, different interrogative"
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    if small < big and _specific(small):
        return "same question with qualifiers added"
    j = len(a & b) / len(a | b)
    if j >= JACCARD_SAME:
        return f"question keys overlap {j:.2f} >= {JACCARD_SAME}"
    return None


def same_question(a: str, b: str) -> bool:
    return why_same(question_key(a), question_key(b)) is not None


def first_same(key: frozenset, kept: list[tuple[str, frozenset]]
               ) -> tuple[str, str] | None:
    """(kept question, why) for the first kept question `key` duplicates."""
    for q, k in kept:
        why = why_same(key, k)
        if why:
            return q, why
    return None
