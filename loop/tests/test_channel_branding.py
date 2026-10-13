"""The channel's banner, About text and keywords carry EVERY channel domain - and the banner never has to.

THE INCIDENT (owner, 2026-10-13). The banner read "bottom of the ocean" while
the channel carried deep sea, materials and (that day) food. Owner refinement
the same day: open-ended. The tagline names the idea, never a domain list; the
About text has one generated line of the current domains.

WHAT THIS PROVES, on loop/channel_branding.py and the real config:
  1. The banner as BUILT is 2560x1440, under 6 MB, and every measured text box
     and panel lies inside the centred 1546x423 safe area.
  2. Every candidate's words carry "evidence chain" and "How we know what we
     know", no deep-sea-only wording, and name no domain (so a new domain
     never needs new words); the logo is visuals/brand.py's own: brand.main()
     still reproduces the original banner's mark pixel-for-pixel.
  3. The composed About text names every channel domain's display name, fits
     YouTube's 1,000 units, keeps no unfilled {{DOMAINS}} token; keywords name
     every domain.
  4. A fourth domain without a branding entry is REFUSED (DOMAIN_UNBRANDED),
     and a fourth panel is a list entry: layout(4) splits the safe area evenly.
  5. V51 fails a fixture missing a domain and passes the recorded read-back.

NEGATIVE PROOF (run 2026-10-13): delete food-science from branding.json
`domains` -> cases 3/4/5 fail naming food-science; set the tagline to "The
bottom of the ocean" in candidate B's lines -> case 2 fails; restore -> green.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import channel_branding as cb                              # noqa: E402
import channel_about as ca                                 # noqa: E402
import validate                                            # noqa: E402
from common import config                                  # noqa: E402

fails: list[str] = []
examined = 0
cfg = config()
sp = cb.spec()
doms = cb.channel_domains(cfg)
names = cb.display_names(cfg, sp)
if len(doms) < 3:
    fails.append(f"only {len(doms)} channel domains found; the owner's rotation names three")

# -- 1. every candidate as built ---------------------------------------------
from PIL import Image, ImageChops                          # noqa: E402
with tempfile.TemporaryDirectory() as td:
    for name in sorted(sp["candidates"]):
        meta = cb.build_banner(out=Path(td) / f"{name}.png", desktop=None, name=name)
        examined += 1
        im = Image.open(meta["path"])
        if im.size != (2560, 1440):
            fails.append(f"{name}: banner is {im.size}")
        if os.path.getsize(meta["path"]) >= 6 * 1024 * 1024:
            fails.append(f"{name}: banner is 6 MB or more")
        n_lines = sum(len(g) for g in sp["candidates"][name]["lines"])
        if len(meta["text_boxes"]) < 2 + n_lines + len(sp["candidates"][name]["panels"]):
            fails.append(f"{name}: text boxes missing (wordmark, lines, mark, credits)")
        if len(meta["art_boxes"]) != len(sp["candidates"][name]["panels"]):
            fails.append(f"{name}: not one art box per panel")
        fails += [f"{name}: {m}" for m in cb.check_banner_meta(meta)]
    bad = copy.deepcopy(meta)
    bad["text_boxes"][0]["box"][0] = cb.SAFE[0] - 1
    if not cb.check_banner_meta(bad):
        fails.append("check_banner_meta passed a wordmark outside the safe area")

# -- 2. the words, and the logo is the original's code -----------------------
examined += 1
for name, cand in sp["candidates"].items():
    text = cb.banner_text(cand)
    fails += [f"{name}: {m}" for m in cb.check_lines(text, sp)]
    for n in names:
        if n.lower() in text.lower():
            fails.append(f"{name}: banner words name a domain ({n!r})")
if not cb.check_lines("Following the evidence chain to the bottom of the ocean.", sp):
    fails.append("check_lines passed the old deep-sea-only line")
sys.path.insert(0, str(LOOP.parent / "visuals"))
import brand                                               # noqa: E402
with tempfile.TemporaryDirectory() as td:
    brand.main(td)
    a_ = Image.open(Path(td) / "banner_2048.png").convert("RGB")
    b_ = Image.open(LOOP.parent / "channel" / "brand" / "banner_2048.png").convert("RGB")
    box = (1024 - 470 - 130, 576 - 6 - 110, 1024 - 470 + 130, 576 - 6 + 80)   # the mark
    if ImageChops.difference(a_.crop(box), b_.crop(box)).getbbox() is not None:
        fails.append("visuals/brand.py no longer reproduces the original logo mark")
src = (LOOP / "channel_branding.py").read_text()
if "brand.mark(" not in src or "design.F_DISPLAY" not in src:
    fails.append("the banner does not draw the logo with brand.mark()/F_DISPLAY")

# -- 3. About text and keywords ---------------------------------------------
examined += 1
desc = cb.description(cfg)
if ca.DOMAINS_TOKEN in desc:
    fails.append("the About text still carries the {{DOMAINS}} token")
if "how we know what we know" not in desc.lower():
    fails.append("About text does not open with 'How we know what we know'")
for d, n in zip(doms, names):
    if n not in desc:
        fails.append(f"About text does not name {d} ({n!r})")
units = len(desc.encode("utf-16-le")) // 2
if units > ca.MAX_DESCRIPTION:
    fails.append(f"About text is {units} units")
kw = cb.keywords(cfg, sp).lower()
for d in doms:
    if not any(k.lower() in kw for k in sp["domains"][d]["keywords"]):
        fails.append(f"keywords carry none of {d}'s")

# -- 4. a new domain: refused without branding; a fourth panel is a list entry
examined += 1
cfg4 = copy.deepcopy(cfg)
cfg4["domains"]["allocation"]["paleontology-extinction"] = 1
try:
    cb.domains_phrase(cfg4, sp)
    fails.append("a channel domain with no branding entry was not refused")
except cb.BrandingRefused as e:
    if "paleontology-extinction" not in str(e):
        fails.append(f"refusal does not name the domain: {e}")
cols = cb.layout(4)
widths = [c["inner"][2] - c["inner"][0] for c in cols]
if len(cols) != 4 or max(widths) - min(widths) > 1 or cols[0]["inner"][0] != cb.SAFE[0] \
        or cols[-1]["inner"][2] != cb.SAFE[2]:
    fails.append(f"layout(4) does not split the safe area evenly: {widths}")

# -- 5. V51 bites, and the recorded read-back passes ---------------------------
examined += 1
full = {"banner_url": "https://yt3.example/b",
        "banner_text": cb.banner_text(cb.candidate(sp)[1]),
        "description": desc, "keywords": cb.keywords(cfg, sp)}
if cb.check_live(full, cfg, sp):
    fails.append(f"check_live failed a complete record: {cb.check_live(full, cfg, sp)}")
missing = dict(full, description=desc.replace(names[-1], ""))
if not any(doms[-1] in m for m in cb.check_live(missing, cfg, sp)):
    fails.append(f"check_live passed a description missing {doms[-1]}")
res = validate.v51_channel_branding()
if not res.ok:
    fails.append(f"V51 fails on the repo's own state: {res.failures}")
if res.examined < 2:
    fails.append("V51 examined too little")

if examined == 0:
    fails.append("examined nothing")
for f in fails:
    print("FAIL:", f)
print(f"test_channel_branding: {examined} cases, {len(fails)} failures")
sys.exit(1 if fails else 0)
