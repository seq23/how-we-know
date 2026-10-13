"""The calm voice and the food sound layer, measured (voice/food_voice.py,
visuals/food_sound.py, V54).

Owner's brief, 2026-10-13: a `calm` voice setting on the existing free voice
route - slower, lower, more pause - switching in at the title card; a low
sound layer of sizzle, snap and pour under the narration, ducked under speech.

  1. The sample's own audio, as measured when it was rendered and recorded in
     channel/specs/food-sample-chocolate.json, meets voice/registers.json's
     contract (calm paces <= 85% of standard, >= 1 semitone lower, pauses
     >= 1.5x) and food_sound.CONTRACT (bed ducks >= 6 dB under speech, voice
     >= 15 dB over the bed, the bed really there in the pauses, no clipping).
  2. The rulers themselves, on synthetic signals: a known pitch shift is
     measured as that shift; an unducked bed fails; a ducked one passes.
  3. The registers file: calm switches at the title card, uses the same
     engine (Chatterbox, MIT weights - voice/LICENSING.md), and every sound
     is public domain or CC0 with its item page recorded.
  4. V54 passes on the real repo.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * the recorded calm median pitch set to standard's -> V54 and case 1 fail
    ("calm is only 0.00 semitones lower than standard");
  * an unducked bed is case 2 itself, run every time.
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
sys.path.append(str(ROOT / "voice"))
sys.path.append(str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import food_sound as S                                         # noqa: E402
import food_voice as FV                                        # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


spec = json.loads((ROOT / "channel" / "specs" / "food-sample-chocolate.json").read_text())

# ------------------------------------------------------------- 1. measured
v = spec["voice"]
check(set(v) == {"standard", "calm"} and v["calm"]["beats"] >= 3,
      f"both registers were measured on the sample: {sorted(v)}")
vp = FV.check(v)
check(not vp, f"calm is slower, lower and more paused than standard: {vp} {v}")
sp = S.check(spec["sound"])
check(not sp, f"the bed ducks under the voice and sits low: {sp} {spec['sound']}")

# --------------------------------------------------------------- 2. rulers
sr = 24000
t = np.arange(sr * 2) / sr
x = (0.3 * np.sin(2 * np.pi * 210 * t) + 0.1 * np.sin(2 * np.pi * 420 * t)).astype(np.float32)
for st in (-1.0, -2.0):
    a, b = FV._median_f0(x, sr), FV._median_f0(FV.shift_down(x, st), sr)
    check(a and b and abs(12 * np.log2(a / b) + st) < 0.25,
          f"a {st} semitone shift measures as {12 * np.log2(a / b):.2f}")
check(len(FV.shift_down(x, -2.0)) > len(x) * 1.1, "the shift also slows the read")
voice = np.zeros(S.SR * 6, np.float32)
voice[:S.SR * 3] = 0.2 * np.sin(2 * np.pi * 200 * np.arange(S.SR * 3) / S.SR)
bed = np.full(S.SR * 6, 0.01, np.float32)
check(bool(S.check(S.measure(voice, bed, voice + bed))), "an unducked bed fails the contract")
ducked = bed.copy()
ducked[:S.SR * 3] *= 0.2
check(not S.check(S.measure(voice, ducked, voice + ducked)), "a bed ducked 14 dB passes")

# -------------------------------------------------------------- 3. settings
regs = FV.registers()
check(regs["switch_at"] == "### Title card" and regs["route"] == "chatterbox-local",
      "calm switches in at the title card on the free local route")
c, s = regs["registers"]["calm"], regs["registers"]["standard"]
check(c["pitch_semitones"] < 0 and c["pause_sentence_s"] > s["pause_sentence_s"]
      and c["cfg_weight"] < s["cfg_weight"], "calm is lower, more paused, more deliberate")
snd = json.loads((ROOT / "channel" / "sound" / "food.json").read_text())["index"]
check({r["key"] for r in snd} == {"sizzle", "snap", "pour"} and all(
      r["licence"].lower() in ("public domain", "cc0") and r["item_url"] and r["sha256"]
      for r in snd), "sizzle, snap and pour: each PD/CC0 with its item page and sha256")

# ------------------------------------------------------------------ 4. V54
import validate as V                                           # noqa: E402
res = V.v54_food_voice_sound().as_dict()
check(not res["failures"] and res["examined"] > 0, f"V54 passes on the real repo: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
