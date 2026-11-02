"""An input a stage cannot read fails that stage by name; it is never taken as empty.

WHY (ci-sweep, 2 Nov 2026). Two handlers whose whole body was `pass` turned a
read failure into a quiet, wrong answer:

  1. loop/titles.py strongest_questions() swallowed ANY error reading the
     publish queue, so a broken queue picked a title as if the queue held no
     compilation row for the question.
  2. research/subject_photo.py held() swallowed ANY error from
     question_card.photos(), so a broken photo manifest listed the episode as
     having no photo and sent the finder to pin another one over it.

Both now let the error through. This test fakes each read failing and requires
the call to raise it; a call that returns instead is a failure. It examines a
fixed list of cases and hard-fails if it examined none.

NEGATIVE PROOF (by hand, 2 Nov 2026): restoring either `except Exception: pass`
makes its case fail ("returned ... instead of raising"); restored, green.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "loop"))
os.environ["LOOP_DRY_RUN"] = "1"

import domains                                                  # noqa: E402,F401  loop's, first
import batch_queue                                              # noqa: E402
import question_card as QC                                      # noqa: E402
import subject_photo as SP                                      # noqa: E402
import titles                                                   # noqa: E402


class Unreadable(RuntimeError):
    """The fault each case injects; only this exact error counts as surfaced."""


def boom(*_a, **_k):
    raise Unreadable("fixture: this input cannot be read")


def surfaced(call) -> str | None:
    """None when `call` raised the injected fault, else what went wrong."""
    try:
        got = call()
    except Unreadable:
        return None
    return f"returned {got!r} instead of raising"


CASES = [
    ("titles.strongest_questions with an unreadable publish queue",
     batch_queue, "queued_entries",
     lambda: titles.strongest_questions(
         "why do deep sea fish die when brought to the surface")),
    ("subject_photo.held with an unreadable photo manifest",
     QC, "photos",
     lambda: SP.held(["how-deep-can-a-sperm-whale-go"])),
]

fails: list[str] = []
examined = 0
for label, mod, attr, call in CASES:
    real = getattr(mod, attr)
    setattr(mod, attr, boom)
    try:
        why = surfaced(call)
    finally:
        setattr(mod, attr, real)
    examined += 1
    print(("  ok  " if why is None else "  ✗  ") + label + ("" if why is None else f": {why}"))
    if why is not None:
        fails.append(f"{label}: {why}")

if examined == 0:
    print("examined zero cases - this test proves nothing and fails")
    sys.exit(1)
print(f"\n{examined} case(s), {len(fails)} failed")
sys.exit(1 if fails else 0)
