"""The visual design system for the ACTIVE domain. All values deliberate;
change here, not in segments.

WHY THIS FILE STOPPED BEING "Deep Sea visual design system"
-----------------------------------------------------------
It hardcoded the ocean palette and the ocean depth scale as bare module
constants, imported wildcard-style (`from design import *`) by every segment
renderer. `visuals/domains.py` and `visuals/segments_materials.py` were then
written to give materials-and-manufacturing its own palette and its own
structural device — and neither could be reached, because nothing ever
selected a domain. `segments_materials` failed at import with
`cannot import name 'DEVICE' from 'design'`, so the thermal renderers existed
and nothing invoked them: the exact defect class this repo keeps producing.

This module now RESOLVES a domain at import time and re-exports that domain's
palette under the same eight names every renderer already uses. A segment
function never asks which domain it is in; it draws with CYAN and gets the
ocean's bioluminescent cyan or the forge orange, whichever domain is active.

SELECTING A DOMAIN
------------------
`HWK_DOMAIN`, read once at import. It defaults to `deep-sea-ocean-science`,
so every existing call site that never sets it imports exactly the values it
always has — deep sea's rendered output does not move by one value, and
`_assert_deep_sea_unmoved()` below proves that rather than asserting it in a
comment. An undeclared domain raises here, at import, before a single frame
can be drawn for a domain nobody declared a palette for.

  HWK_DOMAIN=materials-and-manufacturing python visuals/assemble.py ...
"""
import os

import domains

W, H, FPS = 1920, 1080, 30

DOMAIN = os.environ.get("HWK_DOMAIN", "deep-sea-ocean-science").strip() \
         or "deep-sea-ocean-science"

# Raises for a domain with no declared palette. At IMPORT time, deliberately:
# a domain that reaches a renderer without a palette would otherwise draw a
# whole episode in whatever the previous domain's colours happened to be.
domains.require_declared(DOMAIN)

_P = domains.palette(DOMAIN)

# The eight palette roles. Same names for every domain, so no renderer needs
# to know which one is active — see visuals/domains.py for what each role
# means and why materials' values are what they are.
INK   = _P["INK"]
DEEP  = _P["DEEP"]
MID   = _P["MID"]
CYAN  = _P["CYAN"]
PALE  = _P["PALE"]
AMBER = _P["AMBER"]
TEXT  = _P["TEXT"]
MUTED = _P["MUTED"]

F_DISPLAY  = "/System/Library/Fonts/Supplemental/Georgia.ttf"
F_LABEL    = "/System/Library/Fonts/Helvetica.ttc"
F_MONO     = "/System/Library/Fonts/Menlo.ttc"

# The active domain's structural device: axis, unit, title, max and bands.
# `segments_materials` imports DEVICE from here; deep sea's own renderers use
# ZONES below, which is DEVICE["bands"] under its historical name.
DEVICE = domains.device(DOMAIN)

# Ocean zones: name, top metres, bottom metres. Kept as a module constant
# under its original name because visuals/segments.py, thumbs.py and shorts.py
# all import ZONES directly; for a non-ocean domain this is that domain's own
# bands on its own axis, which is what every one of those call sites actually
# wants.
ZONES = [tuple(b) for b in DEVICE["bands"]]

def ease(t):
    """Smooth in/out. Motion should never start or stop abruptly."""
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))

def depth_color(m):
    """Water colour at a given depth in metres. Light dies with depth.

    Deep sea's own function, unchanged and NOT parameterised to "also do"
    materials. Heat is emitted as its axis rises where light is subtracted as
    depth rises; one function serving both would be the ocean device
    recoloured, which visuals/domains.py exists to prevent.
    `segments_materials.temperature_color` is the materials counterpart.
    """
    if m < 200:   return mix(MID, DEEP, m / 200)
    if m < 1000:  return mix(DEEP, INK, (m - 200) / 800)
    return INK


def _assert_deep_sea_unmoved() -> None:
    """Deep sea's palette is byte-identical to the pre-domain constants.

    Seventeen episodes are already rendered against these exact values. A
    refactor that shifted one channel by one would produce a channel whose
    back catalogue no longer matches its new uploads, and nothing downstream
    would notice — the frames would still render. So the original literals
    are kept here, in the file that used to hold them, and compared.
    """
    original = {
        "INK": (2, 7, 13), "DEEP": (4, 17, 31), "MID": (10, 54, 85),
        "CYAN": (123, 216, 232), "PALE": (184, 242, 234),
        "AMBER": (243, 182, 107), "TEXT": (234, 248, 251),
        "MUTED": (165, 192, 202),
    }
    live = domains.palette("deep-sea-ocean-science")
    moved = {k: (v, live.get(k)) for k, v in original.items() if live.get(k) != v}
    if moved:
        raise AssertionError(
            f"deep sea's palette moved during the domain refactor: {moved}. "
            f"Seventeen rendered episodes use the original values.")
    zones = [tuple(b) for b in domains.device("deep-sea-ocean-science")["bands"]]
    if zones != [("SUNLIGHT", 0, 200), ("TWILIGHT", 200, 1000),
                 ("MIDNIGHT", 1000, 4000), ("ABYSSAL", 4000, 6000),
                 ("HADAL", 6000, 11034)]:
        raise AssertionError(f"deep sea's ZONES moved: {zones}")


_assert_deep_sea_unmoved()
