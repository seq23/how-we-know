#!/usr/bin/env python3
"""Git merge driver for `loop/state/llm_route_ledger.json` - unions both sides.

The route ledger (loop/llm_router.py, owner 2026-10-12) is appended to by
every lane that calls a $0 model: mon-draft, the comment replies, the
localize pass, extend, advise. Two of those can commit within the same minute
and rebase onto each other, exactly as loop/state/quota.json did on
2026-09-03. A textual conflict here is a false positive: every event is a
real, timestamped outcome, so the correct merge is the UNION of both sides'
events per model (deduplicated, oldest first), bounded to the same last-N the
router keeps. Never a side picked, never an event invented.

    python3 loop/tools/merge_route_ledger.py %O %A %B   (writes %A, exit 0)

Registered in .gitattributes (merge=route-ledger-union) and, because git will
not run a driver command from a committed file, in bin/loop-stage.sh's local
git config. Pinned by loop/tests/test_measured_fallback.py.
"""
from __future__ import annotations

import json
import sys

KEEP = 20


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def merge(ours: dict, theirs: dict, keep: int = KEEP) -> dict:
    out = dict(theirs)
    out.update(ours)
    models: dict = {}
    for side in (theirs, ours):
        for m, evs in (side.get("models") or {}).items():
            models.setdefault(m, []).extend(e for e in (evs or [])
                                            if isinstance(e, dict))
    merged = {}
    for m, evs in models.items():
        seen, uniq = set(), []
        for e in evs:
            k = json.dumps(e, sort_keys=True)
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        uniq.sort(key=lambda e: str(e.get("ts") or ""))
        merged[m] = uniq[-keep:]
    out["models"] = merged
    return out


def main(argv: list[str]) -> int:
    _base, ours, theirs = argv[1:4]
    out = merge(_load(ours), _load(theirs))
    with open(ours, "w") as f:
        f.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
