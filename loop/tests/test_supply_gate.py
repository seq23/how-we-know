"""The supply gate: over 14 days of a format made and waiting, make none; reopen
on its own under 14 (her 12 Oct rule, in code 6 Nov 2026).

  a. 90 queued episodes, all made, 12 uploads in 28 days -> HOLD (the old
     code started production anyway: no gate existed);
  b. as uploads drain the shelf the SAME gate opens, with no human;
  c. a shelf that uploaded nothing in 28 days uses the one-a-week floor, so a
     small shelf still opens (no deadlock) and a big one still holds;
  d. Shorts: cut-and-unpublished over 14 days holds, under opens;
  e. the sessions obey it: the batch skips narration and the Shorts cut on
     HOLD, the food night exits 0 (a note, never a red), and the CLI exit
     code is the HOLD signal (10), not a failure.
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
import supply_gate as G  # noqa: E402

fails = []
NOW = dt.datetime(2026, 11, 6, 22, 0, tzinfo=dt.timezone.utc)


def check(ok, msg):
    if not ok:
        fails.append(msg)


def ago(days):
    return (NOW - dt.timedelta(days=days)).isoformat()


with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    for d in ("renders", "plans", "audio", "shorts"):
        (r / d).mkdir()
    queued = [f"ep-{i:02d}" for i in range(90)]
    for i, s in enumerate(queued):
        if i % 2:
            (r / "renders" / f"{s}-final.mp4").write_bytes(b"x")
        else:                                       # narrated, not rendered
            (r / "plans" / f"{s}.json").write_text(json.dumps([{}, {}]))
            (r / "audio" / s).mkdir()
            for k in range(2):
                (r / "audio" / s / f"{k:04d}.wav").write_bytes(b"x")
    led = {"published": [{"slug": f"old-{k}", "uploaded_at": ago(k * 2)} for k in range(12)]}

    # a. 90 made, 12 uploads / 28 days = 0.43/day -> ~210 days: HOLD
    v = G.check("longform", NOW, r, queued=queued, ledger=led)
    check(v["hold"] and v["made"] == 90 and v["line"].startswith("HOLD:"),
          f"(a) 90 made and waiting did not hold: {v['line']}")
    check("making none" in v["line"], f"(a) the hold line does not say so: {v['line']}")

    # a script alone is not supply (no deadlock from authoring ahead)
    (r / "plans" / "script-only.json").write_text(json.dumps([{}]))
    v2 = G.check("longform", NOW, r, queued=queued + ["script-only"], ledger=led)
    check(v2["made"] == 90, f"(a) a script with no audio counted as supply: {v2['made']}")

    # b. uploads drain it: 85 of the 90 uploaded -> 5 / 0.43 = 11.7 days: open
    led2 = {"published": led["published"] + [{"slug": s, "uploaded_at": ago(1)} for s in queued[:85]]}
    v = G.check("longform", NOW, r, queued=queued, ledger=led2)
    check(not v["hold"] and v["days"] < 14, f"(b) under 14 days did not reopen: {v['line']}")
    # a retired upload is not an upload: it is supply again
    led3 = {"published": led2["published"][:-1] + [dict(led2["published"][-1], retired_at="x")]}
    check(G.check("longform", NOW, r, queued=queued, ledger=led3)["made"] == 6,
          "(b) a retired upload still counted as uploaded")

    # c. nothing uploaded in 28 days: floor of one a week
    stale = {"published": [{"slug": "x", "uploaded_at": ago(40)}]}
    one = G.check("longform", NOW, r, queued=queued[:1], ledger=stale)
    many = G.check("longform", NOW, r, queued=queued[:3], ledger=stale)
    check(not one["hold"] and many["hold"], f"(c) floor rate wrong: {one['line']} / {many['line']}")

    # d. Shorts
    for k in range(30):
        (r / "shorts" / f"s{k}-short.mp4").write_bytes(b"x")
    sl = {"published": [{"file": f"s{k}-short.mp4", "uploaded_at": ago(k)} for k in range(14)]}
    v = G.check("shorts", NOW, r, sledger=sl)       # 16 waiting at 0.5/day = 32 days
    check(v["hold"] and v["made"] == 16, f"(d) 16 Shorts waiting at 0.5/day did not hold: {v['line']}")
    sl2 = {"published": [{"file": f"s{k}-short.mp4", "uploaded_at": ago(k % 27)} for k in range(26)]}
    v = G.check("shorts", NOW, r, sledger=sl2)      # 4 waiting at ~0.93/day
    check(not v["hold"], f"(d) 4 Shorts waiting did not reopen: {v['line']}")

# e. the sessions obey it
sh = (ROOT / "bin" / "batch-session.sh").read_text()
narr = sh[sh.index("phase_narrate() {"):]
narr = narr[:narr.index("\n}\n")]
check('supply_gate.py check longform' in narr and '"$grc" -eq 10 ]; then pending_audio=""' in narr,
      "(e) the batch narrates without asking the supply gate")
check(narr.index("supply_gate.py") < narr.index("voice/narrate_all.py"),
      "(e) the gate is asked after narration starts")
shelf = sh[sh.index("shelve_shorts() {"):]
shelf = shelf[:shelf.index("\n}\n")]
check('supply_gate.py check shorts' in shelf and shelf.index("supply_gate.py") < shelf.index("bin/make-shorts.sh"),
      "(e) Shorts are cut without asking the supply gate")
food = (ROOT / "bin" / "food-session.sh").read_text()
check('supply_gate.py check longform' in food and food.index("supply_gate.py check longform") < food.index("\n$LANE_CMD\n"),
      "(e) the food night makes an episode without asking the supply gate")
hold = food[food.index('if [ "$GATE_RC" -eq 10 ]'):]
check("exit 0" in hold[:200], "(e) a food-night HOLD is not a green exit (it must be a note)")
r = subprocess.run([sys.executable, str(LOOP / "supply_gate.py"), "report"], capture_output=True, text=True, cwd=ROOT)
check(r.returncode == 0 and "longform" in r.stdout and "shorts" in r.stdout, f"(e) report: {r.stdout}{r.stderr}")

if fails:
    print("FAIL test_supply_gate")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_supply_gate: 90 made holds, drained reopens, floor rate, Shorts, sessions obey")
