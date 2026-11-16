"""A calm footage set shows only its configured subjects (16 Nov 2026).

"The night sky and stars" was taken out of calm-night (the brand says no
starfields; two Neville renders failed the frame check on a starfield the
judge read as CG). Its already-harvested clips must leave the pool with it,
while every configured subject's clips stay.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "loop"))
import whisper_lane as WL  # noqa: E402
import whisper_reel as R   # noqa: E402

c = WL.cfg()
subjects = [e["subject"] for e in c["calm_footage"]["sets"]["calm-night"]]
assets = [{"calm_set": "calm-night", "subject": s, "seconds": 60, "post_id": f"ok{i}"}
          for i, s in enumerate(subjects)]
assets.append({"calm_set": "calm-night", "subject": "the night sky and stars", "seconds": 60, "post_id": "star"})
got = {a["post_id"] for a in R._pool("calm:calm-night", assets, c)}
fails = []
if "star" in got:
    fails.append("a clip of a subject no longer in config is still in the pool")
if got != {f"ok{i}" for i in range(len(subjects))}:
    fails.append(f"configured subjects missing from the pool: {got}")
if any("star" in s.lower() for s in subjects):
    fails.append("calm-night still lists a starfield subject")
if not subjects:
    raise SystemExit("FAIL: calm-night has no subjects")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print(f"PASS: calm-night pool holds only its {len(subjects)} configured subjects")
