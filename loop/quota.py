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

THE ARITHMETIC AT THE RAISED CADENCE (4 long-form + 9 Shorts a week, owner
decision 2026-09-02). One episode end to end is 2,201 units — upload 1,600,
thumbnail 50, the scheduling flip 50, its caption track 450 (list 50 + insert
400) and its localizations 51 (list 1 + update 50). One Short is 1,700: upload,
thumbnail, flip, and no reach lane. So a week is 4 x 2,201 + 9 x 1,700 = 24,104
units against 70,000 available — 34%, comfortably inside.

THE WEEK IS NOT WHAT BREAKS. The day is. On 2026-09-02 the day reached 9,600 of
10,000 and the Shorts lane deferred. Four reserves keep the peak day bounded
from either running order:

    episode lane   videos_affordable(limit, reserve=shorts_reserve())
    Shorts lane    videos_affordable(limit, reserve=upload_reserve())
    reach lanes    units_affordable(cost, want, reserve=deferrable_reserve())

Worst case either way round is 3 episodes + 2 Shorts + one video's reach =
5 x 1,700 + 501 = 9,001 of the 9,600 usable. The day's episode upload can no
longer be starved by Shorts or by a backfill, and the evening Shorts can no
longer be starved by a four-episode morning.

The two REACH lanes (captions, localizations) added 2026-09-02 spend from the
same account. They are cheap per video but the caption backfill is not: 15 live
videos x (captions.list 50 + captions.insert 400) = 6,750 units, which alone is
most of a day. So neither reach lane may take the last of the allowance — the
publish lane's flip and the daily upload come first. `units_affordable()`
enforces that with an explicit reserve; the reach lanes pass
`reserve=deferrable_reserve()`, so a whole episode upload AND the evening's
Shorts always survive them, and the backfill simply spreads over several daily
runs.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common import read_json                              # noqa: E402

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


def next_reset() -> str:
    """When today's allowance comes back, as an ISO timestamp in Pacific time.

    A quota stop is only allowed to be self-resolving if it can say WHEN it
    resolves — see loop/stop_policy.json. This is that answer, computed rather
    than asserted in prose, so a lane cannot claim to be self-healing on a
    schedule nobody checked.
    """
    n = datetime.now(RESET_TZ)
    tomorrow = (n + timedelta(days=1)).date()
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                        tzinfo=RESET_TZ)
    return midnight.isoformat(timespec="seconds")


def _load() -> dict:
    if not STATE.exists():
        return {"day": _today(), "spent": 0, "by_lane": {}}
    # Through common.read_json, NOT json.loads, so that an unreadable
    # quota.json raises CorruptState and Stage turns it into a named stop that
    # says WHICH FILE. This bare json.loads is the line that crashed the
    # localize lane on 2026-09-03 (run 33783829147) with a traceback naming
    # neither the file nor the git conflict that caused it.
    d = read_json(STATE, default={"day": _today(), "spent": 0, "by_lane": {}})
    if d.get("day") != _today():                  # a new quota day
        return {"day": _today(), "spent": 0, "by_lane": {}}
    return d


def remaining() -> int:
    return max(0, DAILY - HEADROOM - _load()["spent"])


def videos_affordable(want: int, reserve: int = 0) -> int:
    """How many whole videos can still be uploaded today, at most `want`.

    `reserve` is units this caller must NOT touch — the other irreversible
    lane's slot. The episode lane passes `shorts_reserve()`; the Shorts lane
    passes `upload_reserve()`. Both defaulted to 0 before the cadence rose,
    which was survivable at 2 episodes and 4 Shorts a week and is not at 4
    and 9: 4 x 1,700 + 2 x 1,700 is 10,200 units against a 9,600 usable day.
    """
    return max(0, min(want, (remaining() - max(0, reserve)) // PER_VIDEO))


# Every lane that spends the 1,600-unit videos.insert, split by WHAT it uploads.
#
# The split matters and used to be missing. One tuple held both, so a Shorts run
# cleared `upload_reserve()` to zero — and the reserve exists precisely to stop
# a Short from being the reason that day's episode upload fails. A Shorts spend
# is evidence a Short happened; it is no evidence at all that the episode did.
#
# The two reserves are symmetric and each stands down once its own lane has
# spent, so they bound the day from either running order without deadlocking:
# whichever lane runs first sees the other's reserve, and whichever runs second
# sees the first's actual spend.
LONGFORM_LANES = ("backfill", "cloud-upload", "thu-upload")
SHORTS_LANES = ("shorts", "shorts-cloud")
UPLOADING_LANES = LONGFORM_LANES + SHORTS_LANES

# How many Shorts an evening may cost the day. At 9 Shorts a week the lane takes
# one or two a night; two is the peak, and two whole video uploads (3,400 units)
# is what the episode lane must leave room for.
SHORTS_PER_DAY_PEAK = 2


def upload_reserve() -> int:
    """How much to keep back for the day's EPISODE upload, if it has not run.

    A flat reserve is the safe default and the wrong answer late in the day: it
    tells the caption backfill to protect an allowance the 09:00 upload already
    spent, so the reach lanes sit idle guarding nothing. The reserve exists to
    stop a cheap deferrable lane from being the reason a publish slot fails —
    once the day's upload is in the ledger, that risk is over.

    Returns PER_VIDEO while no LONG-FORM lane has spent today, 0 after one has.
    Shorts spending deliberately does not clear it: the long-form upload is the
    one lane that cannot be deferred, and at 4 episodes and 9 Shorts a week the
    Shorts lane runs more often than the episode lane does.
    """
    spent_by = _load().get("by_lane") or {}
    if any(spent_by.get(lane) for lane in LONGFORM_LANES):
        return 0
    return PER_VIDEO


def shorts_reserve() -> int:
    """How much to keep back for the evening's Shorts, if they have not run.

    The mirror of `upload_reserve()`, and the other half of what makes the
    higher cadence fit inside one day. Without it the episode lane's `--limit 4`
    could take 6,800 units at 09:00 and leave the 19:00 Shorts lane nothing —
    and Shorts are the only cheap lever on the subscriber half of the Partner
    Programme threshold, so starving them is not the harmless direction.

    Returns two whole video uploads while no Shorts lane has spent today, 0
    after one has.
    """
    spent_by = _load().get("by_lane") or {}
    if any(spent_by.get(lane) for lane in SHORTS_LANES):
        return 0
    return SHORTS_PER_DAY_PEAK * PER_VIDEO


def deferrable_reserve() -> int:
    """What a cheap, deferrable lane must leave alone: both irreversible lanes.

    Captions and localizations can always wait a day. An episode publish slot
    and an evening Shorts slot cannot, so a reach lane reserves for BOTH.
    """
    return upload_reserve() + shorts_reserve()


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
