"""One thumbnail entry point for EVERY domain, keyed by the episode's slug.

    python visuals/thumbs_for.py <slug> [<slug> ...]      build these
    python visuals/thumbs_for.py --list                   domain -> builder

WHY THIS EXISTS. Until 2026-10-03 `bin/batch-session.sh:thumb_one()` held its
own table of which domain had a thumbnail builder: one line for
materials-and-manufacturing and a `*)` that printed "<domain> has no builder
wired here; skipping" for everything else - including deep-sea-ocean-science,
the channel's FIRST domain. `visuals/thumbs.py` IS the deep-sea builder, but
it is keyed to the twenty hand-numbered episodes ("01".."20"), so the first
unnumbered deep-sea episode to come off the render queue
(how-do-scientists-know-about-other-galaxies) was rendered, captioned and
pushed to R2 with no thumbnail, and the cloud upload lane refused it every
morning for a week ("render is shelved but its thumbnail is not") until the
NOTHING_SHELVED stop paged the owner (#143). Two components each kept their
own list of domains - the batch script's `case` and the planner's domain
table - and the batch's list was the shorter one.

THE REGISTRY BELOW IS THE ONE LIST. `builder_for(domain)` is what the batch
calls, for every rendered episode regardless of domain, and
loop/tests/test_thumbnail_builder_every_domain.py proves that every domain the
channel allocates slots to, and every domain any script declares, resolves to
a builder here. Adding a domain without a thumbnail path fails that test
before it fails on the shelf.

HOW A DEEP-SEA EPISODE IS BUILT.

  numbered (NN-…)   thumbs.EPISODES[NN], the hand-written spec: unchanged.
  unnumbered        derived from the episode's own words, the same way
                    visuals/thumbs_materials.derive_spec does it for materials:
                      hook     first clause of `## Direct-answer lock`, so the
                               card cannot claim more than the script proves;
                      picture  Route A ONLY when exactly one imagery slot in
                               channel/imagery/rights.json is named by the
                               episode's declared topic (slug + hook) - the
                               `trench` photographs for an episode about the
                               Mariana Trench, the `vent` set for hydrothermal
                               vents. Zero or several matches -> Route B, the
                               typographic card on the domain's own palette,
                               which asserts nothing and so cannot assert
                               something false. A galaxy episode filed under
                               deep sea gets type, not a borrowed anglerfish.
                    Every Route A candidate passes the same rights
                    re-verification (sha256 against the manifest), the same
                    saliency framing and the same MIN_SUBJECT_ENERGY refusal
                    as the hand-made twenty - `thumbs.build()` is the one
                    place that draws.

Output contract, identical for every domain: channel/thumbnails/<slug>.jpg,
1280x720 progressive JPEG, under the 2 MB YouTube limit (thumbs.py's own
check), built only when renders/<slug>-final.mp4 exists, because a thumbnail
is one half of the pair the upload lane needs and the other half is the
proof the episode is finished.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "loop"))

SCRIPTS = os.path.join(ROOT, "scripts")
RENDERS = os.path.join(ROOT, "renders")
OUT = os.path.join(ROOT, "channel", "thumbnails")
RIGHTS = os.path.join(ROOT, "channel", "imagery", "rights.json")

DEEP_SEA = "deep-sea-ocean-science"
MATERIALS = "materials-and-manufacturing"
YOUTUBE_THUMB_LIMIT = 2_000_000          # bytes; thumbs.py reports over this


# ------------------------------------------------------------------ the hook
def hook_from_script(path: str) -> str:
    """First clause of `## Direct-answer lock`, cut to feed-size length.

    Same derivation visuals/thumbs_materials.derive_spec uses, lifted here so
    both domains read the claim from the same place in the same way. Returns
    "" when the script has no lock - and "" is a refusal downstream, not a
    blank card.
    """
    if not os.path.exists(path):
        return ""
    text = open(path, encoding="utf-8").read()
    body = text.split("## Direct-answer lock", 1)
    if len(body) < 2:
        return ""
    para = body[1].split("##", 1)[0].strip()
    first = re.split(r"(?<=[.!?])\s+", para)[0] if para else ""
    hook = re.split(r",| - |—|:", first)[0].strip().rstrip(".")
    if len(hook) > 46:
        hook = hook[:46].rsplit(" ", 1)[0]
    # A cut that lands on "through" or "of" is a sentence stopped mid-air, not
    # a claim. Drop trailing function words until the card ends on a word that
    # carries meaning; the title holds the rest of the sentence.
    words = hook.split()
    while len(words) > 2 and words[-1].lower() in DANGLING:
        words.pop()
    return " ".join(words)


DANGLING = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "with",
            "from", "and", "or", "by", "through", "that", "which", "as",
            "into", "than", "is", "are", "was", "were", "be", "because"}


def kicker_from_slug(slug: str) -> str:
    return re.sub(r"^\d\d-", "", slug).replace("-", " ").title()


# ------------------------------------------------------------- deep sea route
def _slot_words(slot: str) -> list[str]:
    return [w for w in slot.lower().split("_") if w]


def deep_sea_slot_for(slug: str, hook: str, slots: list[str]) -> tuple[str | None, str]:
    """Which imagery slot the episode's DECLARED topic names - or None, and why.

    A slot matches when every word of its name appears as a whole word in the
    slug or the hook ("vent" matches "hydrothermal vents", "frilled_shark"
    needs both words). Exactly one match is a picture; anything else is type.
    Matching on the whole script would pick `fish` for every deep-sea episode
    that mentions one, which is the lie-told-in-pictures this gate refuses.
    """
    topic = re.sub(r"[^a-z0-9]+", " ", f"{slug} {hook}".lower())
    words = set(topic.split())
    # `vents` names the vent slot; a plural is the same declared topic.
    stems = words | {w[:-1] for w in words if w.endswith("s") and len(w) > 3}
    hits = sorted(s for s in set(slots)
                  if all(w in stems for w in _slot_words(s)))
    if len(hits) == 1:
        return hits[0], f"topic names the {hits[0]!r} imagery slot"
    if not hits:
        return None, "no imagery slot is named by the episode's declared topic"
    return None, (f"{len(hits)} imagery slots match the declared topic "
                  f"({', '.join(hits)}); a thumbnail needs exactly one")


def derive_deep_sea_spec(slug: str, script_path: str | None = None) -> dict | None:
    """A thumbs.build()-shaped spec for an unnumbered deep-sea episode."""
    path = script_path or os.path.join(SCRIPTS, f"{slug}.md")
    hook = hook_from_script(path)
    if not hook:
        return None
    import thumbs                                          # noqa: PLC0415
    ok, blocked = thumbs.load_manifest() if os.path.exists(RIGHTS) else ({}, {})
    slot, why = deep_sea_slot_for(slug, hook, [a["slot"] for a in ok.values()])
    spec = {"kicker": kicker_from_slug(slug), "hook": hook, "derived": True,
            "slot": slot, "why": why}
    if slot:
        # Declared manifest order, as thumbs.build() expects: it takes the
        # FIRST candidate that frames a subject, not the brightest one.
        spec["media"] = sorted(mid for mid, a in ok.items() if a["slot"] == slot)
    return spec


def typographic_base():
    """The domain palette as a ground, no photograph. Palette follows
    HWK_DOMAIN through visuals/design.py, so one function serves every domain
    that declares colours in visuals/domains.py."""
    import thumbs_materials                                # noqa: PLC0415
    return thumbs_materials.typographic_base()


def build_deep_sea(slug: str, out_dir: str | None = None,
                   script_path: str | None = None) -> str:
    import thumbs                                          # noqa: PLC0415
    out_dir = out_dir or OUT
    m = re.match(r"^(\d\d)-", slug)
    assets, blocked = thumbs.load_manifest()
    thumbs.chosen.clear()
    thumbs.used.clear()
    if m and m.group(1) in thumbs.EPISODES:
        thumbs.verify_rights(assets, blocked)
        im, route = thumbs.build(m.group(1), thumbs.EPISODES[m.group(1)],
                                 assets, blocked)
    else:
        spec = derive_deep_sea_spec(slug, script_path)
        if not spec:
            raise KeyError(
                f"{slug}: the script has no '## Direct-answer lock' to take a "
                f"hook from, so there are no words to set. Refusing to ship a "
                f"card that says nothing.")
        if spec.get("media"):
            thumbs.verify_rights(assets, blocked)
            # A seed per slug, not per episode number: the number is what the
            # hand-made twenty key on, and an unnumbered slug has none.
            num = str(sum(map(ord, slug)) % 97 + 1)
            im, route = thumbs.build(num, dict(kicker=spec["kicker"],
                                               hook=spec["hook"],
                                               media=spec["media"]),
                                     assets, blocked)
        else:
            im = thumbs.compose(typographic_base(), spec["hook"],
                                spec["kicker"], side="left", credit=None)
            route = "B"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{slug}.jpg")
    im.save(path, "JPEG", quality=90, optimize=True, progressive=True)
    _check_output(path)
    return path


def build_materials(slug: str, out_dir: str | None = None,
                    script_path: str | None = None) -> str:
    import thumbs_materials                                # noqa: PLC0415
    if out_dir and out_dir != thumbs_materials.OUT:
        thumbs_materials.OUT = out_dir
    path = thumbs_materials.build_one(slug)
    _check_output(path)
    return path


def _check_output(path: str) -> None:
    from PIL import Image                                  # noqa: PLC0415
    size = os.path.getsize(path)
    with Image.open(path) as im:
        w, h = im.size
        fmt = im.format
    if fmt != "JPEG" or (w, h) != (1280, 720) or size > YOUTUBE_THUMB_LIMIT:
        raise ValueError(f"{path}: {fmt} {w}x{h} {size} bytes is not the "
                         f"1280x720 JPEG under {YOUTUBE_THUMB_LIMIT} bytes the "
                         f"upload lane attaches")


# ------------------------------------------------------------ THE ONE LIST
BUILDERS = {
    DEEP_SEA: build_deep_sea,
    MATERIALS: build_materials,
}


def builder_for(domain: str):
    """The builder for a domain, or a KeyError that names the gap."""
    try:
        return BUILDERS[domain]
    except KeyError:
        raise KeyError(
            f"no thumbnail builder is registered for domain {domain!r} in "
            f"visuals/thumbs_for.py BUILDERS - every allocated domain must "
            f"have one (loop/tests/test_thumbnail_builder_every_domain.py)"
        ) from None


def _loop_domains():
    """loop/domains.py, by path: visuals/domains.py (palettes) shadows the
    name on sys.path, and it is the loop's module that knows a slug's domain."""
    import importlib.util                                  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "loop_domains", os.path.join(ROOT, "loop", "domains.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def domain_of(slug: str) -> str:
    return (os.environ.get("HWK_DOMAIN")
            or _loop_domains().domain_of_slug(slug) or DEEP_SEA)


def _set_palette(dom: str) -> None:
    """visuals/design.py reads HWK_DOMAIN once, at import. A run that builds
    for two domains in one process must re-read it, or the second card ships
    on the first domain's colours."""
    os.environ["HWK_DOMAIN"] = dom
    if "design" in sys.modules and getattr(sys.modules["design"], "DOMAIN", dom) != dom:
        import importlib                                   # noqa: PLC0415
        importlib.reload(sys.modules["design"])


def build(slug: str, out_dir: str | None = None) -> str:
    dom = domain_of(slug)
    _set_palette(dom)
    return builder_for(dom)(slug, out_dir=out_dir)


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for d, fn in sorted(BUILDERS.items()):
            print(f"{d:<32} {fn.__name__}")
        return 0
    slugs = [a for a in argv if not a.startswith("--")]
    if not slugs:
        print(__doc__.split("\n\n", 1)[0])
        return 2
    made, refused = [], []
    for slug in slugs:
        if not os.path.exists(os.path.join(RENDERS, f"{slug}-final.mp4")):
            refused.append((slug, "no render yet"))
            continue
        try:
            p = build(slug)
            made.append(slug)
            print(f"  OK   {slug:<48} {os.path.getsize(p) / 1024:.0f} KB  "
                  f"({domain_of(slug)})")
        except Exception as e:                             # noqa: BLE001
            refused.append((slug, str(e)[:160]))
    for slug, why in refused:
        print(f"  SKIP {slug:<48} {why}")
    if not made:
        # Rule 0: never exit 0 having built nothing.
        print("\nNAMED STOP: no thumbnail was built. Either none of these "
              "episodes is rendered yet, or every build refused above and "
              "says why.")
        return 3
    print(f"\n{len(made)} thumbnail(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
