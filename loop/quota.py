"""One shared account of the YouTube daily quota.

Four scheduled jobs now spend from the same 10,000-unit daily allowance, and
none of them could see the others. On 2026-09-01 the worst case - a Thursday
where the shorts lane, the backfill and the weekly upload all fire - came to
10,200 units. Nothing would have warned anyone; the last upload would simply
have failed with `quotaExceeded` partway through, leaving a half-uploaded video,
which is worse than an unstarted one.

Every lane that spends now RESERVES first. The reservation is per calendar day in
Pacific time, because that is when YouTube resets, not local midnight and not
UTC. A lane that cannot get its reservation takes fewer videos or a named stop -
it never starts work it cannot finish.

This file is the only place the costs are written down:

    videos.insert   1600      thumbnails.set    50
    videos.update     50      daily allowance 10000
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path(__file__).resolve().parent / "state" / "quota.json"
RESET_TZ = ZoneInfo("America/Los_Angeles")   # YouTube resets at midnight PT

UPLOAD = 1600
THUMBNAIL = 50
PRIVACY_FLIP = 50
DAILY = 10000
PER_VIDEO = UPLOAD + THUMBNAIL + PRIVACY_FLIP     # 1700

# Never plan to the very edge: a retry, an extra status read, or a flip the
# publish lane makes must not be the thing that tips the day over.
HEADROOM = 400


def _today() -> str:
    return datetime.now(RESET_TZ).strftime("%Y-%m-%d")


def _load() -> dict:
    if not STATE.exists():
        return {"day": _today(), "spent": 0, "by_lane": {}}
    d = json.loads(STATE.read_text())
    if d.get("day") != _today():                  # a new quota day
        return {"day": _today(), "spent": 0, "by_lane": {}}
    return d


def remaining() -> int:
    return max(0, DAILY - HEADROOM - _load()["spent"])


def videos_affordable(want: int) -> int:
    """How many whole videos can still be uploaded today, at most `want`."""
    return max(0, min(want, remaining() // PER_VIDEO))


def spend(units: int, lane: str) -> None:
    """Record units actually spent. Called AFTER the work, never before."""
    d = _load()
    d["spent"] += units
    d["by_lane"][lane] = d["by_lane"].get(lane, 0) + units
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2) + "\n")


def report() -> str:
    d = _load()
    lanes = ", ".join(f"{k} {v}" for k, v in sorted(d["by_lane"].items())) or "none"
    return (f"quota day {d['day']} (PT): spent {d['spent']} of {DAILY}, "
            f"{remaining()} usable after {HEADROOM} headroom; lanes: {lanes}")
