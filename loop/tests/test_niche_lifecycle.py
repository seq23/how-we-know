"""The niche lifecycle must RETIRE and PROMOTE, and refuse to when it must not.

`loop/monthly.py` computed `exhausted_domains` and `next_domain` every month
from 2026-08 and wrote them into prose that nothing read. A domain could decay
to an empty queue and keep its weekly slots for ever, in a report that named it
as finished. `loop/domains.lifecycle()` closes that; this proves it, and proves
each refusal, by constructing the month rather than waiting years for one.

  1. a decayed, measured domain is RETIRED and the next-ranked one PROMOTED
  2. the new allocation keeps its total, and the rotation's weekdays move
     with it (the promoted domain takes the retired one's days)
  3. RESULTS DECIDE (owner rule A, 2 Nov 2026): a decayed queue HOLDS - under
     30 long videos it is TOPICS_HELD_FOR_EVIDENCE with the counts, and even
     past 30 a thin queue never retires a domain that scores level; a domain
     at exactly half the best does not retire, under half does (check 1).
     NEGATIVE PROOF (by hand, 2026-11-02): restoring "retire the exhausted
     domain" in lifecycle() fails the two hold checks; changing `<` to `<=`
     fails the exactly-half check; restored, green.
  4. with no unused domain left, retirement is refused, named
     NO_REPLACEMENT_DOMAIN - retirement is a swap, never a subtraction
  5. a healthy month changes nothing
  8. a domain that is not ONBOARDED is never promoted: every running domain
     reads ready, the real next-ranked one does not and is refused by name
     (REPLACEMENT_NOT_ONBOARDED, allocation held), and a not-ready domain is
     passed over for the next ready one (1 Nov 2026: space-astronomy was
     promoted with nothing in place and main went red in three workflows)
  6. the SATURDAY HARVEST covers every allocated domain, and stops on one it
     cannot cover
  7. a queued slug with no script still counts toward its domain's depth -
     which is the whole state a promoted domain is in

Hard-fails if it runs zero checks.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
sys.path.insert(0, os.path.join(ROOT, "research"))

import domains as D          # noqa: E402
import footage_lane as FL    # noqa: E402
from common import config    # noqa: E402

CHECKS = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"{label}: {detail or 'failed'}")
    print(f"  ok  {label}")


class depth_of:
    """Force queue_depth()/exhausted() for one constructed month."""

    def __init__(self, depths: dict, exhausted: list):
        self.depths, self.ex = depths, exhausted

    def __enter__(self):
        self._d, self._e = D.queue_depth, D.exhausted
        D.queue_depth = lambda: dict(self.depths)
        D.exhausted = lambda cfg, published=None: list(self.ex)   # noqa: ARG005
        return self

    def __exit__(self, *a):
        D.queue_depth, D.exhausted = self._d, self._e


def evidence(alloc: dict, videos: int, weak: str | None = None,
             weak_score: float = 4.0) -> dict:
    """Every domain `videos` long videos scoring 10.0; `weak` scores weak_score
    (under half the best by default)."""
    ev = {d: {"measured": videos, "videos": videos, "views": 500, "avd_s": 240.0,
              "avp": 38.0, "judgeable": True, "score": 10.0} for d in alloc}
    if weak:
        ev[weak]["score"] = weak_score
    return ev


def main() -> int:
    cfg = config()
    alloc = D.allocation(cfg)
    need = D.results_rule(cfg)["min_long_videos"]
    ceiling = int(cfg["cadence"]["ceiling"])
    victim = sorted(alloc)[0]
    print(f"allocation {alloc}, floor {need} measured episode(s), "
          f"ceiling {ceiling}")

    # 1 + 2 -------------------------------------------------- retire, promote
    # (the next-ranked domain is declared onboarded here; 8 proves the gate)
    real_gaps = D.onboarding_gaps
    D.onboarding_gaps = lambda name, c: []                     # noqa: ARG005
    try:
        with depth_of({d: (0 if d == victim else 20) for d in alloc}, [victim]):
            d = D.lifecycle(cfg, evidence(alloc, need, victim))
    finally:
        D.onboarding_gaps = real_gaps
    check("a domain at 30+ videos scoring under half the best is retired",
          d.get("applied"),
          d.get("stop") or d.get("why", ""))
    check("the weakest-scoring domain is the one retired", d["retired"] == victim,
          f"retired {d['retired']}")
    check("the next-ranked unused domain is promoted",
          d["promoted"] == D.next_unused(list(alloc)),
          f"promoted {d['promoted']}")
    check("the retired domain keeps no slots", victim not in d["allocation"])
    # Since the owner's rotation (2026-10-13) the allocation is expressed in
    # REGISTERED rotation days, not the ceiling: retirement keeps the total.
    check("the allocation keeps its total (the rotation's registered days)",
          sum(d["allocation"].values()) == sum(alloc.values()),
          f"sums to {sum(d['allocation'].values())}, was {sum(alloc.values())}")
    new_rot = D.rotation_after(cfg, d["allocation"])
    moved_cfg = {**cfg, "cadence": {**cfg["cadence"], "rotation": {
        **cfg["cadence"]["rotation"], "weekdays": new_rot}},
        "domains": {**cfg["domains"], "allocation": d["allocation"]}}
    check("the rotation moves with it: the promoted domain takes the retired "
          "one's weekdays and nothing else changes",
          victim not in new_rot.values()
          and D.rotation_counts(moved_cfg) == d["allocation"]
          and all(new_rot[k] == v for k, v in cfg["cadence"]["rotation"]["weekdays"].items()
                  if v not in (victim, d["promoted"])),
          f"{new_rot}")
    # and the split it produces must not raise
    D.slots_at(moved_cfg, 2)
    check("slots_at() accepts the post-retirement split", True)

    # 3 ---------------- RESULTS DECIDE (owner rule A, 2 Nov 2026): a decayed
    # queue HOLDS - below 30 long videos nothing retires, however thin the
    # queue and however weak the score; the domain is listed for more research.
    with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc}, [victim]):
        thin = D.lifecycle(cfg, evidence(alloc, need - 1, victim, 0.0))
    check("a decayed queue below 30 videos HOLDS (does not retire)",
          not thin.get("applied")
          and thin.get("stop") == "TOPICS_HELD_FOR_EVIDENCE"
          and thin.get("allocation") == alloc
          and thin.get("counts", {}).get(victim) == need - 1
          and thin.get("research_more") == [victim]
          and f"{victim} {need - 1}/{need}" in thin.get("why", ""),
          f"{thin.get('stop')}: {thin.get('why', '')[:160]}")
    with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc}, [victim]):
        decayed = D.lifecycle(cfg, evidence(alloc, need))
    check("a decayed queue never retires a domain that scores level",
          not decayed.get("applied") and not decayed.get("stop")
          and decayed.get("research_more") == [victim], decayed.get("why", ""))
    ev_one = evidence(alloc, need)
    ev_one[sorted(alloc)[-1]]["videos"] = need - 1
    with depth_of({d2: 20 for d2 in alloc}, []):
        one_short = D.lifecycle(cfg, ev_one)
    check("one topic short of 30 holds every topic",
          one_short.get("stop") == "TOPICS_HELD_FOR_EVIDENCE", one_short.get("why", ""))
    with depth_of({d2: 20 for d2 in alloc}, []):
        half = D.lifecycle(cfg, evidence(alloc, need, victim, 5.0))
    check("a domain scoring EXACTLY half the best does not retire",
          not half.get("applied") and not half.get("stop"), half.get("why", ""))

    # 4 ------------------------------------------------ nothing left to promote
    real_next = D.next_unused
    D.next_unused = lambda active: None                        # noqa: ARG005
    try:
        with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc},
                      [victim]):
            swap = D.lifecycle(cfg, evidence(alloc, need, victim))
    finally:
        D.next_unused = real_next
    check("retirement with no replacement is refused",
          not swap.get("applied") and swap.get("stop") == "NO_REPLACEMENT_DOMAIN",
          f"{swap.get('stop')}: {swap.get('why', '')[:120]}")

    # 5 ------------------------------------------------------- a healthy month
    with depth_of({d2: 20 for d2 in alloc}, []):
        calm = D.lifecycle(cfg, evidence(alloc, need))
    check("a healthy month retires nothing", not calm.get("applied")
          and not calm.get("stop"), calm.get("why", ""))

    # 6 --------------------------------------------- the harvest sees them all
    picked, uncovered = FL.harvesters_for(cfg)
    check("every allocated domain has a scheduled harvester", not uncovered,
          f"uncovered: {uncovered}")
    check("harvesters were actually found", len(picked) > 0)
    # a harvester may feed several domains (`domains`), as harvesters_for() reads it
    doms = {d_ for h in picked for d_ in (h.get("domains") or [h["domain"]])}
    check("the harvesters span both live domains", doms >= set(alloc),
          f"harvested domains {doms} vs allocation {set(alloc)}")

    real_dec = FL.declared_harvesters
    FL.declared_harvesters = lambda: [h for h in real_dec()
                                      if h["domain"] != victim]
    try:
        _, gone = FL.harvesters_for(cfg)
    finally:
        FL.declared_harvesters = real_dec
    # the removed harvesters may also feed other domains (the stock harvester
    # feeds deep sea, materials and Money): every allocated domain left with no
    # harvester is reported, the victim among them, and no covered one is
    def _feeds(h):
        return h.get("domains") or [h["domain"]]
    left = {d_ for h in real_dec() if h["domain"] != victim and h.get("scheduled", True)
            for d_ in _feeds(h)}
    check("a domain whose harvester disappears is reported, not skipped",
          victim in gone and set(gone) == {d_ for d_ in alloc if d_ not in left},
          f"got {gone}")

    # 7 ------------------------------- a queued slug with no script still counts
    import publish_order_domain as POD                      # noqa: PLC0415
    fake = os.path.join(ROOT, "research", "publish_order__lifecycle_test.json")
    promoted = D.next_unused(list(alloc)) or sorted(D.known())[-1]
    with open(fake, "w", encoding="utf-8") as fh:
        json.dump({"domain": promoted, "generator": "test",
                   "queue": [{"slug": "a-slug-with-no-script-at-all",
                              "domain": promoted, "title": "?"}]}, fh)
    try:
        depth = D.queue_depth()
    finally:
        os.unlink(fake)
    check("a queued slug with no script counts toward its domain",
          depth.get(promoted, 0) >= 1,
          f"{promoted} read as depth {depth.get(promoted, 0)} - a promoted "
          f"domain would be out of runway on its first day")
    check("out_path is derived from the domain name",
          POD.out_path(promoted).endswith(
              f"publish_order_{promoted.replace('-', '_')}.json"))

    # 8 --------------------------------------- only an onboarded domain runs
    for live in alloc:
        g = D.onboarding_gaps(live, cfg)
        check(f"running domain {live} reads as onboarded", not g, f"{g}")
    nxt = D.next_unused(list(alloc))
    gaps = D.onboarding_gaps(nxt, cfg) if nxt else []
    if nxt and gaps:
        with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc},
                      [victim]):
            held = D.lifecycle(cfg, evidence(alloc, need, victim))
        check("a not-onboarded next domain is refused by name, allocation held",
              not held.get("applied")
              and held.get("stop") == "REPLACEMENT_NOT_ONBOARDED"
              and held.get("allocation") == alloc
              and nxt in (held.get("not_onboarded") or {}),
              f"{held.get('stop')}: {held.get('why', '')[:160]}")
    D.onboarding_gaps = lambda name, c: ["planted gap"]        # noqa: ARG005
    try:
        with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc},
                      [victim]):
            none_ready = D.lifecycle(cfg, evidence(alloc, need, victim))
    finally:
        D.onboarding_gaps = real_gaps
    check("with no unused domain onboarded, nothing is promoted",
          not none_ready.get("applied")
          and none_ready.get("stop") == "REPLACEMENT_NOT_ONBOARDED"
          and none_ready.get("allocation") == alloc,
          f"{none_ready.get('stop') or none_ready.get('promoted')}")
    unused = [n for n in D.known() if n not in alloc]
    check("the taxonomy has two unused domains to rank", len(unused) >= 2,
          f"{unused}")
    first, second = unused[0], unused[1]
    D.onboarding_gaps = lambda name, c: ([] if name == second  # noqa: ARG005
                                         else ["planted gap"])
    try:
        with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc},
                      [victim]):
            skip = D.lifecycle(cfg, evidence(alloc, need, victim))
    finally:
        D.onboarding_gaps = real_gaps
    check("a not-ready higher-ranked domain is passed over for a ready one",
          skip.get("applied") and skip.get("promoted") == second
          and first in (skip.get("passed_over") or {}),
          f"{skip.get('stop') or skip.get('promoted')}")

    if CHECKS == 0:
        raise AssertionError("ran zero checks - an empty test proves nothing")
    print(f"\n{CHECKS} check(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
