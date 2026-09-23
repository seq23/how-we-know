"""An empty upload shelf is diagnosed from state, not blamed on the Mac.

THE INCIDENT. Run 35738742706 (2026-09-22) took NOTHING_SHELVED for the
eighth day running and paged the owner (#105): "the Mac is not pushing -
bin/push-to-r2.sh is failing, or com.howweknow.batch is not firing". Neither
was true. The batch fired every night and pushed; all 34 episodes in
research/publish_order*.json were already in the ledger. Four scripts the
Monday lane authored on 2026-09-21 were in loop/render_queue.json and in no
publish_order file, and bin/batch-session.sh only reads the publish_order
files. So the shelf was empty because the queue was used up, and the new
scripts had no route to the narrator. One code covered three states, and the
page named the one that was not happening.

WHAT THIS PROVES, on loop/cloud_upload.py diagnose_empty_shelf() and on the
real loop/stop_policy.json:

  1. The 2026-09-22 state (every queued slug uploaded, stranded authored rows)
     is AUTHORED_NOT_QUEUED. It names the stranded slugs and does not mention
     the Mac's push. It pages on the first report, and an unchanged second
     report is HELD (green).
  2. Queued episodes not yet uploaded are still NOTHING_SHELVED, and the stop
     names them. That is the one state where the Mac is the right place to look.
  3. Episodes the render gate holds are not blamed on the Mac.
  4. A used-up queue with nothing stranded is PUBLISH_QUEUE_UPLOADED. It is
     self-resolving, and it escalates after its cap.
  5. Rows that are finished, dropped or already uploaded do not count as
     stranded.
  6. Zero rows, or a missing hand-off file, never reads as "finished".

NEGATIVE PROOF. Each case asserts an outcome that the pre-fix code, which
always raised NOTHING_SHELVED with "On the Mac: bin/push-to-r2.sh", fails.
Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

# Stop records and held entries go to a scratch dir, never the committed state.
os.environ["LOOP_STOPS_DIR"] = tempfile.mkdtemp(prefix="empty-shelf-stops-")

import common                                             # noqa: E402
import cloud_upload as CU                                 # noqa: E402

fails: list[str] = []
examined = 0

QUEUED = [f"ep-{i:02d}" for i in range(34)]
STRANDED = ["how-do-scientists-know-so-much",
            "how-do-scientists-know-how-old-something-is",
            "why-deep-sea-creatures",
            "how-do-scientists-know-about-other-galaxies"]


def rows(slugs, status="queued"):
    return [{"slug": s, "status": status} for s in slugs]


def blames_mac(why: dict) -> bool:
    text = (why["message"] + " " + why["unblock"]).lower()
    return "push-to-r2" in text or "not pushing" in text


# -- 1. the 2026-09-22 state -------------------------------------------------
examined += 1
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED), set(), rows(STRANDED))
if why["code"] != "AUTHORED_NOT_QUEUED":
    fails.append(f"the 2026-09-22 state was diagnosed {why['code']}, not "
                 f"AUTHORED_NOT_QUEUED")
if blames_mac(why):
    fails.append("the 2026-09-22 diagnosis still blames the Mac's push")
if sorted(why["held_items"] or []) != sorted(STRANDED):
    fails.append(f"AUTHORED_NOT_QUEUED does not name exactly the stranded "
                 f"slugs: {why['held_items']}")
for s in STRANDED:
    if s not in why["message"]:
        fails.append(f"AUTHORED_NOT_QUEUED message does not name {s}")
if "research/publish_order" not in why["message"]:
    fails.append("AUTHORED_NOT_QUEUED does not say WHERE the scripts are "
                 "missing from")

# Disposition, on the real policy. The first report reaches a person; an
# unchanged second report is HELD (green), not paged every day.
examined += 1
d1, why1 = common.disposition(CU.LANE, "AUTHORED_NOT_QUEUED", why["detail"],
                              1, held_items=why["held_items"],
                              unblock=why["unblock"])
d2, why2 = common.disposition(CU.LANE, "AUTHORED_NOT_QUEUED", why["detail"],
                              2, held_items=why["held_items"],
                              unblock=why["unblock"])
if d1 != "needs_human":
    fails.append(f"the first AUTHORED_NOT_QUEUED report is {d1}, not "
                 f"needs_human. Time cannot fix it, so it must reach a person")
if d2 not in ("held", "needs_human"):
    fails.append(f"a repeat AUTHORED_NOT_QUEUED is {d2}")
policy = json.loads((LOOP / "stop_policy.json").read_text())
if "AUTHORED_NOT_QUEUED" in policy.get("self_resolving", {}):
    fails.append("AUTHORED_NOT_QUEUED is classified self-resolving. Nothing "
                 "clears it with time, which is the inert-label defect")

# -- 2. queued episodes still waiting on the Mac ------------------------------
examined += 1
waiting = QUEUED[30:]
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED[:30]), set(), rows(STRANDED))
if why["code"] != "NOTHING_SHELVED":
    fails.append(f"episodes not yet uploaded gave {why['code']}, not "
                 f"NOTHING_SHELVED")
if why["detail"].get("awaiting_mac") != waiting:
    fails.append(f"NOTHING_SHELVED does not name the waiting slugs: "
                 f"{why['detail'].get('awaiting_mac')}")

# -- 3. render-gate holds are not the Mac's fault -----------------------------
examined += 1
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED[:33]), {QUEUED[33]}, [])
if why["code"] == "NOTHING_SHELVED":
    fails.append("an episode held by the render gate was blamed on the Mac")
if why["detail"].get("render_gate_held") != [QUEUED[33]]:
    fails.append("the render-gate hold is not reported in the detail")

# -- 4. used up, nothing stranded ---------------------------------------------
examined += 1
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED), set(), [])
if why["code"] != "PUBLISH_QUEUE_UPLOADED":
    fails.append(f"a fully uploaded queue gave {why['code']}")
if blames_mac(why):
    fails.append("a fully uploaded queue still blames the Mac's push")
d, _ = common.disposition(CU.LANE, "PUBLISH_QUEUE_UPLOADED", why["detail"], 1)
if d != "self_resolving":
    fails.append(f"PUBLISH_QUEUE_UPLOADED run 1 is {d}, not self_resolving")
cap = int(policy["self_resolving"]["PUBLISH_QUEUE_UPLOADED"]["max_consecutive"])
d, _ = common.disposition(CU.LANE, "PUBLISH_QUEUE_UPLOADED", why["detail"],
                          cap + 1)
if d != "needs_human":
    fails.append(f"PUBLISH_QUEUE_UPLOADED past its cap is {d}. A finished "
                 f"state that never ends must still escalate")

# -- 5. rows past the hand-off are not stranded -------------------------------
examined += 1
past = (rows(["a"], "dropped") + rows(["b"], "rendered")
        + rows(["c"], "published") + rows([QUEUED[0]], "queued")
        + [{"status": "queued"}])
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED) | {"d"}, set(),
                              past + rows(["d"], "approved"))
if why["code"] != "PUBLISH_QUEUE_UPLOADED":
    fails.append(f"finished/dropped/queued/uploaded rows were read as stranded:"
                 f" {why['code']} {why.get('held_items')}")

# -- 6. never 'finished' by default -------------------------------------------
examined += 1
why = CU.diagnose_empty_shelf([], set(), set(), [])
if why["code"] != "PUBLISH_QUEUE_EMPTY":
    fails.append(f"a queue with zero rows gave {why['code']}")
why = CU.diagnose_empty_shelf(QUEUED, set(QUEUED), set(), None)
if why["code"] != "NO_QUEUE":
    fails.append(f"a missing loop/render_queue.json gave {why['code']}, so "
                 f"'could not look upstream' reads as 'nothing upstream'")
for code in ("PUBLISH_QUEUE_EMPTY", "NO_QUEUE"):
    d, _ = common.disposition(CU.LANE, code, {}, 1)
    if d != "needs_human":
        fails.append(f"{code} is {d}, not needs_human")

# -- the loader tells missing from empty --------------------------------------
examined += 1
with tempfile.TemporaryDirectory() as td:
    saved = CU.RENDER_QUEUE
    try:
        CU.RENDER_QUEUE = Path(td) / "render_queue.json"
        if CU.handoff_rows() is not None:
            fails.append("handoff_rows() returned rows for a missing file")
        CU.RENDER_QUEUE.write_text(json.dumps({"items": rows(STRANDED)}))
        if [r["slug"] for r in CU.handoff_rows()] != STRANDED:
            fails.append("handoff_rows() did not return the file's rows")
    finally:
        CU.RENDER_QUEUE = saved

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} empty-shelf case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - an empty shelf names its real cause")
