"""The long-form repackage lane, against a FIXTURED YouTube API.

Owner decisions 12-13 Oct 2026 (repackage job 1). Every state file is a
scratch copy, R2 is the filesystem stub, LOOP_DRY_RUN=1 keeps arming from
recording, and the YouTube client is a fixture that records every call.

  1. apply: the new title goes onto the LIVE snippet (merged - categoryId and
     description survive), variant A is set as the thumbnail, 101 units are
     recorded under lane "repackage", titles.json gets applied_at, the ledger
     row its title; a title that no longer passes is not applied;
  2. THE QUOTA GUARD (negative proof): with the Shorts lane's 3,400 and the
     episode upload's 1,700 still unspent and too little left beside them, apply
     and reupload REFUSE (QUOTA_EXHAUSTED, with resets_at) and spend nothing;
     the same day with the Shorts lane already spent fits - the reserve is
     what refused;
  3. slots: fixed local times, at most LONG_FORM_PER_DAY a day, never past or
     inside the lead time, never a taken slot;
  4. reupload phase 1: the shelved render must be the spliced cut (sha256);
     the new video goes up private with a publishAt at a repackage slot and its
     variant-A thumbnail; the old video is untouched;
  5. phase 2: once the new id is public, the ledger row, the Shorts hand-off
     and the playlist point at it, the old id is set PRIVATE (verified) and
     recorded old->new; the client has no delete method at all;
  6. V50 passes on the real repo and fails on a re-pointed slug the ledger
     does not agree with.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
TMP = Path(tempfile.mkdtemp(prefix="repackage-"))
os.environ.update({"LOOP_DRY_RUN": "1", "LOOP_STOPS_DIR": str(TMP / "stops"),
                   "LOOP_BREAKER_FLAG": str(TMP / "breaker.json"),
                   "R2_LOCAL_DIR": str(TMP / "r2"),
                   "GITHUB_EVENT_NAME": "workflow_dispatch"})
os.environ.pop("LONG_FORM_PER_DAY", None)
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import ledger                                                 # noqa: E402
import lengthen                                               # noqa: E402
import longform_title as LT                                   # noqa: E402
import quota                                                  # noqa: E402
import r2                                                     # noqa: E402
import repackage as RP                                        # noqa: E402
import thumb_contract as TC                                   # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUG = "how-hot-does-a-welding-arc-get"
GOOD = "A welding arc core reaches 11,000 degrees Celsius"
ledger.LEDGER = TMP / "ledger.json"
LT.STATE = TMP / "titles.json"
lengthen.STATE = TMP / "lengthen.json"
quota.STATE = TMP / "quota.json"
RP.STATE, RP.SHORTS_LEDGER, RP.PLAYLISTS = (TMP / "repackage.json",
                                            TMP / "shorts.json", TMP / "pl.json")
TC.VARIANTS_DIR = str(TMP / "variants")
(TMP / "variants" / SLUG).mkdir(parents=True)
(TMP / "variants" / SLUG / "A.jpg").write_bytes(b"\xff\xd8 variant A")


def reset_state():
    ledger.LEDGER.write_text(json.dumps({"published": [{
        "slug": SLUG, "question": "how hot does a welding arc get",
        "video_id": "OLD1", "uploaded_at": "2026-09-01T00:00:00+00:00",
        "privacy": "public", "playlist_item_id": "PLI-OLD"}], "queued": []}))
    LT.STATE.write_text(json.dumps({"titles": {SLUG: {
        "slug": SLUG, "new_title": GOOD, "checks_passed": True,
        "question": "how hot does a welding arc get", "applied_at": None}}}))
    RP.SHORTS_LEDGER.write_text(json.dumps({"published": [
        {"slug": SLUG, "video_id": "S1", "handoff_episode": "OLD1", "handoff": "done"}]}))
    RP.PLAYLISTS.write_text(json.dumps({"playlists": {
        "materials-and-manufacturing": {"id": "PL-MAT"},
        "deep-sea-ocean-science": {"id": "PL-DEEP"}}}))
    for p in (quota.STATE, RP.STATE, lengthen.STATE):
        p.unlink(missing_ok=True)


class FakeYT:
    def __init__(self):
        self.calls: list[tuple] = []
        self.privacy = {"OLD1": "public", "NEW1": "private"}

    def video(self, vid):
        self.calls.append(("video", vid))
        return {"snippet": {"title": "Old title", "categoryId": "27",
                            "description": "desc", "tags": ["t"]},
                "status": {"privacyStatus": self.privacy.get(vid, "private")}}

    def update_snippet(self, vid, snippet):
        self.calls.append(("update_snippet", vid, snippet))

    def set_status(self, vid, privacy, publish_at=None):
        self.calls.append(("set_status", vid, privacy, publish_at))
        self.privacy[vid] = privacy

    def set_thumbnail(self, vid, img):
        self.calls.append(("set_thumbnail", vid, Path(img).name))

    def upload(self, payload, video):
        self.calls.append(("upload", payload["snippet"]["title"], Path(video).name))
        return "NEW1"

    def playlist_insert(self, pid, vid):
        self.calls.append(("playlist_insert", pid, vid))
        return "PLI-NEW"


def run(fn, *a, **kw) -> str | None:
    """Run a lane; return the named stop code it took (None = ran clean)."""
    for f in (TMP / "stops").glob("*.json"):
        f.unlink()
    try:
        fn(*a, **kw)
    except SystemExit:
        pass
    for f in (TMP / "stops").glob("*repackage*.json"):
        d = json.loads(f.read_text())
        if d.get("code"):
            return d["code"]
    return None


def spent(lane="repackage") -> int:
    return (json.loads(quota.STATE.read_text()).get("by_lane") or {}).get(lane, 0) \
        if quota.STATE.exists() else 0


def today_pt() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ 1. apply
reset_state()
yt = FakeYT()
code = run(RP.run_apply, yt=yt)
ups = [c for c in yt.calls if c[0] == "update_snippet"]
check(code is None and ups and ups[0][2]["title"] == GOOD
      and ups[0][2]["categoryId"] == "27" and ups[0][2]["description"] == "desc",
      f"apply did not merge the new title onto the live snippet: {code} {yt.calls}")
check(("set_thumbnail", "OLD1", "A.jpg") in yt.calls, "variant A was not set")
check(spent() == RP.APPLY_UNITS == 101, f"apply recorded {spent()} units, not 101")
row = json.loads(LT.STATE.read_text())["titles"][SLUG]
check(row.get("applied_at") and row.get("applied_video_id") == "OLD1",
      f"applied_at was not written: {row}")
check(ledger.load()["published"][0].get("title") == GOOD, "the ledger row's title was not updated")
code = run(RP.run_apply, yt=FakeYT())
check(code == "REPACKAGE_UP_TO_DATE", f"a second apply was not UP_TO_DATE: {code}")
reset_state()
LT.STATE.write_text(json.dumps({"titles": {SLUG: {
    "new_title": "Welding — and how we know", "checks_passed": True}}}))
yt = FakeYT()
run(RP.run_apply, yt=yt)
check(not [c for c in yt.calls if c[0] == "update_snippet"],
      "a title that no longer passes was applied")

# ----------------------------------------------------------- 2. quota guard
reset_state()
quota.STATE.write_text(json.dumps({"day": today_pt(), "spent": 4450,
                                   "by_lane": {"captions": 4450}}))
yt = FakeYT()
code = run(RP.run_apply, yt=yt)
stop = next((d for d in (json.loads(f.read_text()) for f in (TMP / "stops").glob("*repackage*.json"))
             if d.get("code")), {})
check(code == "QUOTA_EXHAUSTED" and not yt.calls and spent() == 0
      and (stop.get("detail") or {}).get("resets_at"),
      f"apply exceeded the day while the Shorts/upload reserves were unspent: "
      f"{code} {yt.calls} {spent()}")
check(RP.reserve() == quota.PER_VIDEO + quota.SHORTS_PER_DAY_PEAK * quota.PER_VIDEO == 5100,
      f"the lane reserve is {RP.reserve()}, not upload 1,700 + Shorts 3,400")
quota.STATE.write_text(json.dumps({"day": today_pt(), "spent": 4450,
                                   "by_lane": {"captions": 1050, "shorts-cloud": 3400}}))
yt = FakeYT()
code = run(RP.run_apply, yt=yt)
check(code is None and spent() == 101,
      f"with the Shorts lane already spent the same day must fit: {code} {spent()}")

# ------------------------------------------------------------------ 3. slots
cfg = dict(RP.DEFAULTS, long_form_per_day=2)
tz = ZoneInfo(cfg["tz"])
now = datetime(2026, 10, 14, 15, 30, tzinfo=tz)           # past 11:00, 2h before 15:00? no: 17:30 lead
s = RP.slots(5, set(), now=now, cfg=cfg)
local = [x.astimezone(tz) for x in s]
per_day: dict = {}
for x in local:
    per_day[x.date()] = per_day.get(x.date(), 0) + 1
check(len(s) == 5 and all(f"{x:%H:%M}" in ("11:00", "15:00") for x in local)
      and max(per_day.values()) <= 2 and all(x > now + timedelta(hours=2) for x in s)
      and local[0].date() == now.date() + timedelta(days=1),
      f"slots broke the fixed-time/per-day/lead rules: {local}")
taken = {RP._iso(s[0])}                                       # noqa: SLF001
check(RP._iso(RP.slots(1, taken, now=now, cfg=cfg)[0]) != RP._iso(s[0]),   # noqa: SLF001
      "a taken slot was handed out again")
check(RP.slots(3, set(), now=now, cfg=dict(cfg, long_form_per_day=0)) == [],
      "long_form_per_day=0 still produced slots")

# ------------------------------------------------------------- 4. phase 1
reset_state()
render = TMP / "render.mp4"
render.write_bytes(b"the spliced cut")
shelf = r2.require()
_dest = TMP / "r2" / r2.render_key(SLUG)          # the stub's own layout;
_dest.parent.mkdir(parents=True, exist_ok=True)     # put() refuses under DRY_RUN
_dest.write_bytes(render.read_bytes())
Path(str(_dest) + r2.META_SUFFIX).write_text(json.dumps({"sha256": lengthen.sha256(render)}))
check((shelf.head(r2.render_key(SLUG)) or {}).get("sha256") == lengthen.sha256(render),
      "fixture: the stub shelf does not report the render's sha256")
lengthen.STATE.write_text(json.dumps({"episodes": {SLUG: {
    "status": "spliced", "new_render_sha256": "not-the-shelved-one"}}}))
yt = FakeYT()
run(RP.run_reupload, yt=yt, shelf=shelf)
check(not [c for c in yt.calls if c[0] == "upload"],
      "a shelved render that is not the spliced cut was uploaded")
lengthen.STATE.write_text(json.dumps({"episodes": {SLUG: {
    "status": "spliced", "new_render_sha256": lengthen.sha256(render)}}}))
RP.STATE.unlink(missing_ok=True)
yt = FakeYT()
code = run(RP.run_reupload, yt=yt, shelf=shelf)
rec = RP.load()["reuploads"].get(SLUG) or {}
at = datetime.fromisoformat(rec.get("scheduled_publish_at", "1970-01-01T00:00:00Z")
                            .replace("Z", "+00:00")).astimezone(tz)
st_calls = [c for c in yt.calls if c[0] == "set_status"]
check(code is None and ("upload", GOOD, f"{SLUG}.mp4") in yt.calls
      and rec.get("new_video_id") == "NEW1" and rec.get("old_video_id") == "OLD1"
      and rec.get("phase") == "scheduled" and f"{at:%H:%M}" in ("11:00", "15:00")
      and st_calls == [("set_status", "NEW1", "private", rec["scheduled_publish_at"])]
      and ("set_thumbnail", "NEW1", "A.jpg") in yt.calls
      and spent() == RP.REUPLOAD_UNITS,
      f"phase 1 did not upload the longer cut privately at a slot: {code} {rec} {yt.calls}")
check(ledger.load()["published"][0]["video_id"] == "OLD1",
      "the ledger moved before the new video was public")
check(lengthen.load()["episodes"][SLUG].get("reuploaded_at"),
      "lengthen.json does not record the re-upload")
RP.STATE.unlink()
lengthen.STATE.write_text(json.dumps({"episodes": {SLUG: {
    "status": "spliced", "new_render_sha256": lengthen.sha256(render)}}}))
quota.STATE.write_text(json.dumps({"day": today_pt(), "spent": 3000,
                                   "by_lane": {"captions": 3000}}))
yt = FakeYT()
code = run(RP.run_reupload, yt=yt, shelf=shelf)
check(code == "QUOTA_EXHAUSTED" and not [c for c in yt.calls if c[0] == "upload"],
      f"reupload started a 1,700-unit upload the day could not hold: {code} {yt.calls}")

# ------------------------------------------------------------- 5. phase 2
quota.STATE.unlink()
RP.save({"reuploads": {SLUG: dict(rec, scheduled_publish_at="2026-01-01T17:00:00Z")},
         "replaced": {}})
yt = FakeYT()
yt.privacy["NEW1"] = "public"
code = run(RP.run_reupload, yt=yt, shelf=shelf)
row = ledger.load()["published"][0]
sh = json.loads(RP.SHORTS_LEDGER.read_text())["published"][0]
check(row["video_id"] == "NEW1" and row["replaced_video_ids"][0]["video_id"] == "OLD1"
      and row["playlist_item_id"] == "PLI-NEW"
      and sh["handoff_episode"] == "NEW1" and sh["handoff"] == "pending"
      and ("set_status", "OLD1", "private", None) in yt.calls
      and ("playlist_insert", "PL-MAT", "NEW1") in yt.calls
      and RP.load()["replaced"].get("OLD1") == "NEW1",
      f"phase 2 did not re-point everything and private the old cut: {row} {sh} {yt.calls}")
check(not any("delete" in n.lower() for n in dir(RP.YouTube)) and
      'method="DELETE"' not in (LOOP / "repackage.py").read_text(),
      "the repackage client has a delete path")

# ------------------------------------------------------------------- 6. V50
import validate as V                                          # noqa: E402
res = V.v50_repackage_state().as_dict()
check(not res["failures"], f"V50 fails on the scratch books it just wrote: {res['failures']}")
led = json.loads(ledger.LEDGER.read_text())
led["published"][0]["video_id"] = "OLD1"
ledger.LEDGER.write_text(json.dumps(led))
res = V.v50_repackage_state().as_dict()
check(any("still points at" in f for f in res["failures"]),
      f"V50 passed a replaced slug the ledger does not agree with: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
