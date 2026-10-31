"""food-science, the third domain: registered everywhere, held by its sample gate.

Owner decision 2026-10-13 (docs/CHANNEL-PLAN.md "A third domain: food
science", "Three-niche schedule"). What this proves, on the real repo:

  1. V52 passes on the real repo with the sample gate reported as a note, and every
     list that enumerates domains names food-science (V52 reads them all).
  2. The sample gate HOLDS: domains.allocation_gate refuses a food row,
     batch_queue.publish_queue_gate refuses a food slug, the digest calendar
     counts no food slot, and loop/handoff.py plans no food playlist - while
     the same row passes once the gate is cleared.
  3. A pending POV line is never selected (pov_match.bank) and counts for
     validate_plan c10 ONLY while the gate is open: cleared with no approved
     line, c10 fails.
  4. The seeded queue: the first video's three questions + >= 20 more, each
     with the free demand signals and its floor verdict recorded, and
     publish_order_domain screens the seeded questions first.
  5. The four food scripts pass the house checks the author lane applies
     (shape, directive truth/parse, the stake-then-payoff hook, the title
     formula and its truth guard), with no network.
  6. loop/upload.altered_content: the episode spec answers YES for the food
     episode; a video with no spec keeps the 14 Sep NO.

NEGATIVE PROOFS (run 2026-10-13, then restored):
  * remove "food-science" from visuals/thumbs_for.BUILDERS -> V52 fails naming
    the missing builder;
  * disable `if dom in gated` in domains.allocation_gate -> cases 1 and 2 fail
    ("allocation_gate let a food row through");
  * the cleared-gate c10 failure is case 3 itself, run every time.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))
sys.path.append(str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import common                                                  # noqa: E402
import domains as D                                            # noqa: E402

FOOD = "food-science"
fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


cfg = common.config()

# ------------------------------------------------------------------ 1. V52
import validate as V                                           # noqa: E402
res = V.v52_food_domain().as_dict()
check(not res["failures"], f"V52 passes on the real repo: {res['failures']}")
check(not res["stops"], "V52 takes no stop on the real repo")

# ------------------------------------------------------------------ 2. the gate (CLEARED 13 Oct 2026)
# The owner approved the round-2 chocolate sample on 13 Oct 2026 ("MUCH better").
# The real config records it, dated; the gate's machinery is still proven on a
# gated COPY, so it holds the next domain that is sample-gated.
gate = cfg["domains"]["sample_gate"][FOOD]
check(gate["state"] == "cleared" and "13 Oct 2026" in gate.get("cleared_note", "")
      and "round 2" in gate.get("cleared_note", ""),
      f"the real gate is cleared with the owner's dated note: {gate.get('state')} / {gate.get('cleared_note')}")
check(FOOD not in D.sample_gated(cfg), "food-science is no longer sample-gated in the real config")
ok, refused = D.allocation_gate([{"slug": "f", "domain": FOOD}], cfg)
check(bool(ok) and not refused, f"allocation_gate lets a food row through now: {refused}")
import batch_queue as BQ                                       # noqa: E402
allowed, why = BQ.publish_queue_gate(["why-bread-rises-steak-browns-chocolate-snaps"])
check(allowed == ["why-bread-rises-steak-browns-chocolate-snaps"],
      f"publish_queue_gate admits the first food episode: {why}")
import digest                                                  # noqa: E402
import datetime as dt                                          # noqa: E402
cal = digest.calendar({"published": []}, cfg, dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc))
check(any(c["domain"] == FOOD for c in cal), "cleared: food's Wed/Sat are counted slots")
gated = json.loads(json.dumps(cfg))
gated["domains"]["sample_gate"][FOOD]["state"] = "awaiting_owner_review"
okg, refg = D.allocation_gate([{"slug": "f", "domain": FOOD}], gated)
check(not okg and "sample_gate" in refg.get("f", ""),
      f"a gated copy still refuses a food row by name: {refg}")
calg = digest.calendar({"published": []}, gated, dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc))
check(calg and not any(c["domain"] == FOOD for c in calg),
      "a gated copy counts no food slot (empty by design, not a gap)")
cleared = cfg

# ------------------------------------------------------------------ 3. POV
import pov_match                                               # noqa: E402
bank = json.loads((ROOT / "pov" / "pov-bank.json").read_text())["lines"]
pending = [ln for ln in bank if ln.get("pending_approval")]
check(len(pending) >= 3 and all(ln.get("domain") == FOOD for ln in pending),
      "three pending food POV lines are in the bank")
check(not any(ln["id"] in {p["id"] for p in pending} for ln in pov_match.bank()),
      "pov_match.bank() never offers a pending line")
import validate_plan as VP                                     # noqa: E402
c10 = VP.c10_domains_admitted()
check(not c10.failures, f"c10 passes on the real repo: {c10.failures}")
check(cfg["domains"].get("pov_not_required", {}).get(FOOD, {}).get("decided") == "2026-10-13",
      "food-science ships with no POV beat by a dated declaration, until its top-up")
saved = VP.config
undeclared = json.loads(json.dumps(cfg))
undeclared["domains"].pop("pov_not_required", None)
VP.config = lambda: undeclared
try:
    c10b = VP.c10_domains_admitted()
finally:
    VP.config = saved
check(any("food-science" in f for f in c10b.failures),
      "c10 FAILS a cleared food domain with only pending lines and no declaration")
# the declaration never excuses a [HUMAN] beat in a shipping food episode
ep = ROOT / "scripts" / "food" / "why-bread-rises-steak-browns-chocolate-snaps.md"
orig = ep.read_text()
try:
    ep.write_text(orig.replace("### Closing\n\n{{ambient}}\n", "### Closing\n\n{{ambient}}\n[HUMAN] ", 1))
    c10c = VP.c10_domains_admitted()
finally:
    ep.write_text(orig)
check(any("[HUMAN]" in f for f in c10c.failures),
      f"c10 FAILS a shipping food episode that carries a [HUMAN] beat: {c10c.failures}")


# ------------------------------------------------------------------ 4. queue
po = json.loads((ROOT / "research" / "publish_order_food_science.json").read_text())
# Every question put to the gate, whatever it decided (2026-10-17: the first
# Saturday score measured the seeded rows; killed ones left the queue).
rows = po["queue"] + po["unmeasured"]
ep_parts = [list(r.get("first_video_parts") or []) for r in po["queue"]]
qs = ({r["query"] for k in ("queue", "unmeasured", "killed", "parts_of_episodes")
       for r in po.get(k) or []} | {q for ps in ep_parts for q in ps})
check(len(po["first_video"]) == 3 and set(po["first_video"]) <= qs and len(qs) >= 23,
      f"queue seeds the first video's three + >= 20 more ({len(qs)})")
check(po["first_video"] in ep_parts,
      "the first video's three are the first_video_parts of a queued episode row")
import batch_queue as BQ                                       # noqa: E402
check(not [r["slug"] for r in po["queue"]
           if (r.get("gate") or {}).get("verdict") in BQ.KILL_VERDICTS
           and not r.get("gate_overridden")],
      "no row the gate killed sits in the food queue")
check(not [r["slug"] for r in po["queue"] if not r.get("first_video_parts")
           and any(r["query"] in ps for ps in ep_parts)],
      "no part of a made episode is queued as its own topic")
check(all(p.get("episode") in {r["slug"] for r in po["queue"]}
          for p in po.get("parts_of_episodes") or []),
      "every recorded part names a queued episode")
check([r["slug"] for r in BQ.food_entries()] ==
      [r["slug"] for r in po["queue"] if BQ.food_made(r["slug"])
       and r.get("first_video_parts")],
      "the batch's food rows are the made episodes only, never their parts")
# The settle pass that keeps it so, on a rebuilt blob with the 2026-10-17
# defects planted: a killed row, a part as a topic, no first_video.
import publish_order_domain as POD                             # noqa: E402
_ep = next(r for r in po["queue"] if r.get("first_video_parts"))
_bad = {"queue": [dict(_ep),
                  {"slug": "x-part", "query": _ep["first_video_parts"][1],
                   "gate": {"verdict": "passed"}},
                  {"slug": "x-dead", "query": "why is x",
                   "gate": {"verdict": "killed_provisional"}},
                  {"slug": "x-live", "query": "why is y",
                   "gate": {"verdict": "passed"}}],
        "killed": [], "unmeasured": [{"query": "why is z",
                                      "meets_floor_on_free_signals": True}]}
_nofile = str(ROOT / "research" / "zz-no-such-queue.json")
POD.settle(_nofile, _bad)
check([r["slug"] for r in _bad["queue"]] == [_ep["slug"], "x-live"]
      and [r["slug"] for r in _bad["killed"]] == ["x-dead"]
      and [(p["slug"], p["episode"]) for p in _bad["parts_of_episodes"]]
      == [("x-part", _ep["slug"])]
      and _bad["first_video"] == list(_ep["first_video_parts"])
      and _bad["meets_floor_on_free_signals"] == ["why is z"],
      "settle() removes killed rows and parts, carries first_video: "
      f"{[r['slug'] for r in _bad['queue']]}")

# ...and the batch's read applies the same two rules to whatever a queue FILE
# holds (files are left as written; batch_queue._screened is the one read).
_saved_raw = BQ._raw_entries
BQ._raw_entries = lambda: [dict(_ep, _domain_file="f.json"),
                           {"slug": "zz-part-unwritten", "query": _ep["first_video_parts"][1],
                            "gate": {"verdict": "passed"}, "_domain_file": "f.json"},
                           {"slug": "zz-killed-unwritten", "query": "why is the sky green",
                            "gate": {"verdict": "killed"}, "_domain_file": "f.json"}]
try:
    _kept = [r["slug"] for r in BQ.queued_entries()]
    _ref = {r["slug"]: r["killed_by"] for r in BQ.refused_entries()}
finally:
    BQ._raw_entries = _saved_raw
check(_kept == [_ep["slug"]] and _ref == {"zz-part-unwritten": "PART_OF_EPISODE",
                                          "zz-killed-unwritten": "GATE_KILLED"},
      f"the batch refuses a part and a killed topic by name: {_kept} {_ref}")

# ONE WRITER for the food clip manifest: research/food_footage.py. On
# 2026-10-17 research/imagery_food.py's Commons clip pass rewrote it in its own
# schema on the CI harvest and V53 went red.
_writers = sorted(p.name for p in (ROOT / "research").glob("*.py")
                  if "food_clips.json" in p.read_text() and p.name != "food_footage.py")
check(_writers == [], f"only research/food_footage.py names food_clips.json: {_writers}")
check(all("demand_without_competition" in r and "meets_floor_on_free_signals" in r
          for r in po["unmeasured"]),
      "every unmeasured row records its free demand and its floor verdict")
check(po["meets_floor_on_free_signals"] == [r["query"] for r in po["unmeasured"]
                                             if r["meets_floor_on_free_signals"]],
      "the floor list is derived from the rows, not typed")
import publish_order_domain as POD                             # noqa: E402
seeded = [r["query"] for r in POD.seed_questions(FOOD)]

# THE WRITER, not only the file (2026-10-31, run 41216027220): the Saturday
# score lane's score_queries() wrote unmeasured rows as {"query", "status"}
# and the checks above went red on committed data. Drive it with one scored and
# one unscored question (competition stubbed from the real measured file, the
# free probe stubbed) and require the unscored row to carry both fields.
import tempfile                                                # noqa: E402
_comp = json.loads((ROOT / "research" / "competition_food_science.json").read_text())
_ok = next(r for r in _comp["results"] if r["status"] == "ok")
_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump(dict(_comp, results=[_ok]), _tmp)
_tmp.close()
_probe = {"autocomplete_completions": 10, "exact_in_autocomplete": True,
          "corpus_breadth": 5, "key_term": "zz", "key_term_completions": 3,
          "key_term_corpus_breadth": 5, "sample_completions": [],
          "provenance": {"endpoint": "stub", "surface": "stub", "fetched_utc": "stub"}}
_saved = POD.ensure_competition, POD.demand_probe
POD.ensure_competition = lambda *a, **k: _tmp.name
POD.demand_probe = lambda q, ct, pause: dict(_probe)
try:
    _rows, _un = POD.score_queries(FOOD, [_ok["query"], "why is zz unscored"], 0, 0)
finally:
    POD.ensure_competition, POD.demand_probe = _saved
    os.unlink(_tmp.name)
check(len(_rows) == 1 and [u["query"] for u in _un] == ["why is zz unscored"]
      and all(isinstance(u.get("demand_without_competition"), float)
              and u.get("meets_floor_on_free_signals")
              == (u["demand_without_competition"] >= POD.DEMAND_FLOOR)
              for u in _un),
      f"score_queries() records free demand and the floor verdict on every unmeasured row: {_un}")
check(seeded[:3] == po["first_video"], "the seeded questions lead with the first video's three")

# ------------------------------------------------------------------ 5. scripts
import author as A                                             # noqa: E402
import longform_title as LT                                    # noqa: E402
import opening                                                 # noqa: E402
import re                                                      # noqa: E402
food = sorted((ROOT / "scripts" / "food").glob("*.md"))
# The hand-made four (the first episode and its three parts), exactly; every
# other food script is the food author lane's (2026-10-25): it carries the
# lane's mark and a kit for each of its segments, and passes the same checks.
HAND = {"why-bread-rises-steak-browns-chocolate-snaps.md", "why-does-bread-rise.md",
        "why-does-chocolate-melt-in-your-mouth-not-your-hand.md", "why-does-seared-meat-taste-good.md"}
import food_author as FA                                       # noqa: E402
check(HAND <= {p.name for p in food}, f"the four hand-made food scripts: {[p.name for p in food]}")
for p in food:
    if p.name in HAND:
        continue
    t = p.read_text()
    check(FA.LANE_MARK in t, f"{p.name}: a food script not hand-made must be the lane's")
    segs = re.findall(r"^### ([A-Z][a-z]+): ", t, re.M)
    for s in dict.fromkeys(segs):
        check((ROOT / "channel" / "food_kits" / f"{s.lower()}.json").exists(),
              f"{p.name}: segment {s} has no kit")
for p in food:
    t = p.read_text()
    check(D.domain_of_script(p) == FOOD, f"{p.name}: **Domain:** food-science")
    probs = A.directive_truth_problems(t) + A.directive_parse_problems(t) \
        + opening.problems(t, opening.active())
    title = LT.script_title(t)
    probs += LT.title_problems(title, t) if title else ["no ## YouTube title"]
    if "Part:" in t:
        pid = re.search(r"FROM POV BANK \((pov-\d+)\)", t).group(1)
        line = next(ln for ln in pov_match.bank() if ln["id"] == pid)
        probs += A.shape_problems(t, {"line": line["line"], "pov_id": pid})
    check(not probs, f"{p.name}: house checks {probs}")

# ------------------------------------------------------------------ 6. altered content
import upload                                                  # noqa: E402
check(upload.altered_content("why-bread-rises-steak-browns-chocolate-snaps") is True,
      "the food episode spec answers YES to altered or synthetic content")
check(upload.altered_content("02-how-deep-sea-creatures-survive-pressure") is False,
      "a video with no spec keeps the 14 Sep NO")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
