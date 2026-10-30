"""A one-off owner acceptance lets ONLY its episode pass ONLY its check, and
only within its bound (channel/specs/acceptances.json, read by
loop/backfill.food_problems -> food_hold and V55).

26 Oct 2026: what-is-inside-chili-coffee-honey stitched at 32.6 min, 0.6 over
the 28-32 window because the author's WPM constant was miscalibrated; Sequoia
accepted it via the coordinator, with a hard bound of 33.0 min.

Cases (on copies of the real spec, so no file in the repo changes):
  0. the frozen 32.6-min fixture fails the window with no acceptance;
  1. the accepted episode passes food_hold;
  2. the same episode at 33.5 min is held;
  3. a different episode with the same failing length is held;
  4. the accepted episode with a DIFFERENT failing check is still held;
  5. a record whose max_min is above the 33.0 hard cap cannot lift it;
  6. V55 passes and notes the acceptance.

Prove-it-fails: make food_hold call check_episode_files directly again (no
food_problems) -> case 1 fails.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))

import backfill as BF                                          # noqa: E402

SLUG = "what-is-inside-chili-coffee-honey"
fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


real_root, real_acc = BF.ROOT, BF.ACCEPTANCES
src = ROOT / "channel" / "specs"
recs = json.loads((src / "acceptances.json").read_text())["acceptances"]
check(any(a["episode"] == SLUG and a["check"] == "episode_minutes" for a in recs),
      "the 26 Oct acceptance record is missing")
check(all(a.get("accepted_by") and a.get("reason") and a.get("date") for a in recs),
      "an acceptance record lacks accepted_by, reason or date")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    specs = root / "channel" / "specs"
    specs.mkdir(parents=True)
    # The fixture is the 32.6-min spec the owner accepted. #251 moved it to
    # specs/superseded/; the Mac's 28 Oct state commit then wrote a fresh
    # 30.8-min re-render back to specs/, and reading "whichever exists, live
    # first" turned the fixture into a PASSING episode (case 3 went green-by-
    # default -> main red). The frozen copy wins, and the length is pinned to
    # the acceptance record's own measurement, so a re-render can never move
    # the fixture again.
    sdir = src / "superseded" if (src / "superseded" / f"{SLUG}.json").exists() else src
    rec = next(a for a in recs if a["episode"] == SLUG and a["check"] == "episode_minutes")
    base = dict(json.loads((sdir / f"{SLUG}.json").read_text()),
                duration_s=float(rec["measured_min"]) * 60)

    def put(slug: str, spec: dict, acc: list[dict] | None = None) -> None:
        (specs / f"{slug}.json").write_text(json.dumps(spec))
        shutil.copy(sdir / f"{SLUG}.proof.npz", specs / f"{slug}.proof.npz")
        (specs / "acceptances.json").write_text(json.dumps({"acceptances": acc if acc is not None else recs}))

    BF.ROOT, BF.ACCEPTANCES = root, specs / "acceptances.json"
    import batch_queue as BQ                                   # noqa: E402
    is_food = BQ.is_food
    BQ.is_food = lambda s: True
    try:
        # the fixture must actually fail the length window without its
        # acceptance, or every case below proves nothing
        put(SLUG, base, [])
        standing, _w = BF.food_problems(SLUG, specs / f"{SLUG}.json")
        check(any(p.startswith("episode runs 32.6 min") for p in standing),
              f"0: the fixture no longer fails the length window: {standing}")

        put(SLUG, base)
        why = BF.food_hold(SLUG)
        check(why is None, f"1: the accepted episode is still held: {why}")

        put(SLUG, dict(base, duration_s=33.5 * 60))
        why = BF.food_hold(SLUG)
        check(bool(why) and "episode runs 33.5 min" in why, f"2: 33.5 min not held: {why}")

        other = "what-is-inside-salt-sugar-vinegar"
        put(other, base)
        why = BF.food_hold(other)
        check(bool(why) and "episode runs 32.6 min" in why, f"3: a different episode passed: {why}")

        broken = json.loads(json.dumps(base))
        broken["attribution_ocr"] = {"examined": 18, "read": 10, "misses": ["x"] * 8}
        broken.pop("hands_notes", None)
        st = dict(broken.get("screen_time") or {})
        st["real_video_share"] = 0.10
        broken["screen_time"] = st
        put(SLUG, broken)
        standing, waived = BF.food_problems(SLUG, specs / f"{SLUG}.json")
        check(bool(standing) and not any(p.startswith("episode runs") for p in standing),
              f"4: a different failing check is not held: standing={standing} waived={waived}")
        check(bool(BF.food_hold(SLUG)), "4: food_hold let a different failing check ship")

        put(SLUG, dict(base, duration_s=33.4 * 60), [dict(recs[0], max_min=40.0)])
        check(bool(BF.food_hold(SLUG)), "5: a record above the 33.0 hard cap lifted it")
    finally:
        BF.ROOT, BF.ACCEPTANCES = real_root, real_acc
        BQ.is_food = is_food

import validate as V                                           # noqa: E402
res = V.v55_food_episode().as_dict()
check(not res["failures"], f"6: V55 fails: {res['failures']}")
live = src / f"{SLUG}.json"
if live.exists() and BF.food_problems(SLUG, live)[1]:
    check(any("ACCEPTED one-off" in n and SLUG in n for n in res.get("notes") or []),
          "6: V55 does not note the acceptance")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
