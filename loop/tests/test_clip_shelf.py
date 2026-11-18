"""The clip shelf (loop/shelf.py, her rulings 17 Nov 2026): idle clips go to
Drive, a shelved clip stays selectable and comes back before its render, and
nothing irreplaceable ever leaves the Mac.

  a. a shelved clip is still a candidate: footage.verify (selection),
     usable_assets and food.catalogue count it; footage.prefetch / verify
     fetch=True pull it back with the recorded sha256 before any frame;
  b. only a recorded clip idle 7+ days is shelved: a clip used or harvested
     in the last 7 days stays; voice references, manifests, state, an
     unrecorded file, a file whose bytes differ from its record and anything
     outside clips/ never move; Drive's copy verifies before the local delete;
  c. Drive unreachable or full is a NAMED STOP and nothing is deleted; a
     render needing a shelved clip fails loudly, never skips it.
"""
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"
import shelf as SH  # noqa: E402
import footage as FT  # noqa: E402
import food  # noqa: E402

fails = []
NOW = dt.datetime(2026, 11, 17, 15, 0, tzinfo=dt.timezone.utc)


def check(ok, msg):
    if not ok:
        fails.append(msg)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def age(p, days):
    t = (NOW - dt.timedelta(days=days)).timestamp()
    os.utime(p, (t, t))


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    imagery, drive = td / "imagery", td / "drive"
    clips = imagery / "clips"
    clips.mkdir(parents=True)
    SH.IMAGERY, SH.CLIPS, SH.MANIFEST = imagery, clips, td / "state" / "shelf.json"
    FT.IMAGERY_DIR = str(imagery)
    food.IMAGERY = imagery
    os.environ["SHELF_REMOTE"] = str(drive)
    os.environ.pop("SHELF_FREE_BYTES", None)

    blobs = {n: f"bytes of {n}".encode() * 500 for n in
             ("idle.mp4", "warm.mp4", "used-lately.mp4", "food_clip__idle.mp4", "drifted.mp4")}
    for n, b in blobs.items():
        (clips / n).write_bytes(b)
    (clips / "drifted.mp4").write_bytes(b"changed since it was cleared")
    assets = [{"title": n, "local_file": f"clips/{n}", "sha256": sha(blobs[n]),
               "source_org": "NOAA", "clean_windows": [{"start": 0, "end": 30}]}
              for n in ("idle.mp4", "warm.mp4", "used-lately.mp4", "drifted.mp4")]
    (imagery / "video_rights.json").write_text(json.dumps({"assets": assets}))
    (imagery / "food_clips.json").write_text(json.dumps({"index": [
        {"key": "honey-pour", "subject": "honey-pour", "local_file": "clips/food_clip__idle.mp4",
         "sha256": sha(blobs["food_clip__idle.mp4"]), "credit_line": "Pixabay", "segment": "honey"}]}))
    # irreplaceable or unrecorded: must never move, however old
    never = {"voice-ref.wav": b"her voice", "unrecorded.mp4": b"no rights record",
             "notes.json": b"{}"}
    for n, b in never.items():
        (clips / n).write_bytes(b)
    outside = imagery / "assets" / "still.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"a still's video, outside clips/")
    for p in list(clips.iterdir()) + [outside, imagery / "video_rights.json"]:
        age(p, 30)
    age(clips / "warm.mp4", 2)                      # harvested Friday: stays
    SH.save({"clips": {}, "used": {"used-lately.mp4": (NOW - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}})

    # b. shelve: only idle, recorded, unchanged clips move
    r = SH.shelve(NOW, busy=None)
    moved = set(SH.load()["clips"])
    check(moved == {"idle.mp4", "food_clip__idle.mp4"},
          f"(b) shelved {sorted(moved)}, wanted only the two idle recorded clips")
    for n in ("idle.mp4", "food_clip__idle.mp4"):
        check(not (clips / n).exists() and (drive / n).read_bytes() == blobs[n],
              f"(b) {n}: not deleted locally after a verified Drive copy")
    for n in ("warm.mp4", "used-lately.mp4", "drifted.mp4", *never):
        check((clips / n).exists() and not (drive / n).exists(), f"(b) {n} left the Mac")
    check(outside.exists() and (imagery / "video_rights.json").exists(),
          "(b) something outside clips/ was shelved")
    check(any("drifted.mp4" in x for x in r["skipped"]), "(b) a drifted clip was not reported")
    # a render running: nothing moves, and it says so
    age(clips / "warm.mp4", 30)
    w = SH.shelve(NOW, busy=lambda: "ffmpeg is running")
    check(w.get("waited") and (clips / "warm.mp4").exists(), "(b) shelving ran during a render")

    # a. selection: a shelved clip is still available
    idle = assets[0]
    check(FT.verify(idle) == str(clips / "idle.mp4"), "(a) verify(fetch=False) refused a shelved clip")
    check(not (clips / "idle.mp4").exists(), "(a) selection fetched the bytes; it should only count it")
    pool = FT.usable_assets({"assets": [a for a in assets if a["title"] != "drifted.mp4"]})
    check(any(a["title"] == "idle.mp4" for a in pool), "(a) usable_assets dropped a shelved clip")
    cat = food.catalogue()
    check("honey-pour" in cat, "(a) food.catalogue dropped a shelved clip: shelving narrowed the pool")
    import whisper_reel as wr  # noqa: E402
    FF = wr._ff()
    saved = FF.IMAGERY, FF.record_problems, FF.speed_for, wr.food_asset
    FF.IMAGERY, FF.record_problems, FF.speed_for = imagery, (lambda r: []), (lambda r, s: 1.0)
    wr.food_asset = lambda r: r
    try:
        idx = json.loads((imagery / "food_clips.json").read_text())["index"]
        check(len(wr.food_pool("honey", idx)) == 1, "(a) the whisper reel pool dropped a shelved food clip")
    finally:
        FF.IMAGERY, FF.record_problems, FF.speed_for, wr.food_asset = saved
    # ... and pulled back before the render, sha-checked, stamped used
    got = FT.prefetch([idle])
    check(got == 1 and (clips / "idle.mp4").read_bytes() == blobs["idle.mp4"],
          "(a) prefetch did not bring the shelved clip back before the render")
    check(SH.load()["used"].get("idle.mp4"), "(a) a pulled clip was not stamped used (it would re-shelve at once)")
    os.remove(clips / "idle.mp4")                   # shelved again
    FT._VERIFIED.clear()
    check(FT.verify(idle, fetch=True) == str(clips / "idle.mp4") and (clips / "idle.mp4").exists(),
          "(a) the render-time safety net did not fetch a missing shelved clip")
    food.verify_asset({**cat["honey-pour"]})
    check((clips / "food_clip__idle.mp4").exists(), "(a) food did not fetch its shelved clip")

    # c. Drive unreachable: a render needing a shelved clip stops loudly
    os.remove(clips / "idle.mp4")
    FT._VERIFIED.clear()
    os.environ["SHELF_REMOTE"] = "no-such-remote-for-tests:Mac-Shelf/clips"
    try:
        FT.verify(idle, fetch=True)
        check(False, "(c) an unreachable shelf let the render go on")
    except SH.ShelfStop as e:
        check(e.code in ("SHELF_UNREACHABLE",) and "NAMED STOP" in str(e), f"(c) wrong stop: {e}")
    except FT.RightsRefusal as e:
        check(False, f"(c) an unreachable shelf read as a missing clip: {e}")
    # c. Drive full: named stop, nothing deleted
    os.environ["SHELF_REMOTE"] = str(drive)
    os.environ["SHELF_FREE_BYTES"] = str(SH.DRIVE_MARGIN + 10)
    try:
        SH.shelve(NOW, busy=None)
        check(False, "(c) a full Drive did not stop")
    except SH.ShelfStop as e:
        check(e.code == "SHELF_DRIVE_FULL", f"(c) wrong stop for a full Drive: {e}")
    check((clips / "warm.mp4").exists(), "(c) a clip was deleted though Drive had no room")
    os.environ.pop("SHELF_FREE_BYTES", None)

    # pull-all brings every shelved clip back by hand
    n = SH.pull_all(log=lambda *_: None)
    check(n >= 1 and (clips / "idle.mp4").exists(), "(pull-all) not every shelved clip came back")

if fails:
    print("FAIL test_clip_shelf")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_clip_shelf: idle clips shelved, irreplaceable kept, shelved clips selectable and "
      "pulled before render, named stops")
