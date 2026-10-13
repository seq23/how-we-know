"""The TRIPTYCH thumbnail layout: one headline, a subject line, three panels.

Owner design, 13 Oct 2026, for multi-subject "What's Inside?" series videos
("Bread, Steak, Chocolate: What's Inside?"): a big headline across the top or
centre, a smaller line naming the three foods beneath it, and three panels,
one glossy picture per food, under the channel's one grade. The three
variants differ in COMPOSITION (vertical panels, horizontal strips, a diagonal
split; headline placement; which food is largest), never in the words.

THE REFERENCE EXAMPLE (owner's pick, 13 Oct 2026 - "thumbnail F" of the food
round-2 sample, variant C of channel/thumbnails/variants/why-bread-rises-steak-
browns-chocolate-snaps): REFERENCE below - a DIAGONAL split, the FIRST subject
(bread) largest, the headline CENTRED over the panels, the subject line beneath.
The vertical-panels and horizontal-strips compositions (D, E) remain valid.

THE WIDENED CONTRACT - visuals/thumb_contract.verify() hands any set whose
contract.json says `"layout": "triptych"` to verify() here, which re-checks
the files on disk (validator V48):
  * ALLOWED ONLY for a series title "<Noun>, <Noun>, <Noun>: What's Inside?";
  * HEADLINE <= 2 words, its drawn width >= HEADLINE_MIN_WIDTH of the frame
    (the <= 3-word rule applies to the headline);
  * SUBTITLE: up to 3 words, and they must be exactly the title's subject
    nouns - nothing else (it is exempt from the word cap for that reason);
  * PANELS: three, each covering >= PANEL_MIN_SHARE of the frame;
  * LEGIBLE AT FEED SIZE: downscaled to 320 px wide, inside the recorded type
    box, the headline is >= 12 px tall with fill/stroke luminance contrast
    >= 4.5:1, the subtitle >= 6 px and >= 3:1 (measured on published pixels, so
    it holds on any host's fonts);
  * GRADE + SOURCES: each panel is the cleared bytes of its source, cover-
    cropped and graded with thumb_contract.grade; the published pixels outside
    the type boxes equal a fresh composition within GRADE_TOLERANCE;
  * DISTINCT: the three pictures (before type) differ pairwise by
    thumb_distinct.MIN_PHASH_DISTANCE.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import thumb_contract as T                                      # noqa: E402
import thumb_distinct as TD                                     # noqa: E402

SERIES_TITLE = re.compile(r"^([A-Z][a-z]+), ([A-Z][a-z]+), ([A-Z][a-z]+): What's Inside\?$")
HEADLINE_MAX_WORDS = 2
HEADLINE_MIN_WIDTH = 0.40
SUBTITLE_MAX_WORDS = 3
PANEL_MIN_SHARE = 0.25
FEED_W = 320
HEAD_MIN_PX, HEAD_MIN_CONTRAST = 12, 4.5
SUB_MIN_PX, SUB_MIN_CONTRAST = 6, 3.0
LAYOUTS = ("vertical", "horizontal", "diagonal")
REFERENCE = {"layout": "diagonal", "largest": 0, "place": "center"}   # the owner's pick (F)
REFERENCE_SET = ("why-bread-rises-steak-browns-chocolate-snaps", "C")
TW, TH = T.TW, T.TH


def _font(size: int):
    return T._font(T._FONT_CANDIDATES, size)                    # noqa: SLF001


def panel_masks(layout: str, largest: int) -> list[Image.Image]:
    """Three L masks (255 inside) tiling the frame; panel `largest` is the biggest."""
    big, small = 0.42, 0.29
    shares = [small, small, small]
    shares[largest] = big
    masks = []
    if layout in ("vertical", "horizontal"):
        span = TW if layout == "vertical" else TH
        edges = np.cumsum([0] + shares) * span
        for i in range(3):
            m = Image.new("L", (TW, TH), 0)
            a, b = int(round(edges[i])), int(round(edges[i + 1]))
            box = (a, 0, b, TH) if layout == "vertical" else (0, a, TW, b)
            ImageDraw.Draw(m).rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=255)
            masks.append(m)
        return masks
    # diagonal: two slanted cuts; the slant shifts the top and bottom edges
    edges = np.cumsum([0] + shares) * TW
    slant = 0.12 * TW
    for i in range(3):
        m = Image.new("L", (TW, TH), 0)
        x0, x1 = edges[i], edges[i + 1]
        top0 = x0 + (slant if i > 0 else 0)
        top1 = x1 + (slant if i < 2 else 0)
        bot0 = x0 - (slant if i > 0 else 0)
        bot1 = x1 - (slant if i < 2 else 0)
        ImageDraw.Draw(m).polygon([(top0, 0), (top1, 0), (bot1, TH), (bot0, TH)], fill=255)
        masks.append(m)
    return masks


def _cover(im: Image.Image, box) -> Image.Image:
    x0, y0, x1, y1 = box
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 0.999), int(im.height * s + 0.999)), Image.LANCZOS)
    cx, cy = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((cx, cy, cx + w, cy + h))


def picture(sources: list[str], layout: str, largest: int) -> tuple[Image.Image, list[float]]:
    """The graded three-panel picture, before any type, and each panel's share."""
    out = Image.new("RGB", (TW, TH), (10, 8, 8))
    shares = []
    for path, m in zip(sources, panel_masks(layout, largest)):
        box = m.getbbox()
        src = Image.open(path).convert("RGB")
        tile = T.grade(_cover(src, box))
        layer = Image.new("RGB", (TW, TH))
        layer.paste(tile, box[:2])
        out = Image.composite(layer, out, m)
        shares.append(float((np.asarray(m) > 127).mean()))
    # warm hairlines between the panels
    edge = Image.new("L", (TW, TH), 0)
    for m in panel_masks(layout, largest):
        edge = Image.fromarray(np.maximum(np.asarray(edge), np.asarray(
            m.filter(ImageFilter.FIND_EDGES))))
    edge = edge.filter(ImageFilter.MaxFilter(5))
    out = Image.composite(Image.new("RGB", (TW, TH), (232, 196, 140)), out, edge)
    return out, shares


def _rows(place: str) -> tuple[int, int]:
    hy = 34 if place == "top" else (TH - 176 - 80) // 2 - 10
    return hy, hy + 186


def band_only(pic: Image.Image, place: str) -> Image.Image:
    """The picture with the soft dark band the type sits on (no type)."""
    hy, sy = _rows(place)
    band = Image.new("L", (TW, TH), 0)
    ImageDraw.Draw(band).rectangle((0, hy + 6, TW, sy + 78), fill=125)
    band = band.filter(ImageFilter.GaussianBlur(22))
    return Image.composite(Image.new("RGB", (TW, TH), (6, 4, 4)), pic, band)


def draw_type(pic: Image.Image, headline: str, subtitle: str, place: str, credit: str):
    """Headline + subtitle (+ credit) over a soft dark band. Returns image and boxes."""
    hf, sf, cf = _font(176), _font(60), T._font(T._CREDIT_FONTS, 18)   # noqa: SLF001
    hy, sy = _rows(place)
    im = band_only(pic, place)
    d = ImageDraw.Draw(im)
    hw = d.textlength(headline, font=hf)
    sw = d.textlength(subtitle, font=sf)
    hx, sx = (TW - hw) / 2, (TW - sw) / 2
    d.text((hx, hy), headline, font=hf, fill=(255, 255, 255), stroke_width=10, stroke_fill=(0, 0, 0))
    d.text((sx, sy), subtitle, font=sf, fill=(255, 236, 200), stroke_width=5, stroke_fill=(0, 0, 0))
    hb = list(d.textbbox((hx, hy), headline, font=hf, stroke_width=10))
    sb = list(d.textbbox((sx, sy), subtitle, font=sf, stroke_width=5))
    cb0 = d.textbbox((0, 0), credit, font=cf)
    cx, cy = TW - 16 - (cb0[2] - cb0[0]), TH - 34
    d.text((cx, cy), credit, font=cf, fill=(235, 235, 235), stroke_width=2, stroke_fill=(0, 0, 0))
    cb = list(d.textbbox((cx, cy), credit, font=cf, stroke_width=2))
    return im, [int(v) for v in hb], [int(v) for v in sb], [int(v) for v in cb]


def _lum(a: np.ndarray) -> np.ndarray:
    c = a / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def legibility(img: Image.Image, bbox) -> tuple[float, float]:
    """At FEED_W wide, measured on the PUBLISHED pixels inside the recorded type
    box (font-independent): (letter height px, luminance contrast between the
    brightest tenth - the letter fill - and the darkest tenth - its stroke)."""
    k = FEED_W / TW
    sz = (FEED_W, int(TH * k))
    small = np.asarray(img.convert("RGB").resize(sz, Image.LANCZOS)).astype(np.float64)
    x0, y0, x1, y1 = (int(round(v * k)) for v in bbox)
    roi = small[max(0, y0):y1 + 1, max(0, x0):x1 + 1].reshape(-1, 3)
    if len(roi) < 20:
        return 0.0, 0.0
    lum = np.sort(_lum(roi))
    n = max(1, len(lum) // 10)
    lf, lr = float(lum[-n:].mean()), float(lum[:n].mean())
    return float(y1 - y0), (lf + 0.05) / (lr + 0.05)


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(slug: str, title: str, headline: str, panels: list[dict], plans: list[dict],
          out_root: str | None = None) -> dict:
    """panels: [{subject, path (under channel/imagery), sha256, credit, ai}] in title order.
    plans: three {layout, largest, place}. Writes A/B/C + contract.json, or refuses."""
    final_dir = os.path.join(out_root or T.VARIANTS_DIR, slug)
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix=f".{slug}-", dir=os.path.dirname(final_dir))
    nouns = list(SERIES_TITLE.match(title).groups()) if SERIES_TITLE.match(title) else []
    subtitle = " · ".join(nouns)
    credit = ("AI-GENERATED IMAGE · " if any(p["ai"] for p in panels) else "") + \
        " · ".join(sorted({p["credit"] for p in panels if not p["ai"]}))
    rec = {"slug": slug, "title": title, "layout": "triptych", "grade": T.GRADE["id"],
           "chosen": T.CHOSEN, "headline": headline, "subtitle": subtitle, "credit": credit,
           "panels": [{k: p[k] for k in ("subject", "source", "sha256", "credit", "ai")} for p in panels],
           "variants": {}}
    for name, plan in zip(T.VARIANT_NAMES, plans):
        pic, shares = picture([os.path.join(T.IMAGERY, p["source"]) for p in panels],
                              plan["layout"], plan["largest"])
        im, hb, sb, cb = draw_type(pic, headline, subtitle, plan["place"], credit)
        im.save(os.path.join(out_dir, f"{name}.jpg"), "JPEG", quality=92, optimize=True,
                progressive=True)
        rec["variants"][name] = {"file": f"{name}.jpg", **plan, "panel_shares": shares,
                                 "text": headline, "headline_bbox": hb, "subtitle_bbox": sb,
                                 "credit_bbox": cb}
    with open(os.path.join(out_dir, "contract.json"), "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    probs = verify_dir(out_dir, rec)
    if probs:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise T.ContractRefused(f"{slug}: triptych refused: " + "; ".join(probs))
    if os.path.isdir(final_dir):
        shutil.rmtree(final_dir)
    os.replace(out_dir, final_dir)
    return {"dir": final_dir, "contract": rec}


def verify_dir(d: str, rec: dict) -> list[str]:
    slug = rec.get("slug", os.path.basename(d))
    p: list[str] = []
    m = SERIES_TITLE.match(rec.get("title") or "")
    if not m:
        return [f"{slug}: the triptych layout is only for a '<Noun>, <Noun>, <Noun>: What's "
                f"Inside?' series title, not {rec.get('title')!r}"]
    if rec.get("grade") != T.GRADE["id"] or rec.get("chosen") != T.CHOSEN:
        p.append(f"{slug}: grade/chooser are not the channel's")
    head = rec.get("headline") or ""
    if not head or len(head.split()) > HEADLINE_MAX_WORDS:
        p.append(f"{slug}: headline {head!r} is over {HEADLINE_MAX_WORDS} words")
    sub = [w for w in re.split(r"\s*·\s*|\s+", rec.get("subtitle") or "") if w]
    if len(sub) > SUBTITLE_MAX_WORDS or [w.lower() for w in sub] != [w.lower() for w in m.groups()]:
        p.append(f"{slug}: subtitle {rec.get('subtitle')!r} must be the title's subject nouns only")
    panels = rec.get("panels") or []
    if len(panels) != 3:
        p.append(f"{slug}: {len(panels)} panels, not 3")
        return p
    for pn in panels:
        path = os.path.join(T.IMAGERY, pn["source"])
        if not os.path.exists(path) or _sha(path) != pn["sha256"]:
            p.append(f"{slug}: panel {pn['subject']}: source missing or not the cleared bytes")
            return p
    if any(pn["ai"] for pn in panels) and "AI-GENERATED IMAGE" not in (rec.get("credit") or ""):
        p.append(f"{slug}: an AI panel without the AI-GENERATED IMAGE credit")
    pics = {}
    for name in T.VARIANT_NAMES:
        v = (rec.get("variants") or {}).get(name)
        f = os.path.join(d, f"{name}.jpg")
        if not v or not os.path.exists(f):
            p.append(f"{slug}: variant {name} missing")
            continue
        if v["text"] != head:
            p.append(f"{slug}/{name}: variants differ in words, not composition")
        pic, shares = picture([os.path.join(T.IMAGERY, pn["source"]) for pn in panels],
                              v["layout"], v["largest"])
        pics[name] = pic
        if min(shares) < PANEL_MIN_SHARE:
            p.append(f"{slug}/{name}: a panel covers {min(shares):.0%} of the frame, under "
                     f"{PANEL_MIN_SHARE:.0%}")
        with Image.open(f) as im:
            if im.size != (TW, TH) or im.format != "JPEG":
                p.append(f"{slug}/{name}: not a {TW}x{TH} JPEG")
                continue
            got = im.convert("RGB")
        hb, sb, cb = v["headline_bbox"], v["subtitle_bbox"], v["credit_bbox"]
        # the picture under the type, compared outside the recorded type boxes
        # (fonts differ between hosts; the panels, grade and band do not)
        want = band_only(pic, v["place"])
        mask = np.ones((TH, TW), bool)
        for x0, y0, x1, y1 in (hb, sb, cb):
            mask[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6] = False
        diff = float(np.abs(np.asarray(got).astype(np.float32) -
                            np.asarray(want).astype(np.float32))[mask].mean())
        if diff > T.GRADE_TOLERANCE:
            p.append(f"{slug}/{name}: published pixels differ from a fresh graded composition "
                     f"by {diff:.1f} per channel")
        if (hb[2] - hb[0]) < HEADLINE_MIN_WIDTH * TW:
            p.append(f"{slug}/{name}: headline spans {(hb[2] - hb[0]) / TW:.0%} of the width, "
                     f"under {HEADLINE_MIN_WIDTH:.0%}")
        h_px, h_c = legibility(got, hb)
        s_px, s_c = legibility(got, sb)
        if h_px < HEAD_MIN_PX or h_c < HEAD_MIN_CONTRAST:
            p.append(f"{slug}/{name}: headline at {FEED_W} px is {h_px:.0f} px tall, contrast "
                     f"{h_c:.1f}:1 (needs {HEAD_MIN_PX} px, {HEAD_MIN_CONTRAST}:1)")
        if s_px < SUB_MIN_PX or s_c < SUB_MIN_CONTRAST:
            p.append(f"{slug}/{name}: subtitle at {FEED_W} px is {s_px:.0f} px tall, contrast "
                     f"{s_c:.1f}:1 (needs {SUB_MIN_PX} px, {SUB_MIN_CONTRAST}:1)")
    if len(pics) == 3:
        p += [f"{slug}: {x}" for x in TD.check(pics, {"A": "a", "B": "b", "C": "c"})]
        lay = {(rec["variants"][n]["layout"], rec["variants"][n]["largest"],
                rec["variants"][n]["place"]) for n in T.VARIANT_NAMES}
        if len(lay) < 3:
            p.append(f"{slug}: two variants share one composition")
    return p


def verify(slug: str, root: str | None = None) -> list[str]:
    d = os.path.join(root or T.VARIANTS_DIR, slug)
    return verify_dir(d, json.load(open(os.path.join(d, "contract.json"))))
