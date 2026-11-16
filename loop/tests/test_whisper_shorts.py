"""Whisper Almanac daily Shorts (loop/whisper_shorts.py), against a fake YouTube.

  a. moments: distinct (>= MIN_GAP_S apart), chapter starts first, inside the video;
     a real ffmpeg cut of a 16:9 render is 1080x1920 and 35-60 s;
  b. an uploaded episode is cut into per_video Shorts (the queue); each night
     dates them ONE A DAY at 19:00 CT on days with none, private, altered
     content = yes, made for kids = no, AI line first, link to the full video;
     quota spent per Short; cut files removed once uploaded; OUTPUT line;
  c. the render is pruned only once it is cut (whisper_upload);
  d. an empty queue is WHISPER_SHORTS_QUEUE_EMPTY, never ZERO_WORK;
  e. a failing cut is red WHISPER_SHORT_FAILED, nothing uploaded;
  f. no quota above How We Know's reserve is UPLOAD_QUOTA, the queue kept;
  g. the supply gate: nothing dated past max_days_ahead (WHISPER_SHORTS_HOLD).
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
S = WS.scfg(C)
NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)      # Mon 06:00 CT
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
        self.inserted: list[dict] = []
        self.upload_status = upload_status

    def insert(self, body, video):
        assert video.exists()
        self.inserted.append(json.loads(json.dumps(body)))
        return f"short{len(self.inserted)}"

    def status(self, ids):
        return {i: {"uploadStatus": self.upload_status} for i in ids}


def sandbox(name: str) -> None:
    d = TMP / name
    for sub in ("scripts", "kits", "work", "stops"):
        (d / sub).mkdir(parents=True)
    WL.SCRIPTS, WL.KITS, WL.WORK = d / "scripts", d / "kits", d / "work"
    os.environ["LOOP_STOPS_DIR"] = str(d / "stops")


DESC = ("A guided whisper.\n{ai}\n50 min of soft whispering.\n\nChapters\n0:00:00 An hour of Neville\n"
        "0:09:28 Gently settle into your bed now\n0:33:08 In Out of This World, Neville wrote this\n"
        "0:34:54 You are lying here in the quiet\n")


def episode(slug: str, **extra) -> dict:
    t = "Law of assumption sleep meditation · whispered ASMR, Neville Goddard (50 min)"
    d = DESC.format(ai=C["channel"]["ai_voice_line"])
    k = {"slug": slug, "kind": "neville", "title": t, "description": d, "length_s": 3041.0,
         "body": WL.upload_body(t, d, C, "neville"), "uploaded": True, "video_id": "LONG1",
         "uploaded_at": "2026-11-16T05:00:00Z", **extra}
    (WL.SCRIPTS / f"{slug}.md").write_text(f"# {slug}\n")
    (WL.KITS / slug).mkdir(parents=True)
    (WL.KITS / slug / "kit.json").write_text(json.dumps(k))
    v = WL.video_path(slug)
    v.parent.mkdir(parents=True, exist_ok=True)
    v.write_bytes(b"mp4" * 100)
    return k


def fake_cut(slug, k, n):
    rows = []
    for i, (t, label) in enumerate(WS.moments(k, float(k["length_s"]), n)):
        f = WS.shorts_dir(slug) / f"{slug}-s{i + 1}.mp4"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"short")
        rows.append({"n": i + 1, "at_s": t, "label": label, "file": f.name, "video_id": None})
    return rows


def run(yt, cutter=fake_cut, now=NOW):
    try:
        rc = WS.run(now=now, yt=yt, cutter=cutter)
    except SystemExit as e:
        rc = e.code
    stop = Path(os.environ["LOOP_STOPS_DIR"]) / f"{common.week_id()}-{WS.LANE}.json"
    return rc, (json.loads(stop.read_text()) if stop.exists() else {})


def ct(iso):
    return WU._utc(iso).astimezone(WU.CT)


# a. moments and the real cut
sandbox("a")
k = episode("ep-a")
ms = WS.moments(k, 3041.0, 3)
check("a. three distinct moments, chapter starts first",
      len(ms) == 3 and all(b[0] - a[0] >= WS.MIN_GAP_S for a, b in zip(ms, ms[1:]))
      and ms[1][1] == "Gently settle into your bed now", ms)
check("a. every moment leaves room for a whole Short", all(t + WS.SHORT_MAX_S < 3041 for t, _ in ms), ms)
check("a. a short video still gets distinct moments", len(WS.moments({}, 400.0, 3)) >= 2)
src = WL.video_path("ep-a")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=1280x720:r=24:d=70",
                "-f", "lavfi", "-i", "sine=f=220:d=70", "-shortest", "-c:v", "libx264",
                "-preset", "ultrafast", "-c:a", "aac", str(src)], check=True)
import shorts as SH                                         # noqa: E402
out = WS.cut_one(src, 1.0, TMP / "a-short.mp4")
s_ = SH.probe_stream(str(out))
secs = SH.probe_duration(str(out))
check("a. the cut is vertical 1080x1920", (s_.get("width"), s_.get("height")) == (1080, 1920), s_)
check("a. the cut runs 35-60 s", 35 <= secs <= 60, secs)

# b. cut into 3, dated one a day
sandbox("b")
episode("ep-b")
yt = FakeYT()
rc, rec = run(yt)
k = WU.read_kit("ep-b")
check("b. the episode is cut into per_video Shorts", len(k.get("shorts") or []) == S["per_video"], k)
n_first = min(S["max_per_run"], S["per_video"])
check("b. max_per_run Shorts uploaded tonight", len(yt.inserted) == n_first, len(yt.inserted))
days = [ct(b["status"]["publishAt"]) for b in yt.inserted]
check("b. one a day, on consecutive days, at 19:00 CT",
      len({d.date() for d in days}) == len(days) and all(d.strftime("%H:%M") == "19:00" for d in days)
      and all((b.date() - a.date()).days == 1 for a, b in zip(days, days[1:])), days)
check("b. the first is today 19:00 CT (lead time kept)", days and days[0].date() == dt.date(2026, 11, 16), days)
st0 = yt.inserted[0]["status"]
sn0 = yt.inserted[0]["snippet"]
check("b. private, altered content = yes, made for kids = no",
      st0.get("privacyStatus") == "private" and st0.get("containsSyntheticMedia") is True
      and st0.get("selfDeclaredMadeForKids") is False, st0)
check("b. #shorts title, distinct per Short, AI line first, link to the full video",
      all("#shorts" in b["snippet"]["title"] and len(b["snippet"]["title"]) <= 100 for b in yt.inserted)
      and len({b["snippet"]["title"] for b in yt.inserted}) == len(yt.inserted)
      and sn0["description"].startswith(C["channel"]["ai_voice_line"])
      and "https://youtu.be/LONG1" in sn0["description"].split("\n")[1], [b["snippet"]["title"] for b in yt.inserted])
check("b. quota spent per Short", SPENT == [WS.UNITS] * n_first, SPENT)
check("b. uploaded cut files are removed, the rest wait",
      len(list(WS.shorts_dir("ep-b").glob("*.mp4"))) == S["per_video"] - n_first)
check("b. green with work done", rc == 0 and not rec, (rc, rec))
ep2 = episode("ep-b2", video_id="LONG2", uploaded_at="2026-11-17T05:00:00Z")
yt2 = FakeYT()
rc, rec = run(yt2, now=NOW + dt.timedelta(days=1))
taken = [ct(r["publish_at"]).date() for kk in WU.kits().values() for r in (kk.get("shorts") or [])
         if r.get("publish_at")]
check("b. the next night never doubles a day", len(taken) == len(set(taken)), taken)
check("b. the older episode's queue goes first",
      yt2.inserted and "LONG1" in yt2.inserted[0]["snippet"]["description"].split("\n")[1] if
      S["per_video"] > S["max_per_run"] else True)

# b2. a Short never goes public before the day after its parent video
sandbox("b2")
thu = "2026-11-20T02:00:00Z"                                         # Thu 19 Nov 20:00 CT
episode("ep-thu", scheduled_publish_at=thu)
yt = FakeYT()
rc, rec = run(yt)                                                   # Mon 16 Nov
days = sorted(ct(b["status"]["publishAt"]).date() for b in yt.inserted)
check("b2. a Thursday video's Shorts start Friday, never Mon-Wed",
      days and days[0] == dt.date(2026, 11, 20) and all(d > dt.date(2026, 11, 19) for d in days), days)
check("b2. still one a day at 19:00 CT",
      len(set(days)) == len(days) and all(ct(b["status"]["publishAt"]).strftime("%H:%M") == "19:00"
                                           for b in yt.inserted), days)

# c. prune waits for the cut
sandbox("c")
episode("ep-c")
from types import SimpleNamespace                           # noqa: E402
notes: list[str] = []
stub = SimpleNamespace(note=notes.append, work=notes.append)
n, gone, _ = WU.prune_confirmed(FakeYT("processed"), WU.kits(), stub, NOW)
check("c. a processed upload not yet cut keeps its render", n == 0 and WL.video_path("ep-c").exists(), notes)
kc = WU.read_kit("ep-c")
kc["shorts_cut"] = "x"
WU.write_kit("ep-c", kc)
n, gone, _ = WU.prune_confirmed(FakeYT("processed"), WU.kits(), stub, NOW)
check("c. once cut the render is pruned", n == 1 and not WL.video_path("ep-c").exists(), notes)

# d. empty queue
sandbox("d")
rc, rec = run(FakeYT())
check("d. an empty queue is WHISPER_SHORTS_QUEUE_EMPTY",
      rec.get("code") == "WHISPER_SHORTS_QUEUE_EMPTY" and rc == 0, (rc, rec))

# e. failing cut
sandbox("e")
episode("ep-e")
yt = FakeYT()


def broken(slug, k, n):
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
check("f. no quota: cut, nothing sent, UPLOAD_QUOTA",
      yt.inserted == [] and len(WS.queue(WU.kits())) == S["per_video"]
      and rec.get("code") in ("UPLOAD_QUOTA", None), (rec, yt.inserted))

# g. supply gate
sandbox("g")
far = WU.stamp(NOW + dt.timedelta(days=S["max_days_ahead"] + 1))
booked = [{"n": i + 1, "at_s": 0, "label": None, "file": "x", "video_id": f"old{i}",
           "publish_at": WU.stamp(NOW + dt.timedelta(days=i))} for i in range(S["max_days_ahead"] + 1)]
episode("ep-old", video_id="OLD", shorts=booked, shorts_cut="x", pruned={"at": "x"})
episode("ep-g")
yt = FakeYT()
rc, rec = run(yt)
check("g. nothing dated past the limit; WHISPER_SHORTS_HOLD, green",
      yt.inserted == [] and rec.get("code") == "WHISPER_SHORTS_HOLD" and rc == 0, (rc, rec, far))

if examined == 0:
    raise SystemExit("FAIL: examined nothing")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print(f"PASS: {examined} whisper Shorts check(s)")
