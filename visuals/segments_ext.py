"""Extended segment renderers for the deep-sea channel.

Same contract as segments.py: fn(t, **kwargs) -> PIL.Image (RGB, W x H), t in [0,1].
Same palette, same fonts, same restraint. Nothing here invents a colour or a fact:
every colour comes from design.py (or is derived from a hue for the one segment
that is *about* wavelength), and every number drawn on screen arrives as an
argument or is computed from one.

Text safety is enforced everywhere by _fit / _wrap / _slot: nothing overlaps and
nothing leaves the canvas.
"""
import math, random, colorsys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from design import *

# ---------------------------------------------------------------- primitives

_fc = {}
def font(path, size):
    k = (path, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(size))
    return _fc[k]


_bgc = {}
def _bg(top, bot):
    """Vertical gradient base. Built at 2x128 and upscaled — the cheap way.
    Cached: every segment here uses a fixed pair, so this is once per pair, not
    once per frame. Callers only ever composite onto it, never mutate it."""
    k = (top, bot)
    if k not in _bgc:
        g = Image.new("RGB", (2, 128))
        px = g.load()
        for y in range(128):
            c = mix(top, bot, y / 127)
            px[0, y] = c
            px[1, y] = c
        if len(_bgc) > 24:
            _bgc.clear()
        _bgc[k] = g.resize((W, H), Image.BILINEAR).convert("RGBA")
    return _bgc[k]


def _dust(d, t, n=70, seed=11, speed=0.3, size=(1, 3), col=None):
    """Marine snow. Deterministic per seed so a segment is stable frame to frame."""
    col = col or PALE
    r = random.Random(seed)
    for _ in range(n):
        x0, y0 = r.random(), r.random()
        sp = speed * r.uniform(0.4, 1.6)
        rad = r.uniform(*size)
        a = int(r.uniform(40, 150))
        drift = math.sin((t * sp * 6) + x0 * 9) * 14
        x = x0 * W + drift
        y = ((y0 + t * sp) % 1.0) * H
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(*col, a))


def _ctext(d, text, f, y, fill, spacing=0, cx=None):
    """Centred text, optionally letter-spaced like the house headers."""
    cx = W / 2 if cx is None else cx
    if spacing:
        wtot = sum(d.textlength(ch, font=f) + spacing for ch in text) - spacing
        x = cx - wtot / 2
        for ch in text:
            d.text((x, y), ch, font=f, fill=fill)
            x += d.textlength(ch, font=f) + spacing
        return
    d.text((cx - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


def _header(d, title, alpha=190):
    _ctext(d, title.upper(), font(F_LABEL, 26), 66, (*CYAN, alpha), spacing=8)


def _fit(d, text, path, size, maxw, minsize=14):
    """Largest font <= size at which `text` fits maxw. Never returns an overflow."""
    s = int(size)
    w = d.textlength(text, font=font(path, s))
    if w <= maxw or not w:
        return font(path, s)
    s = max(minsize, min(s, int(s * maxw / w) + 1))   # estimate, then walk down
    while s > minsize and d.textlength(text, font=font(path, s)) > maxw:
        s -= 1
    return font(path, s)


def _wrap(d, text, f, maxw):
    lines, cur = [], ""
    for wd in str(text).split():
        trial = (cur + " " + wd).strip()
        if cur and d.textlength(trial, font=f) > maxw:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _slot(desired, gap, lo, hi):
    """De-collide a list of desired y positions into a monotone, spaced, clamped set."""
    ys = list(desired)
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    prev = lo
    for i in order:
        ys[i] = max(ys[i], prev)
        prev = ys[i] + gap
    over = prev - gap - hi
    if over > 0:
        shift = min(over, min(ys[i] for i in order) - lo) if ys else 0
        for i in order:
            ys[i] -= max(shift, 0)
    return ys


def _caustics(t, seed=0, rows=72, cols=128, top_bias=True, gain=0.30):
    """Interfering sine sheets — reads as light rippling on water. Vectorised."""
    y, x = np.mgrid[0:rows, 0:cols].astype(np.float32)
    x /= cols
    y /= rows
    p = t * 2 * math.pi
    s = seed * 1.7
    v = (np.sin(x * 11 + p + s) * np.sin(y * 7 - p * 0.6 + s)
         + np.sin((x + y) * 9 - p * 0.8) * np.sin(x * 5 + p * 0.4))
    v = np.clip(v * 0.35 + 0.3, 0, 1) ** 3
    if top_bias:
        v *= np.clip(1.25 - y * 1.9, 0, 1)
    return v * gain


def _blobs(items, rows=72, cols=128):
    """Sum of anisotropic gaussians on a low-res grid. Feed it to _atmos and the
    upscale turns them into genuinely soft glows — PIL ellipses give hard rings."""
    y, x = np.mgrid[0:rows, 0:cols].astype(np.float32)
    out = np.zeros((rows, cols), np.float32)
    for bx, by, sx, sy, amp in items:
        out += amp * np.exp(-(((x - bx) ** 2) / (2 * sx * sx)
                              + ((y - by) ** 2) / (2 * sy * sy)))
    return out


_ROWS, _COLS = 96, 160


def _atmos(top, bot, layers=(), vig=0.62):
    """Build the whole non-particulate background in numpy at low res and upscale
    ONCE. Compositing five full-frame RGBA layers instead costs ~30 ms/frame; this
    costs about a third of that, and the upscale is what softens the glows anyway.

    layers: iterable of (alpha_field, colour) blended in order.
    """
    ramp = np.linspace(0.0, 1.0, _ROWS, dtype=np.float32)[:, None]
    a = np.array(top, np.float32)
    b = np.array(bot, np.float32)
    buf = a + (b - a) * ramp[..., None]
    buf = np.repeat(buf, _COLS, axis=1)
    for field, col in layers:
        f = np.clip(field, 0, 1)[..., None]
        buf += (np.array(col, np.float32) - buf) * f
    if vig:
        buf += (np.array(INK, np.float32) - buf) * _vig_field(vig)[..., None]
    im = Image.fromarray(np.clip(buf, 0, 255).astype(np.uint8), "RGB")
    return im.resize((W, H), Image.BILINEAR)


_vigf = {}
def _vig_field(strength):
    if strength not in _vigf:
        y, x = np.mgrid[0:_ROWS, 0:_COLS].astype(np.float32)
        r = np.sqrt(((x / _COLS - 0.5) * 1.9) ** 2 + ((y / _ROWS - 0.5) * 1.35) ** 2)
        _vigf[strength] = np.clip(r - 0.42, 0, 1) * strength
    return _vigf[strength]


def _hue(deg, sat=0.80, val=1.0):
    """Spectral colour for the wavelength segment, mixed toward the house PALE
    so it still belongs to this show. No literal RGB anywhere."""
    r, g, b = colorsys.hsv_to_rgb((deg % 360) / 360.0, sat, val)
    return mix((int(r * 255), int(g * 255), int(b * 255)), PALE, 0.12)


def _finish(img, ov):
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def _rev(t, i, n, lead=0.55, finish=0.78):
    """Sequenced reveal: element i of n eases in, then holds.

    The span is derived from n so the LAST element is always fully on screen by
    t=finish, however many there are. Fixing the span instead is how you end up
    with a segment whose final items never appear."""
    span = (1.0 + max(n - 1, 0) * lead) / finish
    return ease(max(0.0, min(1.0, t * span - i * lead)))


# ---------------------------------------------------------------- 1. anatomy

def _creature(seed=3):
    """A generated fish-shaped silhouette in unit box coords (x right = head).

    Built as a profile: a spine from tail (x=0) to snout (x=1) with an upper and
    lower half-thickness curve, plus a dorsal swell and a forked tail. Harmonics
    seeded from `seed` so different creatures differ without looking random."""
    r = random.Random(seed)
    ph = [r.uniform(0, 6.28) for _ in range(3)]
    k = [r.uniform(0.7, 1.25) for _ in range(2)]
    n = 90

    def thick(u):
        # 0 at the tail root, fat around u=0.55, tapering to a blunt snout
        base = math.sin(min(max((u - 0.06) / 0.94, 0.0), 1.0) * math.pi) ** 0.75
        return base * (0.86 + 0.14 * math.sin(u * 6 + ph[0]))

    upper, lower = [], []
    for i in range(n + 1):
        u = i / n
        th = thick(u)
        dorsal = 0.26 * k[0] * max(0.0, math.sin((u - 0.30) / 0.45 * math.pi)) ** 1.6
        belly = 0.16 * k[1] * max(0.0, math.sin((u - 0.22) / 0.55 * math.pi)) ** 1.4
        y = 0.5 - 0.16 * math.sin(u * 2.2 + ph[1]) * 0.25          # gentle spine curve
        upper.append((0.08 + u * 0.90, y - th * 0.30 - dorsal * 0.30))
        lower.append((0.08 + u * 0.90, y + th * 0.30 + belly * 0.30))

    tail = [(0.00, 0.74), (0.085, 0.60), (0.005, 0.50), (0.085, 0.40), (0.00, 0.26)]
    return upper + list(reversed(lower)) + tail


def anatomy_callout(t, title="ANATOMY", parts=(), seed=3):
    """Generated creature silhouette with sequenced leader-line callouts.

    parts: list of (label, x_frac, y_frac) in the creature's bounding box.
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=55, speed=0.2, seed=23)

    bx, by, bw, bh = W * 0.29, H * 0.28, W * 0.42, H * 0.46
    def P(xf, yf):
        return (bx + xf * bw, by + yf * bh)

    body = [(bx + u * bw, by + v * bh) for u, v in _creature(seed)]
    grow = ease(min(t * 2.0, 1))
    cx, cy = bx + bw / 2, by + bh / 2
    body = [(cx + (px - cx) * grow, cy + (py - cy) * grow) for px, py in body]

    # trailing barbels — reads as deep-sea without naming a species
    r = random.Random(seed + 40)
    for k in range(5):
        x0 = bx + bw * (0.16 + 0.10 * (k / 4.0))
        y0 = by + bh * (0.62 + r.uniform(-0.06, 0.10))
        seg = []
        for j in range(9):
            f = j / 8.0
            seg.append((x0 - f * bw * 0.16 * grow,
                        y0 + math.sin(t * 2.0 + k + f * 3.0) * 12 * f + f * bh * 0.16))
        d.line(seg, fill=(*CYAN, int(70 * grow)), width=2)

    # ---- callout geometry. Side follows x so a leader never doubles back, and
    # the slots are de-collided vertically before anything is drawn.
    parts = list(parts)
    side_of = {i: ("L" if p[1] < 0.5 else "R") for i, p in enumerate(parts)}
    for empty, full in (("L", "R"), ("R", "L")):
        idx = [i for i in side_of if side_of[i] == full]
        if not any(side_of[i] == empty for i in side_of) and len(idx) > 2:
            pick = min(idx, key=lambda i: parts[i][1]) if empty == "L" \
                else max(idx, key=lambda i: parts[i][1])
            side_of[pick] = empty
    colw = W * 0.23
    calls = []                              # (alpha, point, elbow, textx, slot_y, side)
    for side in ("L", "R"):
        group = [(i, parts[i]) for i in range(len(parts)) if side_of[i] == side]
        if not group:
            continue
        ys = _slot([by + p[2] * bh for _, p in group], 88, 160, H - 120)
        for slot_y, (idx, (label, xf, yf)) in zip(ys, group):
            a = _rev(t, idx, len(parts), lead=0.42)
            if a <= 0.01:
                continue
            ex_, tx = ((bx - W * 0.045, W * 0.05) if side == "L"
                       else (bx + bw + W * 0.045, W - W * 0.05))
            calls.append((a, P(xf, yf), ex_, tx, slot_y, side, label))

    # leaders go down FIRST, so the silhouette occludes the part inside it and
    # each line appears to emerge from the body edge
    for a, (px, py), ex_, tx, slot_y, side, _ in calls:
        A = int(255 * a)
        d.line([(px, py), (ex_, slot_y), (tx, slot_y)], fill=(*CYAN, int(A * 0.5)), width=1)

    d.polygon(body, fill=(*mix(MID, INK, 0.30), int(240 * grow)))
    d.line(body + [body[0]], fill=(*CYAN, int(175 * grow)), width=2)
    # eye glow, on the leading (right) end
    ex, ey = P(0.84, 0.42)
    for rr, aa in ((20, 40), (11, 90), (4, 220)):
        d.ellipse([ex - rr, ey - rr, ex + rr, ey + rr], fill=(*PALE, int(aa * grow)))

    for a, (px, py), ex_, tx, slot_y, side, label in calls:
        A = int(255 * a)
        # a faint x-ray pass on top, so a dot sitting inside the body still
        # visibly connects to its label
        d.line([(px, py), (ex_, slot_y)], fill=(*PALE, int(A * 0.16)), width=1)
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(*PALE, A))
        f = _fit(d, label, F_LABEL, 30, colw)
        wtxt = d.textlength(label, font=f)
        lx = tx if side == "L" else tx - wtxt
        d.text((lx, slot_y - 34), label, font=f, fill=(*TEXT, A))
        d.line([(lx, slot_y - 2), (lx + wtxt, slot_y - 2)], fill=(*AMBER, int(A * 0.8)), width=2)

    _header(d, title)
    return _finish(img, ov)


# ---------------------------------------------------------------- 2. world map

# Coarse hand-built coastlines (lon, lat). Not survey-grade — it only has to read
# as Earth. Original coordinate lists, no third-party dataset.
_LAND = [
    [(-168, 65), (-160, 71), (-140, 70), (-125, 70), (-110, 68), (-95, 70), (-85, 73),
     (-75, 78), (-62, 66), (-55, 52), (-65, 45), (-70, 42), (-75, 35), (-81, 25),
     (-83, 22), (-88, 21), (-90, 29), (-97, 26), (-105, 20), (-110, 23), (-115, 32),
     (-124, 40), (-130, 55), (-140, 60), (-155, 58), (-168, 65)],
    [(-92, 14), (-86, 12), (-83, 9), (-78, 8), (-70, 11), (-60, 10), (-52, 5), (-45, -2),
     (-35, -6), (-38, -13), (-48, -25), (-55, -35), (-62, -40), (-65, -50), (-70, -55),
     (-73, -45), (-72, -35), (-71, -25), (-70, -18), (-76, -10), (-80, -3), (-79, 2),
     (-83, 8), (-88, 16), (-92, 14)],
    [(-17, 15), (-10, 27), (0, 32), (10, 37), (25, 32), (35, 30), (43, 12), (51, 12),
     (45, 0), (40, -10), (35, -22), (28, -33), (20, -34), (15, -25), (12, -15),
     (9, 4), (0, 5), (-8, 4), (-13, 10), (-17, 15)],
    [(-10, 37), (-9, 43), (-2, 43), (0, 48), (-5, 48), (2, 51), (4, 53), (8, 54),
     (10, 57), (5, 60), (12, 65), (20, 70), (28, 71), (40, 68), (55, 70), (70, 73),
     (85, 74), (100, 76), (115, 73), (130, 72), (145, 72), (160, 70), (170, 68),
     (180, 66), (175, 62), (160, 60), (155, 55), (150, 48), (140, 45), (135, 38),
     (126, 38), (122, 30), (118, 24), (110, 21), (108, 11), (104, 8), (100, 13),
     (98, 16), (93, 22), (88, 21), (80, 15), (77, 8), (73, 20), (68, 24), (62, 25),
     (57, 22), (51, 25), (48, 29), (43, 13), (35, 12), (35, 28), (33, 31), (35, 36),
     (28, 40), (23, 40), (18, 40), (15, 38), (12, 45), (8, 44), (3, 43), (-2, 41),
     (-6, 36), (-10, 37)],
    [(113, -22), (114, -34), (118, -35), (129, -32), (135, -35), (140, -38), (147, -38),
     (150, -35), (153, -28), (153, -25), (146, -19), (142, -11), (136, -12), (130, -11),
     (125, -14), (122, -17), (113, -22)],
    [(-45, 60), (-52, 66), (-55, 72), (-45, 78), (-30, 82), (-20, 78), (-22, 70),
     (-32, 64), (-45, 60)],
    [(43, -12), (50, -16), (50, -25), (45, -25), (43, -20), (43, -12)],
    [(-5, 50), (-6, 55), (-3, 58), (0, 54), (1, 51), (-5, 50)],
    [(130, 31), (133, 34), (138, 35), (141, 39), (145, 44), (142, 44), (139, 37),
     (134, 34), (130, 31)],
    [(166, -46), (170, -44), (174, -41), (178, -38), (175, -37), (172, -41), (166, -46)],
    [([(l, -70 + 6 * math.sin(l / 40.0)) for l in range(-180, 181, 20)]
      + [(180, -88), (-180, -88)])][0],
]


def world_map(t, points=(), title="WHERE"):
    """Equirectangular world outline with locations pulsing in.

    points: list of (name, lon, lat).
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.16, seed=31)

    mw, mh = 1440, 720
    ox, oy = (W - mw) / 2, 185
    def XY(lon, lat):
        return (ox + (lon + 180) / 360.0 * mw, oy + (90 - lat) / 180.0 * mh)

    # graticule
    for lon in range(-180, 181, 30):
        x, _ = XY(lon, 0)
        d.line([(x, oy), (x, oy + mh)], fill=(*CYAN, 22), width=1)
    for lat in range(-60, 61, 30):
        _, y = XY(0, lat)
        d.line([(ox, y), (ox + mw, y)], fill=(*CYAN, 22), width=1)
    _, yeq = XY(0, 0)
    d.line([(ox, yeq), (ox + mw, yeq)], fill=(*CYAN, 58), width=1)
    d.rectangle([ox, oy, ox + mw, oy + mh], outline=(*CYAN, 45), width=1)

    fill = (*mix(MID, INK, 0.35), 235)
    edge = (*mix(CYAN, MID, 0.45), 190)
    for poly in _LAND:
        pts = [XY(lo, la) for lo, la in poly]
        d.polygon(pts, fill=fill)
        d.line(pts + [pts[0]], fill=edge, width=1)

    # ---- pins
    pts = list(points)
    placed = []
    for i, (name, lon, lat) in enumerate(pts):
        a = _rev(t, i, len(pts), lead=0.5)
        if a <= 0.01:
            continue
        A = int(255 * a)
        x, y = XY(lon, lat)
        pulse = (t * 1.6 + i * 0.27) % 1.0
        rr = 10 + pulse * 34
        d.ellipse([x - rr, y - rr, x + rr, y + rr],
                  outline=(*CYAN, int(A * (1 - pulse) * 0.7)), width=2)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(*AMBER, A))

        f = _fit(d, name, F_LABEL, 25, W * 0.20)
        tw = d.textlength(name, font=f)
        rightside = x + tw + 34 < ox + mw
        lx = x + 16 if rightside else x - 16 - tw
        ly = y - 13
        # push down until this label clears the ones already drawn
        for _ in range(8):
            if not any(abs(ly - py) < 26 and lx < px + pw and px < lx + tw
                       for px, py, pw in placed):
                break
            ly += 27
        ly = max(oy + 4, min(ly, oy + mh - 28))
        placed.append((lx, ly, tw))
        d.text((lx, ly), name, font=f, fill=(*TEXT, A))

    _header(d, title)
    return _finish(img, ov)


# ---------------------------------------------------------------- 3. timeline

def timeline(t, events=(), title="TIMELINE"):
    """Horizontal dated timeline; events reveal left to right.

    events: list of (year, label). `year` is drawn verbatim as given.
    """
    img = _bg(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=50, speed=0.2, seed=17)

    ev = list(events)
    n = max(len(ev), 1)
    axis_y = H * 0.52
    x0, x1 = W * 0.09, W * 0.91
    prog = ease(min(t * 1.25, 1))
    d.line([(x0, axis_y), (x0 + (x1 - x0) * prog, axis_y)], fill=(*CYAN, 170), width=2)

    slot_w = (x1 - x0) / n
    maxw = slot_w * 0.92
    fy = font(F_MONO, 30)
    fl = font(F_LABEL, 25)
    for i, (year, label) in enumerate(ev):
        cx = x0 + slot_w * (i + 0.5)
        a = _rev(t, i, n, lead=0.55)
        if a <= 0.01:
            continue
        A = int(255 * a)
        up = (i % 2 == 0)
        stem = 60 + (0 if up else 0)
        ty = axis_y - stem if up else axis_y + stem
        d.line([(cx, axis_y), (cx, ty)], fill=(*CYAN, int(A * 0.6)), width=1)
        rr = 6 * a
        d.ellipse([cx - rr, axis_y - rr, cx + rr, axis_y + rr], fill=(*AMBER, A))

        ys = str(year)
        fyy = _fit(d, ys, F_MONO, 30, maxw)
        lines = _wrap(d, label, fl, maxw)
        if len(lines) > 3:
            lines = lines[:3]
        lh = 30
        if up:
            year_y = ty - 34
            block_y = year_y - 8 - len(lines) * lh
        else:
            year_y = ty + 4
            block_y = year_y + 40
        _ctext(d, ys, fyy, year_y, (*AMBER, A), cx=cx)
        for j, ln in enumerate(lines):
            _ctext(d, ln, fl, block_y + j * lh, (*TEXT, int(A * 0.92)), cx=cx)

    _header(d, title)
    return _finish(img, ov)


# ---------------------------------------------------------------- 4. pressure

def pressure_gauge(t, depth_m=1000, label="PRESSURE AT DEPTH", max_atm=None):
    """Dial climbing to the pressure at depth_m. atm = 1 + depth_m/10."""
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.18, seed=5)

    target_atm = 1 + depth_m / 10.0
    if max_atm is None:
        step = 10 ** max(0, int(math.floor(math.log10(max(target_atm, 1)))))
        max_atm = math.ceil(target_atm / step) * step
        if max_atm <= target_atm:
            max_atm += step
    e = ease(min(t * 1.35, 1))
    cur_atm = 1 + (target_atm - 1) * e
    cur_depth = depth_m * e

    # Dial sits high; the readout lives below it. The needle therefore never
    # crosses any type — the failure mode of putting the value inside the dial.
    cx, cy, R = W / 2, H * 0.40, 235
    A0, A1 = 135.0, 405.0          # a 270-degree sweep, gap at the bottom
    def ang(v):
        return math.radians(A0 + (A1 - A0) * max(0.0, min(1.0, v / max_atm)))

    box = [cx - R, cy - R, cx + R, cy + R]
    d.arc(box, A0, A1, fill=(*MUTED, 70), width=3)
    d.arc(box, A0, A0 + (A1 - A0) * min(1.0, cur_atm / max_atm), fill=(*CYAN, 235), width=9)

    ticks = 8
    fm = font(F_MONO, 19)
    for k in range(ticks + 1):
        v = max_atm * k / ticks
        aa = ang(v)
        ca, sa = math.cos(aa), math.sin(aa)
        major = (k % 2 == 0)
        r0 = R + (8 if major else 8)
        r1 = R + (26 if major else 17)
        d.line([(cx + ca * r0, cy + sa * r0), (cx + ca * r1, cy + sa * r1)],
               fill=(*CYAN, 150 if major else 65), width=2 if major else 1)
        if major:
            lab = f"{int(v):,}"
            tw = d.textlength(lab, font=fm)
            d.text((cx + ca * (R + 52) - tw / 2, cy + sa * (R + 52) - 11),
                   lab, font=fm, fill=(*MUTED, 165))

    aa = ang(cur_atm)
    ca, sa = math.cos(aa), math.sin(aa)
    d.line([(cx - ca * 22, cy - sa * 22), (cx + ca * (R - 26), cy + sa * (R - 26))],
           fill=(*AMBER, 245), width=4)
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(*AMBER, 255))

    # depth reads inside the dial, in the wedge the needle can never enter
    dep = f"{int(cur_depth):,} m"
    fdp = _fit(d, dep, F_MONO, 32, R * 1.15)
    _ctext(d, dep, fdp, cy + R * 0.52, (*MUTED, 225), cx=cx)

    val = f"{cur_atm:,.0f}"
    fv = _fit(d, val, F_DISPLAY, 132, W * 0.40)
    _ctext(d, val, fv, cy + R + 92, (*TEXT, 255), cx=cx)
    _ctext(d, "ATMOSPHERES", font(F_LABEL, 28), cy + R + 262, (*CYAN, 220),
           spacing=11, cx=cx)
    _ctext(d, "1 atm at the surface  ·  +1 atm every 10 m",
           font(F_LABEL, 24), H - 64, (*MUTED, 175))
    _header(d, label)
    return _finish(img, ov)


# ---------------------------------------------------------------- 5. light

_DEFAULT_BANDS = [("RED", 15, 0), ("ORANGE", 30, 28), ("YELLOW", 50, 55),
                  ("GREEN", 100, 120), ("BLUE", 200, 208)]


def light_attenuation(t, bands=None, max_depth=None, title="WHERE THE COLOUR GOES",
                      caption="Water absorbs the long wavelengths first."):
    """Wavelengths dying with depth. bands: (name, extinction_m, hue_degrees).

    The depth axis is a square-root scale, not linear — on a linear axis the red
    band is a 50-pixel stub against 900 pixels of empty blue. The axis is
    explicitly ticked at every band depth so the compression is visible, not hidden.
    """
    img = _bg(mix(MID, PALE, 0.10), INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    bands = list(bands or _DEFAULT_BANDS)
    max_depth = max_depth or max(b[1] for b in bands)
    top, bot = 165, H - 140
    def Y(m):
        return top + math.sqrt(max(m, 0) / max_depth) * (bot - top)

    n = len(bands)
    left, right = W * 0.22, W * 0.955
    colw = (right - left) / n

    for i, (name, ext, hue) in enumerate(bands):
        a = _rev(t, i, n, lead=0.35)
        if a <= 0.01:
            continue
        col = _hue(hue)
        cx = left + colw * (i + 0.5)
        bw = colw * 0.66
        yend = Y(min(ext, max_depth))
        # the band itself: a strip that fades out as its wavelength is absorbed
        steps = 30
        for s in range(steps):
            f0, f1 = s / steps, (s + 1) / steps
            y0 = top + (yend - top) * f0
            y1 = top + (yend - top) * f1 + 1
            fade = (1 - f0) ** 1.5
            d.rectangle([cx - bw / 2, y0, cx + bw / 2, y1],
                        fill=(*col, int(225 * fade * a)))
        d.line([(cx - bw / 2, top), (cx + bw / 2, top)], fill=(*col, int(245 * a)), width=4)
        # name above the surface line, extinction depth just under the tail
        fn_ = _fit(d, name, F_LABEL, 27, colw * 0.92)
        _ctext(d, name, fn_, top - 44, (*col, int(240 * a)), cx=cx)
        dl = f"{ext:,} m"
        fd = _fit(d, dl, F_MONO, 24, colw * 0.92)
        _ctext(d, dl, fd, min(yend + 14, bot - 30), (*MUTED, int(220 * a)), cx=cx)

    # depth scale on the left, ticked at the band depths themselves
    fm = font(F_MONO, 20)
    ax = left - 78
    d.line([(ax, top), (ax, bot)], fill=(*CYAN, 60), width=1)
    marks = sorted({0} | {min(b[1], max_depth) for b in bands})
    prev_y = -99
    for m in marks:
        y = Y(m)
        if y - prev_y < 26:
            continue
        prev_y = y
        d.line([(ax - 7, y), (ax + 7, y)], fill=(*CYAN, 130), width=1)
        d.line([(ax + 7, y), (right, y)], fill=(*CYAN, 22), width=1)
        lab = f"{int(m):,} m"
        d.text((ax - 16 - d.textlength(lab, font=fm), y - 11), lab,
               font=fm, fill=(*MUTED, 175))
    _ctext(d, "SURFACE", font(F_LABEL, 21), top - 72, (*MUTED, 165), spacing=6, cx=ax + 4)

    if caption:
        _ctext(d, caption, _fit(d, caption, F_LABEL, 28, W * 0.7), H - 78, (*AMBER, 215))
    _header(d, title)
    return _finish(img, ov)


# ---------------------------------------------------------------- 6. text beat

def text_beat(t, lines=(), emphasis=None, font_size=64):
    """A spoken sentence, revealed line by line. `emphasis` = index or exact line."""
    img = _bg(INK, DEEP)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=35, speed=0.14, seed=13)

    src = [l for l in (list(lines) if not isinstance(lines, str) else [lines]) if l]
    maxw = W * 0.74
    # wrap first, remembering which source line each visual line came from
    vis = []
    for si, ln in enumerate(src):
        f = _fit(d, ln, F_DISPLAY, font_size, maxw, minsize=30)
        for w in _wrap(d, ln, f, maxw):
            vis.append((si, w, f))
    if not vis:
        return _finish(img, ov)

    lh = max(f.size for _, _, f in vis) * 1.42
    total = lh * len(vis)
    if total > H * 0.66:                       # scale down rather than run off canvas
        k = (H * 0.66) / total
        vis = [(si, w, font(F_DISPLAY, max(28, int(f.size * k)))) for si, w, f in vis]
        lh = max(f.size for _, _, f in vis) * 1.42
        total = lh * len(vis)
    y = (H - total) / 2

    def hot(si, txt):
        if emphasis is None:
            return False
        if isinstance(emphasis, int):
            return si == emphasis
        return str(emphasis).strip() == src[si].strip()

    for i, (si, txt, f) in enumerate(vis):
        a = _rev(t, i, len(vis), lead=0.45)
        if a <= 0.01:
            continue
        rise = (1 - a) * 22
        col = AMBER if hot(si, txt) else TEXT
        _ctext(d, txt, f, y + i * lh + rise, (*col, int(255 * a)))

    # a quiet rule under the block, wiping in
    wln = int(W * 0.10 * ease(min(t * 1.8, 1)))
    d.rectangle([W / 2 - wln / 2, y + total + 44, W / 2 + wln / 2, y + total + 47],
                fill=(*CYAN, 180))
    return _finish(img, ov)


# ---------------------------------------------------------------- 7. size ladder

def _human(d, x, baseline, h, col, A):
    """Simple standing figure of height h px, feet on `baseline`, centred on x."""
    head = h * 0.13
    d.ellipse([x - head / 2, baseline - h, x + head / 2, baseline - h + head], fill=(*col, A))
    ty = baseline - h + head
    d.line([(x, ty), (x, baseline - h * 0.42)], fill=(*col, A), width=max(2, int(h * 0.045)))
    d.line([(x - h * 0.15, ty + h * 0.30), (x, ty + h * 0.05), (x + h * 0.15, ty + h * 0.30)],
           fill=(*col, A), width=max(2, int(h * 0.035)))
    d.line([(x - h * 0.13, baseline), (x, baseline - h * 0.42), (x + h * 0.13, baseline)],
           fill=(*col, A), width=max(2, int(h * 0.04)))


def size_ladder(t, items=(), human_m=1.8, title="TO SCALE", sort=True):
    """Lengths from a common left baseline, with a human silhouette for scale.

    items: list of (label, metres). The scale is LINEAR and shared with the human
    figure's height, so the comparison is literal. That honesty has a cost — see
    the notes: an item an order of magnitude shorter than the longest becomes a
    stub, and this segment is the wrong choice for that spread of sizes.
    """
    img = _bg(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.2, seed=29)

    it = [(str(l), float(m)) for l, m in items]
    if not it:
        return _finish(img, ov)
    if sort:
        it.sort(key=lambda p: -p[1])
    biggest = max(max(m for _, m in it), human_m)

    fm = font(F_MONO, 24)
    x0 = W * 0.10
    # leave room at the right for the longest value label so nothing ever clips
    x1 = W - 40 - d.textlength(f"{biggest:,.1f} m", font=fm) - 20
    ppm = (x1 - x0) / biggest
    ground = H - 96
    top = 165
    # the human is drawn at the SAME metres-per-pixel, so the strip it needs is
    # derived from its height — that is what keeps the rows off its label.
    hh = min(human_m * ppm, ground - top - 260)
    bot = ground - hh - 62

    rows = len(it)
    rh = (bot - top) / rows
    bar_h = min(rh * 0.40, 54)
    body_col = mix(CYAN, MID, 0.55)

    d.line([(x0, top - 20), (x0, ground + 6)], fill=(*CYAN, 70), width=1)

    for i, (label, m) in enumerate(it):
        a = _rev(t, i, rows, lead=0.42)
        if a <= 0.01:
            continue
        A = int(255 * a)
        cy = top + rh * (i + 0.5)
        wpx = max(8.0, m * ppm) * a
        y0, y1 = cy - bar_h / 2, cy + bar_h / 2
        # a lozenge, not a bar — closer to a body than to a chart
        d.ellipse([x0, y0, x0 + min(bar_h, wpx), y1], fill=(*body_col, A))
        if wpx > bar_h:
            d.rectangle([x0 + bar_h / 2, y0, x0 + wpx - bar_h * 0.15, y1],
                        fill=(*body_col, A))
            d.polygon([(x0 + wpx - bar_h * 0.5, y0), (x0 + wpx, cy),
                       (x0 + wpx - bar_h * 0.5, y1)], fill=(*body_col, A))
        d.line([(x0 + wpx, y0 - 7), (x0 + wpx, y1 + 7)], fill=(*CYAN, A), width=2)

        lab = _fit(d, label, F_LABEL, 27, W * 0.30)
        d.text((x0 + 12, y0 - 36), label, font=lab, fill=(*TEXT, A))
        val = f"{m:,.1f} m".replace(".0 m", " m")
        vw = d.textlength(val, font=fm)
        vx = min(x0 + wpx + 16, W - 40 - vw)      # never runs off canvas
        d.text((vx, cy - 14), val, font=fm, fill=(*AMBER, A))

    # ---- human, on the same baseline and the same metres-per-pixel
    ha = ease(min(t * 2.2, 1))
    hx = x0 + 40
    d.line([(x0, ground + 6), (x1, ground + 6)], fill=(*MUTED, 120), width=2)
    _human(d, hx, ground, hh, PALE, int(210 * ha))
    d.line([(hx + 26, ground - hh), (hx + 210, ground - hh)],
           fill=(*PALE, int(90 * ha)), width=1)
    hl = f"HUMAN · {human_m:g} m — same scale"
    fh = _fit(d, hl, F_LABEL, 22, W * 0.34)
    d.text((hx + 40, ground - hh - 32), hl, font=fh, fill=(*MUTED, int(200 * ha)))
    _header(d, title)
    return _finish(img, ov)


# ---------------------------------------------------------------- 8. ambient

def ambient_drift(t, variant=0):
    """Connective tissue. No text. 5 distinct looks; variant is taken mod 5."""
    v = int(variant) % 5
    R, C = _ROWS, _COLS
    yy, xx = np.mgrid[0:R, 0:C].astype(np.float32)
    xx = xx / C
    yy = yy / R
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    if v == 0:      # upper column, light rippling on the surface above
        img = _atmos(MID, INK, [(_caustics(t, 0, R, C, gain=0.34), PALE)])
        _dust(d, t, n=95, speed=0.30, seed=101)

    elif v == 1:    # current: soft streaks of water pulling past
        r = random.Random(202)
        streaks = []
        for _ in range(18):
            gy = r.random() * R
            sp = r.uniform(0.5, 1.8)
            gx = ((r.random() + t * sp * 0.35) % 1.4 - 0.2) * C
            streaks.append((gx, gy + math.sin(t * 3 + gy) * 0.8,
                            r.uniform(9, 26), r.uniform(0.8, 1.8),
                            r.uniform(0.05, 0.15)))
        img = _atmos(DEEP, INK, [(_blobs(streaks, R, C), CYAN)])
        _dust(d, t, n=70, speed=0.5, seed=203, size=(1, 2))

    elif v == 2:    # the abyss: near-black, sparse bioluminescent motes
        r = random.Random(304)
        motes, cores = [], []
        for k in range(12):
            x0, y0 = r.random(), r.random()
            sp = r.uniform(0.05, 0.18)
            gx = (x0 + math.sin(t * 2 + k) * 0.02) * C
            gy = ((y0 - t * sp) % 1.0) * R
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 6 + k * 1.7))
            sig = r.uniform(1.8, 4.2)
            motes.append((gx, gy, sig, sig, 0.38 * pulse))
            cores.append((gx / C * W, gy / R * H, sig * 0.8, pulse))
        img = _atmos(INK, mix(INK, DEEP, 0.45), [(_blobs(motes, R, C), PALE)])
        for x, y, rr, pulse in cores:      # a hard point of light inside each glow
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(*PALE, int(185 * pulse)))
        _dust(d, t, n=40, speed=0.12, seed=305, size=(1, 2))

    elif v == 3:    # a shaft of light falling from far above
        drift = 0.5 + 0.10 * math.sin(t * 2 * math.pi * 0.5)
        spread = 0.05 + yy * 0.30
        beam = np.clip(1 - np.abs(xx - (drift + yy * 0.10)) / spread, 0, 1) ** 2
        beam *= np.clip(1.1 - yy * 1.15, 0, 1) * 0.42
        beam += _caustics(t, 4, R, C, gain=0.10)
        img = _atmos(mix(MID, DEEP, 0.4), INK, [(beam, PALE)])
        _dust(d, t, n=120, speed=0.55, seed=406)

    else:           # v == 4: near the floor — heavy snow rising, silt glowing below
        floor = np.clip((yy - 0.72) / 0.28, 0, 1) ** 2 * 0.34
        shear = (0.5 + 0.5 * np.sin(yy * 14 + t * 2 * math.pi)) * 0.05
        img = _atmos(mix(DEEP, MID, 0.3), INK, [(floor + shear, MID)])
        r = random.Random(507)
        for _ in range(150):
            x0, y0 = r.random(), r.random()
            sp = r.uniform(0.3, 1.1)
            rad = r.uniform(1, 4)
            y = ((y0 - t * sp * 0.5) % 1.0) * H
            x = (x0 * W) + math.sin(t * 2 + y0 * 12) * 22
            d.ellipse([x - rad, y - rad, x + rad, y + rad],
                      fill=(*PALE, int(r.uniform(35, 130))))

    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
