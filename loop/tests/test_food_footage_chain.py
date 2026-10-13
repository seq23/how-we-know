"""The food footage FALLBACK CHAIN (research/food_footage.py), held to its contract.

Owner instruction, 2026-10-13: a free fallback chain behind Pixabay, formal and
tested - Pixabay, Pexels, key-free libraries (Mixkit, Coverr), public-domain
archives (Commons, Internet Archive, NASA). Every adapter has the same
search -> candidates -> download -> licence-record contract, a stored licence
URL, a polite rate, and a terms check: an adapter whose site's terms forbid
automated download is DISABLED with the reason, never silently used.

  1. The chain's order and each adapter's licence/terms fields; Coverr is
     disabled by its own terms and refuses to search; licence wording files
     named by adapters are committed.
  2. THE PROOF: with the Pixabay key unavailable (key dir pointed at nothing,
     env key blank - her real key file is never touched) the chocolate shot list
     resolves >= 10 real clips from the fallbacks (recorded candidates, offline).
  3. NEGATIVE: with every fallback off as well, it resolves nothing and fails.
  4. With a (fake, temp) key present, Pixabay is first in the chain.
  5. A key file readable by others is refused; generated/CG Pixabay results
     (isAiGenerated, type "animation") never become candidates; branded or
     drawn clips never match; renditions stay within 1280-1920.
  6. Every clip record in channel/imagery/food_clips.json passes its rights
     fields; no API key appears in any committed footage file.

Proof command (the same check by hand, on the Mac, live or --offline):
    HWK_FOOTAGE_KEY_DIR=/nonexistent PIXABAY_API_KEY= python3 research/food_footage.py --resolve --offline
    HWK_FOOTAGE_KEY_DIR=/nonexistent PIXABAY_API_KEY= HWK_FOOTAGE_DISABLE=pexels,mixkit,coverr,commons,archive,nasa \\
        python3 research/food_footage.py --resolve --offline      # exits 1
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "research"))
os.environ["LOOP_DRY_RUN"] = "1"

import food_footage as FF                                      # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    print(("  ok  " if cond else "  ✗  ") + msg)
    if not cond:
        fails.append(msg)


def env(**kw):
    for k, v in kw.items():
        os.environ[k] = v


env(HWK_FOOTAGE_KEY_DIR="/nonexistent-hwk-proof", PIXABAY_API_KEY="", PEXELS_API_KEY="",
    HWK_FOOTAGE_DISABLE="")

# ------------------------------------------------------------- 1. the chain
check([a.name for a in FF.CHAIN] == ["pixabay", "pexels", "mixkit", "coverr", "commons",
                                      "archive", "nasa"], "chain order: keyed, key-free, PD archives")
check(all(a.licence and a.licence_url.startswith("https://") and a.terms_url.startswith("https://")
          and a.gap_s >= 1.0 for a in FF.CHAIN), "every adapter: licence, licence URL, terms URL, >= 1 s gap")
ok, why = FF.BY_NAME["coverr"].enabled()
check(not ok and "terms forbid" in why, f"Coverr disabled by its own terms: {why[:60]}")
try:
    FF.BY_NAME["coverr"].search("chocolate")
    check(False, "Coverr refused to search")
except PermissionError:
    check(True, "Coverr refuses to search")
for a in FF.CHAIN:
    for f in (a.licence_text, a.terms_text):
        if f:
            check((FF.IMAGERY / f).exists(), f"{a.name}: {f} committed")

# ---------------------------------------------------------- 2. the proof
check(not FF.BY_NAME["pixabay"].enabled()[0] and not FF.BY_NAME["pexels"].enabled()[0],
      "with the key dir pointed at nothing, Pixabay and Pexels are off")
res = FF.resolve(offline=True)
check(res["enough"] and res["count"] >= 10 and not res["by_source"].get("pixabay"),
      f"without Pixabay the fallbacks resolve {res['count']} real clips: {res['by_source']}")
check(len({p["uid"] for p in res["picks"]}) == res["count"], "every resolved clip is distinct")

# ---------------------------------------------------------- 3. negative
env(HWK_FOOTAGE_DISABLE=",".join(FF.FALLBACKS))
neg = FF.resolve(offline=True)
check(neg["count"] == 0 and not neg["enough"], f"with the fallbacks off too: {neg['count']} clips, fails")
env(HWK_FOOTAGE_DISABLE="")

# ------------------------------------------------- 4. Pixabay first when keyed
with tempfile.TemporaryDirectory() as td:
    kp = Path(td) / "pixabay.key"
    kp.write_text("not-a-real-key")
    os.chmod(kp, 0o600)
    env(HWK_FOOTAGE_KEY_DIR=td)
    full = FF.resolve(offline=True)
    check(full["by_source"].get("pixabay", 0) >= 1 and full["enough"],
          f"keyed, Pixabay answers first: {full['by_source']}")
    os.chmod(kp, 0o644)
    try:
        FF.key_for("pixabay")
        check(False, "a world-readable key file is refused")
    except PermissionError:
        check(True, "a world-readable key file is refused")
    env(HWK_FOOTAGE_KEY_DIR="/nonexistent-hwk-proof")

# ------------------------------------------------------ 5. what never passes
px = FF.BY_NAME["pixabay"]
fake = {"hits": [
    {"id": 1, "type": "animation", "isAiGenerated": False, "pageURL": "u1", "tags": "chocolate",
     "videos": {"large": {"url": "x", "width": 1920}}},
    {"id": 2, "type": "film", "isAiGenerated": True, "pageURL": "u2", "tags": "chocolate",
     "videos": {"large": {"url": "x", "width": 1920}}},
    {"id": 3, "type": "film", "isAiGenerated": False, "pageURL": "u3", "tags": "chocolate, pouring",
     "videos": {"large": {"url": "x", "width": 3840}, "medium": {"url": "y", "width": 1920}}}]}
px._q = lambda params, name: fake                               # type: ignore[assignment]
got = px.search("chocolate")
check([c["id"] for c in got] == ["3"] and got[0]["width"] == 1920,
      "Pixabay: animation and AI results dropped; the 1920 rendition picked over 4K")
shot = next(s for s in FF.SHOTS if s["need"] == "stream")
check(not FF.matches({"title": "chocolate pouring 3d render"}, shot)
      and not FF.matches({"title": "nutella chocolate pouring"}, shot)
      and FF.matches({"title": "chocolate pouring slowly"}, shot),
      "drawn/rendered or branded clips never match a need")

# ------------------------------------------------- 6. the manifest on main
man = FF.load()
recs = [r for r in man.get("index") or [] if not r.get("excluded")]
probs = [p for r in recs for p in FF.record_problems(r)]
check(len(recs) >= 10 and not probs, f"{len(recs)} clip records, rights fields complete: {probs[:3]}")
leak = [p.name for p in [FF.MANIFEST, FF.CANDIDATES]
        if re.search(r"key=[A-Za-z0-9]{10,}", p.read_text())]
check(not leak, f"no API key in committed footage files: {leak}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
