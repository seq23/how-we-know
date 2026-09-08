#!/usr/bin/env python
"""captions.py - derive caption tracks and chapter markers from the REAL audio.

Why this can be exact
---------------------
`visuals/assemble.py` treats audio as the timing authority: beat *i* of
`plans/<slug>.json` is mounted to the measured duration of `audio/<slug>/NNNN.wav`,
and a narration track is only muxed when the wav count equals the beat count.
So the offset of every beat in the finished video is not an estimate - it is

    offset[i] = sum(duration(wav[0..i-1]))

Most channels guess their chapter marks. This one measures them.

Text authority
--------------
The words the TTS actually read are `plan[i]["narration"]` (see
`voice/narrate_all.py`, which feeds exactly that string to the model and records
it beside the audio in `audio/<slug>/beats.json`). Cue text therefore comes from
the plan, and is cross-checked two ways:

  * against `audio/<slug>/beats.json` - the text recorded next to the audio, so
    captions and audio cannot disagree about what was said;
  * against `voice/script_text.py` - every beat's prose must be present in the
    script's `## Narration` section, the same extractor the site transcript uses.

Chapters: one source of truth
-----------------------------
`loop/upload.py:build_payload()` builds the YouTube description by parsing the
script's own `## Chapters` block (`- M:SS Title`). This tool does NOT emit a
competing list. It rewrites the timestamps *in that block*, keeping the titles,
so upload keeps reading the one place it always read. The `.chapters.txt`
artifact is a rendering of the same data for eyeballing, never an input.

Usage
-----
  captions.py 05                     # one episode (prefix match)
  captions.py --all                  # every episode with complete audio
  captions.py 05 --check renders/05-...-final.mp4
  captions.py --all --no-write-script
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "voice"))

SCRIPTS = ROOT / "scripts"
PLANS = ROOT / "plans"
AUDIO = ROOT / "audio"
RENDERS = ROOT / "renders"
OUT = ROOT / "captions"

FPS = 30                      # must match visuals/design.py
MIN_BEAT_S = 0.4              # assemble.py: durations.append(max(0.4, d))

# Caption shape. Two lines of <= 42 characters is the readable ceiling for a
# 1920-wide frame at the burn-in size proposed in captions_burnin_proposal; the
# same numbers drive the VTT so on-screen and off-screen captions never differ.
MAX_LINE_CHARS = 42
MAX_LINES = 2
MIN_CUE_S = 1.10              # below this a cue flashes rather than reads
YT_MIN_CHAPTER_S = 10.0       # YouTube drops the whole chapter list otherwise
YT_MIN_CHAPTERS = 3


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------
def wav_duration(path: Path) -> float:
    """Exact wav duration. Identical to assemble.py's ffprobe probe() for PCM,
    without paying a subprocess per beat."""
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def ffprobe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise SystemExit(f"error: ffprobe could not read {path}")


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def episode_slugs() -> list[str]:
    return sorted(p.stem for p in SCRIPTS.glob("*.md"))


def resolve(prefix: str) -> str:
    hits = [s for s in episode_slugs() if s.startswith(prefix) or s == prefix]
    if len(hits) != 1:
        raise SystemExit(f"error: {prefix!r} matched {len(hits)} episodes: {hits}")
    return hits[0]


def load_plan(slug: str) -> list[dict]:
    """The beat list assemble.py indexes audio against.

    `plans/<slug>.json` is the frozen copy; where it is absent the planner is
    deterministic and reproduces it. Never writes to plans/.
    """
    pj = PLANS / f"{slug}.json"
    if pj.exists():
        plan = json.loads(pj.read_text())
        src = f"plans/{slug}.json"
    else:
        import planner
        plan = planner.plan(str(SCRIPTS / f"{slug}.md"))
        src = "planner.plan() (no frozen plan on disk)"
    if not plan:
        raise SystemExit(f"error: {slug} planned 0 beats - refusing to write an "
                         f"empty caption file.")
    return plan, src


def beats_manifest_path(slug: str) -> Path:
    """`audio/<slug>/beats.json` — the audio-to-plan contract, and the ONE file
    in `audio/` that git tracks (`.gitignore` excludes `audio/**/*.wav` and
    nothing else)."""
    return AUDIO / slug / "beats.json"


def read_beats_manifest(slug: str) -> dict[int, dict]:
    p = beats_manifest_path(slug)
    if not p.exists():
        return {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(rows, list):
        return {}
    return {int(r["i"]): r for r in rows if isinstance(r, dict) and "i" in r}


def recorded_durations(slug: str) -> dict[int, float]:
    """Beat index -> the wav duration MEASURED when the audio was generated.

    THIS IS THE WHOLE REASON CAPTIONS CAN BE BUILT IN THE CLOUD. Cue text has
    always been committed (`plans/<slug>.json`); the only input that lived
    exclusively on the voicing Mac was a list of per-beat wav durations — a few
    dozen floats. Persisting them beside the text they belong to turns the
    caption track from "derivable only where the audio is" into "derivable from
    the repository", which is what lets loop/captions_build.py heal an episode
    without the laptop.

    A recorded value is exact, not an estimate: it is `wav_duration()` of the
    very file assemble.py mounted the beat to.
    """
    out = {}
    for i, row in read_beats_manifest(slug).items():
        d = row.get("seconds")
        if isinstance(d, (int, float)) and d > 0:
            out[i] = float(d)
    return out


def record_durations(slug: str, durs: list[float], measured_idx: set[int]) -> int:
    """Write measured wav durations into `audio/<slug>/beats.json`. Returns the
    number of beats whose recorded value changed.

    Only beats whose duration came from a REAL wav on this machine are written:
    a recorded estimate would be a fabricated measurement, and every downstream
    consumer treats `seconds` as measured truth.
    """
    p = beats_manifest_path(slug)
    if not p.exists():
        return 0
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(rows, list):
        return 0
    changed = 0
    for r in rows:
        if not isinstance(r, dict) or "i" not in r:
            continue
        i = int(r["i"])
        if i not in measured_idx or i >= len(durs):
            continue
        # FULL PRECISION, NOT ROUNDED. A wav duration is frames/rate — an
        # exact rational that float holds exactly — and rounding it to six
        # decimals moves it by up to 5e-7 s. That is inaudible and it is not
        # harmless: an SRT timestamp is rounded to the millisecond, so a beat
        # boundary sitting exactly on a millisecond edge lands on the other
        # side of it and the rebuilt file differs from the one built off the
        # wavs. It happened to what-is-carbon-fiber-made-of on the first pass.
        # The whole promise of this file is that the cloud rebuilds the SAME
        # track, so the stored number is the measured number.
        val = float(durs[i])
        if r.get("seconds") != val:
            r["seconds"] = val
            changed += 1
    if changed:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return changed


# Timing sources whose numbers were MEASURED off real narration audio, as
# opposed to the planner's word-count estimate. Anything in this set may be
# used to write a caption track, burn one in, or correct a chapter stamp.
MEASURED_TIMINGS = ("audio", "recorded")


def beat_durations(slug: str, plan: list[dict]):
    """(durations, source, measured). Mirrors assemble.py exactly: measured
    audio when the wav exists, the duration RECORDED from that wav when the wav
    itself is absent (the cloud case — see recorded_durations), the plan's
    estimate only when neither exists.

    `source` is one of:
        audio     every beat measured off a wav present on this machine
        recorded  every beat measured, at least one from the committed manifest
        partial   some beats measured, some estimated
        estimate  nothing measured
    """
    adir = AUDIO / slug
    rec = recorded_durations(slug)
    durs, from_wav, from_record = [], set(), set()
    for i, b in enumerate(plan):
        wav = adir / f"{i:04d}.wav"
        if wav.exists():
            d = wav_duration(wav)
            from_wav.add(i)
        elif i in rec:
            d = rec[i]
            from_record.add(i)
        else:
            d = float(b["seconds"])
        durs.append(max(MIN_BEAT_S, d))
    measured = len(from_wav) + len(from_record)
    if measured == 0:
        source = "estimate"
    elif measured < len(plan):
        source = "partial"
    elif from_record:
        source = "recorded"
    else:
        source = "audio"
    return durs, source, measured


def wav_indices(slug: str, plan: list[dict]) -> set[int]:
    """Beats whose wav is on THIS machine — the only ones whose duration this
    machine is entitled to record. Deliberately a second, cheap pass rather
    than a fourth return value: four call sites unpack beat_durations()'s
    3-tuple and a widened signature would break them silently."""
    adir = AUDIO / slug
    return {i for i in range(len(plan)) if (adir / f"{i:04d}.wav").exists()}


# --------------------------------------------------------------------------
# text verification
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def verify_text(slug: str, plan: list[dict]) -> dict:
    """Two independent checks that the cue text is what was spoken."""
    result = {"beats_json": None, "script_text": None}

    bj = AUDIO / slug / "beats.json"
    if bj.exists():
        recorded = {b["i"]: b["narration"] for b in json.loads(bj.read_text())}
        bad = [i for i, b in enumerate(plan)
               if i in recorded and _norm(recorded[i]) != _norm(b["narration"])]
        result["beats_json"] = {"checked": len(recorded), "mismatched": bad}
        if bad:
            raise SystemExit(
                f"error: {slug} beats {bad[:5]} differ between plans/ and the text "
                f"recorded with the audio. Captions would state words the voice "
                f"never said. Refusing to write.")

    import script_text
    prose = _norm(" ".join(script_text.read_script(str(SCRIPTS / f"{slug}.md"))))
    missing = []
    for i, b in enumerate(plan):
        if b.get("from") == "heading":
            continue                     # title cards are structural, not narration
        if _norm(b["narration"]) not in prose:
            missing.append(i)
    result["script_text"] = {"checked": len(plan), "absent_from_narration": missing}
    return result


# --------------------------------------------------------------------------
# cues
# --------------------------------------------------------------------------
def wrap(text: str) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if len(cand) <= MAX_LINE_CHARS or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def chunk_beat(text: str, seconds: float) -> list[str]:
    """Split one beat's narration into readable cues, never more than the beat's
    duration can hold at MIN_CUE_S each."""
    cap_chars = MAX_LINE_CHARS * MAX_LINES
    # Prefer a sentence boundary to a line boundary: a cue that ends on "... red.
    # The" reads worse than one that ends on the full stop.
    cues = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not sent:
            continue
        if cues and len(cues[-1]) + 1 + len(sent) <= cap_chars:
            cues[-1] = cues[-1] + " " + sent
        elif len(sent) <= cap_chars:
            cues.append(sent)
        else:                            # too long to hold: break on line edges
            lines = wrap(sent)
            cues += [" ".join(lines[i:i + MAX_LINES])
                     for i in range(0, len(lines), MAX_LINES)]
    cap = max(1, int(seconds // MIN_CUE_S))
    while len(cues) > cap:               # merge the shortest neighbour pair
        j = min(range(len(cues) - 1), key=lambda k: len(cues[k]) + len(cues[k + 1]))
        cues[j:j + 2] = [cues[j] + " " + cues[j + 1]]
    return cues


def build_cues(plan, durs):
    """Continuous cues over the whole episode. Time inside a beat is shared by
    character count - the closest proxy to speech duration available without
    forced alignment, and it can never drift because every beat re-syncs to a
    measured offset."""
    cues, t = [], 0.0
    for i, (b, d) in enumerate(zip(plan, durs)):
        text = re.sub(r"\s+", " ", b["narration"]).strip()
        parts = chunk_beat(text, d) if text else []
        if not parts:
            t += d
            continue
        total = sum(len(p) for p in parts) or 1
        start = t
        for k, p in enumerate(parts):
            share = d * len(p) / total
            end = t + d if k == len(parts) - 1 else start + share
            cues.append({"start": start, "end": end, "text": p, "beat": i})
            start = end
        t += d
    if not cues:
        raise SystemExit("error: 0 cues built - refusing to write an empty file.")
    return cues


def ts_vtt(s: float) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"


def ts_srt(s: float) -> str:
    return ts_vtt(s).replace(".", ",")


def write_vtt(cues, path: Path, title: str):
    out = ["WEBVTT", f"NOTE {title} - timed from measured narration audio", ""]
    for c in cues:
        out.append(f"{ts_vtt(c['start'])} --> {ts_vtt(c['end'])}")
        out += wrap(c["text"])[:MAX_LINES] or [c["text"]]
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_srt(cues, path: Path):
    out = []
    for n, c in enumerate(cues, 1):
        out.append(str(n))
        out.append(f"{ts_srt(c['start'])} --> {ts_srt(c['end'])}")
        out += wrap(c["text"])[:MAX_LINES] or [c["text"]]
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


# --------------------------------------------------------------------------
# chapters
# --------------------------------------------------------------------------
CH_LINE = re.compile(r"^(\s*-\s*)(\d{1,2}:\d{2}(?::\d{2})?)(\s+)(.*?)\s*$")


def hms(s: float) -> str:
    """YouTube description form: M:SS, or H:MM:SS past an hour."""
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_chapter_lines(block: str) -> list[dict]:
    rows = []
    for line in block.splitlines():
        mm = CH_LINE.match(line)
        if mm:
            p = mm.group(2).split(":")
            secs = (int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])) if len(p) == 3 \
                else int(p[0]) * 60 + int(p[1])
            rows.append({"raw": line, "stamp": mm.group(2), "seconds": secs,
                         "title": mm.group(4)})
    return rows


def baseline_path(slug: str) -> Path:
    """The hand-written chapter block as it stood BEFORE this tool first
    corrected it. Without pinning it, the second run measures drift against its
    own output and reports ~0 - a validator grading its own homework."""
    return OUT / f"{slug}.chapters.handwritten.txt"


def handwritten(slug: str) -> list[dict]:
    bp = baseline_path(slug)
    if bp.exists():
        return parse_chapter_lines(bp.read_text(encoding="utf-8"))
    _, _, rows = script_chapters(slug)
    return rows


def script_chapters(slug: str):
    """The chapter block as it stands, and where it sits in the file."""
    text = (SCRIPTS / f"{slug}.md").read_text(encoding="utf-8")
    m = re.search(r"## Chapters\s*\n(.*?)(\n## |\Z)", text, re.S)
    if not m:
        return text, None, []
    rows = []
    for line in m.group(1).splitlines():
        mm = CH_LINE.match(line)
        if mm:
            p = mm.group(2).split(":")
            secs = (int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])) if len(p) == 3 \
                else int(p[0]) * 60 + int(p[1])
            rows.append({"raw": line, "stamp": mm.group(2), "seconds": secs,
                         "title": mm.group(4)})
    return text, m, rows


def real_chapters(plan, durs):
    """Heading -> first measured offset. Consecutive beats sharing a heading are
    one chapter, which is how the script's own chapter list is structured."""
    out, t = [], 0.0
    for b, d in zip(plan, durs):
        h = (b.get("heading") or "").strip()
        if h and (not out or out[-1]["title"] != h):
            out.append({"title": h, "seconds": t})
        t += d
    return out, t


def enforce_youtube(chs, total):
    """YouTube ignores the entire chapter list unless the first mark is 0:00,
    there are at least three, and every chapter runs at least 10 seconds. A
    too-short chapter is folded into the one before it (the earlier title wins,
    because it is the one the viewer is already reading)."""
    if not chs:
        return [], ["no chapters"]
    notes = []
    chs = [dict(c) for c in chs]
    if chs[0]["seconds"] > 0.0:
        notes.append(f"first mark was {hms(chs[0]['seconds'])}; forced to 0:00")
        chs[0]["seconds"] = 0.0
    kept = chs
    merged, dropped = [], []
    for i, c in enumerate(kept):
        end = kept[i + 1]["seconds"] if i + 1 < len(kept) else total
        if merged and (end - c["seconds"]) < YT_MIN_CHAPTER_S:
            dropped.append(f"{c['title']} ({end - c['seconds']:.1f}s)")
            continue
        merged.append(c)
    # a short FIRST chapter cannot merge backwards; absorb the second instead
    while len(merged) > 1 and (merged[1]["seconds"] - merged[0]["seconds"]) < YT_MIN_CHAPTER_S:
        dropped.append(f"{merged[1]['title']} (first-chapter merge)")
        del merged[1]
    if dropped:
        notes.append(f"merged {len(dropped)} chapter(s) under {YT_MIN_CHAPTER_S:.0f}s: "
                     + ", ".join(dropped))
    if len(merged) < YT_MIN_CHAPTERS:
        notes.append(f"only {len(merged)} chapters - YouTube needs {YT_MIN_CHAPTERS}")
    return merged, notes


def rewrite_script_chapters(slug: str, chs, dry=False):
    """Correct the timestamps inside the script's own `## Chapters` block.

    This is deliberately the ONLY place chapter truth lives: loop/upload.py's
    build_payload() already parses this block, so upload needs no change and no
    second list can drift away from it. Titles are never touched; only the stamp
    column moves, and lines whose chapter was merged away are removed so YouTube
    accepts the list.
    """
    text, m, rows = script_chapters(slug)
    if m is None:
        return {"written": False, "reason": "script has no ## Chapters block"}

    OUT.mkdir(exist_ok=True)
    bp = baseline_path(slug)
    if not bp.exists():
        bp.write_text(m.group(1).strip("\n") + "\n", encoding="utf-8")

    by_title = {c["title"].strip().lower(): c for c in chs}
    new_lines, removed, unmatched = [], [], []
    for line in m.group(1).splitlines():
        mm = CH_LINE.match(line)
        if not mm:
            new_lines.append(line)
            continue
        title = mm.group(4).strip()
        c = by_title.get(title.lower())
        if c is None:
            removed.append(title)
            continue
        new_lines.append(f"{mm.group(1)}{hms(c['seconds'])}{mm.group(3)}{title}")

    have = {mm.group(4).strip().lower()
            for mm in (CH_LINE.match(l) for l in m.group(1).splitlines()) if mm}
    unmatched = [c["title"] for c in chs if c["title"].strip().lower() not in have]

    body = "\n".join(new_lines)
    if not body.endswith("\n"):
        body += "\n"
    new_text = text[:m.start(1)] + body + text[m.end(1):]
    changed = new_text != text
    if changed and not dry:
        tmp = SCRIPTS / f".{slug}.md.captions.tmp"
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, SCRIPTS / f"{slug}.md")
    return {"written": bool(changed and not dry), "changed": changed,
            "removed_lines": removed, "chapters_not_in_script": unmatched}


# --------------------------------------------------------------------------
# per-episode run
# --------------------------------------------------------------------------
def find_render(slug: str):
    for name in (f"{slug}-final.mp4", f"{slug}.mp4"):
        p = RENDERS / name
        if p.exists():
            return p
    return None


def process(slug: str, write_script=True, check=None, verbose=True) -> dict:
    plan, plan_src = load_plan(slug)
    durs, timing, measured = beat_durations(slug, plan)
    # PERSIST WHAT ONLY THIS MACHINE CAN MEASURE, in the same pass that uses it.
    # audio/<slug>/*.wav is gitignored and audio/<slug>/beats.json is not, so
    # writing the measured durations into the manifest is the whole difference
    # between "this episode can only ever be captioned here" and "any lane can
    # rebuild this caption track from the repository".
    recorded_now = record_durations(slug, durs, wav_indices(slug, plan))
    checks = verify_text(slug, plan)
    cues = build_cues(plan, durs)
    total = sum(durs)

    OUT.mkdir(exist_ok=True)
    vtt, srt = OUT / f"{slug}.vtt", OUT / f"{slug}.srt"
    write_vtt(cues, vtt, slug)
    write_srt(cues, srt)

    real, total2 = real_chapters(plan, durs)
    chs, notes = enforce_youtube(real, total)
    lines = [f"{hms(c['seconds'])} {c['title']}" for c in chs]
    (OUT / f"{slug}.chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # drift against the hand-written stamps
    hand = handwritten(slug)
    hand_by = {h["title"].strip().lower(): h for h in hand}
    drift = []
    for c in real:
        h = hand_by.get(c["title"].strip().lower())
        if h:
            drift.append({"title": c["title"], "hand": h["stamp"],
                          "real": hms(c["seconds"]),
                          "drift_s": round(c["seconds"] - h["seconds"], 1)})
    worst = max((abs(d["drift_s"]) for d in drift), default=0.0)
    mean = round(sum(abs(d["drift_s"]) for d in drift) / len(drift), 1) if drift else 0.0

    # ffprobe reality check
    render = Path(check) if check else find_render(slug)
    probe = None
    if render and render.exists():
        vd = ffprobe_duration(render)
        est_total = sum(max(MIN_BEAT_S, float(b["seconds"])) for b in plan)
        probe = {"file": str(render.relative_to(ROOT)), "video_s": round(vd, 3),
                 "last_cue_end_s": round(cues[-1]["end"], 3),
                 "delta_s": round(cues[-1]["end"] - vd, 3),
                 "ok": abs(cues[-1]["end"] - vd) <= 0.5}
        # A render cut before the narration existed is timed off the plan's
        # word-count estimate. That is a stale VIDEO, not a bad caption track -
        # say so instead of blaming the cues.
        if not probe["ok"] and timing == "audio" and abs(vd - est_total) <= 1.5:
            probe["ok"] = None
            probe["render_timing"] = "estimate (predates narration - re-render)"

    script_edit = {"written": False, "reason": "skipped"}
    if write_script and timing in MEASURED_TIMINGS:
        script_edit = rewrite_script_chapters(slug, chs)
    elif write_script:
        script_edit = {"written": False,
                       "reason": f"timing source is {timing!r}; stamps are only "
                                 f"written from fully measured audio"}

    rec = {
        "episode": slug, "beats": len(plan), "plan_source": plan_src,
        "timing": timing, "beats_measured": measured,
        "durations_recorded": recorded_now,
        "duration_s": round(total, 3), "cues": len(cues),
        "chapters_real": len(real), "chapters_published": len(chs),
        "chapter_notes": notes,
        "drift": {"mean_abs_s": mean, "worst_abs_s": round(worst, 1),
                  "rows": drift},
        "ffprobe": probe, "text_checks": checks, "script_chapters": script_edit,
        "artifacts": [f"captions/{slug}.vtt", f"captions/{slug}.srt",
                      f"captions/{slug}.chapters.txt"],
    }
    (OUT / f"{slug}.timing.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")

    if verbose:
        verdict = ("OK" if probe and probe["ok"] else
                   "STALE RENDER" if probe and probe["ok"] is None else "MISMATCH")
        pr = ("no render" if not probe else
              f"ffprobe {probe['video_s']}s vs cue end {probe['last_cue_end_s']}s "
              f"({verdict})")
        print(f"{slug:<52} {len(plan):>3} beats  {len(cues):>4} cues  "
              f"{timing:<8} {total/60:>5.1f}min  drift mean {mean:>5.1f}s "
              f"worst {worst:>5.1f}s  {pr}")
        for n in notes:
            print(f"    chapters: {n}")
        if checks["script_text"]["absent_from_narration"]:
            print(f"    WARNING beats absent from ## Narration: "
                  f"{checks['script_text']['absent_from_narration']}")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", nargs="*", help="slug prefixes, e.g. 05 10")
    ap.add_argument("--all", action="store_true",
                    help="every episode with a complete measured audio set")
    ap.add_argument("--include-estimated", action="store_true",
                    help="with --all, also emit PROVISIONAL tracks for episodes "
                         "whose narration has not been generated yet")
    ap.add_argument("--no-write-script", action="store_true",
                    help="do not correct the stamps in scripts/<slug>.md")
    ap.add_argument("--check", help="mp4 to ffprobe against (single episode only)")
    a = ap.parse_args()

    if a.all:
        slugs = []
        for s in episode_slugs():
            try:
                plan, _ = load_plan(s)
            except SystemExit:
                continue
            _, timing, _ = beat_durations(s, plan)
            if timing in MEASURED_TIMINGS or a.include_estimated:
                slugs.append(s)
    else:
        slugs = [resolve(p) for p in a.episodes]

    # Rule 0: a run that did nothing must not exit 0.
    if not slugs:
        print("error: no episodes selected - refusing to exit 0 having done "
              "nothing.", file=sys.stderr)
        return 2

    recs = [process(s, write_script=not a.no_write_script,
                    check=a.check if len(slugs) == 1 else None) for s in slugs]

    OUT.mkdir(exist_ok=True)
    (OUT / "index.json").write_text(json.dumps({
        "generated_for": [r["episode"] for r in recs],
        "episodes": recs,
    }, indent=2), encoding="utf-8")

    bad = [r["episode"] for r in recs
           if r["ffprobe"] and r["ffprobe"]["ok"] is False]
    if bad:
        print(f"\nFAIL: last cue does not land on the video duration for {bad}",
              file=sys.stderr)
        return 1
    print(f"\n{len(recs)} episode(s) -> captions/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ==========================================================================
# Burn-in (PROPOSED - nothing here is wired into assemble.py yet)
# ==========================================================================
# Most of this category is watched muted, so the caption is how the video is
# read. The renderer already draws every frame; a caption panel is one paste.
#
# The panel is built ONCE PER CUE and pasted into the frame's bounding box.
# That is the whole performance story: composing a full 1920x1080 RGBA overlay
# per frame costs ~20 ms (+30%); pasting a cached panel costs ~1.4 ms (+2.2%),
# about +20 seconds on a ~15 minute episode render.
#
# Identity comes from visuals/design.py, not from a subtitle renderer: INK at
# 70% for the plate, TEXT for the words, a 3px CYAN underline - the same accent
# the lower thirds already use. (ffmpeg's `subtitles` filter is not an option
# here regardless: the installed ffmpeg 8.1.1 is built without libass.)

CAP_FONT_SIZE = 46
CAP_LINE_H = 62
CAP_PAD = 26
CAP_BOTTOM = 118          # clear of YouTube's progress bar and the safe area
CAP_PLATE_ALPHA = 178     # 70%


class Burner:
    """Draws the caption for a given global timestamp onto a rendered frame."""

    def __init__(self, cues, w=None, h=None):
        from design import W as _W, H as _H
        self.cues = cues
        self.W, self.H = w or _W, h or _H
        self._panels = {}
        self._i = 0

    def _panel(self, text):
        if text in self._panels:
            return self._panels[text]
        from PIL import Image, ImageDraw
        from design import INK, TEXT, CYAN, F_LABEL
        import segments_ext as SX
        f = SX.font(F_LABEL, CAP_FONT_SIZE)
        lines = wrap(text)[:MAX_LINES] or [text]
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bw = int(max(probe.textlength(l, font=f) for l in lines) + CAP_PAD * 2)
        bh = int(CAP_LINE_H * len(lines) + CAP_PAD * 2)
        p = Image.new("RGBA", (bw, bh + 3), (0, 0, 0, 0))
        d = ImageDraw.Draw(p)
        d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=10,
                            fill=(*INK, CAP_PLATE_ALPHA))
        d.line([0, bh, bw, bh], fill=(*CYAN, 150), width=3)
        for k, l in enumerate(lines):
            tw = d.textlength(l, font=f)
            d.text(((bw - tw) / 2, CAP_PAD + k * CAP_LINE_H), l, font=f,
                   fill=(*TEXT, 255))
        pos = (int((self.W - bw) / 2), self.H - CAP_BOTTOM - p.height)
        self._panels[text] = (p, pos)
        return self._panels[text]

    def draw(self, img, t):
        """Paste the cue live at global time `t`. Cues are ordered and
        contiguous, so this walks forward and never rescans."""
        while self._i < len(self.cues) and self.cues[self._i]["end"] <= t:
            self._i += 1
        if self._i >= len(self.cues):
            return img
        c = self.cues[self._i]
        if t < c["start"]:
            return img
        p, pos = self._panel(c["text"])
        img.paste(p, pos, p)
        return img


def burner_for(slug: str):
    """Build a Burner from the measured audio. Hard-fails rather than returning
    an empty overlay - a silent no-op burn is the 'runs but inert' defect."""
    plan, _ = load_plan(slug)
    durs, timing, _ = beat_durations(slug, plan)
    if timing not in MEASURED_TIMINGS:
        raise SystemExit(f"error: {slug} narration is {timing!r}; refusing to burn "
                         f"captions whose timing is not measured.")
    return Burner(build_cues(plan, durs)), [sum(durs[:i]) for i in range(len(plan))]
