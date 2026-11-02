"""A held episode finds its own subject photo (research/subject_photo.py).

Coordinator, 2 Nov 2026: THUMB_NO_SUBJECT_PHOTO / SHORT_NO_SUBJECT_PHOTO must not
wait for a person to pin a Commons file. Proves, with Commons FAKED (no network,
LOOP_DRY_RUN=1, every path a scratch copy):

  1. a held slug with a fake CC0 hit (Commons reports Copyrighted=True for CC0)
     is PINNED - licence wording, item URL, sha256 and credit line recorded the
     way the hand harvest records them - and RELEASED: question_card.photos()
     now finds it and held() no longer lists the slug;
  2. a CC-BY hit is REFUSED (not pinned, still held);
  3. a CC0 logo, a CC0 file under 1000 px, and a CC0 file whose title names
     none of the subject words are refused;
  4. run(): an episode with candidates gets the top one pinned the same night
     (never held); with zero candidates the drawn card is pinned the same
     night (owner, 2 Nov 2026). Formerly: a slug still without a photo after MAX_TRIES nights escalated as
     a DRAWN CARD (visuals/drawn_card.py) and the episode is released; before that
     the night ends SUBJECT_PHOTO_SEARCHING
     (self_resolving), and the two NO_SUBJECT_PHOTO stops are self_resolving
     with the same cap in loop/stop_policy.json.

NEGATIVE PROOF (by hand, 2026-11-02): making research/imagery.pd_licence_ok
accept "CC BY 4.0" makes check 2 fail (the CC-BY hit is pinned); restored, green.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "loop"))
os.environ["LOOP_DRY_RUN"] = "1"

import common                                                   # noqa: E402
import domains                                                  # noqa: E402,F401  loop's, first
import shorts_lane                                              # noqa: E402,F401
import imagery_materials as M                                   # noqa: E402
import question_card as QC                                      # noqa: E402
import subject_photo as SP                                      # noqa: E402
import thumb_contract as TC                                     # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


SLUG = "how-deep-can-a-sperm-whale-go"
TMP = Path(tempfile.mkdtemp(prefix="subject-photo-"))
(TMP / "assets").mkdir()
(TMP / "stops").mkdir()
M.ASSETS = str(TMP / "assets")
TC.IMAGERY = str(TMP)
SP.MANIFEST = TMP / "subject_photos.json"
SP.STATE = TMP / "subject_photo.json"
common.STOPS = TMP / "stops"
M.MIN_INTERVAL = 0

import food_footage as FF                                       # noqa: E402
FF.key_for = lambda name: None          # Commons cases first: no free-library key
check(SLUG in SP.held([SLUG]), "0 the fixture slug starts held (no PD/CC0 photo)")

HITS: dict[str, dict] = {}


def hit(title, short, copyrighted, width=2400, desc="A sperm whale at the surface."):
    HITS[title] = {"url": f"https://upload.example/{len(HITS)}.jpg", "mime": "image/jpeg",
                   "width": width, "height": 1600,
                   "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                   "extmetadata": {"LicenseShortName": {"value": short},
                                   "Copyrighted": {"value": copyrighted},
                                   "Artist": {"value": "A Photographer"},
                                   "ImageDescription": {"value": desc}}}


import io                                                       # noqa: E402
import numpy as _np                                             # noqa: E402
from PIL import Image as _Image                                 # noqa: E402
PAPER_URLS: set[str] = set()


def _jpeg(paper: bool, seed: int) -> bytes:
    rng = _np.random.default_rng(seed)
    a = (_np.full((300, 400, 3), 245) if paper else rng.integers(20, 200, (300, 400, 3)))
    if paper:
        a[100:140, 50:350] = 30                                  # a line of print
    b = io.BytesIO()
    _Image.fromarray(a.astype("uint8")).save(b, "JPEG")
    return b.getvalue()


def fake_polite(url, binary=False, tries=6):
    if binary:
        return _jpeg(url in PAPER_URLS, len(url))
    import urllib.parse as U
    title = U.unquote(url.split("titles=", 1)[1])
    return json.dumps({"query": {"pages": {"1": {"imageinfo": [HITS[title]]}}}})


M._polite = fake_polite


def search_returns(*titles):
    M._search = lambda phrase, limit=6: list(titles)


# 2 - CC-BY refused
hit("File:Sperm whale breaching (cc by).jpg", "CC BY 4.0", "True")
search_returns("File:Sperm whale breaching (cc by).jpg")
r = SP.find(SLUG)
check(r["pinned"] is None and "copyrighted" in (r.get("why") or ""),
      f"2 a CC-BY hit is refused: {r}")
check(SLUG in SP.held([SLUG]), "2 the slug is still held after a CC-BY hit")

# 3 - logo, small, off-subject refused
hit("File:Sperm whale logo.png", "CC0", "True")
hit("File:Sperm whale small.jpg", "CC0", "True", width=640)
hit("File:Harbour at dawn.jpg", "CC0", "True")
search_returns("File:Sperm whale logo.png", "File:Sperm whale small.jpg", "File:Harbour at dawn.jpg")
r = SP.find(SLUG)
check(r["pinned"] is None, f"3 a logo, a small file and an off-subject file are refused: {r}")

# 3b - a CC0 page/plate (mostly paper) is refused on its pixels; the next hit wins
hit("File:Sperm whale plate 1694.jpg", "CC0", "True")
PAPER_URLS.add(HITS["File:Sperm whale plate 1694.jpg"]["url"])
hit("File:Sperm whale surfacing.jpg", "CC0", "True")
search_returns("File:Sperm whale plate 1694.jpg", "File:Sperm whale surfacing.jpg")
r = SP.find(SLUG)
check((r["pinned"] or {}).get("title") == "Sperm whale surfacing.jpg"
      and not any("plate" in x.get("title", "") for x in
                  json.loads(SP.MANIFEST.read_text())["index"]),
      f"3b a printed page is refused and the next photo pinned: {(r['pinned'] or {}).get('title')}")
check(not list((TMP / "assets").glob("*plate-1694*")), "3b the refused page is removed from disk")
SP.MANIFEST.unlink()
for f_ in (TMP / "assets").glob("*"):
    f_.unlink()

# 1 - CC0 pinned and released
hit("File:Sperm whale diving.jpg", "CC0", "True")
search_returns("File:Sperm whale diving.jpg")
r = SP.find(SLUG)
rec = r["pinned"] or {}
check(bool(rec) and rec.get("licence") == "CC0" and rec.get("sha256")
      and rec.get("item_url", "").endswith("Sperm whale diving.jpg")
      and "(CC0)" in rec.get("credit_line", ""), f"1 a CC0 hit is pinned with its rights record: {rec}")
check(bool(QC.photos(SLUG)) and QC.photos(SLUG)[0]["manifest"] == "subject_photos.json",
      "1 question_card.photos now finds it")
check(SLUG not in SP.held([SLUG]), "1 the slug is released (no longer held)")

# 5 - FREE LIBRARIES (owner ruling 2 Nov 2026): a Pixabay PHOTO is pinned with
# the footage chain's rights fields and its licence wording; an AI or video
# hit is refused; question_card.licence_problems refuses CC-BY and a
# free-library record without its committed wording.
SP.MANIFEST.unlink()
for f_ in (TMP / "assets").glob("*"):
    f_.unlink()
FF.key_for = lambda name: "fixture-key" if name == "pixabay" else None
PIX = {"101": {"id": 101, "type": "photo", "isAiGenerated": True, "tags": "sperm whale, ocean",
               "user": "ai", "pageURL": "https://pixabay.com/photos/101/",
               "largeImageURL": "https://cdn.pixabay.example/101_1280.jpg"},
       "102": {"id": 102, "type": "photo", "isAiGenerated": False,
               "tags": "sperm whale, whale, ocean, sea", "user": "diver",
               "pageURL": "https://pixabay.com/photos/sperm-whale-102/",
               "largeImageURL": "https://cdn.pixabay.example/102_1280.jpg"}}


def fake_pixabay(params):
    if params.startswith("id="):
        return {"hits": [PIX[params.split("=", 1)[1]]]}
    return {"hits": list(PIX.values())}


def _wide_jpeg(seed):
    rng = _np.random.default_rng(seed)
    b = io.BytesIO()
    _Image.fromarray(rng.integers(20, 200, (800, 1280, 3)).astype("uint8")).save(b, "JPEG")
    return b.getvalue()


SP._pixabay = fake_pixabay
FF._get = lambda url, binary=False, gap=1.0, host="", headers=None: _wide_jpeg(len(url))
r = SP.find(SLUG)
rec = r["pinned"] or {}
check(rec.get("source") == "pixabay" and rec.get("source_id") == "102"
      and rec.get("licence") == "Pixabay Content License"
      and rec.get("licence_text") == "licences/pixabay-content-license-summary.txt"
      and "PIXABAY" in rec.get("credit_line", "") and not FF.record_problems(rec),
      f"5 a Pixabay photo is pinned with its licence wording (the AI hit refused): {rec}")
check(not QC.licence_problems(rec), f"5 the free-library record passes the one gate: "
                                    f"{QC.licence_problems(rec)}")
check(bool(QC.photos(SLUG)) and SLUG not in SP.held([SLUG]), "5 and releases the slug")
check(bool(QC.licence_problems({"subject": "x", "licence": "CC BY 4.0"})),
      "5 NEGATIVE: a CC-BY record is refused by the one gate")
check(bool(QC.licence_problems(dict(rec, licence_text=None))),
      "5 NEGATIVE: a free-library record without its licence wording is refused")
check(bool(QC.licence_problems(dict(rec, licence="Pexels License"))),
      "5 NEGATIVE: a Pixabay record claiming another library's licence is refused")
FF.key_for = lambda name: None
check("PEXELS_KEY_MISSING" in SP.sources_status()["pexels"],
      "5 Pexels without a key is a named, skipped source - never paid")
SP.MANIFEST.unlink()

# 4 - OWNER RULING 2 Nov 2026: "it's best to pick one and i ask to change it
# than wait". An episode WITH candidates is never held: the top-ranked photo is
# pinned the same night. One with ZERO candidates gets the drawn card the same
# night. No second night, no picker.
OTHER = "how-deep-can-whales-dive"
SP.save_state({})


def run_code(slugs, today):
    try:
        SP.run(slugs, limit=5, today=today)
        return "OK"
    except SystemExit:
        doc = json.loads((Path(common._stops_dir())                       # noqa: SLF001
                          / f"{common.week_id()}-subject-photo.json").read_text())
        return doc.get("code") or doc.get("stop", {}).get("code") or json.dumps(doc)[:120]


def pinned_of(slug):
    if not SP.MANIFEST.exists():
        return {}
    return next((r for r in json.loads(SP.MANIFEST.read_text())["index"]
                 if r["subject"] == f"auto-{slug}"), {})


hit("File:Humpback whales diving.jpg", "CC0", "True", desc="A humpback whale dives at sea.")
search_returns("File:Humpback whales diving.jpg")
check(OTHER in SP.held([OTHER]), f"4 {OTHER} starts held")
got = run_code([OTHER], "2026-11-02")
p1 = pinned_of(OTHER)
check(got == "OK" and p1.get("title") == "Humpback whales diving.jpg"
      and OTHER not in SP.held([OTHER]),
      f"4 with a candidate, the top photo is pinned the same night, never held: {got} {p1.get('title')}")
SP.MANIFEST.unlink()
for f_ in (TMP / "assets").glob("*"):
    f_.unlink()
search_returns()
SP.save_state({})
check(OTHER in SP.held([OTHER]), f"4 {OTHER} is held again with no photo")
got = run_code([OTHER], "2026-11-03")
drawn = pinned_of(OTHER)
check(got == "OK" and drawn.get("source") == "drawn card"
      and (TMP / drawn.get("local_file", "x")).exists() and not QC.licence_problems(drawn),
      f"4 with ZERO candidates the drawn card is pinned the SAME night: {got} {drawn.get('title')}")
check(OTHER not in SP.held([OTHER]) and SP.load_state()[OTHER]["status"] == "drawn card"
      and SP.load_state()[OTHER]["chosen_by"] == "auto",
      "4 and the episode is released, recorded as an auto-pick")
check(bool(QC.licence_problems(dict(drawn, licence="CC BY 4.0"))),
      "4 NEGATIVE: a drawn card without its own-work licence is refused")
SP.MANIFEST.unlink()
pol = json.loads((ROOT / "loop" / "stop_policy.json").read_text())
for code in ("THUMB_NO_SUBJECT_PHOTO", "SHORT_NO_SUBJECT_PHOTO"):
    check(pol["self_resolving"].get(code, {}).get("max_consecutive") == 2,
          f"4 {code} clears the next night (capped at 2)")
check("SUBJECT_PHOTO_SEARCHING" not in json.dumps(pol)
      and "SUBJECT_PHOTO_SEARCHING" not in (ROOT / "research" / "subject_photo.py").read_text(),
      "4 no episode waits a night searching")
check("SUBJECT_PHOTO_EXHAUSTED" not in json.dumps(pol)
      and "SUBJECT_PHOTO_EXHAUSTED" not in (ROOT / "research" / "subject_photo.py").read_text(),
      "4 no stop routes an exhausted episode to a person any more")
check("research/subject_photo.py run" in (ROOT / "bin" / "batch-session.sh").read_text(),
      "4 the nightly batch runs the finder")

print(f"\n{examined} checks, {len(fails)} failed")
if not examined:
    sys.exit("FAIL: examined nothing")
sys.exit(1 if fails else 0)
