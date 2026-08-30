"""Second extension pack: renderers for METHOD, EVIDENCE and UNCERTAINTY prose.

The first two packs cover the *subject* — depth, pressure, light, zones, anatomy,
size, place, date. This pack covers the *epistemics*: how a number was obtained,
what it does and does not include, who reports what, and how sure anyone is.
That is what these scripts are actually made of, and it was previously rendered
as `text_beat` because nothing better existed.

Same contract as segments.py / segments_ext.py:

    fn(t, **kwargs) -> PIL.Image (RGB, W x H), t in [0, 1]

Same palette, same fonts, same restraint. **Nothing here bakes in a fact.** Every
string and every number drawn on screen arrives through kwargs; a renderer called
with no arguments draws its chrome and nothing else. Colour and type come only
from design.py.

Text safety reuses the primitives proven in segments_ext (_fit / _wrap / _slot),
so nothing overlaps and nothing leaves the canvas.

Wiring
------
Two integration points live in files this module is not permitted to edit, so
they are provided here instead and applied by `install()`:

  * `planner.parse_directive` learns the eight new directives (see CONTRACT.md).
  * `planner.INFO`-style informational sets gain the eight new segment names.

`install()` runs automatically at import and is idempotent. To activate the pack
add ONE line — `import segments_ext2` — before planning or assembling. See the
"handoff" note at the bottom of this file.
"""
import math
import random

from PIL import Image, ImageDraw

from design import *
from segments_ext import (
    font, _bg, _dust, _ctext, _header, _fit, _wrap, _slot, _finish, _rev,
)

__all__ = [
    "evidence_chain", "uncertainty_bar", "source_compare", "process_steps",
    "contrast_pair", "magnitude_bar", "definition_card", "checklist_reveal",
    "SEGMENTS", "INFO", "install",
]

SEGMENTS = ("evidence_chain", "uncertainty_bar", "source_compare", "process_steps",
            "contrast_pair", "magnitude_bar", "definition_card", "checklist_reveal")

#: The informational segments contributed by this pack, for runtime accounting.
INFO = frozenset(SEGMENTS)


# ---------------------------------------------------------------- primitives

# Text metrics do not change across the frames of one beat, but _fit walks font
# sizes and _wrap measures every word — at 30 fps that is the same work 200-odd
# times. Memoising both is the single biggest saving in this pack.
_fitc, _wrapc = {}, {}


def _cfit(d, text, path, size, maxw, minsize=14):
    k = (str(text), path, int(size), int(maxw), int(minsize))
    if k not in _fitc:
        if len(_fitc) > 3000:
            _fitc.clear()
        _fitc[k] = _fit(d, str(text), path, size, maxw, minsize)
    return _fitc[k]


def _cwrap(d, text, f, maxw):
    k = (str(text), f.path if hasattr(f, "path") else id(f), f.size, int(maxw))
    if k not in _wrapc:
        if len(_wrapc) > 3000:
            _wrapc.clear()
        _wrapc[k] = _wrap(d, text, f, maxw)
    return _wrapc[k]


def _panel(d, box, alpha_edge=150, alpha_fill=26, col=None, radius=10, width=2):
    """The house card: a barely-there fill with a crisp single-weight edge."""
    col = col or CYAN
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=(*mix(DEEP, col, 0.10), alpha_fill))
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=(*col, alpha_edge), width=width)


def _arrow(d, x0, y, x1, col, A, head=9, width=2):
    """A left-to-right connector. Used only between stages of one argument."""
    if x1 - x0 < 4:
        return
    d.line([(x0, y), (x1 - head, y)], fill=(*col, A), width=width)
    d.polygon([(x1, y), (x1 - head, y - head * 0.55), (x1 - head, y + head * 0.55)],
              fill=(*col, A))


def _block(d, lines, f, cx, y, lh, fill, A, align="center"):
    """Draw pre-wrapped lines; returns the y below the block."""
    for i, ln in enumerate(lines):
        if align == "center":
            _ctext(d, ln, f, y + i * lh, (*fill, A), cx=cx)
        else:
            d.text((cx, y + i * lh), ln, font=f, fill=(*fill, A))
    return y + len(lines) * lh


def _pairs(items):
    """Normalise (a, b) tuples / 'a=b' strings into a list of 2-tuples."""
    out = []
    for it in items or ():
        if isinstance(it, (tuple, list)):
            out.append((str(it[0]), str(it[1]) if len(it) > 1 else ""))
        else:
            a, _, b = str(it).partition("=")
            out.append((a.strip(), b.strip()))
    return out


def _num(s):
    """Best-effort float from a narrated value string. None if there isn't one."""
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        m = None
        for tok in str(s).replace(",", "").split():
            try:
                m = float(tok.strip("()%±+"))
                break
            except ValueError:
                continue
        return m


# ------------------------------------------------------------ 1. evidence chain

def evidence_chain(t, stages=(), title="HOW THE NUMBER IS MADE", conclusion=""):
    """instrument -> signal -> correction -> conclusion, as a flowing chain.

    stages: 2-5 items, each a string or (label, detail). Drawn verbatim.
    conclusion: optional single line beneath, arriving last.

    The chain is the honest shape for this prose: these scripts almost never
    assert a bare number, they assert a number *plus the path that produced it*.
    """
    img = _bg(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.18, seed=41)

    st = _pairs(stages)[:5]
    n = len(st)
    if n:
        x0, x1 = W * 0.06, W * 0.94
        gap = 34 if n > 3 else 46
        cw = ((x1 - x0) - gap * (n - 1)) / n
        maxw = cw - 44

        fl = font(F_LABEL, 27 if n <= 3 else 24)
        fd = font(F_LABEL, 23 if n <= 3 else 20)

        # card height follows the tallest card's CONTENT — a fixed height leaves
        # a third of every card empty, which is what a first pass at this did.
        def fit_wrap(text, base, path, maxw, maxlines, minsize):
            """Largest size <= base whose WRAPPED text fits maxlines.

            _cfit alone shrinks until the string fits on ONE line and then the
            caller wraps it anyway — so a long stage rendered at the minimum size
            with two lines of slack. Wrapping is the thing to measure."""
            size = int(base)
            while size > minsize:
                f = font(path, size)
                if len(_cwrap(d, text, f, maxw)) <= maxlines:
                    return f
                size -= 2
            return font(path, minsize)

        content = []
        for lab, det in st:
            fli = fit_wrap(lab, fl.size, F_LABEL, maxw, 3, 17)
            ll = _cwrap(d, lab, fli, maxw)[:3]
            dl = _cwrap(d, det, fd, maxw)[:4] if det else []
            content.append((fli, ll, dl,
                            len(ll) * fli.size * 1.30
                            + (18 + len(dl) * fd.size * 1.34 if dl else 0)))
        ch = min(H * 0.52, max(150, max(c[3] for c in content) + 92))
        cy = H * (0.44 if conclusion else 0.50)
        top = cy - ch / 2

        for i, (lab, det) in enumerate(st):
            a = _rev(t, i, n, lead=0.5)
            if a <= 0.01:
                continue
            A = int(255 * a)
            bx = x0 + i * (cw + gap)
            last = (i == n - 1)
            col = AMBER if last else CYAN
            _panel(d, (bx, top, bx + cw, top + ch),
                   alpha_edge=int(A * (0.85 if last else 0.62)),
                   alpha_fill=int(A * 0.13), col=col)

            # stage index, quiet, so the order is unambiguous
            d.text((bx + 18, top + 14), f"{i + 1}", font=font(F_MONO, 21),
                   fill=(*MUTED, int(A * 0.65)))

            fli, llines, dlines, tot = content[i]
            lh_l, lh_d = fli.size * 1.30, fd.size * 1.34
            ty = top + (ch - tot) / 2
            cx = bx + cw / 2
            ty = _block(d, llines, fli, cx, ty, lh_l, col, A)
            if dlines:
                _block(d, dlines, fd, cx, ty + 18, lh_d, MUTED, int(A * 0.92))

            if i < n - 1:
                aa = _rev(t, i + 0.5, n, lead=0.5)
                if aa > 0.01:
                    _arrow(d, bx + cw + 6, cy, bx + cw + gap - 6, CYAN, int(200 * aa))

        if conclusion:
            a = _rev(t, n - 0.2, n, lead=0.5)
            if a > 0.01:
                fc = _cfit(d, conclusion, F_DISPLAY, 38, W * 0.80, minsize=24)
                _ctext(d, conclusion, fc, top + ch + 78, (*TEXT, int(235 * a)))

    _header(d, title)
    return _finish(img, ov)


# ----------------------------------------------------------- 2. uncertainty bar

def uncertainty_bar(t, value="", unit="", plus=None, minus=None, confidence="",
                    caption="", title="MEASURED VALUE AND RANGE"):
    """A value drawn as a BAND, not a point. The range is the subject.

    value:      centre, as narrated (string kept verbatim for display)
    plus/minus: half-widths in the same unit; minus defaults to plus
    confidence: e.g. "95 percent confidence", drawn verbatim if given
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=40, speed=0.16, seed=43)

    e = ease(min(t * 1.4, 1))
    cx = W / 2
    axis_y = H * 0.62
    span = W * 0.62                      # full drawn width of the axis

    v = _num(value)
    p = _num(plus)
    m = _num(minus) if minus is not None else p

    # The band occupies a fixed, generous fraction of the axis. The axis is
    # therefore NOT to scale against zero, and it is labelled as a range, never
    # as an absolute scale, so nothing false is implied.
    half = span * 0.30

    # value, large, above the band
    if value:
        fv = _cfit(d, str(value), F_DISPLAY, 170, W * 0.60, minsize=60)
        rise = (1 - ease(min(t * 3, 1))) * 26
        _ctext(d, str(value), fv, H * 0.20 + rise, (*TEXT, 255))
        if unit:
            _ctext(d, str(unit).upper(), font(F_LABEL, 32), H * 0.20 + fv.size * 1.22 + rise,
                   (*CYAN, 230), spacing=11)

    # the band itself
    bw = half * e
    bh = 46
    d.rectangle([cx - bw, axis_y - bh / 2, cx + bw, axis_y + bh / 2], fill=(*CYAN, 62))
    d.rectangle([cx - bw, axis_y - bh / 2, cx + bw, axis_y + bh / 2],
                outline=(*CYAN, 165), width=2)
    # end caps
    for sx in (-1, 1):
        d.line([(cx + sx * bw, axis_y - bh / 2 - 12), (cx + sx * bw, axis_y + bh / 2 + 12)],
               fill=(*CYAN, int(210 * e)), width=2)
    # centre tick — the point estimate
    d.line([(cx, axis_y - bh / 2 - 22), (cx, axis_y + bh / 2 + 22)], fill=(*AMBER, 255), width=3)

    # bound labels, verbatim from the narration's own ± figure
    a2 = ease(max(0.0, min(1.0, (t - 0.30) * 2.6)))
    if a2 > 0.01:
        A = int(255 * a2)
        fm = font(F_MONO, 27)
        if p is not None and v is not None:
            lo = v - (m if m is not None else p)
            hi = v + p
            fmt = (lambda x: f"{x:,.0f}") if float(v).is_integer() else (lambda x: f"{x:,.2f}")
            _ctext(d, fmt(lo), fm, axis_y + bh / 2 + 40, (*MUTED, A), cx=cx - bw)
            _ctext(d, fmt(hi), fm, axis_y + bh / 2 + 40, (*MUTED, A), cx=cx + bw)
        if p is not None:
            pm = f"± {plus}" + (f" {unit.lower()}" if unit else "")
            if minus is not None and _num(minus) != p:
                pm = f"+{plus} / -{minus}" + (f" {unit.lower()}" if unit else "")
            _ctext(d, pm, font(F_MONO, 30), axis_y - bh / 2 - 74, (*AMBER, A))
        if confidence:
            fc = _cfit(d, str(confidence), F_LABEL, 27, W * 0.5, minsize=17)
            _ctext(d, str(confidence), fc, axis_y + bh / 2 + 84, (*CYAN, int(A * 0.9)))

    if caption:
        a3 = ease(max(0.0, min(1.0, (t - 0.42) * 2.4)))
        if a3 > 0.01:
            fcp = font(F_LABEL, 30)
            lines = _cwrap(d, caption, fcp, W * 0.74)[:2]
            _block(d, lines, fcp, cx, H - 148, fcp.size * 1.36, MUTED, int(235 * a3))

    _header(d, title)
    return _finish(img, ov)


# ------------------------------------------------------------ 3. source compare

def source_compare(t, sources=(), title="WHAT EACH SOURCE REPORTS"):
    """2-4 named sources side by side and what each one actually says.

    sources: list of (name, claim). Names and claims are drawn verbatim; this
    segment exists precisely because these scripts often present two authorities
    that do not agree, and flattening that into one number would be a lie.
    """
    img = _bg(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.18, seed=47)

    src = _pairs(sources)[:4]
    n = len(src)
    if n:
        x0, x1 = W * 0.06, W * 0.94
        gap = 40
        cw = ((x1 - x0) - gap * (n - 1)) / n
        maxw = cw - 52
        fn_ = font(F_LABEL, 27 if n <= 3 else 23)
        fc_ = font(F_DISPLAY, 40 if n <= 2 else (34 if n == 3 else 29))

        # measure every card first; the panel is sized to the tallest content so
        # short claims do not sit in a mostly empty box.
        # ONE name font and ONE claim font across the row: fitting each card
        # independently makes the divider rules sit at different heights, which
        # reads as sloppy typesetting rather than as emphasis.
        fni = font(F_LABEL, min(_cfit(d, nm, F_LABEL, fn_.size, maxw, minsize=15).size
                                for nm, _ in src))
        fci = font(F_DISPLAY, min(_cfit(d, cl, F_DISPLAY, fc_.size, maxw, minsize=20).size
                                  for _, cl in src))
        content = []
        for name, claim in src:
            nl = _cwrap(d, name, fni, maxw)[:2]
            cl = _cwrap(d, claim, fci, maxw)[:6]
            content.append((nl, cl))
        nmax = max(len(nl) for nl, _ in content)
        cmax = max(len(cl) for _, cl in content)
        tot = nmax * fni.size * 1.30 + 72 + cmax * fci.size * 1.32
        ch = min(H * 0.62, max(210, tot + 68))
        top = H * 0.50 - ch / 2
        bot = top + ch
        ny0 = top + (ch - tot) / 2

        for i, (name, claim) in enumerate(src):
            a = _rev(t, i, n, lead=0.5)
            if a <= 0.01:
                continue
            A = int(255 * a)
            bx = x0 + i * (cw + gap)
            _panel(d, (bx, top, bx + cw, bot), alpha_edge=int(A * 0.55),
                   alpha_fill=int(A * 0.12))
            cx = bx + cw / 2
            nlines, clines = content[i]

            _block(d, nlines, fni, cx, ny0, fni.size * 1.30, CYAN, A)
            ry = ny0 + nmax * fni.size * 1.30 + 22
            d.line([(bx + 28, ry), (bx + cw - 28, ry)], fill=(*CYAN, int(A * 0.4)), width=1)
            _block(d, clines, fci, cx, ry + 34, fci.size * 1.32, TEXT, A)

    _header(d, title)
    return _finish(img, ov)


# ------------------------------------------------------------- 4. process steps

def process_steps(t, steps=(), title="METHOD", note=""):
    """Numbered stages of a method, revealed one at a time down the page.

    steps: 2-6 strings, or (heading, detail) pairs. Drawn verbatim.
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=40, speed=0.16, seed=53)

    st = _pairs(steps)[:6]
    n = len(st)
    if n:
        lx = W * 0.17
        top = H * (0.20 if not note else 0.18)
        bot = H * (0.88 if not note else 0.80)
        rowh = (bot - top) / n
        r = min(30, rowh * 0.30)
        fh = font(F_LABEL, int(min(38, max(22, rowh * 0.30))))
        fd = font(F_LABEL, int(min(27, max(18, rowh * 0.21))))
        maxw = W * 0.70

        for i, (head, det) in enumerate(st):
            a = _rev(t, i, n, lead=0.5)
            if a <= 0.01:
                continue
            A = int(255 * a)
            cy = top + rowh * (i + 0.5)
            # spine
            if i:
                pa = _rev(t, i - 0.4, n, lead=0.5)
                d.line([(lx, cy - rowh + r), (lx, cy - r)],
                       fill=(*CYAN, int(110 * pa)), width=2)
            d.ellipse([lx - r, cy - r, lx + r, cy + r], outline=(*CYAN, A), width=2,
                      fill=(*mix(DEEP, CYAN, 0.12), int(A * 0.5)))
            _ctext(d, str(i + 1), font(F_MONO, int(r * 1.05)), cy - r * 0.62,
                   (*AMBER, A), cx=lx)

            tx = lx + r + 34
            fhi = _cfit(d, head, F_LABEL, fh.size, maxw, minsize=17)
            hlines = _cwrap(d, head, fhi, maxw)[:2]
            dlines = _cwrap(d, det, fd, maxw)[:2] if det else []
            lh_h, lh_d = fhi.size * 1.26, fd.size * 1.30
            tot = len(hlines) * lh_h + (10 + len(dlines) * lh_d if dlines else 0)
            ty = cy - tot / 2 - fhi.size * 0.16
            ty = _block(d, hlines, fhi, tx, ty, lh_h, TEXT, A, align="left")
            if dlines:
                _block(d, dlines, fd, tx, ty + 10, lh_d, MUTED, int(A * 0.9), align="left")

        if note:
            a = _rev(t, n - 0.2, n, lead=0.5)
            fnn = _cfit(d, note, F_LABEL, 28, W * 0.78, minsize=18)
            _ctext(d, note, fnn, H * 0.88, (*AMBER, int(230 * a)))

    _header(d, title)
    return _finish(img, ov)


# ------------------------------------------------------------- 5. contrast pair

def contrast_pair(t, term="", includes=(), excludes=(),
                  left_label="WHAT IT INCLUDES", right_label="WHAT IT DOES NOT"):
    """What a term covers versus what it is routinely confused with.

    Two columns, deliberately symmetrical so neither side reads as the answer.
    The excluded side is drawn in MUTED with a struck marker, never in a colour
    that would read as "wrong" — these are boundaries, not errors.
    """
    img = _bg(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=45, speed=0.17, seed=59)

    inc = [str(x) for x in (includes or ()) if str(x).strip()][:5]
    exc = [str(x) for x in (excludes or ()) if str(x).strip()][:5]

    if term:
        ft = _cfit(d, str(term), F_DISPLAY, 66, W * 0.72, minsize=34)
        _ctext(d, str(term), ft, H * 0.13, (*TEXT, int(255 * ease(min(t * 3, 1)))))

    top, bot = H * 0.32, H * 0.88
    lefts = (W * 0.09, W * 0.545)
    colw = W * 0.365                     # usable width of each column
    d.line([(W / 2, top - 18), (W / 2, bot)], fill=(*MUTED, 70), width=1)

    n = max(len(inc), len(exc), 1)
    fi = font(F_LABEL, 30)
    tw = colw - 52                       # text starts to the right of its marker
    pad = 34

    # ONE type size across BOTH columns. Fitting each item independently makes the
    # longer-worded side render smaller, which reads as one column mattering less
    # than the other — the opposite of what a contrast is for.
    allit = inc + exc
    fu = font(F_LABEL, min([_cfit(d, it, F_LABEL, fi.size, tw, minsize=18).size
                            for it in allit] or [fi.size]))

    def measure(items):
        rows = []
        for it in items:
            lines = _cwrap(d, it, fu, tw)[:3]
            rows.append((fu, lines, len(lines) * fu.size * 1.26))
        return rows, (sum(r[2] for r in rows) + pad * (len(rows) - 1) if rows else 0)

    measured = [measure(inc), measure(exc)]
    avail_top = top + 62
    # ONE shared start line for both columns: independently centring them makes a
    # 2-item side float against a 3-item side and reads as a mistake.
    y_start = avail_top + max(0, (bot - avail_top - max(m[1] for m in measured)) / 2)

    for side, (items, label, col, lx) in enumerate((
            (inc, left_label, CYAN, lefts[0]), (exc, right_label, MUTED, lefts[1]))):
        _ctext(d, str(label).upper(), font(F_LABEL, 23), top - 4, (*col, 200),
               spacing=5, cx=lx + colw / 2)
        if not items:
            continue
        rows = measured[side][0]
        y = y_start
        for i, (fii, lines, h) in enumerate(rows):
            a = _rev(t, i * 2 + side, n * 2, lead=0.34)
            if a > 0.01:
                A = int(255 * a)
                my = y + fii.size * 0.62
                if side == 0:
                    d.line([(lx, my), (lx + 9, my + 9), (lx + 24, my - 12)],
                           fill=(*CYAN, A), width=3)
                else:
                    d.line([(lx + 2, my - 9), (lx + 20, my + 9)], fill=(*MUTED, A), width=3)
                    d.line([(lx + 20, my - 9), (lx + 2, my + 9)], fill=(*MUTED, A), width=3)
                _block(d, lines, fii, lx + 52, y, fii.size * 1.26,
                       TEXT if side == 0 else MUTED, A, align="left")
            y += h + pad

    return _finish(img, ov)


# ------------------------------------------------------------- 6. magnitude bar

def magnitude_bar(t, items=(), unit="", title="RELATIVE MAGNITUDE", note=""):
    """Horizontal bars on ONE shared linear scale from zero.

    items: list of (label, value). Values must be in the same unit and must all
    be stated in the narration. Unlike size_ladder this is for quantities that
    are not lengths — percentages, multiples, temperatures, atmospheres — so it
    draws no human figure and makes no claim about physical size.

    The scale is linear and starts at zero, which is the only bar scale that
    does not mislead. If one value dwarfs the others the small bars will be
    stubs; that is the true picture and the reason to pick a different segment.
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=40, speed=0.16, seed=61)

    raw = _pairs(items)[:6]
    rows = [(lab, _num(v)) for lab, v in raw]
    rows = [(lab, v) for lab, v in rows if v is not None]
    n = len(rows)
    if n:
        vmax = max(abs(v) for _, v in rows) or 1.0
        lx = W * 0.30
        rx = W * 0.88
        top, bot = H * 0.22, H * (0.80 if note else 0.86)
        rowh = (bot - top) / n
        bh = min(56, rowh * 0.52)
        flab = font(F_LABEL, int(min(30, max(19, rowh * 0.26))))
        fval = font(F_MONO, int(min(30, max(19, rowh * 0.25))))

        d.line([(lx, top - 12), (lx, bot + 12)], fill=(*MUTED, 90), width=1)
        for i, (lab, v) in enumerate(rows):
            a = _rev(t, i, n, lead=0.45)
            if a <= 0.01:
                continue
            A = int(255 * a)
            cy = top + rowh * (i + 0.5)
            wln = (rx - lx) * (abs(v) / vmax) * a
            top_bar = abs(v) == vmax
            # fill stays CYAN for every bar: an AMBER fill over the dark ground
            # goes muddy brown. The largest is marked by its EDGE, not its body.
            d.rectangle([lx, cy - bh / 2, lx + wln, cy + bh / 2], fill=(*CYAN, 82))
            d.rectangle([lx, cy - bh / 2, lx + wln, cy + bh / 2],
                        outline=(*(AMBER if top_bar else CYAN), 210 if top_bar else 175),
                        width=3 if top_bar else 2)

            fl = _cfit(d, lab, F_LABEL, flab.size, lx - W * 0.05, minsize=15)
            d.text((lx - 22 - d.textlength(lab, font=fl), cy - fl.size * 0.62), lab,
                   font=fl, fill=(*TEXT, A))
            vs = (f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}")
            if unit:
                vs = f"{vs} {unit}"
            vx = lx + wln + 18
            if vx + d.textlength(vs, font=fval) > W - 30:      # never run off canvas
                vx = lx + wln - 18 - d.textlength(vs, font=fval)
            d.text((vx, cy - fval.size * 0.62), vs, font=fval,
                   fill=(*(AMBER if top_bar else MUTED), A))

        if note:
            a = _rev(t, n - 0.2, n, lead=0.45)
            fnn = _cfit(d, note, F_LABEL, 28, W * 0.78, minsize=18)
            _ctext(d, note, fnn, H * 0.88, (*MUTED, int(230 * a)))

    _header(d, title)
    return _finish(img, ov)


# ----------------------------------------------------------- 7. definition card

def definition_card(t, term="", meaning="", boundary="", source=""):
    """A term, its precise meaning, and the edge of that meaning.

    The boundary line is the point of the segment: these scripts repeatedly say
    "this word means X, and people assume it also means Y". Rendering only the
    definition would drop the half that matters.
    """
    img = _bg(INK, DEEP)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=35, speed=0.14, seed=67)

    x0, x1 = W * 0.13, W * 0.87
    tx = x0 + 40
    maxw = x1 - tx

    # measure the whole block first so the card is vertically centred and the
    # amber rule is exactly as tall as the content beside it.
    ft = _cfit(d, str(term), F_DISPLAY, 82, maxw, minsize=40) if term else None
    fm = font(F_LABEL, 38)
    fb = font(F_LABEL, 32)
    mlines = _cwrap(d, str(meaning), fm, maxw)[:4] if meaning else []
    blines = _cwrap(d, str(boundary), fb, maxw)[:3] if boundary else []
    tot = 0.0
    if ft:
        tot += ft.size * 1.30
    if mlines:
        tot += 22 + len(mlines) * fm.size * 1.38
    if blines:
        tot += 40 + 26 + 34 + len(blines) * fb.size * 1.34
    y0 = max(H * 0.16, (H - tot) / 2)

    e = ease(min(t * 2.2, 1))
    d.rectangle([x0, y0 - 18, x0 + 5, y0 - 18 + (tot + 36) * e], fill=(*AMBER, 210))

    y = y0
    if ft:
        a = ease(min(t * 3, 1))
        d.text((tx, y + (1 - a) * 20), str(term), font=ft, fill=(*TEXT, int(255 * a)))
        y += ft.size * 1.30

    if mlines:
        a = ease(max(0.0, min(1.0, (t - 0.18) * 2.6)))
        y += 22
        y = _block(d, mlines, fm, tx, y, fm.size * 1.38, MUTED, int(245 * a), align="left")

    if blines:
        a = ease(max(0.0, min(1.0, (t - 0.44) * 2.4)))
        if a > 0.01:
            y += 40
            d.line([(tx, y), (min(x1, tx + 260), y)], fill=(*CYAN, int(150 * a)), width=1)
            y += 26
            d.text((tx, y), "BOUNDARY", font=font(F_LABEL, 21), fill=(*CYAN, int(200 * a)))
            y += 34
            _block(d, blines, fb, tx, y, fb.size * 1.34, TEXT, int(245 * a), align="left")

    if source:
        d.text((x0, H - 70), f"Source: {source}", font=font(F_LABEL, 22), fill=(*MUTED, 165))
    return _finish(img, ov)


# ---------------------------------------------------------- 8. checklist reveal

def checklist_reveal(t, items=(), title="WHAT WOULD HAVE TO BE TRUE", note=""):
    """Criteria satisfied, failed, or still open — resolved one at a time.

    items: list of (text, state) with state in {"met", "unmet", "open"}, or
           strings prefixed "+" / "-" / "?" respectively.

    Nothing here decides a state on its own; the caller supplies it from what the
    narration says, and an unmarked item stays "open".
    """
    img = _bg(DEEP, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _dust(d, t, n=40, speed=0.15, seed=71)

    norm = []
    for it in (items or ()):
        if isinstance(it, (tuple, list)):
            txt, state = str(it[0]), (str(it[1]).lower() if len(it) > 1 else "open")
        else:
            s = str(it).strip()
            state = {"+": "met", "-": "unmet", "?": "open"}.get(s[:1], "open")
            txt = s[1:].strip() if s[:1] in "+-?" else s
        if txt:
            norm.append((txt, state if state in ("met", "unmet", "open") else "open"))
    norm = norm[:6]
    n = len(norm)

    if n:
        lx = W * 0.14
        top = H * (0.21 if not note else 0.19)
        bot = H * (0.87 if not note else 0.80)
        rowh = (bot - top) / n
        bx = min(38, rowh * 0.36)
        f = font(F_LABEL, int(min(36, max(21, rowh * 0.28))))
        maxw = W * 0.72

        for i, (txt, state) in enumerate(norm):
            a = _rev(t, i, n, lead=0.5)
            if a <= 0.01:
                continue
            A = int(255 * a)
            cy = top + rowh * (i + 0.5)
            col = {"met": CYAN, "unmet": MUTED, "open": AMBER}[state]
            d.rounded_rectangle([lx - bx / 2, cy - bx / 2, lx + bx / 2, cy + bx / 2],
                                radius=5, outline=(*col, A), width=2)
            k = ease(max(0.0, min(1.0, a * 1.6 - 0.4)))     # the mark lands after the box
            if k > 0.02:
                q = bx * 0.30
                if state == "met":
                    d.line([(lx - q, cy), (lx - q * 0.15, cy + q * 0.85),
                            (lx + q, cy - q * 0.8)], fill=(*col, int(255 * k)), width=3)
                elif state == "unmet":
                    d.line([(lx - q, cy - q), (lx + q, cy + q)], fill=(*col, int(255 * k)), width=3)
                    d.line([(lx + q, cy - q), (lx - q, cy + q)], fill=(*col, int(255 * k)), width=3)
                else:
                    d.ellipse([lx - q * 0.45, cy - q * 0.45, lx + q * 0.45, cy + q * 0.45],
                              fill=(*col, int(255 * k)))

            fi = _cfit(d, txt, F_LABEL, f.size, maxw, minsize=17)
            lines = _cwrap(d, txt, fi, maxw)[:2]
            lh = fi.size * 1.28
            ty = cy - len(lines) * lh / 2 - fi.size * 0.10
            _block(d, lines, fi, lx + bx / 2 + 30, ty, lh,
                   TEXT if state != "unmet" else MUTED, A, align="left")

        if note:
            a = _rev(t, n - 0.2, n, lead=0.5)
            fnn = _cfit(d, note, F_LABEL, 28, W * 0.78, minsize=18)
            _ctext(d, note, fnn, H * 0.88, (*MUTED, int(230 * a)))

    _header(d, title)
    return _finish(img, ov)


# ------------------------------------------------------------------- directives
#
# The planner owns directive parsing. This pack cannot edit planner.py, so it
# ships its parsers here and grafts them on. Same discipline as the originals:
# malformed arguments return None so the planner falls back rather than drawing
# something wrong, and no parser ever supplies a value of its own.

def _split(raw):
    return [p.strip() for p in raw.split("|")] if raw else []


def parse_directive_ext2(kind, raw):
    """(segment, args) for the eight new directives, or None if not ours/malformed."""
    parts = _split(raw)
    try:
        if kind == "chain":
            if len(parts) < 3:
                return None                      # title + at least two stages
            stages = [p for p in parts[1:] if p]
            concl = ""
            if stages and stages[-1].startswith(">"):
                concl = stages.pop()[1:].strip()
            if len(stages) < 2:
                return None
            return ("evidence_chain", {"title": parts[0], "stages": stages,
                                       "conclusion": concl})

        if kind == "uncertain":
            if len(parts) < 3 or not parts[0]:
                return None
            plus = parts[2].lstrip("±+").strip()
            minus = None
            if "/" in plus:
                plus, _, minus = [x.strip().lstrip("+-") for x in plus.partition("/")]
            if _num(plus) is None:
                return None
            return ("uncertainty_bar", {"value": parts[0], "unit": parts[1],
                                        "plus": plus, "minus": minus,
                                        "confidence": parts[3] if len(parts) > 3 else "",
                                        "caption": parts[4] if len(parts) > 4 else ""})

        if kind == "sources":
            if len(parts) < 3:
                return None                      # title + at least two sources
            src = [p for p in parts[1:] if "=" in p]
            if len(src) < 2:
                return None
            return ("source_compare", {"title": parts[0], "sources": _pairs(src)[:4]})

        if kind == "steps":
            if len(parts) < 3:
                return None                      # title + at least two steps
            st = [p for p in parts[1:] if p and not p.startswith(">")]
            note = next((p[1:].strip() for p in parts[1:] if p.startswith(">")), "")
            if len(st) < 2:
                return None
            return ("process_steps", {"title": parts[0], "steps": _pairs(st)[:6],
                                      "note": note})

        if kind == "contrast":
            if len(parts) < 3:
                return None
            inc = [p[3:].strip() for p in parts[1:] if p.lower().startswith("is=")]
            exc = [p[4:].strip() for p in parts[1:] if p.lower().startswith("not=")]
            if not inc or not exc:
                return None
            return ("contrast_pair", {"term": parts[0], "includes": inc[:5],
                                      "excludes": exc[:5]})

        if kind == "magnitude":
            if len(parts) < 4:
                return None                      # title + unit + two values
            it = _pairs([p for p in parts[2:] if "=" in p])
            it = [(lab, v) for lab, v in it if _num(v) is not None]
            if len(it) < 2:
                return None
            return ("magnitude_bar", {"title": parts[0], "unit": parts[1], "items": it[:6]})

        if kind == "define":
            if len(parts) < 2 or not parts[0] or not parts[1]:
                return None
            return ("definition_card", {"term": parts[0], "meaning": parts[1],
                                        "boundary": parts[2] if len(parts) > 2 else "",
                                        "source": parts[3] if len(parts) > 3 else ""})

        if kind == "checklist":
            if len(parts) < 3:
                return None
            it = [p for p in parts[1:] if p and not p.startswith(">")]
            note = next((p[1:].strip() for p in parts[1:] if p.startswith(">")), "")
            if len(it) < 2:
                return None
            return ("checklist_reveal", {"title": parts[0], "items": it[:6], "note": note})
    except Exception:
        return None
    return None


_installed = False


def install(planner=None):
    """Teach the planner the new directives. Idempotent; safe to call anywhere."""
    global _installed
    if planner is None:
        try:
            import planner as planner  # noqa: PLW0127
        except ImportError:
            return False
    if getattr(planner, "_ext2_installed", False):
        _installed = True
        return True

    base = planner.parse_directive
    rx = planner.DIRECTIVE

    def parse_directive(line):
        got = base(line)
        if got is not None:
            return got
        m = rx.match(line.strip())
        if not m:
            return None
        return parse_directive_ext2(m.group(1).lower(), m.group(2))

    parse_directive.__doc__ = base.__doc__
    planner.parse_directive = parse_directive
    planner._ext2_installed = True

    # keep any informational-segment set the planner exposes in sync
    for attr in ("INFO", "INFORMATIONAL"):
        cur = getattr(planner, attr, None)
        if isinstance(cur, (set, frozenset)):
            setattr(planner, attr, set(cur) | set(SEGMENTS))
    _installed = True
    return True


# Auto-install if the planner is already loaded, so a single `import segments_ext2`
# anywhere in the pipeline is enough.
try:
    import sys as _sys
    if "planner" in _sys.modules:
        install(_sys.modules["planner"])
    else:
        install()
except Exception:                                # never break a render on wiring
    pass


# ---------------------------------------------------------------------- handoff
#
# planner.py and assemble.py are owned elsewhere right now. When they are free,
# two one-line edits make this pack fully automatic:
#
#   planner.py   (after the imports)   :  import segments_ext2 as _x2; _x2.install(sys.modules[__name__])
#   assemble.py  (beside segments_ext) :  import segments_ext2 as SX2   + a lookup in seg_fn
#
# Until then callers add `import segments_ext2` before planning, which is what
# tests/ and the measurement harness do.
