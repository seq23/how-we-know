#!/usr/bin/env python3
"""THE WHISPER ALMANAC AUTHOR ($0, GitHub Actions; or by hand on the Mac).

    python loop/whisper_author.py              # top up: next sleep episode + this week's affirmations
    python loop/whisper_author.py sleep SLUG   # one planned episode (config/whisper_almanac.json)
    python loop/whisper_author.py affirmations [--theme THEME]
    python loop/whisper_author.py teaching neville|shinn [--topic TOPIC]

Sleep: every segment is ONE fact-checked How We Know script (uploaded by
that machine, loop/whisper_lane.fact_checked) rewritten for sleep by a free
model through loop/llm_router.py (Gemini free tier, then the curated $0
OpenRouter list, never paid). Each answer must pass the plain-words check
and the fact guards (loop/whisper_words.py: no new name, no new number) or
it is sent back with its named problems, up to ATTEMPTS times. Only a whole
episode that passes every rule (loop/whisper_lane.script_problems: length
2-3 h, distinct from every other script) is written to scripts/whisper/.

Affirmations: one script a week, money and love in turn, six movements;
every line passes the plain-words check and the brand guardrail (no
guaranteed outcome, no fake proof, no health claim).

Teaching (her rulings 9 Nov 2026: Neville Goddard, Florence Scovel Shinn):
a guided session BUILT ON a technique, never a reading. The explanation and
the guided parts are written by a free model from OUR OWN points (config
`teachings`), never from the book text; the teacher's lines are picked in
code from the verified, rights-cleared quotes (config/teacher_rights.json).
Each script takes a shape and a scene no recent teaching script used, so
every script differs in structure, not only topic (loop/teachings.py).

RUNWAY. Per lane with slots in the mix (config `lanes`; 9 Nov 2026: food,
ocean, neville, money; rotating paused) the
author keeps up to RUNWAY scripts waiting for voice, writing at most
MAX_WRITES a run; a full runway is the self-resolving stop
WHISPER_RUNWAY_FULL, never a green no-op. It runs DAILY (13 Nov 2026: the
mix is 5 videos a week and a weekly run left the Mac with nothing to voice),
and a script one lane's rules refuse never stops the other lanes' scripts.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import whisper_lane as WL                                   # noqa: E402
import whisper_words as W                                   # noqa: E402

ATTEMPTS = 4
RUNWAY = 2
MAX_WRITES = 4
CACHE_FILE = WL.WORK / "_segments.json"   # gitignored; one file, keyed by episode and part
STAGE = "whisper-author"

STYLE = """You rewrite a short, fact-checked science or history script into a WHISPERED SLEEP STORY segment.
The listener is in bed, drifting off. Write for the ear, slow and soft.

Rules you must follow exactly:
- Plain, everyday words. A child of twelve could follow every sentence.
- Keep a real name only when it IS the topic; say it once, softly, and explain it in plain words. After that, say "it", "this glow", "that galaxy", and so on.
- NO acronyms or initials (write "the space agency", not NASA). NO letters mixed with digits.
- When two names appear together, treat them the same: soften both ("space agencies in the United States and Europe") or keep both, never one of each.
- NO numerals at all. Say numbers in soft rounded words, as the source gives them: "about a thousand meters down", "more than a hundred years ago", "in the early nineteen hundreds". Never more than three number words in a row. Never convert a unit, never add a number the source does not give.
- NO unit abbreviations, percent signs, degree signs, equations, brackets or lists.
- No technical strings: never three long words close together.
- Never add a fact, a name, a place or a date that is not in the source. You may leave hard details out. You may slow down, repeat a gentle image, and describe calmly what the source says.
- Short sentences: at most 22 words each, most of them 8 to 14.
- Paragraphs of three to five sentences, separated by one blank line.
- Second person, warm and quiet ("you might picture..."), never excited, no questions that demand an answer, no exclamation marks.
- Begin with one soft line that eases in from the last segment (for example "Now, let your mind drift down a little further."). End with one settling line.
- Write only the segment text. No title, no headings, no notes."""


def _content(resp: dict) -> str:
    return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _complete(messages: list[dict], rejected: set[str]) -> tuple[str, str]:
    import llm_router as R                                  # noqa: PLC0415
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    resp = R.complete(messages, key, temperature=0.6, timeout=240, rejected=rejected)
    return _content(resp).strip(), resp.get("model_used", "")


def clean(text: str) -> list[str]:
    """Model text -> paragraphs; drops headings, markdown and stray quotes."""
    text = re.sub(r"[*_#>`]", "", text)
    paras = [re.sub(r"\s+", " ", p).strip().strip('"“”') for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if len(W.WORD.findall(p)) >= 6]


def target_words(n_segments: int, c: dict, source_words: int | None = None) -> int:
    """Words per segment: about the source's own length (a rewrite, not an
    expansion), but never short of a 2 h 05 min episode or past 2 h 50."""
    v, wpm = c["voice"], float(c["pacing"]["speech_wpm"])
    per_word = 60 / wpm + v["pause_sentence_s"] / 11 + v["pause_paragraph_s"] / 50
    seg = n_segments * v["pause_segment_s"]
    hi = (10200.0 - seg) / per_word
    # about the source's own length: a rewrite, never an expansion; the
    # episode reaches its length with its pause scale (whisper_lane)
    total = min(float(source_words or hi), hi)
    return int(total / n_segments)


def segment_problems(paras: list[str], source: str, named: list[str], want: int,
                     c: dict) -> list[str]:
    text = "\n\n".join(paras)
    probs = W.text_problems(text, named) + W.fact_problems(text, WL.source_narration(source))
    for s in WL.sentences(text):
        n = len(W.WORD.findall(s))
        if n > c["pacing"]["max_sentence_words"]:
            probs.append(f"LONG_SENTENCE {n} words: {s[:50]!r}")
    n = len(W.WORD.findall(text))
    if not 0.75 * want <= n <= 1.6 * want:
        probs.append(f"LENGTH {n} words; write {want} words (between {int(.8*want)} and {int(1.5*want)})")
    return probs


def write_segment(source: str, named: list[str], want: int, c: dict,
                  episode: str, idx: int, frame: str = "") -> tuple[list[str], str]:
    key = f"{episode}/{idx:02d}-{source}"
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    rec = cache.get(key)
    if rec is None:                      # the per-file cache of 6 Nov 2026
        old = WL.WORK / "_segments" / episode / f"{idx:02d}-{source}.json"
        rec = json.loads(old.read_text()) if old.exists() else None
    if rec and not segment_problems(rec["paragraphs"], source, named, want, c):
        return rec["paragraphs"], rec["model"]
    src = WL.source_narration(source)
    keep = ", ".join(named) or "none"
    base = [{"role": "system", "content": STYLE},
            {"role": "user", "content":
             f"Topic names you may keep (each said once, then plain words): {keep}.\n"
             + (f"{frame}\n" if frame else "")
             + f"Write about {want} words.\n\nSOURCE SCRIPT (fact-checked):\n\n{src}"}]
    msgs, rejected, last = list(base), set(), []
    for _ in range(ATTEMPTS):
        try:
            text, model = _complete(msgs, rejected)
        except Exception as e:                              # noqa: BLE001
            # every free model already failed THIS segment once: the roster is
            # small, so start again with all of them rather than stopping
            if not rejected or getattr(e, "code", "") != "OPENROUTER_NO_FREE_MODEL":
                raise
            rejected.clear()
            text, model = _complete(msgs, rejected)
        paras = clean(text)
        last = segment_problems(paras, source, named, want, c) if paras else ["EMPTY answer"]
        if not last:
            cache[key] = {"paragraphs": paras, "model": model}
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(cache, indent=1))
            return paras, model
        # the router never asks a model that failed this segment again
        # (llm_router.complete `rejected`): a rate-limited day otherwise
        # sends every retry to the same weakest model that answered
        if model:
            rejected.add(model)
        msgs = base + [{"role": "assistant", "content": text},
                       {"role": "user", "content":
                        "Rewrite the whole segment. It broke these rules:\n- "
                        + "\n- ".join(last[:15])
                        + "\nFix every one. Keep everything else. Write only the segment text."}]
    raise WL_SegmentRefused(source, last)


class WL_SegmentRefused(Exception):
    def __init__(self, source: str, problems: list[str]):
        super().__init__(f"{source}: {problems[:3]}")
        self.source, self.problems = source, problems


def author_sleep(e: dict, c: dict) -> Path:
    want = target_words(len(e["sources"]), c,
                        sum(len(WL.source_narration(x).split()) for x in e["sources"]))
    segs, models = [], set()
    # her decision 9 Nov 2026: food told as history, ocean as a documentary of a place
    frame = c["lanes"].get(e.get("lane") or "", {}).get("frame", "")
    for i, src in enumerate(e["sources"], 1):
        paras, model = write_segment(src, e["named"], want, c, e["slug"], i, frame)
        segs.append((src, paras))
        models.add(model)
        print(f"  segment {i}/{len(e['sources'])} {src}: {sum(len(p.split()) for p in paras)} words ({model})", flush=True)
    title = e["hook"].split(":")[0]
    out = WL.SCRIPTS / f"{e['slug']}.md"
    text = WL.render_script(e["slug"], "sleep", title, e["sources"], e["named"], segs,
                            {"Topic": e["topic"], "Models": ", ".join(sorted(models))})
    return _commit(out, text)


def _commit(out: Path, text: str) -> Path:
    """Write only a script that passes every rule; a refused one is not kept."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".md.tmp")
    tmp.write_text(text)
    kind = WL.parse(tmp)["kind"]
    scale = WL.fit_pause_scale(WL.parse(tmp), goal_s=float(WL.cfg()["lengths"][kind].get("goal_s", 7500)))
    text = text.replace("**Written:**", f"**Pause scale:** {scale}\n**Written:**", 1)
    text = WL.add_opening(text, out.stem)                    # the promise names the real length
    est = WL.estimate_seconds(WL.parse(tmp) | {"meta": {**WL.parse(tmp)["meta"], "pause scale": str(scale)}})
    text = re.sub(r"\*\*Estimated length:\*\* [^(]*", f"**Estimated length:** {WL.fmt_len(est)} ", text, 1)
    tmp.write_text(text)
    others = [p for p in WL.all_scripts() if p.resolve() != out.resolve()]
    probs = WL.script_problems(tmp, others=others)
    if probs:
        tmp.unlink()
        raise WL_SegmentRefused(out.stem, probs)
    tmp.replace(out)
    return out


AFFIRM_STYLE = """You write whispered sleep affirmations, one short line at a time.
Rules you must follow exactly:
- Each line is one calm sentence of 4 to 14 everyday words, in the first person ("I...") or second person ("You..."). The listener is a woman.
- Present tense, gentle, believable. Feelings, choices, safety, rest, openness.
- NEVER promise an outcome: no amounts, no money figures, no dates, no "by tomorrow", no "fast", no "will make you rich", no "will text you", no specific person or ex. Affirm who she is and how she feels ("I am a woman who builds wealth"), never what will happen.
- NEVER mention health, healing, cures, illness or medicine. No proof, results or screenshots.
- No numerals, acronyms, brackets, lists, emojis or exclamation marks.
- Every line different from every other line. No line repeated with small changes.
- Output only the lines, one per line, nothing else."""


def author_affirmations(theme: str, c: dict) -> Path:
    a = c["affirmations"]
    week = _dt.date.today().isocalendar()
    slug = f"affirmations-{theme}-{week[0]}-w{week[1]:02d}"
    n = 2
    while (WL.SCRIPTS / f"{slug}.md").exists():
        slug = f"affirmations-{theme}-{week[0]}-w{week[1]:02d}-{n}"
        n += 1
    guide = a["topics"][theme].get("guide", "")
    segs, models, seen = [], set(), set()
    others = "\n".join(WL.spoken_text(WL.parse(p)) for p in WL.all_scripts()
                       if WL.parse(p)["kind"] == "affirmations")
    for i, mv in enumerate(a["movements"], 1):
        msgs = [{"role": "system", "content": AFFIRM_STYLE},
                {"role": "user", "content":
                 f"Theme: {a['topics'][theme]['topic']}. {guide}\nMovement {i} of {len(a['movements'])}: {mv}.\n"
                 f"Write {a['lines_per_movement'] + 6} lines."}]
        lines: list[str] = []
        for _ in range(ATTEMPTS):
            text, model = _complete(msgs, set())
            for ln in text.splitlines():
                ln = re.sub(r"^[\s\-*•\d.)]+", "", ln).strip().strip('"“”')
                if not ln or ln.lower() in seen:
                    continue
                if W.text_problems(ln, []) or WL.affirmation_problems(ln) or len(ln.split()) > 16:
                    continue
                if others and W.overlap(ln, others) > 0.5:
                    continue
                if not ln.endswith((".", "?")):
                    ln += "."
                lines.append(ln)
                seen.add(ln.lower())
            models.add(model)
            if len(lines) >= a["lines_per_movement"]:
                break
            msgs = msgs + [{"role": "assistant", "content": text},
                           {"role": "user", "content": "Write more new lines, all different from those."}]
        if len(lines) < a["lines_per_movement"] * 0.8:
            raise WL_SegmentRefused(f"movement {i}", [f"only {len(lines)} usable lines"])
        segs.append((f"movement-{i}", lines[:a["lines_per_movement"]]))
        print(f"  movement {i}: {len(segs[-1][1])} lines", flush=True)
    t = a["topics"][theme]
    out = WL.SCRIPTS / f"{slug}.md"
    text = WL.render_script(slug, "affirmations", f"Whispered {t['topic']} for sleep",
                            [], [], segs, {"Theme": theme, "Topic": t["topic"],
                                           "Models": ", ".join(sorted(models))})
    return _commit(out, text)


TEACH_STYLE = """You write part of a WHISPERED, GUIDED SLEEP MEDITATION for a woman lying in bed.
Write for the ear, slow, soft and warm, in plain everyday words.

Rules you must follow exactly:
- Use ONLY the points you are given about the teacher's idea. Never quote the teacher, never add a fact, a date, a place, a book or a story about the teacher's life.
- Never promise a result: no "you will get", no "guaranteed", no money amounts, no dates, no "by tomorrow", nothing about what another person will do, no health or healing claims. It is a practice for rest and imagination.
- No numerals, acronyms, brackets, lists, headings, emojis or exclamation marks. No quotation marks.
- Short sentences: at most 22 words each, most of them 8 to 14. Paragraphs of three to five sentences, one blank line between them.
- Second person, present tense, gentle ("you might notice...", "let your shoulders soften...").
- Write only the text. No title, no notes."""


def _own_problems(paras: list[str], allowed: str, want: int, c: dict) -> list[str]:
    import teachings as TG                                  # noqa: PLC0415
    text = "\n\n".join(paras)
    probs = W.text_problems(text, []) + W.fact_problems(text, allowed) + WL.affirmation_problems(text)
    if re.search(r"[“”\"]", text):
        probs.append("QUOTE_MARKS no quotation marks in your own words")
    if TG.book_hits(text) > TG.BOOK_HITS_MAX:
        probs.append("BOOK_READ this reads the teacher's book; use only the given points, in new words")
    for s in WL.sentences(text):
        if len(W.WORD.findall(s)) > c["pacing"]["max_sentence_words"]:
            probs.append(f"LONG_SENTENCE: {s[:50]!r}")
    n = len(W.WORD.findall(text))
    if not 0.75 * want <= n <= 1.6 * want:
        probs.append(f"LENGTH {n} words; write about {want} words")
    return probs


def write_own(prompt: str, allowed: str, want: int, c: dict) -> tuple[list[str], str]:
    """One explanation or guided part from a free model, sent back with its
    named problems until it passes (ATTEMPTS)."""
    base = [{"role": "system", "content": TEACH_STYLE}, {"role": "user", "content": prompt}]
    msgs, rejected, last = list(base), set(), []
    for _ in range(ATTEMPTS):
        text, model = _complete(msgs, rejected)
        paras = clean(text)
        last = _own_problems(paras, allowed, want, c) if paras else ["EMPTY answer"]
        if not last:
            return paras, model
        if model:
            rejected.add(model)
        msgs = base + [{"role": "assistant", "content": text},
                       {"role": "user", "content": "Rewrite the whole text. It broke these rules:\n- "
                        + "\n- ".join(last[:15]) + "\nFix every one. Write only the text."}]
    raise WL_SegmentRefused("teaching part", last)


# Each lead is its own spoken sentence (ends with a full stop), so a long
# line never runs over the sentence limit with its lead (9 Nov 2026 run: a
# Shinn lead and quote spoken as one sentence was 30 words and refused).
LEADS = ["In {book}, {who} wrote this.", "{who} put it this way, in {book}.", "From {book}, in {pron} own words.",
         "Here is a line from {book}.", "{who} wrote this in {book}."]


def quote_paras(teacher: str, topic: str, n_done: int, shape: str) -> list[str]:
    """Two or three verified lines for this technique, rotated so the next
    script on it leads with a different one; each names its book."""
    import teachings as TG                                  # noqa: PLC0415
    r = TG.rights()
    ok = TG.quotable(r)
    pool = [q for q in r["quotes"] if topic in q["topics"] and q["title"] in ok
            and r["titles"][q["title"]]["teacher"] == teacher]
    if len(pool) < TG.MIN_QUOTES:
        raise WL_SegmentRefused(f"{teacher}/{topic}", [f"only {len(pool)} cleared quotes recorded for {topic}"])
    k = 3 if len(pool) >= 3 and shape in ("a", "c") else 2
    pick = [pool[(n_done + i) % len(pool)] for i in range(k)]
    who, pron = r["teachers"][teacher]["spoken"], "his" if teacher == "neville" else "her"
    out = []
    for i, q in enumerate(pick):
        t = r["titles"][q["title"]]
        lead = LEADS[(n_done + i) % len(LEADS)].format(book=t.get("spoken_title") or t["title"], who=who, pron=pron)
        out.append(f"{lead} “{q['text']}”")
    return out


def teaching_scripts(teacher: str) -> list[dict]:
    return [WL.parse(p) for p in WL.all_scripts() if WL.parse(p)["kind"] == teacher]


def pick_structure(c: dict) -> tuple[str, str]:
    """The first shape + scene no recent teaching script used."""
    import teachings as TG                                  # noqa: PLC0415
    every = [WL.parse(p) for p in WL.all_scripts() if WL.parse(p)["kind"] in WL.TEACHING]
    recent = {TG.signature(o) for o in sorted(every, key=lambda o: o["meta"].get("written", ""),
                                               reverse=True)[:TG.RECENT]}
    shapes, scenes = list(c["teachings"]["shapes"]), c["teachings"]["scenes"]
    n = len(every)
    for i in range(len(shapes) * len(scenes)):
        sh, sc = shapes[(n + i) % len(shapes)], scenes[(n * 5 + i) % len(scenes)]
        if (sh, sc) not in recent:
            return sh, sc
    raise WL_SegmentRefused("structure", ["every shape and scene was used recently; add scenes"])


def next_topic(teacher: str, c: dict) -> str:
    topics = list(c["teachings"][teacher]["topics"])
    used = [p["meta"].get("technique") for p in teaching_scripts(teacher)]
    return min(topics, key=lambda t: (used.count(t), topics.index(t)))


def author_teaching(teacher: str, topic: str, c: dict) -> Path:
    import teachings as TG                                  # noqa: PLC0415
    r = TG.rights()
    tc = c["teachings"]
    t = tc[teacher]["topics"][topic]
    who = r["teachers"][teacher]["name"]
    shape, scene = pick_structure(c)
    done = sum(1 for p in teaching_scripts(teacher) if p["meta"].get("technique") == topic)
    slug = f"{teacher}-{topic}-{done + 1:02d}"
    allowed = " ".join([who, r["teachers"][teacher]["spoken"], t["name"]])
    allowed += " " + " ".join(f"{w}'s {w}’s" for w in allowed.split())
    points = "\n".join(f"- {x}" for x in t["points"])
    guides = [x for x in tc["shapes"][shape] if x == "guide"]
    parts, models, gi = [], set(), 0
    for kind in tc["shapes"][shape]:
        if kind == "quotes":
            parts.append(("quotes", quote_paras(teacher, topic, done, shape)))
            continue
        if kind == "explain":
            want = tc["explain_words"]
            prompt = (f"Write the short plain EXPLANATION part: what {who}'s idea of {t['name']} is, in our own "
                      f"words, and how to practise it tonight in bed. Say the name {who} once.\n"
                      f"The points (our own words; use only these):\n{points}\nWrite about {want} words.")
        else:
            gi += 1
            want = int(tc["guide_words"] * (2 if len(guides) == 1 else 1))
            stage = ("Settle the body, then step slowly into the scene" if gi == 1 else
                     "Stay inside the scene, quieter and slower, and let it carry the listener into sleep")
            prompt = (f"Write GUIDED part {gi} of {len(guides)}: help her fall asleep in the wish already "
                      f"fulfilled, practising {t['name']} (points below). The scene: {scene}. {stage}. "
                      f"Use long, soft sentences of calm detail; repeat gentle cues; end very softly.\n"
                      f"The points (our own words):\n{points}\nWrite about {want} words.")
        paras, model = write_own(prompt, allowed, want, c)
        models.add(model)
        parts.append((f"{kind}-{gi}" if kind == "guide" else kind, paras))
        print(f"  {kind}: {sum(len(p.split()) for p in paras)} words ({model})", flush=True)
    out = WL.SCRIPTS / f"{slug}.md"
    text = WL.render_script(slug, teacher, f"{who}: {t['name']}, a whispered sleep meditation", [], [],
                            parts, {"Technique": topic, "Shape": shape, "Scene": scene,
                                    "Models": ", ".join(sorted(models))})
    return _commit(out, text)


def waiting(kind: str) -> list[str]:
    return [p.stem for p in WL.all_scripts()
            if WL.parse(p)["kind"] == kind and WL.parse(p)["status"] == WL.READY
            and not WL.video_path(p.stem).exists()]


def waiting_in(lane: str, c: dict) -> list[str]:
    return [p.stem for p in WL.all_scripts()
            if WL.lane_of(WL.parse(p), c) == lane and WL.parse(p)["status"] == WL.READY
            and not WL.made(p.stem)]


def next_in_lane(lane: str, c: dict) -> tuple[str, str]:
    """(what, which): ('affirmations', theme) or ('teaching', teacher), by the
    lane's rotation and how many of its scripts exist."""
    if lane == "neville":
        return "teaching", "neville"
    rot = c["lanes"][lane]["rotation"]
    n = sum(1 for p in WL.all_scripts() if WL.lane_of(WL.parse(p), c) == lane)
    pick = rot[n % len(rot)]
    return ("teaching", pick) if pick in WL.TEACHING else ("affirmations", pick)


def sleep_lanes(c: dict) -> list[str]:
    """The lanes made of How We Know scripts rewritten for sleep (her decision
    9 Nov 2026: food history and ocean documentary; science and materials
    are paused, with no slots in the mix)."""
    return [ln for ln, v in c["lanes"].items() if isinstance(v, dict) and v.get("kinds") == ["sleep"]]


def next_episode(lane: str, c: dict) -> dict | None:
    """The first planned episode of this lane not yet written whose every
    source How We Know has uploaded (an unchecked source would only be
    refused after the free-model calls)."""
    have = {p.stem for p in WL.all_scripts()}
    checked = WL.fact_checked()
    for e in c["episodes"]:
        if (e.get("lane") == lane and e["slug"] not in have
                and all(WL.base_slug(s) in checked for s in e["sources"])):
            return e
    return None


def write_next(lane: str, c: dict) -> Path:
    what, which = next_in_lane(lane, c)
    if what == "teaching":
        return author_teaching(which, next_topic(which, c), c)
    return author_affirmations(which, c)


def run(args, c: dict) -> int:
    import common as C                                      # noqa: PLC0415
    import llm_router as R                                  # noqa: PLC0415
    with C.Stage(STAGE, zero_work_hint="no whisper script was written") as st:
        try:
            if args.cmd == "sleep":
                e = next(x for x in c["episodes"] if x["slug"] == args.slug)
                st.work(f"wrote {author_sleep(e, c).relative_to(WL.ROOT)}")
            elif args.cmd == "affirmations":
                st.work(f"wrote {author_affirmations(args.theme or next_in_lane('money', c)[1], c).relative_to(WL.ROOT)}")
            elif args.cmd == "teaching":
                st.work(f"wrote {author_teaching(args.teacher, args.topic or next_topic(args.teacher, c), c).relative_to(WL.ROOT)}")
            else:
                # every lane with slots, the furthest behind its weekly count
                # first; at most one long sleep episode a run (her decision
                # 9 Nov 2026: food history and ocean documentary are lanes)
                mix, _ = WL.weekly_mix(c)
                sleepy, unplanned, sleep_done = sleep_lanes(c), [], False
                refused: dict[str, WL_SegmentRefused] = {}
                for _ in range(MAX_WRITES + 2 * len(mix)):
                    short = [ln for ln in mix if mix.get(ln, 0) > 0 and ln not in unplanned
                             and ln not in refused
                             and not (sleep_done and ln in sleepy) and len(waiting_in(ln, c)) < RUNWAY]
                    if not short or len(st.units) >= MAX_WRITES:
                        break
                    ln = min(short, key=lambda x: (len(waiting_in(x, c)), -mix[x], x))
                    # ONE LANE'S REFUSED SCRIPT NEVER COSTS THE OTHER LANES
                    # THEIRS (13 Nov 2026: the food episode was refused first
                    # and the run ended, so Neville and Money got no script
                    # and the Mac had nothing to voice the next night).
                    try:
                        if ln in sleepy:
                            e = next_episode(ln, c)
                            if e is None:
                                unplanned.append(ln)
                                continue
                            out = author_sleep(e, c)
                            sleep_done = True
                        else:
                            out = write_next(ln, c)
                    except WL_SegmentRefused as e:
                        refused[ln] = e
                        st.note(f"WHISPER_SEGMENT_REFUSED {ln}: {e.source} still broke the script rules "
                                f"after {ATTEMPTS} free-model attempts: {'; '.join(e.problems[:3])}")
                        continue
                    st.work(f"wrote {out.relative_to(WL.ROOT)} ({ln})")
                if refused and not st.units:
                    raise next(iter(refused.values()))
                for ln in unplanned:
                    st.note(f"WHISPER_EPISODES_UNPLANNED {ln}: no planned episode with every source "
                            f"fact-checked is left to write")
                if not st.units:
                    if unplanned:
                        st.named_stop("WHISPER_EPISODES_UNPLANNED",
                                      f"no planned {', '.join(unplanned)} episode is left to write (every "
                                      "source fact-checked); plan the next ones in "
                                      "config/whisper_almanac.json `episodes`",
                                      unblock="Add the next episodes (unused fact-checked sources, with the lane).")
                    st.named_stop("WHISPER_RUNWAY_FULL",
                                  "scripts waiting for the Mac, by lane: " + ", ".join(
                                      f"{ln} {len(waiting_in(ln, c))}" for ln in mix if mix[ln] > 0),
                                  unblock="Nothing to do: the Mac voices them nightly.")
        except WL_SegmentRefused as e:
            st.named_stop("WHISPER_SEGMENT_REFUSED",
                          f"{e.source} still broke the script rules after {ATTEMPTS} free-model "
                          f"attempts: {'; '.join(e.problems[:3])}",
                          detail={"problems": e.problems[:20]},
                          unblock="Nothing to do: the next daily run retries from the cached good segments.")
        except R.LLMStop as e:
            st.named_stop(e.code, e.message, unblock=e.unblock)
    print(f"OUTPUT {len(st.units)} whisper scripts written")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("sleep")
    s.add_argument("slug")
    a = sub.add_parser("affirmations")
    a.add_argument("--theme", choices=sorted(WL.cfg()["affirmations"]["topics"]))
    t = sub.add_parser("teaching")
    t.add_argument("teacher", choices=list(WL.TEACHING))
    t.add_argument("--topic")
    return run(ap.parse_args(argv), WL.cfg())


if __name__ == "__main__":
    raise SystemExit(main())
