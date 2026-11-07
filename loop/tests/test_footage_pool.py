"""The footage pool deletes only orphans, never a referenced clip, and stops
growing at its cap or near the disk floor (a note, exit 10) - 6 Nov 2026."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))
import footage_pool as P  # noqa: E402

fails = []
with tempfile.TemporaryDirectory() as td:
    img = Path(td) / "imagery"
    clips = img / "clips"
    clips.mkdir(parents=True)
    (clips / "used.mp4").write_bytes(b"u" * 1000)
    (clips / "food_used.mp4").write_bytes(b"f" * 1000)
    (clips / "orphan.org&").write_bytes(b"o" * 500)
    (img / "video_rights.json").write_text(json.dumps({"assets": [{"local_file": "clips/used.mp4"}]}))
    (img / "food_clips.json").write_text(json.dumps({"clips": [{"file": "clips/food_used.mp4"}]}))
    rc, line = P.guard(clips, img, free_gib=lambda: 50.0, floor_gib=6, cap_gib=20)
    left = sorted(p.name for p in clips.iterdir())
    if left != ["food_used.mp4", "used.mp4"]:
        fails.append(f"kept {left}: an orphan stayed or a referenced clip went")
    if rc != 0:
        fails.append(f"room to harvest gave rc={rc}: {line}")
    rc, line = P.guard(clips, img, free_gib=lambda: 50.0, floor_gib=6, cap_gib=0.0000001)
    if rc != P.HOLD_EXIT or not line.startswith("note:"):
        fails.append(f"a pool at its cap did not stop the harvest with a note: {rc} {line}")
    rc, line = P.guard(clips, img, free_gib=lambda: 7.0, floor_gib=6, cap_gib=20)
    if rc != P.HOLD_EXIT:
        fails.append(f"7 GiB free over a 6 GiB floor did not stop the harvest: {rc}")
    if sorted(p.name for p in clips.iterdir()) != ["food_used.mp4", "used.mp4"]:
        fails.append("a hold deleted a referenced clip")
    (img / "broken.json").write_text("{not json")
    (clips / "orphan2").write_bytes(b"x")
    try:
        P.guard(clips, img, free_gib=lambda: 50.0, floor_gib=6, cap_gib=20)
        fails.append("an unreadable manifest still let orphans be deleted")
    except RuntimeError:
        pass
    if not (clips / "orphan2").exists():
        fails.append("a clip was deleted while a manifest could not be read")

sh = (ROOT / "bin" / "batch-session.sh").read_text()
h = sh[sh.index("harvest_footage() {"):]
if not ("loop/footage_pool.py guard" in h and h.index("footage_pool.py") < h.index("research/wide_footage.py")):
    fails.append("the harvest downloads without asking the pool cap")

if fails:
    print("FAIL test_footage_pool")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_footage_pool: orphans only, never a referenced clip, stops at the cap and the floor")
