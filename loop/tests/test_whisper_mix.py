"""Whisper Almanac's weekly mix, her decision 9 Nov 2026 (option "a").

Five videos a week before monetisation: 2 Neville Goddard, 1 Money, 1 food
history, 1 ocean documentary, 0 rotating; uploads Mon Neville, Tue food
history, Wed Money, Thu Neville, Fri ocean documentary. Each check fails on
the code before that decision:

  a. a fresh week's queue (nothing made, every lane stocked) voices exactly
     2 Neville, 1 Money, 1 food history, 1 ocean documentary and no rotating;
  b. a food script's title reads as history; a deep-sea script's title says
     "deep sea documentary" and names a place; an animal-facts ocean title,
     and a food title without history, are refused by the kit check;
  c. Neville uploads land on Mon and Thu; food on Tue, ocean on Fri, Money on Wed;
  c2. a finished food or ocean video takes the other lane's day while that
      lane has no render waiting (a finished video never waits for a planned one);
  d. a food episode's parts are the food script's own sections (no part
     borrows another's text), and the author writes the next food and ocean
     episodes from fact-checked sources only;
  e. "no ai" / "human voiced" in a title is refused.
"""
import datetime as dt
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"

import whisper_lane as WL  # noqa: E402
import whisper_upload as WU  # noqa: E402

c = WL.cfg()
fails: list[str] = []
examined = 0


def check(ok, msg):
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


# -- a. a fresh week's queue --------------------------------------------------
food_ep = next((e for e in c["episodes"] if e.get("lane") == "food"), None)
ocean_ep = next((e for e in c["episodes"] if e.get("lane") == "ocean"), None)
check(food_ep and ocean_ep, "(a) no planned food-history or ocean-documentary episode")
stock = {}
for i in range(3):
    stock[f"nev-{i}"] = {"kind": "neville", "meta": {}}
    stock[f"money-{i}"] = {"kind": "affirmations", "meta": {"theme": "billionaire"}}
    stock[f"love-{i}"] = {"kind": "affirmations", "meta": {"theme": "love"}}
for e in c["episodes"]:
    if e.get("lane") in ("food", "ocean"):
        stock[e["slug"]] = {"kind": "sleep", "meta": {}}
stock["shinn-0"] = {"kind": "shinn", "meta": {}}
orig = WL.parse, WL.all_scripts, WL.voiced, WL.footage_gaps, WL.handed_on, WL.video_path
try:
    WL.all_scripts = lambda: [Path(f"/x/{s}.md") for s in stock]
    WL.parse = lambda f: {"slug": Path(f).stem, "status": WL.READY, "segments": [],
                          **stock[Path(f).stem],
                          "meta": {**stock[Path(f).stem]["meta"], "written": "2026-11-09"}}
    WL.voiced = lambda s: (0, 10)
    WL.footage_gaps = lambda p: []
    WL.handed_on = lambda s: False
    WL.video_path = lambda s: Path("/nonexistent") / f"{s}.mp4"
    c_now = {**c, "episodes": [{k: v for k, v in e.items() if k != "waits_for"} for e in c["episodes"]]}
    mix, _ = WL.weekly_mix(c_now, {})
    made: dict[str, int] = {}
    picked = []
    for _ in range(5):
        q = [s for s in WL.queue(c_now, mix=mix, made=made) if s not in picked]
        check(q, "(a) the queue ran dry before 5 videos")
        if not q:
            break
        picked.append(q[0])
        ln = WL.lane_of(WL.parse(Path(f"/x/{q[0]}.md")), c_now)
        made[ln] = made.get(ln, 0) + 1
    check(made == {"neville": 2, "money": 1, "food": 1, "ocean": 1},
          f"(a) a fresh week voices {made} ({picked}), not 2 Neville, 1 Money, 1 food, 1 ocean, 0 rotating")
finally:
    WL.parse, WL.all_scripts, WL.voiced, WL.footage_gaps, WL.handed_on, WL.video_path = orig

# -- b. titles framed per lane -----------------------------------------------
secs = 7300.0


def kit_for(slug, lane, title=None):
    p = {"slug": slug, "kind": "sleep", "meta": {}, "segments": [], "title": ""}
    t = title or WL.title(p, secs, c)
    d = WL.description(p, secs, c)
    return {"title": t, "description": d, "lane": lane, "body": WL.upload_body(t, d, c, lane)}


for ep, lane in ((food_ep, "food"), (ocean_ep, "ocean")):
    if not ep:
        continue
    m = kit_for(ep["slug"], lane)
    check(WL.lane_of({"slug": ep["slug"], "kind": "sleep", "meta": {}, "segments": []}, c) == lane,
          f"(b) {ep['slug']} is not in the {lane} lane")
    check(WL.meta_problems(m, secs, c) == [], f"(b) the planned {lane} title fails the kit: {m['title']} "
          f"{WL.meta_problems(m, secs, c)}")
food_t = kit_for(food_ep["slug"], "food")["title"].lower()
check("history" in food_t and "science" not in food_t, f"(b) the food title does not read as history: {food_t}")
for e in c["episodes"]:
    if e.get("lane") == "ocean":
        t = kit_for(e["slug"], "ocean")["title"].lower()
        check("deep sea documentary" in t, f"(b) an ocean title lacks 'deep sea documentary': {t}")
        check(not any(w in t for w in ("creature", "animal", "facts", "squid")),
              f"(b) an ocean title uses an animal-facts pattern: {t}")
bad_ocean = kit_for("x", "ocean", "ASMR whispered deep sea creature facts for deep sleep · fall asleep tonight (2 hr)")
check(any("TITLE_LANE_FRAME" in x for x in WL.meta_problems(bad_ocean, secs, c)),
      "(b) an animal-facts ocean title passes the kit check")
bad_food = kit_for("x", "food", "ASMR whispered food science for deep sleep · why bread rises (2 hr)")
check(any("TITLE_LANE_FRAME" in x for x in WL.meta_problems(bad_food, secs, c)),
      "(b) a food title without history passes the kit check")

# -- c. upload days -----------------------------------------------------------
MON_LATE = dt.datetime(2026, 11, 10, 3, 0, tzinfo=dt.timezone.utc)      # Mon 9 Nov 21:00 CST


def slot_day(k, taken=()):
    # both sleep lanes have a render waiting, so each keeps its own day (c2 covers sharing)
    ks = {f"t{i}": {"scheduled_publish_at": s} for i, s in enumerate(taken)}
    ks.update({w: {"lane": w, "length_basis": "measured"} for w in ("food", "ocean")})
    return WU.next_slot(WU.days_for(k, c, ks), ks, MON_LATE, c)


nev = {"kind": "neville", "lane": "neville"}
first = slot_day(nev)
second = slot_day(nev, [WU.stamp(first)])
check((first.strftime("%a"), second.strftime("%a")) == ("Thu", "Mon"),
      f"(c) Neville uploads land on {first:%a} then {second:%a}, not Thu then Mon")
for k, want in (({"kind": "sleep", "lane": "food"}, "Tue"), ({"kind": "sleep", "lane": "ocean"}, "Fri"),
                ({"kind": "affirmations", "lane": "money"}, "Wed")):
    got = slot_day(k).strftime("%a")
    check(got == want, f"(c) a {k['lane']} upload lands on {got}, not {want}")

# c2. a finished video never waits for a planned one (9 Nov 2026): an ocean
#     render takes the free Tue food slot while no food render waits; with a
#     food render waiting it keeps Fri
ocean_k = {"kind": "sleep", "lane": "ocean"}
got = WU.next_slot(WU.days_for(ocean_k, c, {}), {}, MON_LATE, c).strftime("%a")
check(got == "Tue", f"(c2) a rendered ocean video with no food render waiting lands on {got}, not Tue")
food_waits = {"f": {"lane": "food", "length_basis": "measured"}}
got = WU.next_slot(WU.days_for(ocean_k, c, food_waits), food_waits, MON_LATE, c).strftime("%a")
check(got == "Fri", f"(c2) with a food render waiting, the ocean video took {got}, not its own Fri")
nev_days = WU.days_for({"kind": "neville", "lane": "neville"}, c, {})
check(nev_days == ["neville"], f"(c2) a manifesting lane borrows sleep days: {nev_days}")

# -- d. food parts and the author's next episodes ----------------------------
parts = [WL.source_narration(s) for s in food_ep["sources"]]
check(all(len(x.split()) > 600 for x in parts), f"(d) a food part is nearly empty: {[len(x.split()) for x in parts]}")
check("yeast" in parts[0].lower() and "yeast" not in parts[2].lower(),
      "(d) a food part carries another part's text")
whole = WL.source_narration(WL.base_slug(food_ep["sources"][0]))
check("what to notice" not in whole.lower(), "(d) an edit note is read as narration")
import whisper_author as WA  # noqa: E402
for lane in ("food", "ocean"):
    e = WA.next_episode(lane, c)
    if e is not None:
        check(e.get("lane") == lane and all(WL.base_slug(s) in WL.fact_checked() for s in e["sources"]),
              f"(d) the author's next {lane} episode is wrong: {e and e['slug']}")
check(set(WA.sleep_lanes(c)) >= {"food", "ocean"}, f"(d) the author does not write food and ocean: {WA.sleep_lanes(c)}")
unchecked = {**c, "episodes": [{**food_ep, "sources": ["never-uploaded-script"]}]}
check(WA.next_episode("food", unchecked) is None, "(d) the author would write from an unchecked source")

# -- d2. a kit rendered under the retired "history" lane is retitled before upload
stale = {"slug": ocean_ep["slug"], "kind": "sleep", "lane": "history", "length_s": secs,
         "title": "ASMR whispered deep sea creature science for deep sleep · fall asleep tonight (2 hr)",
         "body": {"snippet": {"title": "old"}}}
if (WL.SCRIPTS / f"{ocean_ep['slug']}.md").exists():
    r = WL.retitle(stale, c)
    check(r["lane"] == "ocean" and "deep sea documentary" in r["title"] and r["body"]["snippet"]["title"] == r["title"],
          f"(d2) a stale-lane kit keeps its old title: {r['title']}")
for e in c["episodes"]:
    if (WL.SCRIPTS / f"{e['slug']}.md").exists() and e.get("lane") == "ocean":
        r = WL.retitle({**stale, "slug": e["slug"]}, c)
        check("deep sea documentary" in r["title"], f"(d2) {e['slug']} is not retitled: {r['title']}")
        break
check(WL.retitle({**stale, "video_id": "abc"}, c)["title"] == stale["title"], "(d2) an uploaded kit was retitled")

# -- e. never "no AI" / "human voiced" ---------------------------------------
for w in ("No AI", "human voiced"):
    m = kit_for("x", "", f"ASMR whispered history for deep sleep · {w} (2 hr)")
    check(any("TITLE_BANNED_WORDS" in x for x in WL.meta_problems(m, secs, c)), f"(e) {w!r} in a title passes")

check(examined >= 15, f"only {examined} checks examined")
if fails:
    print("FAIL test_whisper_mix")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"ok test_whisper_mix: {examined} checks; 2 Neville + 1 Money + 1 food history + 1 ocean documentary, "
      "lane titles, Mon/Thu Neville")
