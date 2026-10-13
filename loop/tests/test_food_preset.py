"""The `food` imagery preset's contract, on REAL output (visuals/food.py, V53).

Owner's brief, 2026-10-13, and her verdict on sample round 1 the same day:
dark warm ground, the channel's thumbnail grade on EVERY clip so it reads as one
look, REAL MOVEMENT (stills are not acceptable for food in motion), the
impossible-scale feel from real footage (walls, kaleidoscopes), cuts every
3-5 s in the opening then 6-12 s holds, one glowing cross-section per video
(the only place an AI still may appear), altered content flagged, captions on.

  1. The committed sample proof (channel/specs/food-sample-chocolate.proof.npz)
     passes check_frames: the grade re-derived from the ungraded pixels matches
     the published ones, and the salient subject covers the frame. The sample's
     spec passes check_spec: cadence, >= 60 % real video, 3-5 composites, AI only
     under the device, a recorded licence for every clip on screen.
  2. The grade is the channel's (visuals/thumb_contract.GRADE) and the LUT the
     renderer uses equals the per-pixel function exactly.
  3. The timeline builder obeys the cadence on synthetic beats and real clip
     records: opening shots 3-5 s, body holds 6-12 s, one device, 3-5 composites,
     no AI still on a picture shot.
  4. The ffmpeg treatments write exactly the frames asked for (a wall and a
     kaleidoscope from a generated test clip).
  5. V53 passes on the real repo.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * FOOD_GRADE mix 0.30 -> 0.0 in visuals/food.py -> case 1 fails ("grade not applied");
  * PRESET body_hold_s (6, 12) -> (13, 20) -> cases 1 and 3 fail;
  * REAL_VIDEO_SHARE_MIN 0.60 -> 0.99 -> case 1 fails ("real video is ...% of screen time").
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import food as F                                               # noqa: E402
import food_motion as FM                                       # noqa: E402
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
check(not sp, f"cadence, real video, composites, licences, device, captions: {sp}")
st = F.screen_time(spec)
check(st["real_video_share"] >= 0.60, f"real video is {st['real_video_share']:.0%} of screen time")
check(len(spec["clip_licences"]) >= 10, f"{len(spec['clip_licences'])} distinct real clips on screen")
check(all(s["register"] == "standard" for s in spec["shots"] if "register" in s),
      "every shot is in the one register")
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

# ------------------------------------------------------------ 3. the cadence
clip = lambda uses: {"kind": "clip", "ai": False, "uses": uses}  # noqa: E731
cat = {"sheets": clip(["sheets", "liquid", "scale"]), "pour": clip(["pour", "liquid"]),
       "drip": clip(["drip", "liquid"]), "chunks": clip(["bar", "snap", "solid"]),
       "field": clip(["solid", "scale"]), "cacao": clip(["cacao", "cocoa"]),
       "chocolate-break-macro": {"kind": "ai", "ai": True}}
paras = [{"section": "Cold open", "phase": "opening", "register": "standard", "directive": None,
          "text": "Chocolate can set six ways and melt in your mouth."},
         {"section": "Title card", "phase": "body", "register": "standard", "directive": None,
          "text": "Why?"},
         {"section": "A", "phase": "body", "register": "standard", "directive":
          {"kind": "cross_section", "args": ["bar", "form five"]}, "text": "The crystal in the bar."},
         {"section": "A", "phase": "body", "register": "standard", "directive":
          {"kind": "cross_section", "args": ["bar", "again"]}, "text": "Melt, cocoa butter, pour."},
         {"section": "B", "phase": "body", "register": "standard", "directive": None,
          "text": "Liquid chocolate drips and melts on the tongue."}]
beats = [{"duration": 34.0}, {"duration": 5.0}, {"duration": 20.0},
         {"duration": 31.0}, {"duration": 44.0}]
tl = F.build_timeline(paras, beats, cat)
op = [s["dur"] for s in tl["shots"] if s["phase"] == "opening" and s["kind"] == "picture"]
body = [s["dur"] for s in tl["shots"] if s["phase"] == "body" and s["kind"] == "picture"]
check(op and all(3.0 - 0.05 <= d <= 5.0 + 0.05 for d in op), f"opening cuts within 3-5 s: {op}")
check(body and all(6.0 - 0.05 <= d <= 12.0 + 0.05 for d in body), f"body holds within 6-12 s: {body}")
check(sum(1 for s in tl["shots"] if s["kind"] == "device") == 1,
      "a second cross_section directive in the same part is not a second device")
comp = [s for s in tl["shots"] if s.get("composite")]
check(3 <= len(comp) <= 5 and comp[0] is tl["shots"][0], f"{len(comp)} composites, the first opens the video")
check(all(s["asset"] != "chocolate-break-macro" for s in tl["shots"] if s["kind"] != "device"),
      "the AI still appears only under the device")
spec2 = {**tl, "ai_assets": ["chocolate-break-macro"], "altered_content": True, "credits": {},
         "captions": {"burned_in": True},
         "clip_licences": {k: {f: "x" for f in F.CLIP_LICENCE_FIELDS} for k in cat if k != "chocolate-break-macro"}}
check(not F.check_spec(spec2), f"the built timeline passes the spec contract: {F.check_spec(spec2)}")

# ------------------------------------------------- 4. the ffmpeg treatments
with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=640x360:rate=25:duration=3", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    for tr in ("wall", "kaleido", "slowmo"):
        out = Path(td) / f"{tr}.mp4"
        info = FM.prepare(str(src), {}, 4.0, out, tr)
        check(info["frames"] == 120 and FM.count_frames(out) == 120,
              f"{tr}: exactly 120 frames of 4 s at 30 fps from a 3 s clip (looped seamlessly)")

# ------------------------------------------------------------------ 5. V53
import validate as V                                           # noqa: E402
res = V.v53_food_preset().as_dict()
check(not res["failures"] and res["examined"] > 0, f"V53 passes on the real repo: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
