"""The render gate holds the one that fails and ships the rest - proven, not asserted.

WHAT HAPPENED. 6-13 September 2026: nine finished materials episodes, one of
them (why-is-steel-so-strong) rendered 9.90 minutes against a 10.0 floor. Both
Mac lanes ran V13/V24 and on ANY failure refused EVERYTHING - "nothing was
uploaded this run" - and the self-heal that already existed for a short
episode (loop/extend.py) was invoked by nothing. Eight good episodes waited a
week; five publish slots went unfilled; no report anywhere said so.

WHAT THIS PROVES, against a planted fixture rather than a live render:

  1. One sub-floor episode among N: exactly that slug is held, the other N-1
     are NOT held, and loop/backfill.py:library_pending skips the held one by
     name while keeping the rest pending.
  2. --heal invokes the self-heal for the held slug (HWK_EXTEND_CMD points at
     a stub that records its arguments), and does NOT invoke it for a clipped
     render, which extend.py cannot fix.
  3. Zero renders examined is RENDER_GATE_EMPTY, exit 3 - never a clean pass.
  4. loop/r2.py:push refuses to shelve a held slug and shelves the others.

Negative proof, recorded in the PR that introduced this: with the old
all-or-nothing gate restored in bin/loop-backfill-daily.sh, assertion 1's
"the other N-1 ship" has no code path to pass through, and this file fails.

Hard-fails if the fixture plants nothing or the gate examines nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable
sys.path.insert(0, LOOP)

fails: list[str] = []
tmp = tempfile.mkdtemp(prefix="render-gate-test-")
HOLD = os.path.join(tmp, "render_hold.json")
STOPS = os.path.join(tmp, "stops")
os.makedirs(STOPS)
STUB_LOG = os.path.join(tmp, "extend-calls.log")
STUB = os.path.join(tmp, "extend_stub.py")
open(STUB, "w").write(
    "import sys\nopen(sys.argv[1], 'a').write(' '.join(sys.argv[2:]) + '\\n')\n"
    "print('extended (stub)')\n")

ENV = dict(os.environ, LOOP_RENDER_HOLD=HOLD, LOOP_STOPS_DIR=STOPS,
           HWK_EXTEND_CMD=f"{PY} {STUB} {STUB_LOG}")

GOOD = [f"good-episode-{i}" for i in range(1, 9)]
SHORT = "why-is-steel-so-strong"
CLIPPED = "some-clipped-episode"


def gate(results, *args):
    fx = os.path.join(tmp, "results.json")
    json.dump(results, open(fx, "w"))
    return subprocess.run([PY, os.path.join(LOOP, "render_gate.py"),
                           "--from-json", fx, *args],
                          cwd=ROOT, env=ENV, capture_output=True, text=True)


def hold() -> dict:
    return json.load(open(HOLD)).get("held") or {}


# ---- 1 + 2: one short among nine; held by name, healed, the rest untouched ----
n = len(GOOD) + 2
results = [
    {"name": "V13", "examined": n, "failures": [f"{CLIPPED}: render is 0.412s SHORTER than its narration"]},
    {"name": "V24", "examined": n, "failures": [f"{SHORT}: rendered 9.90 min, under the 10.0-minute hard floor"]},
]
r = gate(results, "--heal")
h = hold()
if set(h) != {SHORT, CLIPPED}:
    fails.append(f"1: expected exactly {{{SHORT}, {CLIPPED}}} held, got {sorted(h)}")
for g in GOOD:
    if g in h:
        fails.append(f"1: {g} passed both validators and was held anyway")
if "8 pass and ship" not in r.stdout and f"{n - 2} pass" not in r.stdout:
    fails.append(f"1: the gate did not say the other {n - 2} ship:\n{r.stdout[-600:]}")
calls = open(STUB_LOG).read().split("\n") if os.path.exists(STUB_LOG) else []
if not any(SHORT in c for c in calls):
    fails.append(f"2: --heal did not invoke the self-heal for {SHORT}; calls={calls}")
if any(CLIPPED in c for c in calls):
    fails.append(f"2: --heal invoked extend.py for a CLIPPED render, which it cannot fix")
gate_files = [f for f in os.listdir(STOPS) if f.endswith("-render-gate.json")]
stop = json.load(open(os.path.join(STOPS, gate_files[0]))) if gate_files else {}
if stop.get("code") != "RENDER_HELD":
    fails.append(f"1: expected a RENDER_HELD stop, got {stop.get('code')!r}")
if not any(SHORT in i for i in stop.get("held_items") or []):
    fails.append(f"1: the RENDER_HELD stop does not name {SHORT} in held_items")

# ---- 1b: the upload route skips the held slug and keeps the rest -------------
os.environ["LOOP_RENDER_HOLD"] = HOLD
import importlib                                                   # noqa: E402
import render_gate                                                 # noqa: E402
importlib.reload(render_gate)
import backfill                                                    # noqa: E402
import batch_queue                                                 # noqa: E402
import ledger                                                      # noqa: E402

fake_rows = [{"slug": s} for s in GOOD + [SHORT, CLIPPED]]
batch_queue.queued_entries = lambda: fake_rows
ledger.load = lambda: {"published": [], "queued": []}
pending = backfill.library_pending(assets=lambda slug: (f"{slug}.mp4", f"{slug}.jpg"))
got = {p[0] for p in pending}
if got != set(GOOD):
    fails.append(f"1b: library_pending should keep exactly the 8 passing episodes; got {sorted(got)}")

# ---- 4: the shelf refuses the held slug and shelves the others --------------
import r2                                                          # noqa: E402
put_keys: list[str] = []


class _FakeBackend:
    def same_as(self, local, key):
        return False, "fresh"

    def put(self, local, key):
        put_keys.append(key)
        return {"size": 1, "sha256": "0" * 64}


# Give every slug a render and a thumbnail on disk under a scratch ROOT.
fake_root = os.path.join(tmp, "root")
os.makedirs(os.path.join(fake_root, "renders"))
os.makedirs(os.path.join(fake_root, "channel", "thumbnails"))
for s_ in GOOD + [SHORT]:
    open(os.path.join(fake_root, "renders", f"{s_}-final.mp4"), "w").write("x")
    open(os.path.join(fake_root, "channel", "thumbnails", f"{s_}.jpg"), "w").write("x")
r2.ROOT = __import__("pathlib").Path(fake_root)
try:
    res = r2.push(_FakeBackend(), GOOD + [SHORT])
except Exception as e:                                             # noqa: BLE001
    fails.append(f"4: r2.push raised against a fake backend: {e}")
    res = {"pushed": []}
shelved = {k for k in put_keys}
if any(SHORT in k for k in shelved):
    fails.append(f"4: r2.push shelved the HELD slug {SHORT}")
for g in GOOD:
    if not any(g in k for k in shelved):
        fails.append(f"4: r2.push did not shelve passing episode {g}")

# ---- 3: zero examined is a hard failure ----------------------------------------
r0 = gate([{"name": "V13", "examined": 0, "failures": []},
           {"name": "V24", "examined": 0, "failures": []}])
if r0.returncode == 0 or "RENDER_GATE_EMPTY" not in (r0.stdout + r0.stderr):
    fails.append(f"3: zero renders examined must be RENDER_GATE_EMPTY, exit 3; got rc={r0.returncode}")

# ---- 5: a clean gate holds nothing and lifts an old hold ----------------------
rc = gate([{"name": "V13", "examined": 9, "failures": []},
           {"name": "V24", "examined": 9, "failures": []}])
if rc.returncode != 0 or hold():
    fails.append(f"5: a clean gate should exit 0 and clear the hold; rc={rc.returncode}, held={hold()}")

# ---- 6: both Mac lanes go THROUGH the gate, and the old all-or-nothing is gone --
# This is what makes the negative proof real: restore the old inline gate in
# either script and this assertion fails, whatever render_gate.py does.
daily = open(os.path.join(ROOT, "bin", "loop-backfill-daily.sh")).read()
batch = open(os.path.join(ROOT, "bin", "batch-session.sh")).read()
if "loop/render_gate.py --heal" not in daily:
    fails.append("6: bin/loop-backfill-daily.sh does not run loop/render_gate.py --heal")
if "RENDER_GATE_FAILED" in daily or "nothing was uploaded this run" in daily:
    fails.append("6: bin/loop-backfill-daily.sh still carries the all-or-nothing gate")
if "loop/render_gate.py" not in batch:
    fails.append("6: bin/batch-session.sh does not run loop/render_gate.py")
if "REFUSING to push to R2" in batch:
    fails.append("6: bin/batch-session.sh still refuses the whole R2 push on one failure")
if "loop/mac_sync.py pull" not in daily or "mac_sync.py heartbeat" not in daily or "mac_sync.py push" not in daily:
    fails.append("6: bin/loop-backfill-daily.sh does not pull/heartbeat/push through loop/mac_sync.py")
if "mac_sync.py heartbeat" not in batch or "mac_sync.py push" not in batch:
    fails.append("6: bin/batch-session.sh does not report a heartbeat")
# The heal runs BEFORE narration in the batch, so it lands in the same pass.
if batch.find("loop/extend.py") > batch.find("--- narration"):
    fails.append("6: bin/batch-session.sh runs extend.py after narration, so a healed script waits a night")

# ---- Rule 0 --------------------------------------------------------------------
if n < 3:
    fails.append("Rule 0: the fixture planted fewer than three episodes")

if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: 1 short + 1 clipped among {n} held by name, {len(GOOD)} shipped, "
      f"self-heal invoked for the short one only, empty gate hard-fails, clean gate lifts the hold")
