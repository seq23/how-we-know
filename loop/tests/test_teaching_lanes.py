"""The teaching lanes (Neville Goddard, Florence Scovel Shinn) and the four-lane mix.

Her rulings 9 Nov 2026: guided whispered sessions BUILT ON a teacher's
techniques, never a straight reading; quote only titles whose US copyright is
recorded as gone; every script differs in structure; practice, never promise;
four lanes steered by the channel's own numbers, never a calendar.

  a. a well-formed teaching script passes every rule (so the rules can pass);
  b. a quote from a title not cleared (in copyright, unchecked, a lecture)
     is refused, and so is a quote naming no book;
  c. a quote that is not word for word a verified line of its title is refused;
  d. a script that reads the book straight through (book sentences outside a
     marked quote) is refused, and so is a quotes part with too many quotes;
  e. the same shape + scene as a recent teaching script, or parts out of
     their shape, is refused;
  f. a promise in the guided part is refused;
  g. the kit: credit, no-endorsement line and quoted books in the description;
     Money carries the one products line; "no ads" in a title is refused;
  h. the mix (her decision 9 Nov 2026): Neville 2, Money 1, food history 1,
     ocean documentary 1, rotating 0 before monetisation; ocean, food and money after; the lane
     with the most watch hours per video takes a slot from the weakest only
     with 2+ measured videos in each; unread numbers move nothing; the queue
     voices the lane furthest behind first;
  i. the rights record: every recorded quote's title is quotable and dated,
     and the book record the straight-reading check reads is not empty.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"

import teachings as T  # noqa: E402
import whisper_lane as WL  # noqa: E402

fails: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


c = WL.cfg()
R = T.rights()
WORDS = ["soft", "slow", "warm", "quiet", "calm", "still", "easy", "gentle"]
PLACES = ["your room", "the hall", "the kitchen", "the window", "your bed", "the door", "the lamp", "the chair"]


def guide(n: int, seed: int) -> list[str]:
    out = []
    for i in range(n):
        w, p = WORDS[(i + seed) % 8], PLACES[(i * 3 + seed) % 8]
        out.append(f"Let your breath grow {w} as you rest near {p} number {i + seed} in your mind. "
                   f"You are already there, and it feels {WORDS[(i + 2) % 8]} and right. "
                   f"Notice the {w} light, the {WORDS[(i + 5) % 8]} air, and how settled you feel "
                   f"{'again ' * (i % 3)}tonight. Nothing needs to happen next {'for now ' * (i % 4)}at all.")
    return [x.replace(f"number {i}", "") for i, x in enumerate(out)]


EXPLAIN = ["Neville taught that the words you say to yourself shape how you see your life.",
           "Tonight you practise a small, kind version of that idea, slowly, in bed. You choose one "
           "short sentence you would hear if the wish were already true. You hear it softly, again and again."]
QUOTES = ["In Awakened Imagination, Neville wrote: “What you desire to hear without, you must hear within.”",
          "Neville put it this way, in Seedtime and Harvest: “What would you think and say and do were "
          "you already the one you want to be? Begin to think and say and do this inwardly.”"]


def build(d: Path, name: str, parts=None, meta=None, kind="neville") -> Path:
    meta = {"Technique": "inner-conversation", "Shape": "d",
            "Scene": c["teachings"]["scenes"][0], **(meta or {})}
    parts = parts or [("explain", EXPLAIN), ("quotes", QUOTES), ("guide-1", guide(70, 0))]
    f = d / f"{name}.md"
    f.write_text(WL.render_script(name, kind, "t", [], [], parts, meta))
    scale = WL.fit_pause_scale(WL.parse(f), goal_s=3780)
    f.write_text(WL.render_script(name, kind, "t", [], [], parts, {**meta, "Pause scale": scale}))
    return f


def probs(f: Path, others=None) -> list[str]:
    return WL.script_problems(f, others=others or [])


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # a. a good script
    good = build(td, "good")
    base = probs(good)
    check(base == [], f"(a) a well-formed teaching script fails: {base[:4]}")

    # b. uncleared titles and a quote with no book
    for lead, code in (("In Resurrection, Neville wrote:", "QUOTE_UNCLEARED_TITLE"),
                       ("In his lectures and lecture compilations (Immortal Man, The Creative Use of "
                        "Imagination, Five Lessons and others), he said:", "QUOTE_"),
                       ("Neville once said:", "QUOTE_NO_TITLE")):
        bad = build(td, "uncleared", parts=[("explain", EXPLAIN),
                                            ("quotes", [f"{lead} “What you desire to hear without, you must hear within.”", QUOTES[1]]),
                                            ("guide-1", guide(70, 0))])
        got = probs(bad)
        check(any(code in x for x in got), f"(b) {lead[:30]!r} was not refused with {code}: {got[:3]}")
    shinn_unchecked = build(td, "shinn-unchecked", kind="shinn",
                            meta={"Technique": "law-of-prosperity"},
                            parts=[("explain", ["Florence Scovel Shinn taught that plenty starts within. "
                                                "Tonight you rest in that feeling, slowly and calmly."]),
                                   ("quotes", ["In The Secret Door to Success, she wrote: “I am awake to my good.”",
                                               "In Your Word Is Your Wand, she wrote: “I am awake to my good, "
                                               "and gather in the harvest of endless opportunities.”"]),
                                   ("guide-1", guide(70, 1))])
    got = probs(shinn_unchecked)
    check(any("QUOTE_UNCLEARED_TITLE" in x and "unchecked" in x for x in got),
          f"(b) a quote from an unchecked Shinn title was not refused: {got[:3]}")

    # c. a line not in the record
    bad = build(td, "misquote", parts=[("explain", EXPLAIN),
                                       ("quotes", [QUOTES[0].replace("within", "inside you"), QUOTES[1]]),
                                       ("guide-1", guide(70, 0))])
    check(any("QUOTE_NOT_IN_RECORD" in x for x in probs(bad)), "(c) a misquoted line was not refused")

    # d. a straight reading, and too many quotes
    book = [q["text"] for q in R["quotes"] if R["titles"][q["title"]]["teacher"] == "neville"]
    reading = [" ".join(book[i:i + 4]) for i in range(0, len(book), 4)]
    bad = build(td, "reading", parts=[("explain", EXPLAIN + reading), ("quotes", QUOTES),
                                      ("guide-1", guide(70, 0))])
    got = probs(bad)
    check(any(x.startswith("BOOK_READ") for x in got), f"(d) a straight reading was not refused: {got[:3]}")
    five = QUOTES + [f"In Out of This World, Neville wrote: “{q['text']}”" for q in R["quotes"]
                     if q["title"] == "out-of-this-world"]
    bad = build(td, "five", parts=[("explain", EXPLAIN), ("quotes", five), ("guide-1", guide(70, 0))])
    check(any("QUOTE_COUNT" in x for x in probs(bad)), "(d) five quotes were not refused")

    # e. structure
    twin = build(td, "twin", parts=[("explain", EXPLAIN), ("quotes", QUOTES), ("guide-1", guide(70, 40))])
    got = probs(twin, others=[good])
    check(any("NOT_DISTINCT_STRUCTURE" in x for x in got), f"(e) the same shape and scene passed: {got[:3]}")
    other_scene = build(td, "scene2", meta={"Scene": c["teachings"]["scenes"][1]},
                        parts=[("explain", EXPLAIN), ("quotes", QUOTES), ("guide-1", guide(70, 40))])
    check(not any("NOT_DISTINCT_STRUCTURE" in x for x in probs(other_scene, others=[good])),
          "(e) a different scene was refused as the same structure")
    bad = build(td, "shape", meta={"Shape": "a"})
    check(any(x.startswith("SHAPE") for x in probs(bad)), "(e) parts out of their shape were not refused")

    # f. a promise
    g = guide(70, 0)
    g[5] = "You will get money by friday, and he will text you tonight."
    bad = build(td, "promise", parts=[("explain", EXPLAIN), ("quotes", QUOTES), ("guide-1", g)])
    check(any("GUARANTEED_OUTCOME" in x for x in probs(bad)), "(f) a promise in the guided part passed")

    # g. the kit text
    p = WL.parse(good)
    secs = WL.estimate_seconds(p, c)
    d = WL.description(p, secs, c)
    for want in ("Neville Goddard (1905", "Not affiliated", "Quoted from: Awakened Imagination (1954)",
                 c["channel"]["ai_voice_line"], "not a promise"):
        check(want in d, f"(g) the Neville description lacks {want!r}")
    check(c["lanes"]["money"]["products_line"] not in d, "(g) the products line is on a Neville video")
    t = WL.title(p, secs, c)
    m = {"title": t, "description": d, "body": WL.upload_body(t, d, c, "neville")}
    m["body"]["status"]["privacyStatus"] = "private"
    check(WL.meta_problems(m, secs, c) == [], f"(g) a Neville title fails the kit rules: {t} {WL.meta_problems(m, secs, c)}")
    check("neville goddard asmr" in m["body"]["snippet"]["tags"], "(g) the secondary tag is missing")
    m2 = {**m, "title": t.replace("·", "· no ads ·")}
    m2["body"] = WL.upload_body(m2["title"], d, c, "neville")
    check(any("TITLE_BANNED_WORDS" in x for x in WL.meta_problems(m2, secs, c)), "(g) 'no ads' in a title passed")
    money = {"kind": "affirmations", "slug": "x", "meta": {"theme": "billionaire"}, "segments": [], "title": ""}
    dm = WL.description(money, 3700, c)
    check(dm.count("billionairehighperformancecoach.com") == 1 and "aplayermode.com" in dm,
          "(g) the Money description lacks its one products line")
    check(WL.lane_of(money, c) == "money" and WL.lane_of({**money, "meta": {"theme": "love"}}, c) == "rotating",
          "(g) affirmation themes are in the wrong lanes")

# g2. every recorded line, with every lead the author may give it, stays a
#     sentence the script check accepts (8 Nov run: a Shinn lead + quote was 30 words)
import whisper_author as WA  # noqa: E402
for teacher, tc in c["teachings"].items():
    if teacher not in WL.TEACHING:
        continue
    for topic in tc["topics"]:
        for n in range(6):
            try:
                paras = WA.quote_paras(teacher, topic, n, "a")
            except WA.WL_SegmentRefused:
                continue
            for para in paras:
                for s in WL.sentences(para):
                    check(len(WL.W.WORD.findall(s)) <= c["pacing"]["max_sentence_words"],
                          f"(g2) {teacher}/{topic} quote sentence too long: {s[:70]!r}")
                pr, _ = T.quote_problems(para, teacher)
                check(pr == [], f"(g2) {teacher}/{topic}: the author's quote paragraph is refused: {pr[:1]}")

# h. the mix and the queue
mix, _ = WL.weekly_mix(c, {})
check(mix == {"neville": 2, "money": 1, "rotating": 0, "food": 1, "ocean": 1}, f"(h) the mix before monetisation: {mix}")
mix, _ = WL.weekly_mix(c, {"subscribers": 1200, "watch_hours_365d": 4100})
check(mix["food"] + mix["ocean"] > 2 and mix["money"] >= 1 and sum(mix.values()) == 5,
      f"(h) monetised did not shift to the sleep lanes and money: {mix}")
# h2. the weekly Monday re-weighting (her yes 11 Nov 2026): the lane with the
# most watch hours per video over 28 days gets the week's spare night; 5 a
# week, every lane with a slot keeps 1, Neville 1 or more; no numbers, no move
base = WL.base_mix(c, {})
lanes = {"neville": {"videos_28d": 3, "watch_hours_per_video": 2.0},
         "money": {"videos_28d": 3, "watch_hours_per_video": 1.0},
         "ocean": {"videos_28d": 4, "watch_hours_per_video": 9.0}}
got = WL.reweight(base, lanes, c)
check(got is not None and got[0] == {"neville": 1, "money": 1, "rotating": 0, "food": 1, "ocean": 2},
      f"(h2) the spare night did not go to the lane with the most watch hours per video: {got}")
for top in ("neville", "money", "food", "ocean"):
    one = {ln: {"videos_28d": 2, "watch_hours_per_video": 9.0 if ln == top else 0.1} for ln in base}
    mix, _ = WL.reweight(base, one, c)
    check(sum(mix.values()) == 5 and mix["neville"] >= 1 and mix["rotating"] == 0
          and all(mix[ln] >= 1 for ln in base if base[ln] > 0) and mix[top] == 2,
          f"(h2) with {top} on top the week is not 5 with every active lane at 1+: {mix}")
check(WL.reweight(base, {}, c) is None and WL.reweight(base, {"ocean": {"videos_28d": 0, "watch_hours_per_video": None}}, c) is None,
      "(h2) a week with no measured video was re-weighted")
check(WL.reweight(base, {"rotating": {"videos_28d": 5, "watch_hours_per_video": 50.0}}, c) is None,
      "(h2) a lane with no slot in the plan took the spare night")
decided = {"week": "2026-W49", "decided_on": "2026-11-30", "base": base, "mix": got[0], "why": got[1]}
mix, why = WL.weekly_mix(c, {"reweight": decided})
check(mix == got[0] and any("2026-W49" in w for w in why), f"(h2) the Monday decision is not the week's mix: {mix} {why}")
mix, _ = WL.weekly_mix(c, {"reweight": decided, "subscribers": 1200, "watch_hours_365d": 4100})
check(mix == WL.base_mix(c, {"subscribers": 1200, "watch_hours_365d": 4100}),
      f"(h2) a decision made on the old plan outlived monetisation: {mix}")
rows = {"the-deep-ocean-at-night": "ocean", "money-a": "money"}
orig_parse, orig_all, orig_voiced = WL.parse, WL.all_scripts, WL.voiced
try:
    WL.all_scripts = lambda: [Path(f"/x/{s}.md") for s in rows]
    WL.parse = lambda f: {"slug": Path(f).stem, "status": WL.READY, "segments": [],
                          "kind": "sleep" if rows[Path(f).stem] == "ocean" else "affirmations",
                          "meta": {"theme": "billionaire", "written": "2026-11-09"}}
    WL.voiced = lambda s: (0, 10)
    q = WL.queue(c, mix={"ocean": 2, "money": 1, "neville": 1, "rotating": 1}, made={"ocean": 2})
    check(q[:1] == ["money-a"], f"(h) the lane furthest behind did not voice first: {q}")
    q = WL.queue(c, mix={"ocean": 2, "money": 1, "neville": 1, "rotating": 1}, made={})
    check(q[:1] == ["the-deep-ocean-at-night"], f"(h) with nothing made, ocean (2 a week) did not lead: {q}")
finally:
    WL.parse, WL.all_scripts, WL.voiced = orig_parse, orig_all, orig_voiced

# i. the rights record
ok = T.quotable(R)
check(len(R["quotes"]) >= 20, "(i) fewer than 20 verified lines recorded")
for q in R["quotes"]:
    t = R["titles"].get(q["title"], {})
    check(q["title"] in ok, f"(i) {q['id']} quotes {q['title']}, which is not quotable")
    check(bool(t.get("checked_on")) and (t.get("status") != "not_renewed" or R["renewal_check"]["sources"]),
          f"(i) {q['title']} has no dated check")
check(all(v["status"] != "not_renewed" or 1923 <= v["published"] <= 1963 for v in R["titles"].values()),
      "(i) a 'not renewed' title outside 1923-1963")
check(all(v["status"] != "public_domain_pre_1930" or v["published"] < 1930 for v in R["titles"].values()),
      "(i) a pre-1930 title published after 1929")
check(len(T.book_runs()) > 1000, "(i) the book record is empty: the straight-reading check would examine nothing")

if fails:
    print("FAIL test_teaching_lanes")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_teaching_lanes: quotes cleared and verbatim, no straight reading, distinct structure, "
      "no promises, kit credits, four-lane mix from the channel's numbers")
