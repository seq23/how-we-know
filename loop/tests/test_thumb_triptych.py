"""The TRIPTYCH thumbnail layout's contract (visuals/thumb_triptych.py, via
thumb_contract.verify, validator V48). Owner design, 13 Oct 2026, for
multi-subject "<Noun>, <Noun>, <Noun>: What's Inside?" videos.

  1. The committed food set (channel/thumbnails/variants/why-bread-rises-
     steak-browns-chocolate-snaps) passes verify(): series title, headline
     <= 2 words at >= 40 % width, subtitle = the subject nouns only, three
     panels each >= 25 %, legible at 320 px, grade + sources re-derived,
     three distinct compositions and pictures.
  2. NEGATIVE, each on a copy of that set: a non-series title; a 3-word
     headline; a subtitle carrying a word that is not a subject noun; two
     variants with one composition; a published file whose headline is
     painted out (pixels and legibility); a panel source swapped for other
     bytes - every one FAILS.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "loop"))
os.environ["LOOP_DRY_RUN"] = "1"

from PIL import Image, ImageDraw                               # noqa: E402

import thumb_contract as T                                     # noqa: E402

SLUG = "why-bread-rises-steak-browns-chocolate-snaps"
fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


src = os.path.join(T.VARIANTS_DIR, SLUG)
rec0 = json.load(open(os.path.join(src, "contract.json")))
check(rec0.get("layout") == "triptych", "the food set is a triptych")
check(T.verify(SLUG) == [], f"the committed triptych passes: {T.verify(SLUG)}")
import thumb_triptych as TT                                    # noqa: E402
ref_slug, ref_name = TT.REFERENCE_SET
ref = json.load(open(os.path.join(T.VARIANTS_DIR, ref_slug, "contract.json")))["variants"][ref_name]
check(ref_slug == SLUG and {k: ref[k] for k in TT.REFERENCE} == TT.REFERENCE,
      f"the owner's pick (F) is the reference composition: {TT.REFERENCE}")


def broken(mutate, files=None) -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        shutil.copytree(src, os.path.join(td, SLUG))
        cp = os.path.join(td, SLUG, "contract.json")
        r = json.load(open(cp))
        mutate(r)
        json.dump(r, open(cp, "w"))
        if files:
            files(os.path.join(td, SLUG))
        return T.verify(SLUG, root=td)


check(bool(broken(lambda r: r.update(title="Why Does Bread Rise?"))), "a non-series title fails")
check(bool(broken(lambda r: r.update(headline="WHAT IS INSIDE?"))), "a 3-word headline fails")
check(bool(broken(lambda r: r.update(subtitle="Bread · Steak · Yum"))), "a non-noun subtitle word fails")


def same_comp(r):
    r["variants"]["B"].update({k: r["variants"]["A"][k] for k in ("layout", "largest", "place")})


check(any("composition" in x or "near-identical" in x for x in broken(same_comp)),
      "two variants with one composition fail")


def paint_out(d):
    f = os.path.join(d, "A.jpg")
    im = Image.open(f).convert("RGB")
    hb = rec0["variants"]["A"]["headline_bbox"]
    ImageDraw.Draw(im).rectangle(hb, fill=(20, 15, 12))
    im.save(f, "JPEG", quality=92)


p = broken(lambda r: None, paint_out)
check(any("headline at 320" in x or "differ from a fresh" in x for x in p),
      f"a painted-out headline fails: {p[:1]}")
check(bool(broken(lambda r: r["panels"][0].update(sha256="0" * 64))), "a panel with other bytes fails")

grey = Image.new("RGB", (T.TW, T.TH), (120, 110, 100))
ImageDraw.Draw(grey).text((200, 34), "WHAT'S INSIDE?", font=TT._font(176), fill=(140, 128, 116),
                          stroke_width=10, stroke_fill=(128, 118, 108))
px, c = TT.legibility(grey, "WHAT'S INSIDE?", 176, (200, 34), 10)
check(c < TT.HEAD_MIN_CONTRAST, f"a low-contrast headline measures {c:.1f}:1 at 320 px - under the floor")
pub = Image.open(os.path.join(src, "A.jpg"))
v = rec0["variants"]["A"]
hy = 34 if v["place"] == "top" else (T.TH - 176 - 80) // 2 - 10
hx = (T.TW - ImageDraw.Draw(pub).textlength(rec0["headline"], font=TT._font(176))) / 2
px, c = TT.legibility(pub, rec0["headline"], 176, (hx, hy), 10)
check(px >= TT.HEAD_MIN_PX and c >= TT.HEAD_MIN_CONTRAST,
      f"the published headline at 320 px: {px:.0f} px tall, {c:.1f}:1")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
