"""The long-form repackage lane, against a FIXTURED YouTube API. Forward only.

Owner decisions 12-13 Oct 2026 (repackage job 1). Every state file is a
scratch copy, LOOP_DRY_RUN=1 keeps arming from recording, and the YouTube
client is a fixture that records every call.

  1. apply: the new title goes onto the LIVE snippet (merged - categoryId and
     description survive), variant A is set as the thumbnail, 101 units are
     recorded under lane "repackage", titles.json gets applied_at, the ledger
     row its title; a PRIVATE SCHEDULED video is covered as well as a public
     one; a title that no longer passes is not applied;
  2. THE QUOTA GUARD (negative proof): with the Shorts lane's 3,400 and the
     episode upload's 1,700 still unspent and too little left beside them, apply
     REFUSES (QUOTA_EXHAUSTED, with resets_at) and spends nothing; the same day
     with the Shorts lane already spent fits - the reserve is what refused;
  3. reschedule: every private, scheduled video moves to the next free slot of
     its own domain's rotation weekday, order kept per domain, one a day, never
     inside 24 h, videos.update only; the ledger keeps rescheduled_from; a dry
     run writes nothing; a video due inside the lead keeps its date;
  4. forward only: the client has no upload, delete or publish method;
  5. V50 passes on the scratch books and fails on a re-dated row off its
     rotation day.
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
                   "GITHUB_EVENT_NAME": "workflow_dispatch"})
os.environ.pop("LONG_FORM_PER_DAY", None)
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import ledger                                                 # noqa: E402
import longform_title as LT                                   # noqa: E402
import quota                                                  # noqa: E402
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
GOOD = "Is a Welding Arc Hotter Than the Sun?"
ledger.LEDGER = TMP / "ledger.json"
LT.STATE = TMP / "titles.json"
quota.STATE = TMP / "quota.json"
TC.VARIANTS_DIR = str(TMP / "variants")
import describe                                               # noqa: E402
describe.STATE = TMP / "descriptions.json"    # never the real search blocks
# A REAL contract set (three variants + contract.json, verify() holds): the
# lane ships variant A only from a set whose contract holds.
TC.build_variants(SLUG, out_root=str(TMP / "variants"), title=GOOD)


def reset_state():
    ledger.LEDGER.write_text(json.dumps({"published": [{
        "slug": SLUG, "question": "how hot does a welding arc get",
        "video_id": "OLD1", "uploaded_at": "2026-09-01T00:00:00+00:00",
        "privacy": "public", "playlist_item_id": "PLI-OLD"}], "queued": []}))
    LT.STATE.write_text(json.dumps({"titles": {SLUG: {
        "slug": SLUG, "new_title": GOOD, "checks_passed": True,
        "question": "how hot does a welding arc get", "applied_at": None}}}))
    quota.STATE.unlink(missing_ok=True)


class FakeYT:
    def __init__(self):
        self.calls: list[tuple] = []
        self.privacy = {"OLD1": "public"}

    def video(self, vid):
        self.calls.append(("video", vid))
        return {"snippet": {"title": "Old title", "categoryId": "27",
                            "description": "desc", "tags": ["t"]},
                "status": {"privacyStatus": self.privacy.get(vid, "private")}}

    def update_snippet(self, vid, snippet):
        self.calls.append(("update_snippet", vid, snippet))

    def set_thumbnail(self, vid, img):
        self.calls.append(("set_thumbnail", vid, Path(img).name))



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

# 1a. a title that went up with no contract variant gets variant A ALONE once
# it exists (job 2, 13 Oct 2026): applied_at must not hide it for good.
reset_state()
VDIR = TMP / "variants" / SLUG
VDIR.rename(VDIR.with_name(SLUG + ".off"))
VDIR.mkdir()
(VDIR / "A.jpg").write_bytes((VDIR.with_name(SLUG + ".off") / "A.jpg").read_bytes())
# a BARE A.jpg (a set refused at B left it behind - how-strong-is-graphene,
# 13 Oct 2026) is not a contract thumbnail and must not ship
check(RP.thumb_for(SLUG) is None, "a bare A.jpg with no contract.json counts as a thumbnail")
yt = FakeYT()
run(RP.run_apply, yt=yt)
row = json.loads(LT.STATE.read_text())["titles"][SLUG]
check(row.get("applied_at") and row.get("thumbnail_applied") is False
      and not [c for c in yt.calls if c[0] == "set_thumbnail"],
      f"with no variant on disk the title should go up alone: {row} {yt.calls}")
check(not RP.apply_plan(), "a title-only row was re-planned with no variant on disk")
import shutil                                                 # noqa: E402
shutil.rmtree(VDIR)
VDIR.with_name(SLUG + ".off").rename(VDIR)
before = spent()
yt = FakeYT()
code = run(RP.run_apply, yt=yt)
row = json.loads(LT.STATE.read_text())["titles"][SLUG]
check(code is None and yt.calls == [("set_thumbnail", "OLD1", "A.jpg")]
      and row.get("thumbnail_applied") is True
      and spent() - before == quota.THUMBNAIL,
      f"the thumbnail-only pass did not set variant A alone for "
      f"{quota.THUMBNAIL} units: {code} {yt.calls} {spent() - before}")
code = run(RP.run_apply, yt=FakeYT())
check(code == "REPACKAGE_UP_TO_DATE", f"after the thumbnail pass: {code}")
# a REBUILT variant A (new text, new bytes) reaches the live video alone
TC.build_variants(SLUG, out_root=str(TMP / "variants"),
                  title="The welding arc is not one thing")
yt = FakeYT()
code = run(RP.run_apply, yt=yt)
check(code is None and yt.calls == [("set_thumbnail", "OLD1", "A.jpg")],
      f"a rebuilt variant A did not reach the live video: {code} {yt.calls}")
code = run(RP.run_apply, yt=FakeYT())
check(code == "REPACKAGE_UP_TO_DATE", f"after the rebuilt thumbnail: {code}")
reset_state()
LT.STATE.write_text(json.dumps({"titles": {SLUG: {
    "new_title": "Welding — and how we know", "checks_passed": True}}}))
yt = FakeYT()
run(RP.run_apply, yt=yt)
check(not [c for c in yt.calls if c[0] == "update_snippet"],
      "a title that no longer passes was applied")

# ------------------------------------- 1c. the demand lane owns a thumbnail
# (coordination, 13 Oct 2026): a live Studio test, or a second packaging round
# (B/C already up) -> the title goes up, variant A does not.
import demand                                                 # noqa: E402
demand.SNAPSHOT = TMP / "demand.json"
for label, vrec in (("test", {"thumbnail_test": {"active": True, "started": "2026-10-10"}}),
                    ("round", {"repackage_round": 1, "thumbnails_used": ["A", "B"]})):
    reset_state()
    demand.SNAPSHOT.write_text(json.dumps({"videos": {"OLD1": {"video_id": "OLD1", **vrec}}}))
    yt = FakeYT()
    run(RP.run_apply, yt=yt)
    check([c for c in yt.calls if c[0] == "update_snippet"]
          and not [c for c in yt.calls if c[0] == "set_thumbnail"],
          f"variant A was pushed over the demand lane's {label}: {yt.calls}")
    check(not [t for t in RP.apply_plan() if t.get("thumb_only")],
          f"a thumbnail-only pass was planned over the demand lane's {label}")
demand.SNAPSHOT.write_text(json.dumps({"videos": {}}))
# V50 holds it: a row whose variant A landed after the test started fails.
import validate as V                                          # noqa: E402
reset_state()
LT.STATE.write_text(json.dumps({"titles": {SLUG: {
    "new_title": GOOD, "checks_passed": True, "applied_at": "2026-10-12T00:00:00+00:00",
    "applied_video_id": "OLD1", "thumbnail_applied": False,
    "thumbnail_applied_at": "2026-10-12T00:00:00+00:00"}}}))
demand.SNAPSHOT.write_text(json.dumps({"videos": {"OLD1": {
    "video_id": "OLD1", "thumbnail_test": {"active": True, "started": "2026-10-10"}}}}))
res = V.v50_repackage_state().as_dict()
check(any("Studio" in f for f in res["failures"]),
      f"V50 passed a variant A that landed during a Studio test: {res['failures']}")
demand.SNAPSHOT.write_text(json.dumps({"videos": {}}))

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

# --------------------------------------------------- 1b. a scheduled video too
reset_state()
led_ = json.loads(ledger.LEDGER.read_text())
led_["published"][0].update(privacy="private", scheduled_publish_at="2026-12-01T16:00:00Z")
ledger.LEDGER.write_text(json.dumps(led_))
yt = FakeYT()
run(RP.run_apply, yt=yt)
check(any(c[0] == "update_snippet" and c[1] == "OLD1" for c in yt.calls),
      "apply skipped a private, scheduled video")

# ------------------------------------------------------------ 3. reschedule
import backfill as B                                          # noqa: E402
import domains                                                # noqa: E402
now = datetime.now(timezone.utc)


def stamp(days: float) -> str:
    return (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


DEEP = ["02-how-deep-sea-creatures-survive-pressure", "04-why-deep-sea-creatures-are-so-scary"]
MAT = ["what-is-kevlar-made-of", "why-is-steel-so-strong"]
assert all(domains.domain_of_slug(x) == "deep-sea-ocean-science" for x in DEEP)
assert all(domains.domain_of_slug(x) == "materials-and-manufacturing" for x in MAT)
rows = [  # off-rotation dates (Sundays/odd days) in a known order
    {"slug": DEEP[0], "video_id": "D0", "privacy": "private", "scheduled_publish_at": stamp(5)},
    {"slug": MAT[0], "video_id": "M0", "privacy": "private", "scheduled_publish_at": stamp(6)},
    {"slug": DEEP[1], "video_id": "D1", "privacy": "private", "scheduled_publish_at": stamp(8)},
    {"slug": MAT[1], "video_id": "M1", "privacy": "private", "scheduled_publish_at": stamp(9)},
    {"slug": DEEP[0], "video_id": "SOON", "privacy": "private", "scheduled_publish_at": stamp(0.5)},
    {"slug": DEEP[1], "video_id": "AIRED", "privacy": "public", "scheduled_publish_at": stamp(-3)},
]
ledger.LEDGER.write_text(json.dumps({"published": rows, "queued": []}))
quota.STATE.unlink(missing_ok=True)


class SchedYT(FakeYT):
    """YouTube as observed 2026-10-13: a re-date applies, but the next
    read-back or two still return the OLD publishAt."""
    STALE_READS = 2

    def __init__(self):
        super().__init__()
        self.pa = {r["video_id"]: r["scheduled_publish_at"] for r in rows}
        self.stale = {}

    def set_schedule(self, vid, publish_at):
        self.calls.append(("set_schedule", vid, publish_at))
        self.stale[vid] = (self.pa.get(vid), self.STALE_READS)
        self.pa[vid] = publish_at

    def status(self, vid):
        old, n = self.stale.get(vid, (None, 0))
        if n:
            self.stale[vid] = (old, n - 1)
            return {"privacy": "private", "publishAt": old}
        return {"privacy": "private", "publishAt": self.pa.get(vid)}


RP.SLEEP = lambda s: None


yt = SchedYT()
code = run(RP.run_reschedule, dry_run=True, yt=yt)
check(not yt.calls and json.loads(ledger.LEDGER.read_text())["published"][0]["scheduled_publish_at"] == stamp(5),
      "a dry-run reschedule wrote something")
plan = {p["video_id"]: p for p in RP.reschedule_plan()}
check("SOON" not in plan and "AIRED" not in plan,
      f"a video due inside the lead, or already public, was planned: {sorted(plan)}")
rot = B.rotation_days()
news = {}
for vid, p in plan.items():
    t = datetime.fromisoformat(p["new"].replace("Z", "+00:00"))
    lt = t.astimezone(B.PUBLISH_TZ)
    news[vid] = t
    check(rot.get(lt.weekday()) == p["domain"] and f"{lt:%H:%M}" == "10:00"
          and t >= now + timedelta(hours=24),
          f"{vid}: re-dated to {lt:%a %H:%M}, not a {p['domain']} rotation slot >= 24h out")
check(news["D0"] < news["D1"] and news["M0"] < news["M1"],
      "the reschedule did not keep each domain's order")
days = [t.astimezone(B.PUBLISH_TZ).date() for t in news.values()]
check(len(days) == len(set(days)), "two re-dated videos share a day")
yt = SchedYT()
code = run(RP.run_reschedule, yt=yt)
led2 = {r["video_id"]: r for r in json.loads(ledger.LEDGER.read_text())["published"]}
check(sorted(c[1] for c in yt.calls if c[0] == "set_schedule") == ["D0", "D1", "M0", "M1"]
      and all(led2[v]["scheduled_publish_at"] == plan[v]["new"]
              and led2[v]["rescheduled_from"] == [r["scheduled_publish_at"] for r in rows if r["video_id"] == v]
              for v in plan)
      and led2["SOON"]["scheduled_publish_at"] == stamp(0.5)
      and spent() == 4 * (quota.VIDEO_UPDATE + quota.VIDEO_READ * 4),
      f"reschedule did not re-date via videos.update, wait out the stale "
      f"read-back and record it: {code} {yt.calls} {spent()}")
# An earlier write that YouTube already applied is recorded, not re-sent.
ledger.LEDGER.write_text(json.dumps({"published": rows, "queued": []}))
yt = SchedYT()
for v_, p_ in plan.items():
    yt.pa[v_] = p_["new"]
code = run(RP.run_reschedule, yt=yt)
led3 = {r["video_id"]: r for r in json.loads(ledger.LEDGER.read_text())["published"]}
check(not [c for c in yt.calls if c[0] == "set_schedule"]
      and all(led3[v]["scheduled_publish_at"] == plan[v]["new"] for v in plan),
      f"a re-date YouTube already held was re-sent or not recorded: {yt.calls}")
ledger.LEDGER.write_text(json.dumps({"published": list(led2.values()), "queued": []}))
code = run(RP.run_reschedule, yt=SchedYT())
check(code == "RESCHEDULE_UP_TO_DATE", f"a second reschedule was not UP_TO_DATE: {code}")

# ------------------------------------------------------------ 4. forward only
check(not any(k in n.lower() for n in dir(RP.YouTube)
              for k in ("upload", "delete", "publish", "insert")),
      f"the repackage client can upload/delete/publish: {dir(RP.YouTube)}")
check(not hasattr(RP, "run_reupload"), "the re-upload command still exists")

# ------------------------------------------------------------------- 5. V50
import validate as V                                          # noqa: E402
LT.STATE.write_text(json.dumps({"titles": {}}))   # this ledger has no OLD1
res = V.v50_repackage_state().as_dict()
check(not res["failures"], f"V50 fails on the scratch books it just wrote: {res['failures']}")
led = json.loads(ledger.LEDGER.read_text())
for r_ in led["published"]:
    if r_["video_id"] == "D0":
        r_["scheduled_publish_at"] = led2["M0"]["scheduled_publish_at"]   # a materials day
ledger.LEDGER.write_text(json.dumps(led))
res = V.v50_repackage_state().as_dict()
check(any("rotation day" in f for f in res["failures"]),
      f"V50 passed a re-dated row off its rotation day: {res['failures']}")

# --- the apply step owns the first minutes of the quota day (16 Oct 2026)
# At 18:30 CT the PT quota day was spent (14 Oct: 9 of 40 fit; 15 Oct: 1 of
# 37). A second cron runs APPLY ONLY right after the reset; every other step
# stays on the evening cron so the Mac's 23:00 CT batch still binds re-opens.
import re as _re                                              # noqa: E402
_wf = (ROOT / ".github" / "workflows" / "loop-repackage.yml").read_text()
_crons = _re.findall(r"^\s*- cron: '([^']+)'", _wf, _re.M)
check(_crons == ["30 23 * * *", "30 8 * * *"],
      f"loop-repackage crons are {_crons}, not the evening run + the 08:30 UTC apply")
_EARLY = "github.event.schedule != '30 8 * * *'"
_steps = {m.group(1).strip(): m.group(2) for m in _re.finditer(
    r"- name: ([^\n]+)\n((?:        [^\n]*\n)+)", _wf)}
_apply = next(v for k, v in _steps.items() if k.startswith("Apply new titles"))
check(_EARLY not in _apply and "repackage.py apply" in _apply,
      "the 08:30 UTC cron does not run the apply step")
for _name in ("Propose long-form titles", "Re-open / extend queued scripts",
              "Build contract thumbnails", "Prepare search blocks"):
    _body = next(v for k, v in _steps.items() if k.startswith(_name))
    check(_EARLY in _body.split("\n", 1)[0] or _EARLY in _body.split("run:", 1)[0],
          f"{_name!r} also runs on the 08:30 UTC apply-only cron")
# 08:30 UTC sits after the PT reset in BOTH clock seasons (07:00 UTC PDT,
# 08:00 UTC PST); 07:30 UTC would land at the END of the old day all winter.

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
