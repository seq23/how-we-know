"""The long-form DESCRIPTION template: a search block people actually type.

    python loop/describe.py prepare [--slugs a b] [--needed] [--limit N] [--dry-run]
    python loop/describe.py show <slug>

Owner instruction, 13 Oct 2026: every long-form description gets a search
block so the video comes up when someone types the question. One reusable
function (compose) builds it for every domain - the upload path
(loop/upload.py build_payload) and `repackage apply` both call it, and the
food lane calls it too; nothing domain-specific is hard-coded here.

THE TEMPLATE, plain sixth-grade words, in this order:
  1. first line: the long-form title (the owner's locked question) plus one
     sentence of answer - the Direct-answer lock's first sentence. This is
     what search and the "..." preview show.
  2. Chapters with timestamps (loop/upload.build_chapters: the real caption
     timing when captions/<slug>.chapters.txt exists), each named as the
     question it answers when a $0-route rewrite of the heading passed.
  3. "Questions this video answers": 4-8 phrasings people really type,
     pulled at $0 from YouTube/Google autocomplete (research/mine.suggest,
     the same endpoint the topic miner uses) for the episode's subject; only
     question-shaped completions that name the subject are kept; the
     episode's own title and question count as phrasings.
  4. one line on sources - "how we know" lives here, never in the title -
     and the source list;
  5. the existing affiliate block, channel line and hashtags.
Tags: the same phrasings plus the subject nouns, within YouTube's 500.

STATE, loop/state/descriptions.json per slug: {questions, chapter_names,
subject, prepared_at, model}. `prepare` fills it (network + the subscription
route in loop-repackage); compose() reads it and never calls the network.
A slug with fewer than MIN_QUESTIONS real phrasings is not composed - the
upload and apply paths hold it rather than ship a thin description.

Guarded by validator V60 (loop/validate.py) and loop/tests/test_describe.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

STATE = LOOP / "state" / "descriptions.json"
SCRIPTS = ROOT / "scripts"
MIN_QUESTIONS = 4
MAX_QUESTIONS = 8
TAGS_MAX = 500                  # YouTube's limit on the tags field, in chars
QUESTION_RE = re.compile(r"^(why|how|what|when|where|who|which|is|are|do|does|"
                         r"can|did|will|could)\b", re.I)
SOURCES_LINE = ("How we know: every figure in this video comes from a named "
                "public source, listed here.")
CHANNEL_LINE = ("Evidence-first explainers. Every on-screen number comes from "
                "a named public source stated in the narration.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or STATE).read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("episodes", {})
    return d


def save(doc: dict, path: Path | None = None) -> None:
    doc["updated"] = _now()
    p = path or STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


# ------------------------------------------------------------ the pieces
def subject_phrase(question: str) -> str:
    """The question's subject words, in the question's own order."""
    import longform_title as LT                            # noqa: PLC0415
    subj = LT.subject_words(question)
    words = [w for w in re.findall(r"[a-z0-9'-]+", (question or "").lower())
             if any(x in subj for x in w.split("-"))]
    return " ".join(dict.fromkeys(words))


def answer_sentence(script: str) -> str:
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)(?:\n\s*\n|\n## |\Z)", script, re.S)
    text = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    first = re.split(r"(?<=[.!?])\s+", text)[0] if text else ""
    return first


def _names_subject(q: str, subject: str) -> bool:
    import longform_title as LT                            # noqa: PLC0415
    want = {LT.stem(w) for w in re.split(r"[\s-]+", subject) if w}
    have = {LT.stem(w) for w in re.split(r"[\s-]+", q.lower()) if w}
    return bool(want & have)


# Never listed unless the script itself talks about it (food agent, 13 Oct
# 2026: "Is steak good for you?" came back for a video that never says).
OFF_LIMITS = {"health", "healthy", "healthier", "unhealthy", "good for you",
              "bad for you", "cancer", "calories", "calorie", "diet", "safe",
              "safe to eat", "price", "cost", "costs", "expensive", "cheap",
              "buy", "worth", "dangerous", "poisonous", "toxic", "nutrition"}


def answered(q: str, script: str) -> list[str]:
    """Why the script does NOT answer question `q` ([] = it does): every
    content word must be traceable to the Direct-answer lock, the narration
    or the sources (the title truth guard's own mechanism), and no
    health/medical/price angle the script never takes."""
    import longform_title as LT                            # noqa: PLC0415
    ev = LT.evidence_text(script)
    have = {LT.stem(w) for w in LT.content_words(ev)}
    p = [f"{w!r} is not in the script" for w in LT.content_words(q)
         if not LT._match(LT.stem(w), have)]               # noqa: SLF001
    low, evl = q.lower(), ev.lower()
    for term in OFF_LIMITS:
        if re.search(rf"\b{re.escape(term)}\b", low) and \
                not re.search(rf"\b{re.escape(term)}\b", evl):
            p.append(f"a {term!r} question the script never answers")
    return p


def search_questions(question: str, title: str, suggest=None,
                     pause: float = 0.3, script: str = "") -> list[str]:
    """4-8 question phrasings people type, from autocomplete. Real strings
    only (research/mine.py's rule); the title and question count."""
    import longform_title as LT                            # noqa: PLC0415
    if suggest is None:
        sys.path.insert(0, str(ROOT / "research"))
        import mine                                        # noqa: PLC0415
        suggest = mine.suggest
    subject = subject_phrase(question) or (question or "").lower()
    seeds = [question, title.rstrip("?").lower(), f"why {subject}",
             f"how {subject}", f"what {subject}", f"is {subject}",
             f"{subject} why", f"{subject} how"]
    found: list[str] = []
    for seed in dict.fromkeys(s for s in seeds if s and s.strip()):
        for s in suggest(seed) or []:
            s = re.sub(r"\s+", " ", str(s)).strip().lower()
            if (QUESTION_RE.match(s) and _names_subject(s, subject)
                    and not LT.BRAND_PHRASE.search(s) and len(s) <= 70
                    and s not in found
                    and (not script or not answered(s, script))):
                found.append(s)
        if pause:
            time.sleep(pause)
    out: list[str] = []
    for s in [title, question] + found:
        q = s.strip().rstrip("?").strip()
        if not q:
            continue
        q = q[0].upper() + q[1:] + "?"
        if q.lower() not in {x.lower() for x in out}:
            out.append(q)
        if len(out) >= MAX_QUESTIONS:
            break
    return out


CHAPTER_PROMPT = """Rewrite each chapter heading of a science video as the \
plain question that chapter answers. Sixth-grade words, at most 8 words, end \
with a question mark, no new facts, never the words "how we know". Same \
order, one per line, nothing else.

VIDEO TITLE: {title}

HEADINGS:
{headings}
"""


def _ask(messages: list[dict]) -> str:
    """One call on the repo's $0 route (subscription first). Tests replace it."""
    import author                                          # noqa: PLC0415
    resp = author.call_openrouter(messages, author.configured_model(),
                                  author.api_key() or "", timeout=120,
                                  temperature=0.3)
    return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def chapter_questions(title: str, labels: list[str]) -> dict[str, str]:
    """{heading: question} or {} when the rewrite does not pass."""
    import longform_title as LT                            # noqa: PLC0415
    if not labels:
        return {}
    try:
        text = _ask([{"role": "user", "content": CHAPTER_PROMPT.format(
            title=title, headings="\n".join(labels))}])
    except Exception:                                      # noqa: BLE001
        return {}
    lines = [re.sub(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+", "", ln).strip()
             for ln in text.splitlines() if ln.strip()]
    if len(lines) != len(labels):
        return {}
    for q in lines:
        if not q.endswith("?") or len(q) > 60 or LT.BRAND_PHRASE.search(q) \
                or len(q.split()) > 9:
            return {}
    return dict(zip(labels, lines))


def _split_chapter(line: str) -> tuple[str, str]:
    m = re.match(r"(\d{1,2}(?::\d{2}){1,2})\s+(.*)", line.strip())
    return (m.group(1), m.group(2).strip()) if m else ("", line.strip())


# ------------------------------------------------------------- compose
def compose(slug: str, script: str, title: str, question: str,
            chapters: list[str], sources: list[str], extra: list[str] | None = None,
            state: dict | None = None) -> tuple[str, list[str]] | None:
    """(description, tags) for one long-form video, or None when the slug
    has no prepared search block (the caller holds the slug)."""
    rec = (state if state is not None else load())["episodes"].get(slug) or {}
    qs = rec.get("questions") or []
    if len(qs) < MIN_QUESTIONS:
        return None
    names = rec.get("chapter_names") or {}
    first = f"{title.strip()} {answer_sentence(script)}".strip()
    parts = [first, ""]
    if chapters:
        parts.append("Chapters")
        for c in chapters:
            ts, label = _split_chapter(c)
            parts.append(f"{ts} {names.get(label, label)}".strip())
        parts.append("")
    parts.append("Questions this video answers:")
    parts += [f"• {q}" for q in qs]
    parts.append("")
    if sources:
        parts.append(SOURCES_LINE)
        parts += [f"• {s}" for s in sources]
        parts.append("")
    for block in extra or []:
        if block:
            parts += [block, ""]
    parts.append(CHANNEL_LINE)
    description = "\n".join(parts)
    subj = [w for w in (rec.get("subject") or subject_phrase(question)).split() if w]
    tags: list[str] = []
    for t in [q.rstrip("?").lower() for q in qs] + subj:
        if t and t not in tags:
            cand = tags + [t]
            # YouTube counts a tag with spaces as wrapped in quotes.
            size = sum(len(x) + (2 if " " in x else 0) for x in cand) + len(cand) - 1
            if size <= TAGS_MAX:
                tags = cand
    return description, tags


def problems(description: str, title: str, question: str,
             chapters_ref: list[str] | None = None, script: str = "") -> list[str]:
    """V60's check on one composed description. [] = it holds."""
    import longform_title as LT                            # noqa: PLC0415
    p: list[str] = []
    block = description.split("Questions this video answers:", 1)
    qs = [ln[1:].strip() for ln in (block[1].split("\n\n", 1)[0].splitlines()
                                    if len(block) > 1 else [])
          if ln.startswith("•") and ln.strip().endswith("?")]
    if script:
        for q_ in qs:
            why = answered(q_, script)
            if why:
                p.append(f"lists {q_!r}, which the script does not answer: {why[0]}")
    if len(qs) < MIN_QUESTIONS:
        p.append(f"{len(qs)} question phrasing(s); the search block needs "
                 f">= {MIN_QUESTIONS}")
    subj = LT.subject_words(question)
    low = {LT.stem(w) for w in re.findall(r"[a-z0-9]+", description.lower())}
    if subj and not (low & {LT.stem(w) for w in subj}):
        p.append(f"the description never names the subject ({', '.join(sorted(subj))})")
    if not description.startswith(title.strip()):
        p.append("the first line is not the title")
    ch = re.findall(r"^(\d{1,2}(?::\d{2}){1,2}) ", description, re.M)
    if not ch or ch[0] not in ("0:00", "00:00"):
        p.append("no chapters starting at 0:00")
    if chapters_ref:
        ref = [_split_chapter(c)[0] for c in chapters_ref]
        if ch != ref:
            p.append(f"chapter timestamps {ch} do not match the render's "
                     f"{ref}")
    return p


# ------------------------------------------------------------- prepare
def _question_and_title(slug: str, text: str) -> tuple[str, str]:
    import longform_title as LT                            # noqa: PLC0415
    q = LT._question_for(slug, text)                       # noqa: SLF001
    t, _w, _s = LT.title_for_upload(slug, text, q)
    return q, t or ""


def prepare(slugs: list[str], dry_run: bool = False, suggest=None,
            doc: dict | None = None) -> dict:
    import upload                                          # noqa: PLC0415
    d = doc if doc is not None else load()
    made, held = [], []
    for slug in slugs:
        sp = SCRIPTS / f"{slug}.md"
        if not sp.exists():
            held.append((slug, "no script"))
            continue
        text = sp.read_text(encoding="utf-8")
        q, title = _question_and_title(slug, text)
        if not title:
            held.append((slug, "no passing long-form title yet"))
            continue
        if dry_run:
            made.append(slug)
            continue
        qs = search_questions(q, title, suggest=suggest, script=text)
        labels = [_split_chapter(c)[1] for c in upload.build_chapters(slug, text)]
        names = chapter_questions(title, labels)
        d["episodes"][slug] = {"questions": qs, "chapter_names": names,
                               "subject": subject_phrase(q), "title": title,
                               "prepared_at": _now()}
        (made if len(qs) >= MIN_QUESTIONS else held).append(
            slug if len(qs) >= MIN_QUESTIONS else (slug, f"{len(qs)} phrasings"))
    if not dry_run and doc is None:
        save(d)
    return {"made": made, "held": held}


def needed(doc: dict | None = None) -> list[str]:
    """Live long-form videos and queued scripts with no prepared block, or a
    block prepared for a different title than today's."""
    import ledger                                          # noqa: PLC0415
    import longform_title as LT                            # noqa: PLC0415
    d = doc if doc is not None else load()
    out = []
    live = [r["slug"] for r in ledger.load()["published"]
            if r.get("video_id") and not r.get("retired_at")]
    queued = sorted(p.stem for p in SCRIPTS.glob("*.md"))
    for slug in dict.fromkeys(live + queued):
        sp = SCRIPTS / f"{slug}.md"
        if not sp.exists():
            continue
        text = sp.read_text(encoding="utf-8")
        _q, title = _question_and_title(slug, text)
        rec = d["episodes"].get(slug) or {}
        if title and (len(rec.get("questions") or []) < MIN_QUESTIONS
                      or rec.get("title") != title):
            out.append(slug)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare")
    pr.add_argument("--slugs", nargs="*")
    pr.add_argument("--needed", action="store_true")
    pr.add_argument("--limit", type=int, default=0)
    pr.add_argument("--dry-run", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("slug")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        import upload                                      # noqa: PLC0415
        text = (SCRIPTS / f"{a.slug}.md").read_text(encoding="utf-8")
        payload = upload.build_payload({"slug": a.slug,
                                        "question": _question_and_title(a.slug, text)[0],
                                        "script": f"scripts/{a.slug}.md"})
        print(payload["snippet"]["description"])
        print("TAGS:", payload["snippet"]["tags"])
        return 0
    slugs = a.slugs or needed()
    if a.limit:
        slugs = slugs[: a.limit]
    from common import Stage, week_id                      # noqa: PLC0415
    with Stage("describe", week_id(),
               zero_work_hint="Every long-form video already has a search block.") as st:
        if not slugs:
            st.named_stop("DESCRIPTIONS_UP_TO_DATE",
                          "every live long-form video and queued script with a "
                          "passing title already has a prepared search block",
                          unblock="Nothing to do; a new title is described the "
                                  "run after it passes.")
        r = prepare(slugs, dry_run=a.dry_run)
        for s in r["made"]:
            st.work(f"search block for {s}" + (" (dry run)" if a.dry_run else ""))
        for s, why in r["held"]:
            st.note(f"held {s}: {why}")
        if not r["made"]:
            st.named_stop("DESCRIPTIONS_HELD",
                          f"{len(r['held'])} slug(s) got no search block: "
                          + "; ".join(f"{s} ({w})" for s, w in r["held"])[:600],
                          held_items=sorted(s for s, _ in r["held"]),
                          unblock="Nothing to type: titles land first, then "
                                  "the next run describes them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
