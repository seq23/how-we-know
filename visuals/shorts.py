"""Finished 16:9 episode -> a standalone 9:16 YouTube Short.

Three decisions are encoded here, and each one is a claim that can be checked:

1. REFRAME BY FIT HORIZONTALLY, TRIM THE CAPTION BAND VERTICALLY.
   89% of beats are full-frame motion typography on a dark particle field:
   headings centred across the full 1920, two-column `contrast_pair` layouts that
   use the outer thirds, `zone_column` with a diagram on the left and its key on
   the right. A 9:16 centre crop of a 1080-high frame keeps 607 of 1920 columns -
   32% of the width - and decapitates almost every one of those layouts. So the
   full width is kept: the source frame is scaled whole to 1080 wide and set as a
   band inside the vertical canvas, with a heavily blurred, darkened cover-scale
   of the same frame behind it - which reads as a continuation of the water
   gradient rather than as letterboxing - a wordmark above and this module's own
   burned-in captions below.

   The masters DO carry burned-in captions, and a Short that simply scaled one
   down would show two caption layers. So the bottom of the source frame is
   cropped away before it is scaled. `source_crop_height()` computes exactly how
   much from visuals/captions.py's own plate geometry and from the real cue line
   counts of the beats THIS Short uses - 782 of 1080 rows kept where a two-line
   cue occurs, 844 where every cue is one line - rather than assuming the worst
   case for the whole episode.

   That crop also takes the source credit with it: `species_image` draws it at
   row 975 and `footage.py` draws its strip at rows 991-1038, both below the
   plate, which ends at 962. The credit is not only pixels - it is a field in
   channel/imagery/rights.json and channel/imagery/video_rights.json, the same
   manifests the renderer read. So `resolve_credits()` re-reads it for the picked
   beats and `draw_chrome()` redraws it in the Short's own chrome, larger and more
   legible than the 12px it was reduced to when the whole 1080 was scaled down.
   ATTRIBUTION IS NEVER DROPPED: a beat whose credit cannot be resolved is
   excluded from the Short rather than shown uncredited.

   The honest cost is the picture band: 440 of 1920 rows where a two-line cue
   occurs (168 fewer than the 608 an uncropped scale would give, -27.6%).

2. THE CUT IS A CHAPTER, NOT A SLICE.
   `select_beats` scores every chapter against the script's `## Direct-answer
   lock` sentence and builds hook + answer: cold open and title card, then the
   winning chapter. One question, one answer. `--count N` takes the next-best
   chapters too, so an 8-minute episode yields several Shorts rather than one.

3. AUDIO IS THE ORIGINAL NARRATION WAVS, NEVER A RE-RENDER.
   The selected beats' wavs are concatenated directly. `verify()` then measures
   the finished file and fails if the mean level is not near the -22.9 dBFS the
   narration is normalised to, so the silent-video failure mode cannot ship.

Nothing in this module writes to plans/, audio/, renders/ or any other module's
files. It reads them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

# Captioning is owned by visuals/captions.py. Import its cue splitter rather than
# writing a second one; if that module is not present, fail loudly rather than
# quietly falling back to a divergent implementation.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from captions import chunk_beat as _chunk_beat   # noqa: E402
import captions as CAP                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FPS = 30                      # must match visuals/design.py; asserted at runtime
OUT_W, OUT_H = 1080, 1920
SRC_W, SRC_H = 1920, 1080     # the master's frame; asserted at runtime
MAX_SECONDS = 58.0            # YouTube Shorts cutoff is 60; leave headroom
TARGET_SECONDS = 50.0
HOOK_MAX = 16.0               # cold open + title card; must not eat the answer
NARRATION_DBFS = -22.9        # what voice/ normalises to
DBFS_TOLERANCE = 3.0

# The caption box is the fixed anchor of the vertical composition: it is where a
# phone-held viewer's eye is, and it is clear of the Shorts UI. The picture band
# hangs ABOVE it, so a shorter band (a deeper source crop) moves the picture down
# rather than moving the captions around.
CAP_BOX_Y = 1074
CAP_BOX_H = 470
CREDIT_GAP = 110              # rows between the band and the caption box, where
                              # the redrawn source credit lives
UNCROPPED_BAND_H = 608        # 1080 * 1080/1920, for the cost arithmetic
CAP_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MARK_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
CAP_SIZE = 60
CAP_LINE = 76
CAP_MAXW = 950                # px, not characters: Arial Bold is proportional and
                              # a 24-character count overflows on wide glyphs
CAP_LINES = 2                 # per on-screen cue
WORDMARK = "HOW WE KNOW"
HANDLE = "@howweknowdeep"

# -------------------------------------------------- source geometry (measured)
#
# visuals/captions.py:Burner._panel builds the plate this crop removes, and the
# numbers below are ITS numbers, imported rather than copied - a second module
# keeping its own idea of where the caption plate is, is exactly the defect this
# repo has been clearing out.
#
#   plate height = CAP_LINE_H * lines + CAP_PAD * 2   (+ CAP_RULE for the
#                                                      3px cyan underline)
#   plate bottom = H - CAP_BOTTOM                     = 962
#   plate top    = 962 - plate height                 = 845 (1 line) / 783 (2)
#
# CONFIRMED on the artefact, not taken on faith: a frame pulled from
# renders/07-...-final.mp4 at t=195s (a two-line cue) has its plate's top edge on
# row 783 exactly, and the cyan underline on rows 959-961, the row-mean stepping
# 150.9 -> 114.9 at 783 and 115.6 -> 142.3 at 958.
CAP_RULE = 3                  # captions.py draws a 3px underline below the plate
CAP_MARGIN = 1                # one row of paranoia, then rounded down to even
CREDIT_ROW = SRC_H - 105      # segments_species.py draws its credit here (975)
FOOTAGE_CREDIT_ROW = SRC_H - 90   # footage.py's strip, measured at rows 991-1038


def plate_top(lines: int) -> int:
    """The topmost source row the burned caption plate can occupy for a cue of
    `lines` lines. Rows at or below this must not reach the Short."""
    return SRC_H - CAP.CAP_BOTTOM - (CAP.CAP_LINE_H * lines + CAP.CAP_PAD * 2
                                     + CAP_RULE)


def source_crop_height(max_lines: int) -> int:
    """How many source rows survive, given the tallest cue in THIS Short.

    Not the episode's worst case, and not a fixed constant: a Short whose every
    cue is one line keeps 844 of 1080 rows, one that contains a two-line cue
    keeps 782. The difference is 62 source rows, which is 35 rows of the finished
    Short's picture band - worth computing rather than assuming.
    """
    if max_lines <= 0:
        return SRC_H                      # no burned caption anywhere; keep all
    h = plate_top(max_lines) - CAP_MARGIN
    return h - (h % 2)                    # even, for yuv420p


def band_geometry(crop_h: int) -> tuple[int, int]:
    """(band_y, band_h) for a source cropped to `crop_h` rows and scaled to
    OUT_W wide. The caption box stays put; the band hangs above it."""
    band_h = int(round(OUT_W * crop_h / SRC_W))
    band_h -= band_h % 2
    return CAP_BOX_Y - CREDIT_GAP - band_h, band_h


def cue_lines_for(slug: str, beats_wanted: set[int]) -> tuple[int, dict]:
    """The tallest burned cue over `beats_wanted`, and the per-beat counts.

    Cues come from captions.build_cues - the function the render actually burned
    - so the beat each cue belongs to is read off the cue, never re-derived from
    timestamps, and the two cannot disagree.
    """
    plan, _ = CAP.load_plan(slug)
    durs, timing, _ = CAP.beat_durations(slug, plan)
    if timing != "audio":
        raise ValueError(f"{slug}: narration timing is {timing!r}; the burned "
                         f"cue geometry cannot be reproduced")
    per_beat: dict[int, int] = {}
    for c in CAP.build_cues(plan, durs):
        n = len(CAP.wrap(c["text"])[:CAP.MAX_LINES]) or 1
        per_beat[c["beat"]] = max(per_beat.get(c["beat"], 0), n)
    used = [per_beat.get(i, 0) for i in beats_wanted]
    return (max(used) if used else 0), per_beat


# --------------------------------------------------------------- attribution
#
# The crop above removes every row below 782, and that is where the renderer put
# the source credit: segments_species.py at row 975, footage.py at 991-1038.
# Those credits are DATA before they are pixels - `credit_line` in
# channel/imagery/species.json, `required_credit` in
# channel/imagery/video_rights.json - so they are re-read here from the same
# manifests the renderer read, and redrawn in the Short's own chrome.
#
# A `stat_card` / `definition_card` "Source: ..." line is drawn at row 1010 and
# goes with the same crop. It is an attribution too, and it comes free: it is
# already in the plan's own args.

class CreditUnresolved(Exception):
    """A beat draws a credit that could not be read back. The beat is dropped."""


def _assemble_durations(slug: str, plan: list) -> list[float]:
    """visuals/assemble.py's durations, exactly - including the tail pad it adds
    to the last beat. footage.assign() places cuts against these."""
    import math
    durs, _, _ = CAP.beat_durations(slug, plan)
    need = math.ceil(sum(durs) * FPS)
    have = sum(max(1, int(round(d * FPS))) for d in durs)
    pad = max(0, need - have)
    if pad:
        durs = list(durs)
        durs[-1] += pad / FPS
    return durs


_FOOTAGE_CUTS: dict[str, list] = {}


def footage_cuts(slug: str, plan: list) -> list:
    """Per-beat footage cut, or None. The same deterministic placement
    visuals/assemble.py made when it rendered the master."""
    if slug not in _FOOTAGE_CUTS:
        import footage as FT
        _FOOTAGE_CUTS[slug] = FT.assign(plan, _assemble_durations(slug, plan),
                                        slug)
    return _FOOTAGE_CUTS[slug]


def beat_credits(slug: str, plan: list, index: int) -> list[str]:
    """Every attribution the master burned into this beat's frames.

    Raises CreditUnresolved when the beat is one that DOES draw a credit and the
    manifest can no longer supply it. Returns [] for a beat that draws none.
    """
    b = plan[index]
    seg = b.get("segment")
    args = b.get("args") or {}
    out = []

    cut = footage_cuts(slug, plan)[index]
    if cut is not None:
        # footage.py: "<LABEL>   ·   <CREDIT>", credit = required_credit or org
        credit = cut.get("credit")
        if not credit:
            raise CreditUnresolved(
                f"{slug} beat {index}: footage clip {cut['asset'].get('title')!r} "
                f"carries neither required_credit nor source_org")
        out.append(str(credit))
    elif seg == "species_image":
        import segments_species as SPX
        try:
            rec = SPX.resolve(args.get("subject"), args.get("asset"),
                              int(args.get("pick", 0)))
        except Exception as e:                              # noqa: BLE001
            raise CreditUnresolved(f"{slug} beat {index}: {e}") from e
        line = args.get("credit") or rec.get("credit_line")
        if not line:
            raise CreditUnresolved(
                f"{slug} beat {index}: species record {rec.get('local_file')!r} "
                f"has no credit_line")
        out.append(str(line))

    if args.get("source"):
        out.append(f"Source: {args['source']}")
    return out


def resolve_credits(slug: str, plan: list, picked: list[int]):
    """(ordered unique credit lines, {beat: reason} for beats that must be cut).

    Deduplicated: a Short that uses three sea-cucumber beats off one NOAA clip
    shows one credit, not three.
    """
    lines, seen, dropped = [], set(), {}
    for i in picked:
        try:
            for c in beat_credits(slug, plan, i):
                k = re.sub(r"[^a-z0-9]+", "", c.lower())
                if k and k not in seen:
                    seen.add(k)
                    lines.append(c)
        except CreditUnresolved as e:
            dropped[i] = str(e)
    return lines, dropped


STOPWORDS = set("""a an and are as at be been but by can do does for from had has have how i if in
into is it its not of on one or that the their them then there these they this to was were what when
where which who why will with you your about also more most other some such than very""".split())


# --------------------------------------------------------------------------- io

def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe_duration(path: str) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", path])
    return float(out.stdout.strip())


def probe_stream(path: str) -> dict:
    out = _run(["ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height", "-of", "json", path])
    info = {"width": None, "height": None, "has_audio": False}
    for s in json.loads(out.stdout).get("streams", []):
        if s.get("codec_type") == "video" and info["width"] is None:
            info["width"], info["height"] = s.get("width"), s.get("height")
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def stream_duration(path: str, kind: str) -> float | None:
    out = _run(["ffprobe", "-v", "error", "-select_streams", kind,
                "-show_entries", "stream=duration",
                "-of", "default=nw=1:nk=1", path])
    try:
        return float(out.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def probe_frames(path: str) -> int:
    out = _run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v",
                "-show_entries", "stream=nb_read_frames",
                "-of", "default=nw=1:nk=1", path])
    return int(out.stdout.strip())


def mean_dbfs(path: str) -> float:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    if not m:
        raise RuntimeError(f"volumedetect produced no mean_volume for {path}")
    return float(m.group(1))


# ----------------------------------------------------------------- beat timing

def beat_timeline(plan: list, audio_dir: str) -> list[dict]:
    """Per-beat audio duration and the beat's exact position in the finished MP4.

    visuals/assemble.py renders each beat to `max(1, round(seconds * FPS))` frames,
    so the video timeline is the audio timeline quantised to whole frames. That
    quantisation is replicated here rather than approximated: over 57 beats the
    accumulated difference is a third of a second, which is a visible desync.
    """
    beats, v_cursor = [], 0.0
    for i, b in enumerate(plan):
        wav = os.path.join(audio_dir, f"{i:04d}.wav")
        if not os.path.exists(wav):
            raise FileNotFoundError(f"missing narration wav for beat {i}: {wav}")
        a_dur = max(0.4, probe_duration(wav))
        frames = max(1, int(round(a_dur * FPS)))
        v_dur = frames / FPS
        beats.append({
            "i": i,
            "segment": b.get("segment", ""),
            "heading": b.get("heading", ""),
            "narration": (b.get("narration") or "").strip(),
            "wav": wav,
            "audio_s": a_dur,
            "video_start": v_cursor,
            "video_s": v_dur,
            "frames": frames,
        })
        v_cursor += v_dur
    return beats


# -------------------------------------------------------------- beat selection

def direct_answer(slug: str) -> str:
    path = os.path.join(ROOT, "scripts", f"{slug}.md")
    md = open(path, encoding="utf-8").read()
    m = re.search(r"^##\s+Direct-answer lock\s*$(.*?)(?=^##\s+\S)", md,
                  re.M | re.S)
    if not m:
        raise ValueError(f"{path} has no '## Direct-answer lock' section")
    text = " ".join(ln.strip() for ln in m.group(1).splitlines() if ln.strip())
    if not text:
        raise ValueError(f"{path} has an empty '## Direct-answer lock' section")
    return text


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in STOPWORDS and len(w) > 2]


# Chapters that are production apparatus, not the answer. These headings recur
# across every script in scripts/ and none of them belongs in a Short.
HEADING_BLOCK = {
    "Title card", "Cold open", "Producer POV", "Final editorial note",
    "What to notice in the edit", "Evidence limit", "The right way to see it",
    "Common myths and questions", "Closing",
}

# Narration that talks about the video instead of the subject. These sentences are
# spoken in the 8-minute episode, where the framing is earned; in a 45-second Short
# they are dead air, and letting one through is how a Short becomes a fragment.
META = re.compile(
    r"\b(this episode|the episode|this video|the video|the rest of this|"
    r"the edit\b|editorial|the editor|the script|the narrator|the audience|"
    r"the viewer|this channel|the channel|the visual|the visuals|on screen|"
    r"the caption|b-roll|the footage|expedition footage|montage|"
    r"companion article|the closing|i will not|the image may|"
    r"the next expedition|before the closing)\b", re.I)


def _chapters(beats: list[dict]) -> list[tuple[str, list[int]]]:
    """Contiguous runs of beats sharing a heading, in plan order."""
    runs = []
    for b in beats:
        if runs and runs[-1][0] == b["heading"]:
            runs[-1][1].append(b["i"])
        else:
            runs.append((b["heading"], [b["i"]]))
    return runs


def select_beats(beats: list[dict], answer: str,
                 max_seconds: float = MAX_SECONDS,
                 target_seconds: float = TARGET_SECONDS,
                 rank: int = 0) -> dict:
    """Pick beats that stand alone as one idea: a hook, then an answer.

    The rule, in order:

      1. HOOK - the `Cold open` beats plus the `Title card` beat, in plan order.
         The cold open is already written as a hook ("A red shrimp can look almost
         black in the water where it lives") and the title card is literally the
         question. Capped at HOOK_MAX seconds so it cannot eat the answer.

      2. ANSWER CHAPTER - every chapter is scored as a whole against the script's
         `## Direct-answer lock` sentence: shared content words, IDF-weighted over
         the episode's own beats so "ocean" counts for far less than "wavelengths",
         length-normalised so a chapter cannot win on volume. Scoring the CHAPTER
         rather than the beat matters: a single short hedging line
         ("Ocean color patterns shift gradually") outscores the real explanation on
         a per-beat measure purely because it is short.

      3. ELIGIBILITY - a chapter is out if its heading is production apparatus
         (HEADING_BLOCK) or if a third or more of its beats talk about the video
         rather than the subject (META). This is what keeps "This episode works as
         a problem-solution montage rather than a parade of creatures" out of a
         Short that is not an episode.

      4. BUDGET - within the winning chapter, the best-matching beat is the centre;
         beats are added forward from it first (an idea completes forward), then
         backward, while the budget holds. Hard cap `max_seconds`.
    """
    df = _idf(beats, answer)
    ranked = []
    for heading, idxs in _chapters(beats):
        if heading in HEADING_BLOCK:
            continue
        content = [i for i in idxs if not META.search(beats[i]["narration"])]
        if len(content) < max(1, len(idxs) * 2 // 3):
            continue                              # mostly production notes
        text = " ".join(beats[i]["narration"] for i in content)
        if len(_words(text)) < 20:
            continue                              # too thin to stand alone
        ranked.append((_score(text, df, len(beats)), heading, content))
    ranked.sort(reverse=True, key=lambda r: r[0])
    if len(ranked) <= rank:
        raise ValueError(f"only {len(ranked)} eligible chapter(s); no rank {rank}")
    _, heading, content = ranked[rank]

    # Hook: cold open + title card, budget-capped.
    # The title card is reserved first: it is the question, and a Short that never
    # asks one is a fragment. Cold-open beats then fill whatever budget is left.
    card = [b["i"] for b in beats if b["heading"] == "Title card"][:1]
    hook_s = sum(beats[i]["video_s"] for i in card)
    hook = list(card)
    for b in beats:
        if (b["heading"] == "Cold open" and not META.search(b["narration"])
                and hook_s + b["video_s"] <= HOOK_MAX):
            hook.append(b["i"])
            hook_s += b["video_s"]
    hook.sort()

    budget = min(target_seconds, max_seconds - hook_s)
    best = max(content, key=lambda i: _score(beats[i]["narration"], df, len(beats)))
    lo = hi = content.index(best)
    total = beats[best]["video_s"]
    for direction in ("fwd", "back"):
        while True:
            nxt = hi + 1 if direction == "fwd" else lo - 1
            if not 0 <= nxt < len(content):
                break
            if total + beats[content[nxt]]["video_s"] > budget:
                break
            total += beats[content[nxt]]["video_s"]
            if direction == "fwd":
                hi = nxt
            else:
                lo = nxt
    window = content[lo:hi + 1]

    picked = hook + window
    total += hook_s
    while total > max_seconds and picked[-1] != best:   # trim tail, keep the answer
        total -= beats[picked[-1]]["video_s"]
        picked.pop()
    if total > max_seconds:
        raise ValueError(f"beat {best} alone is {total:.1f}s, over the {max_seconds}s budget")

    return {"anchor": best, "hook": hook, "chapter": heading, "rank": rank,
            "beats": picked, "seconds": total, "eligible_chapters": len(ranked),
            "ranking": [(round(s, 2), h) for s, h, _ in ranked[:5]]}


def _idf(beats: list[dict], answer: str) -> dict:
    """Inverse document frequency of each direct-answer word over the episode's
    own beats. A word the whole episode repeats is not evidence of a match."""
    docs = [set(_words(b["narration"])) for b in beats]
    return {w: 1.0 / (sum(1 for d in docs if w in d) or 1)
            for w in set(_words(answer))}


def _score(text: str, idf: dict, n_beats: int) -> float:
    tw = _words(text)
    if not tw or not idf:
        return 0.0
    hit = sum(idf[w] for w in set(tw) & set(idf))
    return hit * n_beats / (len(tw) ** 0.5)


# ------------------------------------------------------------------- captions

def caption_cues(picked: list[int], by_index: dict) -> list[dict]:
    """Cues for the Short, on the Short's own clock.

    The split into cues is `visuals/captions.py:chunk_beat` - the module that owns
    captioning in this repo. It is imported, not reimplemented: two components each
    keeping their own idea of where a sentence breaks is exactly the defect this
    repo has been clearing out. The only thing added here is a second subdivision,
    because captions.py is sized for a 42-character 16:9 line and a 1080-wide
    vertical frame holds 24. Timing stays character-proportional within the beat,
    which is what captions.py does, so a Short's captions and the episode's .srt
    can never disagree about when a sentence is spoken.
    """
    cues, t = [], 0.0
    for i in picked:
        b = by_index[i]
        dur = b["video_s"]
        text = re.sub(r"\s+", " ", b["narration"]).strip()
        parts = []
        for cue in (_chunk_beat(text, dur) if text else []):
            parts += _subdivide(cue)
        if not parts:
            t += dur
            continue
        total = sum(len(p) for p in parts) or 1
        start = t
        for k, p in enumerate(parts):
            end = t + dur if k == len(parts) - 1 else start + dur * len(p) / total
            cues.append({"text": p, "start": round(start, 3), "end": round(end, 3)})
            start = end
        t += dur
    return cues


_CAP_FONT = None


def _cap_font():
    global _CAP_FONT
    if _CAP_FONT is None:
        _CAP_FONT = ImageFont.truetype(CAP_FONT, CAP_SIZE)
    return _CAP_FONT


def _wrap_px(text: str, maxw: int = CAP_MAXW) -> list[str]:
    """Wrap on measured width, not character count. The same function backs both
    the cue split and the drawing, so a cue can never be broken one way and
    rendered another."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    font, lines, cur = _cap_font(), [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if d.textlength(cand, font=font) <= maxw or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _subdivide(cue: str) -> list[str]:
    """Re-break one 16:9 cue into vertical-format cues of at most CAP_LINES lines.
    Word boundaries only; never mid-word."""
    lines = _wrap_px(cue.upper()) or [cue.upper()]
    return [" ".join(lines[i:i + CAP_LINES])
            for i in range(0, len(lines), CAP_LINES)]


def _outlined(d, x, y, text, font, radius=5):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                d.text((x + dx, y + dy), text, font=font, fill=(0, 8, 14, 235))
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def draw_caption(text: str, path: str) -> None:
    """One transparent 1080 x CAP_BOX_H strip with the caption centred in it.

    Heavy outline, not a plate: most beats sit on near-black, but `zone_column`
    and the upper-water gradients do not, and a Short is judged on a phone held in
    daylight. Upper case at 60px gives ~24 characters a line at a cap height that
    stays readable in a feed thumbnail.
    """
    img = Image.new("RGBA", (OUT_W, CAP_BOX_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _cap_font()
    lines = _wrap_px(text.upper()) or [""]
    y = (CAP_BOX_H - len(lines) * CAP_LINE) // 2
    for ln in lines:
        _outlined(d, (OUT_W - d.textlength(ln, font=font)) / 2, y, ln, font)
        y += CAP_LINE
    img.save(path)


CREDIT_MAXW = 980
CREDIT_SIZE = 28
CREDIT_MIN_SIZE = 18
CREDIT_LINE_H = 36


def _fit_font(d, text: str, size: int, maxw: int) -> ImageFont.FreeTypeFont:
    """Largest MARK_FONT size at or below `size` that holds `text` in `maxw`."""
    while size > CREDIT_MIN_SIZE:
        f = ImageFont.truetype(MARK_FONT, size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 1
    return ImageFont.truetype(MARK_FONT, CREDIT_MIN_SIZE)


def draw_chrome(path: str, credits: list[str], band_y: int, band_h: int) -> None:
    """The persistent furniture: wordmark above the band, the SOURCE CREDITS in
    the gap under it, handle below the captions, and a hairline at each band edge
    so the letterbox reads as a deliberate frame rather than as a video that
    failed to fill the screen.

    The credits are the point of this function existing. The crop that removes
    the master's burned captions also removes the credit the renderer drew at
    source row 975 (or the footage strip at 991-1038), so it is redrawn here from
    the manifests - at 28px on a 1080-wide canvas rather than the ~13px it became
    when a 24px source line was scaled by 0.5625. A dark plate sits behind it
    because what is under the band is blurred water, not reliably dark.
    """
    img = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mark = ImageFont.truetype(CAP_FONT, 40)
    small = ImageFont.truetype(MARK_FONT, 32)

    txt = " ".join(WORDMARK)                       # letter-spaced, like the stills
    d.text(((OUT_W - d.textlength(txt, font=mark)) / 2, 250), txt,
           font=mark, fill=(184, 242, 234, 225))
    d.text(((OUT_W - d.textlength(HANDLE, font=small)) / 2, 1770), HANDLE,
           font=small, fill=(165, 192, 202, 170))
    for y in (band_y - 3, band_y + band_h + 1):
        d.rectangle([0, y, OUT_W, y + 2], fill=(123, 216, 232, 110))

    if credits:
        rows = [(c.upper(), _fit_font(d, c.upper(), CREDIT_SIZE, CREDIT_MAXW))
                for c in credits]
        block_h = CREDIT_LINE_H * len(rows)
        top = band_y + band_h + int((CREDIT_GAP - block_h) / 2)
        wide = max(d.textlength(t, font=f) for t, f in rows)
        d.rounded_rectangle(
            [(OUT_W - wide) / 2 - 22, top - 12,
             (OUT_W + wide) / 2 + 22, top + block_h + 8],
            radius=8, fill=(2, 7, 13, 190))
        y = top
        for t, f in rows:
            x = (OUT_W - d.textlength(t, font=f)) / 2
            d.text((x, y), t, font=f, fill=(190, 214, 222, 245))
            y += CREDIT_LINE_H
        # the same cyan rule segments_species.py sets beside its credit
        d.rectangle([(OUT_W - wide) / 2 - 22, top + block_h + 10,
                     (OUT_W + wide) / 2 + 22, top + block_h + 11],
                    fill=(123, 216, 232, 120))
    img.save(path)


# --------------------------------------------------------------------- render

def source_render_receipt(src: str) -> dict:
    """What is baked into the finished 16:9 render, from its own receipt."""
    path = src + ".render.json"
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path))
    except Exception:
        return {}


def vfilter(crop_h: int, band_y: int, band_h: int) -> str:
    """Crop the burned caption band off the source, then fit what is left.

    The crop happens FIRST and feeds both branches, so the blurred backing plate
    cannot smear caption pixels into the frame either.
    """
    return (
        f"[0:v]crop={SRC_W}:{crop_h}:0:0,split=2[c0][c1];"
        f"[c0]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},gblur=sigma=42,"
        f"eq=brightness=-0.10:saturation=0.85,setsar=1[bg];"
        f"[c1]scale={OUT_W}:{band_h},setsar=1[fg];"
        f"[bg][fg]overlay=0:{band_y}:format=auto,format=yuv420p,"
        # PIN THE COLOUR TAGS. The per-beat parts are concatenated with -c copy,
        # so every part must carry an IDENTICAL SPS. Left to itself x264 tags
        # some beats `bt709/tv` and others `unknown`, the concat then changes
        # format mid-stream, ffmpeg reinitialises the pass-B filter graph at that
        # point - and the single-frame chrome and caption inputs are already at
        # EOF, so from the first concat boundary onward the finished Short lost
        # its wordmark, its credits and its captions. CONFIRMED by probing the
        # parts (p001/p002 `tv,bt709`, p000/p003/p004 `unknown,unknown`) and by
        # reproducing the disappearance on the raw silent.mp4.
        f"setparams=range=tv:colorspace=bt709:color_primaries=bt709:"
        f"color_trc=bt709[v]"
    )


def make_short(slug: str, outdir: str, max_seconds: float = MAX_SECONDS,
               target_seconds: float = TARGET_SECONDS,
               dry_run: bool = False, rank: int = 0) -> dict:
    plan_path = os.path.join(ROOT, "plans", f"{slug}.json")
    audio_dir = os.path.join(ROOT, "audio", slug)
    # The finished episode is the ONLY source. There is no unburned variant to
    # keep in step with it, and there is nothing to re-render: the burned caption
    # band is cropped off below and the credit it took with it is redrawn.
    src = os.path.join(ROOT, "renders", f"{slug}-final.mp4")
    for p in (plan_path, audio_dir, src):
        if not os.path.exists(p):
            raise FileNotFoundError(f"{slug}: required input missing: {p}")

    info = probe_stream(src)
    if (info["width"], info["height"]) != (SRC_W, SRC_H):
        raise ValueError(f"{src} is {info['width']}x{info['height']}, "
                         f"expected {SRC_W}x{SRC_H}")

    plan = json.load(open(plan_path))
    beats = beat_timeline(plan, audio_dir)
    by_index = {b["i"]: b for b in beats}
    sel = select_beats(beats, direct_answer(slug), max_seconds, target_seconds, rank)
    picked = sel["beats"]

    # --- attribution decides the beat list, not the other way round ----------
    # A beat whose credit cannot be read back out of the manifests is dropped
    # rather than shown uncredited. Dropping the anchor would leave a Short with
    # no answer in it, so that is a failure, not a trim.
    credits, dropped = resolve_credits(slug, plan, picked)
    if dropped:
        for i, why in dropped.items():
            print(f"  {slug}: dropping beat {i} - credit unresolved: {why}",
                  file=sys.stderr)
        if sel["anchor"] in dropped:
            raise ValueError(
                f"{slug}: the anchor beat {sel['anchor']} draws a credit that "
                f"cannot be resolved ({dropped[sel['anchor']]}); refusing to cut "
                f"a Short without its answer beat")
        picked = [i for i in picked if i not in dropped]
        sel["beats"] = picked
        sel["dropped_uncredited"] = {str(i): w for i, w in dropped.items()}
        sel["seconds"] = sum(by_index[i]["video_s"] for i in picked)
        credits, _ = resolve_credits(slug, plan, picked)
    if not picked:
        raise ValueError(f"{slug}: every picked beat was dropped for a "
                         f"missing credit; nothing to cut")
    sel["credits"] = credits

    # --- how much of the source frame the burned captions cost us ------------
    cap_lines, _ = cue_lines_for(slug, set(picked))
    crop_h = source_crop_height(cap_lines)
    band_y, band_h = band_geometry(crop_h)
    sel.update({"cap_lines": cap_lines, "source_crop_height": crop_h,
                "source_rows_dropped": SRC_H - crop_h,
                "band_y": band_y, "band_h": band_h,
                "band_rows_lost": UNCROPPED_BAND_H - band_h})

    sel["narration"] = " ".join(by_index[i]["narration"] for i in picked)
    sel["slug"] = slug
    stem = f"{slug}-short" if rank == 0 else f"{slug}-short{rank + 1}"
    if dry_run:
        sel["output"] = os.path.join(outdir, f"{stem}.mp4")
        return sel

    work = os.path.join(outdir, f"{stem}.work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    # --- pass A: cut each beat out of the finished render and reframe it -------
    #
    # THE LENGTH IS SET IN FRAMES, NOT SECONDS. `-t` as an INPUT option is not
    # trustworthy on the installed ffmpeg 8.1.1: measured on
    # renders/05-...-final.mp4, `-ss 0 -t 3.4667` yields 207 frames (6.90s) where
    # 104 are wanted, and `-ss 0.5 -t 3.4667` yields 192 (6.40s) - it is stopping
    # at roughly 2*t, not after t. That put every part after the first out of
    # step with its own narration: the beats' pictures ran seconds behind their
    # audio and `-shortest` silently cut the tail of the picture off to hide it.
    # A beat is an exact whole number of frames by construction (beat_timeline
    # quantises to it), so ask for that number and the ambiguity disappears.
    # --- absorb the quantisation residue into the last beat ------------------
    # Each beat is round(audio * FPS) whole frames, so the video total is the
    # audio total quantised beat by beat. Those roundings mostly cancel - the
    # mean across 51 Shorts is 0.007s - but they do not always: episode 18's
    # rank 1 and 2 came out 0.038s and 0.035s adrift, past the one-frame budget.
    #
    # Same defect class as the episode renders, where per-beat rounding made the
    # video shorter than its own narration and -shortest then clipped the final
    # word. Fix it the same way: give the LAST beat the whole accumulated
    # difference, so the Short's frame count is round(total_audio * FPS) exactly
    # rather than the sum of independently rounded parts.
    #
    # by_index is shared across the ranks cut from one episode, so the
    # correction is applied to a COPY. Mutating it would make rank 2's timing
    # depend on whether rank 1 was cut first.
    by_index = dict(by_index)
    if picked:
        audio_total = sum(by_index[i]["audio_s"] for i in picked)
        want = max(1, int(round(audio_total * FPS)))
        have = sum(by_index[i]["frames"] for i in picked)
        if want != have:
            last = dict(by_index[picked[-1]])
            last["frames"] = max(1, last["frames"] + (want - have))
            by_index[picked[-1]] = last
            print(f"    timing: {want - have:+d} frame(s) onto the last beat so "
                  f"the cut is {want} frames against {audio_total:.3f}s of audio")

    parts = []
    for n, i in enumerate(picked):
        b = by_index[i]
        part = os.path.join(work, f"p{n:03d}.mp4")
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
              "-ss", f"{b['video_start']:.4f}",
              "-i", src, "-an", "-filter_complex",
              vfilter(crop_h, band_y, band_h), "-map", "[v]",
              "-frames:v", str(b["frames"]),
              "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
              part])
        got = probe_frames(part)
        if got != b["frames"]:
            raise RuntimeError(f"{slug} beat {i}: cut {got} frames, wanted "
                               f"{b['frames']} - the picture would not line up "
                               f"with the narration")
        parts.append(part)

    lst = os.path.join(work, "parts.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    silent = os.path.join(work, "silent.mp4")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
          "-safe", "0", "-i", lst, "-c", "copy", silent])

    # --- audio: the ORIGINAL wavs, concatenated. Never regenerated. -----------
    alst = os.path.join(work, "audio.txt")
    with open(alst, "w") as f:
        for i in picked:
            f.write(f"file '{os.path.abspath(by_index[i]['wav'])}'\n")
    narration = os.path.join(work, "narration.wav")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
          "-safe", "0", "-i", alst, "-c", "copy", narration])

    # --- pass B: burn the chrome and captions in, then mux --------------------
    cues = caption_cues(picked, by_index)
    chrome = os.path.join(work, "chrome.png")
    draw_chrome(chrome, credits, band_y, band_h)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", silent, "-i", chrome]
    for n, c in enumerate(cues):
        png = os.path.join(work, f"c{n:03d}.png")
        draw_caption(c["text"], png)
        cmd += ["-i", png]
    cmd += ["-i", narration]

    graph, cur = ["[0:v][1:v]overlay=0:0[base]"], "base"
    for n, c in enumerate(cues):
        nxt = f"o{n}"
        graph.append(f"[{cur}][{n+2}:v]overlay=0:{CAP_BOX_Y}:"
                     f"enable='between(t,{c['start']:.3f},{c['end']:.3f})'[{nxt}]")
        cur = nxt
    graph.append(f"[{cur}]format=yuv420p[v]")

    out = os.path.join(outdir, f"{stem}.mp4")
    cmd += ["-filter_complex", ";".join(graph),
            "-map", "[v]", "-map", f"{len(cues)+2}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", out]
    _run(cmd)
    shutil.rmtree(work, ignore_errors=True)

    sel.update(verify(out))
    sel["output"] = out
    sel["captions"] = len(cues)

    # --- the receipt the validators read ------------------------------------
    # A guard that has to re-derive the beat selection to check the artefact is a
    # second implementation of it. This records what was actually cut: where each
    # source beat landed on the Short's clock, what crop was applied, and which
    # credits the chrome was told to draw.
    t = 0.0
    segments = []
    for i in picked:
        segments.append({"beat": i, "short_start": round(t, 4),
                         "source_start": round(by_index[i]["video_start"], 4),
                         "seconds": round(by_index[i]["video_s"], 4)})
        t += by_index[i]["video_s"]
    sel["segments"] = segments
    sel["source"] = os.path.relpath(src, ROOT)
    with open(out + ".short.json", "w") as fh:
        json.dump(sel, fh, indent=2)
        fh.write("\n")
    return sel


def verify(path: str) -> dict:
    """Measure the finished file. Every one of these is a way a Short silently
    fails: no audio at all, a mismatch that muted it, over the 60s cutoff, or
    the wrong frame shape."""
    info = probe_stream(path)
    dur = probe_duration(path)
    problems = []
    if not info["has_audio"]:
        problems.append("NO AUDIO STREAM")
    else:
        db = mean_dbfs(path)
        if db < -60:
            problems.append(f"audio present but silent ({db} dBFS)")
        elif abs(db - NARRATION_DBFS) > DBFS_TOLERANCE:
            problems.append(f"mean {db} dBFS is not near narration {NARRATION_DBFS}")
    if dur >= 60.0:
        problems.append(f"duration {dur:.2f}s is not under the 60s Shorts cutoff")
    if (info["width"], info["height"]) != (OUT_W, OUT_H):
        problems.append(f"{info['width']}x{info['height']} is not {OUT_W}x{OUT_H}")

    # A/V drift. `-shortest` hides a picture that is longer than its narration by
    # truncating it, and hides nothing at all about a picture that started
    # drifting at the first beat boundary. Measure both streams and refuse more
    # than one frame of difference.
    drift = None
    if info["has_audio"]:
        v = stream_duration(path, "v")
        a = stream_duration(path, "a")
        if v is not None and a is not None:
            drift = round(v - a, 4)
            if abs(drift) > 1.0 / FPS:
                problems.append(f"video and audio differ by {drift:.3f}s, more "
                                f"than one frame ({1 / FPS:.3f}s)")
    return {"duration_s": round(dur, 2),
            "dimensions": f"{info['width']}x{info['height']}",
            "mean_dbfs": mean_dbfs(path) if info["has_audio"] else None,
            "av_drift_s": drift,
            "problems": problems, "ok": not problems}


# ------------------------------------------------------------------------ cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slugs", nargs="+", help="episode slugs, or 'all'")
    ap.add_argument("--out", default=os.path.join(ROOT, "shorts"))
    ap.add_argument("--max-seconds", type=float, default=MAX_SECONDS)
    ap.add_argument("--target-seconds", type=float, default=TARGET_SECONDS)
    ap.add_argument("--count", type=int, default=1,
                    help="Shorts per episode: the top N scoring chapters. "
                         "Rank 2+ is a supporting idea, not the direct answer.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the beat selection without rendering")
    a = ap.parse_args(argv)

    slugs = a.slugs
    if slugs == ["all"]:
        slugs = sorted(
            os.path.basename(p)[: -len("-final.mp4")]
            for p in os.listdir(os.path.join(ROOT, "renders"))
            if p.endswith("-final.mp4")
        )
    # Rule 0: never exit 0 having made nothing.
    if not slugs:
        sys.exit("FAIL: empty input set - no finished -final.mp4 renders to cut from")

    os.makedirs(a.out, exist_ok=True)
    results, failed = [], []
    for slug in slugs:
        for rank in range(a.count):
            try:
                r = make_short(slug, a.out, a.max_seconds, a.target_seconds,
                               a.dry_run, rank)
            except Exception as e:
                # Rank 0 failing is a real failure. Rank 2+ failing just means the
                # episode has only one self-contained idea, which is normal.
                if rank == 0:
                    print(f"FAIL {slug}: {e}", file=sys.stderr)
                    failed.append(slug)
                else:
                    print(f"  {slug}: no rank-{rank + 1} Short ({e})")
                break
            results.append(r)
            if a.dry_run:
                print(f"\n=== {os.path.basename(r['output'])}   [{r['seconds']:.1f}s]"
                      f"  {r['eligible_chapters']} eligible chapters")
                print(f"    chapter: {r['chapter']}")
                print(f"    anchor beat {r['anchor']}, hook {r['hook']}, "
                      f"beats {r['beats']}")
                print(f"    {r['narration'][:360]}")
            else:
                flag = "OK " if r["ok"] else "BAD"
                print(f"{flag} {r['output']}  {r['duration_s']}s  {r['dimensions']}  "
                      f"{r['mean_dbfs']} dBFS  {r['captions']} captions  "
                      f"drift {r['av_drift_s']}s  band {r['band_h']}px "
                      f"(-{r['band_rows_lost']})  {len(r['credits'])} credit(s)"
                      + (f"  PROBLEMS: {r['problems']}" if r["problems"] else ""))

    if not results:
        sys.exit("FAIL: produced nothing")
    bad = [r for r in results if not a.dry_run and not r["ok"]]
    if bad or failed:
        sys.exit(f"FAIL: {len(bad)} bad output(s), {len(failed)} error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
