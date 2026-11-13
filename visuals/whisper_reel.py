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
(credits()). Each cut is dimmed and desaturated for sleep, down to a luma
floor, never to black (dim_for).
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
# Dim, never black (her 6 Nov rule; 9 Nov measurement: a flat -0.16 turned
# every already-dark deep-sea cut near-black, 42 of 310 sampled frames of the
# W45 render under luma 6). Each cut is dimmed only down to DIM_FLOOR mean luma.
DIM_MAX = 0.16
DIM_FLOOR = 28.0


def dim_for(luma: float) -> str:
    """The eq filter for a cut whose darkest sampled frame has mean luma `luma`."""
    b = min(DIM_MAX, max(0.0, (luma - DIM_FLOOR) / 255.0))
    return f"eq=brightness={-b:.3f}:saturation=0.7:contrast=0.92"


def cut_luma(path: str, seconds: float, workdir: str) -> float:
    """Darkest mean luma of three frames of a rendered cut."""
    from PIL import Image, ImageStat                       # noqa: PLC0415
    vals = []
    for k, t in enumerate((0.2, seconds / 2, max(0.2, seconds - 0.5))):
        j = os.path.join(workdir, f"l{k}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path,
                        "-frames:v", "1", "-vf", "scale=192:-2", j], check=True)
        if os.path.exists(j):
            vals.append(ImageStat.Stat(Image.open(j).convert("L")).mean[0])
            os.remove(j)
    return min(vals) if vals else 255.0


class FootageThin(Exception):
    pass


def subject(asset: dict) -> str:
    return (asset.get("subject") or asset.get("title") or asset.get("local_file") or "?").lower()


def pool(source: str, assets: list[dict], c: dict | None = None) -> list[dict]:
    """A part's clips (_pool), less every clip the final frame check refused
    on a finished render (loop/whisper_lane.refused_clips; 13 Nov 2026: a CG
    starfield and a 3D-rendered ring each failed a finished video, which then
    sat set aside with nothing re-made)."""
    sys.path.insert(0, str(ROOT / "loop"))
    import whisper_lane as WL                              # noqa: PLC0415
    no = WL.refused_clips()
    return [a for a in _pool(source, assets, c) if a.get("post_id") not in no]


def _pool(source: str, assets: list[dict], c: dict | None = None) -> list[dict]:
    """A part's clips. "calm:<set>" (the manifesting lanes, her call 9 Nov
    2026) is that set's harvested clips, interleaved subject by subject so no
    subject crowds the screen; any other source is a How We Know episode's own
    footage (footage.episode_pool)."""
    import footage as F                                    # noqa: PLC0415
    part = food_part(source)
    if part:
        return food_pool(part)
    if not source.startswith("calm:"):
        # '<slug>#<Part>' is one part of a How We Know script: its footage
        return F.episode_pool(source.split("#", 1)[0], assets)
    name = source.split(":", 1)[1]
    if c is None:
        sys.path.insert(0, str(ROOT / "loop"))
        import whisper_lane as WL                          # noqa: PLC0415
        c = WL.cfg()
    refused = c["calm_footage"].get("refused") or {}
    by: dict[str, list[dict]] = {}
    for a in assets:
        # Only clips that hold a whole shot: a shorter one is never placed,
        # and counting it would let the long ones crowd the screen.
        if (a.get("calm_set") == name and float(a.get("seconds") or 0) >= SHOT_S + 1.0
                and a.get("post_id") not in refused):
            by.setdefault(subject(a), []).append(a)
    out, k = [], 0
    while any(k < len(v) for v in by.values()):
        out += [v[k] for v in by.values() if k < len(v)]
        k += 1
    return out


FOOD_SCRIPTS = ROOT / "scripts" / "food"


def food_part(source: str) -> str | None:
    """'<food script slug>#<Part>' -> that part's food segment ('bread'); else None.
    Her week (9 Nov 2026): the food-history sleep video is How We Know's
    fact-checked food script, its Bread, Steak and Chocolate parts as segments."""
    if "#" not in source:
        return None
    slug, part = source.split("#", 1)
    return part.strip().lower() if (FOOD_SCRIPTS / f"{slug}.md").exists() else None


def _ff():
    sys.path.insert(0, str(ROOT / "research"))
    import food_footage as FF                              # noqa: PLC0415
    return FF


def food_asset(rec: dict) -> dict:
    """A channel/imagery/food_clips.json record in the shape visuals/footage.py
    places and renders: its clean windows (reviewed ranges, else the clip less
    its black spans) and, for a stock library, the licence wording committed
    under channel/imagery/licences/ that footage.verify re-checks."""
    FF = _ff()
    a = {**rec, "seconds": float(rec.get("duration_s") or 0),
         "clean_windows": FF.clean_windows(rec),
         # under 1.0: the clip is a little short of a shot and plays slowed
         "speed": FF.speed_for(rec, SHOT_S + 1.0) or 1.0,
         "post_id": f"{rec.get('source')}:{rec.get('source_id')}"}
    if rec.get("source") in ("pixabay", "mixkit", "pexels") and rec.get("licence_text"):
        a["commercial_use_permitted"] = True
        a["licence_wording"] = (ROOT / "channel" / "imagery" / rec["licence_text"]).read_text()
    return a


def food_pool(part: str, index: list[dict] | None = None, present=None) -> list[dict]:
    """A food part's clips: its own food only (never another part's), clean
    rights (food_footage.record_problems), long enough to hold a whole shot
    (a shorter clip is never placed, so it is never counted), and on this Mac
    (a clip this checkout does not hold is fetched first by
    food_footage.fetch_long_missing, never counted on faith). A clip a little
    short of a shot counts when it holds one at no less than two-thirds speed
    (food_footage.speed_for; 13 Nov 2026)."""
    FF = _ff()
    index = FF.load().get("index") or [] if index is None else index
    present = present or (lambda r: (FF.IMAGERY / r["local_file"]).exists())
    return [food_asset(r) for r in index
            if r.get("segment") == part and not r.get("excluded")
            and not FF.record_problems(r) and FF.speed_for(r, SHOT_S + 1.0) is not None and present(r)]


def min_clips(shot_s: float = SHOT_S) -> int:
    """Clips a part needs so no clip returns inside REPEAT_GAP_S."""
    return int(REPEAT_GAP_S // shot_s) + 2


def pictureable(source: str, assets: list[dict]) -> bool:
    return len(pool(source, assets)) >= min_clips()


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
                    src = sec * float(a.get("speed") or 1.0)   # the source seconds this shot shows
                    cut = F.place_cut(a, src, uses.get(i, 0))
                    if cut is None:
                        cut = F.place_cut(a, src, 0) if uses.get(i, 0) else None
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
                raw = os.path.join(td, f"{k:04d}-raw.mp4")
                speed = float(s["asset"].get("speed") or 1.0)
                src_s = s["seconds"] * speed
                F.render_cut({**s["cut"], "asset": s["asset"]}, raw, src_s, td, credit=False)
                # a slowed clip: its frames are spread over the full shot
                slow = [f"setpts=PTS/{speed:.3f}", f"fps={F.FPS}"] if speed < 1.0 else []
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-vf",
                                ",".join(slow + [dim_for(cut_luma(raw, src_s, td)), "scale=1280:720"]),
                                "-t", f"{s['seconds']:.3f}",
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", p],
                               check=True)
                os.remove(raw)
                parts.append(p)
            lst = Path(td) / "parts.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in parts))
            seg = workdir / f"seg{si:02d}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-vf", "scale=1280:720", "-c:v", "libx264", "-preset", "veryfast",
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
