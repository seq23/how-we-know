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

    # ------------------------------------------------ V14 / V15, the Shorts
    #
    # These read the finished 1080x1920 files. The negative case is built by
    # rewriting a Short's RECEIPT, never the validator's own inputs: V14 must
    # re-resolve the credit from the imagery manifests and read it back off the
    # pixels, so a receipt that claims a credited beat the picture does not
    # credit has to fail. A validator that trusted the receipt would pass.
    import json
    from pathlib import Path

    shorts = sorted(Path(ROOT, "shorts").glob("*.mp4.short.json"))
    if not shorts:
        fails.append("no Short receipts in shorts/ - V14 and V15 could not be "
                     "exercised at all")
    else:
        # zero-item guard: an empty Shorts directory must FAIL both.
        for name, fn in (("V14", validate.v14_shorts_attribution),
                         ("V15", validate.v15_shorts_caption_crop)):
            examined += 1
            empty = Path(tmp, f"empty-{name}")
            empty.mkdir(parents=True, exist_ok=True)
            validate.SHORTS_DIR = empty
            if fn().ok:
                fails.append(f"{name} passed an empty shorts/ directory")

        # a credited beat the picture does not credit. Built on a Short whose
        # chrome legitimately draws NO credit strip, so the grafted beat's
        # credit cannot possibly be on screen.
        examined += 1
        sys.path.insert(0, os.path.join(ROOT, "visuals"))
        import shorts as SH  # noqa: E402
        bare = None
        for path in shorts:
            rec = json.loads(path.read_text())
            plan = json.loads(
                Path(ROOT, "plans", f"{rec['slug']}.json").read_text())
            if SH.resolve_credits(rec["slug"], plan, rec["beats"])[0]:
                continue                    # this one does show a credit
            extra = [i for i, b in enumerate(plan)
                     if b.get("segment") == "species_image"
                     and i not in rec["beats"]
                     and SH.resolve_credits(rec["slug"], plan, [i])[0]]
            if extra:
                bare = (path, rec, extra[0])
                break
        if bare is None:
            fails.append("no uncredited Short with a credited beat to graft on; "
                         "V14's negative case could not be built")
        else:
            path, rec, extra_beat = bare
            mp4 = Path(str(path)[: -len(".short.json")])
            pen = Path(tmp, "pen")
            pen.mkdir(parents=True, exist_ok=True)
            shutil.copy(mp4, pen / mp4.name)
            rec["beats"] = sorted(rec["beats"] + [extra_beat])
            (pen / (mp4.name + ".short.json")).write_text(json.dumps(rec))
            validate.SHORTS_DIR = pen
            if validate.v14_shorts_attribution().ok:
                fails.append("V14 passed a Short whose beats require a credit "
                             "that is not on screen")

        # a Short that cropped nothing: the burned caption band is still there
        examined += 1
        nocrop = Path(tmp, "nocrop")
        nocrop.mkdir(parents=True, exist_ok=True)
        rec2 = json.loads(shorts[0].read_text())
        mp4b = Path(str(shorts[0])[: -len(".short.json")])
        shutil.copy(mp4b, nocrop / mp4b.name)
        rec2["source_crop_height"] = 1080
        (nocrop / (mp4b.name + ".short.json")).write_text(json.dumps(rec2))
        validate.SHORTS_DIR = nocrop
        if validate.v15_shorts_caption_crop().ok:
            fails.append("V15 passed a Short whose crop kept the whole 1080-row "
                         "source, burned captions and all")

        # and the real ones still pass
        examined += 1
        validate.SHORTS_DIR = Path(ROOT, "shorts")
        for r in (validate.v14_shorts_attribution(),
                  validate.v15_shorts_caption_crop()):
            if not r.ok:
                fails.append(f"{r.name} FAILED on the real shorts/: {r.failures}")

    shutil.rmtree(tmp, ignore_errors=True)

    if examined == 0:
        fails.append("examined ZERO validator behaviours")
    print(f"inspected {examined} validator behaviour(s)")
    return fails


def check_registry() -> list[str]:
    """Every validator someone calls exists, and every one that exists is run.

    WHY THIS EXISTS. `loop · tests` failed on main every day from 2026-09-01
    with:

        AttributeError: module 'validate' has no attribute
                        'v15_shorts_caption_crop'

    `loop/r2.py` was committed calling `V.v15_shorts_caption_crop`; the half of
    the change that DEFINED it never landed. Half a change on main, red every
    day, and nothing said which half was missing — the traceback names the
    caller, not the fact that a sibling commit is absent.

    Two directions, because the defect has two shapes:

      * **called but not defined** — the break above. Any `validate.vNN_x` or
        `V.vNN_x` reference anywhere in `loop/` must resolve.
      * **defined but never called** — a validator nothing invokes is inert,
        and this repo's recurring defect list names that one explicitly. Every
        `vNN_` function in validate.py must appear in `run_all` or `run_reach`.

    Hard-fails if it finds zero references, which would mean the scan itself
    stopped reaching what it governs.
    """
    import re
    fails, examined = [], 0
    loop_dir = os.path.join(ROOT, "loop")

    # -- called but not defined -------------------------------------------
    refs = set()
    for name in sorted(os.listdir(loop_dir)):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(loop_dir, name)).read()
        for m in re.finditer(r"\b(?:validate|V)\.(v\d+_[a-z_]+)", text):
            refs.add((name, m.group(1)))
    for where, attr in sorted(refs):
        examined += 1
        if not hasattr(validate, attr):
            fails.append(f"loop/{where} calls validate.{attr}, which does not "
                         f"exist — half a change landed, and the lane using it "
                         f"crashes rather than validating anything")
    if not refs:
        fails.append("found ZERO validator references in loop/ — the scan is "
                     "not reaching what it governs")

    # -- defined but never called -----------------------------------------
    src = open(os.path.join(loop_dir, "validate.py")).read()
    defined = set(re.findall(r"^def (v\d+_[a-z_]+)", src, re.M))
    runners = "".join(re.findall(r"^def run_(?:all|reach)\b.*?(?=\n\S)", src,
                                 re.S | re.M))
    if not defined:
        fails.append("found ZERO validators defined in loop/validate.py")
    for name in sorted(defined):
        examined += 1
        if name not in runners:
            fails.append(f"validate.{name} is defined but neither run_all nor "
                         f"run_reach calls it — a validator nothing invokes is "
                         f"inert, and passes by never running")

    print(f"inspected {examined} validator registration(s)")
    return fails


if __name__ == "__main__":
    f = check() + check_registry()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every validator catches its own defect and fails on empty"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
