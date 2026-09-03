#!/usr/bin/env python3
"""Git merge driver for `loop/state/quota.json` — reconciles concurrent lanes.

The defect this exists to fix, CONFIRMED 2026-09-03: `loop-upload-cloud` and
`loop-reach` both spend quota and both commit `loop/state/quota.json` through
`bin/loop-stage.sh`. GitHub's `concurrency: group: loop-state` did not save
this in practice — two `workflow_dispatch` runs one minute apart (33783826056,
33783829147) still overlapped, and the loser's rebase hit a textual conflict
on this file, then died — see `bin/loop-stage.sh` for the other half of that
fix (the retry loop that could never recover from it).

`quota.json` is derived accounting (`{"day", "spent", "by_lane": {lane: n}}`),
never hand-edited, and `loop/quota.py:spend()` only ever ADDS to it. That makes
a textual conflict here unnecessary: the correct merge is not "pick a side",
it is "count both real spends". For each lane, this takes BOTH sides' deltas
from the common ancestor and sums them — never a max, never an overwrite — so
a real unit spent by either lane is never lost and never invented. `spent` is
re-derived as the sum of the merged `by_lane`, never trusted from either side
directly, so it cannot drift out of sync with the lane totals.

A same-day rollover on either side (comparing against `base["day"]`) makes the
deltas incomparable — the newer day's own totals win outright, nothing to sum,
because a new day's spend did not exist yet in the base to take a delta against.

Registered via `.gitattributes` (`loop/state/quota.json merge=quota-union`);
the driver COMMAND is set locally by `bin/loop-stage.sh` before every pull
--rebase, because git will not execute a driver command from a committed file.

If either side fails to parse as JSON, this refuses to guess and returns
non-zero so git falls back to a normal (visible) conflict — better a human
sees a raw conflict than this driver invents a number.

Git invokes this as:  merge_quota_json.py %O %A %B
    %O  common ancestor      %A  current side (OVERWRITTEN with the result)
    %B  other side
"""
from __future__ import annotations

import json
import sys


def _load(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def merge(base: dict, ours: dict, theirs: dict) -> dict:
    if ours.get("day") != base.get("day") or theirs.get("day") != base.get("day"):
        # A day rolled over on at least one side since the common ancestor.
        # Deltas against a stale day are meaningless; the side with the later
        # day already reset to {spent: 0, by_lane: {}} and started counting
        # today for real, so it is simply the answer, not one side of a sum.
        newest = max((ours, theirs), key=lambda d: str(d.get("day") or ""))
        return {"day": newest.get("day"),
                "spent": int(newest.get("spent", 0)),
                "by_lane": dict(newest.get("by_lane", {}))}

    lanes = (set(base.get("by_lane", {}))
             | set(ours.get("by_lane", {}))
             | set(theirs.get("by_lane", {})))
    merged_by_lane = {}
    for lane in sorted(lanes):
        b = int(base.get("by_lane", {}).get(lane, 0))
        a = int(ours.get("by_lane", {}).get(lane, 0))
        t = int(theirs.get("by_lane", {}).get(lane, 0))
        # base + (this side's own increase) + (the other side's own increase).
        # Never (a - b) alone or (t - b) alone -- that would keep only one
        # lane's real spend. Never max(a, t) -- that silently drops whichever
        # lane spent less, which is exactly "losing real quota accounting".
        merged_by_lane[lane] = b + (a - b) + (t - b)
    return {
        "day": base.get("day"),
        "spent": sum(merged_by_lane.values()),
        "by_lane": merged_by_lane,
    }


def main() -> int:
    if len(sys.argv) < 4:
        sys.stderr.write("usage: merge_quota_json.py <base> <ours> <theirs>\n")
        return 2
    base_path, ours_path, theirs_path = sys.argv[1:4]
    base = _load(base_path) or {"day": None, "spent": 0, "by_lane": {}}
    ours = _load(ours_path)
    theirs = _load(theirs_path)
    if ours is None or theirs is None:
        sys.stderr.write("merge_quota_json.py: one side is not valid JSON; "
                          "refusing to guess, falling back to a real conflict\n")
        return 1

    result = merge(base, ours, theirs)
    with open(ours_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(f"merge_quota_json.py: reconciled {ours_path} "
          f"(day {result['day']}, spent {result['spent']}, "
          f"lanes {sorted(result['by_lane'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
