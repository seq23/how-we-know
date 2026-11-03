"""Owner-approved renders: never re-rendered, moved aside, pruned or re-checked.

channel/approved_renders.json holds {slug: {sha256, bytes, approved, by, why}}.
A render is protected only while the file on disk IS the approved bytes (size
first, sha256 on demand), so an approval can never cover a different cut.
Every code path that moves a `renders/<slug>-final.mp4` aside or re-renders it
asks `protected(slug)` first.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "channel" / "approved_renders.json"
RENDERS = ROOT / "renders"


def load() -> dict:
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def protected(slug: str, renders: Path | None = None) -> bool:
    """True when renders/<slug>-final.mp4 is the owner-approved cut."""
    rec = load().get(slug)
    if not rec:
        return False
    f = (renders or RENDERS) / f"{slug}-final.mp4"
    if not f.exists() or f.stat().st_size != int(rec.get("bytes") or -1):
        return False
    return _sha(f) == rec.get("sha256")
