"""The owner's long-form hold (2 Nov 2026), proven negatively.

  1. hold-longform halts EVERY long-form lane with OWNER_HOLD_LONGFORM, green
     (exit 0: her own decision never pages her), and lets every Shorts lane
     through; lift-longform lets the long-form lanes through again.
  2. owner_hold.candidates takes only scheduled, future, non-public rows whose
     render has no footage; never a public, aired or footage-bearing one.
  3. a withdrawn row leaves `published` and is queued again by batch_queue.
  4. the weekly digest shows the hold as one line with no action for her, and
     the hold's own empty calendar is not reported as a red gap.

Hard-fails on zero stages examined.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import breaker  # noqa: E402
import quota  # noqa: E402

PY = sys.executable
_STOPS = os.environ.get("LOOP_STOPS_DIR") or tempfile.mkdtemp(prefix="hold-stops-")
_FLAG = os.environ.get("LOOP_BREAKER_FLAG") or os.path.join(
    tempfile.mkdtemp(prefix="hold-flag-"), "breaker.json")
SHORTS = ("shorts", "shorts-cloud")


def run(*args):
    return subprocess.run([PY, os.path.join(LOOP, "breaker.py"), *args],
                          capture_output=True, text=True, cwd=ROOT,
                          env=dict(os.environ, LOOP_STOPS_DIR=_STOPS,
                                   LOOP_BREAKER_FLAG=_FLAG))


def check_hold() -> tuple[list[str], int]:
    fails, n = [], 0
    backup = _FLAG + ".bak"
    if os.path.exists(_FLAG):
        shutil.copy(_FLAG, backup)
    try:
        run("reset", "--note", "test baseline")
        run("hold-longform", "--detail", "TEST hold")
        for stage in breaker.LONGFORM_STAGES:
            n += 1
            r = run("guard", "--stage", stage)
            out = r.stdout + r.stderr
            if "may proceed" in out or "OWNER_HOLD_LONGFORM" not in out:
                fails.append(f"held long-form lane {stage} was not stopped")
            if r.returncode != 0:
                fails.append(f"{stage} exited {r.returncode} on her own hold; "
                             f"it must be green and never page her")
        for stage in SHORTS:
            n += 1
            if "may proceed" not in run("guard", "--stage", stage).stdout:
                fails.append(f"the long-form hold stopped Shorts lane {stage}")
        run("lift-longform", "--note", "TEST lift")
        for stage in breaker.LONGFORM_STAGES:
            n += 1
            if "may proceed" not in run("guard", "--stage", stage).stdout:
                fails.append(f"{stage} still held after lift-longform")
    finally:
        if os.path.exists(backup):
            shutil.move(backup, _FLAG)
    missing = set(quota.LONGFORM_LANES) - set(breaker.LONGFORM_STAGES)
    if missing:
        fails.append(f"long-form upload lanes not covered by the hold: {missing}")
    return fails, n


def check_candidates() -> tuple[list[str], int]:
    import owner_hold as OH
    at = datetime(2026, 11, 2, tzinfo=timezone.utc)
    fut, past = "2026-11-20T16:00:00Z", "2026-10-20T16:00:00Z"
    rows = [
        {"slug": "a-no-footage", "video_id": "A", "scheduled_publish_at": fut},
        {"slug": "b-no-record", "video_id": "B", "scheduled_publish_at": fut},
        {"slug": "c-has-footage", "video_id": "C", "scheduled_publish_at": fut},
        {"slug": "d-aired", "video_id": "D", "scheduled_publish_at": past},
        {"slug": "e-public", "video_id": "E", "scheduled_publish_at": fut,
         "privacy": "public"},
        {"slug": "f-retired", "video_id": "F", "scheduled_publish_at": fut,
         "retired_at": "x"},
    ]
    foot = {"a-no-footage": 0, "b-no-record": None, "c-has-footage": 12,
            "d-aired": 0, "e-public": 0, "f-retired": 0}
    got = [r["slug"] for r in OH.candidates({"published": rows}, at, foot.get)]
    fails = []
    if got != ["a-no-footage", "b-no-record"]:
        fails.append(f"candidates took {got}; want only the two scheduled, "
                     f"unaired, non-public renders with no footage")
    led = {"published": [{"slug": "a-no-footage", "video_id": "OLD", "retired_at": "x"},
                         *[dict(r) for r in rows]]}
    OH.withdraw(led, "A", fut)
    w = next(r for r in led["published"] if r["video_id"] == "A")
    old = led["published"][0]
    if old.get("withdrawn_at"):
        fails.append("withdraw marked an older duplicate row of the same slug, not the video it unscheduled")
    if not (w.get("withdrawn_at") and w.get("retired_at")) or w.get("schedule_was") != fut \
            or "scheduled_publish_at" in w:
        fails.append(f"withdrawn row not retired+withdrawn with its old date kept: {w}")
    return fails, 2


def check_requeue() -> tuple[list[str], int]:
    import batch_queue
    import ledger
    real = ledger.load
    slug = sorted(p[:-3] for p in os.listdir(os.path.join(ROOT, "scripts"))
                  if p.endswith(".md"))[0]
    fake = {"published": [{"slug": slug, "question": "zz test",
                           "video_id": "Z", "retired_at": "x", "withdrawn_at": "x"}],
            "queued": [], "updated": None}
    ledger.load = lambda: fake
    try:
        q = batch_queue.queued_slugs()
    finally:
        ledger.load = real
    fails = [] if q and q[0] == slug else [
        f"a withdrawn episode is not queued first for re-render (queue head {q[:2]})"]
    return fails, 1


def check_digest() -> tuple[list[str], int]:
    import digest
    today = date(2026, 11, 2)
    cal = [{"date": today + timedelta(days=i), "slug": None, "days_away": i,
            "domain": "deep-sea-ocean-science"} for i in range(1, 6)]
    br = {"state": "closed", "longform_hold": {"on": True, "since": "2026-11-02T21:00:00+00:00",
                                               "detail": "until hostile-review fixes land"}}
    try:
        emoji, subject, lines = digest.verdict([], cal, {}, [], breaker_state=br)
    except TypeError as e:
        return [f"digest.verdict signature changed: {e}"], 1
    text = " | ".join(lines) + " | " + subject
    fails = []
    if "held on purpose" not in text:
        fails.append("the weekly digest does not show the long-form hold")
    if "Episode calendar has gaps" in text:
        fails.append("the hold's own empty calendar is reported as a red gap")
    if "needs you" in subject and "held" in subject:
        fails.append("the hold pages her in the digest subject")
    return fails, 1


def check_cancel_readback() -> tuple[list[str], int]:
    """cancel_schedule must wait out YouTube's stale read-back (2 Nov 2026:
    X2_UfcYnXwc read its old publishAt right after an applied round trip)."""
    import publish as P
    reads = iter([{"privacy": "private", "publishAt": "2026-11-20T16:00:00Z"},
                  {"privacy": "private", "publishAt": "2026-11-20T16:00:00Z"},
                  {"privacy": "private", "publishAt": None}])
    saved = (P.read_status_full, P.set_privacy, P._sleep)
    P.read_status_full = lambda t, v: next(reads)
    P.set_privacy = lambda *a, **k: None
    P._sleep = lambda s: None
    try:
        got = P.cancel_schedule("tok", "VID")
        fails = [] if got == "2026-11-20T16:00:00Z" else [f"cancel_schedule returned {got!r}"]
    except RuntimeError as e:
        fails = [f"cancel_schedule failed on a stale read-back: {e}"]
    finally:
        P.read_status_full, P.set_privacy, P._sleep = saved
    return fails, 1


def main() -> int:
    fails, n = [], 0
    for fn in (check_hold, check_candidates, check_requeue, check_digest,
               check_cancel_readback):
        f, k = fn()
        fails += f
        n += k
    if n == 0:
        print("FAIL: examined nothing")
        return 1
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: owner long-form hold ({n} checks)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
