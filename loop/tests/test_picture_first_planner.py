"""Pictures first (hostile review 2026-11-02, finding 2), proven negatively.

On real scripts from all three domains, the planner's output must:
  * put a picture on screen within FIRST_PICTURE_S;
  * never go MAX_GAP_S without one;
  * keep typographic cards to TEXT_MAX_SHARE of the running time;
  * never show a text card that repeats its own narration (a title card may
    show the episode's question);
  * in a "what does X look like" episode, show X in >= LOOK_LIKE_SHARE of shots;
  * leave every beat's narration and the beat count exactly as parse() makes
    them (the audio is indexed by beat).

Negative proof inside the test: the same scripts planned WITHOUT the picture
pass must fail these checks, or the checks prove nothing.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))

import planner as P  # noqa: E402

LOOK_LIKE = {"what-does-a-goblin-shark-look-like": "goblin_shark",
             "what-does-a-greenland-shark-look-like": "greenland_shark",
             "what-does-a-sea-pig-look-like": "sea_pig"}
OTHERS = ["is-giant-isopod-edible", "how-are-microchips-designed",
          "how-does-butter-get-made-from-cream"]


def problems(slug: str, plan: list[dict]) -> list[str]:
    md = open(os.path.join(ROOT, "scripts", f"{slug}.md")).read()
    r = P.picture_report(plan)
    out = []
    if r["first_picture_s"] is None or r["first_picture_s"] > P.FIRST_PICTURE_S:
        out.append(f"{slug}: first picture at {r['first_picture_s']}s")
    if r["max_gap_s"] > P.MAX_GAP_S:
        out.append(f"{slug}: {r['max_gap_s']}s without a picture")
    if r["text_share"] > P.TEXT_MAX_SHARE:
        out.append(f"{slug}: text cards {r['text_share']:.0%} of the running time")
    title = P._title(md).lower()
    for b in plan:
        if b["segment"] != "text_beat":
            continue
        shown = " ".join(b["args"].get("lines") or []).lower().strip()
        if shown and shown in b["narration"].lower() and shown not in title:
            out.append(f"{slug}: a text card repeats its narration ({shown!r})")
            break
    want = LOOK_LIKE.get(slug)
    if want and r["subject_share"].get(want, 0) < P.LOOK_LIKE_SHARE:
        out.append(f"{slug}: shows {want} in {r['subject_share'].get(want, 0):.0%} of shots")
    beats = P.parse(md)
    if [b["text"] for b in beats] != [b["narration"] for b in plan]:
        out.append(f"{slug}: the picture pass changed the beats the audio is indexed by")
    return out


def main() -> int:
    slugs = list(LOOK_LIKE) + OTHERS
    fails = []
    for s in slugs:
        fails += problems(s, P.plan(os.path.join(ROOT, "scripts", f"{s}.md")))
    # negative proof: without the pass the same checks must catch the old plans
    real = P.picture_pass
    P.picture_pass = lambda plan, *a, **k: plan
    try:
        caught = sum(1 for s in slugs
                     if problems(s, P.plan(os.path.join(ROOT, "scripts", f"{s}.md"))))
    finally:
        P.picture_pass = real
    if caught < len(LOOK_LIKE):
        fails.append(f"negative proof: without the picture pass only {caught} of "
                     f"{len(slugs)} plans failed; the checks do not bite")
    if not slugs:
        fails.append("examined nothing")
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: pictures-first planner ({len(slugs)} scripts)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
