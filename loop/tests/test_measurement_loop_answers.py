"""The measurement loop can answer "is this working" - audit of 2026-10-12.

Five defects, each pinned here:

  1. loop/monthly.py collect() kept only rows stamped in the CURRENT month,
     but runs on the 1st while every Friday row is stamped the month before:
     October's review saw 0 measured videos. Rows across the boundary must
     be read.
  2. There was no history: measurement.json held one row per video and
     channel_stats.json one snapshot. Two measure runs on different dates
     must leave two dated rows per video in loop/state/measurement_history
     .jsonl, a re-run in the same week must not duplicate, and the latest
     view keeps one row per video.
  3. The opening experiment starved: only model drafts were stamped. Every
     script entering the queue through draft.py assembly carries the active
     rule when its opening passes the rule's check, and only then.
  4. The lane measured no Short, no per-video subscriber gain, no traffic
     source and no impressions. Pinned statically on the lane's source and
     on history_rows() with fabricated API rows.
  5. One channel verdict, with floors: computed from fabricated history,
     written to channel_verdict.json, printed as a six-line block in the
     digest.

Every fixture lives in a temp directory; the repo's loop/state is never
written (run_all.py checks).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import measure                                             # noqa: E402
import monthly                                             # noqa: E402
import opening as O                                        # noqa: E402
import verdict as V                                        # noqa: E402
from common import config                                  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    print(f"  {'ok' if ok else '✗'} {name}" + ("" if ok else f": {detail}"))
    if not ok:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="measure-loop-"))
cfg = config()

# ------------------------------------------------- 1. the month boundary
mfile = tmp / "measurement.json"
mfile.write_text(json.dumps({"videos": [
    {"video_id": "a", "at": "2026-09-25T21:15:00+00:00"},   # last Friday of Sep
    {"video_id": "b", "at": "2026-09-04T21:15:00+00:00"},
    {"video_id": "c", "at": "2026-10-01T09:00:00+00:00"},   # the 1st itself
    {"video_id": "d", "at": "2026-08-28T21:15:00+00:00"},   # two months back
]}))
saved = monthly.MEASURE
monthly.MEASURE = mfile
try:
    got = sorted(r["video_id"] for r in monthly.collect("2026-10"))
    check("monthly review on the 1st reads the month just ended",
          got == ["a", "b", "c"], f"collected {got}")
    got = sorted(r["video_id"] for r in monthly.collect("2026-01"))
    check("rows two months back are not read",
          got == [], f"collected {got}")
    mfile.write_text(json.dumps({"videos": [
        {"video_id": "x", "at": "2025-12-26T21:15:00+00:00"}]}))
    got = [r["video_id"] for r in monthly.collect("2026-01")]
    check("December rows are read by the January review", got == ["x"],
          f"collected {got}")
finally:
    monthly.MEASURE = saved

# ------------------------------------------------- 2. the history
hist = tmp / "history.jsonl"


def long_rec(vid: str, views: int, mins: int, avd: int) -> dict:
    return {"video_id": vid, "views": views, "estimated_minutes_watched": mins,
            "average_view_duration_s": avd, "average_view_percentage": 20.0,
            "subscribers_gained": 1, "runtime_s": 600.0,
            "opening": O.PRE_RULE, "aired_at": "2026-09-01"}


def short_rec(vid: str, views: int) -> dict:
    return {"video_id": vid, "views": views, "estimated_minutes_watched": views // 4,
            "average_view_duration_s": 15, "average_view_percentage": 60.0,
            "subscribers_gained": 0}


chan = {"window_days": 28, "start": "x",
        "by_type": {"videoOnDemand": {"views": 400, "minutes": 1200,
                                      "subscribers_gained": 6,
                                      "subscribers_lost": 1},
                    "shorts": {"views": 3600, "minutes": 900,
                               "subscribers_gained": 4,
                               "subscribers_lost": 0},
                    V.UNSPECIFIED: {"views": 50, "minutes": 500,
                                    "subscribers_gained": 0,
                                    "subscribers_lost": 0}},
        "traffic": {"SHORTS": {"views": 3500, "minutes": 800}},
        "subscribers_total": 25}
w1 = measure.history_rows([long_rec("L1", 100, 300, 150), long_rec("L2", 50, 100, 120)],
                          [short_rec("S1", 1000)], chan, {}, "HTTP 400: The query "
                          "is not supported.", "2026-W41", "2026-10-09")
w2 = measure.history_rows([long_rec("L1", 180, 520, 160), long_rec("L2", 70, 140, 118)],
                          [short_rec("S1", 2600)], chan, {}, "HTTP 400: The query "
                          "is not supported.", "2026-W42", "2026-10-16")
V.append_history(w1, hist, today=dt.date(2026, 10, 9))
V.append_history(w2, hist, today=dt.date(2026, 10, 16))
rows = V.load_history(hist)
per = {}
for r in rows:
    if r.get("video_id"):
        per.setdefault(r["video_id"], []).append(r["date"])
check("two measure runs leave two dated rows per video (long-form and Shorts)",
      all(sorted(d) == ["2026-10-09", "2026-10-16"] for d in per.values())
      and set(per) == {"L1", "L2", "S1"}, f"{per}")
check("one channel row per week", sum(r["kind"] == "channel" for r in rows) == 2,
      f"{[r['kind'] for r in rows]}")
V.append_history(w2, hist, today=dt.date(2026, 10, 16))
check("a re-run in the same week replaces, never duplicates",
      len(V.load_history(hist)) == len(rows),
      f"{len(V.load_history(hist))} != {len(rows)}")
old = [{**r, "date": "2023-01-06", "week": "2023-W01"} for r in w1]
V.append_history(old, hist, today=dt.date(2023, 1, 6))
V.append_history(w2, hist, today=dt.date(2026, 10, 16))
check("rows older than HISTORY_DAYS are dropped (bounded file)",
      not any(r["date"] < "2024" for r in V.load_history(hist)),
      "a 2023 row survived")
latest = V._latest_per_video(V.load_history(hist), "long")
check("the latest view keeps exactly one row per video",
      sorted(latest) == ["L1", "L2"] and latest["L1"]["views"] == 180,
      f"{latest}")
src = (LOOP / "measure.py").read_text()
check("measure.py keeps measurement.json as the latest view AND appends history",
      "write_json(MEASURE, m)" in src and "verdict.append_history(hrows)" in src
      and "write_verdict(st, cfg)" in src, "a write is missing from the lane")
check("the history file is under loop/ (committed by bin/loop-stage.sh's "
      "`git add loop`)", str(V.HISTORY).startswith(str(LOOP / "state")),
      str(V.HISTORY))

# ------------------------------------------------- 3. the opening stamp
good = (ROOT / "scripts" / "why-is-steel-so-strong.md").read_text()
bad = (ROOT / "scripts" / "why-does-old-iron-not-rust.md").read_text()
sp = tmp / "good.md"
sp.write_text(good)
out, _ = O.stamp_on_assembly(sp, "cold-open-payoff")
check("an unmarked conforming script is stamped with the active rule on assembly",
      out == "stamped" and O.MARK_RE.search(sp.read_text()).group(1)
      == "cold-open-payoff", out)
out, _ = O.stamp_on_assembly(sp, "cold-open-payoff")
check("a stamped script is never stamped twice",
      out == "marked" and sp.read_text().count("**Opening:**") == 1, out)
bp = tmp / "bad.md"
bp.write_text(bad)
out, why = O.stamp_on_assembly(bp, "cold-open-payoff")
check("a script that buries its answer is NOT stamped (stays in the baseline)",
      out == "nonconforming" and why and "**Opening:**" not in bp.read_text(),
      out)
dsrc = (LOOP / "draft.py").read_text()
check("draft.py assembly stamps every script it queues",
      "opening.stamp_on_assembly(inv)" in dsrc
      and dsrc.index("opening.stamp_on_assembly(inv)")
      < dsrc.index('"work_copy": f"loop/work/'), "the call is missing or late")
check("model drafts are still stamped by author.draft()",
      "opening.mark(text, opening.active())" in (LOOP / "author.py").read_text())
check("the lane passes the ledger's airing dates to the experiment and names "
      "an undecidable week",
      "opening.evaluate(m[\"videos\"], aired=aired_by_variant(pub))" in src
      and "OPENING_NOT_YET_DECIDABLE" in src)

# ------------------------------------------------- 4. what is measured
check("per-video subscribersGained is in the core metrics",
      "subscribersGained" in measure.CORE_METRICS)
check("every Short in the shorts ledger is measured",
      "fetch_shorts(token, short_ids())" in src)
check("impressions/CTR are asked for, and a refusal is recorded verbatim",
      "fetch_impressions(token, video_ids)" in src and "IMPRESSIONS_UNAVAILABLE" in src)
check("the 28-day channel window carries content type AND traffic source",
      "creatorContentType" in src and "insightTrafficSourceType" in src)
srow = [r for r in w2 if r["kind"] == "short"]
crow = [r for r in w2 if r["kind"] == "channel"][0]
check("history rows carry Shorts, subscriber gain, traffic and the API refusal",
      srow and srow[0]["subscribers_gained"] == 0 and crow["traffic"]
      and crow["impressions"]["unavailable"].startswith("HTTP 400"), f"{crow}")

# ------------------------------------------------- 5. the verdict
v = V.compute(V.load_history(hist), cfg, dt.date(2026, 10, 16))
check("28-day views split long-form vs Shorts; unattributed kept out of long-form",
      v["views_28d"]["long_form"] == 400 and v["views_28d"]["shorts"] == 3600
      and v["views_28d"]["unattributed"] == 50 and v["views_28d"]["total"] == 4050
      and v["views_28d"]["shorts_share_pct"] == 88.9, f"{v['views_28d']}")
check("median views per long-form video",
      v["median_views_per_long_form_video"] == 125, f"{v}")
check("AVD against the 146 s floor (28-day long-form)",
      v["avd_s"] == 180.0 and v["avd_floor_s"] == 146.0
      and v["avd_vs_floor"] == "above", f"{v['avd_s']} {v['avd_vs_floor']}")
check("net subscribers in 28 days", v["subscribers_28d_net"] == 9, f"{v}")
check("watch hours against the 3,000-hour Expanded YPP bar",
      v["watch_hours_floor"] == 3000 and v["watch_hours_long_form"] == 11.0
      and v["watch_hours_28d"] == 20.0, f"{v}")
# Without a channel row, the 28-day figure comes from lifetime deltas.
nochan = [r for r in V.load_history(hist) if r["kind"] != "channel"]
nochan += [{**r, "date": "2026-09-11", "week": "2026-W37",
            "views": (r["views"] or 0) // 2,
            "estimated_minutes_watched": (r["estimated_minutes_watched"] or 0) // 2}
           for r in w1 if r["kind"] != "channel"]
v2 = V.compute(nochan, cfg, dt.date(2026, 10, 16))
check("with no channel row, 28-day views come from dated snapshots",
      v2["views_28d"]["long_form"] == 250 - 75 and v2["views_28d"]["shorts"] == 2100,
      f"{v2['views_28d']}")
v3 = V.compute([r for r in nochan if r["date"] >= "2026-10"], cfg)
check("one week of history says 'not yet computable', never 0",
      v3["views_28d"]["total"] is None
      and "not yet computable" in v3["views_28d"]["basis"], f"{v3['views_28d']}")
block = V.digest_block(v)
bullets = [ln for ln in block if ln.startswith("- **")]
check("the digest block is a heading and seven lines, each number with its floor",
      len(bullets) == 7 and "146 s floor" in block[3] + block[4] + block[5]
      and "3,000" in "\n".join(block) and "500" in "\n".join(block)
      and "not exposed" in bullets[-1] and "cadence not measured" in bullets[-2],
      "\n".join(block))
v_sc = {**v, "shorts_cadence": V.shorts_cadence(
    [{"scheduled_publish_at": "2026-10-10T18:00:00Z"},
     {"scheduled_publish_at": "2026-10-20T18:00:00Z"}], 9,
    dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc), 8, "fixture")}
line = [ln for ln in V.digest_block(v_sc) if ln.startswith("- **Shorts:**")]
check("the Shorts line gives 7-day count vs target and shelf depth in weeks",
      line and "1 published in 7 days vs 9/week" in line[0] and "UNDER" in line[0]
      and "shelf 9 verified unpublished = 1.0 week(s)" in line[0], f"{line}")
msrc = (LOOP / "measure.py").read_text()
check("the measure lane records the Shorts cadence with the R2 shelf, and "
      "names an unread shelf",
      "write_verdict(st, cfg, shorts=sc)" in msrc and "SHORTS_SHELF_UNREAD" in msrc
      and "shorts_lane.pending(have)" in msrc)
check("the Sunday digest prints the block",
      "L += channel_verdict.digest_block(cv)"
      in (LOOP / "digest.py").read_text())
saved_v = V.VERDICT
V.VERDICT = tmp / "channel_verdict.json"
try:
    V.write(V.load_history(hist), cfg)
    check("channel_verdict.json is written", V.read()["as_of"] == "2026-10-16")
finally:
    V.VERDICT = saved_v

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
