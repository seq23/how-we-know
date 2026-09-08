"""The caption track is derivable from the repository, so no lane may ask for it.

THE DEFECT THIS GUARDS. Run 34236877023 (2026-09-08, `loop · daily 09:00 CT ·
upload from R2`) exited 3 with

    REFUSE how-strong-is-graphene: captions/how-strong-is-graphene.srt does not exist
    NAMED STOP [CAPTIONS_NOT_READY]
    unblock: ... python visuals/captions.py <slug>   [on the Mac]

The refusal was right and the page was not. The runner was holding every input
the file needs: the cue TEXT is `plan[i]["narration"]` in `plans/<slug>.json`,
and the only datum that ever lived exclusively on the voicing Mac was a list of
per-beat wav durations. Those are now written into `audio/<slug>/beats.json`,
which git tracks, so the track is a pure function of the repository.

Four properties, and the last two are what stop this from being a shortcut:

  A. With no narration audio present AT ALL, the rebuilt .srt is byte-identical
     to the one built from the wavs. Not "close enough" — identical.
  B. `loop/cloud_upload.py` heals BEFORE its captions gate, and the gate is
     still the last word.
  C. It REFUSES to build a track from the planner's word-count estimate. A
     green light bought by inventing cue times would be worse than the stop.
  D. A guard that examines zero episodes hard-fails.

Hard-fails if it examines zero episodes.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
sys.path.insert(0, os.path.join(ROOT, "visuals"))
sys.path.insert(0, os.path.join(ROOT, "voice"))

import captions as CAP                                          # noqa: E402
import captions_build                                           # noqa: E402
import captions_lane                                            # noqa: E402

fails: list[str] = []
examined = 0


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


# ---- A + C. rebuild without audio; refuse without measurement -------------
# Every episode whose beats.json carries a full set of measured durations is a
# subject. Nothing is written outside a temp directory.
subjects = []
for slug in CAP.episode_slugs():
    try:
        plan, _ = CAP.load_plan(slug)
    except SystemExit:
        continue
    rec = CAP.recorded_durations(slug)
    if len(rec) == len(plan) and plan:
        subjects.append((slug, plan))

if not subjects:
    print("FAIL: no episode carries a complete set of measured beat durations "
          "in audio/<slug>/beats.json, so this guard examined zero items. That "
          "is the state the caption lane cannot heal from — it is not a pass.")
    raise SystemExit(1)

real_audio = CAP.AUDIO
try:
    for slug, plan in subjects:
        examined += 1
        CAP.AUDIO = real_audio          # every iteration starts from the truth
        truth, src, _ = CAP.beat_durations(slug, plan)
        with tempfile.TemporaryDirectory() as td:
            # A. no wav anywhere: exactly what a GitHub runner sees.
            manifest_only = os.path.join(td, "audio")
            os.makedirs(os.path.join(manifest_only, slug))
            shutil.copy(CAP.beats_manifest_path(slug),
                        os.path.join(manifest_only, slug, "beats.json"))
            CAP.AUDIO = Path(manifest_only)
            got, src2, measured = CAP.beat_durations(slug, plan)
            if src2 != "recorded":
                fails.append(
                    f"A: {slug} with no wavs present resolved timing source "
                    f"{src2!r} ({measured}/{len(plan)} beats), not 'recorded'. "
                    f"The cloud cannot build this episode's captions.")
                continue
            a = os.path.join(td, "a.srt")
            b = os.path.join(td, "b.srt")
            CAP.write_srt(CAP.build_cues(plan, truth), Path(a))
            CAP.write_srt(CAP.build_cues(plan, got), Path(b))
            ha, hb = sha(open(a, "rb").read()), sha(open(b, "rb").read())
            if ha != hb:
                fails.append(
                    f"A: {slug} rebuilt from beats.json differs from the track "
                    f"built from the wavs ({ha} vs {hb}). A caption track that "
                    f"is only nearly right is a caption track that drifts.")

            # C. strip the measurement entirely: it must refuse, not estimate.
            empty = os.path.join(td, "empty")
            os.makedirs(empty)
            CAP.AUDIO = Path(empty)
            _, src3, _ = CAP.beat_durations(slug, plan)
            if src3 != "estimate":
                fails.append(f"C: {slug} with no timing at all reported "
                             f"{src3!r}, expected 'estimate'")
            if captions_build.timing_source(slug)[0] != "estimate":
                fails.append(f"C: with no timing on disk, captions_build still "
                             f"reports a measured source for {slug}")
finally:
    CAP.AUDIO = real_audio

# ---- C (live). a real uncaptioned, unmeasured episode must be REFUSED ------
#
# Asserted against the repository as it stands rather than a fixture: an
# episode that is queued, has no .srt, and whose narration is incomplete is
# exactly the residue the caption lane cannot heal, and it must be named rather
# than captioned off an estimate.
uncaptioned = dict(captions_lane.uncaptioned(
    [s_ for s_, _ in [(x, 0) for x in CAP.episode_slugs()]]))
unmeasured = [s_ for s_ in uncaptioned
              if captions_build.timing_source(s_)[0] not in ("audio", "recorded")]
if unmeasured:
    examined += 1
    can, cannot = captions_build.buildable(unmeasured)
    if can:
        fails.append(
            f"C: {can} have no measured narration timing and would still be "
            f"captioned. A track timed off the planner's word-count estimate "
            f"puts cues on screen at times the voice does not speak, and it "
            f"would satisfy the upload gate while doing it.")
    if len(cannot) != len(unmeasured):
        fails.append(f"C: {len(unmeasured)} unmeasured episode(s) but only "
                     f"{len(cannot)} refusal(s) — one was neither built nor "
                     f"named, which is a silent skip")

# ---- B. the upload lane heals before it judges, and still judges ----------
src = open(os.path.join(LOOP, "cloud_upload.py")).read()
tree = ast.parse(src)
heal_line = gate_line = None
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        fn = getattr(n.func, "attr", None)
        if fn == "heal" and getattr(getattr(n.func, "value", None), "id",
                                    None) == "captions_build":
            heal_line = n.lineno
        if fn == "uncaptioned":
            gate_line = n.lineno
examined += 1
if heal_line is None:
    fails.append("B: loop/cloud_upload.py never calls captions_build.heal(), so "
                 "an uncaptioned episode still pages the owner for a file the "
                 "runner could build.")
elif gate_line is None:
    fails.append("B: loop/cloud_upload.py no longer asks "
                 "captions_lane.uncaptioned() — the gate is gone, and healing "
                 "without a gate is worse than a gate without healing.")
elif heal_line > gate_line:
    fails.append(f"B: the heal (line {heal_line}) runs AFTER the gate "
                 f"(line {gate_line}), so the gate refuses episodes that would "
                 f"have been healed a moment later.")

# ---- D. the lane hard-fails on an empty selection -------------------------
examined += 1
if "CAPTIONS_BUILD_EXAMINED_NOTHING" not in open(
        os.path.join(LOOP, "captions_build.py")).read():
    fails.append("D: loop/captions_build.py no longer hard-fails when it "
                 "examines zero episodes; an unreadable queue would report a "
                 "clean caption shelf it never looked at.")

print(f"inspected {examined} case(s): {len(subjects)} episode(s) rebuilt from "
      f"committed beat timings alone")
if fails:
    print("\nFAIL:")
    for f in fails:
        print(f"  - {f}")
    raise SystemExit(1)
print("all green - the caption track is derivable from the repo, and no lane "
      "may ask a human for one")
