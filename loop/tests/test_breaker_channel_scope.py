"""A breaker trip halts only the channel it belongs to (16 Nov 2026).

How We Know's materials-and-manufacturing domain trip (13 Nov) stopped
Whisper Almanac's upload on 14 and 15 Nov while a finished Almanac render
waited. Proved both ways, and negatively:

  1. a How We Know trip (the live record shape: no `channel` field) halts a
     How We Know publishing stage and does NOT halt whisper-upload;
  2. a Whisper Almanac trip halts whisper-upload and does NOT halt any How We
     Know publishing stage.

Hard-fails if it checked zero stages.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="breaker-scope-")
os.environ["LOOP_BREAKER_FLAG"] = os.path.join(TMP, "breaker.json")
os.environ.setdefault("LOOP_STOPS_DIR", os.path.join(TMP, "stops"))
os.environ.pop("GITHUB_STEP_SUMMARY", None)
sys.path.insert(0, LOOP)
import breaker  # noqa: E402

FAILS: list[str] = []
CHECKED = 0


def halted(stage: str) -> bool:
    try:
        breaker.guard(stage)
    except SystemExit:
        return True
    return False


def expect(stage: str, want: bool, why: str) -> None:
    global CHECKED
    CHECKED += 1
    got = halted(stage)
    if got != want:
        FAILS.append(f"{why}: {stage} {'halted' if got else 'NOT halted'}")


def write(record: dict) -> None:
    with open(breaker.FLAG, "w") as f:
        json.dump(record, f)


HWK_STAGES = [s for s in breaker.GUARDED if breaker.channel_of(s) == "how-we-know"]
if not HWK_STAGES or breaker.channel_of("whisper-upload") != "whisper-almanac":
    raise SystemExit("FAIL: no How We Know stages, or whisper-upload not scoped to the Almanac")

# 1. How We Know's own domain trip, exactly as loop/state/breaker.json held it on 15 Nov.
hwk = {"state": "tripped", "tripped_at": "2026-11-13T22:05:54+00:00", "cause": "domain",
       "detail": "3 consecutive materials-and-manufacturing videos below the duration floor",
       "history": []}
write(hwk)
expect("whisper-upload", False, "How We Know domain trip")
write(hwk)
expect("thu-upload", True, "How We Know domain trip")

# 2. A Whisper Almanac trip (manual: never auto-resets).
write(dict(breaker.CLOSED))
breaker.trip("manual", "Almanac hold", channel="whisper-almanac")
expect("whisper-upload", True, "Whisper Almanac trip")
for s in HWK_STAGES:
    expect(s, False, "Whisper Almanac trip")

# 3. A How We Know trip with an extra Almanac cause halts both.
write(dict(hwk, also=[{"cause": "manual", "detail": "x", "channel": "whisper-almanac"}]))
expect("whisper-upload", True, "How We Know trip + Almanac extra cause")

if CHECKED < 4:
    raise SystemExit(f"FAIL: checked only {CHECKED} stage(s)")
if FAILS:
    raise SystemExit("FAIL:\n  " + "\n  ".join(FAILS))
print(f"PASS: breaker channel scope held for {CHECKED} stage check(s)")
