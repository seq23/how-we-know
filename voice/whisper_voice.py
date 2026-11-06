#!/usr/bin/env python
"""Per-beat whisper narration for a Whisper Almanac script (Chatterbox, local, $0).

    <tts python> voice/whisper_voice.py scripts/whisper/<slug>.md OUT_DIR \
        --reference ~/.boss-os/asmr-voice/reference_cond10.wav [--until-epoch T]

One beat per paragraph (an affirmation line is a paragraph). Each beat is
OUT_DIR/NNNN.wav + NNNN.json, written only when complete, so a night that
stops (--until-epoch, the batch's 07:00 or the whisper budget) resumes at the
next beat. The pauses are silence added here (config/whisper_almanac.json
`voice`): they cost no narration time on the Mac.

Called ONLY by loop/whisper_lane.py `night`, which runs inside
bin/batch-session.sh under the batch's narrator lock: one narrator at a time
on the 8 GB Mac. The reference is her own whisper sample, which stays on her
Mac (never in a repo).

Exit 0 = every beat done; 4 = stopped by --until-epoch with beats left (the
next night resumes); anything else = a failure the lane names.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "loop"))
SR = 24000


def slow(x: np.ndarray, tempo: float) -> np.ndarray:
    """Pitch-preserving slow-down (ffmpeg atempo): a sleep pace costs no
    narration time. Measured 6 Nov 2026: this register spoke at 170 words a
    minute; tempo 0.82 brings it to ~139."""
    if not tempo or abs(tempo - 1.0) < 1e-3:
        return x
    import subprocess                                        # noqa: PLC0415
    import tempfile                                          # noqa: PLC0415
    import soundfile as sf                                   # noqa: PLC0415
    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "a.wav", Path(td) / "b.wav"
        sf.write(str(a), x, SR, subtype="PCM_16")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a), "-filter:a",
                        f"atempo={tempo}", str(b)], check=True)
        y, _ = sf.read(str(b), dtype="float32")
    return y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--until-epoch", type=float, default=0)
    a = ap.parse_args()

    import whisper_lane as WL                               # noqa: PLC0415
    from synth import chunk_paragraph, match_rms, trim_silence  # noqa: PLC0415
    c = WL.cfg()
    v = c["voice"]
    p = WL.parse(a.script)
    plan = WL.beats(p)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [i for i in range(len(plan))
            if not ((out / f"{i:04d}.wav").exists() and (out / f"{i:04d}.json").exists())]
    if not todo:
        print(f"whisper voice: {p['slug']} already complete ({len(plan)} beats)")
        return 0

    import soundfile as sf                                  # noqa: PLC0415
    import torch                                            # noqa: PLC0415
    from chatterbox.tts import ChatterboxTTS                # noqa: PLC0415
    torch.set_num_threads(min(4, os.cpu_count() or 4))
    model = ChatterboxTTS.from_pretrained(device="cpu")
    model.prepare_conditionals(a.reference, exaggeration=v["exaggeration"])
    t0 = time.time()
    for i in todo:
        if a.until_epoch and time.time() >= a.until_epoch:
            print(f"whisper voice: stopped at beat {i} of {len(plan)} (window ends); resumes next night")
            return 4
        b = plan[i]
        pieces, spans, cur = [], [], 0.0
        if i == 0:
            pieces.append(np.zeros(int(v["opening_silence_s"] * SR), np.float32))
            cur += v["opening_silence_s"]
        chunks = chunk_paragraph(b["text"], int(v["max_words"]))
        for ci, ch in enumerate(chunks):
            torch.manual_seed(4321 + i * 31 + ci)
            w = model.generate(ch, exaggeration=v["exaggeration"], cfg_weight=v["cfg_weight"],
                               temperature=v["temperature"])
            x = w.squeeze(0).detach().cpu().numpy().astype(np.float32)
            pk = float(np.abs(x).max()) or 1.0
            if pk > 1.0:
                x = x / pk
            x = match_rms(trim_silence(x), -26.0)
            x = slow(x, float(v.get("tempo", 1.0)))
            d = len(x) / SR
            spans.append({"text": ch, "start": round(cur, 3), "end": round(cur + d, 3)})
            pieces.append(x)
            cur += d
            if ci < len(chunks) - 1:
                pieces.append(np.zeros(int(v["pause_sentence_s"] * SR), np.float32))
                cur += v["pause_sentence_s"]
        pieces.append(np.zeros(int(b["pause_after_s"] * SR), np.float32))
        audio = np.concatenate(pieces)
        audio = audio * min(1.0, 0.9 / max(1e-6, float(np.abs(audio).max())))
        tmp = out / f"{i:04d}.tmp.wav"
        sf.write(str(tmp), audio, SR, subtype="PCM_16")
        tmp.replace(out / f"{i:04d}.wav")
        speech = sum(s["end"] - s["start"] for s in spans)
        (out / f"{i:04d}.json").write_text(json.dumps({
            "index": i, "segment": b["segment"], "words": len(b["text"].split()),
            "duration": round(len(audio) / SR, 3), "speech_s": round(speech, 3),
            "spans": spans}, indent=1))
        print(f"  [{i + 1}/{len(plan)}] {len(audio) / SR:6.1f}s  elapsed "
              f"{(time.time() - t0) / 60:5.1f}m", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
