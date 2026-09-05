"""Visual design system. All values deliberate; change here, not in segments.

DOMAIN-AWARE, 2026-09-03. This used to hardcode the deep-sea ocean palette
and the Sunlight->Twilight->Midnight->Abyssal->Hadal depth scale as bare
module constants — the file's own original docstring called it "Deep Sea
visual design system." Twelve-odd modules `from design import *`, so every
one of them silently assumed there was only ever one subject.

The palette and structural-device metadata now come from `visuals/domains.py`
for whichever domain `HWK_DOMAIN` names (default `deep-sea-ocean-science`),
but every name this module exported before still exists, with the SAME
values for the default domain — nothing reads differently for deep sea
unless something sets the environment variable. `ease`, `lerp`, `mix` and
`depth_color` keep their ORIGINAL bodies verbatim, not rebuilt from a generic
formula, specifically so deep sea's rendered output cannot move by one pixel
as a side effect of this refactor. See `visuals/segments_materials.py` for
materials-and-manufacturing's own structural-device renderer, which is a
separate module rather than a parameterised version of `depth_descent`/
`zone_column` for the same reason: two functions that cannot be reached by
the wrong domain's data beat one function trusted to branch correctly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# LOADED BY PATH, NOT BY NAME. There are two modules called `domains` in this
# repo - visuals/domains.py (palettes and structural devices) and
# loop/domains.py (taxonomy, slot allocation, queue depth) - and a bare
# `import domains` resolves to whichever tree happens to be first on sys.path,
# or to whichever was imported FIRST, because sys.modules caches by name. The
# sys.path.insert above is not enough: once any loop/ module has been imported,
# sys.modules["domains"] is already loop's, and this file silently binds to the
# wrong one. The symptom is not a clean ImportError - it is
# `AttributeError: module 'domains' has no attribute 'require_declared'`
# raised from inside visuals/footage.py, several imports away from the cause,
# and it appears only when a test touches the loop tree before the visuals one.
# Loading the sibling file explicitly makes the two unable to collide.
import importlib.util as _ilu  # noqa: E402

_dom_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "domains.py")
_spec = _ilu.spec_from_file_location("visuals_domains", _dom_path)
_domains = _ilu.module_from_spec(_spec)
sys.modules.setdefault("visuals_domains", _domains)
_spec.loader.exec_module(_domains)

W, H, FPS = 1920, 1080, 30

DOMAIN = os.environ.get("HWK_DOMAIN", "deep-sea-ocean-science")
_domains.require_declared(DOMAIN)     # hard-fails an undeclared domain here,
                                      # at import time, before any frame is
                                      # ever drawn — see visuals/CONTRACT.md
                                      # and the guard-the-abstraction test.

_PAL = _domains.palette(DOMAIN)
DEVICE = _domains.device(DOMAIN)

# Palette — for deep-sea-ocean-science these are the exact original values
# ("carried forward from the repo's existing SVG stills so thumbnails and
# video share one identity"); for any other domain they are that domain's
# own declaration in visuals/domains.py.
INK   = _PAL["INK"]
DEEP  = _PAL["DEEP"]
MID   = _PAL["MID"]
CYAN  = _PAL["CYAN"]
PALE  = _PAL["PALE"]
AMBER = _PAL["AMBER"]
TEXT  = _PAL["TEXT"]
MUTED = _PAL["MUTED"]

# Type is shared across domains deliberately: this channel's identity is one
# typographic voice narrating different subjects, not a different font per
# subject. "Type that survives downscaling" is a size/weight discipline
# inside each segment renderer, not a per-domain font swap.
# FONT PATHS ARE RESOLVED, NOT HARDCODED, and the reason is that this repo
# renders on two machines. These were three absolute macOS paths, which is
# correct on the Mac that produces every master and wrong everywhere else:
# on the Ubuntu runner `ImageFont.truetype` raises "cannot open resource", and
# because tests/test_directive_truth.py RENDERS one frame per directive to
# prove it is not inert, V1 directive-truth could only ever pass on a Mac.
# That is the "a guard that cannot reach what it governs" defect, and it is
# what kept `loop · Mon 06:00` red.
#
# The macOS path stays FIRST in every list, so on the Mac each of these
# resolves to exactly the file it always did and no rendered frame moves by a
# pixel. The Linux entries only matter where the macOS one is absent.
def _first_font(*candidates: str) -> str:
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "none of these font files exist on this machine: "
        + ", ".join(candidates)
        + ". A renderer with no font does not degrade quietly - PIL's default "
          "bitmap face ignores the requested size, so every fitted line would "
          "silently come out the wrong length.")


F_DISPLAY = _first_font(
    "/System/Library/Fonts/Supplemental/Georgia.ttf",            # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",          # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
)
F_LABEL = _first_font(
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
F_MONO = _first_font(
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)

# Ocean zones: name, top metres, bottom metres. Deep-sea-only, unchanged —
# consumed exclusively by visuals/segments.py's zone_column/depth_descent,
# which remain ocean-only functions. A materials plan never emits a
# zone_column beat, so this constant being "wrong" for materials is moot: it
# is never read for materials. See DEVICE above for the domain-generic
# equivalent (title/unit/bands/max), which visuals/segments_materials.py
# reads instead.
ZONES = [
    ("SUNLIGHT",  0,     200),
    ("TWILIGHT",  200,   1000),
    ("MIDNIGHT",  1000,  4000),
    ("ABYSSAL",   4000,  6000),
    ("HADAL",     6000,  11034),
]

def ease(t):
    """Smooth in/out. Motion should never start or stop abruptly."""
    return t * t * (3 - 2 * t)

def lerp(a, b, t):
    return a + (b - a) * t

def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))

def depth_color(m):
    """Water colour at a given depth in metres. Light dies with depth.

    Deep-sea-only, body unchanged from the original file. Not generalised
    into a shared "scale colour" helper: visuals/segments_materials.py has
    its own temperature_color with its own stops, and the two are not meant
    to be interchangeable — that would be the recolour this refactor was
    explicitly told not to do.
    """
    if m < 200:   return mix(MID, DEEP, m / 200)
    if m < 1000:  return mix(DEEP, INK, (m - 200) / 800)
    return INK
