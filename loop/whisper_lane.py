#!/usr/bin/env python3
"""THE WHISPER ALMANAC LANE: sleep scripts, their checks, their kits, the Mac night.

    python loop/whisper_lane.py status            # one line per script
    python loop/whisper_lane.py check [SLUG ...]  # plain words, facts, length, distinct
    python loop/whisper_lane.py kit SLUG          # title, description, thumbnail
    python loop/whisper_lane.py night --until 07:00 [--budget-min N]
                                                  # the Mac: voice + render, in the batch lock

Whisper Almanac (@whisperalmanac) is a faceless YouTube channel voiced by the
owner's own cloned whisper (her rulings 5-6 Nov 2026, spry brain). It is a
lane of this repo, like food: the same $0 machine as How We Know Deep.

  * loop/whisper_author.py (cloud, $0 free models) rewrites fact-checked How
    We Know scripts for sleep into scripts/whisper/<slug>.md, and writes the
    weekly affirmations script;
  * this file holds every rule a script and its upload kit must meet, in
    code: plain words (loop/whisper_words.py), no invented facts, 2-3 hours,
    a distinct script, the title / description / thumbnail rules;
  * `night` runs on the Mac INSIDE bin/batch-session.sh, under the batch's
    narrator lock (8 GB Mac: one narrator at a time). With no whisper sample
    it is the green owner_action stop WHISPER_SAMPLE_MISSING, naming the
    exact place to drop the file; the first night the file exists it voices
    the first ready episode (voice/whisper_voice.py) and renders it dark
    (visuals/whisper_render.py), resuming night to night from disk.

Nothing here uploads or publishes. An upload kit is written for each episode
(channel/whisper/<slug>/kit.json) with the altered-content flag set.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import whisper_words as W                                   # noqa: E402

CONFIG = ROOT / "config" / "whisper_almanac.json"
SCRIPTS = ROOT / "scripts" / "whisper"
KITS = ROOT / "channel" / "whisper"
WORK = ROOT / "renders" / "whisper"
LEDGER = LOOP / "state" / "ledger.json"
FONTS = ROOT / "channel" / "whisper" / "fonts"
STAGE = "whisper-voice"

READY = "READY FOR VOICE"
STATUSES = (READY, "VOICED", "RENDERED")


def cfg() -> dict:
    return json.loads(CONFIG.read_text())


# ------------------------------------------------------------- the sources
def fact_checked() -> set[str]:
    """Slugs the How We Know machine uploaded and has not retired: they passed
    its source, citation and render gates. The only scripts a sleep episode
    may be rewritten from."""
    led = json.loads(LEDGER.read_text())
    return {e["slug"] for e in led.get("published", []) if not e.get("retired_at")}


def source_path(slug: str) -> Path:
    for p in (ROOT / "scripts" / f"{slug}.md", ROOT / "scripts" / "food" / f"{slug}.md"):
        if p.exists():
            return p
    raise FileNotFoundError(f"no How We Know script for {slug}")


SKIP_SECTIONS = {"title card", "producer pov", "what to notice in the edit",
                 "editorial gate", "b-roll plan"}


def source_narration(slug: str) -> str:
    """The spoken narration of a How We Know script: the `## Narration` part
    only, without directives ({{...}}), the producer POV, the title card or
    edit notes."""
    text = source_path(slug).read_text()
    m = re.search(r"^## Narration\s*$(.*?)(?=^## )", text, re.S | re.M)
    body = m.group(1) if m else ""
    out, skip = [], False
    for line in body.splitlines():
        h = re.match(r"^###\s+(.*)", line)
        if h:
            skip = h.group(1).strip().lower() in SKIP_SECTIONS
            continue
        s = line.strip()
        if skip or not s or s.startswith("{{") or s.startswith("[") or s.startswith("**"):
            continue
        out.append(s)
    return "\n\n".join(out)


# ------------------------------------------------------------- the script
def parse(path: Path | str) -> dict:
    """scripts/whisper/<slug>.md -> {meta, segments: [{source, title, paragraphs}]}."""
    text = Path(path).read_text()
    meta = {k.lower(): v.strip() for k, v in re.findall(r"^\*\*(\w[\w ]*):\*\*\s*(.*)$", text, re.M)}
    segs = []
    for m in re.finditer(r"^## Segment (\d+) · (\S+)\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", m.group(3))]
        paras = [p for p in paras if p and not p.startswith("#")]
        segs.append({"n": int(m.group(1)), "source": m.group(2), "paragraphs": paras})
    title = (re.search(r"^# (.+)$", text, re.M) or [None, ""])[1]
    return {"path": str(path), "slug": Path(path).stem, "title": title,
            "meta": meta, "segments": segs,
            "named": [x.strip() for x in meta.get("named", "").split(",") if x.strip()],
            "kind": meta.get("kind", "sleep"), "status": meta.get("status", "")}


def render_script(slug: str, kind: str, title: str, sources: list[str], named: list[str],
                  segments: list[tuple[str, list[str]]], extra: dict | None = None) -> str:
    est = estimate_seconds({"segments": [{"paragraphs": p} for _, p in segments]})
    head = [f"# {title}", "",
            "**Lane:** whisper-almanac",
            f"**Kind:** {kind}",
            f"**Status:** {READY}",
            f"**Sources:** {', '.join(sources)}",
            f"**Named:** {', '.join(named)}",
            f"**Estimated length:** {fmt_len(est)} (speech at the configured pace plus the pauses added in code)",
            f"**Written:** {_dt.date.today():%Y-%m-%d}"]
    for k, v in (extra or {}).items():
        head.append(f"**{k}:** {v}")
    body = []
    for i, (src, paras) in enumerate(segments, 1):
        body += ["", f"## Segment {i} · {src}", ""]
        for p in paras:
            body += [p, ""]
    return "\n".join(head + body).rstrip() + "\n"


def spoken_text(p: dict) -> str:
    return "\n\n".join(x for s in p["segments"] for x in s["paragraphs"])


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def pause_scale(p: dict) -> float:
    try:
        return float(p.get("meta", {}).get("pause scale") or 1.0)
    except ValueError:
        return 1.0


def speech_and_pauses(p: dict, c: dict | None = None) -> tuple[float, float]:
    """(speech seconds, pause seconds at scale 1.0) for a parsed script."""
    c = c or cfg()
    v, wpm = c["voice"], float(c["pacing"]["speech_wpm"])
    paras = [x for s in p["segments"] for x in s["paragraphs"]]
    words = sum(len(W.WORD.findall(x)) for x in paras)
    sents = sum(max(0, len(sentences(x)) - 1) for x in paras)
    pause = (sents * v["pause_sentence_s"] + len(paras) * v["pause_paragraph_s"]
             + len(p["segments"]) * v["pause_segment_s"])
    if p.get("kind") == "affirmations":
        pause += len(paras) * (c["affirmations"]["pause_after_line_s"] - v["pause_paragraph_s"])
    return words / wpm * 60, pause


def estimate_seconds(p: dict, c: dict | None = None) -> float:
    """Speech at the configured (measured) words per minute, plus every pause
    the voice step adds in code, times the script's pause scale: a rewrite is
    about its source's length, and a sleep episode reaches its length with
    longer silences (free on the Mac), never with padding."""
    c = c or cfg()
    speech, pause = speech_and_pauses(p, c)
    return speech + pause * pause_scale(p) + c["voice"]["opening_silence_s"]


MAX_PAUSE_SCALE = 2.2


def fit_pause_scale(p: dict, c: dict | None = None, goal_s: float = 7500.0) -> float:
    """The pause scale (1.0 to 2.2) that brings a script to about goal_s."""
    c = c or cfg()
    speech, pause = speech_and_pauses(p, c)
    if pause <= 0:
        return 1.0
    return round(min(MAX_PAUSE_SCALE, max(1.0, (goal_s - speech) / pause)), 2)


def fmt_len(sec: float) -> str:
    h, m = divmod(int(sec // 60), 60)
    return f"{h} h {m:02d} min"


# ------------------------------------------------------------- the checks
GUARANTEE = re.compile(
    r"\$\s?\d|\bdollars?\b|\bguarantee|\bwill (?:get|receive|win|earn|make|have) (?:\$|\d|a raise|rich|money)|"
    r"\b(?:by|before) (?:tomorrow|tonight|next week|friday|monday)\b|\bwill (?:text|call|come back|return) (?:you|tonight)\b|"
    r"\byour ex\b|\bspecific person\b", re.I)
HEALTH = re.compile(r"\b(?:heal|heals|healing|cure|cures|cured|disease|illness|"
                    r"medicine|medical|anxiety disorder|depression|insomnia cure|treat|treats|therapy)\b", re.I)
PROOF = re.compile(r"\b(?:i made|i earned|screenshot|results? (?:prove|show)|proof that)\b", re.I)


def affirmation_problems(text: str) -> list[str]:
    """The brand guardrail (approved 6 Nov 2026): affirmations, never a
    guaranteed outcome, no fake proof, no healing or health claims."""
    out = []
    for rx, code in ((GUARANTEE, "GUARANTEED_OUTCOME"), (HEALTH, "HEALTH_CLAIM"), (PROOF, "FAKE_PROOF")):
        for m in rx.finditer(text):
            out.append(f"{code} {m.group(0)!r}")
    return out


def all_scripts() -> list[Path]:
    return sorted(SCRIPTS.glob("*.md"))


def script_problems(path: Path | str, others: list[Path] | None = None,
                    c: dict | None = None) -> list[str]:
    """Every rule a whisper script must meet before it may be voiced."""
    c = c or cfg()
    p = parse(path)
    out: list[str] = []
    if p["meta"].get("lane") != "whisper-almanac":
        out.append("HEADER not a whisper-almanac script")
    if not p["segments"]:
        return out + ["EMPTY no segments examined"]
    kind = p["kind"]
    if kind not in c["lengths"]:
        out.append(f"KIND {kind!r} is not sleep or affirmations")
        return out
    checked = fact_checked() if kind == "sleep" else set()
    for s in p["segments"]:
        where = f"segment {s['n']} ({s['source']})"
        text = "\n\n".join(s["paragraphs"])
        out += W.text_problems(text, p["named"], where)
        for sent in sentences(text):
            n = len(W.WORD.findall(sent))
            if n > c["pacing"]["max_sentence_words"]:
                out.append(f"{where}: LONG_SENTENCE {n} words (at most "
                           f"{c['pacing']['max_sentence_words']}): {sent[:60]!r}")
        if kind == "sleep":
            if s["source"] not in checked:
                out.append(f"{where}: SOURCE_NOT_FACT_CHECKED {s['source']} was never uploaded by How We Know")
            else:
                out += W.fact_problems(text, source_narration(s["source"]), where)
        else:
            out += [f"{where}: {x}" for x in affirmation_problems(text)]
    est = estimate_seconds(p, c)
    lo, hi = c["lengths"][kind]["min_s"], c["lengths"][kind]["max_s"]
    if not lo <= est <= hi:
        out.append(f"LENGTH estimated {fmt_len(est)}, outside {fmt_len(lo)} to {fmt_len(hi)}")
    mine = spoken_text(p)
    for o in (others if others is not None else all_scripts()):
        if Path(o).resolve() == Path(path).resolve():
            continue
        ov = W.overlap(mine, spoken_text(parse(o)))
        if ov > c["distinct"]["max_overlap"]:
            out.append(f"NOT_DISTINCT {ov:.0%} of its eight-word runs are in {Path(o).name}")
    return out


# ------------------------------------------------------------- titles, descriptions
def length_label(seconds: float) -> str:
    """The REAL length, rounded DOWN to the half hour so it is never overstated."""
    halves = int(seconds // 1800)
    if halves < 2:
        return f"{max(1, int(seconds // 60))} min"
    h = halves / 2
    return f"{h:g} hr"


def episode_cfg(p: dict, c: dict) -> dict:
    if p["kind"] == "affirmations":
        theme = p["meta"].get("theme", "money")
        return {**c["affirmations"]["topics"][theme], "slug": p["slug"], "kind": "affirmations",
                "hook": f"Whispered {theme} affirmations for sleep, slow and soft, with long pauses.",
                "still_slots": []}
    for e in c["episodes"]:
        if e["slug"] == p["slug"]:
            return e
    return {"topic": p["meta"].get("topic", "sleep science"), "moment": "drift off tonight",
            "thumb_words": p["title"].lower()[:24], "hook": p["title"], "still_slots": []}


def title(p: dict, seconds: float, c: dict | None = None) -> str:
    c = c or cfg()
    e = episode_cfg(p, c)
    pat = c["titles"]["affirmations_pattern" if p["kind"] == "affirmations" else "sleep_pattern"]
    return pat.format(topic=e["topic"], moment=e["moment"], length=length_label(seconds))


def chapters(p: dict, seg_starts: list[float] | None) -> list[str]:
    if not seg_starts:
        return []
    out = []
    for s, t in zip(p["segments"], seg_starts):
        first = sentences(s["paragraphs"][0])[0] if s["paragraphs"] else s["source"]
        h, rem = divmod(int(t), 3600)
        out.append(f"{h}:{rem // 60:02d}:{rem % 60:02d} {first[:60].rstrip('.')}")
    if out:
        out[0] = "0:00:00" + out[0][7:]
    return out


def description(p: dict, seconds: float, c: dict | None = None,
                seg_starts: list[float] | None = None, credits: list[str] | None = None) -> str:
    c = c or cfg()
    e = episode_cfg(p, c)
    lines = [e["hook"],
             c["channel"]["ai_voice_line"],
             f"{length_label(seconds)} of soft whispering over dim, slow footage of the real thing, no music.",
             ""]
    ch = chapters(p, seg_starts)
    if ch:
        lines += ["Chapters", *ch, ""]
    if p["kind"] == "sleep":
        lines += ["Written for sleep from fact-checked How We Know scripts (howweknowdeep.com).", ""]
    else:
        lines += ["Affirmations are words to rest with, not a promise of any outcome.", ""]
    if credits:
        lines += ["Picture credits", *credits, ""]
    lines += ["#sleep #asmr #whisper"]
    return "\n".join(lines).strip() + "\n"


def meta_problems(meta: dict, seconds: float, c: dict | None = None) -> list[str]:
    """Every upload kit must meet these (her rulings 5-6 Nov 2026)."""
    c = c or cfg()
    out = []
    t = meta.get("title", "")
    tl = t.lower()
    if len(t) > c["titles"]["max_chars"]:
        out.append(f"TITLE_TOO_LONG {len(t)} chars")
    if not any(w.lower() in tl for w in c["titles"]["benefit_words"]):
        out.append("TITLE_NO_BENEFIT (sleep)")
    if not any(w.lower() in tl for w in c["titles"]["trigger_words"]):
        out.append("TITLE_NO_TRIGGER (ASMR / whispered)")
    if f"({length_label(seconds)}" not in t:
        out.append(f"TITLE_LENGTH_NOT_REAL expected ({length_label(seconds)}")
    first3 = "\n".join(meta.get("description", "").splitlines()[:3])
    if c["channel"]["ai_voice_line"] not in first3:
        out.append("AI_LINE_NOT_IN_FIRST_3_LINES")
    st = meta.get("body", {}).get("status", {})
    if st.get("containsSyntheticMedia") is not True:
        out.append("ALTERED_CONTENT_NOT_SET")
    if st.get("privacyStatus") != "private":
        out.append("NOT_UPLOADED_PRIVATE")
    if meta.get("body", {}).get("snippet", {}).get("title") != t:
        out.append("BODY_TITLE_MISMATCH")
    return out


def upload_body(t: str, d: str, c: dict) -> dict:
    """The videos.insert body. `status.containsSyntheticMedia` is YouTube's
    altered-or-synthetic-content box; ads stay on (her call 6 Nov), so
    nothing here turns monetisation off."""
    return {"snippet": {"title": t, "description": d, "categoryId": c["channel"]["category_id"],
                        "defaultLanguage": c["channel"]["default_language"],
                        "tags": ["sleep", "asmr", "whisper", "sleep story", "dark screen"]},
            "status": {"privacyStatus": "private", "containsSyntheticMedia": True,
                       "selfDeclaredMadeForKids": c["channel"]["made_for_kids"]}}


# ------------------------------------------------------------- stills and thumbnail
def stills(slots: list[str], n: int = 1) -> list[dict]:
    """Public-domain stills already licence-checked by the How We Know
    harvest (channel/imagery/rights.json), for the slots named."""
    d = json.loads((ROOT / "channel" / "imagery" / "rights.json").read_text())
    out = []
    for a in d["assets"]:
        if a.get("slot") in slots and a.get("commercial_use_permitted") is not False \
                and a.get("local_file") and (ROOT / "channel" / "imagery" / "assets" /
                                             Path(a["local_file"]).name).exists():
            out.append(a)
    return out[:n]


def credit_line(a: dict) -> str:
    return f"{a.get('title', '')}: {a.get('required_credit') or a.get('source_org', '')} ({a.get('item_url', '')})"


def _font(name: str, size: int):
    from PIL import ImageFont                               # noqa: PLC0415
    if name == "Jost-Light.ttf":                            # the variable font, Light axis
        f = ImageFont.truetype(str(FONTS / "Jost.ttf"), size)
        try:
            f.set_variation_by_name("Light")
        except (OSError, ValueError):
            pass
        return f
    return ImageFont.truetype(str(FONTS / name), size)


def thumbnail(p: dict, seconds: float, out: Path, c: dict | None = None) -> Path:
    """1280x720: one candle in a dark room (the approved brand). An ember glow
    drawn in code, lowercase italic words, the real length. No faces, no
    starfields, no pastel purple, no flashes."""
    from PIL import Image, ImageDraw, ImageFilter          # noqa: PLC0415
    c = c or cfg()
    b = c["brand"]
    e = episode_cfg(p, c)
    W_, H_ = 1280, 720
    img = Image.new("RGB", (W_, H_), b["ground"])
    glow = Image.new("RGB", (W_, H_), b["ground"])
    g = ImageDraw.Draw(glow)
    cx, cy = 980, 430
    for r, col in ((330, b["glow"]), (190, "#5A3A1E"), (90, "#8A5A2A")):
        g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.blend(img, glow, 0.9)
    d = ImageDraw.Draw(img)
    # the candle and its flame
    d.rounded_rectangle((cx - 34, cy + 20, cx + 34, cy + 230), radius=8, fill="#E9D9BC")
    d.line((cx, cy + 20, cx, cy - 4), fill="#2A1E14", width=4)
    flame = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    f = ImageDraw.Draw(flame)
    f.ellipse((cx - 22, cy - 92, cx + 22, cy - 2), fill=b["ember"])
    f.ellipse((cx - 10, cy - 58, cx + 10, cy - 8), fill="#FBE3B0")
    flame = flame.filter(ImageFilter.GaussianBlur(3))
    img.paste(flame, (0, 0), flame)
    d = ImageDraw.Draw(img)
    words = e["thumb_words"].lower()
    size = 118
    font = _font("DMSerifDisplay-Italic.ttf", size)
    while d.textlength(words, font=font) > 760 and size > 70:
        size -= 6
        font = _font("DMSerifDisplay-Italic.ttf", size)
    lines = [words]
    if d.textlength(words, font=font) > 760:
        mid = words.rfind(" ", 0, len(words) // 2 + 4)
        lines = [words[:mid], words[mid + 1:]]
    y = 250 - (len(lines) - 1) * size // 2
    for ln in lines:
        d.text((80, y), ln, font=font, fill=b["ink"])
        y += int(size * 1.05)
    small = _font("Jost-Light.ttf", 40)
    d.text((84, y + 30), f"{length_label(seconds)} · whispered · sleep science", font=small, fill=b["ember"])
    d.text((84, 640), "whisper almanac", font=_font("Jost-Light.ttf", 30), fill="#BFAF95")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def kit(slug: str, measured_s: float | None = None, seg_starts: list[float] | None = None,
        c: dict | None = None) -> dict:
    """channel/whisper/<slug>/kit.json + thumbnail.png. Before voicing the
    length is the ESTIMATE (marked); after voicing, the measured length."""
    c = c or cfg()
    path = SCRIPTS / f"{slug}.md"
    p = parse(path)
    e = episode_cfg(p, c)
    secs = measured_s if measured_s else estimate_seconds(p, c)
    st = stills(e.get("still_slots") or [], 1)
    credits = [credit_line(a) for a in st]
    t = title(p, secs, c)
    dsc = description(p, secs, c, seg_starts, credits)
    meta = {"slug": slug, "kind": p["kind"], "title": t, "description": dsc,
            "length_s": round(secs, 1), "length_basis": "measured" if measured_s else "estimated",
            "still": (st[0]["local_file"] if st else None), "credits": credits,
            "body": upload_body(t, dsc, c), "uploaded": False}
    probs = meta_problems(meta, secs, c)
    meta["problems"] = probs
    d = KITS / slug
    d.mkdir(parents=True, exist_ok=True)
    thumbnail(p, secs, d / "thumbnail.png", c)
    (d / "kit.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return meta


# ------------------------------------------------------------- the sample gate
def sample_dir(c: dict | None = None) -> Path:
    c = c or cfg()
    return Path(os.path.expanduser(os.environ.get("WHISPER_SAMPLE_DIR") or c["sample"]["dir"]))


def find_sample(c: dict | None = None) -> Path | None:
    c = c or cfg()
    for n in c["sample"]["names"]:
        q = sample_dir(c) / n
        if q.exists() and q.stat().st_size > 0:
            return q
    return None


def sample_stop_text(c: dict | None = None) -> str:
    c = c or cfg()
    d = sample_dir(c)
    return (f"no whisper sample at {d}/{c['sample']['names'][0]} (or {c['sample']['names'][1]}). "
            f"Record 20-30 seconds of steady whispering in a quiet room (iPhone Voice Memos "
            f"is fine), and save it as {d}/whisper-sample.m4a or .wav on this Mac. The next "
            f"nightly batch voices the first ready episode on its own.")


def _probe_seconds(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def prepare_reference(sample: Path, c: dict | None = None) -> tuple[Path | None, str]:
    """The sample -> a 24 kHz mono wav Chatterbox reads (kept beside the sample,
    on her Mac, never in the repo). Returns (path, problem)."""
    c = c or cfg()
    secs = _probe_seconds(sample)
    lo, hi = c["sample"]["min_seconds"], c["sample"]["max_seconds"]
    if not lo <= secs <= hi:
        return None, (f"the whisper sample {sample} is {secs:.0f} s long; it needs {lo}-{hi} s "
                      f"of steady whispering. Record it again and save it in the same place.")
    out = sample.parent / c["sample"]["reference_out"]
    if not out.exists() or out.stat().st_mtime < sample.stat().st_mtime:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(sample), "-ac", "1",
                            "-ar", "24000", "-sample_fmt", "s16", str(out)], capture_output=True, text=True)
        if r.returncode:
            return None, f"ffmpeg could not read {sample}: {r.stderr.strip()[:160]}"
    return out, ""


# ------------------------------------------------------------- status and the night
def audio_dir(slug: str) -> Path:
    return WORK / slug / "audio"


def video_path(slug: str) -> Path:
    return WORK / slug / f"{slug}.mp4"


def beats(p: dict) -> list[dict]:
    """One beat per paragraph; the pause after it is silence added in code."""
    c = cfg()
    v = c["voice"]
    out = []
    for si, s in enumerate(p["segments"]):
        for pi, para in enumerate(s["paragraphs"]):
            after = v["pause_paragraph_s"]
            if p["kind"] == "affirmations":
                after = c["affirmations"]["pause_after_line_s"]
            if pi == len(s["paragraphs"]) - 1:
                after = v["pause_segment_s"]
            out.append({"text": para, "segment": si, "pause_after_s": round(after * pause_scale(p), 2),
                        "pause_sentence_s": round(v["pause_sentence_s"] * pause_scale(p), 2)})
    return out


def voiced(slug: str) -> tuple[int, int]:
    p = parse(SCRIPTS / f"{slug}.md")
    n = len(beats(p))
    d = audio_dir(slug)
    done = sum(1 for i in range(n) if (d / f"{i:04d}.wav").exists() and (d / f"{i:04d}.json").exists())
    return done, n


def queue() -> list[str]:
    """Scripts ready for voice, sleep episodes first (the lead lane), oldest first."""
    rows = []
    waits = {e["slug"] for e in cfg()["episodes"] if e.get("waits_for")}
    for f in all_scripts():
        p = parse(f)
        if p["status"] != READY or video_path(p["slug"]).exists() or p["slug"] in waits:
            continue
        rows.append((0 if p["kind"] == "sleep" else 1, p["meta"].get("written", ""), p["slug"]))
    return [s for *_, s in sorted(rows)]


def status_lines() -> list[str]:
    out = []
    for f in all_scripts():
        p = parse(f)
        done, n = voiced(p["slug"])
        state = ("rendered" if video_path(p["slug"]).exists() else
                 f"voiced {done}/{n} beats" if done else "ready for voice")
        out.append(f"{p['slug']}: {p['kind']}, {fmt_len(estimate_seconds(p))} estimated, {state}")
    return out


def _until_epoch(until: str) -> float:
    now = _dt.datetime.now()
    hh, mm = (int(x) for x in until.split(":"))
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t <= now:
        t += _dt.timedelta(days=1)
    return t.timestamp()


def night(until: str, budget_min: int | None, py_tts: str, dry: bool = False) -> int:
    """The Mac step. Called by bin/batch-session.sh while it holds the lock."""
    import common as C                                      # noqa: PLC0415
    c = cfg()
    with C.Stage(STAGE, zero_work_hint="no whisper script is ready for voice") as st:
        q = queue()
        if not q:
            st.named_stop("WHISPER_NOTHING_TO_VOICE",
                          "every Whisper Almanac script is voiced and rendered; the "
                          "cloud author lane writes the next one on Wednesday",
                          unblock="Nothing to do: the next loop-whisper-author run refills it.")
        sample = find_sample(c)
        if sample is None:
            st.named_stop("WHISPER_SAMPLE_MISSING", sample_stop_text(c),
                          detail={"waiting": q, "drop_here": str(sample_dir(c) / "whisper-sample.m4a")},
                          unblock=sample_stop_text(c))
        ref, why = prepare_reference(sample, c)
        if ref is None:
            st.named_stop("WHISPER_SAMPLE_UNUSABLE", why, unblock=why)
        problems = script_problems(SCRIPTS / f"{q[0]}.md")
        if problems:
            st.named_stop("WHISPER_SCRIPT_REFUSED",
                          f"{q[0]} fails {len(problems)} script rule(s): {problems[0]}",
                          detail={"problems": problems[:20]},
                          unblock="loop/whisper_author.py rewrites failing segments on its next run.")
        stop_at = _until_epoch(until)
        if budget_min:
            stop_at = min(stop_at, time.time() + budget_min * 60)
        slug = q[0]
        before, n = voiced(slug)
        if dry:
            st.work(f"DRY: would voice {slug} from beat {before} of {n} until "
                    f"{_dt.datetime.fromtimestamp(stop_at):%H:%M}")
            return 0
        import render_prune as RP                          # noqa: PLC0415
        rc, line = RP.guard()
        print(f"  {line}")
        if rc:
            st.named_stop("DISK_LOW", line, unblock="Free space on the Mac; the next night resumes.")
        if before < n:
            r = subprocess.run([py_tts, str(ROOT / "voice" / "whisper_voice.py"),
                                str(SCRIPTS / f"{slug}.md"), str(audio_dir(slug)),
                                "--reference", str(ref), "--until-epoch", str(int(stop_at))])
            after, _ = voiced(slug)
            if after > before:
                st.work(f"voiced {slug}: beats {before}->{after} of {n}")
            elif r.returncode == 4:
                st.named_stop("WHISPER_WINDOW_CLOSED",
                              f"the night's window closed before {slug} beat {before} of {n}",
                              unblock="Nothing to do: the next batch night resumes at that beat.")
            elif r.returncode:
                st.named_stop("WHISPER_VOICE_FAILED",
                              f"voice/whisper_voice.py exited {r.returncode} on {slug} with no new beat",
                              unblock="Read ~/Library/Logs/how-we-know/batch.log for the traceback.")
        after, _ = voiced(slug)
        if after == n:
            r = subprocess.run([str(ROOT / ".venv" / "bin" / "python"),
                                str(ROOT / "visuals" / "whisper_render.py"), slug])
            if r.returncode == 0 and video_path(slug).exists():
                st.work(f"rendered {video_path(slug).relative_to(ROOT)}")
            elif r.returncode == 5:
                st.named_stop("WHISPER_FOOTAGE_THIN",
                              f"{slug} is voiced, but its subjects do not yet have enough "
                              f"licence-checked footage to meet the footage rules without filler",
                              unblock="Nothing to do: the weekly imagery harvest grows the pool "
                                      "and the next Almanac night renders it; the audio is kept.")
            else:
                st.named_stop("WHISPER_RENDER_FAILED", f"visuals/whisper_render.py exited {r.returncode} on {slug}",
                              unblock="Read the batch log; the audio is complete and kept.")
        print(f"OUTPUT {after - before} whisper beats voiced ({slug} {after}/{n})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    ck = sub.add_parser("check")
    ck.add_argument("slugs", nargs="*")
    kt = sub.add_parser("kit")
    kt.add_argument("slug")
    nt = sub.add_parser("night")
    nt.add_argument("--until", default="07:00")
    nt.add_argument("--py-tts", default=str(ROOT / ".venv-tts" / "bin" / "python"))
    nt.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        lines = status_lines()
        print("\n".join(lines))
        print(f"OUTPUT {len(lines)} whisper scripts")
        return 0 if lines else 2
    if a.cmd == "check":
        paths = [SCRIPTS / f"{s}.md" for s in a.slugs] or all_scripts()
        if not paths:
            print("NAMED STOP [WHISPER_NO_SCRIPTS] no whisper script examined", file=sys.stderr)
            return 2
        bad = 0
        for p in paths:
            probs = script_problems(p)
            bad += bool(probs)
            print(f"{p.stem}: {'OK' if not probs else f'{len(probs)} problem(s)'}")
            for x in probs[:12]:
                print(f"  {x}")
        print(f"OUTPUT {len(paths) - bad} of {len(paths)} whisper scripts pass")
        return 1 if bad else 0
    if a.cmd == "kit":
        m = kit(a.slug)
        print(m["title"])
        for x in m["problems"]:
            print(f"  {x}")
        return 1 if m["problems"] else 0
    if a.cmd == "night":
        return night(a.until, None, a.py_tts, a.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
