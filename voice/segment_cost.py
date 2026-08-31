#!/usr/bin/env python
"""segment_cost.py - is per-CALL overhead worth fighting, or is cost per SECOND?

The question behind it: 1,016 short beats is ~60 calls per episode. If a large
fixed cost is paid per generate() call, fewer/longer segments would cut the job
substantially. If cost is proportional to audio produced, longer segments buy
nothing and the segmentation must stay as it is.

Method - free, no extra inference. Each finished beat wav gives:
    duration  = the audio produced
    wall time = mtime(beat i) - mtime(beat i-1), because narrate_all.py writes
                one file per generate() and writes it atomically on completion
Least-squares fit of  wall = a + b * duration  over the run's own beats:
    a = fixed seconds per call    b = seconds per second of audio produced

Decision rule: merging N beats into one call saves (N-1)*a. That is worth doing
only if a is a large fraction of the mean per-beat wall time. It also costs the
timing contract: visuals/assemble.py mounts beat i's visual to the measured
duration of audio/<ep>/{i:04d}.wav, so any merge must be re-split at exactly the
beat boundary - and a split point guessed from silence drifts, which puts the
picture out of sync with the voice. So the bar for merging is high.

Usage:  segment_cost.py [audio/<episode-slug> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent


def collect(d: Path):
    """(duration, wall_seconds) per beat, in write order."""
    wavs = sorted(d.glob("[0-9][0-9][0-9][0-9].wav"), key=lambda p: p.stat().st_mtime)
    rows = []
    for prev, cur in zip(wavs, wavs[1:]):
        wall = cur.stat().st_mtime - prev.stat().st_mtime
        if wall <= 0 or wall > 3600:          # a resume gap is not a generation
            continue
        info = sf.info(str(cur))
        rows.append((info.duration, wall, cur.name))
    return rows


def main() -> int:
    dirs = [Path(a) for a in sys.argv[1:]] or \
           sorted(p for p in (ROOT / "audio").iterdir()
                  if p.is_dir() and not p.name.startswith("."))
    rows = []
    for d in dirs:
        r = collect(d)
        if r:
            print(f"{d.name}: {len(r)} consecutive beat pairs")
            rows += r
    if len(rows) < 4:
        print("error: need at least 4 consecutive beats to fit; refusing to "
              "report a number from nothing.", file=sys.stderr)
        return 2

    dur = np.array([r[0] for r in rows])
    wall = np.array([r[1] for r in rows])
    A = np.vstack([np.ones_like(dur), dur]).T
    (a, b), *_ = np.linalg.lstsq(A, wall, rcond=None)
    pred = a + b * dur
    ss_res = float(((wall - pred) ** 2).sum())
    ss_tot = float(((wall - wall.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")

    print(f"\nn = {len(rows)} beats")
    print(f"mean beat audio      {dur.mean():7.2f} s")
    print(f"mean wall per beat   {wall.mean():7.1f} s")
    print(f"realtime factor      {dur.sum()/wall.sum():7.4f} x")
    print(f"\nfit  wall = a + b*duration      R^2 = {r2:.3f}")
    print(f"  a (fixed per call)   {a:7.1f} s")
    print(f"  b (per second audio) {b:7.1f} s/s")
    frac = a / wall.mean() if wall.mean() else 0.0
    print(f"\nfixed cost is {frac*100:.0f}% of the mean beat")
    print(f"merging beats 4-to-1 would save ~{frac*0.75*100:.0f}% of total time")
    if frac < 0.25:
        print("VERDICT: per-call overhead is NOT dominant. Longer segments buy "
              "little, and merging would put the assemble.py timing contract at "
              "risk for that little. Keep one wav per beat.")
    else:
        print("VERDICT: per-call overhead IS material. Merging is worth costing "
              "out - but only with an exact re-split at beat boundaries, since "
              "assemble.py takes each beat's measured duration as authority.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
