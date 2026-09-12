"""What a harvester may `require` of the HOST, and how to tell if it is there.

One table, imported by both sides: research/imagery_video.py declares
`HARVESTER["requires"]` in these names, and loop/footage_lane.py checks them
BEFORE spawning the harvester. Two tables would be two components each keeping
their own list with no link — the defect class this repo names first.

Why this exists. Gates B and C of the video harvester read burned-in credits
with Apple's Vision framework off frames ffmpeg pulls from the clip. ubuntu-
latest has neither, and for every scheduled run of the footage lane the video
harvester failed each clip that passed the rights gate with a FileNotFoundError
on `ffmpeg` — reported as a rights rejection ("gate A-credit", 379/379 on run
34672456430) because the screener labelled every exception with the default
gate. A missing binary is not a rights outcome. It is a host that cannot run
the harvester, and it is named here as exactly that.

No imports beyond the standard library, on purpose: research/ must be able to
import this without pulling in the loop's state or config.
"""
from __future__ import annotations

import shutil
import sys

# name -> (what it is for, probe). A probe answers "present on THIS host".
HOST_TOOLS = {
    "ffmpeg": (
        "ffmpeg on PATH, to range-request one frame per probe time straight "
        "off the remote clip",
        lambda: shutil.which("ffmpeg") is not None,
    ),
    "vision-ocr": (
        "macOS with swiftc, to compile the Apple Vision OCR helper that reads "
        "the burned-in credit (gates B and C)",
        lambda: sys.platform == "darwin" and shutil.which("swiftc") is not None,
    ),
}


class UnknownHostTool(KeyError):
    """A harvester required something this table has no probe for.

    Loud on purpose: an unknown requirement silently treated as satisfied is a
    harvester that runs where it cannot finish, and one treated as missing is
    a harvester that never runs. Neither may pass quietly.
    """


def missing(requires) -> list[str]:
    """`name: what it is for` for every required tool this host lacks.

    Empty list means every requirement is met. Order is the declaration's.
    """
    out = []
    for name in list(requires or []):
        if name not in HOST_TOOLS:
            raise UnknownHostTool(
                f"{name!r} is not a host tool loop/host_tools.py knows how to "
                f"probe for (known: {', '.join(sorted(HOST_TOOLS))}). Add a "
                f"probe, or fix the harvester's `requires`.")
        desc, present = HOST_TOOLS[name]
        if not present():
            out.append(f"{name}: {desc}")
    return out
