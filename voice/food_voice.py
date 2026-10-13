#!/usr/bin/env python
"""Per-beat narration with a REGISTER: the food videos' calm voice.

    <tts python> voice/food_voice.py PLAN.json OUT_DIR --reference REF.wav

PLAN.json is a list of beats, `{"text": ..., "register": "standard"|"calm"}`,
as written by visuals/food.py. Each beat becomes OUT_DIR/NNNN.wav plus one
OUT_DIR/beats.json recording, per beat, its register, its duration and the
start/end of every spoken chunk inside it (the caption track is cut from
those, so captions follow the voice rather than a word-count estimate).

The registers live in voice/registers.json. Same engine, same reference
voice and same per-chunk level matching as voice/synth.py and
voice/narrate_all.py (Chatterbox, MIT weights, local, $0); only the
generation settings, the pauses and the pitch differ. The calm register is
lowered by resampling (2^(semitones/12)), which also slows the read by the
same factor - "slower, lower" in one honest step, no time-stretch artefacts.

measure() is the contract's ruler and needs no model: words per minute of
speech, median pitch (YIN, librosa) and mean pause per register, from the
files on disk. loop/tests/test_food_voice_sound.py and V54 read its output.
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
        reg = regs[beat["register"]]
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
        meta = {"index": i, "file": wav_path.name, "register": beat["register"],
                "pitch_factor": round(f, 4), "text": beat["text"],
                "words": len(beat["text"].split()),
                "duration": round(len(audio) / SR, 3), "spans": spans}
        meta_path.write_text(json.dumps(meta, indent=1))
        manifest["beats"].append(meta)
        print(f"  [{i + 1}/{len(plan)}] {beat['register']:<8} {meta['duration']:6.2f}s "
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
    """Per register: speech wpm (words / spoken seconds), median F0, mean pause."""
    man = json.loads((beat_dir / "beats.json").read_text())
    acc: dict[str, dict] = {}
    for b in man["beats"]:
        x, sr = _read_wav(beat_dir / b["file"])
        spoken = sum(s["end"] - s["start"] for s in b["spans"])
        a = acc.setdefault(b["register"], {"words": 0, "spoken_s": 0.0, "total_s": 0.0,
                                           "f0": [], "pauses": [], "beats": 0})
        a["words"] += b["words"]
        a["spoken_s"] += spoken
        a["total_s"] += len(x) / sr
        a["beats"] += 1
        f0 = _median_f0(x, sr)
        if f0:
            a["f0"].append(f0)
        a["pauses"] += _pauses(x, sr)
    out = {}
    for reg, a in acc.items():
        out[reg] = {"beats": a["beats"], "words": a["words"],
                    "wpm": round(a["words"] / (a["spoken_s"] / 60.0), 1) if a["spoken_s"] else None,
                    "pace_wpm": round(a["words"] / (a["total_s"] / 60.0), 1) if a["total_s"] else None,
                    "median_f0_hz": round(float(np.median(a["f0"])), 1) if a["f0"] else None,
                    "mean_pause_s": round(float(np.mean(a["pauses"])), 3) if a["pauses"] else None}
    return out


def check(meas: dict, contract: dict | None = None) -> list[str]:
    """The register contract on measured audio. [] = it holds."""
    c = contract or registers()["contract"]
    s, k = meas.get("standard"), meas.get("calm")
    if not s or not k:
        return [f"need both registers measured, got {sorted(meas)}"]
    p = []
    if not (s["pace_wpm"] and k["pace_wpm"]) or \
            k["pace_wpm"] > s["pace_wpm"] * c["calm_pace_at_most_share_of_standard"]:
        p.append(f"calm paces at {k['pace_wpm']} wpm vs standard {s['pace_wpm']}: not slower by "
                 f"{1 - c['calm_pace_at_most_share_of_standard']:.0%}")
    if not (s["median_f0_hz"] and k["median_f0_hz"]):
        p.append("pitch could not be measured")
    else:
        drop = 12 * np.log2(s["median_f0_hz"] / k["median_f0_hz"])
        if drop < c["calm_pitch_drop_semitones_at_least"]:
            p.append(f"calm is only {drop:.2f} semitones lower than standard "
                     f"(needs {c['calm_pitch_drop_semitones_at_least']})")
    if not (s["mean_pause_s"] and k["mean_pause_s"]) or \
            k["mean_pause_s"] < s["mean_pause_s"] * c["calm_mean_pause_at_least_share_of_standard"]:
        p.append(f"calm pauses {k['mean_pause_s']}s vs standard {s['mean_pause_s']}s: "
                 f"not {c['calm_mean_pause_at_least_share_of_standard']}x longer")
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
