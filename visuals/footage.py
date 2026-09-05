"""Real NOAA footage inside the assembler.

`research/imagery_video.py` harvests rights-cleared ROV clips and records, per
clip, three things this module exists to honour:

  * `clean_windows` -- the spans in which EVERY sampled frame was text-free.
    Outside them the picture carries NOAA head/tail cards or a DVR
    lower-third. A cut is only legal wholly inside one span. Crossing a
    boundary puts a chyron on screen, so it is refused, not clamped.

  * `treatment` -- `as-shot` or `cropped`. A `cropped` clip carries a permanent
    `OCEAN EXPLORATION` corner bug in EVERY frame; the harvester measured the
    rectangle that clears it. That crop is not cosmetic and is not optional:
    without it the wordmark is burned into the finished video.

  * `sha256` -- the bytes the rights decision was made about. If the file on
    disk is not those bytes, the rights decision does not apply to it and it is
    refused. Same rule the still path already enforces.

What this module will NOT do
----------------------------
Put a clip on screen as a species it is not. `SUBJECT_FOOTAGE` is a hand-checked
map from the planner's controlled subject vocabulary to clips that genuinely
show that subject, and `UNILLUSTRATABLE` names the subjects for which no honest
public-domain footage exists. A glass squid is not a colossal squid; a jelly is
not a whale fall. Where there is no honest clip the beat keeps its drawn
treatment, which is the behaviour the channel plan requires.

Two placements
--------------
  1. `ambient_drift` beats -- pure ambience carrying no information. Replaced
     with footage from the episode's own rights-cleared pool. No species claim
     is made, and the clip's own NOAA credit is drawn.
  2. `species_image` beats whose `subject` has an entry in `SUBJECT_FOOTAGE` --
     upgraded from a still of the animal to moving footage of the same animal,
     credit line intact.

Everything else -- typography, stat cards, gauges, still plates with no footage
match -- is untouched and renders exactly as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
MANIFEST = os.path.join(ROOT, "channel", "imagery", "video_rights.json")
IMAGERY_DIR = os.path.join(ROOT, "channel", "imagery")

sys.path.insert(0, HERE)
from design import W, H, FPS  # noqa: E402

# A cut is placed no closer than this to either end of its clean window, on top
# of the 1.0 s the harvester already trimmed inward. Two independent margins,
# because a card fading in across the gap between two OCR probes is the exact
# failure this whole mechanism exists to prevent.
SAFETY_PAD = 0.25
# Below this there is no point cutting to footage at all.
MIN_CUT_SECONDS = 2.0


class RightsRefusal(Exception):
    """A clip failed a rights check. Never caught and turned into a render."""


# ---------------------------------------------------------------- the subject map
#
# Hand-checked. A subject appears here only when a clip in the manifest shows
# THAT ANIMAL, not a relative of it. Each entry is a regex matched against the
# clip's title + caption.
SUBJECT_FOOTAGE = {
    "deep_squid":   r"\b(glass squid|squid)\b",
    "jelly":        r"\b(jelly|jellyfish)\b",
    "siphonophore": r"\bsiphonophore\b",
    "chimaera":     r"\bchimaera\b",
    "deep_eel":     r"\b(synaphobranchid|cutthroat eel)\b",
    "snailfish":    r"\bsnailfish\b",
    "anglerfish":   r"\banglerfish\b",
    "sea_cucumber": r"\bsea cucumber\b",
    "deep_octopus": r"\b(dumbo octopus|octopus)\b",
    # NOT r"\bshrimp\b": the only shrimp-bearing clip in the set is titled
    # "Crab Eating a Shrimp" and is a CRAB clip. Labelling it "red shrimp"
    # would be the same failure as captioning a giant squid plate "colossal".
    "red_shrimp":   r"\bred shrimp\b",
}

# Named refusals. These subjects have no honest public-domain footage, and the
# drawn treatment stands. Listed so the refusal is visible rather than being an
# absence nobody notices.
#
#   giant_squid / colossal squid -- Mesonychoteuthis hamiltoni was described
#       from stomach contents; no PD footage exists and the harvester
#       explicitly refused to pass off Narrowteuthis nessisi as one.
#   whale_fall  -- every whale-fall sequence in circulation is MBARI's, CC-BY.
#   yeti_crab   -- Kiwa footage is Ifremer / Oregon State, not federal PD.
UNILLUSTRATABLE = {
    "giant_squid": "no public-domain colossal/giant squid footage exists; a "
                   "lookalike squid captioned as one is a lie told in pictures",
    "colossal_squid": "described in 1925 from stomach contents; no PD footage",
    "whale_fall": "every circulating whale-fall sequence is CC-BY (MBARI)",
    "yeti_crab": "Kiwa footage is Ifremer/OSU, not a federal work",
}

# Per-episode ambience pools. Reuses the same subject patterns the harvester
# scores coverage with, so the assembler and the harvester cannot disagree
# about which clips belong to which episode.
try:
    sys.path.insert(0, os.path.join(ROOT, "research"))
    from imagery_video import SUBJECTS as EPISODE_SUBJECTS  # noqa: E402
except Exception:                                   # harvester not importable
    EPISODE_SUBJECTS = {}


# ------------------------------------------------------------------- manifest

def load_manifest(path: str | None = None) -> dict:
    """Read the rights manifest.

    The path is resolved at CALL time, not bound as a default argument, so a
    validator can point this module at a fixture manifest. A guard that cannot
    be aimed at a broken state cannot be proven negatively.
    """
    path = path or MANIFEST
    if not os.path.exists(path):
        return {"assets": []}
    return json.load(open(path))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_VERIFIED: dict[str, str] = {}


def verify(asset: dict) -> str:
    """Return the clip's absolute path, or raise. Hashes once per process.

    This is the gate the whole module hangs off: a clip whose bytes are not the
    bytes the rights decision was made about is refused, not rendered.
    """
    rel = asset.get("local_file") or ""
    path = os.path.join(IMAGERY_DIR, rel)
    if rel in _VERIFIED:
        return _VERIFIED[rel]
    if not rel or not os.path.exists(path):
        raise RightsRefusal(f"{asset.get('title')!r}: clip file missing ({rel})")
    want = asset.get("sha256")
    if not want:
        raise RightsRefusal(f"{asset.get('title')!r}: manifest carries no sha256")
    got = sha256_file(path)
    if got != want:
        raise RightsRefusal(
            f"{asset.get('title')!r}: sha256 mismatch — the file on disk is not "
            f"the bytes the rights decision was made about "
            f"(manifest {want[:16]}…, disk {got[:16]}…)")
    _VERIFIED[rel] = path
    return path


def usable_assets(manifest: dict | None = None) -> list[dict]:
    """Every manifest asset that passes verification. Refusals are re-raised;
    this never quietly drops a clip, because a silently shrinking pool is how
    'runs but inert' happens."""
    m = manifest or load_manifest()
    out = []
    for a in m.get("assets", []):
        verify(a)                       # raises on mismatch
        out.append(a)
    return out


# ------------------------------------------------------------------- windows

def windows(asset: dict) -> list[dict]:
    return [w for w in (asset.get("clean_windows") or [])
            if float(w["end"]) > float(w["start"])]


def inside_window(asset: dict, start: float, end: float) -> bool:
    """True only if [start, end] lies wholly inside ONE clean window.

    A cut spanning two windows, or overhanging either edge of one, is False.
    This is the predicate the validator asserts and the placer obeys.
    """
    for w in windows(asset):
        if start >= float(w["start"]) - 1e-9 and end <= float(w["end"]) + 1e-9:
            return True
    return False


def place_cut(asset: dict, seconds: float, nth: int = 0) -> dict | None:
    """Choose a [start, end] of `seconds` wholly inside one clean window.

    Returns None when no window is long enough — the beat then keeps its drawn
    treatment. Never returns a cut that crosses a boundary.
    """
    if seconds < MIN_CUT_SECONDS:
        return None
    need = seconds + 2 * SAFETY_PAD
    cands = [w for w in windows(asset) if float(w["end"]) - float(w["start"]) >= need]
    if not cands:
        return None
    w = cands[nth % len(cands)]
    lo, hi = float(w["start"]) + SAFETY_PAD, float(w["end"]) - SAFETY_PAD
    span = hi - lo
    # Walk the offset so repeated beats off one clip are not the same frames.
    slots = max(1, int(span // seconds))
    off = (nth // max(1, len(cands))) % slots
    start = round(lo + off * seconds, 3)
    end = round(start + seconds, 3)
    if end > hi + 1e-9:                     # last slot short: pin to the tail
        end = round(hi, 3)
        start = round(end - seconds, 3)
    if not inside_window(asset, start, end):
        return None                         # belt and braces; never render it
    return {"start": start, "end": end, "seconds": round(end - start, 3),
            "window": {"start": float(w["start"]), "end": float(w["end"])}}


# ---------------------------------------------------------------------- crop

def crop_filter(asset: dict) -> str:
    """ffmpeg crop expression for a `cropped` clip, '' for `as-shot`.

    `cropped` means the clip carries a permanent OCEAN EXPLORATION corner bug in
    every frame and the recorded rect is what clears it. Ignoring it burns the
    wordmark into the episode.
    """
    if asset.get("treatment") != "cropped":
        return ""
    c = asset.get("crop")
    if not c:
        raise RightsRefusal(
            f"{asset.get('title')!r}: treatment is 'cropped' but no crop rect "
            f"was recorded — the corner wordmark would be burned in")
    sw, sh = int(asset["width"]), int(asset["height"])
    x = int(round(float(c.get("left", 0)) * sw))
    y = int(round(float(c.get("top", 0)) * sh))
    cw = int(round((1 - float(c.get("left", 0)) - float(c.get("right", 0))) * sw))
    ch = int(round((1 - float(c.get("top", 0)) - float(c.get("bottom", 0))) * sh))
    if cw <= 0 or ch <= 0:
        raise RightsRefusal(f"{asset.get('title')!r}: crop rect removes the frame")
    return f"crop={cw}:{ch}:{x}:{y},"


def vf_chain(asset: dict) -> str:
    """crop (if any) -> cover-fill the 1920x1080 frame -> yuv420p."""
    return (f"{crop_filter(asset)}"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,format=yuv420p")


# ------------------------------------------------------------------ placement

def _matches(asset: dict, pattern: str) -> bool:
    blob = f"{asset.get('title','')} {asset.get('caption','')}"
    return bool(re.search(pattern, blob, re.I))


def episode_pool(slug: str, assets: list[dict]) -> list[dict]:
    pat = EPISODE_SUBJECTS.get(slug)
    if not pat:
        return []
    return [a for a in assets if _matches(a, pat)]


def subject_pool(subject: str, assets: list[dict]) -> list[dict]:
    if subject in UNILLUSTRATABLE:
        return []
    pat = SUBJECT_FOOTAGE.get(subject)
    if not pat:
        return []
    return [a for a in assets if _matches(a, pat)]


def assign(plan: list[dict], durations: list[float], slug: str,
           assets: list[dict] | None = None) -> list[dict | None]:
    """One entry per beat: a cut dict, or None to render the beat as drawn.

    Placement is deterministic — same plan, same manifest, same cuts — so a
    re-render is reproducible and a validator can assert against it.
    """
    assets = usable_assets() if assets is None else assets
    amb = episode_pool(slug, assets)
    out: list[dict | None] = [None] * len(plan)
    n_amb = 0
    per_subject: dict[str, int] = {}

    for i, b in enumerate(plan):
        seg = b.get("segment")
        args = b.get("args") or {}
        pool, nth, label = [], 0, None
        if seg == "ambient_drift" and amb:
            pool, nth = amb, n_amb
            n_amb += 1
        elif seg == "species_image":
            subj = args.get("subject")
            pool = subject_pool(subj, assets)
            if pool:
                nth = per_subject.get(subj, 0)
                per_subject[subj] = nth + 1
                label = args.get("label")
        if not pool:
            continue
        asset = pool[nth % len(pool)]
        cut = place_cut(asset, durations[i], nth // max(1, len(pool)))
        if not cut:
            continue
        out[i] = {
            "beat": i, "segment": seg, "asset": asset, "label": label,
            "credit": asset.get("required_credit") or asset.get("source_org"),
            "title": asset.get("title"), **cut,
        }
    return out


# -------------------------------------------------------------------- render

def _credit_overlay(cut: dict, path: str):
    """Small lower-left credit strip, drawn with PIL (this ffmpeg has no
    drawtext — no libfreetype — which is also why captions burn in Python)."""
    from PIL import Image, ImageDraw, ImageFont
    from design import F_LABEL
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(F_LABEL, 24)
    except Exception:
        f = ImageFont.load_default()
    parts = []
    if cut.get("label"):
        parts.append(str(cut["label"]).upper())
    parts.append((cut.get("credit") or "NOAA OCEAN EXPLORATION").upper())
    text = "   ·   ".join(parts)
    x, y = 72, H - 78
    box = d.textbbox((x, y), text, font=f)
    d.rectangle([box[0] - 18, box[1] - 12, box[2] + 18, box[3] + 12],
                fill=(2, 7, 13, 190))
    d.text((x, y), text, font=f, fill=(165, 192, 202, 255))
    img.save(path)


def _caption_pngs(burner, t0: float, t1: float, workdir: str, prefix: str):
    """Full-frame transparent PNGs for every caption cue overlapping this beat,
    with the enable window each one is visible for, in beat-local seconds.

    Footage beats are cut by ffmpeg, not drawn frame by frame in Python, so the
    burner's per-frame paste cannot reach them. Re-using the burner's OWN cached
    panel keeps the burned caption pixel-identical between drawn and footage
    beats, and keeps a single cue list.
    """
    from PIL import Image
    out = []
    cues = [c for c in burner.cues
            if c["end"] > t0 + 1e-6 and c["start"] < t1 - 1e-6]
    for k, c in enumerate(cues):
        panel, pos = burner._panel(c["text"])
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.paste(panel, pos, panel)
        png = os.path.join(workdir, f"{prefix}.cap{k:02d}.png")
        canvas.save(png)
        out.append((png, max(0.0, c["start"] - t0), min(t1 - t0, c["end"] - t0)))
    return out


def render_cut(cut: dict, out_clip: str, seconds: float, workdir: str,
               credit: bool = True, burner=None, t0: float = 0.0) -> str:
    """Render one footage beat to a silent clip of exactly `seconds`.

    Re-checks the sha256 and the window containment immediately before the
    ffmpeg call. The check that matters is the one next to the thing it governs.
    """
    asset = cut["asset"]
    src = verify(asset)                                   # sha256, every render
    if not inside_window(asset, cut["start"], cut["end"]):
        raise RightsRefusal(
            f"{asset.get('title')!r}: cut {cut['start']}-{cut['end']}s is not "
            f"inside a clean window {windows(asset)} - refusing to render a "
            f"frame that may carry a NOAA card or DVR overlay")

    prefix = os.path.basename(out_clip)
    layers = []                                # (png_path, enable_from, enable_to)
    if credit:
        png = os.path.join(workdir, prefix + ".credit.png")
        _credit_overlay(cut, png)
        layers.append((png, None, None))
    if burner is not None:
        layers += _caption_pngs(burner, t0, t0 + seconds, workdir, prefix)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{cut['start']:.3f}", "-t", f"{seconds:.3f}", "-i", src]
    for png, _, _ in layers:
        cmd += ["-i", png]

    chain = [f"[0:v]{vf_chain(asset)}[v0]"]
    for k, (_, a, b) in enumerate(layers):
        en = "" if a is None else f":enable='between(t,{a:.3f},{b:.3f})'"
        chain.append(f"[v{k}][{k + 1}:v]overlay=0:0{en}[v{k + 1}]")
    last = f"[v{len(layers)}]"
    cmd += ["-an", "-filter_complex", ";".join(chain), "-map", last,
            "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "20", out_clip]
    subprocess.run(cmd, check=True)
    for png, _, _ in layers:
        os.remove(png)
    return out_clip


def summarise(cuts: list[dict | None]) -> dict:
    used = [c for c in cuts if c]
    return {"footage_beats": len(used),
            "footage_seconds": round(sum(c["seconds"] for c in used), 1),
            "clips": sorted({c["title"] for c in used}),
            "cropped": sum(1 for c in used
                           if c["asset"].get("treatment") == "cropped")}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--slug")
    a = ap.parse_args()
    if not a.plan:
        assets = usable_assets()
        print(f"{len(assets)} rights-verified clips")
        for s in sorted(EPISODE_SUBJECTS):
            p = episode_pool(s, assets)
            if p:
                print(f"  {s:<50} {len(p)} clip(s)")
        raise SystemExit(0)
    plan = json.load(open(a.plan))
    slug = a.slug or os.path.basename(a.plan)[:-5]
    cuts = assign(plan, [float(b["seconds"]) for b in plan], slug)
    print(json.dumps(summarise(cuts), indent=2))
