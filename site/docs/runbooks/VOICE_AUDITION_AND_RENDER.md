# Voice Audition and Final Render Runbook

## Purpose

Generate the real Kokoro narration WAVs and the ten public-review MP4s in an internet-enabled GitHub Actions runner. The local artifact sandbox cannot fetch Kokoro's Python package or model weights, so no fallback voice may be mislabeled as final.

## Phase A — Human audition

1. Push the repository to GitHub.
2. Open **Actions → Generate Kokoro Voice Audition → Run workflow**.
3. Keep `af_heart` and speeds `0.94,0.98,1.02` for the first run.
4. Download the `kokoro-voice-audition-af_heart` artifact.
5. Listen on headphones and phone speakers.
6. Record one approved speed in `production/narrator-selection.json`.

Approval criteria:

- Calm documentary tone.
- No distracting breathiness or cheerfulness.
- Clean pronunciation of oceanographic terms.
- No clipped final words.
- Comfortable for an eight-minute listen.

The human audition cannot be automated. Acoustic validators can catch clipping and missing files; only a person can approve the channel voice.

## Phase B — Ten narration WAVs and MP4s

1. Open **Actions → Render Launch Video Batch → Run workflow**.
2. Enter the approved voice and speed.
3. Select `10` videos.
4. Download both output artifacts:
   - `launch-narration-wavs`
   - `launch-public-review-mp4s`
5. Review every video before upload. These are public-review masters, not automatically public releases.

## Phase C — YouTube scheduling

Long-form videos should be uploaded and scheduled through YouTube, not Buffer's Shorts integration.

One-time local authorization:

    python production/automation/bootstrap_youtube_oauth.py \
      --client-secrets client_secret.json \
      --output youtube-token.json

Dry-run twenty-video schedule:

    python production/automation/upload_batch.py \
      --start-at 2026-08-03T09:00:00-05:00 \
      --interval-hours 24

Actual upload and scheduling:

    YOUTUBE_TOKEN_JSON=youtube-token.json \
    python production/automation/upload_batch.py \
      --start-at 2026-08-03T09:00:00-05:00 \
      --interval-hours 24 \
      --publish

Scheduled videos remain private until their `publishAt` timestamps. Never commit OAuth files or refresh tokens.


For the canonical current flow, use `TWENTY_VIDEO_ACTIVATION.md`.
