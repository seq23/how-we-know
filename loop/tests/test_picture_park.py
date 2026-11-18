"""Footage self-heal, then park (loop/picture_park.py, 18 Nov 2026).

  a. a footage failure on night 1 and 2 heals (widens its own search) and
     stays in the supply count; night 3 PARKS it: out of the 7-day cap's
     count, out of the render sweep, one morning line, nothing deleted;
  b. a failure for any OTHER reason never counts toward parking;
  c. seven days on, a parked episode is due a retry: healed and tried again;
     one that renders REJOINS the queue and counts as supply again;
  d. parked 60 days -> retired (a note), still out of the cap, never deleted;
  e. a morning line that could not be written stays pending for tomorrow;
  f. the nightly batch wires it: heal before the sweep, record/ok per render,
     the sweep skips parked slugs, settle every night (paused or not).
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
tmp = Path(tempfile.mkdtemp())
os.environ["LOOP_PICTURE_PARK"] = str(tmp / "picture_park.json")
sys.path.insert(0, str(LOOP))
import picture_park as P  # noqa: E402
import supply_gate as G  # noqa: E402

P.STATE = tmp / "picture_park.json"
P.title_of = lambda s: s.replace("-", " ").capitalize() + "?"
fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


# a world: two voiced long-forms, neither rendered
root = tmp / "root"
for slug in ("sea-pigs", "steel"):
    (root / "plans").mkdir(parents=True, exist_ok=True)
    (root / "plans" / f"{slug}.json").write_text(json.dumps([{}, {}]))
    for i in range(2):
        (root / "audio" / slug).mkdir(parents=True, exist_ok=True)
        (root / "audio" / slug / f"{i:04d}.wav").write_bytes(b"x")
LED = {"published": []}


def made():
    return G.longform_made(root, ["sea-pigs", "steel"], LED)


def save(st):
    P.save(st)


check(sorted(made()) == ["sea-pigs", "steel"], "both voiced episodes count as supply")

# a. nights 1-3
st = P.load()
widened = []
for n, day in enumerate(("2026-11-16", "2026-11-17", "2026-11-18"), 1):
    P.heal(st, day, widen_fn=lambda s, t: widened.append((s, t)) or [f"try {t}"])
    P.record_fail(st, "sea-pigs", "NO_SUBJECT_PICTURE: need 9 distinct subjects", day)
    r = P.settle(st, day)
    save(st)
    if n < 3:
        check("sea-pigs" not in P.parked(st) and "sea-pigs" in made(),
              f"night {n}: failing, healing, still counted")
check(widened == [("sea-pigs", 1), ("sea-pigs", 2)],
      f"heal widened the episode on nights 2 and 3, wider each time ({widened})")
check(r["parked_new"] == ["sea-pigs"] and "sea-pigs" in P.parked(st),
      "night 3 in a row: parked")
check(made() == ["steel"], "parked episode no longer counts toward the 7-day cap")
check("sea-pigs" in P.skip(st, "2026-11-19"), "the render sweep skips it")
check((root / "audio" / "sea-pigs" / "0000.wav").exists(), "its voice is kept")
note = [x for x in st["pending_notes"] if x.startswith("parked: Sea pigs?")]
check(len(note) == 1 and "not enough cleared footage" in note[0] and "16 Nov" in note[0],
      f"one morning line names it and its dates ({note})")

# e. notes: once, and a failed write stays pending
said = P.flush_notes(st, send=lambda t: "no morning line: node not found")
check(said == [] and len(st["pending_notes"]) == 1, "an unwritten line stays pending")
said = P.flush_notes(st, send=lambda t: "morning line written")
check(len(said) == 1 and st["pending_notes"] == [], "written once, then cleared")
P.settle(st, "2026-11-19")
check(st["pending_notes"] == [], "an already-parked episode is not announced again")

# b. another kind of failure never counts
log = tmp / "asm.log"
log.write_text("Traceback ...\nffmpeg exited 1\n")
save(st)
subprocess.run([sys.executable, str(LOOP / "picture_park.py"), "record", "steel", str(log)],
               check=True, capture_output=True, env={**os.environ})
check("steel" not in P.load()["episodes"], "a non-footage failure is not counted")

# c. weekly retry, then heals -> rejoins
st = P.load()
check(not P.retry_due(st["episodes"]["sea-pigs"], "2026-11-24"), "no retry before 7 days")
check(P.retry_due(st["episodes"]["sea-pigs"], "2026-11-25"), "retry due after 7 days")
check("sea-pigs" not in P.skip(st, "2026-11-25"), "a due retry is let into the sweep")
check(P.to_heal(st, "2026-11-25") == ["sea-pigs"], "and widened first")
P.record_fail(st, "sea-pigs", "NO_SUBJECT_PICTURE", "2026-11-25")
check("sea-pigs" in P.parked(st) and st["episodes"]["sea-pigs"]["retries"] == ["2026-11-25"],
      "a failed retry stays parked and is dated")
P.record_ok(st, "sea-pigs", "2026-12-02")
save(st)
check("sea-pigs" not in P.parked(st) and sorted(made()) == ["sea-pigs", "steel"],
      "healed: rejoins the queue and counts as supply again")
check(any(x.startswith("rejoined: Sea pigs?") for x in st["pending_notes"]), "with a rejoined line")

# d. retire after 60 days parked
st = {"episodes": {"steel": {"fails": ["2026-09-01", "2026-09-02", "2026-09-03"],
                             "parked_at": "2026-09-03"}}}
r = P.settle(st, "2026-11-02")
check(r["retired_new"] == ["steel"] and "steel" in P.parked(st)
      and not P.retry_due(st["episodes"]["steel"], "2026-12-30"),
      "parked 60 days: retired, still out of the cap, no more retries")
check(any(x.startswith("retired: Steel?") and "never deleted" in x for x in st["pending_notes"]),
      "with a retired line")

# f. the nightly batch wires it
sh = (ROOT / "bin" / "batch-session.sh").read_text()
render = sh[sh.index("phase_render() {"):]
check("picture_park.py heal" in render
      and render.index("picture_park.py heal") < render.index("for slug in $(renderable)"),
      "heal runs before the render sweep")
check('picture_park.py ok "$slug"' in sh and 'picture_park.py record "$slug"' in sh,
      "every render reports ok / failure")
check("picture_park.skip()" in sh, "the sweep skips parked slugs")
rep = sh[sh.index("phase_report() {"):]
check("picture_park.py settle" in rep[:rep.index("\n}\n")], "settle runs in the report (every night)")
import mac_sync  # noqa: E402
check("loop/state/picture_park.json" in mac_sync.MAC_OWNED_GLOBS, "the Mac pushes its state")

if fails:
    print(f"FAIL test_picture_park: {len(fails)}")
    raise SystemExit(1)
print("ok test_picture_park: heals, parks at 3 nights and frees the cap, retries weekly, rejoins, retires")
