"""The narrator nights split 5 Whisper Almanac : 2 How We Know (her ruling,
6 Nov 2026), AFTER the supply gates, with a fallback that never idles the Mac.

  a. Monday and Friday are How We Know nights; the other five are the Almanac's;
     02:00 on a Wednesday belongs to Tuesday's night;
  b. an Almanac night with no whisper sample falls back to How We Know with a
     NOTE (never a stop that fails the night);
  c. the gates decide first: an Almanac night whose own supply gate holds goes
     to How We Know; a How We Know night whose long-form gate holds goes to
     the Almanac when it is ready;
  d. the Whisper gate uses the planned rate before its first upload: 15 made
     at two a week is a hold;
  e. the sessions obey: the batch asks before narrating and rests How We Know
     narration on an Almanac night; the food session steps aside (exit 0).
"""
import datetime as dt
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
import night_split as N  # noqa: E402
import supply_gate as G  # noqa: E402

fails = []
CFG = {"hwk_nights": ["mon", "fri"]}
NOW = dt.datetime(2026, 11, 6, 23, 0, tzinfo=dt.timezone.utc)
OPEN = G.verdict("x", 1, 1.0, 10, NOW)
HOLD = G.verdict("x", 90, 0.4, 10, NOW)


def check(ok, msg):
    if not ok:
        fails.append(msg)


# a. the calendar (6 Nov 2026 is a Friday)
week = {d: N.planned(dt.datetime(2026, 11, 2 + i, 23, 0), CFG)
        for i, d in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}
check([d for d, k in week.items() if k == "hwk"] == ["mon", "fri"], f"(a) How We Know nights: {week}")
check(sum(1 for k in week.values() if k == "whisper") == 5, f"(a) not five Almanac nights: {week}")
check(N.planned(dt.datetime(2026, 11, 4, 2, 0), CFG) == N.planned(dt.datetime(2026, 11, 3, 23, 0), CFG),
      "(a) 02:00 Wednesday is not Tuesday's night")
tue = dt.datetime(2026, 11, 3, 23, 0)
fri = dt.datetime(2026, 11, 6, 23, 0)

# b. no sample: falls back, with a note
k, notes = N.tonight(tue, hwk_gate=OPEN, whisper_gate=OPEN, ready=(False, "her whisper sample is not on the Mac yet"), cfg=CFG)
check(k == "hwk" and any(n.startswith("note:") and "sample" in n for n in notes),
      f"(b) no sample did not fall back with a note: {k} {notes[-1:]}")
k, _ = N.tonight(tue, hwk_gate=OPEN, whisper_gate=OPEN, ready=(True, ""), cfg=CFG)
check(k == "whisper", "(b) a ready Almanac night was not the Almanac's")

# c. the gates first
k, _ = N.tonight(tue, hwk_gate=OPEN, whisper_gate=HOLD, ready=(True, ""), cfg=CFG)
check(k == "hwk", "(c) an Almanac night whose supply gate holds was not given to How We Know")
k, notes = N.tonight(fri, hwk_gate=HOLD, whisper_gate=OPEN, ready=(True, ""), cfg=CFG)
check(k == "whisper", f"(c) a held How We Know night was not given to the Almanac: {notes[-1:]}")
k, _ = N.tonight(fri, hwk_gate=OPEN, whisper_gate=OPEN, ready=(True, ""), cfg=CFG)
check(k == "hwk", "(c) an open How We Know night was taken by the Almanac")

# d. the Whisper gate before any upload: planned rate
check(G.verdict("whisper", 15, 2 / 7, 0, NOW)["hold"], "(d) 15 made at two a week does not hold")
check(not G.verdict("whisper", 3, 2 / 7, 0, NOW)["hold"], "(d) 3 made at two a week holds")

# d2. one upload never drags the pace below the plan (11 Nov 2026: 1 upload in
# 28 days read as 1/28 a day held the Almanac with a single video waiting)
import json as _json, tempfile as _tf, types as _types  # noqa: E401,E402
_tmp = Path(_tf.mkdtemp())
(_tmp / "kits" / "up").mkdir(parents=True)
(_tmp / "kits" / "up" / "kit.json").write_text(_json.dumps({"uploaded_at": "2026-11-05T00:00:00Z"}))
(_tmp / "made.mp4").write_text("x")
_fake = _types.SimpleNamespace(
    KITS=_tmp / "kits",
    all_scripts=lambda: [Path("up.md"), Path("made.md")],
    voiced=lambda slug: (0, 0),
    video_path=lambda slug: _tmp / f"{slug}.mp4",
    cfg=lambda: {"split": {"planned_uploads_per_week": 5}})
_real = sys.modules.get("whisper_lane")
sys.modules["whisper_lane"] = _fake
try:
    v = N.whisper_supply(NOW)
finally:
    if _real is not None:
        sys.modules["whisper_lane"] = _real
    else:
        sys.modules.pop("whisper_lane", None)
check(not v["hold"] and v["per_day"] >= round(5 / 7, 3), f"(d2) one upload held the Almanac: {v['line']}")
check(v["made"] == 1, f"(d2) made counted {v['made']}, expected 1")

# e. the sessions obey
sh = (ROOT / "bin" / "batch-session.sh").read_text()
seq = sh[sh.index("# THE SEQUENCE."):]
check(seq.index("step whisper phase_whisper night") < seq.index("step narrate phase_narrate"),
      "(e) the batch narrates before it asks whose night it is")
narr = sh[sh.index("phase_narrate() {"):]
narr = narr[:narr.index("\n}\n")]
check('${WHISPER_NIGHT:-}' in narr and narr.index("WHISPER_NIGHT") < narr.index("voice/narrate_all.py"),
      "(e) How We Know narration does not rest on an Almanac night")
check("step whisper phase_whisper idle" in sh, "(e) an idle How We Know night is not offered to the Almanac")
food = (ROOT / "bin" / "food-session.sh").read_text()
i = food.index('if [ "$NIGHT_KIND" = "whisper" ]; then')
check("exit 0" in food[i:i + 200] and i < food.index("\n$LANE_CMD\n"),
      "(e) the food session does not step aside on an Almanac night")

if fails:
    print("FAIL test_night_split")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_night_split: 5:2 by night, gates first, sample fallback is a note, sessions obey")
