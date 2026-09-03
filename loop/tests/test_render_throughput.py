"""Render throughput may rise; the timing contract may not move with it.

The Mac is the physical constraint at 4 episodes a week, so `bin/batch-session.sh`
now overlaps rendering with narration. Overlapping is a scheduling change and
must stay one. Two things it could quietly break, both of which would ship as a
finished video with the last word cut off:

  1. **Audio stops being the timing authority.** `visuals/assemble.py` measures
     each beat from its narration wav and renders the picture to that. A
     throughput change that passed a duration, a frame count or an estimate
     would decouple picture from voice, and the video would still play.
  2. **A half-narrated episode reaches the assembler.** The whole safety of
     overlapping rests on rendering only what is finished. If the poll and the
     final sweep ever disagreed about what "finished" means, an episode would
     be assembled against a partial audio directory - and the render would be
     short by exactly the beats that had not been voiced yet.

Proven negatively where a negative proof is possible: the guard is shown to
catch a rewritten batch script that renders unconditionally.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))

BATCH = os.path.join(ROOT, "bin", "batch-session.sh")
ASSEMBLE = os.path.join(ROOT, "visuals", "assemble.py")


def readiness_guard(text: str) -> bool:
    """Does this batch script gate rendering on COMPLETE audio?

    The test of completeness in this repo is "the plan's beat count equals the
    wav count". Written as a predicate so the negative proof can feed it a
    script that does not have one.
    """
    return bool(re.search(r"len\(json\.load\(open\(plan\)\)\)\s*==\s*"
                          r"len\(glob\.glob", text))


def check() -> list[str]:
    fails, examined = [], 0

    batch = open(BATCH).read()
    asm = open(ASSEMBLE).read()

    # -- 1. audio is still the timing authority --------------------------
    examined += 1
    if "AUDIO IS THE AUTHORITY" not in asm:
        fails.append("visuals/assemble.py no longer marks the audio as the "
                     "timing authority; a beat measured from anything else "
                     "lets picture and voice drift apart over ten minutes")
    examined += 1
    if not re.search(r"d\s*=\s*probe\(wav\)", asm):
        fails.append("visuals/assemble.py does not measure each beat from its "
                     "narration wav")

    # -- 2. the batch never overrides the assembler's timing -------------
    examined += 1
    for banned in ("--seconds", "--duration", "--frames", "--fps",
                   "--timing", "--estimate"):
        if banned in batch:
            fails.append(f"bin/batch-session.sh passes {banned} to the "
                         f"assembler. Timing is assemble.py's to decide from "
                         f"the audio; a throughput change may not touch it.")

    # -- 3. rendering is gated on COMPLETE audio -------------------------
    examined += 1
    if not readiness_guard(batch):
        fails.append("bin/batch-session.sh does not gate rendering on the wav "
                     "count matching the plan's beat count. With rendering "
                     "overlapping narration that is the only thing stopping a "
                     "half-narrated episode being assembled short.")

    # NEGATIVE PROOF: a script without that gate must be caught.
    examined += 1
    if readiness_guard("for slug in $(ls plans); do render $slug; done"):
        fails.append("the readiness guard accepts a batch script that renders "
                     "unconditionally - it is not actually checking anything")

    # -- 4. one definition of readiness, used by both paths --------------
    examined += 1
    if batch.count("renderable()") != 1:
        fails.append("bin/batch-session.sh does not define `renderable` "
                     "exactly once; two definitions of 'ready to render' is "
                     "the two-components-each-keeping-their-own-list failure")
    examined += 1
    if batch.count("$(renderable)") < 3:
        fails.append("the preview, the overlap poll and the final sweep do not "
                     "all three call `renderable`, so they could disagree "
                     "about what is finished")
    examined += 1
    if len(re.findall(r"len\(json\.load\(open\(plan\)\)\)\s*==\s*"
                      r"len\(glob\.glob", batch)) != 1:
        fails.append("bin/batch-session.sh contains more than one definition "
                     "of 'ready to render'; a second copy is how one path "
                     "skips an episode while another assembles it short")

    # -- 5. the overlap is on by default, and reversible ------------------
    # A throughput improvement nothing invokes is inert; a throughput change
    # with no way back is a one-way risk.
    examined += 1
    if "OVERLAP=1" not in batch:
        fails.append("the render/narration overlap is not on by default, so "
                     "the throughput change does nothing unless someone "
                     "remembers a flag")
    examined += 1
    if "--no-overlap" not in batch:
        fails.append("there is no way to fall back to the two-phase batch if a "
                     "render is ever found to starve the voice model")
    examined += 1
    if "--max-episodes" not in batch:
        fails.append("the session cannot be bounded, so at 4 episodes a week "
                     "the batch stays a single long marathon rather than "
                     "something that can be run nightly")

    # -- 6. it still holds the machine awake and stays resumable ---------
    examined += 1
    if "caffeinate" not in batch:
        fails.append("bin/batch-session.sh no longer holds the Mac awake; a "
                     "long batch dies on lid close")
    examined += 1
    if 'renders/${slug}-final.mp4" ] && return 0' not in batch:
        fails.append("the render step no longer skips an episode that is "
                     "already rendered, so an interrupted run restarts rather "
                     "than resumes")

    if examined == 0:
        fails.append("examined ZERO render-throughput cases")
    print(f"inspected {examined} render-throughput case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - rendering overlaps narration, and the audio is still "
          "the only thing that decides timing" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
