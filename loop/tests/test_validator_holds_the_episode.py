"""Finding 7 (hostile review 2026-11-02): a validator failure that names an
episode holds THAT episode; the channel-wide breaker is only for a failure that
names none. Proven negatively in-test: an unnamed failure must still return None
(breaker path), and a held slug must be skipped by the upload selection.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

import draft  # noqa: E402


def main() -> int:
    fails = []
    slugs = {"why-is-glass-clear", "is-titanium-stronger-than-steel"}
    named = [{"validator": "V21", "failures": ["why-is-glass-clear: sentence repeats an aired one"]},
             {"validator": "V5", "failures": []}]
    held = draft.episodes_held_by(named, slugs)
    if not held or set(held) != {"why-is-glass-clear"}:
        fails.append(f"a named failure did not hold exactly its episode: {held}")
    unnamed = named + [{"validator": "V9", "failures": ["the channel config has no rotation"]}]
    if draft.episodes_held_by(unnamed, slugs) is not None:
        fails.append("a failure naming no episode was turned into an episode hold "
                     "(it must trip the channel-wide breaker)")
    # the upload selection skips a held episode and keeps the rest
    import json, tempfile                                       # noqa: E401
    import backfill
    import batch_queue
    q = [s for s in batch_queue.queued_slugs()][:40]
    hold = os.path.join(tempfile.mkdtemp(prefix="vhold-"), "h.json")
    found = lambda s: ("render.mp4", "thumb.jpg")              # noqa: E731
    os.environ.pop("LOOP_VALIDATOR_HOLD", None)
    base = [r[0] if isinstance(r, tuple) else r for r in backfill.library_pending(assets=found)]
    base = [x["slug"] if isinstance(x, dict) else x for x in base]
    if not base:
        fails.append("examined nothing: no pending episode to hold")
    else:
        json.dump({"held": {base[0]: ["V21: test"]}}, open(hold, "w"))
        os.environ["LOOP_VALIDATOR_HOLD"] = hold
        after = [r[0] if isinstance(r, tuple) else r for r in backfill.library_pending(assets=found)]
        after = [x["slug"] if isinstance(x, dict) else x for x in after]
        os.environ.pop("LOOP_VALIDATOR_HOLD")
        if base[0] in after:
            fails.append(f"a validator-held episode ({base[0]}) is still offered for upload")
        if set(base) - {base[0]} != set(after):
            fails.append("holding one episode changed what else ships")
    del q
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: a validator holds the episode, not the channel")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
