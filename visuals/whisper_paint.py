#!/usr/bin/env python3
"""Whisper Almanac's slow painting: the picture for NEW manifesting videos.

    .venv/bin/python visuals/whisper_paint.py SLUG --seconds 60 OUT.mp4   # a silent proof

Her ruling 16 Nov 2026: every NEW manifesting video (Neville, Money) shows a
slow abstract painting made here in code ($0) for 30 days from the first
paint upload, then it is judged on the channel's own day-30 numbers; footage
comes back only if paint clearly underperforms. Forward only: nothing already
rendered is re-rendered ("we wont go back and redo anything if it passes the
test only move forward"). Sleep history, ocean and food keep their footage.

The spec (research, 16 Nov 2026), each line enforced below or in the gate:
  * one soft stroke every STROKE_EVERY (4-8 s), each fading in over FADE_S
    (2-3 s); no cuts: the canvas only ever gains paint;
  * the frame stays dim: mean luma 10-20 % (LUMA_BAND); a stroke that would
    lift it out of the band is glazed down toward the ground as it fades in;
  * warm only: amber, ochre, umber, deep rose (PALETTE); no blue, no pure white;
  * a different painting per video: the seed is the video's topic (slug),
    which picks the palette weights, the stroke direction and the composition;
  * our own marks: bristle strokes along random curves. Nothing is copied or
    traced from anyone's paintings.
Frames are streamed straight into ffmpeg at FPS (unchanged frames are reused),
so no frame files touch the disk.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS = 1280, 720, 10
STROKE_EVERY = (4.0, 8.0)
FADE_S = (2.0, 3.0)
LUMA_BAND = (0.10, 0.20)          # mean luma as a share of 255, the gate's band
TARGET = (0.125, 0.175)           # where the painter keeps it, inside the band
GROUND = (18, 14, 11)             # candle-dark #120E0B
PALETTE = {                       # warm only: hue 0-50 degrees, never white
    "amber": (200, 128, 52),
    "ochre": (176, 132, 58),
    "umber": (112, 70, 38),
    "deep rose": (140, 62, 66),
    "sienna": (150, 78, 46),
}


def seed_of(slug: str) -> int:
    return int(hashlib.sha256(slug.encode()).hexdigest()[:12], 16)


def luma(a: np.ndarray) -> float:
    """Mean Rec. 601 luma as a share of 255."""
    return float((a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114).mean() / 255.0)


class Painter:
    """One painting: a seeded composition that gains a stroke at a time."""

    def __init__(self, slug: str):
        self.rng = random.Random(seed_of(slug))
        r = self.rng
        names = list(PALETTE)
        self.weights = [r.uniform(0.3, 1.0) for _ in names]
        self.names = names
        self.angle = r.uniform(-math.pi, math.pi)          # the painting's prevailing direction
        self.centre = (r.uniform(0.3, 0.7) * W, r.uniform(0.35, 0.65) * H)
        self.canvas = self.underpainting()

    def underpainting(self) -> np.ndarray:
        """A soft warm wash, already inside the brightness band at 0:00."""
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        cx, cy = self.centre
        d = np.sqrt(((xx - cx) / W) ** 2 + ((yy - cy) / H) ** 2)
        glow = np.clip(1.0 - d * 1.6, 0, 1)[..., None]
        warm = np.array(PALETTE["umber"], np.float32)
        base = np.array(GROUND, np.float32)
        c = base + (warm - base) * (0.25 + 0.75 * glow)
        return self.fit(c)

    def fit(self, c: np.ndarray) -> np.ndarray:
        """Glaze toward the ground (or lift) until mean luma sits in TARGET."""
        base = np.array(GROUND, np.float32)
        yb = luma(base[None, None, :])
        for _ in range(4):                     # luma is linear in c; the clip makes it near-linear
            y = luma(c)
            if TARGET[0] <= y <= TARGET[1]:
                break
            want = TARGET[1] - 0.004 if y > TARGET[1] else TARGET[0] + 0.004
            c = np.clip(base + (c - base) * (want - yb) / max(y - yb, 1e-6), 0, 220)
        return c

    def colour(self) -> np.ndarray:
        name = self.rng.choices(self.names, weights=self.weights)[0]
        v = self.rng.uniform(0.75, 1.1)
        return np.clip(np.array(PALETTE[name], np.float32) * v, 0, 220)

    def stroke_mask(self) -> np.ndarray:
        """Alpha 0-1 of one bristle stroke along a random curve."""
        from PIL import Image, ImageDraw, ImageFilter          # noqa: PLC0415
        r = self.rng
        length = r.uniform(0.25, 0.6) * W
        width = r.uniform(28, 120)
        a = self.angle + r.gauss(0, 0.6)
        cx, cy = self.centre
        sx = cx + r.gauss(0, W * 0.22) - math.cos(a) * length / 2
        sy = cy + r.gauss(0, H * 0.22) - math.sin(a) * length / 2
        bend = r.uniform(-0.35, 0.35)
        pts = []
        for i in range(48):
            t = i / 47
            ang = a + bend * (t - 0.5) * 2
            pts.append((sx + math.cos(ang) * length * t, sy + math.sin(ang) * length * t))
        nx, ny = -math.sin(a), math.cos(a)
        # the body: a ribbon that swells and tapers, like a loaded brush
        body = Image.new("L", (W, H), 0)
        left, right = [], []
        for i, (x, y) in enumerate(pts):
            t = i / (len(pts) - 1)
            half = width / 2 * (0.35 + 0.65 * math.sin(math.pi * min(1.0, t * 1.15)) ** 0.6)
            left.append((x + nx * half, y + ny * half))
            right.append((x - nx * half, y - ny * half))
        ImageDraw.Draw(body).polygon(left + right[::-1], fill=200)
        body = body.filter(ImageFilter.GaussianBlur(width * 0.08))
        # the bristle texture inside it: streaks of more and less paint
        tex = Image.new("L", (W, H), 150)
        d = ImageDraw.Draw(tex)
        for _ in range(int(width / 2)):
            off = r.uniform(-width / 2, width / 2)
            dry = r.uniform(0.6, 1.0)                          # where the brush runs dry
            line = [(x + nx * off, y + ny * off) for x, y in pts[: max(2, int(len(pts) * dry))]]
            d.line(line, fill=int(r.uniform(90, 255)), width=max(1, int(r.uniform(2, 6))))
        tex = tex.filter(ImageFilter.GaussianBlur(1.4))
        m = (np.asarray(body, np.float32) / 255.0) * (np.asarray(tex, np.float32) / 255.0)
        return m[..., None] * r.uniform(0.45, 0.75)

    def next_target(self) -> np.ndarray:
        """The canvas once the next stroke has fully faded in (kept in the band)."""
        m = self.stroke_mask()
        c = self.canvas * (1 - m) + self.colour() * m
        return self.fit(c)


def frames(slug: str, seconds: float):
    """Yield (bytes, repeat) for each run of identical frames, in order."""
    p = Painter(slug)
    t = 0.0
    total = int(round(seconds * FPS))
    sent = 0
    still = p.canvas.astype(np.uint8).tobytes()
    while sent < total:
        gap = p.rng.uniform(*STROKE_EVERY)
        fade = min(p.rng.uniform(*FADE_S), gap)
        nf, ng = int(round(fade * FPS)), int(round(gap * FPS))
        old, new = p.canvas, p.next_target()
        for i in range(1, nf + 1):
            if sent >= total:
                return
            s = i / nf
            s = s * s * (3 - 2 * s)                            # smoothstep: no visible step
            yield (old + (new - old) * s).astype(np.uint8).tobytes(), 1
            sent += 1
        p.canvas = new
        still = new.astype(np.uint8).tobytes()
        hold = min(max(0, ng - nf), total - sent)
        if hold:
            yield still, hold
            sent += hold
        t += gap


def render(slug: str, seconds: float, out: Path, audio: Path | None = None) -> Path:
    """The painting, `seconds` long, muxed with `audio` when given."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-g", str(FPS * 10), "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for buf, n in frames(slug, seconds):
            for _ in range(n):
                proc.stdin.write(buf)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg exited {proc.returncode} rendering the painting")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60)
    a = ap.parse_args(argv)
    print(render(a.slug, a.seconds, Path(a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
