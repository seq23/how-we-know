"""Thumbnails for How We Know.

A thumbnail competes at about 168x94 in a mobile feed, against faces, saturated
colour and motion. The previous generation of these cards put the entire video
title in a serif over a navy gradient. That is a legible card and a weak
thumbnail: no focal subject, one hue, and far too many words to read at feed
size.

This rebuild does three things differently.

1. ONE SUBJECT. Either a confirmed public-domain NOAA deep-sea photograph
   (Route A) or a procedurally drawn, rim-lit silhouette (Route B). Never a bare
   gradient.
2. FOUR OR FIVE WORDS. The hook is hand-written per episode against that
   episode's "Direct-answer lock", so the thumbnail can never claim more than
   the script proves. The title carries the detail; the thumbnail carries one
   idea.
3. CONTRAST BUILT ON PURPOSE. A directional scrim guarantees the type sits on
   near-black no matter what the photograph does, so the words survive the
   downscale.

Route A imagery is harvested and rights-checked by research/imagery.py and
recorded in channel/imagery/rights.json. Only items whose NOAA item-page credit
resolves to NOAA alone are used. Episodes where no confirmed-PD image exists for
the actual subject fall to Route B rather than borrowing a lookalike animal —
putting a gulper shark under the words "frilled shark" would be exactly the kind
of claim this channel exists to avoid.

Run:  python thumbs.py            (from visuals/)
      python thumbs.py --compare  (also writes the A/B and feed-size sheets)
"""
from __future__ import annotations

import json
import os
import sys
import math
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from design import (INK, DEEP, MID, CYAN, PALE, AMBER, TEXT, MUTED,
                    F_DISPLAY, F_LABEL, mix)

TW, TH = 1280, 720
FEED = (168, 94)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "channel", "thumbnails"))
IMAGERY = os.path.abspath(os.path.join(HERE, "..", "channel", "imagery"))
MANIFEST = os.path.join(IMAGERY, "rights.json")
PROOFS = os.path.join(OUT, "_proofs")

# Georgia Bold is the display face's bold weight — same family as design.F_DISPLAY,
# so we stay inside the type system while gaining the stroke weight a thumbnail needs.
F_DISPLAY_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
if not os.path.exists(F_DISPLAY_BOLD):
    F_DISPLAY_BOLD = F_DISPLAY


def F(path, size):
    return ImageFont.truetype(path, size)


# --------------------------------------------------------------- image grading

def exposure_lift(im: Image.Image, gamma: float) -> Image.Image:
    """Open up a frame whose subject is genuinely dark.

    Needed because the saliency model assumes the subject is the bright,
    coloured thing in dark water -- and one episode's subject is transparency,
    which is precisely an animal that is neither. Rather than lower the
    subject-presence floor until the transparent-animal frame slips under it
    (which would make the guard inert again), lift the picture until the animal
    is genuinely visible. The guard then measures the frame that actually ships.
    """
    if gamma <= 1.0:
        return im.convert("RGB")
    x = np.asarray(im.convert("RGB"), np.float32) / 255.0
    return Image.fromarray((np.clip(x ** (1.0 / gamma), 0, 1) * 255).astype(np.uint8), "RGB")


def grade(im: Image.Image) -> Image.Image:
    """Pull a NOAA frame onto the channel palette without killing its subject.

    A full duotone would look tidy and would also destroy the point of half the
    episodes — the red-shrimp episode needs the shrimp to be red. So this only
    pushes the *shadows* toward DEEP and lifts contrast and saturation slightly.
    The dark water becomes our dark water; the animal stays itself.
    """
    im = im.convert("RGB")
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)

    # shadow tint: strongest where the frame is darkest
    w = np.clip(1.0 - lum * 1.9, 0, 1)[..., None] ** 1.4
    tint = np.array(DEEP, np.float32) / 255.0
    a = a * (1 - w * 0.72) + tint * (w * 0.72)

    # gentle S-curve for punch at feed size
    a = np.clip((a - 0.5) * 1.16 + 0.5, 0, 1)
    out = Image.fromarray((a * 255).astype(np.uint8), "RGB")
    out = ImageEnhance.Color(out).enhance(1.22)
    return out


def cover(im: Image.Image, w: int, h: int, subject=(0.5, 0.5),
          place=(0.5, 0.5), zoom: float = 1.0) -> Image.Image:
    """Scale to fill w x h and crop so that `subject` lands on `place`.

    `subject` is where the animal is in the source frame (0-1); `place` is where
    we want it in the thumbnail. Separating the two is what lets auto_focal find
    the animal while the layout independently decides which half of the frame it
    should occupy.

    zoom > 1 crops in further. An ROV frame is usually a small animal in a large
    volume of water; at 168px that animal disappears entirely unless we push in.
    """
    sw, sh = im.size
    s = max(w / sw, h / sh) * zoom
    nw, nh = max(w, int(round(sw * s))), max(h, int(round(sh * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x = int(round(nw * subject[0] - w * place[0]))
    y = int(round(nh * subject[1] - h * place[1]))
    x = max(0, min(nw - w, x))
    y = max(0, min(nh - h, y))
    return im.crop((x, y, x + w, y + h))


# ------------------------------------------------------------------- saliency

SAL_W, SAL_H = 192, 108


def saliency(im: Image.Image) -> np.ndarray:
    """Where the animal is, as a field rather than a point.

    Normalised to its own peak, which is what you want for LOCATING a subject.
    Returned as a SAL_H x SAL_W map so that everything downstream can ask about
    *extent*, not just location -- which is what lets the zoom be derived rather
    than hand-tuned per episode.
    """
    sal = saliency_abs(im)
    return sal / (sal.max() + 1e-6)


def saliency_abs(im: Image.Image) -> np.ndarray:
    """The same field, on an absolute 0-1 scale rather than normalised to its own peak.

    Normalising by the maximum is right for locating a subject and wrong for
    judging whether one is present: it maps the brightest pixel of an empty
    frame of water to 1.0 just as happily as it maps a lit animal.
    """
    small = im.convert("RGB").resize((SAL_W, SAL_H), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32) / 255.0

    # Distance from the frame's dominant colour, NOT brightness.
    #
    # The first version scored brightness times saturation, which encodes an
    # assumption: that the subject is a lit animal in dark water. Half these
    # photographs are the other polarity -- a dark purple sea cucumber hanging
    # in bright teal water, a black silhouette against a lit seafloor -- and on
    # those the measure locked onto the WATER and reported the animal as
    # background. That is what cropped ep 01's subject through the head: the
    # framer put the brightest region in shot and the animal was not it.
    #
    # Distance from the background colour is polarity-agnostic: it finds the
    # thing that is unlike the water, whether that thing is brighter or darker.
    # The median is the background estimate because water is, by area, most of
    # any ROV still.
    bg = np.median(a.reshape(-1, 3), axis=0)
    wts = np.array([0.6, 0.8, 0.5], np.float32)      # green carries most signal
    d = np.sqrt((((a - bg) ** 2) * wts).sum(-1)) * 1.9

    return np.asarray(Image.fromarray((np.clip(d, 0, 1) * 255).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(3)), np.float32) / 255.0


def _wpct(mass: np.ndarray, q: float) -> float:
    """Weighted quantile of a 1-D marginal, in 0-1 coordinates."""
    c = np.cumsum(mass)
    if c[-1] <= 0:
        return 0.5
    return float(np.searchsorted(c, q * c[-1]) / max(1, len(mass) - 1))


def subject_box(im: Image.Image, keep: float = 0.80) -> tuple[float, float, float, float]:
    """Bounding box of the subject in 0-1 source coordinates.

    This is the fix for the whole defect class. A centroid tells you where to
    point but not how far to push in, so the zoom had to be hand-tuned per
    episode -- and a hand-tuned constant is exactly what cannot adapt when the
    subject is a thin smelt in a wide volume of water. A box has size, so the
    zoom can be derived instead of guessed.

    Marginal weighted quantiles rather than connected components: numpy-only,
    and robust to the speckle of marine snow that a component labeller would
    happily treat as twenty separate subjects.
    """
    sal = saliency(im)
    core = np.where(sal >= np.percentile(sal, 88), sal, 0.0)
    if core.sum() <= 0:
        core = sal
    lo, hi = (1.0 - keep) / 2, 1.0 - (1.0 - keep) / 2
    x0, x1 = _wpct(core.sum(0), lo), _wpct(core.sum(0), hi)
    y0, y1 = _wpct(core.sum(1), lo), _wpct(core.sum(1), hi)
    # never let the box collapse to nothing on a low-contrast frame
    if x1 - x0 < 0.06:
        cx = (x0 + x1) / 2; x0, x1 = cx - 0.03, cx + 0.03
    if y1 - y0 < 0.06:
        cy = (y0 + y1) / 2; y0, y1 = cy - 0.03, cy + 0.03
    return (max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1))


def auto_focal(im: Image.Image, side: str = "left") -> tuple[float, float]:
    """Centre of the subject box. Kept as the single-point view of the same data."""
    x0, y0, x1, y1 = subject_box(im)
    return (float(np.clip((x0 + x1) / 2, 0.03, 0.97)),
            float(np.clip((y0 + y1) / 2, 0.05, 0.95)))


# The free region: the part of the frame the type does not occupy. The scrim
# fades rather than ending hard, so this is inset from the geometric half.
# Derived from the actual type box, not from the geometric half. compose() lays
# the hook into a band 64px in and 0.50*TW wide, so the type really occupies
# 0.05-0.55 of the frame; calling everything past 0.50 "free" is what let the
# midnight-zone depth labels be drawn straight through the hook while the code
# believed they were clear of it.
FREE_X = {"left": (0.57, 0.99), "right": (0.01, 0.43)}
FREE_Y = (0.06, 0.97)

# Absolute saliency at which a pixel counts as subject rather than water,
# and the share of the free half that must reach it. Calibrated against all 61
# manifest assets: frames that read as empty by eye score 0.00-0.04 here, frames
# with a clear animal score 0.35-0.90. Below the floor the picture is water, and
# a card of water is the defect this rebuild exists to fix.
SUBJECT_LEVEL = 0.30
MIN_SUBJECT_ENERGY = 0.07

# Which asset each episode actually resolved to, filled in by build().
chosen: dict = {}
used: set = set()


def frame_subject(src: Image.Image, side: str, fill: float = 0.70,
                  max_upscale: float = 1.30):
    """Choose the crop so the subject actually lands, whole, in the free half.

    Derives the zoom from the subject's size, places the box centre at the free
    region's centre, and -- the part that was missing -- re-checks after the
    crop window is clamped to the source bounds. Clamping is what threw ep 01's
    subject off the top edge: `cover` silently slid the window and told nobody.
    Here, if clamping moves the subject out of the free region, the zoom backs
    off (a looser crop has more room to slide) and we try again.

    Returns (subject, place, zoom) for `cover`, plus the chosen box.
    """
    sw, sh = src.size
    bx0, by0, bx1, by1 = subject_box(src)
    bw, bh = max(1e-3, bx1 - bx0), max(1e-3, by1 - by0)

    fx0, fx1 = FREE_X[side]
    fy0, fy1 = FREE_Y
    fw, fh = fx1 - fx0, fy1 - fy0
    place = ((fx0 + fx1) / 2, (fy0 + fy1) / 2)

    base = max(TW / sw, TH / sh)          # scale that merely fills the frame
    # Zoom so the subject spans `fill` of the free region on its binding axis.
    # This is the number that used to be hand-written per episode.
    want = min((fw * TW) / (bw * sw * base), (fh * TH) / (bh * sh * base)) * fill

    # When the animal already fills the source -- a head-on close-up of a
    # rattail, say -- there is no crop that fits it into half a frame, and
    # trying produced the worst failure of the lot: a wall of scales with the
    # eye hidden behind the words. Frame it against the WHOLE frame instead and
    # let the scrim carry the type over it. A big subject is not a problem to be
    # cropped away.
    oversized = bw > fw or bh > fh
    if oversized:
        want = min(1.0 / (bw * sw * base / TW), 1.0 / (bh * sh * base / TH)) * fill

    zmax = max_upscale / base             # never upscale past sharpness
    zoom = float(np.clip(want, 1.0, zmax))

    # For a frame-filling animal the box centre is a meaningless target -- it is
    # just the middle of the picture, so aiming it at the free half does nothing
    # and centring it buries the animal under the type. What matters on a big
    # subject is its focal detail: the eye, the mouth, the lit edge. Steer by the
    # saliency peak instead, so THAT is what clears the words.
    sub = ((bx0 + bx1) / 2, (by0 + by1) / 2)
    if oversized:
        sal = saliency(src)
        py, px = np.unravel_index(int(np.argmax(sal)), sal.shape)
        sub = (float(px) / (SAL_W - 1), float(py) / (SAL_H - 1))

    for _ in range(14):
        s = base * zoom
        nw, nh = max(TW, int(round(sw * s))), max(TH, int(round(sh * s)))
        x = max(0, min(nw - TW, int(round(nw * sub[0] - TW * place[0]))))
        y = max(0, min(nh - TH, int(round(nh * sub[1] - TH * place[1]))))
        # where the box actually ends up, in output 0-1 coords
        ox0, ox1 = (nw * bx0 - x) / TW, (nw * bx1 - x) / TW
        oy0, oy1 = (nh * by0 - y) / TH, (nh * by1 - y) / TH
        if oversized:
            break
        inside = (ox0 >= fx0 - 0.06 and ox1 <= fx1 + 0.06
                  and oy0 >= fy0 - 0.04 and oy1 <= fy1 + 0.04)
        if inside or zoom <= 1.0001:
            break
        zoom = max(1.0, zoom * 0.88)

    return sub, place, zoom, (bx0, by0, bx1, by1)


def free_region_energy(im: Image.Image, side: str) -> float:
    """Share of the finished frame's free half that carries real subject matter.

    The empty-frame check. Ep 03 was not a cropping accident -- nothing was
    clamped -- it was a frame that contained no subject at all, emitted without
    complaint. Composition must be able to fail loudly, so this measures the
    finished picture and `build` refuses anything that comes back empty.

    The level is ABSOLUTE, deliberately. The first version of this check
    thresholded at a percentile of the frame's own distribution, which meant
    every frame had ~12% of its pixels above its own 88th percentile and the
    guard passed everything put to it -- a validator that runs and asserts
    nothing. Subject presence is a property of the picture, not of its own
    ranking, so it has to be measured against a fixed level.
    """
    sal = saliency_abs(im)
    fx0, fx1 = FREE_X[side]
    band = sal[int(SAL_H * FREE_Y[0]):int(SAL_H * FREE_Y[1]),
               int(SAL_W * fx0):int(SAL_W * fx1)]
    if band.size == 0:
        return 0.0
    return float((band >= SUBJECT_LEVEL).mean())


def scrim(w: int, h: int, side: str = "left", strength: float = 0.90) -> Image.Image:
    """A directional wash of INK so the type always has something to sit on."""
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    if side == "left":
        a = np.clip(1.0 - xx / 0.66, 0, 1) ** 1.45
    else:
        a = np.clip((xx - 0.34) / 0.66, 0, 1) ** 1.45
    a = np.broadcast_to(a, (h, w)).copy()
    a = np.maximum(a * strength, np.clip((yy - 0.62) / 0.38, 0, 1) ** 1.7 * 0.62)
    a = np.maximum(a, np.clip((0.16 - yy) / 0.16, 0, 1) ** 1.7 * 0.30)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = INK
    rgba[..., 3] = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def vignette(w: int, h: int, amount: float = 0.42) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx / w - 0.5) * 1.05) ** 2 + ((yy / h - 0.5) * 1.15) ** 2) / 0.72
    a = np.clip(d - 0.42, 0, 1) ** 1.7 * amount
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


# ------------------------------------------------------- Route B: drawn subjects

def _blur(mask: Image.Image, r: float) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(r))


def rimlit(mask: Image.Image, size, key=(-14, -18), colour=CYAN,
           body=(3, 12, 22), glow=0.55) -> Image.Image:
    """Turn a silhouette mask into a lit object.

    A deep-sea animal in an ROV light is a dark body with a bright edge and a
    soft halo in the surrounding water. That is three layers: an outer blurred
    halo, a near-black body, and a crescent of key light along one edge made by
    subtracting the mask from a shifted copy of itself.
    """
    w, h = size
    out = Image.new("RGBA", size, (0, 0, 0, 0))

    halo = _blur(mask, 46).point(lambda v: int(v * glow * 0.55))
    hl = Image.new("RGBA", size, (*colour, 0))
    hl.putalpha(halo)
    out.alpha_composite(hl)

    bd = Image.new("RGBA", size, (*body, 0))
    bd.putalpha(_blur(mask, 1.1))
    out.alpha_composite(bd)

    shifted = Image.new("L", size, 0)
    shifted.paste(mask, key)
    rim = ImageChops_subtract(shifted, mask)
    rim = _blur(rim, 5).point(lambda v: min(255, int(v * 1.9)))
    rl = Image.new("RGBA", size, (*colour, 0))
    rl.putalpha(rim)
    out.alpha_composite(rl)

    edge = ImageChops_subtract(_blur(mask, 2), mask.point(lambda v: v))
    edge = _blur(edge, 3).point(lambda v: min(255, int(v * 1.3)))
    el = Image.new("RGBA", size, (*PALE, 0))
    el.putalpha(edge.point(lambda v: int(v * 0.5)))
    out.alpha_composite(el)
    return out


def ImageChops_subtract(a: Image.Image, b: Image.Image) -> Image.Image:
    from PIL import ImageChops
    return ImageChops.subtract(a, b)


def marine_snow(d: ImageDraw.ImageDraw, w, h, n, rng, bright=1.0):
    for _ in range(n):
        x, y = rng.random() * w, rng.random() * h
        r = rng.uniform(1.0, 3.4)
        a = int(rng.uniform(25, 120) * bright)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*PALE, a))


def downwelling(w, h, rng, cx=0.62, warm=False):
    """Looking up at the last of the light.

    Route B's first attempt lit these creatures like an ROV subject — a bright
    rim on a black body against black water. At 168x94 that collapses into a
    glowing squiggle. Silhouette against a lit ground is the opposite trade: it
    throws away interior detail, which the feed cannot resolve anyway, and keeps
    outline, which is the only thing it can. It is also what the animal actually
    looks like from below, which matters on a channel about evidence.
    """
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    shaft = np.exp(-((xx - cx) ** 2) / 0.150)
    fall = np.clip(1.0 - yy * 0.82, 0, 1) ** 1.05
    a = np.clip(fall * (0.42 + 0.58 * shaft), 0, 1)

    # Brighter than looks right at 1280px, and correct at 168px. A silhouette is
    # a contrast effect: the shape is only as legible as the water behind it, and
    # the first version lost every creature into its own background in the feed.
    lit = np.array((104, 214, 240) if not warm else (150, 190, 205), np.float32)
    dark = np.array(INK, np.float32)
    rgb = dark[None, None, :] + (lit - dark)[None, None, :] * a[..., None]

    # a few god-rays, so the ground is not a flat wash
    for _ in range(9):
        x0 = rng.uniform(cx - 0.22, cx + 0.22)
        wdt = rng.uniform(0.010, 0.030)
        amp = rng.uniform(0.05, 0.16)
        ray = np.exp(-((xx - x0) ** 2) / (wdt ** 2)) * fall * amp
        rgb += np.array(PALE, np.float32)[None, None, :] * ray[..., None]

    base = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    marine_snow(ImageDraw.Draw(ov), w, h, 190, rng, bright=0.8)
    base.alpha_composite(ov)
    return base


def silhouette(img, mask, colour=(2, 8, 14), edge=True):
    """Lay a near-black body over the lit water, with a faint cool edge so the
    shape does not look like a hole punched in the picture."""
    w, h = img.size
    body = Image.new("RGBA", (w, h), (*colour, 0))
    body.putalpha(_blur(mask, 1.0).point(lambda v: int(v * 0.985)))
    img.alpha_composite(body)
    if edge:
        ring = ImageChops_subtract(_blur(mask, 2.5), mask)
        el = Image.new("RGBA", (w, h), (*CYAN, 0))
        el.putalpha(_blur(ring, 2).point(lambda v: min(255, int(v * 1.15))))
        img.alpha_composite(el)
    return img


def water(w, h, rng, top=MID, bot=INK, glow_at=None):
    """Deep-water ground: vertical falloff, a light source, marine snow."""
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    a = np.array(top, np.float32) * (1 - yy ** 0.72) + np.array(bot, np.float32) * (yy ** 0.72)
    base = Image.fromarray(np.broadcast_to(a, (h, w, 3)).astype(np.uint8), "RGB").convert("RGBA")
    if glow_at:
        cx, cy, rad, peak = glow_at
        yg, xg = np.mgrid[0:h, 0:w].astype(np.float32)
        g = np.clip(1 - np.sqrt((xg - cx) ** 2 + (yg - cy) ** 2) / rad, 0, 1) ** 2.4 * peak
        gl = np.zeros((h, w, 4), np.uint8)
        gl[..., 0], gl[..., 1], gl[..., 2] = CYAN
        gl[..., 3] = (g * 255).astype(np.uint8)
        base.alpha_composite(Image.fromarray(gl, "RGBA"))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    marine_snow(ImageDraw.Draw(ov), w, h, 150, rng)
    base.alpha_composite(ov)
    return base


def _spine_mask(size, pts, widths, taper=True):
    """A tapering tube along a polyline — the basis of every creature body."""
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        w0, w1 = widths[i], widths[i + 1]
        steps = max(2, int(math.hypot(x1 - x0, y1 - y0) / 3))
        for s in range(steps + 1):
            t = s / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            r = (w0 + (w1 - w0) * t) / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return m


def art_shark(size, rng):
    """Ep 12 - a frilled shark: eel-like body, blunt head, six frilled gill
    slits, dorsal set far back. Drawn rather than borrowed, because the NOAA set
    has no confirmed-PD frilled shark and captioning a gulper shark as one would
    be a false claim."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.66)
    pts, wid = [], []
    for i in range(56):
        t = i / 55
        x = w * 0.13 + t * w * 0.86
        y = h * 0.46 + math.sin(t * 4.3 + 0.4) * h * 0.16 * (0.35 + t * 1.1)
        pts.append((x, y)); wid.append(112 * math.sin(min(1, t * 1.18) * math.pi) ** 0.5 + 14)
    m = _spine_mask(size, pts, wid)
    d = ImageDraw.Draw(m)
    hx, hy = pts[0]
    d.ellipse([hx - 30, hy - 58, hx + 120, hy + 58], fill=255)        # blunt head
    d.polygon([(hx - 34, hy - 10), (hx + 40, hy - 30), (hx + 40, hy + 34)], fill=255)
    # pectoral + pelvic fins
    px, py = pts[14]
    d.polygon([(px, py), (px + 130, py + 108), (px + 46, py + 30)], fill=255)
    qx, qy = pts[30]
    d.polygon([(qx, qy), (qx + 96, qy + 88), (qx + 34, qy + 26)], fill=255)
    # single small dorsal, set well back
    rx, ry = pts[40]
    d.polygon([(rx - 44, ry), (rx + 30, ry - 78), (rx + 62, ry)], fill=255)
    tx, ty = pts[-1]
    d.polygon([(tx - 60, ty), (tx + 118, ty - 146), (tx + 96, ty + 44), (tx + 30, ty + 20)], fill=255)
    silhouette(img, m)
    # six gill frills, cut back out of the silhouette as light
    gl = Image.new("RGBA", size, (0, 0, 0, 0)); gd = ImageDraw.Draw(gl)
    for k in range(6):
        gx, gy = pts[3 + k]
        gd.line([(gx + 6, gy - 40), (gx - 6, gy + 40)], fill=(*CYAN, 120), width=5)
    img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(1.5)))
    return img


def art_squid(size, rng):
    """Ep 14 - colossal squid proportions: heavy mantle, terminal fins, eight
    arms and two longer tentacles with clubs. No confirmed-PD photograph of the
    species exists in the NOAA set, so the shape is drawn."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.64)
    m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    cx, cy = w * 0.63, h * 0.26
    d.polygon([(cx, cy - 210), (cx + 96, cy + 30), (cx + 66, cy + 108),
               (cx - 66, cy + 108), (cx - 96, cy + 30)], fill=255)     # mantle
    d.polygon([(cx, cy - 250), (cx + 168, cy - 118), (cx, cy - 96),
               (cx - 168, cy - 118)], fill=255)                        # terminal fins
    d.ellipse([cx - 84, cy + 76, cx + 84, cy + 208], fill=255)         # head
    for k in range(8):                                                 # eight arms
        ang = -0.95 + k * 0.271
        pts, wid = [], []
        for i in range(22):
            t = i / 21
            pts.append((cx + math.sin(ang) * t * 300 + math.sin(t * 3.4 + k) * 40 * t,
                        cy + 190 + t * 330 * (0.75 + abs(math.cos(ang)) * 0.5)))
            wid.append(52 * (1 - t) ** 0.75 + 6)
        m.paste(255, (0, 0), _spine_mask(size, pts, wid))
    for k in (-1, 1):                                                  # two tentacles
        pts, wid = [], []
        for i in range(30):
            t = i / 29
            pts.append((cx + k * (60 + math.sin(t * 2.1) * 150 * t), cy + 190 + t * 500))
            wid.append(30 * (1 - t * 0.7) + 5)
        club = _spine_mask(size, pts, wid)
        ex, ey = pts[-1]
        ImageDraw.Draw(club).ellipse([ex - 34, ey - 66, ex + 34, ey + 34], fill=255)
        m.paste(255, (0, 0), club)
    silhouette(img, m)
    eye = Image.new("RGBA", size, (0, 0, 0, 0))                        # the famous eye
    ImageDraw.Draw(eye).ellipse([cx - 74, cy + 108, cx - 6, cy + 176], fill=(*PALE, 200))
    img.alpha_composite(eye.filter(ImageFilter.GaussianBlur(2)))
    return img


def art_trench(size, rng, crewed=False):
    """Eps 10 and 15 - the water column in section. Depth is the subject, so the
    picture is the shape of the ocean, not an animal: light at the top, a
    V-profile falling away, and a scale down the side."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.60)
    m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    prof = []
    for i in range(w + 1):
        t = i / w
        v = abs(t - 0.60) / 0.46
        y = h * 0.20 + (1 - v ** 2.0) * h * 0.92
        y += math.sin(t * 23) * 6 + math.sin(t * 57) * 3
        prof.append((i, min(h + 4, y)))
    d.polygon([(0, h + 4)] + prof + [(w, h + 4)], fill=255)
    silhouette(img, m, colour=(1, 6, 11))

    ov = Image.new("RGBA", size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    sx = w * 0.905                                                     # depth scale
    od.line([(sx, h * 0.10), (sx, h * 0.92)], fill=(*CYAN, 130), width=3)
    for k in range(6):
        yy = h * 0.10 + k * (h * 0.82 / 5)
        L = 26 if k % 5 else 44
        od.line([(sx - L, yy), (sx, yy)], fill=(*CYAN, 150 if k % 5 else 220), width=3)
    if crewed:
        bx, by = w * 0.60, h * 0.66
        beam = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(beam).polygon(
            [(bx - 14, by), (bx + 14, by), (bx + 150, h), (bx - 150, h)], fill=(*PALE, 60))
        ov.alpha_composite(beam.filter(ImageFilter.GaussianBlur(20)))
        od.ellipse([bx - 30, by - 24, bx + 30, by + 24], fill=(*PALE, 255))
        od.ellipse([bx - 14, by - 34, bx + 14, by - 12], fill=(*PALE, 255))
        od.ellipse([bx - 52, by - 46, bx + 52, by + 46], outline=(*CYAN, 170), width=3)
        od.line([(bx, h * 0.06), (bx, by - 46)], fill=(*CYAN, 90), width=2)
    else:
        od.ellipse([w * 0.585, h * 0.855, w * 0.615, h * 0.885], fill=(*AMBER, 255))
    img.alpha_composite(ov)
    return img


def art_whalefall(size, rng):
    """Ep 16 - a whale-fall skeleton, picked down to bone. The lock says a
    carcass can feed a community for decades, so this is a settled skeleton on
    the seafloor rather than a fresh carcass."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.64)
    fy = h * 0.74
    floor = Image.new("L", size, 0)
    ImageDraw.Draw(floor).polygon([(0, h), (0, fy + 30), (w, fy - 18), (w, h)], fill=255)
    silhouette(img, floor, colour=(3, 12, 20), edge=False)

    m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    sx, sy = w * 0.30, fy - 40
    spine = [(sx + i * (w * 0.62 / 24), sy - 60 + math.sin(i / 24 * 2.3) * 30) for i in range(25)]
    m.paste(255, (0, 0), _spine_mask(size, spine, [20] * 25))
    # Ribs hang DOWNWARD from the spine only, and there are few of them. Drawing
    # both sides of every other vertebra produced a lattice that read as
    # chain-link fencing once it was 168px wide.
    # A ribcage reads as a cage: ribs sweeping down and OUT to a wide belly, then
    # tucking back. Straight ribs hanging off a straight spine read as a rake.
    for i in range(3, 22, 3):
        x, y = spine[i]
        span = 150 * math.sin(i / 22 * math.pi) ** 0.5 + 52
        for sgn in (-1, 1):
            rib = [(x, y),
                   (x + sgn * span * 0.42, y + span * 0.34),
                   (x + sgn * span * 0.60, y + span * 0.86),
                   (x + sgn * span * 0.40, y + span * 1.30)]
            m.paste(255, (0, 0), _spine_mask(size, rib, [24, 20, 15, 10]))
    hx, hy = spine[0]                                                  # skull and jaw
    d.polygon([(hx + 10, hy - 40), (hx - 250, hy + 10), (hx - 236, hy + 40), (hx + 10, hy + 34)], fill=255)
    d.polygon([(hx + 4, hy + 30), (hx - 244, hy + 52), (hx - 238, hy + 76), (hx + 4, hy + 66)], fill=255)
    silhouette(img, m, colour=(4, 14, 22))

    ov = Image.new("RGBA", size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    for _ in range(120):                                               # scavengers
        x = rng.uniform(w * 0.16, w * 0.98); y = rng.uniform(fy - 190, fy + 30)
        r = rng.uniform(1.5, 3.6)
        od.ellipse([x - r, y - r, x + r, y + r], fill=(*AMBER, int(rng.uniform(70, 190))))
    img.alpha_composite(ov)
    return img


def art_yeticrab(size, rng):
    """Ep 17 - Kiwaidae. The setae are the evidence: hair-like bristles on the
    claws that carry the bacteria the crab harvests and eats. So the bristles
    are the one thing drawn in light, against a silhouetted body near a vent."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.66, warm=True)
    plume = Image.new("RGBA", size, (0, 0, 0, 0)); pd = ImageDraw.Draw(plume)
    for _ in range(150):
        t = rng.random()
        x = w * 0.86 + rng.gauss(0, 40) * (0.4 + t); y = h * 0.98 - t * h * 0.62
        r = rng.uniform(12, 50) * (0.4 + t)
        pd.ellipse([x - r, y - r, x + r, y + r], fill=(*AMBER, 10))
    img.alpha_composite(plume.filter(ImageFilter.GaussianBlur(24)))

    m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    cx, cy = w * 0.63, h * 0.56
    d.ellipse([cx - 150, cy - 104, cx + 150, cy + 116], fill=255)      # carapace
    setae = Image.new("L", size, 0); sd = ImageDraw.Draw(setae)
    for s in (-1, 1):                                                  # two chelipeds
        a0 = (cx + s * 96, cy - 30)
        a1 = (cx + s * 300, cy - 150)
        a2 = (cx + s * 452, cy - 46)
        m.paste(255, (0, 0), _spine_mask(size, [a0, a1, a2], [64, 46, 34]))
        d.ellipse([a2[0] - s * 6 - 46, a2[1] - 44, a2[0] - s * 6 + 46, a2[1] + 44], fill=255)
        for i in range(70):                                            # the setae
            t = rng.random()
            if t < 0.5:
                px = a0[0] + (a1[0] - a0[0]) * t * 2; py = a0[1] + (a1[1] - a0[1]) * t * 2
            else:
                u = (t - 0.5) * 2
                px = a1[0] + (a2[0] - a1[0]) * u; py = a1[1] + (a2[1] - a1[1]) * u
            L = rng.uniform(34, 84); ang = rng.uniform(-2.5, -0.6)
            sd.line([(px, py), (px + math.cos(ang) * L, py + math.sin(ang) * L)],
                    fill=int(rng.uniform(150, 255)), width=2)
    for k in range(6):                                                 # walking legs
        s = -1 if k % 2 else 1
        ang = 0.35 + (k // 2) * 0.42
        b = (cx + s * 120, cy + 40)
        j = (b[0] + s * math.cos(ang) * 230, b[1] - 40 + math.sin(ang) * 120)
        e = (j[0] + s * math.cos(ang) * 150, j[1] + 190)
        m.paste(255, (0, 0), _spine_mask(size, [b, j, e], [40, 26, 12]))
    silhouette(img, m)
    sl = Image.new("RGBA", size, (*PALE, 0))
    sl.putalpha(_blur(setae, 2).point(lambda v: int(v * 0.9)))
    img.alpha_composite(sl)
    return img


def art_column(size, rng, free=(0.50, 0.99)):
    """Ep 20 - the midnight zone. The subject is an absence: the depth at which
    sunlight stops. So the picture is the light itself dying down the frame,
    with the bathypelagic band marked where the lock puts it, 1,000-4,000 m."""
    w, h = size
    img = downwelling(w, h, rng, cx=0.66)
    band = Image.new("RGBA", size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    y0 = int(h * 0.40)
    bd.rectangle([0, y0, w, h], fill=(*INK, 215))
    img.alpha_composite(band.filter(ImageFilter.GaussianBlur(26)))

    ov = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    f0, f1 = free
    od.line([(w * f0, y0), (w, y0)], fill=(*CYAN, 200), width=3)
    lf = F(F_LABEL, 24)
    tracked(od, (w * f0 + 10, y0 - 36), "SUNLIGHT ENDS", lf, (*CYAN, 235), track=3)
    for lbl, fy in (("1,000 M", 0.46), ("4,000 M", 0.88)):
        yy = int(h * fy)
        lx = w * (f0 + (f1 - f0) * 0.42)
        od.line([(lx, yy), (w * (f1 - 0.03), yy)], fill=(*MUTED, 170), width=2)
        od.text((lx, yy - 28), lbl, font=F(F_LABEL, 22), fill=(*MUTED, 210))
    # a few animals still down there, barely lit
    for _ in range(7):
        x = rng.uniform(w * 0.52, w * 0.95); y = rng.uniform(h * 0.50, h * 0.92)
        r = rng.uniform(4, 11)
        od.ellipse([x - r, y - r * 0.5, x + r, y + r * 0.5], fill=(*PALE, int(rng.uniform(40, 110))))
    img.alpha_composite(ov)
    return img

# --------------------------------------------------------------- channel marks

def mark(d, cx, cy, s, a=235):
    """The sounding mark: sea-level rule, descent line, a reading at depth."""
    lw = max(2, int(6 * s))
    half = int(78 * s)
    d.line([(cx - half, cy - int(62 * s)), (cx + half, cy - int(62 * s))], fill=(*PALE, a), width=lw)
    d.line([(cx, cy - int(62 * s)), (cx, cy + int(46 * s))], fill=(*CYAN, a), width=lw)
    for i, dy in enumerate((-22, 0, 22)):
        t = int(26 * s) - i * int(6 * s)
        d.line([(cx - t, cy + int(dy * s)), (cx + t, cy + int(dy * s))],
               fill=(*CYAN, a), width=max(1, lw - 1))
    r = int(13 * s)
    d.ellipse([cx - r, cy + int(46 * s) - r, cx + r, cy + int(46 * s) + r], fill=(*AMBER, a))


def tracked(d, xy, text, font, fill, track=3):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + track
    return x


def fit(text, maxw, maxh, start=152, minsz=74, maxlines=3):
    """Largest size at which the hook fits its box. Never clips, never overflows."""
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for size in range(start, minsz - 1, -3):
        f = F(F_DISPLAY_BOLD, size)
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if probe.textlength(trial, font=f) > maxw and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        if len(lines) <= maxlines and len(lines) * (size * 1.06) <= maxh:
            return f, lines, size
    f = F(F_DISPLAY_BOLD, minsz)
    return f, text.split("\n")[:maxlines], minsz


# ------------------------------------------------------------------- composition

def compose(base: Image.Image, hook: str, kicker: str | None,
            side: str = "left", credit: str | None = None) -> Image.Image:
    img = base.convert("RGBA")
    img.alpha_composite(vignette(TW, TH))

    pad = 64
    boxw = int(TW * 0.50)
    x0 = pad if side == "left" else TW - pad - boxw

    # Adaptive scrim. A fixed wash is right for a dark frame and far too weak
    # for a bright one (pale sand, a lit vent chimney), where the kicker in
    # particular disappears. Measure what is actually under the type and darken
    # until the words are guaranteed to win.
    probe = np.asarray(img.convert("RGB"), np.float32) / 255.0
    band = probe[int(TH * 0.14):int(TH * 0.88), x0:x0 + boxw]
    lum = float((band @ np.array([0.299, 0.587, 0.114], np.float32)).mean())
    strength = float(np.clip(0.86 + lum * 1.30, 0.86, 0.985))
    img.alpha_composite(scrim(TW, TH, side, strength))

    ov = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    f, lines, size = fit(hook, boxw, TH * 0.62)
    lead = size * 1.05
    total = len(lines) * lead
    ky = 0
    kf = F(F_LABEL, 27)
    if kicker:
        ky = 44
    y = (TH - total - ky) / 2 + ky - 10

    if kicker:
        # a soft plate under the small caps: they are the first thing to be lost
        # against a bright frame, and a shadow alone will not save 27px type
        kw = sum(d.textlength(c, font=kf) + 4 for c in kicker.upper())
        plate = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rectangle(
            [x0 - 18, y - 74, x0 + kw + 20, y - 24], fill=(*INK, 190))
        img.alpha_composite(plate.filter(ImageFilter.GaussianBlur(11)))
        tracked(d, (x0 + 3, y - 60), kicker.upper(), kf, (*CYAN, 245), track=4)

    for ln in lines:
        # a soft black pad under each line: survives the downscale where a
        # 1px shadow disappears
        d.text((x0 + 4, y + 5), ln, font=f, fill=(0, 0, 0, 165))
        d.text((x0, y), ln, font=f, fill=(*TEXT, 255))
        y += lead

    d.rectangle([x0, y + 20, x0 + 178, y + 30], fill=(*AMBER, 255))
    d.text((x0, y + 46), "HOW WE KNOW", font=F(F_LABEL, 25), fill=(*MUTED, 235))

    mark(d, TW - 74, TH - 108, 0.52, a=210)
    if credit:
        cf = F(F_LABEL, 15)
        wpx = d.textlength(credit, font=cf)
        d.text((TW - 22 - wpx, TH - 26), credit, font=cf, fill=(*MUTED, 150))

    return Image.alpha_composite(img, ov).convert("RGB")


# ------------------------------------------------------------------- the episodes
#
# hook: 4-5 words maximum, written against the episode's Direct-answer lock.
# media: NOAA media id from channel/imagery/rights.json (Route A), or None.
# art:   procedural generator (Route B).
# focal: crop bias, so the subject is not cut in half.
# side:  which half the type occupies.

EPISODES = {
    "01": dict(kicker="Deep-sea bodies", hook="Why they look like that",
               media=[15986, 15400, 12924, 8479]),
    "02": dict(kicker="Pressure", hook="Mostly water, so it holds",
               media=[14848, 12924, 8479]),
    "03": dict(kicker="Nightly migration", hook="They rise every night",
               media=[15400, 10660, 10281]),
    "04": dict(kicker="Why it looks frightening", hook="A mouth built for scarcity",
               media=[12097, 13309, 15767], fill=0.45),
    "05": dict(kicker="Colour at depth", hook="Down here, red is invisible",
               media=[13043, 15248, 10403]),
    "06": dict(kicker="Transparency", hook="No outline, no shadow",
               media=[14878, 12924, 8479], lift=2.0),
    "07": dict(kicker="Depth and strangeness", hook="Deeper is not creepier",
               media=[15526, 14809, 12013, 15757, 15632]),
    "08": dict(kicker="Who lives down there", hook="More than you would guess",
               media=[19137, 10268, 19126, 23998]),
    "09": dict(kicker="The scariest", hook="There is no scariest",
               media=[15767, 13309, 11605, 14526], fill=0.40),
    "10": dict(kicker="Challenger Deep", hook="About 10,935 metres",
               art="trench", side="left"),
    "11": dict(kicker="Dumbo octopus", hook="It swims on ear-like fins",
               media=[15895, 10184, 4091]),
    "12": dict(kicker="Frilled shark", hook="Not a living fossil",
               art="shark", side="left"),
    "13": dict(kicker="Bioluminescence", hook="Light made by chemistry",
               media=[12212, 14878]),
    "14": dict(kicker="Colossal squid", hook="495 kilograms, measured",
               art="squid", side="left"),
    "15": dict(kicker="Challenger Deep", hook="Crewed, eleven kilometres down",
               art="trench_crewed", side="left"),
    "16": dict(kicker="Whale fall", hook="One carcass, decades of food",
               art="whalefall", side="left"),
    "17": dict(kicker="Yeti crab", hook="It farms what it eats",
               art="yeticrab", side="left"),
    "18": dict(kicker="Black smokers", hook="340°C and still liquid",
               media=[16065, 5177]),
    "19": dict(kicker="The deepest fish", hook="Snailfish hold the depth record",
               media=[22125, 14304], lift=1.8),
    "20": dict(kicker="The midnight zone", hook="Below one thousand metres",
               art="column", side="left"),
}

# Every generator takes (size, rng, free) so that art is always told which part
# of the frame the type will occupy. Positioning marks by eye against a layout
# the drawing cannot see is what put "SUNLIGHT ENDS" through the middle of the
# midnight-zone hook.
ART = {
    "shark": lambda s, r, free: art_shark(s, r),
    "squid": lambda s, r, free: art_squid(s, r),
    "trench": lambda s, r, free: art_trench(s, r, crewed=False),
    "trench_crewed": lambda s, r, free: art_trench(s, r, crewed=True),
    "column": art_column,
    "whalefall": lambda s, r, free: art_whalefall(s, r),
    "yeticrab": lambda s, r, free: art_yeticrab(s, r),
}


def load_manifest():
    if not os.path.exists(MANIFEST):
        return {}
    man = json.load(open(MANIFEST))
    ok, blocked = {}, {}
    # thumbnail_ok is a reviewed field, not a rights field: these items are
    # public domain and perfectly reusable, they are simply title cards,
    # calendar wallpapers or wordmarked frames rather than clean photographs.
    for a in man["assets"]:
        mid = int(a["local_file"].split("__")[1])
        (ok if a.get("thumbnail_ok", True) else blocked)[mid] = a
    return ok, blocked


def build(num: str, spec: dict, assets: dict, blocked: dict):
    rng = random.Random(int(num) * 7919)
    credit = None
    if spec.get("media"):
        side = spec.get("side", "auto")
        cands = spec["media"]
        if isinstance(cands, int):
            cands = [cands]

        # Each candidate is a photograph that is TRUTHFUL for this episode's
        # claim -- that judgement stays hand-made, because it is where the
        # evidence discipline lives. Which of them gets used is decided by
        # measuring the finished frame, not by guessing in advance. That is the
        # general repair: a single hand-picked asset plus a hand-tuned zoom has
        # no way to notice it has framed an empty patch of water.
        scored = []
        for mid in cands:
            if mid in blocked:
                continue          # reviewed out as a graphic, not an error
            if mid in used:
                continue          # one photograph per channel: a repeat across
                                  # two thumbnails reads as a mistake in a grid
            rec = assets.get(mid)
            if rec is None:
                raise KeyError(f"episode {num}: media {mid} not in rights manifest")
            src = exposure_lift(Image.open(os.path.join(IMAGERY, rec["local_file"])),
                                spec.get("lift", 1.0))
            # Let the type go opposite the animal rather than fixing the side by
            # hand. Ep 09 put the words straight on top of the anglerfish and
            # left the empty half of the water bare, because "side" was a
            # constant while the subject's position is a property of the photo.
            this_side = side
            if this_side == "auto":
                bx0, _, bx1, _ = subject_box(src)
                this_side = "right" if (bx0 + bx1) / 2 < 0.5 else "left"
            # 0.70 rather than filling the free half edge to edge: an animal
            # cropped to exactly its bounding box has no room around it and
            # reads as texture, not as a creature. Ep 04 at 0.92 was a wall of
            # goosefish skin with no fish visible in it.
            subject, place, zoom, box = frame_subject(src, this_side, spec.get("fill", 0.70))
            if spec.get("focal"):
                subject = spec["focal"]
            cand = grade(cover(src, TW, TH, subject, place, zoom))
            scored.append((free_region_energy(cand, this_side), mid, cand, rec, this_side))

        # Declared order is an editorial judgement made by eye at full size, so
        # it wins: take the FIRST candidate that clears the floor, not the
        # highest-scoring one. Ranking by score instead put the vivid orange
        # anemone ahead of the snailfish on the episode about snailfish -- the
        # measure likes bright busy frames, which is not the same as liking the
        # right subject. The metric's job is to reject failures, not to direct.
        passing = [t for t in scored if t[0] >= MIN_SUBJECT_ENERGY]
        energy, mid, base, rec, side = passing[0] if passing else max(scored, key=lambda t: t[0])

        # Rule 0: no frame ships without a subject in it. An empty card is a
        # defect, not a style. If the best of the truthful candidates still
        # frames nothing, refuse loudly rather than emitting a blank.
        if energy < MIN_SUBJECT_ENERGY:
            raise ValueError(
                f"episode {num}: no candidate frames a subject "
                f"(best={mid} energy={energy:.4f} < {MIN_SUBJECT_ENERGY}); "
                f"tried {cands}")
        chosen[num] = (mid, energy, rec)
        used.add(mid)
        route = "A"
        credit = "NOAA OCEAN EXPLORATION"
    else:
        side = spec.get("side", "left")
        base = ART[spec["art"]]((TW, TH), rng, FREE_X[side]).convert("RGB")
        route = "B"
    if route == "B":
        side = spec.get("side", "left")
    return compose(base, spec["hook"], spec.get("kicker"), side, credit), route


def slug_for(num: str) -> str:
    import glob
    hits = glob.glob(os.path.join(HERE, "..", "scripts", f"{num}-*.md"))
    return os.path.basename(hits[0])[:-3] if hits else num


def main(compare=False):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PROOFS, exist_ok=True)
    assets, blocked = load_manifest()
    chosen.clear(); used.clear()
    made = []
    for num in sorted(EPISODES):
        im, route = build(num, EPISODES[num], assets, blocked)
        slug = slug_for(num)
        p = os.path.join(OUT, f"{slug}.jpg")
        im.save(p, "JPEG", quality=90, optimize=True, progressive=True)
        made.append((slug, os.path.getsize(p), route, im))

    over = [m for m in made if m[1] > 2_000_000]
    print(f"{len(made)} thumbnails -> {OUT}")
    print(f"route A (NOAA public domain): {sum(1 for m in made if m[2]=='A')}")
    print(f"route B (drawn):              {sum(1 for m in made if m[2]=='B')}")
    print(f"largest {max(m[1] for m in made)/1024:.0f} KB; over 2MB: {len(over)}")

    if compare:
        # feed-size proof sheet: exactly how YouTube shows these on mobile
        cols, gap = 5, 12
        rows = (len(made) + cols - 1) // cols
        sw = cols * (FEED[0] + gap) + gap
        sh = rows * (FEED[1] + gap + 14) + gap
        sheet = Image.new("RGB", (sw, sh), (18, 18, 20))
        d = ImageDraw.Draw(sheet)
        for i, (slug, _, route, im) in enumerate(made):
            small = im.resize(FEED, Image.LANCZOS)
            x = gap + (i % cols) * (FEED[0] + gap)
            y = gap + (i // cols) * (FEED[1] + gap + 14)
            sheet.paste(small, (x, y))
            d.text((x, y + FEED[1] + 2), f"{slug[:2]} {route}", fill=(190, 210, 220))
        sheet.save(os.path.join(PROOFS, "feed_168x94.png"))

        big = Image.new("RGB", (4 * 320, 5 * 180), (18, 18, 20))
        for i, (_, _, _, im) in enumerate(made):
            big.paste(im.resize((320, 180), Image.LANCZOS), ((i % 4) * 320, (i // 4) * 180))
        big.save(os.path.join(PROOFS, "grid_full.png"))
        print(f"proofs -> {PROOFS}")
    return made


if __name__ == "__main__":
    main(compare="--compare" in sys.argv)
