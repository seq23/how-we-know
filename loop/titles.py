"""YouTube titles for NEW uploads: curiosity-led, specific, still on-search.

    .venv/bin/python loop/titles.py "what is the midnight zone"   # print one

WHY THIS EXISTS. Owner-approved build, 2026-10-08. The channel audit (25
subscribers, 58 videos) found every title was the bare search query with a
question mark — "How strong is graphene?" — which matches search but gives a
scroller no reason to stop. The Shorts that did travel were deep-sea
("What is the midnight zone?", 1,110 views) and they travelled on the subject,
not the phrasing. So a title now leads with the thing and the channel's own
promise — "The midnight zone — and how we know" — and keeps EVERY content word
of the query, so it still matches the search it was ranked for.

WHERE A TITLE COMES FROM, in order:
  1. The script's own `## YouTube title` section (loop/author.py asks the
     drafting model for one), used ONLY if `title_problems()` finds nothing
     wrong with it: every content word of the query present, every number in
     it present in the script, no clickbait vocabulary, not a bare question,
     within the length cap.
  2. Otherwise a rule-based rewrite of the query (`from_question`). The rule
     set only re-orders the query's own words and adds the channel's promise;
     it can never introduce a figure or a claim the script does not make.

WHAT THIS DOES NOT TOUCH. Published videos keep their titles — nothing here
calls videos.update. The site's question records (site/content/questions.json)
keep the exact query as their H1; that is the search contract the site's
validate-video-contract.mjs holds, and it is unchanged.

Guarded by loop/tests/test_titles_descriptions_topic_mix.py, which fails if a
generated title drops a query word, ends in a bare "?", invents a number, or
uses a banned word.
"""
from __future__ import annotations

import re
import sys

TITLE_MAX = 100            # YouTube's hard limit (loop/upload.py TITLE_MAX)
TITLE_SOFT_MAX = 70        # what a phone shows before truncating
PROMISE = "and how we know"

# Words that carry no search meaning. A title must keep every query word that
# is NOT in here.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "can",
    "how", "what", "why", "when", "where", "which", "who", "of", "in", "on",
    "to", "so", "it", "its", "be", "go", "get", "gets", "there", "about",
    "when", "we", "you", "there", "much", "many", "some", "if", "that",
    "than", "this", "these", "those", "and", "or", "for", "from", "by",
    "at", "as", "into", "up", "made", "make", "really",
}

# Clickbait vocabulary the channel's evidence-first voice never uses. Kept as
# a list so the test can prove each one is refused.
BANNED = ("you won't believe", "shocking", "insane", "mind-blowing",
          "mind blowing", "jaw-dropping", "gone wrong", "secret they",
          "nobody tells you", "!!")

# Proper nouns the lowercase search queries flatten. Multi-word names first.
PROPER_PHRASES = {"challenger deep": "Challenger Deep",
                  "mariana trench": "Mariana Trench"}
PROPER = {
    "mariana": "Mariana", "challenger": "Challenger", "damascus": "Damascus",
    "kevlar": "Kevlar", "izu-ogasawara": "Izu-Ogasawara", "earth": "Earth",
    "pacific": "Pacific", "3d": "3D", "atlantic": "Atlantic", "titanic": "Titanic",
}

_ADJ = r"(strong|hot|big|deep|old|fast|cold|hard|heavy|long|far|high|small|dark)"


def _norm(s: str) -> str:
    s = (s or "").lower().replace("\u2019", "'").replace("n't", " not")
    return re.sub(r"[^a-z0-9 ]+", " ", s.replace("-", " "))


def _stem(w: str) -> str:
    for suf in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_words(question: str) -> list[str]:
    return [w for w in _norm(question).split() if w not in STOPWORDS]


def _cap_proper(s: str) -> str:
    for k, v in PROPER_PHRASES.items():
        s = re.sub(rf"\b{k}\b", v, s, flags=re.I)
    out = []
    for w in s.split(" "):
        out.append(PROPER.get(w.lower(), w) if w.lower() in PROPER else w)
    return " ".join(out)


def _sentence(s: str) -> str:
    s = _cap_proper(s.strip())
    return s[:1].upper() + s[1:] if s else s


def from_question(question: str) -> str:
    """Rule-based curiosity title from the query's own words.

    Statement, not question; the subject first; the channel's promise last.
    """
    q = re.sub(r"\s+", " ", (question or "").strip().rstrip("?").strip()).lower()
    m = None
    rules = [
        # what is X made of -> What X is really made of — and how we know
        (r"^what (is|are) (.+?) made of$",
         lambda m: f"What {m[2]} {m[1]} really made of — {PROMISE}"),
        # what is a/an X -> Meet the X — and how we know what it is
        (r"^what is (?:a|an) (.+)$",
         lambda m: f"Meet the {m[1]} — {PROMISE} what it is"),
        # what is the X -> The X — and how we know
        (r"^what (?:is|are) the (.+)$",
         lambda m: f"The {m[1]} — {PROMISE}"),
        # what happens when X -> What really happens when X — and how we know
        (r"^what happens (when|if|to) (.+)$",
         lambda m: f"What really happens {m[1]} {m[2]} — {PROMISE}"),
        # what lives / what creatures live in X
        (r"^what (\w+ )?(lives?) in (.+)$",
         lambda m: f"What {m[1] or ''}really {m[2]} in {m[3]} — {PROMISE}"),
        # what is X (no article)
        (r"^what (?:is|are) (.+)$",
         lambda m: f"{m[1]} — {PROMISE}"),
        # how ADJ is/are X
        (rf"^how {_ADJ} (is|are) (.+)$",
         lambda m: f"How {m[1]} {m[3]} really {m[2]} — {PROMISE}"),
        # how ADJ can X go/get/dive
        (rf"^how {_ADJ} can (.+?) (go|get|dive|swim|grow)$",
         lambda m: f"How {m[1]} {m[2]} can really {m[3]} — {PROMISE}"),
        # how ADJ does X get
        (rf"^how {_ADJ} does (.+?) (get|go|grow)$",
         lambda m: f"How {m[1]} {m[2]} really {m[3]}s — {PROMISE}"),
        # how is/are X made/designed/formed
        (r"^how (is|are) (.+?) (made|designed|formed|built|tested)$",
         lambda m: f"How {m[2]} {m[1]} really {m[3]} — {PROMISE}"),
        # how do scientists know X -> How scientists know X (already the promise)
        (r"^how do scientists know (.+)$",
         lambda m: f"How scientists know {m[1]}"),
        # how do/does X work
        (r"^how (do|does) (.+?) work(?: in (.+))?$",
         lambda m: (f"How {m[2]} really work{'s' if m[1] == 'does' else ''}"
                    + (f" in {m[3]}" if m[3] else "") + f" — {PROMISE}")),
        # how do/does X VERB Y -> How X VERB(s) Y
        (r"^how (do|does) (.+?) (reach|harden|shatter|form|glow|survive|stay|"
         r"breathe|see|find|eat|move|live|sink|float|make|measure) ?(.*)$",
         lambda m: (f"How {m[2]} {m[3]}{'s' if m[1] == 'does' else ''}"
                    + (f" {m[4]}" if m[4] else "") + f" — {PROMISE}")),
        # why is/are X so Y
        (r"^why (is|are) (.+?) so (\w+)$",
         lambda m: f"Why {m[2]} {m[1]} so {m[3]} — {PROMISE}"),
        # why does X not Y
        (r"^why (?:does|do) (.+?) not (\w+)$",
         lambda m: f"Why {m[1]} doesn't {m[2]} — {PROMISE}"),
        # why X (already a statement)
        (r"^why (.+)$",
         lambda m: f"Why {m[1]} — {PROMISE}"),
        # yes/no: is/does/can X ... -> keep the question, add the promise
        (r"^(is|are|does|do|can|will) (.+)$",
         lambda m: f"{m[1]} {m[2]}? Here's how we know"),
    ]
    for pat, fmt in rules:
        m = re.match(pat, q)
        if m:
            t = fmt(m)
            break
    else:
        t = f"{q} — {PROMISE}"
    t = re.sub(r"\s+", " ", t).strip()
    t = _sentence(t)
    if len(t) > TITLE_MAX:
        # Drop the promise before ever dropping a search word.
        t = _sentence(q)[:TITLE_MAX]
    return t


def script_title(script_text: str) -> str | None:
    """The `## YouTube title` line a drafted script proposes, if any."""
    m = re.search(r"^## YouTube title\s*\n+(.+?)\s*$", script_text or "", re.M)
    if not m:
        return None
    t = m.group(1).strip().strip('"').strip()
    return t or None


def _numbers(s: str) -> list[str]:
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s or "")]


def title_problems(title: str, question: str, script_text: str = "") -> list[str]:
    """Everything wrong with `title` as a NEW upload's title. Empty = usable."""
    p: list[str] = []
    t = (title or "").strip()
    if not t:
        return ["title is empty"]
    if len(t) > TITLE_MAX:
        p.append(f"title is {len(t)} chars, over YouTube's {TITLE_MAX}")
    if t.endswith("?"):
        p.append("title is a bare question — lead with the subject instead")
    if "<" in t or ">" in t:
        p.append("title contains < or >, which YouTube rejects")
    low = t.lower()
    for b in BANNED:
        if b in low:
            p.append(f"title uses banned clickbait wording {b!r}")
    if any(len(w) > 3 and w.isupper() and w.isalpha() for w in t.split()):
        p.append("title shouts a word in capitals")
    have = {_stem(w) for w in _norm(t).split()}
    missing = [w for w in content_words(question) if _stem(w) not in have]
    if missing:
        p.append(f"title drops search word(s) {missing} from the query "
                 f"{question!r}, so it no longer matches the search it was "
                 f"ranked for")
    nums = _numbers(t)
    if nums:
        # A number the query itself carries ("3d printed") is the search
        # term, not a figure; anything else must be stated by the script.
        # The proposed-title section itself is not evidence for its own
        # numbers, so it is cut out before the script is searched.
        body = re.sub(r"^## YouTube title\s*\n.*?(?=^## |\Z)", "",
                      script_text or "", flags=re.M | re.S)
        src = set(_numbers(body)) | set(_numbers(question))
        bad = [n for n in nums if n not in src]
        if bad:
            p.append(f"title states {bad}, which the script never does — "
                     f"no invented figures")
    return p


def title_for(question: str, script_text: str = "") -> str:
    """The title a NEW upload gets. Never raises; always passes title_problems."""
    proposed = script_title(script_text)
    if proposed and not title_problems(proposed, question, script_text):
        return proposed
    t = from_question(question)
    if title_problems(t, question, script_text):
        # The rule-based rewrite failed its own check (an odd query shape).
        # Fall back to the query as a statement with the promise, which keeps
        # every word by construction.
        base = _sentence(re.sub(r"\s+", " ",
                                (question or "").strip().rstrip("?")))
        t = f"{base} — {PROMISE}"
        if len(t) > TITLE_MAX:
            t = base[:TITLE_MAX]
    return t


if __name__ == "__main__":
    for q in sys.argv[1:]:
        print(title_for(q))
