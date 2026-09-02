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
    videos.list        1      captions.list     50
    captions.insert  400      captions.update  450

The two REACH lanes (captions, localizations) added 2026-09-02 spend from the
same account. They are cheap per video but the caption backfill is not: 15 live
videos x (captions.list 50 + captions.insert 400) = 6,750 units, which alone is
most of a day. So neither reach lane may take the last of the allowance — the
publish lane's flip and the daily upload come first. `units_affordable()`
enforces that with an explicit reserve; the reach lanes pass
`reserve=PER_VIDEO`, so at least one whole video upload always survives them,
and the backfill simply spreads over several daily runs.
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

# Verified against developers.google.com/youtube/v3/determine_quota_cost and
# the captions.insert reference on 2026-09-02.
VIDEO_READ = 1            # videos.list
CAPTION_LIST = 50         # captions.list  — how we tell "already has a track"
CAPTION_INSERT = 400      # captions.insert — the expensive one
VIDEO_UPDATE = 50         # videos.update  — the localizations write

# What one video costs each reach lane, end to end.
PER_CAPTION = CAPTION_LIST + CAPTION_INSERT       # 450
PER_LOCALIZE = VIDEO_READ + VIDEO_UPDATE          # 51

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


# Every lane that spends the 1,600-unit videos.insert. If one of these has
# already booked units today, its upload has HAPPENED and there is nothing left
# to hold quota back for.
UPLOADING_LANES = ("backfill", "cloud-upload", "thu-upload", "shorts",
                   "shorts-cloud")


def upload_reserve() -> int:
    """How much to keep back for an upload that has not happened yet today.

    A flat reserve is the safe default and the wrong answer late in the day: it
    tells the caption backfill to protect an allowance the 09:00 upload already
    spent, so the reach lanes sit idle guarding nothing. The reserve exists to
    stop a cheap deferrable lane from being the reason a publish slot fails —
    once the day's upload is in the ledger, that risk is over.

    Returns PER_VIDEO while no uploading lane has spent today, 0 after one has.
    """
    spent_by = _load().get("by_lane") or {}
    if any(spent_by.get(lane) for lane in UPLOADING_LANES):
        return 0
    return PER_VIDEO


def units_affordable(unit_cost: int, want: int, reserve: int = 0) -> int:
    """How many `unit_cost` items fit today, keeping `reserve` units untouched.

    The reserve is the whole point. A caption backfill that spends the day's
    last 6,750 units is not a success — it is the reason that night's upload
    fails halfway through with `quotaExceeded`, and the upload lane is the one
    that cannot be deferred. Reach can always wait a day; a publish slot cannot.
    """
    if unit_cost <= 0:
        raise ValueError("unit_cost must be positive")
    return max(0, min(want, (remaining() - max(0, reserve)) // unit_cost))


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
