"""The demand verdict (phase 4), against a FIXTURED YouTube API.

Every state file is a scratch copy, LOOP_DRY_RUN=1 keeps credentials and
arming out of reach, and both clients are fixtures that record every call.

  1. the pull writes one history row per PUBLIC LONG-FORM video - a Short in
     the ledger and a private video get none - and re-running the same day
     adds nothing (append-only);
  2. retention: a curve is read at 30 s / runtime; an EMPTY curve is the
     string "insufficient", its floor "unknown", never a zero;
  3. verdict states PASS / WATCH / FAIL / INSUFFICIENT, CTR "unknown" until a
     Studio CSV is ingested, then judged;
  4. the second packaging: a FAIL video >= 7 days gets a new, different
     passing title and variant B; with an ACTIVE Studio test it gets the
     title only and set_thumbnail is never called; never round 3, never a
     Short, never under 7 days;
  5. the Monday email traces every number to the snapshot and REFUSES
     (DEMAND_EMAIL_UNTRACED, nothing written) when one does not;
  6. V70 (demand.problems) passes the scratch books and fails - NEGATIVE
     PROOFS - on: a missing history row, an empty pull, a zero retention, a
     judged floor on insufficient data, a third round, a thumbnail changed
     during a test, a repackaged Short, a repackage under 7 days, an email
     number that is not in its snapshot.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
TMP = Path(tempfile.mkdtemp(prefix="demand-"))
os.environ.update({"LOOP_DRY_RUN": "1", "LOOP_STOPS_DIR": str(TMP / "stops"),
                   "LOOP_BREAKER_FLAG": str(TMP / "breaker.json"),
                   "GITHUB_EVENT_NAME": "workflow_dispatch"})
sys.path.insert(0, str(LOOP))
import domains  # noqa: E402,F401  (loop/domains.py before visuals/ joins the path)
sys.path.append(str(ROOT / "visuals"))

import demand as D                                            # noqa: E402
import ledger                                                 # noqa: E402
import longform_title as LT                                   # noqa: E402
import quota                                                  # noqa: E402
import thumb_contract as TC                                   # noqa: E402
from common import NamedStop                                  # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUG = "how-hot-does-a-welding-arc-get"
GOOD = "A welding arc core reaches 11,000 degrees Celsius"
TODAY = date(2026, 10, 30)
ledger.LEDGER = TMP / "ledger.json"
LT.STATE = TMP / "titles.json"
quota.STATE = TMP / "quota.json"
D.SNAPSHOT = TMP / "demand.json"
D.HISTORY = TMP / "demand_history.jsonl"
D.OUTDIR = TMP / "demand"
D.SHORTS_LEDGER = TMP / "shorts_ledger.json"
D.today = lambda: TODAY
TC.VARIANTS_DIR = str(TMP / "variants")
TC.build_variants(SLUG, out_root=str(TMP / "variants"), title=GOOD)
SCRIPT = (ROOT / "scripts" / f"{SLUG}.md").read_text(encoding="utf-8")
check(not LT.title_problems(GOOD, SCRIPT), f"fixture title must pass: "
      f"{LT.title_problems(GOOD, SCRIPT)}")

# V1 public, retention curve, fails every floor; V2 public, no curve;
# V3 private; S1 a Short that leaked into the long-form ledger.
ledger.LEDGER.write_text(json.dumps({"published": [
    {"slug": SLUG, "video_id": "V1", "title": "Old one"},
    {"slug": SLUG, "video_id": "V2", "title": "Old two"},
    {"slug": SLUG, "video_id": "V3", "title": "Private"},
    {"slug": SLUG, "video_id": "S1", "title": "A short"}], "queued": []}))
D.SHORTS_LEDGER.write_text(json.dumps({"published": [{"video_id": "S1"}]}))
LT.STATE.write_text(json.dumps({"titles": {}}))


class FakeAPI:
    def __init__(self, v1_views=120, v1_avp=22.0, curve=True):
        self.calls: list[tuple] = []
        self.analytics_calls = 0
        self.data_units = 0
        self.v1_views, self.v1_avp, self.curve = v1_views, v1_avp, curve

    def videos(self, ids):
        self.data_units += 1
        out = []
        for vid in ids:
            priv = "private" if vid == "V3" else "public"
            out.append({"id": vid, "status": {"privacyStatus": priv},
                        "snippet": {"title": f"Live {vid}",
                                    "publishedAt": "2026-10-01T15:00:00Z"},
                        "contentDetails": {"duration": "PT10M"}})
        return out

    def report(self, metrics, dimensions, ids, start, extra_filter=""):
        self.analytics_calls += 1
        self.calls.append((metrics, dimensions, tuple(ids), start))
        if dimensions == "elapsedVideoTimeRatio":
            if ids == ["V1"] and self.curve:
                return [{"elapsedVideoTimeRatio": 0.01, "audienceWatchRatio": 1.0},
                        {"elapsedVideoTimeRatio": 0.05, "audienceWatchRatio": 0.5},
                        {"elapsedVideoTimeRatio": 0.10, "audienceWatchRatio": 0.3}]
            return []
        if dimensions == "video,insightTrafficSourceType":
            return [{"video": "V1", "insightTrafficSourceType": "YT_SEARCH", "views": 70},
                    {"video": "V1", "insightTrafficSourceType": "RELATED_VIDEO", "views": 30},
                    {"video": "V1", "insightTrafficSourceType": "SUBSCRIBER", "views": 15},
                    {"video": "V1", "insightTrafficSourceType": "EXT_URL", "views": 5}]
        rows = []
        if "V1" in ids:
            rows.append({"video": "V1", "views": self.v1_views,
                         "estimatedMinutesWatched": 300.0, "averageViewDuration": 130,
                         "averageViewPercentage": self.v1_avp, "subscribersGained": 1})
        if "V2" in ids:
            rows.append({"video": "V2", "views": 4, "estimatedMinutesWatched": 9.0,
                         "averageViewDuration": 135, "averageViewPercentage": 55.0,
                         "subscribersGained": 0})
        return rows


class FakeYT:
    def __init__(self):
        self.calls: list[tuple] = []

    def video(self, vid):
        self.calls.append(("video", vid))
        return {"id": vid, "snippet": {"title": f"Live {vid}", "categoryId": "28",
                                       "description": "d"}}

    def update_snippet(self, vid, snippet):
        self.calls.append(("update_snippet", vid, snippet["title"]))

    def set_thumbnail(self, vid, img):
        self.calls.append(("set_thumbnail", vid, Path(img).name))


class St:
    def __init__(self):
        self.done, self.notes, self.units = [], [], []

    def work(self, w):
        self.done.append(w)
        self.units.append(w)

    def note(self, w):
        self.notes.append(w)

    def named_stop(self, code, message, detail=None, unblock="", held_items=None):
        raise NamedStop(code, message, detail, unblock, held_items)


# ------------------------------------------------------------------ 1. pull
print("── 1. one history row per public long-form video, append-only")
doc = D.pull(FakeAPI(), doc={"videos": {}}, day=TODAY)
rows = doc.pop("_rows")
check(doc["pull"]["public_ids"] == ["V1", "V2"],
      f"public long-form ids should be V1, V2 (no Short, no private): "
      f"{doc['pull']['public_ids']}")
check(sorted(r["video_id"] for r in rows) == ["V1", "V2"], f"rows: {rows}")
check(all(r["variant_of"] for r in rows), "every verdict row carries variant_of")
check(D.append_history(rows) == 2, "first append writes both rows")
check(D.append_history(rows) == 0, "a second pull the same day adds no row")
v1 = doc["videos"]["V1"]
check(v1["lifetime"]["traffic"] == {"browse": 15, "suggested": 30, "search": 70,
                                    "external": 5, "other": 0},
      f"traffic split: {v1['lifetime']['traffic']}")
check(v1["days_public"] == 29, f"days public: {v1['days_public']}")

# ------------------------------------------------------------- 2. retention
print("── 2. retention read at 30 s; an empty curve is 'insufficient'")
check(v1["lifetime"]["retention_30s_pct"] == 50.0,
      f"30 s of a 600 s video is ratio 0.05 -> 50 %: {v1['lifetime']['retention_30s_pct']}")
v2 = doc["videos"]["V2"]
check(v2["current"]["retention_30s_pct"] == D.INSUFFICIENT,
      f"no curve must read 'insufficient': {v2['current']['retention_30s_pct']!r}")
check(v2["floors"]["retention_30s"] == D.UNKNOWN, "insufficient -> floor unknown")
check(D.retention_at([], 600) == D.INSUFFICIENT and D.retention_at([(0.01, 1)], None)
      == D.INSUFFICIENT, "retention_at never returns a number without a curve and runtime")

# --------------------------------------------------------------- 3. verdict
print("── 3. verdict states; CTR unknown until Studio")
check(v1["verdict"] == "FAIL", f"V1 fails AVP and retention: {v1['verdict']} {v1['floors']}")
check(v1["floors"]["ctr"] == D.UNKNOWN, "CTR is unknown before any Studio ingest")
check(v2["verdict"] == "INSUFFICIENT", f"V2 has 4 views: {v2['verdict']}")
w = {"current": {"views": 50, "avp_pct": 45.0, "retention_30s_pct": 60.0}}
check(D.judge_video(w) == "WATCH", "mixed floors -> WATCH")
w = {"current": {"views": 50, "avp_pct": 45.0, "retention_30s_pct": 80.0}}
check(D.judge_video(w) == "PASS", "all available floors pass -> PASS")
csvp = TMP / "Table data.csv"
csvp.write_text("Content,Video title,Impressions,Impressions click-through rate (%)\n"
                "Total,,1500,3.1\nV1,Old one,\"1,200\",2.5\nS1,A short,900,9.0\n")
D.SNAPSHOT.write_text(json.dumps(doc))
d2 = D.ingest_studio(csvp, "2026-10-27", doc=copy.deepcopy(doc))
check(d2["videos"]["V1"]["ctr"] == {"pct": 2.5, "impressions": 1200.0,
                                    "as_of": "2026-10-27", "source": "studio"},
      f"Studio CTR merged: {d2['videos']['V1'].get('ctr')}")
check(d2["videos"]["V1"]["floors"]["ctr"] == "fail", "2.5 % is under the 4 % floor")
check("S1" not in d2["videos"], "a Short in the Studio export is never merged")
check(d2["studio"]["skipped"] == 1 and len(d2["_rows"]) == 1, f"{d2['studio']}")

# ------------------------------------------------------ 4. second packaging
print("── 4. second packaging: title + variant B; title only during a test")
D.append_history  # rows already on file


def propose_ok(slug, script, q):
    return {"new_title": GOOD, "checks_passed": True, "problems": []}


def fresh():
    d = D.pull(FakeAPI(), doc={"videos": {}}, day=TODAY)
    d.pop("_rows")
    return d


d = fresh()
check([v["video_id"] for v in D.repackage_candidates(d)] == ["V1"],
      "only the FAIL video >= 7 days is a candidate")
yt, st = FakeYT(), St()
done = D.run_repackage(d, st, yt=yt, propose=propose_ok, day=TODAY)
check(len(done) == 1 and done[0]["thumbnail"] == "B" and done[0]["new_title"] == GOOD,
      f"round 1 -> new title + variant B: {done}")
check(("set_thumbnail", "V1", "B.jpg") in yt.calls, f"variant B set: {yt.calls}")
check(d["videos"]["V1"]["repackage_round"] == 1, "round recorded")
check(quota.report().count("demand") == 1, f"units recorded under lane demand: {quota.report()}")
check(D.repackage_candidates(d) == [], "the just-repackaged video waits 7 days")

d = fresh()
D.cmd_mark_test("V1", True, ["A", "B", "C"], doc=d, day=TODAY)
yt = FakeYT()
done = D.run_repackage(d, St(), yt=yt, propose=propose_ok, day=TODAY)
check(done and done[0]["thumbnail"] is None and done[0]["test_active_at_change"],
      f"active test -> title only: {done}")
check(not any(c[0] == "set_thumbnail" for c in yt.calls),
      "NEGATIVE: set_thumbnail must never be called during an active test")
D.cmd_mark_test("V1", False, None, doc=d, day=TODAY)
check(d["videos"]["V1"]["thumbnail_test"]["active"] is False, "mark-test --end")

d = fresh()
d["videos"]["V1"]["repackage_round"] = 2
check(D.repackage_candidates(d) == [], "never a third automatic round")
d = fresh()
d["videos"]["V1"]["days_public"] = 6
check(D.repackage_candidates(d) == [], "never a video public under 7 days")
d = fresh()
D.SHORTS_LEDGER.write_text(json.dumps({"published": [{"video_id": "S1"},
                                                      {"video_id": "V1"}]}))
check(D.repackage_candidates(d) == [], "never a Short")
D.SHORTS_LEDGER.write_text(json.dumps({"published": [{"video_id": "S1"}]}))
d = fresh()
t, why = D.new_title_for(d["videos"]["V1"] | {"title": GOOD}, propose_ok)
check(t is None and "repeated" in why, f"a repeat of the current title is refused: {why}")

# ------------------------------------------------------------------ 5. email
print("── 5. the Monday email traces every number, or refuses")
d = fresh()
D.run_repackage(d, St(), yt=FakeYT(), propose=propose_ok, day=TODAY)
D.judge(d, TODAY)
subj, body = D.render_email(d)
check(D.untraced(subj + "\n" + body, d) == [],
      f"every number in the email is in the snapshot: {D.untraced(subj + body, d)}")
check(GOOD in body and "Live V1" in body, "old -> new title listed")
check(body.index("Is packaging working") < body.index("## Counts")
      < body.index("## New titles") < body.index("## Hooked")
      < body.index("## Best") < body.index("day-30"), "sections in the owner's order")
bad = D.untraced(body + "\nMedian click-through 9.7 %", d)
check(bad == ["number 9.7"], f"NEGATIVE: an invented number is caught: {bad}")
check(D.untraced("“A title nobody had”", d) == ["title 'A title nobody had'"],
      "NEGATIVE: an invented title is caught")
orig = D.render_email
D.render_email = lambda doc: (orig(doc)[0], orig(doc)[1] + "\nwatched 77.7 %\n")
try:
    D.write_email(d, St())
    check(False, "NEGATIVE: write_email must refuse an untraced number")
except NamedStop as e:
    check(e.code == "DEMAND_EMAIL_UNTRACED", f"refusal code: {e.code}")
check(not list(D.OUTDIR.glob("*.md")) if D.OUTDIR.exists() else True,
      "a refused email writes no file")
D.render_email = orig
path = D.write_email(d, St())
check(path.exists() and path.with_suffix(".json").exists(), "email + its snapshot written")

# ------------------------------------------------------------------ 6. V70
print("── 6. V70 passes sound books and fails each broken one")
D.HISTORY.unlink()
D.append_history([{"date": TODAY.isoformat(), "video_id": x, "source": "analytics"}
                  for x in d["pull"]["public_ids"]])
good_hist = D.history()
check(D.problems(d, good_hist) == [], f"sound books pass: {D.problems(d, good_hist)}")


def breaks(name, mutate, hist=None):
    b = copy.deepcopy(d)
    mutate(b)
    p = D.problems(b, hist if hist is not None else good_hist)
    check(bool(p), f"NEGATIVE ({name}) must fail V70")


breaks("missing history row", lambda b: None, hist=good_hist[:1])
breaks("empty pull", lambda b: b["pull"].update(public_ids=[]))
breaks("zero retention", lambda b: b["videos"]["V2"]["current"].update(retention_30s_pct=0))
breaks("judged on insufficient", lambda b: b["videos"]["V2"]["floors"].update(retention_30s="fail"))
breaks("CTR judged without Studio", lambda b: b["videos"]["V2"]["floors"].update(ctr="fail"))
breaks("third round", lambda b: b["videos"]["V1"]["repackages"].extend(
    [dict(b["videos"]["V1"]["repackages"][0], round=2),
     dict(b["videos"]["V1"]["repackages"][0], round=3)]))
breaks("thumb during test", lambda b: b["videos"]["V1"]["repackages"][0].update(
    test_active_at_change=True, thumbnail="B"))
breaks("under seven days", lambda b: b["videos"]["V1"]["repackages"][0].update(days_public=3))


def short_breaks():
    D.SHORTS_LEDGER.write_text(json.dumps({"published": [{"video_id": "V1"}]}))
    try:
        check(bool(D.problems(d, good_hist)), "NEGATIVE (repackaged Short) must fail V70")
    finally:
        D.SHORTS_LEDGER.write_text(json.dumps({"published": [{"video_id": "S1"}]}))


short_breaks()
md = path.read_text()
path.write_text(md + "\nclick-through 12.3 %\n")
check(bool(D.problems(d, good_hist)), "NEGATIVE (email number not in snapshot) must fail V70")
path.write_text(md)
check(D.problems(d, good_hist) == [], "restored books pass again")

# the validator wiring itself
src = (LOOP / "validate.py").read_text()
check("v70_demand_verdict()" in src and "def v70_demand_verdict" in src,
      "V70 is registered in loop/validate.py run_all")

print(f"\nexamined {examined} checks")
if examined == 0:
    print("FAIL: examined nothing")
    sys.exit(1)
if fails:
    for f in fails:
        print(f"  ✗ {f}")
    sys.exit(1)
print("OK")
