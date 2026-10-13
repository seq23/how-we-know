"""Thumbnail variants are genuinely different pictures (visuals/thumb_distinct.py,
visuals/thumb_contract.build_variants/verify, validator V48).

Owner, 13 Oct 2026: two of the three food round-2 thumbnails were the same
image. A variant test that offers one picture twice tests nothing.

  1. The ruler: pHash of a picture and its quality-80 re-encode are within 2;
     two different pictures are >= 10 apart; a shifted 18 px crop of one image
     (the rejected food pair) is under 10.
  2. check(): a set with two near-identical pictures FAILS; a set whose three
     texts are identical FAILS; three different pictures with two texts pass.
  3. Every committed variant set (channel/thumbnails/variants) passes verify(),
     which now includes the rule - and NEGATIVE: a committed set with its C
     picture swapped for its A picture fails verify().
  4. build_variants on a one-image episode makes B and C clear the threshold
     (or refuses, named), never a duplicate.
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

from PIL import Image                                          # noqa: E402

import thumb_contract as T                                     # noqa: E402
import thumb_distinct as TD                                    # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


slugs = T.contract_slugs()
check(len(slugs) >= 10, f"{len(slugs)} committed variant sets to examine")
rec0 = json.load(open(os.path.join(T.VARIANTS_DIR, slugs[0], "contract.json")))
pics = T._pictures(rec0)
a = pics["A"]

# ---------------------------------------------------------------- 1. ruler
with tempfile.TemporaryDirectory() as td:
    q = os.path.join(td, "q.jpg")
    a.save(q, "JPEG", quality=80)
    d = TD.distance(TD.phash(a), TD.phash(q))
    check(d <= 2, f"a quality-80 re-encode moves pHash by {d}")
other = next(T._pictures(json.load(open(os.path.join(T.VARIANTS_DIR, s, "contract.json"))))["A"]
             for s in slugs if json.load(open(os.path.join(T.VARIANTS_DIR, s, "contract.json")))
             ["variants"]["A"]["source"] != rec0["variants"]["A"]["source"])
d = TD.distance(TD.phash(a), TD.phash(other))
check(d >= TD.MIN_PHASH_DISTANCE, f"two different pictures are {d} apart")
w, h = a.size
shifted = a.crop((18, 0, w, h)).resize((w, h))
d = TD.distance(TD.phash(a), TD.phash(shifted))
check(d < TD.MIN_PHASH_DISTANCE, f"the same picture shifted 18 px is {d} apart - a duplicate")

# ---------------------------------------------------------------- 2. check()
check(bool(TD.check({"A": a, "B": shifted, "C": other}, {"A": "X", "B": "Y", "C": "Z"})),
      "a set with two near-identical pictures fails")
check(bool(TD.check({"A": a, "B": other, "C": Image.new("RGB", a.size, (200, 30, 30))},
                    {"A": "SAME", "B": "SAME", "C": "same"})), "three identical texts fail")
check(not TD.check({"A": a, "B": other, "C": Image.new("RGB", a.size, (200, 30, 30))},
                   {"A": "ONE", "B": "ONE", "C": "TWO"}), "three different pictures, two texts pass")

# ------------------------------------------------- 3. committed sets + negative
bad = {s: T.verify(s) for s in slugs}
bad = {s: p for s, p in bad.items() if p}
check(not bad, f"every committed set passes verify() with the rule: {list(bad.items())[:2]}")
with tempfile.TemporaryDirectory() as td:
    s = slugs[0]
    shutil.copytree(os.path.join(T.VARIANTS_DIR, s), os.path.join(td, s))
    cp = os.path.join(td, s, "contract.json")
    r = json.load(open(cp))
    r["variants"]["C"] = dict(r["variants"]["A"], text=r["variants"]["C"]["text"])
    json.dump(r, open(cp, "w"))
    shutil.copyfile(os.path.join(td, s, "A.jpg"), os.path.join(td, s, "C.jpg"))
    p = T.verify(s, root=td)
    check(any("near-identical" in x for x in p), f"NEGATIVE: C made a copy of A fails verify(): {p[:1]}")

# ----------------------------------------------- 4. the builder on one image
one = next((s for s in slugs if len({v["source"] for v in json.load(open(
    os.path.join(T.VARIANTS_DIR, s, "contract.json")))["variants"].values()}) == 1), None)
if one:
    with tempfile.TemporaryDirectory() as td:
        shutil.copytree(os.path.join(T.VARIANTS_DIR, one), os.path.join(td, one))
        r = json.load(open(os.path.join(td, one, "contract.json")))
        t = [r["variants"][n]["text"] for n in "ABC"]
        try:
            T.build_variants(one, out_root=td, title=r.get("title"), texts=t, keep_a=True)
            check(not T.verify(one, root=td), f"{one}: one image, B and C rebuilt distinct")
        except T.ContractRefused as e:
            check("near-duplicate" in str(e), f"{one}: refused by name, not duplicated: {e}")
else:
    check(True, "no one-image set committed to rebuild")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
