"""The runway rebuild hands validation an item that carries its POV line.

2026-10-12, run 38275491631 (mon-draft): rebuild_runway_if_short() matched a
bank line with pov_match.select(), authored three scripts around it, then
validated an item WITHOUT pov_id/pov_line. V4 reads the line off the item (the
assignment is only recorded after validation passes), so every draft failed
"no POV line assigned and none matched" and the lane stopped
RUNWAY_AUTHORING_FALLBACK with three good scripts thrown away.

This drives the real function with the authoring call stubbed, captures the
item it validates, and runs the REAL V4 over it. Hard-fails on zero items.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="stops-"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import draft  # noqa: E402
import validate  # noqa: E402

SCRIPT = "scripts/how-strong-is-graphene.md"   # any real script; V4 reads it


class St:
    def __init__(self):
        self.notes, self.works, self.stops = [], [], []

    def note(self, m): self.notes.append(m)
    def work(self, m): self.works.append(m)
    def named_stop(self, code, msg, **kw): self.stops.append(code)


def main() -> int:
    fails, captured = [], []
    rows = [{"slug": "why-are-deep-sea-creatures-so-big",
             "query": "why are deep sea creatures so big", "domain": "deep-sea"},
            {"slug": "how-are-microchips-designed",
             "query": "how are microchips designed", "domain": "materials"}]
    saved = (draft.cadence.runway, draft.batch_queue.unwritten_entries,
             draft.domains.by_slug, draft.domains.allocation,
             draft.author.draft, draft.validate.run_all)
    try:
        draft.cadence.runway = lambda per_week: {
            "level": "warn", "short_domains": ["any"], "weeks_remaining": 4,
            "message": "stub"}
        draft.batch_queue.unwritten_entries = lambda: list(rows)
        draft.domains.by_slug = lambda: {}
        draft.domains.allocation = lambda cfg: {"deep-sea": 1, "materials": 1}
        draft.author.draft = lambda q, slug, pov, **kw: {"path": SCRIPT}

        def run_all(items):
            captured.extend(items)
            return False, [{"validator": "stub", "status": "FAIL(1)"}]
        draft.validate.run_all = run_all
        st = St()
        draft.rebuild_runway_if_short(st, {"runway": {"rebuild_max_extra": 3}},
                                      1, [], [])
    finally:
        (draft.cadence.runway, draft.batch_queue.unwritten_entries,
         draft.domains.by_slug, draft.domains.allocation,
         draft.author.draft, draft.validate.run_all) = saved

    if not captured:
        fails.append("the runway rebuild validated ZERO items - this test "
                     "reached nothing")
    for it in captured:
        if not (it.get("pov_id") and it.get("pov_line")):
            fails.append(f"{it['slug']}: validated without pov_id/pov_line")
            continue
        r = validate.v4_pov([dict(it)])
        if r.failures:
            fails.append(f"{it['slug']}: real V4 refuses the item the runway "
                         f"rebuild validates: {r.failures}")
    print(f"examined {len(captured)} runway-rebuild item(s)")
    for f in fails:
        print(f"  ✗ {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
