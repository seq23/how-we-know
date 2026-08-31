# Humanized Script and Render Gate

**Version:** 1.4.0  
**Status:** Active

## What is complete

All twenty launch scripts have received an editorial humanization pass. Each script now contains:

- a unique rewritten cold open;
- one drafted first-person producer observation marked `[HUMAN]`;
- an explicit evidence limitation, correction, or uncertainty;
- a recorded structural variation;
- 1,150–1,350 narration words;
- three key sourced claim checks;
- an exhaustive source map for every digit-bearing narration sentence;
- a fail-closed full-master watch requirement.

The machine-readable and human-readable audits are:

- `production/research/humanization-audit.json`
- `production/research/humanization-audit.md`
- `production/research/number-verification.json`
- `production/research/number-verification.md`
- `production/research/number-verification-exhaustive.json`
- `production/research/number-verification-exhaustive.md`

## What remains human

The drafted first-person observation is not automatically the owner's personal testimony. For each script, the owner must:

1. Read the cold open aloud.
2. Confirm or rewrite the `[HUMAN]` line so it is genuinely true.
3. Listen to the approved Kokoro voice pronounce names and numbers.
4. Watch the complete rendered MP4.
5. Check pacing, title, thumbnail, rights, source links, and final disclosure.
6. Mark every required checklist item in `production/human-pass/NN-slug.md`.
7. Run the receipt-backed approval workflow or `approve_human_pass.py`.

## Kokoro and final render path

The repository contains the real internet-enabled render workflow:

- `.github/workflows/voice-audition.yml`
- `.github/workflows/render-launch-batch.yml`
- `production/automation/synthesize_narration.py`
- `production/automation/render_all.sh`

The artifact environment could not download the Kokoro package and model files. Therefore, it did not fabricate Kokoro WAVs or label fallback speech as final.

A 45.5-second local technical proof was rendered with eSpeak solely to prove the FFmpeg pipeline:

- `production/proofs/01-humanized-technical-proof.wav`
- `production/proofs/01-humanized-technical-proof.mp4`
- `production/proofs/01-humanized-technical-proof-receipt.json`

Do not publish the proof. Its narration is not Kokoro and has not been human-approved.

## Validation commands

```bash
npm run validate
npm test
python production/automation/validate_human_pass.py --count 20
```

The first two commands should pass now. The human-pass command must fail until all twenty scripts are personally confirmed and receipt-approved.
