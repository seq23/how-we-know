"""The food author lane: the next food episode's script and kits, at $0.

    python loop/food_author.py              # stage "food-author" (loop-food-author.yml)
    python loop/food_author.py --plan       # print the next episode's parts; write nothing

WHY THIS EXISTS (2026-10-25). Food was an owner-approved niche (13 Oct: the
round-2 sample and the first full video approved; one voice, normal pace, a
28-32 minute contract) with NOTHING that made its episodes. The first one was
written, footage-picked and rendered by a session by hand; every food topic
after it (chili, coffee, honey, salt, cheese) sat in the queue with no
episode, and the Wednesday and Saturday rotation slots stayed empty. This is
the authoring half of the scheduled food lane; bin/food-session.sh on the Mac
is the rendering half (footage, voice, render, stitch, shelve). Both are in
loop/lanes.py, and V73 holds each to a runner.

WHAT ONE RUN DOES
  1. Backpressure: an authored food episode that has no episode spec yet is
     still the Mac's to render. One in flight at a time - FOOD_EPISODE_IN_FLIGHT
     (self-resolving: the Mac's next food night clears it).
  2. The next THREE unmade food rows, in publish order, become one episode -
     the owner's series shape, "<Food>, <Food>, <Food>: What's Inside?"
     (docs/CHANNEL-PLAN.md, 13 Oct 2026).
  3. Each part is drafted by loop/author.draft() - the same $0 route
     (her subscription first, then the free OpenRouter list, never paid), the
     same house rules, the same truth/URL/shape validation every script gets -
     with the food-science brief. Its narration becomes one segment:
     "### <Food>: <heading>", opening by SAYING its question. Its Producer POV
     section is dropped: food ships no [HUMAN] beat until her food interview
     (domains.pov_not_required; c10).
  4. The episode's cold open, title card and closing are written from the
     parts' own direct-answer locks. NO figures, no names: every number on
     screen stays inside the part that sourced it.
  5. Length is fitted to the contract (28-32 min at the food voice's measured
     169.5 words a minute): whole sections are dropped from the longest
     segment, never its question, its evidence limit or its closing. Too short
     after drafting = FOOD_SCRIPT_TOO_SHORT, nothing written.
  6. A kit per food (visuals/food_kits.py) and the episode row in
     research/publish_order_food_science.json (`first_video_parts`, so the
     score lane's settle() keeps the parts as chapters, not topics).
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import batch_queue as BQ                                    # noqa: E402

FOOD_DIR = ROOT / "scripts" / "food"
KITS = ROOT / "channel" / "food_kits"
SPECS = ROOT / "channel" / "specs"
ORDER = ROOT / "research" / "publish_order_food_science.json"
PARTS_PER_EPISODE = 3
FOOD_WPM = 169.5                 # the first episode: 4,830 words, 28.5 minutes stitched
MINUTES = (28.0, 32.0)
AIM_MINUTES = 30.5
LANE_MARK = "**Made by:** loop/food_author.py"
KEEP_SECTIONS = ("evidence limit", "closing")
STOPWORDS = {"why", "how", "does", "do", "is", "are", "my", "the", "a", "an", "what", "can"}


# ------------------------------------------------------------- choosing
def in_flight() -> list[str]:
    """Lane-authored food episodes with no episode spec: the Mac's to render."""
    out = []
    for p in sorted(FOOD_DIR.glob("*.md")):
        if LANE_MARK in p.read_text() and not (SPECS / f"{p.stem}.json").exists():
            out.append(p.stem)
    return out


def _part_queries() -> set[str]:
    d = json.loads(ORDER.read_text())
    qs = {q for r in d.get("queue") or [] for q in r.get("first_video_parts") or []}
    return qs | {p.get("query") for p in d.get("parts_of_episodes") or []}


def next_parts() -> list[dict]:
    """The next unmade food rows, best first: not a made episode, not a part
    of one, not one of the six the nightly batch made the wrong way."""
    taken = _part_queries()
    out = []
    for r in BQ.food_rows():
        s = r["slug"]
        if r.get("first_video_parts") or BQ.food_made(s) or BQ.food_batch_made(s):
            continue
        if r.get("query") in taken:
            continue
        out.append(r)
    return out[:PARTS_PER_EPISODE]


def food_of(row: dict) -> str:
    """The food noun a question is about: its first content word, singular."""
    words = [w for w in re.findall(r"[a-z]+", (row.get("query") or "").lower())
             if w not in STOPWORDS]
    w = words[0] if words else row["slug"].split("-")[0]
    return w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def episode_slug(foods: list[str]) -> str:
    return "what-is-inside-" + "-".join(foods)


def episode_title(foods: list[str]) -> str:
    return ", ".join(f.capitalize() for f in foods) + ": What's Inside?"


# ------------------------------------------------------------- converting
def sections(text: str, top: str = "Narration") -> list[tuple[str, str]]:
    """(heading, body) for each ### section under `## <top>`."""
    m = re.search(rf"^## {re.escape(top)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return []
    out = []
    for blk in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
        head, _, body = blk.partition("\n")
        out.append((head.strip(), body.strip()))
    return out


def field(text: str, top: str) -> str:
    m = re.search(rf"^## {re.escape(top)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def _strip_human(body: str) -> str:
    return "\n".join(ln for ln in body.splitlines() if "[HUMAN]" not in ln).strip()


def segment_from_draft(text: str, food: str, question: str) -> list[tuple[str, str]]:
    """A drafted explainer -> one food segment's sections, prefixed "<Food>: ".
    The draft's cold open becomes the segment's opening, which SAYS the
    question first (food_episode.check_episode: <= 16 words, ending '?')."""
    q = question.strip().rstrip("?").strip()
    q = q[0].upper() + q[1:] + "?"
    label = food.capitalize()
    out = []
    for head, body in sections(text):
        h = head.lower()
        if h in ("title card", "producer pov"):
            continue
        body = _strip_human(body)
        if not body:
            continue
        if h == "cold open":
            out.append((f"{label}: {q}", f"{q}\n\n{body}"))
        else:
            out.append((f"{label}: {head}", body))
    return out


def words(body: str) -> int:
    return len([w for ln in body.splitlines() if not ln.strip().startswith("{{")
                for w in ln.split()])


def fit(segments: list[list[tuple[str, str]]], fixed_words: int) -> list[list[tuple[str, str]]]:
    """Drop whole sections from the longest segment until the episode fits
    AIM_MINUTES; never a segment's opening, evidence limit or closing."""
    aim = AIM_MINUTES * FOOD_WPM
    total = lambda: fixed_words + sum(words(b) for s in segments for _, b in s)  # noqa: E731
    while total() > aim:
        seg = max(segments, key=lambda s: sum(words(b) for _, b in s))
        cands = [i for i, (h, _) in enumerate(seg) if i > 0 and not any(
            h.lower().endswith(k) for k in KEEP_SECTIONS)]
        if not cands:
            break
        # the edit-notes section first, then the shortest that still gets us under
        notes = [i for i in cands if h_is(seg[i][0], "what to notice")]
        over = total() - aim
        pick = notes[0] if notes else min(cands, key=lambda i: (words(seg[i][1]) < over,
                                                              abs(words(seg[i][1]) - over)))
        seg.pop(pick)
    return segments


def h_is(head: str, what: str) -> bool:
    return what in head.lower()


def _locks(drafts: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", field(t, "Direct-answer lock")) for t in drafts]


def _first_sentence(s: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", s.strip())
    return (m.group(1) if m else s).strip()


def episode_open(foods: list[str], questions: list[str], drafts: list[str]) -> str:
    """The cold open, from the parts' own answers - no figure, no name added."""
    labels = [f.capitalize() for f in foods]
    answers = [_first_sentence(x) for x in _locks(drafts)]
    hook = (f"Three ordinary foods, and inside each one is something nobody could see "
            f"until an instrument showed it. Here is the whole video, one food at a time.")
    lines = [hook] + [f"{lab}. {a}" for lab, a in zip(labels, answers) if a]
    tail = (f"None of this was found by tasting. It was found by measuring - by pulling a "
            f"food apart until its parts could be counted. By the end you will know what is "
            f"inside {', '.join(f.lower() for f in labels[:-1])} and {labels[-1].lower()}, "
            f"and how anyone found out. {labels[0]} first.")
    return "\n\n".join(["{{ambient}}\n" + lines[0],
                        "{{ambient}}\n" + " ".join(lines[1:]),
                        "{{ambient}}\n" + tail])


def episode_close(foods: list[str], nxt: str | None) -> str:
    labels = [f.lower() for f in foods]
    s = (f"So that is what is inside {labels[0]}, {labels[1]} and {labels[2]}: not a "
         f"secret recipe, but chemistry you can measure. Every answer in this video came "
         f"from someone who refused to stop at the taste and looked inside instead.")
    if nxt:
        s += f" Next time: {nxt.rstrip('?')}? Stay curious, and stay hungry."
    else:
        s += " Stay curious, and stay hungry."
    return "{{ambient}}\n" + s


def sources_of(text: str) -> list[str]:
    return [ln for ln in field(text, "Sources").splitlines() if ln.strip().startswith("- ")]


def assemble(foods: list[str], rows: list[dict], drafts: list[str], nxt: str | None) -> str:
    qs = [r.get("title") or r["query"] for r in rows]
    open_ = episode_open(foods, qs, drafts)
    title = episode_title(foods)
    close = episode_close(foods, nxt)
    segs = [segment_from_draft(t, f, r.get("title") or r["query"])
            for t, f, r in zip(drafts, foods, rows)]
    fixed = words(open_) + words(close) + len(title.split())
    segs = fit(segs, fixed)
    total = fixed + sum(words(b) for s in segs for _, b in s)
    mins = total / FOOD_WPM
    slug = episode_slug(foods)
    srcs, seen = [], set()
    for t in drafts:
        for ln in sources_of(t):
            if ln not in seen:
                seen.add(ln)
                srcs.append(ln)
    body = [f"# {title}", "",
            "**Status:** AUTHORED BY THE FOOD LANE - format approved by the owner 13 Oct 2026 "
            "(round-2 sample, \"MUCH better\"); rendered and held to the food contract on the Mac",
            "**Domain:** food-science", f"**Episode:** {slug}",
            f"**Parts:** {', '.join(r['slug'] for r in rows)} (segment order: {', '.join(foods)})",
            "**Register:** one voice at normal explainer pace start to finish (voice/registers.json, V54)",
            f"**Word count:** {total}", f"**Estimated narration:** about {mins:.0f} minutes at "
            f"{FOOD_WPM} words a minute (the first episode's stitched rate)", LANE_MARK, "",
            "## YouTube title", "", title, "", "## Direct-answer lock", "",
            " ".join(_first_sentence(x) for x in _locks(drafts)), "", "## Narration", "",
            "### Cold open", "", open_, "", "### Title card", "", title.replace(":", "."), ""]
    for seg in segs:
        for head, b in seg:
            body += [f"### {head}", "", b, ""]
    body += ["### Closing", "", close, "", "## Sources", "", *srcs, ""]
    return "\n".join(body)


def length_problems(script: str) -> list[str]:
    m = re.search(r"^\*\*Word count:\*\* (\d+)", script, re.M)
    n = int(m.group(1)) if m else 0
    lo, hi = (x * FOOD_WPM for x in MINUTES)
    if not lo <= n <= hi:
        return [f"{n} words is {n / FOOD_WPM:.1f} min at {FOOD_WPM} wpm, outside "
                f"{MINUTES[0]:.0f}-{MINUTES[1]:.0f}"]
    return []


# ------------------------------------------------------------- kits
GENERIC_QUERIES = [("{f}", ["subject", "scale"], 3), ("{f} close up", ["subject", "macro"], 3),
                   ("{f} slow motion", ["subject", "pour"], 3), ("{f} macro", ["subject", "macro"], 2),
                   ("{f} kitchen", ["subject", "process"], 2), ("{f} food", ["subject"], 2)]
# Food-specific searches and words. A food not listed still gets the generic
# kit; these only widen what the footage chain can find.
EXTRA = {
    "chili": {"words": ["chili", "chilli", "pepper", "jalapeno", "capsicum"],
              "queries": [("red chili pepper", ["subject", "heat"], 2), ("hot pepper", ["subject", "heat"], 2)],
              "sound": "sizzle"},
    "coffee": {"words": ["coffee", "espresso"],
               "queries": [("coffee beans", ["subject", "roast"], 3), ("coffee pour", ["pour", "liquid"], 2)],
               "sound": "pour"},
    "honey": {"words": ["honey", "honeycomb"],
              "queries": [("honey dripping", ["drip", "liquid", "pour"], 3), ("honeycomb", ["subject", "macro"], 2)],
              "sound": "pour"},
    "salt": {"words": ["salt"], "queries": [("salt crystals", ["subject", "crystal"], 3)], "sound": "pour"},
    "cheese": {"words": ["cheese"], "queries": [("melted cheese", ["melt", "liquid"], 3)], "sound": None},
}
WORD_USES = [("pour", ["pour", "liquid"]), ("drip", ["drip", "liquid"]), ("melt", ["melt", "liquid"]),
             ("crystal", ["crystal", "macro"]), ("molecule", ["macro"]), ("heat", ["heat", "subject"]),
             ("roast", ["roast"]), ("field", ["scale"]), ("farm", ["scale"]), ("inside", ["macro"])]


def build_kit(food: str) -> dict:
    ex = EXTRA.get(food, {})
    q = [{"query": a.format(f=food), "uses": u, "take": t, "sound": ex.get("sound")}
         for a, u, t in GENERIC_QUERIES] + \
        [{"query": a, "uses": u, "take": t, "sound": ex.get("sound")} for a, u, t in ex.get("queries", [])]
    return {
        "_why": "visuals/food_kits.py; written by loop/food_author.py",
        "food": food, "label": food.upper(), "words": ex.get("words") or [food],
        "queries": q, "off": ["cartoon", "drawing", "logo", "advert"],
        "word_uses": [[food, ["subject"]]] + [[w, u] for w, u in WORD_USES],
        "diagram": {"key": f"{food}-cross-macro", "subject": food,
                    "prompt": f"a {food} cut open in cross-section, its inner structure glowing "
                              f"softly, extreme macro, realistic"},
    }


# ------------------------------------------------------------- the row
def register_episode(slug: str, title: str, rows: list[dict]) -> None:
    d = json.loads(ORDER.read_text())
    queue = d.get("queue") or []
    if any(r.get("slug") == slug for r in queue):
        return
    part_slugs = {r["slug"] for r in rows}
    first = min(i for i, r in enumerate(queue) if r.get("slug") in part_slugs)
    ep = {"slug": slug, "domain": "food-science", "title": title,
          "query": title.rstrip("?").lower(),
          "gate": {"verdict": "passed", "failed": [],
                   "reason": "an episode of three gated food rows, each of which passed: "
                             + "; ".join(f"{r['slug']}: {(r.get('gate') or {}).get('reason', '')}"
                                         for r in rows)},
          "first_video_parts": [r["query"] for r in rows],
          "made_by": "loop/food_author.py + bin/food-session.sh (scripts/food/, rendered as "
                     "pieces and stitched)",
          "queued": date.today().isoformat()}
    keep = [r for r in queue if r.get("slug") not in part_slugs]
    keep.insert(min(first, len(keep)), ep)
    parts = list(d.get("parts_of_episodes") or [])
    parts += [{k: v for k, v in r.items() if not k.startswith("_")} | {"episode": slug}
              for r in rows]
    d["queue"], d["parts_of_episodes"], d["queue_length"] = keep, parts, len(keep)
    ORDER.write_text(json.dumps(d, indent=2) + "\n")


# ------------------------------------------------------------- the stage
def run(plan_only: bool = False) -> int:
    from common import Stage, week_id                       # noqa: PLC0415
    import author                                           # noqa: PLC0415
    import pov_match                                        # noqa: PLC0415
    if plan_only:
        rows = next_parts()
        foods = [food_of(r) for r in rows]
        print(f"in flight: {in_flight() or 'none'}")
        print(f"next food episode: {episode_slug(foods)}  ({episode_title(foods)})")
        for f, r in zip(foods, rows):
            print(f"  {f:<8} {r['slug']}")
        return 0
    with Stage("food-author", week_id(),
               zero_work_hint="loop/food_author.py writes one food episode a run") as st:
        busy = in_flight()
        if busy:
            st.named_stop("FOOD_EPISODE_IN_FLIGHT",
                          f"{busy[0]} is authored and waiting for the Mac's food nights "
                          f"(bin/food-session.sh); one food episode is in flight at a time",
                          unblock="Nothing to do: the food night that stitches it writes its "
                                  "spec, and the next run here authors the next episode.")
        rows = next_parts()
        if len(rows) < PARTS_PER_EPISODE:
            st.named_stop("FOOD_QUEUE_SHORT",
                          f"{len(rows)} unmade food topic(s); an episode takes {PARTS_PER_EPISODE}",
                          unblock="The Saturday score lane refills research/"
                                  "publish_order_food_science.json; the next run uses it.")
        foods = [food_of(r) for r in rows]
        slug = episode_slug(foods)
        print(f"next food episode: {slug}")
        for f, r in zip(foods, rows):
            print(f"  {f:<8} {r['slug']}")
        deadline = time.monotonic() + 150 * 60
        drafts = []
        for r in rows:
            try:
                pov = pov_match.select(r["slug"], r["query"], [], domain="food-science")
            except Exception:                               # noqa: BLE001
                pov = {"pov_id": "none", "line": "", "tag": "", "tier": ""}
            try:
                out = author.draft(r["query"], r["slug"], pov, domain="food-science",
                                   deadline=deadline)
            except author.AuthorStop as e:
                st.named_stop(e.code, f"{r['slug']}: {e.message}", unblock=e.unblock)
            drafts.append((ROOT / out["path"]).read_text())
            st.work(f"drafted {r['slug']} ({out.get('model')}, attempt {out.get('attempt')})")
        later = next_after(rows)
        script = assemble(foods, rows, drafts, later)
        bad = length_problems(script)
        if bad:
            st.named_stop("FOOD_SCRIPT_TOO_SHORT", f"{slug}: {bad[0]}",
                          unblock="The parts drafted short; the next run drafts them again.")
        FOOD_DIR.mkdir(parents=True, exist_ok=True)
        (FOOD_DIR / f"{slug}.md").write_text(script)
        st.work(f"wrote scripts/food/{slug}.md")
        KITS.mkdir(parents=True, exist_ok=True)
        for f in foods:
            kp = KITS / f"{f}.json"
            if not kp.exists():
                kp.write_text(json.dumps(build_kit(f), indent=1) + "\n")
                st.work(f"wrote channel/food_kits/{f}.json")
        register_episode(slug, episode_title(foods), rows)
        st.work(f"queued {slug} in research/publish_order_food_science.json")
    return 0


def next_after(rows: list[dict]) -> str | None:
    taken = {r["slug"] for r in rows}
    for r in next_parts_all():
        if r["slug"] not in taken:
            return r.get("title") or r.get("query")
    return None


def next_parts_all() -> list[dict]:
    keep = PARTS_PER_EPISODE
    try:
        globals()["PARTS_PER_EPISODE"] = 99
        return next_parts()
    finally:
        globals()["PARTS_PER_EPISODE"] = keep


if __name__ == "__main__":
    raise SystemExit(run(plan_only="--plan" in sys.argv))
