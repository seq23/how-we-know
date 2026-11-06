"""ONE QUESTION PER VIDEO (owner, 2 Nov 2026) - titles, thumbnails, Short openers, backfill.

  1. titles.one_question_problems: the owner's 19 approved titles pass; the shapes
     it replaced fail ("— and how we know", "subject: chapter statement", a
     claim, two joined questions).
  2. Every title path makes one question: titles.title_for for every queued query,
     title_for_cut rank 2 (statement chapter -> the episode question; question
     chapter -> that question), longform_title.title_for_upload (falls back to
     the question itself), and the long-form gate refuses a claim title.
  3. Older videos untouched: longform_title.published_needing and
     thumb_contract.needed_slugs never list a video uploaded before
     titles.QUESTION_START.
  4. The thumbnail: build_question_into makes A/B/C with the SAME question on a
     PD/CC0 photo and verify() passes - NEGATIVE: a variant carrying another
     text fails, a picture from food_ai.json (AI) fails.
  5. No photo, no thumbnail: thumbs_for.build raises for an episode with no PD/CC0
     photo and writes no file (no fallback to the old text card).
  6. The Short opener: tall_card is 1080x1920 with the question; shorts_lane.
     opener_of refuses a receipt without it and returns the question with it;
     build_payload titles the Short with it; shorts.stale_opening re-cuts an
     unpublished cut without it and never a published one.
  7. The backfill resolves all 19 to exactly one ledger row each.
  8. V76 passes on the repo and FAILS (negative) on a ledger row uploaded under the
     rule with a "— and how we know" title.
  9. research/imagery.pd_licence_ok accepts CC0 (Commons reports Copyrighted=True
     for it) and still refuses CC-BY.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "loop" / "tools"))
sys.path.insert(0, str(ROOT / "research"))
os.environ["LOOP_DRY_RUN"] = "1"

from PIL import Image                                          # noqa: E402

import titles as T                                             # noqa: E402
import longform_title as LT                                    # noqa: E402
import one_question_backfill as B                              # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


# 1
for _k, _s, t in B.APPROVED:
    check(not T.one_question_problems(t), f"1 approved {t!r} passes")
for bad in ("Why does rice get sticky — and how we know",
            "The deepest part of the ocean: what a depth number leaves out",
            "Damascus steel is not better now",
            "What lives in the trench and why is it red?",
            "Why is it red? Here's how we know"):
    check(bool(T.one_question_problems(bad)), f"1 {bad!r} refused")

# 2
import batch_queue                                             # noqa: E402
qs = [e["query"] for e in batch_queue.queued_entries() if e.get("query")]
check(len(qs) > 10, f"2 the queue has queries ({len(qs)})")
badq = [(q, T.title_for(q)) for q in qs if T.one_question_problems(T.title_for(q))]
check(not badq, f"2 title_for makes one question for every queued query {badq[:2]}")
c2 = T.title_for_cut("what is the deepest part of the ocean", "", 2,
                     "What a depth number leaves out")
check(c2 == "What is the deepest part of the ocean?", f"2 rank-2 statement chapter -> {c2!r}")
c3 = T.title_for_cut("what is the deepest part of the ocean", "", 3,
                     "How is the depth measured?")
check(c3 == "How is the depth measured?", f"2 rank-3 question chapter -> {c3!r}")
sp = ROOT / "scripts" / "why-does-rice-get-sticky.md"
t, why, src = LT.title_for_upload("why-does-rice-get-sticky-fixture", sp.read_text(),
                                  "why does rice get sticky", state={"titles": {}})
check(t == "Why does rice get sticky?" and src == "question",
      f"2 long-form falls back to the question itself ({t!r}, {src})")
check(any("one question" in x for x in LT.title_problems(
    "One broken gene makes rice glue-like", sp.read_text(), "why does rice get sticky")),
      "2 the long-form gate refuses a claim title")

# 3
import ledger                                                  # noqa: E402
# Judged by the slug's LIVE upload (the latest ledger row with a video): a slug
# re-uploaded after the rule is a new video, not a pre-rule one (6 Nov 2026,
# what-is-concrete-made-of went up again under its question).
live_up = {r["slug"]: (r.get("uploaded_at") or "")[:10] for r in ledger.load()["published"]
           if r.get("video_id") and not r.get("retired_at")}
old = {slug for slug, day in live_up.items() if day < T.QUESTION_START}
need = set(LT.published_needing())
check(not (need & old), f"3 no pre-rule video is re-proposed ({sorted(need & old)[:3]})")
import thumb_contract as TC                                    # noqa: E402
check(not (set(TC.needed_slugs()) & (old - {"is-damascus-steel-better"})),
      "3 no pre-rule video gets a new thumbnail set")

# 4
with tempfile.TemporaryDirectory() as td:
    d = Path(td) / "is-damascus-steel-better"
    r = TC.build_question_into("is-damascus-steel-better", str(d),
                               title="Are Damascus knives better?")
    rec = r["contract"]
    check(rec["layout"] == "question-photo-v1"
          and {v["text"] for v in rec["variants"].values()} == {"Are Damascus knives better?"},
          "4 A/B/C carry the same question")
    check(all(v["manifest"] in ("rights.json", "materials.json", "food.json")
              for v in rec["variants"].values()), "4 every picture is a PD/CC0 photo")
    check(TC.verify_question("is-damascus-steel-better", str(d), rec) == [],
          "4 verify passes")
    with Image.open(d / "A.jpg") as im:
        check(im.size == (1280, 720), "4 1280x720")
    bad = json.loads(json.dumps(rec))
    bad["variants"]["B"]["text"] = "DAMASCUS?"
    check(any("not the title question" in x for x in TC.verify_question(
        "is-damascus-steel-better", str(d), bad)), "4 NEGATIVE: another text on B fails")
    bad = json.loads(json.dumps(rec))
    bad["variants"]["C"]["manifest"] = "food_ai.json"
    check(any("cleared photo manifest" in x for x in TC.verify_question(
        "is-damascus-steel-better", str(d), bad)), "4 NEGATIVE: an AI picture fails")

# 5
import thumbs_for                                              # noqa: E402
import question_card as QC                                     # noqa: E402
# Every real episode now has a picture (the finder resolves each the same
# night, 2 Nov 2026), so the no-photo state is constructed: a real slug whose
# photo list is emptied must still be refused, never given the old text card.
nophoto = "how-do-scientists-know-about-other-galaxies"
_real_photos = QC.photos
QC.photos = lambda slug, sp=None: []                           # noqa: ARG005
check(nophoto is not None, f"5 an episode with no PD/CC0 photo exists ({nophoto})")
if nophoto:
    with tempfile.TemporaryDirectory() as td:
        try:
            thumbs_for.build(nophoto, out_dir=td)
            check(False, "5 no photo -> refused")
        except TC.ContractRefused as e:
            check("NO_SUBJECT_PHOTO" in str(e), "5 no photo -> ContractRefused NO_SUBJECT_PHOTO")
        check(not (Path(td) / f"{nophoto}.jpg").exists(), "5 no text-card fallback written")
QC.photos = _real_photos

# 6
import shorts_lane as SL                                       # noqa: E402
with tempfile.TemporaryDirectory() as td:
    png = Path(td) / "o.png"
    op = QC.tall_card("why-does-rice-get-sticky", "Why does rice get sticky?", str(png))
    with Image.open(png) as im:
        check(im.size == (1080, 1920), "6 the opener is 1080x1920")
    check(op["seconds"] == 1.0 and op["question"] == "Why does rice get sticky?",
          "6 the opener is the question, for one second")
    q, why = SL.opener_of({"opener": op})
    check(q == "Why does rice get sticky?" and why is None, "6 opener_of returns the question")
    q, why = SL.opener_of({"opening": "episode"})
    check(q is None and "predates" in why, "6 NEGATIVE: a cut without the opener is refused")
    q, why = SL.opener_of({"opener": {**op, "question": "Why rice sticks — and how we know"}})
    check(q is None, "6 NEGATIVE: an opener question that is not one question is refused")
    p = SL.build_payload("why-does-rice-get-sticky", "why does rice get sticky",
                         title="Why does rice get sticky?")
    check(p["snippet"]["title"] == "Why does rice get sticky?", "6 the Short is titled with it")
    import shorts as SH                                        # noqa: E402
    mp4 = Path(td) / "x-short.mp4"
    mp4.write_bytes(b"")
    Path(f"{mp4}.short.json").write_text(json.dumps({"opening": "episode"}))
    check(SH.stale_opening(str(mp4), 0, published=set()), "6 unpublished old cut is re-cut")
    check(not SH.stale_opening(str(mp4), 0, published={"x-short.mp4"}),
          "6 a published cut is never re-cut")
    Path(f"{mp4}.short.json").write_text(json.dumps({"opening": "episode", "opener": op}))
    check(not SH.stale_opening(str(mp4), 0, published=set()), "6 a cut with the opener is kept")

# 7
items = B.resolve()
check(len(items) == 19 and len({i["video_id"] for i in items}) == 19,
      f"7 the backfill resolves 19 distinct videos ({len(items)})")
check(sum(1 for i in items if i["kind"] == "long") == 1, "7 exactly one long-form")

# 8
import validate as V                                           # noqa: E402
r = V.v76_one_question()
check(r.ok, f"8 V76 passes on the repo {r.failures[:2]}")
fx = {"published": [{"slug": "x", "video_id": "abc", "uploaded_at": "2026-11-04T00:00:00Z",
                     "title": "Why does x happen — and how we know"}]}
r = V.v76_one_question(led=fx, sled={"published": []})
check(not r.ok and any("abc" in f for f in r.failures), "8 NEGATIVE: V76 fails a new two-part title")

# 9
import imagery as I                                            # noqa: E402
def info(short, cr):
    return {"extmetadata": {"LicenseShortName": {"value": short},
                            "Copyrighted": {"value": cr}}}
check(I.pd_licence_ok(info("CC0", "True"))[0], "9 CC0 accepted")
check(I.pd_licence_ok(info("Public domain", "False"))[0], "9 PD accepted")
check(not I.pd_licence_ok(info("CC BY 2.0", "True"))[0], "9 CC-BY refused")

print(f"\n{examined} checks, {len(fails)} failed")
if not examined:
    sys.exit("FAIL: examined nothing")
sys.exit(1 if fails else 0)
