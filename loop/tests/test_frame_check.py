"""A text card in a long-form render must fail the final frame check.

Owner 2026-11-03: the picture is only moving footage or photos of the subject.
visuals/frame_check.py reads the FINISHED render back (one frame every 20 s)
before it is marked done. Proves, on a real video made from a text-card frame:
  1. on the Mac, Apple Vision OCR alone fails it (any word on screen fails);
  2. a vision verdict of "not footage" fails it, and the NAMED STOP lists
     every failing timestamp;
  3. no vision model answering is a NAMED STOP, never a pass;
  4. a frame of footage the judge passes, with no text, passes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))
import frame_check as FC  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

fails, examined = [], 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


tmp = tempfile.mkdtemp(prefix="hwk-frame-check-")
try:
    card = os.path.join(tmp, "card.png")
    img = Image.new("RGB", (1920, 1080), (8, 20, 34))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 110)
    except OSError:
        f = ImageFont.load_default()
    d.text((160, 380), "WHY OXYGEN LIMITS SIZE", font=f, fill=(235, 240, 245))
    d.text((160, 560), "THE TEMPERATURE CLUE", font=f, fill=(150, 200, 220))
    img.save(card)
    video = os.path.join(tmp, "card.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1",
                    "-framerate", "5", "-i", card, "-frames:v", "125", "-vf",
                    "format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", video],
                   check=True)                                    # 25 s: frames at 0:01, 0:21

    passing_judge = lambda frames, subject: [(True, "footage")] * len(frames)   # noqa: E731
    failing_judge = lambda frames, subject: [(False, "a text card")] * len(frames)  # noqa: E731
    no_text = lambda paths: {}                                                   # noqa: E731

    # 1. OCR alone (the Mac) fails the text card, whatever the model says.
    if FC.ocr_available():
        try:
            FC.check(video, "giant isopod", judge=passing_judge)
            check("OCR fails a text card", False, "passed")
        except FC.PictureCheckFailed as e:
            check("OCR fails a text card", "text on screen" in str(e) and len(e.failures) == 2,
                  str(e))
    else:
        print("  NOTE  no Apple Vision OCR on this host; reader 1 runs on the Mac")

    # 2. A failing verdict fails the render and names every timestamp.
    try:
        FC.check(video, "giant isopod", judge=failing_judge, reader=no_text)
        check("a text card fails the frame check", False, "passed")
    except FC.PictureCheckFailed as e:
        check("a text card fails the frame check",
              e.code == "PICTURE_CHECK_FAILED" and "0:01" in str(e) and "0:21" in str(e),
              str(e))

    # 3. No vision model answering is a NAMED STOP, never a pass.
    try:
        FC.check(video, "giant isopod", judge=lambda f, s: None, reader=no_text)
        check("no vision model is a NAMED STOP", False, "passed")
    except FC.FrameCheckUnavailable as e:
        check("no vision model is a NAMED STOP", e.code == "FRAME_CHECK_UNAVAILABLE", str(e))

    # 4. Footage the judge passes, with no text on it, passes.
    foot = os.path.join(tmp, "foot.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "mandelbrot=size=640x360:rate=5", "-frames:v", "50",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", foot],
                   check=True)
    try:
        r = FC.check(foot, "giant isopod", judge=passing_judge, reader=no_text)
        check("passing footage passes", r["failed"] == 0 and r["judged"] == 1, str(r))
    except Exception as e:                                        # noqa: BLE001
        check("passing footage passes", False, repr(e))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if examined == 0:
    print("FAIL: examined zero checks")
    sys.exit(1)
if fails:
    for f in fails:
        print("FAIL:", f)
    sys.exit(1)
print(f"frame check: {examined} check(s) passed")
