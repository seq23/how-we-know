"""research/publish_order_domain.py's `competition` record must carry every
key research/publish_order.py's shared `reason()` unconditionally reads.

Confirmed 2026-09-25, live: dispatching the weekly scorer against both
allocated domains (deep-sea-ocean-science, materials-and-manufacturing —
both genuinely exhausted, `queue_depth()` correctly read 0 for each after
every queued topic aired) reached `reason(rec)` for the first candidate in
EITHER domain and crashed every time:

    KeyError: 'median_subscribers'

`publish_order_domain.py`'s own `"competition": {...}` literal only ever
set 6 of the 4+ keys `reason()` reads — `median_subscribers` was simply
never copied over, though `research/competition.py`'s own return shape
(`c["incumbents"]["median_subscribers"]`) has always carried it. Because
`reason()` reads it BEFORE any branch on `title_gap`, this fails on every
non-empty candidate list, deterministically — not on bad luck, and not on
YouTube Data API quota. It was misclassified as the self-resolving
NEW_DOMAIN_QUOTA every time (`loop/score.py`'s QUOTA_MARKERS regex matched
unrelated quota prose earlier in the same captured output), so the crash
never reached a human: `research/publish_order_domain.py` had, as far as
this investigation could establish, NEVER once produced a queue for either
allocated domain the day its own queue ran dry.

Static and network-free on purpose: reason()'s bar is not "does this
domain currently have live data to score" but "does the SHAPE this file
promises match the shape the shared gate needs" — an AST check that would
have caught the missing field the day it was written, without needing
YouTube quota, a mined corpus, or any of the real inputs this script
otherwise requires.

Rule 0: hard-fails if either key set comes back empty, because a scan
that examines nothing has proved nothing.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

REASON_FILE = ROOT / "research" / "publish_order.py"
GATE_FILE = ROOT / "research" / "publish_order_domain.py"


def keys_reason_reads() -> set[str]:
    """Every `rec["competition"][<literal>]` reason() actually reads."""
    tree = ast.parse(REASON_FILE.read_text(), str(REASON_FILE))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "reason"), None)
    assert fn is not None, "research/publish_order.py no longer defines reason()"
    out = set()
    for node in ast.walk(fn):
        # rec["competition"]["median_subscribers"] parses as
        # Subscript(Subscript(Name("rec"), Constant("competition")),
        #           Constant(<key>))
        if not (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)):
            continue
        base = node.value
        if (isinstance(base, ast.Subscript)
                and isinstance(base.slice, ast.Constant)
                and base.slice.value == "competition"
                and isinstance(base.value, ast.Name)
                and base.value.id == "rec"):
            out.add(node.slice.value)
    return out


def keys_the_domain_gate_provides() -> set[str]:
    """Every literal key set inside publish_order_domain.py's own
    `"competition": {...}` dict."""
    tree = ast.parse(GATE_FILE.read_text(), str(GATE_FILE))
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        # Find this dict via its parent key, "competition" — walk keys/values
        # pairwise since ast.Dict does not carry its own containing key.
        pass
    # A dict literal has no parent pointer in the stdlib AST, so instead walk
    # every dict LITERAL assigned as the value of a "competition" key at any
    # nesting level - the same shape reason()'s own scan above depends on.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "competition"
                    and isinstance(v, ast.Dict)):
                for vk in v.keys:
                    if isinstance(vk, ast.Constant):
                        out.add(vk.value)
    return out


def check() -> list[str]:
    fails = []

    needs = keys_reason_reads()
    if not needs:
        fails.append("reason() scan found ZERO rec[\"competition\"][...] "
                     "reads - the AST walk stopped matching its own source "
                     "and this guard is examining nothing")
        return fails

    have = keys_the_domain_gate_provides()
    if not have:
        fails.append("publish_order_domain.py scan found ZERO keys in any "
                     "\"competition\": {...} literal - the AST walk stopped "
                     "matching and this guard is examining nothing")
        return fails

    missing = needs - have
    if missing:
        fails.append(
            f"research/publish_order_domain.py's \"competition\" record is "
            f"missing {sorted(missing)}, which research/publish_order.py's "
            f"reason() reads unconditionally. reason() is called on every "
            f"non-empty candidate, so this is not an occasional failure - it "
            f"is a KeyError on the FIRST candidate, every single run, "
            f"exactly the 2026-09-25 incident this test pins.")

    print(f"reason() reads {sorted(needs)}; the domain gate provides "
          f"{sorted(have)}.")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the domain gate's competition record carries every "
          "key the shared reason() function reads" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
