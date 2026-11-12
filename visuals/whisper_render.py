#!/usr/bin/env python3
"""Render a voiced Whisper Almanac episode as a DARK-SCREEN video ($0, ffmpeg).

    .venv/bin/python visuals/whisper_render.py SLUG [--seconds N]   # N: a short proof

The picture is DIM, MOVING footage of each segment's own subject, under the
How We Know long-form footage rules (visuals/whisper_reel.py; her ruling
6 Nov 2026: the Sep 2026 demonetisation wave hit dark-screen sleep
compilations). No flashes, no captions or credits burned in (brand do-not
list; the frame check fails any word on screen); every footage source is
credited in the description.

The audio is the authority: every beat wav in order (loop/whisper_lane
beats()), measured, and the kit (channel/whisper/<slug>/kit.json) is rewritten
with the MEASURED length, so the title's length is the real one, and with
chapter times at each segment start.

The disk guard runs first (loop/render_prune.py): below the floor this is
NAMED STOP [DISK_LOW] and no video is started.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))

import whisper_lane as WL                                   # noqa: E402


def picture(slug: str, kit: dict) -> Path:
    if kit.get("still"):
        p = ROOT / "channel" / "imagery" / "assets" / Path(kit["still"]).name
        if p.exists():
            return p
    return WL.KITS / slug / "thumbnail.png"


def render(slug: str, proof_seconds: float | None = None) -> Path:
    import render_prune as RP                               # noqa: PLC0415
    rc, line = RP.guard()
    print(line)
    if rc:
        raise SystemExit(3)
    c = WL.cfg()
    vis = c["visual"]
    p = WL.parse(WL.SCRIPTS / f"{slug}.md")
    n = len(WL.beats(p))
    ad = WL.audio_dir(slug)
    wavs = [ad / f"{i:04d}.wav" for i in range(n)]
    missing = [w.name for w in wavs if not w.exists()]
    if missing and not proof_seconds:
        raise SystemExit(f"NAMED STOP [WHISPER_AUDIO_INCOMPLETE] {slug}: {len(missing)} of {n} beats missing")
    wavs = [w for w in wavs if w.exists()]
    metas = [json.loads((ad / f"{i:04d}.json").read_text()) for i in range(len(wavs))]
    total = sum(m["duration"] for m in metas)
    seg_starts, t, seen = [], 0.0, set()
    for m in metas:
        if m["segment"] not in seen:
            seen.add(m["segment"])
            seg_starts.append(t)
        t += m["duration"]
    dur = min(total, proof_seconds) if proof_seconds else total
    out = WL.video_path(slug) if not proof_seconds else WL.WORK / slug / f"{slug}-proof.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    # segment lengths from the measured beats, cut to the proof length
    seg_secs: dict[int, float] = {}
    for m in metas:
        seg_secs[m["segment"]] = seg_secs.get(m["segment"], 0.0) + m["duration"]
    srcs = [s["source"] for s in p["segments"]]
    fset = WL.footage_set(p, c)
    if fset:                               # manifesting lanes: their own calm footage set,
        srcs = [f"calm:{fset}"] * len(srcs)  # never How We Know's deep sea (her call 9 Nov 2026)
    segs, left = [], dur
    for i in sorted(seg_secs):
        if left <= 0:
            break
        segs.append((srcs[i], min(seg_secs[i], left)))
        left -= seg_secs[i]
    import footage as F                                     # noqa: PLC0415
    import whisper_reel as R                                # noqa: PLC0415
    if any(R.food_part(s) for s, _ in segs):
        # the long food clips this checkout does not hold yet, sha256-checked
        got = R._ff().fetch_long_missing()
        if got["fetched"] or got["refused"]:
            print(f"  food clips fetched for this Mac: {got['fetched']}; refused: {got['refused'][:3]}")
    try:
        assets = F.usable_assets()
        shots = R.plan_reel(segs, assets, pool_of=lambda s: R.pool(s, assets, c))
    except R.FootageThin as e:
        print(f"NAMED STOP [WHISPER_FOOTAGE_THIN] {slug}: {e}")
        raise SystemExit(5)
    probs = R.reel_problems(shots, sum(x for _, x in segs))
    if probs:
        raise SystemExit(f"NAMED STOP [WHISPER_REEL_REFUSED] {slug}: {len(probs)} footage rule(s) broken: {probs[:3]}")
    kit = WL.kit(slug, measured_s=total, seg_starts=seg_starts, c=c,
                 footage_credits=None if proof_seconds else R.credits(shots))
    if fset and not proof_seconds:         # the upload step refuses any other set
        kit["footage_set"] = fset
        (WL.KITS / slug / "kit.json").write_text(json.dumps(kit, indent=2, ensure_ascii=False) + "\n")
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        lst = Path(td) / "beats.txt"
        lst.write_text("".join(f"file '{w}'\n" for w in wavs))
        voice = Path(td) / "voice.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-t", f"{dur:.3f}", str(voice)], check=True)
        tmp = out.with_suffix(".tmp.mp4")
        R.render_reel(shots, tmp, voice, Path(td))
        got = WL._probe_seconds(tmp)
        if abs(got - dur) > 2.0:
            tmp.unlink()
            raise SystemExit(f"NAMED STOP [WHISPER_RENDER_SHORT] rendered {got:.1f}s of {dur:.1f}s")
        tmp.replace(out)
    print(f"rendered {out.relative_to(ROOT)}: {WL.fmt_len(dur)}, "
          f"{out.stat().st_size / 2**20:.0f} MiB; title: {kit['title']}")
    return out


def plan(slug: str) -> int:
    """--plan: the footage the next render of SLUG would show (no ffmpeg)."""
    c = WL.cfg()
    p = WL.parse(WL.SCRIPTS / f"{slug}.md")
    fset = WL.footage_set(p, c)
    import footage as F                                     # noqa: PLC0415
    import whisper_reel as R                                # noqa: PLC0415
    assets = F.usable_assets()
    srcs = [f"calm:{fset}"] if fset else list(dict.fromkeys(s["source"] for s in p["segments"]))
    for s in srcs:
        pool = R.pool(s, assets, c)
        subs = sorted({R.subject(a) for a in pool})
        print(f"{slug} ({p['kind']}, footage {s}): {len(pool)} clip(s) of {len(subs)} subject(s): "
              f"{'; '.join(subs)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    if a.plan:
        return plan(a.slug)
    render(a.slug, a.seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
