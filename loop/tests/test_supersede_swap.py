"""A private upload whose render was superseded after it went up is SWAPPED.

WHY (2026-10-15). how-deep-can-a-sperm-whale-go went up as hh5mMno-Iis
(private, publishAt 2026-11-09T16:00Z) at 2026-10-13T14:05Z from the Mac. Its
ledger row reached main at 19:34Z (#215), so the 14:44Z cloud queue-reopen
(loop/lengthen.py queue_slugs -> published_slugs) saw it as still queued and
re-opened it; the Mac re-rendered it on 14 Oct. Nothing handled "uploaded
privately, then superseded": the OLD opening would have aired on 9 Nov.

loop/supersede_swap.py (run by loop/cloud_upload.py before the day's uploads)
must, with the YouTube calls stubbed and every state file in a temp dir:
  1. swap a private, scheduled, superseded-after-upload video: new cut uploaded,
     dated with the SAME publishAt, same live title, captioned; the old one made
     private with its publishAt cleared - NEVER deleted; ledger, Shorts hand-off
     targets and the caption record repointed to the new id;
  2. never touch a public video (ledger public, date passed, or reads back
     public) - no upload, no privacy write;
  3. ignore a row uploaded AFTER its render was superseded;
  4. carry a swap it cannot afford, and raise SUPERSEDED_SWAP_LATE when the
     publish time is closer than the next run;
  5. resume an upload still processing on the next run without uploading twice;
  6. be wired into cloud_upload.run before the new-upload selection;
  7. hold no delete path.

NEGATIVE PROOF (2026-10-15): making candidates() return [] fails case 1
(16 checks: the private video stays on the old cut); dropping both public checks (ledger and
read-back) fails case 2; replacing make_private+cancel_schedule with a delete call fails cases 1
and 5 (10 checks, "never deleted" among them). Restored -> green.

  8. (2026-10-16) poll a stale read-back after each verified write rather than
     stop red on one immediate read; a write that never applies still stops.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"      # nothing here may reach the real channel

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import captions_lane as CL                                  # noqa: E402
import common                                               # noqa: E402
import ledger                                               # noqa: E402
import quota                                                # noqa: E402
import supersede_swap as SW                                 # noqa: E402

fails: list[str] = []
examined = 0


def check(cond, msg):
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


class Stop(Exception):
    def __init__(self, code):
        self.code = code


class St:
    def __init__(self):
        self.notes, self.works = [], []

    def note(self, m):
        self.notes.append(m)

    def work(self, m):
        self.works.append(m)

    def named_stop(self, code, message, **kw):
        raise Stop(code)


class FakeApi:
    """YouTube, in memory. Has no delete; any attempt to reach one is recorded."""

    def __init__(self, videos, process_after=0):
        self.v = videos            # id -> {privacy, publishAt, title, upload_status}
        self.calls: list[tuple] = []
        self.n = 0
        self.process_after = process_after

    def __getattr__(self, name):
        if "delete" in name.lower():
            self.calls.append(("DELETE", name))
            return lambda *a, **k: None
        raise AttributeError(name)

    def status(self, vid):
        self.calls.append(("status", vid))
        x = self.v.get(vid)
        if not x:
            return {"found": False}
        if x.get("upload_status") == "uploaded" and self.process_after <= 0:
            x["upload_status"] = "processed"
        self.process_after -= 1
        return {"found": True, **x}

    def payload(self, slug, q):
        return {"snippet": {"title": "rebuilt title", "description": "d"},
                "status": {"privacyStatus": "private"}}

    def upload(self, payload, render):
        self.n += 1
        vid = f"NEW{self.n}"
        self.calls.append(("upload", vid, payload["snippet"]["title"]))
        self.v[vid] = {"privacy": "private", "publishAt": None,
                       "title": payload["snippet"]["title"],
                       "upload_status": "uploaded"}
        return vid

    def thumbnail(self, vid, img):
        self.calls.append(("thumbnail", vid))

    def schedule(self, vid, stamp):
        self.calls.append(("schedule", vid, stamp))
        self.v[vid].update(privacy="private", publishAt=stamp)

    def make_private(self, vid):
        self.calls.append(("private", vid))
        self.v[vid]["privacy"] = "private"

    def cancel_schedule(self, vid):
        self.calls.append(("cancel", vid))
        was = self.v[vid].get("publishAt")
        self.v[vid]["publishAt"] = None
        return was

    def insert_caption(self, vid, srt):
        self.calls.append(("caption", vid))
        return f"CAP-{vid}"


class StaleApi(FakeApi):
    """YouTube whose read-back lags a status write by `lag` reads - what run
    38913876948 met: F684ebB13gg's schedule applied, the next read said
    publishAt=None. `never` = the write is accepted and never applied."""

    def __init__(self, videos, lag=2, never=False):
        super().__init__(videos)
        self.lag, self.never, self.shown, self.pending = lag, never, {}, {}

    def _write(self, vid, real, before):
        self.shown[vid] = before
        self.pending[vid] = 0 if self.never else self.lag
        if self.never:
            self.v[vid].update(before)
        return real

    def schedule(self, vid, stamp):
        before = {k: self.v[vid].get(k) for k in ("privacy", "publishAt")}
        super().schedule(vid, stamp)
        self._write(vid, None, before)
        if self.never:
            self.pending.pop(vid)

    def cancel_schedule(self, vid):
        before = {k: self.v[vid].get(k) for k in ("privacy", "publishAt")}
        return self._write(vid, super().cancel_schedule(vid), before)

    def status(self, vid):
        got = super().status(vid)
        if self.pending.get(vid, 0) > 0:
            self.pending[vid] -= 1
            return {**got, **self.shown[vid]}
        return got


TMP = Path(tempfile.mkdtemp(prefix="supersede-swap-"))
saved = {"led": ledger.LEDGER, "q": quota.STATE, "state": SW.STATE,
         "sup": SW.SUPERSEDED, "sh": SW.SHORTS_LEDGER, "cs": CL.STATE_FILE,
         "cd": CL.CAPTIONS_DIR, "dry": common._dry_run_refuses}
AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-11-09T16:00:00Z"


def setup(rows, sup, shorts=None, spent=0):
    ledger.LEDGER = TMP / "ledger.json"
    quota.STATE = TMP / "quota.json"
    SW.STATE = TMP / "swaps.json"
    SW.SUPERSEDED = TMP / "superseded.json"
    SW.SHORTS_LEDGER = TMP / "shorts.json"
    CL.STATE_FILE = TMP / "captions.json"
    CL.CAPTIONS_DIR = TMP / "captions"
    CL.CAPTIONS_DIR.mkdir(exist_ok=True)
    for f in (SW.STATE, CL.STATE_FILE):
        f.unlink(missing_ok=True)
    ledger.LEDGER.write_text(json.dumps({"published": rows, "queued": []}))
    SW.SUPERSEDED.write_text(json.dumps(sup))
    SW.SHORTS_LEDGER.write_text(json.dumps({"published": shorts or []}))
    quota.STATE.write_text(json.dumps({"day": quota._today(), "spent": spent,
                                       "by_lane": {}}))
    for r in rows:
        (CL.CAPTIONS_DIR / f"{r['slug']}.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhi\n", encoding="utf-8")


def jload(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def row(slug, vid, uploaded, stamp=STAMP, **kw):
    return {"slug": slug, "question": slug, "video_id": vid, "title": "t",
            "uploaded_at": uploaded, "privacy": "private",
            "scheduled_publish_at": stamp, **kw}


def go(api, reserve=0, at=AT):
    st = St()
    try:
        out = SW.run(st, api_factory=lambda: api,
                     shelf_look=lambda s: (f"r/{s}", f"t/{s}"),
                     fetch=lambda k, d: (d.write_bytes(b"x"), d)[1], tmp=TMP,
                     lane="cloud-upload", reserve=reserve, at=at,
                     sleep=lambda s: None, wait_s=60)
    except Stop as e:
        out = {"swapped": [], "public": [], "waiting": {}, "inflight": [],
               "stop": e.code}
    return st, out


SUP = {"superseded_at": "2026-10-14T04:00:05+00:00", "sha256": "x"}

try:
    common._dry_run_refuses = lambda p: False     # temp paths only, see setup()

    # 1 ------------------------------------------------------------ the swap
    setup([row("whale", "OLD", "2026-10-13T14:05:07+00:00")], {"whale": SUP},
          shorts=[{"video_id": "S1", "handoff_episode": "OLD", "handoff": "done"}])
    api = FakeApi({"OLD": {"privacy": "private", "publishAt": STAMP,
                           "title": "Live title", "upload_status": "processed"}})
    st, out = go(api)
    check(out["swapped"] == ["whale"] and not out.get("stop"),
          f"1 not swapped: {out}")
    ups = [c for c in api.calls if c[0] == "upload"]
    check(len(ups) == 1 and ups[0][2] == "Live title",
          f"1 one upload under the LIVE title expected: {ups}")
    check(("schedule", "NEW1", STAMP) in api.calls,
          "1 new video not dated with the SAME publishAt")
    check(api.v.get("NEW1", {}).get("privacy") == "private"
          and api.v.get("NEW1", {}).get("publishAt") == STAMP, "1 new video not scheduled")
    check(api.v["OLD"]["privacy"] == "private" and not api.v["OLD"]["publishAt"],
          "1 superseded-after-upload private video left on the old cut/schedule")
    check("OLD" in api.v and not any(c[0] == "DELETE" for c in api.calls),
          "1 the old video was deleted - it must be privated, never deleted")
    pos = {c: i for i, c in enumerate(api.calls)}
    check(pos.get(("schedule", "NEW1", STAMP), 10**9)
          < pos.get(("private", "OLD"), -1),
          "1 the old video was privated before the new one was dated")
    led = jload(ledger.LEDGER, {}).get("published", [])
    old_r = next((r for r in led if r["video_id"] == "OLD"), {})
    new_r = next((r for r in led if r["video_id"] == "NEW1"), {})
    check(old_r.get("status") == "superseded_duplicate" and old_r.get("retired_at")
          and "scheduled_publish_at" not in old_r
          and old_r.get("schedule_was") == STAMP,
          f"1 old ledger row not retired as superseded_duplicate: {old_r}")
    check(new_r.get("scheduled_publish_at") == STAMP
          and new_r.get("replaces") == "OLD", f"1 new ledger row wrong: {new_r}")
    sh = (jload(SW.SHORTS_LEDGER, {}).get("published") or [{}])[0]
    check(sh.get("handoff_episode") == "NEW1" and sh.get("handoff") == "pending",
          f"1 Shorts hand-off still points at the old id: {sh}")
    cs = jload(CL.STATE_FILE, {}).get("videos", {})
    check(cs.get("NEW1", {}).get("caption_id") == "CAP-NEW1",
          "1 caption track not recorded for the new id")
    check(SW.candidates(json.loads(ledger.LEDGER.read_text()),
                        {"whale": SUP}) == [],
          "1 a finished swap is still a candidate - it would swap again")
    api2 = FakeApi(dict(api.v))
    go(api2)
    check(not any(c[0] == "upload" for c in api2.calls),
          "1 a second run re-uploaded an already-swapped episode")

    # 2/3 ----------------------------------------------- public never touched
    setup([row("pub", "P1", "2026-10-13T00:00:00+00:00", privacy="public"),
           row("due", "P2", "2026-10-13T00:00:00+00:00",
               stamp="2026-10-14T16:00:00Z"),
           row("live", "P3", "2026-10-13T00:00:00+00:00"),
           row("after", "A1", "2026-10-14T05:00:00+00:00")],
          {s: SUP for s in ("pub", "due", "live", "after")})
    api = FakeApi({"P1": {"privacy": "public"}, "P2": {"privacy": "public"},
                   "P3": {"privacy": "public", "publishAt": None},
                   "A1": {"privacy": "private", "publishAt": STAMP}})
    st, out = go(api)
    writes = [c for c in api.calls if c[0] not in ("status",)]
    check(writes == [], f"2 a public video was swapped or written: {writes}")
    check(sorted(out["public"]) == ["due", "live", "pub"],
          f"2 public videos not named: {out['public']}")
    check(all(c[1] != "A1" for c in api.calls),
          "3 a row uploaded after its supersede was treated as stale")

    # 4 ------------------------------------------------- quota: carry / late
    setup([row("whale", "OLD", "2026-10-13T14:05:07+00:00")], {"whale": SUP},
          spent=quota.DAILY - quota.HEADROOM - SW.SWAP_UNITS + 1)
    api = FakeApi({"OLD": {"privacy": "private", "publishAt": STAMP}})
    st, out = go(api)
    check("whale" in out["waiting"] and "quota" in out["waiting"]["whale"]
          and not any(c[0] == "upload" for c in api.calls),
          f"4 an unaffordable swap was started: {out}")
    late_at = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
    _, out = go(FakeApi({"OLD": {"privacy": "private", "publishAt": STAMP}}),
                at=late_at)
    check(out.get("stop") == "SUPERSEDED_SWAP_LATE",
          f"4 a swap that cannot finish before publish raised no "
          f"SUPERSEDED_SWAP_LATE stop: {out.get('stop')}")
    pol = json.loads((LOOP / "stop_policy.json").read_text())
    check("SUPERSEDED_SWAP_LATE" not in json.dumps(pol.get("self_resolving", {})),
          "4 SUPERSEDED_SWAP_LATE must stay needs_human (it reaches her)")

    # 5 ------------------------------------------- still processing: resume
    setup([row("whale", "OLD", "2026-10-13T14:05:07+00:00")], {"whale": SUP})
    api = FakeApi({"OLD": {"privacy": "private", "publishAt": STAMP,
                           "upload_status": "processed"}}, process_after=10**6)
    st, out = go(api)
    check(out["inflight"] == ["whale"] and api.v["OLD"]["publishAt"] == STAMP
          and not any(c[0] in ("private", "cancel") for c in api.calls),
          f"5 the old video was retired before the new one processed: {out}")
    api.process_after = 0
    st, out = go(api)
    check(out["swapped"] == ["whale"]
          and sum(c[0] == "upload" for c in api.calls) == 1,
          f"5 resume did not finish, or uploaded twice: {out}")

    # 8 --------------------------- a stale read-back is not a failed write
    # 2026-10-16, run 38913876948: the schedule applied, the immediate read
    # said publishAt=None, the lane stopped red. Both verified writes (the new
    # cut's date, the old cut's cleared date) must poll, not judge one read.
    setup([row("whale", "OLD", "2026-10-13T14:05:07+00:00")], {"whale": SUP})
    api = StaleApi({"OLD": {"privacy": "private", "publishAt": STAMP,
                            "title": "Live title", "upload_status": "processed"}},
                   lag=3)
    st, out = go(api)
    check(out["swapped"] == ["whale"] and not out.get("stop"),
          f"8 a stale read-back after the schedule write stopped the swap: {out}")
    check(api.v["NEW1"]["publishAt"] == STAMP and not api.v["OLD"]["publishAt"],
          "8 the swap did not finish on the real (lagged) state")
    check(sum(c[0] == "schedule" for c in api.calls) == 1,
          "8 a lagged read made the swap write the schedule twice")
    # ...and a write YouTube never applies is still the named stop.
    setup([row("whale", "OLD", "2026-10-13T14:05:07+00:00")], {"whale": SUP})
    api = StaleApi({"OLD": {"privacy": "private", "publishAt": STAMP,
                            "upload_status": "processed"}}, never=True)
    st, out = go(api)
    check(out.get("stop") == "SUPERSEDED_SWAP_NOT_SCHEDULED"
          and api.v["OLD"]["publishAt"] == STAMP
          and not any(c[0] in ("private", "cancel") for c in api.calls),
          f"8 a schedule that never applied did not stop with the old video "
          f"untouched: {out}")
    # resume: the earlier write applied after all - read first, never re-sent
    api.never = False
    api.v["NEW1"].update(privacy="private", publishAt=STAMP)
    st, out = go(api)
    check(out["swapped"] == ["whale"]
          and sum(c[0] == "schedule" for c in api.calls) == 1,
          f"8 a resumed swap re-sent a schedule YouTube already holds: {out}")

    # 6 ------------------------------------------------------ wired, not inert
    src = (LOOP / "cloud_upload.py").read_text(encoding="utf-8")
    body = src[src.index("def run(limit"):]
    check("run_swaps(st" in body and body.index("run_swaps(st")
          < body.index("backfill.library_pending("),
          "6 cloud_upload.run does not run the swap before new uploads")
    check("shorts_reserve()" in src[src.index("def run_swaps"):src.index("def run(limit")],
          "6 the swap is not in the episode lane's quota order")

    # 7 ------------------------------------------------------ no delete path
    sw_src = (LOOP / "supersede_swap.py").read_text(encoding="utf-8").lower()
    check('"delete"' not in sw_src and "method=\"delete\"" not in sw_src
          and "videos.delete" not in sw_src.replace("never", ""),
          "7 supersede_swap.py gained a delete path")

    # the real repo: the episode that started this is a candidate or swapped
    real = json.loads(saved["led"].read_text())
    real_sup = json.loads(saved["sup"].read_text())
    whale = [r for r in real["published"]
             if r.get("slug") == "how-deep-can-a-sperm-whale-go"]
    check(whale and (any(r in SW.candidates(real, real_sup) for r in whale)
                     or any(r.get("replaces") for r in whale)),
          "real: how-deep-can-a-sperm-whale-go is neither queued for the swap "
          "nor swapped")
finally:
    ledger.LEDGER, quota.STATE, SW.STATE = saved["led"], saved["q"], saved["state"]
    SW.SUPERSEDED, SW.SHORTS_LEDGER = saved["sup"], saved["sh"]
    CL.STATE_FILE, CL.CAPTIONS_DIR = saved["cs"], saved["cd"]
    common._dry_run_refuses = saved["dry"]

if examined == 0:
    print("FAIL test_supersede_swap: examined nothing")
    sys.exit(1)
if fails:
    print(f"FAIL test_supersede_swap ({len(fails)}/{examined}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"PASS test_supersede_swap ({examined} checks)")
