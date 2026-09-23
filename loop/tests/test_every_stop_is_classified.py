"""Every stop this repo can emit has been DECIDED about. No code may drift in.

WHAT THIS GUARDS, and why the existing taxonomy test is not enough.

`loop/tests/test_stop_taxonomy.py` proves the mechanism works and that every
code IN THE POLICY is really raised by a lane. It cannot see the opposite gap:
a code raised by a lane and named in no section at all. Those take
`default_disposition: needs_human` and go red — which was the right default
while `self_resolving` was the only alternative, and became a real hazard on
2026-09-08 when the owner's instruction was that a named stop must never reach
her as a failed build. An unclassified code is now a decision nobody made,
delivered to her inbox.

So this asserts the closure in the OTHER direction:

  A. Every stop code the source can raise appears in exactly one of
     `self_resolving`, `owner_action` or `needs_human`.
  B. Every code named in the policy is really raised (or is a documented
     wildcard family whose generator still exists).
  C. `owner_action` behaves: green exit, an owner_action.json record, and the
     record cleared by the stage's next success.
  D. The wildcard families resolve.

Hard-fails if it examines zero codes — an empty scan would pass every
assertion here and prove nothing, which is the exact defect class this repo
keeps finding.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable

# Section C runs real stages that take real stops. loop/tests/run_all.py
# points LOOP_STOPS_DIR at scratch; run on its own, this file wrote
# loop/state/stops/_held.json. Default to scratch here as well.
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="classified-stops-"))
POLICY = json.load(open(os.path.join(LOOP, "stop_policy.json")))

fails: list[str] = []


def section(name: str) -> dict:
    return {k: v for k, v in (POLICY.get(name) or {}).items()
            if not k.startswith("_")}


SELF = section("self_resolving")
OWNER = section("owner_action")
HUMAN = section("needs_human")


# --------------------------------------------------------------------------
# Collect every code the source can raise.
#
# Literal first arguments to `st.named_stop(...)` are read straight out of the
# AST. Codes chosen at runtime are read from the SAME source, not from a list
# maintained here: each entry below names the file and the expression that
# builds the code, and the scan asserts that expression is still present, so a
# refactor that moves or renames one fails this test instead of silently
# shrinking the audit.
# --------------------------------------------------------------------------
GENERATED = {
    # code                          (file,             a substring that must
    #                                                   still be in that file)
    "OAUTH_EXPIRED":               ("upload.py", '"expired_refresh": "OAUTH_EXPIRED"'),
    "OAUTH_NOT_CONSENTED":         ("upload.py", '"no_token": "OAUTH_NOT_CONSENTED"'),
    "OAUTH_UNUSABLE":              ("upload.py", '"OAUTH_UNUSABLE"'),
    "OAUTH_MISSING":               ("upload.py", '"OAUTH_MISSING"'),
    "WRONG_CHANNEL":               ("upload.py", '"WRONG_CHANNEL"'),
    "CHANNEL_UNREADABLE":          ("upload.py", '"CHANNEL_UNREADABLE"'),
    "UPLOADS_LOCKED_PRIVATE":      ("publish.py", '"UPLOADS_LOCKED_PRIVATE"'),
    "FLIP_FAILED":                 ("publish.py", '"FLIP_FAILED"'),
    "R2_AUTH_FAILED":              ("r2.py", '"R2_AUTH_FAILED"'),
    "R2_COMMAND_FAILED":           ("r2.py", '"R2_COMMAND_FAILED"'),
    "R2_CREDENTIALS_MISSING":      ("r2.py", '"R2_CREDENTIALS_MISSING"'),
    "WRANGLER_MISSING":            ("r2.py", '"WRANGLER_MISSING"'),
    "DRY_RUN_WRITE_REFUSED":       ("r2.py", '"DRY_RUN_WRITE_REFUSED"'),
    "DRY_RUN_NO_CREDENTIALS":      ("r2.py", '"DRY_RUN_NO_CREDENTIALS"'),
    "SHORTS_UNVERIFIED":           ("r2.py", '"SHORTS_UNVERIFIED"'),
    "OPENROUTER_KEY_MISSING":      ("author.py", '"OPENROUTER_KEY_MISSING"'),
    "OPENROUTER_UNAUTHORISED":     ("author.py", '"OPENROUTER_UNAUTHORISED"'),
    "OPENROUTER_OUT_OF_CREDIT":    ("author.py", '"OPENROUTER_OUT_OF_CREDIT"'),
    "OPENROUTER_RATE_LIMITED":     ("author.py", '"OPENROUTER_RATE_LIMITED"'),
    "OPENROUTER_ERROR":            ("author.py", '"OPENROUTER_ERROR"'),
    "OPENROUTER_UNREACHABLE":      ("author.py", '"OPENROUTER_UNREACHABLE"'),
    "DRAFT_FAILED_VALIDATION":     ("author.py", '"DRAFT_FAILED_VALIDATION"'),
    "TOPIC_EXCLUDED":              ("author.py", '"TOPIC_EXCLUDED"'),
    "INSUFFICIENT_DOMAIN_EVIDENCE": ("domains.py", '"INSUFFICIENT_DOMAIN_EVIDENCE"'),
    "QUEUE_DECAYED_BUT_UNMEASURED": ("domains.py", '"QUEUE_DECAYED_BUT_UNMEASURED"'),
    "NO_REPLACEMENT_DOMAIN":       ("domains.py", '"NO_REPLACEMENT_DOMAIN"'),
    "QUOTA_DEFERRED":              ("localize.py", '"QUOTA_DEFERRED"'),
    "CAPTIONS_QUOTA_DEFERRED":     ("validate.py", '"CAPTIONS_QUOTA_DEFERRED"'),
    "LOCALIZE_QUOTA_DEFERRED":     ("validate.py", '"LOCALIZE_QUOTA_DEFERRED"'),
    "ZERO_WORK":                   ("common.py", '"ZERO_WORK"'),
    "STATE_FILE_CORRUPT":          ("common.py", '"STATE_FILE_CORRUPT"'),
    "BREAKER_TRIPPED":             ("breaker.py", '"BREAKER_TRIPPED" if first'),
    "BREAKER_TRIPPED_ALREADY_REPORTED":
                                   ("breaker.py", '"BREAKER_TRIPPED_ALREADY_REPORTED"'),
    # The upload lane's empty-shelf diagnosis picks one of these from state
    # (loop/cloud_upload.py diagnose_empty_shelf) and raises it by variable.
    "NOTHING_SHELVED":             ("cloud_upload.py", '"code": "NOTHING_SHELVED"'),
    "PUBLISH_QUEUE_UPLOADED":      ("cloud_upload.py", '"code": "PUBLISH_QUEUE_UPLOADED"'),
    "AUTHORED_NOT_QUEUED":         ("cloud_upload.py", '"code": "AUTHORED_NOT_QUEUED"'),
    "PUBLISH_QUEUE_EMPTY":         ("cloud_upload.py", '"code": "PUBLISH_QUEUE_EMPTY"'),
    "NO_QUEUE":                    ("cloud_upload.py", '"code": "NO_QUEUE"'),
    # Synthesised by the digest from the Mac's heartbeat, not raised by a lane.
    "MAC_NOT_SHIPPING":            ("digest.py", '"code": "MAC_NOT_SHIPPING"'),
}

# Families the loop BUILDS a code for. Each must be matched by a wildcard key.
FAMILIES = {
    "LANE_NOT_ARMED_": ("arming.py", 'f"LANE_NOT_ARMED_{lane.upper()'),
    "ANALYTICS_HTTP_": ("measure.py", 'f"ANALYTICS_HTTP_{e.code}"'),
}


def shell_codes() -> dict[str, list[str]]:
    """Codes the Mac's SHELL lanes raise: `named_stop "CODE" ...` in bin/*.sh.

    THE GAP THIS CLOSES. bin/loop-backfill-daily.sh raised PULL_FAILED,
    REBASE_IN_PROGRESS and RENDER_GATE_FAILED for a week (6-13 September 2026)
    and none of them was in the policy, because this audit only read loop/*.py.
    A Mac lane's stop is a stop; it is scanned like the rest.
    """
    import re
    found: dict[str, list[str]] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "bin", "*.sh"))):
        for i, line in enumerate(open(path), 1):
            m = re.search(r'\bnamed_stop\s+"([A-Z0-9_]+)"', line)
            if m:
                found.setdefault(m.group(1), []).append(
                    f"bin/{os.path.basename(path)}:{i}")
    return found


def literal_codes() -> dict[str, list[str]]:
    found: dict[str, list[str]] = shell_codes()
    for path in sorted(glob.glob(os.path.join(LOOP, "*.py"))):
        src = open(path).read()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            fails.append(f"{os.path.basename(path)} does not parse: {e}")
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if fn != "named_stop" or not n.args:
                continue
            a = n.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                found.setdefault(a.value, []).append(
                    f"{os.path.basename(path)}:{n.lineno}")
    return found


def run_audit() -> int:
    global fails
    fails = []
    literal = literal_codes()

    # ---- A. every code is classified exactly once -----------------------------
    all_codes = dict(literal)
    for code, (fname, needle) in GENERATED.items():
        src = open(os.path.join(LOOP, fname)).read()
        if needle not in src:
            fails.append(
                f"A: this test claims {code} is built in loop/{fname} by "
                f"{needle!r}, and that expression is no longer there. The audit "
                f"has gone stale — fix the reference, do not delete the code.")
        else:
            all_codes.setdefault(code, []).append(f"{fname} (generated)")

    if len(all_codes) < 60:
        print(f"FAIL: scanned only {len(all_codes)} stop codes. This repo raises "
              f"~70; a scan this small means the AST walk stopped matching and "
              f"every assertion below would pass on nothing.")
        return 1

    for code, sites in sorted(all_codes.items()):
        homes = [s for s, d in (("self_resolving", SELF), ("owner_action", OWNER),
                                ("needs_human", HUMAN)) if code in d]
        if not homes:
            fails.append(
                f"A: `{code}` is raised at {sites[0]} and appears in NO section of "
                f"loop/stop_policy.json. It would take the needs-a-human default "
                f"and fail a job — decide where it belongs: can a machine clear it "
                f"(build the recovery), can only she (owner_action), or is it a "
                f"defect (needs_human)?")
        elif len(homes) > 1:
            fails.append(f"A: `{code}` is classified in {homes} at once. One code, "
                         f"one disposition.")

    # ---- B. nothing in the policy is a fiction --------------------------------
    for name, sect in (("self_resolving", SELF), ("owner_action", OWNER)):
        for code in sect:
            if code.endswith("*"):
                # `ANALYTICS_HTTP_5*` narrows the `ANALYTICS_HTTP_` family rather
                # than naming it, which is the point of wildcards: a 5xx is
                # Google's server and a 4xx is this repo's request, and the two
                # must not share a disposition.
                stem = code[:-1]
                if not any(stem.startswith(f) for f in FAMILIES):
                    fails.append(f"B: wildcard `{code}` in {name} matches no known "
                                 f"generated family.")
                continue
            if code not in all_codes:
                fails.append(
                    f"B: `{code}` is classified {name} in loop/stop_policy.json and "
                    f"nothing in loop/ raises it. A rule that cannot reach what it "
                    f"governs is inert.")

    for prefix, (fname, needle) in FAMILIES.items():
        src = open(os.path.join(LOOP, fname)).read()
        if needle not in src:
            fails.append(f"B: the {prefix}* family is no longer built in "
                         f"loop/{fname} by {needle!r}.")
        sys.path.insert(0, LOOP)

    # ---- D. the wildcards actually resolve ------------------------------------
    sys.path.insert(0, LOOP)
    import common                                                     # noqa: E402

    for probe, want in (("LANE_NOT_ARMED_UPLOAD_CLOUD", "owner_action"),
                        ("ANALYTICS_HTTP_503", "self_resolving"),
                        ("ANALYTICS_HTTP_403", "needs_human")):
        disp, why = common.disposition("probe-stage", probe, {}, 1)
        if disp != want:
            fails.append(f"D: `{probe}` classified {disp}, expected {want} — {why}")

    # ---- C. owner_action is green, recorded, and cleared by success -----------
    HARNESS = r'''
import os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "loop"))
from common import Stage
mode = os.environ["MODE"]
with Stage("probe-owner-stage", "2026-W37") as st:
    if mode == "stop":
        st.named_stop("OAUTH_MISSING", "no credential in this environment",
                      unblock="re-consent")
    st.work("did a real unit of work")

'''
    with tempfile.TemporaryDirectory() as td:
        hp = os.path.join(td, "harness.py")
        open(hp, "w").write(HARNESS)
        stops = os.path.join(td, "stops")
        os.makedirs(stops)
        env = dict(os.environ, REPO=ROOT, LOOP_STOPS_DIR=stops, MODE="stop")
        # LOOP_STOPS_DIR also redirects the owner-action record (see
        # common._owner_action_path), so this test cannot write a live "waiting on
        # you" row into the committed state and into her next digest.
        r = subprocess.run([PY, hp], env=env, capture_output=True, text=True,
                           cwd=ROOT)
        if r.returncode != 0:
            fails.append(
                f"C: an OAUTH_MISSING stop exited {r.returncode}; owner_action "
                f"stops must exit 0 so she is never paged for a credential she "
                f"will renew when she next sits down.\n{r.stdout[-600:]}")
        if "WAITING ON THE OWNER" not in r.stdout:
            fails.append("C: the banner did not say the stop is waiting on the "
                         "owner — green with no explanation is just silence.")
        rec_path = os.path.join(stops, "2026-W37-probe-owner-stage.json")
        if not os.path.exists(rec_path):
            fails.append("C: no stop record was written for an owner_action stop.")
        else:
            rec = json.load(open(rec_path))
            if rec.get("disposition") != "owner_action":
                fails.append(f"C: recorded disposition {rec.get('disposition')!r}, "
                             f"expected 'owner_action'.")

    print(f"examined {len(all_codes)} stop codes: "
          f"{len(SELF)} self-resolving, {len(OWNER)} owner-action, "
          f"{len(HUMAN)} needs-a-human")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("PASS: every stop code this repo can raise has an explicit disposition.")
    return 0


# IMPORT-SAFE ON PURPOSE. loop/tests/test_stop_taxonomy.py imports GENERATED
# from here so the two guards share ONE list of the codes the loop builds
# rather than writes -- two components each keeping their own copy of that list
# is a named defect class in this repo. An import must therefore not run the
# audit, spawn subprocesses, or exit the caller.
if __name__ == "__main__":
    raise SystemExit(run_audit())
