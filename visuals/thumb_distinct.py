"""Thumbnail variants must be genuinely different: a perceptual-hash gate.

Owner, 13 Oct 2026, on the food round-2 thumbnails: two of the three were the
same picture. A variant test (A/B/C) that offers the same image twice tests
nothing. visuals/thumb_contract.build_variants calls check() before a set is
moved into place, and thumb_contract.verify() (validator V48) re-runs it on
every committed set, so a near-duplicate set FAILS.

  * PICTURE: every pair of variants differs by a pHash Hamming distance of at
    least MIN_PHASH_DISTANCE, measured on the graded picture BEFORE any type is
    drawn (64-bit DCT pHash) - one picture under two captions is one picture.
  * TEXT: the three texts are not all identical.

THRESHOLD, measured 2026-10-13 on the pictures themselves (before type):
  * the food round-2 set the owner rejected: A and B the same AI image, crops
    18 px apart - distance 6 (and 0 on the pictures that were literally reused);
  * 14 of the 24 committed sets had A and C (or A and B) as ONE picture under
    two captions - distance 0;
  * re-encoding a JPEG at quality 80 - distance 0-2;
  * the repaired sets: different crops of one image 10-38, different images 24-38.
  10 sits above every duplicate and all encoding noise, at the floor of crops a
  person reads as different pictures; it is also pHash's conventional
  "different image" boundary (<= ~8 is the same image).

Kept in its own module so the shared builder (visuals/thumb_contract.py) only calls it:
build_variants picks B and C crops that clear it, and verify() re-runs it.
"""
from __future__ import annotations

import itertools

import numpy as np
from PIL import Image

MIN_PHASH_DISTANCE = 10


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    m[0] *= 1 / np.sqrt(2)
    return m * np.sqrt(2 / n)


_D32 = _dct_matrix(32)


def phash(im: Image.Image | str) -> int:
    """64-bit perceptual hash: 32x32 grey, 2-D DCT, top-left 8x8 above its median."""
    if isinstance(im, str):
        with Image.open(im) as f:
            im = f.convert("L").resize((32, 32), Image.LANCZOS)
    else:
        im = im.convert("L").resize((32, 32), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float64)
    d = _D32 @ a @ _D32.T
    low = d[:8, :8].flatten()
    bits = low > np.median(low[1:])
    return int("".join("1" if b else "0" for b in bits), 2)


def distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def check(images: dict[str, Image.Image | str], texts: dict[str, str]) -> list[str]:
    """[] when every pair of variants differs; named problems otherwise."""
    p: list[str] = []
    hs = {k: phash(v) for k, v in images.items()}
    for a, b in itertools.combinations(sorted(hs), 2):
        d = distance(hs[a], hs[b])
        if d < MIN_PHASH_DISTANCE:
            p.append(f"variants {a} and {b} are near-identical (pHash distance {d}, "
                     f"needs >= {MIN_PHASH_DISTANCE}): a variant test needs different pictures")
    t = [" ".join((texts.get(k) or "").upper().split()) for k in sorted(texts)]
    if len(t) >= 2 and len(set(t)) == 1:
        p.append(f"all variants carry the same text {t[0]!r}: at least one must differ")
    return p
