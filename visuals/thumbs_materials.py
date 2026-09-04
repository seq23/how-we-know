"""Thumbnails for materials-and-manufacturing episodes.

`visuals/thumbs.py` is keyed to deep-sea episode NUMBERS - its EPISODES table
is "01".."20", `slug_for` globs `scripts/<num>-*.md`, and its route B draws one
of three hand-made deep-sea illustrations (squid, whalefall, yeticrab). A
materials episode has no number and no drawn art, so it had no thumbnail path
at all: `backfill.local_assets` reported "no thumbnail built" and the three
finished materials episodes could not be uploaded, having been narrated,
rendered and rights-checked.

WHAT THIS REUSES, and why that matters more than the code it saves. It does not
reimplement a thumbnail. It builds the `assets` record and `spec` that
`thumbs.build()` already takes and calls it, so a materials thumbnail goes
through the SAME saliency framing, the same `frame_subject` fill, the same
`free_region_energy` measurement, the same MIN_SUBJECT_ENERGY Rule 0 refusal -
no frame ships without a subject in it - and the same credit drawn from the
item's own record rather than hardcoded. A second implementation is how the
two domains end up with different rules about what may ship, and the rule that
matters here is the one that refuses.

ROUTE A ONLY. Deep sea can fall back to drawn art; materials has none, and
inventing a decorative illustration for a channel whose premise is evidence
would be the wrong direction to solve this in. If a subject has no verified
public-domain photograph, this refuses and says so, and the episode does not
get a thumbnail until one exists.

Run:  python visuals/thumbs_materials.py                 build every one it can
      python visuals/thumbs_materials.py <slug> [<slug>]  build just these
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.environ.setdefault("HWK_DOMAIN", "materials-and-manufacturing")

import thumbs                                              # noqa: E402

OUT = os.path.join(ROOT, "channel", "thumbnails")
MATERIALS = os.path.join(ROOT, "channel", "imagery", "materials.json")

# kicker: the frame's small line. hook: the large one - the episode's own
# claim, not a tease. subject: which verified image carries it, by the key in
# channel/imagery/materials.json. Hand-written, because the pairing of a
# photograph with a claim IS the evidence judgement and is the one thing here
# that must not be generated.
SPECS: dict[str, dict] = {
    "how-are-microchips-made": dict(
        kicker="Photolithography", hook="Light draws the circuit",
        subject="cleanroom"),
    "how-does-quenching-harden-steel": dict(
        kicker="Quenching", hook="Hardness is trapped, not added",
        subject="micrograph-steel"),
    "how-do-self-healing-materials-work": dict(
        kicker="Self-healing", hook="The repair is carried, not made",
        subject="concrete"),
    "how-is-a-silicon-wafer-made": dict(
        kicker="Silicon", hook="One crystal, pulled from a melt",
        subject="silicon-wafer"),
    "what-is-a-semiconductor-made-of": dict(
        kicker="Semiconductors", hook="Pure silicon, deliberately spoiled",
        subject="silicon-wafer"),
    "why-is-steel-so-strong": dict(
        kicker="Steel", hook="Carbon in the way of the slip",
        subject="molten-steel"),
    "how-is-3d-printed-metal-made": dict(
        kicker="Metal printing", hook="Welded one layer at a time",
        subject="3d-printed-metal"),
    "why-is-carbon-fiber-so-strong": dict(
        kicker="Carbon fibre", hook="Strength that runs one way",
        subject="carbon-fiber"),
    "what-is-carbon-fiber-made-of": dict(
        kicker="Carbon fibre", hook="Cooked until only carbon is left",
        subject="carbon-fiber"),
    "what-is-concrete-made-of": dict(
        kicker="Concrete", hook="Mostly stone, held by a gel",
        subject="concrete"),
    "how-hot-does-a-welding-arc-get": dict(
        kicker="The arc", hook="Hotter than the metal it joins",
        subject="welding-arc"),
    "how-strong-is-graphene": dict(
        kicker="Graphene", hook="One atom thick, and it holds",
        subject="graphene-lattice"),
    "what-is-aerogel-made-of": dict(
        kicker="Aerogel", hook="Almost entirely air",
        subject="aerogel"),
}


def _assets_for(subject: str):
    """A thumbs-shaped rights record for one verified materials image."""
    man = json.load(open(MATERIALS))
    recs = [r for r in man["index"] if r["subject"] == subject]
    if not recs:
        raise KeyError(
            f"no verified public-domain image for subject {subject!r}. "
            f"Route B does not exist for this domain - see the module "
            f"docstring - so this episode gets no thumbnail until one does.")
    rec = dict(recs[0])
    # thumbs.build draws `thumb_credit`; materials records carry the fuller
    # credit_line used in-video. Short form for a 168px-wide feed tile.
    rec.setdefault("thumb_credit", rec["credit_line"].split(" — ")[-1]
                   if " — " in rec["credit_line"] else rec["credit_line"])
    mid = abs(hash(rec["local_file"])) % 10_000_000
    return {mid: rec}, mid


def build_one(slug: str) -> str:
    spec = SPECS.get(slug)
    if not spec:
        raise KeyError(
            f"{slug} has no thumbnail spec in visuals/thumbs_materials.py. "
            f"The kicker, the hook and WHICH photograph carries the claim are "
            f"an editorial judgement and are deliberately not generated.")
    assets, mid = _assets_for(spec["subject"])
    thumbs.chosen.clear()
    thumbs.used.clear()
    im, route = thumbs.build(str(mid % 97 + 1),
                             dict(kicker=spec["kicker"], hook=spec["hook"],
                                  media=[mid], fill=spec.get("fill", 0.70)),
                             assets, {})
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{slug}.jpg")
    im.save(path, "JPEG", quality=90, optimize=True, progressive=True)
    return path


def main(slugs: list[str] | None = None) -> int:
    if not slugs:
        slugs = sorted(SPECS)
    made, refused = [], []
    for slug in slugs:
        if not os.path.exists(os.path.join(ROOT, "renders", f"{slug}-final.mp4")):
            refused.append((slug, "no render yet"))
            continue
        try:
            p = build_one(slug)
            made.append((slug, os.path.getsize(p)))
            print(f"  OK   {slug:<36} {os.path.getsize(p)/1024:.0f} KB")
        except Exception as e:                             # noqa: BLE001
            refused.append((slug, str(e)[:110]))
    for slug, why in refused:
        print(f"  SKIP {slug:<36} {why}")
    if not made:
        # Rule 0: this must not exit 0 having produced nothing.
        print("\nNAMED STOP: no materials thumbnail was built. Either no "
              "materials episode is rendered yet, or every one that is has no "
              "verified public-domain image for its subject.")
        return 3
    print(f"\n{len(made)} thumbnail(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main([a for a in sys.argv[1:] if not a.startswith("-")]))
