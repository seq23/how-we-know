"""A real unhandled exception must never be misread as a self-resolving quota
stop just because the word "quota" appears earlier in the same output.

Confirmed 2026-09-25, live: research/publish_order_domain.py crashed with an
unhandled `KeyError: 'median_subscribers'` on the first candidate for BOTH
allocated domains, every run. research/competition.py's own routine progress
text mentions "10,000 quota units/day" as ordinary reporting, not a problem —
but `QUOTA_MARKERS` matched it anyway, before the traceback beneath it was
ever considered, and the run was recorded self-resolving ("retries next
Saturday") for a code defect that retrying could never fix. The crash never
reached a human.

Rule 0: hard-fails if the stage records no stop, because a test that examined
nothing has proved nothing.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

SCRATCH = Path(tempfile.mkdtemp(prefix="score-traceback-"))
os.environ["LOOP_STOPS_DIR"] = str(SCRATCH / "stops")
(SCRATCH / "stops").mkdir()

sys.path.insert(0, str(LOOP))
import score  # noqa: E402

# The real shape: routine, benign quota-reporting text ABOVE a real crash.
# This is what defeated the naive ordering — QUOTA_MARKERS matched line 1
# and the traceback below it was never read.
CRASH_WITH_INCIDENTAL_QUOTA_TEXT = (
    "  [note] spent 1,240 of 10,000 quota units/day measuring competition\n"
    "Traceback (most recent call last):\n"
    '  File "research/publish_order_domain.py", line 548, in main\n'
    '    rec["reason"] = reason(rec)\n'
    '  File "research/publish_order.py", line 333, in reason\n'
    '    subs = rec["competition"]["median_subscribers"]\n'
    "KeyError: 'median_subscribers'\n"
)


def check() -> list[str]:
    fails, examined = [], 0

    def fake_run(cmd, **kw):
        target = Path(str(cmd[1])).name
        if target == "publish_order_domain.py":
            return SimpleNamespace(returncode=1,
                                   stdout=CRASH_WITH_INCIDENTAL_QUOTA_TEXT,
                                   stderr="")
        if target == score.entrypoint().name:
            return SimpleNamespace(returncode=0, stdout="ranked", stderr="")
        raise AssertionError(f"unexpected subprocess: {cmd}")

    # An empty hold register: main() also decides promotion holds through
    # the same subprocess.run (2026-09-25), and this test's subject is the
    # domain gate's traceback, not the real loop/promotion_holds.json.
    empty_holds = SCRATCH / "promotion_holds.json"
    empty_holds.write_text('{"holds": []}')
    saved = (score.subprocess.run, score.missing_queues, score.HOLDS_PATH)
    score.subprocess.run = fake_run
    score.HOLDS_PATH = empty_holds
    score.missing_queues = lambda: {
        "deep-sea-ocean-science": SCRATCH / "publish_order_deep-sea.json"}
    try:
        try:
            score.main()
        except SystemExit:
            pass
    finally:
        score.subprocess.run, score.missing_queues, score.HOLDS_PATH = saved

    # -- Rule 0 / the trap itself, pinned --------------------------------
    examined += 1
    if not score.QUOTA_MARKERS.search(CRASH_WITH_INCIDENTAL_QUOTA_TEXT):
        fails.append("QUOTA_MARKERS no longer matches the incidental quota "
                     "text this fixture relies on to exercise the real "
                     "collision - update the fixture if competition.py's "
                     "progress text changed")

    examined += 1
    if not score.TRACEBACK_MARKER.search(CRASH_WITH_INCIDENTAL_QUOTA_TEXT):
        fails.append("score.TRACEBACK_MARKER does not recognise a real "
                     "Python traceback - the priority check this test pins "
                     "cannot fire at all")

    examined += 1
    import json  # noqa: PLC0415
    stops = sorted((SCRATCH / "stops").glob("*weekly-score*.json"))
    if not stops:
        fails.append("the stage recorded no stop at all; a crash must "
                     "still be named")
        return fails
    rec = json.loads(stops[-1].read_text())
    if rec.get("code") == "NEW_DOMAIN_QUOTA":
        fails.append("a real unhandled exception was classified "
                     "NEW_DOMAIN_QUOTA - the incidental 'quota units/day' "
                     "text above the traceback outranked the traceback "
                     "itself, exactly the 2026-09-25 incident this test "
                     "pins")
    elif rec.get("code") != "NEW_DOMAIN_UNSCORED":
        fails.append(f"expected NEW_DOMAIN_UNSCORED, got {rec.get('code')!r}")

    examined += 1
    if rec.get("disposition") == "self_resolving":
        fails.append("a real crash must not be dispositioned self_resolving "
                     "- retrying next Saturday cannot fix a KeyError")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} traceback-priority case(s)")
    return fails


if __name__ == "__main__":
    import shutil  # noqa: PLC0415
    try:
        f = check()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for x in f:
        print(f"  ✗ {x}")
    print("all green - a real traceback outranks incidental quota text in "
          "the same output" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
