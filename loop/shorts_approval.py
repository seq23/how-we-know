"""Which cut Shorts are allowed to be published. One file, one decision.

The owner reviews the cuts and approves them; nothing publishes without being
named here. Requested 2026-09-01: *"show me the shorts when they're done and i
guess you will queue the shorts i approve?"*

WHY AN EXPLICIT GATE AND NOT JUST "RANK 1". The ranker picks each episode's best
chapter against that episode's own direct-answer lock, and rank 1 has been right
every time it was checked. Ranks 2 and 3 have not: one was a hedge chapter
("These are broad patterns, not rigid rules") and another was an editorial note
about the edit itself, which is fine inside an eight-minute episode and fatal in
a forty-second Short. Publishing those blind would put the channel's weakest
sentences in front of its widest audience.

So: **a Short publishes only if it is listed APPROVED here.** No default, no
"rank 1 is probably fine". An unreviewed cut sits on disk and costs nothing.

The file is `loop/state/shorts_approval.json`:

    {"approved": ["05-...-short.mp4"], "rejected": ["07-...-short2.mp4"],
     "notes": {"07-...-short2.mp4": "hedge chapter, not the physics"}}

Rejection is recorded, not just absence, so a Short that was LOOKED AT and turned
down is distinguishable from one nobody has seen yet. Those are different states
and the report says which is which.
"""
from __future__ import annotations

import json
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
STATE = LOOP / "state" / "shorts_approval.json"
SHORTS = ROOT / "shorts"


def load() -> dict:
    if STATE.exists():
        d = json.loads(STATE.read_text())
        d.setdefault("approved", [])
        d.setdefault("rejected", [])
        d.setdefault("notes", {})
        return d
    return {"approved": [], "rejected": [], "notes": {}}


def save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")


def approve(names: list[str], note: str = "") -> dict:
    d = load()
    for n in names:
        if n in d["rejected"]:
            d["rejected"].remove(n)
        if n not in d["approved"]:
            d["approved"].append(n)
        if note:
            d["notes"][n] = note
    d["approved"].sort()
    save(d)
    return d


def reject(names: list[str], note: str = "") -> dict:
    d = load()
    for n in names:
        if n in d["approved"]:
            d["approved"].remove(n)
        if n not in d["rejected"]:
            d["rejected"].append(n)
        if note:
            d["notes"][n] = note
    d["rejected"].sort()
    save(d)
    return d


def is_approved(name: str) -> bool:
    return name in load()["approved"]


def is_rejected(name: str) -> bool:
    """The only check the lane makes. Approval is NOT required.

    The owner declined a per-Short approval step (2026-09-01) - ranks 1 and 2
    publish automatically. This stays as a VETO: if a bad cut is ever spotted,
    naming it here keeps it off the channel permanently, and the record says it
    was seen and refused rather than merely never reviewed.
    """
    return name in load()["rejected"]


def status() -> dict:
    """Every cut Short, split into approved / rejected / never reviewed."""
    d = load()
    on_disk = sorted(p.name for p in SHORTS.glob("*.mp4")) if SHORTS.is_dir() else []
    approved = [n for n in on_disk if n in d["approved"]]
    rejected = [n for n in on_disk if n in d["rejected"]]
    # "unreviewed" is NOT a blocking state - ranks 1-2 publish without review.
    unreviewed = [n for n in on_disk
                  if n not in d["approved"] and n not in d["rejected"]]
    return {"on_disk": on_disk, "approved": approved, "rejected": rejected,
            "unreviewed": unreviewed, "notes": d["notes"]}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("approve", "reject"):
        fn = approve if sys.argv[1] == "approve" else reject
        fn(sys.argv[2:])
    s = status()
    print(f"  on disk    : {len(s['on_disk'])}")
    print(f"  approved   : {len(s['approved'])}")
    print(f"  rejected   : {len(s['rejected'])}")
    print(f"  unreviewed : {len(s['unreviewed'])}  (ranks 1-2 still publish; "
          f"only 'rejected' blocks)")
