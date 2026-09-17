"""The weekly scorer refreshes the primary ranking BEFORE anything can stop it,
and a missing API key is named as the owner's, not as a quota.

WHAT BROKE. `loop · Sat 06:00 · score` (loop/score.py) exists so that
research/publish_order.json - the file every publishing lane reads, judged by
the 10-day staleness gate in loop/cadence.py - is never stale. On 2026-09-12
(runs 34687628665 and 34705307582) it ran the first-scoring gate for
"new" domains BEFORE the primary scorer. That gate stopped, the stop ended
the stage, and the primary ranking was never regenerated. Ten days later
(2026-09-17, run 35230863447) `cadence.publish_order()` raised
PublishOrderStale and `loop · tests` went red on main - triggered by an
unrelated backfill commit, caused by a Saturday that had "succeeded".

Three defects, one class ("runs but inert", wearing a green tick):

  1. ORDER. A named stop is the last thing a stage does, so anything that can
     stop must come AFTER the work the stage exists to do.
  2. NAME. The gate had stopped on YOUTUBE_API_KEY_ABSENT - the owner has not
     supplied a key - but the quota regex matched the words "10,000 quota
     units/day" in that very banner, so it was filed as NEW_DOMAIN_QUOTA:
     self-resolving, "the next Saturday run retries". A missing key does not
     resolve on a retry. It is owner_action.
  3. TRIGGER. The gate fired for deep sea, which HAS a scored file - every
     one of its 16 topics was simply already uploaded. `missing_queues()`
     asked for remaining inventory when it meant "never scored", so it re-ran
     a first-scoring gate every Saturday for a domain scored on 2026-08-30.

This test drives loop/score.py's real main() in-process against a fake
scorer and a fake domain gate, and proves all three. Proven negatively in
the PR that added it: with the pre-fix ordering restored, case A fails.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))

# The suite's runner sets this; a bare invocation must not write the loop's
# own state either.
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="score-test-"))

import cadence  # noqa: E402
import score  # noqa: E402
import competition  # noqa: E402  (research/competition.py: the real banner)

fails: list[str] = []
examined = 0


def key_absent_banner() -> str:
    """competition.py's REAL key-absent output, not a paraphrase of it.

    The regression was that this text contains the word 'quota'. If the
    script's wording ever changes so that it no longer does, this fixture
    changes with it - it is built from the same STOP record the script prints.
    """
    rec = competition.STOP
    lines = ["=" * 72, "NAMED STOP: " + rec["name"], "=" * 72,
             f"Missing : {rec['what_is_missing']}",
             f"Owner   : {rec['who_must_supply_it']}",
             "Stop recorded at research/competition_stop.json. No score was "
             "written, because no score was measured.",
             "Exit 0: this is a declared stop, not a failure."]
    text = "\n".join(lines)
    assert "quota" in text.lower(), "fixture no longer reproduces the trap"
    return text


def fresh_ranking() -> dict:
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "generator": "research/publish_order.py",
            "queue": [{"slug": "01-test-topic", "queue_position": 1,
                       "domain": "deep-sea-ocean-science"}]}


def stale_ranking() -> dict:
    r = fresh_ranking()
    r["generated_at"] = (dt.datetime.now(dt.timezone.utc)
                         - dt.timedelta(days=30)).isoformat()
    return r


class Harness:
    """Run score.main() with the scorer and the domain gate replaced.

    `gate_output` is what the fake publish_order_domain.py prints;
    `gate_rc` its exit code. The fake primary scorer writes a fresh ranking
    to the (redirected) PUBLISH_ORDER and exits 0.
    """

    def __init__(self, gate_output: str, gate_rc: int = 3,
                 domains: dict | None = None):
        self.calls: list[str] = []
        self.gate_output = gate_output
        self.gate_rc = gate_rc
        # Under ROOT: the stage prints every path relative to it. Removed
        # in run()'s finally, so nothing is left in the tree.
        self.tmp = Path(tempfile.mkdtemp(prefix=".score-harness-", dir=ROOT))
        self.order = self.tmp / "publish_order.json"
        self.entry = self.tmp / "fake_scorer.py"
        self.entry.write_text("# stand-in for research/publish_order.py\n")
        self.order.write_text(json.dumps(stale_ranking()))
        self.domains = ({"promoted-domain": self.tmp / "publish_order_promoted-domain.json"}
                        if domains is None else domains)
        self.stops = Path(tempfile.mkdtemp(prefix="score-stops-"))

    def fake_run(self, argv, **kw):
        cmd = " ".join(str(a) for a in argv)
        if str(self.entry) in cmd:
            self.calls.append("primary")
            self.order.write_text(json.dumps(fresh_ranking()))
            return subprocess.CompletedProcess(argv, 0, "ranked 1", "")
        if "publish_order_domain.py" in cmd:
            self.calls.append("gate")
            return subprocess.CompletedProcess(argv, self.gate_rc,
                                              self.gate_output, "")
        raise AssertionError(f"unexpected subprocess: {cmd}")

    def run(self) -> tuple[int, dict]:
        saved = (score.subprocess.run, score.entrypoint, score.missing_queues,
                 cadence.PUBLISH_ORDER, os.environ.get("LOOP_STOPS_DIR"))
        score.subprocess.run = self.fake_run
        score.entrypoint = lambda: self.entry
        score.missing_queues = lambda: dict(self.domains)
        cadence.PUBLISH_ORDER = self.order
        os.environ["LOOP_STOPS_DIR"] = str(self.stops)
        rc = 0
        try:
            score.main()
        except SystemExit as e:
            rc = int(e.code or 0)
        finally:
            (score.subprocess.run, score.entrypoint, score.missing_queues,
             cadence.PUBLISH_ORDER) = saved[:4]
            if saved[4] is None:
                os.environ.pop("LOOP_STOPS_DIR", None)
            else:
                os.environ["LOOP_STOPS_DIR"] = saved[4]
        recs = [json.loads(p.read_text()) for p in self.stops.glob("*-weekly-score.json")]
        self.fresh = self.order_is_fresh()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return rc, (recs[0] if recs else {})

    def order_is_fresh(self) -> bool:
        gen = json.loads(self.order.read_text()).get("generated_at", "")
        when = dt.datetime.fromisoformat(gen)
        return (dt.datetime.now(dt.timezone.utc) - when).days < 1


def check(label: str, cond: bool, why: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(f"{label}: {why}")


def main() -> int:
    # ---------------------------------------------------------------- A
    # The domain gate stops on a missing key. The primary ranking MUST already
    # be fresh on disk, the primary MUST have run before the gate, and the
    # stop MUST be the owner's (NEW_DOMAIN_KEY_ABSENT), green.
    h = Harness(key_absent_banner())
    rc, rec = h.run()
    check("A.order", h.calls[:1] == ["primary"],
          f"the primary scorer did not run first; call order was {h.calls}")
    check("A.gate-ran", "gate" in h.calls,
          f"the new-domain gate never ran; call order was {h.calls}")
    check("A.fresh", h.fresh,
          "the primary ranking was NOT refreshed before the stage ended - "
          "this is the 2026-09-12 failure")
    check("A.code", rec.get("code") == "NEW_DOMAIN_KEY_ABSENT",
          f"a missing key was filed as {rec.get('code')!r}, not "
          f"NEW_DOMAIN_KEY_ABSENT (the quota regex matched the key banner)")
    check("A.green", rc == 0,
          f"an owner_action stop must exit 0, not {rc}")
    check("A.disposition", rec.get("disposition") == "owner_action",
          f"disposition was {rec.get('disposition')!r}, not owner_action")

    # ---------------------------------------------------------------- B
    # A REAL quota exhaustion is still NEW_DOMAIN_QUOTA (self-resolving).
    # The reclassification must not have swallowed the genuine case.
    h = Harness("HTTP 403 quotaExceeded: The request cannot be completed "
                "because you have exceeded your quota.")
    rc, rec = h.run()
    check("B.code", rec.get("code") == "NEW_DOMAIN_QUOTA",
          f"a real quota stop was filed as {rec.get('code')!r}")
    check("B.fresh", h.fresh,
          "the primary ranking was not refreshed before the quota stop")
    check("B.green", rc == 0, f"a self-resolving stop must exit 0, not {rc}")

    # ---------------------------------------------------------------- C
    # No new domain at all: the stage does its one job and reports OK.
    h = Harness("", domains={})
    rc, rec = h.run()
    check("C.ok", rc == 0 and not rec,
          f"with nothing to gate the stage should exit 0 with no stop; got "
          f"rc={rc} rec={rec.get('code')!r}")
    check("C.fresh", h.fresh, "the primary ranking was not refreshed")

    # ---------------------------------------------------------------- D
    # stop_kind() itself: key absence wins over the word 'quota'.
    kind = getattr(score, "stop_kind", None) or (lambda _: "MISSING")
    check("D.key-first", kind(key_absent_banner()) == "key_absent",
          "stop_kind() classified the key-absent banner as something else")
    check("D.quota", kind("dailyLimitExceeded") == "quota",
          "stop_kind() no longer recognises a quota error")
    check("D.none", kind("16 topic(s) survived the gate") is None,
          "stop_kind() saw a stop in ordinary output")

    # ---------------------------------------------------------------- E
    # missing_queues() means NEVER SCORED, not EXHAUSTED. Every live domain
    # in the real repo has a scored file, so with the real files on disk the
    # answer must be empty - deep sea's 16 uploaded topics are not a missing
    # queue. (If a domain is ever promoted with no file, this case will
    # correctly turn non-empty, and the gate is what scores it.)
    import domains as dom  # noqa: PLC0415
    from common import config  # noqa: PLC0415
    scored = dom.queue_depth(include_published=True)
    allocated = list(dom.allocation(config()))
    check("E.examined", bool(allocated), "no allocated domains to examine")
    missing = score.missing_queues()
    should_be_missing = {d for d in allocated if scored.get(d, 0) == 0}
    check("E.never-scored-only", set(missing) == should_be_missing,
          f"missing_queues() returned {sorted(missing)} but the domains "
          f"with no scored file are {sorted(should_be_missing)} (scored "
          f"depth incl. published: {scored})")

    # ---------------------------------------------------------------- F
    # Both new codes are classified as the owner's, so
    # test_every_stop_is_classified.py and the digest see them.
    policy = json.load(open(LOOP / "stop_policy.json"))
    owner = policy.get("owner_action") or {}
    for code in ("NEW_DOMAIN_KEY_ABSENT", "SCORER_KEY_ABSENT"):
        check(f"F.{code}", code in owner,
              f"{code} is not classified under owner_action")

    if examined == 0:
        print("FAIL: examined zero cases")
        return 1
    print(f"inspected {examined} score-ordering case(s)")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("all green - the weekly scorer refreshes the ranking before anything can stop it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
