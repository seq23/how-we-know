"""Every tracked path a loop stage can write is named by that stage's commit
pathspecs -- proven STATICALLY, before the stage runs.

CONFIRMED on run 34687628665 (2026-09-12, `loop · Sat 06:00 · score demand ÷
competition`, issue #78). research/competition.py wrote its named stop to
research/competition_stop.json -- tracked, and outside the weekly-score
pathspec -- so `git pull --rebase` refused three times on "You have unstaged
changes" and a full weekly scoring pass was thrown away. #79 fixed that
pathspec and added a RUNTIME guard in bin/loop-stage.sh that fails the stage
by name when a tracked file is left modified. That guard is right and it is
late: it fires on the Saturday, on the runner, after the work is done. This
test is the other half. loop/tools/write_set.py reads each stage's source,
follows calls (not imports) from its entry point through helpers, methods,
`with` blocks and subprocess entrypoints, evaluates every path constant, and
asks: does a pathspec for this stage cover every tracked file it can write?

Running it over main found the same class twice more, both latent:

  * mon-draft writes scripts/<slug>.md (loop/draft.py:164, when it AUTHORS
    rather than assembles) and pov/pov-assignments.json (loop/pov_match.py:602).
    Every Monday so far assembled; the first one that authors would have
    tripped the runtime guard with the script written and lost.
  * weekly-score writes research/mined_queries_<slug>.json through
    research/mine_domain.py the first time a domain is scored. Untracked when
    new, so not even the runtime guard could see it: mined on the runner,
    thrown away, mined again next week.

Both pathspecs are added in bin/loop-stage.sh. Negative proofs below restore
each defect -- the #78 line, and each of the two new ones -- and show the STRAY
return. Hard-fails on zero stages, zero resolved write targets, or a stage
whose closure resolved nothing.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, os.path.join(LOOP, "tools"))

import write_set as W                                       # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {name}")
    else:
        print(f"  ✗ {name}{(': ' + detail) if detail else ''}")
        fails.append(name)


def strays_with(script_text: str, stage_filter=None) -> dict[str, dict[str, list[str]]]:
    """stage -> {pattern: [uncovered tracked files]} under a given wrapper text."""
    table = W.pathspecs(script_text)
    tracked = W.tracked_files()
    out = {}
    for stage, entry, _wf in W.stages():
        if stage_filter and stage not in stage_filter:
            continue
        a = W.audit(stage, entry, table, tracked)
        if a["stray"]:
            out[stage] = a["stray"]
    return out


def main() -> int:
    script = open(W.LOOP_STAGE, encoding="utf-8").read()
    stages = W.stages()
    if not stages:
        print("FAIL: found zero `bin/loop-stage.sh <stage> <entry.py>` invocations "
              "in the workflows -- nothing examined")
        return 1
    print(f"  {len(stages)} stage(s) invoked from the workflows")

    # ------------------------------------------------------------ coverage
    table = W.pathspecs(script)
    tracked = W.tracked_files()
    check("the wrapper stages `loop` unconditionally (the state directory)",
          "loop" in table.get(None, []), str(table.get(None)))
    total_resolved = 0
    for stage, entry, wf in stages:
        a = W.audit(stage, entry, table, tracked)
        hits = a["tracked_hits"]
        total_resolved += len(a["targets"])
        check(f"{stage} ({entry}): resolved {len(a['targets'])} write target(s), "
              f"{len(hits)} on tracked paths, every one covered by "
              f"{a['specs']}", bool(a["targets"]) and not a["stray"],
              f"STRAY {a['stray']}" if a["stray"] else "resolved nothing -- the "
              "extractor cannot see this stage's writes, which is a failure of "
              "the proof, not a pass")
        hard = [u for u in a["unresolved"] if "cli/env-sourced" not in u]
        check(f"{stage}: every unresolved write target is CLI/env-sourced "
              f"(attributed at its caller)", not hard, str(hard))
    check("resolved write targets across all stages > 0", total_resolved > 0)

    # ------------------------------------------- the #78 file, specifically
    ws = W.audit("weekly-score", "loop/score.py", table, tracked)
    check("weekly-score's write set contains research/competition_stop.json "
          "(the file run 34687628665 left unstaged)",
          "research/competition_stop.json" in ws["tracked_hits"],
          str(sorted(ws["tracked_hits"])))
    check("weekly-score's write set contains research/mined_queries_*.json "
          "(the deep-mine output)",
          any(p.startswith("research/mined_queries") for p in ws["tracked_hits"]))
    md = W.audit("mon-draft", "loop/draft.py", table, tracked)
    check("mon-draft's write set contains scripts/*.md and pov/pov-assignments.json",
          any(p.startswith("scripts/") for p in md["tracked_hits"])
          and "pov/pov-assignments.json" in md["tracked_hits"],
          str(sorted(md["tracked_hits"])))

    # ------------------------------------------------- NEGATIVE PROOFS
    # Each restores ONE defect by deleting its pathspec line from the wrapper
    # text and shows the STRAY come back for exactly that stage.
    # Since 2026-09-25 weekly-score promotes held scripts too, so `git add
    # scripts` and the POV pathspec each appear in TWO stage blocks. A
    # proof removes the line inside ITS stage's `if [ "$STAGE" = ... ]`
    # block only - deleting every copy would prove the other stage's
    # defect, not this one's.
    def in_block(stage: str, line: str) -> str:
        return (r'(if \[ "\$STAGE" = "' + re.escape(stage) + r'" \]; then\n'
                r'(?:(?!^fi\n).*\n)*?)^\s*' + line + r'\n')

    proofs = [
        ("weekly-score", in_block("weekly-score",
                                  r"git add research/competition\*\.json 2>/dev/null"),
         "research/competition_stop.json", "the #78 defect"),
        ("weekly-score", in_block("weekly-score",
                                  r"git add research/mined_queries\*\.json 2>/dev/null"),
         "research/mined_queries_*.json", "the deep-mine output"),
        ("weekly-score", in_block("weekly-score", r"git add scripts 2>/dev/null"),
         "scripts/*.md", "a promoted hold's script"),
        ("weekly-score", in_block("weekly-score",
                                  r"git add pov/pov-assignments\.json 2>/dev/null"),
         "pov/pov-assignments.json", "a promoted hold's POV record"),
        ("mon-draft", in_block("mon-draft", r"git add scripts 2>/dev/null"),
         "scripts/*.md", "the promoted script"),
        ("mon-draft", in_block("mon-draft",
                               r"git add pov/pov-assignments\.json 2>/dev/null"),
         "pov/pov-assignments.json", "the POV bank record"),
    ]
    for stage, pattern, expect, what in proofs:
        broken, n = re.subn(pattern, r"\1", script, flags=re.M)
        check(f"negative proof setup: the '{expect}' pathspec line exists to remove",
              n == 1, f"matched {n}")
        if n != 1:
            continue
        s = strays_with(broken, {stage})
        got = s.get(stage, {})
        check(f"negative proof: without its pathspec, {stage} shows STRAY "
              f"{expect} ({what})", expect in got, f"strays={sorted(got)}")
    check("with every pathspec present there is no STRAY anywhere",
          not strays_with(script))

    # -------------------------------------------------- the runtime guard
    check("bin/loop-stage.sh still carries the Rule 0 runtime guard (#79) that "
          "names a stray tracked file",
          'STRAY="$(git diff --name-only' in script
          and "modified tracked file(s) that no pathspec" in script)

    print(f"\n{len(fails)} failure(s)")
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
