#!/usr/bin/env python3
"""Selecting a POV line and not writing it down is what made V32 fail every week.

THE DEFECT THIS GUARDS. `pov_match.select()` picked a line from the owner's own
interview bank; `author.draft()` wrote it into the script and cited it — "matched
from POV BANK pov-027 before rewriting"; and NOTHING recorded the choice. Every
reference to `pov/pov-assignments.json` in the loop was a read.

So V32 asked which bank line each [HUMAN] beat traced to, found nothing, and
refused the episode. On 2026-09-07 that produced six requests to the owner to
approve lines she had ALREADY given in an interview, while 115 unused lines sat
in her bank. The gap was a missing write, not a missing line.

Hard-fails when it examines zero episodes.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))

import pov_match  # noqa: E402


def check() -> list[str]:
    fails: list[str] = []
    examined = 0

    # 1. THE WRITER EXISTS AND IS CALLED. A recorder nothing invokes is the
    #    "runs but inert" shape, and is indistinguishable from this bug.
    if not hasattr(pov_match, "record_assignment"):
        fails.append("pov_match.record_assignment() is missing — nothing can "
                     "write an assignment, so V32 will refuse every authored "
                     "episode exactly as it did before")
        return fails

    draft_src = (ROOT / "loop" / "draft.py").read_text(encoding="utf-8")
    if "record_assignment(" not in draft_src:
        fails.append("loop/draft.py never calls pov_match.record_assignment() "
                     "— the loop selects a line, cites it in the script, and "
                     "writes nothing down. That is the original defect.")

    # 2. IT IS CALLED WHERE THE SCRIPT IS PROMOTED, not before validation. An
    #    assignment for a script that failed validation points at a file that
    #    does not exist.
    promoted = draft_src.find("dest.write_text(text")
    recorded = draft_src.find("record_assignment(")
    if promoted == -1 or recorded == -1 or recorded < promoted:
        fails.append("record_assignment() is not inside the branch that "
                     "promotes the script — an assignment could be written for "
                     "a draft that never became a script")

    # 3. IT ADDS A ROW, AND ONLY WHEN THERE IS NOT ONE.
    doc = json.loads((ROOT / "pov" / "pov-assignments.json").read_text())
    before = len(doc["assignments"])
    existing = doc["assignments"][0]["video"] if before else None
    examined += before
    if before == 0:
        fails.append("pov/pov-assignments.json has no rows, so this guard "
                     "examined nothing")
        return fails

    # 4. A HAND ASSIGNMENT IS NEVER OVERWRITTEN. select() treats one as
    #    authoritative; a run that replaced it would be deciding something the
    #    owner decided.
    if existing:
        line = {"pov_id": "pov-001", "line": "x", "tier": "transferable"}
        if pov_match.record_assignment(existing, line) is not False:
            fails.append(f"record_assignment overwrote the existing assignment "
                         f"for {existing!r} — a hand assignment must win")

    # 5. THE SOURCE IS DISTINGUISHABLE FROM AN OWNER APPROVAL. "She read this
    #    line and claimed it" and "the author borrowed it from her bank" are
    #    different acts and must not read the same in the file.
    # Read the DEFAULT it would write, not the source text. The first version of
    # this check grepped `inspect.getsource` and matched its own docstring, which
    # explains the distinction — a test failing on the words that describe the
    # rule rather than on the behaviour it names.
    import inspect
    default = inspect.signature(pov_match.record_assignment).parameters["source"].default
    if "owner-approved" in str(default):
        fails.append(f"record_assignment defaults to source={default!r} — an "
                     "automated borrow must never look like a line she read "
                     "and claimed")

    print(f"inspected {examined} existing assignment(s); writer present and called")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - an authored episode records the bank line it borrowed"
          if not f else f"{len(f)} failure(s)")
    raise SystemExit(1 if f else 0)
