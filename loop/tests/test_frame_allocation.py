"""The rendered video must never be shorter than the narration it carries.

visuals/assemble.py rounded each beat's duration to a whole frame on its own.
Half a frame lost per beat, sixty-odd beats, and the video came out 50-90 ms
SHORTER than its audio - so the final `-shortest` mux trimmed the tail of the
last spoken beat. Four materials renders shipped that way and V13 caught them.

Proved on the REAL beat durations of those four episodes, not on invented
numbers, because the defect is an accumulation and only real data accumulates
the same way.

  1. the old per-beat rounding reproduces the exact shortfall V13 reported
  2. the drift-corrected allocation is never short, on any of the four
  3. it is never short on synthetic worst cases either - every beat landing
     exactly on a half-frame boundary, which is where rounding is maximally
     wrong
  4. the frame count is still a whole number of frames per beat, and at least
     one, so no beat vanishes

Hard-fails if it runs zero checks.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))

FPS = 30
CHECKS = 0

# The four V13 caught, and what it measured. The audio is on disk; these are
# the numbers the validator reported, kept so a regression is recognisable.
KNOWN_SHORT = {
    "how-does-tempered-glass-shatter": -0.051,
    "how-is-damascus-steel-made": -0.089,
    "how-strong-is-graphene": -0.067,
    "what-is-carbon-fiber-made-of": -0.082,
}


def check(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"{label}: {detail or 'failed'}")
    print(f"  ok  {label}")


def old_allocation(durs: list) -> int:
    """What assemble.py did before 2026-09-05: round each beat on its own."""
    return sum(max(1, int(round(d * FPS))) for d in durs)


def new_allocation(durs: list) -> list:
    """What it does now: allocate across the episode, ceil the last beat."""
    frames, emitted = [], 0
    for i, _ in enumerate(durs):
        due = sum(durs[:i + 1])
        want = (math.ceil(due * FPS) if i == len(durs) - 1
                else int(round(due * FPS)))
        frames.append(max(1, want - emitted))
        emitted += frames[-1]
    return frames


def probe(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True).stdout.strip()
    return float(out)


def main() -> int:
    # The generator must actually contain the fix, not just this test's copy.
    src = open(os.path.join(ROOT, "visuals", "assemble.py"),
               encoding="utf-8").read()
    check("assemble.py allocates frames across the episode",
          "frames=frames[i]" in src and "math.ceil(due * FPS)" in src,
          "the drift-corrected allocation is not in visuals/assemble.py")
    check("assemble.py asserts the allocation covers the narration",
          "the mux would clip the last beat" in src)

    examined = 0
    for slug, reported in KNOWN_SHORT.items():
        d = os.path.join(ROOT, "audio", slug)
        if not os.path.isdir(d):
            continue                      # audio lives on the Mac, not in CI
        wavs = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
        if not wavs:
            continue
        durs = [max(0.4, probe(os.path.join(d, w))) for w in wavs]
        total = sum(durs)
        examined += 1

        old_s = old_allocation(durs) / FPS
        check(f"{slug}: the old rounding really was short",
              old_s < total,
              f"old allocation gave {old_s:.3f}s for {total:.3f}s of audio")
        check(f"{slug}: the shortfall matches what V13 reported",
              abs((old_s - total) - reported) < 0.01,
              f"got {old_s - total:+.3f}s, V13 reported {reported:+.3f}s")

        frames = new_allocation(durs)
        new_s = sum(frames) / FPS
        check(f"{slug}: the new allocation is never short",
              new_s >= total,
              f"new allocation gave {new_s:.3f}s for {total:.3f}s of audio")
        check(f"{slug}: and does not overshoot by more than a frame",
              new_s - total <= 1.0 / FPS + 1e-9,
              f"overshoot {new_s - total:.4f}s")
        check(f"{slug}: every beat keeps at least one frame",
              all(f >= 1 for f in frames) and len(frames) == len(durs))

    if examined == 0:
        # CI has no audio. The synthetic cases below still have to run, and the
        # source checks above already ran, so this is a legitimate partial - but
        # it must be said out loud rather than passing silently.
        print("  note: no audio on this machine; real-episode checks skipped")

    # Worst case for rounding: every beat exactly on a half-frame boundary.
    half = [0.5 / FPS + 1.0] * 200
    check("synthetic half-frame beats: old rounding is short",
          old_allocation(half) / FPS < sum(half) - 1e-9,
          "the worst case did not reproduce the defect, so this proves nothing")
    check("synthetic half-frame beats: new allocation is not",
          sum(new_allocation(half)) / FPS >= sum(half) - 1e-9)

    odd = [0.4, 1.0 / 3, 2.0 / 7, 5.9999, 0.4]
    check("synthetic ragged beats: new allocation is not short",
          sum(new_allocation(odd)) / FPS >= sum(odd) - 1e-9)

    if CHECKS == 0:
        raise AssertionError("ran zero checks - an empty test proves nothing")
    print(f"\n{CHECKS} check(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
