#!/usr/bin/env python
"""Per-beat narration for the food videos: ONE voice, start to finish.

    <tts python> voice/food_voice.py PLAN.json OUT_DIR --reference REF.wav
    python voice/food_voice.py - OUT_DIR --measure        # the ruler, no model

Owner verdict on food sample round 1 (2026-10-13): "one voice, normal
explainer pace, start to finish" - the calm register and its title-card switch
are gone; the imagery carries the hypnotic quality, not the narration.

PLAN.json is a list of beats `{"text": ...}` (any `register` other than
"standard" is refused). Each beat becomes OUT_DIR/NNNN.wav plus one
OUT_DIR/beats.json recording, per beat, its duration and the start/end of every
spoken chunk inside it (the caption track is cut from those). Same engine,
reference voice and per-chunk level matching as voice/synth.py and
voice/narrate_all.py (Chatterbox, MIT weights, local, $0).

measure() is the contract's ruler and needs no model: per beat, speech wpm
(words / spoken seconds), median pitch (autocorrelation, numpy only) and
pauses; and pace (words / total seconds) per third of the video. check() FAILS
a render whose pitch or pace changes mid-video (voice/registers.json
`contract`). loop/tests/test_food_voice_sound.py and V54 read its output.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
REGISTERS = HERE / "registers.json"
SR = 24000


def registers() -> dict:
    return json.loads(REGISTERS.read_text())


def pitch_factor(semitones: float) -> float:
    return float(2.0 ** (semitones / 12.0))


def shift_down(x: np.ndarray, semitones: float) -> np.ndarray:
    """Lower pitch by resampling: play SR samples as if at SR*f. Longer, lower.
    numpy only (the ruler and its self-check run in CI, which has no scipy)."""
    if not semitones:
        return x
    f = pitch_factor(semitones)
    n = int(round(len(x) / f))
    return np.interp(np.arange(n) * f, np.arange(len(x)), x).astype(np.float32)


def _chunks(text: str, max_words: int = 40) -> list[str]:
    sys.path.insert(0, str(HERE))
    from synth import chunk_paragraph                       # noqa: PLC0415
    return chunk_paragraph(text, max_words)


def synthesise(plan: list[dict], out: Path, reference: str,
               device: str = "cpu") -> dict:
    sys.path.insert(0, str(HERE))
    from synth import LEXICON, apply_lexicon, match_rms, trim_silence  # noqa: PLC0415
    import torch                                             # noqa: PLC0415
    from chatterbox.tts import ChatterboxTTS                 # noqa: PLC0415
    torch.set_num_threads(min(4, os.cpu_count() or 4))
    regs = registers()["registers"]
    model = ChatterboxTTS.from_pretrained(device=device)
    out.mkdir(parents=True, exist_ok=True)
    import soundfile as sf                                   # noqa: PLC0415
    manifest = {"reference": os.path.basename(reference), "sr": SR, "beats": []}
    conditioned = None
    t0 = time.time()
    for i, beat in enumerate(plan):
        if beat.get("register", "standard") != "standard":
            raise ValueError(f"beat {i} asks for register {beat['register']!r}: food videos "
                             f"are one voice start to finish")
        reg = regs["standard"]
        wav_path = out / f"{i:04d}.wav"
        meta_path = out / f"{i:04d}.json"
        if wav_path.exists() and meta_path.exists():
            manifest["beats"].append(json.loads(meta_path.read_text()))
            continue
        if conditioned != reg["exaggeration"]:
            model.prepare_conditionals(reference, exaggeration=reg["exaggeration"])
            conditioned = reg["exaggeration"]
        f = pitch_factor(reg["pitch_semitones"])
        pieces, spans, cursor = [], [], 0.0
        chunks = _chunks(beat["text"], int(reg.get("max_words", 40)))
        for ci, chunk in enumerate(chunks):
            torch.manual_seed(1234 + i * 31 + ci)
            w = model.generate(apply_lexicon(chunk, LEXICON), audio_prompt_path=None,
                               exaggeration=reg["exaggeration"],
                               cfg_weight=reg["cfg_weight"],
                               temperature=reg["temperature"])
            a = w.squeeze(0).detach().cpu().numpy().astype(np.float32)
            pk = float(np.abs(a).max()) or 1.0
            if pk > 1.0:
                a = a / pk
            a = match_rms(trim_silence(a), -23.0)
            a = shift_down(a, reg["pitch_semitones"])
            dur = len(a) / SR
            spans.append({"text": chunk, "start": round(cursor, 3),
                          "end": round(cursor + dur, 3)})
            pieces.append(a)
            cursor += dur
            gap = reg["pause_sentence_s"] if ci < len(chunks) - 1 else reg["pause_paragraph_s"]
            pieces.append(np.zeros(int(gap * SR), np.float32))
            cursor += gap
        audio = np.concatenate(pieces)
        peak = float(np.abs(audio).max())
        if peak > 0.97:
            audio = audio * (0.97 / peak)
        sf.write(str(wav_path), audio, SR, subtype="PCM_16")
        meta = {"index": i, "file": wav_path.name, "register": "standard",
                "pitch_factor": round(f, 4), "text": beat["text"],
                "words": len(beat["text"].split()),
                "duration": round(len(audio) / SR, 3), "spans": spans}
        meta_path.write_text(json.dumps(meta, indent=1))
        manifest["beats"].append(meta)
        print(f"  [{i + 1}/{len(plan)}] {meta['duration']:6.2f}s "
              f"elapsed {(time.time() - t0) / 60:5.1f}m", flush=True)
    (out / "beats.json").write_text(json.dumps(manifest, indent=1))
    return manifest


# --------------------------------------------------------------- the ruler
def _median_f0(x: np.ndarray, sr: int = SR) -> float | None:
    """Median pitch of the loud frames, by autocorrelation. numpy only."""
    n, hop = 2048, 1024
    lo, hi = int(sr / 400), int(sr / 60)
    frames = [x[i:i + n] for i in range(0, len(x) - n, hop)]
    if not frames:
        return None
    rms = np.array([np.sqrt(np.mean(f ** 2)) for f in frames])
    gate = 0.5 * float(np.median(rms[rms > 0]) if (rms > 0).any() else 0)
    out = []
    for f, r in zip(frames, rms):
        if r <= gate or r < 1e-4:
            continue
        f = f - f.mean()
        ac = np.fft.irfft(np.abs(np.fft.rfft(f, 2 * n)) ** 2)[:n]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.3:
            out.append(sr / lag)
    return float(np.median(out)) if out else None


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    import wave                                              # noqa: PLC0415
    with wave.open(str(path)) as w:
        sr, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768.0
    return x, sr


def _pauses(x: np.ndarray, sr: int = SR, floor_db: float = -40.0,
            min_s: float = 0.25) -> list[float]:
    hop = int(0.01 * sr)
    frames = len(x) // hop
    env = np.array([np.sqrt(np.mean(x[k * hop:(k + 1) * hop] ** 2) + 1e-12)
                    for k in range(frames)])
    db = 20 * np.log10(env + 1e-12)
    quiet = db < floor_db
    out, run = [], 0
    for q in quiet:
        if q:
            run += 1
        else:
            if run * 0.01 >= min_s:
                out.append(run * 0.01)
            run = 0
    return out


def measure(beat_dir: Path) -> dict:
    """Per beat and per third of the video: speech wpm, pace, median F0, pauses."""
    man = json.loads((beat_dir / "beats.json").read_text())
    beats, t0 = [], 0.0
    for b in man["beats"]:
        x, sr = _read_wav(beat_dir / b["file"])
        spoken = sum(s["end"] - s["start"] for s in b["spans"])
        total = len(x) / sr
        f0 = _median_f0(x, sr)
        beats.append({"index": b["index"], "register": b.get("register", "standard"),
                      "pitch_factor": b.get("pitch_factor", 1.0), "words": b["words"],
                      "start_s": round(t0, 2), "total_s": round(total, 3),
                      "spoken_s": round(spoken, 3),
                      "wpm": round(b["words"] / (spoken / 60.0), 1) if spoken else None,
                      "median_f0_hz": round(f0, 1) if f0 else None,
                      "pauses": [round(p, 2) for p in _pauses(x, sr)]})
        t0 += total
    thirds = []
    for k in range(3):
        lo, hi = t0 * k / 3, t0 * (k + 1) / 3
        w = s_ = 0.0
        for b in beats:                       # words and seconds by overlap with the third
            a0, a1 = b["start_s"], b["start_s"] + b["total_s"]
            ov = max(0.0, min(a1, hi) - max(a0, lo))
            if ov > 0:
                w += b["words"] * ov / b["total_s"]
                s_ += ov
        thirds.append(round(w / (s_ / 60.0), 1) if s_ else None)
    f0s = [b["median_f0_hz"] for b in beats if b["median_f0_hz"]]
    return {"register": sorted({b["register"] for b in beats}), "beats": beats,
            "total_s": round(t0, 2), "pace_wpm_by_third": thirds,
            "median_f0_hz": round(float(np.median(f0s)), 1) if f0s else None,
            "words": sum(b["words"] for b in beats)}


def check(meas: dict, contract: dict | None = None) -> list[str]:
    """ONE voice start to finish, measured. [] = it holds; a mid-video change of
    pitch or pace is a failure."""
    c = contract or registers()["contract"]
    beats = meas.get("beats") or []
    if not beats:
        return ["no beats measured - a voice check that hears nothing proves nothing"]
    p = []
    regs = set(meas.get("register") or []) | {b.get("register", "standard") for b in beats}
    if regs != {c["only_register"]}:
        p.append(f"registers {sorted(regs)} - food videos are one voice ({c['only_register']})")
    if any(abs(float(b.get("pitch_factor") or 1.0) - 1.0) > 1e-3 for b in beats):
        p.append("a beat was pitch-shifted at synthesis - one voice means no shift anywhere")
    big = [b for b in beats if b["words"] >= c["min_words_per_measured_beat"]]
    if len(big) < 2:
        p.append(f"only {len(big)} beat(s) long enough to measure; need >= 2")
        return p
    f0 = [b["median_f0_hz"] for b in big if b["median_f0_hz"]]
    if len(f0) < 2:
        p.append("pitch could not be measured")
    else:
        med = float(np.median(f0))
        for b in big:
            if b["median_f0_hz"]:
                d = 12 * np.log2(b["median_f0_hz"] / med)
                if abs(d) > c["pitch_spread_semitones_at_most"]:
                    p.append(f"beat {b['index']} sits {d:+.2f} semitones from the video's median "
                             f"pitch (limit {c['pitch_spread_semitones_at_most']}): the pitch changes mid-video")
    wpm = [b["wpm"] for b in big if b["wpm"]]
    med_w = float(np.median(wpm))
    for b in big:
        if b["wpm"] and abs(b["wpm"] / med_w - 1) > c["speech_wpm_spread_share_at_most"]:
            p.append(f"beat {b['index']} speaks at {b['wpm']} wpm vs median {med_w:.0f} "
                     f"(limit {c['speech_wpm_spread_share_at_most']:.0%}): the pace changes mid-video")
    th = [x for x in meas.get("pace_wpm_by_third") or [] if x]
    if len(th) == 3:
        m = float(np.median(th))
        for k, x in enumerate(th):
            if abs(x / m - 1) > c["pace_spread_share_at_most"]:
                p.append(f"third {k + 1} paces at {x} wpm vs {m:.0f} (limit "
                         f"{c['pace_spread_share_at_most']:.0%}): the pace changes mid-video")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("out")
    ap.add_argument("--reference", required=False)
    ap.add_argument("--measure", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    if a.measure:
        m = measure(out)
        print(json.dumps({"measured": m, "problems": check(m)}, indent=1))
        return 0
    plan = json.loads(Path(a.plan).read_text())
    synthesise(plan, out, a.reference)
    m = measure(out)
    (out / "measurements.json").write_text(json.dumps(m, indent=1))
    print(json.dumps({"measured": m, "problems": check(m)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
