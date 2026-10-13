"""The first full food video: its contract, its hold in the upload lane, its plumbing.

Owner, 13 Oct 2026: the round-2 chocolate sample is approved ("MUCH better");
build the food lane out to publish "Bread, Steak, Chocolate: What's Inside?".
Her two notes the same day are part of the contract: LIMIT HUMAN HANDS (a
measured preference, noted above 15 %, failing above 30 %) and MESMERISING
(slow motion or composites >= 40 % of every segment, speed-ramped slow motion
for pours and drips, the richest clip first).

    .venv/bin/python loop/tests/test_food_episode.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "voice"))
os.environ.setdefault("LOOP_DRY_RUN", "1")

FAILS: list[str] = []
N = 0
SLUG = "why-bread-rises-steak-browns-chocolate-snaps"


def check(cond, msg: str) -> None:
    global N
    N += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        FAILS.append(msg)


import food  # noqa: E402
import food_episode as FE  # noqa: E402
import food_motion as FM  # noqa: E402

# ------------------------------------------------------------ 1. the contract
fx = json.loads((ROOT / "loop" / "tests" / "fixtures" / "food_episode_spec.json").read_text())
check(FE.check_episode(fx) == [], f"the synthetic episode passes as built: {FE.check_episode(fx)[:3]}")
check(fx["piece_order"] == ["open", "chocolate", "bread", "steak"] + ["tail"],
      "segment order: chocolate first, then bread, then steak")
import validate as V  # noqa: E402
res = V.v55_food_episode().as_dict()
check(not res["failures"], f"V55 passes on the real repo: {res['failures']}")
check(res["examined"] >= 1, "V55 examined at least one food episode")
# hands: a preference with a note, a failure past 30 %
h20 = V._food_mark_hands(fx, 0.20)
check(not FE.check_episode(h20) and food.hands_notes({"shots": [x for p in h20["pieces"] for x in p["shots"]]}),
      "hands on 20 %: passes, with a note")
check(any("hands" in p for p in FE.check_episode(V._food_mark_hands(fx, 0.35))), "hands on 35 %: fails")
# spectacle per segment
seg = next(p for p in fx["pieces"] if p["piece"] == "chocolate")
check(seg["screen_time"]["spectacle_share"] >= food.SPECTACLE_SHARE_MIN,
      f"the chocolate segment is >= 40 % spectacle ({seg['screen_time']['spectacle_share']:.0%})")
flat = {"shots": [{**x, "treatment": "play", "composite": False} if x.get("treatment") in
                  ("slowmo", "wall", "kaleido") else x for x in seg["shots"]],
        "piece": "chocolate", "ai_assets": seg["ai_assets"], "clip_licences": seg["clip_licences"],
        "credits": seg["credits"], "captions": {"burned_in": True}, "altered_content": True}
check(any("spectacle" in p for p in food.check_spec(flat)), "a segment with no slow motion fails spectacle")
# the sample (one question, five composites) keeps its own approved contract
sample = json.loads((ROOT / "channel" / "specs" / "food-sample-chocolate.json").read_text())
check(food.check_spec(sample) == [], f"the approved round-2 sample still passes: {food.check_spec(sample)}")

# ------------------------------------------------- 2. slow motion, speed-ramped
pour = {"uses": ["pour", "liquid"], "sha256": "x"}
sear = {"uses": ["sear", "sizzle"], "sha256": "y"}
g = FM.graph(pour, 4.0, "slowmo", 12.0)
check(g["ramp"] and "if(lt(T," in g["vf"] and g["speed"] == FM.RAMP_TO,
      "a pour in slow motion is speed-ramped from real speed")
g2 = FM.graph(sear, 4.0, "slowmo", 12.0)
check(not g2["ramp"] and g2["speed"] == FM.SLOWMO, "a sear in slow motion is a steady 2x")
check(food.treatment_for({"uses": ["sizzle"]}, "body") == "slowmo"
      and food.treatment_for({"uses": ["flame"]}, "body") == "slowmo",
      "sizzles and flames default to slow motion in the body")

check(FM._span({"black": {"spans": [[0.0, 2.867]]}}, 9.17)[0] > 2.867,
      "a clip that opens on black is never used from its black (pixabay:71743 put a black frame in the cold open)")
check(FM._span({"black": {"spans": [[7.0, 9.17]]}}, 9.17)[1] < 7.0, "nor from the black it closes on")

# ------------------------------------------------------ 3. parse and pieces
paras = food.parse(ROOT / "scripts" / "food" / f"{SLUG}.md")
pcs = food.pieces(paras)
check(list(pcs) == ["open", "chocolate", "bread", "steak", "tail"], f"pieces in order: {list(pcs)}")
for s in food.SEGMENTS:
    first = paras[pcs[s][0]]["text"]
    check(first.endswith("?") and paras[pcs[s][0]]["phase"] == "opening",
          f"{s} opens by saying its question, cut like an opening: {first!r}")
words = sum(len(p["text"].split()) for p in paras)
check(4300 <= words <= 5300, f"{words} narrated words: 28-32 minutes at the sample's measured pace")
check(not any("[HUMAN]" in p["text"] for p in paras),
      "no [HUMAN] beat: food ships no producer POV until her food interview")
sp = food.parse(ROOT / "scripts" / "food" / "why-does-chocolate-melt-in-your-mouth-not-your-hand.md")
check(sum(1 for p in sp if p["phase"] == "opening") == 1,
      "a single-question script keeps the sample's cutting (no segment re-hook)")

# ------------------------------------------------- 4. the queue and the lanes
import batch_queue as BQ  # noqa: E402
import domains as D  # noqa: E402
import backfill as BF  # noqa: E402
check(SLUG in [r["slug"] for r in BQ.food_entries()], "the episode is a queued food entry")
check(SLUG not in [r["slug"] for r in BQ.written_entries()],
      "the nightly batch never plans, narrates or renders it (not a written entry)")
check(SLUG not in [r["slug"] for r in BQ.unwritten_entries()],
      "the Monday lane never authors it (not an unwritten entry)")
check(D.domain_of_slug(SLUG) == "food-science", "domain_of_slug reads scripts/food/")
spec_kind = json.loads((ROOT / "channel" / "specs" / f"{SLUG}.json").read_text()).get("kind")
pending = [s for s, _, _ in BF.library_pending(assets=lambda s: (Path("r.mp4"), Path("t.jpg")))]
if spec_kind == "food-episode" and not FE.check_episode_files(ROOT / "channel" / "specs" / f"{SLUG}.json"):
    check(SLUG in pending, "a passing food episode is pending for the upload lane")
else:
    check(SLUG not in pending, "a food episode without a passing spec is HELD by library_pending")
    try:
        BF.upload_one(None, "", SLUG, "q", Path("r.mp4"), Path("t.jpg"), None)
        check(False, "upload_one refused a failing food episode")
    except BF.FoodContractRefused as e:
        check("food contract" in str(e), f"upload_one refuses it by name: {str(e)[:90]}")

# ---------------------------------------------- 5. R2: a render over the cap
import r2  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    os.environ.pop("LOOP_DRY_RUN", None)
    try:
        b = r2.LocalBackend(d / "shelf")
        b.part_bytes = 1000
        f = d / "big.mp4"
        f.write_bytes(os.urandom(3500))
        b.put(f, "renders/x-final.mp4")
        parts = sorted(p.name for p in (d / "shelf" / "renders").iterdir() if ".part" in p.name)
        check(len(parts) == 4, f"a file over the cap is shelved as parts: {parts}")
        check(b.same_as(f, "renders/x-final.mp4")[0], "the sidecar names the whole file (size + sha256)")
        got = b.get("renders/x-final.mp4", d / "back.mp4")
        check(got.read_bytes() == f.read_bytes(), "get reassembles the parts byte for byte")
        (d / "shelf" / "renders" / parts[1]).write_bytes(b"tampered")
        try:
            b.get("renders/x-final.mp4", d / "bad.mp4")
            check(False, "a corrupt part is refused")
        except r2.R2Unavailable as e:
            check(e.code == "PARTS_CORRUPT" and not (d / "bad.mp4").exists(),
                  "a corrupt part is refused and nothing is left behind")
        b.delete("renders/x-final.mp4")
        check(not list((d / "shelf" / "renders").iterdir()), "delete removes every part and the sidecar")
        small = d / "small.mp4"
        small.write_bytes(b"x" * 500)
        b.put(small, "renders/y-final.mp4")
        check(not list((d / "shelf" / "renders").glob("y-final.mp4.part*")),
              "a file under the cap is one object, as before")
    finally:
        os.environ["LOOP_DRY_RUN"] = "1"

print(f"examined {N} case(s)")
if FAILS:
    print("FAIL: " + "; ".join(FAILS[:5]))
    raise SystemExit(1)
