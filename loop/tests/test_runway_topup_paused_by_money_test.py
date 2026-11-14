"""A healthy runway that cannot top up because of the Money test is a dated
policy pause, not the "goes dark" alarm (13 Nov 2026, runs 43150712370 and
43343042941).

The daily runway check read 5.7 weeks, level ok, under the 6-week target. Every
queued topic was materials (long-forms paused, her call 9 Nov) or money
(authored only by loop/money_author.py), so nothing was authorable, and the
lane raised RUNWAY_AUTHORING_FALLBACK - exit 3, an issue - two days running.

  a. ok runway, every candidate in a Money-test domain ->
     RUNWAY_TOPUP_PAUSED_BY_MONEY_TEST with resolves_at, classified
     self-resolving (exit 0) by loop/stop_policy.json;
  b. the same queue with the runway at WARN still pages:
     RUNWAY_AUTHORING_FALLBACK;
  c. an ok runway with one authorable topic still authors it, no stop.
No network. Writes only to temp dirs. Hard-fails on zero items.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("LOOP_DRY_RUN", "1")
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="stops-"))
HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))

import common                                              # noqa: E402
import draft                                               # noqa: E402

fails: list[str] = []
examined = 0


def check(ok, msg):
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


class St:
    def __init__(self):
        self.notes, self.works, self.stops = [], [], []

    def note(self, m): self.notes.append(m)
    def work(self, m): self.works.append(m)

    def named_stop(self, code, msg, detail=None, **kw):
        self.stops.append((code, detail or {}))
        raise common.NamedStop(code, msg, detail, kw.get("unblock", ""), kw.get("held_items"))


CFG = {"runway": {"rebuild_max_extra": 3, "target_weeks": 6},
       "domains": {"money_test": {
           "started": "2026-11-10", "check_days": 30,
           "own_author": {"money": "loop/money_author.py"},
           "longform_paused": {"materials": "no new materials long-forms"}}}}

tmp = Path(tempfile.mkdtemp(prefix="runway-money-"))
(tmp / "scripts").mkdir()
(tmp / "loop" / "drafts").mkdir(parents=True)


def rebuild(level: str, queue: list[dict]) -> St:
    saved = (draft.ROOT, draft.cadence.runway, draft.batch_queue.unwritten_entries,
             draft.domains.by_slug, draft.domains.allocation, draft.author.draft,
             draft.validate.run_all, draft.cadence.record_authoring_evidence,
             draft.pov_match.select, draft.pov_match.record_assignment)
    st = St()
    try:
        draft.ROOT = tmp
        draft.cadence.runway = lambda per_week: {
            "level": level, "short_domains": [] if level == "ok" else ["any"],
            "weeks_remaining": 5.7 if level == "ok" else 3.5, "videos_per_week": 6,
            "by_domain": {}, "message": f"stub {level}"}
        draft.batch_queue.unwritten_entries = lambda: list(queue)
        draft.domains.by_slug = lambda: {}
        draft.domains.allocation = lambda cfg: {"materials": 2, "money": 2, "deep-sea": 2}

        def fake_draft(q, slug, pov, **kw):
            p = tmp / "loop" / "drafts" / f"{slug}.md"
            p.write_text(f"# {q}?\n")
            return {"path": str(p.relative_to(tmp))}
        draft.author.draft = fake_draft
        draft.validate.run_all = lambda items: (True, [{"validator": "stub", "status": "PASS"}])
        draft.cadence.record_authoring_evidence = lambda *a, **k: {"scripts": []}
        draft.pov_match.select = lambda slug, q, used: {"pov_id": "p", "line": "l"}
        draft.pov_match.record_assignment = lambda slug, pov: None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                draft.rebuild_runway_if_short(st, CFG, 6, [], set())
            except common.NamedStop:
                pass
    finally:
        (draft.ROOT, draft.cadence.runway, draft.batch_queue.unwritten_entries,
         draft.domains.by_slug, draft.domains.allocation, draft.author.draft,
         draft.validate.run_all, draft.cadence.record_authoring_evidence,
         draft.pov_match.select, draft.pov_match.record_assignment) = saved
    return st


PAUSED_QUEUE = [{"slug": "metal-a", "query": "why metal a", "domain": "materials"},
                {"slug": "money-a", "query": "how money a", "domain": "money"}]

# a.
st = rebuild("ok", PAUSED_QUEUE)
codes = [c for c, _ in st.stops]
check(codes == ["RUNWAY_TOPUP_PAUSED_BY_MONEY_TEST"], f"(a) ok runway under the Money test stopped {codes}")
detail = st.stops[0][1] if st.stops else {}
check(detail.get("resolves_at") == "2026-12-10", f"(a) resolves_at {detail.get('resolves_at')}")
disp, why = common.disposition("daily-runway", "RUNWAY_TOPUP_PAUSED_BY_MONEY_TEST", detail, 1)
check(disp == "self_resolving", f"(a) classified {disp}: {why}")

# b.
st = rebuild("warn", PAUSED_QUEUE)
codes = [c for c, _ in st.stops]
check(codes == ["RUNWAY_AUTHORING_FALLBACK"], f"(b) a WARN runway with nothing authorable stopped {codes}")

# c.
st = rebuild("ok", PAUSED_QUEUE + [{"slug": "deep-a", "query": "how deep a", "domain": "deep-sea"}])
check(not st.stops and len(st.works) == 1, f"(c) an authorable topic was not authored: stops {st.stops}, works {st.works}")

if examined == 0:
    print("FAIL test_runway_topup_paused_by_money_test: examined 0")
    raise SystemExit(1)
for f in fails:
    print(f"  ✗ {f}")
print(f"{'FAIL' if fails else 'ok'} test_runway_topup_paused_by_money_test: {examined} checks")
raise SystemExit(1 if fails else 0)
