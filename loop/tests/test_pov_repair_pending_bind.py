#!/usr/bin/env python3
"""A script rewritten in the cloud must not leave the POV repair "needing a human".

THE DEFECT THIS GUARDS (CONFIRMED 2026-10-13, main 28ac4e4). Two faults met:

  1. `pov_match.select()` excluded only the twelve-video rotation window, so the
     Monday draft handed pov-001 (owned by live how-deep-mariana-trench) to two
     new scripts and pov-038 (owned by live how-deep-can-a-sperm-whale-go) to a
     third. `record_assignment()` rightly refused the reuse, so all three were
     promoted with an untraced [HUMAN] beat.
  2. `loop/queue_reopen.py` then rewrote their openings in the cloud
     (`pending_bind`: plans/, audio/ and renders/ stay the OLD script's until
     the Mac's `lengthen.py bind`). `loop/pov_repair.py` matched the [HUMAN]
     sentence against that stale frozen plan, found nothing, and stopped as
     POV_UNREPAIRABLE - "needs a human" - for all three.

Properties, all behavioural, on one of the three rebuilt in its 28ac4e4 state:

  A. V71 FAILS on the broken state (the guard can see the defect).
  B. A stale plan that is NOT pending bind is still refused - the divergence
     guard is kept, not loosened.
  C. A pending-bind rewrite is repaired: a bank line no other live episode
     owns, the assignment recorded, both script twins identical, the
     fingerprint bind() checks moved to the new script, plans/ untouched (bind
     must see the OLD plan to retire the old wavs).
  D. After bind's re-freeze (planner.plan(script) -> plans/) the lane has
     nothing left to do and V71 passes.
  E. select() never hands out a line another live episode owns.

Hard-fails if it examines zero cases. LOOP_DRY_RUN=1: nothing leaves this box.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))
sys.path.append(str(ROOT / "visuals"))

import lengthen                                                # noqa: E402
import pov_match                                               # noqa: E402
import pov_repair                                              # noqa: E402
import validate                                                # noqa: E402

SLUG = "what-lives-in-mariana-trench"
# The 28ac4e4 defect, rebuilt from the tracked files (CI clones shallow, so
# the old commit is not there to `git show`): the script's [HUMAN] beat speaks
# pov-001 - owned by live how-deep-mariana-trench - with no row of its own.
REUSED = "pov-001"
OWNER = "how-deep-mariana-trench"


def broken_script() -> str:
    text = (ROOT / "scripts" / f"{SLUG}.md").read_text(encoding="utf-8")
    para = next(p for p in text.split("\n\n") if "[HUMAN]" in p)
    line = next(l["line"] for l in pov_match.bank() if l["id"] == REUSED)
    return text.replace(para, f"[HUMAN] {line}", 1)


def broken_assignments() -> dict:
    doc = json.loads((ROOT / "pov" / "pov-assignments.json").read_text())
    doc["assignments"] = [a for a in doc["assignments"] if a["video"] != SLUG]
    assert any(a["video"] == OWNER and a["pov_id"] == REUSED
               for a in doc["assignments"]), "fixture premise gone"
    return doc


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture(tmp: Path, pending: bool) -> None:
    for d in ("scripts", "drafts", "plans", "audio", "renders", "captions"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    pov_match.ASSIGNMENTS = ROOT / "pov" / "pov-assignments.json"
    script = broken_script()
    doc = broken_assignments()
    (tmp / "scripts" / f"{SLUG}.md").write_text(script, encoding="utf-8")
    (tmp / "drafts" / f"{SLUG}.md").write_text(script, encoding="utf-8")
    # The tracked plan: either the old script's (pending bind, as on
    # 28ac4e4) or tonight's re-freeze - neither carries the pov-001 sentence.
    (tmp / "plans" / f"{SLUG}.json").write_text(
        (ROOT / "plans" / f"{SLUG}.json").read_text(), encoding="utf-8")
    (tmp / "assignments.json").write_text(json.dumps(doc, indent=2) + "\n")
    eps = {}
    if pending:
        eps[SLUG] = {"status": "scripted", "mode": "pending_bind",
                     "kind": "reopen", "new_script_sha256": sha(script)}
    (tmp / "lengthen.json").write_text(json.dumps({"episodes": eps}))
    pov_repair.SCRIPTS = lengthen.SCRIPTS = tmp / "scripts"
    lengthen.DRAFTS = tmp / "drafts"
    pov_repair.PLANS = lengthen.PLANS = tmp / "plans"
    pov_repair.AUDIO = tmp / "audio"
    pov_repair.RENDERS = tmp / "renders"
    pov_repair.CAPTIONS = tmp / "captions"
    lengthen.STATE = tmp / "lengthen.json"
    pov_match.ASSIGNMENTS = tmp / "assignments.json"


def v71(fails: list, want_ok: bool, label: str) -> None:
    r = validate.v71_queued_pov_traced(slugs=[SLUG]).as_dict()
    ok = r["status"] == "PASS"
    if ok != want_ok or r["examined"] != 1:
        fails.append(f"{label}: V71 {r['status']} (examined {r['examined']}), "
                     f"wanted {'PASS' if want_ok else 'FAIL'}: {r['failures']}")


def check() -> list[str]:
    fails: list[str] = []
    examined = 0

    # B. stale plan, not pending bind -> still refused, nothing written
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fixture(tmp, pending=False)
        before = (tmp / "scripts" / f"{SLUG}.md").read_text()
        rec = pov_repair.repair_one(SLUG)
        examined += 1
        if not rec.get("refused"):
            fails.append(f"B: a stale plan outside pending bind was not "
                         f"refused: {rec}")
        if (tmp / "scripts" / f"{SLUG}.md").read_text() != before:
            fails.append("B: a refused repair changed the script")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fixture(tmp, pending=True)
        examined += 1
        # A. the guard sees the broken state
        v71(fails, False, "A (broken 28ac4e4 state)")

        plan_before = (tmp / "plans" / f"{SLUG}.json").read_bytes()
        rec = pov_repair.repair_one(SLUG)
        # C.
        if not rec.get("pov_id") or not rec.get("pending_bind"):
            fails.append(f"C: pending-bind episode was not repaired: {rec}")
            return fails
        script = (tmp / "scripts" / f"{SLUG}.md").read_text()
        if (tmp / "drafts" / f"{SLUG}.md").read_text() != script:
            fails.append("C: the loop/drafts twin no longer matches scripts/")
        st = lengthen.pending_bind(SLUG)
        if not st or st.get("new_script_sha256") != sha(script):
            fails.append("C: lengthen.json's new_script_sha256 was not moved "
                         "to the repaired script - tonight's bind refuses it")
        if (tmp / "plans" / f"{SLUG}.json").read_bytes() != plan_before:
            fails.append("C: plans/ was written before bind - bind would "
                         "treat the new plan as the old one")
        row = pov_match.hand_assignments().get(SLUG)
        if not row or row["pov_id"] != rec["pov_id"]:
            fails.append(f"C: assignment not recorded: {row}")
        if rec["pov_id"] in pov_match.owned_by_other_live(SLUG):
            fails.append(f"C: {rec['pov_id']} is owned by another live episode")
        v71(fails, True, "C (repaired, still pending bind)")

        # D. bind re-freezes the plan from the script; nothing left to repair
        import planner                                       # noqa: PLC0415
        (tmp / "plans" / f"{SLUG}.json").write_text(json.dumps(
            planner.plan(str(tmp / "scripts" / f"{SLUG}.md")), indent=2))
        d = lengthen.load()
        d["episodes"][SLUG].update(status="full_rerender", mode="full")
        lengthen.save(d)
        examined += 1
        if SLUG in pov_repair.candidates():
            fails.append("D: after bind the episode is still a repair candidate")
        v71(fails, True, "D (bound)")

    # E. select() never returns a line another live episode owns
    for probe, subject in (
            ("probe-mariana", "what lives in the mariana trench, in the dark"),
            ("probe-giants", "why are deep sea creatures so big"),
            ("probe-evidence", "how do we know an animal behaves this way")):
        examined += 1
        pov_match.ASSIGNMENTS = ROOT / "pov" / "pov-assignments.json"
        pick = pov_match.select(probe, subject, [])
        owned = pov_match.owned_by_other_live(probe)
        if pick["pov_id"] in owned:
            fails.append(f"E: select({probe!r}) returned {pick['pov_id']}, "
                         f"which a live episode already owns")
    if examined == 0:
        fails.append("examined zero cases")
    print(f"examined {examined} case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - a cloud rewrite leaves the POV repair clean"
          if not f else f"{len(f)} failure(s)")
    raise SystemExit(1 if f else 0)
