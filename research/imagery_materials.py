"""Materials-and-manufacturing -> image index. Fourth gate, same discipline.

Why a separate module rather than a parameter on imagery_species.py
-------------------------------------------------------------------
The species module's job is to prove that a picture IS a named animal, and its
hardest test is identity: a giant squid plate captioned "colossal squid" is a
lie told in pictures. Materials has a different hardest test. Nobody will
mistake one photograph of molten steel for another, but the RIGHTS surface is
much wider: deep sea's imagery is overwhelmingly NOAA and Commons PD-old,
while materials imagery is NASA, NARA, USGS, national labs, old engineering
engravings and a great deal of modern corporate photography that looks
identical on a search results page and is not free.

So the licence gate is reused unchanged and the third-party screen is
DIFFERENT, deliberately, and the difference is the point:

  (1) LICENCE, live, unchanged: `imagery.pd_licence_ok`, imported not
      reimplemented. Commons `extmetadata` must report Copyrighted=False and a
      public-domain or CC0 licence tag. CC-BY, CC-BY-SA, CC-BY-NC and Flickr's
      "no known copyright restrictions" all hard-fail. This channel is
      monetised and CC-BY is not a public-domain dedication.

  (2) COPYRIGHT ASSERTION screen, this module's own. `imagery.THIRD_PARTY`
      cannot be reused here: it rejects on the words "university",
      "institute", "nasa", "usgs", "museum" and "foundation", which is correct
      for deep sea, where the only federal source in play is NOAA and a
      university credit means the PD-USGov tag is wrong. Applied to materials
      it would reject a NASA photograph and a NARA scan - works of the U.S.
      federal government that ARE public domain under 17 U.S.C. 105 - while
      catching nothing extra. Screening on the wrong list is not a stricter
      gate, it is a gate pointed at the wrong thing. What this module screens
      for instead is an ASSERTION OF COPYRIGHT in the item's own Artist,
      Credit, Attribution or Description text, because a Commons PD tag is a
      volunteer's judgement and the item page's own prose is the best evidence
      that the judgement was wrong.

  (3) IDENTITY, hand-written, machine-required. Every subject below carries
      `depicts` (what the picture literally IS - a photograph, an engraving, a
      micrograph), `subject_basis` (why this image is this subject) and
      `credit_line` (what is drawn on screen). CONTRACT.md rule: a picture is
      captioned with a word the viewer is hearing, and an engraving is
      credited as an engraving.

What this index will not do
---------------------------
Substitute. If a subject has no image that passes, it gets no image and the
drawn treatment stands. An unrelated furnace captioned as a semiconductor fab
is the failure this whole file exists to prevent.

Run:  python research/imagery_materials.py            harvest and verify
      python research/imagery_materials.py --verify   re-verify what is on disk
      python research/imagery_materials.py --dry-run  gate only, download nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import imagery as I                                        # noqa: E402

OUT = os.path.join(ROOT, "channel", "imagery")
ASSETS = os.path.join(OUT, "assets")
MATERIALS_MANIFEST = os.path.join(OUT, "materials.json")

# --------------------------------------------------------------------------
# THE WEEKLY LANE FINDS THIS FILE THROUGH THIS DECLARATION, not through a list
# kept somewhere else. loop/footage_lane.py globs research/imagery*.py, reads
# this literal without importing the module, and runs the ones whose `domain`
# currently holds a slot in loop/config.json's allocation. Two components each
# keeping their own list, with no link between them, is exactly how
# research/imagery_materials.py came to be wired to no lane at all.
#
# `gate` is the rights function this file MUST still contain. The lane refuses
# to run a harvester whose gate has gone missing, so "relax the check to get
# more material" fails loudly instead of quietly succeeding.
HARVESTER = {
    "domain": "materials-and-manufacturing",
    "gate": "pd_licence_ok",
    "manifest": "channel/imagery/materials.json",
    "args": ["--missing"],
    "scheduled": True,
    "what": "materials stills - Wikimedia Commons, public-domain gate only",
}


COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Wikidata Q19652 is "public domain". Restricting the SEARCH itself to items
# whose copyright status is PD means the licence gate is rejecting edge cases
# rather than doing all the work, and it keeps the number of live fetches
# proportionate to what is actually usable.
PD_STATEMENT = "haswbstatement:P6216=Q19652"

# An assertion of copyright in the item's own words. Narrow on purpose: this
# fires on a CLAIM, not on the presence of an organisation's name, because for
# this domain the organisations are mostly the reason the work is free.
COPYRIGHT_ASSERTION = re.compile(
    r"(?i)\b("
    r"copyright|\(c\)\s*\d|&copy;|©|"
    r"all rights reserved|used with permission|permission required|"
    r"getty|shutterstock|alamy|adobe stock|istock|"
    r"reproduced by permission|do not reproduce"
    r")\b")


# Commons rate-limits bursts, and imagery._get gives up after 3 tries with a
# 1.5s step. The first full run lost 74 of 118 candidate lookups that way and
# reported them as "no candidate passed both gates" - a THROTTLE reading as a
# rights failure, which is the worst possible confusion for this module: it
# makes a free image look unfree and silently shrinks coverage. So requests
# here are spaced and retried much harder, and a lookup that still fails is
# recorded as a FETCH failure and never as a licence one.
_LAST = [0.0]
MIN_INTERVAL = 0.9        # seconds between requests to commons


def _polite(url: str, binary: bool = False, tries: int = 6):
    import time as _t
    last = None
    for i in range(tries):
        gap = MIN_INTERVAL - (_t.monotonic() - _LAST[0])
        if gap > 0:
            _t.sleep(gap)
        _LAST[0] = _t.monotonic()
        try:
            return I._get(url, binary=binary, tries=1)
        except Exception as exc:
            last = exc
            _t.sleep(2.0 * (i + 1))
    raise last


def _text(info: dict, *keys) -> str:
    em = info.get("extmetadata", {})
    out = []
    for k in keys:
        v = str(em.get(k, {}).get("value", ""))
        out.append(re.sub(r"<[^>]+>", " ", v))
    return " ".join(out)


def copyright_asserted(info: dict) -> tuple[bool, str]:
    """Does the item's own page claim copyright, whatever its licence tag says?"""
    blob = _text(info, "Artist", "Credit", "Attribution", "ImageDescription",
                 "UsageTerms", "Restrictions")
    m = COPYRIGHT_ASSERTION.search(blob)
    if m:
        return True, f"item page asserts {m.group(0)!r} in its own credit or description"
    return False, ""


# ---------------------------------------------------------------------------
# The subjects. Hand-written: what the picture must show, and why an image of
# it belongs on screen while that sentence is being spoken. `queries` are
# ordered - the first candidate that passes both gates wins, so put the most
# specific phrasing first.
# ---------------------------------------------------------------------------

SUBJECTS: list[dict] = [
    {"key": "molten-steel", "label": "MOLTEN STEEL",
     "queries": ["molten steel pouring foundry", "steel ladle pouring", "molten iron casting"],
     "depicts": "photograph",
     "subject_basis": "Liquid steel being poured. Used only under narration about melting, "
                      "casting or the forge range of the thermal scale."},
    {"key": "welding-arc", "label": "WELDING ARC",
     "queries": ["arc welding sparks", "welder arc welding", "gas tungsten arc welding"],
     "depicts": "photograph",
     "subject_basis": "An electric welding arc in operation. Used under narration about arc "
                      "temperature or plasma."},
    {"key": "silicon-wafer", "label": "SILICON WAFER",
     "queries": ["silicon wafer mirror finish", "silicon wafer", "silicon ingot boule"],
     "depicts": "photograph",
     "subject_basis": "A polished monocrystalline silicon wafer or the boule it is cut from."},
    {"key": "microchip-die", "label": "SILICON DIE",
     "queries": ["integrated circuit die photograph", "microprocessor die shot",
                 "silicon chip die micrograph"],
     "depicts": "micrograph",
     "subject_basis": "A decapped integrated-circuit die. Credited as a micrograph, never as "
                      "a photograph of a packaged chip."},
    {"key": "carbon-fiber", "label": "CARBON FIBRE",
     "queries": ["carbon fiber weave fabric", "carbon fibre cloth", "carbon fiber composite"],
     "depicts": "photograph",
     "subject_basis": "Woven carbon-fibre fabric or a cured laminate."},
    {"key": "damascus-blade", "label": "PATTERN-WELDED STEEL",
     "queries": ["damascus steel blade pattern", "pattern welded blade", "damascus steel knife"],
     "depicts": "photograph",
     "subject_basis": "A blade showing the surface pattern of pattern-welded or crucible steel. "
                      "Captioned as pattern-welded unless the item page identifies wootz."},
    {"key": "blast-furnace", "label": "BLAST FURNACE",
     "queries": ["blast furnace ironworks", "bessemer converter", "steel mill blast furnace"],
     "depicts": "photograph",
     "subject_basis": "Primary ironmaking or steelmaking plant. Used for narration about "
                      "industrial-scale production, never about a laboratory process."},
    {"key": "rust", "label": "IRON OXIDE",
     "queries": ["rusted iron surface", "corroded iron plate", "rust corrosion metal"],
     "depicts": "photograph",
     "subject_basis": "Iron oxide on a corroding iron or steel surface."},
    {"key": "aerogel", "label": "SILICA AEROGEL",
     "queries": ["silica aerogel block", "aerogel", "aerogel insulation"],
     "depicts": "photograph",
     "subject_basis": "A monolith of silica aerogel."},
    {"key": "graphene-lattice", "label": "GRAPHENE LATTICE",
     "queries": ["graphene lattice structure diagram", "graphene honeycomb lattice", "graphene"],
     "depicts": "diagram",
     "subject_basis": "The hexagonal carbon lattice. A structural diagram, credited as a "
                      "diagram - graphene is not photographable at this scale."},
    {"key": "titanium", "label": "TITANIUM",
     "queries": ["titanium metal crystals", "titanium ingot", "titanium sponge metal"],
     "depicts": "photograph",
     "subject_basis": "Titanium in metallic form."},
    {"key": "tempered-glass", "label": "FRACTURED GLASS",
     "queries": ["shattered tempered glass", "broken safety glass fragments",
                 "tempered glass fracture"],
     "depicts": "photograph",
     "subject_basis": "The characteristic dice-shaped fragmentation of thermally toughened "
                      "glass. Used only where the narration is describing that fracture mode."},
    {"key": "concrete", "label": "CONCRETE",
     "queries": ["concrete pouring construction", "reinforced concrete rebar",
                 "concrete cement mixer construction"],
     "depicts": "photograph",
     "subject_basis": "Concrete being placed, or reinforcement before a pour."},
    {"key": "crystal-structure", "label": "CRYSTAL LATTICE",
     "queries": ["body centered cubic crystal structure", "crystal lattice diagram metal",
                 "face centered cubic unit cell"],
     "depicts": "diagram",
     "subject_basis": "A unit-cell diagram of a metallic crystal structure. Credited as a "
                      "diagram."},
    {"key": "micrograph-steel", "label": "STEEL MICROSTRUCTURE",
     "queries": ["steel microstructure micrograph", "martensite microstructure",
                 "pearlite microstructure steel"],
     "depicts": "micrograph",
     "subject_basis": "An etched and polished section of steel under a microscope. The grain "
                      "structure narration about phases and quenching is describing."},
    {"key": "3d-printed-metal", "label": "METAL 3D PRINTING",
     "queries": ["selective laser melting metal powder", "metal 3d printed part",
                 "direct metal laser sintering"],
     "depicts": "photograph",
     "subject_basis": "Powder-bed metal additive manufacturing, or a part produced by it."},
    {"key": "cleanroom", "label": "SEMICONDUCTOR CLEANROOM",
     "queries": ["semiconductor cleanroom fab", "cleanroom bunny suit wafer",
                 "photolithography cleanroom"],
     "depicts": "photograph",
     "subject_basis": "A semiconductor fabrication cleanroom."},
    {"key": "kevlar-aramid", "label": "ARAMID FIBRE",
     "queries": ["aramid fiber fabric", "kevlar fabric weave", "ballistic aramid fabric"],
     "depicts": "photograph",
     "subject_basis": "Woven aramid fabric. Captioned as aramid unless the item page names "
                      "the trade name itself."},
]

# Subjects that were looked for and deliberately have no entry. Named, so a
# gap is a recorded decision rather than something nobody got round to.
UNILLUSTRATABLE: dict[str, dict] = {
    "self-healing-polymer": {
        "why": "Published micrographs of healed crack faces are overwhelmingly figures from "
               "copyrighted journal articles. A generic photograph of epoxy would show "
               "nothing the narration is describing, and a healed crack that is not the one "
               "being discussed is a picture that asserts a result. The drawn treatment "
               "stands."},
}


def _search_raw(srsearch: str, limit: int) -> list[str]:
    q = (f"{COMMONS_API}?action=query&format=json&list=search&srnamespace=6"
         f"&srlimit={limit}&srsearch=" + urllib.parse.quote(srsearch))
    try:
        return [h["title"] for h in json.loads(_polite(q))["query"]["search"]]
    except Exception:
        return []


def _search(phrase: str, limit: int = 6) -> list[str]:
    """PD-tagged candidates first, then the open field.

    The P6216 structured-data filter is an OPTIMISATION, not the rights gate.
    Most of Commons predates structured copyright statements, so filtering the
    search on it dropped nine of eighteen subjects for want of a machine-
    readable claim rather than for want of a free image - welding arcs, rust
    and titanium among them, none of which are short of public-domain
    photographs. The gate is `imagery.pd_licence_ok` reading the item page
    live, and it is applied identically to both passes: widening the search
    cannot widen what is accepted, only what is considered.
    """
    seen, out = set(), []
    for srsearch in (f"{phrase} {PD_STATEMENT}", phrase):
        for t in _search_raw(srsearch, limit):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def harvest(dry_run: bool = False, only: list[str] | None = None) -> dict:
    """Harvest the subjects in `only` (default: all) and MERGE into the manifest.

    Merging, not overwriting: a partial re-run for the subjects a throttled
    first pass missed must not delete the records that pass already verified.
    That is the same rule imagery.py states for its two gates - neither may
    delete the other's records - applied to two runs of one gate.
    """
    os.makedirs(ASSETS, exist_ok=True)
    prior = {}
    if os.path.exists(MATERIALS_MANIFEST):
        for rec in json.load(open(MATERIALS_MANIFEST)).get("index", []):
            prior[rec["subject"]] = rec
    accepted, rejected = [], []
    todo = [s for s in SUBJECTS if (not only or s["key"] in only)]
    for sub in todo:
        if sub["key"] in prior and (not only or sub["key"] not in only):
            accepted.append(prior[sub["key"]])
            continue
        got = None
        for phrase in sub["queries"]:
            for title in _search(phrase):
                try:
                    iq = (f"{COMMONS_API}?action=query&format=json&prop=imageinfo"
                          f"&iiprop=url|size|mime|extmetadata&titles="
                          + urllib.parse.quote(title))
                    pages = json.loads(_polite(iq))["query"]["pages"]
                    page = next(iter(pages.values()))
                    if "missing" in page or not page.get("imageinfo"):
                        raise KeyError(f"commons file not found: {title}")
                    info = page["imageinfo"][0]
                except Exception as e:
                    rejected.append({"subject": sub["key"], "title": title,
                                     "reason": f"imageinfo failed: {e}"})
                    continue
                if (info.get("mime") or "").split("/")[-1] not in ("jpeg", "png", "jpg"):
                    continue
                if int(info.get("width") or 0) < 900:
                    continue                      # too small to fill 1920x1080
                ok, why = I.pd_licence_ok(info)
                if not ok:
                    rejected.append({"subject": sub["key"], "title": title,
                                     "item_url": info.get("descriptionurl"), "reason": why})
                    continue
                claimed, why_c = copyright_asserted(info)
                if claimed:
                    rejected.append({"subject": sub["key"], "title": title,
                                     "item_url": info.get("descriptionurl"), "reason": why_c})
                    continue
                got = (title, info, phrase, why)
                break
            if got:
                break
        if not got:
            rejected.append({"subject": sub["key"], "title": None,
                             "reason": "no candidate passed both gates"})
            continue

        title, info, phrase, why = got
        stem = re.sub(r"[^a-z0-9]+", "-", title.lower().removeprefix("file:")).strip("-")[:60]
        src = info["url"].split("?")[0]
        ext = os.path.splitext(urllib.parse.urlparse(src).path)[1].lower() or ".jpg"
        fname = f"mat__{sub['key']}__{stem}{ext}"
        path = os.path.join(ASSETS, fname)
        sha = None
        if not dry_run:
            blob = _polite(src, binary=True)
            with open(path, "wb") as f:
                f.write(blob)
            sha = hashlib.sha256(blob).hexdigest()

        artist = re.sub(r"\s+", " ", _text(info, "Artist")).strip()
        licence = re.sub(r"<[^>]+>", "", str(
            info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", ""))).strip()
        accepted.append({
            "subject": sub["key"],
            "label": sub["label"],
            "title": title.removeprefix("File:"),
            "depicts": sub["depicts"],
            "subject_basis": sub["subject_basis"],
            # Drawn on screen. The medium is stated, so an engraving is never
            # presented as a photograph, and the licence is named.
            "credit_line": f"{sub['label']} — {sub['depicts'].upper()}, "
                           f"{(artist or 'UNATTRIBUTED')[:48].upper()} ({licence.upper()})",
            "treatment": "photo" if sub["depicts"] in ("photograph", "micrograph") else "plate",
            "source_org": artist or "Wikimedia Commons",
            "licence": licence,
            "matched_query": phrase,
            "item_url": info.get("descriptionurl"),
            "direct_url": src,
            # RELATIVE TO channel/imagery/, with the assets/ prefix, because
            # that is what segments_species.treated() joins against and the
            # species records already use. A bare filename resolved to
            # channel/imagery/<name> and raised FileNotFoundError at the first
            # frame - after the plan had been written.
            "local_file": f"assets/{fname}" if not dry_run else None,
            "sha256": sha,
            "width": info.get("width"), "height": info.get("height"),
            "licence_basis": why,
        })
        print(f"  OK   {sub['key']:<18} {title[:58]}")
    for r in rejected:
        if r["title"] is None:
            print(f"  DROP {r['subject']:<18} {r['reason']}")

    got = {a["subject"] for a in accepted}
    for key, rec in prior.items():
        if key not in got:
            accepted.append(rec)
    accepted.sort(key=lambda a: a["subject"])

    man = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "domain": "materials-and-manufacturing",
        "policy": ("Public domain or CC0 only, verified live at the Commons item page. "
                   "CC-BY is not a public-domain dedication and this channel is monetised. "
                   "Licence gate is research/imagery.pd_licence_ok, imported not "
                   "reimplemented; the copyright-assertion screen is this module's own and "
                   "differs from imagery.THIRD_PARTY on purpose - see the module docstring."),
        "rights_fields_required": ["depicts", "subject_basis", "credit_line", "item_url",
                                   "licence", "sha256"],
        "asset_count": len(accepted),
        "subjects_total": len(SUBJECTS),
        "subjects_covered": sorted({a["subject"] for a in accepted}),
        "subjects_unillustratable": UNILLUSTRATABLE,
        "rejected": rejected,
        "index": accepted,
    }
    if not dry_run:
        json.dump(man, open(MATERIALS_MANIFEST, "w"), indent=2)
    return man


def verify_rights(man: dict | None = None) -> int:
    """Every recorded asset is on disk, unmodified, and carries its rights fields."""
    man = man or json.load(open(MATERIALS_MANIFEST))
    req = man["rights_fields_required"]
    n = 0
    for rec in man["index"]:
        missing = [k for k in req if not rec.get(k)]
        if missing:
            raise AssertionError(f"{rec['subject']}: missing rights field(s) {missing}")
        path = os.path.join(OUT, rec["local_file"])
        if not os.path.exists(path):
            raise AssertionError(f"{rec['subject']}: {rec['local_file']} is not on disk")
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != rec["sha256"]:
            raise AssertionError(f"{rec['subject']}: {rec['local_file']} sha256 changed "
                                 f"since it was rights-checked")
        n += 1
    if n == 0:
        raise AssertionError("verified zero assets - an empty index must fail, not pass. "
                             "A validator that examines nothing proves nothing.")
    return n


if __name__ == "__main__":
    if "--verify" in sys.argv:
        print(f"materials rights verified: {verify_rights()} assets, sha256 matched")
        raise SystemExit(0)
    dry = "--dry-run" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = [a for a in sys.argv[sys.argv.index("--only") + 1:]
                if not a.startswith("--")]
    if "--missing" in sys.argv:
        have = set()
        if os.path.exists(MATERIALS_MANIFEST):
            have = {r["subject"] for r in json.load(
                open(MATERIALS_MANIFEST)).get("index", [])}
        only = [s["key"] for s in SUBJECTS if s["key"] not in have]
        print(f"retrying {len(only)} subject(s) with no verified image: "
              f"{', '.join(only)}\n")
    man = harvest(dry_run=dry, only=only)
    print(f"\n{man['asset_count']}/{len(SUBJECTS)} subjects covered -> {MATERIALS_MANIFEST}")
    if not dry:
        print(f"rights verified: {verify_rights(man)} assets, sha256 matched on every file")
