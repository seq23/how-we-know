"""Food-science -> image index (stills). The materials gate, unchanged, on food.

The third domain (owner decision 2026-10-13, docs/CHANNEL-PLAN.md "A third
domain: food science") needs REAL pictures for the things that are real - a
loaf, a seared steak, a cocoa pod, Pasteur, the instruments - and real moving
footage for food in motion (pours, sizzles, snaps). The fantastical-scale
shots (fields of dough, a thousand steaks, chocolate falling in sheets) are AI
stills and live in `visuals/food_stills.py`, with their own provenance; nothing
in this module is generated.

THE GATE is research/imagery_materials.py's, imported and run unchanged:
  (1) LICENCE, live: `imagery.pd_licence_ok` on the Commons item page -
      public domain or CC0 only. CC-BY is not a public-domain dedication and
      the channel is monetised.
  (2) COPYRIGHT ASSERTION screen: the item's own Artist/Credit/Description
      prose must not assert copyright.
  (3) IDENTITY, hand-written: every subject says what the picture literally
      is (`depicts`), why it belongs under that sentence (`subject_basis`),
      and the credit drawn on screen.

CLIPS ARE NOT HARVESTED HERE. Real food footage comes through
research/food_footage.py only (CLAUDE.md, owner widening 2026-10-13), and
the food clip manifest (food_footage.MANIFEST) is that module's alone. Until
2026-10-17 this module also ran a Commons-only clip pass that rewrote the same
file in its own schema: the first Saturday CI harvest replaced the Mac's
verified clip records with one Commons record and redded main (V53,
test_food_footage_chain). One manifest, one writer; test_food_domain pins it.

PEXELS AND PIXABAY. Both licences allow free commercial use and the owner's
brief names them. Their search APIs need a free key tied to an account, and
there is none in the vault on 2026-10-13. With `PEXELS_API_KEY` /
`PIXABAY_API_KEY` absent the harvester records the source as unavailable in
the manifest (named, never silent) and harvests from Commons alone. A
Pexels/Pixabay asset, when one is added, must record `licence` = "Pexels
License" / "Pixabay Content License" and its page URL per asset, like these.

    python research/imagery_food.py            # stills
    python research/imagery_food.py --missing  # only subjects with nothing yet
    python research/imagery_food.py --verify   # sha256 + rights fields on disk
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import imagery_materials as M                                  # noqa: E402

FOOD_MANIFEST = os.path.join(M.OUT, "food.json")
DOMAIN = "food-science"

HARVESTER = {
    "domain": "food-science",
    "gate": "pd_licence_ok",
    "manifest": "channel/imagery/food.json",
    "args": ["--missing"],
    "scheduled": True,
    "what": "food stills - Wikimedia Commons, public-domain/CC0 gate only",
}

SUBJECTS: list[dict] = [
    {"key": "chocolate-bar", "title_none": ["шакаляд", "packag", "wrapper", "box", "milky way"], "title_any": ["chocolate"], "label": "CHOCOLATE",
     "queries": ["dark chocolate bar broken pieces", "chocolate bar", "dark chocolate"],
     "depicts": "photograph",
     "subject_basis": "A bar or broken pieces of chocolate: the glossy, snapping solid the "
                      "chocolate question is about."},
    {"key": "cocoa-pod", "title_any": ["cacao", "cocoa", "theobroma"], "label": "CACAO POD",
     "queries": ["cacao pod opened beans", "cocoa pod tree", "theobroma cacao fruit"],
     "depicts": "photograph",
     "subject_basis": "The fruit of Theobroma cacao, whose seeds give cocoa butter."},
    {"key": "cocoa-beans", "title_any": ["cacao", "cocoa"], "label": "COCOA BEANS",
     "queries": ["cocoa beans roasted", "cocoa beans", "cacao beans fermented"],
     "depicts": "photograph",
     "subject_basis": "Fermented or roasted cocoa beans, the source of the fat the "
                      "narration measures."},
    {"key": "melted-chocolate", "title_none": ["industries of war"], "title_any": ["chocolate"], "label": "MELTED CHOCOLATE",
     "queries": ["melted chocolate", "chocolate melting", "liquid chocolate"],
     "depicts": "photograph",
     "subject_basis": "Chocolate above its melting range; used where the narration says "
                      "it has melted."},
    {"key": "bread-loaf", "title_none": ["magic yeast", "advert"], "title_any": ["bread", "loaf", "sourdough"], "label": "BREAD",
     "queries": ["sourdough loaf crumb cross section", "bread loaf sliced crumb",
                 "bread loaf"],
     "depicts": "photograph",
     "subject_basis": "A baked loaf and its crumb, the gas cells the bread question is about."},
    {"key": "dough", "title_none": ["machine", "1877"], "title_any": ["dough"], "label": "DOUGH",
     "queries": ["bread dough rising bowl", "bread dough", "yeast dough"],
     "depicts": "photograph",
     "subject_basis": "Unbaked yeasted dough."},
    {"key": "yeast-micrograph", "title_any": ["saccharomyces", "yeast"], "label": "BAKER'S YEAST",
     "queries": ["saccharomyces cerevisiae micrograph", "saccharomyces cerevisiae sem",
                 "yeast cells microscope"],
     "depicts": "micrograph",
     "subject_basis": "Saccharomyces cerevisiae cells under a microscope. Credited as a "
                      "micrograph."},
    {"key": "pasteur", "title_any": ["pasteur"], "label": "LOUIS PASTEUR",
     "queries": ["Louis Pasteur portrait", "Louis Pasteur photograph Nadar",
                 "Louis Pasteur laboratory"],
     "depicts": "photograph",
     "subject_basis": "Louis Pasteur (1822-1895), whose 1857 fermentation work the bread "
                      "segment cites."},
    {"key": "seared-steak", "title_none": ["steak house", "restaurant", "postcard", "grill ("], "title_any": ["steak", "beef"], "label": "SEARED STEAK",
     "queries": ["seared steak crust", "grilled steak", "beef steak cooked"],
     "depicts": "photograph",
     "subject_basis": "A seared or grilled steak showing the browned crust the Maillard "
                      "segment explains."},
    {"key": "maillard", "title_any": ["maillard"], "label": "LOUIS-CAMILLE MAILLARD",
     "queries": ["Louis-Camille Maillard", "Louis Camille Maillard chimiste"],
     "depicts": "photograph",
     "subject_basis": "Louis-Camille Maillard (1878-1936), who reported the "
                      "sugar-amino acid browning reaction in 1912."},
    {"key": "gas-chromatograph", "title_any": ["chromatograph"], "label": "GAS CHROMATOGRAPH",
     "queries": ["gas chromatograph instrument", "gas chromatography laboratory",
                 "gas chromatograph"],
     "depicts": "photograph",
     "subject_basis": "A gas chromatograph: the instrument that separates the crust's "
                      "aroma compounds."},
    {"key": "xray-diffraction", "title_any": ["diffract", "x-ray", "xray"], "label": "X-RAY DIFFRACTION",
     "queries": ["x-ray diffractometer", "x-ray powder diffraction instrument",
                 "x-ray diffraction pattern"],
     "depicts": "photograph",
     "subject_basis": "An X-ray diffraction instrument or pattern: how the six crystal "
                      "forms of cocoa butter are told apart."},
    {"key": "calorimeter", "title_none": ["neutron", "nevada", "bulkhead", "nuclear"], "title_any": ["calorimet"], "label": "CALORIMETER",
     "queries": ["differential scanning calorimeter", "differential scanning calorimetry",
                 "calorimeter laboratory"],
     "depicts": "photograph",
     "subject_basis": "A differential scanning calorimeter: how each crystal form's melting "
                      "point is measured."},
    {"key": "wheat-field", "title_none": ["van gogh", "painting", "reaper"], "title_any": ["wheat"], "label": "WHEAT",
     "queries": ["wheat field harvest", "wheat field", "wheat ears"],
     "depicts": "photograph",
     "subject_basis": "Wheat, the flour the dough is made from."},
]

UNILLUSTRATABLE: dict[str, dict] = {
    "cocoa-butter-form-v": {
        "why": "The form V crystal itself is seen only as a diffraction pattern or a "
               "polarised micrograph in copyrighted journal figures. The drawn "
               "cross-section device (visuals/food.py) stands in, and the narration says "
               "it is a drawing."},
    "loaf-xray-tomography": {
        "why": "Published X-ray tomography of a baking loaf is journal figures under "
               "copyright. The drawn cross-section device stands in."},
}

def unavailable_sources() -> list[dict]:
    """The owner-named free sources this host cannot reach, named in the manifest."""
    out = []
    for name, var in (("Pexels", "PEXELS_API_KEY"), ("Pixabay", "PIXABAY_API_KEY")):
        if not os.environ.get(var):
            out.append({"source": name, "why": f"${var} absent: the free search API "
                        f"needs an account key; Commons PD/CC0 is used alone"})
    return out


def harvest(dry_run: bool = False, only: list[str] | None = None) -> dict:
    man = M.harvest(dry_run=dry_run, only=only, subjects=SUBJECTS,
                    manifest=FOOD_MANIFEST, domain=DOMAIN, prefix="food",
                    unillustratable=UNILLUSTRATABLE)
    man["sources_unavailable"] = unavailable_sources()
    if not dry_run:
        json.dump(man, open(FOOD_MANIFEST, "w"), indent=2)
    return man


def verify_rights() -> int:
    """The STILLS this module writes. The food clip manifest is
    research/food_footage.py's manifest (its clips live on the Mac, never in
    git) and that module verifies it; reading it here failed every CI run
    with "<clip> is not on disk" (run of 2026-10-17, harvest_runs.json)."""
    return M.verify_rights(manifest=FOOD_MANIFEST)


if __name__ == "__main__":
    if "--verify" in sys.argv:
        print(f"food rights verified: {verify_rights()} assets, sha256 matched")
        raise SystemExit(0)
    dry = "--dry-run" in sys.argv
    only = None
    if "--missing" in sys.argv:
        have = set()
        if os.path.exists(FOOD_MANIFEST):
            have = {r["subject"] for r in json.load(open(FOOD_MANIFEST)).get("index", [])}
        only = [s["key"] for s in SUBJECTS if s["key"] not in have]
        print(f"retrying {len(only)} still subject(s)")
    # One subject per pass so the manifest is written after EACH subject:
    # a slow Commons day or a killed run keeps everything already verified
    # (harvest() merges into the manifest; the first full pass on 2026-10-13
    # was killed at 15 minutes holding ten verified files and no manifest).
    man = None
    for key in (only if only is not None else [s["key"] for s in SUBJECTS]):
        man = harvest(dry_run=dry, only=[key])
    if man:
        print(f"\n{man['asset_count']}/{len(SUBJECTS)} still subjects -> {FOOD_MANIFEST}")
    if not dry:
        print(f"rights verified: {verify_rights()} assets, sha256 matched on every file")
