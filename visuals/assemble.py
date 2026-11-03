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
    import disk_guard                                     # noqa: PLC0415
    disk_guard.preflight(workdir)        # LOW_DISK: stop before writing frames
    fn = seg_fn(beat["segment"])
    n = max(1, int(frames if frames is not None else round(seconds * FPS)))
    fdir = os.path.join(workdir, f"f{idx:04d}")
    os.makedirs(fdir, exist_ok=True)
    clip = os.path.join(workdir, f"c{idx:04d}.mp4")
    try:
        args = beat.get("args") or {}
        for i in range(n):
            try:
                img = fn(i / max(n - 1, 1), **args)
            except TypeError:                   # arg mismatch -> never crash a batch
                img = seg_fn("ambient_drift")(i / max(n - 1, 1), variant=idx % 5)
            if burner is not None:
                burner.draw(img, t0 + i / FPS)
            img.save(f"{fdir}/{i:05d}.png")
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate",str(FPS),
                        "-i",f"{fdir}/%05d.png","-c:v","libx264","-pix_fmt","yuv420p",
                        "-crf","20",clip], check=True)
        got = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-count_packets",
                              "-show_entries","stream=nb_read_packets","-of",
                              "default=nw=1:nk=1",clip], capture_output=True, text=True).stdout.strip()
        if got != str(n):
            raise RuntimeError(f"beat {idx}: encoded {got} frame(s), {n} drawn")
    finally:
        # The PNG folder goes the moment its clip is encoded and checked, or
        # the moment it fails - never left to fill the disk.
        shutil.rmtree(fdir, ignore_errors=True)
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
             music=True, burn_captions=False, slug=None):
    plan = json.load(open(plan_path))
    # A DOMAIN'S GRAPHICS NEVER APPEAR IN ANOTHER DOMAIN'S VIDEO (2026-11-01:
    # the deep-sea depth gauge on the rice episode). The active domain is
    # HWK_DOMAIN, which bin/batch-session.sh sets from the script's own line.
    import plan_domain as _pd
    _bad = _pd.foreign(plan, os.environ.get("HWK_DOMAIN", _pd.DEEP))
    if _bad:
        raise ValueError(
            f"PLAN_DOMAIN_FOREIGN {plan_path}: {len(_bad)} beat(s) draw another "
            f"domain's graphics ({_bad[0][2]}, beat {_bad[0][0]}); "
            f"visuals/plan_domain.py sweep re-plans it")
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

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loop"))
    import picture_time
    spoken = list(durations)
    durations, holds = picture_time.apply(plan, spoken)
    plan = [{**b, "imagery_only_s": h} for b, h in zip(plan, holds)]
    # Pad EACH wav, so the next sentence starts after its picture interval.
    if audio_clips and any(holds):
        padded = []
        for i, (wav, hold) in enumerate(zip(audio_clips, holds)):
            dest = os.path.join(workdir, f"voice-{i:04d}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav,
                            "-af", f"apad=pad_dur={hold}", dest], check=True)
            padded.append(dest)
        audio_clips = padded

    if burn_captions:
        # Owner 2026-11-03: nothing on a long-form picture but the subject.
        # Captions go to YouTube as a soft track (loop/captions_lane.py).
        raise ValueError("burned-in captions are refused on a long-form "
                         "picture; the .srt goes up as a soft subtitle track")

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

    # THE PICTURE IS ONLY MOVING IMAGERY OF THE SUBJECT (owner 2026-11-03:
    # "just a video with moving imagery of large deep-sea creatures and thats
    # it nothing else"). The plan's beats time the NARRATION; they no longer
    # choose the picture. visuals/longform_picture.py builds the shots from
    # the subject's footage (then slowed reuse, then moving photographs) and
    # refuses any card, diagram, filler, plate, caption or credit overlay.
    import longform_picture as LP                         # noqa: PLC0415
    slug = slug or os.path.splitext(os.path.basename(plan_path))[0]
    shots = LP.build(emitted / FPS, LP.subject_clips(slug), LP.subject_photos(slug))
    shot_frames = LP.allocate(shots, emitted)
    used = LP.summarise(shots)
    print(f"  picture: {used['footage_shots']} footage shot(s) "
          f"({used['footage_seconds']}s, {used['slowed_shots']} slowed), "
          f"{used['photo_shots']} moving photo(s) ({used['photo_seconds']}s), "
          f"{len(used['clips'])} clip(s)", flush=True)

    clips = []
    for i, (shot, n) in enumerate(zip(shots, shot_frames)):
        clips.append(LP.render_shot(shot, os.path.join(workdir, f"c{i:04d}.mp4"), n))
        if (i+1) % 10 == 0 or i == len(shots)-1:
            print(f"  rendered {i+1}/{len(shots)} shots", flush=True)

    # --- concat video ---------------------------------------------------------
    lst = os.path.join(workdir, "clips.txt")
    with open(lst,"w") as f:
        for c in clips: f.write(f"file '{os.path.abspath(c)}'\n")
    silent = os.path.join(workdir, "silent.mp4")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat",
                    "-safe","0","-i",lst,"-c","copy",silent], check=True)

    # --- mux audio ------------------------------------------------------------
    if master_audio and os.path.exists(master_audio) and not any(holds):
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
    write_picture_record(out_path, shots, shot_frames, frames, used)
    return {"output": out_path, "beats": len(plan), "duration_s": round(total,1),
            "audio": bool(track), "timing": "audio" if audio_clips else "estimate",
            "picture": "footage-only",
            "footage": {"footage_beats": len(plan), **used}}


def write_picture_record(out_path, shots, shot_frames, beat_frames, used):
    """Beside the master: what it shows and who to credit. visuals/shorts.py
    takes a Short's credits from it (no credit is burned into the master any
    more), and loop/upload.py lists the credits in the description."""
    import longform_picture as LP                         # noqa: PLC0415
    st = os.stat(out_path)
    rec = {"_why": "What this footage-only master shows, per shot, and the "
                   "credit for every beat (visuals/assemble.py). The authority "
                   "for a Short's footage credit and the description's credits.",
           "master": {"bytes": st.st_size, "mtime": int(st.st_mtime)},
           "picture": "footage-only",
           "footage_beats_expected": len(beat_frames),
           "credits": used["credits"],
           "shots": [{"kind": s["kind"], "title": s["title"], "credit": s["credit"],
                      "seconds": round(n / FPS, 3), "speed": s.get("speed", 1.0),
                      "source": s["asset"].get("source") or s["asset"].get("source_org"),
                      "licence": s["asset"].get("licence") or s["asset"].get("rights_basis", "")[:80]}
                     for s, n in zip(shots, shot_frames)],
           "beats": {str(k): v for k, v in
                     LP.beat_credits(shots, shot_frames, beat_frames).items()}}
    with open(out_path + ".footage.json", "w") as fh:
        json.dump(rec, fh, indent=2)
        fh.write("\n")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("plan"); ap.add_argument("out")
    ap.add_argument("--audio-dir"); ap.add_argument("--master-audio")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--slug", help="the episode (default: the plan's file name)")
    a = ap.parse_args()
    r = assemble(a.plan, a.out, a.audio_dir, a.master_audio,
                 music=not a.no_music, slug=a.slug)
    print(json.dumps(r, indent=2))
