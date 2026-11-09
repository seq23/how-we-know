#!/usr/bin/env python3
"""THE TEACHING LANES' RULES (Neville Goddard, Florence Scovel Shinn), in code.

    python loop/teachings.py rights        # the rights record, one line per title

Her rulings 9 Nov 2026 ("build the neville lane", then Shinn in the rotating
slot): a teaching video is a guided whispered session BUILT ON a teacher's
techniques, never a straight reading of a book:

  1. a short plain explanation of the technique, in our own words;
  2. a few of the teacher's own lines, each naming its book;
  3. a long guided section to fall asleep in the wish fulfilled.

What this file refuses (loop/whisper_lane.script_problems calls it for the
kinds `neville` and `shinn`; loop/tests/test_teaching_lanes.py proves each
one negatively):

  QUOTE_UNCLEARED_TITLE  a quote from a title whose US copyright is not
                         recorded as gone (config/teacher_rights.json: a
                         renewal found, in copyright, a lecture, unchecked)
  QUOTE_NO_TITLE         a quote that names no book
  QUOTE_NOT_IN_RECORD    a quote that is not, word for word, one of the
                         verified lines recorded for its title
  QUOTE_COUNT / TOO_MUCH_QUOTED
                         fewer than 2 or more than 4 quotes; more than
                         MAX_QUOTED_WORDS of his or her words in one video
  BOOK_READ              the teacher's book text outside a marked quote
                         (sampled eight-word runs, config/teacher_shingles.txt)
  SHAPE / NOT_DISTINCT_STRUCTURE
                         the parts are not in the declared shape, or the
                         shape and scene repeat a recent teaching script
  plus the brand guardrail (no guaranteed outcome, no income or health claim)
  and the plain-words check, on every spoken line.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import whisper_words as W                                   # noqa: E402

RIGHTS = ROOT / "config" / "teacher_rights.json"
SHINGLES = ROOT / "config" / "teacher_shingles.txt"
KINDS = ("neville", "shinn")
MAX_QUOTES, MIN_QUOTES = 4, 2
MAX_QUOTED_WORDS = 120
BOOK_HITS_MAX = 1          # sampled eight-word runs of book text allowed outside quotes
SAMPLE_MOD = 8             # one eight-word run in eight is kept in the shingle file
RECENT = 12                # a shape + scene may not repeat within the last 12 teaching scripts
QUOTE_RX = re.compile(r"^(?P<lead>[^“”\"]*)[“\"](?P<q>.+)[”\"]\s*$")


def rights() -> dict:
    return json.loads(RIGHTS.read_text())


def tokens(text: str) -> list[str]:
    """Words, lowercased, letters only: OCR line-break hyphens and dashes
    never decide whether a line matches its book."""
    text = re.sub(r"(\w)[-­]\s+(\w)", r"\1\2", text)
    return [t for t in (re.sub(r"[^a-z]", "", w.lower()) for w in W.WORD.findall(text)) if t]


def run_hash(run: list[str]) -> str:
    return hashlib.blake2b(" ".join(run).encode(), digest_size=4).hexdigest()


def sampled_runs(text: str) -> set[str]:
    t = tokens(text)
    out = set()
    for i in range(max(0, len(t) - 7)):
        h = run_hash(t[i:i + 8])
        if int(h, 16) % SAMPLE_MOD == 0:
            out.add(h)
    return out


_BOOK: set[str] | None = None


def book_runs() -> set[str]:
    global _BOOK
    if _BOOK is None:
        _BOOK = {x.strip() for x in SHINGLES.read_text().splitlines()
                 if x.strip() and not x.startswith("#")} if SHINGLES.exists() else set()
    return _BOOK


def book_hits(text: str) -> int:
    return len(sampled_runs(text) & book_runs())


def quotable(r: dict | None = None) -> dict[str, dict]:
    r = r or rights()
    ok = set(r["quotable_statuses"])
    return {k: v for k, v in r["titles"].items() if v.get("status") in ok}


def _title_in(lead: str, r: dict) -> str | None:
    low = lead.lower()
    best = None
    for k, v in r["titles"].items():
        for name in (v["title"], v.get("spoken_title", "")):
            if name and name.lower() in low and (best is None or len(name) > best[1]):
                best = (k, len(name))
    return best[0] if best else None


def quote_problems(para: str, teacher: str, r: dict | None = None) -> tuple[list[str], int]:
    """One quote paragraph: `<lead naming the book> “<the line>”`.
    Returns (problems, words quoted)."""
    r = r or rights()
    m = QUOTE_RX.match(para.strip())
    if not m:
        return [f"QUOTE_FORMAT not a quote paragraph (a lead naming the book, then the line in quotes): {para[:60]!r}"], 0
    lead, q = m.group("lead"), m.group("q")
    n = len(tokens(q))
    if len(tokens(lead)) > 16:
        return [f"QUOTE_LEAD_TOO_LONG {len(tokens(lead))} words before the quote: {lead[:60]!r}"], n
    title = _title_in(lead, r)
    if title is None:
        return [f"QUOTE_NO_TITLE the quote names no book: {para[:60]!r}"], n
    t = r["titles"][title]
    if t.get("teacher") != teacher:
        return [f"QUOTE_WRONG_TEACHER {t['title']!r} is not by this script's teacher"], n
    if title not in quotable(r):
        return [f"QUOTE_UNCLEARED_TITLE {t['title']!r} is {t.get('status', 'unchecked')} "
                f"(only titles whose US copyright is recorded as gone may be quoted)"], n
    if tokens(q) not in [tokens(x["text"]) for x in r["quotes"] if x["title"] == title]:
        return [f"QUOTE_NOT_IN_RECORD not a verified line of {t['title']!r}: {q[:60]!r}"], n
    return [], n


def shape_of(p: dict) -> list[str]:
    return [re.sub(r"-\d+$", "", s["source"]) for s in p["segments"]]


def signature(p: dict) -> tuple[str, str]:
    return (p["meta"].get("shape", ""), p["meta"].get("scene", ""))


def teaching_problems(p: dict, others: list[dict], c: dict) -> list[str]:
    """Every teaching-lane rule on a parsed script (see the module doc)."""
    import whisper_lane as WL                               # noqa: PLC0415
    r = rights()
    out: list[str] = []
    teacher = p["kind"]
    tcfg = c["teachings"].get(teacher)
    if tcfg is None:
        return [f"TEACHER {teacher!r} is not configured"]
    topic = p["meta"].get("technique", "")
    if topic not in tcfg["topics"]:
        out.append(f"TECHNIQUE {topic!r} is not one of {teacher}'s configured topics")
    shape = p["meta"].get("shape", "")
    want = c["teachings"]["shapes"].get(shape)
    if want is None:
        out.append(f"SHAPE {shape!r} is not a configured shape")
    elif shape_of(p) != want:
        out.append(f"SHAPE the parts are {shape_of(p)}, the shape {shape!r} is {want}")
    if p["meta"].get("scene", "") not in c["teachings"]["scenes"]:
        out.append(f"SCENE {p['meta'].get('scene', '')!r} is not a configured scene")
    nq, quoted, rest = 0, 0, []
    for s in p["segments"]:
        kind = re.sub(r"-\d+$", "", s["source"])
        for j, para in enumerate(s["paragraphs"]):
            if s is p["segments"][0] and j == 0 and WL._is_opening(para):
                rest.append(para)          # the spoken promise always opens segment 1
            elif kind == "quotes":
                probs, n = quote_problems(para, teacher, r)
                out += [f"segment {s['n']} (quotes): {x}" for x in probs]
                nq, quoted = nq + 1, quoted + n
            else:
                rest.append(para)
    if not MIN_QUOTES <= nq <= MAX_QUOTES:
        out.append(f"QUOTE_COUNT {nq} quotes (between {MIN_QUOTES} and {MAX_QUOTES})")
    if quoted > MAX_QUOTED_WORDS:
        out.append(f"TOO_MUCH_QUOTED {quoted} of the teacher's words (at most {MAX_QUOTED_WORDS}): "
                   f"a guided session built on the technique, never a reading")
    own = "\n\n".join(rest)
    if not book_runs():
        out.append("BOOK_RECORD_MISSING config/teacher_shingles.txt is empty: the straight-reading "
                   "check examined nothing (run loop/tools/teacher_texts.py)")
    hits = book_hits(own)
    if hits > BOOK_HITS_MAX:
        out.append(f"BOOK_READ {hits} sampled eight-word runs of the teacher's book text outside "
                   f"a marked quote: never a straight reading")
    names = " ".join([r["teachers"][teacher]["name"], r["teachers"][teacher]["spoken"]]
                     + [v["title"] + " " + v.get("spoken_title", "") for v in r["titles"].values()]
                     + [tcfg["topics"][topic]["name"] if topic in tcfg["topics"] else ""])
    names += " " + " ".join(f"{w}'s {w}’s" for w in names.split())
    for x in W.fact_problems(own, names):
        out.append(x.replace("is not in the source script", "is not the teacher, a book or the technique"))
    out += [f"{x}" for x in WL.affirmation_problems(own)]
    mine = signature(p)
    recent = sorted((o for o in others if o["kind"] in KINDS),
                    key=lambda o: o["meta"].get("written", ""), reverse=True)[:RECENT]
    for o in recent:
        if signature(o) == mine:
            out.append(f"NOT_DISTINCT_STRUCTURE shape {mine[0]!r} and scene {mine[1]!r} repeat "
                       f"{Path(o['path']).name}: every script differs in structure, not only topic")
            break
    return out


def credits(p: dict, r: dict | None = None) -> list[str]:
    """The description's rights lines: the teacher, the quoted books, no endorsement."""
    r = r or rights()
    t = r["teachers"][p["kind"]]
    books = []
    for s in p["segments"]:
        if re.sub(r"-\d+$", "", s["source"]) != "quotes":
            continue
        for para in s["paragraphs"]:
            m = QUOTE_RX.match(para.strip())
            k = _title_in(m.group("lead"), r) if m else None
            if k and k not in books:
                books.append(k)
    quoted = "; ".join(f"{r['titles'][k]['title']} ({r['titles'][k]['published']})" for k in books)
    out = [t["credit_line"]]
    if quoted:
        out.append(f"Quoted from: {quoted}, public domain in the US.")
    out.append(r["not_affiliated_line"])
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["rights"]:
        r = rights()
        ok = quotable(r)
        for k, v in r["titles"].items():
            nq = sum(1 for q in r["quotes"] if q["title"] == k)
            print(f"{v['teacher']:8} {v['title'][:48]:48} {str(v.get('published')):5} {v['status']:22} "
                  f"{'QUOTABLE' if k in ok else 'never quoted'} ({nq} lines)")
        print(f"OUTPUT {len(r['titles'])} titles, {len(ok)} quotable, {len(r['quotes'])} verified lines, "
              f"{len(book_runs())} sampled book runs")
        return 0 if r["titles"] and book_runs() else 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
