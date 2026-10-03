"""An extended script re-voices the beats it moved; narration follows the plan.

TWO DEFECTS, one contract: audio/<slug>/NNNN.wav is indexed by plan position.

  A. loop/extend.py inserts narration before the closing section, so every
     beat from the insertion point on moves to a new index. The wavs already
     at those indices were synthesised from the sentences that USED to be
     there, and voice/narrate_all.py skips any index that has a valid wav. On
     2026-10-03 three held episodes (how-do-scientists-know-so-much,
     how-do-scientists-know-how-old-something-is,
     why-deep-sea-fish-die-when-brought-to-surface) were extended with 2-3
     closing beats each sitting under the wrong text; the re-render would
     have spoken the old closing lines under the new section's captions.
     extend.retire_stale_audio() moves exactly those wavs aside.

  B. voice/narrate_all.py planned from the SCRIPT every night while the
     render reads plans/<slug>.json. Episode 13's script had drifted to 62
     beats against a 61-beat plan, so the narrator voiced beat 61 every night
     and bin/batch-session.sh moved it aside as an orphan every night.
     planner.plan_for_audio() returns the plan file when one exists.

NEGATIVE PROOF (run once, 2026-10-03): make retire_stale_audio return []
-> case A fails; make plan_for_audio ignore the plan file -> case B fails.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

os.environ["LOOP_STOPS_DIR"] = tempfile.mkdtemp(prefix="extend-stale-stops-")

import extend                                             # noqa: E402
import planner                                            # noqa: E402

fails: list[str] = []
examined = 0

tmp = Path(tempfile.mkdtemp(prefix="extend-stale-"))

# -- A. wavs from the insertion point on are retired, the rest kept ----------
examined += 1
slug = "ep"
adir = tmp / "audio" / slug
adir.mkdir(parents=True)
old = ["a", "b", "c", "closing one", "closing two", "closing three"]
for i in range(len(old)):
    (adir / f"{i:04d}.wav").write_bytes(b"RIFF" + bytes(200))
# The extension inserts two beats before the closing section: indices 3..7
# now hold different text from what the wavs at 3..5 were cut from.
new = ["a", "b", "c", "new one", "new two", "closing one", "closing two",
       "closing three"]
moved = extend.retire_stale_audio(
    slug, {i: t for i, t in enumerate(old)}, audio_dir=tmp / "audio",
    new_plan=[{"narration": t} for t in new])
if sorted(moved) != ["0003.wav", "0004.wav", "0005.wav"]:
    fails.append(f"retired {sorted(moved)}, expected the three moved closing "
                 f"beats 0003-0005")
kept = sorted(p.name for p in adir.glob("[0-9]*.wav"))
if kept != ["0000.wav", "0001.wav", "0002.wav"]:
    fails.append(f"unchanged beats were not left in place: {kept}")
parked = sorted(p.name for p in (adir / "superseded").glob("*.wav")) \
    if (adir / "superseded").is_dir() else []
if parked != ["0003.wav", "0004.wav", "0005.wav"]:
    fails.append(f"stale wavs were not moved to superseded/ (nothing may be "
                 f"deleted): {parked}")

# -- A2. the record of what was voiced can come from beats.json ---------------
examined += 1
slug2 = "ep2"
adir2 = tmp / "audio" / slug2
adir2.mkdir(parents=True)
for i in range(3):
    (adir2 / f"{i:04d}.wav").write_bytes(b"RIFF" + bytes(200))
(adir2 / "beats.json").write_text(json.dumps(
    [{"i": 0, "narration": "x"}, {"i": 1, "narration": "y"},
     {"i": 2, "narration": "z"}]))
moved2 = extend.retire_stale_audio(
    slug2, None, audio_dir=tmp / "audio",
    new_plan=[{"narration": "x"}, {"narration": "inserted"},
              {"narration": "y"}, {"narration": "z"}])
if sorted(moved2) != ["0001.wav", "0002.wav"]:
    fails.append(f"with beats.json as the record, retired {sorted(moved2)}, "
                 f"expected 0001-0002")

# -- A3. nothing to compare, nothing moved (no silent mass retirement) --------
examined += 1
slug3 = "ep3"
adir3 = tmp / "audio" / slug3
adir3.mkdir(parents=True)
(adir3 / "0000.wav").write_bytes(b"RIFF" + bytes(200))
moved3 = extend.retire_stale_audio(slug3, None, audio_dir=tmp / "audio",
                                   new_plan=[{"narration": "q"}])
if moved3:
    fails.append(f"with no record of what was voiced, {moved3} was retired - "
                 f"a guess, and a mass re-narration on a published episode")

# -- C. the Shorts cut from the superseded render go with it ------------------
# Their receipts resolve credits through plans/<slug>.json and the crop through
# renders/<slug>-final.mp4; left behind, V14/V15 fail on them and
# bin/push-to-r2.sh shelves NO Short for any episode (2026-10-03 evening).
examined += 1
sdir = tmp / "shorts"
sdir.mkdir()
for name in ("ep-short.mp4", "ep-short.mp4.short.json", "ep-short2.mp4",
             "ep-short2.mp4.short.json", "ep-other-short.mp4", "other-short.mp4"):
    (sdir / name).write_bytes(b"x")
moved_s = extend.retire_shorts("ep", shorts_dir=sdir)
if sorted(moved_s) != ["ep-short.mp4", "ep-short.mp4.short.json",
                       "ep-short2.mp4", "ep-short2.mp4.short.json"]:
    fails.append(f"retire_shorts moved {sorted(moved_s)}; expected exactly ep's "
                 f"cuts and receipts")
left = sorted(p.name for p in sdir.glob("*.mp4"))
if left != ["ep-other-short.mp4", "other-short.mp4"]:
    fails.append(f"other episodes' Shorts were touched: {left}")
parked_s = sorted(p.name for p in (sdir / "superseded-short").iterdir()) \
    if (sdir / "superseded-short").is_dir() else []
if len(parked_s) != 4:
    fails.append(f"stale Shorts were not parked (nothing may be deleted): {parked_s}")
src_e = (ROOT / "loop" / "extend.py").read_text(encoding="utf-8")
body = src_e.split("def extend_one(", 1)[1].split("\ndef ", 1)[0]
if "retire_shorts(slug)" not in body:
    fails.append("extend_one() does not retire the Shorts when it supersedes "
                 "the render - the helper exists and nothing invokes it")

# -- B. narration follows the plan file when one exists -----------------------
examined += 1
plans = tmp / "plans"
scripts = tmp / "scripts"
plans.mkdir()
scripts.mkdir()
(scripts / "s.md").write_text(
    "# Q\n\n**Domain:** deep-sea-ocean-science\n\n## Narration\n\n"
    "### One\n\nFirst sentence here. Second sentence here. Third sentence.\n\n"
    "### Two\n\nFourth sentence here. Fifth sentence here.\n", encoding="utf-8")
from_script = planner.plan(str(scripts / "s.md"))
(plans / "s.json").write_text(json.dumps(from_script[:2]))
got, source = planner.plan_for_audio("s", plans_dir=str(plans),
                                     scripts_dir=str(scripts))
if source != "plan" or len(got) != 2:
    fails.append(f"plan_for_audio planned from the {source} ({len(got)} beats) "
                 f"although plans/s.json (2 beats) exists - the narrator would "
                 f"voice beats the render never indexes")
(plans / "s.json").unlink()
got, source = planner.plan_for_audio("s", plans_dir=str(plans),
                                     scripts_dir=str(scripts))
if source != "script" or len(got) != len(from_script):
    fails.append(f"without a plan file, plan_for_audio gave {source} with "
                 f"{len(got)} beats, expected the script's {len(from_script)}")

# -- B2. voice/narrate_all.py actually calls it ("exists but nothing invokes it")
examined += 1
src = (ROOT / "voice" / "narrate_all.py").read_text(encoding="utf-8")
if "planner.plan_for_audio(" not in src:
    fails.append("voice/narrate_all.py does not call planner.plan_for_audio - "
                 "the narrator still plans from the script")

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} stale-audio / plan-source case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - moved beats are re-voiced and narration follows the plan file")
