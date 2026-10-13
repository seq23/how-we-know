"""Real footage, prepared for the food preset: trims, slow motion, seamless loops,
push-ins, and the IMPOSSIBLE-SCALE composites (a wall of pours, a kaleidoscope).

    .venv/bin/python visuals/food_motion.py demo CLIP.mp4 OUT_DIR   # one of each treatment

Owner verdict on sample round 1 (2026-10-13): real MOVEMENT - pours, drips,
chocolate falling in sheets - and the "impossible scale" feel (a wall of pours,
a field of dough), made from real clips, at $0, on this Mac. Every treatment is
one ffmpeg pass that writes EXACTLY round(dur * FPS) frames of 1920x1080 at 30
fps (asserted after), so the renderer (visuals/food.py) streams them frame by
frame and never holds a clip in memory (8 GB Mac: a 10 s 1080p clip decoded
whole is 1.9 GB).

TREATMENTS (each a pure function of its source clip and parameters; the spec
records which shot used which, so NOTE.txt can say what is a composite):
  play     trim from the clip's usable span, cover-crop to 16:9; a clip shorter
           than its shot plays forward then backward (ping-pong) - a seamless
           loop, never a jump cut back to the start.
  slowmo   the same at SLOWMO x slower, frames blended (minterpolate blend -
           cheap and honest; no invented motion vectors).
  pushin   play + a slow push-in (scale 1.00 -> PUSH_IN over the shot).
  wall     COMPOSITE: the clip tiled GRID_COLS x GRID_ROWS, every tile started
           at a staggered offset and alternate tiles mirrored, so one pour
           becomes a wall of pours that never move in step.
  kaleido  COMPOSITE: four-way mirror symmetry of the clip's centre, drifting slowly.

The grade is NOT applied here: visuals/food.py applies the one food LUT to
every frame of every treatment, stills and clips alike, so the whole video
reads as one look and check_frames() can prove it on proof frames.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1920, 1080, 30
SLOWMO = 2.0
# SPEED-RAMPED SLOW MOTION (owner, 13 Oct 2026: "keep speed-ramped slow motion
# as the default treatment for pours and drips"). A pour starts at real speed
# and eases into RAMP_TO x slower over its first RAMP_IN_S seconds of source,
# then holds there; frames blended, never invented.
RAMP_TO = 2.6
RAMP_IN_S = 0.8
RAMP_USES = {"pour", "drip", "liquid", "sheets", "coat"}
PUSH_IN = 1.12
GRID_COLS, GRID_ROWS = 4, 3
KALEIDO_DRIFT = 0.6          # share of the free margin the mirror window drifts across
KALEIDO_PERIOD_S = 24.0      # one slow drift cycle
TREATMENTS = ("play", "slowmo", "pushin", "wall", "kaleido")
COMPOSITES = ("wall", "kaleido")
COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
# One frame shape for every treatment, so the cut from a clip to a composite reads as one film:
# a soft dark vignette (the warm-dark ground); the colour grade itself is visuals/food.py's LUT.
VIGNETTE = "vignette=angle=PI/6"


def probe_duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def count_frames(path: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return int(r.stdout.strip().split(",")[0])


def _span(rec: dict, clip_dur: float, use: int = 0) -> tuple[float, float]:
    """The usable part of a clip: one of its recorded ranges (the `use`-th, so a
    clip shown twice shows different footage), else the whole clip minus 0.3 s at
    each end (stock clips often open on a fade)."""
    rng = rec.get("ranges") or []
    if rng:
        a, b = rng[use % len(rng)]
        return float(a), float(min(b, clip_dur))
    pad = 0.3 if clip_dur > 3 else 0.0
    return pad, clip_dur - pad


def ramped_len(span: float, k: float = RAMP_TO, r: float = RAMP_IN_S) -> float:
    r = min(r, span)
    return r * (1 + k) / 2 + k * (span - r)


def _base_chain(src_span_s: float, need_s: float, speed: float, ramp: bool = False) -> str:
    """Filters that turn [0, src_span_s] of input into >= need_s seconds at 30 fps,
    slowed by `speed` (or ramped from real speed to RAMP_TO), ping-ponged when the
    slowed span is too short."""
    if ramp:
        k, r = RAMP_TO, min(RAMP_IN_S, src_span_s)
        f = [f"setpts='(if(lt(T,{r:.3f}),T+({k - 1:.3f})/(2*{r:.3f})*T*T,"
             f"{r * (1 + k) / 2:.4f}+{k:.3f}*(T-{r:.3f})))/TB'",
             f"minterpolate=fps={FPS}:mi_mode=blend"]
        out_len = ramped_len(src_span_s, k, r)
    else:
        f = [f"setpts={speed:.4f}*PTS"] if speed != 1.0 else []
        out_len = src_span_s * speed
    if ramp:
        pass
    elif speed != 1.0:
        f.append(f"minterpolate=fps={FPS}:mi_mode=blend")
    else:
        f.append(f"fps={FPS}")
    chain = ",".join(f)
    if out_len + 0.05 < need_s:
        # forward + reverse = a seamless loop; repeated as many times as needed
        reps = int(need_s / (2 * out_len)) + 1
        chain += (f",split[fw][bw0];[bw0]reverse[bw];[fw][bw]concat=n=2:v=1:a=0,"
                  f"loop=loop={reps}:size=32767:start=0")
    return chain


def graph(rec: dict, dur: float, treatment: str, clip_dur: float, seed: int = 0,
          offset: float = 0.0) -> dict:
    """The ffmpeg filter graph for one treatment - a pure function (no ffmpeg
    needed), so a host without ffmpeg can still check what would be drawn."""
    if treatment not in TREATMENTS:
        raise ValueError(f"unknown treatment {treatment!r}")
    n = int(round(dur * FPS))
    cd = clip_dur
    if rec.get("ranges"):
        a, b = _span(rec, cd, int(round(offset / 2.5)))
    else:
        a, b = _span(rec, cd)
        a = min(b - 0.5, a + offset) if b - a > 1.0 else a
    span = max(0.2, b - a)
    ramp = treatment == "slowmo" and bool(set(rec.get("uses") or []) & RAMP_USES)
    speed = (RAMP_TO if ramp else SLOWMO) if treatment == "slowmo" else 1.0
    trim = f"trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS"
    if rec.get("crop"):                       # x, y, w, h as fractions of the source frame
        cx, cy, cw, ch = rec["crop"]
        trim += f",crop=trunc(iw*{cw}/2)*2:trunc(ih*{ch}/2)*2:trunc(iw*{cx}):trunc(ih*{cy})"
    base = _base_chain(span, dur + 0.5, speed, ramp)
    if treatment in ("play", "slowmo"):
        vf = f"[0:v]{trim},{base},{COVER}[v]"
    elif treatment == "pushin":
        z = PUSH_IN - 1.0
        vf = (f"[0:v]{trim},{base},{COVER},"
              f"scale=w='trunc({W}*(1+{z}*t/{dur:.3f})/2)*2':h='trunc({H}*(1+{z}*t/{dur:.3f})/2)*2'"
              f":eval=frame,crop={W}:{H}[v]")
    elif treatment == "wall":
        tw, th = W // GRID_COLS, H // GRID_ROWS
        k = GRID_COLS * GRID_ROWS
        parts = [f"[0:v]{trim},{base},scale={tw}:{th}:force_original_aspect_ratio=increase,"
                 f"crop={tw}:{th},split={k}" + "".join(f"[s{i}]" for i in range(k))]
        loop_s = max(span * speed, 1.0)
        tiles = []
        for i in range(k):
            # staggered start: each tile begins at a different point of the loop
            off = ((i * 7 + seed) % k) / k * loop_s
            flip = ",hflip" if (i + i // GRID_COLS) % 2 else ""
            parts.append(f"[s{i}]trim=start={off:.3f},setpts=PTS-STARTPTS{flip}[t{i}]")
            tiles.append(f"[t{i}]")
        layout = "|".join(f"{(i % GRID_COLS) * tw}_{(i // GRID_COLS) * th}" for i in range(k))
        parts.append("".join(tiles) + f"xstack=inputs={k}:layout={layout}:fill=black,"
                     f"scale={W}:{H},setsar=1[v]")
        vf = ";".join(parts)
        base = _base_chain(span, dur + loop_s + 0.5, speed)   # room for the largest offset
        parts[0] = (f"[0:v]{trim},{base},scale={tw}:{th}:force_original_aspect_ratio=increase,"
                    f"crop={tw}:{th},split={k}" + "".join(f"[s{i}]" for i in range(k)))
        vf = ";".join(parts)
    else:                                                     # kaleido
        # Four-way mirror of a window that drifts slowly over the clip's CENTRE
        # (where the subject is), so the symmetry turns without ever showing an
        # empty corner or a rotation's black edge.
        qw, qh = W // 2, H // 2
        drift = f"{KALEIDO_DRIFT}*sin(2*PI*t/{KALEIDO_PERIOD_S})"
        vf = (f"[0:v]{trim},{base},scale={int(W * 1.25)}:{int(H * 1.25)}:force_original_aspect_ratio=increase,"
              f"crop={int(W * 1.25)}:{int(H * 1.25)},"
              f"crop={qw}:{qh}:x='(iw-{qw})/2+(iw-{qw})/2*{drift}':y='(ih-{qh})/2+(ih-{qh})/2*{drift}*0.6',"
              f"split[q0][q1];[q1]hflip[q1f];[q0][q1f]hstack,split[h0][h1];[h1]vflip[h1f];"
              f"[h0][h1f]vstack,setsar=1[v]")
    vf = vf[:-3] + f",{VIGNETTE}[v]"                      # every treatment ends "...[v]"
    return {"vf": vf, "frames": n, "span": [round(a, 3), round(b, 3)], "speed": speed,
            "ramp": ramp}


def prepare(rec_path: str, rec: dict, dur: float, out: Path, treatment: str = "play",
            seed: int = 0, offset: float = 0.0) -> dict:
    """Write `out` (exact frames, 1920x1080, 30 fps, no audio). Returns what it did."""
    g = graph(rec, dur, treatment, probe_duration(rec_path), seed, offset)
    vf, n, speed = g["vf"], g["frames"], g["speed"]
    a, b = g["span"]
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", rec_path, "-filter_complex", vf, "-map", "[v]",
           "-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
           "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    subprocess.run(cmd, check=True)
    got = count_frames(out)
    if got != n:
        raise RuntimeError(f"{out.name}: {got} frames written, {n} wanted")
    return {"treatment": treatment, "composite": treatment in COMPOSITES, "frames": n,
            "span": [round(a, 3), round(b, 3)], "speed": speed}


class Stream:
    """Frames of a prepared segment, read in order, one at a time."""

    def __init__(self, path: Path):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.n = 0
        self.last = None

    def next(self):
        import numpy as np                                    # noqa: PLC0415
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            self.n += 1
        return self.last

    def close(self):
        try:
            self.p.stdout.close()
            self.p.kill()
            self.p.wait()
        except Exception:                                     # noqa: BLE001
            pass


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "demo":
        out = Path(argv[2])
        out.mkdir(parents=True, exist_ok=True)
        for t in TREATMENTS:
            print(t, json.dumps(prepare(argv[1], {}, 6.0, out / f"{t}.mp4", t)))
        return 0
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
