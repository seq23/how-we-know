"""Runway must count a dated, un-aired episode as inventory - per domain too.

WHAT BROKE. `cadence.runway()` has counted uploaded-and-dated episodes as
runway since 2026-09-05, with a comment saying an alarm wrong in the ALARMING
direction is one people learn to ignore. `domains.domain_runway()` was written
separately and counted only `queue_depth()` - the topics not yet MADE. A slug
leaves the publish-order queue the moment its episode exists, so a domain whose
whole queue has been made, uploaded and dated reads `queued: 0` -> `0.0 weeks`
-> `critical`.

On 2026-09-06 deep-sea-ocean-science had 0 queued and 14 episodes dated across
the next 7 weeks. The aggregate said 8.2 weeks (healthy, floor is 4.0). The
per-domain figure said 0.0/critical, the "worse of aggregate and any domain"
rule promoted it to the channel, and `loop · Sun 06:00 · rank topics` raised
RUNWAY_CRITICAL and exited 3 EVERY WEEK - a false alarm, weekly, forever.

WHAT THIS ASSERTS

  1. THE JOIN. The aggregate's `scheduled_not_yet_aired` equals the sum of the
     per-domain `scheduled_ahead`. Two counters that can disagree is how this
     started; this fails if they are ever forked again.
  2. NO FALSE CRITICAL. A domain with an empty queue and a full calendar is
     `ok`, not `critical`.
  3. THE ALARM STILL WORKS. A domain with an empty queue AND an empty calendar
     is still `critical`. This is the half that matters: the fix must not have
     muted the guard, only stopped it lying.
  4. RETIRED IS NOT INVENTORY. A retired row with a cancelled publishAt is not
     counted - the aggregate used to count it and overstated runway by a week.

Hard-fails when it examines zero domains or zero ledger rows.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

FUTURE = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30))
PAST = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30))


def _row(slug, when, **kw):
    r = {"slug": slug, "video_id": f"vid-{slug}", "privacy": "private",
         "scheduled_publish_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")}
    r.update(kw)
    return r


def _runway_with(ledger_rows, slug_domain, cfg, per_week):
    """Run the REAL runway arithmetic over a synthetic ledger."""
    import ledger as L                                      # noqa: PLC0415
    import domains as D                                     # noqa: PLC0415
    import cadence as C                                     # noqa: PLC0415

    old_load, old_by_slug, old_depth = L.load, D.by_slug, D.queue_depth
    old_slots = D.slots_at
    try:
        L.load = lambda: {"published": ledger_rows}
        D.by_slug = lambda: slug_domain
        D.queue_depth = lambda *a, **k: {}          # nothing left to MAKE
        D.slots_at = lambda c, n: {d: 2 for d in set(slug_domain.values())}
        return D.domain_runway(cfg, per_week), C, D
    finally:
        L.load, D.by_slug, D.queue_depth, D.slots_at = (
            old_load, old_by_slug, old_depth, old_slots)


def check() -> list[str]:
    import cadence as C                                     # noqa: PLC0415
    import domains as D                                     # noqa: PLC0415
    import ledger as L                                      # noqa: PLC0415
    from common import config                               # noqa: PLC0415

    fails: list[str] = []
    cfg = config()
    examined = 0

    # -- 1. the join, against the REAL repo state -----------------------
    real = C.runway(4)
    rows = L.load()["published"]
    if not rows:
        return ["examined ZERO ledger rows - this guard proved nothing"]
    if not real.get("by_domain"):
        return ["examined ZERO domains - domain_runway() returned nothing, so "
                "the per-domain half of the guard is unreachable"]
    examined += len(real["by_domain"])

    per_domain_sum = sum(v.get("scheduled_ahead", 0)
                         for v in real["by_domain"].values())
    if per_domain_sum != real["scheduled_not_yet_aired"]:
        fails.append(
            f"the aggregate counts {real['scheduled_not_yet_aired']} dated "
            f"episode(s) and the per-domain figures sum to {per_domain_sum} - "
            f"two counters that disagree about what inventory is, which is the "
            f"defect this guard exists for")

    # -- 2 & 3 & 4. the three scenarios, on a synthetic ledger ----------
    scenarios = [
        # (name, rows, expected level, why)
        ("empty queue, full calendar",
         [_row(f"d{i}", FUTURE) for i in range(14)],
         "ok",
         "14 episodes uploaded and dated is the most finished inventory a "
         "domain has, not the emptiest - this is the false RUNWAY_CRITICAL "
         "from run 34026361219"),
        ("empty queue, empty calendar",
         [_row("aired", PAST, privacy="public")],
         "critical",
         "nothing queued and nothing dated IS out of runway - if this stops "
         "firing the fix muted the alarm instead of correcting it"),
        ("calendar is entirely RETIRED",
         [_row(f"r{i}", FUTURE, retired_at="2026-09-05T00:00:00+00:00")
          for i in range(14)],
         "critical",
         "a retired row keeps its scheduled_publish_at but its publishAt was "
         "cancelled on the live API - it will never air and is not inventory"),
    ]
    for name, srows, want, why in scenarios:
        examined += 1
        slug_domain = {r["slug"]: "test-domain" for r in srows}
        got, _, _ = _runway_with(srows, slug_domain, cfg, 4)
        lvl = (got.get("test-domain") or {}).get("level")
        if lvl != want:
            fails.append(
                f"scenario {name!r}: domain_runway reported {lvl!r}, expected "
                f"{want!r}. {why}")

    if examined == 0:
        fails.append("examined ZERO domains or scenarios")
    print(f"inspected {len(real['by_domain'])} live domain(s), "
          f"{len(rows)} ledger row(s) and {len(scenarios)} scenario(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - runway counts dated episodes, per domain and in "
          "aggregate, and still fires when the calendar is really empty"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
