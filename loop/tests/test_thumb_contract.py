"""The long-form thumbnail contract, asserted on REAL output.

Owner decisions 12-13 Oct 2026 (repackage job 1). Builds the three variants
for a real deep-sea episode and a real materials episode from the committed,
rights-verified imagery into a scratch directory, then proves:

  1. three variants + contract.json exist; the chooser names A; thumbs_for.build
     ships A as channel/<out>/<slug>.jpg (byte-identical);
  2. on the real JPEGs: text <= 3 words, subject fill >= 60% with real subject
     energy, 1280x720, and the channel GRADE applied (verify() re-grades the
     recorded crop of the recorded source and compares the published pixels);
  3. negatives: an UNGRADED variant fails verify; a contract claiming a crop
     whose subject fills under 60% fails; draw() refuses four words; a slug
     with no rights-verified image of its subject is ContractRefused, named;
  4. V48 passes on the real repo and fails on a planted bad contract.

NEGATIVE PROOF (run once, 2026-10-13): make grade() return its input
unchanged -> case 3 "ungraded" no longer differs and V48's self-check fails;
restore -> green. Hard-fails if it examines nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

from PIL import Image                                         # noqa: E402
import thumb_contract as TC                                   # noqa: E402

fails: list[str] = []
examined = 0
TMP = Path(tempfile.mkdtemp(prefix="thumb-contract-"))


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUGS = {"19-what-is-the-deepest-fish-ever-recorded":
         "The deepest fish ever recorded was filmed 8,336 meters down",
         "what-is-carbon-fiber-made-of": "Carbon fiber is made of carbon atoms"}
root = str(TMP / "variants")
for slug, title in SLUGS.items():
    try:
        r = TC.build_variants(slug, out_root=root, title=title)
    except TC.ContractRefused as e:
        check(False, f"{slug}: the contract refused an episode with verified "
                     f"imagery: {e}")
        continue
    c = r["contract"]
    check(set(c["variants"]) == {"A", "B", "C"} and c["chosen"] == "A"
          and TC.chooser(slug, root).endswith(f"{slug}/A.jpg"),
          f"{slug}: not three variants with A chosen: {list(c['variants'])}")
    check(len({json.dumps([v['box'], v['text'], v['source']]) for v in c["variants"].values()}) == 3,
          f"{slug}: the three variants are not distinct in crop, text or image")
    for name, v in c["variants"].items():
        check(v["words"] <= 3 and len(v["text"].split()) <= 3,
              f"{slug}/{name}: {v['text']!r} is over three words")
        check(v["fill"] >= TC.SUBJECT_FILL_MIN,
              f"{slug}/{name}: subject fill {v['fill']} under 60%")
        check(v["credit"], f"{slug}/{name}: the image credit was dropped")
    check(TC.verify(slug, root) == [], f"{slug}: verify() on real output: "
                                       f"{TC.verify(slug, root)}")

# -------------------------------------------- 1b. thumbs_for ships variant A
import thumbs_for                                             # noqa: E402
out = TMP / "ship"
p = thumbs_for.build("19-what-is-the-deepest-fish-ever-recorded", out_dir=str(out))
check(Path(p).read_bytes() == (out / "variants" / "19-what-is-the-deepest-fish-ever-recorded" / "A.jpg").read_bytes(),
      "thumbs_for.build did not ship variant A as the upload thumbnail")

# ------------------------------------- 2b. no phrase ends mid-thought
# 2026-10-13: "100 DEGREES PER", "10,935 METERS PLUS" were built for live videos.
for t_, want in (("Faster than 100 degrees per second, carbon is trapped", "100 DEGREES"),
                 ("Challenger Deep is 10,935 meters, plus or minus six", "10,935 METERS")):
    got = TC.text_options(t_)
    check(got and got[0] == want and not any(
        x.split()[-1].lower() in TC.DANGLING for x in got if len(x.split()) > 1),
          f"thumbnail text ends on a dangling word: {t_!r} -> {got}")

# --------------------------- 2c. clause boundaries, and no partial sets
got = TC.text_options("Steel fails at 0.4 gigapascals, graphene at 130")
check(got and got[0] == "0.4 GIGAPASCALS" and not any("GRAPHENE" in x and "0.4" in x for x in got),
      f"thumbnail text crosses a clause and prints one figure over another subject: {got}")
import tempfile as _tf                                          # noqa: E402
_d = _tf.mkdtemp()
# The refusal is forced: graphene now builds (13 Oct 2026, the builder tries
# more crops for distinct B/C), so B is made impossible - no two pictures can
# be 65 bits apart on a 64-bit hash - and the directory must stay empty.
import thumb_distinct as _TD                                    # noqa: E402
_keep = _TD.MIN_PHASH_DISTANCE
_TD.MIN_PHASH_DISTANCE = 65
try:
    TC.build_variants("how-strong-is-graphene", out_root=_d)    # refused at B
    _left = None
except TC.ContractRefused:
    _left = os.listdir(_d)
finally:
    _TD.MIN_PHASH_DISTANCE = _keep
check(_left == [], f"a refused set left files behind for a lane to ship: {_left}")

# ------------------------------- 2d. PLAIN thumbnail words (owner, 13 Oct)
import longform_title as _LT                                    # noqa: E402
_t = TC.text_options("At a thousand meters, the danger is not a fish",
                     _LT.subject_words("why deep sea creatures are so scary"))
check("NOT FISH" not in _t and "NOT A FISH" not in _t,
      f"a riddle fragment was offered as thumbnail text: {_t}")
_t = TC.text_options("Why chocolate melts in your mouth but not in your hand",
                     _LT.subject_words("why chocolate snaps"))
check(_t and _t[0] == "CHOCOLATE MELTS", f"variant A does not name the plain subject: {_t}")
_t = TC.text_options("Steel fails at 0.4 gigapascals, graphene at 130",
                     _LT.subject_words("how strong is graphene"))
check(not any("0.4" in x for x in _t), f"a figure from another subject's clause: {_t}")

# ------------------------------------ 2e. THE DRAMA LINE (owner's lock)
_ti = (ROOT / "scripts" / "how-strong-is-titanium.md").read_text(encoding="utf-8")
_sub = {"titanium"}
check(not TC.drama_problems("TITANIUM", _ti, _sub), "a bare subject failed the drama gate")
check(TC.drama_problems("TITANIUM BEATS DIAMOND HAMMERS", _ti, _sub),
      "four words passed the drama gate")
check(any("not in the script" in x for x in TC.drama_problems("TITANIUM UNICORN", _ti, _sub)),
      "a word the script never says passed the drama gate")
check(any("neither" in x for x in TC.drama_problems("VERY GOOD", _ti, _sub)),
      "a line with no subject, figure or contradiction passed")
_saved_tt = TC.THUMB_TEXT
TC.THUMB_TEXT = os.path.join(_tf.mkdtemp(), "thumb_text.json")
_asked = []
_lines = TC.drama_text("how-strong-is-titanium", "Is Titanium Stronger Than Steel?", _ti, _sub,
                       ask=lambda m: (_asked.append(m) or ("TITANIUM\nTITANIUM UNICORN\nA B C D", "fx")))
check(_lines == ["TITANIUM"] and len(_asked) == 1, f"drama_text did not gate the model's lines: {_lines}")
_again = TC.drama_text("how-strong-is-titanium", "Is Titanium Stronger Than Steel?", _ti, _sub,
                       ask=lambda m: (_ for _ in ()).throw(AssertionError("asked twice")))
check(_again == ["TITANIUM"], "the cached drama line was not reused")
TC.THUMB_TEXT = _saved_tt

# --------------------------------------------------------------- 3. negatives
slug = "19-what-is-the-deepest-fish-ever-recorded"
bad_root = TMP / "bad"
shutil.copytree(Path(root) / slug, bad_root / slug)
rec = json.loads((bad_root / slug / "contract.json").read_text())
vA = rec["variants"]["A"]
src = TC._open_source({"path": os.path.join(TC.IMAGERY, vA["source"]),   # noqa: SLF001
                       "crop": vA.get("crop")})
ungraded = src.crop(tuple(vA["box"])).resize((TC.TW, TC.TH))
ungraded.save(bad_root / slug / "A.jpg", "JPEG", quality=92)
check(any("grade" in p for p in TC.verify(slug, str(bad_root))),
      "an UNGRADED variant passed verify()")
shutil.copy(Path(root) / slug / "A.jpg", bad_root / slug / "A.jpg")
W, H = src.size
rec["variants"]["B"]["box"] = [0, 0, W, int(W * 9 / 16)] if W * 9 / 16 <= H else [0, 0, int(H * 16 / 9), H]
rec["variants"]["B"]["text_bbox"] = [0, 0, 0, 0]
(bad_root / slug / "contract.json").write_text(json.dumps(rec))
pr = TC.verify(slug, str(bad_root))
check(any("/B:" in p for p in pr),
      f"a contract whose recorded crop is not the published one passed: {pr}")
try:
    TC.draw(ungraded, "ONE TWO THREE FOUR", "credit")
    check(False, "draw() accepted four words")
except ValueError:
    check(True, "")
try:
    TC.build_variants("how-strong-is-titanium", out_root=str(TMP / "none"),
                      title="Titanium alloys reach 1400 megapascals")
    check(False, "an episode with no verified image of its subject got a contract")
except TC.ContractRefused as e:
    check("how-strong-is-titanium" in str(e), "ContractRefused does not name the slug")

# --------------------------------------------------------------------- 4. V48
import validate as V                                          # noqa: E402
res = V.v48_thumbnail_contract().as_dict()
check(not res["failures"], f"V48 fails on the real repo: {res['failures']}")
saved = TC.VARIANTS_DIR
TC.VARIANTS_DIR = str(bad_root)
try:
    res = V.v48_thumbnail_contract().as_dict()
    check(any("/B:" in f for f in res["failures"]),
          f"V48 passed a planted bad contract: {res['failures']}")
finally:
    TC.VARIANTS_DIR = saved

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
