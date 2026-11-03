"""The final frame check: a long-form render is not done until its frames prove it.

Owner ruling 2026-11-03: the long-form picture is only moving footage or photos
of the subject. visuals/longform_picture.py builds it that way; this reads the
FINISHED file back and checks, because a rule the output is never checked
against is a wish.

One frame every SAMPLE_EVERY seconds. Each frame must pass two readers:
  1. Apple Vision OCR (research/imagery_video.ocr, on the Mac): any word on
     screen fails the frame - a long-form picture carries no text at all.
  2. A vision model on the free route (Gemini free tier only - a text-only
     model cannot see a frame, so none is asked): "is this real footage or a
     photograph of <subject>? any text, diagram, graphic or abstract filler?"

Any failing frame fails the render: NAMED STOP PICTURE_CHECK_FAILED, listing
every failing timestamp. No vision model answering is NAMED STOP
FRAME_CHECK_UNAVAILABLE - the render is not marked done, and the next batch
asks again.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SAMPLE_EVERY = 20.0
BATCH = 8                   # frames per model request
MIN_WORD = 3                # OCR tokens shorter than this are noise


class PictureCheckFailed(RuntimeError):
    code = "PICTURE_CHECK_FAILED"

    def __init__(self, msg: str, failures: list[tuple[float, str]]):
        super().__init__(msg)
        self.failures = failures


class FrameCheckUnavailable(RuntimeError):
    code = "FRAME_CHECK_UNAVAILABLE"


def stamp(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def duration(video: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", video], capture_output=True, text=True)
    return float(out.stdout.strip())


def sample(video: str, workdir: str, every: float = SAMPLE_EVERY) -> list[tuple[float, str]]:
    """[(seconds, jpg)] - one frame per `every` seconds, from 1 s in."""
    total = duration(video)
    out, t = [], 1.0
    while t < total:
        p = os.path.join(workdir, f"f{int(t):05d}.jpg")
        subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                        "-vf", "scale=768:-2", "-q:v", "4", p], check=True)
        out.append((t, p))
        t += every
    return out


# ------------------------------------------------------------------ reader 1

def ocr_available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc"))


def text_on_screen(paths: list[str]) -> dict[str, str]:
    """{path: words found} for every frame carrying any word. {} off the Mac."""
    if not ocr_available():
        return {}
    sys.path.insert(0, os.path.join(ROOT, "research"))
    import imagery_video as IV                         # noqa: PLC0415
    found = {}
    for p, boxes in IV.ocr(paths).items():
        words = [b.get("t", "") for b in boxes
                 if len(re.sub(r"[^A-Za-z0-9]", "", b.get("t", ""))) >= MIN_WORD]
        if words:
            found[p] = " ".join(words)[:80]
    return found


# ------------------------------------------------------------------ reader 2

def question(subject: str) -> str:
    return (
        f"These {{n}} images are frames from a documentary whose picture must be "
        f"ONLY real moving footage or real photographs of: {subject}.\n"
        "For each frame answer: is it real camera footage or a real photograph "
        "of that subject (or a closely matching one)? Does it show ANY text, "
        "caption, title, diagram, chart, graphic, illustration, engraving, or "
        "computer-generated particles/starfield/abstract filler? Natural marine "
        "snow, silt, bubbles or plankton in real underwater footage are NOT "
        "filler and do not fail a frame. A frame passes only if it is real "
        "footage/photo of the subject with none of the failing things.\n"
        'Answer with a JSON array, one object per frame in order: '
        '[{"frame": 1, "pass": true, "why": "short reason"}, ...] and nothing else.')


def gemini_judge(frames: list[str], subject: str) -> list[tuple[bool, str]] | None:
    """[(pass, why)] per frame from a free Gemini vision model, or None."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    sys.path.insert(0, HERE)
    import shot_list                                    # noqa: PLC0415
    shot_list._keys()                                   # GEMINI_API_KEY from .secrets
    import llm_router as R                              # noqa: PLC0415
    content = [{"type": "text", "text": question(subject).replace("{n}", str(len(frames)))}]
    for p in frames:
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    import time                                         # noqa: PLC0415
    tries = [(m, wait) for wait in (0, 60, 120) for m in R.gemini_models()]
    for k, (model, wait) in enumerate(tries):
        # The free tier answers 429/503 under load; two slower rounds before
        # FRAME_CHECK_UNAVAILABLE (measured 2026-11-03: a retry 90 s later passed).
        if wait and model == R.gemini_models()[0]:
            time.sleep(wait)
        resp, why = R._gemini_try(model, [{"role": "user", "content": content}], 120, 0.0)
        if not resp:
            continue
        text = resp["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", text, re.S)
        try:
            rows = json.loads(m.group(0)) if m else []
        except ValueError:
            rows = []
        if len(rows) == len(frames):
            return [(bool(r.get("pass")), str(r.get("why") or "")[:120]) for r in rows]
    return None


# ------------------------------------------------------------------- the gate

def check_frames(frames: list[tuple[float, str]], subject: str, judge=None,
                 reader=None) -> dict:
    """Pass every frame, or raise PictureCheckFailed naming each failing time."""
    if not frames:
        raise PictureCheckFailed("PICTURE_CHECK_FAILED: no frame was sampled", [])
    judge = judge or gemini_judge
    reader = reader or text_on_screen
    texts = reader([p for _, p in frames])
    failures: list[tuple[float, str]] = []
    for t, p in frames:
        if p in texts:
            failures.append((t, f"text on screen: {texts[p]!r}"))
    judged = 0
    for i in range(0, len(frames), BATCH):
        chunk = frames[i:i + BATCH]
        verdicts = judge([p for _, p in chunk], subject)
        if verdicts is None:
            raise FrameCheckUnavailable(
                "FRAME_CHECK_UNAVAILABLE: no free vision model answered (Gemini "
                "free tier); the render is kept but not marked done, and the "
                "next batch checks it again")
        for (t, _), (ok, why) in zip(chunk, verdicts):
            judged += 1
            if not ok and not any(ft == t for ft, _ in failures):
                failures.append((t, why or "not footage of the subject"))
    if failures:
        failures.sort()
        raise PictureCheckFailed(
            "PICTURE_CHECK_FAILED at " + ", ".join(
                f"{stamp(t)} ({why})" for t, why in failures), failures)
    return {"frames": len(frames), "judged": judged, "failed": 0}


def check(video: str, subject: str, judge=None, reader=None,
          every: float = SAMPLE_EVERY) -> dict:
    work = tempfile.mkdtemp(prefix="hwk-frames-")
    try:
        return check_frames(sample(video, work, every), subject, judge, reader)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def check_variety(video: str) -> dict:
    """The variety rule (owner 2026-11-03: "a new image every 30 sec at least or
    20"), read from the shot record assemble.py keeps beside the render: a new
    distinct shot at every 20 s sample, no source moment again inside 3 min,
    no subject over ~25% while another had material. NAMED STOP
    PICTURE_CHECK_FAILED with every finding."""
    sys.path.insert(0, HERE)
    import longform_picture as LP                       # noqa: PLC0415
    rec_p = video + ".footage.json"
    try:
        shots = json.load(open(rec_p))["shots"]
    except (OSError, ValueError, KeyError) as e:
        raise PictureCheckFailed(f"PICTURE_CHECK_FAILED: no shot record beside "
                                 f"{video} ({e}) - variety cannot be proven", [])
    probs = LP.variety_problems(shots, SAMPLE_EVERY)
    if probs:
        raise PictureCheckFailed("PICTURE_CHECK_FAILED (variety): " + "; ".join(probs[:12]),
                                 [(0.0, p) for p in probs])
    return {"shots": len(shots), "variety": "ok"}


def check_render(video: str, slug: str) -> dict:
    """Variety from the record first (free, exact), then every 20 s frame."""
    v = check_variety(video)
    return {**check(video, subject_of(slug)), **v}


def subject_of(slug: str) -> str:
    sys.path.insert(0, HERE)
    import shot_list                                    # noqa: PLC0415
    subs = shot_list.subjects(slug)
    title = shot_list.title_of(slug)
    return f"{', '.join(subs)} (the video is titled {title!r})" if subs else title


if __name__ == "__main__":
    # frame_check.py VIDEO SLUG [--restore]: --restore moves a render set aside
    # as .picture-check-failed back into place when it now passes.
    vid, slug = sys.argv[1], sys.argv[2]
    if "--restore" in sys.argv and vid.endswith(".picture-check-failed"):
        final = vid[: -len(".picture-check-failed")]
        try:
            v = check_variety(vid) if os.path.exists(vid + ".footage.json") else {}
            r = {**check(vid, subject_of(slug)), **v}
        except (PictureCheckFailed, FrameCheckUnavailable) as e:
            print(f"NAMED STOP {e}")
            raise SystemExit(3)
        os.replace(vid, final)
        if os.path.exists(vid + ".footage.json"):
            os.replace(vid + ".footage.json", final + ".footage.json")
        print(json.dumps({**r, "restored": final}))
        raise SystemExit(0)
    try:
        print(json.dumps(check_render(vid, slug)))
    except (PictureCheckFailed, FrameCheckUnavailable) as e:
        print(f"NAMED STOP {e}")
        raise SystemExit(3)
