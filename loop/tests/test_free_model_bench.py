"""The free model bench left honest evidence (owner, 2026-10-12).

"do some research to figure out which would be best to put forth?"
loop/bench_free_models.py measures every $0 model in config/llm_routing.json
against the real prompt and the real checks. This pins its newest results:

  A. research/free_model_bench/<latest>.json exists and parses.
  B. Every roster model in config has at least one row, or an explicit
     skipped reason. A bench that could not run passes only when the JSON
     says why (not_run_reason).
  C. No key-like string ("sk-") anywhere in the JSON or markdown.
  D. The markdown names the same winner the JSON ranks first.
  E. Every row carries a failure category from the fixed set.

No network. Hard-fails on zero cases. Re-run the bench whenever the roster
changes; B then fails until it is re-run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "free_model_bench"
CATS = {"passed", "length_only", "dead_url", "structure", "truncated", "empty_or_error"}


def check() -> list[str]:
    fails: list[str] = []
    files = sorted(OUT.glob("????-??-??.json"))
    if not files:
        return ["no research/free_model_bench/<date>.json; run loop/bench_free_models.py"]
    jf = files[-1]
    md = jf.with_suffix(".md")
    try:
        res = json.loads(jf.read_text())
    except ValueError as e:
        return [f"{jf.name} does not parse: {e}"]
    if not md.exists():
        fails.append(f"{md.name} missing next to {jf.name}")
    roster = [m["id"] for m in json.loads(
        (ROOT / "config" / "llm_routing.json").read_text())["models"]]
    rows = res.get("rows", [])
    cases = 0
    if res.get("bench_status") != "ran" and not (res.get("not_run_reason") or "").strip():
        fails.append("bench did not run and records no not_run_reason")
    for m in roster:
        cases += 1
        if not any(r.get("model") == m for r in rows) and \
                not (res.get("skipped", {}).get(m) or "").strip():
            fails.append(f"roster model {m} has no bench row and no skipped reason")
    for r in rows + res.get("expansions", []):
        cases += 1
        if r.get("category") not in CATS:
            fails.append(f"row {r.get('model')}/{r.get('topic')} category "
                         f"{r.get('category')!r} not in {sorted(CATS)}")
    for f in (jf, md):
        if f.exists() and "sk-" in f.read_text():
            fails.append(f"{f.name} contains 'sk-' - a key may have leaked")
    rank = res.get("ranking") or []
    if rows and not rank:
        fails.append("rows present but no ranking")
    if rank and md.exists():
        cases += 1
        m = re.search(r"\*\*Winner:\*\* `([^`]+)`", md.read_text())
        if not m or m.group(1) != rank[0]["model"]:
            fails.append(f"markdown winner {m.group(1) if m else None!r} != JSON "
                         f"rank 1 {rank[0]['model']!r}")
    if not (res.get("verdict") or "").strip():
        fails.append("no verdict")
    if cases == 0:
        fails.append("examined zero cases")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print(f"test_free_model_bench: {'FAILED' if f else 'ok'}")
    sys.exit(1 if f else 0)
