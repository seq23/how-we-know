"""Whisper Almanac's final frame check: a sleep picture, judged as one.

    .venv/bin/python visuals/whisper_frame_check.py SLUG            # check the render
    .venv/bin/python visuals/whisper_frame_check.py SLUG --restore  # a set-aside render
                                                                    # that now passes goes back in line

How We Know's gate (visuals/frame_check.py) demands the named animal clearly
in EVERY frame of a documentary. A 1-2 hour dimmed sleep video samples ~300
frames, and one frame of open water failed the whole video (W45: the held
render failed at 0:01 on "bare seabed"). That gate stays exactly as it is for
How We Know. This one is Whisper Almanac's (config/whisper_almanac.json
`picture_gate`, 9 Nov 2026):

  HARD FAILS, any single frame:
    * any word on screen (Apple Vision OCR, as How We Know);
    * black pillarbox bars (frame_check.black_bars);
    * a NEAR-BLACK frame: mean luma of the dimmed frame under
      `near_black_luma`, measured here in code, never by the model (her
      6 Nov rule: dim moving footage, never a dark screen);
    * the judge says it is not real camera footage, or shows text, a
      diagram, graphic, illustration or CG particle/starfield filler.
  THE SUBJECT: ambient frames (open water, seabed, silt, sky) pass, but at
    least `subject_share_min` of the sampled frames must show real footage
    of the named subject, or the video fails (SUBJECT_SHARE_LOW).

The judge is the free vision route only (frame_check.ask_vision: Gemini free
tier, then $0 OpenRouter vision models; never paid). It answers each frame
with SEPARATE fields - real_footage, graphic_or_text, subject_visible - so
one combined "pass" cannot hide which rule a frame broke. No model answering
is FRAME_CHECK_UNAVAILABLE: the render is kept and the next batch checks it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import frame_check as FC                                    # noqa: E402

PictureCheckFailed = FC.PictureCheckFailed
FrameCheckUnavailable = FC.FrameCheckUnavailable
FIELDS = ("real_footage", "graphic_or_text", "subject_visible")


def gate_cfg() -> dict:
    c = json.load(open(os.path.join(ROOT, "config", "whisper_almanac.json")))
    g = c["picture_gate"]
    return {"subject_share_min": float(g["subject_share_min"]),
            "near_black_luma": float(g["near_black_luma"])}


def frame_luma(paths: list[str]) -> dict[str, float]:
    """{path: mean luma 0-255} of each sampled frame."""
    from PIL import Image, ImageStat                         # noqa: PLC0415
    return {p: ImageStat.Stat(Image.open(p).convert("L")).mean[0] for p in paths}


def question(subject: str, n: int) -> str:
    return (
        f"These {n} images are frames from a dim, slow SLEEP video whose picture "
        f"is real moving camera footage of: {subject}. Dark, quiet frames are "
        "expected and are fine.\n"
        "Answer three separate questions for each frame:\n"
        "  real_footage: is it real camera footage or a real photograph (true), "
        "rather than a drawing, render, animation or graphic (false)? Natural "
        "marine snow, silt, bubbles, plankton, rain, stars in a real night sky "
        "are real footage.\n"
        "  graphic_or_text: does it show ANY text, caption, title, logo, "
        "diagram, chart, illustration, engraving, or computer-generated "
        "particles/starfield/abstract filler?\n"
        "  subject_visible: is the named subject (or a closely matching one) "
        "visible in the frame? Open water, bare seabed, empty sky or a dark "
        "frame with no subject is false.\n"
        'Answer with a JSON array, one object per frame in order: '
        '[{"frame": 1, "real_footage": true, "graphic_or_text": false, '
        '"subject_visible": true, "why": "short reason"}, ...] and nothing else.')


def _valid(rows: list[dict]) -> bool:
    return all(isinstance(r.get(f), bool) for r in rows for f in FIELDS)


def gemini_judge(frames: list[str], subject: str) -> list[dict] | None:
    """[{real_footage, graphic_or_text, subject_visible, why}] per frame, or None."""
    return FC.ask_vision(frames, question(subject, len(frames)), valid=_valid)


# ------------------------------------------- does it LOOK like its set? (19 Nov 2026)
# Her question after the "not luxury enough" Money video: why was it not caught?
# Every gate checked licence, words, darkness, length and share - none judged
# whether a clip LOOKS like its set. A tag word was the only test. This is that
# judgement, by the free vision route only (frame_check.ask_vision), asked at
# harvest (research/imagery_stock_video) and on a kit's contact sheet before
# upload (loop/whisper_upload.look_check). The question is config
# (calm_footage.set_rules.<set>.look), never code per lane.

def look_question(look: str, subject: str, n: int) -> str:
    return (
        f"These {n} images are frames of stock footage chosen for a sleep video. "
        f"Each must read, at a glance, as: {look}. The footage is meant to show: {subject}.\n"
        "For each frame answer looks (true only when a viewer would see exactly that "
        "at a glance; false for anything ordinary, plain, tourist, public, crowded or "
        "off-subject) and a short why.\n"
        'Answer with a JSON array, one object per frame in order: '
        '[{"frame": 1, "looks": true, "why": "short reason"}, ...] and nothing else.')


def look_judge(frames: list[str], subject: str, look: str) -> list[dict] | None:
    """[{looks, why}] per frame from the free vision route, or None when none answered."""
    return FC.ask_vision(frames, look_question(look, subject, len(frames)),
                         valid=lambda rows: all(isinstance(r.get("looks"), bool) for r in rows))


def look_failures(frames: list[str], subject: str, look: str, judge=None) -> dict[str, str] | None:
    """{frame path: why} for every frame judged NOT to look like its set; {} when
    all do; None when no free model answered (the caller fails closed)."""
    judge = judge or look_judge
    out: dict[str, str] = {}
    for i in range(0, len(frames), FC.BATCH):
        chunk = frames[i:i + FC.BATCH]
        rows = judge(chunk, subject, look)
        if rows is None or len(rows) != len(chunk):
            return None
        for p, r in zip(chunk, rows):
            if r.get("looks") is not True:
                out[p] = str(r.get("why") or "does not look like its set")[:160]
    return out


def check_frames(frames: list[tuple[float, str]], subject: str, judge=None, reader=None,
                 luma=None, cfg: dict | None = None, second_look=None) -> dict:
    """Pass the sleep picture, or raise PictureCheckFailed naming each failing time."""
    if not frames:
        raise PictureCheckFailed("PICTURE_CHECK_FAILED: no frame was sampled", [])
    g = cfg or gate_cfg()
    judge = judge or gemini_judge
    reader = reader or FC.text_on_screen
    luma = luma or frame_luma
    paths = [p for _, p in frames]
    texts, bars, lum = reader(paths), FC.black_bars(paths), luma(paths)
    hard: dict[float, str] = {}
    for t, p in frames:
        if p in texts:
            hard[t] = f"text on screen: {texts[p]!r}"
        elif p in bars:
            hard[t] = bars[p]
        elif lum[p] < g["near_black_luma"]:
            hard[t] = f"near-black frame (mean luma {lum[p]:.1f} < {g['near_black_luma']:g})"
    subject_frames = 0
    for i in range(0, len(frames), FC.BATCH):
        chunk = frames[i:i + FC.BATCH]
        rows = judge([p for _, p in chunk], subject)
        if rows is None:
            raise FrameCheckUnavailable(
                "FRAME_CHECK_UNAVAILABLE: no free vision model answered (Gemini "
                "free tier); the render is kept but not marked done, and the "
                "next batch checks it again")
        for (t, _), r in zip(chunk, rows):
            why = str(r.get("why") or "")[:100]
            if t not in hard and r.get("graphic_or_text") is not False:
                hard[t] = f"text, graphic or filler: {why}"
            elif t not in hard and r.get("real_footage") is not True:
                hard[t] = f"not real footage: {why}"
            if t not in hard and r.get("subject_visible") is True:
                subject_frames += 1
    if second_look:
        # A free model's flag on ONE sampled frame is confirmed on that same shot before it
        # fails a 1-2 h video: real text, a graphic or CG filler stays on screen for the shot,
        # a misread does not (9 Nov 2026: real NOAA squid called CG at 4:41, "2 Se" read off
        # bare seabed at 22:21 - both clean to the eye; the episode sat held). Measured fails
        # (near-black, black bars) are never second-guessed.
        for t, why in list(hard.items()):
            if not (why.startswith("text") or why.startswith("not real footage")):
                continue
            near = second_look(t)
            if not near:
                continue
            near_paths = [p for _, p in near]
            near_text = reader(near_paths)
            rows = judge(near_paths, subject) or []
            flagged = bool(near_text) or len(rows) != len(near_paths) or any(
                r.get("graphic_or_text") is not False or r.get("real_footage") is not True for r in rows)
            if not flagged:
                del hard[t]
    share = subject_frames / len(frames)
    if hard:
        fl = sorted(hard.items())
        raise PictureCheckFailed(
            "PICTURE_CHECK_FAILED at " + ", ".join(f"{FC.stamp(t)} ({w})" for t, w in fl), fl)
    if share < g["subject_share_min"]:
        raise PictureCheckFailed(
            f"PICTURE_CHECK_FAILED (SUBJECT_SHARE_LOW): {subject_frames} of {len(frames)} "
            f"frames ({share:.0%}) show the subject; at least "
            f"{g['subject_share_min']:.0%} must", [(0.0, "subject share")])
    return {"frames": len(frames), "judged": len(frames), "failed": 0,
            "subject_share": round(share, 3)}


def check(video: str, subject: str, judge=None, reader=None, luma=None,
          every: float = FC.SAMPLE_EVERY) -> dict:
    work = tempfile.mkdtemp(prefix="whisper-frames-")
    try:
        def second_look(t: float) -> list[tuple[float, str]]:
            out = []
            for dt in (-3.0, 3.0):
                t2 = t + dt
                if t2 <= 0:
                    continue
                p = os.path.join(work, f"near{int(t2 * 10):07d}.jpg")
                r = subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error",
                                    "-y", "-ss", f"{t2:.2f}", "-i", video, "-frames:v", "1",
                                    "-vf", "scale=768:-2", "-q:v", "4", p])
                if r.returncode == 0 and os.path.exists(p):
                    out.append((t2, p))
            return out
        return check_frames(FC.sample(video, work, every), subject, judge, reader, luma,
                            second_look=second_look)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# THE PAINT GATE (her ruling 16 Nov 2026). A painted manifesting video is a
# graphic by design, so the judge's "real footage" question cannot apply; its
# own rules, every one measured in code (no model, never unavailable):
#   * no word on screen (OCR) and no black bars, as above;
#   * mean luma inside PAINT_LUMA (10-20 % of 255): dim, never a dark screen;
#   * no pure white: under PAINT_WHITE_MAX of pixels at 240+ on every channel;
#   * warm only: under PAINT_BLUE_MAX of lit pixels blue-dominant.
PAINT_LUMA = (0.10, 0.20)
PAINT_WHITE_MAX = 0.001
PAINT_BLUE_MAX = 0.01


def paint_frame_problem(path: str) -> str | None:
    """The first paint rule this frame breaks, or None."""
    import numpy as np                                      # noqa: PLC0415
    from PIL import Image                                   # noqa: PLC0415
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = float((r * 0.299 + g * 0.587 + b * 0.114).mean() / 255.0)
    if not PAINT_LUMA[0] <= y <= PAINT_LUMA[1]:
        return f"brightness {y:.1%} outside {PAINT_LUMA[0]:.0%}-{PAINT_LUMA[1]:.0%}"
    white = float(((r >= 240) & (g >= 240) & (b >= 240)).mean())
    if white > PAINT_WHITE_MAX:
        return f"pure white on {white:.2%} of the frame"
    lit = (r + g + b) > 60
    blue = float(((b > r + 8) & (b > g + 8) & lit).sum() / max(1, lit.sum()))
    if blue > PAINT_BLUE_MAX:
        return f"blue on {blue:.1%} of the painted area"
    return None


def check_paint_frames(frames: list[tuple[float, str]], reader=None) -> dict:
    if not frames:
        raise PictureCheckFailed("PICTURE_CHECK_FAILED: no frame was sampled", [])
    reader = reader or FC.text_on_screen
    paths = [p for _, p in frames]
    texts, bars = reader(paths), FC.black_bars(paths)
    hard: list[tuple[float, str]] = []
    for t, p in frames:
        why = (f"text on screen: {texts[p]!r}" if p in texts else bars.get(p) if p in bars
               else paint_frame_problem(p))
        if why:
            hard.append((t, why))
    if hard:
        raise PictureCheckFailed("PICTURE_CHECK_FAILED (paint gate) at "
                                 + ", ".join(f"{FC.stamp(t)} ({w})" for t, w in hard[:6]), hard)
    return {"frames": len(frames), "gate": "paint"}


def check_paint(video: str, reader=None, every: float = FC.SAMPLE_EVERY) -> dict:
    work = tempfile.mkdtemp(prefix="whisper-paint-frames-")
    try:
        return check_paint_frames(FC.sample(video, work, every), reader)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    """SLUG [--restore]: check the render; with --restore, a render set aside
    by a failed check goes back in line when it now passes (the upload step
    then uploads it on its own schedule - never by hand)."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import datetime as dt                                    # noqa: PLC0415
    import whisper_lane as WL                               # noqa: PLC0415
    import whisper_upload as WU                             # noqa: PLC0415
    slug = argv[0]
    c = WL.cfg()
    video = WL.video_path(slug)
    src = WU.set_aside(slug) if "--restore" in argv else video
    if not src.exists():
        print(f"NAMED STOP WHISPER_RENDER_MISSING: {src} does not exist")
        return 3
    try:
        r = (check_paint(str(src)) if WU.read_kit(slug).get("picture") == "paint"
             else check(str(src), WU.subject(slug, c)))
    except (PictureCheckFailed, FrameCheckUnavailable) as e:
        print(f"NAMED STOP {e}"[:1500])
        return 3
    if "--restore" in argv:
        os.replace(src, video)
        k = WU.read_kit(slug)
        k["frame_check"] = {"passed": True, "file": WU.fingerprint(video),
                            "at": WU.stamp(dt.datetime.now(dt.timezone.utc)),
                            "frames": r["frames"], "subject_share": r.get("subject_share"),
                            "gate": r.get("gate", "whisper")}
        WU.write_kit(slug, k)
        r["restored"] = str(video)
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
