"""Guard for the species-image index and its renderer.

The rule this file enforces is the channel's own: nothing is drawn that the
rights record does not support, and a check that examined nothing FAILS rather
than reporting a clean bill of health.

Every negative case here is proved by breaking the thing on purpose, showing the
failure names what broke, and restoring. A guard that has never been seen to
fail is not a guard.

Run:  python tests/test_species_imagery.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "visuals"))
sys.path.insert(0, os.path.join(HERE, "..", "research"))

import imagery_species as SP
import segments_species as SS
import thumbs as T

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   {detail}"))
    if not cond:
        FAIL.append(name)


def raises(fn, *a, **kw):
    """(did_raise, message)."""
    try:
        fn(*a, **kw)
        return False, ""
    except Exception as exc:
        return True, str(exc)


MAN = SP.load_species()

# ------------------------------------------------------------------ the guard
print("rights verification")

n = SP.verify_rights(MAN)
check("verifies every asset", n == len(MAN["assets"]), f"{n} of {len(MAN['assets'])}")
check("verifies a non-empty set", n > 0, f"n={n}")

# Rule 0: an empty index must FAIL, not pass on an empty loop.
empty = {"assets": []}
did, msg = raises(SP.verify_rights, empty)
check("Rule 0: zero assets hard-fails", did and "zero" in msg.lower(), msg)

# The in-video guard may never be weaker than the thumbnail guard.
check("rights fields are a superset of thumbs.RIGHTS_FIELDS",
      set(T.RIGHTS_FIELDS) <= set(SP.SPECIES_RIGHTS_FIELDS),
      f"missing {set(T.RIGHTS_FIELDS) - set(SP.SPECIES_RIGHTS_FIELDS)}")


# ------------------------------------------------- negative proof: bad sha256
print("negative proof: corrupted sha256")

victim = MAN["assets"][0]["local_file"]
broken = copy.deepcopy(MAN)
broken["assets"][0]["sha256"] = "0" * 64
did, msg = raises(SP.verify_rights, broken)
check("a wrong sha256 fails", did, "verification PASSED on a corrupted hash")
check("the failure names the file", victim in msg, msg[:160])
check("the failure explains what it means", "different bytes" in msg, msg[:160])

# restore and show green again
check("restored: verification is green again",
      SP.verify_rights(SP.load_species()) == len(MAN["assets"]))


# --------------------------------------------- negative proof: blank rights field
print("negative proof: blanked rights field")

for field in ("rights_basis", "required_credit", "item_url", "subject_basis",
              "credit_line", "depicts"):
    broken = copy.deepcopy(MAN)
    broken["assets"][0][field] = ""
    did, msg = raises(SP.verify_rights, broken)
    check(f"blank {field} fails", did, "verification PASSED on a blank rights field")
    check(f"the failure names {field}", field in msg, msg[:160])

check("restored: verification is green again",
      SP.verify_rights(SP.load_species()) == len(MAN["assets"]))


# ------------------------------------ negative proof: a file that is not on disk
print("negative proof: file missing from disk")

broken = copy.deepcopy(MAN)
broken["assets"][0]["local_file"] = "assets/does-not-exist.jpg"
did, msg = raises(SP.verify_rights, broken)
check("a missing file fails", did and "not on disk" in msg, msg[:160])


# ---------------------------------- negative proof: the substitution this prevents
print("negative proof: substituting a different animal")

broken = copy.deepcopy(MAN)
broken["assets"][0]["subject"] = "colossal_squid"
did, msg = raises(SP.verify_rights, broken)
check("a record claiming an unillustratable subject fails", did, "it PASSED")
check("the failure says substitution", "unillustratable" in msg, msg[:200])

broken = copy.deepcopy(MAN)
broken["assets"][0]["depicts"] = "photograph of a colossal squid"
did, msg = raises(SP.verify_rights, broken)
check("an out-of-set `depicts` fails", did and "mislabel" in msg, msg[:200])

check("restored: verification is green again",
      SP.verify_rights(SP.load_species()) == len(MAN["assets"]))


# ------------------------------------------------------------------ the index
print("index integrity")

for key in SP.UNILLUSTRATABLE:
    check(f"{key} carries no assets",
          not MAN["index"][key]["assets"], MAN["index"][key]["assets"])
    check(f"{key} states why", len(MAN["index"][key].get("why", "")) > 80)
    check(f"{key} names the substitution to avoid",
          bool(MAN["index"][key].get("do_not_substitute")))

check("every asset's subject is a subject some script names",
      all(a["subject"] in SP.SUBJECTS for a in MAN["assets"]))
check("every asset is cleared for commercial use",
      all(a["commercial_use_permitted"] for a in MAN["assets"]))
check("no asset is CC-BY or CC-BY-SA",
      not any("cc by" in a["rights_check"].lower() for a in MAN["assets"]),
      [a["local_file"] for a in MAN["assets"] if "cc by" in a["rights_check"].lower()])

# A plate credited as a photograph is the failure mode this whole credit system
# exists to prevent.
for a in MAN["assets"]:
    if a["depicts"] in ("lithograph", "engraving", "chart"):
        check(f"printed matter is not credited as a photograph: {a['credit_line']}",
              "photograph" not in a["credit_line"].lower())
        check(f"printed matter carries its year: {a['credit_line']}",
              any(ch.isdigit() for ch in a["credit_line"]))


# --------------------------------------------------------------- the renderer
print("renderer refuses to substitute")

for key in SP.UNILLUSTRATABLE:
    did, msg = raises(SS.resolve, key)
    check(f"resolve({key!r}) raises", did, "it returned an image record")
    check(f"resolve({key!r}) says do not substitute",
          "unillustratable" in msg or "substitute" in msg, msg[:140])

did, _ = raises(SS.resolve, "not_a_subject_at_all")
check("resolve on an unknown subject raises", did)
did, _ = raises(SS.resolve, None, "assets/not-in-the-index.jpg")
check("resolve on an unindexed asset raises", did)


# --------------------------------------------------------------- the directive
print("directive parsing")

covered = sorted(SS.index()["_by_subject"])
check("a covered subject parses to species_image",
      SS.parse_species_directive("species", covered[0])[0] == "species_image")
check("the label is carried through verbatim",
      SS.parse_species_directive("species", f"{covered[0]} | red shrimp")[1]["label"]
      == "red shrimp")
check("an unillustratable subject falls back (returns None)",
      SS.parse_species_directive("species", "colossal_squid") is None)
check("an uncovered subject falls back",
      SS.parse_species_directive("species", "viperfish") is None)
check("an empty directive falls back",
      SS.parse_species_directive("species", "") is None)
check("another directive kind is not claimed",
      SS.parse_species_directive("stat", "10,935 | METRES") is None)


# --------------------------------------------------------------- the heuristic
print("heuristic")

multi = ("A barreleye, anglerfish, siphonophore, sea cucumber, and deep octopus can "
         "occupy the same broad world while solving different versions of the same "
         "problem.")
check("a five-subject sentence gets no picture",
      SS.heuristic_beat(multi, []) is None)

one = "The anglerfish's lure is an energy strategy as much as a hunting trick."
got = SS.heuristic_beat(one, [])
check("a one-subject sentence gets a picture", got is not None and got["subject"] == "anglerfish")
check("the label is the narration's own word",
      got and got["label"].lower() in one.lower(), got)
check("a subject shown recently is not repeated",
      SS.heuristic_beat(one, ["anglerfish"]) is None)

# The generic-term trap: "colossal squid" and "giant squid" both contain
# "squid", which is deep_squid's own term. Before the longest-term rule, this
# sentence matched deep_squid and would have put a NOAA photograph of a Dana
# octopus squid under the words "colossal squid".
colossal = "Colossal squid are the heaviest known invertebrates."
check("an unillustratable subject is never matched",
      SS.heuristic_beat(colossal, []) is None, SS.match_subjects(colossal))
check("an unillustratable subject silences the whole sentence",
      SS.match_subjects(colossal) == [], SS.match_subjects(colossal))
check("a sentence naming BOTH colossal and giant squid gets no picture",
      SS.match_subjects("Colossal squid and giant squid are different animals.") == [],
      SS.match_subjects("Colossal squid and giant squid are different animals."))
check("giant squid beats the generic squid term",
      [k for k, _ in SS.match_subjects("Giant squid can reach greater total length.")]
      == ["giant_squid"],
      SS.match_subjects("Giant squid can reach greater total length."))
check("the yeti crab silences its sentence",
      SS.match_subjects("The yeti crab farms bacteria on its own setae.") == [])


# ------------------------------------------------- the beat count must not move
print("beat count invariance (the audio contract)")

import planner  # noqa: E402

SCRIPTS = os.path.join(HERE, "..", "scripts")
import glob  # noqa: E402

paths = sorted(glob.glob(os.path.join(SCRIPTS, "*.md")))
check("there are scripts to inspect", len(paths) >= 20, len(paths))

before = {os.path.basename(p): len(planner.parse(open(p).read())) for p in paths}
SS.install(planner)
after = {os.path.basename(p): len(planner.parse(open(p).read())) for p in paths}
moved = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
check("installing the graft moves no beat in any script", not moved, moved)

# and with a species directive actually present in the text
sample = ("## Narration\n\n### A section\n\n"
          "{{species: anglerfish | anglerfish}}\n"
          "The anglerfish lure is an energy strategy as much as a hunting trick, "
          "bringing prey close instead of swimming through darkness.\n")
beats = planner.parse(sample)
check("a {{species}} line is stripped from the prose, not spoken",
      beats and "{{" not in beats[0]["text"], beats[0]["text"] if beats else "")
check("a {{species}} line produces one beat, not two", len(beats) == 1, len(beats))
check("a {{species}} directive resolves to species_image",
      beats and beats[0]["directive"] and beats[0]["directive"][0] == "species_image",
      beats[0]["directive"] if beats else None)


# ---------------------------------------------------------------------- render
print("render")

rec = SS.resolve(covered[0])
im = SS.species_image(0.5, subject=covered[0], label="test")
check("renders a full frame", im.size == (1920, 1080), im.size)
check("renders RGB", im.mode == "RGB", im.mode)
px = list(im.convert("L").resize((32, 18)).getdata())
check("the frame is not blank", max(px) - min(px) > 40, f"range {max(px) - min(px)}")


print()
if FAIL:
    print(f"{len(FAIL)} FAILED: " + ", ".join(FAIL[:8]))
    sys.exit(1)
print("all species imagery checks passed")
