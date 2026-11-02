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
     slug gets a DRAWN CARD (visuals/drawn_card.py, owner ruling 2 Nov 2026)
     and is released: never held for a person.

State: loop/state/subject_photo.json {slug: {tries, last_tried, status, ...}}.
Guarded by loop/tests/test_subject_photo.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
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
            "title_words": terms,
            # only weak words ("deep sea creatures"): the title must carry all of them
            "title_min_words": (len(terms) if all(t in WEAK for t in terms)
                                else min(2, len(terms))),
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


# ---------------------------------------------------------- free libraries
# OWNER RULING, 2 Nov 2026: thumbnail and Short-opening STILLS may also come
# from Pexels, Pixabay and Mixkit - the 13 Oct food-footage widening (commercial
# reuse, no attribution required, licence wording stored and re-checked, still
# credited), for every domain. The licence check is research/food_footage.py's
# own (record_problems against its adapter: Pixabay Content License, Pexels
# License, Mixkit Free License); anything else, CC-BY included, is refused.
#   pixabay  image API, the key the footage chain already uses
#            (~/.config/how-we-know/pixabay.key or $PIXABAY_API_KEY); every
#            hit re-checked BY ID before download (type photo, not AI).
#   pexels   needs a key ($PEXELS_API_KEY / pexels.key); none exists and Pexels
#            paused new keys (13 Oct) - the adapter reports PEXELS_KEY_MISSING
#            and is skipped. Its site forbids scraping; nothing paid.
#   mixkit   has no still-photo library (video, music, templates): nothing to search.
PIXABAY_LIMIT = 50
# A Pixabay "photo" can still be digital art: a composited monster octopus
# passed as a photo on the first run (2 Nov 2026). Its own tags say so.
NOT_A_REAL_PHOTO = re.compile(
    r"\b(monster|fantasy|mystical|surreal|digital art|3d|render(?:ing)?|composite|"
    r"manipulation|photoshop|illustration|artwork|concept art|sci-?fi|dragon|"
    r"creepy art|horror)\b")


def _used_elsewhere(key: str) -> set[str]:
    """Source ids other episodes already show: one picture, one episode."""
    try:
        man = json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return set()
    return {str(r.get("source_id")) for r in man.get("index") or []
            if r.get("subject") != key and r.get("source_id")}


def _ff():
    import food_footage as F                               # noqa: PLC0415
    return F


def sources_status() -> dict:
    F = _ff()
    return {"pixabay": "enabled" if F.key_for("pixabay") else
            "PIXABAY_KEY_MISSING: no ~/.config/how-we-know/pixabay.key or $PIXABAY_API_KEY",
            "pexels": "enabled" if F.key_for("pexels") else
            "PEXELS_KEY_MISSING: no pexels.key or $PEXELS_API_KEY (Pexels paused new keys)",
            "mixkit": "no still-photo library to search",
            "commons": "enabled"}


def _pixabay(params: str) -> dict:
    F = _ff()
    return json.loads(F._get("https://pixabay.com/api/?image_type=photo&safesearch=true"
                             f"&key={F.key_for('pixabay')}&{params}", gap=1.0))


def _tag_score(tags: str, terms: list[str]) -> int:
    first = [t.strip() for t in (tags or "").lower().split(",")][:4]
    return sum(1 for w in terms if any(re.search(rf"\b{re.escape(w)}", t) for t in first))


def _rank(tags: str, terms: list[str]) -> int:
    """Tag relevance, plus a strong bonus when the FIRST tag is the subject
    itself ("butter", "sperm whale"), not a thing containing it ("butter cream")."""
    first = (tags or "").lower().split(",")[0].strip()
    bonus = 4 if first == terms[0] else 2 if first in {" ".join(terms), " ".join(terms[:2])} else 0
    return _tag_score(tags, terms) + bonus


def pixabay_find(slug: str, sub: dict, skip: set[str]) -> tuple[dict | None, list[str]]:
    """The best Pixabay PHOTO of the subject: (record, whys)."""
    import imagery_materials as M                          # noqa: PLC0415
    F = _ff()
    if not F.key_for("pixabay"):
        return None, [sources_status()["pixabay"]]
    terms, need = sub["title_words"], int(sub.get("title_min_words") or 1)
    whys: list[str] = []
    skip = set(skip) | _used_elsewhere(sub["key"])
    qs = list(dict.fromkeys(sub["queries"][:2] + [terms[0]]))
    pool: dict[str, tuple[str, dict]] = {}
    for q in qs:
        try:
            hits = _pixabay(f"per_page={PIXABAY_LIMIT}&q=" + urllib.parse.quote(q)).get("hits") or []
        except Exception as e:                             # noqa: BLE001
            whys.append(f"pixabay search failed ({str(e)[:80]})")
            continue
        for h in hits:
            pool.setdefault(str(h.get("id")), (q, h))
    ranked = sorted(pool.values(), key=lambda qh: -_rank(qh[1].get("tags", ""), terms))
    for q, h in ranked[:40]:
        if True:
            hid = str(h.get("id"))
            first_tag = (h.get("tags") or "").lower().split(",")[0].strip()
            if hid in skip or (_tag_score(h.get("tags", ""), terms) < need
                               and first_tag != terms[0]):
                continue
            if NOT_A_REAL_PHOTO.search((h.get("tags") or "").lower()):
                whys.append(f"pixabay {hid}: tagged as art, not a real photo")
                continue
            if h.get("type") != "photo" or h.get("isAiGenerated"):
                whys.append(f"pixabay {hid}: {h.get('type')}/AI - not a photo")
                continue
            blob = (h.get("tags") or "").lower()
            if M.BRAND_WORDS.search(blob):
                whys.append(f"pixabay {hid}: brand/logo-heavy tags")
                continue
            if sub.get("context_any") and not any(c in blob for c in sub["context_any"]):
                whys.append(f"pixabay {hid}: its tags never place it in the episode's domain")
                continue
            # RE-CHECK BY ID before download, as the footage chain does
            again = (_pixabay(f"id={int(hid)}").get("hits") or [{}])[0]
            if again.get("type") != "photo" or again.get("isAiGenerated"):
                whys.append(f"pixabay {hid}: re-check says {again.get('type')}/AI")
                continue
            url = again.get("largeImageURL") or ""
            data = F._get(url, binary=True, gap=1.0)
            from io import BytesIO                         # noqa: PLC0415
            from PIL import Image                          # noqa: PLC0415
            with Image.open(BytesIO(data)) as im:
                w, hgt = im.size
            if w < MIN_WIDTH:
                whys.append(f"pixabay {hid}: {w} px wide, under {MIN_WIDTH}")
                continue
            fname = f"auto__{sub['key']}__pixabay-{hid}.jpg"
            path = Path(M.ASSETS) / fname
            path.write_bytes(data)
            bad = pixel_problem(path)
            if bad:
                path.unlink(missing_ok=True)
                whys.append(f"pixabay {hid}: {bad}")
                continue
            a = F.BY_NAME["pixabay"]
            user = (again.get("user") or "Pixabay").upper()
            rec = {"subject": sub["key"], "label": sub["label"],
                   "title": again.get("tags") or "", "depicts": "photograph",
                   "subject_basis": sub["subject_basis"],
                   "credit_line": f"{sub['label']} — PHOTOGRAPH, {user[:40]} / PIXABAY",
                   "treatment": "photo", "source": "pixabay", "source_id": hid,
                   "source_org": again.get("user") or "Pixabay",
                   "licence": a.licence, "licence_url": a.licence_url,
                   "licence_text": a.licence_text, "terms_text": a.terms_text,
                   "matched_query": q, "item_url": again.get("pageURL"),
                   "download_url": url.split("?")[0], "local_file": f"assets/{fname}",
                   "sha256": hashlib.sha256(data).hexdigest(), "width": w, "height": hgt,
                   "fetched_at": _now(),
                   "licence_basis": (f"Pixabay Content License: API re-checked id {hid} "
                                     f"(type photo, not AI) at download")}
            probs = F.record_problems(rec)
            if probs:
                path.unlink(missing_ok=True)
                whys.append(f"pixabay {hid}: {probs[0]}")
                continue
            _pin(rec)
            return rec, whys
    return None, whys or ["pixabay: no photo whose tags name the subject"]


def _pin(rec: dict) -> None:
    """Write one record into the manifest, replacing that subject's record."""
    try:
        man = json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        man = {"domain": "any", "policy": "", "index": []}
    man["index"] = [r for r in man.get("index") or [] if r.get("subject") != rec["subject"]] + [rec]
    man["index"].sort(key=lambda r: r["subject"])
    man["asset_count"] = len(man["index"])
    man["subjects_covered"] = sorted({r["subject"] for r in man["index"]})
    man["generated"] = _now()
    man["policy"] = ("Thumbnail and Short-opening stills: public domain or CC0 (Commons, "
                     "imagery.pd_licence_ok), or Pixabay / Pexels / Mixkit under their free "
                     "licences (owner ruling 2 Nov 2026), checked by research/food_footage."
                     "record_problems with the licence wording stored under licences/. "
                     "Anything else, CC-BY included, is refused.")
    man.setdefault("rights_fields_required", ["depicts", "subject_basis", "credit_line",
                                              "item_url", "licence", "sha256"])
    MANIFEST.write_text(json.dumps(man, indent=2))


def find(slug: str, attempts: int = 3, replace: str | None = None) -> dict:
    """Search, gate and pin one slug: Pixabay first (a plain photo of the
    subject), then Commons PD/CC0. `replace` = the local_file of a weak pick to
    swap out; it is never chosen again. {"pinned": record} or {"pinned": None, "why"}."""
    import imagery_materials as M                          # noqa: PLC0415
    sub = subject_for(slug)
    if sub is None:
        return {"pinned": None, "why": "no subject words in its question or slug"}
    old = None
    if replace:
        try:
            old = next(r for r in json.loads(MANIFEST.read_text())["index"]
                       if r.get("local_file") == replace)
        except (OSError, ValueError, StopIteration):
            old = None
    skip = {str(old.get("source_id"))} if old and old.get("source_id") else set()
    rec, whys = pixabay_find(slug, sub, skip)
    if rec:
        if old and old.get("local_file") != rec["local_file"]:
            (Path(M.ASSETS).parent / old["local_file"]).unlink(missing_ok=True)
        return {"pinned": rec, "queries": sub["queries"], "replaced": replace}
    sub["skip_titles"] = (["File:" + old["title"]] if old and not old.get("source") else [])
    try:                                    # one picture, one episode (Commons too)
        sub["skip_titles"] += ["File:" + r["title"] for r in json.loads(MANIFEST.read_text())["index"]
                               if r.get("subject") != sub["key"] and not r.get("source")]
    except (OSError, ValueError):
        pass
    for _ in range(attempts):
        man = M.harvest(only=[sub["key"]], subjects=[sub], manifest=str(MANIFEST),
                        domain="any", prefix="auto", unillustratable={})
        rec = next((r for r in man.get("index") or [] if r["subject"] == sub["key"]), None)
        if not (rec and rec.get("local_file") and rec.get("sha256")) or (
                old and rec.get("local_file") == old.get("local_file")):
            whys += [r.get("reason") for r in man.get("rejected") or []
                     if r.get("subject") == sub["key"] and r.get("reason")]
            if old:
                whys.append("no better photo found; the current pick is kept")
            break
        path = Path(M.ASSETS).parent / rec["local_file"]
        bad = pixel_problem(path) if path.exists() else "downloaded file missing"
        if not bad:
            if old:
                (Path(M.ASSETS).parent / old["local_file"]).unlink(missing_ok=True)
            return {"pinned": rec, "queries": sub["queries"], "replaced": replace}
        whys.append(f"{rec['title']}: {bad}")
        sub["skip_titles"].append("File:" + rec["title"])
        _drop(rec)
    return {"pinned": None, "queries": sub["queries"],
            "why": "; ".join(whys)[-300:] or "no candidate"}


def pin_drawn_card(slug: str) -> dict:
    """Draw the episode's card (visuals/drawn_card.py) and pin it as its picture."""
    import imagery_materials as M                          # noqa: PLC0415
    import drawn_card as DC                                # noqa: PLC0415
    key = f"auto-{slug}"
    fname = f"auto__{key}__drawn-card.jpg"
    terms = subject_terms(slug) or re.split(r"[-\s]+", re.sub(r"^\d+-", "", slug))
    rec = DC.write(slug, terms, str(Path(M.ASSETS) / fname))
    rec.update(subject=key, label=" ".join(terms[:3]).upper(), local_file=f"assets/{fname}",
               title=f"Drawn card ({rec['motif']})", fetched_at=_now(),
               subject_basis=(f"No licence-passing photo of {slug}'s subject in "
                              f"{MAX_TRIES} nightly searches; a plain drawn schematic "
                              f"(owner ruling 2 Nov 2026)."))
    _pin(rec)
    return rec


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


def run(slugs: list[str] | None = None, limit: int = PER_RUN, today: str | None = None,
        force: bool = False) -> int:
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
               and (force or (state.get(s) or {}).get("last_tried") != today)][:limit]
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
        # OWNER RULING, 2 Nov 2026 ("Yes, drawn card"): after MAX_TRIES nights
        # with no licence-passing photo, the episode gets a DRAWN CARD
        # (visuals/drawn_card.py) and is released - never held for a person.
        for s in sorted(set(exhausted)):
            rec = pin_drawn_card(s)
            row = state.setdefault(s, {"tries": MAX_TRIES})
            row.update(status="drawn card", file=rec["local_file"],
                       licence=rec["licence"], found_at=_now())
            st.work(f"{s}: no photo in {MAX_TRIES} nights - drawn card "
                    f"({rec['motif']}) pinned - {release(s)}")
        save_state(state)
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
    r.add_argument("--force", action="store_true",
                   help="search again today (a new source was added)")
    sub.add_parser("held")
    rp = sub.add_parser("replace", help="swap a weak pick for a plainer photo")
    rp.add_argument("slugs", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "held":
        h = held()
        for s in h:
            print(s)
        print(f"{len(h)} held")
        return 0
    if a.cmd == "replace":
        return replace_picks(a.slugs)
    return run(a.slugs, a.limit, force=a.force)


def replace_picks(slugs: list[str]) -> int:
    """Swap each slug's pinned photo for a plainer one when one exists."""
    from common import Stage, week_id                      # noqa: PLC0415
    with Stage("subject-photo-replace", week_id(),
               zero_work_hint="No better photo was found for any of these.") as st:
        try:
            idx = {r["subject"]: r for r in json.loads(MANIFEST.read_text())["index"]}
        except (OSError, ValueError):
            idx = {}
        for s in slugs:
            cur = idx.get(f"auto-{s}")
            r = find(s, replace=cur["local_file"] if cur else None)
            if r["pinned"] and (not cur or r["pinned"]["local_file"] != cur["local_file"]):
                st.work(f"{s}: replaced {(cur or {}).get('title', 'nothing')!r} with "
                        f"{r['pinned']['title'][:80]!r} ({r['pinned']['licence']}) - {release(s)}")
            else:
                st.note(f"{s}: kept {(cur or {}).get('title')!r}: {(r.get('why') or '')[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
