"""The `food` imagery preset's contract, on REAL output (visuals/food.py, V53).

Owner's brief, 2026-10-13: dark warm ground, one glossy subject lit from the
side, the channel's thumbnail grade, slow zooms and parallax on stills, cuts
every 3-5 s in the opening then 8-15 s holds, one glowing cross-section per
video, realistic AI stills flagged as altered content, captions on.

  1. The committed sample proof (channel/specs/food-sample-chocolate.proof.npz:
     the ungraded composite and the DECODED final frame for each sampled
     picture frame of the rendered sample) passes check_frames: the grade
     re-derived from the ungraded pixels matches the published ones, and the
     salient subject covers the frame. The sample's spec passes check_spec:
     opening cuts, calm holds, one device, credits, altered_content.
  2. The grade is the channel's: FOOD_GRADE carries the thumbnail grade's
     shadow, highlight and contrast (visuals/thumb_contract.GRADE), and the
     LUT the renderer uses equals the per-pixel function exactly.
  3. The timeline builder obeys the cadence on synthetic beats: opening shots
     3-5 s, calm holds 8-15 s, at most one device per part.
  4. V53 passes on the real repo.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * FOOD_GRADE mix 0.30 -> 0.0 in visuals/food.py -> case 1 fails ("grade not
    applied") on the committed proof;
  * PRESET opening_cut_s (3, 5) -> (6, 9) -> cases 1 and 3 fail.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import food as F                                               # noqa: E402
import thumb_contract as TC                                    # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


SPEC = ROOT / "channel" / "specs" / "food-sample-chocolate.json"
PROOF = ROOT / "channel" / "specs" / "food-sample-chocolate.proof.npz"

# ----------------------------------------------------------- 1. real output
check(SPEC.exists() and PROOF.exists(), "the sample's spec and proof frames are committed")
spec = json.loads(SPEC.read_text())
z = np.load(PROOF)
n, probs = F.check_frames(z["ungraded"], z["final"], z["masks"])
check(n >= 5 and not probs, f"grade + subject coverage on {n} real proof frames: {probs}")
sp = F.check_spec(spec)
check(not sp, f"cadence, device, credits, captions, altered_content: {sp}")
check(spec["altered_content"] is True and spec["ai_assets"],
      "AI stills are on screen and the spec flags altered content")
check(spec["captions"]["burned_in"] is True, "captions are burned in")

# ------------------------------------------------------------- 2. the grade
g, t = F.FOOD_GRADE, TC.GRADE
check(g["base"] == t["id"] and tuple(g["shadow"]) == tuple(t["shadow"])
      and tuple(g["highlight"]) == tuple(t["highlight"]) and g["contrast"] == t["contrast"],
      "FOOD_GRADE is the channel's thumbnail grade (#191), mixed for motion")
rng = np.random.default_rng(1)
px = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
check(np.array_equal(F.grade_frame(px), F.grade_array(px)),
      "the renderer's LUT equals the per-pixel grade exactly")
dark = np.full((8, 8, 3), 40, np.uint8)
gd = F.grade_array(dark)[0, 0].astype(int)
check(gd[2] > gd[0], f"shadows lean navy under the grade: {gd.tolist()}")

# ------------------------------------------------------------ 3. the cadence
cat = {k: {"kind": "ai", "ai": True} for k in
       ("chocolate-sheets", "chocolate-river", "chocolate-ocean", "chocolate-mountain",
        "melting-square", "chocolate-break-macro", "cocoa-butter-wall")}
paras = [{"section": "Cold open", "register": "standard", "directive": None,
          "text": "Chocolate can set six ways and melt in your mouth."},
         {"section": "Title card", "register": "calm", "directive": None, "text": "Why?"},
         {"section": "A", "register": "calm", "directive": {"kind": "cross_section",
          "args": ["bar", "form five"]}, "text": "The crystal in the bar."},
         {"section": "A", "register": "calm", "directive": {"kind": "cross_section",
          "args": ["bar", "again"]}, "text": "Melt, cocoa butter, chocolate."},
         {"section": "B", "register": "calm", "directive": None,
          "text": "Liquid chocolate melts on the tongue."}]
beats = [{"duration": 37.0}, {"duration": 5.0}, {"duration": 20.0},
         {"duration": 31.0}, {"duration": 44.0}]
tl = F.build_timeline(paras, beats, cat)
op = [s["dur"] for s in tl["shots"] if s.get("register") == "standard"]
calm = [s["dur"] for s in tl["shots"] if s.get("register") == "calm"]
check(op and all(3.0 - 0.05 <= d <= 5.0 + 0.05 for d in op), f"opening cuts within 3-5 s: {op}")
check(calm and all(8.0 - 0.05 <= d <= 15.0 + 0.05 for d in calm), f"calm holds within 8-15 s: {calm}")
check(sum(1 for s in tl["shots"] if s["kind"] == "device") == 1,
      "a second cross_section directive in the same part is not a second device")
check(not F.check_spec({**tl, "ai_assets": [], "credits": {}, "captions": {"burned_in": True}}),
      "the built timeline passes the spec contract")

# ------------------------------------------------------------------ 4. V53
sys.path.insert(0, str(HERE.parent))
import validate as V                                           # noqa: E402
res = V.v53_food_preset().as_dict()
check(not res["failures"] and res["examined"] > 0, f"V53 passes on the real repo: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
