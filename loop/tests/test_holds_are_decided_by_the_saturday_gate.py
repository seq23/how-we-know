"""A promotion hold is decided by the Saturday gate, never parked for the owner.

Owner instruction, 2026-09-25, on finding four scripts "awaiting her promotion
decision" since the 23rd: "why can't these be left somewhere for an automated
process to pick up and decide on?" loop/score.py dispose_promotion_holds() is
that process. This pins every branch of it against a fixture hold register,
with the gate subprocess stubbed so nothing spends quota or touches the real
scripts/, publish orders, hold file, POV ledger or decision log:

  0. a hold whose script asks a question ALREADY MADE is declined before
     anything else - even when its slug is a queued row - with no gate call:
     the real why-deep-sea-creatures script, "Why do deep sea creatures look
     so strange?", is episode 01 ("... look so weird") (2026-09-25);
  1. a hold whose slug is ALREADY a queued row, asking a NEW question, is
     promoted without a gate call (the gate already passed it);
  2. a hold the gate PASSES is promoted: script at scripts/<slug>.md, a gated
     row appended to its domain's publish order under the HOLD's slug (not
     the gate's auto-slug), its POV line recorded, the hold row gone;
  3. a hold the gate KILLS is declined: the draft moves to loop/drafts/declined/
     (moved, never deleted), the hold row gone;
  4. a hold whose domain holds no weekly slots is declined without a gate call;
  5. a hold the gate cannot run for (no key) is DEFERRED: the row stays, its
     gate_deferred count rises, nothing else changes, no stop yet;
  6. every decision is a dated entry in the decision log;
  7. a hold deferred HOLD_GATE_DEFERRALS times is the HOLD_GATE_FAILED stop -
     a hold a month old is stuck, not waiting.

Hard-fails on zero examined cases and if the stub saw no gate call at all.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

SCRATCH = Path(tempfile.mkdtemp(prefix="hold-gate-"))
os.environ["LOOP_STOPS_DIR"] = str(SCRATCH / "stops")
(SCRATCH / "stops").mkdir()
os.environ["LOOP_DRY_RUN"] = "1"

sys.path.insert(0, str(LOOP))
import batch_queue  # noqa: E402
import common       # noqa: E402
import domains      # noqa: E402
import pov_match    # noqa: E402
import score        # noqa: E402

POV = ("When I picture the deep ocean I don't see blue water or fish. I see "
       "black. A massive amount of black space where you can't tell what's "
       "beside you or beneath you.")
POV2 = ("It feels quiet, but not peaceful quiet. More like being somewhere "
        "you were never designed to be.")
BANK = [{"id": "pov-001", "tag": "scale", "tier": "specific", "line": POV},
        {"id": "pov-002", "tag": "scale", "tier": "specific", "line": POV2}]


def script(title: str, domain: str = "deep-sea-ocean-science",
           pov: str = POV) -> str:
    # One bank line per script: pov_match.record_assignment() refuses a
    # second script on the same line (POV_ID_REUSED), by design.
    return (f"# {title}\n\n**Status:** DRAFT\n\n**Domain:** {domain}\n\n"
            f"## Narration\n\nProse.\n\n### Producer POV\n\n[HUMAN] {pov}\n\n"
            f"## Sources\n- x\n")


def gate_row(query: str, verdict: str, reason: str) -> dict:
    return {"slug": "auto-" + query.replace(" ", "-"), "domain":
            "deep-sea-ocean-science", "title": query.capitalize() + "?",
            "query": query, "gate": {"verdict": verdict, "failed": [],
                                     "reason": reason},
            "combined": {"combined_score": 0.42}}


def check() -> list[str]:
    fails, examined = [], 0
    calls: list[str] = []

    # ---------------------------------------------------------- the fixture
    drafts = SCRATCH / "drafts"
    drafts.mkdir()
    holds = {
        "already-queued": script("How do deep sea creatures see in the dark"),
        "repeats-made": script("Why do deep sea creatures look so strange",
                               pov=POV2),
        "gate-passes": script("How do scientists know how deep the ocean is",
                              pov=POV2),
        "gate-kills": script("How do scientists know so much"),
        "off-plan": script("How do scientists know about other galaxies",
                           domain="space"),
        "no-key": script("How do scientists know how old something is"),
    }
    for slug, text in holds.items():
        (drafts / f"{slug}.md").write_text(text, encoding="utf-8")
    # score.py resolves `script` against ROOT and checks it IS
    # DRAFTS_DIR/<slug>.md; a scratch outside ROOT must be absolute, which
    # ROOT / "/abs/path" leaves untouched.
    hold_doc = {"_why": ["fixture"], "holds": [
        {"slug": s, "script": str(drafts / f"{s}.md"),
         "held_since": "2026-09-23"} for s in holds]}
    holds_path = SCRATCH / "promotion_holds.json"
    holds_path.write_text(json.dumps(hold_doc, indent=1))
    queue_file = SCRATCH / "publish_order_deep_sea_ocean_science.json"
    queue_file.write_text(json.dumps({"domain": "deep-sea-ocean-science",
                                      "queue": []}))
    scripts_dir = SCRATCH / "scripts"
    scripts_dir.mkdir()
    declined_dir = SCRATCH / "declined"
    log = SCRATCH / "DECISION-LOG.md"
    log.write_text("# Decision log\n")
    assignments = SCRATCH / "pov-assignments.json"
    assignments.write_text(json.dumps({"assignments": []}))

    def fake_run(cmd, **kw):
        if "--query" not in cmd:
            raise AssertionError(f"unexpected subprocess: {cmd}")
        q = cmd[cmd.index("--query") + 1]
        calls.append(q)
        if q.startswith("how do scientists know how deep"):
            row = gate_row(q, "passed", "demand 0.61 clears the 0.16 floor "
                                        "and title gap 0.9 clears the 0.3 "
                                        "ceiling.")
        elif q.startswith("how do scientists know so much"):
            row = gate_row(q, "kill", "demand 0.04 is under the 0.10 firm "
                                      "floor.")
        elif q.startswith("how do scientists know how old"):
            return SimpleNamespace(returncode=3, stdout="", stderr=
                                   "NAMED STOP YOUTUBE_API_KEY_ABSENT: no "
                                   "youtube data api key in this environment\n")
        else:
            raise AssertionError(f"the gate was asked about {q!r}, which "
                                 f"this fixture never expects to be gated")
        return SimpleNamespace(returncode=0, stderr="", stdout=
                               "scoring 1 candidate(s)…\nHOLD_GATE_VERDICT "
                               + json.dumps({"rows": [row], "unmeasured": []})
                               + "\n")

    saved = (score.subprocess.run, score.HOLDS_PATH, score.SCRIPTS_DIR,
             score.DECLINED_DIR, score.DECISION_LOG, score.RESEARCH_DIR,
             score.DRAFTS_DIR, batch_queue.queued_entries, domains.allocation,
             pov_match.bank, pov_match.ASSIGNMENTS, batch_queue.made_questions)
    score.subprocess.run = fake_run
    # THE CHANNEL'S "ALREADY MADE" LIST IS A FIXTURE TOO. It used to be the
    # real ledger plus every real scripts/*.md H1, which made case 5 depend on
    # live state: on 2026-09-26 the real Saturday gate promoted
    # how-do-scientists-know-how-old-something-is into scripts/, so the
    # fixture's "no-key" hold (the same question) was declined as a repeat
    # before it could ever be deferred, and case 7 found no hold left at all.
    # Episode 01 is the one made question the fixture needs (case 0).
    import topic_identity as TI
    made = [("why deep sea creatures look so weird",
             TI.question_key("why deep sea creatures look so weird"))]
    batch_queue.made_questions = lambda exclude=frozenset(): list(made)
    score.HOLDS_PATH, score.SCRIPTS_DIR = holds_path, scripts_dir
    score.DECLINED_DIR, score.DECISION_LOG = declined_dir, log
    score.RESEARCH_DIR, score.DRAFTS_DIR = SCRATCH, drafts
    batch_queue.queued_entries = lambda: [
        {"slug": "already-queued", "query": "how deep sea creatures see",
         "_domain_file": "publish_order_fixture.json"},
        {"slug": "repeats-made", "query": "why deep sea creatures",
         "_domain_file": "publish_order_fixture.json"}]
    domains.allocation = lambda cfg: {"deep-sea-ocean-science": 2}
    pov_match.bank = lambda: list(BANK)
    pov_match.ASSIGNMENTS = assignments
    stop = None
    try:
        try:
            with common.Stage("weekly-score", "2026-W39") as st:
                score.dispose_promotion_holds(st)
        except SystemExit as e:
            stop = e
        # ---------------------------------------------------------------
        # -- Rule 0
        examined += 1
        if not calls:
            fails.append("the stub saw ZERO gate calls; nothing was decided")
            return fails
        if stop is not None:
            fails.append(f"the fixture's first pass must not stop (nothing is "
                         f"deferred past the cap yet); stage exited {stop.code}")

        left = {h["slug"]: h for h in json.loads(holds_path.read_text())["holds"]}
        queue = json.loads(queue_file.read_text())["queue"]
        logged = log.read_text()
        recorded = {a["video"]: a for a in
                    json.loads(assignments.read_text())["assignments"]}

        # -- 0. repeats an episode already made: declined, never gated -------
        examined += 1
        if "repeats-made" in left:
            fails.append("a hold repeating episode 01 is still held")
        if (scripts_dir / "repeats-made.md").exists():
            fails.append("a hold repeating episode 01 was promoted to "
                         "scripts/ (its slug is a queued row, which must not "
                         "shortcut the repeat check)")
        if not (declined_dir / "repeats-made.md").exists() \
                or (drafts / "repeats-made.md").exists():
            fails.append("the repeat was not MOVED to loop/drafts/declined/")
        if any(c.startswith("why do deep sea") for c in calls):
            fails.append("a hold repeating an episode already made was sent "
                         "to the gate; it must be declined before any spend")
        if "repeats-made" in recorded:
            fails.append("a declined repeat had its POV line recorded")

        # -- 1. already queued: promoted, no gate call ------------------------
        examined += 1
        if "already-queued" in left or not (scripts_dir / "already-queued.md").exists():
            fails.append("a hold whose slug is already a queued row was not "
                         "promoted to scripts/")
        if any(c.startswith("how do deep sea") for c in calls):
            fails.append("a hold whose slug is already a queued row was "
                         "re-gated; the gate already passed it")

        # -- 2. gate passes: promoted, row under the HOLD's slug, POV recorded
        examined += 1
        if "gate-passes" in left or not (scripts_dir / "gate-passes.md").exists():
            fails.append("a hold the gate passed was not promoted to scripts/")
        rows = [r for r in queue if r.get("slug") == "gate-passes"]
        if len(rows) != 1:
            fails.append(f"the passed hold's row was not appended to its "
                         f"domain's publish order under the hold's own slug: "
                         f"{[r.get('slug') for r in queue]!r}")
        elif rows[0].get("gate", {}).get("verdict") != "passed" \
                or not rows[0].get("promoted_from_hold"):
            fails.append("the appended row does not carry the gate's verdict "
                         "and the hold's provenance")
        if recorded.get("gate-passes", {}).get("pov_id") != "pov-002" \
                or recorded.get("already-queued", {}).get("pov_id") != "pov-001":
            fails.append(f"a promoted script's POV line was not recorded "
                         f"against the bank: {recorded!r}")

        # -- 3. gate kills: declined, draft MOVED not deleted -----------------
        examined += 1
        if "gate-kills" in left:
            fails.append("a hold the gate killed is still held")
        if (scripts_dir / "gate-kills.md").exists():
            fails.append("a killed hold was promoted anyway")
        if not (declined_dir / "gate-kills.md").exists():
            fails.append("the declined draft is not in loop/drafts/declined/ "
                         "- declining must move it, never delete it")
        if (drafts / "gate-kills.md").exists():
            fails.append("the declined draft was copied, not moved; it still "
                         "sits where the stray-script scan would find it")

        # -- 4. off-plan domain: declined, never gated ------------------------
        examined += 1
        if "off-plan" in left or not (declined_dir / "off-plan.md").exists():
            fails.append("a hold in a domain with no weekly slots was not "
                         "declined")
        if any(c.startswith("how do scientists know about other") for c in calls):
            fails.append("a hold in an unallocated domain was gated; nothing "
                         "could air it whatever the gate said")

        # -- 5. no key: deferred, counted, kept -------------------------------
        examined += 1
        if "no-key" not in left:
            fails.append("a hold the gate could not run for was decided anyway")
        elif left["no-key"].get("gate_deferred") != 1:
            fails.append(f"the deferred hold's gate_deferred is not 1: "
                         f"{left['no-key']!r}")
        if (drafts / "no-key.md").exists() is False:
            fails.append("the deferred draft was moved")

        # -- 6. the decision log ---------------------------------------------
        examined += 1
        for slug, verdict in (("repeats-made", "DECLINED"),
                              ("already-queued", "PROMOTED"),
                              ("gate-passes", "PROMOTED"),
                              ("gate-kills", "DECLINED"),
                              ("off-plan", "DECLINED")):
            if f"**{verdict}** `{slug}`" not in logged:
                fails.append(f"decision log has no {verdict} line for {slug}")
        if "no-key" in logged:
            fails.append("a deferred hold was written to the decision log as "
                         "if decided")

        # -- 7. the deferral cap is the HOLD_GATE_FAILED stop ------------------
        examined += 1
        doc = json.loads(holds_path.read_text())
        for h in doc["holds"]:
            if h["slug"] == "no-key":
                h["gate_deferred"] = score.HOLD_GATE_DEFERRALS - 1
        holds_path.write_text(json.dumps(doc))
        exit_code = None
        try:
            with common.Stage("weekly-score", "2026-W39") as st:
                score.dispose_promotion_holds(st)
        except SystemExit as e:
            exit_code = int(e.code or 0)
        recs = sorted((SCRATCH / "stops").glob("*weekly-score*.json"))
        rec = json.loads(recs[-1].read_text()) if recs else {}
        if rec.get("code") != "HOLD_GATE_FAILED":
            fails.append(f"a hold deferred {score.HOLD_GATE_DEFERRALS} times "
                         f"did not raise HOLD_GATE_FAILED; got "
                         f"{rec.get('code')!r} (exit {exit_code})")
        elif exit_code != 3:
            fails.append(f"HOLD_GATE_FAILED is needs_human and must exit 3; "
                         f"got {exit_code}")
    finally:
        (score.subprocess.run, score.HOLDS_PATH, score.SCRIPTS_DIR,
         score.DECLINED_DIR, score.DECISION_LOG, score.RESEARCH_DIR,
         score.DRAFTS_DIR, batch_queue.queued_entries, domains.allocation,
         pov_match.bank, pov_match.ASSIGNMENTS,
         batch_queue.made_questions) = saved

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"inspected {examined} hold-disposition case(s); gate calls: {calls}")
    return fails


if __name__ == "__main__":
    try:
        f = check()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every hold is decided by the Saturday gate, nothing "
          "waits on the owner" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
