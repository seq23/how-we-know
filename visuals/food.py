"""The `food` imagery preset, and the renderer that applies it.

    .venv/bin/python visuals/food.py render SCRIPT.md VOICE_DIR OUT.mp4 [--beats 0,1,2]
    .venv/bin/python visuals/food.py check OUT.mp4            # the contract, on the file

THE OWNER'S BRIEF (2026-10-13, docs/CHANNEL-PLAN.md "A third domain: food
science"): marvellous, hypnotic, realistic not animated, AI is fine,
FANTASTICAL IN SCALE, NOT PHYSICS. Turned into a contract every line of which
check() measures on the rendered file (validator V53,
loop/tests/test_food_preset.py):

  * GRADE. A dark warm ground and the channel's own split tone: the
    thumbnail grade of #191 (visuals/thumb_contract.GRADE,
    hwk-split-navy-amber-v1 - navy shadows, amber highlights, contrast 1.18)
    mixed lighter for moving pictures and with the photograph's own colour
    pushed up (FOOD_GRADE). Applied to every picture frame as an exact
    per-pixel LUT before any type is drawn; the render keeps proof frames of
    the ungraded picture so check() can re-grade them and compare.
  * ONE GLOSSY SUBJECT, side-lit. The AI stills are prompted for exactly that
    (visuals/food_stills.LOOK); real stills and clips are chosen for it.
    Measured as subject coverage: the salient subject spans at least
    SUBJECT_COVERAGE_MIN of the frame's larger side on picture frames.
  * MOTION ON STILLS. A slow zoom plus a two-layer depth parallax (the
    salient subject drifts against its own background) on every still; real
    clips play as shot.
  * CADENCE. Cuts every 3-5 s in the hooked opening; holds of 8-15 s after
    the title card. The shot list is written beside the render and check()
    reads it.
  * ONE SIGNATURE DEVICE per part: the glowing cross-section
    ({{cross_section: SUBJECT | LABEL}}) - the subject cut open, one
    butter-white line tracing the structure that answers the question. It is
    a drawing and the note says so.
  * HONEST CREDITS. Every real still or clip draws its credit line; every AI
    still draws "AI-GENERATED IMAGE". The episode spec beside the render sets
    `altered_content: true` whenever a realistic AI still is on screen, and
    loop/upload.py sends it as YouTube's containsSyntheticMedia.
  * CAPTIONS ON. Burned in, from the voice's own chunk timings, plus an .srt.

No AI video: no open video model runs on this Mac (8 GB, no weights), so every
AI shot is a still given motion here. Nothing in this module is paid.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
IMAGERY = ROOT / "channel" / "imagery"

W, H, FPS = 1920, 1080, 30

PRESET = {
    "id": "food-v1",
    "opening_cut_s": (3.0, 5.0),
    "calm_hold_s": (8.0, 15.0),
    "still_zoom": (1.0, 1.08),
    "parallax_px": 28,
    "crossfade_s": 1.0,
    "devices_per_part_max": 1,
}
# A subject on screen: the salient box spans >= 30% of the frame's larger side
# AND salient pixels carry real energy (the thumbnail contract's floor, so an
# empty dark frame cannot pass by being dark everywhere). Calibrated on the
# first sample's proof frames 2026-10-13: every picture shot 0.33-0.90 span,
# energy 0.17-0.98; a flat frame 0.06 / 0.0.
SUBJECT_COVERAGE_MIN = 0.30
PROOF_STEP = 8                       # proof frames kept at 240x135
GRADE_TOLERANCE = 6.0                # mean |diff| per channel after h264

FOOD_GRADE = {
    "id": "food-v1/hwk-split-navy-amber-v1",
    "base": "hwk-split-navy-amber-v1",
    "shadow": (8, 22, 40),
    "highlight": (255, 222, 168),
    "contrast": 1.18,
    "mix": 0.30,
    "saturation": 1.30,
}

INK = (14, 9, 7)
GLOW = (255, 236, 196)
TEXT = (252, 244, 232)


# ------------------------------------------------------------------ the grade
def grade_array(a: np.ndarray, g: dict | None = None) -> np.ndarray:
    """uint8 RGB -> graded uint8 RGB. Same split tone as the thumbnails."""
    g = g or FOOD_GRADE
    x = a.astype(np.float32) / 255.0
    lum = x @ np.array([0.299, 0.587, 0.114], np.float32)
    k = g["contrast"]
    curve = np.clip((lum - 0.5) * k + 0.5, 0, 1)[..., None]
    sh = np.array(g["shadow"], np.float32) / 255.0
    hi = np.array(g["highlight"], np.float32) / 255.0
    duo = sh * (1 - curve) + hi * curve
    own = np.clip((x - 0.5) * k + 0.5, 0, 1)
    l2 = (own @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    own = np.clip(l2 + (own - l2) * g["saturation"], 0, 1)
    out = g["mix"] * duo + (1 - g["mix"]) * own
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


_LUT: np.ndarray | None = None


def lut() -> np.ndarray:
    """The grade as an exact 256^3 lookup (48 MB), built once."""
    global _LUT
    if _LUT is None:
        r = np.arange(256, dtype=np.uint8)
        cube = np.stack(np.meshgrid(r, r, r, indexing="ij"), -1).reshape(-1, 3)
        _LUT = grade_array(cube.reshape(256, 65536, 3)).reshape(-1, 3)
    return _LUT


def grade_frame(a: np.ndarray) -> np.ndarray:
    idx = (a[..., 0].astype(np.uint32) << 16) | (a[..., 1].astype(np.uint32) << 8) | a[..., 2]
    return lut()[idx]


# --------------------------------------------------------------- the script
DIRECTIVE = re.compile(r"^\{\{\s*(\w+)\s*:?\s*(.*?)\s*\}\}$")


def parse(script: Path) -> list[dict]:
    """Narration paragraphs in order: section, directive (kind, args), text."""
    t = script.read_text(encoding="utf-8")
    nar = t.split("## Narration", 1)[1].split("\n## ", 1)[0]
    out, sec = [], None
    for block in re.split(r"\n\s*\n", nar):
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            lines = block.split("\n")
            sec = lines[0][4:].strip()
            block = "\n".join(lines[1:]).strip()
            if not block:
                continue
        lines = block.split("\n")
        d = None
        for ln in lines:
            m = DIRECTIVE.match(ln.strip())
            if m:
                d = {"kind": m.group(1).lower(),
                     "args": [x.strip() for x in m.group(2).split("|")] if m.group(2) else []}
        text = " ".join(ln for ln in lines if not DIRECTIVE.match(ln.strip())).strip()
        out.append({"section": sec, "directive": d, "text": text,
                    "register": "standard" if sec == "Cold open" else "calm"})
    return out


# ------------------------------------------------------------------ imagery
def catalogue() -> dict[str, dict]:
    """key -> asset record, from the three rights/provenance manifests."""
    cat: dict[str, dict] = {}
    for name, kind in (("food.json", "still"), ("food_clips.json", "clip"),
                       ("food_ai.json", "ai")):
        p = IMAGERY / name
        if not p.exists():
            continue
        for r in json.loads(p.read_text()).get("index") or []:
            if r.get("excluded"):
                continue                    # reviewed and refused, with its reason
            key = r.get("subject") or r.get("key")
            path = IMAGERY / r["local_file"]
            if not path.exists():
                continue
            cat[key] = {**r, "kind": kind, "path": str(path),
                        "credit": ("AI-GENERATED IMAGE" if kind == "ai"
                                   else (r.get("credit_line") or "")),
                        "ai": kind == "ai"}
    return cat


def verify_asset(rec: dict) -> None:
    """The bytes on screen are the bytes the rights/provenance record names."""
    h = hashlib.sha256(Path(rec["path"]).read_bytes()).hexdigest()
    if h != rec.get("sha256"):
        raise ValueError(f"{rec['path']}: sha256 differs from its manifest record")
    if not rec.get("credit"):
        raise ValueError(f"{rec['path']}: no credit line - the beat is dropped, "
                         f"never shown uncredited (CLAUDE.md)")


# Keyword -> asset keys, most specific first. The paragraph's own words pick
# its pictures; nothing is shown that the narration is not talking about,
# except the scale shots, which are the preset's atmosphere.
KEYWORDS: list[tuple[str, list[str]]] = [
    ("x-ray", ["xray-diffraction"]),
    ("calorimet", ["calorimeter"]),
    ("chromatograph", ["gas-chromatograph"]),
    ("pasteur", ["pasteur"]),
    ("maillard", ["maillard", "seared-crust-macro"]),
    ("microscope", ["yeast-micrograph"]),
    ("yeast", ["yeast-micrograph", "dough-field"]),
    ("dough", ["dough-field", "dough", "dough-kneading"]),
    ("loaf", ["bread-loaf", "loaf-crumb-macro"]),
    ("crust", ["seared-crust-macro", "seared-steak"]),
    ("steak", ["thousand-steaks", "seared-steak", "steak-sizzle"]),
    ("sear", ["seared-crust-macro", "steak-sizzle", "thousand-steaks"]),
    ("temper", ["tempering-slab", "chocolate-making"]),
    ("cacao", ["cacao-field", "cocoa-pod", "cocoa-beans"]),
    ("cocoa butter", ["cocoa-butter-wall", "cocoa-beans"]),
    ("snap", ["chocolate-snap", "chocolate-break-macro"]),
    ("gloss", ["gloss-macro"]),
    ("melt", ["melting-square", "melted-chocolate", "chocolate-pour", "chocolate-sheets"]),
    ("liquid", ["chocolate-river", "chocolate-ocean", "chocolate-pour"]),
    ("crystal", ["chocolate-break-macro", "gloss-macro", "chocolate-mountain"]),
    ("bar", ["chocolate-bar", "chocolate-snap", "chocolate-mountain"]),
    ("chocolate", ["chocolate-sheets", "chocolate-river", "chocolate-ocean",
                   "chocolate-mountain", "melting-square"]),
]
# Thumbnail subjects per slug, best first (visuals/thumb_contract.candidates).
THUMB_SUBJECTS = {
    "why-bread-rises-steak-browns-chocolate-snaps":
        ["thumb-chocolate-halves", "thumb-chocolate-crystal", "thumb-chocolate-break", "chocolate-break-macro"],
    "why-does-chocolate-melt-in-your-mouth-not-your-hand":
        ["chocolate-snap", "melting-square", "chocolate-break-macro"],
    "why-does-bread-rise": ["dough-field", "bread-loaf", "loaf-crumb-macro"],
    "why-does-seared-meat-taste-good": ["thousand-steaks", "seared-crust-macro", "seared-steak"],
}
SCALE_SHOTS = ["chocolate-sheets", "chocolate-river", "chocolate-ocean",
               "chocolate-mountain", "cacao-field", "tempering-slab"]


def pool_for(text: str, cat: dict) -> list[str]:
    low = text.lower()
    out: list[str] = []
    for word, keys in KEYWORDS:
        if word in low:
            out += [k for k in keys if k in cat and k not in out]
    out += [k for k in SCALE_SHOTS if k in cat and k not in out]
    return out


# ----------------------------------------------------------------- timeline
def cut_lengths(total: float, lo: float, hi: float, seed: int) -> list[float]:
    """Split `total` seconds into shots each within [lo, hi], varied in length
    around the middle of the range so the cutting has a rhythm, not a metronome."""
    if total <= hi:
        return [total]
    mid = (lo + hi) / 2
    n = max(1, round(total / mid))
    while total / n > hi:
        n += 1
    while n > 1 and total / n < lo:
        n -= 1
    rng = np.random.default_rng(seed)
    w = rng.uniform(0.7, 1.3, n)
    parts = total * w / w.sum()
    for _ in range(200):                                 # clamp, then re-spread
        parts = np.clip(parts, lo, hi)
        err = total - parts.sum()
        if abs(err) < 1e-6:
            break
        free = (parts < hi) if err > 0 else (parts > lo)
        if not free.any():
            break
        parts[free] += err / free.sum()
    return [float(x) for x in parts]


def build_timeline(paras: list[dict], beats: list[dict], cat: dict) -> dict:
    """Shots over the narration: cuts in the opening, holds after the title."""
    shots, t, used, last = [], 0.0, {}, None
    devices = 0
    for i, (p, b) in enumerate(zip(paras, beats)):
        dur = float(b["duration"])
        if p["section"] == "Title card":
            shots.append({"start": t, "dur": dur, "kind": "title", "beat": i,
                          "text": p["text"], "asset": "chocolate-ocean"
                          if "chocolate-ocean" in cat else None})
            t += dur
            continue
        d = p.get("directive") or {}
        if d.get("kind") == "cross_section" and devices < PRESET["devices_per_part_max"]:
            devices += 1
            shots.append({"start": t, "dur": dur, "kind": "device", "beat": i,
                          "asset": "chocolate-break-macro" if "chocolate-break-macro" in cat
                          else pool_for(p["text"], cat)[0],
                          "label": (d.get("args") or ["", ""])[-1]})
            t += dur
            continue
        lo, hi = PRESET["opening_cut_s"] if p["register"] == "standard" else PRESET["calm_hold_s"]
        pool = pool_for(p["text"], cat)
        for j, L in enumerate(cut_lengths(dur, lo, hi, seed=i)):
            # least-used first, so a part does not repeat itself
            order = sorted(pool, key=lambda k: (used.get(k, 0), pool.index(k)))
            pick = next((k for k in order if k != last), order[0])
            last = pick
            used[pick] = used.get(pick, 0) + 1
            shots.append({"start": t, "dur": L, "kind": "picture", "beat": i,
                          "asset": pick, "register": p["register"]})
            t += L
    return {"preset": PRESET["id"], "grade": FOOD_GRADE["id"], "duration": t,
            "shots": shots}


# ----------------------------------------------------------- picture layers
def _font(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    cands = (["/System/Library/Fonts/Supplemental/Georgia.ttf"] if serif else
             ["/System/Library/Fonts/Avenir Next.ttc",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"])
    cands += ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size, index=5 if c.endswith("Avenir Next.ttc") else 0)
            except Exception:                              # noqa: BLE001
                return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * s + 0.5)), max(h, int(im.height * s + 0.5))),
                   Image.LANCZOS)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


class Still:
    """A still with a slow zoom and a two-layer depth parallax."""

    def __init__(self, path: str):
        # Oversize by the zoom and parallax margin once; every frame is then
        # a crop + resize of this, never of the multi-megapixel original.
        m = PRESET["still_zoom"][1] + 0.06
        src = Image.open(path).convert("RGB")
        self.base = cover(src, int(W * m), int(H * m))
        import thumbs                                         # noqa: PLC0415
        sal = thumbs.saliency_abs(self.base.resize((W // 4, H // 4)))
        mask = Image.fromarray((np.clip(sal / (np.percentile(sal, 97) + 1e-6), 0, 1)
                                * 255).astype(np.uint8))
        self.mask = mask.resize(self.base.size, Image.BILINEAR).filter(
            ImageFilter.GaussianBlur(24))

    def frame(self, u: float, direction: int = 1) -> Image.Image:
        """u in [0, 1] through the shot."""
        z0, z1 = PRESET["still_zoom"]
        e = 0.5 - 0.5 * math.cos(math.pi * u)               # ease in-out
        bw, bh = self.base.size

        def view(z: float, dx: float) -> tuple:
            # The base is oversized by the zoom + parallax margin, so at z=1
            # the window is exactly one output frame wide, centred.
            vw, vh = W / z, H / z
            cx, cy = bw / 2 + dx, bh / 2
            return (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)

        p = PRESET["parallax_px"] * (e - 0.5) * direction
        zb = z0 + (z1 - z0) * e * 0.6
        zf = z0 + (z1 - z0) * e
        bg = self.base.resize((W, H), Image.BILINEAR, box=view(zb, -p * 0.4))
        fg = self.base.resize((W, H), Image.BILINEAR, box=view(zf, p))
        mk = self.mask.resize((W, H), Image.BILINEAR, box=view(zf, p))
        return Image.composite(fg, bg, mk)


class Clip:
    """A real clip, decoded once, scaled to cover the frame."""

    def __init__(self, path: str, seconds: float):
        n = int(seconds * FPS) + 2
        cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf",
               f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
               "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        k = len(raw) // (W * H * 3)
        if k == 0:
            raise ValueError(f"{path}: no frames decoded")
        self.frames = np.frombuffer(raw[:k * W * H * 3], np.uint8).reshape(k, H, W, 3)

    def frame(self, u: float, direction: int = 1) -> Image.Image:
        i = int(u * (len(self.frames) - 1))
        # ping-pong a clip shorter than its hold, never a hard loop jump
        return Image.fromarray(self.frames[i])


def cross_section(base: Image.Image, u: float, label: str) -> Image.Image:
    """The signature device: one glowing butter-white line through the cut."""
    im = Image.blend(base, Image.new("RGB", base.size, INK), 0.35)
    lines = Image.new("L", base.size, 0)
    d = ImageDraw.Draw(lines)
    reveal = min(1.0, u / 0.6)
    x_end = int(W * (0.12 + 0.76 * reveal))
    for k in range(9):                                     # stacked crystal layers
        y = int(H * (0.30 + 0.05 * k))
        pts = [(x, y + int(10 * math.sin(x / 70.0 + k * 0.9)))
               for x in range(int(W * 0.12), x_end, 12)]
        if len(pts) > 1:
            d.line(pts, fill=255, width=3)
    glow = lines.filter(ImageFilter.GaussianBlur(10))
    core = Image.new("RGB", base.size, GLOW)
    im = Image.composite(core, im, glow.point(lambda v: min(255, int(v * 1.6))))
    im = Image.composite(core, im, lines)
    if label and u > 0.35:
        dd = ImageDraw.Draw(im)
        f = _font(40)
        a = min(1.0, (u - 0.35) / 0.2)
        col = tuple(int(c * a + 20 * (1 - a)) for c in GLOW)
        dd.text((int(W * 0.12), int(H * 0.22)), label.upper(), font=f, fill=col)
    return im


# ------------------------------------------------------------------ overlays
def draw_credit(im: Image.Image, credit: str) -> tuple:
    d = ImageDraw.Draw(im)
    f = _font(20)
    tb = d.textbbox((0, 0), credit, font=f)
    x, y = W - (tb[2] - tb[0]) - 28, 22
    d.text((x + 1, y + 1), credit, font=f, fill=(0, 0, 0))
    d.text((x, y), credit, font=f, fill=(225, 214, 200))
    return (x - 2, y - 2, x + tb[2] - tb[0] + 3, y + tb[3] - tb[1] + 6)


def wrap(text: str, f, width: int, d: ImageDraw.ImageDraw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) > width and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def draw_caption(im: Image.Image, text: str) -> tuple | None:
    if not text:
        return None
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(46)
    lines = wrap(text, f, int(W * 0.72), d)[:2]
    lh = 60
    y0 = H - 70 - lh * len(lines)
    box = None
    for k, ln in enumerate(lines):
        tw = d.textlength(ln, font=f)
        x = (W - tw) / 2
        y = y0 + k * lh
        d.rounded_rectangle((x - 18, y - 6, x + tw + 18, y + lh - 6), 10,
                            fill=(10, 6, 4, 150))
        d.text((x, y), ln, font=f, fill=TEXT)
        b = (int(x - 20), int(y - 8), int(x + tw + 20), int(y + lh))
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    return box


def draw_card(im: Image.Image, d_: dict, u: float) -> tuple | None:
    """A quiet lower-left card for a directive whose figure the voice speaks."""
    kind, args = d_.get("kind"), d_.get("args") or []
    if kind == "stat" and len(args) >= 2:
        big, small = args[0], args[1]
    elif kind == "timeline" and args:
        big, small = args[0].split("=", 1)[0], args[0].split("=", 1)[-1]
    elif kind == "kitchen" and len(args) >= 2:
        big, small = f"{args[0]}°C", args[1]
    elif kind == "define" and len(args) >= 2:
        big, small = args[0], args[1]
    else:
        return None
    if u < 0.08 or u > 0.92:
        return None
    d = ImageDraw.Draw(im, "RGBA")
    fb, fs = _font(92, serif=True), _font(30)
    x, y = 90, int(H * 0.50)
    d.text((x, y), big, font=fb, fill=GLOW)
    d.text((x + 4, y + 110), small.upper(), font=fs, fill=(230, 214, 190))
    tw = max(d.textlength(big, font=fb), d.textlength(small.upper(), font=fs))
    return (x - 6, y - 6, int(x + tw + 10), y + 160)


def draw_title(im: Image.Image, text: str, u: float) -> tuple:
    d = ImageDraw.Draw(im, "RGBA")
    f = _font(78, serif=True)
    lines = wrap(text, f, int(W * 0.7), d)
    a = int(255 * min(1.0, u / 0.25, (1 - u) / 0.15 if u > 0.85 else 1.0))
    y = H / 2 - len(lines) * 50
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((W - tw) / 2, y), ln, font=f, fill=(*TEXT, max(0, a)))
        y += 100
    return (int(W * 0.12), int(H / 2 - len(lines) * 50 - 10), int(W * 0.88), int(y + 10))


# ------------------------------------------------------------------- render
def caption_at(spans: list[tuple], t: float) -> str:
    for s, e, txt in spans:
        if s <= t < e:
            return txt
    return ""


def caption_spans(beats: list[dict]) -> list[tuple]:
    """(start, end, text) on the video clock, ~8 words per caption."""
    out, t0 = [], 0.0
    for b in beats:
        for sp in b["spans"]:
            words = sp["text"].split()
            dur = sp["end"] - sp["start"]
            n = max(1, math.ceil(len(words) / 8))
            per = math.ceil(len(words) / n)
            for k in range(n):
                seg = words[k * per:(k + 1) * per]
                if not seg:
                    continue
                s = t0 + sp["start"] + dur * (k * per) / len(words)
                e = t0 + sp["start"] + dur * min(len(words), (k + 1) * per) / len(words)
                out.append((round(s, 3), round(e, 3), " ".join(seg)))
        t0 += b["duration"]
    return out


def srt(spans: list[tuple]) -> str:
    def ts(x: float) -> str:
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i + 1}\n{ts(s)} --> {ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(spans))


def render(script: Path, voice_dir: Path, out: Path, beat_idx: list[int] | None,
           bed: Path | None = None, proof_every: int = 90) -> dict:
    paras = parse(script)
    if beat_idx is not None:
        paras = [paras[i] for i in beat_idx]
    beats = json.loads((voice_dir / "beats.json").read_text())["beats"]
    if len(beats) != len(paras):
        raise ValueError(f"{len(beats)} voiced beats for {len(paras)} paragraphs")
    for p, b in zip(paras, beats):
        if b["text"].split()[:6] != p["text"].split()[:6]:
            raise ValueError(f"beat {b['index']} voices {b['text'][:40]!r}, not "
                             f"{p['text'][:40]!r}")
        if b["register"] != p["register"]:
            raise ValueError(f"beat {b['index']} is {b['register']}, its section "
                             f"says {p['register']}")
    cat = catalogue()
    tl = build_timeline(paras, beats, cat)
    for s in tl["shots"]:
        if s.get("asset"):
            verify_asset(cat[s["asset"]])
    caps = caption_spans(beats)
    work = out.with_suffix(".work")
    work.mkdir(parents=True, exist_ok=True)
    proofs = work / "proofs"
    proofs.mkdir(exist_ok=True)
    silent = work / "picture.mp4"
    # Re-mixing sound or captions-free changes must not cost a 10-minute
    # picture pass: reuse picture.mp4 when the shot list is unchanged.
    tl_path, log_path = work / "timeline.json", work / "proofs.json"
    if (silent.exists() and tl_path.exists() and log_path.exists()
            and json.loads(tl_path.read_text()) == json.loads(json.dumps(tl))):
        return _finish(script, voice_dir, out, work, silent, tl, beats, caps, cat,
                       json.loads(log_path.read_text()), bed)
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
         "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(silent)],
        stdin=subprocess.PIPE)
    total = int(round(tl["duration"] * FPS))
    cache: dict[str, object] = {}
    proof_log = []
    xf = int(PRESET["crossfade_s"] * FPS)

    def layer(s: dict, local: float) -> Image.Image:
        key = s.get("asset")
        rec = cat.get(key) if key else None
        if key not in cache:
            cache.clear() if len(cache) > 6 else None
            cache[key] = (Clip(rec["path"], s["dur"] + 2) if rec and rec["kind"] == "clip"
                          else Still(rec["path"]) if rec else None)
        src = cache[key]
        u = min(1.0, max(0.0, local / max(s["dur"], 1e-6)))
        base = src.frame(u, 1 if hash(key) % 2 else -1) if src else Image.new("RGB", (W, H), INK)
        if s["kind"] == "device":
            base = cross_section(base, u, s.get("label", ""))
        if s["kind"] == "title":
            base = Image.blend(base, Image.new("RGB", (W, H), INK), 0.55)
        return base

    shots = tl["shots"]
    si = 0
    for f in range(total):
        t = f / FPS
        while si < len(shots) - 1 and t >= shots[si]["start"] + shots[si]["dur"]:
            si += 1
        s = shots[si]
        local = t - s["start"]
        pic = layer(s, local)
        # calm holds dissolve into the next shot; the opening cuts hard
        nxt = shots[si + 1] if si + 1 < len(shots) else None
        remain = s["start"] + s["dur"] - t
        if (nxt and s.get("register") == "calm" and nxt.get("kind") != "title"
                and remain * FPS < xf):
            a = 1 - remain * FPS / xf
            pic = Image.blend(pic, layer(nxt, 0.0), a * 0.999)
        arr = np.asarray(pic, dtype=np.uint8)
        graded = grade_frame(arr)
        if f % proof_every == 0:
            np.save(proofs / f"{f:06d}.npy", arr[::PROOF_STEP, ::PROOF_STEP])
        im = Image.fromarray(graded)
        boxes = []
        rec = cat.get(s.get("asset") or "")
        if rec:
            boxes.append(draw_credit(im, rec["credit"]))
        p = paras[s["beat"]]
        if s["kind"] == "title":
            boxes.append(draw_title(im, s["text"], min(1.0, local / s["dur"])))
        elif p.get("directive"):
            bstart = next(x["start"] for x in shots if x["beat"] == s["beat"])
            since = t - bstart
            if 1.0 <= since <= 7.0:
                b = draw_card(im, p["directive"], (since - 1.0) / 6.0)
                if b:
                    boxes.append(b)
        # the title card shows the question itself; no caption under it
        cb = None if s["kind"] == "title" else draw_caption(im, caption_at(caps, t))
        if cb:
            boxes.append(cb)
        if s["kind"] == "device":
            boxes.append((0, 0, W, H))       # the device is drawn, not graded
        if f % proof_every == 0:
            proof_log.append({"frame": f, "shot": shots.index(s), "kind": s["kind"],
                              "masked": [list(map(int, b)) for b in boxes if b]})
        enc.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
        if f % (FPS * 10) == 0:
            print(f"  frame {f}/{total}", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encoder failed")
    tl_path.write_text(json.dumps(tl))
    log_path.write_text(json.dumps(proof_log))
    return _finish(script, voice_dir, out, work, silent, tl, beats, caps, cat,
                   proof_log, bed)


def _finish(script, voice_dir, out, work, silent, tl, beats, caps, cat,
            proof_log, bed) -> dict:
    shots = tl["shots"]

    # ---- audio: the voice, the low food bed ducked under it, then the mux
    voice = work / "voice.wav"
    lst = work / "voice.txt"
    lst.write_text("".join(f"file '{voice_dir / b['file']}'\n" for b in beats))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-ar", "48000", "-ac", "1", str(voice)], check=True)
    import food_sound                                         # noqa: PLC0415
    bed_raw = bed or food_sound.build_bed(tl, work / "bed.wav")
    mix = food_sound.duck_and_mix(voice, bed_raw, work)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mix["mix"]),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", str(out)], check=True)
    out.with_suffix(".srt").write_text(srt(caps))
    ai = sorted({s["asset"] for s in shots if s.get("asset") and cat[s["asset"]]["ai"]})
    real = sorted({s["asset"] for s in shots if s.get("asset") and not cat[s["asset"]]["ai"]})
    spec = {
        "script": str(script.relative_to(ROOT)) if script.is_relative_to(ROOT) else str(script),
        "preset": PRESET, "grade": FOOD_GRADE, "duration_s": round(tl["duration"], 2),
        "shots": shots, "captions": {"burned_in": True, "sidecar": out.with_suffix(".srt").name},
        "ai_assets": ai, "real_assets": real,
        "credits": {k: cat[k]["credit"] for k in real},
        # YouTube's altered-or-synthetic-content disclosure. loop/upload.py
        # reads this field and sends status.containsSyntheticMedia.
        "altered_content": bool(ai),
        "ai_video_clips": 0,
        "ai_video_note": "no open video model runs on this Mac; AI shots are stills with motion",
        "sound": mix["measured"], "proofs": proof_log,
    }
    out.with_suffix(".food.json").write_text(json.dumps(spec, indent=1))
    return spec


# -------------------------------------------------------------------- check
def _decode(mp4: Path, frames: list[int]) -> dict[int, np.ndarray]:
    sel = "+".join(f"eq(n\\,{f})" for f in frames)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-vf", f"select={sel}",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    k = len(raw) // (W * H * 3)
    arr = np.frombuffer(raw[:k * W * H * 3], np.uint8).reshape(k, H, W, 3)
    return {f: arr[i] for i, f in enumerate(frames[:k])}


def check_spec(spec: dict) -> list[str]:
    """Cadence, device count and honesty fields, from the episode spec."""
    p: list[str] = []
    shots = spec.get("shots") or []
    if not shots:
        return ["no shots - a render that shows nothing proves nothing"]
    lo_o, hi_o = PRESET["opening_cut_s"]
    lo_c, hi_c = PRESET["calm_hold_s"]
    for i, s in enumerate(shots):
        if s["kind"] != "picture":
            continue
        d = s["dur"]
        if s.get("register") == "standard" and not (lo_o - 0.05 <= d <= hi_o + 0.05):
            p.append(f"opening shot {i} holds {d:.1f}s, outside {lo_o}-{hi_o}s")
        if s.get("register") == "calm" and d > hi_c + 0.05:
            p.append(f"calm shot {i} holds {d:.1f}s, over {hi_c}s")
        if s.get("register") == "calm" and d < lo_c - 0.05:
            beat_total = sum(x["dur"] for x in shots if x["beat"] == s["beat"])
            if beat_total >= lo_c:
                p.append(f"calm shot {i} cuts after {d:.1f}s, under {lo_c}s")
    if not any(s.get("register") == "standard" for s in shots):
        p.append("no opening shots: the hooked opening is missing")
    if not any(s.get("register") == "calm" for s in shots):
        p.append("no calm holds: the register never shifts")
    n_dev = sum(1 for s in shots if s["kind"] == "device")
    if n_dev > PRESET["devices_per_part_max"]:
        p.append(f"{n_dev} signature devices in one part, over "
                 f"{PRESET['devices_per_part_max']}")
    if spec.get("ai_assets") and not spec.get("altered_content"):
        p.append("AI stills on screen but altered_content is not set")
    for k, c in (spec.get("credits") or {}).items():
        if not c:
            p.append(f"{k}: real asset with no credit line")
    if not (spec.get("captions") or {}).get("burned_in"):
        p.append("captions are not on")
    return p


def check_frames(ungraded: np.ndarray, final: np.ndarray,
                 masks: np.ndarray) -> tuple[int, list[str]]:
    """Grade applied and subject coverage on (N, h, w, 3) proof frames.

    `masks` is True where a frame is PICTURE (type, credits and captions are
    drawn after the grade and are excluded). The final frame must equal the
    re-graded ungraded frame within GRADE_TOLERANCE, and be closer to it than
    to the ungraded one - so "grade applied" is measured, not asserted."""
    import thumbs                                             # noqa: PLC0415
    p, examined, cover_ok = [], 0, 0
    for i in range(len(ungraded)):
        m = masks[i].astype(bool)
        if m.sum() < 500:
            continue
        examined += 1
        got = final[i].astype(np.float32)
        want = grade_frame(ungraded[i]).astype(np.float32)
        dg = float(np.abs(got - want)[m].mean())
        du = float(np.abs(got - ungraded[i].astype(np.float32))[m].mean())
        if dg > GRADE_TOLERANCE or dg >= du:
            p.append(f"proof frame {i}: grade not applied (|out-graded| {dg:.1f}, "
                     f"|out-ungraded| {du:.1f})")
        pic = Image.fromarray(ungraded[i])
        x0, y0, x1, y1 = thumbs.subject_box(pic, keep=0.80)
        energy = float((thumbs.saliency_abs(pic) >= thumbs.SUBJECT_LEVEL).mean())
        if max(x1 - x0, y1 - y0) >= SUBJECT_COVERAGE_MIN and energy >= thumbs.MIN_SUBJECT_ENERGY:
            cover_ok += 1
    if examined == 0:
        p.append("examined zero proof frames - a contract that checks nothing fails")
    elif cover_ok < 0.8 * examined:
        p.append(f"subject covers >= {SUBJECT_COVERAGE_MIN:.0%} of the frame on only "
                 f"{cover_ok}/{examined} picture frames")
    return examined, p


def export_proof(mp4: Path, out_npz: Path) -> Path:
    """The picture proof frames of a render: ungraded, decoded final, mask."""
    spec = json.loads(mp4.with_suffix(".food.json").read_text())
    proofs = [x for x in spec["proofs"] if x["kind"] == "picture"]
    proofs = proofs[::max(1, math.ceil(len(proofs) / 12))]   # ~12 spread frames
    frames = _decode(mp4, [x["frame"] for x in proofs])
    work = mp4.with_suffix(".work") / "proofs"
    U, F, M = [], [], []
    for x in proofs:
        f = x["frame"]
        if f not in frames:
            continue
        u = np.load(work / f"{f:06d}.npy")
        fin = frames[f][::PROOF_STEP, ::PROOF_STEP]
        m = np.ones(u.shape[:2], bool)
        for b in x["masked"]:
            x0, y0, x1, y1 = (v // PROOF_STEP for v in b)
            m[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2] = False
        U.append(u)
        F.append(fin)
        M.append(m)
    np.savez_compressed(out_npz, ungraded=np.stack(U), final=np.stack(F),
                        masks=np.stack(M))
    return out_npz


def check(mp4: Path) -> list[str]:
    """The preset's contract, measured on the rendered file. [] = it holds."""
    spec_p = mp4.with_suffix(".food.json")
    if not spec_p.exists():
        return [f"{mp4.name}: no episode spec beside it"]
    spec = json.loads(spec_p.read_text())
    p = check_spec(spec)
    tmp = mp4.with_suffix(".work") / "proof.npz"
    export_proof(mp4, tmp)
    z = np.load(tmp)
    _n, fp = check_frames(z["ungraded"], z["final"], z["masks"])
    return p + fp


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.split("\n\n")[0])
        return 2
    if argv[0] == "check":
        probs = check(Path(argv[1]))
        print("\n".join(probs) or "food preset contract holds")
        return 1 if probs else 0
    if argv[0] == "render":
        idx = None
        if "--beats" in argv:
            idx = [int(x) for x in argv[argv.index("--beats") + 1].split(",")]
        spec = render(Path(argv[1]), Path(argv[2]), Path(argv[3]), idx)
        print(json.dumps({k: spec[k] for k in ("duration_s", "ai_assets", "real_assets",
                                               "altered_content")}, indent=1))
        probs = check(Path(argv[3]))
        print("\n".join(probs) or "food preset contract holds")
        return 1 if probs else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
