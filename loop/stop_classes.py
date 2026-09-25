"""Every stop kind has exactly one of three classes. None waits on a decision.

Owner's rule, 2026-09-25, verbatim: "Nothing is supposed to wait on the owner.
This should be a rule in the repo so you never forget." (CLAUDE.md, RUNBOOK.md.)

  automated     loop/stop_policy.json `self_resolving`: the loop acts on a
                written rule and logs it; green, capped.
  owner_secret  `owner_action`: ONLY a credential, account or external
                service she alone holds, named in the entry's `holds`
                ({kind, what}); green and self-explaining, capped.
  error         `needs_human`: a real defect; red.

`audit()` lists every stop kind the source can raise (the same collectors
loop/tests/test_every_stop_is_classified.py uses - imported, not copied) plus
every classified code, and returns one row per kind with its class and
anything wrong with it:
  * no class, or more than one;
  * an owner_secret entry without a valid `holds` - which is what a parked
    decision looks like;
  * decision wording ("hers to decide", "a decision for a person", "waiting
    on you" ...) in any policy text or in any stop message/unblock the source
    raises.
loop/validate.py V45 reports it; loop/tests/test_nothing_waits_on_the_owner.py
proves it fails on a planted decision stop.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
POLICY = LOOP / "stop_policy.json"

CLASS_OF_SECTION = {"self_resolving": "automated",
                    "owner_action": "owner_secret",
                    "needs_human": "error"}
HOLD_KINDS = {"credential", "account", "external_service"}

DECISION_WORDING = re.compile(
    r"\b(?:hers to (?:decide|make|start|choose|do)|her (?:decision|call|choice)"
    r"|is hers by|decision for a person|this is the decision point"
    r"|awaiting (?:the owner|her)(?:'s)? (?:decision|confirmation)"
    r"|waiting on (?:you|her|the owner)|only she can (?:decide|choose)"
    r"|owner (?:must|should|has to) decide|deliberately not automatic"
    r"|her promotion decision|until she decides|for her to decide)\b",
    re.I)


def _policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY).read_text())


def _rules(pol: dict) -> dict[str, list[tuple[str, object]]]:
    out: dict[str, list[tuple[str, object]]] = {}
    for sec in CLASS_OF_SECTION:
        for code, rule in (pol.get(sec) or {}).items():
            if not code.startswith("_"):
                out.setdefault(code, []).append((sec, rule))
    return out


def raised_codes() -> set[str]:
    sys.path.insert(0, str(LOOP / "tests"))
    import test_every_stop_is_classified as A                 # noqa: PLC0415
    codes = set(A.literal_codes()) | set(A.GENERATED)
    codes |= {prefix + "*" for prefix in A.FAMILIES}
    # A code BUILT at the call site (named_stop(f"RUNWAY_{level}")) is
    # invisible to a literal scan; its constant prefix is listed as a family
    # so it can never sit unclassified - which is how RUNWAY_WARN stayed a
    # red-by-default stop until 2026-09-25.
    for path in sorted(LOOP.glob("*.py")):
        for n in ast.walk(ast.parse(path.read_text())):
            if (isinstance(n, ast.Call)
                    and getattr(n.func, "attr", None) == "named_stop"
                    and n.args and isinstance(n.args[0], ast.JoinedStr)):
                head = n.args[0].values[0] if n.args[0].values else None
                if isinstance(head, ast.Constant) and head.value:
                    codes.add(head.value + "*")
    return codes


def _texts(rule) -> list[str]:
    if isinstance(rule, str):
        return [rule]
    out = []
    for k in ("why", "escalation"):
        v = rule.get(k)
        if isinstance(v, str):
            out.append(v)
    return out


def source_stop_texts() -> list[tuple[str, str]]:
    """(where, text) for every string a stop in loop/*.py says to a reader:
    named_stop() arguments and `message`/`unblock` values in stop dicts."""
    out = []
    for path in sorted(LOOP.glob("*.py")):
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            strs = []
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "named_stop":
                strs = list(n.args[1:]) + [k.value for k in n.keywords
                                            if k.arg in ("unblock",)]
            elif isinstance(n, ast.Dict):
                strs = [v for k, v in zip(n.keys, n.values)
                        if isinstance(k, ast.Constant)
                        and k.value in ("message", "unblock")]
            for s in strs:
                for c in ast.walk(s):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        out.append((f"{path.name}:{getattr(c, 'lineno', '?')}",
                                    c.value))
    return out


def audit(policy_path: Path | None = None,
          extra_texts: list[tuple[str, str]] | None = None) -> dict:
    pol = _policy(policy_path)
    rules = _rules(pol)
    codes = sorted(raised_codes() | set(rules))
    rows, problems = [], []
    for code in codes:
        homes = rules.get(code, [])
        family = code.endswith("*") and not homes
        if family:
            # A code FAMILY (ANALYTICS_HTTP_*) is classified per member by
            # narrower wildcards (ANALYTICS_HTTP_5* automated, _4* error).
            homes = [h for c in rules if c != code and c.startswith(code[:-1])
                     for h in rules[c]]
        elif not homes:
            wild = [c for c in rules if c.endswith("*")
                    and code.startswith(c[:-1])]
            homes = [h for c in wild for h in rules[c]]
        cls = sorted({CLASS_OF_SECTION[s] for s, _ in homes})
        why = []
        if not cls:
            why.append("no class")
        elif len(cls) > 1 and not family:
            why.append(f"more than one class: {cls}")
        for sec, rule in homes:
            if sec == "owner_action":
                h = rule.get("holds") if isinstance(rule, dict) else None
                if not (isinstance(h, dict) and h.get("kind") in HOLD_KINDS
                        and h.get("what")):
                    why.append("owner stop names no credential, account or "
                               "external service it holds (`holds`) - a "
                               "parked decision")
            for t in _texts(rule):
                m = DECISION_WORDING.search(t)
                if m:
                    why.append(f"policy text asks for an owner decision: "
                               f"{m.group(0)!r}")
        rows.append({"code": code,
                     "class": ("/".join(cls) if family else
                               cls[0] if len(cls) == 1 else None),
                     "problems": why})
        problems += [f"{code}: {w}" for w in why]
    for where, t in source_stop_texts() + list(extra_texts or []):
        m = DECISION_WORDING.search(t)
        if m:
            problems.append(f"{where}: a stop asks for an owner decision: "
                            f"{m.group(0)!r}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["class"] or "unclassed"] = counts.get(r["class"] or "unclassed", 0) + 1
    return {"rows": rows, "problems": problems, "counts": counts}


if __name__ == "__main__":
    a = audit()
    for r in a["rows"]:
        print(f"{r['class'] or '-':<13} {r['code']}"
              + (f"   !! {'; '.join(r['problems'])}" if r["problems"] else ""))
    print(a["counts"])
    for p in a["problems"]:
        print("PROBLEM:", p)
    sys.exit(1 if a["problems"] else 0)
