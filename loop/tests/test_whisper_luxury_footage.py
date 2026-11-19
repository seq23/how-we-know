"""Money footage must LOOK like money (her complaint 19 Nov 2026, "inferior
images - not luxury enough", and her question "why wasn't this caught?").

The Money video affirmations-money-2026-w45 went up with a Kyiv river tour
boat as "a yacht", resort pools with swimmers and a Prague office tower: a tag
word was the only test, and five subjects carried the whole video. Proves:
  a. at harvest, a clip whose tags signal an ordinary/tourist scene (the Kyiv
     boat's real tags) is refused, and so is a letterboxed 1920x746 clip; a
     superyacht's tags pass;
  b. a money-luxury pool short of its distinct-subject floor is the NAMED
     STOP WHISPER_SUBJECTS_SHORT (never filled with weak clips) and is not
     pictureable; at the floor it plans;
  c. the look check (free vision route, config `look`) refuses the tourist-
     boat frame with its reason, and no model answering returns None (the
     caller fails closed);
  d. before upload, the kit's contact sheet is written next to the kit and a
     "no" on the tourist-boat clip raises LOOK_CHECK_FAILED naming its time;
     no model answering is FrameCheckUnavailable;
  e. in the nightly run, that failure sends nothing and is the NAMED STOP
     WHISPER_LOOK_REFUSED.
Hard-fails on zero checks.
"""
from __future__ import annotations

import datetime as dt
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
TMP = Path(tempfile.mkdtemp(prefix="whisper-luxury-"))
os.environ["LOOP_STOPS_DIR"] = str(TMP / "stops")

from PIL import Image                                       # noqa: E402

import breaker                                              # noqa: E402
import common                                               # noqa: E402
import frame_check as FC                                    # noqa: E402
import imagery_stock_video as STOCK                         # noqa: E402
import whisper_frame_check as WFC                           # noqa: E402
import whisper_lane as WL                                   # noqa: E402
import whisper_reel as R                                    # noqa: E402
import whisper_upload as WU                                 # noqa: E402

fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


C = WL.cfg()
SET = C["calm_footage"]["sets"]["money-luxury"]
RULES = R.set_rules(C, "money-luxury")
YACHT = next(e for e in SET if "yacht" in e["subject"])
KYIV = {"id": 119437, "width": 1920, "height": 1080,
        "title": "yacht, vessel, tourism, kiev, ukraine, dnieper, luxury, summer, boat, vacation, "
                 "transportation, cruise, yachting, marine"}
SUPER = {"id": 1, "width": 3840, "height": 2160, "title": "superyacht, luxury, sunset, mediterranean"}
SICILY = {"id": 1188, "width": 1920, "height": 746, "title": "luxury penthouse, sicily, interior"}

# a. harvest refusals
check("a. the Kyiv tour boat's own tags are refused at harvest",
      (STOCK.harvest_refusal(RULES, YACHT, KYIV) or "").startswith("tag:"),
      STOCK.harvest_refusal(RULES, YACHT, KYIV))
check("a. a letterboxed 1920x746 clip is refused", (STOCK.harvest_refusal(RULES, SET[0], SICILY) or "")
      .startswith("size:"), STOCK.harvest_refusal(RULES, SET[0], SICILY))
check("a. a superyacht's tags pass", STOCK.harvest_refusal(RULES, YACHT, SUPER) is None,
      STOCK.harvest_refusal(RULES, YACHT, SUPER))
check("a. the set's floor is at least 6 distinct subjects", int(RULES.get("min_subjects") or 0) >= 6, RULES)

# b. the subject floor
WL.REFUSED_CLIPS = TMP / "refused.json"


def clips(n_subjects: int) -> list[dict]:
    return [{"post_id": f"pixabay:{s}{i}", "calm_set": "money-luxury", "seconds": 40.0,
             "width": 1920, "height": 1080, "subject": SET[s]["subject"]}
            for s in range(n_subjects) for i in range(3)]


floor = int(RULES["min_subjects"])
try:
    R.pool("calm:money-luxury", clips(floor - 1), C)
    check("b. a pool short of subjects stops", False, "no stop")
except R.FootageThin as e:
    check("b. a pool short of subjects is the NAMED STOP WHISPER_SUBJECTS_SHORT",
          str(e).startswith("WHISPER_SUBJECTS_SHORT"), str(e))
check("b. ...and is not pictureable", R.pictureable("calm:money-luxury", clips(floor - 1)) is False)
at_floor = R.pool("calm:money-luxury", clips(floor), C)
check("b. at the floor every clip is in the pool", len(at_floor) == floor * 3, len(at_floor))
small = clips(floor) + [{**clips(1)[0], "post_id": "pixabay:small", "width": 1920, "height": 746}]
check("b. a letterboxed clip already on record never reaches the reel",
      "pixabay:small" not in {a["post_id"] for a in R.pool("calm:money-luxury", small, C)})

# c. the look judge
BOAT = TMP / "pixabay-119437.jpg"
JET = TMP / "pixabay-777.jpg"
Image.new("RGB", (320, 180), (60, 70, 80)).save(BOAT)
Image.new("RGB", (320, 180), (30, 24, 18)).save(JET)


def judge(frames, subject, look):
    return [{"looks": "119437" not in f, "why": "a public river tour boat, not a superyacht"
             if "119437" in f else "a private jet cabin"} for f in frames]


bad = WFC.look_failures([str(BOAT), str(JET)], "a yacht at sunset", RULES["look"], judge)
check("c. the tourist-boat frame does not look like luxury, with its reason",
      bad == {str(BOAT): "a public river tour boat, not a superyacht"}, bad)
check("c. no model answering is None (fail closed)",
      WFC.look_failures([str(BOAT)], "x", RULES["look"], lambda *a: None) is None)
check("c. the look question names the set's look and the subject",
      RULES["look"][:30] in WFC.look_question(RULES["look"], "a yacht at sunset", 1))

# d. the contact sheet before upload
WL.KITS, WL.WORK = TMP / "kits", TMP / "work"
(WL.KITS / "ep-money").mkdir(parents=True)
kit = {"slug": "ep-money", "footage_set": "money-luxury",
       "reel": [[0.0, 18.0, "pixabay:777"], [18.0, 18.0, "pixabay:119437"], [36.0, 18.0, "pixabay:777"]]}


def grab(video, t, out):
    Image.open(BOAT if abs(t - 27.0) < 0.01 else JET).save(out)
    return out


try:
    WU.look_check(Path("v.mp4"), "ep-money", kit, C, judge=judge, grab=grab)
    check("d. a no on the contact sheet blocks the upload", False, "passed")
except FC.PictureCheckFailed as e:
    check("d. a no on the tourist-boat clip is LOOK_CHECK_FAILED naming it",
          str(e).startswith("LOOK_CHECK_FAILED") and "pixabay:119437" in str(e)
          and "pixabay:777 at" not in str(e), str(e))
    check("d. ...at the time that clip is on screen (for repair to refuse it)",
          [t for t, _ in e.failures] == [27.0], e.failures)
check("d. the contact sheet sits next to the kit", (WL.KITS / "ep-money" / "contact-sheet.jpg").exists())
try:
    WU.look_check(Path("v.mp4"), "ep-money", kit, C, judge=lambda *a: None, grab=grab)
    check("d. no model answering holds the upload", False, "passed")
except FC.FrameCheckUnavailable:
    check("d. no model answering is FrameCheckUnavailable: nothing goes up unjudged", True)
check("d. a painted kit has nothing to judge",
      WU.look_check(Path("v.mp4"), "ep-money", {"picture": "paint"}, C)["look"].startswith("not"))

# e. the nightly run names it
breaker.guard = lambda lane: None
WU.spend = lambda u: None
WU.afford = lambda: True
WL.script_problems = lambda path, others=None, c=None: []
WL.SCRIPTS = TMP / "scripts"
WL.SCRIPTS.mkdir()
(WL.SCRIPTS / "ep-money.md").write_text("# ep-money\n")
secs = 7300.0
t = f"ASMR whispered money affirmations for sleep ({WL.length_label(secs)})"
d = f"Soft.\n{C['channel']['ai_voice_line']}\n2 hr.\n"
k = {**kit, "kind": "sleep", "title": t, "description": d, "length_s": secs, "length_basis": "measured",
     "body": WL.upload_body(t, d, C), "uploaded": False, "problems": []}
(WL.KITS / "ep-money" / "kit.json").write_text(json.dumps(k))
(WL.KITS / "ep-money" / "thumbnail.png").write_bytes(b"png")
v = WL.video_path("ep-money")
v.parent.mkdir(parents=True, exist_ok=True)
v.write_bytes(b"mp4" * 100)
sent: list = []


class FakeYT:
    def channel(self):
        return {"id": C["channel"]["id"], "handle": "@whisperalmanac", "long_uploads": "allowed"}

    def insert(self, body, video):
        sent.append(body)
        return "vid1"

    def status(self, ids):
        return {}

    def thumbnail(self, vid, png):
        pass


def look_fails(video, slug, c):
    return WU.look_check(video, slug, WU.read_kit(slug), c, judge=judge, grab=grab)


WU.repair = lambda st, now, reel_of=None: []     # the repair has its own test (test_whisper_upload j)
try:
    WU.run(now=dt.datetime(2026, 11, 19, 13, 0, tzinfo=dt.timezone.utc), yt=FakeYT(),
           checker=look_fails, notify=lambda s: "noted", renderer=lambda s: 0)
except SystemExit:
    pass
stop = Path(os.environ["LOOP_STOPS_DIR"]) / f"{common.week_id()}-{WU.LANE}.json"
rec = json.loads(stop.read_text()) if stop.exists() else {}
check("e. nothing is sent", sent == [], sent)
check("e. the run is the NAMED STOP WHISPER_LOOK_REFUSED", rec.get("code") == "WHISPER_LOOK_REFUSED", rec)

if not examined:
    raise SystemExit("FAIL: zero checks ran")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print(f"PASS: {examined} checks - money footage must look like money")
