"""plan.json (+ per-beat narration audio) -> finished MP4.

Timing authority is the AUDIO, never the plan's word-count estimate. Each beat's
visual is rendered to the exact measured duration of its narration clip, so
picture and voice can never drift apart over an 8-minute video.
"""
import json
import math, os, subprocess, shutil, sys
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
# The ACTIVE domain's structural-device renderers (design.DOMAIN, set from
# HWK_DOMAIN). Without this a materials plan referencing thermal_ascent raised
# "unknown segment type" at render, after narration had already been paid for.
SM = None
try:
    import design as _design
    if _design.DOMAIN == "materials-and-manufacturing":
        import segments_materials as SM
except Exception:
    SM = None

def seg_fn(name):
    if SM and hasattr(SM, name): return getattr(SM, name)
    if hasattr(S, name):  return getattr(S, name)
    if SX and hasattr(SX, name): return getattr(SX, name)
    if SX2 and hasattr(SX2, name): return getattr(SX2, name)
    raise KeyError(f"unknown segment type: {name}")

def probe(path):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nw=1:nk=1",path], capture_output=True, text=True)
    return float(out.stdout.strip())

def render_beat(beat, idx, workdir, seconds, burner=None, t0=0.0):
    """Render one beat to a silent clip of exactly `seconds`.

    `burner` (visuals/captions.Burner) draws the caption live at global time
    t0 + i/FPS. It caches one pre-rendered panel per cue, so the cost is a
    bounding-box paste (~1.4 ms/frame) rather than a full-frame composite."""
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
             music=True, burn_captions=False, footage=True, slug=None):
    plan = json.load(open(plan_path))
    slug = slug or os.path.splitext(os.path.basename(plan_path))[0]
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

    # --- never let the picture end before the narration does -----------------
    # Each beat renders as round(seconds*FPS) FRAMES, so a beat whose duration
    # rounds DOWN makes the video fractionally shorter than its own audio. The
    # mux below uses -shortest, so that deficit truncates the narration: on
    # 2026-08-31 episode 10 lost 0.098s and episode 18 lost 0.122s off the end -
    # not silence, but the final word, measured at -14.4 dB and -20.6 dB against
    # a -45 dB floor.
    #
    # Frames only ever round down by a fraction each, so the fix is to give the
    # LAST beat the accumulated shortfall. -shortest is kept: it is still the
    # right guard against the opposite error, a video that runs on past the
    # narration.
    pad_frames = 0
    if audio_clips and len(audio_clips) == len(plan):
        need = math.ceil(sum(durations) * FPS)
        have = sum(max(1, int(round(d * FPS))) for d in durations)
        pad_frames = max(0, need - have)
        if pad_frames:
            durations[-1] += pad_frames / FPS
            print(f"  padded the last beat by {pad_frames} frame(s) "
                  f"({pad_frames / FPS:.3f}s) so -shortest cannot clip the "
                  f"final word", flush=True)

    # --- real footage ---------------------------------------------------------
    # A beat backed by a rights-verified NOAA clip cuts ONLY inside one of that
    # clip's measured clean windows, with the recorded crop applied when the
    # clip carries the permanent OCEAN EXPLORATION corner bug. A clip whose
    # bytes do not match the manifest sha256 raises rather than rendering.
    # Every other beat renders exactly as it always has.
    cuts, fsum = [None] * len(plan), None
    FT = None
    if footage:
        import footage as FT
        cuts = FT.assign(plan, durations, slug)      # RightsRefusal propagates
        fsum = FT.summarise(cuts)
        print(f"  footage: {fsum['footage_beats']} beat(s), "
              f"{fsum['footage_seconds']}s, {fsum['cropped']} cropped, "
              f"clips {fsum['clips']}", flush=True)

    # --- optional burned-in captions ----------------------------------------
    # Off by default. Timed from the SAME measured durations decided above, so
    # the burn, the .vtt and the chapter stamps cannot disagree.
    burner = None
    if burn_captions:
        import captions as CAP
        if len(audio_clips) != len(plan):
            raise SystemExit("refusing to burn captions: this episode is not "
                             "fully narrated, so cue timing would be guessed.")
        burner = CAP.Burner(CAP.build_cues(plan, durations))
        print(f"  burning {len(burner.cues)} caption cues", flush=True)

    clips, t0 = [], 0.0
    for i, b in enumerate(plan):
        if cuts[i] is not None:
            clips.append(FT.render_cut(
                cuts[i], os.path.join(workdir, f"c{i:04d}.mp4"),
                durations[i], workdir, burner=burner, t0=t0))
        else:
            clips.append(render_beat(b, i, workdir, durations[i], burner, t0))
        t0 += durations[i]
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
    result = {"output": out_path, "beats": len(plan), "duration_s": round(total,1),
              "audio": bool(track), "timing": "audio" if audio_clips else "estimate",
              "captions_burned": bool(burner), "footage": fsum,
              "audio_s": round(sum(durations), 2) if audio_clips else None,
              "tail_pad_frames": pad_frames}
    # A receipt beside the file. Downstream consumers must be able to learn what
    # is baked into the picture WITHOUT re-deriving it: visuals/shorts.py burns
    # its own captions, and a Short cut from an already-burned episode would show
    # two caption layers. That has to be knowable, not guessed.
    with open(out_path + ".render.json", "w") as fh:
        json.dump(result, fh, indent=2)
    return result

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("plan"); ap.add_argument("out")
    ap.add_argument("--audio-dir"); ap.add_argument("--master-audio")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--burn-captions", action="store_true",
                    help="draw the narration on screen (most of this category is "
                         "watched muted). Measured cost ~+2%% render time.")
    ap.add_argument("--no-footage", action="store_true",
                    help="render every beat as drawn, ignoring the NOAA clip set")
    ap.add_argument("--slug", help="episode slug for footage lookup "
                                   "(default: the plan filename)")
    a = ap.parse_args()
    r = assemble(a.plan, a.out, a.audio_dir, a.master_audio, music=not a.no_music,
                 burn_captions=a.burn_captions, footage=not a.no_footage,
                 slug=a.slug)
    print(json.dumps(r, indent=2))
