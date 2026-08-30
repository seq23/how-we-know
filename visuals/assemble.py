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

def seg_fn(name):
    if hasattr(S, name):  return getattr(S, name)
    if SX and hasattr(SX, name): return getattr(SX, name)
    raise KeyError(f"unknown segment type: {name}")

def probe(path):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nw=1:nk=1",path], capture_output=True, text=True)
    return float(out.stdout.strip())

def render_beat(beat, idx, workdir, seconds):
    """Render one beat to a silent clip of exactly `seconds`."""
    fn = seg_fn(beat["segment"])
    n = max(1, int(round(seconds * FPS)))
    fdir = os.path.join(workdir, f"f{idx:04d}")
    os.makedirs(fdir, exist_ok=True)
    args = beat.get("args") or {}
    for i in range(n):
        try:
            img = fn(i / max(n - 1, 1), **args)
        except TypeError:                       # arg mismatch -> never crash a batch
            img = seg_fn("ambient_drift")(i / max(n - 1, 1), variant=idx % 5)
        img.save(f"{fdir}/{i:05d}.png")
    clip = os.path.join(workdir, f"c{idx:04d}.mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(FPS),
                    "-i",f"{fdir}/%05d.png","-c:v","libx264","-pix_fmt","yuv420p",
                    "-crf","20",clip], check=True)
    shutil.rmtree(fdir)
    return clip

def assemble(plan_path, out_path, audio_dir=None, master_audio=None, workdir=None):
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

    clips = []
    for i, b in enumerate(plan):
        clips.append(render_beat(b, i, workdir, durations[i]))
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
    a = ap.parse_args()
    r = assemble(a.plan, a.out, a.audio_dir, a.master_audio)
    print(json.dumps(r, indent=2))
