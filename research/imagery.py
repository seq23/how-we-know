"""Rights-checked imagery harvester: NOAA Ocean Exploration, plus public domain.

Two gates, one manifest. `harvest` walks NOAA Ocean Exploration; `pd_harvest`
(python imagery.py --pd) fetches a hand-chosen set of items whose own item page
asserts public domain or CC0, verified live. Both write channel/imagery/rights.json
and neither may delete the other's records.

Route A of the thumbnail rebuild. The premise of this channel is evidence
discipline, so the rule here is the same one we apply to claims: nothing enters
the set unless the provenance is confirmed at the item page, not inferred from
the domain.

What NOAA actually says (https://oceanexplorer.noaa.gov/about/media-kit/,
checked 2026-08-30):

    "For images and videos posted on this website, we ask that you include the
    credit information included in the caption associated with each image or
    video. If space is limited, please credit NOAA Ocean Exploration
    (preferred) or NOAA. A limited number of images and videos posted on the
    website are copyrighted. If the image caption includes the word
    'copyright', additional permissions are required for use."

That is a per-item rule, so it must be enforced per item. Being on a .gov host
proves nothing: a survey of ~40 deep-sea items found roughly 40% credited to
third parties who are NOT federal — MBARI, Ocean Exploration Trust,
UW/NSF-OOI/WHOI, GFOE, and named individual photographers. Those are outside
17 U.S.C. 105 and are excluded.

So the gate is an allowlist, not a blocklist: the credit line must resolve to
NOAA and nobody else. Anything ambiguous is dropped. An empty set beats a
manifest full of guesses.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "channel", "imagery"))
ASSETS = os.path.join(OUT, "assets")
MANIFEST = os.path.join(OUT, "rights.json")

API = "https://oceanexplorer.noaa.gov/wp-json/wp/v2"
MEDIA_KIT = "https://oceanexplorer.noaa.gov/about/media-kit/"
UA = {"User-Agent": "Mozilla/5.0 (How We Know; thumbnail rights verification)"}

# ---------------------------------------------------------------- rights gate

# The credit must be NOAA and only NOAA. Leading "Image courtesy of" is common
# boilerplate and is stripped before matching. A trailing expedition name is
# fine — that is NOAA's own expedition, not a co-author.
CREDIT_OK = re.compile(
    r"^(?:image|photo|video)?\s*(?:courtesy\s+of\s+)?"
    r"noaa(?:\s+ocean\s+exploration|\s+office\s+of\s+ocean\s+exploration[\w\s]*)?"
    r"\s*[,.:;]?\s*(?P<rest>.*)$",
    re.I,
)

# If any of these survive in the credit after the NOAA prefix, a non-federal
# party has a stake in the work. Drop it. This list is deliberately broad; a
# false negative costs us one image, a false positive costs us a rights claim
# we cannot defend.
#
# NOTE on `courtesy of [a-z]+ [a-z]+`: this clause is for a credit that names a
# person or a body MID-STRING ("..., courtesy of Jane Smith"). It must never be
# allowed to see the LEADING boilerplate, because "Image courtesy of NOAA
# Ocean" matches it and the item is thrown away for saying "courtesy of" in
# front of NOAA's own name. See strip_courtesy() below: the boilerplate that
# CREDIT_OK's comment promises is stripped is now genuinely stripped BEFORE
# this pattern runs. Measured cost of the bug: 32 of 388 NOAA video posts and
# 8 of 63 rejected still candidates.
THIRD_PARTY = re.compile(
    r"(?i)\b("
    r"copyright|\(c\)|&copy;|"
    r"mbari|monterey bay|"
    r"ocean exploration trust|nautilus|"
    r"whoi|woods hole|"
    r"uw/|university|univ\.|college|institute|institution|"
    r"gfoe|global foundation|"
    r"schmidt|oceanx|nekton|"
    r"usgs|boem|onr|nsf|ooi|nasa|"
    r"photographer|courtesy of [a-z]+ [a-z]+|"
    r"llc|inc\.|ltd|foundation|aquarium|museum"
    r")\b"
)

# An expedition name is allowed to follow the NOAA credit, but only if it looks
# like a NOAA expedition label rather than a second organisation. We accept a
# short trailing phrase of words/digits and reject anything with a slash (the
# marker of a joint credit like "UW/NSF-OOI/WHOI").
EXPEDITION_OK = re.compile(r"^[\w\s‘’'&+.:\-]*$")


# The leading "Image courtesy of" / "Video courtesy of" / "Courtesy of"
# boilerplate NOAA puts in front of its own credits. Stripping it is what
# CREDIT_OK's own comment has always claimed to do. Only the LEADING occurrence
# is removed, so a second, mid-string "courtesy of <someone>" still trips
# THIRD_PARTY.
#
# This is the single implementation. research/imagery_video.py imports it
# rather than keeping a second copy.
COURTESY_BOILERPLATE = re.compile(
    r"^\s*(?:videos?|images?|photos?|footage|images\s+and\s+sounds)?"
    r"\s*courtesy\s+of\s+",
    re.I,
)


def strip_courtesy(credit: str | None) -> tuple[str, bool]:
    """Remove the leading 'courtesy of' boilerplate. Returns (credit, stripped).

    Nothing is loosened: the string that comes back still has to name NOAA and
    nobody else. All this does is stop the boilerplate itself being read as a
    third-party credit.
    """
    raw = (credit or "").strip()
    n = COURTESY_BOILERPLATE.sub("", raw).strip()
    return n, n != raw


def _get(url: str, binary: bool = False, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as f:
                return f.read() if binary else f.read().decode("utf-8", "replace")
        except Exception as exc:  # network flake, not a rights problem
            last = exc
            time.sleep(1.5 * (i + 1))
    raise last


def _text(fragment: str) -> str:
    t = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def scrape_credit(item_url: str) -> str | None:
    """Pull the Credit block off the item page. None if there isn't one.

    No credit means no confirmed provenance, which means we do not use it.
    """
    page = _get(item_url)
    m = re.search(r"(?is)>\s*Credit\s*<[^>]*>(.{0,600}?)(?:<h\d|<footer|</section)", page)
    if not m:
        m = re.search(r"(?is)Credit\s*</[^>]+>(.{0,400}?)</div", page)
    if not m:
        return None
    credit = _text(m.group(1))
    return credit or None


def credit_is_noaa_only(credit: str | None) -> tuple[bool, str]:
    """The whole rights decision, in one auditable place.

    The raw credit is what we DISPLAY; only the string handed to the gate is
    normalised, and the reason string always quotes the raw credit so the
    decision stays auditable.
    """
    if not credit:
        return False, "no credit line on item page"
    raw = credit
    gated, stripped = strip_courtesy(credit)
    if THIRD_PARTY.search(gated):
        return False, f"third-party or copyrighted credit: {raw!r}"
    m = CREDIT_OK.match(gated)
    if not m:
        return False, f"credit does not resolve to NOAA alone: {raw!r}"
    rest = m.group("rest").strip().rstrip(".")
    if rest and (not EXPEDITION_OK.match(rest) or "/" in rest):
        return False, f"credit carries a co-author: {raw!r}"
    if stripped:
        return True, ("NOAA-only credit, no copyright notice (after stripping "
                      f"the leading 'courtesy of' boilerplate; raw credit was "
                      f"{raw!r})")
    return True, "NOAA-only credit, no copyright notice"


# ---------------------------------------------------------------- harvesting

def search(term: str, per_page: int = 8) -> list[dict]:
    q = urllib.parse.quote(term)
    url = (f"{API}/multimedia?search={q}&per_page={per_page}"
           f"&_fields=id,link,title,content,featured_media")
    try:
        return json.loads(_get(url))
    except Exception:
        return []


def media_detail(mid: int) -> dict | None:
    try:
        return json.loads(_get(f"{API}/media/{mid}?_fields=id,source_url,media_details,mime_type"))
    except Exception:
        return None


def harvest(terms: dict[str, list[str]], per_term: int = 8, want: int = 3) -> list[dict]:
    """terms maps a slot name -> search phrases. Returns accepted records."""
    os.makedirs(ASSETS, exist_ok=True)
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_media: set[int] = set()

    for slot, phrases in terms.items():
        got = 0
        for phrase in phrases:
            if got >= want:
                break
            for item in search(phrase, per_term):
                if got >= want:
                    break
                mid = item.get("featured_media")
                if not mid or mid in seen_media:
                    continue
                seen_media.add(mid)

                credit = scrape_credit(item["link"])
                ok, why = credit_is_noaa_only(credit)
                if not ok:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "title": _text(item["title"]["rendered"]),
                                     "credit": credit, "reason": why})
                    continue

                det = media_detail(mid)
                if not det or not det.get("mime_type", "").startswith("image/"):
                    continue
                md = det.get("media_details", {})
                if md.get("width", 0) < 1200:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "reason": f"too small: {md.get('width')}px"})
                    continue

                src = det["source_url"]
                fname = f"{slot}__{mid}__{os.path.basename(urllib.parse.urlparse(src).path)}"
                path = os.path.join(ASSETS, fname)
                try:
                    blob = _get(src, binary=True)
                except Exception as exc:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "reason": f"download failed: {exc}"})
                    continue
                with open(path, "wb") as f:
                    f.write(blob)

                accepted.append({
                    "slot": slot,
                    "search_phrase": phrase,
                    "title": _text(item["title"]["rendered"]),
                    "caption": _text(item.get("content", {}).get("rendered", "")),
                    "source_org": "NOAA Ocean Exploration",
                    "item_url": item["link"],
                    "direct_url": src,
                    "local_file": os.path.relpath(path, OUT),
                    "width": md.get("width"),
                    "height": md.get("height"),
                    "rights_basis": (
                        "Work of the U.S. federal government published by NOAA Ocean "
                        "Exploration. Item page credit resolves to NOAA alone with no "
                        "third-party co-credit and no copyright notice, which is the "
                        "test NOAA's own media kit sets for reuse."
                    ),
                    "rights_check": why,
                    "media_kit_url": MEDIA_KIT,
                    "required_credit": credit,
                    "commercial_use_permitted": True,
                    "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "bytes": len(blob),
                })
                got += 1
                time.sleep(0.2)

    # A second harvester (pd_harvest) writes non-NOAA public-domain records into
    # the same manifest. Rewriting the file wholesale would silently delete that
    # work -- and the deletion would only surface later, as a KeyError at
    # thumbnail build time. So merge on `local_file` and keep what we did not
    # produce.
    accepted = _merge_assets(_load_manifest_assets(), accepted, keep_source=SOURCE_NOAA_OE)
    _write_manifest(accepted, rejected, gate="noaa-ocean-exploration")
    return accepted


SOURCE_NOAA_OE = "NOAA Ocean Exploration"

# One place that decides whether an image may ship, for every source. NOAA
# Ocean Exploration items go through credit_is_noaa_only(); everything else
# through pd_licence_ok(). Both write the same fields, so the manifest stays one
# auditable list rather than two half-documented ones.
MANIFEST_POLICY = (
    "Two gates, one manifest. (1) NOAA Ocean Exploration: accept only items whose "
    "item-page credit resolves to NOAA alone; reject any credit naming a non-federal "
    "partner (MBARI, Ocean Exploration Trust, WHOI/UW, GFOE, universities, named "
    "individual photographers) or containing a copyright notice; reject items with no "
    "credit line. Presence on a noaa.gov host is not evidence of public domain. "
    "(2) Other sources: accept only items whose own item page asserts public domain or "
    "CC0, verified live against the Wikimedia Commons extmetadata API (Copyrighted=False "
    "and a public-domain/CC0 licence tag). CC-BY, CC-BY-SA, CC-BY-NC and "
    "'no known copyright restrictions' are all rejected. Every record carries the item "
    "URL, the direct URL, the rights basis, the date checked and the sha256 of the "
    "bytes actually on disk."
)


def _load_manifest_assets() -> list[dict]:
    if not os.path.exists(MANIFEST):
        return []
    try:
        return json.load(open(MANIFEST)).get("assets", [])
    except Exception:
        return []


def _merge_assets(existing: list[dict], fresh: list[dict], keep_source: str) -> list[dict]:
    """Fresh records replace same-file old ones; records from OTHER sources survive."""
    fresh_files = {a["local_file"] for a in fresh}
    kept = [a for a in existing
            if a["local_file"] not in fresh_files and a.get("source_org") != keep_source]
    return kept + fresh


def _write_manifest(assets: list[dict], rejected: list[dict], gate: str) -> None:
    """Rewrite the manifest, replacing only THIS gate's rejections."""
    old = {}
    if os.path.exists(MANIFEST):
        try:
            old = json.load(open(MANIFEST))
        except Exception:
            old = {}
    for r in rejected:
        r.setdefault("gate", gate)
    prev_rej = [r for r in old.get("rejected", [])
                if r.get("gate", "noaa-ocean-exploration") != gate]
    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": MANIFEST_POLICY,
        "media_kit_url": MEDIA_KIT,
        "accepted_count": len(assets),
        "rejected_count": len(prev_rej) + len(rejected),
        "assets": assets,
        "rejected": prev_rej + rejected,
    }
    if "thumbnail_exclusions_note" in old:
        manifest["thumbnail_exclusions_note"] = old["thumbnail_exclusions_note"]
    os.makedirs(OUT, exist_ok=True)
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)


# ------------------------------------------------- gate 2: public-domain sources
#
# The NOAA Ocean Exploration set cannot cover every episode. Four subjects have
# no NOAA photograph that is BOTH truthful and usable: the Mariana Trench as a
# place, the descent to it, the frilled shark, and a midnight-zone animal. For
# those the honest alternatives are a historical scientific plate, a historical
# bathymetric chart, and a US Navy / NOAA archival photograph -- all genuinely
# public domain, none of them a lookalike animal wearing another species' name.
#
# Each item below was chosen by hand (the identification and the "is this
# actually the subject" judgement must be human), but its LICENCE is verified
# programmatically at fetch time against Wikimedia Commons' extmetadata, so a
# retag or a deletion breaks the build instead of quietly shipping.

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Only these. "No known copyright restrictions" (the Flickr Commons tag) is a
# statement that the holder found no restrictions, not a public-domain
# dedication, so it is not enough.
PD_LICENCE_TAGS = {"public domain", "cc0", "cc0 1.0", "pd", "pd-usgov", "pdm-owner"}


def commons_imageinfo(title: str) -> dict:
    url = (f"{COMMONS_API}?action=query&format=json&prop=imageinfo"
           f"&iiprop=url|size|mime|extmetadata&titles={urllib.parse.quote(title)}")
    pages = json.loads(_get(url))["query"]["pages"]
    page = next(iter(pages.values()))
    if "missing" in page or not page.get("imageinfo"):
        raise KeyError(f"commons file not found: {title}")
    return page["imageinfo"][0]


def pd_licence_ok(info: dict) -> tuple[bool, str]:
    """The whole rights decision for gate 2, in one auditable place."""
    em = info.get("extmetadata", {})

    def val(key):
        return re.sub(r"<[^>]+>", "", str(em.get(key, {}).get("value", ""))).strip()

    short = val("LicenseShortName").lower()
    copyrighted = val("Copyrighted").lower()
    if copyrighted == "true":
        return False, f"item page marks the work as copyrighted ({short or 'no licence tag'})"
    if short not in PD_LICENCE_TAGS:
        return False, f"licence is {short!r}, which is not public domain or CC0"
    return True, f"Commons item page asserts {val('LicenseShortName')} (Copyrighted=False)"


def pd_harvest(items: list[dict] | None = None) -> list[dict]:
    """Fetch, licence-check and record the hand-chosen public-domain items."""
    items = PD_ITEMS if items is None else items
    os.makedirs(ASSETS, exist_ok=True)
    accepted, rejected = [], []
    for it in items:
        info = commons_imageinfo(it["commons_title"])
        ok, why = pd_licence_ok(info)
        if not ok:
            rejected.append({"gate": "public-domain", "slot": it["slot"],
                             "item_url": info.get("descriptionurl"),
                             "title": it["title"], "reason": why})
            continue
        src = info["url"].split("?")[0]
        ext = os.path.splitext(urllib.parse.urlparse(src).path)[1] or ".jpg"
        fname = f"{it['slot']}__{it['id']}__{it['stem']}{ext}"
        path = os.path.join(ASSETS, fname)
        blob = _get(src, binary=True)
        with open(path, "wb") as f:
            f.write(blob)
        rec = {
            "slot": it["slot"],
            "search_phrase": it.get("search_phrase", it["stem"]),
            "title": it["title"],
            "caption": it["caption"],
            "source_org": it["source_org"],
            "item_url": info.get("descriptionurl"),
            "origin_url": it.get("origin_url"),
            "direct_url": src,
            "local_file": os.path.relpath(path, OUT),
            "width": info.get("width"),
            "height": info.get("height"),
            "rights_basis": it["rights_basis"],
            "rights_check": why,
            "media_kit_url": it.get("rights_url", info.get("descriptionurl")),
            "required_credit": it["required_credit"],
            "thumb_credit": it["thumb_credit"],
            "treatment": it["treatment"],
            "commercial_use_permitted": True,
            "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "thumbnail_ok": it.get("thumbnail_ok", True),
        }
        if it.get("crop"):
            rec["crop"] = it["crop"]
        if not rec["thumbnail_ok"]:
            rec["thumbnail_excluded_reason"] = it["thumbnail_excluded_reason"]
        accepted.append(rec)
        time.sleep(1.5)          # Commons rate-limits bots hard; be a good citizen

    # Keep every record this run did not itself produce -- including the whole
    # NOAA Ocean Exploration set. Records are matched by the numeric id embedded
    # in the filename, so re-running replaces rather than duplicates.
    mine = {it["id"] for it in items}
    kept = [a for a in _load_manifest_assets()
            if int(a["local_file"].split("__")[1]) not in mine]
    _write_manifest(kept + accepted, rejected, gate="public-domain")
    if rejected:
        raise SystemExit("licence check FAILED for: " +
                         "; ".join(f"{r['title']}: {r['reason']}" for r in rejected))
    return accepted


PD_ITEMS = [
    {
        "id": 900001, "slot": "trench", "stem": "krummel-1907-marianen-graben",
        "commons_title": "File:Mariana Trench Map 1907.jpg",
        "title": "Der Marianen-Graben (1907 bathymetric chart)",
        "caption": ("Otto Krümmel's chart of the Mariana Trench, printed in Handbuch "
                    "der Ozeanographie (1907). The figures are individual soundings in "
                    "metres and the closed contours are the trench itself -- this is "
                    "what the deepest place on Earth looked like when it was measured "
                    "by dropping a weighted line."),
        "source_org": "NOAA Photo Library (via Wikimedia Commons)",
        "origin_url": "https://www.photolib.noaa.gov/htmls/map00052.htm",
        "rights_url": "https://www.photolib.noaa.gov/about.html#about_images",
        "rights_basis": (
            "Two independent public-domain bases. (1) Published 1907 in Otto Krümmel, "
            "Handbuch der Ozeanographie; Krümmel died in 1912, so the work is out of "
            "copyright worldwide and in the United States as a pre-1930 publication. "
            "(2) The scan is published by the NOAA Photo Library and tagged "
            "PD-USGov-NOAA on its Commons item page."),
        "required_credit": "Otto Krümmel, Handbuch der Ozeanographie (1907); scan: NOAA Photo Library",
        "thumb_credit": "KRÜMMEL CHART, 1907", "treatment": "chart",
        # to the ruled border of the chart: the surrounding page carries
        # show-through from the reverse of the sheet, which is not the chart
        "crop": [0.020, 0.070, 0.940, 0.962],
    },
    {
        "id": 900002, "slot": "frilled_shark", "stem": "gunther-1887-plate-lxiv",
        "commons_title": "File:Chlamydoselachus anguineus1.jpg",
        "title": "Chlamydoselachus anguineus, Challenger Report Plate LXIV (1887)",
        "caption": ("Robert Mintern's lithograph of the frilled shark, Plate LXIV of "
                    "Albert Günther's Report on the Deep-Sea Fishes Collected by "
                    "H.M.S. Challenger During the Years 1873-1876 (1887). The species "
                    "had been described by Garman three years earlier; this is the "
                    "animal itself, drawn from a specimen, not a reconstruction."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/reportondeepseaf00gn",
        "rights_basis": (
            "Published 1887; the illustrator Robert Mintern died in 1908, so the plate "
            "is out of copyright in every jurisdiction that uses life+70 or shorter, "
            "and in the United States as a pre-1930 publication. The Commons item page "
            "carries PD-scan / PD-old-auto-expired and marks the file not copyrighted."),
        "required_credit": ("Robert Mintern, in A. Günther, Report on the Deep-Sea Fishes "
                            "of H.M.S. Challenger (1887), Plate LXIV"),
        "thumb_credit": "CHALLENGER REPORT PLATE, 1887", "treatment": "plate",
    },
    {
        "id": 900003, "slot": "frilled_shark", "stem": "noaa-2004-frilled-shark-in-situ",
        "commons_title": "File:Chlamydoselachus anguineus NOOA.jpg",
        "title": "Frilled shark in its natural habitat (NOAA, 2004)",
        "caption": ("A frilled shark filmed from the submersible Johnson-Sea-Link II at "
                    "2,866 feet on 26 August 2004, during NOAA's Estuary to the Abyss "
                    "expedition. Identified on board by shark biologist Josh Loefer; "
                    "NOAA published it as the first known footage of the species in the "
                    "wild."),
        "source_org": "NOAA Ocean Exploration (2004 archive, via Wikimedia Commons)",
        "origin_url": ("https://web.archive.org/web/20250903065752/"
                       "https://oceanexplorer.noaa.gov/explorations/04etta/logs/aug27/"
                       "media/frilled_shark.html"),
        "rights_basis": (
            "Work of the U.S. federal government: a NOAA Office of Ocean Exploration "
            "expedition image, published on oceanexplorer.noaa.gov with a NOAA-only "
            "credit and no copyright notice. The Commons item page carries "
            "PD-USGov-NOAA and marks the file not copyrighted."),
        "required_credit": "NOAA Ocean Exploration, Estuary to the Abyss 2004",
        "thumb_credit": "NOAA OCEAN EXPLORATION", "treatment": "photo",
        "thumbnail_ok": False,
        "thumbnail_excluded_reason": (
            "Public domain and correctly identified, but the video overlay -- date, "
            "time, DEPTH 2866FT, TEMP, SALIN -- is burned into the top of the frame, "
            "and the shark itself is a low-contrast blur that disappears entirely at "
            "168 px. Same reason as the wordmarked NOAA frames: usable, not usable "
            "inside our own layout."),
    },
    {
        "id": 900004, "slot": "vehicle", "stem": "trieste-nh96797-1960",
        "commons_title": ("File:Bathyscaphe Trieste with USS Lewis (DE-535) over the "
                          "Marianas Trench, 23 January 1960 (NH 96797).jpg"),
        "title": "Bathyscaphe Trieste before the Challenger Deep dive, 23 January 1960",
        "caption": ("Trieste on the surface over the Mariana Trench on the morning of "
                    "23 January 1960, hours before Jacques Piccard and Don Walsh rode "
                    "her to the bottom of Challenger Deep. The destroyer escort USS "
                    "Lewis is steaming past behind her."),
        "source_org": "U.S. Naval History and Heritage Command (via Wikimedia Commons)",
        "origin_url": "https://www.history.navy.mil/our-collections/photography.html",
        "rights_basis": (
            "Official U.S. Navy photograph NH 96797, a work of the U.S. federal "
            "government prepared by a Navy employee in the course of duty, and "
            "therefore public domain under 17 U.S.C. 105. The Commons item page marks "
            "the file not copyrighted."),
        "required_credit": "U.S. Navy photo NH 96797",
        "thumb_credit": "U.S. NAVY, 23 JANUARY 1960", "treatment": "archive",
    },
    {
        "id": 900005, "slot": "vehicle", "stem": "trieste-piccard-walsh-1960",
        "commons_title": "File:Bathyscaphe Trieste Piccard-Walsh.jpg",
        "title": "Don Walsh and Jacques Piccard inside Trieste, 1960",
        "caption": ("Lieutenant Don Walsh, USN, and Jacques Piccard in the crew sphere "
                    "of the bathyscaphe Trieste, 1960 -- the two men who reached the "
                    "bottom of Challenger Deep, in the space they did it from."),
        "source_org": "NOAA Photo Library, Ship Collection (via Wikimedia Commons)",
        "origin_url": "https://www.photolib.noaa.gov/",
        "rights_basis": (
            "NOAA Ship Collection image ship3224, a work of the U.S. federal government "
            "and therefore public domain under 17 U.S.C. 105. The Commons item page "
            "carries PD-USGov-NOAA and marks the file not copyrighted."),
        "required_credit": "NOAA Photo Library, Ship Collection (ship3224)",
        "thumb_credit": "NOAA PHOTO LIBRARY, 1960", "treatment": "archive",
    },
    {
        "id": 900006, "slot": "vehicle", "stem": "trieste-nh96801-hoisted",
        "commons_title": "File:Bathyscaphe Trieste.jpg",
        "title": "Bathyscaphe Trieste hoisted from the water",
        "caption": ("Trieste lifted clear of the water by a floating crane during "
                    "testing by the Navy Electronics Laboratory at San Diego, before "
                    "shipping to the Marianas. The striped cylinder is the petrol "
                    "float; the crew sphere is the small ball slung beneath it."),
        "source_org": "U.S. Naval History and Heritage Command (via Wikimedia Commons)",
        "origin_url": "https://www.history.navy.mil/our-collections/photography.html",
        "rights_basis": (
            "Official U.S. Navy photograph NH 96801, released by the U.S. Navy "
            "Electronics Laboratory; a work of the U.S. federal government and "
            "therefore public domain under 17 U.S.C. 105. The Commons item page marks "
            "the file not copyrighted."),
        "required_credit": "U.S. Navy photo NH 96801",
        "thumb_credit": "U.S. NAVY PHOTO NH 96801", "treatment": "archive",
    },
    {
        "id": 900007, "slot": "column", "stem": "gunther-1887-melanocetus-murrayi",
        "commons_title": "File:Melanocetus murrayi (Murrays abyssal anglerfish).jpg",
        "title": "Melanocetus murrayi, Challenger Report plate (1887)",
        "caption": ("Robert Mintern's lithograph of Melanocetus murrayi, Murray's "
                    "abyssal anglerfish, from Albert Günther's Report on the Deep-Sea "
                    "Fishes Collected by H.M.S. Challenger (1887). A bathypelagic "
                    "animal: it lives in the midnight zone, below 1,000 metres, where "
                    "the only light is the light animals make."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/reportondeepseaf00gn",
        "rights_basis": (
            "Published 1887; illustrator Robert Mintern died in 1908. Out of copyright "
            "worldwide under life+70 and in the United States as a pre-1930 "
            "publication. The Commons item page carries PD-scan / PD-old-70 and marks "
            "the file not copyrighted."),
        "required_credit": ("Robert Mintern, in A. Günther, Report on the Deep-Sea Fishes "
                            "of H.M.S. Challenger (1887)"),
        "thumb_credit": "CHALLENGER REPORT PLATE, 1887", "treatment": "plate",
    },
]


TERMS = {
    "anglerfish":    ["anglerfish", "chaunacops", "coffinfish"],
    "jelly":         ["deep sea jellyfish", "narcomedusae", "benthocodon"],
    "siphonophore":  ["siphonophore"],
    "octopus":       ["dumbo octopus", "grimpoteuthis", "deep sea octopus"],
    "squid":         ["deep sea squid", "bathyteuthis", "magnapinna"],
    "vent":          ["hydrothermal vent chimney", "black smoker"],
    "crab":          ["squat lobster", "deep sea crab", "galatheid"],
    "sponge":        ["glass sponge", "hexactinellid", "venus flower basket"],
    "coral":         ["bubblegum coral", "iridogorgia", "bamboo coral"],
    "cucumber":      ["sea cucumber", "holothurian", "sea pig"],
    "star":          ["brisingid sea star", "basket star", "crinoid"],
    "fish":          ["rattail fish", "grenadier", "cusk eel", "tripodfish"],
    "whalefall":     ["whale fall", "whale bone"],
    "seafloor":      ["abyssal seafloor sediment", "manganese nodules"],
    "vehicle":       ["remotely operated vehicle deep discoverer", "rov dive"],
    # episode-specific probes
    "yeti_crab":     ["yeti crab", "kiwa"],
    "frilled_shark": ["frilled shark", "deep sea shark", "sixgill shark"],
    "snailfish":     ["snailfish", "liparid", "hadal trench"],
    "whale_bone":    ["whale fall bone", "whale skeleton seafloor"],
    "trench":        ["mariana trench", "challenger deep", "trench dive"],
    "biolum":        ["bioluminescent", "bioluminescence deep sea"],
    "eyes":          ["big eye fish deep sea", "deep sea fish eye"],
    "transparent":   ["transparent sea cucumber", "translucent deep sea"],
    "red_animal":    ["red deep sea shrimp", "red jellyfish deep"],
    "column":        ["midwater water column", "midnight zone"],
}

if __name__ == "__main__":
    if "--pd" in sys.argv:
        got = pd_harvest()
        print(f"public-domain gate: accepted {len(got)}")
        for a in got:
            print(f"  {a['slot']:14} {a['width']}x{a['height']:<5} {a['rights_check']}")
        print(f"manifest -> {MANIFEST}")
        raise SystemExit(0)

    got = harvest(TERMS)
    with open(MANIFEST) as f:
        man = json.load(f)
    print(f"accepted {man['accepted_count']} / rejected {man['rejected_count']}")
    print(f"manifest -> {MANIFEST}")
    from collections import Counter
    print("by slot:", dict(Counter(a["slot"] for a in got)))
    reasons = Counter(re.sub(r":.*", "", r.get("reason", "?")) for r in man["rejected"])
    for r, n in reasons.most_common():
        print(f"  rejected {n:3}  {r}")
