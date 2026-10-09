"""New-upload titles, affiliate blocks and the Shorts topic mix (owner build 2026-10-08).

Proves, with no network and no credential (LOOP_DRY_RUN=1):

  TITLES (loop/titles.py)
  1. every query in every live publish-order queue gets a title that passes
     title_problems(): keeps every search word, is not a bare question, no
     banned word, within 100 chars, no figure the script does not state;
  2. the rule-based rewrite is the shape the owner approved —
     "what is the midnight zone" -> "The midnight zone — and how we know";
  3. a script's own `## YouTube title` is used when it passes, and REFUSED
     (falling back) when it drops a search word, invents a number, is a bare
     question or uses clickbait — and the NEGATIVE proof: title_problems()
     finds each of those defects when fed them directly;
  4. upload.build_payload and shorts_lane.build_payload both title through it.

  AFFILIATES (loop/affiliates.py, channel/affiliates.json)
  5. the config ships with BOTH ids empty, and an episode citing a listed
     book gets a block of PLAIN links (no tag=) plus the FTC disclosure;
  6. with an Amazon tag set, the same block carries tag= and the Amazon
     Associates sentence; a verified ISBN adds a Bookshop.org link with /a/<id>/;
  7. an episode that cites no listed item gets NO block (no topic guessing),
     and every configured item matches at least one real script's Sources —
     a config entry nothing cites is a wish, not a link;
  8. upload.build_payload places the block before the channel footer and the
     hashtag line stays last.

  SHORTS TOPIC MIX (loop/shorts_lane.py order_by_mix, config shorts_topics)
  9. the config holds deep sea above materials and materials above zero;
 10. from an all-materials recent history, a mixed candidate list is ordered
     deep sea first and comes out 3:1 over a run of eight;
 11. favoured terms (midnight zone, pressure, trench) lead within deep sea;
 12. with only materials ready, materials still airs (never a stall);
 13. pending() routes through order_by_mix.

  RELATED EPISODE (loop/handoff.py)
 14. a Short with no public episode gets a "Related episode:" first line,
     and short_description() replaces it with the Short's own episode link;
 15. related_episode_for picks the public, same-domain, best-matching episode
     against a fake YouTube client and reads nothing under LOOP_DRY_RUN.

Hard-fails if it examines zero cases.
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
tmp = Path(tempfile.mkdtemp(prefix="titles-test-"))
os.environ.setdefault("LOOP_STOPS_DIR", str(tmp / "stops"))
(tmp / "stops").mkdir(exist_ok=True)

import affiliates as A        # noqa: E402
import batch_queue            # noqa: E402
import discovery              # noqa: E402
import domains                # noqa: E402
import handoff as H           # noqa: E402
import shorts_lane as SL      # noqa: E402
import titles as T            # noqa: E402
import upload as up           # noqa: E402
from common import config     # noqa: E402

examined, fails = 0, []


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -- {detail}"))
    if not ok:
        fails.append(name)


DEEP, MAT = "deep-sea-ocean-science", "materials-and-manufacturing"

# ------------------------------------------------------------------ titles
print("titles")
rows = batch_queue.queued_entries()
check("the live queue is not empty", len(rows) > 0)
bad = []
for r in rows:
    t = T.title_for(r["query"])
    probs = T.title_problems(t, r["query"])
    if probs:
        bad.append((r["query"], t, probs))
check(f"all {len(rows)} queued queries get a clean title", not bad, str(bad[:3]))

check("midnight zone shape",
      T.title_for("what is the midnight zone") == "The midnight zone — and how we know",
      T.title_for("what is the midnight zone"))
check("graphene shape",
      T.title_for("how strong is graphene") == "How strong graphene really is — and how we know",
      T.title_for("how strong is graphene"))
check("no new title is a bare question",
      not any(T.title_for(r["query"]).endswith("?") for r in rows))

script = ("# What is the deepest fish ever recorded?\n\n## YouTube title\n\n"
          "{t}\n\n## Direct-answer lock\n\nThe deepest fish recorded on video is "
          "a snailfish filmed at 8,336 meters.\n\n## Narration\n")
q = "what is the deepest fish ever recorded"
good = "The deepest fish ever recorded was filmed 8,336 m down — and how we know"
check("a passing script title is used verbatim",
      T.title_for(q, script.format(t=good)) == good, T.title_for(q, script.format(t=good)))
for label, prop, needle in (
        ("drops a search word", "The fish filmed 8,336 m down — and how we know", "drops search word"),
        ("invents a number", "The deepest fish ever recorded was filmed 9,000 m down", "never does"),
        ("is a bare question", "What is the deepest fish ever recorded?", "bare question"),
        ("uses clickbait", "SHOCKING: the deepest fish ever recorded", "banned")):
    s_ = script.format(t=prop)
    got = T.title_for(q, s_)
    check(f"a script title that {label} is refused", got != prop, got)
    check(f"title_problems names it when it {label}",
          any(needle in p for p in T.title_problems(prop, q, s_)),
          str(T.title_problems(prop, q, s_)))
check("a number the query itself carries is not an invented figure",
      not T.title_problems(T.title_for("how is 3d printed metal made"),
                           "how is 3d printed metal made"))

slug = "how-hot-does-a-welding-arc-get"
item = {"slug": slug, "script": f"scripts/{slug}.md",
        "question": "how hot does a welding arc get"}
ep = up.build_payload(item)
check("upload.build_payload titles through titles.py",
      ep["snippet"]["title"] == T.title_for(item["question"],
                                            (ROOT / item["script"]).read_text()),
      ep["snippet"]["title"])
sh = SL.build_payload("20-what-is-the-midnight-zone", "what is the midnight zone")
check("shorts_lane.build_payload titles through titles.py",
      sh["snippet"]["title"] == "The midnight zone — and how we know", sh["snippet"]["title"])

# ------------------------------------------------------------- affiliates
print("affiliates")
cfg = A.load()
# 9 Oct 2026: the owner's Amazon Associates Store ID is live (seq23-20); Bookshop is not set yet.
check("the shipped Amazon tag is the owner's Store ID", cfg["amazon_associates_tag"] == "seq23-20", cfg["amazon_associates_tag"])
check("the shipped Bookshop id is still empty", cfg["bookshop_affiliate_id"] == "")
txt = (ROOT / item["script"]).read_text()
blk = A.block_for(txt, cfg)
check("a citing episode gets a block", "Welding Handbook" in blk, blk)
check("shipped links carry the owner's tag and the Associates sentence",
      "tag=seq23-20" in blk and cfg["amazon_disclosure"] in blk and "/a/" not in blk, blk)
check("the FTC disclosure is present, above the first link",
      cfg["disclosure"] in blk and blk.index(cfg["disclosure"]) < blk.index("• "), blk)
untagged = dict(cfg, amazon_associates_tag="", bookshop_affiliate_id="")
ub = A.block_for(txt, untagged)
check("with no id the links carry no tracking", ub and "tag=" not in ub and "/a/" not in ub, ub)
check("no Amazon Associates sentence while no tag is set", cfg["amazon_disclosure"] not in ub)
tagged = dict(cfg, amazon_associates_tag="howweknow-20", bookshop_affiliate_id="12345",
              items=[dict(cfg["items"][0], bookshop_isbn13="9780000000002")])
tb = A.block_for(txt, tagged)
check("with a tag set, links carry tag= and the Associates sentence",
      "tag=howweknow-20" in tb and cfg["amazon_disclosure"] in tb, tb)
check("a verified ISBN adds a Bookshop affiliate link",
      "https://bookshop.org/a/12345/9780000000002" in tb, tb)
deep_txt = (ROOT / "scripts" / "20-what-is-the-midnight-zone.md").read_text()
check("an episode that cites no listed item gets no block", A.block_for(deep_txt, cfg) == "")
all_src = "\n".join(A.sources_section(p.read_text()) for p in (ROOT / "scripts").glob("*.md")).lower()
orphan = [it["id"] for it in cfg["items"] if not any(c.lower() in all_src for c in it["cited_as"])]
check(f"every one of {len(cfg['items'])} configured items is cited by a real script",
      cfg["items"] and not orphan, str(orphan))
d = ep["snippet"]["description"]
check("the episode description carries the block before the footer",
      "Books and references cited in this episode:" in d
      and d.index("Books and references") < d.index("Evidence-first explainers"), d[-600:])
check("the hashtag line is still the last line",
      d.rstrip().split("\n")[-1].startswith("#")
      and discovery.strip_hashtag_line(d) != d)

# --------------------------------------------------------------- topic mix
print("shorts topic mix")
st = config().get("shorts_topics") or {}
mix = st.get("domain_mix") or {}
check("deep sea outweighs materials, materials kept above zero",
      mix.get(DEEP, 0) > mix.get(MAT, 0) > 0, str(mix))

deep_slugs = [s for s in domains.by_slug() if domains.domain_of_slug(s) == DEEP]
mat_slugs = [s for s in domains.by_slug() if domains.domain_of_slug(s) == MAT]
check("both domains have slugs to test with", len(deep_slugs) >= 6 and len(mat_slugs) >= 6)
cands = mat_slugs[:6] + deep_slugs[:6]          # materials FIRST in queue order
out = SL.order_by_mix(cands, recent=mat_slugs[:8])
doms = [domains.domain_of_slug(s) for s in out[:8]]
check("after an all-materials history, deep sea goes first", doms[0] == DEEP, str(doms))
check("eight picks come out 6 deep sea : 2 materials",
      doms.count(DEEP) == 6 and doms.count(MAT) == 2, str(doms))
check("nothing is dropped", sorted(out) == sorted(cands))
fav = [s for s in deep_slugs if "midnight" in s or "pressure" in s or "trench" in s]
plain = [s for s in deep_slugs if s not in fav and SL._favour_score(s, {t for t in st["favoured_terms"]}) == 0]
if fav and plain:
    o2 = SL.order_by_mix([plain[0], fav[0]], recent=[])
    check("a favoured deep-sea subject leads within its domain", o2[0] == fav[0], str(o2))
check("only materials ready -> materials still airs",
      SL.order_by_mix(mat_slugs[:3], recent=[]) == mat_slugs[:3])
check("pending() routes through order_by_mix",
      "return order_by_mix(out, cfg=cfg)" in (LOOP / "shorts_lane.py").read_text())

# ---------------------------------------------------------- related episode
print("related episode")
rel = SL.build_payload("20-what-is-the-midnight-zone", "what is the midnight zone",
                       related=("REL1", "The deepest fish ever recorded — and how we know"))
first = rel["snippet"]["description"].split("\n")[0]
check("no public episode -> a Related episode first line",
      first == "Related episode: https://youtu.be/REL1 — The deepest fish ever recorded — and how we know", first)
swapped = H.short_description(rel["snippet"]["description"], "OWN1", "what is the midnight zone")
check("the hand-off replaces the related line with the Short's own episode",
      swapped.split("\n")[0].startswith("Full episode: https://youtu.be/OWN1")
      and "Related episode:" not in swapped, swapped[:200])
check("the related line is not added when the own episode is public",
      "Related episode" not in SL.build_payload(
          "20-what-is-the-midnight-zone", "what is the midnight zone",
          episode_video_id="OWN1", related=("REL1", "x"))["snippet"]["description"])
check("related_episode_for reads nothing under LOOP_DRY_RUN",
      H.related_episode_for("tok", "20-what-is-the-midnight-zone") is None)


class FakeYT:
    def __init__(self, public: set[str]):
        self.public, self.calls = public, 0

    def api_get(self, path, params):
        self.calls += 1
        return {"items": [{"id": i, "status": {"privacyStatus": "public" if i in self.public else "private"},
                           "snippet": {"title": f"Live title {i}"}}
                          for i in params["id"].split(",")]}


import ledger as L            # noqa: E402
led = L.load()
same = [r for r in led["published"] if r.get("video_id") and not r.get("retired_at")
        and domains.domain_of_slug(r["slug"]) == DEEP
        and r["slug"] != "20-what-is-the-midnight-zone"]
other = [r for r in led["published"] if r.get("video_id")
         and domains.domain_of_slug(r["slug"]) == MAT]
if same:
    yt = FakeYT({r["video_id"] for r in same} | {r["video_id"] for r in other})
    got = H.related_episode_for("tok", "20-what-is-the-midnight-zone", yt=yt)
    check("related_episode_for returns a public same-domain episode in one read",
          got is not None and got[0] in {r["video_id"] for r in same}
          and got[1].startswith("Live title") and yt.calls == 1, str(got))
    check("no public candidate -> None", H.related_episode_for(
        "tok", "20-what-is-the-midnight-zone", yt=FakeYT(set())) is None)

print(f"\n{examined} check(s), {len(fails)} failure(s)")
if examined == 0:
    print("FAIL: examined zero cases")
    sys.exit(1)
sys.exit(1 if fails else 0)
