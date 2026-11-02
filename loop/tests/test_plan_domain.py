"""A domain's graphics never appear in another domain's video (visuals/plan_domain.py, V75).

CONFIRMED 2026-11-01 (the owner's screenshot): the rice Short showed the deep-sea
"CHALLENGER DEEP ... METRES" depth gauge. visuals/planner.py chose its signals at
import from HWK_DOMAIN (default deep sea; the batch's plan step never set it) and
had no food-science row.

  1. planner.plan() on the real rice and welding-arc scripts, with HWK_DOMAIN UNSET
     (the batch's plan step), emits no foreign segment - and the beat narration is
     identical to the frozen plan (the audio stays valid).
  2. An undeclared domain raises; it is never planned with the ocean's table.
  3. plan_domain.foreign() sees an ocean gauge and an ocean-default stat card in a
     food plan, and nothing in a deep-sea one.
  4. assemble.assemble() refuses a foreign plan before rendering a frame.
  5. V75 passes on the repo and FAILS when the rice plan's depth gauge is put back
     (negative proof on a copy of plans/).
  6. sweep() on a fixture tree re-plans a foreign plan beat for beat, retires its
     render into renders/superseded-domain/ and records its sha256.

NEGATIVE PROOF (by hand, 2026-11-01): restoring the import-time table
(`SIGNALS, COLD_OPEN_SEGMENT = _SIGNALS_BY_DOMAIN.get(_design.DOMAIN, ...)` used by
plan()) makes checks 1 and 5 fail; restored, all pass.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "loop"))
os.environ["LOOP_DRY_RUN"] = "1"
os.environ.pop("HWK_DOMAIN", None)

import plan_domain as PD                                       # noqa: E402
import planner                                                 # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


# 1
for slug, dom in (("why-does-rice-get-sticky", PD.FOOD),
                  ("how-hot-does-a-welding-arc-get", PD.MAT)):
    new = planner.plan(str(ROOT / "scripts" / f"{slug}.md"))
    old = json.loads((ROOT / "plans" / f"{slug}.json").read_text())
    check(not PD.foreign(new, dom), f"1 {slug}: no foreign segment with HWK_DOMAIN unset "
                                    f"({sorted({x[1] for x in PD.foreign(new, dom)})})")
    check([b["narration"] for b in new] == [b["narration"] for b in old],
          f"1 {slug}: beats identical to the narrated plan")

# 2
try:
    planner.signals_for("underwater-basket-weaving")
    check(False, "2 an undeclared domain raises")
except KeyError:
    check(True, "2 an undeclared domain raises")

# 3
fx = [{"segment": "depth_descent", "args": {}}, {"segment": "text_beat", "args": {}},
      {"segment": "stat_card", "args": {}}, {"segment": "thermal_ascent", "args": {}}]
check([x[0] for x in PD.foreign(fx, PD.FOOD)] == [0, 2], "3 food: gauge + ocean-default card seen")
check([x[0] for x in PD.foreign(fx, PD.DEEP)] == [3], "3 deep sea: only the heat device is foreign")

# 4
import assemble                                                # noqa: E402
with tempfile.TemporaryDirectory() as td:
    pf = Path(td) / "p.json"
    pf.write_text(json.dumps(fx[:1]))
    os.environ["HWK_DOMAIN"] = PD.FOOD
    try:
        assemble.assemble(str(pf), str(Path(td) / "o.mp4"), audio_dir=td)
        check(False, "4 assemble refuses a foreign plan")
    except ValueError as e:
        check("PLAN_DOMAIN_FOREIGN" in str(e), "4 assemble refuses a foreign plan")
    finally:
        os.environ.pop("HWK_DOMAIN", None)

# 5
import validate as V                                           # noqa: E402
check(V.v75_plan_domain().ok, "5 V75 passes on the repo")
with tempfile.TemporaryDirectory() as td:
    pd = Path(td) / "plans"
    shutil.copytree(ROOT / "plans", pd)
    rice = json.loads((pd / "why-does-rice-get-sticky.json").read_text())
    rice[0]["segment"], rice[0]["args"] = "depth_descent", {}
    (pd / "why-does-rice-get-sticky.json").write_text(json.dumps(rice))
    r = V.v75_plan_domain(plans_dir=pd)
    check(not r.ok and any("why-does-rice-get-sticky" in f for f in r.failures),
          "5 NEGATIVE: V75 fails with the rice depth gauge put back")

# 6
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    for d in ("plans", "renders", "scripts", "loop/state"):
        (t / d).mkdir(parents=True)
    slug = "why-does-rice-get-sticky"
    shutil.copy(ROOT / "scripts" / f"{slug}.md", t / "scripts" / f"{slug}.md")
    bad = json.loads((ROOT / "plans" / f"{slug}.json").read_text())
    bad[0]["segment"], bad[0]["args"] = "depth_descent", {}
    (t / "plans" / f"{slug}.json").write_text(json.dumps(bad))
    (t / "renders" / f"{slug}-final.mp4").write_bytes(b"old cut")
    (t / "loop/state/ledger.json").write_text(json.dumps({"published": []}))
    saved = (PD.PLANS, PD.RENDERS, PD.STATE, PD.SUPERSEDED, PD.ROOT)
    PD.PLANS, PD.RENDERS, PD.STATE = t / "plans", t / "renders", t / "loop/state"
    PD.SUPERSEDED = PD.STATE / "superseded_renders.json"
    orig_domain_of, PD.domain_of = PD.domain_of, (lambda s: PD.FOOD)
    PD.ROOT = t
    try:
        rc = PD.sweep()
    finally:
        PD.PLANS, PD.RENDERS, PD.STATE, PD.SUPERSEDED, PD.ROOT = saved
        PD.domain_of = orig_domain_of
    fixed = json.loads((t / "plans" / f"{slug}.json").read_text())
    sup = json.loads((t / "loop/state/superseded_renders.json").read_text())
    check(rc == 0 and not PD.foreign(fixed, PD.FOOD) and len(fixed) == len(bad),
          "6 sweep re-plans beat for beat with no foreign segment")
    check(not (t / "renders" / f"{slug}-final.mp4").exists()
          and (t / "renders/superseded-domain" / f"{slug}-final.mp4").exists()
          and sup.get(slug, {}).get("sha256"), "6 sweep retires the render and records its sha256")

print(f"\n{examined} checks, {len(fails)} failed")
if not examined:
    sys.exit("FAIL: examined nothing")
sys.exit(1 if fails else 0)
