"""The frame sampler never seeks past the last video frame.

16 Nov 2026: a render whose audio ran past its picture (container 3041.1 s)
was sampled at 3041.0 s; ffmpeg decoded no frame and the whole whisper-upload
stage crashed. A clip with 0.6 s more audio than picture, sampled at a step
that lands in that tail, must sample cleanly.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))
import frame_check as FC  # noqa: E402

d = tempfile.mkdtemp(prefix="frame-end-")
v = os.path.join(d, "v.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:r=24:d=10",
                "-f", "lavfi", "-i", "sine=f=220:d=10.6", "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", v], check=True)
total = FC.duration(v)
try:
    got = FC.sample(v, d, every=total - 1.05)      # second sample lands in the audio-only tail
except subprocess.CalledProcessError as e:
    raise SystemExit(f"FAIL: sampling crashed near the end ({e.cmd[8]} s of {total:.2f})")
if not got or not all(os.path.getsize(p) > 0 for _, p in got):
    raise SystemExit(f"FAIL: no frames sampled ({got})")
print(f"PASS: {len(got)} frame(s) sampled from a {total:.2f} s clip, none past the picture")
