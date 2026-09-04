"""Put verified materials images into an EXISTING plan without moving a beat.

The materials counterpart of `visuals/plan_species.py`, and it follows that
module's rule exactly, for that module's reason: narration is synthesised per
beat — audio/<slug>/0000.wav, 0001.wav, … — and assemble.py pairs clip i with
plan[i], so the beat count in plans/<slug>.json IS the audio contract. This
tool never plans. It opens a finished plan and rewrites ONE FIELD, `segment`
plus that beat's `args`, on beats that already exist, and it re-uses
`plan_species.check_contract` rather than restating the invariant — one
definition of "this edit cannot make a video go mute", not two that can drift.

Why materials needs this at all
-------------------------------
The 18 materials plans came out at 15.3% `ambient_drift` and 44.5%
`text_beat`, against a 5.5%/35.5% baseline across the 20 shipped deep-sea
plans. The difference is that deep sea has `species_image`: 5.3% of its beats
are a photograph of the thing being described, placed by plan_species.py into
exactly these filler beats. Materials had no equivalent, so an episode about a
welding arc was carrying a quarter of its runtime as abstract drift.

What may be replaced, and what may not
--------------------------------------
Only `text_beat` and `ambient_drift` — the planner's fillers. An informational
segment is carrying real content and is never displaced, and that now includes
this domain's own device renderers, `thermal_ascent` and `process_column`.
Neither is the Producer POV quote, which is the one beat in an episode where a
person is speaking as themselves.

Matching is deliberately conservative. A beat qualifies only when its own
narration contains one of the subject's hand-written terms, and when exactly
ONE subject matches — a sentence that names three materials is a list, and any
single picture of a list is an arbitrary choice. Where nothing matches, the
drawn treatment stands. That is the whole point: an unrelated furnace under a
sentence about semiconductors would be a lie told in pictures.

Run:  python plan_materials_images.py ../plans/why-is-steel-so-strong.json
      python plan_materials_images.py --all
      python plan_materials_images.py --all --apply
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("HWK_DOMAIN", "materials-and-manufacturing")

import segments_materials as SM                            # noqa: E402
from plan_species import check_contract                    # noqa: E402

PLANS = os.path.abspath(os.path.join(HERE, "..", "plans"))

REPLACEABLE = {"text_beat", "ambient_drift"}
PROTECTED_FROM = {"directive"}
PROTECTED_SEGMENTS = {"quote_card", "thermal_ascent", "process_column"}

# At most this share of an episode's beats becomes a photograph. Same value and
# same reason as plan_species.MAX_SHARE: the complaint an image lane answers is
# "we are describing things and not showing them", not "make it a slideshow".
MAX_SHARE = 0.22

# A subject may not recur inside this many beats of itself.
NO_REPEAT = 6

# And it may appear at most this many times per episode PER IMAGE it actually
# has. The welding episode matched "welding" or "the arc" in twelve beats and
# the index holds exactly one verified arc photograph, so a first pass put the
# same picture on screen eleven times in eight minutes. A repeated photograph
# stops being evidence and becomes wallpaper, and the viewer reads it as the
# channel having one stock image - which is the opposite of the impression an
# evidence-first channel needs to give.
USES_PER_IMAGE = 2

# The words a beat must actually say. Hand-written per subject, because this is
# the identity claim: the picture is captioned with a word the viewer is
# hearing (visuals/CONTRACT.md rule 1), so the term list IS the caption
# vocabulary and may not be generated.
TERMS: dict[str, list[str]] = {
    "molten-steel":     ["molten steel", "molten iron", "liquid steel", "pouring",
                         "casting", "molten metal"],
    "welding-arc":      ["welding arc", "welding", "the arc", "welder"],
    "silicon-wafer":    ["wafer", "silicon ingot", "boule", "monocrystalline silicon"],
    "microchip-die":    ["silicon die", "die shot", "integrated circuit",
                         "microchip", "transistor"],
    "carbon-fiber":     ["carbon fibre", "carbon fiber", "fibre tow", "fiber tow",
                         "woven fabric"],
    "damascus-blade":   ["damascus", "pattern-welded", "wootz", "blade"],
    "blast-furnace":    ["blast furnace", "steel mill", "bessemer", "smelting",
                         "steelmaking"],
    "rust":             ["rust", "rust*", "corrosion", "corrod*", "iron oxide",
                         "patina"],
    "aerogel":          ["aerogel", "silica aerogel"],
    "graphene-lattice": ["graphene", "hexagonal lattice", "honeycomb lattice"],
    "titanium":         ["titanium"],
    "tempered-glass":   ["tempered glass", "toughened glass", "safety glass",
                         "shatter*"],
    "concrete":         ["concrete", "cement paste", "rebar", "reinforcing bar",
                         "aggregate"],
    "crystal-structure": ["unit cell", "crystal lattice", "body-centred cubic",
                          "face-centred cubic", "crystal structure"],
    "micrograph-steel": ["microstructure", "martensite", "pearlite", "ferrite",
                         "austenite", "grain boundary", "grain structure"],
    "3d-printed-metal": ["3d print*", "additive manufactur*", "laser melting",
                         "powder bed", "sinter*"],
    "cleanroom":        ["cleanroom", "clean room", "photolithograph*",
                         "fabrication plant", "semiconductor fab"],
    "kevlar-aramid":    ["kevlar", "aramid", "ballistic fabric"],
}


def available() -> set[str]:
    """Subjects that actually have a rights-verified image on disk."""
    try:
        return set(SM.material_index()["_by_subject"])
    except Exception:
        return set()


def match_subjects(text: str, have: set[str]) -> list[tuple[str, str]]:
    """(subject, the surface form the NARRATION used), longest term first.

    The label drawn on screen is the words the sentence itself used, so the
    caption is never a word the viewer is not hearing.
    """
    low = text.lower()
    hits = []
    for key in sorted(have):
        best = None
        for term in sorted(TERMS.get(key, []), key=len, reverse=True):
            # BOTH boundaries. With only a leading \b, "die" matched
            # "Diels-Alder" and put a photograph of a CPU die under a sentence
            # about reversible polymer chemistry, and "fab" matched "fabric".
            # That is the substitution this whole index exists to forbid,
            # arriving through a prefix. A term ending in "*" is an explicit
            # stem and keeps the open end.
            stem = term.endswith("*")
            core = term[:-1] if stem else term
            pat = r"\b" + re.escape(core) + ("" if stem else r"\b")
            m = re.search(pat, low)
            if m:
                best = text[m.start():m.end()]
                break
        if best:
            hits.append((key, best.strip()))
    return hits


def annotate(plan: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (new_plan, changes). Pure; writes nothing."""
    out = [dict(b) for b in plan]
    have = available()
    cap = int(len(out) * MAX_SHARE)
    changes: list[dict] = []
    subj_at: dict[int, str] = {}

    n_assets = {}
    try:
        for k, v in SM.material_index()["_by_subject"].items():
            n_assets[k] = len(v)
    except Exception:
        pass
    budget = {k: max(1, n * USES_PER_IMAGE) for k, n in n_assets.items()}
    used: dict[str, int] = {}

    def eligible(b, h):
        return (b.get("from") not in PROTECTED_FROM
                and b.get("segment") not in PROTECTED_SEGMENTS
                and b.get("segment") in REPLACEABLE
                and "title card" not in h and "producer pov" not in h)

    for i, b in enumerate(out):
        if len(changes) >= cap:
            break
        h = (b.get("heading") or "").lower()
        if not eligible(b, h):
            continue
        hits = match_subjects(b.get("narration", ""), have)
        # Exactly one subject, or the picture is an arbitrary pick from a list.
        if len(hits) != 1:
            continue
        key, surface = hits[0]
        if used.get(key, 0) >= budget.get(key, 1):
            continue
        if any(subj_at.get(j) == key for j in range(max(0, i - NO_REPEAT), i)):
            continue
        used[key] = used.get(key, 0) + 1
        b["segment"] = "material_image"
        b["args"] = {"subject": key, "label": surface.upper(), "pick": 0}
        b["from"] = (b.get("from", "") + "+material").strip("+")
        subj_at[i] = key
        changes.append({"beat": i, "subject": key, "label": surface,
                        "narration": b.get("narration", "")[:74]})

    # Picks assigned in BEAT order, so the pictures improve in the order the
    # viewer actually sees them (plan_species.py's rule, same reason).
    seen_n: dict[str, int] = {}
    for c in changes:
        c["pick"] = seen_n.get(c["subject"], 0)
        out[c["beat"]]["args"]["pick"] = c["pick"]
        seen_n[c["subject"]] = c["pick"] + 1
    return out, changes


def run(path: str, apply: bool = False) -> list[dict]:
    plan = json.load(open(path))
    new, changes = annotate(plan)
    check_contract(plan, new)          # ONE definition of the audio contract
    name = os.path.basename(path)
    print(f"\n{name}  {len(plan)} beats  ->  {len(changes)} material images "
          f"({len(changes) / max(1, len(plan)) * 100:.0f}% of beats)")
    for c in changes:
        print(f"  beat {c['beat']:>3}  -> material_image [{c['subject']}] "
              f"“{c['label']}”")
    if not changes:
        print("  (no beat names exactly one covered subject; drawn treatment stands)")
    if apply:
        json.dump(new, open(path, "w"), indent=2)
        print(f"  written -> {path}")
    return changes


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all" in sys.argv:
        import json as _j
        mats = [r["slug"] for r in _j.load(
            open(os.path.join(HERE, "..", "research",
                              "publish_order_materials.json")))["queue"]]
        paths = [os.path.join(PLANS, f"{s}.json") for s in mats]
        paths = [p for p in paths if os.path.exists(p)]
    else:
        paths = args
    if not paths:
        raise SystemExit("nothing to do: pass plan paths or --all")
    total = 0
    for p in paths:
        total += len(run(p, apply))
    print(f"\n{total} material image(s) across {len(paths)} plan(s)"
          f"{' — WRITTEN' if apply else ' — dry run, nothing written'}")
