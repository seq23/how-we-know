#!/usr/bin/env python3
"""Every registered validator passes on the code this commit carries.

THE DEFECT THIS GUARDS ("exists but nothing invokes it"). On 2026-10-13 main
(632964f) was green while three registered validators failed on its own
content: V21 (a sentence shared by two scripts), V30 (50 rows of a tracked
manifest) and V32 (a scheduled episode's POV with no entry). Nothing in CI
ran `validate.run_all()`. test_validators.py proves each validator CATCHES a
planted defect and that each is registered, but never asked whether the real
registry passes on the real repo; the only callers of run_all() are the
Monday lane (loop/draft.py, weekly) and the breaker. So a validator could
fail for days while every merge went green, and the first to notice was the
next Monday lane, which stopped.

DECIDED: the full registry runs in CI and BLOCKS. Every validator already
decides for itself what it can see here - the machine-local ones (V9-V15,
V24, V13/V31 renders) go N/A when their footage, renders or Shorts are not
on this machine, by their own rule - so there is no Mac-only list to keep
and no allowlist of known failures. A row that is not PASS or N/A fails
this test, named.

LOOP_DRY_RUN=1 and V6's gaps file pointed at scratch, so a run writes no
channel state (run_all.py's state snapshot checks that too).
"""
from __future__ import annotations

import copy
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"
HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import validate  # noqa: E402
from common import read_json  # noqa: E402

validate.ATTRIBUTION_GAPS = Path(tempfile.mkdtemp(prefix="reg-gaps-")) / "attribution_gaps.json"


def check() -> list[str]:
    fails: list[str] = []

    # The test is only a gate if CI runs it: loop-tests.yml must run the
    # harness that globs test_*.py, on every pull request.
    # CI shards the suite (run_all.py --shard K/N); every shard 1..N must be
    # in the matrix or files - this one included - silently never run.
    wf = (ROOT / ".github" / "workflows" / "loop-tests.yml").read_text()
    if "loop/tests/run_all.py" not in wf or "pull_request" not in wf:
        fails.append("loop-tests.yml no longer runs loop/tests/run_all.py on "
                     "pull_request, so this registry gate blocks nothing")
    m = re.search(r"run_all\.py --shard \$\{\{ matrix\.shard \}\}/(\d+)", wf)
    shards = re.search(r"shard:\s*\[([0-9,\s]+)\]", wf)
    if m:
        n = int(m.group(1))
        have = sorted(int(x) for x in shards.group(1).split(",")) if shards else []
        if have != list(range(1, n + 1)):
            fails.append(f"loop-tests.yml runs run_all.py in {n} shards but its "
                         f"matrix names {have} - a missing shard is a slice of "
                         f"the suite that never runs")

    items = copy.deepcopy(read_json(ROOT / "loop" / "render_queue.json")["items"])
    ok, rows = validate.run_all(items)

    defined = set(re.findall(r"^def (v\d+_[a-z_]+)",
                             (LOOP / "validate.py").read_text(), re.M))
    if not rows:
        fails.append("validate.run_all() returned ZERO rows - the registry "
                     "examined nothing, which is a failure, not a pass")
    # run_reach's validators need the live channel and run in loop-reach.yml;
    # every OTHER defined validator must have produced exactly one row here.
    src = (LOOP / "validate.py").read_text()
    reach_body = re.search(r"^def run_reach\b.*?(?=\n\S)", src, re.S | re.M)
    reach = set(re.findall(r"(v\d+_[a-z_]+)\(", reach_body.group(0))) \
        if reach_body else set()
    if not reach:
        fails.append("could not read run_reach's validators from validate.py")
    want = len(defined - reach)
    if len(rows) != want:
        fails.append(f"run_all() returned {len(rows)} rows; validate.py defines "
                     f"{want} validators outside run_reach - some are not "
                     f"running, or one runs twice")

    for row in rows:
        st = row["status"]
        if st.startswith("PASS") or st.startswith("N/A"):
            continue
        fails.append(f"{row['validator']} is {st} on this commit: "
                     + "; ".join(row["failures"][:3])
                     + (f" (+{len(row['failures']) - 3} more)"
                        if len(row["failures"]) > 3 else ""))
    if not ok and not fails:
        fails.append("run_all() reported not all_passed, yet no row failed")
    print(f"inspected {len(rows)} registered validator(s) on this commit")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every registered validator passes on this commit"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
