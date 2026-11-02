"""The automatic subject-photo finder: a held episode clears itself.

    python research/subject_photo.py run [--limit 12] [--slugs a b]   # THE MAC, nightly
    python research/subject_photo.py held                             # list what is held

WHY (coordinator, 2 Nov 2026). The one-question rule (visuals/question_card.py)
needs a public-domain or CC0 PHOTO of each video's subject for its thumbnail
and its Short's opening second. With none, the episode stops by name
(THUMB_NO_SUBJECT_PHOTO / SHORT_NO_SUBJECT_PHOTO) - and the only way out was a
person pinning a Commons file in research/imagery_*.py, which is exactly how
the rice and Damascus photos for the mock-up were found. A stop that waits on a
person breaks the repo's first rule, so this does that search itself, every
night, for every held episode:

  1. HELD = every episode with a script that still needs a picture (its
     long-form is not uploaded, or fewer of its Shorts are published than it
     may publish - shorts_lane.cuts_for) and that has no PD/CC0 photo
     (question_card.photos).
  2. SEARCH Wikimedia Commons with the episode's own subject words
     (longform_title.subject_words of its question, then its slug), most
     specific phrase first - through the SAME gate the hand harvest uses
     (research/imagery_materials.harvest): the licence read live from the item
     page (imagery.pd_licence_ok: PD or CC0 only), the copyright-assertion
     screen, a brand/logo/packaging screen, a photo or PNG at >= MIN_WIDTH px,
     and the file title must name a subject word (whole word). The record keeps
     the licence wording, item URL, sha256 and the on-screen credit line
     exactly as the hand harvest does, in channel/imagery/subject_photos.json.
  3. PIN the first passing photo (subject key "auto-<slug>"), which
     thumb_contract.candidates reads, and RELEASE the episode: the same run
     builds its thumbnail if it is rendered (visuals/thumbs_for.py), and the
     batch's shelve step right after re-cuts its Shorts with the opener.
  4. A slug that finds nothing is retried on the next night, up to MAX_TRIES
     nights; the two NO_SUBJECT_PHOTO stops stay self_resolving meanwhile
     (loop/stop_policy.json, capped at the same count). After MAX_TRIES the
     slug is SUBJECT_PHOTO_EXHAUSTED (needs_human): the search really found
     nothing free, which is a defect in coverage someone must see.

State: loop/state/subject_photo.json {slug: {tries, last_tried, status, ...}}.
Guarded by loop/tests/test_subject_photo.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "loop"))     # loop/domains.py, not visuals/domains.py

MANIFEST = ROOT / "channel" / "imagery" / "subject_photos.json"
STATE = ROOT / "loop" / "state" / "subject_photo.json"
MAX_TRIES = 5            # nights; matches stop_policy max_consecutive for the two stops
MIN_WIDTH = 1000
PER_RUN = 20             # slugs searched per night (Commons is rate-limited)
# Words that name the channel's domain or a quantity, not a subject: "deep"
# alone matches every ocean file on Commons. Dropped while a stronger word remains.
WEAK = {"deep", "sea", "ocean", "many", "some", "most", "creature", "creatures",
        "thing", "things", "something", "actually", "look", "looks", "like",
        "taste", "good", "better", "after", "creepers", "creepy", "weird",
        "scary", "big", "dive", "rising", "old", "know"}
# A word like "challenger" or "creepers" names other things too (a space
# shuttle, a climbing plant): a deep-sea photo's own page must say it is marine.
CONTEXT = {"deep-sea-ocean-science": ["ocean", "sea", "marine", "deep", "noaa",
                                      "underwater", "submarine", "seafloor", "trench",
                                      "abyss", "whale", "fish", "coral", "vent"]}
TITLE_NONE = ["logo", "brand", "label", "packag", "advert", "poster", "wrapper",
              "signage", "storefront", "menu", ".svg", "map", "diagram", "chart",
              "screenshot", "icon", "flag", "coat of arms", "stamp", "coin",
              "drawing", "painting", "illustration", "engraving", "print",
              "woodblock", "woodcut", "ukiyo", "lithograph", "sketch", "cartoon",
              "damage", "tornado"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")


def question_of(slug: str) -> str:
    try:
        import backfill                                    # noqa: PLC0415
        return backfill.question_for(slug)
    except Exception:                                      # noqa: BLE001
        return re.sub(r"^\d+-", "", slug).replace("-", " ")


def subject_terms(slug: str, question: str | None = None) -> list[str]:
    """The episode's subject words, in the question's order, then the slug's."""
    import longform_title as LT                            # noqa: PLC0415
    import titles as T                                     # noqa: PLC0415
    # the episode's ONE question (a compilation's strongest), not its whole query
    q = T.title_for(question or question_of(slug))
    subj = LT.subject_words(q)
    order = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if w in subj]
    for w in ([] if order else re.sub(r"^\d+-", "", slug).split("-")):
        if w in LT.subject_words(w.replace("-", " ")) and w not in order:
            order.append(w)
    terms = [w for w in dict.fromkeys(order) if len(w) >= 3]
    strong = [w for w in terms if w not in WEAK]
    return strong or terms


def queries(terms: list[str]) -> list[str]:
    """Most specific first: all terms, adjacent pairs, then single words."""
    out = []
    if terms:
        out.append(" ".join(terms[:4]))
    out += [f"{a} {b}" for a, b in zip(terms, terms[1:])]
    out += [t for t in terms if len(t) >= 4]
    return list(dict.fromkeys(out))[:6]


def needs_picture(slug: str, led: dict, sled: dict) -> bool:
    import shorts_lane as SL                               # noqa: PLC0415
    up = {r["slug"] for r in led.get("published") or [] if r.get("video_id")
          and not r.get("retired_at")}
    shorts = sum(1 for r in sled.get("published") or []
                 if r.get("slug") == slug and r.get("video_id"))
    return slug not in up or shorts < SL.cuts_for(slug)


def held(slugs: list[str] | None = None) -> list[str]:
    """Episodes that need a picture and have no PD/CC0 photo of their subject."""
    import batch_queue                                     # noqa: PLC0415
    import domains                                         # noqa: PLC0415
    import ledger                                          # noqa: PLC0415
    import question_card as QC                             # noqa: PLC0415
    import shorts_lane as SL                               # noqa: PLC0415
    led, sled = ledger.load(), SL.load_ledger()
    if slugs is None:
        live = set(batch_queue.queued_slugs()) | {
            r["slug"] for r in led.get("published") or [] if r.get("video_id")}
        slugs = sorted(s for s in live if domains.script_of(s) is not None)
    out = []
    for s in slugs:
        if not needs_picture(s, led, sled):
            continue
        try:
            if QC.photos(s):
                continue
        except Exception:                                  # noqa: BLE001
            pass
        out.append(s)
    # rendered on this machine first: those are the ones a stop is holding now
    return sorted(out, key=lambda s: (not (ROOT / "renders" / f"{s}-final.mp4").exists(), s))


def subject_for(slug: str) -> dict | None:
    terms = subject_terms(slug)
    if not terms:
        return None
    label = " ".join(terms[:3]).upper()
    import domains as D                                    # noqa: PLC0415
    ctx = CONTEXT.get(D.domain_of_slug(slug) or "", [])
    return {"key": f"auto-{slug}", "label": label, "queries": queries(terms),
            "context_any": ctx,
            "title_words": terms, "title_min_words": min(2, len(terms)),
            "title_none": TITLE_NONE, "brand_screen": True, "photo_only": True,
            "min_width": MIN_WIDTH, "depicts": "photograph",
            "subject_basis": (f"Found automatically for {slug} by its subject words "
                              f"{terms}: the file title names one of them, the item "
                              f"page licence is PD/CC0 (research/subject_photo.py).")}


PAPER_MAX = 0.5          # share of near-white, unsaturated pixels: a page, not a scene
COLOUR_MIN = 0.05        # ...unless a real share of the picture is in colour (food on a white plate)


def pixel_problem(path: Path) -> str | None:
    """A photograph of a scene, not a printed page: an engraving plate or an
    archive card scan is mostly paper (measured 2 Nov 2026: the Pomet whale
    plate and an archive print card 0.63, the PD photos pinned 0.00-0.42)."""
    import numpy as np                                     # noqa: PLC0415
    from PIL import Image                                  # noqa: PLC0415
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((512, 512))
            a = np.asarray(im).astype(float)
    except Exception as e:                                 # noqa: BLE001
        return f"not a readable image ({e})"
    g, sat = a.mean(2), a.max(2) - a.min(2)
    paper = float(((g > 200) & (sat < 25)).mean())
    colour = float((sat > 40).mean())     # a plate of food has colour; a page has ink
    if paper > PAPER_MAX and colour < COLOUR_MIN:
        return f"mostly paper ({paper:.2f} near-white): a printed page or plate, not a photo"
    return None


def _drop(rec: dict) -> None:
    """Remove a refused pin from the manifest and disk."""
    man = json.loads(MANIFEST.read_text())
    man["index"] = [r for r in man.get("index") or [] if r is not rec
                    and r.get("local_file") != rec.get("local_file")]
    man["asset_count"] = len(man["index"])
    man["subjects_covered"] = sorted({r["subject"] for r in man["index"]})
    MANIFEST.write_text(json.dumps(man, indent=2))
    import imagery_materials as M                          # noqa: PLC0415
    (Path(M.ASSETS).parent / rec["local_file"]).unlink(missing_ok=True)


def find(slug: str, attempts: int = 3) -> dict:
    """Search, gate and pin one slug. {"pinned": record} or {"pinned": None, "why"}."""
    import imagery_materials as M                          # noqa: PLC0415
    sub = subject_for(slug)
    if sub is None:
        return {"pinned": None, "why": "no subject words in its question or slug"}
    sub["skip_titles"] = []
    whys: list[str] = []
    for _ in range(attempts):
        man = M.harvest(only=[sub["key"]], subjects=[sub], manifest=str(MANIFEST),
                        domain="any", prefix="auto", unillustratable={})
        rec = next((r for r in man.get("index") or [] if r["subject"] == sub["key"]), None)
        if not (rec and rec.get("local_file") and rec.get("sha256")):
            whys += [r.get("reason") for r in man.get("rejected") or []
                     if r.get("subject") == sub["key"] and r.get("reason")]
            break
        path = Path(M.ASSETS).parent / rec["local_file"]
        bad = pixel_problem(path) if path.exists() else "downloaded file missing"
        if not bad:
            return {"pinned": rec, "queries": sub["queries"]}
        whys.append(f"{rec['title']}: {bad}")
        sub["skip_titles"].append("File:" + rec["title"])
        _drop(rec)
    return {"pinned": None, "queries": sub["queries"],
            "why": "; ".join(whys)[-300:] or "no candidate"}


def release(slug: str) -> str:
    """Build the thumbnail of a rendered episode now; its Shorts are re-cut by
    the batch's shelve step that follows (shorts_lane.cut_groups)."""
    if not (ROOT / "renders" / f"{slug}-final.mp4").exists():
        return "pinned; built when it renders"
    if (ROOT / "channel" / "thumbnails" / f"{slug}.jpg").exists():
        return "pinned; Shorts re-cut by tonight's shelve step"
    try:
        import thumbs_for                                  # noqa: PLC0415
        thumbs_for.build(slug)
        return "pinned; thumbnail built"
    except Exception as e:                                 # noqa: BLE001
        return f"pinned; thumbnail not built ({str(e)[:120]})"


def run(slugs: list[str] | None = None, limit: int = PER_RUN, today: str | None = None) -> int:
    from common import Stage, week_id                      # noqa: PLC0415
    today = today or date.today().isoformat()
    with Stage("subject-photo", week_id(),
               zero_work_hint="Every episode that needs a picture has a PD/CC0 photo.") as st:
        state = load_state()
        todo = held(slugs)
        if not todo:
            st.named_stop("SUBJECT_PHOTOS_COMPLETE",
                          "no episode is held for want of a subject photo",
                          unblock="Nothing to do.")
        exhausted = [s for s in todo if (state.get(s) or {}).get("tries", 0) >= MAX_TRIES]
        due = [s for s in todo if s not in exhausted
               and (state.get(s) or {}).get("last_tried") != today][:limit]
        for s in due:
            r = find(s)
            row = state.setdefault(s, {"tries": 0})
            row["tries"] = int(row.get("tries", 0)) + 1
            row["last_tried"] = today
            row["queries"] = r.get("queries")
            if r["pinned"]:
                row.update(status="found", file=r["pinned"]["local_file"],
                           licence=r["pinned"].get("licence"),
                           item_url=r["pinned"].get("item_url"), found_at=_now())
                st.work(f"{s}: pinned {r['pinned']['title']!r} "
                        f"({r['pinned'].get('licence')}) - {release(s)}")
            else:
                row.update(status="exhausted" if row["tries"] >= MAX_TRIES else "searching",
                           why=r.get("why"))
                st.note(f"{s}: no PD/CC0 photo yet (try {row['tries']}/{MAX_TRIES}): "
                        f"{(r.get('why') or '')[:160]}")
                if row["tries"] >= MAX_TRIES:
                    exhausted.append(s)
        save_state(state)
        if exhausted:
            st.named_stop(
                "SUBJECT_PHOTO_EXHAUSTED",
                f"{len(exhausted)} episode(s) found no public-domain or CC0 photo of "
                f"their subject in {MAX_TRIES} nightly Commons searches: "
                + ", ".join(sorted(exhausted)),
                held_items=sorted(exhausted),
                unblock="The automatic search found nothing free under these subject "
                        "words (loop/state/subject_photo.json has the queries). Pin a "
                        "Commons file in research/imagery_*.py, or widen subject_terms.")
        if not st.units:
            st.named_stop(
                "SUBJECT_PHOTO_SEARCHING",
                f"{len(todo)} episode(s) held for a subject photo; none found tonight "
                f"({len(due)} searched); retried tomorrow",
                held_items=sorted(todo),
                unblock="Nothing to type: the nightly search retries each one up to "
                        f"{MAX_TRIES} nights.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=PER_RUN)
    r.add_argument("--slugs", nargs="+")
    sub.add_parser("held")
    a = ap.parse_args(argv)
    if a.cmd == "held":
        h = held()
        for s in h:
            print(s)
        print(f"{len(h)} held")
        return 0
    return run(a.slugs, a.limit)


if __name__ == "__main__":
    raise SystemExit(main())
