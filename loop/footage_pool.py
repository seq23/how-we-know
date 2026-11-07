#!/usr/bin/env python3
"""THE FOOTAGE POOL CAP: channel/imagery/clips never grows past its cap or into the disk floor.

    python loop/footage_pool.py guard     # exit 0: room to harvest; 10: no new clips tonight (a note)
    python loop/footage_pool.py report

6 Nov 2026: the pool was 14.7 GiB of a Mac with 11 GiB free, and the one
storage item nothing bounded (the weekly harvest added 166 clips on 2 Nov).

  * ORPHANS are deleted: a file in clips/ that no manifest under
    channel/imagery/ references can never be picked by any render (13 files,
    0.34 GiB on 6 Nov, among them the collided Kiska file #331 replaced).
  * A referenced clip is NEVER evicted: both channels' remakes and the
    Whisper Almanac reels draw on the clips of uploaded episodes.
  * Over POOL_CAP_GIB (default 20), or with less than the disk floor plus
    HARVEST_ROOM_GIB free, the harvest downloads nothing tonight: exit 10,
    "note: footage pool ..." - a note, never a red; re-judged every night.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGERY = ROOT / "channel" / "imagery"
CLIPS = IMAGERY / "clips"
POOL_CAP_GIB = float(os.environ.get("POOL_CAP_GIB", "20"))
HARVEST_ROOM_GIB = 2.0
HOLD_EXIT = 10


def referenced(imagery: Path = IMAGERY) -> set[str]:
    refs: set[str] = set()
    for f in glob.glob(str(imagery / "*.json")):
        try:
            text = Path(f).read_text()
            json.loads(text)
        except (OSError, ValueError):
            # an unreadable manifest means we cannot tell what is used:
            # nothing may be called an orphan
            raise RuntimeError(f"cannot read {f}; no clip is treated as an orphan")
        refs |= {os.path.basename(m) for m in re.findall(r'clips/([^"\\\\]+)', text)}
    return refs


def pool_bytes(clips: Path = CLIPS) -> int:
    return sum(p.stat().st_size for p in clips.iterdir() if p.is_file()) if clips.exists() else 0


def prune_orphans(clips: Path = CLIPS, imagery: Path = IMAGERY, dry: bool = False) -> list[tuple[str, int]]:
    refs = referenced(imagery)
    if not refs:
        raise RuntimeError("no manifest references any clip; refusing to treat the whole pool as orphans")
    out = []
    for p in sorted(clips.iterdir()) if clips.exists() else []:
        if p.is_file() and not p.name.startswith(".") and p.name not in refs:
            out.append((p.name, p.stat().st_size))
            if not dry:
                p.unlink()
    return out


def guard(clips: Path = CLIPS, imagery: Path = IMAGERY, free_gib=None, floor_gib: float | None = None,
          cap_gib: float = POOL_CAP_GIB) -> tuple[int, str]:
    gone = prune_orphans(clips, imagery)
    freed = sum(b for _, b in gone) / 2 ** 30
    size = pool_bytes(clips) / 2 ** 30
    free = free_gib() if free_gib else shutil.disk_usage(ROOT).free / 2 ** 30
    if floor_gib is None:
        floor_gib = float(os.environ.get("DISK_FLOOR_GIB", "6"))
    base = f"footage pool {size:.1f} GiB (cap {cap_gib:g}); {len(gone)} orphan clip(s) deleted ({freed:.2f} GiB); {free:.1f} GiB free"
    if size >= cap_gib:
        return HOLD_EXIT, f"note: {base} - at its cap, so no new clips tonight; the pool is re-judged nightly"
    if free < floor_gib + HARVEST_ROOM_GIB:
        return HOLD_EXIT, (f"note: {base} - under the disk floor plus {HARVEST_ROOM_GIB:g} GiB, "
                           f"so no new clips tonight")
    return 0, f"{base} - room to harvest"


def main(argv: list[str]) -> int:
    if argv[:1] == ["guard"]:
        rc, line = guard()
        print(line)
        return rc
    if argv[:1] == ["report"]:
        print(f"footage pool {pool_bytes() / 2 ** 30:.2f} GiB, "
              f"{len(prune_orphans(dry=True))} orphan(s)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
