"""The hook rule: stake-then-payoff is first, in force, gated and measured.

Owner instruction, 13 Oct 2026: "a hook, not an encyclopaedia opening".
WHAT THIS PROVES (scratch state only):
  1. stake-then-payoff is FIRST in loop/opening.py VARIANTS and is the active
     rule in the committed loop/state/opening_variant.json;
  2. the gate: a <=15-word staked first sentence whose payoff lands inside 75
     words passes; a 16+-word first sentence fails; a first sentence that
     restates the title (or the question) fails; a payoff pushed past 75 words
     still fails;
  3. the author's draft gate and prompt carry it (a failing draft is
     redrafted inside the retry loop); V44 holds a stamped script to it;
  4. the 28-day measurement still works with it active: it waits, keeps a
     winner, and a loser switches to cold-open-payoff and logs why;
  5. the module docstring records the instruction and that published cuts are
     never edited in place.

NEGATIVE PROOF (run once, 2026-10-13): set "first_sentence_max" to 40 ->
case 2 "16+-word first sentence" fails here; restore -> green.
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
os.environ["LOOP_DRY_RUN"] = "1"

import opening as O                                           # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


V = "stake-then-payoff"
check(next(iter(O.VARIANTS)) == V, f"{V} is not first in VARIANTS")
check(json.loads((LOOP / "state" / "opening_variant.json").read_text())["active"] == V
      and O.active() == V, f"{V} is not the active rule")


def script(first: str, filler_words: int = 0, title: str = "The ocean layer "
           "where sunlight never reaches") -> str:
    filler = " ".join(["Pressure"] * filler_words)
    return (f"# What is the midnight zone?\n\n**Domain:** deep-sea-ocean-science\n\n"
            f"## YouTube title\n\n{title}\n\n"
            f"## Direct-answer lock\n\nThe midnight zone is the ocean layer from "
            f"1,000 to 4,000 meters where no sunlight reaches.\n\n"
            f"## Narration\n\n### Cold open\n\n{first} {filler} The midnight zone "
            f"is the ocean layer from 1,000 to 4,000 meters where no sunlight "
            f"reaches. Here is how we know.\n\n### Title card\n\nWhat is the "
            f"midnight zone?\n\n## Sources\n\n- NOAA — https://oceanexplorer.noaa.gov/\n")


good = script("Below 1,000 meters, the last photon of sunlight is gone.")
check(not O.problems(good, V), f"a staked hook failed: {O.problems(good, V)}")
long_first = script("Below one thousand meters in every ocean on Earth the very "
                    "last photon of daylight finally runs out completely.")
check(any("at most 15" in p for p in O.problems(long_first, V)),
      "a 16+-word first sentence passed the hook rule")
restates = script("The midnight zone is the ocean layer where sunlight never reaches.")
check(any("restates the title" in p for p in O.problems(restates, V)),
      "a first sentence restating the title passed")
q_restate = script("What is the midnight zone, the dark zone?",
                   title="Below 1,000 meters the last photon is gone")
check(any("restates the question" in p for p in O.problems(q_restate, V)),
      "a first sentence restating the question passed")
buried = script("Below 1,000 meters, the last photon of sunlight is gone.", 90)
check(any("not in the first 75" in p for p in O.problems(buried, V)),
      "a payoff past 75 words passed the hook rule")

import author                                                 # noqa: E402
pov = {"line": "x" * 70, "pov_id": "pov-000", "tag": "t", "tier": "1"}
check(any(p.startswith(f"opening rule {V}") for p in author.shape_problems(long_first, pov)),
      "author.shape_problems does not redraft a weak hook")
check(O.prompt_text(V) in author.build_prompt("what is the midnight zone", pov)[0]["content"],
      "the drafting prompt does not carry the hook rule")
check("15 words" in O.prompt_text(V) or "at most 15" in O.prompt_text(V),
      "the hook prompt does not state the 15-word limit")

import validate as VAL                                        # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="hook-"))
saved_root = VAL.ROOT
try:
    (tmp / "scripts").mkdir()
    (tmp / "scripts" / "bad.md").write_text(O.mark(long_first, V))
    (tmp / "scripts" / "ok.md").write_text(O.mark(good, V))
    VAL.ROOT = tmp
    res = VAL.v44_opening_payoff_first([{"slug": "bad", "script": "scripts/bad.md"},
                                        {"slug": "ok", "script": "scripts/ok.md"}]).as_dict()
    check(any("bad" in f for f in res["failures"]) and not any("ok:" in f for f in res["failures"]),
          f"V44 did not hold a stamped script to the hook rule: {res['failures']}")
finally:
    VAL.ROOT = saved_root

# ------------------------------------------------- 4. measurement, with it active
state = tmp / "opening_variant.json"
start = datetime(2026, 10, 13, tzinfo=timezone.utc)
rows = ([{"average_view_duration_s": 113, "opening": O.PRE_RULE}] * 4 +
        [{"average_view_duration_s": 90, "opening": V,
          "aired_at": (start + timedelta(days=i)).date().isoformat()} for i in range(4)])
r = O.evaluate(rows, now=start + timedelta(days=5), path=state)
check(r["action"] == "wait" and r["active"] == V, f"did not wait first: {r}")
due = start + timedelta(days=2 + O.COMPARE_AFTER_DAYS + 1)
win = [dict(x, average_view_duration_s=150) if x["opening"] == V else x for x in rows]
r = O.evaluate(win, now=due, path=state)
check(r["action"] == "keep", f"a winning hook was not kept: {r}")
r = O.evaluate(rows, now=due, path=state)
doc = json.loads(state.read_text())
check(r["action"] == "switch" and doc["active"] == "cold-open-payoff"
      and "not above" in doc["history"][-1]["why"],
      f"a losing hook did not switch to cold-open-payoff and log why: {r}")

doc_s = O.__doc__ or ""
check("13 Oct 2026" in doc_s and "encyclopaedia" in doc_s
      and "never edited in place" in doc_s,
      "loop/opening.py docstring does not record the 13 Oct 2026 instruction "
      "and the never-in-place rule")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
