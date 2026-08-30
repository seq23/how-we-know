"""The exclusion gate carries the owner's judgement, so it is proven negatively.

There is no weekly human topic approval any more: she gave blanket approval,
subject only to hard exclusions. That makes `loop/exclusions.py` the single
thing standing between the miner and a published video, and a gate nobody has
watched refuse anything is a decoration.

So this feeds it the three classes she named explicitly - nothing adult,
nothing morally grey, nothing with legal exposure (health/medical, personal
finance, legal advice) - plus every other taxonomy exclusion, and asserts each
is refused BY NAME. It then asserts legitimate topics still pass, because a
gate that refuses everything is equally useless.

It also asserts the taxonomy and the enforcement cannot drift apart, and that
an empty candidate set is a hard failure rather than a quiet pass.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import exclusions as E  # noqa: E402

# (topic, the exclusion it must be refused under). Her three named classes come
# first, because those are the ones she said out loud.
MUST_REFUSE = [
    # --- nothing with legal exposure: health / medical -------------------
    ("what supplements help you dive deeper", "Medical"),
    ("can deep sea sponges cure cancer", "Medical"),
    ("best diet for divers", "Medical"),
    ("does deep sea water treat depression", "Medical"),
    # --- nothing with legal exposure: personal finance -------------------
    ("how to invest in deep sea mining stocks", "Financial"),
    ("is ocean crypto a good investment", "Financial"),
    ("deep sea mining tax breaks explained", "Financial"),
    # --- nothing with legal exposure: legal advice -----------------------
    ("can you sue over ocean pollution", "Financial"),
    ("do I need a lawyer to salvage a shipwreck", "Financial"),
    # --- nothing adult ---------------------------------------------------
    ("deep sea creature sexual reproduction nude footage", "Adult"),
    ("nsfw ocean documentary", "Adult"),
    # --- nothing morally grey -------------------------------------------
    ("how whales are slaughtered for meat", "Morally grey"),
    ("shark finning footage", "Morally grey"),
    # --- the rest of the taxonomy ---------------------------------------
    ("megalodon is still alive proof", "Conspiracy"),
    ("mermaid caught on camera real", "Conspiracy"),
    ("bermuda triangle disappearances explained", "Conspiracy"),
    ("titan submersible victims final moments", "Recent tragedy"),
    ("the murder that sank a fishing boat", "True crime"),
    ("how to make a bomb underwater", "Firearms"),
    ("hold your breath longer than a free diver", "Dangerous acts"),
    ("deep sea documentary full episode download", "third-party footage"),
    ("ocean facts for kids nursery rhyme", "children"),
    ("did god create the deep sea", "Religion"),
    ("senator votes against ocean bill", "political"),
    ("submarine company is a scam", "defamation"),
    ("best casino near the ocean", "Gambling"),
    ("cocaine found in deep sea fish", "Drugs"),
    ("navy rifle used on a whale", "Firearms"),
]

MUST_ADMIT = [
    "how deep is the mariana trench",
    "why are deep sea creatures red",
    "how do scientists measure ocean depth",
    "what is a hydrothermal vent",
    "how does bioluminescence work",
    "what happens when a whale dies in the deep ocean",
    "why does black smoker water not boil",
    "what is the midnight zone",
    "how do submersibles survive the pressure",
    "what is the deepest fish ever recorded",
]


def check() -> list[str]:
    fails, examined = [], 0

    # ------------------------------------- no silently-disabled rule
    # A pattern ending in a LITERAL backslash-b is not a word boundary: it
    # requires an actual backslash character, so the whole rule matches
    # nothing. That happened to the morally-grey rule and left "shark finning"
    # admitted; nothing else in the suite would have caught it.
    for name, pats in E.ALL_RULES.items():
        for pat in pats:
            examined += 1
            if pat.endswith("\\\\b"):
                fails.append(f"rule {name!r} has a pattern ending in a LITERAL "
                             f"backslash-b, so it can never match")
            try:
                import re as _re
                _re.compile(E._inflect(pat))
            except _re.error as err:
                fails.append(f"rule {name!r} does not compile: {err}")

    # ---------------------------------------------- taxonomy <-> enforcement
    examined += 1
    for p in E.check_authority_coverage():
        fails.append(p)

    # ---------------------------------------------- every barred class refused
    for topic, expect in MUST_REFUSE:
        examined += 1
        d = E.decide(topic)
        if d.admitted:
            fails.append(f"ADMITTED a barred topic: {topic!r}")
            continue
        if expect.lower() not in d.rule.lower():
            fails.append(f"{topic!r} was refused under {d.rule!r}, expected "
                         f"something matching {expect!r}")
        if not d.matched:
            fails.append(f"{topic!r} was refused without naming what matched")

    # ---------------------------------------------- legitimate topics survive
    for topic in MUST_ADMIT:
        examined += 1
        d = E.decide(topic)
        if not d.admitted:
            fails.append(f"REFUSED a legitimate topic: {topic!r} "
                         f"(rule {d.rule!r}, matched {d.matched!r}) — a gate "
                         f"that refuses everything is as bad as no gate")

    # ---------------------------------------------- narration mode
    # Broad on topics, advice-shaped on prose. Both directions matter.
    for prose, should_admit in [
        ("satellite altimetry supplements the sonar record", True),
        ("pressure treatment of the raw data is applied", True),
        ("the risk to the vehicle is considerable", True),
        ("scientists debunked the claim that mermaids are real", True),
        ("there is no evidence that megalodon survives", True),
        ("you should take a supplement before diving", False),
        ("you should invest in this stock", False),
        ("mermaids are real and the government is hiding it", False),
        ("you can try this at home", False),
        ("the company deliberately lied about the hull", False),
    ]:
        examined += 1
        d = E.decide_body(prose)
        if d.admitted != should_admit:
            fails.append(f"narration gate got {prose!r} wrong: "
                         f"admitted={d.admitted}, expected {should_admit}")

    # ---------------------------------------------- domain gate
    examined += 1
    if E.decide("how deep is the ocean", domain="celebrity-gossip").admitted:
        fails.append("a topic in an unadmitted domain was let through")

    # ---------------------------------------------- empty is a HARD failure
    examined += 1
    if E.decide("").admitted:
        fails.append("an empty candidate was admitted")

    # An empty admitted set must stop the ranking stage, not pass it.
    examined += 1
    rank_src = (LOOP / "rank.py").read_text()
    if "NO_ADMITTED_TOPICS" not in rank_src:
        fails.append("loop/rank.py has no hard failure for an empty admitted "
                     "candidate set — it would exit 0 having selected nothing")

    # ---------------------------------------------- no human topic gate left
    examined += 1
    for f, banned in (("rank.py", "owner_action"),
                      ("prepare.py", "NOT_APPROVED")):
        src = (LOOP / f).read_text()
        if banned in src:
            fails.append(f"loop/{f} still blocks on a human topic decision "
                         f"({banned!r}); selection is automatic now")

    if examined == 0:
        fails.append("examined ZERO exclusion cases")
    print(f"inspected {examined} exclusion case(s): "
          f"{len(MUST_REFUSE)} barred, {len(MUST_ADMIT)} legitimate")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every barred class refused by name, every legitimate "
          "topic admitted" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
