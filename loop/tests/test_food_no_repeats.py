"""The food author never makes the same video twice.

THE INCIDENT (2 Nov 2026). The 13 Oct episode "Bread, Steak, Chocolate:
What's Inside?" (why-bread-rises-steak-browns-chocolate-snaps, 8bVPoTWAfFQ,
public 17 Oct) was made. The author then wrote
what-is-inside-chocolate-steak-bread from three DIFFERENT questions about the
SAME three foods; it was due to render on the Mac that night and was undone
with food_author.py --unmake. Only the SAME VIDEO is a repeat - the same trio
(order-insensitive) or the same slug. Owner, 2 Nov: "a new video with another
meat in it but a different trio is fine. That was so petty." No synonyms.

WHAT THIS PROVES
  1. A constructed queue holding only the 13 Oct episode, whose next rows are
     chocolate, steak, bread, cheese: next_parts() refuses the third food that
     would complete the 13 Oct trio and takes cheese instead; a trio sharing
     one or two foods, or a "meat" for its "steak", is allowed.
  2. The same set is read from a food episode SPEC alone and from an UPLOAD
     (ledger) alone, with no queue row behind them.
  3. On the real records, no two made episodes have the same set, and the
     next episode next_parts() would author is not a made set.
Prove-it-fails: delete the `repeats(foods | {f}, made)` check in next_parts
-> cases 1 and 3 fail; restore -> green.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / "visuals"))

import food_author as A                                        # noqa: E402
import batch_queue as BQ                                       # noqa: E402
import ledger                                                  # noqa: E402

fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


FIRST = {"slug": "why-bread-rises-steak-browns-chocolate-snaps", "domain": "food-science",
         "first_video_parts": ["why does bread rise", "why does seared meat taste good",
                               "why does chocolate melt"]}


def row(q: str) -> dict:
    return {"slug": q.replace(" ", "-"), "query": q, "domain": "food-science"}


CANDS = ["why does chocolate taste so good", "why does steak taste better seared",
         "why is my bread not rising", "how is cheese made"]

real = (A.ORDER, A.SPECS, A.SUPERSEDED, BQ.food_rows, A._part_queries, ledger.load)
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    try:
        A.SPECS, A.SUPERSEDED = t / "specs", t / "specs" / "superseded"
        A.SUPERSEDED.mkdir(parents=True)
        A.ORDER = t / "order.json"
        ledger.load = lambda: {"published": [], "queued": []}
        A._part_queries = lambda: set(FIRST["first_video_parts"])
        cands = [row(q) for q in CANDS]
        BQ.food_rows = lambda: [FIRST] + cands

        # 1. the 13 Oct episode as a queue row
        A.ORDER.write_text(json.dumps({"queue": [FIRST] + cands}))
        made = A.made_sets()
        check(A.repeats(["chocolate", "steak", "bread"], made) == FIRST["slug"],
              f"chocolate/steak/bread not seen as the 13 Oct set (made: {made})")
        check(A.repeats(["bread", "chocolate", "steak"], made) == FIRST["slug"],
              "the same trio in another order was not seen as the 13 Oct video")
        check(A.repeats(["dough", "beef", "cocoa"], made) is None,
              "a different trio was refused (no synonym matching - owner, 2 Nov)")
        check(A.repeats(["butter", "rice", "meat"], made) is None,
              "butter/rice/meat refused - one shared food is not a repeat")
        check(A.repeats(["chocolate", "steak", "cheese"], made) is None,
              "a set sharing two foods was refused - only the same set is a repeat")
        got = [r["query"] for r in A.next_parts()]
        want = [CANDS[0], CANDS[1], CANDS[3]]
        check(got == want, f"next_parts() = {got}, not {want} (the 13 Oct set again?)")

        # 2. a spec alone, then an upload alone, with no queue row
        A.ORDER.write_text(json.dumps({"queue": cands}))
        (A.SPECS / "the-spec-only-episode.json").write_text(json.dumps(
            {"domain": "food-science", "segments": [{"subjects": [s]} for s in
                                                   ("bread", "steak", "chocolate")]}))
        check(A.repeats(["steak", "chocolate", "bread"]) is not None,
              "a food episode SPEC was not read")
        for p in A.SPECS.glob("*.json"):
            p.unlink()
        ledger.load = lambda: {"published": [{"slug": FIRST["slug"],
                                              "title": "Bread, Steak, Chocolate: What's Inside?"}]}
        check(A.repeats(["chocolate", "steak", "bread"]) is not None,
              "an UPLOAD (ledger) was not read")
        check(A.repeats(["chocolate", "meat", "bread"]) is None, "the ledger refused a new trio")
    finally:
        A.ORDER, A.SPECS, A.SUPERSEDED, BQ.food_rows, A._part_queries, ledger.load = real

# 3. the real records ----------------------------------------------------------
d = json.loads(A.ORDER.read_text())
eps = [r for r in d.get("queue") or [] if r.get("first_video_parts")]
check(len(eps) >= 2, f"only {len(eps)} food episode row(s) on record")
for e in eps:
    mine = [A.food_of({"query": q, "slug": e["slug"]}) for q in e["first_video_parts"]]
    same = A.repeats(mine, A.made_sets(skip_episode=e["slug"]))
    check(same is None, f"{e['slug']} is the same set of foods as {same}")
nxt = A.next_parts()
if len(nxt) == A.PARTS_PER_EPISODE:
    same = A.repeats([A.food_of(r) for r in nxt])
    check(same is None, f"the next episode {[r['slug'] for r in nxt]} repeats {same}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
