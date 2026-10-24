#!/usr/bin/env python
"""Prove every LEXICON respelling is spoken as the intended word.

Why this exists (2026-09-21). The owner heard "hypothermal" for "hydrothermal"
in the Short for `20-what-is-the-midnight-zone`. Whisper on that Short's own
audio heard "Hydro-thermal vents", "The Bath-E-Pell A.J. Ike zone" for
bathypelagic and "local chemo, syn, that, ik, sources" for chemosynthetic.
Chatterbox has no phoneme input; it reads the respelling as TEXT, so a
hyphenated, CAPS-stressed dictionary respelling ("bath-ee-pel-AJ-ic") is
spoken as spelled-out letters and separate words. The lexicon's STYLE was the
defect, and nothing had ever listened to the result.

What this does. For every LEXICON entry it synthesises a short carrier
sentence with the production voice and parameters, transcribes it with
whisper-1, and passes the entry only if the transcript contains the intended
word (fuzzy, space-insensitive). The passing table is written to
`pronunciation_probe.json` next to this file and is the PIN that
`test_lexicon_is_proven.py` reads on every suite run, so a respelling cannot
change without being listened to again.

Run on the Mac (narration runs there; the render venv has no torch):

    ~/GitHub/how-we-know/.venv-tts/bin/python \
        ~/GitHub/how-we-know/voice/tests/pronunciation_probe.py

2026-10-24: transcription is LOCAL now - whisper.cpp (`whisper-cli`, ggml-small.en,
fetched once by voice/pronounce.py) - so a probe costs $0 and needs no key
(AI cost posture: nothing paid). The paid whisper-1 path is gone.

    --raw-ok TERM[,TERM] speak each term with NO entry and record the ones
                         heard correctly in the pin's "raw_ok" section: the
                         committed proof that a hard word needs no respelling

    --only TERM[,TERM]   probe a subset (iterating on a respelling)
    --keep               keep the per-term wavs in voice/tests/probe_wavs/
    --write-pin          write pronunciation_probe.json (default: only when
                         every probed term passes and no --only was given)
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
VOICE = HERE.parent
ROOT = VOICE.parent
sys.path.insert(0, str(VOICE))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

import synth  # noqa: E402

PIN = HERE / "pronunciation_probe.json"
WAVS = HERE / "probe_wavs"
REFERENCE = VOICE / "reference_A_clean_cond10.wav"

# Production parameters: voice/narrate_all.py defaults. The probe must hear
# what the batch produces, not a cleaner or a different voice.
EXAGGERATION, CFG_WEIGHT, TEMPERATURE, SEED = 0.4, 0.4, 0.7, 1234

# Carrier sentences. Two readings per term, in different positions, because
# a word at the end of a sentence is read differently from one mid-clause.
CARRIERS = (
    "Scientists have studied {t} for decades.",
    "The {t} is what the survey measured first.",
)

# Whisper normalises acronyms unpredictably ("R O V" -> "ROV" / "R.O.V.").
# Compare with everything but letters removed, and accept a close match.
# 0.84 let "chemosin, that ick" pass for chemosynthetic on the first run;
# 0.9 does not.
MATCH_RATIO = 0.9

# Whisper's own spelling of a word it does not know. "hadal" said correctly
# (HAY-dul) comes back as "Haydol"; that is the pronunciation being right and
# the transcriber's dictionary being small. Each alias is a spelling Whisper
# produced for a reading a human confirmed, nothing else. Keep this short.
WHISPER_SPELLINGS: dict[str, tuple[str, ...]] = {
    "MBARI": ("embaree", "embarry", "em bar ee", "embari", "mbare", "mbaree"),
    "Kaikō": ("kaiko", "kyko", "kaikou", "kyeko", "kaikoh"),
    "Grimpoteuthis": ("grimpotoothis", "grimpotoothus", "grimpotuthis"),
    "Pseudoliparis": ("pseudoliparis", "pseudoleparis", "sudoliparis"),
    "Kiwa": ("keewa", "kiwa", "keewah"),
    "Czochralski": ("chokralski", "chocralski", "chokralsky", "chochralski"),
    # "wootz" (WOOTS): raw, "woots" and "woot's" all came back as "woods" -
    # the transcriber normalises the sound to the common word. No entry.
    "wootz": ("woods", "woots", "wutz"),
    "hexamethyldisilazane": ("hexamethyldisilazane", "hexamethyldisylazane"),
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def heard(intended: str, transcript: str) -> tuple[bool, float]:
    """Does the transcript contain the intended word? (verdict, best ratio)."""
    have = norm(transcript)
    wants = [norm(intended)] + [norm(a) for a in WHISPER_SPELLINGS.get(intended, ())]
    best = 0.0
    for want in wants:
        if not want:
            continue
        if want in have:
            return True, 1.0
        w = len(want)
        for width in (w - 2, w - 1, w, w + 1, w + 2, w + 3):
            if width <= 0:
                continue
            for i in range(0, max(1, len(have) - width + 1)):
                r = difflib.SequenceMatcher(None, want, have[i:i + width]).ratio()
                best = max(best, r)
    return best >= MATCH_RATIO, best


def transcribe(wav: np.ndarray, key: str | None = None) -> str:
    """Local whisper.cpp; `key` is accepted and ignored (the old paid path)."""
    import tempfile
    import pronounce  # noqa: PLC0415
    why = pronounce.whisper_ready()
    if why:
        raise SystemExit(f"NAMED STOP [WHISPER_LOCAL_UNAVAILABLE]: {why}")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        sf.write(fh.name, wav, synth.SR, subtype="PCM_16")
        try:
            return pronounce.transcribe_file(fh.name)
        finally:
            os.unlink(fh.name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--write-pin", action="store_true")
    ap.add_argument("--raw", action="store_true",
                    help="speak each term WITHOUT its entry, to learn whether "
                         "the entry is needed at all")
    ap.add_argument("--raw-ok", default="",
                    help="comma list: probe raw and pin the passes as raw_ok")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--carriers", type=int, default=len(CARRIERS),
                    help="readings per term; a pin always uses all of them, "
                         "a --raw screen may use 1")
    args = ap.parse_args()
    if args.carriers < len(CARRIERS) and not args.raw:
        raise SystemExit("a pin needs every carrier; --carriers applies to --raw only")

    key = None   # local whisper.cpp; see transcribe()
    lex = dict(synth.LEXICON)
    if args.raw_ok:
        args.raw, args.only = True, args.raw_ok
    terms = [t.strip() for t in args.only.split(",") if t.strip()] or list(lex)
    unknown = [t for t in terms if t not in lex]
    if unknown and not args.raw:
        raise SystemExit(f"not in LEXICON: {unknown}")
    # --raw may name terms that have no entry yet: that is how a candidate
    # from the lexicon-gap scan is screened before anyone writes one.
    if not terms:
        raise SystemExit("NAMED STOP [ZERO_TERMS]: the lexicon is empty")

    import torch  # noqa: E402
    from chatterbox.tts import ChatterboxTTS  # noqa: E402
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device=args.device)
    model.prepare_conditionals(str(REFERENCE), exaggeration=EXAGGERATION)
    print(f"model ready in {time.time() - t0:.0f}s; probing {len(terms)} term(s)",
          flush=True)
    if args.keep:
        WAVS.mkdir(exist_ok=True)

    rows: dict[str, dict] = {}
    n_pass = 0
    for i, term in enumerate(terms, 1):
        readings = []
        ok_all = True
        for ci, carrier in enumerate(CARRIERS[:args.carriers]):
            sentence = carrier.format(t=term)
            use = {k: v for k, v in lex.items() if k != term} if args.raw else lex
            text = synth.apply_lexicon(sentence, use)
            torch.manual_seed(SEED + ci)
            wav = model.generate(text, audio_prompt_path=None,
                                 exaggeration=EXAGGERATION, cfg_weight=CFG_WEIGHT,
                                 temperature=TEMPERATURE)
            a = wav.squeeze(0).detach().cpu().numpy().astype(np.float32)
            pk = float(np.abs(a).max())
            if pk > 1.0:
                a = a / pk
            if args.keep:
                sf.write(WAVS / f"{norm(term)}-{ci}.wav", a, synth.SR, subtype="PCM_16")
            tr = transcribe(a, key)
            ok, ratio = heard(term, tr)
            ok_all = ok_all and ok
            readings.append({"carrier": sentence, "spoken_text": text,
                             "heard": tr, "ratio": round(ratio, 3), "ok": ok})
        rows[term] = {"respelling": lex.get(term), "ok": ok_all, "readings": readings}
        n_pass += ok_all
        mark = "ok " if ok_all else "MISS"
        worst = min(readings, key=lambda r: r["ratio"])
        shown = "(raw, no entry)" if args.raw else lex[term]
        print(f"  [{i:02d}/{len(terms)}] {mark} {term:<18} -> {shown!r:<28} "
              f"heard {worst['heard']!r}", flush=True)

    print(f"\n{n_pass}/{len(terms)} term(s) heard as intended")
    failed = [t for t in terms if not rows[t]["ok"]]
    if failed:
        print("MISS: " + ", ".join(failed))

    if args.raw_ok:
        pin = json.loads(PIN.read_text())
        ro = pin.setdefault("raw_ok", {})
        for t in terms:
            if rows[t]["ok"] and t not in lex:
                ro[t] = {"ok": True, "readings": rows[t]["readings"]}
        pin["raw_ok"] = dict(sorted(ro.items(), key=lambda kv: kv[0].lower()))
        pin["raw_ok_transcriber"] = "whisper.cpp ggml-small.en (local, $0)"
        PIN.write_text(json.dumps(pin, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {len(ro)} raw_ok proof(s) to {PIN.relative_to(ROOT)}")
        return 1 if failed else 0

    full = not args.only and not args.raw
    if args.write_pin or (full and not failed):
        pin = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "reference": REFERENCE.name,
               "params": {"exaggeration": EXAGGERATION, "cfg_weight": CFG_WEIGHT,
                          "temperature": TEMPERATURE, "seed": SEED},
               "match_ratio": MATCH_RATIO, "carriers": list(CARRIERS),
               "terms": rows}
        if not full and PIN.exists():
            old = json.loads(PIN.read_text())
            old["terms"].update(rows)
            old["generated"] = pin["generated"]
            pin = old
        PIN.write_text(json.dumps(pin, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {PIN.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
