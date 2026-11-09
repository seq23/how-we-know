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


# ------------------------------------------------------------------ reader 1b

BAR_FRACTION = 0.06        # each side strip examined
BAR_BLACK = 14             # mean luminance at or below this is a black bar
BAR_PICTURE = 22           # ...when the middle of the frame is brighter than this


def black_bars(paths: list[str]) -> dict[str, str]:
    """{path: why} for every frame carrying black pillarbox bars (a 4:3 picture
    inside the 16:9 frame). Both side strips must be near-black and uniform
    while the middle carries a picture; a dark sea fills the whole frame and
    is not a bar."""
    from PIL import Image, ImageStat                     # noqa: PLC0415
    found = {}
    for p in paths:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        k = max(2, int(w * BAR_FRACTION))
        left = ImageStat.Stat(im.crop((0, 0, k, h)))
        right = ImageStat.Stat(im.crop((w - k, 0, w, h)))
        mid = ImageStat.Stat(im.crop((k, 0, w - k, h)).convert("L"))
        # Black bars are dark in EVERY channel. Deep blue ocean can have
        # very low luminance while its blue channel still carries a picture.
        if (max(left.mean) <= BAR_BLACK and max(right.mean) <= BAR_BLACK
                and max(left.stddev) < 6 and max(right.stddev) < 6
                and mid.mean[0] > BAR_PICTURE):
            found[p] = "black pillarbox bars at the sides"
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
        "filler and do not fail a frame. The subject must be CLEARLY IN FRAME "
        "and the main thing in the picture: fail a frame of bare sediment, rock "
        "or open water with no animal, a frame where ROV or camera hardware "
        "dominates and the animal is small, an animal that is a tiny speck, "
        "or one mostly cut off at the edge. A frame passes only if it is real "
        "footage/photo with the subject clearly visible and none of the "
        "failing things.\n"
        'Answer with a JSON array, one object per frame in order: '
        '[{"frame": 1, "pass": true, "why": "short reason"}, ...] and nothing else.')


_LAST_OK = [""]
# Free OpenRouter models that read images (config/llm_routing.json roster;
# is_free() re-checked on every call).
VISION_FREE = ["nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free"]


def gemini_judge(frames: list[str], subject: str) -> list[tuple[bool, str]] | None:
    """[(pass, why)] per frame from a free Gemini vision model, or None."""
    rows = ask_vision(frames, question(subject).replace("{n}", str(len(frames))))
    if rows is None:
        return None
    return [(bool(r.get("pass")), str(r.get("why") or "")[:120]) for r in rows]


def ask_vision(frames: list[str], prompt: str, valid=None) -> list[dict] | None:
    """One JSON object per frame from the free vision route (Gemini free tier,
    then the $0 OpenRouter vision models), or None when none answered.
    `valid(rows)` may refuse a malformed answer, so the next model is asked.
    Shared with visuals/whisper_frame_check.py."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    sys.path.insert(0, HERE)
    import shot_list                                    # noqa: PLC0415
    or_key = shot_list._keys()                          # GEMINI_API_KEY from .secrets
    import llm_router as R                              # noqa: PLC0415
    content = [{"type": "text", "text": prompt}]
    for p in frames:
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    import time                                         # noqa: PLC0415
    # The model that answered last goes first (measured 2026-11-03: the free
    # tier's flash models hit a 20-a-day cap and every call then spent its
    # time on three 429s before the lite model answered).
    # Then the $0 OpenRouter vision models (measured 2026-11-03: Gemini's free
    # tier ran out at 500 a day; nemotron-3.5-super-vl answered 3 frames in
    # 14 s and failed the text card and the ROV-dominated frame correctly).
    models = R.gemini_models() + [m for m in VISION_FREE if R.is_free(m)]
    if _LAST_OK[0] in models:
        models = [_LAST_OK[0]] + [m for m in models if m != _LAST_OK[0]]
    tries = [(m, wait) for wait in (0, 60, 120) for m in models]
    for k, (model, wait) in enumerate(tries):
        # The free tier answers 429/503 under load; two slower rounds before
        # FRAME_CHECK_UNAVAILABLE (measured 2026-11-03: a retry 90 s later passed).
        if wait and model == models[0]:
            time.sleep(wait)
        if model.startswith(R.GEMINI_PREFIX):
            resp, why = R._gemini_try(model, [{"role": "user", "content": content}], 120, 0.0)
        else:
            try:
                resp = R._post(json.dumps(R.openrouter_body(
                    model, [{"role": "user", "content": content}], 0.0)).encode(), or_key, 120)
                cost = R.reported_cost(resp)
                if cost:                                # never paid: refuse the answer
                    raise RuntimeError(f"{model} reported cost {cost}")
            except Exception as e:                      # noqa: BLE001
                print(f"[vision-route] skipped {model}: {str(e)[:100]}", flush=True)
                resp = None
        if not resp:
            continue
        text = resp["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", text, re.S)
        try:
            rows = json.loads(m.group(0)) if m else []
        except ValueError:
            rows = []
        if (len(rows) == len(frames) and all(isinstance(r, dict) for r in rows)
                and (valid is None or valid(rows))):
            _LAST_OK[0] = model
            return rows
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
    bars = black_bars([p for _, p in frames])
    for t, p in frames:
        if p in texts:
            failures.append((t, f"text on screen: {texts[p]!r}"))
        elif p in bars:
            failures.append((t, bars[p]))
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
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import review_cut
    if probs and review_cut.enabled():
        print("REVIEW VARIETY: " + "; ".join(probs), flush=True)
        return {"shots": len(shots), "variety": "review", "findings": probs}
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
    if "--restore" in sys.argv:
        sys.path.insert(0, os.path.join(ROOT, "loop"))
        import review_cut
        review_cut.refuse_publish()
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
