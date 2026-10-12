"""A validated draft carried over from an earlier run is promoted to scripts/.

2026-10-12, run 38278464493 (mon-draft): three publish-queue drafts authored by
run 38272528658 (which V21 stopped) sat in loop/drafts/. The next run found the
files, did not re-author them, so they were not `generated` - and promotion
only looked at `generated`. They validated green, were queued, and stayed in
loop/drafts/, which the Mac's batch never narrates.

Checks carried_draft() on every shape, then that the item main() builds and
the promotion branch both use it. Hard-fails on zero cases.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="stops-"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import draft  # noqa: E402


def main() -> int:
    fails, cases = [], 0
    drafts = sorted(p for p in (draft.ROOT / "loop" / "drafts").glob("*.md"))
    real = f"loop/drafts/{drafts[0].name}" if drafts else None
    if not real:
        fails.append("no loop/drafts/*.md to test against")
    else:
        for t, want, why in (
            ({"needs_authoring": True, "script": real}, True,
             "a queue slot whose draft exists from an earlier run"),
            ({"needs_authoring": True, "script": real, "generated": True}, False,
             "authored THIS run - already promoted as generated"),
            ({"needs_authoring": False, "script": real}, False,
             "inventory, not a queue slot"),
            ({"needs_authoring": True, "script": "loop/drafts/no-such-slug.md"},
             False, "no draft on disk"),
            ({"needs_authoring": True, "script": "scripts/" + drafts[0].name},
             False, "already in scripts/"),
        ):
            cases += 1
            got = draft.carried_draft(t)
            if got != want:
                fails.append(f"carried_draft({t}) = {got}, want {want}: {why}")

    src = open(os.path.join(LOOP, "draft.py"), encoding="utf-8").read()
    cases += 1
    if '"carried_draft": carried_draft(t)' not in src:
        fails.append("main() no longer stamps carried_draft on the queued item")
    cases += 1
    if not re.search(r'if it\.get\("generated"\) or it\.get\("carried_draft"\):'
                     r'\s*\n\s*promote_to_scripts\(st, it\)', src):
        fails.append("the passed-validators branch no longer promotes a "
                     "carried draft - it would stay in loop/drafts/ forever")
    if cases == 0:
        fails.append("examined zero cases")
    print(f"examined {cases} case(s)")
    for f in fails:
        print(f"  ✗ {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
