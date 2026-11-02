"""The food author picks real foods, uses every unmade food row, and keeps
two food episodes a week moving.

THE INCIDENT (W44, issue #271, 1-2 Nov 2026). Food owns Wednesday and
Saturday in the owner's rotation, yet four food days in the next two weeks
were empty:
  * food_of() took the first word outside a 13-word stoplist, so "what
    happens to meat when you cook it" became "happen" and "what to do when
    chocolate is not melting" became "to": the in-flight episode was
    what-is-inside-happen-to-cheese, its narration named "Happen." and "To."
    as foods and its kits searched stock footage for "happen" and "to";
  * next_parts() excluded the six food rows the nightly batch had scripted
    the wrong way (validated scripts, never shippable as explainers), so 6 of
    the 9 unmade food rows could never air;
  * one episode in flight and one author run a week capped food at ONE
    episode a week for TWO food days.

WHAT THIS PROVES
  1. food_of() names the food for every real food query shape, and never a
     verb, a pronoun or a qualifier.
  2. On the real queue, the batch-scripted rows are offered as parts, and no
     planned episode carries the same food twice.
  3. A batch-scripted part is taken from its script, never re-drafted
     (run() reads scripts/<slug>.md for it).
  4. in_flight() returns the OLDEST authored episode first, not the
     alphabetically first, and up to two may wait (MAX_IN_FLIGHT >= 2).
  5. unmake() puts an unrendered episode's parts back where it stood and
     removes its script and orphan kits; it refuses a rendered one.
Prove-it-fails: restore the old food_of (first non-stopword) -> case 1 fails
on "happen"/"to"; restore the food_batch_made exclusion -> case 2 fails;
restore sorted() in_flight -> case 4 fails.
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

fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


# 1. the food noun ----------------------------------------------------------
CASES = {
    "what happens to meat when you cook it": "meat",
    "what to do when chocolate is not melting": "chocolate",
    "how is cheese made": "cheese",
    "what to do if melted chocolate is too thick": "chocolate",
    "why is my bread flat": "bread",
    "why does dough rise": "dough",
    "why do chili peppers taste hot": "chili",
    "why does coffee taste bitter": "coffee",
    "why does honey never spoil": "honey",
    "why does steak taste better seared": "steak",
    "how does butter get made from cream": "butter",
    "why does rice get sticky": "rice",
    "why does meat need to rest after cooking": "meat",
}
for q, want in CASES.items():
    got = A.food_of({"query": q, "slug": q.replace(" ", "-")})
    check(got == want, f"food_of({q!r}) = {got!r}, not {want!r}")

# 2. every unmade row is a part; one food per episode -------------------------
rows = A.next_parts_all()
check(len(rows) >= A.PARTS_PER_EPISODE,
      f"only {len(rows)} unmade food row(s) offered - this test cannot reach what it governs")
batch = [r["slug"] for r in BQ.food_rows()
         if BQ.food_batch_made(r["slug"]) and not r.get("first_video_parts")]
offered = {r["slug"] for r in rows}
for s in batch:
    check(s in offered, f"{s}: a batch-scripted food row is not offered as a part")
nxt = A.next_parts()
foods = [A.food_of(r) for r in nxt]
check(len(set(foods)) == len(foods), f"the next episode repeats a food: {foods}")

# 3. a batch-scripted part is read, not re-drafted ---------------------------
src = (ROOT / "loop" / "food_author.py").read_text()
run_src = src[src.index("def run("):src.index("def next_after(")]
check("food_batch_made" in run_src and 'scripts" / f"{r[\'slug\']}.md' in run_src,
      "run() does not take a batch-scripted part from its script")

# 4. oldest authored first; two may wait -------------------------------------
check(A.MAX_IN_FLIGHT >= 2, f"MAX_IN_FLIGHT {A.MAX_IN_FLIGHT}: food cannot reach two a week")
real = (A.FOOD_DIR, A.SPECS, A.ORDER, A.KITS)
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    A.FOOD_DIR, A.SPECS, A.ORDER, A.KITS = t / "food", t / "specs", t / "order.json", t / "kits"
    for d in (A.FOOD_DIR, A.SPECS, A.KITS):
        d.mkdir()
    try:
        for slug in ("what-is-inside-apple-x", "what-is-inside-zucchini-y"):
            (A.FOOD_DIR / f"{slug}.md").write_text(
                f"# t\n**Parts:** a, b (segment order: {slug.split('-')[3]}, x)\n{A.LANE_MARK}\n")
        A.ORDER.write_text(json.dumps({"queue": [
            {"slug": "what-is-inside-zucchini-y", "queued": "2026-10-29"},
            {"slug": "what-is-inside-apple-x", "queued": "2026-11-02"}]}))
        check(A.in_flight() == ["what-is-inside-zucchini-y", "what-is-inside-apple-x"],
              f"in_flight() is not oldest-first: {A.in_flight()}")

        # 5. unmake --------------------------------------------------------
        (A.KITS / "apple.json").write_text("{}")
        (A.KITS / "zucchini.json").write_text("{}")
        A.ORDER.write_text(json.dumps({
            "queue": [{"slug": "r0"}, {"slug": "what-is-inside-apple-x"}, {"slug": "r9"}],
            "parts_of_episodes": [{"slug": "p1", "episode": "what-is-inside-apple-x"},
                                  {"slug": "p2", "episode": "what-is-inside-apple-x"},
                                  {"slug": "q1", "episode": "other"}]}))
        A.unmake("what-is-inside-apple-x")
        d = json.loads(A.ORDER.read_text())
        check([r["slug"] for r in d["queue"]] == ["r0", "p1", "p2", "r9"],
              f"unmake did not put the parts back in place: {d['queue']}")
        check([r["slug"] for r in d["parts_of_episodes"]] == ["q1"],
              f"unmake left the episode's parts recorded: {d['parts_of_episodes']}")
        check(not (A.FOOD_DIR / "what-is-inside-apple-x.md").exists(), "unmake kept the script")
        check(not (A.KITS / "apple.json").exists(), "unmake kept an orphan kit")
        check((A.KITS / "zucchini.json").exists(), "unmake removed a kit another script uses")
        (A.SPECS / "what-is-inside-zucchini-y.json").write_text("{}")
        try:
            A.unmake("what-is-inside-zucchini-y")
            check(False, "unmake undid a RENDERED episode (forward only)")
        except SystemExit:
            check(True, "")
    finally:
        A.FOOD_DIR, A.SPECS, A.ORDER, A.KITS = real

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
