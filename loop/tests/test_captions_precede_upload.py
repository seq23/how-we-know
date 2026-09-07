"""An episode may not be given an air date before its captions exist.

WHAT BROKE, AND WHY IT LOOKED LIKE A REGRESSION. V16 caption-track went
PASS(examined 20) on the 09-05 scheduled reach run and FAIL(3)(examined 22) on
the 09-06 one, with no commit between them (runs 33973856968 and 34041348292).
Nothing regressed. The upload lane put how-does-tempered-glass-shatter,
how-strong-is-titanium and how-is-damascus-steel-made on the calendar at
2026-09-05T21:36Z with no captions/<slug>.srt committed for any of them, and
V16 went red the moment they counted as scheduled.

That is the same shape as the POV gate next door: V16 reads the LEDGER, and an
episode only reaches the ledger by being uploaded, so V16 speaks after the
video is on YouTube. A guard downstream of the thing it governs can report the
harm; it cannot prevent it.

And it is not recoverable afterwards. The .srt is derived from the narration
WAVs by visuals/captions.py, and `audio/**/*.wav` is gitignored — so it can
only be produced on the machine that voiced the episode. An episode uploaded
without one is a video this repo can never caption.

WHAT THIS ASSERTS

  1. THE JOIN. Every slug V16 fails for a MISSING .srt is also refused by
     `captions_lane.uncaptioned()`, the rule the pre-upload gate uses. Two
     components each keeping their own list is this repo's named defect.
  2. ONE RULE, NOT TWO. loop/cloud_upload.py calls that same function rather
     than reimplementing "usable .srt".
  3. THE GATE IS REACHABLE, and is a REFUSAL, not a blanket halt: a captioned
     episode still ships, an uncaptioned one is dropped by name.
  4. AND NOT A SILENT SKIP. If refusing empties the run, the lane has a
     CAPTIONS_NOT_READY named stop rather than an exit 0 that did nothing.
  5. IT HARD-FAILS ON EMPTY, PROVEN AGAINST AN EMPTY DIRECTORY: pointed at a
     captions/ with nothing in it, the gate refuses EVERY episode. A gate that
     went quiet when its evidence vanished would be the "runs but inert"
     defect, and would have let exactly these three through.

Hard-fails when it examines zero episodes.
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)


def check() -> list[str]:
    import captions_lane                                    # noqa: PLC0415
    import validate as V                                    # noqa: PLC0415
    from pathlib import Path                                # noqa: PLC0415

    fails: list[str] = []

    # The subjects of the rule: every episode that has a script at all.
    import glob                                             # noqa: PLC0415
    slugs = [os.path.basename(p)[:-3]
             for p in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.md")))]
    if not slugs:
        return ["examined ZERO scripts - the gate has nothing to govern, so a "
                "pass here would mean nothing"]
    examined = len(slugs)

    have = [s for s in slugs if captions_lane.srt_for(s).exists()]
    lacking = [s for s in slugs if not captions_lane.srt_for(s).exists()]
    if not have:
        fails.append("not one episode has an .srt - this guard cannot prove "
                     "the gate lets a CAPTIONED episode through")

    # -- 1. the join with V16 -------------------------------------------
    r = V.v16_caption_track()
    if r.examined == 0:
        fails.append("V16 examined zero videos, so the join cannot be tested")
    # Only the "does not exist" failures are this gate's business; a video that
    # HAS an .srt and no uploaded track yet is the reach lane's backlog, not an
    # upload-ordering fault.
    v16_missing = {s for s in slugs
                   if any(s in f and "does not exist" in f
                          for f in getattr(r, "failures", []))}
    gate_bad = {s for s, _ in captions_lane.uncaptioned(slugs)}
    missed = v16_missing - gate_bad
    if missed:
        fails.append(
            f"V16 fails {sorted(missed)} for a missing .srt but the PRE-UPLOAD "
            f"gate would let them through - the two rules have drifted, which "
            f"is how the first three reached the calendar uncaptionable")

    # -- 2. one rule, not two -------------------------------------------
    src = open(os.path.join(LOOP, "cloud_upload.py")).read()
    if "captions_lane.uncaptioned" not in src:
        fails.append("loop/cloud_upload.py does not call "
                     "captions_lane.uncaptioned() - either the gate is not "
                     "invoked at all ('runs but inert'), or it has grown a "
                     "second copy of the rule that can drift from V16's")
    if "CAPTIONS_NOT_READY" not in src:
        fails.append("loop/cloud_upload.py has no CAPTIONS_NOT_READY named "
                     "stop - a run emptied by refusals would exit 0 having "
                     "done nothing (Rule 0)")

    # -- 3. a refusal, not a blanket halt -------------------------------
    if have and lacking:
        refused = {s for s, _ in captions_lane.uncaptioned(have + lacking)}
        wrongly_refused = sorted(refused & set(have))
        wrongly_allowed = sorted(set(lacking) - refused)
        if wrongly_refused:
            fails.append(f"the gate refused captioned episode(s) "
                         f"{wrongly_refused} - it is halting the lane rather "
                         f"than refusing the episode")
        if wrongly_allowed:
            fails.append(f"the gate allowed uncaptioned episode(s) "
                         f"{wrongly_allowed}")

    # -- a zero-cue .srt is not a caption track -------------------------
    real_dir = captions_lane.CAPTIONS_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            captions_lane.CAPTIONS_DIR = Path(tmp)
            (Path(tmp) / "inert.srt").write_text("", encoding="utf-8")
            if not captions_lane.uncaptioned(["inert"]):
                fails.append("a .srt with zero timed cues was accepted - a "
                             "file that exists and says nothing is exactly "
                             "the 'exists but inert' defect")

            # -- 5. the empty-directory proof ---------------------------
            os.remove(os.path.join(tmp, "inert.srt"))
            empty = {s for s, _ in captions_lane.uncaptioned(slugs)}
            if empty != set(slugs):
                fails.append(
                    f"pointed at an EMPTY captions/ directory the gate "
                    f"refused only {len(empty)} of {len(slugs)} episode(s) - "
                    f"it must refuse every one. A gate that goes quiet when "
                    f"its evidence disappears proves nothing.")
    finally:
        captions_lane.CAPTIONS_DIR = real_dir

    # An empty SELECTION is a clean selection, not a silent pass: the caller
    # is the one that must not act on nothing, and it has its own named stop.
    if captions_lane.uncaptioned([]) != []:
        fails.append("uncaptioned([]) did not return [] - the gate cannot "
                     "tell an empty selection from a clean one")

    if examined == 0:
        fails.append("examined ZERO episodes")

    print(f"inspected {examined} episode(s): {len(have)} with an .srt, "
          f"{len(lacking)} without; V16 examined {r.examined}")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - no episode can be given an air date before its captions "
          "exist" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
