"""Whisper Almanac's slow painting (her ruling 16 Nov 2026).

  a. the painter keeps the spec: a stroke every 4-8 s fading in over 2-3 s,
     never a cut; every frame 10-20 % luma, warm, no pure white; the same
     topic paints the same picture and another topic a different one;
  b. the paint gate passes a painted frame and fails blue, white, too dark,
     too bright and words on screen;
  c. which picture a render gets: a NEW Neville/Money video is painted; one
     rendered before, a sleep-history video, or any after a "footage"
     verdict keeps footage; a kit's recorded picture never changes;
  d. the day-30 verdict: before 30 days nothing is judged; footage returns
     only when paint is worse on BOTH % viewed and view duration; judged once;
  e. a painted kit is not refused for having no footage set.
Hard-fails on zero checks.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"
import whisper_frame_check as WFC                           # noqa: E402
import whisper_lane as WL                                   # noqa: E402
import whisper_paint as WP                                  # noqa: E402
import whisper_scorecard as SC                              # noqa: E402
import whisper_upload as WU                                 # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="whisper-paint-"))
fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


# a. the painter
SECS = 120
runs = list(WP.frames("neville-sats-01", SECS))
total = sum(n for _, n in runs)
check("a. the frame count matches the length", total == SECS * WP.FPS, total)
arrs = [np.frombuffer(b, np.uint8).reshape(WP.H, WP.W, 3) for b, _ in runs]
lum = [WP.luma(a.astype(np.float32)) for a in arrs[::5]]
check("a. every frame 10-20 % luma", all(WP.LUMA_BAND[0] <= y <= WP.LUMA_BAND[1] for y in lum),
      (min(lum), max(lum)))
holds = [n for _, n in runs if n > 1]
strokes = len(holds)
check("a. one stroke every 4-8 s", SECS / 8 - 2 <= strokes <= SECS / 4 + 2, strokes)
steps = [float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) for a, b in zip(arrs, arrs[1:])]
check("a. no cuts: no frame jumps from the one before", max(steps) < 3.0, max(steps))
last = arrs[-1].astype(np.int16)
check("a. warm only, no pure white",
      float(((last[..., 2] > last[..., 0] + 8) & (last[..., 2] > last[..., 1] + 8)).mean()) < 0.01
      and not ((last >= 240).all(axis=2)).any())
same = next(iter(WP.frames("neville-sats-01", 20)))[0]
other = next(iter(WP.frames("affirmations-money-2026-w47", 20)))[0]
check("a. the topic seeds the painting", same == runs[0][0] and other != runs[0][0])

money = next(iter(WP.frames("affirmations-money-2026-w47", 20, lane="money")))[0]
pal = WP.palette_for("money")
check("a. Money paints in its own luxury palette from config; Neville keeps the shared one",
      money != other and pal["colours"] != WP.PALETTE and WP.palette_for("neville")["colours"] == WP.PALETTE
      and "gold" in pal["colours"] and "champagne" in pal["colours"])
mrun = list(WP.frames("affirmations-money-2026-w47", 60, lane="money"))
marr = [np.frombuffer(b, np.uint8).reshape(WP.H, WP.W, 3) for b, _ in mrun][::5]
check("a. the Money palette stays 10-20 % luma, warm, never white",
      all(WP.LUMA_BAND[0] <= WP.luma(a.astype(np.float32)) <= WP.LUMA_BAND[1] for a in marr)
      and all(float(((a[..., 2].astype(int) > a[..., 0] + 8) & (a[..., 2].astype(int) > a[..., 1] + 8)).mean()) < 0.01
              and not ((a >= 240).all(axis=2)).any() for a in marr))

# b. the paint gate
def frame(rgb=None, arr=None) -> str:
    p = TMP / f"f{len(list(TMP.glob('f*.png')))}.png"
    Image.fromarray(arr if arr is not None else np.full((360, 640, 3), rgb, np.uint8)).save(p)
    return str(p)


painted = frame(arr=arrs[-1])
no_text = lambda paths: {}                                   # noqa: E731
check("b. a painted frame passes", WFC.check_paint_frames([(1.0, painted)], no_text)["gate"] == "paint")
blue = arrs[-1].copy()
blue[:, :320] = (20, 40, 90)
bad = {"blue": frame(arr=blue), "dark": frame((10, 8, 6)), "bright": frame((120, 90, 60))}
white = arrs[-1].copy()
white[:40, :40] = 255
bad["white"] = frame(arr=white)
for name, p in bad.items():
    try:
        WFC.check_paint_frames([(1.0, p)], no_text)
        check(f"b. a {name} frame fails", False, "passed")
    except WFC.PictureCheckFailed:
        check(f"b. a {name} frame fails", True)
try:
    WFC.check_paint_frames([(1.0, painted)], lambda paths: {paths[0]: "LAW"})
    check("b. words on screen fail", False)
except WFC.PictureCheckFailed:
    check("b. words on screen fail", True)

# c. which picture
WL.SCRIPTS, WL.KITS, WL.WORK = TMP / "scripts", TMP / "kits", TMP / "work"
WL.CHANNEL_STATE = TMP / "whisper_channel.json"
C = WL.cfg()


def script(slug: str, lane: str, kind: str, kit: dict | None = None) -> dict:
    (WL.KITS / slug).mkdir(parents=True, exist_ok=True)
    if kit is not None:
        (WL.KITS / slug / "kit.json").write_text(json.dumps(kit))
    return {"slug": slug, "kind": kind, "lane": lane}


orig_lane = WL.lane_of
WL.lane_of = lambda p, c=None: p["lane"]
check("c. a new Neville video is painted", WL.picture_for("n1", script("n1", "neville", "neville"), C) == "paint")
check("c. a new Money video is painted",
      WL.picture_for("m1", script("m1", "money", "affirmations"), C) == "paint")
check("c. a Neville video rendered before keeps footage (forward only)",
      WL.picture_for("n2", script("n2", "neville", "neville", {"frame_check": {"passed": False}}), C) == "footage")
check("c. a sleep-history video keeps footage", WL.picture_for("f1", script("f1", "food", "sleep"), C) == "footage")
check("c. a recorded picture never changes",
      WL.picture_for("n3", script("n3", "neville", "neville", {"picture": "paint", "frame_check": {}}), C) == "paint")
WL.CHANNEL_STATE.write_text(json.dumps({"paint_trial": {"verdict": "footage"}}))
check("c. after a footage verdict a new video takes footage",
      WL.picture_for("n4", script("n4", "neville", "neville"), C) == "footage")
WL.CHANNEL_STATE.unlink()
WL.lane_of = orig_lane

# d. the day-30 verdict
NOW = dt.datetime(2026, 12, 20, tzinfo=dt.timezone.utc)


def kits(paint_day: int) -> dict:
    t = (NOW - dt.timedelta(days=paint_day)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"p": {"video_id": "P", "lane": "neville", "picture": "paint", "scheduled_publish_at": t, "length_s": 3000},
            "f": {"video_id": "F", "lane": "neville", "scheduled_publish_at": "2026-11-17T02:00:00Z", "length_s": 3000}}


def fake(paint_pct, paint_s, foot_pct=40.0, foot_s=900.0):
    def get(url, token, **q):
        if q.get("dimensions") == "video":
            hdr = [{"name": n} for n in ("video", "views", "averageViewPercentage", "averageViewDuration")]
            want = q["filters"].removeprefix("video==").split(",")
            rows = [["P", 100, paint_pct, paint_s], ["F", 100, foot_pct, foot_s]]
            return {"columnHeaders": hdr, "rows": [r for r in rows if r[0] in want]}
        return {"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}],
                "rows": [[0.1, 0.5]]}
    return get


r = SC.paint_verdict("t", NOW, C, kits(10), None, fake(10, 100))
check("d. before day 30 nothing is judged", r and r["verdict"] is None, r)
r = SC.paint_verdict("t", NOW, C, kits(31), None, fake(20.0, 400.0))
check("d. paint worse on both -> footage", r["verdict"] == "footage", r)
check("d. the line names both groups' numbers", "Paint 20.0% viewed" in SC.paint_line(r), SC.paint_line(r))
r2 = SC.paint_verdict("t", NOW, C, kits(31), None, fake(20.0, 850.0))
check("d. paint worse on one only -> paint stays", r2["verdict"] == "paint", r2)
check("d. judged once, never re-judged", SC.paint_verdict("t", NOW, C, kits(31), r, fake(90, 3000)) is r)

# e. a painted kit has no footage set and is not refused for it
WL.script_problems = lambda path, others=None, c=None: []
WL.meta_problems = lambda meta, secs, c=None: []
base = {"kind": "neville", "lane": "neville", "length_s": 3000, "length_basis": "measured",
        "body": {"status": {"selfDeclaredMadeForKids": False}}}
check("e. a painted kit is not refused for having no footage set",
      not any("WRONG_FOOTAGE_SET" in x for x in WU.lane_problems("n1", {**base, "picture": "paint"}, C)))
check("e. a footage kit with no set still is",
      any("WRONG_FOOTAGE_SET" in x for x in WU.lane_problems("n1", base, C)))

if examined == 0:
    raise SystemExit("FAIL: examined nothing")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print(f"PASS: {examined} whisper paint check(s)")
