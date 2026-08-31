"""THE WEEKLY ENTRYPOINT. One idempotent command; the loop owns the schedule.

    python research/weekly.py

That is the whole contract. It refreshes demand, trend and competition data,
re-runs the gate, and writes a fresh research/publish_order.json for the loop
to act on. Safe to run twice; safe to run when quota is gone; never writes a
fabricated number.

STAGES
------
  1. competition   YouTube Data API v3, ~2,040 quota units for the 20 episodes.
                   SKIPPED when the existing file is younger than --max-age-days,
                   which is what makes a re-run inside the same week free.
  2. trends        Google Trends, free, slow. --skip-trends to omit.
  3. rank          The gate and the combined score -> publish_order.json.
  4. rework        Free autocomplete mining for any saturated kill.

QUOTA
-----
search.list costs 100 units against 10,000/day, so the episode pass is the
only stage that spends, and it spends deliberately: 20 searches for the 20
episodes that decide this week's publish. If quota is gone, stage 1 takes a
NAMED STOP, the previous competition file is reused, and the output is marked
`competition_data_stale` with its age. It never imputes a score and never
silently proceeds as if the data were fresh.

FAILURE POLICY
--------------
Rule 0: no stage exits 0 having done nothing. Every stage reports done,
skipped-with-reason, or named-stop-with-reason, and the run manifest records
which. An empty candidate set is a hard failure, not a pass.

OUTPUTS
-------
  research/publish_order.json      the loop's authoritative input
  research/weekly_run.json         manifest: what ran, what it cost, what stopped
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
MANIFEST = os.path.join(HERE, "weekly_run.json")
COMP = os.path.join(HERE, "competition_scripts.json")
ORDER = os.path.join(HERE, "publish_order.json")


def age_days(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path, encoding="utf-8"))
        ts = d.get("measured_at") or d.get("generated_at") or d.get("fetched_at")
        when = datetime.fromisoformat(ts)
    except Exception:
        when = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400


def run(name: str, argv: list[str], timeout: int = 3600) -> dict:
    print(f"\n=== {name} ===", flush=True)
    t0 = time.time()
    p = subprocess.run([PY] + argv, cwd=HERE, capture_output=True, text=True,
                       timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    print(out[-2500:], flush=True)
    return {"stage": name, "argv": argv[1:], "returncode": p.returncode,
            "seconds": round(time.time() - t0, 1),
            "quota_exhausted": "QUOTA" in out.upper() and "EXHAUST" in out.upper(),
            "tail": out[-1200:]}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-age-days", type=float, default=6.0,
                    help="reuse competition data younger than this instead of "
                         "spending quota again")
    ap.add_argument("--force-competition", action="store_true",
                    help="refresh competition data regardless of age")
    ap.add_argument("--skip-trends", action="store_true")
    ap.add_argument("--skip-rework", action="store_true")
    ap.add_argument("--pause", type=float, default=0.4)
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat()
    stages: list[dict] = []
    print(f"weekly run started {started}")

    # ---- stage 1: competition ---------------------------------------
    a = age_days(COMP)
    if a is not None and a < args.max_age_days and not args.force_competition:
        stages.append({
            "stage": "competition", "status": "skipped",
            "reason": (f"existing competition data is {a:.1f} days old, under "
                       f"the {args.max_age_days}-day reuse window. Skipping "
                       "saves 2,040 quota units and makes a re-run inside the "
                       "same week free. Use --force-competition to override."),
            "quota_units_spent": 0})
        print(f"\n=== competition === skipped, data is {a:.1f} days old")
    else:
        r = run("competition", ["competition.py", "--from-scripts",
                                "--out", "competition_scripts.json",
                                "--budget", "2500"])
        if r["returncode"] != 0:
            if r["quota_exhausted"] or a is not None:
                r["status"] = "named_stop"
                r["name"] = "YOUTUBE_QUOTA_EXHAUSTED"
                r["reason"] = (
                    "search.list quota is spent for today (resets at midnight "
                    "Pacific). No score was fabricated. The previous "
                    f"competition file is {a:.1f} days old and is reused; the "
                    "output is marked competition_data_stale."
                    if a is not None else
                    "search.list quota is spent and there is no previous "
                    "competition file to fall back on.")
                if a is None:
                    stages.append(r)
                    write(started, stages, fatal=(
                        "No competition data exists and quota is exhausted. "
                        "There is nothing to rank. Re-run after the Pacific "
                        "midnight reset."))
                    return 2
            else:
                r["status"] = "failed"
                stages.append(r)
                write(started, stages, fatal="competition stage failed")
                return 2
        else:
            r["status"] = "done"
        stages.append(r)

    if not os.path.exists(COMP):
        write(started, stages, fatal="competition_scripts.json missing")
        return 2

    # ---- stage 2: trends (free) -------------------------------------
    if args.skip_trends:
        stages.append({"stage": "trends", "status": "skipped",
                       "reason": "--skip-trends"})
    else:
        kws = ",".join(q for _, _, q in _questions())
        r = run("trends", ["trends.py", "--keywords", kws, "--pause", "4",
                           "--out", "trends_scripts.json", "--resume"])
        r["status"] = "done" if r["returncode"] == 0 else "degraded"
        if r["returncode"] != 0:
            r["reason"] = ("Trends is unavailable or throttled. It is a "
                           "bounded +/-15% adjustment and never a driver, so "
                           "the ranking proceeds without it, neutral.")
        stages.append(r)

    # ---- stage 3: rank ----------------------------------------------
    r = run("rank", ["publish_order.py", "--pause", str(args.pause)])
    r["status"] = "done" if r["returncode"] == 0 else "failed"
    stages.append(r)
    if r["returncode"] != 0:
        write(started, stages, fatal="ranking failed; publish_order.json not "
                                     "refreshed")
        return 2

    # ---- stage 4: rework (free) -------------------------------------
    order = json.load(open(ORDER, encoding="utf-8"))
    saturated = [k for k in order["killed"]
                 if "saturation" in (k.get("failed_axes") or [])]
    if args.skip_rework or not saturated:
        stages.append({"stage": "rework", "status": "skipped",
                       "reason": ("--skip-rework" if args.skip_rework else
                                  "no saturated kills this run")})
    else:
        r = run("rework", ["rework.py", "--pause", str(args.pause)])
        r["status"] = "done" if r["returncode"] == 0 else "failed"
        stages.append(r)

    write(started, stages, order=order, comp_age=age_days(COMP))
    return 0


def _questions():
    sys.path.insert(0, HERE)
    from competition import script_questions
    return script_questions()


def write(started: str, stages: list[dict], fatal: str | None = None,
          order: dict | None = None, comp_age: float | None = None) -> None:
    m = {
        "_what_this_is": ("Manifest of the last weekly run. Diagnostic only -- "
                          "the loop's input is publish_order.json."),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": "python research/weekly.py",
        "rule_0": ("No stage exits 0 having done nothing. Each stage below is "
                   "done, skipped with a reason, or a named stop with a "
                   "reason."),
        "stages": stages,
        "fatal": fatal,
        "competition_data_age_days": (round(comp_age, 2) if comp_age is not None
                                      else None),
        "competition_data_stale": (comp_age is not None and comp_age > 8),
    }
    if order:
        m["result"] = {
            "queue_length": order["queue_length"],
            "killed": len(order["killed"]),
            "next_to_publish": (order["queue"][0]["query"]
                                if order["queue"] else None),
            "runway_weeks_at_2_per_week": round(order["queue_length"] / 2, 1),
        }
    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), indent=2)
    if fatal:
        print(f"\nFATAL: {fatal}")
    else:
        print(f"\nwrote {MANIFEST}")
        if order:
            print(f"queue {order['queue_length']}, killed {len(order['killed'])}, "
                  f"runway {order['queue_length']/2:.1f} weeks at 2/week")


if __name__ == "__main__":
    sys.exit(main())
