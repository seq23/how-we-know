"""The render gate's picture floor (hostile review 2026-11-02, finding 1).

A render whose beats show almost no picture is HELD and healed (moved aside,
plan dropped, so the nightly batch re-renders it pictures-first); a render at
or above the floor passes; a render made AFTER its picture heal airs as is
(the fallback - never an endless re-render loop). Proven negatively: with the
floor check removed, the bare render passes and the test goes red.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import render_gate as R  # noqa: E402


def _render(d: Path, plans: Path, slug: str, beats: int, footage: int, stills: int):
    (d / f"{slug}-final.mp4").write_bytes(slug.encode())
    (d / f"{slug}-final.mp4.render.json").write_text(json.dumps(
        {"beats": beats, "footage": {"footage_beats": footage}}))
    plan = [{"segment": "species_image"}] * stills + [{"segment": "text_beat"}] * (beats - stills)
    (plans / f"{slug}.json").write_text(json.dumps(plan))


def main() -> int:
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="picfloor-"))
    renders, plans = tmp / "renders", tmp / "plans"
    renders.mkdir()
    plans.mkdir()
    _render(renders, plans, "bare", 80, 0, 0)          # the 41 renders since mid-October
    _render(renders, plans, "footage", 80, 12, 0)      # 15% from footage
    _render(renders, plans, "stills", 80, 0, 30)       # a look-like episode's plates
    _render(renders, plans, "healed", 80, 0, 2)        # re-rendered after its heal
    heals = {"healed": {"at_epoch": time.time() - 3600}}
    r = R.picture_floor(["bare", "footage", "stills", "healed", "absent"],
                        renders=renders, plans=plans, heals=heals)
    held = {f.split(":", 1)[0] for f in r["failures"]}
    if r["examined"] != 4:
        fails.append(f"examined {r['examined']} renders, want 4 (absent one skipped)")
    if held != {"bare"}:
        fails.append(f"held {sorted(held)}; want only the bare render")
    if not any(n.startswith("healed:") for n in r["notes"]):
        fails.append("a render made after its picture heal was not let through (fallback)")
    # the gate turns the failure into a HOLD on that slug alone
    j = R.judge([r])
    if set(j["held"]) != {"bare"}:
        fails.append(f"render_gate.judge held {sorted(j['held'])}")
    # negative proof: a floor of zero lets the bare render through
    saved = R.PICTURE_FLOOR
    R.PICTURE_FLOOR = 0.0
    try:
        if R.picture_floor(["bare"], renders=renders, plans=plans, heals={})["failures"]:
            fails.append("negative proof broken: floor 0 still fails")
    finally:
        R.PICTURE_FLOOR = saved
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: render gate picture floor")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
