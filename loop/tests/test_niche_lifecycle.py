"""The niche lifecycle must RETIRE and PROMOTE, and refuse to when it must not.

`loop/monthly.py` computed `exhausted_domains` and `next_domain` every month
from 2026-08 and wrote them into prose that nothing read. A domain could decay
to an empty queue and keep its weekly slots for ever, in a report that named it
as finished. `loop/domains.lifecycle()` closes that; this proves it, and proves
each refusal, by constructing the month rather than waiting years for one.

  1. a decayed, measured domain is RETIRED and the next-ranked one PROMOTED
  2. the new allocation still sums to cadence.ceiling
  3. a decayed domain with too FEW measured episodes is refused, named
     QUEUE_DECAYED_BUT_UNMEASURED - a thin queue early is a scoring backlog
  4. with no unused domain left, retirement is refused, named
     NO_REPLACEMENT_DOMAIN - retirement is a swap, never a subtraction
  5. a healthy month changes nothing
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


def evidence(alloc: dict, measured: int, weak: str | None = None) -> dict:
    ev = {d: {"measured": measured, "views": 500, "avd_s": 240.0,
              "avp": 38.0, "judgeable": True} for d in alloc}
    if weak:
        ev[weak]["avd_s"] = 12.0
    return ev


def main() -> int:
    cfg = config()
    alloc = D.allocation(cfg)
    need = D.min_episodes_to_judge(cfg)
    ceiling = int(cfg["cadence"]["ceiling"])
    victim = sorted(alloc)[0]
    print(f"allocation {alloc}, floor {need} measured episode(s), "
          f"ceiling {ceiling}")

    # 1 + 2 -------------------------------------------------- retire, promote
    with depth_of({d: (0 if d == victim else 20) for d in alloc}, [victim]):
        d = D.lifecycle(cfg, evidence(alloc, need, victim))
    check("a decayed, measured domain is retired", d.get("applied"),
          d.get("stop") or d.get("why", ""))
    check("the decayed domain is the one retired", d["retired"] == victim,
          f"retired {d['retired']}")
    check("the next-ranked unused domain is promoted",
          d["promoted"] == D.next_unused(list(alloc)),
          f"promoted {d['promoted']}")
    check("the retired domain keeps no slots", victim not in d["allocation"])
    check("the allocation still sums to cadence.ceiling",
          sum(d["allocation"].values()) == ceiling,
          f"sums to {sum(d['allocation'].values())}")
    # and the split it produces must not raise
    D.slots_at({**cfg, "domains": {**cfg["domains"],
                                   "allocation": d["allocation"]}}, 2)
    check("slots_at() accepts the post-retirement split", True)

    # 3 ------------------------------------------- decayed but barely measured
    with depth_of({d2: (0 if d2 == victim else 20) for d2 in alloc}, [victim]):
        thin = D.lifecycle(cfg, evidence(alloc, need - 1, victim))
    check("a thin queue with too few measured episodes is refused",
          not thin.get("applied")
          and thin.get("stop") == "QUEUE_DECAYED_BUT_UNMEASURED",
          f"{thin.get('stop')}: {thin.get('why', '')[:120]}")

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
    doms = {h["domain"] for h in picked}
    check("the harvesters span both live domains", doms >= set(alloc),
          f"harvested domains {doms} vs allocation {set(alloc)}")

    real_dec = FL.declared_harvesters
    FL.declared_harvesters = lambda: [h for h in real_dec()
                                      if h["domain"] != victim]
    try:
        _, gone = FL.harvesters_for(cfg)
    finally:
        FL.declared_harvesters = real_dec
    check("a domain whose harvester disappears is reported, not skipped",
          gone == [victim], f"got {gone}")

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

    if CHECKS == 0:
        raise AssertionError("ran zero checks - an empty test proves nothing")
    print(f"\n{CHECKS} check(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
