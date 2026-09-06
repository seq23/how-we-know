"""The upload lane's planner and its title map must read ONE list.

WHAT BROKE. `loop/cloud_upload.py` built its slug -> question map from
`research/publish_order.json` BY NAME, while `backfill.library_pending`
selects from `batch_queue.queued_entries()`, which globs
`research/publish_order*.json`. While the channel published one domain the two
were the same 16 rows and nothing showed. The moment
`research/publish_order_materials.json` appeared they diverged - 34 selectable
against 16 titled - and run 34038288267 pulled 50,982,483 verified bytes of
`how-is-a-silicon-wafer-made` out of R2 and died on `questions[slug]` with a
bare `KeyError`, after the download and before the upload. Every materials
episode was unreachable by that lane.

WHY IT WAS NOT CAUGHT. `loop/tests/test_cloud_upload.py:_pick_slug()` chooses
its subject from `research/publish_order.json` - the SAME single file the
defect lived in - so the harness could only ever pick a slug that was in both
lists. The one case that fails is the one case the test could not select.

WHAT THIS ASSERTS, and it is the join rather than the filename:

  1. every slug `library_pending` may select has a question in the lane's map
  2. no queue row is untitled (a `query` that is missing or empty)
  3. the map is built from EVERY publish-order file, proven by adding a new
     domain file at runtime and watching the map grow - a lane that had gone
     back to reading one file by name would not move

Hard-fails when it examines zero slugs, zero queue files, or when the
"add a domain" probe finds nothing to add.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable

sys.path.insert(0, LOOP)


def check() -> list[str]:
    import batch_queue                                     # noqa: PLC0415
    import cloud_upload                                    # noqa: PLC0415

    fails: list[str] = []

    files = batch_queue.publish_order_files()
    if not files:
        return ["examined ZERO publish-order files - research/ is missing or "
                "renamed, and an empty queue is indistinguishable from a "
                "finished one"]

    selectable = batch_queue.queued_slugs()
    questions = cloud_upload.questions_map()
    if not selectable:
        return ["examined ZERO queued slugs - the publish queue is empty, so "
                "this guard proved nothing"]
    if not questions:
        return ["cloud_upload.questions_map() returned NOTHING while "
                f"{len(selectable)} slug(s) are selectable"]

    # -- 1 & 2. the join, per slug --------------------------------------
    examined = 0
    for slug in selectable:
        examined += 1
        if slug not in questions:
            fails.append(
                f"{slug} can be SELECTED for upload by "
                f"backfill.library_pending but has no entry in "
                f"cloud_upload.questions_map() - this is the KeyError from run "
                f"34038288267")
        elif not questions[slug]:
            fails.append(f"{slug} is queued with no `query`, so the lane "
                         f"cannot title its video")

    # -- 3. the map really does read every domain file ------------------
    # BEHAVIOURAL, not a grep. A lane that had reverted to naming one file
    # would still import batch_queue and still pass a source check; it would
    # not see a domain file that did not exist when it was written.
    probe = os.path.join(ROOT, "research", "publish_order_zzguardprobe.json")
    if os.path.exists(probe):
        fails.append(f"{probe} already exists - refusing to overwrite it")
    else:
        payload = {"queue": [{"slug": "zz-guard-probe-episode",
                              "query": "zz guard probe episode",
                              "domain": "zz-guard-probe"}]}
        try:
            with open(probe, "w") as fh:
                json.dump(payload, fh)
            r = subprocess.run(
                [PY, "-c",
                 "import sys; sys.path.insert(0, %r);"
                 "import cloud_upload;"
                 "print('yes' if 'zz-guard-probe-episode' in "
                 "cloud_upload.questions_map() else 'no')" % LOOP],
                capture_output=True, text=True, cwd=ROOT)
            saw = (r.stdout or "").strip().splitlines()[-1:] or [""]
            if saw[0] != "yes":
                fails.append(
                    "a new research/publish_order_*.json file did NOT appear "
                    "in cloud_upload.questions_map() - the lane is reading one "
                    "queue file by name again, which is the exact defect this "
                    f"guard exists for (stdout={r.stdout!r} stderr="
                    f"{r.stderr[-300:]!r})")
        finally:
            if os.path.exists(probe):
                os.unlink(probe)

    # -- the zero-item hard fail, proven ---------------------------------
    # Point the SAME map builder at a research/ directory holding one EMPTY
    # queue file. It must come back empty, and this guard must call that a
    # failure rather than an easy pass.
    tmp = tempfile.mkdtemp(prefix="hwk-empty-queue-")
    try:
        os.makedirs(os.path.join(tmp, "research"))
        with open(os.path.join(tmp, "research", "publish_order.json"), "w") as fh:
            json.dump({"queue": []}, fh)
        r = subprocess.run(
            [PY, "-c",
             "import sys, pathlib; sys.path.insert(0, %r);"
             "import batch_queue; batch_queue.ROOT = pathlib.Path(%r);"
             "import cloud_upload;"
             "print('EMPTY' if not cloud_upload.questions_map() else 'NONEMPTY')"
             % (LOOP, tmp)],
            capture_output=True, text=True, cwd=ROOT)
        if "EMPTY" not in (r.stdout or ""):
            fails.append(
                "pointed at an EMPTY publish queue, questions_map() did not "
                f"come back empty - this guard cannot tell zero from many "
                f"(stdout={r.stdout!r} stderr={r.stderr[-300:]!r})")

        # ...and with NO queue file at all it must RAISE, never return {}.
        os.unlink(os.path.join(tmp, "research", "publish_order.json"))
        r = subprocess.run(
            [PY, "-c",
             "import sys, pathlib; sys.path.insert(0, %r);"
             "import batch_queue; batch_queue.ROOT = pathlib.Path(%r);"
             "import cloud_upload;"
             "\ntry:\n cloud_upload.questions_map()\n print('RETURNED')\n"
             "except batch_queue.NoPublishOrder:\n print('RAISED')"
             % (LOOP, tmp)],
            capture_output=True, text=True, cwd=ROOT)
        if "RAISED" not in (r.stdout or ""):
            fails.append(
                "with NO research/publish_order*.json at all, questions_map() "
                "did not raise NoPublishOrder - a queue that cannot be read "
                f"would look like a finished one (stdout={r.stdout!r} "
                f"stderr={r.stderr[-300:]!r})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if examined == 0:
        fails.append("examined ZERO slugs")
    print(f"inspected {examined} queued slug(s) across {len(files)} "
          f"publish-order file(s); {len(questions)} titled")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the upload planner and its title map read one list"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
