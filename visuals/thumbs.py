"""Thumbnails, generated from the same design system as the video.

YouTube shows these as small as 168x94 in the mobile feed, so the rule is:
few words, very large, very high contrast, one focal shape.
"""
import os, re, glob, textwrap
from PIL import Image, ImageDraw, ImageFont
from design import *

TW, TH = 1280, 720
OUT = "../channel/thumbnails"; os.makedirs(OUT, exist_ok=True)
def F(p, s): return ImageFont.truetype(p, s)

def grad(w, h, top, bot):
    g = Image.new("RGB", (2, 160)); px = g.load()
    for y in range(160):
        c = mix(top, bot, y / 159); px[0, y] = c; px[1, y] = c
    return g.resize((w, h), Image.BILINEAR)

def radial(w, h, cx, cy, rad, col, peak=0.30):
    """Smooth radial falloff. Stacked ellipses band visibly at thumbnail size."""
    import numpy as np
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / rad
    a = np.clip(1.0 - dist, 0, 1) ** 2.2 * peak
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = col
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")

def snow(d, w, h, n, seed):
    import random
    r = random.Random(seed)
    for _ in range(n):
        x, y = r.random() * w, r.random() * h
        rad = r.uniform(1.2, 3.0)
        d.ellipse([x-rad, y-rad, x+rad, y+rad], fill=(*PALE, int(r.uniform(30, 110))))

def mark(d, cx, cy, s, a=230):
    lw = max(2, int(5 * s)); half = int(60 * s)
    d.line([(cx-half, cy-int(48*s)), (cx+half, cy-int(48*s))], fill=(*PALE, a), width=lw)
    d.line([(cx, cy-int(48*s)), (cx, cy+int(34*s))], fill=(*CYAN, a), width=lw)
    for i, dy in enumerate((-18, 0, 18)):
        t = int(20*s) - i*int(4*s)
        d.line([(cx-t, cy+int(dy*s)), (cx+t, cy+int(dy*s))], fill=(*CYAN, a), width=max(1, lw-1))
    r = int(10 * s)
    d.ellipse([cx-r, cy+int(34*s)-r, cx+r, cy+int(34*s)+r], fill=(*AMBER, a))

def hook(title):
    """The thumbnail asks the question; it does not restate the whole title."""
    t = re.sub(r"^\d+-", "", title).replace("-", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t[0].upper() + t[1:]

def fit(d, text, maxw, maxh, start=112, minsz=54):
    """Largest size at which the text fits the box. Never overflows, never clips."""
    for size in range(start, minsz - 1, -4):
        f = F(F_DISPLAY, size)
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=f) > maxw and cur:
                lines.append(cur); cur = w
            else: cur = trial
        if cur: lines.append(cur)
        if len(lines) <= 4 and len(lines) * (size * 1.18) <= maxh:
            return f, lines, size
    f = F(F_DISPLAY, minsz)
    return f, textwrap.wrap(text, 22)[:4], minsz

def build(num, title, hero=None):
    img = grad(TW, TH, MID, INK).convert("RGBA")
    img.alpha_composite(radial(TW, TH, 1010, 300, 460, CYAN, 0.26))

    ov = Image.new("RGBA", (TW, TH), (0,0,0,0)); d = ImageDraw.Draw(ov)
    snow(d, TW, TH, 60, seed=int(num))
    mark(d, 1035, 300, 2.5, a=90)          # large, quiet focal shape
    txt = hook(title)
    f, lines, size = fit(d, txt, maxw=TW*0.74, maxh=TH*0.52)
    total = len(lines) * size * 1.18
    y = (TH - total) / 2 - 18
    for ln in lines:
        # drop shadow for legibility over any background
        d.text((62+3, y+3), ln, font=f, fill=(0, 0, 0, 150))
        d.text((62, y), ln, font=f, fill=(*TEXT, 255))
        y += size * 1.18
    d.rectangle([62, y + 16, 62 + 190, y + 24], fill=(*AMBER, 255))
    d.text((TW-232, TH-58), "HOW WE KNOW", font=F(F_LABEL, 24), fill=(*CYAN, 210))
    return Image.alpha_composite(img, ov).convert("RGB")

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    import planner, segments as SEG
    try: import segments_ext as SX
    except ImportError: SX = None
    INFO = ("depth_descent","zone_column","anatomy_callout","pressure_gauge",
            "light_attenuation","stat_card","comparison","size_ladder","timeline")
    def resolve(n):
        if hasattr(SEG, n): return getattr(SEG, n)
        if SX and hasattr(SX, n): return getattr(SX, n)
        return None
    made = []
    for f in sorted(glob.glob("../scripts/*.md")):
        base = os.path.basename(f)[:-3]
        num = base.split("-")[0]
        hero = None
        for b in planner.plan(f):                 # first real visual in this script
            if b["segment"] in INFO:
                fn = resolve(b["segment"])
                if fn: hero = (fn, b["args"] or {}); break
        im = build(num, base, hero)
        p = f"{OUT}/{base}.jpg"
        im.save(p, "JPEG", quality=88, optimize=True)
        made.append((base, os.path.getsize(p)))
    print(f"{len(made)} thumbnails -> {OUT}")
    big = [m for m in made if m[1] > 2_000_000]
    print("over YouTube's 2MB limit:", len(big))
    print(f"largest: {max(m[1] for m in made)/1024:.0f} KB")
