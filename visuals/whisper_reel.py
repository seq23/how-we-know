"""Dim, MOVING footage for a Whisper Almanac episode - the How We Know long-form
footage rules, reused, never a dark screen.

Her ruling 6 Nov 2026 (money case): "Dim, moving footage, not a dark screen.
The Sep 2026 demonetisation wave hit near-identical dark-screen sleep
compilations. Reuse the HWK long-form footage rules." Those rules (spry brain,
3 Nov 2026), enforced here in code by reel_problems():

  * a new distinct shot at least every 20 seconds (SHOT_S <= 20);
  * a clip (and so any source moment) never repeats within 3 minutes;
  * no single subject over about 25% of screen time while other subjects exist;
  * on a shortfall widen the pool (the whole episode's subjects), never filler:
    a reel that cannot meet the rules is refused (WHISPER_FOOTAGE_THIN).

Each segment's pool is the footage of the How We Know episode it was rewritten
from (visuals/footage.episode_pool: NOAA first, licence-checked stock second),
so the picture shows the named subject. Every cut sits inside a clean window,
is sha256-verified (visuals/footage.render_cut). No credit is burned into the
picture: the final frame check fails any word on screen (as How We Know's
long-form, owner 2026-11-03); every source is credited in the description
(credits()). The reel is dimmed and desaturated in one pass for sleep.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "visuals"))

SHOT_S = 18.0
REPEAT_GAP_S = 180.0
SUBJECT_CAP = 0.25
DIM = "eq=brightness=-0.16:saturation=0.7:contrast=0.92"


class FootageThin(Exception):
    pass


def subject(asset: dict) -> str:
    return (asset.get("subject") or asset.get("title") or asset.get("local_file") or "?").lower()


def min_clips(shot_s: float = SHOT_S) -> int:
    """Clips a part needs so no clip returns inside REPEAT_GAP_S."""
    return int(REPEAT_GAP_S // shot_s) + 2


def pictureable(slug: str, assets: list[dict]) -> bool:
    import footage as F                                    # noqa: PLC0415
    return len(F.episode_pool(slug, assets)) >= min_clips()


def plan_reel(segments: list[tuple[str, float]], assets: list[dict], pool_of=None,
              shot_s: float = SHOT_S) -> list[dict]:
    """[(source slug, seconds)] -> shots [{asset, cut, segment, t0, seconds}]."""
    import footage as F                                    # noqa: PLC0415
    pool_of = pool_of or (lambda slug: F.episode_pool(slug, assets))
    pools = [pool_of(s) for s, _ in segments]
    # FOOTAGE OF THE SUBJECT NAMED, PART BY PART (her call 6 Nov 2026): a part
    # draws only on its own source episode's footage - never another part's
    # (deep-sea footage under a galaxy part reads as low effort). Too few
    # clips to avoid a repeat inside REPEAT_GAP_S is refused, never padded.
    need = min_clips(shot_s)
    for (src, _), p in zip(segments, pools):
        if len(p) < need:
            raise FootageThin(f"{src}: {len(p)} clip(s) of its own subject; a part needs {need}")
    last_t: dict[int, float] = {}
    uses: dict[int, int] = {}
    shots, t = [], 0.0
    for si, (_, seg_s) in enumerate(segments):
        end = t + seg_s
        local = pools[si]
        ri = 0
        while t < end - 1e-6:
            sec = min(shot_s, end - t)
            if sec < 2.0 and shots:                        # a sliver joins the last shot
                shots[-1]["seconds"] += sec
                t = end
                break
            pick = None
            for cand_pool in (local,):
                n = len(cand_pool)
                for k in range(n):
                    a = cand_pool[(ri + k) % n]
                    i = id(a)
                    if t - last_t.get(i, -1e9) < REPEAT_GAP_S + 1.0:
                        continue
                    cut = F.place_cut(a, sec, uses.get(i, 0))
                    if cut is None:
                        cut = F.place_cut(a, sec, 0) if uses.get(i, 0) else None
                    if cut is None:
                        continue
                    pick = (a, cut)
                    ri = (ri + k + 1) % n
                    break
                if pick:
                    break
            if not pick:
                raise FootageThin(f"segment {si + 1}: no clip free of a repeat inside "
                                  f"{REPEAT_GAP_S:.0f} s at {t:.0f} s (pool {len(local)})")
            a, cut = pick
            shots.append({"asset": a, "cut": cut, "segment": si, "t0": round(t, 3), "seconds": round(sec, 3)})
            last_t[id(a)] = t
            uses[id(a)] = uses.get(id(a), 0) + 1
            t += sec
    return shots


def reel_problems(shots: list[dict], total_s: float) -> list[str]:
    """The HWK long-form footage rules, checked on the plan that is rendered."""
    out = []
    if not shots:
        return ["EMPTY no shots planned"]
    covered = sum(s["seconds"] for s in shots)
    if abs(covered - total_s) > 1.0:
        out.append(f"COVERAGE shots cover {covered:.0f} s of {total_s:.0f} s")
    seen: dict[str, float] = {}
    share: dict[str, float] = {}
    for s in shots:
        if s["seconds"] > 20.0 + 2.0:
            out.append(f"SHOT_TOO_LONG {s['seconds']:.0f} s at {s['t0']:.0f} s (a new shot every 20 s)")
        key = s["asset"].get("local_file") or s["asset"].get("title")
        prev = seen.get(key)
        if prev is not None and s["t0"] - prev < REPEAT_GAP_S:
            out.append(f"REPEAT {key} again after {s['t0'] - prev:.0f} s (at least {REPEAT_GAP_S:.0f})")
        seen[key] = s["t0"]
        share[subject(s["asset"])] = share.get(subject(s["asset"]), 0) + s["seconds"]
    if len(share) > 1:
        for subj, sec in share.items():
            if sec / covered > SUBJECT_CAP + 0.02:
                out.append(f"SUBJECT_OVER_CAP {subj!r} holds {sec / covered:.0%} of the screen (cap ~25%)")
    return out


def credits(shots: list[dict]) -> list[str]:
    """One description line per footage source the reel shows."""
    import longform_picture as LP                          # noqa: PLC0415
    return sorted({LP._credit(s["asset"]) for s in shots} - {"", None})


def render_reel(shots: list[dict], out: Path, audio: Path, workdir: Path) -> Path:
    """Render segment by segment (small temp files on an 8 GB Mac), dim it,
    and mux the voice. The audio is the authority for length. 720p at most
    900 kb/s: about 1 GB for a 2.25-hour episode (a sleeping viewer, dim
    slow footage), small enough for the Mac and the free storage caps."""
    import footage as F                                    # noqa: PLC0415
    seg_files = []
    for si in sorted({s["segment"] for s in shots}):
        with tempfile.TemporaryDirectory(dir=workdir) as td:
            parts = []
            for k, s in enumerate(x for x in shots if x["segment"] == si):
                p = os.path.join(td, f"{k:04d}.mp4")
                F.render_cut({**s["cut"], "asset": s["asset"]}, p, s["seconds"], td, credit=False)
                parts.append(p)
            lst = Path(td) / "parts.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in parts))
            seg = workdir / f"seg{si:02d}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-vf", f"{DIM},scale=1280:720", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "28", "-maxrate", "900k", "-bufsize", "1800k", "-an", str(seg)], check=True)
            seg_files.append(seg)
    lst = workdir / "segs.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in seg_files))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-shortest", "-movflags", "+faststart",
                    str(out)], check=True)
    for p in seg_files:
        p.unlink(missing_ok=True)
    return out
