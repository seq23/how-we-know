"""The long-form title formula: gated, truth-guarded, proposed on $0, wired.

Owner decisions 12-13 Oct 2026 (repackage job 1). WHAT THIS PROVES, on real
scripts, with the model fixtured and every state path a scratch file:

  1. the formula: a plain traceable question passes; "how we know" fails; an
     invented figure fails; an unsupported word fails; a claim, a second
     clause or a missing "?" fails (one question per video, 2 Nov 2026);
  2. title_for_upload: titles.json first, the script's own title second, the
     episode's own question third; nothing passing -> None (held);
  3. the proposer: a first reply whose candidates all fail is fed back with
     the rejections, the second passes; run_propose writes slug, old title,
     new title, checks_passed and applied_at=null; an all-failing model
     records checks_passed false;
  4. the wiring: upload.build_payload refuses (TitleRefused) without a passing
     title; author.shape_problems rejects a draft whose ## YouTube title fails
     (so it is redrafted inside the retry loop); the cloud upload lane holds
     the slug before any byte is fetched (TITLE_REFUSED);
  5. V47: a self-check that cannot be loosened, plus a live upload row whose
     recorded title fails is a hard failure.

NEGATIVE PROOF (run once, 2026-10-13): delete the BRAND_PHRASE check in
title_problems -> case 1 "how we know" fails here and V47's self-check fails;
restore -> green. Hard-fails if it examines nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"

import longform_title as LT                                  # noqa: E402

fails: list[str] = []
examined = 0
TMP = Path(tempfile.mkdtemp(prefix="lf-title-"))
LT.STATE = TMP / "titles.json"


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUG = "how-hot-does-a-welding-arc-get"
SCRIPT = (ROOT / "scripts" / f"{SLUG}.md").read_text(encoding="utf-8")
Q = "how hot does a welding arc get"

# ---------------------------------------------------------------- 1. formula
# THE LOCK (owner, 13 Oct 2026): <=40 chars, sixth grade, one idea, the
# subject first, simple numbers. Her three titles are the reference set and
# must pass against their own scripts.
for ex_slug, ex_title in LT.EXEMPLARS.items():
    ex_text = (ROOT / "scripts" / f"{ex_slug}.md").read_text(encoding="utf-8")
    ex_pr = LT.title_problems(ex_title, ex_text, LT._question_for(ex_slug, ex_text))  # noqa: SLF001
    check(not ex_pr, f"the owner's locked exemplar {ex_title!r} fails the gate: {ex_pr}")
check(LT.EXEMPLARS == {
    "20-what-is-the-midnight-zone": "Why Is the Deep Sea So Dark?",
    "19-what-is-the-deepest-fish-ever-recorded": "How Deep Can a Fish Live?",
    "how-strong-is-titanium": "Is Titanium Stronger Than Steel?"},
    "the owner's three locked titles changed")
# ONE QUESTION PER VIDEO (owner, 2 Nov 2026) supersedes the 13 Oct series
# shape: a compilation ships its strongest single question.
_fs = (ROOT / "scripts" / "food" / "why-bread-rises-steak-browns-chocolate-snaps.md").read_text(encoding="utf-8")
check(any("one question" in x for x in LT.title_problems(
          "Bread, Steak, Chocolate: What's Inside?", _fs, LT.question_of(_fs))),
      "the retired series shape still passes")
_ft, _fw, _fsrc = LT.title_for_upload("why-bread-rises-steak-browns-chocolate-snaps", _fs,
                                      None, {"titles": {}})
check(_ft == "Why does bread rise?", f"a compilation does not ship its strongest single question: {_ft} {_fw}")
check(any("one question" in x for x in LT.title_problems(
          "Bread, Steak, Chocolate: Why It Works", _fs, LT.question_of(_fs))),
      "a colon title passed")
good = "Is a Welding Arc Hotter Than the Sun?"
check(not LT.title_problems(good, SCRIPT, Q),
      f"a plain, traceable question failed: {LT.title_problems(good, SCRIPT, Q)}")
# HARD: these still hold the upload - her one-question format and the truth
# guard (owner, 2 Nov 2026: no petty validation; the rest are notes).
cases = {
    "invented figure": ("Can a Welding Arc Reach 45,000 Degrees?", "never does"),
    "unsupported word": ("Is a Welding Arc Hotter Than Lava?", "unsupported"),
    "a claim, not a question": ("A welding arc is not simple", "one question"),
    "no question mark": ("How hot does a welding arc get", "one question"),
    "second clause": ("How hot is a welding arc — and how we know?", "one question"),
    "two ideas": ("Is a welding arc hot, or is it bright?", "one idea"),
}
for label, (t, needle) in cases.items():
    pr = LT.title_problems(t, SCRIPT, Q)
    check(any(needle in p for p in pr),
          f"formula: a title with {label} was not refused for it: {t!r} -> {pr}")
# NOTES: style rules are reported, never a hold, and never a hard problem.
notes = {
    "how we know": ("How we know a welding arc is hot", "how we know"),
    "too long": ("Is a Welding Arc Hotter Than the Sun Is Today?", "characters"),
    "hard number": ("Does a Welding Arc Hit 11,487 Degrees?", "simple and vivid"),
    "jargon": ("Is welding arc tensile heat simple?", "jargon"),
    "subject late": ("Do Sun Fires Burn Hotter Than Welding?", "first 4 words"),
}
for label, (t, needle) in notes.items():
    nt, pr = LT.title_notes(t, SCRIPT, Q), LT.title_problems(t, SCRIPT, Q)
    check(any(needle in n for n in nt), f"note: {label} not reported for {t!r}: {nt}")
    check(not any(needle in p for p in pr),
          f"style rule {label} still HOLDS the upload for {t!r}: {pr}")
check(not LT.title_problems("Is a Welding Arc Hotter Than the Sun Today?", SCRIPT, Q)
      or "characters" not in " ".join(LT.title_problems(
          "Is a Welding Arc Hotter Than the Sun Today?", SCRIPT, Q)),
      "a title over 40 characters is still refused for its length")

# ------------------------------------------------------- 2. title_for_upload
LT.STATE.write_text(json.dumps({"titles": {SLUG: {"new_title": good,
                                                  "checks_passed": True}}}))
t, why, src = LT.title_for_upload(SLUG, SCRIPT, Q)
check(t == good and src == "titles.json", f"titles.json did not win: {t} {src}")
LT.STATE.write_text(json.dumps({"titles": {SLUG: {
    "new_title": "Welding — and how we know", "checks_passed": True}}}))
own = LT.script_title(SCRIPT)
t, why, src = LT.title_for_upload(SLUG, SCRIPT, Q)
if own and not LT.title_problems(own, SCRIPT, Q):
    check(t == own and src == "script", f"the script's own title was not used: {t}")
else:
    # ONE QUESTION PER VIDEO (2 Nov 2026): the question itself is the fallback
    check(t == "How hot does a welding arc get?" and src == "question",
          f"no passing draft must fall back to the plain question: {t} {why}")
# ... and when not even the question passes, the upload is held (None)
t, why, src = LT.title_for_upload(SLUG, SCRIPT.replace("## YouTube title", "## Old"),
                                  "how hot does a welding arc get when the "
                                  "electrode is tungsten and the shielding gas is argon "
                                  "flowing at twelve litres a minute")
check(t is None or not LT.title_problems(t, SCRIPT, Q),
      f"a title that fails the gate was returned: {t}")
LT.STATE.unlink()

# ----------------------------------------------------------- 3. the proposer
calls: list[list[dict]] = []
replies = iter([
    "Welding arcs — and how we know\nHow hot does a welding arc get",
    "Is a Welding Arc Hotter Than the Sun?\nA welding arc reaches "
    "99,999 degrees"])


def fake_ask(messages):
    calls.append(messages)
    return next(replies), "fixture/free-model"


LT._ask = fake_ask                                            # noqa: SLF001
r = LT.propose(SLUG, SCRIPT, Q)
check(r["checks_passed"] and r["new_title"] == good and r["attempts"] == 2,
      f"the proposer did not retry to a passing title: {r}")
check(len(calls) == 2 and "rejected" in calls[1][-1]["content"]
      and "how we know" in calls[1][-1]["content"],
      "the rejections were not fed back to the model")
replies = iter([good])
LT._ask = lambda m: (next(replies), "fixture/free-model")    # noqa: SLF001
out = LT.run_propose([SLUG])
doc = json.loads(LT.STATE.read_text())
row = doc["titles"].get(SLUG) or {}
check(out["made"] == [SLUG] and row.get("new_title") == good
      and row.get("checks_passed") is True and row.get("applied_at") is None
      and row.get("old_title") and "proposed_at" in row,
      f"run_propose did not write the documented row: {row}")
LT._ask = lambda m: ("Welding — and how we know", "fixture")  # noqa: SLF001
r = LT.propose(SLUG, SCRIPT, Q)
check(r["checks_passed"] is False and r["problems"],
      f"an all-failing model was recorded as passing: {r}")

# -------------------------------------------------------------- 4. wiring
import upload as up                                           # noqa: E402
LT.STATE.write_text(json.dumps({"titles": {}}))
item = {"slug": SLUG, "script": f"scripts/{SLUG}.md", "question": Q}
_door = LT.title_for_upload
LT.title_for_upload = lambda *a, **k: (None, ["fixture: nothing passes"], "")
try:
    up.build_payload(item)
    check(False, "upload.build_payload shipped a long-form upload with no "
                 "passing title")
except up.TitleRefused as e:
    check(SLUG in str(e), "TitleRefused does not name the slug")
finally:
    LT.title_for_upload = _door
import author                                                 # noqa: E402
pov = {"line": "x" * 70}
bad_draft = SCRIPT
if "## YouTube title" in bad_draft:
    import re                                                 # noqa: E402
    bad_draft = re.sub(r"(## YouTube title\s*\n+).+", r"\1Welding — and how we know",
                       bad_draft, count=1)
else:
    bad_draft = bad_draft.replace("## Direct-answer lock",
                                  "## YouTube title\n\nWelding — and how we know"
                                  "\n\n## Direct-answer lock", 1)
check(any("YouTube title" in p and "how we know" in p
          for p in author.shape_problems(bad_draft, pov)),
      "author.shape_problems does not redraft a failing ## YouTube title")
good_draft = bad_draft.replace("Welding — and how we know", good)
check(not any(p.startswith("YouTube title") for p in author.shape_problems(good_draft, pov)),
      "author.shape_problems rejects a passing ## YouTube title")
src = (LOOP / "cloud_upload.py").read_text()
check("longform_title.title_for_upload" in src and '"TITLE_REFUSED"' in src
      and src.index("TITLE gate") < src.index("fetch(shelf, rk"),
      "the cloud upload lane does not hold an untitled slug before fetching it")

# --------------------------------------------------------------------- 5. V47
import validate as V                                          # noqa: E402
import ledger                                                 # noqa: E402
# THE REAL REPO MEANS THE REAL titles.json TOO. This check ran with LT.STATE
# still pointed at the fixture above, so the real proposals were never
# examined and a queued repair could not be seen.
_fixture_state, LT.STATE = LT.STATE, LOOP / "state" / "titles.json"
try:
    res = V.v47_longform_title([]).as_dict()
finally:
    LT.STATE = _fixture_state
check(not res["failures"], f"V47 self-check fails on the real repo: {res['failures']}")
saved = ledger.LEDGER

# -- 5a'. a live failing title is HELD only while a passing repair is queued
# (TITLE_RETITLE_PENDING, 2026-10-13); with no repair, or a repair that itself
# fails, or one already applied, it is a hard failure.
BADLIVE = "Can a Welding Arc Reach 45,000 Degrees?"   # an invented figure: hard
fake = TMP / "ledger_retitle.json"
fake.write_text(json.dumps({"published": [{
    "slug": SLUG, "question": Q, "video_id": "X", "uploaded_at": "2026-10-14T00:00:00+00:00",
    "title": BADLIVE}], "queued": []}))
ledger.LEDGER = fake
try:
    for label, row, want_held in [
            ("passing unapplied repair", {"new_title": good, "checks_passed": True,
                                          "applied_at": None}, True),
            ("no repair queued", None, False),
            ("repair that fails", {"new_title": "Is a Welding Arc Hotter Than Lava?",
                                   "checks_passed": True, "applied_at": None}, False),
            ("repair already applied", {"new_title": good, "checks_passed": True,
                                        "applied_at": "2026-10-14T01:00:00+00:00"}, False),
            ("repair not checks_passed", {"new_title": good, "checks_passed": False}, False)]:
        LT.STATE.write_text(json.dumps({"titles": {SLUG: row} if row else {}}))
        res = V.v47_longform_title([]).as_dict()
        live_fail = any("live title" in f for f in res["failures"])
        held = any(st.get("code") == "TITLE_RETITLE_PENDING" and SLUG in st.get("items", [])
                   for st in res.get("stops") or [])
        if want_held:
            check(held and not live_fail, f"V47 {label}: not held by name: {res}")
        else:
            check(live_fail and not held, f"V47 {label}: a failing live title passed: {res}")
finally:
    ledger.LEDGER = saved
    if LT.STATE.exists():
        LT.STATE.unlink()
fake = TMP / "ledger.json"
fake.write_text(json.dumps({"published": [{
    "slug": SLUG, "question": Q, "video_id": "X", "uploaded_at": "2026-10-14T00:00:00+00:00",
    "title": "Can a Welding Arc Reach 45,000 Degrees?"}], "queued": []}))
ledger.LEDGER = fake
try:
    res = V.v47_longform_title([]).as_dict()
    check(any("never does" in f for f in res["failures"]),
          f"V47 passed a live upload whose title fails the formula: {res}")
finally:
    ledger.LEDGER = saved

# ------------------------------------------- 5b. a leading figure survives
# 2026-10-13: "76 percent of ..." was parsed as list item 76 and proposed as
# "percent of deep-sea pelagic animals produce light" - and it passed.
check(LT._candidates("1. Seventy\n2) Eighty\n- Ninety\n76 percent of fish glow")  # noqa: SLF001
      == ["Seventy", "Eighty", "Ninety", "76 percent of fish glow"],
      f"_candidates mangles a leading figure: {LT._candidates('76 percent of fish glow')}")  # noqa: SLF001
check(any("begins with a capital" in p_ for p_ in
          LT.title_problems("percent of welding arcs reach 11,000 degrees", SCRIPT, Q)),
      "a title fragment starting mid-sentence passed the formula")

# ------------------------------------------- 5c. PLAINNESS (owner, 13 Oct)
# "6 crystals, a breathing fungus and a crust you never see" -> "those words
# make no sense". The subject, in plain words; no riddles, no lists; Flesch 60+.
FQ = "why bread rises, steak browns and chocolate snaps"
bad_food = LT.plainness_problems("6 crystals, a breathing fungus and a crust you never see", FQ)
check(any("subject" in x for x in bad_food) and any("more than one idea" in x for x in bad_food),
      f"the owner's riddle title passed the plainness rule: {bad_food}")
for good_, q_ in (("Why chocolate melts in your mouth but not in your hand", "why chocolate snaps"),
                  ("How Deep Can a Fish Live?", "what is the deepest fish ever recorded"),
                  ("Why hydrothermal vents never boil over", "what is hydrothermal vents")):
    check(not LT.plainness_problems(good_, q_),
          f"a plain title failed plainness: {good_!r} {LT.plainness_problems(good_, q_)}")
check(any("grade" in x or "jargon" in x for x in LT.plainness_problems(
          "Titanium's anisotropic microstructural deformation characteristics", "how strong is titanium")),
      "a jargon title passed the readability floor")
check(any("subject" in x for x in LT.title_notes(
          "Window glass that is ninety-nine percent air", SCRIPT, Q)),
      "title_notes does not report the plainness rule")

# ------------------------------------------- 6. --needed: live videos too
# Job 2 (13 Oct 2026): every live long-form video gets a passing title, and
# the daily lane must keep proposing for any live video that has none - else
# `repackage apply` (titles.json only) leaves its old title up for good.
fake.write_text(json.dumps({"published": [
    {"slug": SLUG, "question": Q, "video_id": "LIVE1",
     "uploaded_at": "2026-10-26T00:00:00+00:00"},
    {"slug": SLUG, "question": Q, "video_id": "DUP0",
     "uploaded_at": "2026-10-26T00:00:00+00:00",
     "retired_at": "2026-09-02T00:00:00+00:00"}], "queued": []}))
ledger.LEDGER = fake
try:
    LT.STATE.write_text(json.dumps({"titles": {}}))
    check(LT.published_needing() == [SLUG],
          f"a live video with no titles.json row is not needed: {LT.published_needing()}")
    LT.STATE.write_text(json.dumps({"titles": {SLUG: {
        "new_title": "Welding — and how we know", "checks_passed": True}}}))
    check(LT.published_needing() == [SLUG],
          "a live video whose recorded title no longer passes is not needed")
    LT.STATE.write_text(json.dumps({"titles": {SLUG: {
        "new_title": good, "checks_passed": True}}}))
    check(LT.published_needing() == [],
          f"a live video with a passing row is re-proposed: {LT.published_needing()}")
    check(SLUG not in LT.needed_slugs(), "needed_slugs re-proposes a titled live video")
    # OLDER VIDEOS UNTOUCHED (owner, 2 Nov 2026): uploaded before
    # titles.QUESTION_START, a failing row is never re-proposed.
    fake.write_text(json.dumps({"published": [
        {"slug": SLUG, "question": Q, "video_id": "OLD1",
         "uploaded_at": "2026-10-20T00:00:00+00:00"}], "queued": []}))
    LT.STATE.write_text(json.dumps({"titles": {SLUG: {
        "new_title": "Welding — and how we know", "checks_passed": True}}}))
    check(LT.published_needing() == [],
          f"a pre-rule live video is re-proposed: {LT.published_needing()}")
finally:
    ledger.LEDGER = saved
wf = (ROOT / ".github" / "workflows" / "loop-repackage.yml").read_text()
check('ARGS="--needed' in wf and "longform_title.py propose $ARGS" in wf,
      "the daily repackage lane does not propose with --needed: live videos "
      "with no passing title would never get one")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
