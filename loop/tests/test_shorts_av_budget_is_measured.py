"""A Short's picture and audio are each judged against the NARRATION, on
budgets that were measured - not against each other on a number that matched
a comment.

WHAT HAPPENED. visuals/shorts.py:verify refused a cut when the video and
audio streams differed by more than one frame (33 ms). On 2026-09-18
why-is-carbon-fiber-so-strong measured 0.039 s and was refused
deterministically on every re-cut, so it could not ship - while its picture
was exactly right (1605 frames against 53.509 s of narration). Measured over
all 69 cuts on 2026-09-19: the picture was within half a frame of the WAV on
every cut made since the last-beat correction, and the whole of the 0.039 s
was `-shortest` stopping the AAC encoder 48 ms early, at a 1024-sample frame
boundary, because the picture was 9 ms shorter than the WAV. That truncation
hit 23 of 69 cuts (11-64 ms) and, with 30-40 ms of trailing silence in the
last-beat WAVs, ate into the last spoken word in 7 of them - and the old rule
PASSED 22 of those 23, since it only compared the two streams to each other.
It also passed 38 older cuts whose picture was up to 1.5 frames short, for
the same reason: the audio had been cut down to match.

WHAT THIS PROVES, on planted durations (the verdict is a pure function of
video, audio and narration seconds) and on the cutter's own source:

  1. a picture that is a real two frames off its narration is refused, and
     so is a one-frame miscount in either direction - the budget is the
     half-frame that round(narration * FPS) guarantees, not a whole frame
  2. a cut whose only discrepancy is the AAC container residual (sub-ms) is
     accepted, and the residual is reported, not refused
  3. an audio stream truncated by `-shortest` (the carbon-fiber shape:
     picture -9 ms, audio -48 ms) IS refused - as a truncation of the
     narration, which is what it is, not as a "drift"
  4. the budgets are derived, not typed: PICTURE_BUDGET_S is half a frame
     plus the probe epsilon, and AUDIO_BUDGET_S sits above the 0.3 ms
     container residual and below the 11 ms smallest truncation ever seen
  5. the mux no longer passes `-shortest` (the cause), and verify() is
     handed the narration total so it has something honest to judge against
  6. the verdict over a planted receipt set hard-fails on zero receipts

Negative proof, recorded in the PR that introduced this: with the old
|video - audio| > 1/FPS rule restored, assertion 3's carbon-fiber shape is
refused for the wrong reason and assertion 2's shapes with a truncated audio
that happens to match a short picture are accepted; with `-shortest`
restored, assertion 5 fails.

Hard-fails if it runs fewer than eight verdicts.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))

import shorts as S  # noqa: E402

fails: list[str] = []
FPS = S.FPS
FRAME = 1.0 / FPS
verdicts = 0


def verdict(video, audio, narration):
    global verdicts
    verdicts += 1
    return S.av_verdict(video, audio, narration)


def refused(problems, word):
    return any(word in p for p in problems)


# ---- 1: real picture errors are refused -------------------------------------------
nar = 53.5093                                   # carbon fiber's WAV total
exact = round(nar * FPS) / FPS                  # 1605 frames = 53.500
for frames_off in (-2, -1, 1, 2):
    v = exact + frames_off * FRAME
    p, info = verdict(v, nar, nar)
    if not refused(p, "frame count is wrong"):
        fails.append(f"1: a picture {frames_off:+d} frame(s) off its narration "
                     f"({v:.3f}s vs {nar:.3f}s) was accepted: {p}")
    if refused(p, "narration was truncated"):
        fails.append("1: a picture error was reported as an audio truncation")

# ---- 2: the AAC container residual is information, not a refusal ---------------
# The largest residual measured over the 46 untruncated cuts was 0.3 ms; the
# picture may sit anywhere inside its half-frame.
for v_off, a_off in ((-0.0093, -0.0003), (+0.0160, +0.0003), (0.0, 0.0),
                     (-0.0160, -0.0003)):
    p, info = verdict(nar + v_off, nar + a_off, nar)
    if p:
        fails.append(f"2: picture {v_off:+.4f}s / audio {a_off:+.4f}s was refused: {p}")
    if info["audio_vs_narration_s"] != round(a_off, 4):
        fails.append(f"2: the audio residual was not reported ({info})")
    if info["picture_vs_narration_s"] is None:
        fails.append("2: the picture measurement was not reported")

# ---- 3: the carbon-fiber shape is refused, as a truncation ----------------------
p, info = verdict(53.500, 53.461, nar)
if not refused(p, "narration was truncated"):
    fails.append(f"3: audio truncated 48 ms by -shortest was accepted: {p}")
if refused(p, "frame count is wrong"):
    fails.append("3: a correct 1605-frame picture was refused as a frame error")
if info["av_drift_s"] != 0.039:
    fails.append(f"3: the stream difference is no longer reported ({info})")
# ...and the 22 truncations the old rule waved through. 16-...-short2:
# picture -32 ms (pre-correction cut), audio -64 ms, streams differ by +32 ms.
p, _ = verdict(57.333, 57.301, 57.365)
if not refused(p, "narration was truncated") or not refused(p, "frame count"):
    fails.append(f"3: a short picture hidden by a shorter audio was accepted: {p}")
# The smallest truncation -shortest produced, 11 ms (02-...-short2).
p, _ = verdict(32.733, 32.725, 32.736)
if not refused(p, "narration was truncated"):
    fails.append(f"3: an 11 ms truncation was accepted: {p}")

# ---- 4: the budgets are derived ------------------------------------------------
if abs(S.PICTURE_BUDGET_S - (0.5 / FPS + S.PROBE_EPS_S)) > 1e-12:
    fails.append(f"4: PICTURE_BUDGET_S {S.PICTURE_BUDGET_S} is not half a frame "
                 f"plus the probe epsilon")
if S.PICTURE_BUDGET_S >= FRAME:
    fails.append("4: the picture budget is a whole frame again, which misses "
                 "half of all one-frame miscounts")
if not (0.0003 < S.AUDIO_BUDGET_S < 0.011):
    fails.append(f"4: AUDIO_BUDGET_S {S.AUDIO_BUDGET_S} is not between the "
                 f"measured container residual and the smallest truncation")
if not (0 < S.PROBE_EPS_S <= 0.002):
    fails.append(f"4: PROBE_EPS_S {S.PROBE_EPS_S} is not a probe rounding allowance")

# ---- 5: the cause is gone and the verifier is told the narration --------------
src = open(os.path.join(ROOT, "visuals", "shorts.py")).read()
ms = src[src.find("def make_short("):src.find("def av_verdict(")]
if '"-shortest"' in ms:
    fails.append("5: the final mux still passes -shortest, which truncates the "
                 "AAC stream at a 1024-sample boundary whenever the picture "
                 "is a few ms short")
if not re.search(r"verify\(out,\s*narration_s=", ms):
    fails.append("5: make_short() does not hand verify() the narration total")
vs = src[src.find("def verify("):src.find("# ---------------------------------"
                                          "--------------------------------------- cli")]
if "av_verdict(" not in vs:
    fails.append("5: verify() does not use av_verdict()")
if re.search(r"1\.0\s*/\s*FPS|1\s*/\s*FPS", vs):
    fails.append("5: verify() still carries a one-frame budget of its own")

# ---- 6: nothing to judge is a failure, not a pass -----------------------------
def judge_receipts(receipts: list[dict]) -> tuple[int, list[str]]:
    """The shape a validator over shorts/*.short.json takes: examined count
    and problems. Zero examined is a hard failure."""
    if not receipts:
        raise RuntimeError("examined zero receipts")
    probs = []
    for r in receipts:
        p, _ = S.av_verdict(r["video_s"], r["audio_s"], r["narration_s"])
        probs += p
    return len(receipts), probs


try:
    judge_receipts([])
    fails.append("6: a verdict over zero receipts passed")
except RuntimeError:
    pass
n, probs = judge_receipts([
    {"video_s": 53.500, "audio_s": 53.509, "narration_s": nar},
    {"video_s": 53.500, "audio_s": 53.461, "narration_s": nar},
])
if n != 2 or len(probs) != 1:
    fails.append(f"6: planted receipts judged wrongly: examined {n}, problems {probs}")

# ---- no narration total: report, never refuse -------------------------------
p, info = verdict(53.500, 53.461, None)
if p or info["av_drift_s"] != 0.039:
    fails.append(f"a bare re-verify with no narration total misjudged: {p} {info}")

# ---- Rule 0 --------------------------------------------------------------------
if verdicts < 8:
    fails.append(f"Rule 0: only {verdicts} verdicts were exercised")

if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"OK shorts A/V budget is measured: {verdicts} verdicts - picture judged "
      f"against narration on a half-frame ({S.PICTURE_BUDGET_S * 1000:.1f} ms), "
      f"audio on {S.AUDIO_BUDGET_S * 1000:.0f} ms, -shortest gone from the mux")
