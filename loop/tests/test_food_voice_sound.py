"""One voice start to finish, and the food sound layer, measured
(voice/food_voice.py, visuals/food_sound.py, V54).

Owner verdict on food sample round 1, 2026-10-13: "ONE VOICE, NORMAL EXPLAINER
PACE, START TO FINISH" - the calm register and its title-card switch are
removed, and a render whose narration pace or pitch changes mid-video FAILS.
The bed (sizzle, snap, pour; public domain) stays, ducked under speech and
matched to the real clips on screen.

  1. The sample's own audio, measured when it was rendered and recorded in
     channel/specs/food-sample-chocolate.json, is one register, never
     pitch-shifted, every long beat within 1 semitone and 20 % speech rate of the
     median, every third within 20 % pace; the bed meets food_sound.CONTRACT.
  2. The ruler fails what round 1 was: the same measurement with one beat
     2 semitones lower and slower, and with a calm register named, both FAIL.
  3. The rulers on synthetic signals: a known pitch shift measures as that shift;
     an unducked bed fails; a ducked one passes.
  4. Settings: voice/registers.json holds ONE register and no switch point;
     every sound is PD/CC0 with its item page; a clip's own `sound` decides the
     cue under it (a pour under a pour, snaps under breaking bars, silence under
     a still heap).
  5. V54 passes on the real repo.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * the recorded median pitch of the longest beat lowered 2 semitones in the
    sample spec -> V54 and case 1 fail ("sits -2.00 semitones from the video's median");
  * a "calm" register put back in voice/registers.json -> case 4 and V54 fail.
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
check(v.get("register") == ["standard"] and len(v["beats"]) >= 5,
      f"one register measured over {len(v.get('beats') or [])} beats: {v.get('register')}")
vp = FV.check(v)
check(not vp, f"pitch and pace hold start to finish: {vp} thirds={v.get('pace_wpm_by_third')}")
sp = S.check(spec["sound"])
check(not sp, f"the bed ducks under the voice and sits low: {sp} {spec['sound']}")

# ------------------------------------------------ 2. round 1 would fail now
bad = json.loads(json.dumps(v))
b = max(bad["beats"], key=lambda x: x["words"])
b["median_f0_hz"] *= 2 ** (-2 / 12)
b["wpm"] *= 0.75
check(bool(FV.check(bad)), "a beat 2 semitones lower and 25% slower fails one-voice")
bad = json.loads(json.dumps(v))
bad["beats"][-1]["register"] = "calm"
check(bool(FV.check(bad)), "a calm beat fails one-voice")
bad = json.loads(json.dumps(v))
bad["pace_wpm_by_third"] = [175.0, 122.0, 112.0]
check(bool(FV.check(bad)), "round 1's thirds (175 -> 122 -> 112 wpm) fail one-voice")

# --------------------------------------------------------------- 3. rulers
sr = 24000
t = np.arange(sr * 2) / sr
x = (0.3 * np.sin(2 * np.pi * 210 * t) + 0.1 * np.sin(2 * np.pi * 420 * t)).astype(np.float32)
for st in (-1.0, -2.0):
    a, b_ = FV._median_f0(x, sr), FV._median_f0(FV.shift_down(x, st), sr)
    check(a and b_ and abs(12 * np.log2(a / b_) + st) < 0.25,
          f"a {st} semitone shift measures as {12 * np.log2(a / b_):.2f}")
voice = np.zeros(S.SR * 6, np.float32)
voice[:S.SR * 3] = 0.2 * np.sin(2 * np.pi * 200 * np.arange(S.SR * 3) / S.SR)
bed = np.full(S.SR * 6, 0.01, np.float32)
check(bool(S.check(S.measure(voice, bed, voice + bed))), "an unducked bed fails the contract")
ducked = bed.copy()
ducked[:S.SR * 3] *= 0.2
check(not S.check(S.measure(voice, ducked, voice + ducked)), "a bed ducked 14 dB passes")

# -------------------------------------------------------------- 4. settings
regs = FV.registers()
check(set(regs["registers"]) == {"standard"} and "switch_at" not in regs
      and regs["route"] == "chatterbox-local",
      "one register on the free local route, no switch point")
check(regs["registers"]["standard"]["pitch_semitones"] == 0.0, "the one register is unshifted")
snd = json.loads((ROOT / "channel" / "sound" / "food.json").read_text())["index"]
check({r["key"] for r in snd} == {"sizzle", "snap", "pour"} and all(
      r["licence"].lower() in ("public domain", "cc0") and r["item_url"] and r["sha256"]
      for r in snd), "sizzle, snap and pour: each PD/CC0 with its item page and sha256")
cat = {"pourclip": {"kind": "clip", "sound": "pour"}, "heap": {"kind": "clip", "sound": None},
       "bars": {"kind": "clip", "sound": "snap"}}
check(S.shot_cue({"asset": "pourclip"}, cat) == "pour" and S.shot_cue({"asset": "heap"}, cat) is None
      and S.shot_cue({"asset": "bars"}, cat) == "snap",
      "each clip's own sound decides its cue (pour / silence / snap)")

# ------------------------------------------------------------------ 5. V54
import validate as V                                           # noqa: E402
res = V.v54_food_voice_sound().as_dict()
check(not res["failures"] and res["examined"] > 0, f"V54 passes on the real repo: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
