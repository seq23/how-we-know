"""loop/comments.py: `act` cannot hide or reply without an instruction record.

WHAT THIS PINS.

  A. The gate. apply_instruction() refuses - before any network call - an
     instruction that lacks instructed_by / instructed_at / source, names an
     illegal action, replies with no text, or targets a comment the sweep
     never recorded. The write function is stubbed with a recorder and the
     recorder must stay EMPTY.
  B. The negative proof. The same module with assert_backed() neutered DOES
     write - so it is the gate, and only the gate, standing between an
     unbacked instruction and the channel.
  C. The CLI path: `act --instructions` with one unbacked line among good
     ones applies NOTHING and names INSTRUCTION_UNBACKED (exit 3).
  D. A backed instruction is applied through the write path and recorded in
     the ledger with who instructed it, when, and via what; a second run of
     the same instruction is idempotent (INSTRUCTIONS_ALREADY_APPLIED, no
     second write).
  E. The classifier parser refuses a shape it cannot trust (missing id,
     unknown class, reported class with no action) and accepts a good one.
  F. Brand separation: the module names no other business.
  G. Every stop code the module raises is classified in stop_policy.json
     (test_every_stop_is_classified.py covers this repo-wide; this is the
     local, faster check with the same rule).

Runs entirely offline: LOOP_DRY_RUN=1, a temp ledger, a stubbed token.
Hard-fails if it examined zero cases.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
PY = sys.executable

os.environ["LOOP_DRY_RUN"] = "1"
sys.path.insert(0, str(LOOP))

import comments as C                                            # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")
    else:
        print(f"  ok   {name}")


def ledger_with(*ids: str) -> dict:
    led = C._empty_ledger()
    for i in ids:
        led["seen"][i] = {"comment_id": i, "video_id": "vid1",
                          "video_title": "t", "author": "a", "text": "x",
                          "published_at": "2026-09-20T00:00:00Z",
                          "class": "negative", "proposed_action": "reply"}
    return led


GOOD = {"action": "reply", "reply_text": "Thanks - the figure is from NOAA.",
        "instructed_by": "owner", "instructed_at": "2026-09-21T13:00:00Z",
        "source": "email reply #monique"}


def recorder(mod):
    calls: list[tuple] = []

    def fake_write(token, path, params, body):
        calls.append((path, params, body))
        return {"id": "reply-1"}
    mod._write = fake_write
    return calls


# ---------------------------------------------------------------- A. gate
calls = recorder(C)
led = ledger_with("c1")
unbacked = {
    "no record at all": {"action": "hide"},
    "missing instructed_by": {**GOOD, "instructed_by": ""},
    "missing instructed_at": {**GOOD, "instructed_at": None},
    "missing source": {k: v for k, v in GOOD.items() if k != "source"},
    "illegal action": {**GOOD, "action": "delete"},
    "reply without text": {**GOOD, "reply_text": "  "},
    "not an object": "hide",
}
for name, ins in unbacked.items():
    try:
        C.apply_instruction("tok", "c1", ins, led)
        check(f"A refuses {name}", False, "no Unbacked raised")
    except C.Unbacked:
        check(f"A refuses {name}", True)
try:
    C.apply_instruction("tok", "never-swept", dict(GOOD), led)
    check("A refuses an unswept comment", False, "no Unbacked raised")
except C.Unbacked:
    check("A refuses an unswept comment", True)
check("A no write happened", not calls, f"writes: {calls}")
check("A nothing recorded", not led["actions"] and not led["instructions"],
      str(led["actions"]))

# ------------------------------------------------------ B. negative proof
src = (LOOP / "comments.py").read_text()
needle = "    assert_backed(comment_id, ins, led)\n    rec = led[\"seen\"]"
check("B the gate line exists where the proof expects it", needle in src)
broken = src.replace(needle, "    pass\n    rec = led[\"seen\"]")
with tempfile.TemporaryDirectory() as td:
    bp = Path(td) / "comments_broken.py"
    bp.write_text(broken)
    spec = importlib.util.spec_from_file_location("comments_broken", bp)
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    bcalls = recorder(B)
    bled = ledger_with("c1")
    try:
        B.apply_instruction("tok", "c1", {**GOOD, "instructed_by": ""}, bled)
        broke = True
    except Exception as e:                               # noqa: BLE001
        broke = False
        why = repr(e)
    check("B with the gate removed the unbacked reply IS written",
          broke and len(bcalls) == 1,
          f"broke={broke} calls={bcalls} " + ("" if broke else why))

# ---------------------------------------------------------------- C. CLI
with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, LOOP_DRY_RUN="1",
               LOOP_STOPS_DIR=os.environ.get("LOOP_STOPS_DIR") or td)
    # Point the module's ledger at a temp copy by running through a shim.
    shim = Path(td) / "shim.py"
    ledger_path = Path(td) / "ledger.json"
    ledger_path.write_text(json.dumps(ledger_with("c1", "c2")))
    ins_path = Path(td) / "ins.json"
    ins_path.write_text(json.dumps({"c1": GOOD, "c2": {"action": "hide"}}))
    shim.write_text(
        f"import sys; sys.path.insert(0, {str(LOOP)!r})\n"
        "import comments as C\n"
        "from pathlib import Path\n"
        f"C.LEDGER = Path({str(ledger_path)!r}); C.COMMENTS_DIR = C.LEDGER.parent\n"
        "calls = []\n"
        "C._write = lambda *a: calls.append(a) or {'id': 'r'}\n"
        f"rc = C.act(Path({str(ins_path)!r}))\n")
    r = subprocess.run([PY, str(shim)], capture_output=True, text=True,
                       cwd=ROOT, env=env)
    out = r.stdout + r.stderr
    check("C act exits 3 on a batch with one unbacked line",
          r.returncode == 3, f"rc={r.returncode}\n{out[-800:]}")
    check("C act names INSTRUCTION_UNBACKED", "INSTRUCTION_UNBACKED" in out)
    after = json.loads(ledger_path.read_text())
    check("C act applied NOTHING (the good line included)",
          not after["actions"] and not after["instructions"],
          json.dumps(after["actions"]))

    # ------------------------------------------------------------- D. backed
    ins_path.write_text(json.dumps({"c1": GOOD}))
    shim2 = Path(td) / "shim2.py"
    shim2.write_text(
        f"import sys; sys.path.insert(0, {str(LOOP)!r})\n"
        "import comments as C, upload as up\n"
        "from pathlib import Path\n"
        f"C.LEDGER = Path({str(ledger_path)!r}); C.COMMENTS_DIR = C.LEDGER.parent\n"
        "up.load_credentials = lambda cfg: {'access_token': 'tok'}\n"
        "import quota; quota.spend = lambda *a: None\n"
        "calls = []\n"
        "C._write = lambda *a: calls.append(a) or {'id': 'reply-9'}\n"
        "try:\n"
        f"    rc = C.act(Path({str(ins_path)!r}))\n"
        "except SystemExit as e:\n"
        "    rc = e.code\n"
        "print('WRITES', len(calls), calls[0][1] if calls else None)\n"
        "raise SystemExit(rc)\n")
    r = subprocess.run([PY, str(shim2)], capture_output=True, text=True,
                       cwd=ROOT, env=env)
    out = r.stdout + r.stderr
    check("D a backed reply runs green", r.returncode == 0,
          f"rc={r.returncode}\n{out[-800:]}")
    check("D exactly one write, to comments.insert",
          "WRITES 1 comments" in out and "setModerationStatus" not in out, out[-300:])
    after = json.loads(ledger_path.read_text())
    act_rec = (after["actions"] or [{}])[0]
    check("D the ledger records who/when/via and the reply id",
          act_rec.get("instructed_by") == "owner"
          and act_rec.get("instructed_at") == GOOD["instructed_at"]
          and act_rec.get("source") == GOOD["source"]
          and act_rec.get("reply_id") == "reply-9",
          json.dumps(act_rec))
    r = subprocess.run([PY, str(shim2)], capture_output=True, text=True,
                       cwd=ROOT, env=env)
    out = r.stdout + r.stderr
    check("D re-running the same instruction is idempotent",
          r.returncode == 0 and "INSTRUCTIONS_ALREADY_APPLIED" in out
          and "WRITES 0" in out, out[-500:])

# --------------------------------------------------------------- E. parser
good = json.dumps([{"id": "a", "class": "question", "proposed_action": "reply",
                    "proposed_reply": "Yes.", "product_note": None},
                   {"id": "b", "class": "praise"}])
parsed = C.parse_classification("```json\n" + good + "\n```", ["a", "b"])
check("E parses a fenced, well-formed answer",
      parsed["a"]["proposed_reply"] == "Yes." and parsed["b"]["class"] == "praise"
      and parsed["b"]["proposed_action"] is None)
for name, bad in {
    "missing id": json.dumps([{"id": "a", "class": "other"}]),
    "unknown class": json.dumps([{"id": "a", "class": "meh"},
                                 {"id": "b", "class": "praise"}]),
    "reported class without action": json.dumps(
        [{"id": "a", "class": "negative"}, {"id": "b", "class": "praise"}]),
    "not an array": json.dumps({"id": "a"}),
}.items():
    try:
        C.parse_classification(bad, ["a", "b"])
        check(f"E refuses {name}", False, "accepted")
    except (ValueError, KeyError, TypeError):
        check(f"E refuses {name}", True)

# ------------------------------------------------------------- F. brands
low = src.lower()
for word in ("west peek", "westpeek", "spry", "spry.vc"):
    check(f"F module never names {word!r}", word not in low)
check("F the account is the channel's own", "the channel's own Google account" in src)
check("F no personal mailbox is named in source", "@gmail.com" not in low)

# ------------------------------------------------------------- G. policy
policy = json.loads((LOOP / "stop_policy.json").read_text())
classified = set()
for sec in ("self_resolving", "owner_action", "needs_human"):
    classified |= {k for k in policy.get(sec, {}) if not k.startswith("_")}
import re                                                       # noqa: E402
raised = set(re.findall(r'named_stop\(\s*"([A-Z_]+)"', src))
raised |= set(re.findall(r'named_stop\(\n\s*"([A-Z_]+)"', src))
check("G module raises at least six named codes", len(raised) >= 6,
      str(sorted(raised)))
for code in sorted(raised):
    check(f"G {code} is classified", code in classified)

print(f"\n{examined} check(s), {len(fails)} failure(s)")
if examined == 0:
    print("FAIL: examined zero cases")
    sys.exit(1)
sys.exit(1 if fails else 0)
