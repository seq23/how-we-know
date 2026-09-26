"""The opening rule: payoff in the first 30 seconds, gated, marked, measured.

THE FINDING. loop/state/retention_finding.md, 2026-09-25: 1m53s average view
duration over 10 videos against a 146s floor; 6 of 10 lose the average viewer
inside two minutes. The decision (made for the owner - nothing waits on her):
every script drafted from 2026-09-28 lands its payoff inside the first 30
seconds, then walks the "how we know" chain; published videos are untouched.

WHAT THIS PROVES (scratch paths only, nothing under loop/state/ is written):
  1. the check: a script whose cold open states the Direct-answer lock passes;
     the same script with the answer pushed past the first 75 words fails;
     real catalogue scripts split both ways (the rule discriminates);
  2. the gate: loop/author.shape_problems() carries the opening problem, so a
     buried answer is fed back and redrafted inside the retry loop; the
     prompt and the hand-authoring brief both carry the rule text;
  3. the marker: mark() stamps the variant, variant_of() reads it back,
     unmarked (pre-rule) scripts read "pre-rule";
  4. V44: a marked script that buries its answer fails; a pre-rule one is
     exempt; zero items fails;
  5. the measurement: evaluate() WAITS before 28 days, KEEPS a variant that
     beats its baseline, SWITCHES (and logs to its state) one that does not,
     and settles on the best measured variant once the list is exhausted;
  6. the measure lane tags every record with `opening` and writes "What the
     loop is doing about it" into the finding.
Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import opening as O                                        # noqa: E402

fails: list[str] = []
examined = 0

FILLER = ("The deep ocean covers most of the planet and most of it has never "
          "been seen directly by anyone at all in any way whatsoever. ") * 6
ANSWER = ("Anglerfish glow because bacteria living inside the lure produce "
          "light through a chemical reaction.")


def script(cold: str) -> str:
    return (f"# Why do anglerfish glow?\n\n**Status:** DRAFT\n"
            f"**Domain:** deep-sea-ocean-science\n\n"
            f"## Direct-answer lock\n\n{ANSWER} Researchers confirmed it by "
            f"culturing the bacteria.\n\n## Narration\n\n### Cold open\n\n"
            f"{{{{stat: 1 | lure | x | NOAA}}}}\n{cold}\n\n### Title card\n\n"
            f"Why do anglerfish glow?\n\n## Editorial gate\n\n- x\n")


good = script(ANSWER + " " + FILLER)
buried = script(FILLER + ANSWER)

# ------------------------------------------------------------ 1. the check
examined += 2
if O.problems(good, "cold-open-payoff"):
    fails.append(f"payoff-first script failed: {O.problems(good, 'cold-open-payoff')}")
if not O.problems(buried, "cold-open-payoff"):
    fails.append("a script whose answer starts past word 75 passed")
examined += 1
if O.problems(buried, "question-first-teaser") == []:
    fails.append("the teaser variant passed a script that never poses the "
                 "question in its first 10 seconds")
real = sorted((ROOT / "scripts").glob("*.md"))
res = {p.name: bool(O.problems(p.read_text(), "cold-open-payoff")) for p in real}
examined += len(res)
if not any(res.values()) or all(res.values()):
    fails.append(f"on the real catalogue the rule passes or fails EVERYTHING "
                 f"({sum(res.values())}/{len(res)} fail) - it does not "
                 f"discriminate")
if res.get("why-is-steel-so-strong.md", True):
    fails.append("why-is-steel-so-strong (answer in its first sentence) fails")
if not res.get("08-what-creatures-live-in-the-deep-sea.md"):
    fails.append("episode 08, whose cold open does not state its answer, passes")

# ------------------------------------------------------------ 2. the gate
import author                                              # noqa: E402
import draft                                               # noqa: E402

pov = {"line": "x" * 70, "pov_id": "pov-001"}
examined += 1
if not any(p.startswith("opening rule") for p in
           author.shape_problems(buried, pov)):
    fails.append("author.shape_problems() does not reject a buried answer, so "
                 "it would never be redrafted")
if any(p.startswith("opening rule") for p in author.shape_problems(good, pov)):
    fails.append("author.shape_problems() rejects a payoff-first opening")
examined += 1
system = author.build_prompt("why do anglerfish glow", pov)[0]["content"]
if O.prompt_text("cold-open-payoff") not in system:
    fails.append("the drafting prompt does not carry the opening rule")
examined += 1
if "O.prompt_text()" not in (LOOP / "draft.py").read_text().replace(
        "opening.prompt_text()", "O.prompt_text()"):
    fails.append("the hand-authoring brief does not carry the opening rule")

# ------------------------------------------------------------ 3. the marker
examined += 1
m = O.mark(good, "cold-open-payoff")
if "**Opening:** cold-open-payoff" not in m or \
        m.index("**Opening:**") < m.index("**Domain:**"):
    fails.append("mark() did not stamp the variant after **Domain:**")
if O.mark(m, "question-first-teaser").count("**Opening:**") != 1:
    fails.append("re-marking duplicated the marker")
examined += 1
if O.variant_of("why-is-steel-so-strong") != O.PRE_RULE:
    fails.append("an unmarked published script is not read as pre-rule")

# ------------------------------------------------------------ 4. V44
import validate                                            # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="opening-", dir=str(ROOT / "loop")))
try:
    (tmp / "bad.md").write_text(O.mark(buried, "cold-open-payoff"))
    (tmp / "ok.md").write_text(O.mark(good, "cold-open-payoff"))
    rel = lambda n: str((tmp / n).relative_to(ROOT))       # noqa: E731
    examined += 3
    r = validate.v44_opening_payoff_first([{"slug": "bad", "script": rel("bad.md")}])
    if r.ok:
        fails.append("V44 passed a marked script that buries its answer")
    r = validate.v44_opening_payoff_first([{"slug": "ok", "script": rel("ok.md")},
                                           {"slug": "steel", "script":
                                            "scripts/why-is-steel-so-strong.md"}])
    if not r.ok:
        fails.append(f"V44 failed a good + a pre-rule script: {r.failures}")
    if validate.v44_opening_payoff_first([]).ok:
        fails.append("V44 passed on zero items")
finally:
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()

# ------------------------------------------------------------ 5. measurement
state = Path(tempfile.mkdtemp(prefix="opening-state-")) / "opening_variant.json"
start = datetime(2026, 9, 28, tzinfo=timezone.utc)


def vids(old: float, new: float, variant: str = "cold-open-payoff",
         base: str = O.PRE_RULE) -> list[dict]:
    return ([{"average_view_duration_s": old, "opening": base}] * 4
            + [{"average_view_duration_s": new, "opening": variant}] * 4)


examined += 1
r = O.evaluate(vids(113, 90), now=start + timedelta(days=10), path=state)
if r["action"] != "wait" or state.exists():
    fails.append(f"evaluate() acted before {O.COMPARE_AFTER_DAYS} days: {r}")
examined += 1
r = O.evaluate(vids(113, 150), now=start + timedelta(days=29), path=state)
if r["action"] != "keep":
    fails.append(f"a variant that beats its baseline was not kept: {r}")
examined += 1
r = O.evaluate(vids(113, 100), now=start + timedelta(days=29), path=state)
doc = json.loads(state.read_text()) if state.exists() else {}
if (r["action"] != "switch" or doc.get("active") != "question-first-teaser"
        or not doc.get("history") or "not above" not in doc["history"][-1]["why"]):
    fails.append(f"a losing variant did not switch to the next one and log "
                 f"why: {r} / {doc}")
examined += 1
later = datetime.fromisoformat(doc["since"]) + timedelta(days=29)
v = (vids(113, 100) + [{"average_view_duration_s": 95,
                        "opening": "question-first-teaser"}] * 4)
r = O.evaluate(v, now=later, path=state)
if r["action"] != "switch" or r.get("to") != "cold-open-payoff":
    fails.append(f"with every variant tried and losing, evaluate() did not "
                 f"settle on the best measured one: {r}")
examined += 1
if O.active(state) not in O.VARIANTS:
    fails.append("active() returned an unknown variant")

# ------------------------------------------------------------ 6. the lane
msrc = (LOOP / "measure.py").read_text()
examined += 1
if '"opening": opening.variant_of(' not in msrc:
    fails.append("the measure lane does not tag each video with its opening")
import measure                                             # noqa: E402

fin = Path(tempfile.mkdtemp(prefix="finding-")) / "retention_finding.md"
saved = measure.FINDING
measure.FINDING = fin
try:
    cp = {"status": "measured", "format_verdict": "FORMAT PROBLEM",
          "mean_view_duration_mm_ss": "1m53s", "measured": 10,
          "floor_avd_seconds": 146.0, "videos_losing_viewers_in_first_2min": 6,
          "early_exit_threshold_minutes": 2.0, "mean_pct_of_actual_runtime": 23.9,
          "pct_basis": "x"}
    acting = O.evaluate(vids(113, 90), now=start, path=state.parent / "n.json",
                        write=False)
    measure.write_finding(cp, {}, acting)
finally:
    measure.FINDING = saved
examined += 1
txt = fin.read_text()
if "What the loop is doing about it" not in txt or "cold-open-payoff" not in txt:
    fails.append("the finding does not say what the loop is doing about it")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
