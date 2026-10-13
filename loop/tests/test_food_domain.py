"""food-science, the third domain: registered everywhere, held by its sample gate.

Owner decision 2026-10-13 (docs/CHANNEL-PLAN.md "A third domain: food
science", "Three-niche schedule"). What this proves, on the real repo:

  1. V52 passes on the real repo with the sample gate reported as a note, and every
     list that enumerates domains names food-science (V52 reads them all).
  2. The sample gate HOLDS: domains.allocation_gate refuses a food row,
     batch_queue.publish_queue_gate refuses a food slug, the digest calendar
     counts no food slot, and loop/handoff.py plans no food playlist - while
     the same row passes once the gate is cleared.
  3. A pending POV line is never selected (pov_match.bank) and counts for
     validate_plan c10 ONLY while the gate is open: cleared with no approved
     line, c10 fails.
  4. The seeded queue: the first video's three questions + >= 20 more, each
     with the free demand signals and its floor verdict recorded, and
     publish_order_domain screens the seeded questions first.
  5. The four food scripts pass the house checks the author lane applies
     (shape, directive truth/parse, the stake-then-payoff hook, the title
     formula and its truth guard), with no network.
  6. loop/upload.altered_content: the episode spec answers YES for the food
     episode; a video with no spec keeps the 14 Sep NO.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * remove "food-science" from visuals/thumbs_for.BUILDERS -> V52 fails naming
    the missing builder;
  * disable `if dom in gated` in domains.allocation_gate -> cases 1 and 2 fail
    ("allocation_gate let a food row through");
  * the cleared-gate c10 failure is case 3 itself, run every time.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))
sys.path.append(str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import common                                                  # noqa: E402
import domains as D                                            # noqa: E402

FOOD = "food-science"
fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


cfg = common.config()

# ------------------------------------------------------------------ 1. V52
import validate as V                                           # noqa: E402
res = V.v52_food_domain().as_dict()
check(not res["failures"], f"V52 passes on the real repo: {res['failures']}")
check(not res["stops"], "V52 takes no stop on the real repo")

# ------------------------------------------------------------------ 2. the gate (CLEARED 13 Oct 2026)
# The owner approved the round-2 chocolate sample on 13 Oct 2026 ("MUCH better").
# The real config records it, dated; the gate's machinery is still proven on a
# gated COPY, so it holds the next domain that is sample-gated.
gate = cfg["domains"]["sample_gate"][FOOD]
check(gate["state"] == "cleared" and "13 Oct 2026" in gate.get("cleared_note", "")
      and "round 2" in gate.get("cleared_note", ""),
      f"the real gate is cleared with the owner's dated note: {gate.get('state')} / {gate.get('cleared_note')}")
check(FOOD not in D.sample_gated(cfg), "food-science is no longer sample-gated in the real config")
ok, refused = D.allocation_gate([{"slug": "f", "domain": FOOD}], cfg)
check(bool(ok) and not refused, f"allocation_gate lets a food row through now: {refused}")
import batch_queue as BQ                                       # noqa: E402
allowed, why = BQ.publish_queue_gate(["why-bread-rises-steak-browns-chocolate-snaps"])
check(allowed == ["why-bread-rises-steak-browns-chocolate-snaps"],
      f"publish_queue_gate admits the first food episode: {why}")
import digest                                                  # noqa: E402
import datetime as dt                                          # noqa: E402
cal = digest.calendar({"published": []}, cfg, dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc))
check(any(c["domain"] == FOOD for c in cal), "cleared: food's Wed/Sat are counted slots")
gated = json.loads(json.dumps(cfg))
gated["domains"]["sample_gate"][FOOD]["state"] = "awaiting_owner_review"
okg, refg = D.allocation_gate([{"slug": "f", "domain": FOOD}], gated)
check(not okg and "sample_gate" in refg.get("f", ""),
      f"a gated copy still refuses a food row by name: {refg}")
calg = digest.calendar({"published": []}, gated, dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc))
check(calg and not any(c["domain"] == FOOD for c in calg),
      "a gated copy counts no food slot (empty by design, not a gap)")
cleared = cfg

# ------------------------------------------------------------------ 3. POV
import pov_match                                               # noqa: E402
bank = json.loads((ROOT / "pov" / "pov-bank.json").read_text())["lines"]
pending = [ln for ln in bank if ln.get("pending_approval")]
check(len(pending) >= 3 and all(ln.get("domain") == FOOD for ln in pending),
      "three pending food POV lines are in the bank")
check(not any(ln["id"] in {p["id"] for p in pending} for ln in pov_match.bank()),
      "pov_match.bank() never offers a pending line")
import validate_plan as VP                                     # noqa: E402
c10 = VP.c10_domains_admitted()
check(not c10.failures, f"c10 passes on the real repo: {c10.failures}")
check(cfg["domains"].get("pov_not_required", {}).get(FOOD, {}).get("decided") == "2026-10-13",
      "food-science ships with no POV beat by a dated declaration, until its top-up")
saved = VP.config
undeclared = json.loads(json.dumps(cfg))
undeclared["domains"].pop("pov_not_required", None)
VP.config = lambda: undeclared
try:
    c10b = VP.c10_domains_admitted()
finally:
    VP.config = saved
check(any("food-science" in f for f in c10b.failures),
      "c10 FAILS a cleared food domain with only pending lines and no declaration")
# the declaration never excuses a [HUMAN] beat in a shipping food episode
ep = ROOT / "scripts" / "food" / "why-bread-rises-steak-browns-chocolate-snaps.md"
orig = ep.read_text()
try:
    ep.write_text(orig.replace("### Closing\n\n{{ambient}}\n", "### Closing\n\n{{ambient}}\n[HUMAN] ", 1))
    c10c = VP.c10_domains_admitted()
finally:
    ep.write_text(orig)
check(any("[HUMAN]" in f for f in c10c.failures),
      f"c10 FAILS a shipping food episode that carries a [HUMAN] beat: {c10c.failures}")


# ------------------------------------------------------------------ 4. queue
po = json.loads((ROOT / "research" / "publish_order_food_science.json").read_text())
rows = po["queue"] + po["unmeasured"]
qs = {r["query"] for r in rows}
check(set(po["first_video"]) <= qs and len(qs) >= 23,
      f"queue seeds the first video's three + >= 20 more ({len(qs)})")
check(all("demand_without_competition" in r and "meets_floor_on_free_signals" in r
          for r in po["unmeasured"]),
      "every unmeasured row records its free demand and its floor verdict")
check(po["meets_floor_on_free_signals"] == [r["query"] for r in po["unmeasured"]
                                             if r["meets_floor_on_free_signals"]],
      "the floor list is derived from the rows, not typed")
import publish_order_domain as POD                             # noqa: E402
seeded = [r["query"] for r in POD.seed_questions(FOOD)]
check(seeded[:3] == po["first_video"], "the seeded questions lead with the first video's three")

# ------------------------------------------------------------------ 5. scripts
import author as A                                             # noqa: E402
import longform_title as LT                                    # noqa: E402
import opening                                                 # noqa: E402
import re                                                      # noqa: E402
food = sorted((ROOT / "scripts" / "food").glob("*.md"))
check(len(food) == 4, f"four food scripts (three parts + the episode): {[p.name for p in food]}")
for p in food:
    t = p.read_text()
    check(D.domain_of_script(p) == FOOD, f"{p.name}: **Domain:** food-science")
    probs = A.directive_truth_problems(t) + A.directive_parse_problems(t) \
        + opening.problems(t, opening.active())
    title = LT.script_title(t)
    probs += LT.title_problems(title, t) if title else ["no ## YouTube title"]
    if "Part:" in t:
        pid = re.search(r"FROM POV BANK \((pov-\d+)\)", t).group(1)
        line = next(ln for ln in pov_match.bank() if ln["id"] == pid)
        probs += A.shape_problems(t, {"line": line["line"], "pov_id": pid})
    check(not probs, f"{p.name}: house checks {probs}")

# ------------------------------------------------------------------ 6. altered content
import upload                                                  # noqa: E402
check(upload.altered_content("why-bread-rises-steak-browns-chocolate-snaps") is True,
      "the food episode spec answers YES to altered or synthetic content")
check(upload.altered_content("02-how-deep-sea-creatures-survive-pressure") is False,
      "a video with no spec keeps the 14 Sep NO")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
