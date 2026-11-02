"""The drawn card: an episode with no licensable photo is never held.

    python visuals/drawn_card.py <slug> <out.jpg>      # draw one (1280x720)

OWNER RULING, 2 Nov 2026 ("Yes, drawn card"): when research/subject_photo.py
has searched MAX_TRIES nights and found no photo that passes the licence check,
the episode's one-question picture is a DRAWN CARD instead of a stop routed to
a person. It is:

  * generated here, with PIL only - no image model, no AI, nothing paid;
  * the channel's own colours (visuals/design.py: INK/DEEP/MID/CYAN/AMBER);
  * a plain SCHEMATIC of the subject - a depth line, sediment layers, galaxy
    dots, a generic deep-sea silhouette - flat lines and dots, plainly a
    drawing and never photoreal, labelled "ILLUSTRATION";
  * recorded in channel/imagery/subject_photos.json with source "drawn card",
    so the thumbnail and the Short's opening second (visuals/question_card.py)
    use it exactly as they use a photo, the question drawn over it.

The motif is chosen from the episode's own subject words (MOTIFS); an episode
matching none gets the plain "rings" motif. Guarded by
loop/tests/test_drawn_card.py.
"""
from __future__ import annotations

import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw                            # noqa: E402

SOURCE = "drawn card"
LICENCE = "Own work: drawn in-repo by visuals/drawn_card.py (no image model)"
CREDIT = "ILLUSTRATION — DRAWN BY HOW WE KNOW"
W, H = 1600, 1600            # square master; question_card crops it to 16:9 or 9:16

# Channel colours, fixed here (visuals/design.py's deep-sea palette) so a card
# never depends on HWK_DOMAIN at import.
INK, DEEP, MID = (6, 14, 28), (10, 32, 58), (22, 70, 110)
CYAN, AMBER, MUTED = (110, 200, 220), (240, 180, 90), (150, 170, 190)

# subject word -> motif, first match wins
MOTIFS = [
    ("depth", ("challenger", "trench", "deep", "depth", "dive", "submersible",
               "bathyscaphe", "reach", "zone", "midnight", "ocean")),
    ("layers", ("old", "age", "sediment", "layer", "rock", "fossil", "core",
                "dating", "date", "years")),
    ("galaxy", ("galaxy", "galaxies", "star", "stars", "universe", "space")),
    ("creature", ("creature", "creatures", "creepy", "creepers", "fish", "anglerfish",
                  "monster", "animal", "animals")),
]


def motif_for(words: list[str]) -> str:
    ws = {w.lower() for w in words}
    for name, keys in MOTIFS:
        if ws & set(keys):
            return name
    return "rings"


def _bg(d: ImageDraw.ImageDraw) -> None:
    for y in range(H):                                    # flat two-tone ramp
        t = y / H
        c = tuple(int(DEEP[i] * (1 - t) + INK[i] * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)


def _depth(d) -> None:
    """A depth line with ticks, a vehicle on it (float above, sphere below),
    all inside the centre band both crops keep (y 380-1220, x 400-1200)."""
    x = W // 2 - 220
    d.line([(x, 380), (x, 1220)], fill=CYAN, width=6)
    for i in range(6):
        y = 380 + i * 168
        d.line([(x - 40, y), (x + 40, y)], fill=CYAN, width=6)
    vx, vy = W // 2 + 120, 760
    d.rounded_rectangle([vx - 230, vy - 150, vx + 230, vy - 40], radius=50, outline=AMBER, width=10)
    d.line([(vx, vy - 40), (vx, vy + 10)], fill=AMBER, width=10)
    d.ellipse([vx - 80, vy + 10, vx + 80, vy + 170], outline=AMBER, width=10)
    d.ellipse([vx - 18, vy + 72, vx + 18, vy + 108], fill=CYAN)
    d.line([(x, vy + 90), (vx - 80, vy + 90)], fill=MUTED, width=3)
    d.rectangle([W // 2 - 420, 1180, W // 2 + 420, 1220], fill=MID)


def _layers(d) -> None:
    rnd = random.Random(7)
    y, cols = 200, [MID, DEEP, (60, 90, 110), (90, 80, 60), MID, (50, 60, 80)]
    i = 0
    while y < H - 150:
        h = rnd.randint(70, 180)
        wob = [(x, y + int(12 * math.sin(x / 140 + i))) for x in range(0, W + 40, 40)]
        d.polygon(wob + [(W, y + h), (0, y + h)], fill=cols[i % len(cols)])
        d.line(wob, fill=MUTED, width=3)
        y += h
        i += 1
    d.rectangle([W // 2 - 60, 160, W // 2 + 60, H - 150], outline=AMBER, width=8)   # a core


def _galaxy(d) -> None:
    rnd = random.Random(11)
    cx, cy = W // 2, int(H * 0.45)
    for arm in range(2):
        for k in range(700):
            t = k / 700 * 4.2
            r = 40 + t * 150
            a = t + arm * math.pi + rnd.uniform(-0.25, 0.25)
            x = cx + r * math.cos(a) + rnd.gauss(0, 14)
            y = cy + 0.55 * r * math.sin(a) + rnd.gauss(0, 10)
            s = rnd.choice((2, 3, 4))
            d.ellipse([x - s, y - s, x + s, y + s], fill=CYAN if k % 5 else AMBER)
    d.ellipse([cx - 36, cy - 26, cx + 36, cy + 26], fill=AMBER)
    for _ in range(140):
        x, y = rnd.randrange(W), rnd.randrange(H)
        d.point((x, y), fill=MUTED)


def _creature(d) -> None:
    cx, cy = W // 2, int(H * 0.47)
    # a generic fish outline: oval body, tail, a big mouth line, a lure
    d.ellipse([cx - 360, cy - 200, cx + 300, cy + 200], outline=CYAN, width=12)
    d.polygon([(cx + 290, cy), (cx + 520, cy - 180), (cx + 520, cy + 180)], outline=CYAN, width=12)
    d.line([(cx - 360, cy + 10), (cx - 120, cy + 70)], fill=CYAN, width=12)
    for k in range(6):
        x = cx - 330 + k * 40
        d.line([(x, cy + 18 + k * 9), (x + 12, cy + 60 + k * 9)], fill=MUTED, width=6)
    d.ellipse([cx - 230, cy - 90, cx - 170, cy - 30], outline=CYAN, width=10)
    d.arc([cx - 420, cy - 420, cx - 80, cy - 120], 200, 330, fill=CYAN, width=8)
    d.ellipse([cx - 455, cy - 330, cx - 395, cy - 270], fill=AMBER)


def _rings(d) -> None:
    for r in range(80, 700, 90):
        d.ellipse([W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r], outline=MID, width=6)


def draw(words: list[str]) -> tuple[Image.Image, str]:
    """(the drawn master, motif name). Deterministic for the same words."""
    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)
    _bg(d)
    m = motif_for(words)
    {"depth": _depth, "layers": _layers, "galaxy": _galaxy,
     "creature": _creature, "rings": _rings}[m](d)
    # "ILLUSTRATION" is in the credit drawn over every crop (CREDIT)
    return im, m


def write(slug: str, words: list[str], out_path: str) -> dict:
    """Draw the card for `slug` to out_path (JPEG); the record fields."""
    import hashlib                                          # noqa: PLC0415
    im, m = draw(words)
    im.save(out_path, "JPEG", quality=92)
    data = open(out_path, "rb").read()
    return {"source": SOURCE, "motif": m, "licence": LICENCE, "credit_line": CREDIT,
            "depicts": "drawing", "treatment": "drawn", "sha256": hashlib.sha256(data).hexdigest(),
            "width": W, "height": H, "item_url": "visuals/drawn_card.py"}


if __name__ == "__main__":
    import re                                               # noqa: PLC0415
    slug, out = sys.argv[1], sys.argv[2]
    print(write(slug, re.split(r"[-\s]+", slug), out))
