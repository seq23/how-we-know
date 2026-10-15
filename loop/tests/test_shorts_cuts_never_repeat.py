"""Two cuts of one episode never look like a repeat (owner build 2026-10-14).

From 12 Oct 2026 the cloud lane published deep sea's rank-2 cuts of episodes
whose rank 1 aired in September, and viewers saw them as repeats for two
reasons: visuals/shorts.py opened EVERY cut on the episode's cold open and
title card (21/21 multi-cut episodes shared their first two beats), and the
title came from the episode question alone ("What is the deepest part of the
ocean?" then "The deepest part of the ocean — and how we know"). Proves, with
no network and no credential:

  1. select_beats: rank 1 still opens on the cold open + title card; rank 2+
     opens on its OWN chapter's first beat(s), never on a cold-open or
     title-card beat, and no two ranks of one episode share an opening beat;
     the receipt says opening "chapter" and where the chapter starts;
  2. titles.title_for_cut: rank 1 is title_for, unchanged; rank 2+ names its
     chapter, keeps every query word (title_problems is empty) and is never
     the rank-1 title or another rank's title - over every real script; a rank
     2+ cut with no chapter is refused, never titled like rank 1;
  3. build_payload: a rank 2+ description links the episode AT its chapter
     (?t=); rank 1 links the top; loop/handoff.py keeps the offset when it
     rewrites the line;
  4. shorts_lane.cut_chapter refuses an old-rule rank 2+ receipt, so such a
     cut cannot be uploaded; visuals/shorts.py --keep-existing re-cuts an
     old-rule rank 2+ cut that is not on the channel and keeps one that is;
  5. REAL RECEIPTS in shorts/ when this machine has them (the Mac): every pair
     of cuts of one episode has disjoint openings and distinct first two
     beats, and every unpublished rank 2+ receipt is a chapter-opening cut.
     A rank 2+ cut already on the channel before this rule (listed in the
     shorts ledger) is the only exemption - it is never re-uploaded.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.append(str(ROOT / "visuals"))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import domains  # noqa: E402
import handoff as H  # noqa: E402
import shorts_lane as SL  # noqa: E402
import titles as T  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")


# ---- 1: the opening -----------------------------------------------------
try:
    import shorts as S                                    # noqa: E402
except Exception as e:                                    # PIL / captions absent
    S = None
    check("1 visuals/shorts.py imports", False, repr(e))

if S is not None:
    def beat(i, heading, text, secs=4.0):
        return {"i": i, "segment": "", "heading": heading, "narration": text,
                "wav": "", "audio_s": secs, "video_start": 0.0, "video_s": secs,
                "frames": int(secs * 30)}

    chap = {
        "Pressure crushes gas, not water": [
            "Pressure squeezes air spaces hard while water barely compresses at all.",
            "Gas-filled lungs and swim bladders collapse long before watery tissue does.",
            "Animals without air spaces feel pressure as a chemistry problem instead."],
        "Proteins need piezolytes to fold": [
            "Deep fish carry piezolytes such as TMAO that keep proteins folded under load.",
            "TMAO concentration rises with depth in every fish family measured so far.",
            "Past roughly eight kilometres the TMAO needed would make cells too salty."],
        "Membranes stay fluid with unsaturated fats": [
            "Cold and pressure both stiffen membranes, and deep animals answer with fats.",
            "Unsaturated fatty acids keep membranes flexible enough for nerves to work.",
            "Labs compare membrane fluidity in shallow and deep relatives directly."],
    }
    beats, i = [], 0
    for h, txt in (("Cold open", "A fish lives where pressure would crush a submarine."),
                   ("Cold open", "It does not have armor and it is not strong."),
                   ("Title card", "How do deep sea creatures survive pressure?")):
        beats.append(beat(i, h, txt)); i += 1
    for h, lines in chap.items():
        for txt in lines:
            beats.append(beat(i, h, txt)); i += 1
    t = 0.0
    for b in beats:
        b["video_start"] = t
        t += b["video_s"]
    answer = ("Deep sea creatures survive pressure with water-rich bodies, "
              "piezolytes like TMAO and unsaturated membrane fats.")
    sels = [S.select_beats(beats, answer, rank=r) for r in range(3)]
    opening_beats = {i for i, b in enumerate(beats)
                     if b["heading"] in ("Cold open", "Title card")}
    check("1 rank 1 opens on cold open + title card (unchanged)",
          set(sels[0]["hook"]) == opening_beats and sels[0].get("opening") == "episode",
          str(sels[0]["hook"]))
    for s in sels[1:]:
        r = s["rank"] + 1
        own = [b["i"] for b in beats if b["heading"] == s["chapter"]]
        check(f"1 rank {r} opens on its own chapter",
              s["hook"] and s["hook"][0] == own[0] and set(s["hook"]) <= set(own)
              and s["beats"][0] == own[0] and s.get("opening") == "chapter",
              f"hook {s['hook']} beats {s['beats']} chapter {own}")
        check(f"1 rank {r} carries no cold-open/title-card beat",
              not (set(s["beats"]) & opening_beats), str(s["beats"]))
        check(f"1 rank {r} receipt says where its chapter starts",
              abs(s.get("chapter_start_s", -9) - beats[own[0]]["video_start"]) < 1e-6,
              str(s.get("chapter_start_s")))
        check(f"1 rank {r} stays inside the budget",
              s["seconds"] <= S.MAX_SECONDS and s["anchor"] in s["beats"], str(s))
    for a in range(3):
        for b in range(a + 1, 3):
            check(f"1 ranks {a + 1} and {b + 1} share no opening beat",
                  not (set(sels[a]["hook"]) & set(sels[b]["hook"]))
                  and sels[a]["beats"][:2] != sels[b]["beats"][:2],
                  f"{sels[a]['hook']} vs {sels[b]['hook']}")

# ---- 2: titles over every real script -------------------------------------
import backfill as B  # noqa: E402

n_scripts = 0
for slug in sorted(domains.by_slug()):
    sp = ROOT / "scripts" / f"{slug}.md"
    if not sp.exists():
        continue
    try:
        q = B.question_for(slug)
    except KeyError:
        continue
    text = sp.read_text(encoding="utf-8")
    ch = re.search(r"^## Chapters\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    heads = []
    for h in re.findall(r"^\s*-\s*\d{1,2}:\d{2}(?::\d{2})?\s+(.+?)\s*$",
                        ch.group(1) if ch else "", re.M):
        if h not in S.HEADING_BLOCK and h not in heads:
            heads.append(h)
    heads = heads[:2]
    if len(heads) < 2:
        continue
    n_scripts += 1
    got = [T.title_for_cut(q, text, 1)] + [
        T.title_for_cut(q, text, r, h) for r, h in ((2, heads[0]), (3, heads[1]))]
    check(f"2 {slug}: rank 1 title unchanged", got[0] == T.title_for(q, text), got[0])
    check(f"2 {slug}: three cuts, three titles", len(set(got)) == 3, str(got))
    for t_ in got:
        check(f"2 {slug}: on-search and clean", not T.title_problems(t_, q, text),
              f"{t_!r}: {T.title_problems(t_, q, text)}")
check("2 examined real scripts", n_scripts >= 10, str(n_scripts))
try:
    T.title_for_cut("what is the midnight zone", "", 2, None)
    check("2 rank 2 with no chapter is refused", False, "returned a title")
except ValueError:
    check("2 rank 2 with no chapter is refused", True)
check("2 the owner's worked example",
      T.title_for_cut("what is the deepest part of the ocean", "", 2,
                      "What a depth number leaves out")
      == "The deepest part of the ocean: what a depth number leaves out — and how we know")

# ---- 3: the description links the chapter -------------------------------
deep = sorted(s for s, d in domains.by_slug().items() if d == "deep-sea-ocean-science"
              and (ROOT / "scripts" / f"{s}.md").exists())
slug = deep[0]
q = B.question_for(slug)
p1 = SL.build_payload(slug, q, episode_video_id="EPI")
p2 = SL.build_payload(slug, q, episode_video_id="EPI", rank=2,
                      chapter="Pressure acts most dramatically on gas",
                      chapter_start_s=55.9)
d1 = p1["snippet"]["description"].split("\n", 1)[0]
d2 = p2["snippet"]["description"].split("\n", 1)[0]
check("3 rank 1 links the top of the episode",
      d1.startswith(H.LINK_PREFIX + "EPI ") and "?t=" not in d1, d1)
check("3 rank 2 links its chapter", d2.startswith(H.LINK_PREFIX + "EPI?t=55 "), d2)
check("3 rank 2 title is not rank 1's",
      p1["snippet"]["title"] != p2["snippet"]["title"], p2["snippet"]["title"])
check("3 handoff sees the offset as the link",
      H.has_link(p2["snippet"]["description"], "EPI", 55.9)
      and not H.has_link(p1["snippet"]["description"], "EPI", 55.9))
check("3 handoff rewrite keeps the offset",
      H.short_description(p2["snippet"]["description"], "EPI2", q, 55.9)
      .startswith(H.LINK_PREFIX + "EPI2?t=55 "))

# ---- 4: an old-rule cut cannot be uploaded, --keep-existing re-cuts it ----
tmp = Path(tempfile.mkdtemp(prefix="cuts-never-repeat-"))
old = tmp / "x-short2.mp4"
old.write_bytes(b"x")
Path(f"{old}.short.json").write_text(json.dumps(
    {"rank": 1, "hook": [0, 2], "chapter": "Something else", "beats": [0, 2, 9]}))
try:
    SL.cut_chapter(old, 2)
    check("4 old-rule rank 2 receipt refused at upload", False, "accepted")
except ValueError:
    check("4 old-rule rank 2 receipt refused at upload", True)
new = tmp / "y-short3.mp4"
new.write_bytes(b"x")
Path(f"{new}.short.json").write_text(json.dumps(
    {"rank": 2, "opening": "chapter", "chapter": "Bones store energy",
     "chapter_start_s": 148.1}))
check("4 new-rule rank 3 receipt read", SL.cut_chapter(new, 3) == ("Bones store energy", 148.1))
check("4 rank 1 needs no chapter", SL.cut_chapter(tmp / "nothing.mp4", 1) == (None, None))
if S is not None:
    check("4 --keep-existing re-cuts an unpublished old-rule rank 2",
          S.stale_opening(str(old), 1, published=set()) is True)
    check("4 --keep-existing keeps a published old-rule rank 2",
          S.stale_opening(str(old), 1, published={old.name}) is False)
    check("4 --keep-existing keeps a chapter-opening cut",
          S.stale_opening(str(new), 2, published=set()) is False)
    check("4 rank 1 is never stale", S.stale_opening(str(old), 0, published=set()) is False)

# ---- 5: real receipts on this machine -----------------------------------
shorts_dir = ROOT / "shorts"
recs = sorted(shorts_dir.glob("*-short*.mp4.short.json")) if shorts_dir.exists() else []
published = {r.get("file") for r in SL.load_ledger().get("published", []) if r.get("file")}
by_slug: dict[str, list] = {}
for rp in recs:
    rec = json.loads(rp.read_text())
    name = rp.name[: -len(".short.json")]
    by_slug.setdefault(rec.get("slug") or name.split("-short")[0], []).append((name, rec))
real = grandfathered = 0
for slug_, cuts in sorted(by_slug.items()):
    for name, rec in cuts:
        if int(rec.get("rank") or 0) >= 1 and name not in published:
            real += 1
            check(f"5 {name} is a chapter-opening cut",
                  rec.get("opening") == "chapter", f"opening={rec.get('opening')!r}")
    for a in range(len(cuts)):
        for b in range(a + 1, len(cuts)):
            (na, ra), (nb, rb) = cuts[a], cuts[b]
            deeper = na if int(ra.get("rank") or 0) else nb
            if deeper in published and not (ra.get("opening") == "chapter"
                                             or rb.get("opening") == "chapter"):
                grandfathered += 1      # aired before 2026-10-14; never re-uploaded
                continue
            real += 1
            check(f"5 {na} / {nb} open differently",
                  not (set(ra.get("hook") or []) & set(rb.get("hook") or []))
                  and (ra.get("beats") or [])[:2] != (rb.get("beats") or [])[:2],
                  f"hooks {ra.get('hook')} / {rb.get('hook')}")
            check(f"5 {na} / {nb} different chapters",
                  ra.get("chapter") != rb.get("chapter"), str(ra.get("chapter")))
if recs:
    check("5 real receipts examined", real > 0, f"{len(recs)} receipts, 0 cases")

if examined == 0:
    sys.exit("FAIL test_shorts_cuts_never_repeat: examined zero cases")
if fails:
    print("FAIL test_shorts_cuts_never_repeat:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_shorts_cuts_never_repeat: {examined} checks - rank 2+ opens on "
      f"its own chapter, names it, links it; {n_scripts} scripts titled; "
      f"{real} real-receipt case(s) on this machine, {grandfathered} already-aired "
      f"pair(s) exempt")
