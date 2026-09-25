"""Nothing waits on the owner - a rule the code reads, not a wish.

Owner's rule, 2026-09-25, verbatim: "Nothing is supposed to wait on the owner.
This should be a rule in the repo so you never forget."

WHAT THIS PROVES:
  1. CLAUDE.md and RUNBOOK.md carry the rule sentence, verbatim, at the top
     (a specification no code reads is a wish);
  2. V45 (loop/stop_classes.py) passes on the real repo: every stop kind is
     automated, a secret only she holds, or an error, and none asks her for a
     decision - and it lists a non-trivial number of kinds;
  3. NEGATIVE PROOF, once per failure shape, on scratch copies of the policy:
     a planted owner stop with no `holds`, a planted decision sentence, and a
     raised code with no class each make the audit fail;
  4. the codes that used to park a decision are now automated policy
     (SHORTS_INVENTORY_EXHAUSTED, CADENCE_SCALE_WITHHELD,
     SCRIPTS_AWAITING_PROMOTION_RUNWAY_CRITICAL, INSUFFICIENT_DOMAIN_EVIDENCE,
     QUEUE_DECAYED_BUT_UNMEASURED, NO_REPLACEMENT_DOMAIN, RUNWAY_WARN), and
     FORMAT_PROBLEM is no stop at all;
  5. an unarmed lane arms itself when its secrets are present, and stops -
     naming the missing secret - only when one is absent.
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
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import stop_classes as SC                                  # noqa: E402

RULE = ("Nothing waits on the owner. A finding becomes an action with a "
        "measurement, never a question. Only a secret or an account she alone "
        "holds may stop, and that stop is green and self-explaining.")

fails: list[str] = []
examined = 0

# ------------------------------------------------------------ 1. the rule
for doc in ("CLAUDE.md", "RUNBOOK.md"):
    examined += 1
    text = (ROOT / doc).read_text()
    flat = " ".join(text.split())
    if RULE not in flat:
        fails.append(f"{doc} does not carry the rule sentence verbatim")
    elif flat.index(RULE) > 400:
        fails.append(f"{doc} carries the rule, but not at the top")

# ------------------------------------------------------------ 2. real repo
a = SC.audit()
examined += len(a["rows"])
if len(a["rows"]) < 100:
    fails.append(f"the audit listed only {len(a['rows'])} stop kinds")
if a["problems"]:
    fails.append(f"V45 fails on the real repo: {a['problems'][:5]}")
import validate                                            # noqa: E402

r = validate.v45_nothing_waits_on_the_owner()
examined += 1
if not r.ok or r.examined < 100:
    fails.append(f"V45 not green on the real repo: {r.failures[:3]}")
if "v45_nothing_waits_on_the_owner()" not in (LOOP / "validate.py").read_text():
    fails.append("V45 is not registered in validate.run_all")

# ------------------------------------------------------------ 3. negative
pol = json.loads(SC.POLICY.read_text())


def planted(mutate) -> dict:
    p = json.loads(json.dumps(pol))
    mutate(p)
    path = Path(tempfile.mkdtemp(prefix="policy-")) / "stop_policy.json"
    path.write_text(json.dumps(p))
    return SC.audit(policy_path=path)


examined += 1
res = planted(lambda p: p["owner_action"].__setitem__(
    "PICK_A_THUMBNAIL_STYLE", {"why": "Two styles tested; choose one.",
                               "max_consecutive": 3}))
if not any("PICK_A_THUMBNAIL_STYLE" in x and "holds" in x for x in res["problems"]):
    fails.append("an owner stop naming no secret it holds passed the audit")
examined += 1
res = planted(lambda p: p["self_resolving"]["QUOTA_EXHAUSTED"].__setitem__(
    "why", "The allowance is spent; whether to buy more is her decision."))
if not any("QUOTA_EXHAUSTED" in x and "decision" in x for x in res["problems"]):
    fails.append("decision wording in a policy text passed the audit")
examined += 1
res = planted(lambda p: p["self_resolving"].pop("QUOTA_EXHAUSTED"))
if not any(x.startswith("QUOTA_EXHAUSTED: no class") for x in res["problems"]):
    fails.append("a raised stop kind with no class passed the audit")
examined += 1
res = SC.audit(extra_texts=[("planted.py:1", "Nothing is broken. This is the "
                              "decision point: pick a format.")])
if not any("planted.py" in x for x in res["problems"]):
    fails.append("decision wording in a stop's unblock text passed the audit")

# ------------------------------------------------------------ 4. converted
cls = {r["code"]: r["class"] for r in a["rows"]}
for code in ("SHORTS_INVENTORY_EXHAUSTED", "CADENCE_SCALE_WITHHELD",
             "SCRIPTS_AWAITING_PROMOTION_RUNWAY_CRITICAL",
             "INSUFFICIENT_DOMAIN_EVIDENCE", "QUEUE_DECAYED_BUT_UNMEASURED",
             "NO_REPLACEMENT_DOMAIN", "RUNWAY_WARN"):
    examined += 1
    if cls.get(code) != "automated":
        fails.append(f"{code} is {cls.get(code)}, not automated policy")
examined += 1
if "FORMAT_PROBLEM" in cls:
    fails.append("FORMAT_PROBLEM is still a stop kind")
for code, row in pol["owner_action"].items():
    if code.startswith("_"):
        continue
    examined += 1
    if (row.get("holds") or {}).get("kind") not in SC.HOLD_KINDS:
        fails.append(f"owner stop {code} names no credential/account it holds")

# ------------------------------------------------------------ 5. arming
import arming                                              # noqa: E402


class Stopped(Exception):
    pass


class St:
    def named_stop(self, code, msg, **kw):
        raise Stopped(code, msg, kw)


saved_armed, saved_env = arming.is_armed, dict(os.environ)
arming.is_armed = lambda lane: False
os.environ.pop("GITHUB_EVENT_NAME", None)
try:
    secrets = arming.LANES["reach"]["secrets"]
    for k in secrets:
        os.environ[k] = "x"
    examined += 1
    try:
        arming.gate(St(), "reach")
    except Stopped as e:
        fails.append(f"an unarmed lane with every secret present did not arm "
                     f"itself: {e.args[0]}")
    os.environ.pop(secrets[-1])
    examined += 1
    try:
        arming.gate(St(), "reach")
        fails.append("an unarmed lane missing a secret did not stop")
    except Stopped as e:
        if e.args[0] != "LANE_NOT_ARMED_REACH" or secrets[-1] not in e.args[1]:
            fails.append(f"the arming stop does not name the missing secret: "
                         f"{e.args[:2]}")
finally:
    arming.is_armed = saved_armed
    os.environ.clear()
    os.environ.update(saved_env)

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s); stop kinds {a['counts']}")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
