"""Every domain the channel can render has a thumbnail builder, in ONE list.

THE INCIDENT (#143, 2026-W40). bin/batch-session.sh:thumb_one() kept its own
`case "$dom"` of builders: materials-and-manufacturing had one, and the `*)`
branch printed "deep-sea-ocean-science has no builder wired here; skipping".
visuals/thumbs.py IS the deep-sea builder, keyed to the twenty hand-numbered
episodes, so the first unnumbered deep-sea episode to render
(how-do-scientists-know-about-other-galaxies) was pushed to R2 with no
thumbnail and the cloud lane refused it for eight runs. Two components each
kept their own list of domains; the batch's was the shorter one.

WHAT THIS PROVES, on visuals/thumbs_for.py (the one registry) and on the real
batch script:

  1. Every domain the channel allocates slots to (loop/domains.allocation on
     the real config) AND every domain any script in scripts/ declares has a
     builder in thumbs_for.BUILDERS. A new domain without a thumbnail path
     fails here, before it fails on the shelf.
  2. An unnumbered deep-sea slug derives a spec from its own words: a hook
     from `## Direct-answer lock`, a picture only when its declared topic
     names exactly one imagery slot, type otherwise. Ambiguity is type, never
     a guess.
  3. The derived path produces the artifact the upload lane attaches:
     1280x720 JPEG under 2 MB, built into a scratch dir.
  4. bin/batch-session.sh:thumb_one() calls thumbs_for.py and keeps no domain
     table of its own - "exists but nothing invokes it" is the other half of
     the defect.

NEGATIVE PROOF (run once, 2026-10-03): remove the deep-sea entry from
BUILDERS -> case 1 fails naming the domain; restore -> green.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import common                                             # noqa: E402
import thumbs_for as TF                                   # noqa: E402

loop_domains = TF._loop_domains()                         # noqa: SLF001

fails: list[str] = []
examined = 0

# -- 1. one list covers every domain the channel can render -------------------
cfg = common.config()
allocated = set(loop_domains.allocation(cfg))
declared = set(loop_domains.by_slug().values())
need = sorted(allocated | declared)
if not need:
    fails.append("no allocated or declared domain found - this test cannot "
                 "reach what it governs")
for d in need:
    examined += 1
    try:
        fn = TF.builder_for(d)
    except KeyError as e:
        fails.append(str(e))
        continue
    if not callable(fn):
        fails.append(f"{d}: BUILDERS entry is not callable")

# -- 2. the derived deep-sea spec: words from the script, picture only when the
#       declared topic names exactly one slot ---------------------------------
examined += 1
slots = ["trench", "vent", "fish", "frilled_shark", "squid", "crab"]
cases = {
    "what-lives-in-mariana-trench": "trench",
    "what-is-hydrothermal-vents": "vent",                 # plural names the slot
    "how-do-scientists-know-about-other-galaxies": None,  # nothing deep-sea
    "how-deep-can-a-sperm-whale-go": None,
    "what-fish-eats-the-frilled-shark": None,             # two slots: type, not a guess
}
for slug, want in cases.items():
    got, why = TF.deep_sea_slot_for(slug, "Pressure does it", slots)
    if got != want:
        fails.append(f"slot for {slug!r}: wanted {want!r}, got {got!r} ({why})")

tmp = Path(tempfile.mkdtemp(prefix="thumbs-for-"))
script = tmp / "why-the-deep-is-dark.md"
script.write_text(
    "# Why is the deep sea dark?\n\n**Domain:** deep-sea-ocean-science\n\n"
    "## Direct-answer lock\n\nSunlight is absorbed by water within the first "
    "few hundred metres, so below about 1,000 metres no daylight remains.\n\n"
    "## Narration\n\n### Cold open\n\nText.\n", encoding="utf-8")
spec = TF.derive_deep_sea_spec("why-the-deep-is-dark", str(script))
if not spec or not spec.get("hook"):
    fails.append(f"no hook derived from a script with a Direct-answer lock: {spec}")
elif spec["hook"].split()[-1].lower() in TF.DANGLING:
    fails.append(f"hook ends on a function word: {spec['hook']!r}")
if spec and spec.get("media"):
    fails.append(f"a topic naming no slot was given a picture: {spec}")
empty = tmp / "no-lock.md"
empty.write_text("# Q\n\n## Narration\n\nText.\n", encoding="utf-8")
if TF.derive_deep_sea_spec("no-lock", str(empty)) is not None:
    fails.append("a script with no Direct-answer lock derived a spec (a card "
                 "with no claim would ship)")

# -- 3. the derived card is the artifact the uploader attaches ----------------
examined += 1
os.environ["HWK_DOMAIN"] = TF.DEEP_SEA
try:
    out = TF.build_deep_sea("why-the-deep-is-dark", out_dir=str(tmp / "out"),
                            script_path=str(script))
    from PIL import Image                                 # noqa: PLC0415
    with Image.open(out) as im:
        if im.format != "JPEG" or im.size != (1280, 720):
            fails.append(f"derived card is {im.format} {im.size}, not a 1280x720 JPEG")
    if os.path.getsize(out) > TF.YOUTUBE_THUMB_LIMIT:
        fails.append(f"derived card is {os.path.getsize(out)} bytes, over the limit")
except Exception as e:                                    # noqa: BLE001
    fails.append(f"derived deep-sea build raised: {type(e).__name__}: {e}")

# -- 4. the batch invokes the registry and keeps no list of its own -----------
examined += 1
sh = (ROOT / "bin" / "batch-session.sh").read_text(encoding="utf-8")
m = re.search(r"\nthumb_one\(\) \{\n(.*?)\n\}\n", sh, re.S)
if not m:
    fails.append("bin/batch-session.sh has no thumb_one() function")
else:
    body = m.group(1)
    if "visuals/thumbs_for.py" not in body:
        fails.append("thumb_one() does not call visuals/thumbs_for.py")
    if re.search(r"case\s+\"?\$dom", body) or "no builder wired" in body:
        fails.append("thumb_one() still keeps its own domain -> builder table")

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} thumbnail-builder case(s) across {len(need)} domain(s): "
      f"{', '.join(need)}")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - every domain has a thumbnail builder, and the batch calls it")
