"""The Saturday scorer refreshes the primary ranking BEFORE anything can stop it.

Run 35230863447 (2026-09-17): `loop · tests` went red on validate_plan check 4
- research/publish_order.json twelve days old, past the ten-day threshold.
Nothing was wrong with the ranking. The weekly-score lane had run green on
09-12 and stopped - self-resolving, "retries next Saturday" - on a missing
YouTube key while gating a NEW domain, and that stop was raised BEFORE the
lane ever invoked research/publish_order.py. Two Saturdays of green, and the
one file every publishing lane reads had not been touched since 09-05.

Two defects, both pinned here by running the real stage against stubbed
subprocesses:

  1. ORDER. The primary scorer must be invoked even when the new-domain gate
     stops, and it must be invoked first.
  2. LABEL. A missing key is not a quota. competition.py's key-absent stop
     says "10,000 quota units/day" in its prose, which matched QUOTA_MARKERS
     and dressed an owner_action state as self_resolving. It must come out as
     NEW_DOMAIN_KEY_ABSENT and stay green as owner_action - not page her, not
     pretend time will fix it.

Rule 0: hard-fails if the stage records no stop at all or the stub sees no
calls, because a test that examined nothing has proved nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

# Redirect every stop-side write BEFORE common is imported, so the real
# Stage.__exit__ lands in a scratch directory and never in loop/state.
SCRATCH = Path(tempfile.mkdtemp(prefix="score-order-"))
os.environ["LOOP_STOPS_DIR"] = str(SCRATCH / "stops")
(SCRATCH / "stops").mkdir()

sys.path.insert(0, str(LOOP))
import cadence  # noqa: E402
import score    # noqa: E402

# The exact prose research/competition.py prints when the key is absent. The
# word "quota" is in it; that is the trap.
KEY_ABSENT_TEXT = (
    "  NAMED STOP  YOUTUBE_API_KEY_ABSENT\n"
    "  who_must_supply_it: The owner. Free tier, 10,000 quota units/day, no "
    "card required.\n"
    "Stop recorded at research/competition_stop.json. No score was written, "
    "because no score was measured.\n"
    "Exit 0: this is a declared stop, not a failure.\n")


def check() -> list[str]:
    fails, examined = [], 0

    # A private copy of the ranking, ELEVEN days old - stale by the config's
    # threshold - so a run that never refreshes it is caught by the stage's
    # own RANKING_STALE_AFTER_SCORING, not only by this test.
    real = cadence.PUBLISH_ORDER
    raw = json.loads(real.read_text())
    stale_at = (dt.datetime.now(dt.timezone.utc)
                - dt.timedelta(days=11)).isoformat()
    raw["generated_at"] = stale_at
    tmp_order = SCRATCH / "publish_order.json"
    tmp_order.write_text(json.dumps(raw))

    calls: list[str] = []

    def fake_run(cmd, **kw):
        target = Path(str(cmd[1])).name
        calls.append(target)
        if target == "publish_order_domain.py":
            return SimpleNamespace(returncode=0, stdout=KEY_ABSENT_TEXT,
                                   stderr="")
        if target == score.entrypoint().name:
            fresh = json.loads(tmp_order.read_text())
            fresh["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            tmp_order.write_text(json.dumps(fresh))
            return SimpleNamespace(returncode=0, stdout="ranked", stderr="")
        raise AssertionError(f"unexpected subprocess: {cmd}")

    saved = (score.subprocess.run, score.missing_queues, cadence.PUBLISH_ORDER)
    score.subprocess.run = fake_run
    score.missing_queues = lambda: {
        "deep-sea-ocean-science": SCRATCH / "publish_order_deep-sea.json"}
    cadence.PUBLISH_ORDER = tmp_order
    exit_code = None
    try:
        try:
            score.main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    finally:
        score.subprocess.run, score.missing_queues, cadence.PUBLISH_ORDER = saved

    # -- Rule 0 -----------------------------------------------------------
    examined += 1
    if not calls:
        fails.append("the stage invoked NOTHING - the stub saw zero calls")
        return fails

    # -- 1. order ---------------------------------------------------------
    examined += 1
    ep = score.entrypoint().name
    if ep not in calls:
        fails.append(f"{ep} was never invoked - the new-domain stop cost the "
                     f"channel its weekly ranking refresh (the 09-05..09-17 "
                     f"defect)")
    elif "publish_order_domain.py" in calls and \
            calls.index(ep) > calls.index("publish_order_domain.py"):
        fails.append(f"{ep} ran AFTER the new-domain gate; a stop there "
                     f"would skip it")
    examined += 1
    after = json.loads(tmp_order.read_text())
    if after.get("generated_at") == stale_at:
        fails.append("the ranking's generated_at was not refreshed")

    # -- 2. label ---------------------------------------------------------
    examined += 1
    stops = sorted((SCRATCH / "stops").glob("*weekly-score*.json"))
    if not stops:
        fails.append("the stage recorded no stop; the key-absent gate must "
                     "surface as a NAMED stop, not vanish")
        return fails
    rec = json.loads(stops[-1].read_text())
    if rec.get("code") == "NEW_DOMAIN_QUOTA":
        fails.append("a missing YouTube key was recorded as NEW_DOMAIN_QUOTA "
                     "- 'retries next Saturday' on a state time cannot fix")
    elif rec.get("code") != "NEW_DOMAIN_KEY_ABSENT":
        fails.append(f"expected NEW_DOMAIN_KEY_ABSENT, got {rec.get('code')!r}")
    examined += 1
    if rec.get("disposition") != "owner_action":
        fails.append(f"NEW_DOMAIN_KEY_ABSENT dispositioned as "
                     f"{rec.get('disposition')!r}; only she can mint the key, "
                     f"so it must be owner_action - green, in the digest")
    if exit_code != 0:
        fails.append(f"the stage exited {exit_code}; an owner_action stop "
                     f"must exit 0 and not page her")
    examined += 1
    done = " ".join(rec.get("work_done_before_stop") or [])
    if "ranking is fresh" not in done:
        fails.append("the stop record does not carry the ranking refresh in "
                     "work_done_before_stop - the work happened but the "
                     "record would say the lane did nothing")

    # -- the trap itself, pinned ------------------------------------------
    examined += 1
    if not score.QUOTA_MARKERS.search(KEY_ABSENT_TEXT):
        fails.append("QUOTA_MARKERS no longer matches the key-absent prose; "
                     "if competition.py changed its text, update "
                     "KEY_ABSENT_TEXT here so this test still exercises the "
                     "real collision")
    key_rx = getattr(score, "KEY_ABSENT_MARKERS", None)
    if key_rx is None or not key_rx.search(KEY_ABSENT_TEXT):
        fails.append("score.KEY_ABSENT_MARKERS is missing or does not "
                     "recognise competition.py's key-absent stop")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} scorer-ordering case(s); stage calls: {calls}")
    return fails


if __name__ == "__main__":
    try:
        f = check()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the weekly scorer refreshes the ranking before any "
          "stop can reach it" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
