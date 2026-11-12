"""Whisper Almanac's food-history reel draws on long food clips, part by part.

Her week (9 Nov 2026): the food-history sleep video is How We Know's
fact-checked food script, its Bread, Steak and Chocolate parts as segments. A
reel holds each shot 18 s and never repeats a clip inside 3 minutes (the rule
stays as it is), so a part needs 12 clips that can each hold an 18 s shot.
Before this the food parts drew on How We Know's deep-sea footage manifest
(no food at all) and the food clips were cut for 6-10 s beats. Proves:

  1. a '<food script>#<Part>' source is that part's food; any other is not;
  2. its pool is channel/imagery/food_clips.json's clips of THAT food only,
     long enough to hold a shot, with clean rights - never another part's,
     never a short clip, never an excluded one or one whose rights fail;
  3. a clip's clean windows skip its black spans, or follow its reviewed ranges;
  4. a stock clip still passes the stock licence gate the render re-runs
     (visuals/footage.verify);
  5. the repeat rule is unchanged (18 s shots, 3 minutes, 12 clips a part),
     and three parts of 12 long clips plan a reel that breaks no footage rule,
     while 11 clips in one part are refused (WHISPER_FOOTAGE_THIN);
  6. the long-clip harvest refuses off-subject clips (chicken wings in a steak
     part, cake in a bread part, a cow in a field) and accepts the food itself;
  7. the food long-form catalogue leaves the sleep clips out, and a food
     harvest keeps them.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "research"))
os.environ["LOOP_DRY_RUN"] = "1"

import food_footage as FF  # noqa: E402
import imagery_stock_video as STOCK  # noqa: E402
import whisper_reel as R  # noqa: E402

fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


FOOD_EP = "why-bread-rises-steak-browns-chocolate-snaps"
real = FF.load()["index"][0]               # a real pixabay record: its rights fields


def rec(part: str, i: int, secs: float = 40.0, **kw) -> dict:
    return {**real, "subject": f"{part}-long-pixabay-{i}", "key": f"{part}-long-pixabay-{i}",
            "segment": part, "source_id": str(9000 + i), "duration_s": secs, "ranges": None,
            "black": {"spans": []}, "local_file": f"clips/{part}{i}.mp4", "excluded": False,
            "lane": FF.LONG_LANE, **kw}


# ------------------------------------------------------------ 1. which part
check("1a a part of the food script is its food", R.food_part(f"{FOOD_EP}#Bread") == "bread",
      R.food_part(f"{FOOD_EP}#Bread"))
check("1b a deep-sea source or a calm set is not a food part",
      R.food_part("what-lives-in-mariana-trench") is None and R.food_part("calm:money-luxury") is None
      and R.food_part("what-lives-in-mariana-trench#Vents") is None, "matched")

# ------------------------------------------------------------ 2. the pool
index = ([rec("bread", i) for i in range(3)] + [rec("steak", 10)]
         + [rec("bread", 20, secs=12.0), rec("bread", 21, excluded=True),
            rec("bread", 22, licence="CC BY 4.0")])
ON = lambda r: True                        # CI holds no clips; the Mac check is 2d
pool = R.food_pool("bread", index, ON)
check("2a a part's pool is its own food's long clips with clean rights only",
      sorted(a["subject"] for a in pool) == [f"bread-long-pixabay-{i}" for i in range(3)],
      [a["subject"] for a in pool])
check("2b another part's clips never join it", all(a["segment"] == "bread" for a in pool), pool)
check("2c the reel pool for '<food script>#Steak' is the steak clips",
      [a["subject"] for a in R.food_pool("steak", index, ON)] == ["steak-long-pixabay-10"], "")
check("2d a clip this Mac does not hold is not counted", R.food_pool("bread", index, lambda r: False) == [], "")

fetched = {}
blob = b"clip-bytes"
import hashlib  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    real_img = FF.IMAGERY
    FF.IMAGERY = Path(td)
    try:
        good = rec("bread", 30, sha256=hashlib.sha256(blob).hexdigest(), download_url="https://x/a.mp4")
        bad = rec("bread", 31, sha256="0" * 64, download_url="https://x/b.mp4")
        res = FF.fetch_long_missing([good, bad], get=lambda url: blob)
        on_disk = sorted(p.name for p in (Path(td) / "clips").glob("*"))
    finally:
        FF.IMAGERY = real_img
check("2e a recorded clip missing on this Mac is fetched only when its bytes match the sha256",
      res["fetched"] == 1 and len(res["refused"]) == 1 and on_disk == ["bread30.mp4"], (res, on_disk))

# ------------------------------------------------------------ 3. windows
w = FF.clean_windows({"duration_s": 30.0, "black": {"spans": [[0.0, 2.5], [20.0, 21.0]]}})
check("3a clean windows skip black spans", w == [{"start": 2.5, "end": 20.0}, {"start": 21.0, "end": 30.0}], w)
check("3b a reviewed range is the window", FF.clean_windows({"duration_s": 90, "ranges": [[10, 40]]})
      == [{"start": 10.0, "end": 40.0}], "")
check("3c a clip whose black edges leave no 19 s window cannot hold a shot",
      not FF.holds({"duration_s": 30.0, "black": {"spans": [[10.0, 12.0]]}}), "held")

# ------------------------------------------------------------ 4. the licence gate at render
a = R.food_asset(rec("bread", 1))
ok, why = STOCK.stock_licence_ok(a)
check("4a a Pixabay food clip passes the stock licence gate the render re-runs", ok, why)
ok2, _ = STOCK.stock_licence_ok(R.food_asset(rec("bread", 2, attribution_required=True)))
check("4b a clip that requires attribution is refused by that gate", not ok2, "passed")

# ------------------------------------------------------------ 5. the reel rules
check("5a the repeat rule is unchanged: 18 s shots, 3 minutes, 12 clips a part",
      (R.SHOT_S, R.REPEAT_GAP_S, R.min_clips()) == (18.0, 180.0, 12), (R.SHOT_S, R.REPEAT_GAP_S))
parts = {p: [R.food_asset(rec(p, i)) for i in range(12)] for p in ("bread", "steak", "chocolate")}
segs = [(f"{FOOD_EP}#{p.capitalize()}", 1200.0) for p in parts]
shots = R.plan_reel(segs, [], pool_of=lambda s: parts[R.food_part(s)])
probs = R.reel_problems(shots, 3600.0)
check("5b three parts of 12 long clips each plan a full reel that breaks no footage rule",
      shots and not probs and all(s["asset"]["segment"] == R.food_part(segs[s["segment"]][0]) for s in shots),
      probs[:3])
short = {**parts, "chocolate": parts["chocolate"][:11]}
try:
    R.plan_reel(segs, [], pool_of=lambda s: short[R.food_part(s)])
    thin = False
except R.FootageThin:
    thin = True
check("5c a part with 11 long clips is refused, never padded", thin, "planned")
real_pool = R.food_pool
R.food_pool = lambda part, index=None: parts[part]
try:
    check("5d a food part with 12 long clips is pictureable (the lane voices it)",
          R.pictureable(f"{FOOD_EP}#Bread", []), "not pictureable")
finally:
    R.food_pool = real_pool

# ------------------------------------------------------------ 6. the harvest gate
cases = {("steak", "bbq, barbecue, chicken wings, grill"): False,
         ("bread", "flour, cake, dessert, sweets"): False,
         ("steak", "beef, meadow, agriculture, cow, animal"): False,
         ("steak", "steak, grill, meat, beef, food"): True,
         ("bread", "bread, food, healthy, delicious"): True,
         ("chocolate", "chocolate, candy, sugar"): True,
         ("chocolate", "chocolate, 3d, render"): False}
got = {k: FF._long_head_ok({"title": k[1], "item_url": ""}, k[0]) for k in cases}
check("6a the long-clip harvest takes the food itself and refuses off-subject clips",
      got == cases, {k: v for k, v in got.items() if v != cases[k]})

# ------------------------------------------------------------ 7. the food lane is untouched
import food as FOOD  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    img = Path(td)
    (img / "clips").mkdir()
    for r_ in (rec("bread", 1), {**rec("bread", 2), "lane": None, "subject": "bread-buns"}):
        (img / r_["local_file"]).write_bytes(b"x")
    (img / "food_clips.json").write_text(json.dumps({"index": [rec("bread", 1),
                                                               {**rec("bread", 2), "lane": None,
                                                                "subject": "bread-buns"}]}))
    real_img = FOOD.IMAGERY
    FOOD.IMAGERY = img
    try:
        cat = FOOD.catalogue()
    finally:
        FOOD.IMAGERY = real_img
check("7a the food long-form catalogue leaves the sleep clips out", set(cat) == {"bread-buns"}, sorted(cat))

with tempfile.TemporaryDirectory() as td:
    man = Path(td) / "food_clips.json"
    man.write_text(json.dumps({"index": [rec("bread", 1)], "rejected": []}))
    saved = (FF.MANIFEST, FF.resolve, FF.measure_hands, FF.score_richness, FF.sources_status)
    FF.MANIFEST = man
    FF.resolve = lambda shots=None, **k: {"picks": [], "misses": [], "by_source": {}}
    FF.measure_hands = FF.score_richness = lambda ix: ix
    FF.sources_status = lambda: {}
    try:
        out = FF.harvest(segments=["bread"])
    finally:
        FF.MANIFEST, FF.resolve, FF.measure_hands, FF.score_richness, FF.sources_status = saved
check("7b a food harvest of the same food keeps the sleep clips",
      [r_["subject"] for r_ in out["index"]] == ["bread-long-pixabay-1"], out["index"])

print(f"examined {examined} case(s), {len(fails)} failed")
if examined == 0:
    sys.exit("examined zero cases")
if fails:
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print("all green - each food part draws on its own long clips, and the repeat rule is unchanged")
