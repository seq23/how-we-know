"""The rendering-side domain registry. ONE place a palette or structural
device may be declared for a domain that publishes video.

Until this file existed, `visuals/design.py` hardcoded the ocean palette and
the Sunlight->Twilight->Midnight->Abyssal->Hadal depth scale as bare module
constants, imported wildcard-style (`from design import *`) into every
segment renderer. That is survivable for one domain and stops being
survivable the moment a second one renders: there was no way to ask "what is
materials-and-manufacturing's palette" because nothing SAID materials had one.

This module is deliberately small. It does not try to make every segment
renderer domain-generic — most of `visuals/segments_ext.py` and
`visuals/segments_ext2.py` already are (they take a title, items and labels
as arguments and draw with whatever `design` exports, never a hardcoded
ocean word). Only the STRUCTURAL DEVICE — the one organising idea a domain
tells its whole visual identity around — needs its own declaration and its
own renderer: `visuals/segments.py`'s `depth_descent`/`zone_column` for deep
sea, `visuals/segments_materials.py`'s `thermal_ascent`/`process_column` for
materials. Neither is touched by the other; deep sea's functions are not
parameterised to "also do" materials; a materials value passed to a
deep-sea-only function must not be silently accepted.

`design.py` selects a domain at IMPORT TIME from the `HWK_DOMAIN` environment
variable, defaulting to `deep-sea-ocean-science` — so every existing call
site that never sets the variable keeps importing exactly the values it
always has, unchanged. That default is what makes deep sea's output
byte-identical: nothing about its numbers moved, only where they are read
from.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Palettes. Eight named colours per domain, same roles for every domain so a
# segment renderer never has to ask which domain it is in:
#   INK    near-black, the darkest ground
#   DEEP   a step up from INK, the common gradient partner
#   MID    the lightest ground colour, used at the "shallow"/"cold" end
#   CYAN   primary accent — the identity colour, used for the widest range of
#          UI (rules, ticks, active state)
#   PALE   secondary accent, softer than CYAN
#   AMBER  warm accent, used sparingly for emphasis (a single rule, a single
#          highlighted value)
#   TEXT   body text on a dark ground
#   MUTED  secondary/caption text
# ---------------------------------------------------------------------------

PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "deep-sea-ocean-science": {
        # Carried forward verbatim from the original visuals/design.py so
        # this domain's rendered output does not move by one value.
        "INK":   (2, 7, 13),
        "DEEP":  (4, 17, 31),
        "MID":   (10, 54, 85),
        "CYAN":  (123, 216, 232),
        "PALE":  (184, 242, 234),
        "AMBER": (243, 182, 107),
        "TEXT":  (234, 248, 251),
        "MUTED": (165, 192, 202),
    },
    "materials-and-manufacturing": {
        # Grounded in the domain's own structural device (see DEVICES below):
        # blackbody incandescence, the real colour sequence a metal actually
        # emits as it heats — cold graphite through iron, ember red, forge
        # orange, temper straw, to arc-plasma white-blue. Not the ocean
        # palette recoloured: the ocean's device is "light dies with depth"
        # (colour is subtracted as the axis increases); materials' device is
        # the physical inverse, "colour is emitted by heat" (colour is
        # ADDED as the axis increases). Different axis, different physics,
        # different palette role for every stop.
        "INK":   (15, 13, 12),      # graphite — cold, unheated metal
        "DEEP":  (46, 39, 35),      # worked iron at rest
        "MID":   (110, 46, 27),     # ember — first visible heat, ~600 C
        "CYAN":  (235, 122, 41),    # forge orange — primary accent, ~1000 C
        "PALE":  (247, 199, 118),   # temper straw — secondary accent
        "AMBER": (156, 212, 255),   # arc/plasma blue-white, used sparingly
                                    # for the single hottest reading on a card
        "TEXT":  (250, 244, 236),
        "MUTED": (189, 171, 158),
    },
}


# ---------------------------------------------------------------------------
# Structural devices. Each domain organises its cards around ONE continuous
# physical axis with real, named thresholds — never invented, always a
# convention drawn from the domain's own literature.
#
# "bands" is the domain's equivalent of the ocean's ZONES: (name, low, high)
# on the domain's own axis. "stops" is the colour ramp along that axis, used
# by `segments_materials.thermal_ascent`/`process_column` the same way
# `design.depth_color` walks the ocean's own MID->DEEP->INK stops.
# ---------------------------------------------------------------------------

DEVICES: dict[str, dict] = {
    "deep-sea-ocean-science": {
        "axis": "depth",
        "unit": "m",
        "unit_label": "METRES",
        "title": "THE WATER COLUMN",
        "max": 11034,
        "default_descent_label": "CHALLENGER DEEP",
        "bands": [
            ("SUNLIGHT",  0,     200),
            ("TWILIGHT",  200,   1000),
            ("MIDNIGHT",  1000,  4000),
            ("ABYSSAL",   4000,  6000),
            ("HADAL",     6000,  11034),
        ],
        # Reproduced here for reference only — design.depth_color is the
        # implementation actually called, and is not rebuilt from this list,
        # so a change here cannot silently move deep sea's rendered colour.
        "source_note": "NOAA/GEBCO depth-zone convention, unchanged.",
    },
    "materials-and-manufacturing": {
        "axis": "temperature",
        "unit": "C",
        "unit_label": "DEGREES C",
        "title": "THE THERMAL SCALE",
        "max": 6000,
        "default_ascent_label": "TUNGSTEN ARC",
        # Real engineering-material thresholds, ASM Handbook / NIST scale
        # conventions — the same evidentiary bar as the ocean's own NOAA
        # depth zones, cited per-episode in narration and ## Sources, never
        # asserted by the visual alone:
        #   AMBIENT  service temperature for most polymers and coatings
        #   TEMPER   steel tempering / stress-relief range (ASM Handbook v4)
        #   FORGE    hot-working and annealing range for structural steel
        #   MELT     melting range spanning common engineering metals
        #            (aluminium ~660 C, steel ~1370-1510 C) through
        #            refractory ceramics
        #   PLASMA   arc-welding plasma column / atmospheric-reentry heating
        "bands": [
            ("AMBIENT", 0,    200),
            ("TEMPER",  200,  600),
            ("FORGE",   600,  1300),
            ("MELT",    1300, 2500),
            ("PLASMA",  2500, 6000),
        ],
        "source_note": ("ASM Handbook Vol. 4 (heat treating) and NIST "
                        "melting-point references; band edges are rounded "
                        "engineering convention, not a claim any single "
                        "material sits exactly there — the per-episode "
                        "figure always comes from that episode's own "
                        "narration and ## Sources."),
    },
}


# ---------------------------------------------------------------------------
# Source allowlists live in loop/domain_sources.py, not here — they gate
# NARRATION and its ## Sources block, which loop/author.py and
# loop/validate.py both need, and neither imports visuals/. Duplicating the
# list in both trees is exactly the "two components, no link" defect this
# refactor exists to remove, so there is one file, imported by both sides of
# the pipeline that need it. `require_declared()` below still checks that a
# source allowlist exists for every domain declared here, by delegating to
# that module rather than keeping a second copy.
# ---------------------------------------------------------------------------


def known() -> list[str]:
    return sorted(PALETTES)


def has_palette(domain: str) -> bool:
    return domain in PALETTES


def has_device(domain: str) -> bool:
    return domain in DEVICES


def palette(domain: str) -> dict[str, tuple[int, int, int]]:
    if domain not in PALETTES:
        raise KeyError(
            f"{domain!r} has no palette in visuals/domains.py. Every domain "
            f"that can render a frame needs one; {len(PALETTES)} declared: "
            f"{known()}.")
    return PALETTES[domain]


def device(domain: str) -> dict:
    if domain not in DEVICES:
        raise KeyError(
            f"{domain!r} has no structural device in visuals/domains.py. "
            f"Every domain that can render a frame needs one; {len(DEVICES)} "
            f"declared: {sorted(DEVICES)}.")
    return DEVICES[domain]


def require_declared(domain: str) -> None:
    """Guard: this domain may render a frame. Raises, never warns.

    Checked by `visuals/design.py` at import time (so nothing can render a
    single frame for an undeclared domain) and by the domain-abstraction
    validator (so a missing source allowlist is caught even though this
    module cannot see loop/domain_sources.py without importing across the
    tree boundary, which it deliberately does not do here).
    """
    palette(domain)
    device(domain)
