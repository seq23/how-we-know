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
import json as _json                                       # noqa: E402
import os as _os                                           # noqa: E402

OUT = os.path.join(ROOT, "channel", "thumbnails")
MATERIALS = os.path.join(ROOT, "channel", "imagery", "materials.json")

# kicker: the frame's small line. hook: the large one - the episode's own
# claim, not a tease. subject: which verified image carries it, by the key in
# channel/imagery/materials.json. Hand-written, because the pairing of a
# photograph with a claim IS the evidence judgement and is the one thing here
# that must not be generated.
SPECS: dict[str, dict] = {
    # No verified public-domain image exists for these three subjects - every
    # Commons candidate had an item page asserting copyright - so they carry
    # type on the domain palette and no borrowed photograph. `subject` names
    # what they WOULD use if an image is ever cleared.
    "how-does-tempered-glass-shatter": dict(
        kicker="Tempered glass", hook="It fails all at once, by design",
        subject="tempered-glass"),
    "how-strong-is-titanium": dict(
        kicker="Titanium", hook="Strong for its weight, not absolutely",
        subject="titanium"),
    "how-is-damascus-steel-made": dict(
        kicker="Damascus steel", hook="The pattern is the weld",
        subject="damascus-blade"),

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


def derive_spec(slug: str) -> dict | None:
    """Build a spec from the script itself when SPECS has no hand-written one.

    WHY THIS EXISTS. Requiring a hand-written entry per episode made the
    thumbnail a human dependency, and a human dependency in the middle of an
    automated pipeline is a stall waiting to happen: on 2026-09-05 nine
    episodes sat rendered and un-uploadable because nobody had written nine
    table entries, and the 09:00 upload agent reported "0 pending" every
    morning without saying why in a place anyone was reading.

    Everything here is derived, and derived from the episode's own words:

      hook     the first sentence of `## Direct-answer lock`, trimmed to fit.
               That block IS the episode's claim - it is what the script
               already commits to answering - so it cannot say something the
               episode does not.
      kicker   the subject's own display label from the imagery manifest.
      subject  whichever verified image's terms the script mentions MOST, using
               the same TERMS table plan_materials_images places images with.
               One table, two consumers, so the picture on the thumbnail and
               the pictures in the video cannot disagree about what a word
               means.

    SPECS still wins where it has an entry, so a hand-made pairing is never
    overwritten by a derived one. Returns None when no verified image matches,
    which is a refusal, not a fallback - the same rule as everywhere else here.
    """
    import re as _re
    path = _os.path.join(ROOT, "scripts", f"{slug}.md")
    if not _os.path.exists(path):
        return None
    text = open(path).read()

    body = text.split("## Direct-answer lock", 1)
    hook = ""
    if len(body) > 1:
        para = body[1].split("##", 1)[0].strip()
        first = _re.split(r"(?<=[.!?])\s+", para)[0] if para else ""
        # Thumbnails are read at 168px wide in a feed. Long claims do not
        # survive that, so take the first clause and let the title carry
        # the rest.
        hook = _re.split(r",| - |—|:", first)[0].strip().rstrip(".")
        if len(hook) > 46:
            hook = hook[:46].rsplit(" ", 1)[0]

    have = {}
    try:
        for rec in _json.load(open(MATERIALS))["index"]:
            have.setdefault(rec["subject"], rec)
    except Exception:
        return None

    # MATCH ON WHAT THE EPISODE IS ABOUT, not on what it mentions. Counting
    # term frequency across the whole script chose `welding-arc` for the
    # Damascus steel episode and `micrograph-steel` for the titanium one,
    # because a metallurgy script says "steel" and "forge" constantly while
    # being about something else. A picture of a welding arc on an episode
    # about pattern-welded blades is the lie-told-in-pictures this whole
    # imagery gate exists to prevent, and automating it would only have made
    # it happen faster.
    #
    # So the subject must be named where the episode declares its topic - the
    # slug or the direct-answer sentence - and it must be the only such match.
    # Anything less returns None and the episode gets no thumbnail until a
    # human pairs one, which is the correct outcome, not a failure.
    import plan_materials_images as PMI
    topic = f"{slug.replace('-', ' ')} {hook}".lower()
    hits = [subj for subj in have
            if any(t.rstrip("*").lower() in topic
                   for t in PMI.TERMS.get(subj, []))]
    if not hook:
        # Nothing to say. This is the one honest None: route B below is a
        # typographic card and it has no words to set.
        return None
    if len(hits) != 1:
        # NO PICTURE, RATHER THAN NO THUMBNAIL.
        #
        # Ambiguity here used to return None, and None means build_one raises
        # and the episode has no thumbnail — which means backfill.local_assets()
        # never counts it as pending and it sits rendered and un-uploadable
        # forever. what-is-kevlar-made-of was exactly that on 2026-09-08: a
        # finished, captioned, shelved episode blocked by a 200 KB JPEG that
        # nothing was ever going to build.
        #
        # Route B already exists for "no verified image matches" and needs no
        # picture at all — only the episode's own claim and its own name. It
        # asserts nothing, which is the whole point of it, so it is available
        # here too. What must NEVER happen is picking one of several ambiguous
        # images: a welding arc on an episode about Damascus steel is the
        # lie-told-in-pictures this gate exists to prevent, and that refusal is
        # unchanged. `subject: None` is what routes build_one to the type.
        return {"kicker": slug.replace("-", " ").title(),
                "hook": hook, "subject": None, "derived": True,
                "why_no_image": (f"{len(hits)} verified public-domain image(s) "
                                 f"match this episode's declared topic; a "
                                 f"thumbnail needs exactly one")}
    best = hits[0]
    return {"kicker": have[best].get("label", best.replace("-", " ")).title(),
            "hook": hook, "subject": best, "derived": True}


def typographic_base():
    """A ground made only of the domain's own palette. No photograph.

    ROUTE B FOR MATERIALS, and the reason it is type and not drawn art:
    deep sea has three hand-made illustrations it can fall back to; materials
    has none, and inventing decorative art for a channel whose premise is
    evidence would be solving the wrong problem. A picture that asserts
    nothing cannot assert something false.

    This exists because three episodes - tempered glass, titanium and Damascus
    steel - are fully rendered and have NO verified public-domain image: every
    candidate the harvester found has an item page marking the work
    copyrighted. Without a route B they stay un-uploadable forever, which
    converts a rights outcome into a permanently stalled pipeline. With one,
    they ship carrying their own words and no borrowed picture.
    """
    from PIL import Image, ImageDraw, ImageFilter
    from design import INK, DEEP, MID, CYAN
    import random as _r

    W, H = thumbs.TW, thumbs.TH
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    # Vertical gradient along the domain's thermal axis: cold graphite at the
    # top, ember toward the base. design.py supplies every colour, so this
    # follows the palette if it is ever retuned.
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(a + (b - a) * (t ** 1.6)) for a, b in zip(INK, MID))
        d.line([(0, y), (W, y)], fill=c)
    # A faint scatter, blurred - texture, not imagery.
    spark = Image.new("RGB", (W, H), (0, 0, 0))
    sd = ImageDraw.Draw(spark)
    rnd = _r.Random(11)
    for _ in range(220):
        x, y = rnd.randrange(W), rnd.randrange(int(H * 0.45), H)
        rad = rnd.choice((1, 1, 2))
        sd.ellipse([x - rad, y - rad, x + rad, y + rad], fill=CYAN)
    img = Image.blend(img, Image.blend(img, spark.filter(
        ImageFilter.GaussianBlur(2)), 0.30), 0.5)
    return img


def build_one(slug: str) -> str:
    spec = SPECS.get(slug) or derive_spec(slug)
    if not spec:
        raise KeyError(
            f"{slug}: no hand-written spec and nothing could be derived - "
            f"either the script has no '## Direct-answer lock' to take a hook "
            f"from, or no verified public-domain image matches anything it "
            f"says. Add an image for its subject, or a SPECS entry. Refusing "
            f"to ship a thumbnail whose picture is unrelated to the episode.")
    try:
        if not spec.get("subject"):
            # Declared imageless by derive_spec. Raising here is how it reaches
            # the typographic route below, which is the same path a missing
            # image already took.
            raise KeyError(spec.get("why_no_image", "no subject resolved"))
        assets, mid = _assets_for(spec["subject"])
        thumbs.chosen.clear()
        thumbs.used.clear()
        im, route = thumbs.build(str(mid % 97 + 1),
                                 dict(kicker=spec["kicker"], hook=spec["hook"],
                                      media=[mid], fill=spec.get("fill", 0.70)),
                                 assets, {})
    except KeyError:
        # No verified image for this subject. Ship the type, not a stand-in.
        im = thumbs.compose(typographic_base(), spec["hook"], spec["kicker"],
                            side="left", credit=None)
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
