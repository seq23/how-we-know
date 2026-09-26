"""What the Monday lane writes must pass NEXT week's full validation.

THE INCIDENT (found 2026-09-26, before it fired). loop/validate.py run over
the repository failed V1, V21, V27, V36 and V43. The Monday lane validates
only the week's own items and then promotes them into scripts/, so every one
of these would have surfaced on 2026-09-28 as a validator failure over LAST
week's work, where nothing retries - and draft.py trips the circuit breaker
on any validator failure, halting publishing. Three causes were structural:

  * V36: loop/author.py's FORMAT template, its REQUIRED_SECTIONS and
    draft.py's brief all still required "## Human fingerprint gate", the
    heading V36 has rejected in scripts/ since 2026-09-05. Every generated
    script was born failing it (six on disk).
  * V1 (parse): the author's retry loop checked that a directive's numbers
    were spoken, never that the planner could PARSE it. Three {{uncertain}}
    directives with a prose VALUE or RANGE reached scripts/.
  * V27: batch_queue refuses same-question rows on read since #127/#128 and
    names each in refused_entries(); V27 read every refusal as a lane that
    cannot see a domain (20 failures).

WHAT THIS PROVES:
  1. the generator's template, filled, satisfies V36's own constants
     (GATE_BULLETS, GATE_DEBT) and carries no retired heading; the author's
     REQUIRED_SECTIONS and the human brief name the same heading;
  2. author.shape_problems() rejects each of the three unparseable
     directives found on 2026-09-26, and accepts a parseable one;
  3. V27 accepts a refused row that is NAMED with a reason, and still fails a
     row that is merely missing from the merged queue, or refused with no
     reason.
Hard-fails on zero examined items.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
os.environ.setdefault("LOOP_STOPS_DIR", tempfile.mkdtemp(prefix="gen-val-"))
sys.path.insert(0, str(LOOP))

import author        # noqa: E402
import batch_queue   # noqa: E402
import draft         # noqa: E402
import validate      # noqa: E402

BAD_20260926 = [
    "{{uncertain: seven hundred fifty thousand | species | range five hundred "
    "thousand to ten million | low confidence | estimated marine species, many "
    "deep-sea}}",
    "{{uncertain: 10 | billion light-years | Cepheid limit | high confidence | "
    "beyond this, Type Ia supernovae are used}}",
    "{{uncertain: 20,000 to 2 million | bacterial operational taxonomic units | "
    "published range, model-dependent | low confidence | Marine bacterial "
    "diversity estimate}}",
]
GOOD = "{{uncertain: 100 | °C/s | 50 to 200 | composition-dependent | critical cooling rate}}"


def check() -> list[str]:
    fails, examined = [], 0

    # 1. the gate section the generator writes is the one V36 accepts
    filled = author.FORMAT.format(pov_id="pov-001", pov_line="x",
                                  domain="deep-sea-ocean-science", wpm=145)
    examined += 1
    if "## Human fingerprint gate" in filled:
        fails.append("author.FORMAT still writes the retired '## Human "
                     "fingerprint gate' heading V36 rejects")
    if "## Editorial gate" not in filled:
        fails.append("author.FORMAT writes no '## Editorial gate' section")
    else:
        i = filled.index("## Editorial gate")
        j = filled.find("\n## ", i + 1)
        block = filled[i:j if j > 0 else len(filled)]
        m = validate.GATE_DEBT.search(block)
        if m:
            fails.append(f"author.FORMAT's gate records a human step nobody "
                         f"performs ({m.group(0)!r}); V36 fails it")
        for bullet in validate.GATE_BULLETS:
            examined += 1
            if bullet not in block:
                fails.append(f"author.FORMAT's gate is missing V36's "
                             f"{bullet!r}")
    examined += 1
    if "## Editorial gate" not in author.REQUIRED_SECTIONS or any(
            "fingerprint" in s_ for s_ in author.REQUIRED_SECTIONS):
        fails.append(f"author.REQUIRED_SECTIONS does not require the heading "
                     f"V36 does: {author.REQUIRED_SECTIONS}")
    src = (LOOP / "draft.py").read_text()
    if '"## Human fingerprint gate"' in src:
        fails.append("loop/draft.py's authoring brief still asks a human for "
                     "the retired '## Human fingerprint gate' section")
    if not hasattr(draft, "main"):
        fails.append("loop/draft.py did not import")

    # 2. unparseable directives are caught inside the retry loop
    def script(line: str) -> str:
        return ("# Q\n\n## Narration\n\n" + line + "\nWe measured 100 and 50 "
                "to 200 °C/s, a critical cooling rate that is "
                "composition-dependent.\n\n## Editorial gate\n\n- x\n")
    for bad in BAD_20260926:
        examined += 1
        if not author.directive_parse_problems(script(bad)):
            fails.append(f"the author's self-check accepted an unparseable "
                         f"directive: {bad[:70]}")
    examined += 1
    if author.directive_parse_problems(script(GOOD)):
        fails.append(f"the author's self-check rejected a parseable directive: "
                     f"{author.directive_parse_problems(script(GOOD))}")
    if "directive_parse_problems(text)" not in (LOOP / "author.py").read_text():
        fails.append("shape_problems() does not call directive_parse_problems")

    # 3. V27 and refused rows
    real_refused = batch_queue.refused_entries
    real_queued = batch_queue.queued_slugs
    try:
        examined += 1
        r = validate.v27_lanes_see_every_domain()
        if r.failures:
            fails.append(f"V27 fails on the real repo: {r.failures[:2]}")
        refused = real_refused()
        if refused:
            examined += 1
            gone = refused[0]["slug"]
            batch_queue.refused_entries = lambda: [
                dict(x, why=None, killed_by=None) if x["slug"] == gone else x
                for x in refused]
            r = validate.v27_lanes_see_every_domain()
            if not any("no reason" in f_ for f_ in r.failures):
                fails.append("V27 accepted a refused row that names no reason")
        batch_queue.refused_entries = real_refused
        examined += 1
        merged = real_queued()
        victim = merged[0]
        batch_queue.queued_slugs = lambda: [s_ for s_ in merged if s_ != victim]
        r = validate.v27_lanes_see_every_domain()
        if not any("absent from the merged queue" in f_ for f_ in r.failures):
            fails.append(f"V27 did not fail when {victim} silently vanished "
                         f"from the merged queue")
    finally:
        batch_queue.refused_entries = real_refused
        batch_queue.queued_slugs = real_queued

    if examined == 0:
        fails.append("examined ZERO items")
    print(f"inspected {examined} generator/validator item(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - what the Monday lane writes passes next week's full "
          "validation" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
