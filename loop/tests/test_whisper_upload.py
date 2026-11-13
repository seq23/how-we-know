"""The Whisper Almanac upload: only a checked episode goes up, scheduled, confirmed.

loop/whisper_upload.py (the Mac's nightly `whisper-upload` step). Proves, with a
fake YouTube (no network; LOOP_DRY_RUN=1 refuses the real credential):
  a. a finished episode that FAILS the frame check is never sent: NAMED STOP
     FRAME_CHECK_FAILED, a morning line, the file set aside (never deleted)
     and never voiced or rendered again;
  b. a passing one is uploaded PRIVATE with publishAt at 20:00 Central on a
     sleep day, altered content = yes, made for kids = no, with the kit's own
     title, description and tags; YouTube's read-back (processing started) is
     recorded and the local render is KEPT;
  c. the render and voice wavs are deleted only once YouTube says processed;
  d. the supply gate: 14+ days of the format waiting holds a new upload
     (green), nothing sent;
  e. a token for the wrong channel, or none, is WHISPER_YT_TOKEN_INVALID;
  f. no quota, or YouTube's quotaExceeded, is UPLOAD_QUOTA;
  g. a kit that fails a lane check (altered content not set) is refused;
  j. A FAILED FRAME CHECK REPAIRS ITSELF (13 Nov 2026): when the failing
     times name clips, those clips are refused for every video, the failed
     render is removed, nothing is sent, nobody is paged, and the episode is
     back in line; the reel never places a refused clip again;
  k. a render set aside on an earlier night (a kit with no recorded reel) is
     repaired from its re-planned reel, rendered again from its kept voice
     and uploaded the same run;
  l. an episode that fails again after MAX_REPAIRS re-renders stays the red
     FRAME_CHECK_FAILED, set aside;
  m. the author's "waiting for voice" count ignores a script the Mac already
     rendered (a measured kit), and one lane's refused script does not stop
     the other lanes' scripts.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

TMP = Path(tempfile.mkdtemp(prefix="whisper-upload-"))
import breaker                                              # noqa: E402
import common                                               # noqa: E402
import frame_check as FC                                    # noqa: E402
import publish as P                                         # noqa: E402
import whisper_lane as WL                                   # noqa: E402
import whisper_upload as WU                                 # noqa: E402

breaker.guard = lambda lane: None            # the live breaker is not this test's subject
P._sleep = lambda s: None
WL.script_problems = lambda path, others=None, c=None: []   # the script rules have their own tests
SPENT: list[int] = []
WU.spend = SPENT.append
WU.afford = lambda: True
C = WL.cfg()
NOW = dt.datetime(2026, 11, 7, 13, 0, tzinfo=dt.timezone.utc)          # Sat 07:00 CT
TUE_2000_CT = "2026-11-11T02:00:00Z"                                    # Tue 10 Nov 20:00 CST

fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


class FakeYT:
    def __init__(self, handle="@whisperalmanac", upload_status="uploaded", insert_error=None,
                 channel_id=None, long_uploads="allowed", gone=()):
        self._handle, self.upload_status, self.insert_error = handle, upload_status, insert_error
        self.channel_id = channel_id or (C["channel"]["id"] if handle == "@whisperalmanac" else "UCother")
        self.long_uploads, self.gone = long_uploads, set(gone)
        self.inserted: list[dict] = []
        self.published: dict[str, str] = {}

    def channel(self):
        return {"id": self.channel_id, "handle": self._handle, "long_uploads": self.long_uploads}

    def insert(self, body, video):
        if self.insert_error:
            raise self.insert_error
        assert video.exists()
        self.inserted.append(json.loads(json.dumps(body)))
        vid = f"vid{len(self.inserted)}"
        self.published[vid] = body["status"]["publishAt"]
        return vid

    def status(self, ids):
        return {i: {"uploadStatus": self.upload_status, "privacyStatus": "private",
                    "publishAt": self.published.get(i, "2026-12-01T02:00:00Z"),
                    "containsSyntheticMedia": True} for i in ids if i not in self.gone}

    def thumbnail(self, vid, png):
        pass


def sandbox(name: str) -> Path:
    d = TMP / name
    for sub in ("scripts", "kits", "work", "stops"):
        (d / sub).mkdir(parents=True)
    WL.SCRIPTS, WL.KITS, WL.WORK = d / "scripts", d / "kits", d / "work"
    WL.REFUSED_CLIPS = d / "refused_clips.json"
    os.environ["LOOP_STOPS_DIR"] = str(d / "stops")
    return d


def episode(slug: str, kind: str = "sleep", synthetic: bool = True, **extra) -> dict:
    (WL.SCRIPTS / f"{slug}.md").write_text(f"# {slug}\n")
    secs = 7300.0
    t = f"ASMR whispered deep sea for deep sleep · drift off ({WL.length_label(secs)}, dim)"
    d = f"Soft facts.\n{C['channel']['ai_voice_line']}\n2 hr of soft whispering.\n"
    body = WL.upload_body(t, d, C)
    body["status"]["containsSyntheticMedia"] = synthetic
    k = {"slug": slug, "kind": kind, "title": t, "description": d, "length_s": secs,
         "length_basis": "measured", "body": body, "uploaded": False, "problems": [], **extra}
    (WL.KITS / slug).mkdir(parents=True)
    (WL.KITS / slug / "kit.json").write_text(json.dumps(k))
    (WL.KITS / slug / "thumbnail.png").write_bytes(b"png")
    v = WL.video_path(slug)
    (v.parent / "audio").mkdir(parents=True)
    v.write_bytes(b"mp4" * 100)
    (v.parent / "audio" / "0000.wav").write_bytes(b"wav")
    return k


def passes(video, slug, c):
    return {"frames": 365, "judged": 365, "failed": 0}


def run(yt, checker=passes, now=NOW):
    lines: list[str] = []
    try:
        rc = WU.run(now=now, yt=yt, checker=checker, notify=lambda t: lines.append(t) or "noted")
    except SystemExit as e:
        rc = e.code
    stop = Path(os.environ["LOOP_STOPS_DIR"]) / f"{common.week_id()}-{WU.LANE}.json"
    rec = json.loads(stop.read_text()) if stop.exists() else {}
    return rc, rec, lines


try:
    # a. a failing frame check: never sent, set aside, seen
    sandbox("a")
    episode("ep-a")

    def fails_frames(video, slug, c):
        raise FC.PictureCheckFailed("PICTURE_CHECK_FAILED at 0:21 (text on screen: 'NOAA')", [(21.0, "text")])
    yt = FakeYT()
    rc, rec, lines = run(yt, fails_frames)
    check("a. a failing frame check sends nothing", yt.inserted == [], yt.inserted)
    check("a. it is NAMED STOP FRAME_CHECK_FAILED, red",
          rec.get("code") == "FRAME_CHECK_FAILED" and rec.get("disposition") == "needs_human", rec)
    check("a. it puts a line in her morning email", len(lines) == 1 and "picture check" in lines[0], lines)
    check("a. the file is set aside, never deleted",
          WU.set_aside("ep-a").exists() and not WL.video_path("ep-a").exists())
    check("a. a set-aside episode is never voiced or rendered again", WL.handed_on("ep-a"))

    # b. a passing episode: private, scheduled 20:00 CT, flagged, confirmed, render kept
    sandbox("b")
    k = episode("ep-b")
    yt = FakeYT(upload_status="uploaded")
    rc, rec, lines = run(yt)
    check("b. one upload", len(yt.inserted) == 1, yt.inserted)
    st = yt.inserted[0]["status"] if yt.inserted else {}
    sn = yt.inserted[0]["snippet"] if yt.inserted else {}
    check("b. uploaded PRIVATE, never public at once", st.get("privacyStatus") == "private", st)
    check("b. scheduled for the next sleep day at 20:00 Central", st.get("publishAt") == TUE_2000_CT, st)
    check("b. altered or synthetic content = yes", st.get("containsSyntheticMedia") is True, st)
    check("b. made for kids = no", st.get("selfDeclaredMadeForKids") is False, st)
    check("b. the kit's own title, description and tags",
          sn.get("title") == k["title"] and sn.get("description") == k["description"]
          and sn.get("tags") == k["body"]["snippet"]["tags"], sn)
    got = WU.read_kit("ep-b")
    check("b. the id, schedule and YouTube's read-back are recorded",
          got.get("video_id") == "vid1" and got.get("scheduled_publish_at") == TUE_2000_CT
          and (got.get("youtube_confirmed") or {}).get("upload_status") == "uploaded", got)
    check("b. the run is green with work done", rc == 0 and not rec, (rc, rec))
    check("b. the render is KEPT while YouTube is still processing",
          WL.video_path("ep-b").exists() and (WL.audio_dir("ep-b") / "0000.wav").exists())
    check("b. the uploaded episode is never voiced again", WL.handed_on("ep-b"))

    # c. a later night: processed -> the local render and wavs go
    yt2 = FakeYT(upload_status="processed")
    rc, rec, lines = run(yt2)
    check("c. nothing uploaded twice", yt2.inserted == [], yt2.inserted)
    check("c. deleted only once YouTube reports it processed",
          not WL.video_path("ep-b").exists() and not (WL.audio_dir("ep-b") / "0000.wav").exists()
          and WU.read_kit("ep-b").get("pruned"), WU.read_kit("ep-b"))

    # d. the supply gate: 14+ days of the format already waiting
    sandbox("d")
    episode("ep-old", scheduled_publish_at="2026-11-23T02:00:00Z", video_id="old1", uploaded=True,
            pruned={"at": "x"})
    episode("ep-new")
    yt = FakeYT()
    rc, rec, lines = run(yt)
    check("d. 14+ days waiting holds the upload", yt.inserted == [], yt.inserted)
    check("d. the hold is a green note, not red",
          rec.get("code") == "WHISPER_UPLOAD_HOLD" and rc == 0, (rc, rec))
    check("d. the held render waits on the Mac", WL.video_path("ep-new").exists())

    # e. the wrong channel, or no token at all
    sandbox("e")
    episode("ep-e")
    yt = FakeYT(handle="@howweknowdeep")
    rc, rec, lines = run(yt)
    check("e. a token for another channel uploads nothing", yt.inserted == [])
    check("e. it is WHISPER_WRONG_CHANNEL, with a morning line",
          rec.get("code") == "WHISPER_WRONG_CHANNEL" and len(lines) == 1, (rec, lines))
    sandbox("e2")
    episode("ep-e2")
    rc, rec, lines = run(None)
    check("e. no usable token (LOOP_DRY_RUN refuses it) is WHISPER_YT_TOKEN_INVALID",
          rec.get("code") == "WHISPER_YT_TOKEN_INVALID", rec)

    # f. quota
    sandbox("f")
    episode("ep-f")
    WU.afford = lambda: False
    yt = FakeYT()
    rc, rec, lines = run(yt)
    WU.afford = lambda: True
    check("f. no allowance left uploads nothing", yt.inserted == [])
    check("f. it is UPLOAD_QUOTA, with a morning line",
          rec.get("code") == "UPLOAD_QUOTA" and len(lines) == 1, (rec, lines))
    sandbox("f2")
    episode("ep-f2")
    rc, rec, lines = run(FakeYT(insert_error=WU.QuotaSpent("quotaExceeded")))
    check("f. YouTube's quotaExceeded is UPLOAD_QUOTA",
          rec.get("code") == "UPLOAD_QUOTA" and not WU.read_kit("ep-f2").get("video_id"), rec)

    # g. a lane check fails at upload time
    sandbox("g")
    episode("ep-g", synthetic=False)
    yt = FakeYT()
    rc, rec, lines = run(yt)
    check("g. a kit without the altered-content box is refused, never sent",
          yt.inserted == [] and rec.get("code") == "WHISPER_UPLOAD_REFUSED", (yt.inserted, rec))
    # h. an unverified channel (11 Nov 2026: a 1 h 43 min upload was abandoned and removed)
    sandbox("h")
    episode("ep-h")
    yt = FakeYT(long_uploads="eligible")
    rc, rec, lines = run(yt)
    check("h. a long video is not sent while longUploadsStatus is not allowed",
          yt.inserted == [] and rec.get("code") == "WHISPER_LONG_UPLOADS_NOT_ALLOWED" and len(lines) == 1,
          (yt.inserted, rec, lines))

    # i. an upload YouTube no longer lists is lost, never "still processing": sent again
    sandbox("i")
    episode("ep-i", uploaded=True, video_id="gone1", uploaded_at="2026-11-06T10:00:00Z",
            privacy="private", scheduled_publish_at="2026-11-11T02:00:00Z")
    yt = FakeYT(gone={"gone1"})
    rc, rec, lines = run(yt)
    k = WU.read_kit("ep-i")
    check("i. the removed upload's render is sent again in the same run",
          len(yt.inserted) == 1 and k.get("video_id") == "vid1", (yt.inserted, k))
    check("i. the old id is kept under lost_uploads",
          [x.get("video_id") for x in k.get("lost_uploads", [])] == ["gone1"], k.get("lost_uploads"))
    check("i. a removed upload sent again is one morning line, never AWAITING_PROCESSING or a red stop",
          rec.get("code") != "WHISPER_AWAITING_PROCESSING" and rc in (0, None)
          and any("uploaded again" in x for x in lines), (rc, rec, lines))
    sandbox("i2")
    episode("ep-i2", uploaded=True, video_id="gone2", uploaded_at="2026-11-06T10:00:00Z",
            lost_uploads=[{"video_id": "a"}, {"video_id": "b"}])
    yt = FakeYT(gone={"gone2"})
    rc, rec, lines = run(yt)
    check("i. a third removal is not re-sent and is WHISPER_UPLOAD_LOST",
          yt.inserted == [] and rec.get("code") == "WHISPER_UPLOAD_LOST", (yt.inserted, rec))

    # j. a failed frame check that names clips repairs itself
    import whisper_reel as R                                # noqa: E402
    sandbox("j")
    episode("ep-j", reel=[[0.0, 18.0, "pixabay:1"], [18.0, 18.0, "pixabay:2"], [36.0, 18.0, "pixabay:3"]])

    def fails_clip(video, slug, c):
        raise FC.PictureCheckFailed("PICTURE_CHECK_FAILED at 0:21 (not real footage: a 3D render)",
                                    [(21.0, "not real footage: a 3D render")])
    yt = FakeYT()
    rc, rec, lines = run(yt, fails_clip)
    k = WU.read_kit("ep-j")
    check("j. nothing is sent", yt.inserted == [], yt.inserted)
    check("j. the clip on screen at the failing time is refused, and only it",
          set(WL.refused_clips()) == {"pixabay:2"}, WL.refused_clips())
    check("j. nobody is paged: no red stop and no morning line",
          rec.get("code") != "FRAME_CHECK_FAILED" and rec.get("disposition") != "needs_human" and lines == [],
          (rec, lines))
    check("j. the failed render is out of the way and the episode is back in line",
          not WU.set_aside("ep-j").exists() and not WL.video_path("ep-j").exists()
          and not WL.handed_on("ep-j") and k.get("repairs") == 1, k.get("repairs"))
    calm = [{"post_id": f"pixabay:{i}", "calm_set": "calm-night", "seconds": 30.0, "subject": f"s{i}"}
            for i in (1, 2, 3)]
    shown = [a["post_id"] for a in R.pool("calm:calm-night", calm, C)]
    check("j. the reel never places a refused clip again", shown == ["pixabay:1", "pixabay:3"], shown)

    # k. a render set aside on an earlier night: repaired, rendered again, uploaded
    sandbox("k")
    episode("ep-k", frame_check={"passed": False, "file": "x", "at": "2026-11-06T10:00:00Z",
                                 "why": "PICTURE_CHECK_FAILED at 4:41 (not real footage: 3D render), "
                                        "16:41 (black pillarbox bars at the sides)"})
    WL.video_path("ep-k").replace(WU.set_aside("ep-k"))
    WL.ready_to_render = lambda c=None: [] if (WL.video_path("ep-k").exists() or WL.handed_on("ep-k")) else ["ep-k"]
    rendered: list[str] = []

    def renders(slug):
        rendered.append(slug)
        WL.video_path(slug).write_bytes(b"new" * 100)
        return 0
    old_reel = lambda slug: [[270.0, 18.0, "pixabay:9"], [990.0, 18.0, "mixkit:7"], [1008.0, 18.0, "pixabay:1"]]  # noqa: E731
    yt = FakeYT()
    lines = []
    try:
        WU.run(now=NOW, yt=yt, checker=passes, notify=lambda t: lines.append(t) or "noted",
               renderer=renders, reel_of=old_reel)
    except SystemExit:
        pass
    check("k. both clips named by the old message are refused",
          set(WL.refused_clips()) == {"pixabay:9", "mixkit:7"}, WL.refused_clips())
    check("k. it is rendered again from its kept voice", rendered == ["ep-k"], rendered)
    check("k. the new render is checked and uploaded the same run",
          len(yt.inserted) == 1 and WU.read_kit("ep-k").get("video_id") == "vid1", yt.inserted)

    # l. repaired MAX_REPAIRS times and still failing: the red stop, set aside
    sandbox("l")
    WL.ready_to_render = lambda c=None: []
    episode("ep-l", repairs=WU.MAX_REPAIRS, reel=[[0.0, 40.0, "pixabay:5"]])
    yt = FakeYT()
    rc, rec, lines = run(yt, fails_clip)
    check("l. past the repair cap it is FRAME_CHECK_FAILED, red, with a morning line",
          rec.get("code") == "FRAME_CHECK_FAILED" and rec.get("disposition") == "needs_human"
          and len(lines) == 1, (rec, lines))
    check("l. the file stays set aside and no clip is refused",
          WU.set_aside("ep-l").exists() and WL.refused_clips() == {}, WL.refused_clips())

    # m. the cloud author: a rendered script is not "waiting"; one lane's refusal is not the run's
    import whisper_author as WA                             # noqa: E402
    sandbox("m")
    episode("ep-m")
    WL.video_path("ep-m").unlink()                          # the cloud holds the kit, never the render
    check("m. a script with a measured kit counts as made where the render is absent", WL.made("ep-m"))
    k = WU.read_kit("ep-m")
    k["length_basis"] = "estimated"
    WU.write_kit("ep-m", k)
    check("m. a script whose kit is only an estimate is still waiting", not WL.made("ep-m"))
    wrote: list[str] = []
    WA.WL.weekly_mix = lambda c=None, nums=None: ({"food": 1, "neville": 2, "money": 1}, [])
    WA.waiting_in = lambda lane, c: [x for x in wrote if x == lane]
    WA.sleep_lanes = lambda c: ["food"]
    WA.next_episode = lambda lane, c: {"slug": "food-ep"}

    def refuse_food(e, c):
        raise WA.WL_SegmentRefused("food-ep", ["LENGTH estimated 1 h 39 min"])

    def write(lane, c):
        wrote.append(lane)
        return WL.ROOT / "scripts" / "whisper" / f"{lane}-{len(wrote)}.md"
    WA.author_sleep, WA.write_next = refuse_food, write

    class Args:
        cmd = None
    os.environ["LOOP_STOPS_DIR"] = str(TMP / "m" / "stops")
    try:
        rc = WA.run(Args(), C)
    except SystemExit as e:
        rc = e.code
    check("m. the other lanes' scripts are written after food's is refused",
          sorted(wrote) == ["money", "money", "neville", "neville"] and rc in (0, None), (wrote, rc))
    wrote.clear()
    WA.write_next = lambda lane, c: (_ for _ in ()).throw(WA.WL_SegmentRefused(lane, ["x"]))
    try:
        rc = WA.run(Args(), C)
    except SystemExit as e:
        rc = e.code
    stop = TMP / "m" / "stops" / f"{common.week_id()}-{WA.STAGE}.json"
    rec = json.loads(stop.read_text()) if stop.exists() else {}
    check("m. a run where every lane is refused is the named stop, never a green nothing",
          rec.get("code") == "WHISPER_SEGMENT_REFUSED", rec)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

if not examined:
    print("FAIL: nothing examined")
    raise SystemExit(1)
if fails:
    print(f"{len(fails)} failure(s):")
    for f in fails:
        print(f"  - {f}")
    raise SystemExit(1)
print(f"whisper upload: {examined} check(s) passed")
