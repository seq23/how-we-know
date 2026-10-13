"""The long-form title formula, as code. Long-form ONLY; Shorts keep loop/titles.py.

    .venv/bin/python loop/longform_title.py check <slug> "<title>"     # judge one
    .venv/bin/python loop/longform_title.py propose --slugs a b c      # draft + write
    .venv/bin/python loop/longform_title.py propose --pending --limit 6
    .venv/bin/python loop/longform_title.py propose --published --dry-run
    .venv/bin/python loop/longform_title.py propose --needed --limit 6    # the daily lane

WHY THIS EXISTS. Owner decision, 12-13 Oct 2026 (repackage job 1 of 3). The
2026-10-08 formula (loop/titles.py) kept every query word and ended "— and how
we know". On the long-form side that produced titles that restate the search
query and spend a quarter of their length on the channel's own name: "The
midnight zone — and how we know". The brand stays in the channel name and in
the script's second act. A long-form title now has to do one job: make a
scroller stop, with a claim the episode actually makes.

THE LOCK (owner, 13 Oct 2026 - supersedes the 60-character formula below
where they differ). Her three titles ARE the reference set (EXEMPLARS):
    20-what-is-the-midnight-zone               "Why Is the Deep Sea So Dark?"
    19-what-is-the-deepest-fish-ever-recorded  "How Deep Can a Fish Live?"
    how-strong-is-titanium                     "Is Titanium Stronger Than Steel?"
  * <= 40 characters, target ~30;
  * sixth grade: Flesch-Kincaid grade <= 6, no word over three syllables
    unless it is the subject's own name, no jargon (JARGON);
  * ONE idea: usually a plain question; a short claim only when the
    script's answer is itself a contradiction (then it must carry one);
  * the subject named in the first four words, in the word a stranger uses
    (the question's own subject words, or the domain's plain word: deep sea);
  * numbers only when simple and vivid (<= 2 significant digits, no decimals);
  * never "how we know"; truth-guarded against the script as before.

THE FORMULA (title_problems() enforces every line, mechanically):

  * at most TITLE_MAX = 60 characters (what a phone shows untruncated);
  * a SPECIFIC subject (>= MIN_CONTENT_WORDS content words) plus a STAKE: a
    concrete figure, a contradiction ("never", "without", "not", ...) or a
    stake verb ("crush", "die", "shatter", ...);
  * never the phrase "how we know" in any form;
  * never a bare restatement of the episode's question: a title whose content
    words are all already in the question adds nothing the search result
    didn't, and every script in this repo carries a stake in its
    Direct-answer lock;
  * no clickbait vocabulary (loop/titles.py BANNED, the same list), no shouted
    capitals, not a bare question, no < or > (YouTube rejects them).

THE TRUTH GUARD, the way loop/opening.py checks the answer: every content word
of the title must be traceable, after a light stem, to the script's evidence
text (the Direct-answer lock, the narration and the sources), and every figure
in it must be stated there - digits, or spelled out the way the narration
speaks numbers for the voice. The script's own `## YouTube title` section is
cut out first, so a proposed title is never evidence for itself. An
unsupported word or figure is a rejection, not a warning.

WHERE A LONG-FORM TITLE COMES FROM (title_for_upload, the only door):
  1. loop/state/titles.json, when its entry for the slug passes today;
  2. the script's `## YouTube title`, when it passes;
  3. nothing - the upload lane HOLDS the slug (TITLE_REFUSED) and the proposer
     (`propose --pending`, run daily in loop-repackage) drafts one on the $0 route.
A failing title therefore cannot reach YouTube by any path.

THE PROPOSER drafts on the repo's model route (loop/llm_router.py: her Claude
subscription first, Gemini free tier, then the $0 OpenRouter list; never a
paid model), validates every candidate, feeds the rejections back and retries
up to MAX_ATTEMPTS times. Results go to loop/state/titles.json:
    {slug: {slug, question, old_title, old_title_source, new_title,
            checks_passed, problems, model, proposed_at, applied_at}}
`applied_at` stays null until loop/repackage.py `apply` writes it to the live
video (job 2). A slug whose every attempt failed is recorded with
checks_passed false and is never applied.

Guarded by validator V47 (loop/validate.py) and
loop/tests/test_longform_title.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

STATE = LOOP / "state" / "titles.json"
SCRIPTS = ROOT / "scripts"

TITLE_MAX = 40                 # owner's lock, 13 Oct 2026 (was 60)
TITLE_TARGET = 30
MIN_CONTENT_WORDS = 2
MAX_GRADE = 6.0                # Flesch-Kincaid grade: sixth grade
MAX_SYLLABLES = 3              # per word, unless it is the subject's own name
SUBJECT_WITHIN = 4             # the subject is named in the first few words
# THE LOCK - the owner's own titles (13 Oct 2026). The gate must pass these
# three against their scripts and refuse anything that would not sit beside
# them (loop/tests/test_longform_title.py pins them).
EXEMPLARS = {
    "20-what-is-the-midnight-zone": "Why Is the Deep Sea So Dark?",
    "19-what-is-the-deepest-fish-ever-recorded": "How Deep Can a Fish Live?",
    "how-strong-is-titanium": "Is Titanium Stronger Than Steel?",
}
# The word a stranger uses for a domain counts as naming the subject ("Why Is
# the Deep Sea So Dark?" is the midnight-zone episode).
# THE SERIES SHAPE (owner, 13 Oct 2026) for a multi-question video: two or
# three plain subject nouns and "What's Inside?" - "Bread, Steak, Chocolate:
# What's Inside?". The one allowed exception to "one idea".
SERIES_RE = re.compile(r"^[A-Z][a-z]{1,11}(?:, [A-Z][a-z]{1,11}){1,2}: What['\u2019]s Inside\?$")
DOMAIN_PLAIN = {"deep-sea-ocean-science": {"deep", "sea", "ocean"}}
JARGON = {"bathypelagic", "abyssopelagic", "hadal", "pelagic", "abyssal",
          "tensile", "anisotropic", "gigapascal", "gigapascals", "megapascal",
          "megapascals", "crystalline", "polymer", "polymers", "stabilization",
          "metallurgical", "microstructure", "isotope", "isotopes"}
MAX_ATTEMPTS = 3
RULE_START = "2026-10-13"      # uploads from this day on are held to it (V47)

# "how we know" in any spelling a model might reach for.
BRAND_PHRASE = re.compile(r"\bhow\s+(?:we|scientists?|do\s+we)\s+know\b", re.I)

STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "do",
    "does", "did", "can", "could", "will", "would", "has", "have", "had", "of",
    "in", "on", "at", "to", "for", "from", "by", "as", "into", "onto", "over",
    "under", "up", "down", "out", "off", "and", "or", "but", "so", "if",
    "than", "then", "that", "this", "these", "those", "it", "its", "it's",
    "what", "why", "how", "when", "where", "which", "who", "whom", "whose",
    "we", "you", "your", "our", "they", "their", "them", "there", "here",
    "with", "about", "one", "just", "really", "actually", "even", "still",
    "most", "more", "less", "much", "many", "some", "any", "all", "every",
    "each", "s", "t", "what's", "that's", "there's", "here's", "who's",
}
# Words that state a contradiction: the title says the obvious is false.
CONTRADICTION = {
    "never", "no", "not", "without", "isn't", "aren't", "doesn't", "don't",
    "can't", "cannot", "won't", "nothing", "nobody", "none", "only", "yet",
    "despite", "although", "instead", "wrong", "myth", "invisible", "zero",
    "impossible", "backwards", "opposite", "unexpected", "surprising",
}
# Verbs that carry a stake: something is lost, broken or survived.
STAKE = {
    "die", "dies", "dying", "dead", "death", "kill", "kills", "crush",
    "crushes", "crushed", "crushing", "break", "breaks", "broke", "broken",
    "fail", "fails", "failed", "failure", "survive", "survives", "surviving",
    "explode", "explodes", "collapse", "collapses", "shatter", "shatters",
    "melt", "melts", "burn", "burns", "freeze", "freezes", "vanish",
    "vanishes", "lose", "loses", "lost", "starve", "starves", "drown",
    "implode", "implodes", "tear", "tears", "crack", "cracks", "rust",
    "rusts", "stop", "stops", "outlast", "outlasts", "beat", "beats",
    "dissolve", "dissolves", "eat", "eats", "eaten", "hunt", "hunts",
}
# PLAINNESS (owner, 13 Oct 2026, on "6 crystals, a breathing fungus and a
# crust you never see": "those words make no sense"). A title names its
# subject in the words a stranger recognises instantly and states a claim a
# 12-year-old understands on first read. Question words that are NOT the
# subject - they never satisfy "names the subject":
SUBJECT_GENERIC = {
    "made", "make", "work", "works", "working", "get", "gets", "got", "so",
    "know", "knows", "scientists", "scientist", "people", "happens", "happen",
    "happening", "brought", "thing", "things", "something", "part", "really",
    "strong", "hot", "big", "old", "far", "long", "fast", "high", "low",
    "weird", "scary", "creepier", "deeper", "true", "real", "kind", "kinds",
    "type", "types", "way", "ways", "use", "used", "need", "needs",
    "not", "ever", "go", "goes", "look", "looks", "live", "lives", "living",
    "die", "dies", "survive", "recorded", "explored", "little", "other",
    "we've", "reach", "designed", "printed", "surfacing", "brought",
}
PLAIN_MIN_FLESCH = 60.0        # Flesch reading ease of the title alone
# "6 crystals, a breathing fungus and a crust": a numbered list of riddles.
# A list that NAMES its subjects ("Why bread rises, steak browns and chocolate
# snaps") is plain; a list of riddles is caught by the subject check.
LIST_RE = re.compile(r"^\s*\d+\s+[a-z]+\b[^.]*,", re.I)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "million": 1_000_000,
               "billion": 1_000_000_000}
FIGURE_WORDS = {"half", "twice", "double", "triple", "thousand", "million",
                "billion", "hundred", "percent", "degrees"}


def _banned() -> tuple[str, ...]:
    import titles                                          # noqa: PLC0415
    return titles.BANNED


# ------------------------------------------------------------- tokenising
def _tokens(s: str) -> list[str]:
    s = (s or "").lower().replace("’", "'").replace("—", " ")
    return re.findall(r"[a-z0-9][a-z0-9'.,-]*[a-z0-9]|[a-z0-9]", s)


def _clean(w: str) -> str:
    return w.strip("'.,-")


def stem(w: str) -> str:
    w = _clean(w.lower())
    if w.endswith("'s"):
        w = w[:-2]
    for suf in ("ically", "ation", "ingly", "ness", "ment", "ing", "ied",
                "ies", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_words(s: str) -> list[str]:
    out = []
    for t in _tokens(s):
        t = _clean(t)
        if not t or t in STOP or re.fullmatch(r"[\d.,]+", t):
            continue
        out.append(t)
    return out


def _match(a: str, have: set[str]) -> bool:
    """Stem match, plus a shared-prefix match for inflections the light
    stemmer misses (exist/existed/existence): both stems >= 5 characters and
    one a prefix of the other."""
    if a in have:
        return True
    if len(a) >= 5:
        return any(len(h) >= 5 and (h.startswith(a) or a.startswith(h))
                   for h in have)
    return False


# ---------------------------------------------------------------- figures
def figures(s: str) -> list[float]:
    """Every number written in digits, and every spelled-out one, as floats."""
    out = []
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    out += _spelled_numbers(s)
    return out


def _spelled_numbers(s: str) -> list[float]:
    words = re.findall(r"[a-z]+", (s or "").lower().replace("-", " "))
    out, cur, total, live = [], 0, 0, False
    for w in words + ["."]:
        if w in NUMBER_WORDS:
            cur += NUMBER_WORDS[w]
            live = True
        elif w == "hundred" and live:
            cur *= 100
        elif w in SCALE_WORDS and live:
            total += cur * SCALE_WORDS[w]
            cur = 0
        elif w == "and" and live:
            continue
        else:
            if live:
                out.append(float(total + cur))
            cur, total, live = 0, 0, False
    return out


def _numbers_in_title(t: str) -> list[float]:
    return [float(m.replace(",", ""))
            for m in re.findall(r"\d[\d,]*(?:\.\d+)?", t or "")]


# ------------------------------------------------------------ the evidence
def evidence_text(script: str) -> str:
    """What a title may draw on: everything but the proposed-title section
    and the front-matter lines (status, word count, estimates)."""
    body = re.sub(r"^## YouTube title\s*\n.*?(?=^## |\Z)", "", script or "",
                  flags=re.M | re.S)
    body = re.sub(r"^\*\*[^*]+:\*\*.*$", "", body, flags=re.M)
    return body


def question_of(script: str) -> str:
    m = re.search(r"^# (.+)$", script or "", re.M)
    return m.group(1).strip() if m else ""


def answer_lock(script: str) -> str:
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)(?:\n## |\Z)",
                  script or "", re.S)
    return " ".join(m.group(1).split()) if m else ""


def has_stake(title: str) -> bool:
    toks = [_clean(t) for t in _tokens(title)]
    if _numbers_in_title(title):
        return True
    return any(t in CONTRADICTION or t in STAKE or t in FIGURE_WORDS
               or t.endswith("n't") for t in toks)


# --------------------------------------------------------------- the gate
def subject_words(question: str) -> set[str]:
    """The episode's subject, in the question's own plain words: its content
    words minus the ones that are only how the question is asked."""
    out = set()
    for w in content_words(question or ""):
        for x in re.split(r"[-\u2013]", w):
            if x and x not in SUBJECT_GENERIC and x not in STOP:
                out.add(x)
    return out


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 2 if re.search(r"\d", word) else 0      # a figure reads as ~2
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def flesch(text: str, names: set[str] | None = None) -> float:
    """Flesch reading ease of one line: 206.835 - 1.015*(words/sentence)
    - 84.6*(syllables/word). 60+ is plain English. Words in `names` (the
    episode's own subject - "hydrothermal", "semiconductor") count as one
    syllable: the subject's name is fixed, the words around it are not."""
    words = [w for w in re.findall(r"[\w][\w'.,%-]*", text or "") if w.strip(".,")]
    if not words:
        return 0.0
    ns = {stem(n) for n in (names or ())}
    syl = sum(1 if stem(_clean(w.strip(".,"))) in ns else _syllables(w)
              for w in words)
    return 206.835 - 1.015 * len(words) - 84.6 * (syl / len(words))


def fk_grade(text: str, names: set[str] | None = None) -> float:
    """Flesch-Kincaid grade of one line; the subject's own name counts as one
    syllable ("titanium" is the word a stranger uses for titanium)."""
    words = [w for w in re.findall(r"[\w][\w'.,%-]*", text or "") if w.strip(".,")]
    if not words:
        return 99.0
    ns = {stem(n) for n in (names or ())}
    syl = sum(1 if stem(_clean(w.strip(".,"))) in ns else _syllables(w)
              for w in words)
    return 0.39 * len(words) + 11.8 * (syl / len(words)) - 15.59


def _simple_number(tok: str) -> bool:
    """'5', '10', '11,000', '340' are simple; '8,336', '1.4', '0.4' are not."""
    t = tok.replace(",", "")
    if not re.fullmatch(r"\d+", t):
        return False
    if "," not in tok and 1000 <= int(t) <= 2099:
        return True                  # a year ("in 1857") is vivid, not a statistic
    return len(t.rstrip("0")) <= 2


def plainness_problems(title: str, question: str, script: str = "") -> list[str]:
    """The owner's LOCKED title contract (13 Oct 2026), mechanically: one
    idea, sixth-grade words, the subject named in the first few words in
    the word a stranger uses, simple numbers only."""
    p: list[str] = []
    m = re.search(r"^\*\*Domain:\*\*\s*(\S+)", script or "", re.M)
    subj = subject_words(question) | DOMAIN_PLAIN.get(m.group(1) if m else "", set())
    words = re.findall(r"[\w][\w'%-]*", title)
    lead = [w for w in words if _clean(w).lower() not in STOP][:SUBJECT_WITHIN]
    early = {stem(x) for w in lead
             for x in re.split(r"[-\u2013]", _clean(w).lower()) if x}
    if subj and not (early & {stem(w) for w in subj}):
        p.append(f"title does not name the subject in its first "
                 f"{SUBJECT_WITHIN} words that count, in a stranger's word (one of: "
                 f"{', '.join(sorted(subj))}) - never a metaphor or riddle")
    series = bool(SERIES_RE.match(title))
    if not series and (LIST_RE.search(title) or title.count(",") > 1
                       or re.search(r"[:;]", title)):
        p.append("title carries more than one idea - one plain question or "
                 "one short claim")
    g = fk_grade(title, subj)
    if g > MAX_GRADE:
        p.append(f"title reads at grade {g:.1f}; the lock is sixth grade "
                 f"(short common words)")
    ss = {stem(w) for w in subj}
    long_ = [w for w in words if _syllables(w) > MAX_SYLLABLES
             and stem(_clean(w)) not in ss]
    jar = [w for w in words if _clean(w).lower() in JARGON]
    if long_ or jar:
        p.append(f"title uses jargon or long words {sorted(set(long_ + jar))} - "
                 f"the words a curious 12-year-old says out loud")
    hard = [w for w in re.findall(r"\d[\d,.]*", title)
            if not _simple_number(w.rstrip(".,"))]
    if hard:
        p.append(f"title number(s) {hard} are not simple and vivid "
                 f"('5 miles down', never '8,336 metres')")
    return p


def title_problems(title: str, script: str, question: str | None = None) -> list[str]:
    """Everything wrong with `title` as a long-form title. [] = it may ship."""
    p: list[str] = []
    t = (title or "").strip()
    if not t:
        return ["title is empty"]
    q = question if question is not None else question_of(script)
    if len(t) > TITLE_MAX:
        p.append(f"title is {len(t)} characters, over the {TITLE_MAX} a phone "
                 f"shows")
    if not (t[0].isupper() or t[0].isdigit()):
        # A fragment: "percent of deep-sea pelagic animals produce light" was
        # proposed and passed on 2026-10-13 after _candidates() stripped its
        # leading figure as if it were list numbering.
        p.append(f"title starts with {t[0]!r}: a title begins with a capital "
                 f"or a figure, never mid-sentence")
    if BRAND_PHRASE.search(t):
        p.append("title contains 'how we know' - the brand lives in the "
                 "channel name and the script's second act, never the title")
    is_question = t.endswith("?")
    if "<" in t or ">" in t:
        p.append("title contains < or >, which YouTube rejects")
    low = t.lower()
    for b in _banned():
        if b in low:
            p.append(f"title uses banned clickbait wording {b!r}")
    if any(len(w) > 3 and w.isupper() and w.isalpha() for w in t.split()):
        p.append("title shouts a word in capitals")
    cw = content_words(t)
    if len(cw) < MIN_CONTENT_WORDS:
        p.append(f"title has {len(cw)} content word(s); a specific subject "
                 f"needs at least {MIN_CONTENT_WORDS}")
    if not is_question and not has_stake(t):
        p.append("a claim title must state the script's contradiction (never/"
                 "not/without ...) or a stake; otherwise ask the plain "
                 "question a curious person would type")
    p += plainness_problems(t, q, script)
    qs = {stem(w) for w in content_words(q)}
    ts = {stem(w) for w in cw}
    if ts and qs and ts <= qs:
        p.append(f"title is a bare restatement of the question {q!r}: every "
                 f"content word is already in it; say the stake the script "
                 f"makes")
    # THE TRUTH GUARD.
    ev = evidence_text(script)
    have = {stem(w) for w in content_words(ev)} | qs
    # A contradiction word is the title's framing of a negation the script
    # makes; it is traceable when the evidence negates anything at all.
    negates = any(_clean(w) in CONTRADICTION or _clean(w).endswith("n't")
                  for w in _tokens(ev))
    unsupported = [w for w in cw if not _match(stem(w), have)
                   and not (negates and (w in CONTRADICTION or w.endswith("n't")))]
    if unsupported:
        p.append(f"title word(s) {unsupported} are not in the script's "
                 f"answer, narration or sources - unsupported claim")
    nums = _numbers_in_title(t)
    if nums:
        stated = set(figures(ev)) | set(figures(q))
        bad = [n for n in nums if n not in stated]
        if bad:
            p.append(f"title states {[_fmt(n) for n in bad]}, which the "
                     f"script never does - no invented figures")
    return p


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)


def problems(title: str, script: str, question: str | None = None) -> list[str]:
    return title_problems(title, script, question)


# ---------------------------------------------------------- the state file
def load(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or STATE).read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("titles", {})
    return d


def save(doc: dict, path: Path | None = None) -> None:
    doc["updated"] = _now()
    p = path or STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True,
                            ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def script_title(script: str) -> str | None:
    import titles                                          # noqa: PLC0415
    return titles.script_title(script)


def title_for_upload(slug: str, script: str, question: str | None = None,
                     state: dict | None = None) -> tuple[str | None, list[str], str]:
    """(title, problems, source). title is None when nothing passes - the
    caller HOLDS the slug. Never invents one."""
    doc = state if state is not None else load()
    why: list[str] = []
    row = doc["titles"].get(slug) or {}
    cand = row.get("new_title")
    if cand:
        pr = title_problems(cand, script, question)
        if not pr:
            return cand, [], "titles.json"
        why += [f"titles.json: {x}" for x in pr]
    own = script_title(script)
    if own:
        pr = title_problems(own, script, question)
        if not pr:
            return own, [], "script"
        why += [f"script ## YouTube title: {x}" for x in pr]
    if not cand and not own:
        why.append("no proposed title in loop/state/titles.json and no "
                   "## YouTube title in the script")
    return None, why, ""


# ------------------------------------------------------------- the proposer
PROMPT = """You title long-form YouTube episodes for an evidence-first science \
channel. Write {n} candidate titles for the episode below, one per line, no \
numbering, no quotes, nothing else.

THE OWNER'S LOCKED RULE - a program checks every candidate:
- at most {max} characters; aim for about {target};
- ONE idea: usually the plain question a curious person would say out loud or \
type into search; a short claim only when the script's answer is itself a \
contradiction ("... is not ...");
- sixth-grade words: short and common, no jargon, no word over three \
syllables except the subject's own name;
- name the subject in the first few words, in the word a stranger uses - one \
of: {subject};
- numbers only when simple and vivid ("5 miles down", never "8,336 metres");
- never the words "how we know";
- every word must be supported by the script below; add no facts.

The owner's own titles - yours must sit naturally beside these:
  "Why Is the Deep Sea So Dark?"
  "How Deep Can a Fish Live?"
  "Is Titanium Stronger Than Steel?"

QUESTION: {question}

DIRECT-ANSWER LOCK: {answer}

SCRIPT EXCERPT:
{excerpt}
"""


def _excerpt(script: str, words: int = 700) -> str:
    import opening                                         # noqa: PLC0415
    return " ".join(opening.narration_words(script)[:words])


def _ask(messages: list[dict]) -> tuple[str, str]:
    """One model call on the repo's $0 route. Returns (text, model_used).
    Tests replace this function; nothing here may reach a paid model."""
    import author                                          # noqa: PLC0415
    resp = author.call_openrouter(messages, author.configured_model(),
                                  author.api_key() or "", timeout=240,
                                  temperature=0.7)
    choice = (resp.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return text, resp.get("model_used") or ""


def _candidates(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        # List markers only ("1. ", "2) ", "- ", "* "). The old pattern
        # [-*\d.)]+ also ate a LEADING FIGURE: "76 percent of ..." became
        # "percent of ..." (2026-10-13, what-lives-in-the-depths-of-the-ocean).
        line = re.sub(r"^\s*(?:[-*\u2022]|\d{1,2}[.)])\s+", "", line).strip().strip('"\'')
        if line and len(line) < 120:
            out.append(line)
    return out


def propose(slug: str, script: str, question: str | None = None,
            n: int = 5) -> dict:
    """Draft, validate, retry. Returns {new_title, checks_passed, problems,
    model, attempts}."""
    q = question or question_of(script)
    messages = [{"role": "user", "content": PROMPT.format(
        n=n, max=TITLE_MAX, target=TITLE_TARGET, question=q,
        answer=answer_lock(script),
        subject=", ".join(sorted(subject_words(q))) or "the question's subject",
        excerpt=_excerpt(script))}]
    last: dict[str, list[str]] = {}
    model = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text, model = _ask(messages)
        cands = _candidates(text)
        judged = [(c, title_problems(c, script, q)) for c in cands]
        ok = [c for c, pr in judged if not pr]
        if ok:
            # Shortest passing candidate: the most room left on a phone.
            best = min(ok, key=len)
            return {"new_title": best, "checks_passed": True, "problems": [],
                    "model": model, "attempts": attempt}
        last = {c: pr for c, pr in judged}
        feedback = "\n".join(f"- {c!r}: {'; '.join(pr)}"
                             for c, pr in judged[:n]) or "- no candidates"
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "Every candidate was rejected by the "
             "checks:\n" + feedback + f"\n\nWrite {n} new candidates that pass. "
             "Same rules. Titles only, one per line."}]
    best = next(iter(last), None)
    return {"new_title": best, "checks_passed": False,
            "problems": last.get(best, ["the model returned no candidate"]),
            "model": model, "attempts": MAX_ATTEMPTS}


def old_title_of(slug: str, question: str, script: str) -> tuple[str, str]:
    """What the video is (or would be) titled under the old rule. The ledger
    row's recorded title when there is one; otherwise loop/titles.py's 2026-10-08
    formula, which is what the upload path produced until this module."""
    import ledger                                          # noqa: PLC0415
    for r in ledger.load().get("published") or []:
        if r.get("slug") == slug and r.get("title"):
            return r["title"], "ledger"
    import titles                                          # noqa: PLC0415
    return titles.title_for(question, script), "titles.py (2026-10-08 rule)"


def _question_for(slug: str, script: str) -> str:
    try:
        import batch_queue                                 # noqa: PLC0415
        for q in batch_queue.queued_entries():
            if q.get("slug") == slug and q.get("query"):
                return q["query"]
    except Exception:                                      # noqa: BLE001
        pass
    import ledger                                          # noqa: PLC0415
    for r in ledger.load().get("published") or []:
        if r.get("slug") == slug and r.get("question"):
            return r["question"]
    return question_of(script)


def pending_slugs() -> list[str]:
    """Scripts not yet uploaded whose title would not pass today."""
    import ledger                                          # noqa: PLC0415
    done = ledger.published_slugs()
    doc = load()
    out = []
    for p in sorted(SCRIPTS.glob("*.md")):
        if p.stem in done:
            continue
        text = p.read_text(encoding="utf-8")
        t, _, _ = title_for_upload(p.stem, text, _question_for(p.stem, text), doc)
        if t is None:
            out.append(p.stem)
    return out


def published_slugs() -> list[str]:
    import ledger                                          # noqa: PLC0415
    return [r["slug"] for r in ledger.load().get("published") or []
            if r.get("video_id") and not r.get("retired_at")
            and (SCRIPTS / f"{r['slug']}.md").exists()]


def published_needing(doc: dict | None = None) -> list[str]:
    """Live long-form videos (public or private-scheduled) whose titles.json
    row is missing, failed, or no longer passes against today's script.
    `repackage apply` puts only titles.json rows on live videos, so a live
    video with no passing row would keep its old title forever; the daily
    lane proposes these (job 2, 13 Oct 2026). Unique, ledger order."""
    doc = doc if doc is not None else load()
    out: list[str] = []
    for slug in published_slugs():
        if slug in out:
            continue
        text = (SCRIPTS / f"{slug}.md").read_text(encoding="utf-8")
        row = doc["titles"].get(slug) or {}
        t = row.get("new_title")
        if row.get("checks_passed") and t and not title_problems(
                t, text, _question_for(slug, text)):
            continue
        out.append(slug)
    return out


def needed_slugs() -> list[str]:
    """Everything the daily lane must title: scripts not yet uploaded first
    (the upload lane holds them), then live videos with no passing row."""
    out = pending_slugs()
    return out + [s for s in published_needing() if s not in out]


def run_propose(slugs: list[str], dry_run: bool = False,
                path: Path | None = None) -> dict:
    doc = load(path)
    made, failed = [], []
    for slug in slugs:
        sp = SCRIPTS / f"{slug}.md"
        if not sp.exists():
            failed.append((slug, "no scripts/<slug>.md"))
            continue
        text = sp.read_text(encoding="utf-8")
        q = _question_for(slug, text)
        old, src = old_title_of(slug, q, text)
        if dry_run:
            print(f"  would propose {slug}: old {old!r}")
            made.append(slug)
            continue
        if slug in EXEMPLARS:
            # The owner wrote this one (the lock); the model never replaces it.
            t_ = EXEMPLARS[slug]
            pr_ = title_problems(t_, text, q)
            r = {"new_title": t_, "checks_passed": not pr_, "problems": pr_,
                 "model": "owner (locked exemplar, 13 Oct 2026)", "attempts": 0}
        else:
            r = propose(slug, text, q)
        prev = doc["titles"].get(slug) or {}
        doc["titles"][slug] = {
            "slug": slug, "question": q, "old_title": old,
            "old_title_source": src, "new_title": r["new_title"],
            "checks_passed": r["checks_passed"], "problems": r["problems"],
            "model": r["model"], "attempts": r["attempts"],
            "proposed_at": _now(),
            # Re-proposing an applied title starts a new cycle for job 2.
            "applied_at": None,
            **({"previous": {k: prev.get(k) for k in
                             ("new_title", "applied_at")}} if prev else {}),
        }
        (made if r["checks_passed"] else failed).append(
            slug if r["checks_passed"] else (slug, "; ".join(r["problems"])[:200]))
        print(f"  {'OK  ' if r['checks_passed'] else 'FAIL'} {slug}: "
              f"{r['new_title']!r}")
    if not dry_run and slugs:
        save(doc, path)
    return {"made": made, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("slug")
    c.add_argument("title")
    pr = sub.add_parser("propose")
    g = pr.add_mutually_exclusive_group(required=True)
    g.add_argument("--slugs", nargs="+")
    g.add_argument("--slugs-file")
    g.add_argument("--pending", action="store_true")
    g.add_argument("--published", action="store_true")
    g.add_argument("--needed", action="store_true",
                   help="pending scripts + live videos with no passing title")
    pr.add_argument("--limit", type=int, default=0)
    pr.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        sp = SCRIPTS / f"{a.slug}.md"
        text = sp.read_text(encoding="utf-8") if sp.exists() else ""
        if not text:
            print(f"NAMED STOP: no scripts/{a.slug}.md to check against")
            return 3
        p = title_problems(a.title, text, _question_for(a.slug, text))
        for x in p:
            print(f"  ✗ {x}")
        print("PASS" if not p else "FAIL")
        return 0 if not p else 1

    if a.slugs:
        slugs = a.slugs
    elif a.slugs_file:
        slugs = [s.strip() for s in Path(a.slugs_file).read_text().split()
                 if s.strip()]
    elif a.pending:
        slugs = pending_slugs()
    elif a.needed:
        slugs = needed_slugs()
    else:
        slugs = published_slugs()
    if a.limit:
        slugs = slugs[: a.limit]
    from common import Stage, week_id                      # noqa: PLC0415
    with Stage("titles", week_id(),
               zero_work_hint="No script needed a long-form title.") as st:
        if not slugs:
            st.named_stop(
                "TITLES_UP_TO_DATE",
                "every script not yet uploaded (and, with --needed, every "
                "live long-form video) already has a long-form title that "
                "passes loop/longform_title.py",
                unblock="Nothing to do; new scripts are titled on the next run.")
        r = run_propose(slugs, dry_run=a.dry_run)
        for s in r["made"]:
            st.work(f"titled {s}" + (" (dry run)" if a.dry_run else ""))
        for s, why in r["failed"]:
            st.note(f"refused {s}: {why}")
        if not r["made"]:
            st.named_stop(
                "TITLES_REFUSED",
                f"{len(r['failed'])} script(s) got no passing long-form title "
                f"after {MAX_ATTEMPTS} attempts each: "
                + "; ".join(f"{s} ({w[:80]})" for s, w in r["failed"]),
                detail={"refused": [s for s, _ in r["failed"]]},
                held_items=sorted(s for s, _ in r["failed"]),
                unblock="Nothing to type: the next daily run proposes again "
                        "with fresh drafts; the upload lane holds these slugs "
                        "until one passes, so no failing title can ship.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
