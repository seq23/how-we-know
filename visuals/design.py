"""Deep Sea visual design system. All values deliberate; change here, not in segments."""
W, H, FPS = 1920, 1080, 30

# Palette — carried forward from the repo's existing SVG stills so thumbnails and
# video share one identity.
INK        = (2, 7, 13)        # near-black, the abyss
DEEP       = (4, 17, 31)       # deep water
MID        = (10, 54, 85)      # upper water column
CYAN       = (123, 216, 232)   # primary accent — light, bioluminescence
PALE       = (184, 242, 234)   # secondary accent
AMBER      = (243, 182, 107)   # warm accent, used sparingly for emphasis
TEXT       = (234, 248, 251)
MUTED      = (165, 192, 202)

F_DISPLAY  = "/System/Library/Fonts/Supplemental/Georgia.ttf"
F_LABEL    = "/System/Library/Fonts/Helvetica.ttc"
F_MONO     = "/System/Library/Fonts/Menlo.ttc"

# Ocean zones: name, top metres, bottom metres
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
    """Water colour at a given depth in metres. Light dies with depth."""
    if m < 200:   return mix(MID, DEEP, m / 200)
    if m < 1000:  return mix(DEEP, INK, (m - 200) / 800)
    return INK
