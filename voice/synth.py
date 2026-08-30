#!/usr/bin/env python
"""
synth.py - local zero-shot narration synthesis for the faceless-YouTube pipeline.

Engine: Chatterbox TTS (Resemble AI), MIT licensed weights, 100% local inference.
Nothing is uploaded anywhere. Output is 24 kHz mono PCM WAV.

Why it is built this way
------------------------
* Chatterbox conditions the decoder on only the FIRST 10 s of the reference wav
  and the T3 prompt on the first 6 s (see chatterbox/tts.py DEC_COND_LEN /
  ENC_COND_LEN). Feeding a two-minute file therefore wastes it and can seed the
  clone with silence or a throat-clear. `--auto-window` picks the most densely
  voiced 10 s window instead of blindly taking the head of the file.
* `prepare_conditionals()` is expensive and re-runs on every `generate()` call
  that is handed an `audio_prompt_path`. We run it ONCE and then synthesise every
  chunk against the cached conditionals.
* A single generate() call is capped at max_new_tokens=1000 (~40 s of audio) and
  quality degrades well before that, so text is chunked on sentence boundaries.
* Each chunk is loudness-matched to a target RMS to stop level drift accumulating
  across an 8-minute read, then paragraphs are joined with natural pauses.

Usage
-----
  synth.py SCRIPT.md OUT.wav --reference voice/reference_A_clean.wav
  synth.py SCRIPT.md OUT.wav --reference REF.wav --auto-window --seed 1234
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

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from script_text import read_script  # noqa: E402

SR = 24000  # Chatterbox S3GEN_SR; also the pipeline's target rate

# ---------------------------------------------------------------------------
# Pronunciation lexicon.
#
# Chatterbox has NO phoneme input - the tokenizer is text-level - so the only
# override mechanism is respelling. These are applied to the synthesis text
# only; the source script is never modified. Keys are matched case-insensitively
# on word boundaries. Add niche terms here as they come up.
# ---------------------------------------------------------------------------
LEXICON: dict[str, str] = {
    # Acronyms that must be spelled out rather than read as words.
    "NOAA": "Noh-ah",
    "MBARI": "em-BAR-ee",
    "ROV": "R O V",
    "ROVs": "R O Vs",
    "CTD": "C T D",
    "GPS": "G P S",
    # Terms the base model tends to mangle.
    "hadal": "hay-dal",
    "Kaiko": "Kye-koh",
    "Kaikō": "Kye-koh",
    "bathypelagic": "bath-ee-pel-AJ-ic",
    "abyssopelagic": "ab-iss-oh-pel-AJ-ic",
    "mesopelagic": "mez-oh-pel-AJ-ic",
    "bioluminescence": "bye-oh-loo-min-ESS-ence",
    "bioluminescent": "bye-oh-loo-min-ESS-ent",
    "cephalopod": "SEF-uh-lo-pod",
    "cephalopods": "SEF-uh-lo-pods",
    "bathymetric": "bath-ee-MET-ric",
    "bathymetry": "buh-THIM-uh-tree",
    "Trieste": "Tree-EST-ay",
    "siphonophore": "sy-FON-oh-for",
    "siphonophores": "sy-FON-oh-fors",
    "Mariana": "Mah-ree-AH-nuh",
}


def apply_lexicon(text: str, lex: dict[str, str]) -> str:
    if not lex:
        return text
    for term in sorted(lex, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(term)}\b", lex[term], text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bSt)(?<!\bvs)(?<!\bapprox)(?<!\be\.g)(?<!\bi\.e)"


def split_sentences(par: str) -> list[str]:
    parts = re.split(rf"{_ABBREV}(?<=[.!?])[\"')\]]*\s+", par.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_paragraph(par: str, max_words: int) -> list[str]:
    """Group whole sentences into chunks of at most `max_words` words."""
    chunks: list[str] = []
    cur: list[str] = []
    n = 0
    for sent in split_sentences(par):
        w = len(sent.split())
        if w > max_words:  # a single very long sentence: split on clause commas
            if cur:
                chunks.append(" ".join(cur))
                cur, n = [], 0
            clauses = re.split(r"(?<=,)\s+", sent)
            buf: list[str] = []
            bn = 0
            for c in clauses:
                cw = len(c.split())
                if bn + cw > max_words and buf:
                    chunks.append(" ".join(buf))
                    buf, bn = [], 0
                buf.append(c)
                bn += cw
            if buf:
                chunks.append(" ".join(buf))
            continue
        if n + w > max_words and cur:
            chunks.append(" ".join(cur))
            cur, n = [], 0
        cur.append(sent)
        n += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def rms_dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return 20.0 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)


def match_rms(x: np.ndarray, target_db: float, max_gain_db: float = 9.0) -> np.ndarray:
    """Nudge a chunk toward the target level. Clamped so a near-silent or
    blown-up chunk cannot be violently rescaled."""
    cur = rms_dbfs(x)
    if cur < -70.0:
        return x
    g = float(np.clip(target_db - cur, -max_gain_db, max_gain_db))
    return x * (10.0 ** (g / 20.0))


def trim_silence(x: np.ndarray, thresh_db: float = -45.0, keep_ms: int = 40) -> np.ndarray:
    """Trim leading/trailing near-silence, keeping a short natural cushion."""
    if x.size == 0:
        return x
    win = 256
    n = (len(x) // win) * win
    if n == 0:
        return x
    frames = x[:n].reshape(-1, win)
    e = 20.0 * np.log10(np.sqrt((frames.astype(np.float64) ** 2).mean(1)) + 1e-12)
    loud = np.where(e > thresh_db)[0]
    if loud.size == 0:
        return x
    keep = int(keep_ms * SR / 1000)
    a = max(0, loud[0] * win - keep)
    b = min(len(x), (loud[-1] + 1) * win + keep)
    return x[a:b]


def high_shelf(x: np.ndarray, gain_db: float, f0: float = 6000.0, sr: int = SR) -> np.ndarray:
    """Gentle high-shelf to restore presence.

    Measured on this voice: the reference has 8-12 kHz energy at -7.0 dB, but the
    S3Gen 24 kHz vocoder returns it at -19.8 dB - a ~12.7 dB 'air' deficit that
    reads as muffled on headphones.

    This is a PARTIAL correction, not a fix. Measured: +3.5 dB shelf moves the
    8-12 kHz band from -19.8 to -16.4 dB, i.e. it recovers about 3.4 dB of a
    12.7 dB deficit while leaving 0-300 Hz and 300-3000 Hz untouched. Fully
    closing the gap would need ~+13 dB, which turns sibilance harsh and amplifies
    vocoder hiss. 3.5 dB is the conservative setting that helps without artifacts.
    RBJ cookbook biquad.
    """
    if abs(gain_db) < 0.01:
        return x
    from scipy.signal import lfilter

    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / 0.9 - 1.0) + 2.0)
    tsa = 2.0 * np.sqrt(A) * alpha
    b = [A * ((A + 1) + (A - 1) * cw + tsa),
         -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - tsa)]
    a = [(A + 1) - (A - 1) * cw + tsa,
         2 * ((A - 1) - (A + 1) * cw),
         (A + 1) - (A - 1) * cw - tsa]
    y = lfilter(np.array(b) / a[0], np.array(a) / a[0], x.astype(np.float64))
    return y.astype(np.float32)


def pick_voiced_window(path: str, seconds: float = 10.0) -> np.ndarray:
    """Return the most densely voiced `seconds`-long window of a reference wav."""
    import librosa

    y, _ = librosa.load(path, sr=SR)
    if len(y) <= seconds * SR:
        return y
    hop = 512
    e = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    edb = 20.0 * np.log10(e + 1e-12)
    voiced = edb > (np.percentile(edb, 90) - 25.0)
    w = int(seconds * SR / hop)
    best_i, best_s = 0, -1e9
    for i in range(0, len(voiced) - w):
        seg = voiced[i:i + w]
        frac = seg.mean()
        lvl = edb[i:i + w][seg].mean() if seg.any() else -99.0
        s = frac * 100.0 + lvl * 0.3
        if s > best_s:
            best_s, best_i = s, i
    start = best_i * hop
    return y[start:start + int(seconds * SR)]


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Local voice-cloned narration (Chatterbox TTS, offline)."
    )
    ap.add_argument("script", help="Input .md production script or plain .txt")
    ap.add_argument("output", help="Output .wav path (24 kHz mono)")
    ap.add_argument("--reference", required=True, help="Reference voice WAV to clone")
    ap.add_argument("--section", default="Narration", help="H2 section to read (default: Narration)")
    ap.add_argument("--auto-window", action="store_true",
                    help="Condition on the most voiced 10s of the reference instead of its first 10s")
    # 40 s ceiling / ~145 WPM = ~95 words is the hard truncation limit; 45 leaves
    # comfortable headroom for slow, emphatic delivery.
    ap.add_argument("--max-words", type=int, default=45,
                    help="Max words per synthesis chunk (hard ceiling ~95; see 40s token cap)")
    ap.add_argument("--pause-sentence", type=float, default=0.16, help="Pause between chunks (s)")
    ap.add_argument("--pause-paragraph", type=float, default=0.55, help="Pause between paragraphs (s)")
    ap.add_argument("--exaggeration", type=float, default=0.4)
    ap.add_argument("--cfg-weight", type=float, default=0.4)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=1234, help="Fixed seed keeps takes reproducible")
    ap.add_argument("--target-db", type=float, default=-23.0, help="Per-chunk RMS target (dBFS)")
    ap.add_argument("--no-level-match", action="store_true", help="Disable per-chunk level matching")
    ap.add_argument("--presence-db", type=float, default=3.5,
                    help="High-shelf gain above 6 kHz to offset the vocoder's measured "
                         "~12 dB air loss (default 3.5; use 0 to disable)")
    ap.add_argument("--no-lexicon", action="store_true", help="Disable pronunciation respellings")
    ap.add_argument("--lexicon", help="JSON file of extra {term: respelling} overrides")
    ap.add_argument("--device", default=None, help="cpu | mps (default: auto)")
    ap.add_argument("--dry-run", action="store_true", help="Show chunk plan, synthesise nothing")
    args = ap.parse_args()

    paragraphs = read_script(args.script, args.section)
    if not paragraphs:
        print(f"error: no narration text found in {args.script}", file=sys.stderr)
        return 2

    lex = {} if args.no_lexicon else dict(LEXICON)
    if args.lexicon:
        lex.update(json.loads(Path(args.lexicon).read_text(encoding="utf-8")))

    plan: list[list[str]] = [chunk_paragraph(p, args.max_words) for p in paragraphs]
    n_chunks = sum(len(c) for c in plan)
    n_words = sum(len(p.split()) for p in paragraphs)
    print(f"{args.script}\n  {len(paragraphs)} paragraphs -> {n_chunks} chunks, {n_words} words")

    if args.dry_run:
        for pi, chunks in enumerate(plan):
            for ci, c in enumerate(chunks):
                print(f"  [{pi:02d}.{ci}] ({len(c.split()):2d}w) {apply_lexicon(c, lex)[:100]}")
        return 0

    # Chatterbox 0.1.7 builds the BOS embedding with a hardcoded batch of 2 for
    # the CFG path, so cfg_weight=0 crashes inside t3.inference with a tensor
    # size mismatch. Fail fast with an explanation instead of a 20-minute crash.
    if args.cfg_weight <= 0.0:
        print("error: --cfg-weight must be > 0; cfg_weight=0 is broken upstream "
              "in chatterbox 0.1.7 (batch-2 BOS embed). Use 0.3-0.5.", file=sys.stderr)
        return 2

    import torch  # noqa: E402
    from chatterbox.tts import ChatterboxTTS  # noqa: E402

    # 4 performance cores on an M-series; oversubscribing thrashes on 8 GB.
    torch.set_num_threads(min(4, os.cpu_count() or 4))

    # Default to CPU deliberately. Measured on the 8 GB M2: CPU sustains
    # ~0.085x realtime, while the MPS path spent its time in uninterruptible
    # page-wait (state U) and did not finish a single short sentence in 15
    # minutes - unified memory is the bottleneck, not compute. Pass
    # --device mps to try it on a machine with more RAM.
    device = args.device or "cpu"
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device=device)
    print(f"  model loaded on {device} in {time.time() - t0:.1f}s")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Condition ONCE, then reuse for every chunk.
    ref_path = args.reference
    tmp_ref = None
    if args.auto_window:
        seg = pick_voiced_window(args.reference, 10.0)
        tmp_ref = str(Path(args.output).with_suffix(".refwindow.wav"))
        sf.write(tmp_ref, seg, SR, subtype="PCM_16")
        ref_path = tmp_ref
    model.prepare_conditionals(ref_path, exaggeration=args.exaggeration)
    print(f"  conditioned on {Path(ref_path).name}")

    sil_s = np.zeros(int(args.pause_sentence * SR), dtype=np.float32)
    sil_p = np.zeros(int(args.pause_paragraph * SR), dtype=np.float32)

    pieces: list[np.ndarray] = []
    levels: list[float] = []
    t_start = time.time()
    done = 0
    for pi, chunks in enumerate(plan):
        for ci, chunk in enumerate(chunks):
            text = apply_lexicon(chunk, lex)
            torch.manual_seed(args.seed + done)
            wav = model.generate(
                text,
                audio_prompt_path=None,          # use cached conditionals
                exaggeration=args.exaggeration,
                cfg_weight=args.cfg_weight,
                temperature=args.temperature,
            )
            a = wav.squeeze(0).detach().cpu().numpy().astype(np.float32)
            # Chatterbox can return samples above full scale (measured peak 1.07),
            # which would clip on PCM16 write. Pull a hot chunk down before it is
            # level-matched, so one loud chunk cannot drag the whole track quiet.
            pk = float(np.abs(a).max())
            if pk > 1.0:
                a = a / pk
            a = trim_silence(a)
            levels.append(rms_dbfs(a))
            if not args.no_level_match:
                a = match_rms(a, args.target_db)
            # Chatterbox caps a call at max_new_tokens=1000 speech tokens at
            # 25 Hz = 40.0 s of audio, and truncates mid-sentence without any
            # error. Anything landing on that ceiling has almost certainly been
            # cut off, so say so loudly rather than shipping a clipped read.
            if len(a) / SR > 39.0:
                print(f"      WARNING: chunk hit the ~40s generation ceiling and was "
                      f"probably truncated. Lower --max-words (currently "
                      f"{args.max_words}).", file=sys.stderr)
            pieces.append(a)
            if ci < len(chunks) - 1:
                pieces.append(sil_s)
            done += 1
            el = time.time() - t_start
            print(f"  [{done}/{n_chunks}] {len(a)/SR:5.2f}s  raw={levels[-1]:6.1f}dBFS  "
                  f"elapsed={el/60:4.1f}m", flush=True)
        if pi < len(plan) - 1:
            pieces.append(sil_p)

    out = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    out = high_shelf(out, args.presence_db)
    peak = float(np.abs(out).max())
    if peak > 0.97:  # only touch it if we would otherwise clip
        out = out * (0.97 / peak)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, out, SR, subtype="PCM_16")
    if tmp_ref and Path(tmp_ref).exists():
        Path(tmp_ref).unlink()

    dur = len(out) / SR
    comp = time.time() - t_start
    drift = levels[-1] - levels[0] if len(levels) > 1 else 0.0
    print(f"\n  wrote {args.output}")
    print(f"  {dur:.1f}s audio ({dur/60:.2f} min) in {comp:.1f}s compute "
          f"= {dur/comp:.3f}x realtime")
    print(f"  raw chunk level: first {levels[0]:.1f} dBFS, last {levels[-1]:.1f} dBFS, "
          f"drift {drift:+.1f} dB, spread {max(levels)-min(levels):.1f} dB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
