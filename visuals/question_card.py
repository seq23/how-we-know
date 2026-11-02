"""ONE QUESTION PER VIDEO: the picture every video carries (owner, 2 Nov 2026).

    python visuals/question_card.py <slug> "<question>" <out.jpg> [--tall]

The owner's rule, approved from the mock-up of 2 Nov 2026: every video gets one
plain question. That question is the title, it sits on a PHOTO of the subject
for the thumbnail, and it is the first second of every Short. This module draws
that one picture, in two shapes:

  * WIDE (1280x720): the long-form thumbnail (visuals/thumb_contract.py builds
    its A/B/C variants from it - the variants change the PHOTO or its crop,
    never the question or the layout);
  * TALL (1080x1920): a Short's opening second (visuals/shorts.py), the
    question sitting above the caption box so the caption she likes is
    still read underneath it.

THE LAYOUT, every element of it fixed here and nowhere else:
  photo of the subject, cropped to the frame - no grade, no template, no
  graphic; a dark gradient over the bottom (transparent to 35% of the height,
  then to 78% black at the bottom edge); the question in large bold white type
  in that gradient (on the tall card the dark is full strength from just
  above the question down, so the captions stay readable); a small "HOW WE KNOW" mark at the top; the photo's required
  credit, small (attribution is never dropped - CLAUDE.md).

THE PHOTO is public domain or CC0, or - owner ruling of 2 Nov 2026, the 13 Oct
food-footage widening applied to these stills in every domain - a Pixabay,
Pexels or Mixkit photo under its free licence (commercial reuse, no attribution
required), its licence wording stored under channel/imagery/licences/ and
checked by research/food_footage.record_problems, and still credited.
Anything else, CC-BY included, is refused (licence_problems). It comes from
the manifests this repo already rights-checks (thumb_contract.candidates: channel/imagery/rights.json,
materials.json, food.json - re-hashed against the recorded sha256 before a
pixel is used). AI-generated stills (food_ai.json) are NOT photos and are never
used here. No photo = NoSubjectPhoto, raised by name; the callers turn it into
a named stop and nothing falls back to the old text card.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import numpy as np                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont                 # noqa: E402

LAYOUT = "question-photo-v1"
MARK = "HOW WE KNOW"
WIDE = (1280, 720)
TALL = (1080, 1920)
GRADIENT_FROM = 0.35          # share of the height where the dark begins
GRADIENT_ALPHA = 0.78         # black at the bottom edge
# A Short's caption box (visuals/shorts.py CAP_BOX_Y): the question sits above it.
TALL_QUESTION_BOTTOM = 1040
TALL_GRADIENT = (0.22, 0.52)  # (begins, full strength) as shares of the height
OPENER_SECONDS = 1.0          # owner: "for its first second"
# Manifests whose images are photographs cleared for these stills. food_ai.json is AI.
PHOTO_MANIFESTS = ("rights.json", "materials.json", "food.json",
                   "subject_photos.json")   # research/subject_photo.py, same gate

_BOLD = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
_MARK = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
_CREDIT = ("/System/Library/Fonts/Supplemental/Arial.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")


class NoSubjectPhoto(Exception):
    """No public-domain / CC0 photograph of this video's subject exists in the
    rights-checked manifests. A NAMED stop, never a fallback."""


def _font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise FileNotFoundError(f"no bold font among {paths}")


# ------------------------------------------------------------------ photos
FREE_LIBRARIES = ("pixabay", "pexels", "mixkit")
_PD = re.compile(r"public domain|\bpd\b|cc0|pd-usgov|pdm", re.I)


def licence_problems(rec: dict) -> list[str]:
    """The ONE licence gate for a thumbnail / Short-opening still: PD or CC0,
    or a free-library photo passing research/food_footage.record_problems
    (its adapter's licence, the licence wording recorded and committed).
    Anything else - CC-BY included - is refused."""
    src = rec.get("source")
    if src in FREE_LIBRARIES:
        sys.path.insert(0, os.path.join(ROOT, "research"))
        import food_footage as F                           # noqa: PLC0415
        p = F.record_problems(rec)
        lt = rec.get("licence_text")
        if not lt or not os.path.exists(os.path.join(ROOT, "channel", "imagery", lt)):
            p.append(f"{rec.get('subject')}: licence wording {lt!r} not committed")
        return p
    lic = rec.get("licence") or ""
    if not _PD.search(lic) or re.search(r"\bby\b|by-sa|by-nc", lic, re.I):
        return [f"{rec.get('subject')}: licence {lic!r} is neither PD/CC0 nor a "
                f"free-library licence"]
    return []


def manifest_record(local_file: str) -> dict | None:
    """The subject_photos.json record for a file (the finder's own manifest)."""
    import json                                            # noqa: PLC0415
    import thumb_contract as TC                            # noqa: PLC0415
    try:
        man = json.load(open(os.path.join(TC.IMAGERY, "subject_photos.json")))
    except (OSError, ValueError):
        return None
    return next((r for r in man.get("index") or [] if r.get("local_file") == local_file), None)


def photos(slug: str, script_path: str | None = None) -> list[dict]:
    """Cleared photographs of THIS video's subject, best first (never AI)."""
    import thumb_contract as TC                            # noqa: PLC0415
    out = []
    for c in TC.candidates(slug, script_path):
        if c.get("manifest") not in PHOTO_MANIFESTS:
            continue
        if c["manifest"] == "subject_photos.json":
            rec = manifest_record(c["local_file"])
            if not rec or licence_problems(rec):
                continue
        out.append(c)
    return out


def photo_for(slug: str, script_path: str | None = None) -> dict:
    """The photo a video's question card uses: the long-form thumbnail's
    variant A photo when that set is a question-photo set (so the Short opens
    on the same picture as the thumbnail), else the best candidate."""
    import json                                            # noqa: PLC0415
    import thumb_contract as TC                            # noqa: PLC0415
    try:
        rec = json.load(open(os.path.join(TC.VARIANTS_DIR, slug, "contract.json")))
    except (OSError, ValueError):
        rec = {}
    a = (rec.get("variants") or {}).get("A") or {}
    if rec.get("layout") == LAYOUT and a.get("manifest") in PHOTO_MANIFESTS:
        path = os.path.join(TC.IMAGERY, a["source"])
        if os.path.exists(path) and TC._sha(path) == a.get("sha256"):  # noqa: SLF001
            return {"path": path, "local_file": a["source"], "sha256": a["sha256"],
                    "credit": a["credit"], "crop": a.get("crop"),
                    "subject": a.get("subject"), "manifest": a["manifest"]}
    got = photos(slug, script_path)
    if not got:
        raise NoSubjectPhoto(
            f"{slug}: no public-domain or CC0 photograph of this video's subject "
            f"in channel/imagery (rights.json, materials.json, food.json; AI "
            f"stills are not photos). Harvest one (research/imagery_*.py) - the "
            f"video is held until then, never given the old text card")
    return got[0]


def open_photo(c: dict) -> Image.Image:
    im = Image.open(c["path"]).convert("RGB")
    if c.get("crop"):
        x0, y0, x1, y1 = c["crop"]
        w, h = im.size
        im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    return im


def tall_box(src: Image.Image) -> tuple[int, int, int, int]:
    """A 9:16 window centred on the photo's subject (thumbs.subject_box)."""
    import thumbs                                          # noqa: PLC0415
    W, H = src.size
    bx0, by0, bx1, by1 = thumbs.subject_box(src, keep=0.80)
    ch = H
    cw = ch * 9 / 16
    if cw > W:
        cw, ch = W, W * 16 / 9
    sx, sy = (bx0 + bx1) / 2 * W, (by0 + by1) / 2 * H
    x0 = min(max(0.0, sx - cw / 2), W - cw)
    y0 = min(max(0.0, sy - ch / 2), H - ch)
    return (int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch)))


# ------------------------------------------------------------------ drawing
def base(src: Image.Image, box, size) -> Image.Image:
    """The photo crop with the dark bottom gradient: the picture before type.
    No grade: the photograph's own colour (owner: no graphics/templates)."""
    W, H = size
    im = src.crop(tuple(box)).resize((W, H), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    y = np.arange(H, dtype=np.float32) / max(H - 1, 1)
    # Tall: the question sits ABOVE the caption box (row 1040 of 1920), so the
    # dark reaches full strength there and stays down through the captions.
    lo, hi = (GRADIENT_FROM, 1.0) if H <= W else TALL_GRADIENT
    k = np.clip((y - lo) / (hi - lo), 0, 1) * GRADIENT_ALPHA
    a = a * (1 - k)[:, None, None]
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGB")


def _wrap(d, text: str, font, maxw: float) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if cur and d.textlength(t, font=font) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def draw(base_im: Image.Image, question: str, credit: str,
         tall: bool = False) -> tuple[Image.Image, dict]:
    """Type on the base: (image, {"text", "mark", "credit"} bboxes)."""
    im = base_im.copy()
    W, H = im.size
    d = ImageDraw.Draw(im)
    margin = int(W * 0.06)
    maxw = W - 2 * margin
    size = int(H * (0.105 if not tall else 0.052))
    floor = int(H * (0.05 if not tall else 0.03))
    while True:
        f = _font(_BOLD, size)
        lines = _wrap(d, question, f, maxw)
        lead = int(size * 1.08)
        if len(lines) <= 3 and all(d.textlength(ln, font=f) <= maxw for ln in lines):
            break
        if size <= floor:
            raise ValueError(f"question {question!r} does not fit the card in "
                             f"three lines")
        size -= 4
    bottom = TALL_QUESTION_BOTTOM if tall else int(H * 0.91)
    y = bottom - lead * len(lines)
    stroke = max(1, size // 30)
    tb = [W, H, 0, 0]
    for ln in lines:
        w = d.textlength(ln, font=f)
        x = (W - w) / 2 if tall else margin
        d.text((x, y), ln, font=f, fill=(255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0))
        bb = d.textbbox((x, y), ln, font=f, stroke_width=stroke)
        tb = [min(tb[0], bb[0]), min(tb[1], bb[1]), max(tb[2], bb[2]), max(tb[3], bb[3])]
        y += lead
    mf = _font(_MARK, int(H * (0.024 if not tall else 0.016)))
    mark = " ".join(MARK)                  # letter-spaced, as in the mock-up
    mw = d.textlength(mark, font=mf)
    mx = (W - mw) / 2 if tall else margin
    my = int(H * (0.06 if not tall else 0.05))
    d.text((mx, my), mark, font=mf, fill=(255, 255, 255),
           stroke_width=1, stroke_fill=(0, 0, 0))
    mb = d.textbbox((mx, my), mark, font=mf, stroke_width=1)
    cf = _font(_CREDIT, max(14, int(H * (0.024 if not tall else 0.012))))
    cw = d.textlength(credit, font=cf)
    if cw > W - 2 * 12:
        credit = credit[: max(8, int(len(credit) * (W - 24) / cw)) - 1] + "…"
        cw = d.textlength(credit, font=cf)
    cx = W - 12 - cw
    cy = 10 if not tall else my + (mb[3] - mb[1]) + 18
    if tall:
        cx = (W - cw) / 2
    d.text((cx, cy), credit, font=cf, fill=(235, 235, 235),
           stroke_width=2, stroke_fill=(0, 0, 0))
    cb = d.textbbox((cx, cy), credit, font=cf, stroke_width=2)
    return im, {"text": [int(v) for v in tb], "mark": [int(v) for v in mb],
                "credit": [int(v) for v in cb]}


def question_problems(question: str) -> list[str]:
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import titles                                          # noqa: PLC0415
    return titles.one_question_problems(question)


def tall_card(slug: str, question: str, out_png: str,
              script_path: str | None = None) -> dict:
    """A Short's opening picture, written as a 1080x1920 PNG. Returns the
    receipt fields (photo, credit, question). Raises NoSubjectPhoto."""
    bad = question_problems(question)
    if bad:
        raise ValueError(f"{slug}: opener question {question!r}: {bad[0]}")
    c = photo_for(slug, script_path)
    src = open_photo(c)
    box = tall_box(src)
    im, boxes = draw(base(src, box, TALL), question, c["credit"], tall=True)
    im.save(out_png)
    return {"kind": LAYOUT, "question": question, "seconds": OPENER_SECONDS,
            "source": c["local_file"], "manifest": c["manifest"],
            "sha256": c["sha256"], "credit": c["credit"], "box": list(box),
            "bboxes": boxes}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__.split("\n\n", 1)[0])
        return 2
    slug, q, out = args
    try:
        if "--tall" in argv:
            r = tall_card(slug, q, out)
        else:
            c = photo_for(slug)
            src = open_photo(c)
            import thumb_contract as TC                    # noqa: PLC0415
            box = TC.crop_box(src, 0.85, (0.5, 0.42))
            im, _ = draw(base(src, box, WIDE), q, c["credit"])
            im.save(out, "JPEG", quality=92)
            r = {"source": c["local_file"]}
    except NoSubjectPhoto as e:
        print(f"NAMED STOP: NO_SUBJECT_PHOTO {e}")
        return 3
    print(f"OK {out} ({r['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
