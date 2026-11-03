"""A long-form picture is ONLY moving imagery of the subject (owner 2026-11-03).

Her words, after "Why are deep-sea creatures so big?" came out as particle
filler, text cards and diagrams: "it should just be a video with moving imagery
of large deep-sea creatures and thats it nothing else". Then: "cant u just make
images move as long as u want?!" - never hold an episode for a footage
shortfall.

Proves, where the picture is built (visuals/longform_picture.py) and where it
is rendered (visuals/assemble.py):
  1. a plan built from a short footage pool is footage first, then the same
     spans slowed (each at most 3 times, never back to back), then moving
     photographs - and covers the narration exactly;
  2. a plan holding any shot that is not footage or a photograph FAILS;
  3. a shortfall never stops; only zero footage AND zero photos is a NAMED
     STOP (NO_SUBJECT_PICTURE);
  4. assemble.py renders a plan full of text cards, diagrams and filler beats
     without drawing a single one of them;
  5. LOW_DISK: under 15 GB free, a shot or a drawn beat stops before writing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import longform_picture as LP  # noqa: E402
import disk_guard  # noqa: E402

fails: list[str] = []


def check(name, ok, why=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


def clip(i, clean):
    return {"post_id": f"t:{i}", "title": f"Giant isopod {i}", "source_org": "NOAA",
            "required_credit": "NOAA Ocean Exploration",
            "clean_windows": [{"start": 0.0, "end": clean}], "treatment": "as-shot"}


def photo(i, rel="p.jpg"):
    return {"local_file": rel if i == 0 else f"p{i}.jpg", "title": f"Giant isopod photo {i}",
            "treatment": "photo", "commercial_use_permitted": True,
            "required_credit": "NOAA"}


# ---- 1. footage first, then slowed reuse, then moving photographs --------
clips = [clip(0, 20.5), clip(1, 16.5)]           # ~36 s of clean footage
total = 300.0
shots = LP.build(total, clips, [photo(0), photo(1)])
kinds = Counter(s["kind"] for s in shots)
check("only footage and photographs", set(kinds) <= {"footage", "photo"}, str(kinds))
check("covers the narration exactly",
      abs(sum(s["seconds"] for s in shots) - total) < 0.05,
      f"{sum(s['seconds'] for s in shots)} of {total}")
order = [s["kind"] for s in shots]
check("footage comes before photographs",
      "photo" not in order or "footage" not in order[order.index("photo"):], str(order))
showings = Counter((s["key"], s["start"]) for s in shots if s["kind"] == "footage")
check("a span is on screen at most 3 times", max(showings.values()) <= 3, str(showings))
slowed = [s for s in shots if s["kind"] == "footage" and s["speed"] < 1]
check("reuse is slowed to 0.5-0.75x", slowed and all(0.5 <= s["speed"] <= 0.75 for s in slowed),
      str([s["speed"] for s in slowed]))
check("a reuse has a different framing than the first showing",
      all((s["zoom"], tuple(s["pan"])) != (1.0, (0.5, 0.5)) for s in slowed))
b2b = [i for i in range(1, len(shots)) if shots[i]["key"] == shots[i - 1]["key"]
       and (shots[i].get("showing", 1) > 1 or shots[i]["kind"] == "photo")]
check("a reuse never follows its own clip", not b2b, str(b2b))
ph = [s["seconds"] for s in shots if s["kind"] == "photo"]
check("photographs move for 8-15 s each", ph and all(8 <= x <= 15 for x in ph[:-1]), str(ph))

# ---- 2. a plan with anything else on screen fails ------------------------
for bad in ({"kind": "drawn", "segment": "text_beat", "seconds": 4.0, "key": "x"},
            {"kind": "drawn", "segment": "ambient_drift", "seconds": 4.0, "key": "y"},
            {"kind": "photo", "asset": {"treatment": "plate"}, "seconds": 9.0, "key": "z"},
            {**shots[0], "captions": True}):
    try:
        LP.check(shots[:1] + [bad])
        check(f"refuses {bad.get('segment') or bad.get('asset', {}).get('treatment') or 'captions'}",
              False, "check() passed it")
    except LP.NotSubjectPicture:
        check(f"refuses {bad.get('segment') or bad.get('asset', {}).get('treatment') or 'captions'}", True)

# ---- 3. a shortfall never stops; only nothing-at-all is a NAMED STOP -----
try:
    LP.build(600.0, [], [])
    check("zero footage and zero photos is a NAMED STOP", False, "build() returned")
except LP.NoSubjectPicture as e:
    check("zero footage and zero photos is a NAMED STOP",
          e.code == "NO_SUBJECT_PICTURE" and "NO_SUBJECT_PICTURE" in str(e), str(e))
for name, cl, ph_ in (("photos only", [], [photo(0)]), ("one short clip only", [clip(0, 9.0)], [])):
    try:
        s = LP.build(600.0, cl, ph_)
        check(f"a shortfall still fills 10 min ({name})",
              abs(sum(x["seconds"] for x in s) - 600) < 0.05)
    except Exception as e:                               # noqa: BLE001
        check(f"a shortfall still fills 10 min ({name})", False, repr(e))

# ---- 4. assemble.py draws none of the plan's cards, diagrams or filler ---
import assemble  # noqa: E402

tmp = tempfile.mkdtemp(prefix="hwk-footage-only-")
try:
    from PIL import Image
    Image.new("RGB", (2400, 1350), (20, 60, 90)).save(os.path.join(tmp, "p.jpg"))
    plan = [{"segment": "text_beat", "seconds": 1.5, "narration": "a", "args": {}},
            {"segment": "definition_card", "seconds": 1.5, "narration": "b", "args": {}},
            {"segment": "ambient_drift", "seconds": 1.5, "narration": "c", "args": {}}]
    pp = os.path.join(tmp, "why-are-deep-sea-creatures-so-big.json")
    json.dump(plan, open(pp, "w"))
    drawn = []
    real_rb, real_dir = assemble.render_beat, LP.IMAGERY_DIR
    real_sc, real_sp = LP.subject_clips, LP.subject_photos
    assemble.render_beat = lambda b, *a, **k: drawn.append(b["segment"]) or (_ for _ in ()).throw(
        AssertionError(f"drew a {b['segment']} beat"))
    LP.IMAGERY_DIR = tmp
    LP.subject_clips = lambda slug, assets=None: []
    LP.subject_photos = lambda slug, stills=None: [photo(0)]
    out = os.path.join(tmp, "out.mp4")
    try:
        r = assemble.assemble(pp, out, music=False)
        rec = json.load(open(out + ".footage.json"))
        check("assemble draws no card, diagram or filler beat", not drawn, str(drawn))
        check("the master's record lists only footage and photos",
              rec["picture"] == "footage-only"
              and {s["kind"] for s in rec["shots"]} <= {"footage", "photo"}, str(rec)[:200])
        check("every beat carries a credit for Shorts", all(rec["beats"].values()), str(rec["beats"]))
    except Exception as e:                               # noqa: BLE001
        check("assemble draws no card, diagram or filler beat", False, repr(e)[:300])
    try:
        assemble.assemble(pp, out, music=False, burn_captions=True)
        check("burned-in captions are refused", False, "assemble() burned them")
    except (ValueError, TypeError):
        check("burned-in captions are refused", True)
    assemble.render_beat = real_rb

    # ---- 5. LOW_DISK stops before anything is written --------------------
    real_free = disk_guard.free_bytes
    disk_guard.free_bytes = lambda path=None: 3 * 1024 ** 3
    try:
        target = os.path.join(tmp, "low.mp4")
        try:
            LP.render_shot({"kind": "photo", "asset": photo(0), "seconds": 2.0,
                            "zoom": 1.15, "pan": [0, 1]}, target, 60)
            check("LOW_DISK stops a shot render", False, "rendered")
        except disk_guard.LowDisk as e:
            check("LOW_DISK stops a shot render",
                  e.code == "LOW_DISK" and not os.path.exists(target), str(e))
        wd = os.path.join(tmp, "work")
        os.makedirs(wd)
        try:
            assemble.render_beat(plan[0], 0, wd, 1.0, frames=30)
            check("LOW_DISK stops a drawn beat before its PNG frames", False, "rendered")
        except disk_guard.LowDisk:
            check("LOW_DISK stops a drawn beat before its PNG frames", not os.listdir(wd),
                  str(os.listdir(wd)))
    finally:
        disk_guard.free_bytes = real_free
        LP.IMAGERY_DIR, LP.subject_clips, LP.subject_photos = real_dir, real_sc, real_sp
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"longform footage-only: {len(fails)} failure(s)")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("longform footage-only: all checks passed")
