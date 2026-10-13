"""The long-form description template: a search block people actually type.

Owner instruction, 13 Oct 2026. No network and no model here: autocomplete
and the $0 route are fixtured; every state path is a scratch file.

  1. search_questions keeps only question-shaped autocomplete strings that
     name the subject, never "how we know", title and question first, 4-8;
  2. compose: the title is the first line with the one-sentence answer, the
     chapters keep the render's timestamps and take their question names,
     the "Questions this video answers" block, the sources line, tags within
     500 characters carrying the phrasings and the subject; no block -> None;
  3. upload.build_payload ships the composed description when the block is
     prepared (the one template for upload and repackage apply);
  4. problems(): a composed description passes; fewer than four phrasings,
     no subject, or chapter times that are not the render's each fail;
  5. V60 passes on the real repo and fails on a block with three phrasings.

NEGATIVE PROOF (run once, 2026-10-13): MIN_QUESTIONS lowered to 1 in
problems() -> cases 4 and 5 fail; restored -> green.
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

import describe as D                                          # noqa: E402

fails: list[str] = []
examined = 0
TMP = Path(tempfile.mkdtemp(prefix="describe-"))


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUG = "how-strong-is-titanium"
SCRIPT = (ROOT / "scripts" / f"{SLUG}.md").read_text(encoding="utf-8")
Q = "how strong is titanium"
TITLE = "Is Titanium Stronger Than Steel?"

# ---------------------------------------------------------- 1. phrasings
FAKE = {
    "how strong is titanium": ["how strong is titanium", "how strong is titanium compared to steel",
                               "titanium strength chart", "how we know titanium is strong"],
    "why titanium": ["why titanium is used in planes", "why is titanium so expensive"],
    "is titanium": ["is titanium stronger than steel", "is titanium magnetic",
                    "is gold heavier than lead"],
}
got = D.search_questions(Q, TITLE, suggest=lambda s: FAKE.get(s, []), pause=0)
check(got[0] == TITLE and got[1] == "How strong is titanium?",
      f"the title and the question do not lead the phrasings: {got}")
check(all(g.endswith("?") for g in got) and 4 <= len(got) <= D.MAX_QUESTIONS,
      f"phrasings are not 4-8 questions: {got}")
check(not any("chart" in g or "how we know" in g.lower() or "gold" in g for g in got),
      f"a non-question, brand or off-subject string got in: {got}")
check(len(D.search_questions(Q, TITLE, suggest=lambda s: ["x"] * 3, pause=0)) == 2,
      "with no real phrasings the list was padded")

# ------------------------------------------------------------ 2. compose
STATE = TMP / "descriptions.json"
D.STATE = STATE
CH = ["0:00 Cold open", "0:41 What strength means", "3:10 Titanium against steel"]
D.save({"episodes": {SLUG: {"questions": got, "subject": "titanium", "title": TITLE,
                            "chapter_names": {"What strength means": "What does strong mean?"}}}})
desc, tags = D.compose(SLUG, SCRIPT, TITLE, Q, CH, ["NIST - https://www.nist.gov/"],
                       extra=["Books: none"])
check(desc.splitlines()[0].startswith(TITLE + " ") and len(desc.splitlines()[0]) > len(TITLE) + 5,
      f"the first line is not the title plus one sentence of answer: {desc.splitlines()[0]!r}")
check("0:41 What does strong mean?" in desc and "3:10 Titanium against steel" in desc
      and "0:00 Cold open" in desc, "chapters lost their times or their question names")
check("Questions this video answers:" in desc and all(f"• {g}" in desc for g in got),
      "the phrasings block is missing")
check(D.SOURCES_LINE in desc and "Books: none" in desc and D.CHANNEL_LINE in desc,
      "the sources line, the extra block or the channel line is missing")
size = sum(len(t) + (2 if " " in t else 0) for t in tags) + len(tags) - 1
check("titanium" in tags and got[1].rstrip("?").lower() in tags and size <= D.TAGS_MAX,
      f"tags do not carry the phrasings and the subject within 500: {tags} ({size})")
check(D.compose("no-such-slug", SCRIPT, TITLE, Q, CH, []) is None,
      "a slug with no prepared block was composed")

# ----------------------------------------------------- 3. the upload door
import longform_title as LT                                   # noqa: E402
import upload                                                 # noqa: E402
LT.STATE = TMP / "titles.json"
LT.STATE.write_text(json.dumps({"titles": {SLUG: {"new_title": TITLE, "checks_passed": True}}}))
snip = upload.build_payload({"slug": SLUG, "question": Q,
                             "script": f"scripts/{SLUG}.md"})["snippet"]
check(snip["description"].startswith(TITLE) and "Questions this video answers:" in snip["description"]
      and "titanium" in snip["tags"],
      "upload.build_payload does not ship the composed search block")

# ------------------------------------------------------------ 4. problems
ref = upload.build_chapters(SLUG, SCRIPT)
check(not D.problems(snip["description"], TITLE, Q, ref),
      f"a composed description fails its own check: {D.problems(snip['description'], TITLE, Q, ref)}")
thin = snip["description"].replace("• " + got[2], "").replace("• " + got[3], "")
check(any("phrasing" in p for p in D.problems(thin, TITLE, Q, ref)),
      "a description with too few phrasings passed")
check(any("subject" in p for p in D.problems("T?\n0:00 a", "T?", Q)),
      "a description that never names the subject passed")
if ref:
    shifted = [("0:00 " if i == 0 else "9:59 ") + c.split(" ", 1)[1] for i, c in enumerate(ref)]
    if len(ref) > 1:
        check(any("do not match" in p for p in D.problems(snip["description"], TITLE, Q, shifted)),
              "chapter times that are not the render's passed")

# ------------------------------------------------------------------ 5. V60
import validate as V                                          # noqa: E402
D.STATE = LOOP / "state" / "descriptions.json"
LT.STATE = LOOP / "state" / "titles.json"
res = V.v60_description_search_block().as_dict()
check(not res["failures"], f"V60 fails on the real repo: {res['failures'][:3]}")
D.STATE = STATE
LT.STATE = TMP / "titles.json"
D.save({"episodes": {SLUG: {"questions": got[:4], "subject": "titanium", "title": TITLE}}})
saved_min = D.MIN_QUESTIONS
d0 = D.load()
d0["episodes"][SLUG]["questions"] = got[:4]
D.save(d0)
orig_compose = D.compose


def thin_compose(*a, **k):
    out = orig_compose(*a, **k)
    if out is None:
        return None
    desc_, tags_ = out
    return desc_.replace("• " + got[3] + "\n", ""), tags_


D.compose = thin_compose
try:
    res = V.v60_description_search_block().as_dict()
finally:
    D.compose = orig_compose
check(any("phrasing" in f for f in res["failures"]),
      f"V60 passed a description with three phrasings: {res['failures'][:2]}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
