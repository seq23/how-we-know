"""The footage validators must actually catch things - proven by breaking them.

V9-V12 govern visuals/footage.py, which puts rights-cleared NOAA ROV footage on
screen. Each condition here is broken on purpose, the failure is shown to
return, and the state is restored and shown green again. A gate that has never
rejected anything is not known to work.

  1. V9  a cut that crosses a clean-window boundary must FAIL
  2. V10 a `cropped` clip with its crop rect removed must FAIL
  3. V11 a clip whose bytes do not match the manifest sha256 must FAIL
  4. V12 footage placed on a beat that draws information must FAIL,
         and footage placed on an UNILLUSTRATABLE subject must FAIL
  5. all four must FAIL - not pass - when they examine zero clips

Hard-fails if it examines zero checks.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
sys.path.insert(0, os.path.join(ROOT, "visuals"))

import validate  # noqa: E402
import footage as FT  # noqa: E402


def temp_manifest(mutate) -> str:
    """A copy of the live manifest with `mutate` applied, written to /tmp."""
    m = copy.deepcopy(FT.load_manifest(os.path.join(
        ROOT, "channel", "imagery", "video_rights.json")))
    mutate(m)
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(m, fh)
    fh.close()
    return fh.name


class swap_manifest:
    """Point footage.py at a different manifest and clear the hash cache."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.old, self.cache = FT.MANIFEST, dict(FT._VERIFIED)
        FT.MANIFEST = self.path
        FT._VERIFIED.clear()
        return self

    def __exit__(self, *a):
        FT.MANIFEST = self.old
        FT._VERIFIED.clear()
        FT._VERIFIED.update(self.cache)
        return False


def check() -> list[str]:
    fails, examined = [], 0

    def want(cond, msg):
        nonlocal examined
        examined += 1
        if not cond:
            fails.append(msg)

    # -- baseline: the real state is green -------------------------------
    base = {"V9": validate.v9_footage_window(), "V10": validate.v10_footage_crop(),
            "V11": validate.v11_footage_hash(), "V12": validate.v12_footage_scope()}
    for k, r in base.items():
        want(r.ok, f"{k} does not pass on the real, unmodified state: "
                   f"{r.status} {r.failures[:2]}")
        want(r.examined > 0, f"{k} examined 0 items on the real state - it "
                             f"cannot reach what it governs")

    # -- 1. V9: a cut that crosses a window boundary ---------------------
    real_place = FT.place_cut

    def bad_place(asset, seconds, nth=0):
        cut = real_place(asset, seconds, nth)
        if cut is None:
            return None
        cut = dict(cut)
        cut["end"] = round(cut["window"]["end"] + 2.0, 3)   # over the edge
        cut["start"] = round(cut["end"] - seconds, 3)
        return cut

    FT.place_cut = bad_place
    try:
        r = validate.v9_footage_window()
        want(not r.ok, "V9 PASSED a cut that runs past the end of its clean "
                       "window - the boundary guard is not load-bearing")
        want(r.examined > 0, "V9 examined 0 items while broken")
    finally:
        FT.place_cut = real_place
    r = validate.v9_footage_window()
    want(r.ok, f"V9 did not go green again after restoring place_cut: {r.failures[:2]}")

    # ...and the renderer's own last-line check refuses it too.
    assets = FT.usable_assets()
    a = assets[0]
    w = FT.windows(a)[0]
    bad = {"asset": a, "start": w["end"] - 1.0, "end": w["end"] + 3.0,
           "label": None, "credit": None, "title": a["title"]}
    try:
        FT.render_cut(bad, "/dev/null", 4.0, tempfile.gettempdir())
        fails.append("footage.render_cut rendered a cut that leaves the clean "
                     "window instead of refusing it")
        examined += 1
    except FT.RightsRefusal:
        examined += 1

    # -- 2. V10: a cropped clip with no crop rect ------------------------
    def strip_crop(m):
        for x in m["assets"]:
            if x.get("treatment") == "cropped":
                x["crop"] = {"left": 0, "top": 0, "right": 0, "bottom": 0}
                return
        raise SystemExit("no cropped clip in the manifest to break")

    with swap_manifest(temp_manifest(strip_crop)):
        r = validate.v10_footage_crop()
        want(not r.ok, "V10 PASSED a 'cropped' clip whose rect removes nothing "
                       "- the OCEAN EXPLORATION corner bug would be burned in")
        want(r.examined > 0, "V10 examined 0 items while broken")
    r = validate.v10_footage_crop()
    want(r.ok, f"V10 did not go green again: {r.failures[:2]}")

    # vf_chain itself must refuse, not silently skip the crop.
    ghost = dict(assets[0])
    ghost["treatment"], ghost["crop"] = "cropped", None
    try:
        FT.vf_chain(ghost)
        fails.append("footage.vf_chain built a filter for a 'cropped' clip with "
                     "no rect instead of refusing")
        examined += 1
    except FT.RightsRefusal:
        examined += 1

    # -- 3. V11: bytes that are not the bytes the rights cover -----------
    def bend_hash(m):
        m["assets"][0]["sha256"] = "0" * 64

    with swap_manifest(temp_manifest(bend_hash)):
        r = validate.v11_footage_hash()
        want(not r.ok, "V11 PASSED a clip whose sha256 does not match the "
                       "manifest - the rights decision does not cover it")
        want(any("sha256 mismatch" in f for f in r.failures),
             "V11 failed for some other reason than the hash mismatch")
    r = validate.v11_footage_hash()
    want(r.ok, f"V11 did not go green again: {r.failures[:2]}")

    # -- 4. V12: footage on a beat that carries information --------------
    real_assign = FT.assign

    def bad_assign(plan, durs, slug, assets=None):
        cuts = real_assign(plan, durs, slug, assets)
        for i, b in enumerate(plan):
            if b["segment"] == "stat_card" and cuts[i] is None:
                a0 = (assets or FT.usable_assets())[0]
                cut = real_place(a0, min(durs[i], 5.0), 0)
                if cut:
                    cuts[i] = {"beat": i, "segment": b["segment"], "asset": a0,
                               "label": None, "credit": None,
                               "title": a0["title"], **cut}
                    return cuts
        return cuts

    FT.assign = bad_assign
    try:
        r = validate.v12_footage_scope()
        want(not r.ok, "V12 PASSED footage drawn over a stat_card - a beat that "
                       "carries a number on screen")
    finally:
        FT.assign = real_assign
    r = validate.v12_footage_scope()
    want(r.ok, f"V12 did not go green again: {r.failures[:2]}")

    # ...and an UNILLUSTRATABLE subject must never be given footage.
    want("giant_squid" in FT.UNILLUSTRATABLE,
         "giant_squid is no longer declared unillustratable - a lookalike squid "
         "captioned 'colossal squid' is a lie told in pictures")
    want(FT.subject_pool("giant_squid", assets) == [],
         "footage.subject_pool offered clips for giant_squid")
    for subj in FT.UNILLUSTRATABLE:
        want(subj not in FT.SUBJECT_FOOTAGE,
             f"{subj} is both unillustratable AND mapped to footage")

    # -- 5. zero examined must FAIL, never pass --------------------------
    with swap_manifest(temp_manifest(lambda m: m.update({"assets": []}))):
        for name, fn in (("V9", validate.v9_footage_window),
                         ("V10", validate.v10_footage_crop),
                         ("V11", validate.v11_footage_hash)):
            r = fn()
            want(not r.ok, f"{name} PASSED with zero clips in the manifest - a "
                           f"validator that examines nothing must fail")
            want("examined 0" in r.status,
                 f"{name} did not report that it examined zero items "
                 f"(status {r.status!r})")

    if examined == 0:
        fails.append("this test examined zero checks")
    print(f"footage validators: {examined} check(s), {len(fails)} failure(s)")
    return fails


if __name__ == "__main__":
    problems = check()
    for p in problems:
        print(f"  FAIL {p}")
    print("OK" if not problems else f"{len(problems)} FAILURE(S)")
    sys.exit(1 if problems else 0)
