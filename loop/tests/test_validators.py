"""The validators must actually catch things — proven by breaking the input.

A validator suite that has only ever seen a good week is untested. For each
hard validator this constructs a queue row that violates exactly what it
governs and asserts the failure returns; then it asserts the real week passes.

It also asserts the zero-item guard: every validator handed an empty list must
FAIL, not pass. A green tick on an empty loop is the defect, not the absence of
one.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import validate  # noqa: E402

# V6 records its gaps in loop/state/attribution_gaps.json, the committed file
# the approval page reads. This test feeds it fixtures, so a run here rewrote
# that file with fixture results. Point it at scratch instead.
from pathlib import Path as _Path  # noqa: E402
validate.ATTRIBUTION_GAPS = _Path(tempfile.mkdtemp(prefix="v6-gaps-")) / "attribution_gaps.json"
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

    # `shorts/` holds rendered MP4s and is gitignored, so it does not exist on
    # an Actions runner at all. That is not the same thing as an empty one.
    #
    # Absent because the artefacts are gitignored -> these two negatives cannot
    # run HERE, and saying "V14 could not be exercised" as a FAILURE would mean
    # loop/tests is red on every CI run forever for an environment gap. That is
    # how a suite stops being read.
    #
    # Present but empty -> a real defect, and it still fails. So the two states
    # are distinguished by asking git, not by counting files.
    shorts_dir = Path(ROOT, "shorts")
    shorts = sorted(shorts_dir.glob("*.mp4.short.json"))
    ignored = subprocess.run(["git", "check-ignore", "-q", "shorts"],
                             cwd=ROOT).returncode == 0
    if not shorts and shorts_dir.exists() and not ignored:
        fails.append("shorts/ is present, tracked and holds no receipts - V14 "
                     "and V15 could not be exercised at all")
    elif not shorts:
        # Not a pass, and not a silent skip: named, counted, and pointed at the
        # machine where it DOES run. bin/make-shorts.sh runs V14/V15 for real
        # against the pixels on the Mac.
        print("  · shorts/ is gitignored and absent here, so V14 and V15's "
              "negatives cannot run on this machine. They are exercised on the "
              "Mac, where the rendered Shorts exist.")
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
            # credits as they stand with NO footage on any beat: the species
            # and `source` lines alone (the render record is not needed to
            # find a beat that is credited either way)
            none = {i: None for i in range(len(plan))}
            if SH.resolve_credits(rec["slug"], plan, rec["beats"], none)[0]:
                continue                    # this one does show a credit
            extra = [i for i, b in enumerate(plan)
                     if b.get("segment") == "species_image"
                     and i not in rec["beats"]
                     and SH.resolve_credits(rec["slug"], plan, [i], none)[0]]
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


def inspect_src(fn) -> str:
    import inspect  # noqa: PLC0415
    return inspect.getsource(fn)


def check_v21() -> list[str]:
    """V21 exempts [HUMAN] lines BY TAG, keeps narrated prose strict, and
    bounds [HUMAN] reuse by pov_match's rotation window.

    2026-10-12, run 38272528658: the Monday lane went red because two scripts
    shared the owner's own interview line, which pov_match reuses on purpose.
    (a) a shared [HUMAN] line passes; (b) a shared narrated sentence fails;
    (c) one [HUMAN] line in more unaired scripts than the window fails, while
    the same count with the extras aired passes. Hard-fails on zero cases.
    """
    fails, cases = [], 0
    human = "[HUMAN] How do we know an animal behaves a certain way when we've seen it three times?"
    narrated = "The rest of this video follows that question through every single source we could find."

    def write(d, name, extra):
        Path(d, name + ".md").write_text(
            "# T\n\n## Narration\n\nA short opening line here.\n\n"
            f"Unique prose for {name} with enough words to count as a sentence.\n\n"
            f"{extra}\n\n## Sources\n\n- x\n")

    def run(names_extra, aired=(), window=2, live=None):
        d = tempfile.mkdtemp(prefix="v21-")
        for n, e in names_extra:
            write(d, n, e)
        live = {n for n, _ in names_extra} if live is None else live
        return validate.v21_no_boilerplate(scripts_dir=d, aired=aired,
                                           window=window, live=live)

    from pathlib import Path  # noqa: PLC0415
    # (a) a [HUMAN] line shared by two scripts is the owner's voice, not boilerplate
    cases += 1
    r = run([("a", human), ("b", human)])
    if r.failures or r.examined != 2:
        fails.append(f"V21 (a): two scripts sharing a [HUMAN] line must pass; "
                     f"got examined={r.examined} failures={r.failures}")
    # (b) a narrated sentence shared by two scripts is still boilerplate
    cases += 1
    r = run([("a", narrated), ("b", narrated)])
    if not any("verbatim narrated" in f for f in r.failures):
        fails.append("V21 (b): two scripts sharing an 8+ word NARRATED sentence "
                     "must fail; the [HUMAN] exemption has swallowed narration")
    # (b') the SAME words, tagged in one script and narrated in two others,
    # still fail on the narrated pair - the tag exempts lines, not text.
    cases += 1
    r = run([("a", "[HUMAN] " + narrated), ("b", narrated), ("c", narrated)])
    if not any("verbatim narrated" in f for f in r.failures):
        fails.append("V21 (b'): exemption must be by the [HUMAN] tag in the "
                     "source, never by matching the text of a human line")
    # (c) the same [HUMAN] line in more unaired scripts than the window fails
    cases += 1
    r = run([("a", human), ("b", human), ("c", human)], window=2)
    if not any("rotation window" in f for f in r.failures):
        fails.append("V21 (c): a [HUMAN] line in 3 unaired scripts with a "
                     "window of 2 must fail - the exemption became a loophole")
    # (c') aired scripts do not count toward the bound
    cases += 1
    r = run([("a", human), ("b", human), ("c", human)], aired={"a"}, window=2)
    if r.failures:
        fails.append(f"V21 (c'): only UNAIRED scripts count against the window; "
                     f"got {r.failures}")
    # (d) a DEAD script (not live: killed, never queued, never aired) is not
    # judged - but a live pair with the same sentence still fails, and a dead
    # script is reported by name, never dropped silently.
    cases += 1
    r = run([("a", narrated), ("b", narrated), ("c", "")], live={"a", "c"})
    if r.failures or r.examined != 2:
        fails.append(f"V21 (d): a sentence shared with a dead script must not "
                     f"fail and the dead script must not be examined; got "
                     f"examined={r.examined} failures={r.failures}")
    if not any("b.md" in n and "dead-topic" in n for n in r.notes):
        fails.append("V21 (d): the dead script was dropped without a note")
    cases += 1
    r = run([("a", narrated), ("b", narrated), ("c", "")], live={"a", "b"})
    if not any("verbatim narrated" in f for f in r.failures):
        fails.append("V21 (d'): two LIVE scripts sharing a narrated sentence "
                     "must still fail when a dead script sits beside them")
    # (d'') the live set is batch_queue.live_slugs(), never a second list
    cases += 1
    if "live_slugs()" not in inspect_src(validate.v21_no_boilerplate):
        fails.append("V21 must take its live set from batch_queue.live_slugs()")
    # the window is pov_match's own, never a hardcoded copy
    cases += 1
    import inspect  # noqa: PLC0415
    if "rotation_window()" not in inspect.getsource(validate.v21_no_boilerplate):
        fails.append("V21 must read its window from pov_match.rotation_window()")
    # (e) 2026-10-26, run 40311984912: a draft the run is ABOUT to promote is
    # judged at the gate. It sat in loop/drafts/ while V21 globbed scripts/
    # alone, so the collision surfaced a commit later on main.
    cases += 1
    sd = tempfile.mkdtemp(prefix="v21-scripts-")
    dd = tempfile.mkdtemp(prefix="v21-drafts-")
    write(sd, "a", narrated)
    write(dd, "p", narrated)
    item = {"slug": "p", "script": str(Path(dd, "p.md"))}
    r = validate.v21_no_boilerplate(scripts_dir=sd, aired=(), window=2,
                                    live={"a"}, items=[item])
    if r.examined != 2 or not any("verbatim narrated" in f and "p.md" in f
                                  for f in r.failures):
        fails.append(f"V21 (e): a draft pending promotion that repeats a live "
                     f"script's sentence must fail at the gate; got "
                     f"examined={r.examined} failures={r.failures}")
    # (e') promotion never overwrites scripts/<slug>.md, so a draft whose slug
    # already has a script is not pending and not judged twice.
    cases += 1
    write(sd, "p", "")
    r = validate.v21_no_boilerplate(scripts_dir=sd, aired=(), window=2,
                                    live={"a", "p"}, items=[item])
    if r.failures or r.examined != 2:
        fails.append(f"V21 (e'): a draft whose scripts/ copy exists is not "
                     f"pending; got examined={r.examined} failures={r.failures}")
    # (e'') run_all hands its queue rows to V21, or (e) never runs in the lane
    cases += 1
    if "v21_no_boilerplate(items=items)" not in inspect_src(validate.run_all):
        fails.append("V21 (e''): validate.run_all() must pass its items to "
                     "v21_no_boilerplate, or drafts pending promotion go unjudged")
    # (f) the author's retry loop applies the same rule to draft TEXT, against
    # live scripts AND live unpromoted drafts, never against its own slug.
    cases += 1
    sd = tempfile.mkdtemp(prefix="v21-idx-s-")
    dd = tempfile.mkdtemp(prefix="v21-idx-d-")
    write(sd, "a", narrated)
    write(dd, "q", "Another long narrated sentence that only the draft q says aloud.")
    idx = validate.live_narration_index(scripts_dir=sd, drafts_dir=dd,
                                        live={"a", "q"})
    text = Path(sd, "a.md").read_text().replace("Unique prose for a", "Unique prose for z")
    probs = validate.verbatim_repeat_problems(text, "z", index=idx)
    if len(idx) < 2 or not any("a.md" in x for x in probs):
        fails.append(f"V21 (f): verbatim_repeat_problems must flag a draft "
                     f"repeating a live script; index={len(idx)} probs={probs}")
    own = validate.live_narration_index(exclude_slug="a", scripts_dir=sd,
                                        drafts_dir=dd, live={"a", "q"})
    if validate.verbatim_repeat_problems(text, "a", index=own):
        fails.append("V21 (f): re-authoring a slug must not be judged "
                     "against its own previous script")
    cases += 1
    import author as _author  # noqa: PLC0415
    if ("verbatim_repeat_problems" not in inspect_src(_author.shape_problems)
            or "shape_problems(text, pov, slug)" not in inspect_src(_author.draft)):
        fails.append("V21 (f'): author.shape_problems must apply "
                     "verbatim_repeat_problems and author.draft must pass the "
                     "slug, or a stock sentence reaches the gate unretried")
    # zero scripts examined is a failure, not a pass
    cases += 1
    r = validate.v21_no_boilerplate(scripts_dir=tempfile.mkdtemp(prefix="v21-"),
                                    aired=(), window=2, live=set())
    if r.status != "FAIL(examined 0)" and not r.failures:
        fails.append(f"V21 on an empty scripts dir must fail; got {r.status}")
    if cases == 0:
        fails.append("check_v21 examined zero cases")
    print(f"inspected {cases} V21 case(s)")
    return fails


def check_v30() -> list[str]:
    """V30 rule B: a tracked manifest's asset must be tracked, OR be kept
    machine-local by .gitignore AND pinned by sha256 in its row.

    2026-10-13: channel/imagery/food_clips.json (tracked by design, clips under
    the gitignored channel/imagery/clips/) failed all 50 rows. Built in a
    scratch git repo: (a) ignored + sha256 passes; (b) ignored, no sha256
    fails; (c) untracked and NOT ignored fails - the materials.json defect is
    still caught. Hard-fails on zero cases.
    """
    from pathlib import Path  # noqa: PLC0415
    fails, cases = [], 0
    d = Path(tempfile.mkdtemp(prefix="v30-"))
    (d / "bin").mkdir()
    (d / "loop").mkdir()
    (d / "channel" / "imagery" / "clips").mkdir(parents=True)
    (d / "bin" / "lane.sh").write_text("python loop/lane.py\n")
    (d / "loop" / "lane.py").write_text("import json\n")
    (d / ".gitignore").write_text("channel/imagery/clips/\n")
    (d / "channel" / "imagery" / "tracked.jpg").write_text("x")

    def manifest(rows):
        (d / "channel" / "imagery" / "m.json").write_text(
            json.dumps({"index": rows}))
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)

    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    saved = validate.ROOT
    validate.ROOT = d
    try:
        sha = "a" * 64
        cases += 1
        manifest([{"local_file": "tracked.jpg"},
                  {"local_file": "clips/c.mp4", "sha256": sha}])
        r = validate.v30_cloud_visibility()
        if r.failures:
            fails.append(f"V30 (a): a gitignored-by-design clip pinned by "
                         f"sha256 must pass; got {r.failures}")
        cases += 1
        manifest([{"local_file": "clips/c.mp4"}])
        r = validate.v30_cloud_visibility()
        if not any("no 64-hex" in f for f in r.failures):
            fails.append("V30 (b): a gitignored clip with no sha256 must fail - "
                         "nothing pins the bytes")
        cases += 1
        manifest([{"local_file": "forgotten.jpg", "sha256": sha}])
        r = validate.v30_cloud_visibility()
        if not any("which is not" in f for f in r.failures):
            fails.append("V30 (c): an untracked asset that .gitignore does NOT "
                         "exclude must still fail, sha256 or not")
    finally:
        validate.ROOT = saved
        shutil.rmtree(d, ignore_errors=True)
    if cases == 0:
        fails.append("check_v30 examined zero cases")
    print(f"inspected {cases} V30 case(s)")
    return fails


if __name__ == "__main__":
    f = check() + check_registry() + check_v21() + check_v30()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every validator catches its own defect and fails on empty"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
