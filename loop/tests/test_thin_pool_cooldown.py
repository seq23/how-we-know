"""A thin footage pool fills with safe reuse/photos, never an early repeat.
Set HWK_OLD_PICTURE to run the identical behavior against the pre-fix module.
"""
import importlib.util
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "visuals"))
import longform_picture as LP
if os.environ.get("HWK_OLD_PICTURE"):
    spec = importlib.util.spec_from_file_location("old_picture", os.environ["HWK_OLD_PICTURE"])
    LP = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(LP)
clips = [{"post_id": f"clip:{i}", "title": f"animal {i}", "_subject": f"animal {i}",
          "required_credit": "NOAA", "clean_windows": [{"start": 0, "end": length} ]}
         for i, length in enumerate([33, 25, 9, 49, 5, 5])]
photos = [{"local_file": f"photo{i}.jpg", "title": f"animal {i % 6}",
           "_subject": f"animal {i % 6}", "required_credit": "NOAA"} for i in range(30)]
reel = LP.build(300, clips, photos)
assert reel and abs(sum(s["seconds"] for s in reel) - 300) < .001
seen, t = {}, 0
for s in reel:
    moment = (s["key"], s["start"])
    assert moment not in seen or t - seen[moment] >= 180 - 1e-6, (moment, t, seen.get(moment))
    t += s["seconds"]
    seen[moment] = t
assert any(s["kind"] == "photo" for s in reel)
assert any(s["kind"] == "footage" and s["speed"] < 1 for s in reel)
assert not LP.variety_problems(reel), LP.variety_problems(reel)
print("OK thin pool: full reel, slowed footage and photos, every repeat >= 180s")
