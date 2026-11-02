"""YouTube titles for NEW uploads: ONE plain question (owner, 2 Nov 2026).

CURRENT RULE: the title is the question alone - see one_question_problems()
and the 2026-11-02 DECISION-LOG entry. The 2026-10-08 history below explains
the statement-plus-promise titles it replaced; title_for() no longer makes them.

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

# ONE QUESTION PER VIDEO (owner, 2 Nov 2026, from the approved mock-up): the
# title is ONE plain question and nothing else - no "— and how we know"
# suffix, no second clause, no chapter statement. It binds every title path
# (Shorts rank 1 and 2+, long-form via loop/longform_title.py, the repackage
# and demand lanes that retitle through it). Older videos keep their titles:
# the rule binds uploads from QUESTION_START (the 25 Oct-2 Nov backfill,
# loop/tools/one_question_backfill.py, is the one retitle of live videos).
QUESTION_START = "2026-10-25"
QUESTION_WORDS = ("how", "why", "what", "which", "who", "where", "when", "is",
                  "are", "was", "were", "do", "does", "did", "can", "could",
                  "will", "would", "should", "has", "have")
QUESTION_MAX = 70          # what a phone shows; the owner's longest is 47

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


def one_question_problems(title: str) -> list[str]:
    """Everything that stops `title` being ONE plain question. [] = it is."""
    t = (title or "").strip()
    if not t:
        return ["title is empty"]
    p: list[str] = []
    if not t.endswith("?"):
        p.append("title is not a question - one plain question, ending '?'")
    if t.count("?") != 1:
        p.append("title asks more than one question")
    first = t.split()[0].lower().replace("\u2019", "'")
    if first.split("'")[0] not in QUESTION_WORDS:
        p.append(f"title starts with {t.split()[0]!r}: a plain question starts "
                 f"with a question word (How, Why, What, Is, Can ...)")
    if not t[0].isupper():
        p.append("title does not start with a capital")
    if re.search(r"\s[\u2014\u2013-]\s|:|;|\.\s|!", t):
        p.append("title has a second clause (a dash, colon, semicolon or "
                 "second sentence) - the question alone")
    if re.search(r"\band how we know\b|here's how we know", t, re.I):
        p.append("title carries the 'and how we know' suffix - the question alone")
    if re.search(r",?\s+(?:and|or|but)\s+(?:how|why|what|where|when|which|who|"
                 r"is|are|does|do|can)\b", t, re.I):
        p.append("title joins two questions - ask the strongest one")
    if len(t) > QUESTION_MAX:
        p.append(f"title is {len(t)} characters, over {QUESTION_MAX}")
    return p


_CONTRACT = {"does not": "doesn't", "do not": "don't", "is not": "isn't",
             "are not": "aren't", "can not": "can't", "cannot": "can't"}


_AUX = {"is", "are", "was", "were", "do", "does", "did", "can", "could", "will",
        "would", "should", "has", "have", "had", "doesn't", "don't", "isn't",
        "aren't", "can't", "didn't"}


def _grammar(q: str) -> str:
    """A search query is often a statement behind a question word ("why deep
    sea creatures look so weird"). Make it a question with the query's own
    words: a trailing is/are moves up ("why many deep sea creatures are red"
    -> "why are many deep sea creatures red"); otherwise why/how/where/when
    with no auxiliary in its first three words takes "do" ("how deep sea
    creatures survive the pressure" -> "how do deep sea creatures survive the
    pressure"). What/which/who questions ask about their subject and keep
    their order."""
    w = q.split(" ")
    if len(w) < 3 or w[0].lower() not in ("why", "how", "where", "when"):
        return q
    if any(x.lower() in _AUX for x in w[1:4]):
        return q
    low = [x.lower() for x in w]
    for aux in ("is", "are"):
        if aux in low[2:]:
            i = low.index(aux, 2)
            return " ".join([w[0], aux] + w[1:i] + w[i + 1:])
    return " ".join([w[0], "do"] + w[1:])


def as_question(question: str) -> str:
    """The search query as one plain question: sentence case, proper nouns,
    the query's own words, '?' - "why does rice get sticky" ->
    "Why does rice get sticky?". Adds nothing the query does not say beyond
    the auxiliary a question needs (_grammar)."""
    q = re.sub(r"\s+", " ", (question or "").strip().rstrip("?").strip())
    for k, v in _CONTRACT.items():
        q = re.sub(rf"\b{k}\b", v, q, flags=re.I)
    q = _grammar(q)
    return _sentence(q) + "?" if q else ""


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
    p += [x for x in one_question_problems(t) if x != "title is empty"]
    if "<" in t or ">" in t:
        p.append("title contains < or >, which YouTube rejects")
    low = t.lower()
    for b in BANNED:
        if b in low:
            p.append(f"title uses banned clickbait wording {b!r}")
    if any(len(w) > 3 and w.isupper() and w.isalpha() for w in t.split()):
        p.append("title shouts a word in capitals")
    have = {_stem(w) for w in _norm(t).split()}
    # A compilation's strongest single question (strongest_questions) answers
    # PART of its query by rule (owner, 2 Nov 2026): it keeps its own words.
    q_eff = t if t in strongest_questions(question) else question
    missing = [w for w in content_words(q_eff) if _stem(w) not in have]
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
    """The title a NEW upload gets: ONE plain question. The script's own
    `## YouTube title` when it passes title_problems, else the query itself as
    a question (as_question). Never raises."""
    proposed = script_title(script_text)
    if proposed and not title_problems(proposed, question, script_text):
        return proposed
    plain = as_question(question)
    if not one_question_problems(plain):
        return plain
    for cand in strongest_questions(question):
        if not one_question_problems(cand):
            return cand
    return plain


_SUBORDINATE = r"\s+(?:when|while|if|because|after|before|even though|although)\s+"
_QWORD = r"\s+(?=(?:what|why|how|where|which|who)\s)"


def strongest_questions(question: str) -> list[str]:
    """Shorter single questions from a query too long or compound to be one:
    a compilation's first question (its queue title's first comma clause, or
    the query cut where a second question word starts), then the question
    without its trailing subordinate clause ("... the deep ocean when we've
    explored so little of it" -> "... the deep ocean?"). Only the query's own
    words, in their order."""
    q = re.sub(r"\s+", " ", (question or "").strip().rstrip("?")).strip()
    out: list[str] = []
    try:
        import batch_queue                                 # noqa: PLC0415
        for e in batch_queue.queued_entries():
            if e.get("query") == q and "," in (e.get("title") or ""):
                out.append(as_question(e["title"].split(",")[0]))
    except Exception:                                      # noqa: BLE001
        pass
    if "," in q:                          # a compilation's own "A, B and C?"
        out.append(as_question(q.split(",")[0]))
    parts = re.split(_QWORD, q, flags=re.I)
    if len(parts) > 1:
        out.append(as_question(parts[0]))
    for base in [q] + ([parts[0]] if len(parts) > 1 else []):
        cut = re.split(_SUBORDINATE, base, maxsplit=1, flags=re.I)
        if len(cut) > 1 and len(cut[0].split()) >= 3:
            out.append(as_question(cut[0]))
    return out


def _subject(base: str) -> str:
    """The subject half of an episode title: the part before its promise."""
    s = re.sub(r"\?\s*Here's how we know$", "", base.strip())
    s = re.split(r"\s+[—–]\s+", s)[0]
    s = re.sub(rf"\s*[—–-]?\s*{PROMISE}.*$", "", s, flags=re.I)
    return s.strip().rstrip("?:.,; ")


def _chapter_phrase(chapter: str) -> str:
    c = re.sub(r"\s+", " ", (chapter or "").strip()).rstrip(".?:;,")
    c = re.sub(r"\s*:\s*", " — ", c)          # one colon per title: ours
    first = c.split(" ", 1)[0] if c else ""
    keep = (first.lower() in PROPER or any(c.lower().startswith(k)
                                           for k in PROPER_PHRASES)
            or first[1:2].isupper() or first == "I")
    return c if keep else c[:1].lower() + c[1:]


def chapter_title(question: str, chapter: str, script_text: str = "",
                  rank: int = 2) -> str:
    """The title of a rank 2+ cut: the single question ITS chapter answers.

    Owner rule, 2 Nov 2026 (supersedes the 2026-10-14 chapter statements such
    as "The deepest part of the ocean: what a depth number leaves out — and
    how we know"): a Short's title is the one question its cut answers. A
    chapter heading that is itself one plain question is that question;
    otherwise the cut answers the episode's question, and its title is that
    question (the cut still opens on its own chapter - visuals/shorts.py -
    so it is not a repeat of rank 1's picture)."""
    ch = re.sub(r"\s+", " ", (chapter or "").strip())
    if ch and not one_question_problems(ch):
        return _cap_proper(ch)
    return title_for(question, script_text)


def title_for_cut(question: str, script_text: str = "", rank: int = 1,
                  chapter: str | None = None) -> str:
    """The title for cut `rank` of an episode. Rank 1 is `title_for`, unchanged;
    rank 2+ must name its chapter (`chapter_title`) - a rank 2+ cut with no
    chapter is refused rather than given the rank-1 title again."""
    if rank <= 1:
        return title_for(question, script_text)
    if not (chapter or "").strip():
        raise ValueError(f"cut {rank} has no chapter heading; it would be "
                         f"titled exactly like cut 1")
    return chapter_title(question, chapter, script_text, rank)


if __name__ == "__main__":
    for q in sys.argv[1:]:
        print(title_for(q))
