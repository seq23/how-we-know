"""Hostile review 2026-11-02, findings 3, 8 and 18, proven negatively.

  1. An empty day within 14 days goes to a ready episode from ANY topic when
     its own topic has nothing in the run; a topic with a ready episode keeps
     its own day.
  2. An unreadable publish time refuses to schedule (never double-books).
  3. The daily runway check authors when the Mac's written queue is under two
     nights even while the runway reads ok, and names RUNWAY_FULL otherwise.
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="calfill-"))

import backfill as B  # noqa: E402
import domains as D  # noqa: E402
import draft  # noqa: E402
from common import config  # noqa: E402


def main() -> int:
    fails = []
    per_week = 4
    split = B.domain_weekdays(config(), per_week)
    if len(split) < 2:
        print("FAIL: fewer than two domains on the rotation; nothing to borrow")
        return 1
    doms = sorted(split)
    mine, other = doms[0], doms[1]
    real = D.domain_of_slug
    D.domain_of_slug = lambda s: {"a": mine, "b": other}.get(s)
    try:
        led = {"published": []}
        alone = B.schedule_slugs(led, ["a"], per_week)[0]
        own = B.rotation_slots(B.datetime.now(B.timezone.utc) + B.timedelta(hours=B.MIN_LEAD_HOURS),
                               1, split[mine], set())[0]
        anyday = B.rotation_slots(B.datetime.now(B.timezone.utc) + B.timedelta(hours=B.MIN_LEAD_HOURS),
                                  1, tuple(sorted(w for v in split.values() for w in v)), set())[0]
        if alone != min(own, anyday):
            fails.append(f"a ready {mine} episode got {alone}, not the first empty day {min(own, anyday)}")
        both = B.schedule_slugs(led, ["a", "b"], per_week)
        if both[0].astimezone(B.PUBLISH_TZ).weekday() not in split[mine]:
            fails.append(f"{mine} took {other}'s day although {other} had an episode ready")
        try:
            B.rotation_slots(B.datetime.now(B.timezone.utc), 1, split[mine], {"not-a-date"})
            fails.append("an unreadable publish time was skipped (its day could be double-booked)")
        except ValueError:
            pass
    finally:
        D.domain_of_slug = real

    seen = {}
    real_rb, real_q = draft.rebuild_runway_if_short, draft.mac_queue
    draft.rebuild_runway_if_short = lambda st, *a, **k: seen.update(force=k.get("force"))
    try:
        for q, want in (([], True), (["x"] * 20, False)):
            draft.mac_queue = lambda q=q: q
            try:
                draft.daily()
            except SystemExit:
                pass
            if seen.get("force") is not want:
                fails.append(f"Mac queue of {len(q)}: force={seen.get('force')}, want {want}")
    finally:
        draft.rebuild_runway_if_short, draft.mac_queue = real_rb, real_q

    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: calendar fill and daily runway")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
