"""Shorts: drain a backlog at 2/day, and an empty shelf in a short week is a stop.

Owner, 2026-10-12: "the backlog needs to be drained properly - possibly 2 short
posts per day until its drained". And from 22 Sep the cloud Shorts lane exited
0 every day while publishing 3, 3 and then 1 Short a week against
shorts_per_week = 9, because an empty shelf was a self-resolving no-op.

Proves, with fabricated ledgers and shelves (no network, no credential):

  1. drain_mode: 30 verified cuts on the shelf -> DRAIN, 2 per run; 8 -> normal;
     the line names the mode and the depth in weeks;
  2. plan() in drain mode puts two Shorts from DIFFERENT episodes on one local
     day at 19:00 and 21:00; the normal ladder never exceeds its 9 rungs a
     week; the "never two from one episode a day" rule holds in drain mode;
  3. shelf_dry: 9+ published in the trailing 7 days -> no stop; 1 -> a stop
     whose first line names the count, the target and the last shelf date;
  4. SHORTS_SHELF_DRY is self-resolving for 2 consecutive days and needs a
     human on the 3rd; NO_SHORTS_SHELVED escalates on the 3rd too and names
     the Mac batch stop file.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP))
tmp = Path(tempfile.mkdtemp(prefix="shorts-drain-"))
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")
os.environ.setdefault("LOOP_DRY_RUN", "1")

import common as C  # noqa: E402
import domains  # noqa: E402
import shorts_cloud as SC  # noqa: E402
import shorts_lane as SL  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")


cfg = C.config()
per_week = int(cfg["cadence"]["shorts_per_week"])
drain_cfg = cfg["cadence"].get("shorts_drain") or {}
check("0 config shorts_drain per_day 2, at >= 2 weeks",
      drain_cfg.get("per_day") == 2
      and drain_cfg.get("while_backlog_weeks_at_least") == 2, str(drain_cfg))

# ---- 1: the mode --------------------------------------------------------
d30, d8 = SL.drain_mode(30, cfg), SL.drain_mode(8, cfg)
check("1 30 cuts -> drain, 2 per run", d30["on"] and d30["per_run"] == 2, str(d30))
check("1 8 cuts -> normal", not d8["on"] and d8["per_run"] is None, str(d8))
check("1 the line names mode and depth in weeks",
      "DRAIN 2/day" in d30["line"] and f"{30 / per_week:.1f} week" in d30["line"]
      and "normal" in d8["line"], d30["line"] + " | " + d8["line"])
edge = SL.drain_mode(2 * per_week, cfg)
check("1 exactly two weeks of supply drains", edge["on"], str(edge))
check("1 one cut short of two weeks does not",
      not SL.drain_mode(2 * per_week - 1, cfg)["on"])

# ---- 2: the plan --------------------------------------------------------
by = domains.by_slug()
slugs = sorted(by)[:30]
assert len(slugs) >= 10, "need real slugs"
picks = [SL.Pick(s, 1) for s in slugs]
empty = {"published": []}
p_drain = SL.plan(empty, picks, 14, drain=True)
days: dict = {}
for p, t in p_drain:
    days.setdefault(SL._local_day(t), []).append((p, t))
two_a_day = [v for v in days.values() if len(v) == 2]
# The plan starts at the next free evening slot, so the run's own clock decides
# whether today still has both (before 19:00: 7 days of two) or only the 21:00
# (8 days: one, six of two, one). Pinned exactly either way - it went red at
# 20:00 local on 13 Oct 2026 with no commit behind it.
order = [days[k] for k in sorted(days)]
first_hour = min(t for _, t in p_drain).astimezone(SL.SHORTS_TZ).hour
if first_hour == 19:
    want_ok = len(days) == 7 and len(two_a_day) == 7
else:
    want_ok = (first_hour == 21 and len(days) == 8 and len(order[0]) == 1
               and len(order[-1]) == 1 and all(len(v) == 2 for v in order[1:-1]))
check("2 drain: 14 Shorts planned two a day (7 days, or 8 when today has only 21:00 left)",
      len(p_drain) == 14 and want_ok, f"{len(p_drain)} on {len(days)} days, first slot {first_hour}:00")
hours = sorted({t.astimezone(SL.SHORTS_TZ).hour for _, t in p_drain})
check("2 drain slots are 19:00 and 21:00 local", hours == [19, 21], str(hours))
check("2 drain never puts one episode twice on a day",
      all(len({p.slug for p, _ in v}) == len(v) for v in days.values()))
# a lone episode's ranks are kept fourteen days apart in drain mode too
lone = SL.plan(empty, [SL.Pick(slugs[0], 1), SL.Pick(slugs[0], 2)], 2, drain=True)
# 2026-10-14: fourteen days apart, not merely two days - so in one run only
# the first is planned; the second never lands inside the gap.
check("2 drain: a lone episode's second cut never lands inside fourteen days",
      [p for p, _ in lone] == [SL.Pick(slugs[0], 1)], str(lone))
two = SL.plan(empty, [SL.Pick(slugs[0], 1), SL.Pick(slugs[0], 2),
                      SL.Pick(slugs[1], 1)], 3, drain=True)
check("2 drain: the other episode takes the next slot, the repeat waits",
      [p for p, _ in two] == [SL.Pick(slugs[0], 1), SL.Pick(slugs[1], 1)],
      str(two))
p_norm = SL.plan(empty, picks, 18)
first = min(t for _, t in p_norm)
in_week = [t for _, t in p_norm if t < first + timedelta(days=7)]
check("2 normal ladder: at most shorts_per_week in any 7 days",
      len(in_week) <= per_week, f"{len(in_week)} in the first 7 days")

# ---- 3: shelf_dry -------------------------------------------------------
now = datetime(2026, 10, 12, 23, 0, tzinfo=timezone.utc)


def ledger(n: int) -> dict:
    return {"published": [{
        "slug": f"s{i}", "rank": 1,
        "uploaded_at": (now - timedelta(days=2, hours=i)).isoformat(),
        "scheduled_publish_at": (now - timedelta(hours=6 + 12 * i))
        .strftime("%Y-%m-%dT%H:%M:%SZ")} for i in range(n)]}


check("3 9 in 7 days -> no stop", SC.shelf_dry(ledger(per_week), cfg, at=now) is None)
dry = SC.shelf_dry(ledger(1), cfg, at=now)
check("3 1 in 7 days + empty shelf -> stop", dry is not None)
if dry:
    first_line = dry["message"].splitlines()[0]
    check("3 first line names count vs target and the last shelf date",
          first_line.startswith(f"1 Short(s) published in the trailing 7 days "
                                f"vs a target of {per_week}/week")
          and (now - timedelta(days=2)).strftime("%Y-%m-%d") in first_line,
          first_line)
old = {"published": [{"slug": "x", "scheduled_publish_at": "2026-09-01T00:00:00Z",
                      "uploaded_at": "2026-08-30T00:00:00Z"}]}
check("3 a ledger whose Shorts are all older than 7 days counts 0",
      SL.published_trailing(old, 7, now) == 0)

# ---- 4: escalation ------------------------------------------------------
pol = C.stop_policy()
for code in ("SHORTS_SHELF_DRY", "NO_SHORTS_SHELVED"):
    rule = (pol.get("self_resolving") or {}).get(code) or {}
    check(f"4 {code} is self_resolving with max_consecutive 2",
          rule.get("max_consecutive") == 2, str(rule)[:200])
    got = [C.disposition("shorts-cloud", code, {}, k)[0] for k in (1, 2, 3)]
    check(f"4 {code}: green on days 1-2, a human on day 3",
          got[:2] == ["self_resolving", "self_resolving"]
          and got[2] not in ("self_resolving", "held", "owner_action"), str(got))
    check(f"4 {code} escalation names the Mac batch stop file",
          "mac-batch.json" in rule.get("escalation", ""), rule.get("escalation", ""))

if examined == 0:
    print("FAIL test_shorts_drain_and_dry_shelf: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_shorts_drain_and_dry_shelf:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_shorts_drain_and_dry_shelf: {examined} checks - drain 2/day "
      f"from two weeks of backlog, a dry shelf in a short week stops and "
      f"escalates on day 3")
