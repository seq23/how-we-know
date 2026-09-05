"""plan.json (+ per-beat narration audio) -> finished MP4.

Timing authority is the AUDIO, never the plan's word-count estimate. Each beat's
visual is rendered to the exact measured duration of its narration clip, so
picture and voice can never drift apart over an 8-minute video.
"""
import json, os, subprocess, shutil, sys, math
from design import W, H, FPS
import segments as S
try:
    import segments_ext as SX
except ImportError:
    SX = None
try:
    import segments_ext2 as SX2
    import segments_species  # grafts species_image onto `segments`
except ImportError:
    SX2 = None
try:
    import segments_materials as SM   # materials-and-manufacturing's own
                                       # structural-device renderers; a no-op
                                       # import for any other domain's plan,
                                       # since those plans never name one of
                                       # its segment types
except ImportError:
    SM = None

def seg_fn(name):
    if hasattr(S, name):  return getattr(S, name)
    if SX and hasattr(SX, name): return getattr(SX, name)
    if SX2 and hasattr(SX2, name): return getattr(SX2, name)
    if SM and hasattr(SM, name): return getattr(SM, name)
    raise KeyError(f"unknown segment type: {name}")

def probe(path):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nw=1:nk=1",path], capture_output=True, text=True)
    return float(out.stdout.strip())

def render_beat(beat, idx, workdir, seconds, burner=None, t0=0.0, frames=None):
    """Render one beat to a silent clip of exactly `frames` frames.

    `frames` is passed by the caller, which allocates them across the whole
    episode so per-beat rounding cannot accumulate (see `assemble`). Falls back
    to rounding `seconds` when called directly.

    `burner` (visuals/captions.Burner) draws the caption live at global time
    t0 + i/FPS, so the words on screen come from the same measured audio the
    beat is cut to. It caches one pre-rendered panel per cue, so the per-frame
    cost is a bounding-box paste rather than a full-frame composite.
    """
    fn = seg_fn(beat["segment"])
    n = max(1, int(frames if frames is not None else round(seconds * FPS)))
    fdir = os.path.join(workdir, f"f{idx:04d}")
    os.makedirs(fdir, exist_ok=True)
    args = beat.get("args") or {}
    for i in range(n):
        try:
            img = fn(i / max(n - 1, 1), **args)
        except TypeError:                       # arg mismatch -> never crash a batch
            img = seg_fn("ambient_drift")(i / max(n - 1, 1), variant=idx % 5)
        if burner is not None:
            burner.draw(img, t0 + i / FPS)
        img.save(f"{fdir}/{i:05d}.png")
    clip = os.path.join(workdir, f"c{idx:04d}.mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(FPS),
                    "-i",f"{fdir}/%05d.png","-c:v","libx264","-pix_fmt","yuv420p",
                    "-crf","20",clip], check=True)
    shutil.rmtree(fdir)
    return clip

def mix_bed(narration, out, duck_db=-32.0, seed=7):
    """Lay the generated ambient bed under narration. The bed is low-frequency
    only, so it fills silence without masking speech. Sidechain-free: at -32 dB
    it never competes, and ducking would pump audibly under a calm read."""
    import subprocess as sp
    dur = probe(narration)
    bed_wav = out + ".bed.wav"
    here = os.path.dirname(os.path.abspath(__file__))
    sp.run([sys.executable, os.path.join(here, "music.py"), str(dur + 2), bed_wav,
            "--seed", str(seed)], check=True)
    sp.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i", narration, "-i", bed_wav,
            "-filter_complex",
            f"[1:a]volume={duck_db}dB,aformat=sample_fmts=fltp:sample_rates=48000[b];"
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000[v];"
            f"[v][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
            "-map","[a]","-c:a","pcm_s16le", out], check=True)
    os.remove(bed_wav)
    return out


def assemble(plan_path, out_path, audio_dir=None, master_audio=None, workdir=None,
             music=True, burn_captions=False):
    plan = json.load(open(plan_path))
    workdir = workdir or out_path + ".work"
    os.makedirs(workdir, exist_ok=True)

    # --- decide each beat's duration -----------------------------------------
    durations, audio_clips = [], []
    for i, b in enumerate(plan):
        wav = os.path.join(audio_dir, f"{i:04d}.wav") if audio_dir else None
        if wav and os.path.exists(wav):
            d = probe(wav); audio_clips.append(wav)     # AUDIO IS THE AUTHORITY
        else:
            d = float(b["seconds"])                     # estimate only if no audio
        durations.append(max(0.4, d))

    # CAPTIONS ARE BURNED FROM THE SAME MEASURED DURATIONS the beats are cut
    # to, never from the plan's word-count estimate, so the words cannot drift
    # away from the voice over an eight-minute video.
    burner = None
    if burn_captions:
        import captions as CAP                            # noqa: PLC0415
        burner = CAP.Burner(CAP.build_cues(plan, durations))
        print(f"  burning {len(burner.cues)} caption cues", flush=True)

    # FRAMES ARE ALLOCATED ACROSS THE WHOLE EPISODE, NOT PER BEAT. Rounding
    # each beat independently to a whole frame drops up to half a frame per
    # beat, and over sixty-odd beats that summed to a video 50-90 ms SHORTER
    # than its narration -- so the final `-shortest` mux clipped the tail of
    # the last spoken beat. V13 caught it on four materials renders.
    #
    # Each beat's count is the difference between the frames due by the END of
    # that beat and the frames already emitted, so an error is corrected by the
    # next beat instead of accumulating. The LAST beat rounds UP, which is what
    # guarantees the video is never shorter than the audio: `-shortest` then
    # trims at most one frame of picture rather than any narration.
    total_s = sum(durations)
    frames, emitted = [], 0
    for i, d in enumerate(durations):
        due = sum(durations[:i + 1])
        want = (math.ceil(due * FPS) if i == len(durations) - 1
                else int(round(due * FPS)))
        frames.append(max(1, want - emitted))
        emitted += frames[-1]
    assert emitted / FPS >= total_s - 1e-9, (
        f"allocated {emitted} frame(s) = {emitted / FPS:.3f}s for {total_s:.3f}s "
        f"of narration; the mux would clip the last beat")

    clips, t0 = [], 0.0
    for i, b in enumerate(plan):
        clips.append(render_beat(b, i, workdir, durations[i], burner, t0,
                                 frames=frames[i]))
        # Captions are drawn at the frame times actually emitted, so the words
        # cannot drift from the picture the drift correction just adjusted.
        t0 += frames[i] / FPS
        if (i+1) % 10 == 0 or i == len(plan)-1:
            print(f"  rendered {i+1}/{len(plan)}", flush=True)

    # --- concat video ---------------------------------------------------------
    lst = os.path.join(workdir, "clips.txt")
    with open(lst,"w") as f:
        for c in clips: f.write(f"file '{os.path.abspath(c)}'\n")
    silent = os.path.join(workdir, "silent.mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat",
                    "-safe","0","-i",lst,"-c","copy",silent], check=True)

    # --- mux audio ------------------------------------------------------------
    if master_audio and os.path.exists(master_audio):
        track = master_audio
    elif audio_clips and len(audio_clips) == len(plan):
        alst = os.path.join(workdir,"audio.txt")
        with open(alst,"w") as f:
            for a in audio_clips: f.write(f"file '{os.path.abspath(a)}'\n")
        track = os.path.join(workdir,"narration.wav")
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat",
                        "-safe","0","-i",alst,"-c","copy",track], check=True)
    else:
        track = None

    if track and music:
        try:
            track = mix_bed(track, os.path.join(workdir, "mixed.wav"))
        except Exception as e:
            print(f"  music bed skipped: {e}")      # narration alone is still valid

    if track:
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",silent,
                        "-i",track,"-c:v","copy","-c:a","aac","-b:a","192k",
                        "-shortest",out_path], check=True)
    else:
        shutil.copy(silent, out_path)

    total = probe(out_path)
    shutil.rmtree(workdir, ignore_errors=True)
    return {"output": out_path, "beats": len(plan), "duration_s": round(total,1),
            "audio": bool(track), "timing": "audio" if audio_clips else "estimate"}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("plan"); ap.add_argument("out")
    ap.add_argument("--audio-dir"); ap.add_argument("--master-audio")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--burn-captions", action="store_true",
                    help="draw the measured caption track into the frames")
    a = ap.parse_args()
    r = assemble(a.plan, a.out, a.audio_dir, a.master_audio,
                 music=not a.no_music, burn_captions=a.burn_captions)
    print(json.dumps(r, indent=2))
