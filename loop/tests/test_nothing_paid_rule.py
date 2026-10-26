"""The "nothing paid" rule is where code reads it (owner, 2026-10-11).

Owner policy, verbatim: "nothing should be paid ... cut the probes and make
them free." Until 2026-10-25 that rule lived only in
`docs/cost/zero-paid-llm.md` - a document nothing read and CLAUDE.md never
mentioned, so an agent starting in this repo could not find it. A
specification no code reads is a wish.

WHAT THIS PROVES:
  1. CLAUDE.md says "nothing paid", as a rule under "Rules that are not up for
     debate", and points at docs/cost/zero-paid-llm.md;
  2. V74 (loop/validate.py) passes on the real repo, examines a non-trivial
     number of claims, and is registered in validate.run_all;
  3. the document names the code that enforces it, and every named stop it
     promises is a code a loop module can actually raise;
  4. NEGATIVE PROOF, once per failure shape, on scratch copies of the repo: the
     rule removed from CLAUDE.md, the rule demoted out of that section, the
     pointer to the document removed, the document deleted, a promised stop no
     source raises, max_cost_usd above 0, paid_fallback true, a paid model in
     the list, and an API key on the subscription route each make V74 fail.
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

DOC = "docs/cost/zero-paid-llm.md"
fails: list[str] = []
examined = 0

# ------------------------------------------------------------ 1. the rule
examined += 1
claude = (ROOT / "CLAUDE.md").read_text()
if "nothing paid" not in " ".join(claude.split()).lower():
    fails.append('CLAUDE.md does not say "nothing paid"')
examined += 1
if DOC not in claude:
    fails.append(f"CLAUDE.md does not point at {DOC}")
examined += 1
body = claude.split("## Rules that are not up for debate")[-1].split("\n## ")[0]
if "nothing paid" not in " ".join(body.split()).lower():
    fails.append('"nothing paid" is not a rule that is not up for debate')

# ------------------------------------------------------------ 2. real repo
r = validate.v74_nothing_paid_rule()
examined += r.examined
if not r.ok:
    fails.append(f"V74 is not green on the real repo: {r.failures[:3]}")
if r.examined < 15:
    fails.append(f"V74 examined only {r.examined} claim(s)")
if "v74_nothing_paid_rule()" not in (LOOP / "validate.py").read_text():
    fails.append("V74 is not registered in validate.run_all")

# ------------------------------------------------------------ 3. the document
examined += 1
doc = (ROOT / DOC).read_text()
for name in ("config/llm_routing.json", "loop/llm_router.py"):
    examined += 1
    if name not in doc:
        fails.append(f"{DOC} does not name {name}")

# ------------------------------------------------------------ 4. negative
SCRATCH: list[str] = []


def planted(mutate) -> validate.Result:
    """Run V74 against a scratch copy of everything it reads."""
    base = Path(tempfile.mkdtemp(prefix="nothing-paid-"))
    SCRATCH.append(str(base))
    shutil.copy2(ROOT / "CLAUDE.md", base / "CLAUDE.md")
    (base / "docs" / "cost").mkdir(parents=True)
    shutil.copy2(ROOT / DOC, base / DOC)
    (base / "config").mkdir()
    shutil.copy2(ROOT / "config" / "llm_routing.json",
                 base / "config" / "llm_routing.json")
    (base / "loop").mkdir()
    for f in (ROOT / "loop").glob("*.py"):
        shutil.copy2(f, base / "loop" / f.name)
    mutate(base)
    return validate.v74_nothing_paid_rule(root=base)


def edit(base: Path, rel: str, fn) -> None:
    p = base / rel
    p.write_text(fn(p.read_text()))


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
    ("the rule removed from CLAUDE.md",
     lambda b: edit(b, "CLAUDE.md",
                    lambda t: t.replace("Nothing paid", "Spend freely")),
     "nothing paid"),
    ("the rule demoted out of the section",
     lambda b: edit(b, "CLAUDE.md", lambda t: t.replace(
         "## Rules that are not up for debate",
         "## Rules that are not up for debate\n\n## Asides\n", 1)),
     "up for debate"),
    ("the pointer to the document removed",
     lambda b: edit(b, "CLAUDE.md", lambda t: t.replace(DOC, "docs/nowhere.md")),
     DOC),
    ("the document deleted",
     lambda b: (b / DOC).unlink(),
     DOC),
    ("the document stops naming the router",
     lambda b: edit(b, DOC,
                    lambda t: t.replace("loop/llm_router.py", "the router")),
     "loop/llm_router.py"),
    ("a promised stop no source raises",
     lambda b: edit(b, DOC, lambda t: t + "\n`OPENROUTER_INVENTED_STOP`\n"),
     "OPENROUTER_INVENTED_STOP"),
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
     lambda b: cfg(b, lambda d: d["subscription_route"].__setitem__(
         "env", "ANTHROPIC_API_KEY")),
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
