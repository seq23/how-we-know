"""How We Know's Money lane (her calls 8-9 Nov 2026), proved on behaviour.

  1. a How We Know night narrates Money scripts first; deep sea only when no
     Money script waits; food and materials never; nothing to voice is [];
  2. the generic authoring path (loop/draft.py) refuses paused domains and
     leaves Money to loop/money_author.py; deep sea still passes;
  3. R-ADV-04 in code: a Money draft without "not financial advice" or with a
     tip / money promise is refused; the disclaimer is added to the closing;
  4. a Money episode's footage is the Money set only - never NOAA, never a
     deep-sea stock clip, never another set;
  5. the per-lane 30-day check: sums per lane in the test window; a video with
     no measured row, or an unreadable file, is None ("not read"), never 0;
     the check is due 30 days after the test starts;
  6. the real config: both long-form nights, food paused, materials 0 slots,
     Money in the rotation, and the 12 topics queued in rank order;
  7. food long-forms are paused at both halves (author and Mac lane);
  8. a Money plan never carries another domain's graphics.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "loop"))       # loop/domains.py, not visuals/domains.py
os.environ["LOOP_DRY_RUN"] = "1"

import domains as D  # noqa: E402
import lane_check as LC  # noqa: E402
import money_author as MA  # noqa: E402
import night_split as NS  # noqa: E402
from common import config  # noqa: E402

M, DEEP, MAT, FOOD = "money-and-business", "deep-sea-ocean-science", "materials-and-manufacturing", "food-science"
fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


CFG = config()

# ------------------------------------------------------------ 1. the nights
real_scripts = MA.SCRIPTS
with tempfile.TemporaryDirectory() as td:
    sd = Path(td) / "scripts"
    sd.mkdir()
    for s in ("m1", "m2", "d1", "mat1", "f1", "m-done"):
        (sd / f"{s}.md").write_text("x")
    dom = {"m1": M, "m2": M, "m-done": M, "d1": DEEP, "mat1": MAT, "f1": FOOD}.get
    real_loop = NS.LOOP
    NS.LOOP = Path(td) / "loop"                   # scripts/ is LOOP.parent / "scripts"
    try:
        q = ["d1", "mat1", "m1", "f1", "m-done", "m2", "unwritten-money"]
        got, why = NS.longform_slugs(q, dom, lambda s: s == "m-done", CFG)
        check("1a a How We Know night narrates the Money scripts still to voice, in queue order",
              got == ["m1", "m2"], f"{got} ({why})")
        got, why = NS.longform_slugs(["d1", "mat1", "f1", "m-done"], dom, lambda s: s == "m-done", CFG)
        check("1b with no Money script to voice, deep sea fills the night (never materials or food)",
              got == ["d1"], f"{got} ({why})")
        got, why = NS.longform_slugs(["mat1", "f1"], dom, lambda s: False, CFG)
        check("1c paused domains are never narrated; nothing to voice is an empty night with a reason",
              got == [] and why, f"{got} ({why})")
    finally:
        NS.LOOP = real_loop

# ------------------------------------------------- 2. the generic authoring path
rows = [{"slug": "a", "domain": DEEP}, {"slug": "b", "domain": MAT},
        {"slug": "c", "domain": FOOD}, {"slug": "d", "domain": M}]
ok, refused = D.longform_gate(rows, CFG)
check("2a loop/draft.py authors deep sea only: materials and food paused, Money left to its lane",
      [r["slug"] for r in ok] == ["a"] and set(refused) == {"b", "c", "d"}
      and "money_author" in refused["d"], f"{[r['slug'] for r in ok]} {refused}")
src = (ROOT / "loop" / "draft.py").read_text()
check("2b loop/draft.py runs the Money test's gate after the allocation gate",
      "domains.longform_gate(selected, cfg)" in src, "draft.py does not call longform_gate")

# ------------------------------------------------------------ 3. R-ADV-04
GOOD = """# Old title
**Domain:** money-and-business

## Narration

### Cold open
The SEC record shows how it was caught.

### Closing
That is how the record shows it.

## Sources
- SEC - https://www.sec.gov/
"""
t = MA.finish(GOOD, {"title": "How was Bernie Madoff actually caught?"})
check("3a the finished script says the disclaimer in its closing and carries the topic's plain question",
      MA.DISCLAIMER in t.split("### Closing", 1)[1].split("## Sources")[0]
      and t.startswith("# How was Bernie Madoff actually caught?") and not MA.money_problems(t),
      MA.money_problems(t))
check("3b a draft with no disclaimer is refused", any("not financial advice" in p for p in MA.money_problems(GOOD)),
      MA.money_problems(GOOD))
bad = t.replace("That is how the record shows it.", "You should buy index funds and get rich.")
probs = MA.money_problems(bad)
check("3c a tip or a get-rich promise in the narration is refused",
      sum("R-ADV-04" in p and "promise" in p for p in probs) >= 2, probs)
check("3d a script that is not declared Money is refused",
      any("Domain" in p for p in MA.money_problems(t.replace(M, DEEP))), "accepted")

# ------------------------------------------------------------ 4. footage
import footage as F  # noqa: E402

assets = ([{"local_file": f"m{i}", "post_id": f"pixabay:{i}", "source": "pixabay", "money_set": "hwk-money",
            "domain": M, "subject": ["coins", "a courthouse and the law"][i % 2], "title": "coins"}
           for i in range(4)]
          + [{"local_file": "noaa", "source": "noaa-ncei-oer", "title": "anglerfish deep sea"},
             {"local_file": "ds", "post_id": "pixabay:99", "source": "pixabay", "subject": "coins",
              "title": "coins", "domain": DEEP},
             {"local_file": "calm", "post_id": "pixabay:98", "source": "pixabay", "calm_set": "money-luxury",
              "subject": "a yacht at sunset", "title": "yacht"}])
real_dom = F.episode_domain
F.episode_domain = lambda slug: M if slug == "money-ep" else DEEP
try:
    pool = F.episode_pool("money-ep", assets, needed=10)
    check("4a a Money episode takes only the Money set (no NOAA, no deep-sea stock, no Almanac set)",
          {a["local_file"] for a in pool} == {"m0", "m1", "m2", "m3"}, [a["local_file"] for a in pool])
    check("4b the Money set is interleaved subject by subject",
          [a["subject"] for a in pool[:2]] == ["coins", "a courthouse and the law"], [a["subject"] for a in pool])
    check("4c a deep-sea episode never takes a Money clip",
          not any(a.get("money_set") for a in F.episode_pool("deep-ep", assets, needed=10)), "it did")
finally:
    F.episode_domain = real_dom

# ------------------------------------------------------------ 5. the 30-day check
cfg5 = json.loads(json.dumps(CFG))
cfg5["domains"]["money_test"]["started"] = "2026-11-10"
pub = [{"slug": "m1", "video_id": "v1", "scheduled_publish_at": "2026-11-13T16:00:00Z"},
       {"slug": "m2", "video_id": "v2", "scheduled_publish_at": "2026-11-17T16:00:00Z"},
       {"slug": "d1", "video_id": "v3", "scheduled_publish_at": "2026-11-16T16:00:00Z"},
       {"slug": "old", "video_id": "v4", "scheduled_publish_at": "2026-10-01T16:00:00Z"}]
dom5 = {"m1": M, "m2": M, "d1": DEEP, "old": DEEP}.get
rows5 = [{"video_id": "v1", "at": "2026-11-20", "views": 100, "estimated_minutes_watched": 120, "subscribers_gained": 3},
         {"video_id": "v1", "at": "2026-11-27", "views": 200, "estimated_minutes_watched": 300, "subscribers_gained": 5},
         {"video_id": "v2", "at": "2026-11-27", "views": 50, "estimated_minutes_watched": 60, "subscribers_gained": 1},
         {"video_id": "v4", "at": "2026-11-27", "views": 999, "estimated_minutes_watched": 9999, "subscribers_gained": 99}]
res = {r["lane"]: r for r in LC.check(cfg5, pub, rows5, dt.date(2026, 11, 28), dom5)}
mo = res.get(M) or {}
check("5a the Money lane sums its window's videos from the latest row each",
      (mo.get("videos"), mo.get("views"), mo.get("watch_hours"), mo.get("subscribers")) == (2, 250, 6.0, 6),
      mo)
ds = res.get(DEEP) or {}
check("5b a lane video with no measured row is 'not read' (None), never 0; older videos are outside the window",
      ds.get("videos") == 1 and ds.get("watch_hours") is None and ds.get("subscribers") is None
      and ds.get("unread") == ["v3"] and "not read" in LC.line(ds), ds)
check("5c before day 30 the check is due; on day 30 it is read",
      mo.get("state") == "30-day check due 2026-12-10"
      and LC.check(cfg5, pub, rows5, dt.date(2026, 12, 10), dom5)[0]["state"] == "30-day check: read",
      mo.get("state"))
bad_file = Path(tempfile.mkdtemp()) / "m.json"
bad_file.write_text("{not json")
none = LC.check(cfg5, pub, LC.read_rows(bad_file), dt.date(2026, 11, 28), dom5)
check("5d an unreadable measurement file reads every lane 'not read', never 0",
      all(r["watch_hours"] is None and r["subscribers"] is None and r["unread"] for r in none), none)
import digest  # noqa: E402
import ledger  # noqa: E402

real_rows = LC.read_rows
LC.read_rows = lambda path=None: None
try:
    blk = "\n".join(digest.lanes_block(cfg5, {"published": pub}, dt.datetime(2026, 11, 28)))
finally:
    LC.read_rows = real_rows
check("5e the digest's lane table shows 'not read' and the named stop when the numbers cannot be read",
      "LANE_CHECK_NOT_READ" in blk
      and all([c.strip() for c in ln.split("|")[3:6]] == ["not read"] * 3
              for ln in blk.splitlines() if ln.startswith(f"| {DEEP}") or ln.startswith(f"| {M}")),
      blk[-400:])
check("5f the digest no longer carries the 30-long-videos table",
      "Long videos measured" not in blk and not hasattr(digest, "topics_block"), "topics_block still there")

# ------------------------------------------------------------ 6. the real config
t6 = D.money_test(CFG)
rot = CFG["cadence"]["rotation"]["weekdays"]
alloc = D.allocation(CFG)
check("6a the Money test: started, 30 days, deep sea as the fallback, food and materials paused",
      t6.get("started") and int(t6.get("check_days", 0)) == 30 and t6.get("fallback") == DEEP
      and set(t6.get("longform_paused") or {}) == {FOOD, MAT}, t6)
# Money takes food's Wed/Sat (food long-forms paused); materials keeps Tue/Fri
# only for the episodes already dated there - no new materials long-form is
# drafted, because the generic draft lane's gate refuses it.
_, refused6 = D.longform_gate([{"slug": "x-mat", "domain": MAT}, {"slug": "x-food", "domain": FOOD}], CFG)
check("6b Money holds two upload days, food none, and no new materials long-form is drafted",
      sorted(k for k, v in rot.items() if v == M) == ["sat", "wed"] and alloc.get(M) == 2
      and alloc.get(FOOD) == 0 and FOOD not in rot.values()
      and set(refused6) == {"x-mat", "x-food"}, (rot, alloc, refused6))
q = json.loads(MA.ORDER.read_text())["queue"]
check("6c the 12 Money topics are queued in rank order, every row gated passed",
      [r["slug"] for r in q[:12]] == [x["slug"] for x in MA.topics()] and len(MA.topics()) == 12
      and all((r.get("gate") or {}).get("verdict") == "passed" for r in q), [r["slug"] for r in q])

# ------------------------------------------------------------ 7. food paused
import food_author as FA  # noqa: E402
import food_lane as FL  # noqa: E402

check("7a the food author is paused by the config", bool(FA.paused()), FA.paused())
said: list[str] = []
real_say = FL.say
FL.say = said.append
try:
    rc = FL.run(None, "07:00")
finally:
    FL.say = real_say
check("7b the Mac's food night renders nothing and says FOOD_LONGFORM_PAUSED",
      rc == 3 and any("FOOD_LONGFORM_PAUSED" in s for s in said), (rc, said))

# ------------------------------------------- 7c. one failed topic, not the run
# 13 Nov 2026: the run ended on FTX's fourth failed draft (DRAFT_FAILED_
# VALIDATION, an issue) with ten more topics unwritten and no Money script for
# the night. A topic that is not written is a note; the next one is tried.
import os  # noqa: E402
import common  # noqa: E402

stops = Path(tempfile.mkdtemp(prefix="money-stops-"))
os.environ["LOOP_STOPS_DIR"] = str(stops)
real7 = MA.write_queue, MA.published_slugs, MA.in_flight, MA.next_topics, MA.write_topic
tried: list[str] = []


def fake_write(fail: set[str]):
    def w(t, used, deadline, author, pov_match, validate):
        tried.append(t["slug"])
        if t["slug"] in fail:
            raise MA.TopicStop("DRAFT_FAILED_VALIDATION", f"{t['slug']}: 4 drafts failed", "retry")
        return f"wrote scripts/{t['slug']}.md"
    return w


def run7():
    try:
        rc = MA.run()
    except SystemExit as e:
        rc = e.code
    f = stops / f"{common.week_id()}-money-author.json"
    rec = json.loads(f.read_text()) if f.exists() else {}
    f.unlink(missing_ok=True)
    return rc, rec


try:
    MA.write_queue, MA.published_slugs, MA.in_flight = (lambda: {}), (lambda: set()), (lambda pub=None: [])
    MA.next_topics = lambda pub=None: [{"slug": f"t{k}", "title": f"T{k}?"} for k in range(1, 6)]
    MA.write_topic = fake_write({"t1"})
    rc, rec = run7()
    check("7c a topic the models cannot write today is skipped and the next one is written",
          tried == ["t1", "t2"] and rc == 0 and rec.get("code") != "DRAFT_FAILED_VALIDATION", (tried, rc, rec))
    tried.clear()
    MA.write_topic = fake_write({"t1", "t2", "t3", "t4", "t5"})
    rc, rec = run7()
    check("7d a run that writes nothing is the named stop, after TOPICS_A_RUN topics and no more",
          tried == ["t1", "t2", "t3"] and MA.TOPICS_A_RUN == 3 and rec.get("code") == "DRAFT_FAILED_VALIDATION"
          and rc not in (0, None), (tried, rc, rec))
finally:
    MA.write_queue, MA.published_slugs, MA.in_flight, MA.next_topics, MA.write_topic = real7
    shutil.rmtree(stops, ignore_errors=True)

# ------------------------------------------------------------ 8. graphics
import plan_domain as PD  # noqa: E402
import planner as P  # noqa: E402

sig, cold = P.signals_for(M)
names = {n for n, _ in sig} | {cold}
check("8a the Money planner uses no ocean, heat or kitchen device",
      not names & {"depth_descent", "pressure_gauge", "zone_column", "light_attenuation", "world_map",
                   "anatomy_callout", "thermal_ascent", "process_column"}, names)
check("8b a depth gauge in a Money plan is caught as another domain's graphic",
      PD.foreign([{"segment": "depth_descent", "args": {}}], M), "not caught")

print(f"examined {examined} case(s), {len(fails)} failed")
if examined == 0:
    sys.exit("examined zero cases")
if fails:
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print("all green - the Money lane takes both nights, holds R-ADV-04, shows money footage, "
      "and is judged per lane at 30 days")
