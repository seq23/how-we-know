#!/usr/bin/env python3
"""THE WHISPER ALMANAC AUTHOR ($0, GitHub Actions; or by hand on the Mac).

    python loop/whisper_author.py              # top up: next sleep episode + this week's affirmations
    python loop/whisper_author.py sleep SLUG   # one planned episode (config/whisper_almanac.json)
    python loop/whisper_author.py affirmations [--theme money|love]

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

RUNWAY. The Mac voices about one sleep episode a week (docs/WHISPER-ALMANAC.md),
so the author keeps at most RUNWAY sleep scripts waiting for voice and one
affirmations script; a full runway is the self-resolving stop
WHISPER_RUNWAY_FULL, never a green no-op.
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
                  episode: str, idx: int) -> tuple[list[str], str]:
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
             f"Write about {want} words.\n\nSOURCE SCRIPT (fact-checked):\n\n{src}"}]
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
    for i, src in enumerate(e["sources"], 1):
        paras, model = write_segment(src, e["named"], want, c, e["slug"], i)
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
    scale = WL.fit_pause_scale(WL.parse(tmp))
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
- Each line is one calm sentence of 4 to 14 everyday words, in the first person ("I...") or second person ("You...").
- Present tense, gentle, believable. Feelings, choices, safety, rest, openness.
- NEVER promise an outcome: no amounts, no money figures, no dates, no "by tomorrow", no "will text you", no specific person or ex.
- NEVER mention health, healing, cures, illness or medicine. No proof, results or screenshots.
- No numerals, acronyms, brackets, lists, emojis or exclamation marks.
- Every line different from every other line. No line repeated with small changes.
- Output only the lines, one per line, nothing else."""


def author_affirmations(theme: str, c: dict) -> Path:
    a = c["affirmations"]
    week = _dt.date.today().isocalendar()
    slug = f"affirmations-{theme}-{week[0]}-w{week[1]:02d}"
    segs, models, seen = [], set(), set()
    others = "\n".join(WL.spoken_text(WL.parse(p)) for p in WL.all_scripts()
                       if WL.parse(p)["kind"] == "affirmations")
    for i, mv in enumerate(a["movements"], 1):
        msgs = [{"role": "system", "content": AFFIRM_STYLE},
                {"role": "user", "content":
                 f"Theme: {theme}. Movement {i} of {len(a['movements'])}: {mv}.\n"
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
    text = WL.render_script(slug, "affirmations", f"Whispered {theme} affirmations for sleep",
                            [], [], segs, {"Theme": theme, "Topic": t["topic"],
                                           "Models": ", ".join(sorted(models))})
    return _commit(out, text)


def waiting(kind: str) -> list[str]:
    return [p.stem for p in WL.all_scripts()
            if WL.parse(p)["kind"] == kind and WL.parse(p)["status"] == WL.READY
            and not WL.video_path(p.stem).exists()]


def next_theme(c: dict) -> str:
    rot = c["affirmations"]["rotation"]
    return rot[_dt.date.today().isocalendar()[1] % len(rot)]


def run(args, c: dict) -> int:
    import common as C                                      # noqa: PLC0415
    import llm_router as R                                  # noqa: PLC0415
    with C.Stage(STAGE, zero_work_hint="no whisper script was written") as st:
        try:
            if args.cmd == "sleep":
                e = next(x for x in c["episodes"] if x["slug"] == args.slug)
                st.work(f"wrote {author_sleep(e, c).relative_to(WL.ROOT)}")
            elif args.cmd == "affirmations":
                st.work(f"wrote {author_affirmations(args.theme or next_theme(c), c).relative_to(WL.ROOT)}")
            else:
                have = {p.stem for p in WL.all_scripts()}
                todo = [e for e in c["episodes"] if e["slug"] not in have]
                if len(waiting("sleep")) < RUNWAY and todo:
                    st.work(f"wrote {author_sleep(todo[0], c).relative_to(WL.ROOT)}")
                if not waiting("affirmations"):
                    st.work(f"wrote {author_affirmations(next_theme(c), c).relative_to(WL.ROOT)}")
                if not st.units:
                    if not todo and len(waiting("sleep")) < RUNWAY:
                        st.named_stop("WHISPER_EPISODES_UNPLANNED",
                                      "every planned Whisper Almanac episode is written; plan the "
                                      "next ones in config/whisper_almanac.json `episodes`",
                                      unblock="Add the next episodes (8-9 unused fact-checked sources each).")
                    st.named_stop("WHISPER_RUNWAY_FULL",
                                  f"{len(waiting('sleep'))} sleep and {len(waiting('affirmations'))} "
                                  f"affirmations script(s) are waiting for the Mac to voice them",
                                  unblock="Nothing to do: the Mac voices them nightly.")
        except WL_SegmentRefused as e:
            st.named_stop("WHISPER_SEGMENT_REFUSED",
                          f"{e.source} still broke the script rules after {ATTEMPTS} free-model "
                          f"attempts: {'; '.join(e.problems[:3])}",
                          detail={"problems": e.problems[:20]},
                          unblock="Nothing to do: the next run retries from the cached good segments.")
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
    a.add_argument("--theme", choices=["money", "love"])
    return run(ap.parse_args(argv), WL.cfg())


if __name__ == "__main__":
    raise SystemExit(main())
