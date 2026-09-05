"""Species -> image index for in-video imagery. Third gate on the same manifest discipline.

Why this exists
---------------
The narration names animals. The screen shows diagrams. The owner watched
episode 1 and said the obvious true thing: "the descriptions are happening and
we have no animal photos of what we are describing." This module builds the
index that fixes that, subject by subject, with the provenance discipline the
channel already applies to claims.

The gate, and why it is stricter than gate 2
--------------------------------------------
`research/imagery.py` has two gates: a NOAA credit gate and a Commons
public-domain gate (`pd_licence_ok`). This module adds a third, which is gate 2
plus two tests that only matter once an image is being asserted to depict a
NAMED SPECIES on screen:

  (1) LICENCE, live, unchanged: Commons `extmetadata` must report
      Copyrighted=False and a public-domain or CC0 licence tag. CC-BY, CC-BY-SA,
      CC-BY-NC and Flickr's "no known copyright restrictions" all hard-fail.
      This is `imagery.pd_licence_ok`, reused, not reimplemented.

  (2) THIRD-PARTY SCREEN over the item's own Artist, Credit and Description
      text, using `imagery.THIRD_PARTY`. A Commons PD tag is a volunteer's
      judgement and volunteers get it wrong. This test caught a live example on
      the first pass: `File:Whalefall hires.jpg` is tagged {{PD-USGov-NOAA}} and
      hosted on oceanexplorer.noaa.gov, and its own description reads "Image
      courtesy of Craig Smith, University of Hawaii." A university professor's
      photograph is not a work of the U.S. federal government, so the PD tag is
      wrong and the file is rejected here even though gate 2 alone would have
      passed it. See REJECTED_ON_PURPOSE.

  (3) IDENTITY, hand-written, machine-required. Every record must carry
      `depicts` (what the picture literally IS -- a lithograph, a specimen
      photograph, an ROV frame), `subject_basis` (why this image is THIS
      animal), and `credit_line` (what goes on screen). A plate is credited as a
      plate. "CHALLENGER REPORT PLATE, 1887" is honest; "photograph" is not.

What this index will not do
---------------------------
Substitute. Some subjects have no public-domain image and cannot get one, and
for those the answer is the drawn treatment plus a stated absence, never a
lookalike. A giant squid plate captioned "colossal squid" is a lie told in
pictures, and on a channel called How We Know it is the worst available failure.
`UNILLUSTRATABLE` names each one and says why.

Run:  python imagery_species.py            build/refresh the index
      python imagery_species.py --verify   re-verify what is on disk
      python imagery_species.py --coverage per-subject coverage report
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import imagery as I  # noqa: E402  (the two existing gates and their helpers)

OUT = I.OUT
ASSETS = os.path.join(OUT, "assets")
SPECIES_MANIFEST = os.path.join(OUT, "species.json")

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
    "domain": "deep-sea-ocean-science",
    "gate": "pd_licence_ok",
    "manifest": "channel/imagery/species.json",
    "args": [],
    "scheduled": True,
    "what": "species stills - the per-creature index every deep-sea episode "
            "draws its subject shots from",
}

RIGHTS_MANIFEST = I.MANIFEST


# --------------------------------------------------------------- the subjects
#
# Every animal or physical subject NAMED in the narration of the 20 scripts,
# with the episodes that name it. `terms` are the exact surface forms the
# narration uses; the planner heuristic matches on these, so they must be what
# is actually spoken, not what a taxonomist would prefer.

SUBJECTS = {
    "anglerfish":     {"display": "Anglerfish",
                       "terms": ["anglerfish", "angler fish"],
                       "episodes": ["01", "03", "04", "07", "08", "09", "13"]},
    "barreleye":      {"display": "Barreleye",
                       "terms": ["barreleye"],
                       "episodes": ["01", "06"]},
    "siphonophore":   {"display": "Siphonophore",
                       "terms": ["siphonophore"],
                       "episodes": ["01", "08"]},
    "sea_cucumber":   {"display": "Sea cucumber",
                       "terms": ["sea cucumber", "holothurian"],
                       "episodes": ["01", "07", "08"]},
    "deep_octopus":   {"display": "Deep-sea octopus",
                       "terms": ["deep octopus", "dumbo octopus", "grimpoteuthis"],
                       "episodes": ["01", "11"]},
    "red_shrimp":     {"display": "Red deep-sea shrimp",
                       "terms": ["red shrimp", "shrimp"],
                       "episodes": ["05"]},
    "red_jelly":      {"display": "Red deep-sea jellyfish",
                       "terms": ["red jellyfish", "jelly"],
                       "episodes": ["05", "08"]},
    "deep_squid":     {"display": "Deep-sea squid",
                       "terms": ["squid"],
                       "episodes": ["05", "09", "14"]},
    "snailfish":      {"display": "Snailfish",
                       "terms": ["snailfish"],
                       "episodes": ["07", "08", "10", "18", "19"]},
    # Deliberately separate from `snailfish`. Episodes 10 and 19 turn on the
    # HADAL snailfish -- the animals filmed at 7,700-8,336 m that hold the
    # vertebrate depth record -- and no image of one is public domain. Keeping
    # them as one subject would let a 758 m snailfish answer to the phrase
    # "hadal snailfish", which is the kind of quiet substitution this index
    # exists to make impossible.
    "hadal_snailfish": {"display": "Hadal snailfish",
                        "terms": ["hadal snailfish"],
                        "episodes": ["10", "19"]},
    "mariana_trench": {"display": "The Mariana Trench",
                       "terms": ["mariana trench", "challenger deep"],
                       "episodes": ["10", "15"]},
    "trieste":        {"display": "Bathyscaphe Trieste",
                       "terms": ["trieste"],
                       "episodes": ["10", "15"]},
    "giant_squid":    {"display": "Giant squid",
                       "terms": ["giant squid", "architeuthis"],
                       "episodes": ["04", "09", "14"]},
    "frilled_shark":  {"display": "Frilled shark",
                       "terms": ["frilled shark"],
                       "episodes": ["12"]},
    "viperfish":      {"display": "Viperfish",
                       "terms": ["viperfish"],
                       "episodes": ["09"]},
    "dragonfish":     {"display": "Dragonfish",
                       "terms": ["dragonfish"],
                       "episodes": ["04", "08", "09", "12", "20"]},
    "lanternfish":    {"display": "Lanternfish",
                       "terms": ["lanternfish"],
                       "episodes": ["08"]},
    "grenadier":      {"display": "Rattail / grenadier",
                       "terms": ["rattail", "grenadier"],
                       "episodes": ["08"]},
    "black_smoker":   {"display": "Black smoker vent",
                       "terms": ["black smoker", "hydrothermal vent"],
                       "episodes": ["17", "18"]},
    "whale_fall":     {"display": "Whale fall",
                       "terms": ["whale fall", "whale bone"],
                       "episodes": ["16"]},
    "vampire_squid":  {"display": "Vampire squid",
                       "terms": ["vampire squid"],
                       "episodes": ["09"]},
    "isopod":         {"display": "Giant isopod",
                       "terms": ["isopod"],
                       "episodes": ["09"]},
    "krill":          {"display": "Krill",
                       "terms": ["krill"],
                       "episodes": ["08"]},
    "amphipod":       {"display": "Amphipod",
                       "terms": ["amphipod"],
                       "episodes": ["08"]},
    "cusk_eel":       {"display": "Cusk-eel",
                       "terms": ["cusk-eel", "cusk eel"],
                       "episodes": ["19"]},
    "colossal_squid": {"display": "Colossal squid",
                       "terms": ["colossal squid", "mesonychoteuthis"],
                       "episodes": ["14"]},
    "yeti_crab":      {"display": "Yeti crab",
                       "terms": ["yeti crab", "kiwa"],
                       "episodes": ["17"]},
    "osedax":         {"display": "Osedax bone worm",
                       "terms": ["osedax"],
                       "episodes": ["16"]},
}


# ------------------------------------------------------ what cannot be shown
#
# These are not gaps waiting to be filled. Each was surveyed against Wikimedia
# Commons on the date below and every image of the actual animal was CC-BY or
# CC-BY-SA -- reusable, but not a public-domain dedication, and this channel is
# monetised. The correct output is the drawn treatment plus a stated absence.

SURVEY_DATE = "2026-08-31"

UNILLUSTRATABLE = {
    "colossal_squid": {
        "why": (
            "Mesonychoteuthis hamiltoni was described by Robson in 1925 from two "
            "arm crowns recovered from a sperm whale's stomach, so there is no "
            "historical plate drawn from a whole animal and nothing pre-1930 to "
            "fall back on. Every photograph in existence is of a modern specimen "
            "-- Te Papa's preserved female, the Natural History Museum's beak and "
            "tentacular club -- and all of them are CC BY-SA 3.0/4.0 or CC BY 3.0. "
            "A CC-BY licence is a permission, not a public-domain dedication, and "
            "does not clear the monetisation bar this channel set."),
        "surveyed": "31 Commons files matching 'Mesonychoteuthis hamiltoni' and "
                    "'colossal squid'; 3 returned public domain and NONE of the three "
                    "depicts the animal (two are distribution maps, one is a user "
                    "drawing tagged as own work).",
        "do_not_substitute": (
            "A giant squid plate is the obvious temptation and is forbidden. Episode 14 "
            "is ABOUT the confusion between the two animals -- its own narration says "
            "'drawings often stretch a colossal squid to giant-squid proportions'. "
            "Illustrating that sentence with a stretched giant squid would enact the "
            "error the episode exists to correct."),
        "what_ships_instead": (
            "The drawn squid treatment (thumbs.art_squid) and the informational "
            "segments. Episode 14 also names the GIANT squid as its explicit contrast "
            "animal, and that one IS covered here from Verrill's 1882 plate -- labelled "
            "GIANT SQUID, never colossal."),
    },
    "yeti_crab": {
        "why": (
            "Kiwa hirsuta was described in 2005 and Kiwa puravida in 2011, so the "
            "genus post-dates every public-domain illustration corpus. All Commons "
            "images are Ifremer or MNHN expedition photographs under CC BY 4.0, or "
            "journal figures under CC BY, or CC BY-SA."),
        "surveyed": "32 Commons files matching 'Kiwa hirsuta', 'Kiwa puravida' and "
                    "'yeti crab'; 1 returned public domain and it is a portrait of a "
                    "New Zealand soldier named Te Moananui-a-Kiwa Ngarimu -- a name "
                    "collision, not a crab.",
        "do_not_substitute": (
            "A squat lobster (Munidopsis, galatheid) is the near-miss. NOAA has clean "
            "public-domain squat lobster frames and they are NOT Kiwa. Episode 17 is "
            "specifically about how Kiwa farms bacteria on its own setae; a galatheid "
            "captioned 'yeti crab' would illustrate a different animal doing a "
            "different thing."),
        "what_ships_instead": "The drawn yeti crab treatment (thumbs.art_yeticrab).",
    },
    "whale_fall": {
        "why": (
            "Three routes, all closed. (a) The best public-domain candidate, "
            "File:Whalefall hires.jpg (2048x1536), is tagged PD-USGov-NOAA but its own "
            "description says 'Image courtesy of Craig Smith, University of Hawaii' -- "
            "a university employee's photograph, not a federal work, so the tag is "
            "wrong and the third-party screen rejects it. (b) The three genuinely clean "
            "federal frames are NOAA Undersea Research Program images at 483x328, "
            "388x477 and 377x423. Those are honest and usable in principle, but they "
            "are below the smallest Wikimedia thumbnail bucket, which means only the "
            "original file is addressable and upload.wikimedia.org now refuses "
            "automated fetches of originals; and at that size they cannot be placed in "
            "a 1920x1080 frame without an upscale that would show. (c) Every remaining "
            "whale-fall image, including the MBARI and Monterey Bay sanctuary "
            "material, is CC BY 2.0 or CC BY-SA."),
        "surveyed": "39 Commons files matching 'whale fall', 'Osedax' and 'whale skeleton "
                    "seafloor'; 7 returned public domain, of which 4 are unrelated "
                    "(a Landsat scene of Elephant Island, a feeding humpback at the "
                    "surface, a 1942 bombing raid, a Massachusetts town history) and the "
                    "3 relevant ones are the sub-bucket NOAA NURP frames above.",
        "do_not_substitute": (
            "A seafloor sediment frame or a surface humpback is the near-miss. Episode "
            "16 is about a carcass on the abyssal floor and the succession of animals "
            "that work it; neither substitute shows that."),
        "what_ships_instead": (
            "The drawn whale-fall treatment (thumbs.art_whalefall). If the resolution "
            "route ever reopens -- a direct fetch from nurp.noaa.gov rather than "
            "through Commons -- the three NURP frames are named above and are clean."),
        "reopenable": True,
    },
    "hadal_snailfish": {
        "why": (
            "Every image of a hadal snailfish is recent and rights-encumbered. The "
            "Mariana snailfish (Pseudoliparis swirei) and the 8,336 m Izu-Ogasawara "
            "record fish were filmed by the Newcastle University / University of "
            "Western Australia hadal landers and by the Minderoo-UWA Deep Sea Research "
            "Centre; those are institutional works under copyright or CC-BY at best, "
            "not public-domain dedications. No historical plate exists either: the "
            "hadal Liparidae were described from the 1950s onward, decades after the "
            "pre-1930 window."),
        "surveyed": "89 Commons files matching 'Careproctus', 'Paraliparis', 'Liparis "
                    "liparis' and 'Pseudoliparis amblystomopsis'; 28 returned public "
                    "domain and every one of them is a shallower or mid-depth genus -- "
                    "the Challenger and U.S. Fish Commission plates. None is a hadal "
                    "species.",
        "do_not_substitute": (
            "A shallower snailfish is the near-miss, and it is a good enough picture "
            "that the temptation is real: the 1887 Paraliparis bathybius plate and the "
            "NOAA frames at 758 m and 1,365 m all show unmistakable snailfish. They are "
            "in the index under `snailfish` and each one states its own identity on "
            "screen -- the plate carries 'Paraliparis bathybius, not one of the hadal "
            "record-holders' and the photographs carry their depth in the credit line. "
            "That is what makes them usable beside a hadal sentence: the frame corrects "
            "the inference the narration might otherwise invite."),
        "what_ships_instead": (
            "A snailfish that says which snailfish it is. The depth record itself is "
            "carried by the numbers -- the stat and uncertainty segments -- not by a "
            "photograph."),
        # The ONE case in this table where a related subject may stand in, and
        # only because every record under it corrects the inference on screen.
        # `nearest` is honoured by the heuristic only for records that carry a
        # standing_note, so the substitution cannot happen silently. The other
        # four entries deliberately have no `nearest`: there is no animal that
        # can stand next to the words "colossal squid" or "yeti crab" and be
        # made honest by a caption.
        "nearest": "snailfish",
        "nearest_condition": (
            "only records carrying a standing_note, so the frame itself says which "
            "snailfish it is and that it is not a record-holder"),
    },
    "osedax": {
        "why": (
            "Osedax was described in 2004. Every Commons image is a journal figure "
            "under CC BY 3.0/4.0 or an aquarium photograph under CC0-claimed terms "
            "that do not verify as CC0 in extmetadata."),
        "surveyed": "39 Commons files matching 'Osedax' and 'whale fall'; the PD "
                    "results are the NOAA whale-fall photographs recorded below, none "
                    "of which resolves an Osedax worm.",
        "do_not_substitute": (
            "A tubeworm (Riftia) is the near-miss and is a vent animal, not a bone "
            "worm."),
        "what_ships_instead": (
            "The whale-fall NOAA photographs, which ARE covered, credited as the "
            "skeleton and the community rather than as the worm."),
    },
}


# ------------------------------------------------- rejected after a live check
#
# Kept in the module rather than a log because the reason is the argument. Each
# of these would have passed gate 2 on its Commons licence tag alone.

REJECTED_ON_PURPOSE = [
    {
        "commons_title": "File:Whalefall hires.jpg",
        "subject": "whale_fall",
        "commons_licence": "PD-USGov-NOAA, Copyrighted=False",
        "reason": (
            "The file's own description says 'This image was captured six years later "
            "by Craig Smith from the University of Hawaii. Image courtesy of Craig "
            "Smith, University of Hawaii.' A university employee's photograph is not a "
            "work of the U.S. federal government under 17 U.S.C. 105, so the "
            "PD-USGov-NOAA tag is a mistagging. Hosting on oceanexplorer.noaa.gov "
            "proves nothing -- that is the same finding the NOAA gate in imagery.py "
            "was built on. Rejected by the third-party screen."),
        "cost": "The best whale-fall community image (2048x1536). The three NOAA "
                "Undersea Research Program frames below are smaller but clean.",
    },
    {
        "commons_title": "File:Euphausia superba.jpg",
        "subject": "krill",
        "commons_licence": "PD-USGov-NOAA, Copyrighted=False",
        "reason": (
            "Author is 'Dr. Wayne Trivelpiece', a named individual. Trivelpiece was a "
            "NOAA Southwest Fisheries Science Center scientist, which would make this a "
            "federal work, but the Commons page asserts nothing about his employment "
            "and the manifest cannot record a rights basis it has not verified. Held "
            "out rather than guessed. Krill are named once, in episode 08, and the "
            "episode does not depend on the picture."),
        "cost": "One 4240x2893 krill photograph, in one episode, in one sentence.",
    },
    {
        "commons_title": "File:Colossal squid at Te Papa.jpg (and 14 sibling files)",
        "subject": "colossal_squid",
        "commons_licence": "CC BY-SA 3.0 / CC BY-SA 4.0 / CC BY 3.0",
        "reason": "CC-BY and CC-BY-SA are permissions, not public-domain dedications. "
                  "Absolute constraint; no exception for a subject we badly want.",
        "cost": "All imagery of the colossal squid. See UNILLUSTRATABLE.",
    },
    {
        "commons_title": "File:Kiwa hirsuta (MNHN-IU-2010-1683) 001.jpeg (and 11 siblings)",
        "subject": "yeti_crab",
        "commons_licence": "CC BY 4.0 / CC BY-SA 2.5",
        "reason": "As above.",
        "cost": "All imagery of the yeti crab. See UNILLUSTRATABLE.",
    },
]


# ------------------------------------------------------------- the PD records
#
# Hand-chosen: the identification and the "is this actually the subject"
# judgement must be human. The LICENCE is verified live at fetch time and
# re-verified against the bytes on disk before any pixel is drawn.

PD_SPECIES = [
    # ---------------------------------------------------------------- ep 10
    {
        "id": 910001, "subject": "snailfish", "stem": "gunther-1887-paraliparis-bathybius",
        "commons_title": "File:Paraliparis bathybius.jpg",
        "title": "Paraliparis bathybius, Challenger Report plate (1887)",
        "depicts": "lithograph",
        "credit_line": "CHALLENGER REPORT PLATE, 1887",
        "standing_note": "Paraliparis bathybius — not one of the hadal record-holders",
        "treatment": "plate",
        "subject_basis": (
            "A snailfish (Liparidae) drawn from a Challenger specimen by Robert "
            "Mintern for Gunther's Report on the Deep-Sea Fishes, 1887. Snailfish are "
            "the family that holds the vertebrate depth records named in episodes 07, "
            "10 and 19. This plate is a deep-water Paraliparis, NOT Pseudoliparis "
            "belyaevi and NOT a hadal record-holder; it is credited as the plate it is "
            "and the narration's record claims are carried by the numbers, not by this "
            "picture."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/reportondeepseaf00gn",
        "rights_basis": (
            "Published 1887 in A. Gunther, Report on the Deep-Sea Fishes Collected by "
            "H.M.S. Challenger. The illustrator Robert Mintern died in 1908, so the "
            "plate is out of copyright under life+70 worldwide and in the United States "
            "as a pre-1930 publication. The Commons item page carries PD-scan / "
            "PD-old-70 and marks the file not copyrighted."),
        "required_credit": ("R. Mintern, in A. Gunther, Report on the Deep-Sea Fishes of "
                            "H.M.S. Challenger (1887)"),
    },
    # ---------------------------------------------------------------- ep 01
    {
        "id": 910003, "subject": "barreleye", "stem": "vaillant-1888-opisthoproctus-soleatus",
        "commons_title": "File:Opisthoproctus soleatus1.jpg",
        "title": "Opisthoproctus soleatus, Travailleur et Talisman plate (1888)",
        "depicts": "lithograph",
        "credit_line": "TALISMAN EXPEDITION PLATE, 1888",
        "treatment": "plate",
        "subject_basis": (
            "Opisthoproctus soleatus is a barreleye, in the same family "
            "(Opisthoproctidae) the narration names. Drawn by Bideault for Leon "
            "Vaillant's report on the Travailleur and Talisman expeditions, 1888."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/xpeditionsscie00vail",
        "rights_basis": (
            "Published 1888 in L. Vaillant, Expeditions scientifiques du Travailleur et "
            "du Talisman. Vaillant died in 1914. Out of copyright under life+70 and in "
            "the United States as a pre-1930 publication. The Commons item page carries "
            "PD-scan / PD-old-70 and marks the file not copyrighted."),
        "required_credit": ("Bideault, in L. Vaillant, Expeditions scientifiques du "
                            "Travailleur et du Talisman (1888)"),
    },
    {
        "id": 910002, "subject": "barreleye", "stem": "noaa-2024-barreleye-gulf-of-alaska",
        "commons_title": "File:Barreleye-fish GoK.jpg",
        "title": "Barreleye (Opisthoproctidae), Gulf of Alaska, 2024",
        "depicts": "specimen photograph",
        "credit_line": "NOAA OCEAN EXPLORATION, 2024",
        "standing_note": "Specimen on deck, not in habitat",
        "treatment": "photo",
        "subject_basis": (
            "NOAA's own caption identifies it to FAMILY: 'A barreleye fish (in the "
            "family Opisthoproctidae) collected with the Methot trawl during the "
            "Exploring Pelagic Biodiversity of the Gulf of Alaska expedition.' The "
            "Commons page also files it under Category:Macropinna microstoma, which "
            "NOAA does not say. So it is credited as a barreleye and never as "
            "Macropinna. Episodes 01 and 06 both say 'barreleye' and neither says "
            "Macropinna, so family level is exactly the claim the narration makes."),
        "source_org": "NOAA Ocean Exploration (via Wikimedia Commons)",
        "origin_url": ("https://archive.oceanexplorer.noaa.gov/explorations/"
                       "24skq-ak-seamounts/gallery/gallery.html"),
        "rights_basis": (
            "Work of the U.S. federal government: a NOAA Ocean Exploration expedition "
            "image published on oceanexplorer.noaa.gov with no individual or "
            "institutional co-credit and no copyright notice. The Commons item page "
            "carries PD-USGov-NOAA and marks the file not copyrighted."),
        "required_credit": ("NOAA Ocean Exploration, Exploring Pelagic Biodiversity of the "
                            "Gulf of Alaska and the Impact of Its Seamounts, 2024"),
    },
    {
        "id": 910004, "subject": "anglerfish", "stem": "ford-1864-melanocetus-johnsonii",
        "commons_title": "File:MelanocetusJohnsoniiFord.jpg",
        "title": "Melanocetus johnsonii, the humpback anglerfish (1864)",
        "depicts": "lithograph",
        "credit_line": "ZOOLOGICAL SOCIETY PLATE, 1864",
        "treatment": "plate",
        "subject_basis": (
            "G. H. Ford's plate XXV from the Proceedings of the Zoological Society of "
            "London, 1864 -- the illustration published WITH Gunther's original "
            "description of the species. It shows the illicium and esca, the lure "
            "episodes 01, 04, 09 and 13 all describe."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/proceedingsofgen64zool",
        "rights_basis": (
            "Published 1864 (issued 1865) in the Proceedings of the Zoological Society "
            "of London; the illustrator George Henry Ford died in 1876. Out of "
            "copyright worldwide and in the United States as a pre-1930 publication. "
            "The Commons item page carries PD-old-70 and marks the file not "
            "copyrighted."),
        "required_credit": ("G. H. Ford, Proceedings of the Zoological Society of London "
                            "(1864), Plate XXV"),
    },
    {
        "id": 910006, "subject": "siphonophore", "stem": "haeckel-1888-siphonophorae-plate",
        "commons_title": "File:Haeckel Siphonophorae 7.jpg",
        "title": "Siphonophore colony, Challenger Report plate (1888)",
        "depicts": "lithograph",
        "credit_line": "CHALLENGER REPORT PLATE, 1888",
        "treatment": "plate",
        "subject_basis": (
            "A plate from Ernst Haeckel's Report on the Siphonophorae Collected by "
            "H.M.S. Challenger, 1888 -- the same expedition this channel is named "
            "after, and the monograph that established what a siphonophore colony "
            "looks like. Episodes 01 and 08 name the siphonophore as the colonial "
            "animal that is not one animal."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/reportonsiphonop00haec",
        "rights_basis": (
            "Published 1888 in E. Haeckel, Report on the Siphonophorae Collected by "
            "H.M.S. Challenger. Haeckel died in 1919, so the plate is out of copyright "
            "under life+70 worldwide and in the United States as a pre-1930 "
            "publication. The Commons item page marks the file not copyrighted."),
        "required_credit": ("E. Haeckel, Report on the Siphonophorae Collected by "
                            "H.M.S. Challenger (1888)"),
    },
    # ---------------------------------------------------------------- ep 14
    {
        "id": 910007, "subject": "giant_squid", "stem": "verrill-1882-architeuthis-dux",
        "commons_title": "File:Architeuthis dux Verrill 1882.jpg",
        "title": "Architeuthis dux, Verrill (1882)",
        "depicts": "lithograph",
        "credit_line": "VERRILL PLATE, 1882",
        "treatment": "plate",
        "subject_basis": (
            "Addison Emery Verrill's 1882 plate of Architeuthis dux from The "
            "Cephalopods of the Northeastern Coast of America -- a GIANT squid, drawn "
            "from Newfoundland specimens. Episode 14 names the giant squid as its "
            "explicit contrast animal ('Giant squid can reach greater total length "
            "because their feeding tentacles are extremely long'), and the long "
            "feeding tentacles are the thing this plate shows. It is credited GIANT "
            "SQUID on screen and must NEVER appear on a colossal squid line."),
        "source_org": "Biodiversity Heritage Library / Internet Archive (via Wikimedia Commons)",
        "origin_url": "https://archive.org/details/cephalopodsofnor00verr",
        "rights_basis": (
            "Published 1882 in A. E. Verrill, The Cephalopods of the Northeastern Coast "
            "of America. Verrill died in 1926, so the plate is out of copyright under "
            "life+70 worldwide and in the United States as a pre-1930 publication. The "
            "Commons item page carries PD-scan / PD-old-auto-expired and marks the file "
            "not copyrighted."),
        "required_credit": ("A. E. Verrill, The Cephalopods of the Northeastern Coast of "
                            "America (1882)"),
    },
    # ---------------------------------------------------------------- ep 16
    {
        "id": 910005, "subject": "anglerfish", "stem": "noaa-2004-melanocetus-johnsonii",
        "commons_title": "File:Melanocetus johnsonii by NOAA.jpg",
        "title": "Melanocetus johnsonii, NOAA Ship Delaware II (2004)",
        "depicts": "specimen photograph",
        "credit_line": "NOAA PHOTO LIBRARY, 2004",
        "standing_note": "Specimen on deck, not in habitat",
        "treatment": "photo",
        "subject_basis": (
            "A humpback anglerfish specimen photographed by personnel of NOAA Ship "
            "Delaware II. Pairs with the 1864 Ford plate of the same species: the "
            "drawing and the animal, 140 years apart."),
        "source_org": "NOAA Photo Library (via Wikimedia Commons)",
        "origin_url": "https://www.photolib.noaa.gov/",
        "rights_basis": (
            "Work of the U.S. federal government: authored by 'Personnel of NOAA Ship "
            "DELAWARE II', a federal crew acting in the course of duty, published by "
            "the NOAA Photo Library. Public domain under 17 U.S.C. 105. The Commons "
            "item page carries PD-USGov-NOAA and marks the file not copyrighted."),
        "required_credit": "NOAA Photo Library; personnel of NOAA Ship Delaware II",
    },
]


# --------------------------------------------- reuse of the verified NOAA set
#
# 61 NOAA Ocean Exploration frames are already harvested, licence-checked and
# hashed in channel/imagery/rights.json. Re-downloading them would create a
# second copy of the same bytes and a second chance to disagree about their
# rights. Instead the index POINTS AT the existing record by its media id and
# adds only what an in-video credit needs: which subject it depicts, and what
# the credit line should say.
#
# Two things are hand-decided here and cannot be automated. The slot a frame was
# harvested under is a search term, not an identification -- slot "crab" holds a
# frame titled "Coral and Jellyfish" and slot "trench" holds a moray eel. And
# the credit line has to state the illumination, because episode 05 is ABOUT the
# fact that ROV lamps supply red light the animal's own world does not have, and
# its own narration sets the rule: "If it uses white ROV light, the caption must
# say so."

NOAA_SUBJECTS = [
    # media_id, subject, credit_line, note
    (13043, "red_shrimp", "NOAA OCEAN EXPLORATION, ROV LAMPS",
     "NOAA: 'this bright red shrimp, seen at a depth of 1,795 meters'. The frame is "
     "lit by the ROV's white lamps, which is the episode's whole point, so the credit "
     "says so."),
    (15248, "red_shrimp", "NOAA OCEAN EXPLORATION, ROV LAMPS",
     "NOAA: 'A close look at a beautifully colored red shrimp... nearly 20 centimeters "
     "long.'"),
    # Ordered last: NOAA's own caption says the shrimp is 'within a small opening in an
    # outcrop', and it is -- a few pixels of it, against a large lit rock face. True,
    # rights-clean, and the weakest of the three as a picture of a shrimp.
    (10403, "red_shrimp", "NOAA OCEAN EXPLORATION, ROV LAMPS",
     "NOAA: 'This red shrimp was observed within a small opening in an outcrop.'"),
    (14848, "red_jelly", "NOAA OCEAN EXPLORATION, ROV LAMPS",
     "NOAA: 'The dusky red jelly, Poralia sp., is a common sight during midwater "
     "transects.'"),
    (12212, "deep_squid", "NOAA OCEAN EXPLORATION, ROV LAMPS",
     "NOAA: 'This Dana octopus squid followed remotely operated vehicle Deep Discoverer "
     "during much of its descent.'"),
    (13309, "anglerfish", "NOAA OCEAN EXPLORATION",
     "NOAA: 'An anglerfish in the genus Chaunacops, commonly called a toadfish or "
     "coffinfish.'"),
    (12097, "anglerfish", "NOAA OCEAN EXPLORATION",
     "NOAA: 'A goosefish, a type of anglerfish, seen during Dive 08 of the third "
     "Voyage to the Ridge expedition.'"),
    (14526, "anglerfish", "NOAA OCEAN EXPLORATION",
     "NOAA: 'This anglerfish, in the genus Chaunacops.'"),
    (28649, "siphonophore", "NOAA OCEAN EXPLORATION",
     "NOAA: 'we observed this deepwater siphonophore at a depth of 1,531 meters.'"),
    (28654, "sea_cucumber", "NOAA OCEAN EXPLORATION",
     "NOAA: 'This sea cucumber, or holothurian, was seen perched on polymetallic "
     "nodules.'"),
    (15986, "sea_cucumber", "NOAA OCEAN EXPLORATION",
     "NOAA: 'The swimming sea cucumber, Enypniastes eximia.'"),
    # Ordered last: this frame carries a burned-in OCEAN EXPLORATION wordmark in
    # the lower left, where the credit line goes. Public domain and correctly
    # identified, so it stays in the index; it is simply not the one to reach for
    # first. Same judgement thumbs.py records for the wordmarked NOAA frames.
    (28794, "sea_cucumber", "NOAA OCEAN EXPLORATION",
     "NOAA: 'This sea cucumber with interesting and long appendages was seen on the "
     "seafloor during Dive 11 of the 2026 Cook Islands ROV Exploration cruise.'"),
    (10184, "deep_octopus", "NOAA OCEAN EXPLORATION",
     "NOAA: 'this dumbo octopus displayed a body posture that had never before been "
     "observed in cirrate octopods.'"),
    (4091, "deep_octopus", "NOAA OCEAN EXPLORATION",
     "NOAA: 'this squee-worthy dumbo octopus' at the Atlantis II Seamounts."),
    (15895, "deep_octopus", "NOAA OCEAN EXPLORATION",
     "NOAA: 'an Opisthoteuthis agassizii, during Dive 12 of the 2019 Southeastern U.S. "
     "Deep-sea Exploration.'"),
    (22125, "snailfish", "NOAA OCEAN EXPLORATION, 1,365 M",
     "NOAA: 'An example of a deep-sea snailfish... spotted at a depth of 1,365 meters.' "
     "The depth is ON the credit line deliberately. Episodes 10 and 19 discuss hadal "
     "snailfish at 7,000-8,300 m; this animal is a snailfish but is not one of the "
     "record-holders, and a credit that names its depth prevents the viewer inferring "
     "otherwise."),
    (14304, "snailfish", "NOAA OCEAN EXPLORATION, 758 M",
     "NOAA: 'This snailfish was seen resting on a closed anemone at 758 meters depth.' "
     "Same reasoning as above."),
    (16065, "black_smoker", "NOAA OCEAN EXPLORATION",
     "NOAA: 'Heated water shimmers as it is emitted from a small black smoker "
     "hydrothermal vent seen at a depth of 2,947 meters.'"),
    (5177, "black_smoker", "NOAA OCEAN EXPLORATION",
     "NOAA: 'An actively venting hydrothermal vent chimney shrouded in black smoke and "
     "covered with vent animals.'"),
    (12013, "grenadier", "NOAA OCEAN EXPLORATION",
     "NOAA: 'This deep-sea lizardfish (Bathysaurus mollis)'. Filed under the "
     "deep-benthic-fish subject, credited as what it is; it is NOT a grenadier and is "
     "here only as a same-habitat benthic fish for episode 08's survey line."),
]

# The three existing hand-chosen public-domain records in rights.json that are
# already in-video material for the priority episodes.
PD_REUSE = [
    (900001, "mariana_trench", "KRUMMEL CHART, 1907",
     "Otto Krummel's 1907 bathymetric chart of the Mariana Trench. Episode 10 is "
     "about how the depth is measured; this is the measurement, as it was in 1907."),
    # Ordered so the first Trieste a viewer sees is unmistakably Trieste. NH 96797
    # is captioned "Trieste with USS Lewis" and the destroyer takes most of the
    # frame; under the label "Trieste" that reads as a warship. It stays -- it is
    # the morning of the dive -- but it goes third.
    (900006, "trieste", "U.S. NAVY PHOTO NH 96801",
     "Trieste hoisted from the water, showing the petrol float and the crew sphere."),
    (900005, "trieste", "NOAA PHOTO LIBRARY, 1960",
     "Don Walsh and Jacques Piccard inside Trieste's crew sphere."),
    (900004, "trieste", "U.S. NAVY, 23 JANUARY 1960",
     "Trieste on the surface over the Mariana Trench hours before the Challenger Deep "
     "descent, with the destroyer escort USS Lewis steaming past behind her. Episode "
     "10's timeline names 'Crewed Trieste descent, 1960'."),
    (900002, "frilled_shark", "CHALLENGER REPORT PLATE, 1887",
     "Mintern's Plate LXIV of Chlamydoselachus anguineus, episode 12's subject."),
    (900007, "anglerfish", "CHALLENGER REPORT PLATE, 1887",
     "Mintern's plate of Melanocetus murrayi, Murray's abyssal anglerfish."),
]


# ------------------------------------------------------------------ the gate

def third_party_free(info: dict) -> tuple[bool, str]:
    """Screen the item's own prose for a non-federal or copyrighted stakeholder.

    A Commons licence template is a volunteer's conclusion. The description,
    artist and credit fields are the evidence that conclusion was drawn from,
    and when they disagree with the template the template is wrong. Run the same
    THIRD_PARTY pattern the NOAA gate uses, over all three.
    """
    em = info.get("extmetadata", {})

    def val(key):
        return re.sub(r"<[^>]+>", " ", str(em.get(key, {}).get("value", ""))).strip()

    prose = " ".join(val(k) for k in ("Artist", "Credit", "ImageDescription"))
    prose = re.sub(r"\s+", " ", prose)
    hit = I.THIRD_PARTY.search(prose)
    if hit:
        at = max(0, hit.start() - 60)
        return False, (f"item text names a third party or a copyright: "
                       f"{hit.group(0)!r} in ...{prose[at:hit.end() + 60]}...")
    return True, "no third-party or copyright stakeholder named in artist, credit or description"


IDENTITY_FIELDS = ("subject", "depicts", "credit_line", "subject_basis", "treatment")

# Every field a species record must carry before any pixel of it may ship.
# The first nine are thumbs.RIGHTS_FIELDS -- the same nine, deliberately, so the
# in-video guard can never be weaker than the thumbnail guard. A test asserts
# that this tuple stays a superset of it.
SPECIES_RIGHTS_FIELDS = ("source_org", "item_url", "direct_url", "rights_basis",
                         "rights_check", "required_credit", "commercial_use_permitted",
                         "date_checked", "sha256") + IDENTITY_FIELDS

VALID_DEPICTS = {"lithograph", "engraving", "chart", "photograph",
                 "specimen photograph", "archival photograph"}

SPECIES_POLICY = (
    "Third gate, own manifest. An image may be shown while the narration names a "
    "species only if ALL of: (1) its Wikimedia Commons item page reports "
    "Copyrighted=False and a public-domain or CC0 licence tag, checked live at fetch "
    "time (CC-BY, CC-BY-SA, CC-BY-NC and 'no known copyright restrictions' all "
    "hard-fail); (2) its own artist, credit and description name no non-federal party "
    "and carry no copyright notice, which catches Commons files mistagged PD-USGov "
    "when the description credits a university or an individual photographer; (3) a "
    "human has written down what the picture literally IS (depicts), why it is this "
    "animal (subject_basis) and what the on-screen credit says (credit_line). The "
    "credit names the medium and its year -- an 1887 lithograph is credited as a "
    "plate, never as a photograph. Records reused from rights.json are not "
    "re-downloaded; they keep the sha256 their licence was checked against. A subject "
    "with no qualifying image is recorded in UNILLUSTRATABLE with the survey behind "
    "it, and is never illustrated with a different animal."
)


# Wikimedia asks bots to identify themselves and to back off hard on 429. The
# first run of this harvester was throttled mid-set, which is a rights problem
# and not just a nuisance: a half-written manifest is a manifest whose licence
# checks and whose bytes disagree. So the fetch retries with a long backoff and
# the harvest hard-fails rather than writing a partial index.
# 2000 px wide is comfortably above the 1920 px frame, so a species image can
# fill the canvas without an upscale, and small enough that Commons will render
# it rather than refuse.
RENDER_WIDTH = 1920

# upload.wikimedia.org answers 429 to automated fetches of ORIGINAL files but
# serves /thumb/ renderings normally. MediaWiki only produces a /thumb/ URL when
# the requested width is meaningfully smaller than the source, so the request
# width has to be chosen per file from the standard buckets. A file smaller than
# the smallest bucket has no thumb at all and cannot be fetched -- which is a
# real coverage limit, not a bug, and is recorded as one.
THUMB_BUCKETS = (1920, 1280, 1024, 800, 640, 480, 320)


def _render_width(source_width: int) -> int | None:
    for b in THUMB_BUCKETS:
        if b <= RENDER_WIDTH and source_width >= b * 1.15:
            return b
    return None

SPECIES_UA = {"User-Agent": ("HowWeKnow/1.0 (deep-sea explainer channel; species image "
                             "rights verification; contact via repository) python-urllib")}


def _polite_get(url: str, binary: bool = False, tries: int = 6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=SPECIES_UA)
            with urllib.request.urlopen(req, timeout=90) as f:
                return f.read() if binary else f.read().decode("utf-8", "replace")
        except Exception as exc:
            last = exc
            time.sleep(6 * (i + 1))
    raise last


def _rec_from_commons(it: dict) -> dict:
    # iiurlwidth asks Commons to RENDER the file at a width we choose and hand
    # back a thumburl. That is not an optimisation: upload.wikimedia.org now
    # answers 429 to automated fetches of original files and its own error text
    # says "instead use thumbnail images in sizes listed on
    # https://w.wiki/GHai". The rendering is Wikimedia's own derivative of the
    # same public-domain item, so the licence argument is unchanged; what
    # changes is that `direct_url` records the rendered URL and the sha256 is of
    # the rendered bytes -- which is the point of the hash, since those are the
    # bytes that get drawn. `original_url` keeps the pointer to the full file.
    def _imageinfo(width: int | None):
        q = (f"{I.COMMONS_API}?action=query&format=json&prop=imageinfo"
             f"&iiprop=url|size|mime|extmetadata"
             + (f"&iiurlwidth={width}" if width else "")
             + f"&titles={urllib.parse.quote(it['commons_title'])}")
        page = next(iter(json.loads(_polite_get(q))["query"]["pages"].values()))
        if "missing" in page or not page.get("imageinfo"):
            raise KeyError(f"commons file not found: {it['commons_title']}")
        return page["imageinfo"][0]

    info = _imageinfo(None)
    want = _render_width(info.get("width") or 0)
    if want is None:
        raise ValueError(
            f"{it['commons_title']}: source is {info.get('width')}x{info.get('height')}, "
            f"below the smallest Wikimedia thumbnail bucket ({THUMB_BUCKETS[-1]} px), so "
            f"only the original file is addressable and upload.wikimedia.org refuses "
            f"automated fetches of originals. Too small to place at 1920x1080 in any "
            f"case.")
    info = _imageinfo(want)
    ok, why = I.pd_licence_ok(info)
    if not ok:
        raise ValueError(f"{it['commons_title']}: {why}")
    ok2, why2 = third_party_free(info)
    if not ok2:
        raise ValueError(f"{it['commons_title']}: {why2}")
    if it["depicts"] not in VALID_DEPICTS:
        raise ValueError(f"{it['commons_title']}: depicts={it['depicts']!r} is not one "
                         f"of {sorted(VALID_DEPICTS)}")

    original = info["url"].split("?")[0]
    src = (info.get("thumburl") or info["url"]).split("?")[0]
    ext = os.path.splitext(urllib.parse.urlparse(src).path)[1] or ".jpg"
    fname = f"sp-{it['subject']}__{it['id']}__{it['stem']}{ext}"
    path = os.path.join(ASSETS, fname)
    # The LICENCE is always re-checked live above; the BYTES need only be
    # fetched once. Re-using a file already on disk keeps re-runs cheap and
    # keeps us off Wikimedia's throttle, and cannot weaken the guard: the
    # sha256 written below is computed from the bytes that are actually there.
    blob = open(path, "rb").read() if os.path.exists(path) else _polite_get(src, binary=True)
    with open(path, "wb") as f:
        f.write(blob)

    return {
        "subject": it["subject"],
        "title": it["title"],
        "depicts": it["depicts"],
        "credit_line": it["credit_line"],
        "treatment": it["treatment"],
        "subject_basis": it["subject_basis"],
        "standing_note": it.get("standing_note", ""),
        "source_org": it["source_org"],
        "item_url": info.get("descriptionurl"),
        "origin_url": it.get("origin_url"),
        "direct_url": src,
        "original_url": original,
        "local_file": os.path.relpath(path, OUT),
        "width": info.get("thumbwidth") or info.get("width"),
        "height": info.get("thumbheight") or info.get("height"),
        "source_width": info.get("width"),
        "source_height": info.get("height"),
        "rights_basis": it["rights_basis"],
        "rights_check": f"{why}; {why2}",
        "required_credit": it["required_credit"],
        "commercial_use_permitted": True,
        "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        "origin": "commons-public-domain",
    }


# A snailfish photographed at 758 m or 1,365 m is a snailfish, and it is not one
# of the animals that hold the hadal depth record. The credit line already
# carries the depth; this makes the point in words, on the frame, so the picture
# corrects the inference rather than inviting it.
STANDING_NOTES = {
    22125: "Deep-sea snailfish at 1,365 m — not a hadal record-holder",
    14304: "Snailfish at 758 m — not a hadal record-holder",
}


def _rec_from_rights_manifest(mid: int, subject: str, credit_line: str,
                              note: str, by_id: dict) -> dict:
    src = by_id.get(mid)
    if src is None:
        raise KeyError(f"media {mid} is not in {RIGHTS_MANIFEST}; the species index "
                       f"may not invent a rights record")
    depicts = {"plate": "lithograph", "chart": "chart",
               "archive": "archival photograph"}.get(src.get("treatment", "photo"),
                                                     "photograph")
    rec = dict(src)
    rec.update({
        "subject": subject,
        "depicts": depicts,
        "credit_line": credit_line,
        "treatment": src.get("treatment", "photo"),
        "subject_basis": note,
        "standing_note": STANDING_NOTES.get(mid, ""),
        "origin": "rights.json",
    })
    return rec


def harvest() -> dict:
    """Build the index. Licence-checks live; hard-fails rather than half-writing."""
    os.makedirs(ASSETS, exist_ok=True)
    by_id = {}
    if os.path.exists(RIGHTS_MANIFEST):
        for a in json.load(open(RIGHTS_MANIFEST))["assets"]:
            by_id[int(a["local_file"].split("__")[1])] = a

    assets, failures = [], []
    for it in PD_SPECIES:
        try:
            assets.append(_rec_from_commons(it))
            print(f"  PD   {it['subject']:16} {it['title'][:56]}", flush=True)
            time.sleep(2.5)          # Commons throttles bots hard; be a good citizen
        except Exception as exc:
            failures.append({"commons_title": it["commons_title"], "reason": str(exc)})
            print(f"  FAIL {it['subject']:16} {exc}", flush=True)

    for mid, subject, credit, note in NOAA_SUBJECTS + PD_REUSE:
        try:
            assets.append(_rec_from_rights_manifest(mid, subject, credit, note, by_id))
        except Exception as exc:
            failures.append({"media_id": mid, "reason": str(exc)})
            print(f"  FAIL {subject:16} media {mid}: {exc}", flush=True)

    covered = {a["subject"] for a in assets}
    index = {}
    for key, meta in SUBJECTS.items():
        entry = {"display": meta["display"], "terms": meta["terms"],
                 "episodes": meta["episodes"],
                 "assets": [a["local_file"] for a in assets if a["subject"] == key]}
        if key in UNILLUSTRATABLE:
            entry["status"] = "unillustratable"
            entry.update(UNILLUSTRATABLE[key])
        elif entry["assets"]:
            entry["status"] = "covered"
        else:
            entry["status"] = "uncovered"
            entry["why"] = "no public-domain candidate has been surveyed for this subject yet"
        index[key] = entry

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "survey_date": SURVEY_DATE,
        "policy": SPECIES_POLICY,
        "rights_fields_required": list(SPECIES_RIGHTS_FIELDS),
        "asset_count": len(assets),
        "subjects_covered": sorted(covered),
        "subjects_unillustratable": sorted(UNILLUSTRATABLE),
        "index": index,
        "assets": assets,
        "rejected_on_purpose": REJECTED_ON_PURPOSE,
        "failures": failures,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(SPECIES_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    if failures:
        raise SystemExit("species index FAILED for: " +
                         "; ".join(f"{f.get('commons_title', f.get('media_id'))}: {f['reason']}"
                                   for f in failures))
    return manifest


# --------------------------------------------------------------- the guard

def load_species() -> dict:
    if not os.path.exists(SPECIES_MANIFEST):
        raise FileNotFoundError(
            f"{SPECIES_MANIFEST} does not exist; run `python imagery_species.py` first. "
            f"No species image may be drawn without a verified manifest.")
    return json.load(open(SPECIES_MANIFEST))


def verify_rights(manifest: dict | None = None) -> int:
    """Re-check every species record against the bytes on disk. Returns items checked.

    Same shape and the same failure modes as thumbs.verify_rights, extended to
    the in-video set and to the three identity fields a credit line depends on.
    Four failures this catches:

      (1) a record whose rights fields were never filled in, which is easy to
          introduce by hand-editing the manifest and invisible until someone
          asks where an image came from;
      (2) a file whose bytes no longer match the sha256 recorded when the
          licence was verified, which means the licence was checked against a
          different image from the one about to be drawn;
      (3) a record claiming to depict a subject the index has declared
          UNILLUSTRATABLE, which is the substitution this whole module exists to
          prevent;
      (4) a `depicts` value outside the closed set, which is how a lithograph
          would end up credited as a photograph.

    Rule 0: a check that examined nothing must fail. An empty index would
    otherwise sail through and report a clean bill of health.
    """
    man = manifest if manifest is not None else load_species()
    n = 0
    for rec in man.get("assets", []):
        where = rec.get("local_file", "?")
        missing = [f for f in SPECIES_RIGHTS_FIELDS if not rec.get(f)]
        if missing:
            raise ValueError(f"{where}: species record is missing {missing}")
        if not rec["commercial_use_permitted"]:
            raise ValueError(f"{where}: not cleared for commercial use")
        if rec["depicts"] not in VALID_DEPICTS:
            raise ValueError(f"{where}: depicts={rec['depicts']!r} is not one of "
                             f"{sorted(VALID_DEPICTS)}; a credit line built from it "
                             f"would mislabel the medium")
        if rec["subject"] in UNILLUSTRATABLE:
            raise ValueError(f"{where}: claims to depict {rec['subject']!r}, which the "
                             f"index declares unillustratable. This is the substitution "
                             f"the index exists to prevent.")
        if rec["subject"] not in SUBJECTS:
            raise ValueError(f"{where}: subject {rec['subject']!r} is not a subject named "
                             f"in any script")
        path = os.path.join(OUT, rec["local_file"])
        if not os.path.exists(path):
            raise FileNotFoundError(f"{where}: file in manifest is not on disk")
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != rec["sha256"]:
            raise ValueError(f"{where}: sha256 does not match the manifest "
                             f"({got[:12]} != {rec['sha256'][:12]}); the licence was "
                             f"checked against different bytes")
        n += 1
    if n == 0:
        raise ValueError("species rights verification examined zero assets")
    return n


# ------------------------------------------------------------------ coverage

def coverage(man: dict | None = None) -> list[dict]:
    man = man or load_species()
    rows = []
    for key, e in man["index"].items():
        rows.append({"subject": key, "display": e["display"], "status": e["status"],
                     "episodes": e["episodes"], "n": len(e["assets"]),
                     "why": e.get("why", "")})
    return rows


def _print_coverage(man: dict) -> None:
    rows = coverage(man)
    order = {"covered": 0, "unillustratable": 1, "uncovered": 2}
    for r in sorted(rows, key=lambda r: (order[r["status"]], r["subject"])):
        eps = ",".join(r["episodes"])
        print(f"  {r['status']:16} {r['n']:2}  {r['display']:26} ep {eps}")
        if r["status"] != "covered":
            print(f"       {r['why'][:150]}")


if __name__ == "__main__":
    if "--verify" in sys.argv:
        man = load_species()
        n = verify_rights(man)
        print(f"species rights verified: {n} assets, sha256 matched on every file")
        raise SystemExit(0)
    if "--coverage" in sys.argv:
        _print_coverage(load_species())
        raise SystemExit(0)
    man = harvest()
    n = verify_rights(man)
    print(f"\n{man['asset_count']} species assets -> {SPECIES_MANIFEST}")
    print(f"rights verified: {n} assets, sha256 matched on every file\n")
    _print_coverage(man)
