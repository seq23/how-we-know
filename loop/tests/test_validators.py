"""The validators must actually catch things — proven by breaking the input.

A validator suite that has only ever seen a good week is untested. For each
hard validator this constructs a queue row that violates exactly what it
governs and asserts the failure returns; then it asserts the real week passes.

It also asserts the zero-item guard: every validator handed an empty list must
FAIL, not pass. A green tick on an empty loop is the defect, not the absence of
one.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import validate  # noqa: E402
from common import read_json  # noqa: E402

REAL = os.path.join(LOOP, "render_queue.json")


def row_for(slug: str, script: str) -> dict:
    return {"slug": slug, "question": "What is the deepest part of the ocean?",
            "script": script}


def check() -> list[str]:
    fails, examined = [], 0
    tmp = tempfile.mkdtemp()

    # ------------------------------------------------ zero-item guard
    for name, fn in (("V3 taxonomy", validate.v3_taxonomy),
                     ("V4 pov", validate.v4_pov),
                     ("V5 sources-present", validate.v5_sources_present),
                     ("V6 attribution", validate.v6_attribution),
                     ("V7 plans", validate.v7_plans)):
        examined += 1
        r = fn([])
        if r.ok:
            fails.append(f"{name} PASSED on an empty list — a validator that "
                         f"examines zero items must fail")
        if "examined 0" not in r.status:
            fails.append(f"{name} did not report that it examined zero items")

    # ------------------------------------------------ the real week passes
    if os.path.exists(REAL):
        q = read_json(REAL)
        items = [dict(i) for i in q["items"]]
        if items:
            examined += 1
            for name, fn in (("V3", validate.v3_taxonomy),
                             ("V4", validate.v4_pov),
                             ("V5", validate.v5_sources_present),
                             ("V7", validate.v7_plans)):
                r = fn([dict(i) for i in items])
                if not r.ok:
                    fails.append(f"{name} failed on the real queue: "
                                 f"{r.failures[:2]}")

    # ------------------------------------------------ break each one
    src = os.path.join(ROOT, "scripts", "10-what-is-the-deepest-part-of-the-ocean.md")
    if not os.path.exists(src):
        fails.append("the fixture script is missing; these negatives cannot run")
        print(f"inspected {examined} validator behaviour(s)")
        return fails
    body = open(src).read()

    # V5: strip the sources from a script that speaks numbers.
    examined += 1
    broken = os.path.join(tmp, "no-sources.md")
    open(broken, "w").write(body.split("## Sources")[0] + "## Sources\n\n")
    rel = os.path.relpath(broken, ROOT)
    r = validate.v5_sources_present([row_for("no-sources", rel)])
    if r.ok:
        fails.append("V5 passed a digit-bearing script with an empty ## Sources")

    # V5: a source entry with no URL is not a source.
    examined += 1
    nourl = os.path.join(tmp, "no-url.md")
    open(nourl, "w").write(body.split("## Sources")[0] +
                           "## Sources\n\n- NOAA says so\n- Someone else\n")
    r = validate.v5_sources_present(
        [row_for("no-url", os.path.relpath(nourl, ROOT))])
    if r.ok:
        fails.append("V5 passed a source entry with no URL")

    # V4: a script with no POV assignment must fail, never be invented.
    examined += 1
    r = validate.v4_pov([row_for("not-a-real-slug", os.path.relpath(src, ROOT))])
    if r.ok:
        fails.append("V4 passed a video with no POV assignment — the pipeline "
                     "must never invent a POV line")

    # V4: the same POV id twice in one week must fail the rotation window.
    examined += 1
    if os.path.exists(REAL):
        q = read_json(REAL)
        if len(q["items"]) >= 2:
            dup = [dict(q["items"][0]), dict(q["items"][0])]
            dup[1]["slug"] = q["items"][0]["slug"]
            r = validate.v4_pov(dup)
            if r.ok:
                fails.append("V4 passed the same POV id used twice in one week")

    # V3: a question that touches a hard exclusion must fail.
    examined += 1
    bad = row_for("bad", os.path.relpath(src, ROOT))
    bad["question"] = "What supplement cures deep sea sickness?"
    r = validate.v3_taxonomy([bad])
    if r.ok:
        fails.append("V3 passed a question touching a hard exclusion")

    # V7: a file that is not a script cannot plan to real beats.
    examined += 1
    empty = os.path.join(tmp, "empty.md")
    open(empty, "w").write("# nothing\n")
    r = validate.v7_plans([row_for("empty", os.path.relpath(empty, ROOT))])
    if r.ok:
        fails.append("V7 passed a file that plans to no beats")

    shutil.rmtree(tmp, ignore_errors=True)

    if examined == 0:
        fails.append("examined ZERO validator behaviours")
    print(f"inspected {examined} validator behaviour(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every validator catches its own defect and fails on empty"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
