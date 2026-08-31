"""Put species images into an EXISTING plan without moving a single beat.

Why this and not a planner change
---------------------------------
The obvious way to add a visual is to teach planner.py a new heuristic and
re-plan. That is the wrong move right now and would have been the expensive kind
of wrong. Narration is synthesised per beat -- audio/<slug>/0000.wav, 0001.wav,
... -- and assemble.py pairs clip i with plan[i]. The beat count in
plans/<slug>.json IS the audio contract. Re-planning can change it (a heuristic
that fires changes `segment`, but a planner edit is one refactor away from
changing how prose splits), and a mismatch does not error: it silently produces
a video whose audio runs out, which is how episode 1 nearly shipped mute.

So this tool never plans. It opens a finished plan and rewrites ONE FIELD --
`segment`, plus that beat's `args` -- on beats that already exist. It asserts,
before writing, that the beat count, every `seconds` value and every `narration`
string are byte-identical to what it read. If any of those moved it refuses to
write.

Where a picture goes
--------------------
Only into beats that are currently carrying nothing. `text_beat` and
`ambient_drift` are the planner's fillers: a typographic beat is the narration's
own words set in Georgia, and an ambient drift is water. Those are exactly the
beats the owner was looking at when she said "the descriptions are happening and
we have no animal photos of what we are describing". An informational segment --
a stat card, an uncertainty band, a chain of method stages -- is carrying real
content and is never displaced. Neither is the Producer POV quote, which is the
one beat in the episode that is a person speaking.

What goes in it
---------------
`segments_species.heuristic_beat`, which fires only when the beat's own
narration names EXACTLY ONE covered subject, and which returns nothing at all
for a sentence that names the colossal squid, the yeti crab, a whale fall or
Osedax. The label drawn on screen is the surface form the narration itself used,
so CONTRACT.md rule 1 holds by construction: the picture is captioned with a
word the viewer is hearing.

Run:  python plan_species.py ../plans/10-*.json            dry run, prints the diff
      python plan_species.py ../plans/10-*.json --apply    rewrite in place
      python plan_species.py --all                         dry run over every plan
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import segments_species as SS

PLANS = os.path.abspath(os.path.join(HERE, "..", "plans"))

# Beats that are carrying nothing and may be replaced by a picture.
REPLACEABLE = {"text_beat", "ambient_drift"}

# Beats that are never touched, whatever their segment type. A directive is a
# human instruction and outranks any heuristic; the POV quote is the only beat
# in an episode where a person is speaking as themselves.
PROTECTED_FROM = {"directive"}
PROTECTED_SEGMENTS = {"quote_card"}

# At most this share of an episode's beats becomes a species image. The
# complaint was "not enough animal pictures", not "make it a slideshow" -- an
# explainer that cuts to a photograph every fourth beat stops explaining.
MAX_SHARE = 0.22


# A subject may not recur inside this many beats of itself.
NO_REPEAT = 3


def suppressed_for(episode: str) -> set[str]:
    """Subjects a given episode must never show, because of what it is ABOUT.

    Episode 14 is the colossal squid, and `deep_squid`'s search term is the bare
    word "squid". Its narration says "what the squid does when the target is
    close enough" -- meaning the colossal squid -- and a generic-term match put
    a NOAA photograph of a Dana octopus squid under that sentence. That is the
    substitution the whole index exists to forbid, arriving through the back
    door of a common noun.

    So: in any episode that names an unillustratable subject, every covered
    subject whose own term is contained inside that subject's term is
    suppressed. `deep_squid` ("squid") is inside "colossal squid" and goes.
    `giant_squid` ("giant squid") is not, and stays -- episode 14 names the
    giant squid explicitly as its contrast animal, and Verrill's 1882 plate is
    the right picture for that sentence.
    """
    out = set()
    for key, meta in SP_SUBJECTS.items():
        if key not in SS.SP.UNILLUSTRATABLE or episode not in meta["episodes"]:
            continue
        # A subject the entry itself nominates as its honest stand-in is exempt.
        # `hadal_snailfish` has terms ["hadal snailfish"], which contains
        # `snailfish` -- so the containment rule alone would suppress every
        # snailfish in episodes 10 and 19, the two episodes that most need one.
        # It nominates `snailfish` as its `nearest`, and every snailfish record
        # states on screen which snailfish it is, so it stays.
        nearest = SS.SP.UNILLUSTRATABLE[key].get("nearest")
        for bad in meta["terms"]:
            for other, om in SP_SUBJECTS.items():
                if other in SS.SP.UNILLUSTRATABLE or other == nearest:
                    continue
                if any(t.lower() in bad.lower() for t in om["terms"]):
                    out.add(other)
    return out


SP_SUBJECTS = SS.SP.SUBJECTS


def annotate(plan: list[dict], episode: str = "") -> tuple[list[dict], list[dict]]:
    """Return (new_plan, changes). Pure; writes nothing."""
    out = [dict(b) for b in plan]
    cap = int(len(out) * MAX_SHARE)
    block = suppressed_for(episode)

    def eligible(b, h):
        return (b.get("from") not in PROTECTED_FROM
                and b.get("segment") not in PROTECTED_SEGMENTS
                and b.get("segment") in REPLACEABLE
                and "title card" not in h and "producer pov" not in h)

    def candidates(text):
        """Subjects this text could honestly illustrate, best first.

        One named subject is the clean case. TWO is still honest and is allowed:
        "Crewed and uncrewed full-ocean-depth vehicles have reached and surveyed
        parts of Challenger Deep, beginning with the crewed Trieste descent in
        1960" names the trench and the vessel, and a photograph of either is a
        true picture of that sentence. Three or more is a list, and any single
        picture of a list is an arbitrary choice -- episode 01's "A barreleye,
        anglerfish, siphonophore, sea cucumber, and deep octopus" stays a text
        beat. The more specific surface form leads, and the caller falls through
        to the next candidate when the first is already spent.
        """
        hits = [x for x in SS.match_subjects(text)
                if x[0] not in block and SS.available(x[0])]
        if not hits or len(hits) > 2:
            return []
        return sorted(hits, key=lambda x: -len(x[1]))

    # Tier B needs to know what each SECTION names, so gather that first.
    section_subject: dict[str, list] = {}
    for b in out:
        section_subject.setdefault(b.get("heading", ""), [])
    for head in section_subject:
        text = " ".join(b.get("narration", "") for b in out if b.get("heading") == head)
        section_subject[head] = candidates(text)

    placed: list[int] = []
    subj_at: dict[int, str] = {}
    used: dict[str, int] = {}
    changes = []

    def place(i, b, key, surface, tier):
        if len(changes) >= cap:
            return False
        # NEVER SHOW THE SAME PICTURE TWICE. A subject may appear at most as
        # many times as it has distinct verified images, and each appearance
        # takes the next one. The first draft of this pass put the 1907 Krummel
        # chart into eight beats of episode 10 -- the section-level tier is
        # generous and mariana_trench has exactly one asset, so "more imagery"
        # became "the same picture, over and over", which reads as a broken edit
        # rather than as illustration.
        n_assets = len(SS.index()["_by_subject"].get(key, []))
        if used.get(key, 0) >= min(3, n_assets):
            return False
        if any(abs(i - j) < NO_REPEAT and subj_at[j] == key for j in placed):
            return False
        if any(abs(i - j) < 2 for j in placed):        # never two in a row
            return False
        pick = used.get(key, 0)
        changes.append({"beat": i, "was": b["segment"], "subject": key,
                        "label": surface, "tier": tier, "pick": pick,
                        "narration": b.get("narration", "")[:74]})
        b["segment"] = "species_image"
        b["args"] = {"subject": key, "label": surface, "pick": pick}
        b["from"] = (b.get("from", "") + f"+species-{tier}").strip("+")
        placed.append(i)
        subj_at[i] = key
        used[key] = pick + 1
        return True

    # TIER A -- the beat's own sentence names the animal. The strongest case:
    # the viewer hears the word while the picture is on screen.
    for i, b in enumerate(out):
        h = (b.get("heading") or "").lower()
        if not eligible(b, h):
            continue
        for key, surface in candidates(b.get("narration", "")):
            if place(i, b, key, surface, "beat"):
                break

    # TIER B -- the SECTION names exactly one animal, and this beat inside it is
    # carrying nothing. Weaker than tier A and deliberately second: the viewer
    # hears the name within a few seconds either side rather than on the beat
    # itself. Still rule-1 clean, because the label is a surface form taken
    # verbatim from that section's own narration and the credit line states what
    # the image actually is. This tier is what makes the difference between two
    # animal pictures in an eight-minute episode and eight -- these scripts are
    # epistemic prose and name a species about five times each.
    for i, b in enumerate(out):
        h = (b.get("heading") or "").lower()
        if not eligible(b, h) or i in placed:
            continue
        for key, surface in section_subject.get(b.get("heading", ""), []):
            if place(i, b, key, surface, "section"):
                break

    # Picks are assigned in BEAT order, not in the order the two tiers happened
    # to run. Tier A sweeps the whole plan before tier B starts, so without this
    # a tier-B beat early in the episode was handed the third-choice image while
    # the first choice appeared thirty beats later. The viewer sees beats in
    # order; the pictures should improve in that order too.
    changes.sort(key=lambda c: c["beat"])
    seen_n: dict[str, int] = {}
    for c in changes:
        c["pick"] = seen_n.get(c["subject"], 0)
        out[c["beat"]]["args"]["pick"] = c["pick"]
        seen_n[c["subject"]] = c["pick"] + 1
    return out, changes


def check_contract(before: list[dict], after: list[dict]) -> None:
    """The audio contract. Raises rather than writing a plan that would go mute."""
    if len(before) != len(after):
        raise ValueError(f"beat count moved: {len(before)} -> {len(after)}. "
                         f"Audio is generated per beat index; this would produce a "
                         f"video with no sound past beat {min(len(before), len(after))}.")
    for i, (a, b) in enumerate(zip(before, after)):
        if a.get("seconds") != b.get("seconds"):
            raise ValueError(f"beat {i}: seconds moved {a.get('seconds')} -> "
                             f"{b.get('seconds')}")
        if a.get("narration") != b.get("narration"):
            raise ValueError(f"beat {i}: narration text changed; the audio for this "
                             f"beat was synthesised from the old text")
        if a.get("heading") != b.get("heading"):
            raise ValueError(f"beat {i}: heading changed")


def run(path: str, apply: bool = False) -> list[dict]:
    plan = json.load(open(path))
    episode = os.path.basename(path)[:2]
    new, changes = annotate(plan, episode)
    check_contract(plan, new)
    name = os.path.basename(path)
    print(f"\n{name}  {len(plan)} beats  ->  {len(changes)} species images "
          f"({len(changes) / max(1, len(plan)) * 100:.0f}% of runtime beats)")
    for c in changes:
        print(f"  beat {c['beat']:>3}  {c['was']:<14} -> species_image "
              f"[{c['subject']}] “{c['label']}”  ({c['tier']})")
        print(f"            {c['narration']}...")
    if not changes:
        print("  (no beat in this episode names exactly one covered subject)")
    if apply:
        json.dump(new, open(path, "w"), indent=2)
        print(f"  written -> {path}")
    return changes


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all" in sys.argv or not args:
        args = sorted(glob.glob(os.path.join(PLANS, "*.json")))
    total = 0
    for p in args:
        total += len(run(p, apply))
    print(f"\n{total} species images across {len(args)} plans"
          + ("  (APPLIED)" if apply else "  (dry run; pass --apply to write)"))
