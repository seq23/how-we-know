"""A Short's footage credit comes from the RENDER, never from today's manifest.

On 14 Oct 2026 four re-cut Shorts failed V14 (01 short3, 07/08/18 short2):
visuals/shorts.py re-ran footage.assign() against whatever
channel/imagery/video_rights.json the cutting checkout held, and in a checkout
without that git-ignored manifest load_manifest() is an empty pool BY DESIGN -
so each footage beat became "no footage" and the Short credited the species
engraving ("ZOOLOGICAL SOCIETY PLATE, 1864", "NOAA OCEAN EXPLORATION") over a
NOAA clip the master burns with a different credit. Proves, with no network
and no credential:

  1. beat_credits takes a footage beat's credit from the render record, and
     the answer does not move when the manifest is absent (the 14 Oct
     condition) or when footage.assign would place something else;
  2. visuals/shorts.py no longer re-derives placement (no footage.assign);
  3. render_footage_record refuses a master that may burn footage when no
     credit line is known, refuses a record whose count disagrees with the
     render receipt, and reads nothing for a render that burned no footage;
     a record for a re-rendered master is stale and not used;
  4. match_credit_line separates "Seascape Alaska" from "Seascape Alaska 5"
     and answers None rather than guess;
  5. V14 reads the master for EVERY beat a Short uses (no re-derivation gate),
     fails a credit the master did not show, checks the Short's strip at
     every beat, and the chrome credit is one static overlay;
  6. REAL DATA on the Mac: every kept render record adds up to its render
     receipt, and every unpublished cut's receipt credits are exactly what
     its render record resolves to.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "visuals"), str(ROOT / "loop")]

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}" + (f": {detail}" if detail else ""))


import footage as FT                                       # noqa: E402
import shorts as SH                                        # noqa: E402

# ---- 1: the credit is the render's ---------------------------------------
plans = sorted((ROOT / "plans").glob("*.json"))
case = None
for pj in plans:
    plan = json.loads(pj.read_text())
    for i, b in enumerate(plan):
        if b.get("segment") == "species_image":
            case = (pj.stem, plan, i)
            break
    if case:
        break
check("1 a plan with a species_image beat exists", case is not None)
if case:
    slug, plan, i = case
    burned = "NOAA Ocean Exploration, Voyage to the Ridge 2022"
    got = SH.beat_credits(slug, plan, i, {i: burned})
    check("1 a footage beat credits what the render burned", got[:1] == [burned],
          str(got))
    saved = (FT.MANIFEST, FT.CLIPS_DIR, FT.assign)
    try:
        FT.MANIFEST = str(ROOT / "no-such-manifest.json")
        FT.CLIPS_DIR = str(ROOT / "no-such-clips")

        def _boom(*a, **k):
            raise AssertionError("footage.assign called while crediting a cut")
        FT.assign = _boom
        try:
            again = SH.beat_credits(slug, plan, i, {i: burned})
        except AssertionError as e:
            again = [f"raised: {e}"]
        check("1 with NO manifest (the 14 Oct checkout) the credit is unchanged",
              again == got, f"{again} != {got}")
    finally:
        FT.MANIFEST, FT.CLIPS_DIR, FT.assign = saved
    try:
        SH.beat_credits(slug, plan, i, {})
        check("1 a beat missing from the record is unresolved, not guessed", False)
    except SH.CreditUnresolved:
        check("1 a beat missing from the record is unresolved, not guessed", True)

# ---- 2: no re-derivation left ---------------------------------------------
src = (ROOT / "visuals" / "shorts.py").read_text()
check("2 visuals/shorts.py does not call footage.assign",
      "FT.assign(" not in src and "footage_cuts" not in src)
vsrc = (ROOT / "loop" / "validate.py").read_text()
v14 = vsrc[vsrc.find("def _credits_the_master_burned"):]
v14 = v14[:v14.find("\ndef v15_shorts_caption_crop")]
check("2 V14 does not re-derive placement either",
      "footage_cuts(" not in v14 and "FT.assign(" not in v14)

# ---- 3: the record refuses rather than guesses ----------------------------
with tempfile.TemporaryDirectory() as td:
    master = os.path.join(td, "x-final.mp4")
    Path(master).write_bytes(b"not a video")
    tl = [{"i": k, "video_start": float(k), "video_s": 1.0} for k in range(4)]
    plan4 = [{"segment": "text_beat"} for _ in range(4)]
    saved = (SH.footage_credit_lines, SH._read_strips)
    try:
        Path(master + ".render.json").write_text(
            json.dumps({"footage": {"footage_beats": 2}}))
        SH.footage_credit_lines = lambda: []
        try:
            SH.render_footage_record("x", plan4, master, tl)
            check("3 footage expected and no credit line known -> refused", False)
        except SH.RenderRecordUnreadable:
            check("3 footage expected and no credit line known -> refused", True)

        SH.footage_credit_lines = lambda: ["NOAA Ocean Exploration, Seascape Alaska"]
        SH._read_strips = lambda s, times, w: {
            k: ("SNAILFISH · NOAA OCEAN EXPLORATION, SEASCAPE ALASKA"
                if k[0] == 1 else "") for k in times}
        try:
            SH.render_footage_record("x", plan4, master, tl)
            check("3 a record that does not add up to the receipt -> refused", False)
        except SH.RenderRecordUnreadable:
            check("3 a record that does not add up to the receipt -> refused", True)
        check("3 a refused record is not kept",
              not os.path.exists(master + SH.FOOTAGE_RECORD_SUFFIX))

        Path(master + ".render.json").write_text(
            json.dumps({"footage": {"footage_beats": 1}}))
        rec = SH.render_footage_record("x", plan4, master, tl)
        check("3 a record that adds up is built and kept",
              rec == {0: None, 1: "NOAA Ocean Exploration, Seascape Alaska",
                      2: None, 3: None}
              and SH.load_footage_record(master) == rec, str(rec))
        Path(master).write_bytes(b"re-rendered, different bytes")
        check("3 a record for a re-rendered master is stale",
              SH.load_footage_record(master) is None)

        os.remove(master + SH.FOOTAGE_RECORD_SUFFIX)
        Path(master + ".render.json").write_text(
            json.dumps({"footage": {"footage_beats": 0}}))

        def _no_ocr(*a, **k):
            raise AssertionError("OCR'd a master that burned no footage")
        SH._read_strips = _no_ocr
        try:
            rec0 = SH.render_footage_record("x", plan4, master, tl)
            check("3 a render with no footage reads nothing",
                  all(v is None for v in rec0.values()) and len(rec0) == 4)
        except AssertionError as e:
            check("3 a render with no footage reads nothing", False, str(e))
    finally:
        SH.footage_credit_lines, SH._read_strips = saved

# Strip-free masters: credits survive absent legacy segments/manifests,
# but mismatched bytes, timing or shot records must fail closed.
with tempfile.TemporaryDirectory() as td:
    import assemble as AS
    import longform_picture as LP
    master = str(Path(td) / "x.mp4")
    Path(master).write_bytes(b"master pixels")
    shots = [{"kind": "footage", "title": "isopod", "credit": "NOAA",
              "key": "a", "start": 0, "subject": "isopod", "speed": 1,
              "asset": {"source_org": "NOAA"}}]
    AS.write_picture_record(master, shots, [60], [30, 30], {"credits": ["NOAA"]})
    tl = [{"i": 0, "video_start": 0, "video_s": 1},
          {"i": 1, "video_start": 1, "video_s": 1}]
    record = SH.render_footage_record("x", [{}, {}], master, tl)
    check("strip-free credits resolve without legacy species segments",
          SH.beat_credits("x", [{"segment": "species_image", "args": {"source": "old"}}],
                          0, record) == ["NOAA"])
    import validate as V
    rec = {"slug": "x", "source": master, "beats": [0, 1],
           "segments": [{"beat": 0, "source_start": 0, "seconds": 1},
                        {"beat": 1, "source_start": 1, "seconds": 1}]}
    want, dropped, disagree = V._credits_the_master_burned(SH, None, rec, [{}, {}], Path(td))
    check("V14 resolves strip-free credits independently of short receipt",
          want == ["NOAA"] and not dropped and not disagree)
    rec["segments"][0]["source_start"] = .5
    check("V14 refuses cut timing from a different master",
          bool(V._credits_the_master_burned(SH, None, rec, [{}, {}], Path(td))[1]))
    # Existing approved masters get a read-only legacy migration by exact
    # approved bytes, with credits re-derived from actual cut intervals.
    rp = Path(master + SH.FOOTAGE_RECORD_SUFFIX)
    original = json.loads(rp.read_text())
    legacy = {k: v for k, v in original.items() if k not in
              ("master_sha256", "beat_frames", "shot_frames")}
    rp.write_text(json.dumps(legacy))
    real_root = SH.ROOT
    try:
        SH.ROOT = td
        pin = Path(td) / "channel" / "approved_renders.json"
        pin.parent.mkdir()
        pin.write_text(json.dumps({"x.mp4": {"sha256": original["master_sha256"],
                                              "bytes": len(b"master pixels")}}))
        check("approved legacy master resolves without changing master or sidecar",
              SH.picture_credits(master, tl) == {0: "NOAA", 1: "NOAA"}
              and rp.read_text() == json.dumps(legacy))
        pin.write_text("{}")
        try:
            SH.picture_credits(master, tl)
            check("unapproved unbound legacy record is refused", False)
        except SH.RenderRecordUnreadable:
            check("unapproved unbound legacy record is refused", True)
    finally:
        SH.ROOT = real_root
        rp.write_text(json.dumps(original))
    # V15 still measures the crop on strip-free masters. A receipt alone
    # cannot make the uncropped picture pass.
    from unittest.mock import patch
    import numpy as np
    from PIL import Image
    rows = np.arange(SH.SRC_H, dtype=np.uint16)[:, None]
    pixels = np.zeros((SH.SRC_H, SH.SRC_W, 3), dtype=np.uint8)
    pixels[:, :, 0] = rows % 251
    pixels[:, :, 1] = (rows // 3) % 251
    full_image = Image.fromarray(pixels)
    source_png, short_png = Path(td) / "source.png", Path(td) / "short.png"
    full_image.save(source_png)
    crop_h = SH.source_crop_height(2)
    by, bh = SH.band_geometry(crop_h)
    short_image = Image.new("RGB", (SH.OUT_W, SH.OUT_H))
    short_image.paste(full_image.crop((0, 0, SH.SRC_W, crop_h))
                      .resize((SH.OUT_W, bh), Image.BICUBIC), (0, by))
    short_image.save(short_png)
    receipt = {"slug": "x", "source": master, "source_crop_height": crop_h,
               "band_y": by, "band_h": bh, "cap_lines": 2,
               "segments": [{"beat": i, "source_start": i, "short_start": i,
                             "seconds": 1} for i in range(2)]}
    mp4 = Path(td) / "cut.mp4"
    def frame(path, *args):
        return str(source_png if str(path) == master else short_png)
    with patch.object(V, "ROOT", Path(td)), patch.object(V, "_frame", side_effect=frame), \
         patch.object(V, "_shorts_env", return_value=(SH, lambda paths: {}, [(mp4, receipt)])):
        good = V.v15_shorts_caption_crop()
        check("V15 proves strip-free crop on actual pixel bands", good.examined > 0 and not good.failures)
        short_image.paste(full_image.resize((SH.OUT_W, bh), Image.BICUBIC), (0, by))
        short_image.save(short_png)
        bad = V.v15_shorts_caption_crop()
        check("V15 refuses uncropped strip-free source pixels", bool(bad.failures))
    Path(master).write_bytes(b"changed pixels")
    try:
        SH.picture_credits(master)
        check("changed master bytes invalidate strip-free credits", False)
    except SH.RenderRecordUnreadable:
        check("changed master bytes invalidate strip-free credits", True)

# ---- 4: the matcher --------------------------------------------------------
known = ["NOAA Ocean Exploration, Seascape Alaska",
         "NOAA Ocean Exploration, Seascape Alaska 5",
         "NOAA Ocean Exploration, Voyage to the Ridge 2022"]
check("4 '...Alaska 5' on screen -> the 5 line",
      SH.match_credit_line("SNAILFISH · NOAA OCEAN EXPLORATION, SEASCAPE ALASKA 5",
                           known) == known[1])
check("4 '...Alaska' alone -> the plain line",
      SH.match_credit_line("SNAILFISH · NOAA OCEAN EXPLORATION, SEASCAPE ALASKA",
                           known) == known[0])
check("4 nothing readable -> None",
      SH.match_credit_line("ANGLERFISH", known) is None)
check("4 the species plate's 'NOAA OCEAN EXPLORATION' is not a footage credit",
      SH.match_credit_line("NOAA OCEAN EXPLORATION", known) is None)

# the species credit drawn just above the footage strip is not footage:
# 01 beat 38 (barreleye plate) reads "NOAA OCEAN EXPLORATION, 2024" at row 974
_, sy, _, sh = SH.FOOTAGE_STRIP
box = lambda row, t: {"t": t, "y": (row - sy) / sh}       # noqa: E731
items = [box(974, "-NOAA OCEAN EXPLORATION, 2024"),
         box(1011, "Specimen on deck, not in habitat")]
check("4 a species credit above the strip is not read as footage",
      SH.match_credit_line(SH.footage_strip_text(items),
                           known + ["NOAA Ocean Exploration"]) is None)
items = [box(999, "ANGLERFISH\u2022 NOAA OCEAN EXPLORATION, SEASCAPE ALASKA")]
check("4 the footage strip's own row is read",
      SH.match_credit_line(SH.footage_strip_text(items), known) == known[0])
items = [box(1010, "Source: NOAA Ocean Exploration")]
check("4 a stat card's 'Source:' line is not a footage strip",
      SH.match_credit_line(SH.footage_strip_text(items),
                           known + ["NOAA Ocean Exploration"]) is None)
check("4 the strip is read full width (a long credit runs past x=1360)",
      SH.FOOTAGE_STRIP[0] == 0 and SH.FOOTAGE_STRIP[2] == SH.SRC_W)
check("4 a credit truncated in the manifest is told from the full one",
      SH.match_credit_line(
          "NOAA OCEAN EXPLORATION, 2023 SHAKEDOWN + EXPRESS WEST COAST EXPLORATIO",
          ["NOAA Ocean Exploration",
           "NOAA Ocean Exploration, 2023 Shakedown + EXPRESS West Coast Exploratio",
           "NOAA Ocean Exploration, 2023 Shakedown + EXPRESS West Coast Exploration"])
      == "NOAA Ocean Exploration, 2023 Shakedown + EXPRESS West Coast Exploratio")
check("4 case-only duplicates in the manifest are one credit",
      SH.match_credit_line("NOAA OCEAN EXPLORATION, 2019 SOUTHEASTERN U.S. DEEP-SEA EXPLORATION",
                           ["NOAA Ocean Exploration, 2019 Southeastern U.S. Deep-Sea Exploration",
                            "NOAA Ocean Exploration, 2019 Southeastern U.S. Deep-sea Exploration"])
      is not None)

# ---- 5: V14 covers every beat ---------------------------------------------
body = vsrc[vsrc.find("def v14_shorts_attribution"):]
body = body[:body.find("\ndef v15_shorts_caption_crop")]
check("5 V14 reads the master for every beat the Short uses",
      'for i in rec["beats"]' in v14 and "cuts[i] is not None" not in v14)
check("5 V14 fails a credit the master does not show",
      "that the \"\n                        f\"master does not show" in body
      or "master does not show" in body)
check("5 V14 reads the Short's credit strip at every beat",
      "_samples(rec, 10 ** 6)" in body and "_samples(rec, 1)" not in body)
check("5 the chrome (credits) is ONE static overlay for the whole cut",
      '"[0:v][1:v]overlay=0:0[chr]"' in src)

# ---- 6: real data (the Mac) -----------------------------------------------
shorts_dir = ROOT / "shorts"
records = sorted((ROOT / "renders").glob(f"*-final.mp4{SH.FOOTAGE_RECORD_SUFFIX}"))
if records:
    for rp in records:
        d = json.loads(rp.read_text())
        exp = d.get("footage_beats_expected")
        n = sum(1 for v in d["beats"].values() if v)
        check(f"6 {rp.name} adds up to its render receipt",
              exp is None or exp == n, f"{n} != {exp}")
    ledger = json.loads((ROOT / "loop/state/shorts_ledger.json").read_text())
    published = {r.get("file") for r in ledger.get("published", [])}
    for rj in sorted(shorts_dir.glob("*.mp4.short.json")):
        mp4 = rj.name[: -len(".short.json")]
        if mp4 in published:
            continue                     # on the channel; never re-uploaded
        rec = json.loads(rj.read_text())
        master = str(ROOT / rec["source"])
        kept = SH.load_footage_record(master)
        if kept is None:
            check(f"6 {mp4} has a render record to be credited from", False)
            continue
        plan = json.loads((ROOT / "plans" / f"{rec['slug']}.json").read_text())
        want, _ = SH.resolve_credits(rec["slug"], plan, rec["beats"], kept)
        same = lambda xs: [SH._tokens(x) for x in xs or []]       # noqa: E731
        check(f"6 {mp4} credits exactly what its render record resolves to",
              same(rec.get("credits")) == same(want),
              f"{rec.get('credits')} != {want}")
else:
    print("  · no renders/*.footage.json here (the cloud); part 6 runs on the Mac")

if examined == 0:
    print("FAIL test_shorts_credit_from_render: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_shorts_credit_from_render:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_shorts_credit_from_render: {examined} checks - footage credits "
      f"come from the render's record, never today's manifest")
