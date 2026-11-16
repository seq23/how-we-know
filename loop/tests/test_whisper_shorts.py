"""Whisper Almanac Shorts (loop/whisper_shorts.py), against a fake YouTube.

  a. a real ffmpeg cut of a 16:9 render is 1080x1920 and 35-60 s;
  b. an uploaded episode with its render gets ONE Short: private, the
     episode's publish date, altered content = yes, the AI line first, a link
     to the full video; recorded in the kit, quota spent, OUTPUT line;
  c. the render is pruned only once the Short is made (whisper_upload);
  d. nothing waiting is the green WHISPER_SHORTS_NOTHING_TO_CUT, never ZERO_WORK;
  e. a failing cut is the red WHISPER_SHORT_FAILED, nothing uploaded;
  f. no quota above How We Know's reserve is UPLOAD_QUOTA, nothing cut.
Hard-fails on zero checks.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"
TMP = Path(tempfile.mkdtemp(prefix="whisper-shorts-"))
os.environ["LOOP_BREAKER_FLAG"] = str(TMP / "breaker.json")

import common                                               # noqa: E402
import whisper_lane as WL                                   # noqa: E402
import whisper_shorts as WS                                 # noqa: E402
import whisper_upload as WU                                 # noqa: E402

SPENT: list[int] = []
WS.spend = SPENT.append
WS.afford = lambda: True
C = WL.cfg()
NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)
PUB = "2026-11-17T02:00:00Z"
fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


class FakeYT:
    def __init__(self, upload_status="processed"):
        self.inserted: list[tuple[dict, Path]] = []
        self.upload_status = upload_status

    def insert(self, body, video):
        assert video.exists()
        self.inserted.append((json.loads(json.dumps(body)), video))
        return f"short{len(self.inserted)}"

    def status(self, ids):
        return {i: {"uploadStatus": self.upload_status} for i in ids}


def sandbox(name: str) -> None:
    d = TMP / name
    for sub in ("scripts", "kits", "work", "stops"):
        (d / sub).mkdir(parents=True)
    WL.SCRIPTS, WL.KITS, WL.WORK = d / "scripts", d / "kits", d / "work"
    os.environ["LOOP_STOPS_DIR"] = str(d / "stops")


def episode(slug: str, **extra) -> dict:
    t = "Law of assumption sleep meditation · whispered ASMR, Neville Goddard (50 min)"
    d = f"A guided whisper.\n{C['channel']['ai_voice_line']}\n50 min of soft whispering.\n"
    k = {"slug": slug, "kind": "neville", "title": t, "description": d, "length_s": 3041.0,
         "body": WL.upload_body(t, d, C, "neville"), "uploaded": True, "video_id": "LONG1",
         "scheduled_publish_at": PUB, **extra}
    (WL.SCRIPTS / f"{slug}.md").write_text(f"# {slug}\n")
    (WL.KITS / slug).mkdir(parents=True)
    (WL.KITS / slug / "kit.json").write_text(json.dumps(k))
    v = WL.video_path(slug)
    v.parent.mkdir(parents=True, exist_ok=True)
    v.write_bytes(b"mp4" * 100)
    return k


def fake_cut(slug, k, out):
    out.write_bytes(b"short")
    return out


def run(yt, cutter=fake_cut):
    try:
        rc = WS.run(now=NOW, yt=yt, cutter=cutter)
    except SystemExit as e:
        rc = e.code
    stop = Path(os.environ["LOOP_STOPS_DIR"]) / f"{common.week_id()}-{WS.LANE}.json"
    return rc, (json.loads(stop.read_text()) if stop.exists() else {})


try:
    # a. the real cut
    sandbox("a")
    episode("ep-a")
    src = WL.video_path("ep-a")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=1280x720:r=24:d=70",
                    "-f", "lavfi", "-i", "sine=f=220:d=70", "-shortest", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", str(src)], check=True)
    out = WS.cut("ep-a", WU.read_kit("ep-a"), TMP / "a-short.mp4")
    import shorts as S                                      # noqa: E402
    s = S.probe_stream(str(out))
    secs = S.probe_duration(str(out))
    check("a. the cut is vertical 1080x1920", (s.get("width"), s.get("height")) == (1080, 1920), s)
    check("a. the cut runs 35-60 s", 35 <= secs <= 60, secs)

    # b. one Short per uploaded episode
    sandbox("b")
    episode("ep-b")
    yt = FakeYT()
    rc, rec = run(yt)
    check("b. exactly one Short uploaded", len(yt.inserted) == 1, yt.inserted)
    body = yt.inserted[0][0] if yt.inserted else {"snippet": {}, "status": {}}
    st, sn = body["status"], body["snippet"]
    check("b. private with the episode's publish date",
          st.get("privacyStatus") == "private" and st.get("publishAt") == PUB, st)
    check("b. altered content = yes, made for kids = no",
          st.get("containsSyntheticMedia") is True and st.get("selfDeclaredMadeForKids") is False, st)
    check("b. #shorts title, AI line first, link to the full video",
          "#shorts" in sn.get("title", "") and len(sn["title"]) <= 100
          and sn.get("description", "").startswith(C["channel"]["ai_voice_line"])
          and "https://youtu.be/LONG1" in sn["description"].split("\n")[1], sn)
    k = WU.read_kit("ep-b")
    check("b. the Short is recorded and its quota spent",
          (k.get("short") or {}).get("video_id") == "short1" and SPENT == [WS.UNITS], (k, SPENT))
    check("b. green with work done", rc == 0 and not rec, (rc, rec))
    check("b. the cut file does not stay on disk", not WS.short_path("ep-b").exists())
    rc, rec = run(FakeYT())
    check("b. a second night makes no second Short", rec.get("code") == "WHISPER_SHORTS_NOTHING_TO_CUT", rec)

    # c. prune waits for the Short
    sandbox("c")
    episode("ep-c")
    from types import SimpleNamespace
    notes: list[str] = []
    stub = SimpleNamespace(note=notes.append, work=notes.append)
    n, gone, _ = WU.prune_confirmed(FakeYT("processed"), WU.kits(), stub, NOW)
    check("c. a processed upload with no Short keeps its render",
          n == 0 and WL.video_path("ep-c").exists(), (n, notes))
    k = WU.read_kit("ep-c")
    k["short"] = {"video_id": "s"}
    WU.write_kit("ep-c", k)
    n, gone, _ = WU.prune_confirmed(FakeYT("processed"), WU.kits(), stub, NOW)
    check("c. once the Short exists the render is pruned", n == 1 and not WL.video_path("ep-c").exists(), notes)

    # d. nothing waiting
    sandbox("d")
    rc, rec = run(FakeYT())
    check("d. nothing to cut is the green WHISPER_SHORTS_NOTHING_TO_CUT",
          rec.get("code") == "WHISPER_SHORTS_NOTHING_TO_CUT" and rc == 0, (rc, rec))

    # e. a failing cut
    sandbox("e")
    episode("ep-e")
    yt = FakeYT()

    def broken(slug, k, out):
        raise RuntimeError("ffmpeg exited 1")
    rc, rec = run(yt, broken)
    check("e. a failing cut is red WHISPER_SHORT_FAILED and uploads nothing",
          rec.get("code") == "WHISPER_SHORT_FAILED" and rc != 0 and yt.inserted == [], (rc, rec))
    check("e. the try is counted", WU.read_kit("ep-e").get("short_tries") == 1)

    # f. no quota
    sandbox("f")
    episode("ep-f")
    WS.afford = lambda: False
    yt = FakeYT()
    rc, rec = run(yt)
    WS.afford = lambda: True
    check("f. no quota is UPLOAD_QUOTA, nothing cut or sent",
          rec.get("code") == "UPLOAD_QUOTA" and yt.inserted == [] and not WU.read_kit("ep-f").get("short_tries"),
          (rec, yt.inserted))
finally:
    pass

if examined == 0:
    raise SystemExit("FAIL: examined nothing")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print(f"PASS: {examined} whisper Shorts check(s)")
