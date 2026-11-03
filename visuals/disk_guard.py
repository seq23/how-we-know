"""LOW_DISK preflight for every render step that writes to disk.

On 2026-11-03 the Data volume fell to 135 MB free during the render batch and
the Mac froze. The renderer writes a per-segment clip (and, for a drawn beat, a
folder of PNG frames) before encoding, so a nearly full disk is filled to the
last byte by the render itself. Every segment render calls `preflight()` first:
under MIN_FREE_GB free it stops with the NAMED STOP `LOW_DISK` and writes
nothing.
"""
from __future__ import annotations

import os
import shutil

MIN_FREE_GB = 15.0
# The volume user data lives on (macOS); elsewhere, the folder being written.
DATA_VOLUME = "/System/Volumes/Data"


class LowDisk(RuntimeError):
    """NAMED STOP LOW_DISK: too little free space to render safely."""
    code = "LOW_DISK"


def free_bytes(path: str | None = None) -> int:
    target = DATA_VOLUME if os.path.isdir(DATA_VOLUME) else (path or os.getcwd())
    while target and not os.path.exists(target):
        target = os.path.dirname(target)
    return shutil.disk_usage(target or "/").free


def preflight(path: str | None = None, min_free_gb: float = MIN_FREE_GB) -> None:
    free = free_bytes(path)
    if free < min_free_gb * 1024 ** 3:
        raise LowDisk(
            f"LOW_DISK: {free / 1024 ** 3:.1f} GB free, under the "
            f"{min_free_gb:.0f} GB a render needs; nothing was written. Free "
            f"space (old renders/*.work folders, superseded renders), then "
            f"re-run - the batch resumes where it stopped.")
