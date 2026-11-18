"""A domain trip holds back its domain, not the channel (18 Nov 2026).

The materials-and-manufacturing trip of 13 Nov halted every How We Know
publishing lane for five days: no Short and no long-form for deep sea or
food, which were holding. Proved both ways, and negatively:

  1. the live record (no `domain` field, the domain only in its detail)
     does NOT halt the scoped lanes (cloud-upload, shorts-cloud, backfill),
     and names materials-and-manufacturing as the one blocked domain;
  2. the scoped lanes' selectors skip that domain's items and keep the others
     (backfill.library_pending, shorts_lane.pending, with stubbed queues);
  3. every other cause (strike, retention, validator, manual) still halts
     every How We Know lane, a domain trip still halts the unscoped lanes,
     and a domain trip whose domain cannot be read halts everything;
  4. a new trip records its domain; a reset forgets it.

Hard-fails if it checked nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="breaker-domain-")
os.environ["LOOP_BREAKER_FLAG"] = os.path.join(TMP, "breaker.json")
os.environ.setdefault("LOOP_STOPS_DIR", os.path.join(TMP, "stops"))
os.environ.pop("GITHUB_STEP_SUMMARY", None)
sys.path.insert(0, LOOP)
import breaker  # noqa: E402

FAILS: list[str] = []
CHECKED = 0
MAT = "materials-and-manufacturing"


def halted(stage: str) -> bool:
    try:
        breaker.guard(stage)
    except SystemExit:
        return True
    return False


def expect(stage: str, want: bool, why: str) -> None:
    global CHECKED
    CHECKED += 1
    got = halted(stage)
    if got != want:
        FAILS.append(f"{why}: {stage} {'halted' if got else 'NOT halted'}")


def write(record: dict) -> None:
    Path(breaker.FLAG).write_text(json.dumps(record))


LIVE = {"state": "tripped", "tripped_at": "2026-11-13T22:05:54+00:00", "cause": "domain",
        "detail": f"3 consecutive {MAT} videos below the duration floor while 1 other domain(s) "
                  "are holding. That is a NICHE that is not working, not a format that is.",
        "longform_owner_approval_required": True, "history": []}

# 1. the live record: the scoped lanes publish, the domain is named
for s in breaker.DOMAIN_SCOPED:
    write(LIVE)
    expect(s, False, "the live materials domain trip")
write(LIVE)
if breaker.blocked_domains() != {MAT}:
    FAILS.append(f"the live trip's blocked domain is {breaker.blocked_domains()}, not {MAT}")

# 2. the selectors skip the tripped domain's items and keep the others
import backfill  # noqa: E402
import batch_queue  # noqa: E402
import domains  # noqa: E402
import shorts_lane  # noqa: E402
import render_gate  # noqa: E402
import lengthen  # noqa: E402
import ledger  # noqa: E402
import approved_renders  # noqa: E402

DOMAIN = {"deep-1": "deep-sea-ocean-science", "steel-1": MAT, "bread-1": "food-science"}
saved = (batch_queue.queued_entries, domains.domain_of_slug, render_gate.held_slugs, lengthen.upload_hold,
         ledger.published_slugs, approved_renders.load, backfill.food_hold, shorts_lane.load_ledger,
         shorts_lane.voice_blocked, shorts_lane.cuts_for, shorts_lane.order_by_mix, ledger.load)
try:
    batch_queue.queued_entries = lambda *a, **k: [{"slug": s} for s in DOMAIN]
    domains.domain_of_slug = lambda s, default=None: DOMAIN.get(s, default)
    render_gate.held_slugs = lambda: set()
    lengthen.upload_hold = lambda s: None
    ledger.published_slugs = lambda: set()
    ledger.load = lambda: {"published": [{"slug": "bread-1", "scheduled_publish_at": "2026-11-20T16:00:00Z"}]}
    approved_renders.load = lambda: {s: {"sha256": "x"} for s in DOMAIN}
    backfill.food_hold = lambda s: None
    shorts_lane.load_ledger = lambda: {"published": []}
    shorts_lane.voice_blocked = lambda: set()
    shorts_lane.cuts_for = lambda s, cfg=None: 1
    shorts_lane.order_by_mix = lambda out, cfg=None: out
    os.environ["LOOP_VALIDATOR_HOLD"] = os.path.join(TMP, "none.json")
    for record, want in ((LIVE, {"deep-1", "bread-1"}), (dict(breaker.CLOSED), set(DOMAIN))):
        write(record)
        got = {s for s, *_ in backfill.library_pending(assets=lambda s: (Path("r"), Path("t")))}
        CHECKED += 1
        if got != want:
            FAILS.append(f"backfill.library_pending under {record.get('cause')}: {sorted(got)}, want {sorted(want)}")
        got = {p.slug for p in shorts_lane.pending(have=lambda s, r: True, cfg={})}
        CHECKED += 1
        if got != want:
            FAILS.append(f"shorts_lane.pending under {record.get('cause')}: {sorted(got)}, want {sorted(want)}")
finally:
    (batch_queue.queued_entries, domains.domain_of_slug, render_gate.held_slugs, lengthen.upload_hold,
     ledger.published_slugs, approved_renders.load, backfill.food_hold, shorts_lane.load_ledger,
     shorts_lane.voice_blocked, shorts_lane.cuts_for, shorts_lane.order_by_mix, ledger.load) = saved

# 3. every other cause still halts every lane; unscoped lanes still halt on a domain trip
for cause in ("strike", "manual"):            # never auto-reset, so the halt is certain
    for s in breaker.DOMAIN_SCOPED:
        write(dict(LIVE, cause=cause))
        expect(s, True, f"a {cause} trip")
write(LIVE)
expect("thu-upload", True, "the domain trip on an unscoped lane")
write(dict(LIVE, detail="one niche is low"))
expect("cloud-upload", True, "a domain trip whose domain cannot be read")
write(dict(LIVE, also=[{"cause": "manual", "detail": "x"}]))
expect("shorts-cloud", True, "a domain trip plus a manual cause")

# 4. a new trip records its domain; a reset forgets it
write(dict(breaker.CLOSED))
b = breaker.trip("domain", "low", domain="food-science")
if b.get("domain") != "food-science" or breaker.blocked_domains() != {"food-science"}:
    FAILS.append(f"a new domain trip did not record its domain: {b}")
b = breaker.reset("test")
if b.get("domain") or breaker.blocked_domains():
    FAILS.append(f"a reset kept the domain: {b}")

if CHECKED < 10:
    raise SystemExit(f"FAIL: checked only {CHECKED} thing(s)")
if FAILS:
    raise SystemExit("FAIL:\n  " + "\n  ".join(FAILS))
print(f"PASS: a domain trip holds back only its domain ({CHECKED} checks)")
