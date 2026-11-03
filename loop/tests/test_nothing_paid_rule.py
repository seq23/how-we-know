"""The "nothing paid" rule is where code reads it (owner, 2026-10-11).

Owner policy, verbatim: "nothing should be paid ... cut the probes and make
them free." Until 2026-10-25 that rule lived only in
`docs/cost/zero-paid-llm.md` - a document nothing read and CLAUDE.md never
mentioned, so an agent starting in this repo could not find it. A
specification no code reads is a wish.

WHAT THIS PROVES (doc-wording checks removed 2026-11-01; behaviour only):
  1. V74 (loop/validate.py) passes on the real repo and is registered in
     validate.run_all;
  2. NEGATIVE PROOF, once per failure shape, on scratch copies of
     config/llm_routing.json: max_cost_usd above 0, paid_fallback true, no
     snapshot_date, a paid model in the list, an API key on the subscription
     route and a Gemini route off the free tier each make V74 fail.
Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import validate                                            # noqa: E402

fails: list[str] = []
examined = 0

# ------------------------------------------------------------ 2. real repo
r = validate.v74_nothing_paid_rule()
examined += r.examined
if not r.ok:
    fails.append(f"V74 is not green on the real repo: {r.failures[:3]}")
if r.examined < 8:
    fails.append(f"V74 examined only {r.examined} claim(s)")
if "v74_nothing_paid_rule()" not in (LOOP / "validate.py").read_text():
    fails.append("V74 is not registered in validate.run_all")

# ------------------------------------------------------------ 4. negative
SCRATCH: list[str] = []


def planted(mutate) -> validate.Result:
    """Run V74 against a scratch copy of everything it reads."""
    base = Path(tempfile.mkdtemp(prefix="nothing-paid-"))
    SCRATCH.append(str(base))
    (base / "config").mkdir()
    shutil.copy2(ROOT / "config" / "llm_routing.json",
                 base / "config" / "llm_routing.json")
    mutate(base)
    return validate.v74_nothing_paid_rule(root=base)


def cfg(base: Path, fn) -> None:
    p = base / "config" / "llm_routing.json"
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


# The scratch copy itself must be green, or every negative proof below is
# proving nothing but a broken fixture.
examined += 1
if not planted(lambda b: None).ok:
    fails.append("the unmutated scratch copy already fails V74")

CASES = [
    ("max_cost_usd above 0",
     lambda b: cfg(b, lambda d: d.__setitem__("max_cost_usd", 5)),
     "max_cost_usd"),
    ("paid_fallback true",
     lambda b: cfg(b, lambda d: d.__setitem__("paid_fallback", True)),
     "paid_fallback"),
    ("no snapshot_date",
     lambda b: cfg(b, lambda d: d.pop("snapshot_date", None)),
     "snapshot_date"),
    ("a paid model in the list",
     lambda b: cfg(b, lambda d: d["models"].append("anthropic/claude-opus-4.5")),
     "claude-opus-4.5"),
    ("an API key on the subscription route",
     lambda b: cfg(b, lambda d: d.setdefault("subscription_route", {
         "provider": "claude-code", "env": "CLAUDE_CODE_OAUTH_TOKEN",
         "model": "opus"}).__setitem__("env", "ANTHROPIC_API_KEY")),
     "subscription_route"),
    ("gemini_route not free-tier",
     lambda b: cfg(b, lambda d: d["gemini_route"].__setitem__(
         "free_tier_only", False)),
     "free_tier"),
]

for name, mutate, expect in CASES:
    examined += 1
    res = planted(mutate)
    if res.ok:
        fails.append(f"V74 passed with {name}")
    elif not any(expect.lower() in f.lower() for f in res.failures):
        fails.append(f"V74 failed on {name}, but said {res.failures[:2]} - "
                     f"nothing about {expect!r}")

for d in SCRATCH:
    shutil.rmtree(d, ignore_errors=True)

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s); {len(CASES)} negative proof(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
