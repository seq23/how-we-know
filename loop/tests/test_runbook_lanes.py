"""RUNBOOK.md's "Lanes" table names every loop-state lane, and its "Calls a
model?" column matches the code.

Owner, 2026-10-12: one row per scheduled lane, so a new lane cannot be added
without a row. Every workflow in the `loop-state` concurrency group must have
a row; every backticked lane in the table must be a real workflow; the model
column says "yes" exactly where loop/tests/test_claude_subscription_route.py
derives (from the call graph to llm_router.complete()) that the lane reaches a
model. Hard-fails on zero rows.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import test_claude_subscription_route as S  # noqa: E402

RUNBOOK = ROOT / "RUNBOOK.md"


def table_rows(text: str) -> dict[str, str]:
    """{lane name: calls-a-model cell} for rows naming a workflow in backticks."""
    m = re.search(r"^## Lanes\n(.*?)(?=^## )", text, re.M | re.S)
    if not m:
        return {}
    rows = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].startswith("`"):
            continue
        rows[cells[0].strip("`")] = cells[-1].lower()
    return rows


def check() -> list[str]:
    fails = []
    rows = table_rows(RUNBOOK.read_text())
    if not rows:
        return ["RUNBOOK.md has no '## Lanes' table rows - examined ZERO lanes"]
    wfs = {p.stem: p.read_text() for p in S.WORKFLOWS.glob("*.yml")}
    grouped = {n for n, t in wfs.items()
               if re.search(r"^\s*group:\s*loop-state\s*$", t, re.M)}
    if not grouped:
        fails.append("no workflow is in the loop-state group - the scan is broken")
    for n in sorted(grouped - set(rows)):
        fails.append(f"{n}.yml is in the loop-state queue but has no row in "
                     f"RUNBOOK.md's Lanes table")
    for n in sorted(set(rows) - set(wfs)):
        fails.append(f"Lanes table names `{n}`, which is not a workflow")
    _, lanes = S.lane_problems(S.router_reaching_modules())
    model_lanes = {Path(x).stem for x in lanes}
    for n, cell in rows.items():
        if n not in wfs:
            continue
        says = cell.startswith("yes")
        if says != (n in model_lanes):
            fails.append(f"Lanes table says {n} calls a model: {cell!r}; the "
                         f"call graph says {'yes' if n in model_lanes else 'no'}")
    print(f"inspected {len(rows)} Lanes row(s), {len(grouped)} loop-state "
          f"workflow(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every lane has a row" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
