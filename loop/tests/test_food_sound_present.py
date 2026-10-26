"""Every sound the food preset can pick resolves to a file before a food night
renders, and a missing one stops the night early BY NAME.

25 Oct 2026: the food night rendered footage and voice for five hours, then
died at the first piece render - ffmpeg exit 254 on
channel/sound/food_sound__sizzle.ogg. The .ogg files are gitignored
(channel/sound/*.ogg); the 13 Oct harvest ran in a worktree, so this Mac's main
checkout never had them, and the stop line said only "see the lines above".

Cases:
  1. every cue the preset can pick (SOUNDS, CUE_FOR, and every `sound` a real
     clip in research/food_footage.SHOTS carries) has a record in
     channel/sound/food.json whose file is food_sound__<key>.ogg;
  2. ensure() fetches each missing file and lands it on disk (network stubbed);
  3. ensure() refuses bytes that do not hash to the rights-checked sha256, and
     a failed fetch, each with SoundMissing NAMING channel/sound/<file>;
  4. _load() on a missing file raises SoundMissing naming it, not ffmpeg 254;
  5. loop/food_lane.run calls ensure() BEFORE any stage and stops with
     NAMED STOP [FOOD_SOUND_MISSING];
  6. the FOOD_PIECE_CONTRACT stop line carries food_episode.render_failure(),
     which names the exception or first failing problem (never "see the lines
     above").

Prove-it-fails: drop `ensure()` from food_lane.run -> case 5 fails; put
"(see the lines above)" back -> case 6 fails; delete the "sizzle" record from
food.json -> case 1 fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))
sys.path.append(str(ROOT / "research"))
os.environ["LOOP_DRY_RUN"] = "1"

import food_sound as S                                         # noqa: E402

fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


# ------------------------------------------------------------------ 1. records
man = {r["key"]: r for r in json.loads(S.MANIFEST.read_text())["index"]}
cues = set(S.SOUNDS) | set(S.CUE_FOR)
try:
    import food_footage as FF                                  # noqa: E402
    shots = getattr(FF, "SHOTS", {})
    rows = shots.values() if isinstance(shots, dict) else shots
    for row in rows:
        for r in (row if isinstance(row, list) else [row]):
            if isinstance(r, dict) and r.get("sound"):
                cues.add(r["sound"])
except Exception as exc:                                      # noqa: BLE001
    fails.append(f"research/food_footage.py did not import: {exc}")
check(len(cues) >= 3, f"the preset lists {len(cues)} cues; expected sizzle, pour, snap at least")
for cue in sorted(cues):
    rec = man.get(cue)
    check(rec is not None, f"cue '{cue}' can be picked but has no record in channel/sound/food.json")
    if rec:
        check(rec["local_file"] == f"food_sound__{cue}.ogg",
              f"cue '{cue}' points at {rec['local_file']}")
        check(bool(re.fullmatch(r"[0-9a-f]{64}", rec.get("sha256", ""))),
              f"cue '{cue}' has no sha256 to check a fetch against")

# ------------------------------------------------------------------ 2-4. ensure / _load
real_sound = S.SOUND
with tempfile.TemporaryDirectory() as td:
    S.SOUND = Path(td)
    blobs = {}

    def fake_fetch(rec, _wrong=False):
        # bytes that hash to the manifest: we cannot forge sha256, so the test
        # rewrites the manifest copy it reads instead
        b = f"ogg bytes for {rec['key']}".encode()
        blobs[rec["key"]] = b
        return b

    fake_man = {"policy": "test", "index": []}
    for k, r in man.items():
        b = f"ogg bytes for {k}".encode()
        fake_man["index"].append(dict(r, sha256=hashlib.sha256(b).hexdigest()))
    real_manifest = S.MANIFEST
    S.MANIFEST = Path(td) / "food.json"
    S.MANIFEST.write_text(json.dumps(fake_man))
    try:
        got = S.ensure(fetch=fake_fetch)
        check(sorted(got) == sorted(f"channel/sound/food_sound__{k}.ogg" for k in cues),
              f"ensure fetched {got}")
        check(all((S.SOUND / f"food_sound__{k}.ogg").exists() for k in cues),
              "ensure did not land every file on disk")
        check(S.ensure(fetch=lambda r: (_ for _ in ()).throw(AssertionError("refetched"))) == [],
              "ensure re-fetched files already on disk")

        (S.SOUND / "food_sound__sizzle.ogg").unlink()
        try:
            S.ensure(fetch=lambda r: b"some other recording")
            fails.append("ensure accepted bytes that do not match the rights-checked sha256")
        except S.SoundMissing as exc:
            check("channel/sound/food_sound__sizzle.ogg" in str(exc), f"sha refusal unnamed: {exc}")

        def down(_r):
            raise OSError("network down")
        try:
            S.ensure(fetch=down)
            fails.append("ensure passed with a missing file and a failed fetch")
        except S.SoundMissing as exc:
            check("channel/sound/food_sound__sizzle.ogg" in str(exc), f"fetch failure unnamed: {exc}")

        try:
            S._load("sizzle")
            fails.append("_load ran ffmpeg on a missing file")
        except S.SoundMissing as exc:
            check("food_sound__sizzle.ogg" in str(exc), f"_load miss unnamed: {exc}")
    finally:
        S.SOUND, S.MANIFEST = real_sound, real_manifest

# ------------------------------------------------------------------ 5-6. the lane
lane = (ROOT / "loop" / "food_lane.py").read_text()
body = lane[lane.index("def run(slug"):]
body = body[:body.index("\ndef ", 10)]
i_ensure = body.find("food_sound.ensure()")
i_first_stage = body.find('"footage" not in st["stages"]')
check(i_ensure != -1, "food_lane.run never calls food_sound.ensure()")
check(i_first_stage == -1 or (i_ensure != -1 and i_ensure < i_first_stage),
      "food_lane.run checks the sounds only after the footage stage")
check("FOOD_SOUND_MISSING" in body, "no NAMED STOP [FOOD_SOUND_MISSING] in food_lane.run")
check("see the lines above" not in lane, "a food-lane stop still says 'see the lines above'")
m = re.search(r"FOOD_PIECE_CONTRACT\][^\n]*\n[^\n]*", body)
check(bool(m) and "render_failure(" in m.group(0),
      "the FOOD_PIECE_CONTRACT stop line does not carry food_episode.render_failure()")

import food_episode as FE                                      # noqa: E402
with tempfile.TemporaryDirectory() as td:
    w = Path(td)
    check("no render-result.json" in FE.render_failure(w), "render_failure silent with no result")
    FE.write_render_result(w, error="SoundMissing: channel/sound/food_sound__sizzle.ogg is not on disk")
    check("food_sound__sizzle.ogg" in FE.render_failure(w), "render_failure lost the exception")
    FE.write_render_result(w, problems={"chili": ["hands on screen 31%", "x"]})
    check(FE.render_failure(w).startswith("piece chili: hands on screen 31%"),
          f"render_failure lost the problem: {FE.render_failure(w)}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
