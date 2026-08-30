"""Segment renderers. Each returns a PIL frame for time t in [0,1]."""
import math, random
from PIL import Image, ImageDraw, ImageFont
from design import *

_fc = {}
def font(path, size):
    k = (path, size)
    if k not in _fc: _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

def _grad(top, bot):
    """Vertical gradient base. Built at low res and scaled — 40x faster."""
    g = Image.new("RGB", (2, 128))
    px = g.load()
    for y in range(128):
        c = mix(top, bot, y / 127)
        px[0, y] = c; px[1, y] = c
    return g.resize((W, H), Image.BILINEAR)

def _snow(d, t, n=90, seed=7, speed=0.35, size=(1, 3)):
    """Marine snow: slow organic drift. The connective tissue between beats."""
    r = random.Random(seed)
    for _ in range(n):
        x0, y0 = r.random(), r.random()
        sp = speed * r.uniform(0.4, 1.6)
        rad = r.uniform(*size)
        a = int(r.uniform(40, 150))
        drift = math.sin((t * sp * 6) + x0 * 9) * 14
        x = x0 * W + drift
        y = ((y0 + t * sp) % 1.0) * H
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(*PALE, a))

def _center(d, text, f, y, fill, spacing=0):
    if spacing:
        wtot = sum(d.textlength(ch, font=f) + spacing for ch in text) - spacing
        x = (W - wtot) / 2
        for ch in text:
            d.text((x, y), ch, font=f, fill=fill); x += d.textlength(ch, font=f) + spacing
        return
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def depth_descent(t, to_depth=11034, label="CHALLENGER DEEP"):
    """Signature shot: a continuous fall through the water column."""
    e = ease(t); cur = to_depth * e
    img = _grad(depth_color(cur * 0.25), depth_color(cur))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=110, speed=0.9)
    # depth ruler ticks stream upward past the viewer
    step = 500
    first = int(cur // step) * step
    for i in range(-2, 9):
        m = first - i * step
        if m < 0 or m > to_depth: continue
        y = H * 0.5 + (cur - m) * (H / 3400)
        if -60 < y < H + 60:
            major = m % 2000 == 0
            d.line([(W - 300, y), (W - (250 if major else 275), y)],
                   fill=(*CYAN, 200 if major else 90), width=2 if major else 1)
            if major:
                d.text((W - 240, y - 13), f"{m:,} m", font=font(F_MONO, 22), fill=(*CYAN, 210))
    d.line([(W - 300, 0), (W - 300, H)], fill=(*CYAN, 45), width=1)
    # live readout
    _center(d, f"{int(cur):,}", font(F_DISPLAY, 150), H * 0.40, (*TEXT, 255))
    _center(d, "METRES", font(F_LABEL, 30), H * 0.40 + 205, (*MUTED, 210), spacing=10)
    _center(d, label, font(F_LABEL, 26), 70, (*CYAN, 190), spacing=7)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def stat_card(t, value="11,034", unit="METRES", caption="", source=""):
    """One number, held. Used when narration lands a verified figure."""
    img = _grad(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=60, speed=0.22)
    rise = (1 - ease(min(t * 3, 1))) * 34          # settle in
    _center(d, value, font(F_DISPLAY, 210), H * 0.30 + rise, (*TEXT, 255))
    _center(d, unit, font(F_LABEL, 34), H * 0.30 + 285 + rise, (*CYAN, 230), spacing=12)
    if caption:
        _center(d, caption, font(F_LABEL, 38), H * 0.66, (*MUTED, 235))
    # accent rule wipes in
    wln = int(300 * ease(min(t * 2.2, 1)))
    d.rectangle([W // 2 - wln // 2, H * 0.60, W // 2 + wln // 2, H * 0.60 + 5], fill=(*AMBER, 255))
    if source:
        d.text((70, H - 70), f"Source: {source}", font=font(F_LABEL, 22), fill=(*MUTED, 165))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def zone_column(t, highlight=None):
    """Five zones. Uses a compressed depth axis so the shallow zones are legible;
    the axis is labelled with real depths so the compression is visible, not hidden."""
    img = _grad(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=70, speed=0.3)
    x0, x1 = W * 0.26, W * 0.52
    top_y, bot_y = 165, H - 165
    hl = (highlight or "").strip().upper() or None

    def ypos(m):                       # sqrt axis: shallow zones stay readable
        return top_y + (m / 11034) ** 0.5 * (bot_y - top_y)

    prev_label_y = -999
    for i, (name, top, bot) in enumerate(ZONES):
        yt, yb = ypos(top), ypos(bot)
        rev = ease(max(0, min(1, t * 4.5 - i * 0.5)))
        if rev <= 0: continue
        h = (yb - yt) * rev
        on = (hl is None) or (hl == name)
        c = depth_color((top + bot) / 2)
        # lift the fill so blocks read against the background
        fill = mix(c, PALE, 0.16 if on else 0.05)
        d.rectangle([x0, yt, x1, yt + h], fill=(*fill, 255))
        d.line([(x0, yt), (x1, yt)], fill=(*CYAN, 200 if on else 70), width=2)
        if rev > 0.9:
            ly = max(yt + 8, prev_label_y + 62)      # never collide
            a = 255 if on else 120
            col = CYAN if on else MUTED
            d.line([(x1 + 8, ly + 14), (x1 + 26, ly + 14)], fill=(*col, a), width=2)
            d.text((x1 + 36, ly), name, font=font(F_LABEL, 26), fill=(*col, a))
            d.text((x1 + 36, ly + 30), f"{top:,}-{bot:,} m",
                   font=font(F_MONO, 19), fill=(*MUTED, a))
            prev_label_y = ly
    d.line([(x0, top_y), (x0, bot_y)], fill=(*CYAN, 90), width=1)
    _center(d, "THE WATER COLUMN", font(F_LABEL, 26), 72, (*CYAN, 200), spacing=8)
    d.text((x0 - 150, bot_y - 10), "11,034 m", font=font(F_MONO, 19), fill=(*MUTED, 150))
    d.text((x0 - 150, top_y - 6), "0 m", font=font(F_MONO, 19), fill=(*MUTED, 150))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def comparison(t, a_label="MOUNT EVEREST", a_m=8849, b_label="CHALLENGER DEEP", b_m=11034):
    """Everest rises, the trench descends. The point is that one fits inside the other."""
    img = _grad(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=50, speed=0.25)
    sea = H * 0.34                      # sea level sits high; the deep needs the room
    up_span, dn_span = sea - 150, (H - 120) - sea
    scale = min(up_span / a_m, dn_span / b_m)
    e = ease(min(t * 1.5, 1))
    lab_a = ease(max(0.0, min(1.0, (t - 0.28) * 3)))   # labels arrive, then stay

    # Everest, above
    hgt = a_m * scale * e
    x = W * 0.33
    d.rectangle([x - 105, sea - hgt, x + 105, sea], fill=(*PALE, 55))
    d.line([(x - 105, sea - hgt), (x + 105, sea - hgt)], fill=(*PALE, 255), width=3)

    # Challenger Deep, below
    dep = b_m * scale * e
    x2 = W * 0.67
    d.rectangle([x2 - 105, sea, x2 + 105, sea + dep], fill=(*CYAN, 45))
    d.line([(x2 - 105, sea + dep), (x2 + 105, sea + dep)], fill=(*CYAN, 255), width=3)

    if lab_a > 0:
        A = int(255 * lab_a)
        for x_, m, lab, col, ytxt, ylab in [
            (x,  a_m, a_label, PALE, sea - hgt - 46, sea - hgt - 82),
            (x2, b_m, b_label, CYAN, sea + dep + 18, sea + dep + 54)]:
            tx = f"{m:,} m"
            d.text((x_ - d.textlength(tx, font=font(F_MONO, 28)) / 2, ytxt), tx,
                   font=font(F_MONO, 28), fill=(*col, A))
            d.text((x_ - d.textlength(lab, font=font(F_LABEL, 24)) / 2, ylab), lab,
                   font=font(F_LABEL, 24), fill=(*MUTED, A))

    d.line([(120, sea), (W - 120, sea)], fill=(*MUTED, 150), width=2)
    d.text((120, sea - 34), "SEA LEVEL", font=font(F_LABEL, 21), fill=(*MUTED, 170))
    if lab_a > 0.6:
        msg = f"Everest would sit {b_m - a_m:,} m below the surface."
        _center(d, msg, font(F_LABEL, 30), H - 78, (*AMBER, int(235 * lab_a)))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def quote_card(t, text="", attrib=""):
    """Her POV line, given room. Deliberately quiet."""
    img = _grad(INK, DEEP)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=40, speed=0.16)
    f = font(F_DISPLAY, 52)
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if d.textlength(trial, font=f) > W * 0.68 and cur: lines.append(cur); cur = wd
        else: cur = trial
    if cur: lines.append(cur)
    y = H / 2 - len(lines) * 38
    d.rectangle([W * 0.15, y - 40, W * 0.15 + 4, y + len(lines) * 76 + 10], fill=(*AMBER, 200))
    for i, ln in enumerate(lines):
        a = int(255 * ease(max(0, min(1, t * 4 - i * 0.3))))
        d.text((W * 0.19, y + i * 76), ln, font=f, fill=(*TEXT, a))
    if attrib:
        d.text((W * 0.19, y + len(lines) * 76 + 34), attrib, font=font(F_LABEL, 24), fill=(*MUTED, 190))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
