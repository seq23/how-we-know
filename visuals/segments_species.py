"""The species-image segment: show the animal the narration just named.

Same contract as segments.py -- fn(t, **kwargs) -> PIL.Image (RGB, W x H), t in
[0,1] -- and the same palette, fonts and restraint.

Why this segment exists
-----------------------
The owner watched episode 1 and said: "I would rather have more animal pictures
-- the descriptions are happening and we have no animal photos of what we are
describing." She is right. Every other segment in this repo draws an
abstraction: a gauge, a ladder, a chain of stages. When the narration says
"barreleye", the screen should be able to show a barreleye.

What it will not do
-------------------
Draw anything the rights index has not verified. Every asset is re-hashed
against the sha256 its licence was checked under before a single pixel is
composited (`imagery_species.verify_rights`), the check runs once per process
and hard-fails on an empty set, and a subject the index declares
UNILLUSTRATABLE raises rather than falling back to a lookalike. A giant squid
plate captioned "colossal squid" is a lie told in pictures.

The credit line
---------------
Always drawn, always naming what the image ACTUALLY IS. An 1887 lithograph is
credited "CHALLENGER REPORT PLATE, 1887", never "photograph". An ROV frame from
an episode about red light is credited "NOAA OCEAN EXPLORATION, ROV LAMPS",
because episode 05's own narration sets that rule: "If it uses white ROV light,
the caption must say so." This mirrors how thumbs.py already credits per asset
via `thumb_credit`; the field here is `credit_line`.

The subject label
-----------------
CONTRACT.md rule 1 -- never write a value that is not already stated in the
narration -- applies with full force. The label is whatever word the narration
used, passed in by the directive or matched verbatim by the planner heuristic.
The renderer never names the animal itself: if no label is supplied, none is
drawn, and the credit stands alone.

Wiring
------
`install()` grafts the renderer onto the `segments` module and the
`{{species: ...}}` directive onto the planner, exactly as segments_ext2 does.
See the handoff note at the bottom for the two one-line edits that make it
automatic; they touch planner.py and assemble.py and are NOT applied here.
"""
from __future__ import annotations

import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "research")))

from design import (W, H, INK, DEEP, MID, CYAN, PALE, AMBER, TEXT, MUTED,
                    F_DISPLAY, F_LABEL, F_MONO, ease, mix)
import thumbs as T                       # TREATMENTS, grade, cover, trim_scan_border
import imagery_species as SP             # the index and its guard

IMAGERY = os.path.abspath(os.path.join(HERE, "..", "channel", "imagery"))

SEGMENTS = ("species_image",)


# ------------------------------------------------------------------ the guard
#
# Verified once per process, then cached. Cached on the VERIFIED MANIFEST, not
# on a boolean: if the check ever fails the exception propagates on every
# subsequent call rather than being swallowed by a "already tried" flag.

_index = None


def index() -> dict:
    """The rights-verified species index. Raises rather than returning empty."""
    global _index
    if _index is None:
        man = SP.load_species()
        n = SP.verify_rights(man)          # hard-fails on zero; re-hashes every file
        if n == 0:                         # belt and braces; verify_rights raises first
            raise ValueError("species index verified zero assets")
        by_subject: dict[str, list[dict]] = {}
        by_file: dict[str, dict] = {}
        for rec in man["assets"]:
            by_subject.setdefault(rec["subject"], []).append(rec)
            by_file[rec["local_file"]] = rec
        # A record that has to caveat itself goes last within its subject. The
        # 2004 anglerfish and the 2024 barreleye are both specimens in a tray on
        # deck: correctly identified, cleanly public domain, and not what the
        # animal looks like alive. They stay in the index -- an episode with
        # three anglerfish beats needs three anglerfish -- but the first picture
        # a viewer gets of an animal should not be the one that needs a
        # disclaimer under it. Manifest order is preserved within each group, so
        # the hand-set editorial order still decides everything else.
        for recs in by_subject.values():
            recs.sort(key=lambda r: bool(r.get("standing_note")))
        man["_by_subject"], man["_by_file"], man["_verified"] = by_subject, by_file, n
        _index = man
    return _index


def available(subject: str) -> bool:
    return bool(index()["_by_subject"].get(subject))


def resolve(subject: str | None = None, asset: str | None = None,
            pick: int = 0) -> dict:
    """Choose the record to draw. Refuses to substitute."""
    man = index()
    if asset:
        rec = man["_by_file"].get(asset)
        if rec is None:
            raise KeyError(f"species asset {asset!r} is not in the verified index")
        return rec
    if not subject:
        raise KeyError("species_image needs a subject or an asset")
    if subject in SP.UNILLUSTRATABLE:
        raise KeyError(
            f"subject {subject!r} is declared unillustratable: "
            f"{SP.UNILLUSTRATABLE[subject]['why'][:200]}... "
            f"Do not substitute; the drawn treatment stands.")
    cands = man["_by_subject"].get(subject)
    if not cands:
        raise KeyError(f"no verified public-domain image for subject {subject!r}")
    return cands[pick % len(cands)]


# ------------------------------------------------------------- image handling

_treated: dict[str, Image.Image] = {}


def treated(rec: dict) -> Image.Image:
    """Load, crop, and grade an asset the way its own medium wants.

    Reuses thumbs.TREATMENTS rather than reimplementing them, so a Challenger
    plate looks the same in the video as it does on the thumbnail: ink rendered
    as light on deep water, the engraver's line intact, nobody able to mistake
    it for a photograph. `grade` (the shadow-tint built for ROV stills) is
    applied only to photographs -- running it over a lithograph that has already
    been mapped onto the palette is what turned an early chart into a white
    sheet with a black panel bolted to one side.
    """
    key = rec["local_file"]
    if key in _treated:
        return _treated[key]
    raw = Image.open(os.path.join(IMAGERY, key))
    if rec.get("crop"):
        cx0, cy0, cx1, cy1 = rec["crop"]
        w, h = raw.size
        raw = raw.crop((int(w * cx0), int(h * cy0), int(w * cx1), int(h * cy1)))
    treat = rec.get("treatment", "photo")
    if treat not in T.TREATMENTS:
        raise KeyError(f"{key}: unknown treatment {treat!r}")
    im = T.TREATMENTS[treat](raw)
    if treat == "photo":
        im = T.grade(im)
    if len(_treated) > 12:
        _treated.clear()
    _treated[key] = im.convert("RGB")
    return _treated[key]


_frame_cache: dict[str, tuple[float, float, float]] = {}

# How much of the frame width the animal should occupy. 0.52 rather than filling
# it: an animal cropped to its own bounding box reads as texture, not as a
# creature. Same finding as thumbs.frame_subject, same number range.
SUBJECT_FILL = 0.52
MAX_PUSH = 1.8


def _auto_frame(src: Image.Image, rec: dict) -> tuple[float, float, float]:
    """(subject_x, subject_y, zoom) so the animal fills SUBJECT_FILL of the frame."""
    key = rec["local_file"]
    if key in _frame_cache:
        return _frame_cache[key]
    if rec.get("treatment", "photo") != "photo":
        # A plate or a chart is already the whole picture; pushing in on its
        # densest region crops the animal's tail off.
        out = (0.5, 0.5, 1.0)
    else:
        x0, y0, x1, y1 = T.subject_box(src)
        bw, bh = max(1e-3, x1 - x0), max(1e-3, y1 - y0)
        if bw > 0.55 or bh > 0.55:
            # The saliency mass is spread across the frame, which means it is
            # not one animal -- it is a lit rock face, or a whole reef, or
            # marine snow. Pushing in on the CENTROID of a diffuse box lands on
            # empty water: one red-shrimp frame zoomed to a patch of gravel with
            # the shrimp off-frame. When the measure cannot find a subject, do
            # not act on it.
            out = (0.5, 0.5, 1.0)
        else:
            z = min(SUBJECT_FILL / bw, (SUBJECT_FILL * 0.95) / bh, MAX_PUSH)
            out = ((x0 + x1) / 2, (y0 + y1) / 2, max(1.0, z))
    if len(_frame_cache) > 32:
        _frame_cache.clear()
    _frame_cache[key] = out
    return out


def _needs_backing(img: Image.Image, box: tuple[int, int, int, int]) -> bool:
    """True when type over `box` would sit on something too light to read on.

    A 1960 press print of a hull against a tropical sky puts a third of the
    frame near paper-white; the label went into it and vanished. Measure the
    region that is about to be typed on rather than assuming every frame is dark
    water.
    """
    region = img.convert("L").crop(box).resize((24, 8), Image.BILINEAR)
    px = list(region.getdata())
    return (sum(px) / len(px)) > 70


def _bg(t: float) -> Image.Image:
    """Deep water, the same gradient every other segment sits on."""
    g = Image.new("RGB", (2, 128))
    px = g.load()
    for y in range(128):
        c = mix(DEEP, INK, y / 127)
        px[0, y] = c
        px[1, y] = c
    return g.resize((W, H), Image.BILINEAR)


def _snow(d, t, n=55, seed=19, speed=0.18):
    r = random.Random(seed)
    for _ in range(n):
        x0, y0 = r.random(), r.random()
        sp = speed * r.uniform(0.4, 1.6)
        rad = r.uniform(1, 3)
        a = int(r.uniform(30, 110))
        x = x0 * W + math.sin((t * sp * 6) + x0 * 9) * 12
        y = ((y0 + t * sp) % 1.0) * H
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(*PALE, a))


_fc = {}


def font(path, size):
    k = (path, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(size))
    return _fc[k]


def _tracked(d, xy, text, f, fill, track=6):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track


def _tracked_w(d, text, f, track=6):
    return sum(d.textlength(ch, font=f) + track for ch in text) - track


def _scrim(h_frac: float, strength: float = 0.92) -> Image.Image:
    """A bottom gradient to black, so type always sits on near-ink.

    A photograph decides its own tonality and a caption cannot be allowed to
    depend on it. Same reasoning as the directional scrim in thumbs.compose.
    """
    band = int(H * h_frac)
    g = Image.new("L", (1, band))
    px = g.load()
    for y in range(band):
        px[0, y] = int(255 * strength * (y / max(1, band - 1)) ** 1.5)
    mask = g.resize((W, band), Image.BILINEAR)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    black = Image.new("RGBA", (W, band), (*INK, 255))
    layer.paste(black, (0, H - band), mask)
    return layer


# ------------------------------------------------------------- the renderer

def species_image(t, subject=None, asset=None, label="", credit="", pick=0,
                  note="", zoom=1.0):
    """One verified public-domain image of the animal the narration just named.

    subject  index key, e.g. "barreleye". Refused if unillustratable.
    asset    an explicit local_file, when a script wants one exact picture.
    label    the word the NARRATION used. Drawn top-left. Never invented here.
    credit   overrides the record's credit_line. Normally leave empty.
    pick     which of the subject's images, when there are several.
    note     one short line under the credit, e.g. a stated caveat.
    zoom     extra push-in for a frame whose subject is small.
    """
    rec = resolve(subject, asset, pick)
    src = treated(rec)
    img = _bg(t).convert("RGBA")

    # A slow push, 3.5% over the beat. Enough that the frame is alive; small
    # enough that nobody reads it as a zoom.
    e = ease(t)
    scale = zoom * (1.0 + 0.035 * e)
    sw, sh = src.size

    # A PLATE OR A CHART IS NEVER CROPPED. Cover-to-fill is right for a
    # photograph -- an ROV frame is a window and any part of it is still the
    # window -- and wrong for an engraving, where the picture has edges the
    # engraver chose. Full-bleeding the 1887 frilled shark plate cut the head
    # off the animal, which is the one thing that plate exists to show. So the
    # medium decides the layout: photographs fill the frame, printed matter is
    # contained inside it.
    printed = rec.get("treatment", "photo") in ("plate", "chart")
    if not printed and sw >= W * 0.98 and sh >= H * 0.92:
        # Big enough to hold the frame: full bleed, pushed in on the animal.
        #
        # An ROV still is usually a small animal in a large volume of water, and
        # a straight 1:1 crop leaves the subject as a speck with the credit line
        # bigger than the fish. thumbs.subject_box already finds where the
        # animal is -- the same measurement the thumbnail builder frames on --
        # so reuse it rather than hand-tuning a zoom per asset, which is exactly
        # the failure thumbs.py documents.
        cx, cy, z = _auto_frame(src, rec)
        pic = T.cover(src, W, H, subject=(cx, cy), place=(0.5, 0.48), zoom=z * scale)
        img.alpha_composite(pic.convert("RGBA"), (0, 0))
        card = None
    else:
        # Smaller than the canvas. Fit it inside a card rather than upscaling
        # into mush: an archival print shown at something near its true size,
        # framed, is honest; the same print blown up to 1920 px is not.
        box_w, box_h = int(W * 0.86), int(H * 0.78)
        f = min(box_w / sw, box_h / sh, 1.6) * scale
        nw, nh = max(2, int(sw * f)), max(2, int(sh * f))
        pic = src.resize((nw, nh), Image.LANCZOS)
        x, y = (W - nw) // 2, int(H * 0.46) - nh // 2
        # a soft bloom behind the card so it sits in water, not on a slab
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(halo).rectangle([x - 26, y - 26, x + nw + 26, y + nh + 26],
                                       fill=(*MID, 120))
        img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(34)))
        img.alpha_composite(pic.convert("RGBA"), (x, y))
        card = (x, y, nw, nh)

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    _snow(d, t, n=48)
    if card:
        x, y, nw, nh = card
        d.rectangle([x - 1, y - 1, x + nw, y + nh], outline=(*CYAN, 105), width=2)

    img.alpha_composite(_scrim(0.30 if card is None else 0.22))
    img.alpha_composite(ov)
    d = ImageDraw.Draw(img)

    # --- the label: the narration's own word, or nothing -----------------
    if label:
        fl = font(F_DISPLAY, 62)
        rise = (1 - ease(min(t * 3, 1))) * 14
        lw = int(d.textlength(label, font=fl))
        if _needs_backing(img, (60, 60, min(W, 160 + lw), 200)):
            band = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
            g = Image.new("L", (1, 230))
            gp = g.load()
            for y in range(230):
                gp[0, y] = int(215 * (1 - y / 229) ** 1.4)
            band.paste(Image.new("RGBA", (W, 230), (*INK, 255)), (0, 0),
                       g.resize((W, 230), Image.BILINEAR))
            img.alpha_composite(band, (0, 0))
            d = ImageDraw.Draw(img)
        d.rectangle([96, 92 + rise, 100, 92 + rise + 62], fill=(*AMBER, 230))
        d.text((124, 84 + rise), label, font=fl, fill=(*TEXT, 255))

    # --- the credit: what the image actually IS --------------------------
    line = (credit or rec["credit_line"]).upper()
    fc = font(F_LABEL, 24)
    a = int(235 * ease(min(max(0.0, t * 2.4 - 0.15), 1.0)))
    cw = _tracked_w(d, line, fc, 5)
    d.line([(96, H - 92), (96 + 34, H - 92)], fill=(*CYAN, a), width=2)
    _tracked(d, (142, H - 105), line, fc, (*CYAN, a), track=5)
    # A record may carry a standing caveat about what the picture is -- a
    # specimen photographed on deck is not the animal in its habitat, and the
    # frame should say so without the script having to remember.
    sub = note or rec.get("standing_note", "")
    if sub:
        d.text((142, H - 70), sub, font=font(F_LABEL, 21), fill=(*MUTED, int(a * 0.85)))

    # The medium, spelled out on the right. A viewer who wants to know whether
    # they are looking at a drawing or a photograph should not have to decode a
    # credit line.
    dep = rec["depicts"].upper()
    fd = font(F_MONO, 19)
    d.text((W - 96 - d.textlength(dep, font=fd), H - 102), dep,
           font=fd, fill=(*MUTED, int(a * 0.8)))
    return img.convert("RGB")


# ------------------------------------------------------------------ planning

def parse_species_directive(kind: str, raw: str):
    """{{species: SUBJECT | LABEL | NOTE}} -> ("species_image", args) or None.

    SUBJECT is an index key. LABEL is the word the NARRATION uses and is the
    only thing drawn as prose, so a caller that omits it gets a credit line and
    no claim. A subject that is unknown, unillustratable or uncovered returns
    None, which makes the planner fall back to the prose heuristics -- the same
    behaviour CONTRACT.md rule 5 already specifies for a directive whose data is
    absent. Silence is the correct failure here: the alternative is a beat that
    looks annotated and shows the wrong animal.
    """
    if kind != "species":
        return None
    parts = [p.strip() for p in raw.split("|")] if raw else []
    if not parts or not parts[0]:
        return None
    subject = parts[0].strip().lower().replace(" ", "_").replace("-", "_")
    args = {"subject": subject,
            "label": parts[1] if len(parts) > 1 else "",
            "note": parts[2] if len(parts) > 2 else ""}
    try:
        if subject in SP.UNILLUSTRATABLE or not available(subject):
            return None
    except Exception:
        return None
    return ("species_image", args)


# --------------------------------------------------------------- the heuristic
#
# PROPOSED, not installed. See the handoff note.
#
# For an undirected paragraph: if the beat's own text names exactly one covered
# subject (matching SUBJECTS[...]["terms"] on a word boundary), and that subject
# has not been shown in the last NO_REPEAT beats, the beat MAY become a
# species_image with `label` set to the matched surface form -- the narration's
# own word, verbatim, so rule 1 holds by construction.
#
# "Exactly one" is deliberate. Episode 01 has the sentence "A barreleye,
# anglerfish, siphonophore, sea cucumber, and deep octopus can occupy the same
# broad world" -- five subjects in one breath, and any single picture there
# would be arbitrary. That sentence should stay a text beat.

NO_REPEAT = 4


def _corrects_itself(subject: str) -> bool:
    """True when EVERY verified record for `subject` states its own limits on frame."""
    recs = index()["_by_subject"].get(subject) or []
    return bool(recs) and all(r.get("standing_note") for r in recs)


def match_subjects(text: str) -> list[tuple[str, str]]:
    """[(subject_key, the surface form the text actually used)], deduped.

    Two rules keep this from producing exactly the substitution the index exists
    to forbid, and both were found by the guard rather than by reading:

    LONGEST TERM WINS. "colossal squid" and "giant squid" both contain "squid",
    which is `deep_squid`'s own term. Matched naively, the sentence "Colossal
    squid are the heaviest known invertebrates" matched deep_squid and would
    have put a NOAA photograph of a Dana octopus squid under the words colossal
    squid. So terms are tried longest first and a shorter term is refused if its
    match falls inside a span a longer one has already claimed.

    AN UNILLUSTRATABLE SUBJECT SILENCES THE WHOLE SENTENCE. If the text names
    the colossal squid, the yeti crab, a whale fall or Osedax, this returns
    nothing at all -- not "nothing for that subject", nothing for the sentence.
    A sentence about the colossal squid that happens to mention a sperm whale
    must not become a picture of a sperm whale while the narrator says colossal
    squid.
    """
    import re as _re
    terms = []
    for key, meta in SP.SUBJECTS.items():
        for term in meta["terms"]:
            terms.append((len(term), term, key))
    terms.sort(reverse=True)

    claimed: list[tuple[int, int]] = []
    hits, seen = [], set()
    for _, term, key in terms:
        for m in _re.finditer(rf"\b{_re.escape(term)}(?:es|s)?\b", text, _re.I):
            if any(m.start() >= a and m.end() <= b for a, b in claimed):
                continue                       # a longer term already owns this span
            claimed.append((m.start(), m.end()))
            if key in SP.UNILLUSTRATABLE:
                near = SP.UNILLUSTRATABLE[key].get("nearest")
                if near and _corrects_itself(near):
                    # The one sanctioned stand-in, and only where every record
                    # under `near` carries a standing_note -- so the frame says
                    # on screen which animal this actually is and that it is not
                    # the record-holder the narration is talking about. If any
                    # record loses its note this stops being allowed, silently
                    # and immediately, which is the point.
                    if near not in seen:
                        seen.add(near)
                        hits.append((near, m.group(0)))
                    break
                return []                      # the sentence gets no picture at all
            if key not in seen:
                seen.add(key)
                hits.append((key, m.group(0)))
            break
    return hits


def heuristic_beat(text: str, recent: list[str]) -> dict | None:
    """Args for a species_image beat, or None to leave the beat alone."""
    hits = [h for h in match_subjects(text) if available(h[0])]
    if len(hits) != 1:
        return None
    key, surface = hits[0]
    if key in recent[-NO_REPEAT:]:
        return None
    return {"subject": key, "label": surface}


# ------------------------------------------------------------------ install

_installed = False


def install(planner=None) -> bool:
    """Graft the renderer onto `segments` and the directive onto the planner.

    Idempotent. Grafting the RENDERER onto the segments module rather than
    asking assemble.py to look in a fourth place means the assemble-side wiring
    is a bare import and nothing else -- see the handoff note.
    """
    global _installed
    try:
        import segments as _S
        _S.species_image = species_image
    except Exception:
        pass

    if planner is None:
        try:
            import planner as planner  # noqa: PLW0127
        except ImportError:
            _installed = True
            return False
    if getattr(planner, "_species_installed", False):
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
        return parse_species_directive(m.group(1).lower(), m.group(2))

    parse_directive.__doc__ = base.__doc__
    planner.parse_directive = parse_directive
    planner._species_installed = True

    for attr in ("INFO", "INFORMATIONAL"):
        cur = getattr(planner, attr, None)
        if isinstance(cur, (set, frozenset)):
            setattr(planner, attr, set(cur) | set(SEGMENTS))
    _installed = True
    return True


try:
    if "planner" in sys.modules:
        install(sys.modules["planner"])
    else:
        install()
except Exception:                                # never break a render on wiring
    pass


# ---------------------------------------------------------------------- handoff
#
# planner.py and assemble.py are owned elsewhere while narration is generating,
# and the audio-to-plan beat count must stay exact. Two one-line edits make this
# pack automatic and NEITHER is applied here:
#
#   planner.py   (beside the segments_ext2 graft):
#       import segments_species as _sp; _sp.install(sys.modules[__name__])
#
#   assemble.py  (beside `import segments_ext2 as SX2`):
#       import segments_species                      # grafts onto `segments`
#
# The assemble edit needs no change to seg_fn, because install() puts
# `species_image` on the `segments` module that seg_fn already checks first.
#
# BEAT COUNT: neither edit can change it. planner.parse() strips directive lines
# before it splits prose into beats, and it does so with the DIRECTIVE regex,
# which already matches `{{species: ...}}` today -- an unparsed directive line is
# still removed from the prose. So a script carrying {{species}} directives
# produces exactly the same number of beats before and after the graft. What
# changes is one field, `segment`, on beats that already exist.

if __name__ == "__main__":
    man = index()
    print(f"species index: {man['_verified']} assets verified, "
          f"{len(man['_by_subject'])} subjects covered")
    for k in sorted(man["_by_subject"]):
        recs = man["_by_subject"][k]
        print(f"  {k:16} {len(recs)}  " +
              ", ".join(f"{r['credit_line']} ({r['depicts']})" for r in recs[:3]))
