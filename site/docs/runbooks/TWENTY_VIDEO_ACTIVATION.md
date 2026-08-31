# Twenty-Video Activation Runbook

## 1. Open the credentialless operations guide

1. Confirm the repository already exists on GitHub and GitHub Actions are enabled.
2. Open `/admin` on the deployed site.
3. Paste the existing GitHub repository as `owner/repository` and save the links locally.
4. Do not add YouTube or OAuth secrets to source files.

The `/admin` page links to the exact workflows, scripts, checklists, receipts, and runbooks below. It does not create a GitHub repository or store credentials.

## 2. Generate the Kokoro audition

1. From `/admin`, open **Generate Kokoro Voice Audition**.
2. Choose **Run workflow**.
3. Keep voice `af_heart` and generate the three configured speed variants.
4. Download the audition artifact.
5. Listen on headphones, laptop speakers, and phone speakers.
6. Record the selected speed in `production/narrator-selection.json` and the score in `production/narrator-scorecard.csv`.
7. Set narrator status to `human-approved` only after the listening decision.

## 3. Complete and approve the human pass

For each sequence 1–20:

1. Open the final Markdown script, plaintext narration, and matching human-pass file from `/admin`.
2. Rewrite the cold open by hand.
3. Watch the approved original assets and add one truthful `[HUMAN]` observation.
4. Add an evidence limit or disputed measurement where relevant.
5. Apply the final narration edits to both script forms.
6. Check every required box in the human-pass file.
7. From `/admin`, open **Approve Human Pass**.
8. Select the video number, enter the human reviewer name, and run the workflow.

The workflow refuses incomplete checklists, unresolved placeholders, missing `[HUMAN]` text, unexpectedly short narration, or a missing source section. It records the plaintext SHA-256 and commits the approval receipt.

After all twenty approvals, `python production/automation/validate_human_pass.py --count 20` must pass. Any later script edit invalidates the recorded hash.

## 4. Generate twenty Kokoro WAVs and MP4 masters

1. Confirm approvals show 20/20.
2. From `/admin`, open **Render Twenty-Video Launch Batch**.
3. Enter the approved voice and speed, choose `20`, and run.
4. Download `twenty-video-narration-wavs` and `twenty-video-public-review-mp4s` from the completed workflow.
5. Watch every opening, ending, chapter transition, and a middle section.
6. Replace failed masters before uploading. Mechanical validation does not replace human review.

## 5. Create YouTube credentials once

1. In Google Cloud Console, create or select a project.
2. Enable **YouTube Data API v3**.
3. Configure the OAuth consent screen.
4. Create a **Desktop app** OAuth client.
5. Download `client_secret.json` outside the repository.
6. Install dependencies:

    python -m pip install -r production/automation/requirements-youtube.txt

7. Bootstrap the refresh token outside Git:

    python production/automation/bootstrap_youtube_oauth.py --client-secrets /absolute/path/client_secret.json --output /secure/path/youtube-token.json

## 6. Dry-run the schedule

Choose a future Monday:

    python production/automation/upload_batch.py --start-date YYYY-MM-DD --timezone America/Chicago --limit 20

Inspect every receipt under `production/provider-receipts/youtube/`. A dry-run receipt has no video ID.

## 7. Upload and schedule

    YOUTUBE_TOKEN_JSON=/secure/path/youtube-token.json python production/automation/upload_batch.py --start-date YYYY-MM-DD --timezone America/Chicago --limit 20 --publish

The uploader creates each video as private, schedules it, applies its thumbnail, and writes the returned video ID and watch URL into the provider receipt.

## 8. Retrieve live YouTube IDs

Read `production/provider-receipts/youtube/*.json`. A successful provider receipt contains `videoId` and `watchUrl` returned by YouTube.

## 9. Activate videos on the site

After manually confirming public playback:

    python production/automation/sync_site_from_receipts.py --confirm-public
    npm run generate
    npm run validate
    npm test
    npm run build

Then deploy. This adds players, transcripts, chapters, `VideoObject`, Watch listings, and the video sitemap only after public confirmation.
