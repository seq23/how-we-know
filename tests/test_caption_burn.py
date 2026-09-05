"""The burned-in captions must land, and must land ONLY where they belong.

Proven on real beats of a real episode, negatively where it matters:

  1. A frame rendered with the burner differs from the same frame rendered
     without it - the burn is not inert.
  2. It differs ONLY inside the caption band. A burn that touched the rest of
     the frame would be silently covering the typography the episode exists to
     show.
  3. A frame at a timestamp no cue covers is pixel-identical to the unburned
     one - the burner does not paint an empty plate over quiet passages.
  4. The panel cache returns the SAME object for the same cue text. The cached
     panel is the whole reason the burn costs ~2% instead of ~30%; if the cache
     stopped hitting, the cost would climb and nothing would say so.
  5. assemble.py REFUSES to burn captions for an episode whose narration is
     incomplete - cue timing would be a word-count guess, and a caption track
     that is confidently wrong is worse than none.
  6. A footage beat gets the burn too, from the same cue list.

Hard-fails if it examines zero frames.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))
os.chdir(ROOT)

try:
    import segments_ext2, segments_species  # noqa: F401,E402
except Exception:
    pass
import assemble as A  # noqa: E402
import captions as CAP  # noqa: E402
import footage as FT  # noqa: E402
from design import W, H, FPS  # noqa: E402

# Where the caption plate is allowed to live, from captions.py's own constants.
BAND_TOP = H - CAP.CAP_BOTTOM - (CAP.CAP_LINE_H * CAP.MAX_LINES + CAP.CAP_PAD * 2) - 8
BAND_BOTTOM = H - CAP.CAP_BOTTOM + 8

SLUG = "18-why-does-black-smoker-water-not-boil"


def episode():
    plan = json.load(open(f"plans/{SLUG}.json"))
    durs = []
    for i, b in enumerate(plan):
        wav = f"audio/{SLUG}/{i:04d}.wav"
        durs.append(max(0.4, A.probe(wav) if os.path.exists(wav)
                        else float(b["seconds"])))
    return plan, durs, CAP.build_cues(plan, durs)


def check() -> list[str]:
    from PIL import Image, ImageChops
    fails, examined = [], 0

    def want(cond, msg):
        nonlocal examined
        examined += 1
        if not cond:
            fails.append(msg)

    plan, durs, cues = episode()
    want(len(cues) > 0, "build_cues produced no cues for a fully narrated episode")

    # A beat that a cue definitely covers.
    i = next(k for k, b in enumerate(plan) if b["segment"] == "text_beat"
             and (b.get("narration") or "").strip())
    t0 = sum(durs[:i])
    fn = A.seg_fn(plan[i]["segment"])
    args = plan[i].get("args") or {}
    try:
        plain = fn(0.5, **args)
    except TypeError:
        plain = A.seg_fn("ambient_drift")(0.5, variant=0)
    plain = plain.convert("RGB")

    # -- 1 & 2: the burn lands, and only in the band ---------------------
    burner = CAP.Burner(cues)
    t = t0 + durs[i] / 2
    burnt = burner.draw(plain.copy(), t).convert("RGB")
    diff = ImageChops.difference(plain, burnt)
    bbox = diff.getbbox()
    want(bbox is not None,
         "the burner changed nothing on a frame a cue covers - the burn is inert")
    if bbox:
        want(bbox[1] >= BAND_TOP and bbox[3] <= BAND_BOTTOM,
             f"the burn painted outside the caption band: bbox {bbox} vs "
             f"allowed y {BAND_TOP}-{BAND_BOTTOM} - it is covering the picture")

    # -- 3: a timestamp past the last cue must not be touched ------------
    quiet = CAP.Burner(cues)
    after = cues[-1]["end"] + 5.0
    untouched = quiet.draw(plain.copy(), after).convert("RGB")
    want(ImageChops.difference(plain, untouched).getbbox() is None,
         "the burner painted a caption plate at a time no cue covers")

    # -- 4: the panel cache actually caches ------------------------------
    txt = cues[0]["text"]
    a1 = burner._panel(txt)
    a2 = burner._panel(txt)
    want(a1 is a2, "Burner._panel rebuilt the panel for a repeated cue - the "
                   "cache is what keeps the burn at ~2% instead of ~30%")

    # -- 5: NEGATIVE. estimated timing must be refused -------------------
    partial = "04-why-deep-sea-creatures-are-so-scary"
    nwav = len([f for f in os.listdir(f"audio/{partial}")
                if f.endswith(".wav")]) if os.path.isdir(f"audio/{partial}") else 0
    nbeat = len(json.load(open(f"plans/{partial}.json")))
    if nwav < nbeat:
        out = os.path.join(tempfile.gettempdir(), "burnguard.mp4")
        r = subprocess.run(
            [sys.executable, "visuals/assemble.py", f"plans/{partial}.json", out,
             "--audio-dir", f"audio/{partial}", "--burn-captions", "--no-footage"],
            cwd=ROOT, capture_output=True, text=True)
        want(r.returncode != 0,
             f"assemble.py burned captions for {partial} on {nwav}/{nbeat} wavs - "
             f"the cue timing would be a word-count guess")
        want("refusing to burn captions" in (r.stdout + r.stderr),
             "the refusal was not named - a human must see WHY it stopped")
        want(not os.path.exists(out),
             "a video was written despite the caption refusal")
        # ...and with no audio at all, likewise.
        r2 = subprocess.run(
            [sys.executable, "visuals/assemble.py", f"plans/{partial}.json", out,
             "--burn-captions", "--no-footage"], cwd=ROOT,
            capture_output=True, text=True)
        want(r2.returncode != 0,
             "assemble.py burned captions with no narration audio at all")
    else:
        # Every episode is fully narrated: prove the guard on the API instead,
        # so this test can never quietly stop checking condition 5.
        try:
            CAP.burner_for(partial)
            fails.append("captions.burner_for did not refuse an episode whose "
                         "timing is not measured")
        except SystemExit:
            pass
        examined += 1

    # -- 6: a footage beat is captioned from the same cue list -----------
    assets = FT.usable_assets()
    want(len(assets) > 0, "no rights-verified clips - this test examined no footage")
    if assets:
        wd = tempfile.mkdtemp()
        try:
            a = assets[0]
            cut = FT.place_cut(a, 3.0, 0)
            cut.update(asset=a, label=None,
                       credit=a.get("required_credit"), title=a["title"])
            b = CAP.Burner(cues)
            with_cap = os.path.join(wd, "cap.mp4")
            FT.render_cut(cut, with_cap, 3.0, wd, burner=b, t0=t0)
            no_cap = os.path.join(wd, "nocap.mp4")
            FT.render_cut(cut, no_cap, 3.0, wd)
            for p in (with_cap, no_cap):
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                                "-y", "-ss", "1.0", "-i", p, "-frames:v", "1",
                                p + ".png"], check=True)
            f1 = Image.open(with_cap + ".png").convert("RGB")
            f2 = Image.open(no_cap + ".png").convert("RGB")
            d = ImageChops.difference(f1, f2).convert("L")
            # These two frames went through libx264 separately, so a pixel-exact
            # band test would fail on compression noise alone: adding the plate
            # shifts bit allocation across the lower half of the frame. Compare
            # the MAGNITUDE inside the caption band against outside it instead.
            band = d.crop((0, max(0, BAND_TOP), W, min(H, BAND_BOTTOM)))
            above = d.crop((0, 0, W, max(1, BAND_TOP)))
            m_band = sum(band.getdata()) / (band.width * band.height)
            m_above = sum(above.getdata()) / (above.width * above.height)
            want(m_band > 4.0,
                 f"a footage beat rendered near-identically with and without the "
                 f"burner (mean diff in the caption band {m_band:.2f}) - footage "
                 f"beats are missing their captions")
            want(m_above < 1.5 and m_band > 6 * max(m_above, 0.05),
                 f"the footage-beat burn disturbed the picture outside the "
                 f"caption band (band {m_band:.2f} vs above {m_above:.2f})")
        finally:
            shutil.rmtree(wd, ignore_errors=True)

    if examined == 0:
        fails.append("this test examined zero frames")
    print(f"caption burn: {examined} check(s) on {SLUG}, {len(cues)} cues, "
          f"{len(fails)} failure(s)")
    return fails


if __name__ == "__main__":
    problems = check()
    for p in problems:
        print(f"  FAIL {p}")
    print("OK" if not problems else f"{len(problems)} FAILURE(S)")
    sys.exit(1 if problems else 0)
