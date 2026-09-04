"""Today's research stands until invalidated. Do not re-pay for it every run.

Item 13b, 2026-09-03. `research/publish_order.staleness_days: 10` already
proves the shape: an artifact carries the date and method that produced it,
and a reader compares age against a NAMED window rather than re-deriving on
every run. This module is the same idea applied to the PAID measurement
scripts in this directory — the ones that spend a real network call or a real
model call per run, not the ones that only re-derive from files already on
disk (research/propose.py, research/commercial.py: both say so in their own
`derived_from` field, and neither needs a window here because neither costs
anything to re-run).

WINDOWS, AND WHY EACH ONE IS WHAT IT IS. Shelf life differs by what decays:

    mine.py / mine_broad.py   30 days   Autocomplete demand signal. Search
                                         interest drifts over a month but not
                                         a week; 30 days is inside
                                         `publish_order.staleness_days`'s own
                                         order of magnitude for "still
                                         representative of current demand."
    trends.py                 30 days   Same signal, same window - it is
                                         sampled alongside mine_broad.py and
                                         a mismatched pair of windows would
                                         let one drift ahead of the other.
    competition.py             14 days   COMPETITION SCORING DECAYS IN WEEKS,
                                         explicitly named as such in item 11 -
                                         the search results a query returns
                                         change faster than raw demand does,
                                         so this window is half the demand
                                         scripts' rather than the same.

NOT GIVEN A WINDOW HERE, DELIBERATELY:

    loop/durations.py's measured speaking rate (loop/state/runtime_model.json)
    is durable until the voice changes, not until a clock runs out - a
    time-based window would re-derive it for no reason on day 31, or trust a
    stale figure through day 29 if the voice actually changed on day 5. It
    already has the correct policy: `model(refresh=False)` reads the cached
    file forever, and only `--refresh` (a person deciding the voice changed,
    or new renders existing) re-derives it. See loop/durations.py's own
    docstring.

A script that wants this guard calls `guard(OUTPUT_PATH, WINDOW_DAYS, LABEL)`
at the very top of its CLI entrypoint. Within the window it prints why and
exits 0 - not a failure, a legitimate skip, exactly like a self-resolving
named stop reaching the log without paging anyone. `--force` on the CLI
(the caller's own argparse) is the only way past it, and it stays a
deliberate flag a human types, never a default.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

WINDOWS_DAYS = {
    "mine.py": 30,
    "mine_broad.py": 30,
    "trends.py": 30,
    "competition.py": 14,
}


# Every research/*.py script here names its own "when did I run" field
# differently (mined_at, fetched_at, measured_at, generated_at) - a real,
# already-existing inconsistency, not one this module invents. Checked
# against every field name actually in use rather than picking one and
# silently falling through to mtime for the other three.
TIMESTAMP_FIELDS = ("generated_at", "_generated_at", "mined_at", "fetched_at",
                    "measured_at")


def artifact_age_days(path: str) -> float | None:
    """Age in days, from whichever of TIMESTAMP_FIELDS the artifact carries,
    else the file's mtime. None if the file is absent."""
    if not os.path.exists(path):
        return None
    try:
        data = json.load(open(path, encoding="utf-8"))
        stamp = next((data.get(f) for f in TIMESTAMP_FIELDS if data.get(f)),
                    None) if isinstance(data, dict) else None
        if stamp:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - when).total_seconds() / 86400
    except (ValueError, json.JSONDecodeError, OSError):
        pass
    return (datetime.now(timezone.utc).timestamp()
           - os.path.getmtime(path)) / 86400


def guard(output_path: str, window_days: float, label: str,
         force: bool = False) -> None:
    """Exit 0 (a legitimate skip, not a failure) if `output_path` is younger
    than `window_days` and `force` was not passed. Otherwise return quietly
    and let the caller spend the network/model call it exists to make."""
    if force:
        print(f"[staleness] --force given; re-running {label} regardless of "
             f"age", flush=True)
        return
    age = artifact_age_days(output_path)
    if age is None:
        print(f"[staleness] {output_path} does not exist yet; {label} runs.",
             flush=True)
        return
    if age <= window_days:
        print(f"[staleness] {output_path} is {age:.1f} day(s) old, within "
             f"the {window_days}-day window for {label}. NOT re-running - "
             f"today's research stands until invalidated. Pass --force to "
             f"override.", flush=True)
        sys.exit(0)
    print(f"[staleness] {output_path} is {age:.1f} day(s) old, past the "
         f"{window_days}-day window for {label}; re-running.", flush=True)


OUTPUT_FOR = {
    "mine.py": "mined_queries.json",
    "mine_broad.py": "broad_mined.json",
    "trends.py": "trends.json",
    "competition.py": "competition.json",
}

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, window in WINDOWS_DAYS.items():
        out = os.path.join(here, OUTPUT_FOR[name])
        age = artifact_age_days(out)
        status = ("MISSING" if age is None else
                  "FRESH" if age <= window else "STALE")
        print(f"{name:<18} window {window:>3}d  "
             f"{'—' if age is None else f'{age:.1f}d old':>10}  {status}")
