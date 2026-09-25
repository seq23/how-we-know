"""One exhausted domain's stop must not skip another's turn.

Confirmed 2026-09-25: deep-sea-ocean-science and materials-and-manufacturing
were BOTH fully exhausted (every queued topic already published, `queue_depth`
correctly excludes anything aired). The Saturday scorer reached deep-sea,
hit a quota stop, and `st.named_stop()` raised — `Stage.__exit__` turned that
into `sys.exit` for the WHOLE stage, so materials-and-manufacturing, in
exactly the same state, was silently never even attempted. Every week, for as
long as deep-sea's own quota-constrained refill took to clear, the second
domain got zero chance to refill either — the channel went completely dark on
new topics rather than half-dark.

Rule 0: hard-fails if the stage records no stop at all, or the stub sees
fewer than two `publish_order_domain.py` calls, because a test where the
second domain was never even invoked has proved nothing about the fix.
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

SCRATCH = Path(tempfile.mkdtemp(prefix="score-multidomain-"))
os.environ["LOOP_STOPS_DIR"] = str(SCRATCH / "stops")
(SCRATCH / "stops").mkdir()

sys.path.insert(0, str(LOOP))
import cadence  # noqa: E402
import common   # noqa: E402
import score    # noqa: E402


def check() -> list[str]:
    fails, examined = [], 0

    calls: list[str] = []

    # deep-sea fails on quota, materials-and-manufacturing succeeds. The
    # ORDER in the dict matters: deep-sea first, so a loop that aborts on the
    # first stop would never reach the second at all.
    #
    # UNDER ROOT, NOT SCRATCH: score_new_domains() logs a successful path via
    # path.relative_to(ROOT), which is about the real repo layout, not this
    # test's fixture - a path outside it is a test bug, not a bug in the fix.
    scratch_under_root = ROOT / "research" / ".test-scratch-multidomain"
    scratch_under_root.mkdir(exist_ok=True)
    dom_paths = {
        "deep-sea-ocean-science": scratch_under_root / "publish_order_deep-sea.json",
        "materials-and-manufacturing": scratch_under_root / "publish_order_materials.json",
    }

    def fake_run(cmd, **kw):
        target = Path(str(cmd[1])).name
        if "--query" in cmd:
            raise AssertionError(f"a held script was gated with no hold on "
                                 f"file: {cmd}")
        if target == "publish_order_domain.py":
            dom = cmd[cmd.index("--domain") + 1]
            calls.append(f"publish_order_domain.py:{dom}")
            if dom == "deep-sea-ocean-science":
                return SimpleNamespace(
                    returncode=1,
                    stdout="NAMED STOP NEW_DOMAIN_QUOTA\nquotaExceeded\n",
                    stderr="")
            # materials-and-manufacturing: a real success, and it must
            # actually be attempted for this branch to ever run.
            dom_paths[dom].write_text("{}")
            return SimpleNamespace(returncode=0, stdout="scored", stderr="")
        if target == score.entrypoint().name:
            calls.append("publish_order.py")
            return SimpleNamespace(returncode=0, stdout="ranked", stderr="")
        raise AssertionError(f"unexpected subprocess: {cmd}")

    # NO HOLDS. main() also runs dispose_promotion_holds() (2026-09-25),
    # which reads loop/promotion_holds.json and, through the same
    # subprocess.run, gates every held script. Left at the real register
    # this test's quota-shaped stub would DEFER every real hold (writing
    # gate_deferred counters into the real file) and promote any hold whose
    # slug is already queued (writing a real scripts/<slug>.md) - which is
    # exactly what happened the first time it ran. An empty scratch register
    # keeps the subject of this test the domains, and the assertion on
    # `calls` below now also proves no hold sneaks a gate call in.
    empty_holds = SCRATCH / "promotion_holds.json"
    empty_holds.write_text('{"holds": []}')
    saved = (score.subprocess.run, score.missing_queues, score.HOLDS_PATH)
    score.subprocess.run = fake_run
    score.missing_queues = lambda: dict(dom_paths)
    score.HOLDS_PATH = empty_holds
    exit_code = None
    try:
        try:
            score.main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    finally:
        score.subprocess.run, score.missing_queues, score.HOLDS_PATH = saved

    # -- Rule 0 -------------------------------------------------------------
    examined += 1
    if not calls:
        fails.append("the stage invoked NOTHING - the stub saw zero calls")
        return fails

    # -- both domains were attempted -----------------------------------------
    examined += 1
    gate_calls = [c for c in calls if c.startswith("publish_order_domain.py:")]
    if len(gate_calls) != 2:
        fails.append(
            f"expected the gate invoked for BOTH domains, got {gate_calls!r} "
            f"- the first domain's stop is still ending the run before the "
            f"second domain's turn")

    # -- the one that succeeded actually wrote its queue ---------------------
    examined += 1
    if not dom_paths["materials-and-manufacturing"].exists():
        fails.append(
            "materials-and-manufacturing never got its queue written, even "
            "though its gate call was stubbed to succeed - it was not "
            "reached")

    # -- the run still names the domain that failed, and exits non-zero -----
    examined += 1
    stops = sorted((SCRATCH / "stops").glob("*weekly-score*.json"))
    if not stops:
        fails.append("the failing domain's stop vanished; it must still be "
                      "named even though the run also did real work")
        return fails
    import json  # noqa: PLC0415
    rec = json.loads(stops[-1].read_text())
    if "deep-sea-ocean-science" not in (rec.get("message") or ""):
        fails.append(f"the recorded stop does not name deep-sea-ocean-science: "
                     f"{rec.get('message')!r}")
    examined += 1
    if exit_code != 0:
        fails.append(f"NEW_DOMAIN_QUOTA is self-resolving and must exit 0 "
                     f"(pages nobody, retries next Saturday), same as before "
                     f"this fix; got {exit_code}")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} multi-domain case(s); stage calls: {calls}")
    return fails


if __name__ == "__main__":
    import shutil  # noqa: PLC0415
    try:
        f = check()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        shutil.rmtree(ROOT / "research" / ".test-scratch-multidomain",
                     ignore_errors=True)
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every domain missing a queue gets a turn, even after "
          "an earlier one's stop" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
