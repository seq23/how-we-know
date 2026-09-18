"""An idle batch night still cuts and shelves Shorts - proven, not asserted.

WHAT HAPPENED. 18 September 2026: the cloud Shorts lane stopped
NO_SHORTS_SHELVED and classified it self-resolving "on the Mac's next push".
Seven rendered materials episodes had no Short cut. There was no next push:
bin/batch-session.sh only reached bin/push-to-r2.sh at the end of a
narrate-or-render night and never ran bin/make-shorts.sh at all - every
Short on the channel had been cut by hand. The Mac had been exiting 0 with
"nothing to do" every night since 8 September while the shelf ran dry. The
"exists but nothing invokes it" class, wearing a self-resolving label.

WHAT THIS PROVES, against a planted fixture rather than the live renders:

  1. loop/shorts_lane.py:uncut names exactly the rendered episodes with no
     cut, in render order, and nothing else.
  2. A render set with nothing to examine RAISES - it is not "nothing uncut".
  3. bin/batch-session.sh defines shelve_shorts, which runs make-shorts.sh on
     the uncut set and then push-to-r2.sh; it is invoked on the
     "nothing to do" path BEFORE that path's exit 0, and again on the
     narrate-or-render path; and there is no bare push-to-r2.sh call left
     outside it, so the function is the only door to the shelf.

Negative proof, recorded in the PR that introduced this: with the
`shelve_shorts` call removed from the nothing-to-do block, assertion 3 fails
and nothing else in the suite notices - which is exactly how the shelf ran
dry for ten nights.

Hard-fails if the fixture plants fewer than three renders.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import shorts_lane as SL  # noqa: E402

fails: list[str] = []
tmp = Path(tempfile.mkdtemp(prefix="shorts-uncut-test-"))
renders = tmp / "renders"
shorts = tmp / "shorts"
renders.mkdir()
shorts.mkdir()

# ---- 1: exactly the uncut ones, in render order ---------------------------------
EPISODES = ["what-is-aerogel-made-of", "why-does-old-iron-not-rust",
            "why-is-steel-so-strong", "how-hot-does-a-welding-arc-get"]
CUT = {"why-does-old-iron-not-rust"}
for slug in EPISODES:
    (renders / f"{slug}-final.mp4").write_bytes(b"")
    # a stray non-final render must not count as an episode
    (renders / f"{slug}-draft.mp4").write_bytes(b"")
for slug in CUT:
    (shorts / f"{slug}-short.mp4").write_bytes(b"")
# a second-rank cut alone does not make an episode "cut": rank 1 is the lane's
(shorts / "why-is-steel-so-strong-short2.mp4").write_bytes(b"")

got = SL.uncut(renders, shorts)
want = sorted(s for s in EPISODES if s not in CUT)
if got != want:
    fails.append(f"1: uncut() returned {got}, wanted {want}")
n = len(EPISODES)

# ---- 2: an empty render set is a refusal, not a clean "nothing uncut" ------------
empty = tmp / "empty"
empty.mkdir()
try:
    SL.uncut(empty, shorts)
    fails.append("2: uncut() on a directory with no *-final.mp4 returned instead of raising")
except RuntimeError:
    pass

# ---- 3: the batch script cuts and shelves on BOTH paths -------------------------
batch = open(os.path.join(ROOT, "bin", "batch-session.sh")).read()

if "shelve_shorts()" not in batch:
    fails.append("3: bin/batch-session.sh does not define shelve_shorts")
else:
    body_start = batch.find("shelve_shorts()")
    body_end = batch.find("\n}\n", body_start)
    body = batch[body_start:body_end]
    if "shorts_lane.uncut()" not in body:
        fails.append("3: shelve_shorts does not ask shorts_lane.uncut() what to cut")
    if "bin/make-shorts.sh" not in body:
        fails.append("3: shelve_shorts does not run bin/make-shorts.sh")
    if "bin/push-to-r2.sh" not in body:
        fails.append("3: shelve_shorts does not run bin/push-to-r2.sh")
    if body.find("bin/make-shorts.sh") > body.find("bin/push-to-r2.sh"):
        fails.append("3: shelve_shorts pushes before it cuts, so tonight's cuts wait a night")

    # The nothing-to-do block: from its NAMED STOP line to its exit 0, the
    # function must be called. Locate the block by its own words.
    stop_at = batch.find('NAMED STOP: nothing to do.')
    if stop_at < 0:
        fails.append("3: the nothing-to-do NAMED STOP is gone from bin/batch-session.sh")
    else:
        exit_at = batch.find("\n  exit 0\n", stop_at)
        block = batch[stop_at:exit_at]
        # An invocation line, not the word - a comment that mentions the
        # function must not satisfy this.
        if not re.search(r"^\s*shelve_shorts\s*$", block, re.M):
            fails.append("3: the nothing-to-do path exits 0 without shelve_shorts - "
                         "an idle week starves the cloud Shorts lane")

    # The narrate-or-render path calls it too, after the function body.
    calls = [m.start() for m in re.finditer(r"^\s*shelve_shorts\s*$", batch, re.M)]
    if len(calls) < 2:
        fails.append(f"3: shelve_shorts is invoked {len(calls)} time(s); both paths must call it")

    # No back door: every push-to-r2.sh invocation lives inside the function.
    outside = [m.start() for m in re.finditer(r"^\s*bin/push-to-r2\.sh", batch, re.M)
               if not (body_start <= m.start() <= body_end)]
    if outside:
        fails.append("3: bin/push-to-r2.sh is still called outside shelve_shorts, "
                     "so a path can shelve without cutting")

# ---- Rule 0 --------------------------------------------------------------------
if n < 3:
    fails.append("Rule 0: the fixture planted fewer than three renders")

if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"OK shorts are cut on idle nights: {len(want)} uncut of {n} planted, "
      f"empty set refused, both batch paths shelve through shelve_shorts")
