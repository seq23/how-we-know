"""One unwritten queue row must never cost the night its Shorts.

WHAT HAPPENED. 2026-09-25, commit a107efd (loop W39 weekly-score) wrote
research/publish_order_materials_and_manufacturing.json with 24 topics that
had no scripts/<slug>.md yet - the Monday lane's to write, exactly as the
queue is designed to hold them. From the next night, every Mac batch
(bin/batch-session.sh, 23:00) crashed in loop/captions_build.py: it read
the WHOLE queue, `buildable()` sorted it, and the first unwritten slug
(`does-damascus-steel-rust` - first alphabetically, nothing else special
about it) reached `visuals/captions.py:load_plan`, which handed a script
path that did not exist to `planner.plan()`, whose `open()` raised
FileNotFoundError. `timing_source()` caught only SystemExit. The script's
captions case then did `exit "$CAPRC"` BEFORE `shelve_shorts`, so no Short
reached R2 for a week; the cloud lane "publish a Short from R2" named
NO_SHORTS_SHELVED seven days running and went red on 30 Sep.

Three defects, one guard each:

  1. THE QUEUE SAYS WHOSE ROW A SLUG IS. loop/batch_queue.py:written_entries
     is the counterpart of unwritten_entries(): written rows are the Mac's,
     unwritten rows are Monday's, and every queued row is exactly one or the
     other (or held). loop/captions_build.py reads written_slugs(), so an
     unwritten topic is never examined for a caption gap.
  2. A MISSING SCRIPT IS A VERDICT ABOUT ONE SLUG, NEVER A CRASH. load_plan
     names it as a SystemExit; timing_source/record_durations also catch
     FileNotFoundError, because the planner does its own open() calls.
  3. shelve_shorts RUNS EVEN WHEN captions_build FAILS. The failure branch
     no longer exits; the heartbeat records ok=0 and the script exits with
     CAPRC at the very end, after Shorts, harvest and report.

Negative proof (recorded in the PR that introduced this): with the three
changes reverted, section 1 fails on AttributeError (no written_slugs),
section 2 fails with FileNotFoundError, and section 3 fails on the `exit`
inside the captions case. With only defect 2 fixed, section 2's run() check
still fails: the unwritten slug is named in CAPTIONS_UNBUILDABLE, which is
defect 1 wearing a green stop.

Hard-fails if it examines zero items. Never writes committed state: stops go
to a temp LOOP_STOPS_DIR and the fixture queue lives in a temp ROOT.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "voice"))

os.environ["LOOP_DRY_RUN"] = "1"
os.environ.setdefault("LOOP_STOPS_DIR",
                      tempfile.mkdtemp(prefix="shorts-survive-stops-"))

import batch_queue                                         # noqa: E402
import captions_build                                      # noqa: E402

fails: list[str] = []
examined = 0

WRITTEN = "zz-fixture-written-topic"
UNWRITTEN = "zz-fixture-unwritten-topic"
GHOST = "zz-fixture-no-such-episode"

# ------------------------------------------------ 1. the queue, on a fixture
TMP = Path(tempfile.mkdtemp(prefix="shorts-survive-queue-"))
(TMP / "research").mkdir()
(TMP / "scripts").mkdir()
(TMP / "research" / "publish_order_fixture.json").write_text(json.dumps({
    "domain": "fixture-domain",
    "queue": [
        {"slug": WRITTEN, "domain": "fixture-domain",
         "query": "how does a written fixture topic reach the mac"},
        {"slug": UNWRITTEN, "domain": "fixture-domain",
         "query": "why does an unwritten fixture topic belong to monday"},
    ]}))
(TMP / "scripts" / f"{WRITTEN}.md").write_text(
    "# How does a written fixture topic reach the Mac?\n\n## Narration\n\n"
    "A written row is the Mac's.\n")

real_root, real_holds = batch_queue.ROOT, batch_queue.PROMOTION_HOLDS
batch_queue.ROOT = TMP
batch_queue.PROMOTION_HOLDS = TMP / "promotion_holds.json"   # absent: no holds
try:
    try:
        written = batch_queue.written_slugs()
    except AttributeError as e:
        fails.append(f"1: batch_queue has no written_slugs(): {e}")
        written = None
    queued = batch_queue.queued_slugs()
    unwritten = [r["slug"] for r in batch_queue.unwritten_entries()]
    examined += len(queued)
    if sorted(queued) != sorted([WRITTEN, UNWRITTEN]):
        fails.append(f"1: fixture queue read as {queued}; the fixture is wrong, "
                     f"not the code")
    if written is not None:
        if written != [WRITTEN]:
            fails.append(f"1: written_slugs() = {written}, wanted [{WRITTEN!r}]")
        if unwritten != [UNWRITTEN]:
            fails.append(f"1: unwritten_entries() = {unwritten}, wanted "
                         f"[{UNWRITTEN!r}]")
        if sorted(written + unwritten) != sorted(queued):
            fails.append("1: written + unwritten != queued; a queued row must "
                         "be exactly one or the other")

    # ---------------------------------- 2. the captions lane, on that queue
    # The written fixture row has a script in the FIXTURE root only, so to
    # visuals/captions.py it is unplannable (no plans/, no scripts/): the
    # verdict must be a CANNOT BUILD line and a named stop, not a traceback.
    try:
        src, measured, total = captions_build.timing_source(GHOST)
        examined += 1
        if not src.startswith("unplannable"):
            fails.append(f"2: timing_source({GHOST!r}) = {src!r}; wanted an "
                         f"'unplannable: ...' verdict")
        if (measured, total) != (0, 0):
            fails.append(f"2: timing_source({GHOST!r}) measured {measured}/"
                         f"{total}; a missing script measures nothing")
    except FileNotFoundError as e:
        fails.append(f"2: timing_source({GHOST!r}) raised FileNotFoundError "
                     f"({e}) - one missing script crashes the whole stage")

    try:
        can, cannot = captions_build.buildable([GHOST])
        examined += 1
        if can or [s for s, _ in cannot] != [GHOST]:
            fails.append(f"2: buildable([{GHOST!r}]) = ({can}, {cannot}); "
                         f"wanted ([], [({GHOST!r}, why)])")
    except FileNotFoundError as e:
        fails.append(f"2: buildable([{GHOST!r}]) raised FileNotFoundError: {e}")

    try:
        if captions_build.record_durations([GHOST], note=lambda *_: None):
            fails.append(f"2: record_durations([{GHOST!r}]) claimed to record "
                         f"timing for a script that does not exist")
        examined += 1
    except FileNotFoundError as e:
        fails.append(f"2: record_durations([{GHOST!r}]) raised "
                     f"FileNotFoundError: {e}")

    # run() with no explicit slugs reads the fixture queue. Before the fix it
    # read BOTH rows and crashed on the unwritten one; with only the catch
    # fixed it names the unwritten row in CAPTIONS_UNBUILDABLE. Correct is:
    # exit 3, the stop names the written row only.
    stops = Path(os.environ["LOOP_STOPS_DIR"])
    before = {p.name for p in stops.glob("*.json")}
    try:
        rc = captions_build.run(dry_run=True)
        fails.append(f"2: run(dry_run=True) returned {rc} with a queue whose "
                     f"only written row is unplannable; wanted the "
                     f"CAPTIONS_UNBUILDABLE named stop (exit 3)")
    except FileNotFoundError as e:
        fails.append(f"2: run(dry_run=True) raised FileNotFoundError ({e}): "
                     f"the lane read an unwritten queue row")
    except SystemExit as e:
        examined += 1
        if e.code != 3:
            fails.append(f"2: run(dry_run=True) exited {e.code}, wanted 3 "
                         f"(a named stop)")
        new = [stops / n for n in {p.name for p in stops.glob("*.json")} - before]
        docs = [json.loads(p.read_text()) for p in new]
        text = json.dumps(docs)
        if "CAPTIONS_UNBUILDABLE" not in text:
            fails.append(f"2: the stop written was not CAPTIONS_UNBUILDABLE: "
                         f"{text[:300]}")
        if WRITTEN not in text:
            fails.append(f"2: the stop does not name the written row {WRITTEN!r}")
        if UNWRITTEN in text:
            fails.append(f"2: the stop names the UNWRITTEN row {UNWRITTEN!r}: "
                         f"the lane still examines Monday's topics")
finally:
    batch_queue.ROOT, batch_queue.PROMOTION_HOLDS = real_root, real_holds

# ----------------------------------------- 1b. the live queue, same rule
live_written = batch_queue.written_slugs() if hasattr(batch_queue, "written_slugs") else []
live_unwritten = [r["slug"] for r in batch_queue.unwritten_entries()]
live_held = set(batch_queue.promotion_holds())
live_queued = batch_queue.queued_slugs()
examined += len(live_queued)
if not live_written:
    fails.append("1b: the live queue has no written row at all - this guard "
                 "examined nothing the Mac could narrate")
for s in live_written:
    if not (ROOT / "scripts" / f"{s}.md").exists():
        fails.append(f"1b: written_slugs() names {s!r}, which has no script")
uncovered = [s for s in live_queued
             if s not in live_written and s not in live_unwritten
             and s not in live_held]
if uncovered:
    fails.append(f"1b: queued rows that are neither written, unwritten nor "
                 f"held: {uncovered}")

# ---------------------------------- 3. the batch script keeps its Shorts
batch = (ROOT / "bin" / "batch-session.sh").read_text()
call_at = batch.find("$PY loop/captions_build.py\n")
if call_at < 0:
    fails.append("3: bin/batch-session.sh no longer runs loop/captions_build.py")
else:
    examined += 1
    case_at = batch.find("case $CAPRC in", call_at)
    esac_at = batch.find("\nesac\n", case_at)
    if case_at < 0 or esac_at < 0:
        fails.append("3: the captions result is no longer handled in a "
                     "`case $CAPRC in ... esac` block")
    else:
        block = batch[case_at:esac_at]
        if re.search(r"\bexit\b", block):
            fails.append("3: the captions case block exits the script - the "
                         "Shorts of every other episode die with one caption "
                         "failure")
    shelve_calls = [m.start() for m in
                    re.finditer(r"^\s*shelve_shorts\s*$", batch, re.M)]
    after = [c for c in shelve_calls if c > call_at]
    if not after:
        fails.append("3: no shelve_shorts invocation after captions_build")
    else:
        tail = batch[max(after):]
        if not re.search(r'^\s*exit "\$CAPRC"\s*$', tail, re.M):
            fails.append("3: the script never exits with $CAPRC after "
                         "shelve_shorts - a captions failure is now silent")
        if not re.search(r"^\s*harvest_footage\s*$", tail, re.M):
            fails.append("3: harvest_footage no longer runs after the Shorts "
                         "on the narrate-or-render path")
    if re.search(r"heartbeat --lane batch --ok 1\b", batch):
        fails.append("3: the batch heartbeat hardcodes --ok 1; a captions "
                     "failure would report as a clean night")

# ------------------------------------------------------------------ verdict
if examined == 0:
    print("FAIL: examined zero items")
    raise SystemExit(1)
if fails:
    print(f"FAIL ({len(fails)}):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print(f"ok: shorts lane survives a missing script "
      f"({examined} items examined; {len(live_written)} written / "
      f"{len(live_unwritten)} unwritten / {len(live_held)} held in the live queue)")
