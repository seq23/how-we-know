# Pronunciation probe

This used to be a paragraph of narration to synthesise and listen to by ear.
Nobody did, and the lexicon shipped respellings the model read as letters
("Bath-E-Pell A.J. Ike" for bathypelagic, heard by the owner on 2026-09-21).

The probe is now executable and its verdict is pinned:

    cd ~/GitHub/creator-network && python3 scripts/vault-exec.py -- \
        ~/GitHub/how-we-know/.venv-tts/bin/python \
        ~/GitHub/how-we-know/voice/tests/pronunciation_probe.py

- `pronunciation_probe.py` synthesises every `synth.LEXICON` term in two
  carrier sentences with the production voice and parameters, transcribes
  each with whisper-1, and passes a term only when the transcript contains it.
- `--raw` speaks a term WITHOUT its entry: the screen that decides whether an
  entry is needed at all. `--only a,b` iterates on a few. `--keep` leaves the
  wavs in `probe_wavs/` to listen to.
- A full passing run writes `pronunciation_probe.json`, which
  `loop/tests/test_lexicon_respellings.py` reads on every suite run: an entry
  that is missing from the pin, changed since, or was not heard as intended
  fails the suite, as does a hyphen or a CAPS chunk in any respelling.
