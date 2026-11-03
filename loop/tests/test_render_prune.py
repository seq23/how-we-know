"""At most one superseded render copy per episode is kept; the rest go to the
Trash; the live render and its records are never touched (2026-11-03: four
550 MB aside copies of one episode while the Mac ran out of disk)."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render_prune as RP  # noqa: E402

fails = []
with tempfile.TemporaryDirectory() as td:
    r, t = Path(td) / "renders", Path(td) / "trash"
    r.mkdir()
    names = ["ep-final.mp4", "ep-final.mp4.footage.json",
             "ep-final.mp4.pre-footage-only", "ep-final.mp4.pre-footage-only.1",
             "ep-final.mp4.picture-check-failed", "ep-final.mp4.picture-check-failed.footage.json",
             "other-final.mp4.below-picture-floor"]
    for i, n in enumerate(names):
        (r / n).write_text(n)
        os.utime(r / n, (time.time() - 100 + i, time.time() - 100 + i))
    moved = RP.prune(r, t)
    left = sorted(p.name for p in r.iterdir())
    want = ["ep-final.mp4", "ep-final.mp4.footage.json", "ep-final.mp4.picture-check-failed",
            "ep-final.mp4.picture-check-failed.footage.json", "other-final.mp4.below-picture-floor"]
    if left != want:
        fails.append(f"kept {left}, wanted {want}")
    if sorted(p.name for p in t.iterdir()) != ["ep-final.mp4.pre-footage-only",
                                                 "ep-final.mp4.pre-footage-only.1"]:
        fails.append(f"trash holds {sorted(p.name for p in t.iterdir())}")
    if not moved:
        fails.append("examined nothing")
for f in fails:
    print("FAIL:", f)
print("render prune:", "FAILED" if fails else "ok - one aside copy per episode, live render untouched")
sys.exit(1 if fails else 0)
