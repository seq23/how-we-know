"""One definition of a food video, read by the producer AND the contract.

THE INCIDENT (#235, 23-25 Oct 2026). loop/backfill.food_hold() decided "food"
by the domain; loop/batch_queue.py decided it by "is scripts/food/<slug>.md on
disk?". A food-science row with no food-pipeline script was therefore the
Monday lane's to author and the Mac batch's to render: mon-draft (6b650ac,
19 Oct) wrote six food topics into scripts/*.md, the batch rendered them as
~11-minute explainers with no episode spec, the contract held all six on
every upload run, and NOTHING_SHELVED blamed the Mac ("shelved without a
thumbnail") until its streak exited 3 and opened a needs-you issue.

WHAT THIS PROVES, on the real repository and the real loop/stop_policy.json:
  1. Every food-science queue row is is_food(), and NO food row is in the
     Monday lane's list (unwritten_entries) or the Mac batch's
     (written_entries) - the producer side cannot make one the wrong way.
  2. A non-food unwritten row is still the Monday lane's.
  3. The six batch-made food renders are held by the contract by NAME, with
     the true reason, not "no spec" - and food_hold reads is_food.
  4. The empty-shelf diagnosis never counts food or unwritten rows as
     "waiting on the Mac", never calls a food hold a missing thumbnail, and
     names them under QUEUE_AWAITING_PRODUCTION, which is self-resolving at
     the streak that paged on 23 Oct (exit 0).
  5. A written, non-food row still waiting IS NOTHING_SHELVED.
  6. No reader keeps its own copy: backfill.py, batch_queue.py and
     cloud_upload.py compare to "food-science" nowhere except FOOD_DOMAIN.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_STOPS_DIR"] = tempfile.mkdtemp(prefix="food-def-stops-")

import batch_queue as BQ                                  # noqa: E402
import backfill                                           # noqa: E402
import cloud_upload as CU                                 # noqa: E402
import common                                             # noqa: E402

fails: list[str] = []
examined = 0

BATCH_MADE = ["why-does-chocolate-taste-so-good", "why-does-steak-taste-better-seared",
              "why-is-my-bread-not-rising", "how-does-butter-get-made-from-cream",
              "why-does-rice-get-sticky", "why-does-meat-need-to-rest-after-cooking"]

# -- 1. producer side --------------------------------------------------------
food_rows = [r for r in BQ._raw_entries() if BQ._row_domain(r) == BQ.FOOD_DOMAIN]
if not food_rows:
    fails.append("no food-science queue row found - this test cannot reach what it governs")
unwritten = {r["slug"] for r in BQ.unwritten_entries()}
written = {r["slug"] for r in BQ.written_entries()}
for r in food_rows:
    examined += 1
    if not BQ.is_food(r) or not BQ.is_food(r["slug"]):
        fails.append(f"{r['slug']}: a food-science row is not is_food()")
    if r["slug"] in unwritten:
        fails.append(f"{r['slug']}: a food row is in the Monday lane's unwritten_entries()")
    if r["slug"] in written:
        fails.append(f"{r['slug']}: a food row is in the Mac batch's written_entries()")

# -- 2. a non-food unwritten row is still Monday's ---------------------------
nonfood_unwritten = [r for r in BQ.queued_entries()
                     if not BQ.is_food(r) and not BQ.food_made(r["slug"])
                     and not (ROOT / "scripts" / f"{r['slug']}.md").exists()
                     and r["slug"] not in BQ.promotion_holds()]
for r in nonfood_unwritten[:5]:
    examined += 1
    if r["slug"] not in unwritten:
        fails.append(f"{r['slug']}: a non-food unwritten row left the Monday lane")

# -- 3. the six batch-made renders are held by name, truthfully -------------
for s in BATCH_MADE:
    if not (ROOT / "scripts" / f"{s}.md").exists():
        continue
    examined += 1
    if not BQ.food_batch_made(s):
        fails.append(f"{s}: not recognised as a food video made by the batch")
    why = backfill.food_hold(s) or ""
    if "made by the nightly batch" not in why:
        fails.append(f"{s}: food_hold says {why[:80]!r}, not the real reason")
if backfill.food_hold("how-deep-is-the-ocean-really") is not None and \
        not BQ.is_food("how-deep-is-the-ocean-really"):
    fails.append("food_hold held a non-food slug")
src = (LOOP / "backfill.py").read_text()
fh = src[src.index("def food_hold"):src.index("class CadenceExceedsLadder")]
if "is_food(" not in fh:
    fails.append("backfill.food_hold does not read batch_queue.is_food")

# -- 4. the diagnosis: food + unwritten are not the Mac's -------------------
class Shelf:
    def head(self, key):                     # renders shelved, no thumbnail
        return {"size": 1} if key.endswith(".mp4") else None

STEEL = ["is-damascus-steel-better", "does-damascus-steel-rust"]
FOOD_UNMADE = ["why-does-cheese-melt"]
queued = BATCH_MADE + FOOD_UNMADE + STEEL
why = CU.diagnose_empty_shelf(queued, set(), set(), [], shelf=Shelf(),
                              food=set(BATCH_MADE + FOOD_UNMADE),
                              written=set(BATCH_MADE))
examined += 1
if why["code"] != "QUEUE_AWAITING_PRODUCTION":
    fails.append(f"food + unwritten rows diagnosed {why['code']}, not QUEUE_AWAITING_PRODUCTION")
d = why["detail"]
if d.get("awaiting_authoring") != STEEL:
    fails.append(f"awaiting_authoring = {d.get('awaiting_authoring')}, not {STEEL}")
if d.get("food_made_by_batch_held") != BATCH_MADE:
    fails.append("the batch-made food renders are not named as held")
if "thumbnail" in why["message"].lower() or "push-to-r2" in (why["message"] + why["unblock"]):
    fails.append("a food hold was blamed on a missing thumbnail / the Mac's push")
for streak in (1, 11, 14):
    disp, _ = common.disposition("cloud-upload", why["code"], why["detail"], streak,
                                 held_items=why["held_items"], unblock=why["unblock"])
    examined += 1
    if disp not in common.GREEN_DISPOSITIONS:
        fails.append(f"QUEUE_AWAITING_PRODUCTION at streak {streak} is {disp} (exits 3)")

# -- 5. a written non-food row waiting IS the Mac's -------------------------
why = CU.diagnose_empty_shelf(queued + ["ep-written"], set(), set(), [], shelf=Shelf(),
                              food=set(BATCH_MADE + FOOD_UNMADE),
                              written=set(BATCH_MADE) | {"ep-written"})
examined += 1
if why["code"] != "NOTHING_SHELVED" or why["detail"].get("awaiting_mac") != ["ep-written"]:
    fails.append(f"a written batch row gave {why['code']} / {why['detail'].get('awaiting_mac')}")
if set(why["detail"].get("shelved_without_thumbnail") or []) & set(BATCH_MADE):
    fails.append("a food-held render was reported as shelved without a thumbnail")

# -- 6. no reader keeps its own copy ----------------------------------------
for f in ("backfill.py", "batch_queue.py", "cloud_upload.py"):
    examined += 1
    text = (LOOP / f).read_text()
    hits = [m.start() for m in re.finditer(r'[=!]=\s*"food-science"', text)]
    if hits:
        fails.append(f"loop/{f} compares to \"food-science\" itself ({len(hits)}x) - read batch_queue.is_food")

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} food-definition case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - one definition of a food video, read by producer and contract")
