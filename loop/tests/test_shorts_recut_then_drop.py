"""Finding 6 (hostile review 2026-11-02): a Short cut that fails V14/V15 is
re-cut once, then dropped; a cut whose render is gone is dropped at once; a
dropped cut is never re-cut. Negative proof in-test: without the dropped list
the cut would be asked for again."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
TMP = Path(tempfile.mkdtemp(prefix="recut-"))
os.environ["LOOP_SHORTS_RECUT"] = str(TMP / "recut.json")

import shorts_lane as SL  # noqa: E402


def main() -> int:
    fails = []
    shorts, renders = TMP / "shorts", TMP / "renders"
    shorts.mkdir(); renders.mkdir()
    (renders / "ep-final.mp4").write_bytes(b"x")
    name = "ep-short.mp4"
    for n in (name, f"{name}.short.json"):
        (shorts / n).write_text("cut")
    if SL.heal_held_cut(name, "ep", shorts, renders) != "recut" or (shorts / name).exists():
        fails.append("a first failure did not move the cut aside for a re-cut")
    if SL.uncut(renders, shorts) != ["ep"]:
        fails.append("the moved-aside cut is not asked for again (no re-cut)")
    (shorts / name).write_text("recut")
    if SL.heal_held_cut(name, "ep", shorts, renders) != "dropped":
        fails.append("a second failure did not drop the cut")
    if SL.uncut(renders, shorts) != []:
        fails.append("a dropped cut is asked for again every night")
    (shorts / "gone-short.mp4").write_text("cut")
    if SL.heal_held_cut("gone-short.mp4", "gone", shorts, renders) != "dropped":
        fails.append("a cut whose render is gone was not dropped at once")
    (renders / "gone-final.mp4").write_bytes(b"restored")
    if "gone-short.mp4" in SL.dropped_cuts(shorts):
        fails.append("restored master did not release its retired cut for a fresh gated cut")
    (shorts / "gone-short.mp4").write_text("fresh cut")
    if SL.heal_held_cut("gone-short.mp4", "gone", shorts, renders) != "recut":
        fails.append("restored master inherited failure attempts from missing source")
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: Shorts re-cut, then drop")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
