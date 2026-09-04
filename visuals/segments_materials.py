"""Materials-and-manufacturing's structural-device renderers.

The materials equivalent of `visuals/segments.py`'s `depth_descent` and
`zone_column` — NOT those functions made generic. Ocean depth's device is
"light dies with depth": colour is subtracted as the axis increases. A metal
heating is the physical inverse: colour is EMITTED as the axis increases
(blackbody incandescence — a real, cited phenomenon, not a decorative
choice). Sharing one parameterised function across an additive and a
subtractive colour model would have produced exactly the "ocean device
recoloured" outcome this domain was told to avoid, so this is a separate
module with its own two functions instead, built from `visuals/domains.py`'s
materials DEVICE (title/unit/max/bands) rather than from deep sea's ZONES.

`visuals/assemble.py` discovers these the same way it discovers
`segments_ext`/`segments_ext2`: an optional import, looked up by function
name in `seg_fn()`. A materials plan references `thermal_ascent` or
`process_column` by name in its beat's `"segment"` field; a deep-sea plan
never does, because deep-sea scripts never emit a `{{thermal}}` or
`{{stages}}` directive (see visuals/planner.py, visuals/CONTRACT.md).
"""
from design import (AMBER, CYAN, DEVICE, F_DISPLAY, F_LABEL, F_MONO,
                    INK, MID, MUTED, PALE, TEXT, W, H, ease, mix)
from segments import _center, _grad, _snow, font  # shared drawing helpers —
                                                   # domain-agnostic already


# Blackbody-inspired stops along the materials thermal axis: cold graphite,
# through the palette's own MID (ember) / CYAN (forge orange) / PALE (temper
# straw) accents, to AMBER (arc/plasma white-blue) at the top. Uses the
# ACTIVE domain's own palette constants (imported above), so this stays
# correct even if visuals/domains.py's materials palette is retuned later —
# nothing here hardcodes an RGB triple a second time.
_STOPS = [
    (0,    INK),
    (600,  MID),
    (1300, CYAN),
    (2500, PALE),
    (6000, AMBER),
]


def temperature_color(c):
    """Colour at a given temperature in Celsius. Heat is born, not lost."""
    for i in range(len(_STOPS) - 1):
        v0, c0 = _STOPS[i]
        v1, c1 = _STOPS[i + 1]
        if c < v1:
            t = 0.0 if v1 == v0 else max(0.0, (c - v0) / (v1 - v0))
            return mix(c0, c1, min(1.0, t))
    return _STOPS[-1][1]


def thermal_ascent(t, to_temp=None, label=None):
    """Signature shot: a continuous rise through the thermal scale.

    Materials' analogue of depth_descent — an ascent rather than a descent,
    because the axis this domain organises around runs from cold to hot, not
    surface to abyss.
    """
    to_temp = to_temp if to_temp is not None else DEVICE["max"]
    label = label if label is not None else DEVICE.get(
        "default_ascent_label", DEVICE.get("title", ""))
    e = ease(t); cur = to_temp * e
    img = _grad(temperature_color(cur * 0.25), temperature_color(cur))
    from PIL import Image, ImageDraw
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=90, speed=0.5)
    step = 500
    first = int(cur // step) * step
    for i in range(-2, 9):
        c = first - i * step
        if c < 0 or c > to_temp: continue
        y = H * 0.5 + (cur - c) * (H / 3400)
        if -60 < y < H + 60:
            major = c % 1000 == 0
            d.line([(W - 300, y), (W - (250 if major else 275), y)],
                   fill=(*CYAN, 200 if major else 90), width=2 if major else 1)
            if major:
                d.text((W - 245, y - 13), f"{c:,}°C", font=font(F_MONO, 22),
                       fill=(*CYAN, 210))
    d.line([(W - 300, 0), (W - 300, H)], fill=(*CYAN, 45), width=1)
    _center(d, f"{int(cur):,}", font(F_DISPLAY, 150), H * 0.40, (*TEXT, 255))
    _center(d, "DEGREES C", font(F_LABEL, 30), H * 0.40 + 205, (*MUTED, 210),
           spacing=10)
    _center(d, label.upper(), font(F_LABEL, 26), 70, (*CYAN, 190), spacing=7)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def process_column(t, highlight=None):
    """The thermal scale, five bands. Materials' analogue of zone_column —
    compressed axis (sqrt) so the low-temperature bands stay legible, the
    axis labelled with real values so the compression is visible, not
    hidden, exactly as the ocean version discloses its own compression."""
    from PIL import Image, ImageDraw
    bands = DEVICE["bands"]
    axis_max = DEVICE["max"]
    img = _grad(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=70, speed=0.3)
    x0, x1 = W * 0.26, W * 0.52
    top_y, bot_y = 165, H - 165
    hl = (highlight or "").strip().upper() or None

    def ypos(c):
        return top_y + (c / axis_max) ** 0.5 * (bot_y - top_y)

    prev_label_y = -999
    for i, (name, lo, hi) in enumerate(bands):
        yt, yb = ypos(lo), ypos(hi)
        rev = ease(max(0, min(1, t * 4.5 - i * 0.5)))
        if rev <= 0: continue
        h = (yb - yt) * rev
        on = (hl is None) or (hl == name)
        c = temperature_color((lo + hi) / 2)
        fill = mix(c, PALE, 0.16 if on else 0.05)
        d.rectangle([x0, yt, x1, yt + h], fill=(*fill, 255))
        d.line([(x0, yt), (x1, yt)], fill=(*CYAN, 200 if on else 70), width=2)
        if rev > 0.9:
            ly = max(yt + 8, prev_label_y + 62)
            a = 255 if on else 120
            col = CYAN if on else MUTED
            d.line([(x1 + 8, ly + 14), (x1 + 26, ly + 14)], fill=(*col, a), width=2)
            d.text((x1 + 36, ly), name, font=font(F_LABEL, 26), fill=(*col, a))
            d.text((x1 + 36, ly + 30), f"{lo:,}-{hi:,}°C",
                   font=font(F_MONO, 19), fill=(*MUTED, a))
            prev_label_y = ly
    d.line([(x0, top_y), (x0, bot_y)], fill=(*CYAN, 90), width=1)
    _center(d, DEVICE["title"], font(F_LABEL, 26), 72, (*CYAN, 200), spacing=8)
    d.text((x0 - 150, bot_y - 10), f"{axis_max:,}°C", font=font(F_MONO, 19),
           fill=(*MUTED, 150))
    d.text((x0 - 150, top_y - 6), "0°C", font=font(F_MONO, 19), fill=(*MUTED, 150))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


# ---------------------------------------------------------------------------
# Verified public-domain photographs, micrographs and diagrams.
#
# The DRAWING is segments_species.draw_image_beat — one implementation, shared
# between the domains, because the credit line and the medium stamp are the
# part that may not drift. What is materials-specific is only the index it
# resolves against: research/imagery_materials.py's
# channel/imagery/materials.json, whose licence gate is imagery.pd_licence_ok
# (imported, not reimplemented) and whose copyright-assertion screen is
# deliberately NOT imagery.THIRD_PARTY — that list rejects "nasa", "usgs" and
# "university", which for this domain are the reason a work is free rather
# than evidence that it is not.
# ---------------------------------------------------------------------------

import json as _json
import os as _os

_MAT_INDEX = None


class NoMaterialImage(KeyError):
    """No verified public-domain image for this subject. Never substituted."""


def material_index():
    """Load and index the rights-verified materials manifest. Cached."""
    global _MAT_INDEX
    if _MAT_INDEX is not None:
        return _MAT_INDEX
    here = _os.path.dirname(_os.path.abspath(__file__))
    path = _os.path.join(here, "..", "channel", "imagery", "materials.json")
    man = _json.load(open(path))
    by_subject, by_file = {}, {}
    for rec in man["index"]:
        by_subject.setdefault(rec["subject"], []).append(rec)
        by_file[rec["local_file"]] = rec
    _MAT_INDEX = {"_by_subject": by_subject, "_by_file": by_file,
                  "_unillustratable": man.get("subjects_unillustratable", {})}
    return _MAT_INDEX


def material_image(t, subject=None, asset=None, label="", credit="", pick=0,
                   note="", zoom=1.0):
    """One verified public-domain image of the material the narration named.

    Refuses rather than substitutes. A photograph of a blast furnace shown
    while the narration describes a semiconductor cleanroom is a lie told in
    pictures, and it is the failure the whole imagery gate exists to prevent —
    so a subject with no verified image raises here and the drawn treatment
    stands instead.
    """
    import segments_species as _SS                         # noqa: PLC0415

    man = material_index()
    if asset:
        rec = man["_by_file"].get(asset)
        if rec is None:
            raise NoMaterialImage(
                f"materials asset {asset!r} is not in the verified index")
    else:
        if not subject:
            raise NoMaterialImage("material_image needs a subject or an asset")
        if subject in man["_unillustratable"]:
            raise NoMaterialImage(
                f"subject {subject!r} is declared unillustratable: "
                f"{man['_unillustratable'][subject]['why'][:200]}... "
                f"Do not substitute; the drawn treatment stands.")
        cands = man["_by_subject"].get(subject)
        if not cands:
            raise NoMaterialImage(
                f"no verified public-domain image for subject {subject!r}")
        rec = cands[pick % len(cands)]
    return _SS.draw_image_beat(t, rec, label=label or rec.get("label", ""),
                               credit=credit, note=note, zoom=zoom)
