# Deep Sea Authority Engine
## Remaining Phases — Step-by-Step Operator Runbook

**Repository baseline:** v1.3.0  
**Baseline commit:** `4950c8c7774962d2bf47d753893f203134e1247b`  
**Audience:** Owner/operator using GitHub, a local computer, Google Cloud, YouTube, and Cloudflare  
**Purpose:** Complete the human approval, Kokoro narration, twenty-master render, YouTube publication, site synchronization, and deployment phases.

---

# 1. Finish line

This runbook is complete when all of the following are true:

- [ ] Kokoro narrator voice and speed are human-approved.
- [ ] All 20 scripts have completed the human editorial pass.
- [ ] The human-pass approval ledger shows `20/20` approved.
- [ ] Twenty final Kokoro narration WAVs exist.
- [ ] Twenty reviewed MP4 masters exist.
- [ ] All 20 videos are uploaded to the correct YouTube channel.
- [ ] Every upload has a real YouTube `videoId` and `watchUrl` receipt.
- [ ] Each video is scheduled or public in YouTube Studio.
- [ ] Public videos are synchronized into the companion site.
- [ ] The site passes generation, validation, tests, typecheck, and build.
- [ ] The site is deployed and the public video pages work.

Do the phases in order. Do not skip the human voice or human script gates.

---

# 2. What happens where

| Work | Where it happens |
|---|---|
| Navigate to files and workflows | `/admin` page |
| Generate Kokoro audition WAVs | GitHub Actions |
| Listen and choose the narrator | Your ears: headphones, laptop, phone |
| Edit scripts and checklists | `github.dev`, GitHub web editor, or local editor |
| Record script approvals | GitHub Actions |
| Generate 20 WAVs and MP4s | GitHub Actions |
| Review final masters | Your local computer |
| Create YouTube OAuth credentials | Google Cloud Console |
| Authorize the YouTube channel | Your local computer/browser |
| Dry-run and upload the batch | Your local computer |
| Receive live YouTube IDs | Provider receipt JSON files |
| Synchronize videos into the site | Your local computer |
| Deploy site | GitHub Actions or local Wrangler |

`/admin` is a credentialless guide. It opens the correct GitHub pages but does not run actions, store tokens, or know live provider status.

---

# 3. Before starting

## 3.1 Required starting state

- The v1.3.0 repository already exists on GitHub.
- The v1.3.0 files are on the repository's default branch, normally `main`.
- GitHub Actions is enabled for the repository.
- You can write to the repository.
- You have access to the Google account that owns the YouTube channel.
- You have a local Mac, Windows, or Linux computer for OAuth and final provider commands.

## 3.2 Local software

Install or confirm:

- Git
- Python 3.12 or newer
- Node.js 22.12 or newer
- npm
- FFmpeg and `ffprobe`

Check them:

```bash
git --version
python3 --version
node --version
npm --version
ffmpeg -version
ffprobe -version
```

On macOS with Homebrew:

```bash
brew install git python node ffmpeg
```

## 3.3 Clone the existing repository

Replace the placeholder with your real repository:

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Confirm the expected version:

```bash
node -p "require('./package.json').version"
```

Expected:

```text
1.3.0
```

## 3.4 Open `/admin`

Use either method:

### Deployed site

Open:

```text
https://YOUR_SITE_DOMAIN/admin
```

Paste:

```text
YOUR_GITHUB_OWNER/YOUR_REPOSITORY
```

Select **Save links**.

### Local site

Create the local environment file:

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```text
VITE_SITE_URL=http://localhost:3000
VITE_GA_MEASUREMENT_ID=
VITE_GITHUB_REPOSITORY=YOUR_GITHUB_OWNER/YOUR_REPOSITORY
VITE_GITHUB_BRANCH=main
```

Install and start:

```bash
npm install
npm run dev
```

Open the local URL printed by Vite, then add `/admin`.

---

# 4. Phase 1 — Generate the Kokoro voice audition

## 4.1 Run the workflow

From `/admin`, select **Open voice-audition workflow**.

Or in GitHub:

1. Open the repository.
2. Select **Actions**.
3. Select **Generate Kokoro Voice Audition**.
4. Select **Run workflow**.
5. Choose the default branch.
6. Enter:

```text
voice: af_heart
speeds: 0.94,0.98,1.02
```

7. Select **Run workflow**.

The workflow is defined at:

```text
.github/workflows/voice-audition.yml
```

## 4.2 Download the audition files

After the workflow succeeds:

1. Open the completed workflow run.
2. Find **Artifacts**.
3. Download:

```text
kokoro-voice-audition-af_heart
```

The repository retains this artifact for 14 days. Download it before it expires.

## 4.3 Listen correctly

Listen to every speed on:

- Headphones
- Laptop speakers
- Phone speakers

Score each version from 1–5:

| Test | What to listen for |
|---|---|
| Authority | Calm documentary presence, not cheerful or sales-like |
| Pronunciation | Scientific and oceanographic terms sound acceptable |
| Pacing | Not rushed, not sluggish |
| Clipping | No cut-off words or endings |
| Fatigue | Comfortable for an 8–12 minute video |
| Consistency | Stable voice and loudness throughout |

## 4.4 Decide the speed

Default decision rule:

- Choose `0.94` if `0.98` feels rushed.
- Choose `0.98` if it feels natural and controlled.
- Choose `1.02` only if `0.98` feels clearly too slow.
- Reject `af_heart` and run another audition if the voice itself is wrong.

This decision cannot be automated. A waveform validator cannot decide whether the channel voice feels right.

---

# 5. Phase 2 — Record the narrator decision

From `/admin`, open:

```text
production/narrator-selection.json
production/narrator-scorecard.csv
```

## 5.1 Update `narrator-selection.json`

Set the approved speed and status:

```json
{
  "voice": "af_heart",
  "speed": 0.98,
  "status": "human-approved"
}
```

Do not delete the other existing fields. Change only the selected values.

## 5.2 Update `narrator-scorecard.csv`

Record the scores and your final decision. Preserve the existing CSV headers.

## 5.3 Commit the decision

Using GitHub's web editor, `github.dev`, or local Git, commit both files.

Local command option:

```bash
git add production/narrator-selection.json production/narrator-scorecard.csv
git commit -m "Approve Kokoro narrator configuration"
git push
```

## 5.4 Gate check

Do not continue until:

- `production/narrator-selection.json` contains `"status": "human-approved"`.
- The chosen speed matches the audition you actually listened to.
- The scorecard records the human decision.

---

# 6. Phase 3 — Complete the human pass for all 20 videos

This is the longest owner task. Work in batches of five if needed, but approve each video separately.

## 6.1 Easiest browser editing method

1. Open the repository on GitHub.
2. Press the `.` key.
3. GitHub opens the repository in the browser-based `github.dev` editor.
4. Edit all three files for one video.
5. Commit and push the three-file change together.

## 6.2 Files for each video

For sequence `NN`, edit:

```text
production/scripts/final/NN-SLUG.md
production/scripts/plaintext/NN-SLUG.txt
production/human-pass/NN-SLUG.md
```

The `/admin` table links directly to all three files for each sequence.

## 6.3 Required changes for each video

### A. Final Markdown script

In `production/scripts/final/NN-SLUG.md`:

- Rewrite the cold open in your own words.
- Read the cold open aloud once.
- Add one truthful first-person line marked `[HUMAN]`.
- Preserve the `## SOURCES` section.
- Add a factual limitation, contested measurement, or source boundary when relevant.
- Make at least one structural choice different from the preceding video.
- Remove unresolved placeholders.

Example format:

```text
[HUMAN] I replayed the expedition footage several times, and the animal disappears against the seafloor faster than the still images suggest.
```

Only use a statement you actually observed. Do not paste the example unless it is true.

### B. Plaintext narration

In `production/scripts/plaintext/NN-SLUG.txt`:

- Apply the same final narration wording.
- Include the truthful `[HUMAN]` line.
- Keep at least 900 words.
- Remove unresolved placeholders.

The plaintext file is the file Kokoro narrates. If the Markdown and plaintext disagree, the audio follows the plaintext.

### C. Human-pass checklist

In `production/human-pass/NN-SLUG.md`:

- Replace the observation placeholder with the actual `[HUMAN]` line.
- Check every required box by changing `[ ]` to `[x]`.
- Do not manually mark the recorded approval section as complete.
- The approval workflow writes the reviewer, timestamp, and SHA-256 receipt.

## 6.4 Commit the edits before approval

Commit the three edited files for that video.

Example:

```bash
git add \
  production/scripts/final/01-why-deep-sea-creatures-look-so-weird.md \
  production/scripts/plaintext/01-why-deep-sea-creatures-look-so-weird.txt \
  production/human-pass/01-why-deep-sea-creatures-look-so-weird.md

git commit -m "Complete human pass for video 01"
git push
```

## 6.5 Run the approval workflow

From `/admin`, select **Run approval workflow**.

Or in GitHub:

1. Open **Actions**.
2. Select **Approve Human Pass**.
3. Select **Run workflow**.
4. Choose the sequence number.
5. Enter the reviewer name exactly as you want it recorded.
6. Run the workflow.

The workflow:

- Verifies the final Markdown script exists.
- Verifies the plaintext narration exists.
- Verifies the checklist is fully checked.
- Requires a truthful `[HUMAN]` line.
- Rejects unresolved placeholders.
- Requires the Markdown `SOURCES` section.
- Requires at least 900 plaintext words.
- Records the plaintext SHA-256.
- Updates the approval ledger.
- Commits and pushes the approval receipt.

## 6.6 Repeat for all 20

Use this sequence list:

| # | Slug |
|---:|---|
| 01 | `why-deep-sea-creatures-look-so-weird` |
| 02 | `how-deep-sea-creatures-survive-pressure` |
| 03 | `why-deep-sea-creatures-are-surfacing` |
| 04 | `why-deep-sea-creatures-are-so-scary` |
| 05 | `why-many-deep-sea-creatures-are-red` |
| 06 | `why-some-deep-sea-creatures-are-transparent` |
| 07 | `why-deep-sea-creatures-get-creepier-deeper` |
| 08 | `what-creatures-live-in-the-deep-sea` |
| 09 | `what-is-the-scariest-deep-sea-creature` |
| 10 | `what-is-the-deepest-part-of-the-ocean` |
| 11 | `what-is-a-dumbo-octopus` |
| 12 | `what-is-a-frilled-shark` |
| 13 | `how-does-bioluminescence-work-in-the-deep-sea` |
| 14 | `how-big-is-a-colossal-squid` |
| 15 | `how-do-people-reach-challenger-deep` |
| 16 | `what-happens-when-a-whale-dies-in-the-deep-ocean` |
| 17 | `what-is-a-yeti-crab` |
| 18 | `why-does-black-smoker-water-not-boil` |
| 19 | `what-is-the-deepest-fish-ever-recorded` |
| 20 | `what-is-the-midnight-zone` |

## 6.7 Validate the full approval gate

Pull the workflow commits locally:

```bash
git pull
```

Run:

```bash
python3 production/automation/validate_human_pass.py --count 20
```

Expected:

```json
{
  "approved": 20,
  "status": "pass"
}
```

## 6.8 Important hash rule

If you edit a plaintext narration file after approving it, the stored hash no longer matches. The render workflow will fail.

After any post-approval narration edit:

1. Update the Markdown and checklist if needed.
2. Commit the edit.
3. Run **Approve Human Pass** again for that sequence.

---

# 7. Phase 4 — Render all 20 Kokoro WAVs and MP4 masters

## 7.1 Confirm the gate

Before running the batch:

- Narrator status is `human-approved`.
- Human-pass validation shows `20/20`.
- All approval workflow commits are on the default branch.

## 7.2 Run the render workflow

From `/admin`, select **Open twenty-video render workflow**.

Or in GitHub:

1. Open **Actions**.
2. Select **Render Twenty-Video Launch Batch**.
3. Select **Run workflow**.
4. Enter the approved voice.
5. Enter the approved speed.
6. Select `20` for `video_count`.
7. Run the workflow.

Expected inputs:

```text
voice: af_heart
speed: 0.98
video_count: 20
```

Use your actual approved speed, not automatically `0.98`.

The workflow is allowed up to six hours. It installs Kokoro and FFmpeg, validates human approvals, creates narration WAVs, renders the MP4s, and runs mechanical validation.

## 7.3 Download both artifacts

After success, download:

```text
twenty-video-narration-wavs
twenty-video-public-review-mp4s
```

The artifacts are retained for 14 days.

## 7.4 Put the files into the local repository

Extract or copy the files into:

```text
production/audio/narration/
production/outputs/
```

The WAV and MP4 binaries are intentionally Git-ignored. Keep a separate backup outside the repository.

Recommended backup structure:

```text
Deep-Sea-Launch-Masters/
  narration-wavs/
  mp4-masters/
  workflow-artifacts-original/
```

## 7.5 Validate the local batch

Run:

```bash
python3 production/automation/validate_rendered_batch.py --count 20
```

Expected output includes:

```text
production/outputs/render-receipt.json
```

The validator confirms:

- 20 WAVs exist.
- 20 MP4s exist.
- Each MP4 is at least seven minutes.
- Each MP4 is larger than the suspiciously-small-file threshold.
- `ffprobe` can read the files.

Mechanical validation does not approve the videos for publication.

---

# 8. Phase 5 — Human-review the 20 rendered masters

Review every MP4 before any upload.

## 8.1 Minimum review points per video

Watch:

- First 60 seconds
- Every chapter transition
- At least one full middle section
- Final 60 seconds

## 8.2 Master review checklist

For each video:

- [ ] Cold open sounds human and specific.
- [ ] Scientific names are pronounced acceptably.
- [ ] No sentence is cut off.
- [ ] No unexplained voice change occurs.
- [ ] Narration is louder than the music.
- [ ] Music does not pulse or distract.
- [ ] No frozen, black, corrupt, or missing frames.
- [ ] Thumbnail opening is legible.
- [ ] Title and spoken topic match.
- [ ] Chapters occur in the right order.
- [ ] Video length is acceptable.
- [ ] The ending names the intended next episode.
- [ ] Factual limits and sources remain accurate.

## 8.3 Failure handling

If one video fails:

1. Do not rerender all 20 unless necessary.
2. Fix the affected source script, asset, or metadata.
3. If narration changes, reapprove its human-pass hash.
4. Render that item again using the repository automation.
5. Replace the failed master.
6. Rerun the rendered-batch validator.

A mechanically valid MP4 becomes a **final public master** only after this human review passes.

---

# 9. Phase 6 — Create YouTube API credentials

YouTube uploads require OAuth authorization for the Google account that owns the channel.

## 9.1 Create or select a Google Cloud project

In Google Cloud Console:

1. Create or select a project.
2. Name it something recognizable, such as `Deep Sea Channel Publisher`.
3. Open the API library.
4. Enable **YouTube Data API v3**.

## 9.2 Configure OAuth

In the Google Auth/OAuth area:

1. Configure the consent screen or app branding.
2. Choose the appropriate audience.
3. If the app remains in testing, add your own Google account as a test user.
4. Create an OAuth client.
5. Choose **Desktop app**.
6. Download the client JSON.

Save it outside the repository, for example:

```text
~/secure/deep-sea/client_secret.json
```

Never commit this file.

## 9.3 Install the YouTube Python dependencies

From the repository root:

```bash
python3 -m pip install -r production/automation/requirements-youtube.txt
```

## 9.4 Create the local refresh-token file

```bash
mkdir -p ~/secure/deep-sea

python3 production/automation/bootstrap_youtube_oauth.py \
  --client-secrets ~/secure/deep-sea/client_secret.json \
  --output ~/secure/deep-sea/youtube-token.json
```

A browser opens.

1. Sign in with the account that owns the correct YouTube channel.
2. Review the requested `youtube.upload` permission.
3. Approve it.
4. Confirm the token JSON was written.

Check:

```bash
ls -l ~/secure/deep-sea/youtube-token.json
```

Never commit `client_secret.json` or `youtube-token.json`.

---

# 10. Phase 7 — Dry-run the twenty-video schedule

The repository's default launch cadence is:

- 4 videos per day
- 5 days
- America/Chicago
- 9:00 AM
- 12:30 PM
- 4:00 PM
- 7:30 PM

## 10.1 Choose the start date

Choose a future date in `YYYY-MM-DD` format. A Monday is recommended for the five-day launch wave.

Example placeholder:

```text
YYYY-MM-DD
```

## 10.2 Run the dry run

Do not add `--publish`:

```bash
python3 production/automation/upload_batch.py \
  --start-date YYYY-MM-DD \
  --timezone America/Chicago \
  --limit 20
```

This does not contact YouTube. It writes intended provider receipts under:

```text
production/provider-receipts/youtube/
```

## 10.3 Inspect all 20 dry-run receipts

Every receipt should contain:

```json
{
  "mode": "dry-run",
  "privacyStatus": "private",
  "publishAt": "FUTURE_TIMESTAMP",
  "videoId": null,
  "watchUrl": null
}
```

Check:

- Correct MP4 filename
- Correct thumbnail
- Correct title
- Correct article slug
- Correct date
- Correct local time
- Correct order
- No duplicate sequence
- `videoId` is null
- `watchUrl` is null

Stop and fix metadata or schedule errors before publishing.

---

# 11. Phase 8 — Upload and schedule all 20 videos

## 11.1 Final preflight

Confirm:

- [ ] All 20 final masters passed human review.
- [ ] All 20 thumbnails are correct.
- [ ] All descriptions and source links are correct.
- [ ] Dry-run receipts are correct.
- [ ] Start date is in the future.
- [ ] OAuth token belongs to the correct channel owner.

## 11.2 Run the real upload

```bash
YOUTUBE_TOKEN_JSON=~/secure/deep-sea/youtube-token.json \
python3 production/automation/upload_batch.py \
  --start-date YYYY-MM-DD \
  --timezone America/Chicago \
  --limit 20 \
  --publish
```

The uploader:

- Uploads each MP4.
- Sets title, description, tags, language, and category.
- Declares `containsSyntheticMedia: true`.
- Starts each upload as private.
- Sets the future `publishAt` timestamp.
- Applies the custom PNG thumbnail.
- Writes the returned YouTube ID and watch URL into the provider receipt.

## 11.3 Watch the terminal

The uploader prints progress during resumable upload. Do not close the terminal while it is running.

If the command stops on one video:

1. Read the error.
2. Do not rerun blindly.
3. Inspect which receipts already contain real IDs.
4. Avoid duplicate uploads.
5. Resume manually or patch the batch script only after identifying the exact stopping point.

## 11.4 Important API audit boundary

A newly created or unaudited YouTube API project may upload videos that remain restricted to private viewing. The upload can still return a real video ID.

After the batch:

1. Open YouTube Studio.
2. Confirm all 20 uploads exist.
3. Confirm thumbnail, title, and description.
4. Confirm whether each video shows a valid scheduled-publication time.
5. If the API project cannot make them public, schedule them manually in YouTube Studio or complete the required API compliance audit.

Do not interpret a returned ID as proof that the video is public.

---

# 12. Phase 9 — Verify and record the live YouTube IDs

Provider receipts are written under:

```text
production/provider-receipts/youtube/
```

A successful live receipt contains:

```json
{
  "mode": "publish",
  "videoId": "REAL_YOUTUBE_ID",
  "watchUrl": "https://www.youtube.com/watch?v=REAL_YOUTUBE_ID",
  "publishAt": "..."
}
```

## 12.1 Print the full ID list

```bash
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("production/provider-receipts/youtube").glob("*.json")):
    receipt = json.loads(path.read_text())
    print(
        path.stem,
        receipt.get("videoId"),
        receipt.get("watchUrl"),
        receipt.get("publishAt"),
    )
PY
```

## 12.2 ID gate

Do not continue until every intended upload has:

- A nonempty `videoId`
- A valid `watchUrl`
- The expected `publishAt`
- A matching video in YouTube Studio

Commit provider receipts only if you intentionally want the non-secret IDs, URLs, and scheduling evidence in repository history. Never commit OAuth credentials.

---

# 13. Phase 10 — Confirm public playback

Wait until the videos reach their publication times.

For every video:

- Open the watch URL in a signed-out/private browser window.
- Confirm it is public.
- Confirm playback starts.
- Confirm the thumbnail appears.
- Confirm title and description are correct.
- Confirm chapter timestamps work.
- Confirm the description links back to the correct article URL.

Do not run the site synchronization command while videos are merely private or scheduled.

---

# 14. Phase 11 — Synchronize public videos into the site

The synchronization script trusts your `--confirm-public` flag. It does not call YouTube to prove public status.

The local MP4 masters must still be present because the script uses `ffprobe` to compute duration.

Run:

```bash
python3 production/automation/sync_site_from_receipts.py --confirm-public
```

The script updates `content/questions.json` with:

- `status: published`
- Real YouTube video ID
- YouTube thumbnail URL
- Upload/publication date
- Verified MP4 duration
- Final transcript
- Chapters

## 14.1 Regenerate and validate

```bash
npm install
npm run generate
npm run validate
npm test
npm run typecheck
npm run build
```

Or use the combined command:

```bash
npm run verify
```

## 14.2 Inspect generated video surfaces

Confirm:

- Question pages show the visible player.
- `/watch` lists the published videos.
- `VideoObject` JSON-LD exists only for published videos.
- `/video-sitemap.xml` contains the published videos.
- Article and video title/answer language remain synchronized.
- Canonical URLs point to the production domain.

## 14.3 Commit the activation

```bash
git add \
  content/questions.json \
  public \
  content/admin-status.json \
  production/provider-receipts/youtube

git commit -m "Activate twenty published YouTube videos"
git push
```

Adjust the staged paths if generation changes additional tracked files.

---

# 15. Phase 12 — Configure the production site environment

Create or update `.env.local` locally:

```text
VITE_SITE_URL=https://YOUR_PRODUCTION_DOMAIN
VITE_GA_MEASUREMENT_ID=
VITE_GITHUB_REPOSITORY=YOUR_GITHUB_OWNER/YOUR_REPOSITORY
VITE_GITHUB_BRANCH=main
```

Rules:

- `VITE_SITE_URL` must be the real canonical production origin before final build.
- Leave analytics empty until the measurement property and privacy requirements are ready.
- `VITE_GITHUB_REPOSITORY` is not a secret.
- Do not commit `.env.local`.

---

# 16. Phase 13 — Deploy to Cloudflare Workers

The repository deploys TanStack Start output to Cloudflare Workers using:

```text
.output/server/index.mjs
.output/public
```

## 16.1 Local deployment option

Authenticate Wrangler:

```bash
npx wrangler login
```

Validate and deploy:

```bash
npm install
npm run verify
npx wrangler deploy
```

## 16.2 GitHub Actions deployment option

Add these repository secrets:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

The current workflow does not automatically inject the public Vite environment values. Before relying on GitHub Actions for the final canonical build, do one of the following:

### Preferred: add repository variables and expose them in the workflow

Create these GitHub repository variables under **Settings → Secrets and variables → Actions → Variables**:

```text
VITE_SITE_URL=https://YOUR_PRODUCTION_DOMAIN
VITE_GITHUB_REPOSITORY=YOUR_GITHUB_OWNER/YOUR_REPOSITORY
VITE_GITHUB_BRANCH=main
VITE_GA_MEASUREMENT_ID=
```

Then edit `.github/workflows/deploy-cloudflare.yml` and add this job-level environment block under `jobs.deploy`:

```yaml
env:
  VITE_SITE_URL: ${{ vars.VITE_SITE_URL }}
  VITE_GITHUB_REPOSITORY: ${{ vars.VITE_GITHUB_REPOSITORY }}
  VITE_GITHUB_BRANCH: ${{ vars.VITE_GITHUB_BRANCH }}
  VITE_GA_MEASUREMENT_ID: ${{ vars.VITE_GA_MEASUREMENT_ID }}
```

Commit that workflow change before running deployment.

### Alternative: deploy locally

Use Section 16.1. Local deployment reads `.env.local`, which is simpler when you do not want to edit the GitHub workflow.

Then, for GitHub Actions:

1. Open **Actions**.
2. Select **Deploy Cloudflare Worker**.
3. Select **Run workflow**.
4. Run it on the default branch.

The deployment workflow runs `npm install`, `npm run verify`, and Wrangler deploy.

If you do not yet know the final Workers URL or custom domain, perform an initial deployment, record the assigned URL, set `VITE_SITE_URL` to that canonical origin, then rebuild and deploy again. Do not leave the provisional fallback domain in the final canonical tags.

## 16.3 Deployment verification

On the public origin, confirm:

- Home page loads.
- `/admin` loads and remains `noindex`.
- `/explore` works on desktop and mobile.
- `/questions/` routes load.
- `/creatures/` routes load.
- `/zones/` routes load.
- `/watch` shows published videos.
- `/sitemap.xml` loads.
- `/video-sitemap.xml` loads after video activation.
- `/robots.txt` loads.
- `/llms.txt` loads.
- Canonicals use the production domain.
- JSON-LD is valid and matches visible content.
- Embedded videos play.
- Reduced-motion behavior works.

Attach the custom domain only after the Worker URL is healthy.

---

# 17. Refresh `/admin` readiness counts

`/admin` displays the status committed into the deployed snapshot. It does not poll GitHub or YouTube.

After approvals, renders, receipts, or site activation change:

```bash
npm run generate
npm run validate
npm test
npm run build
```

Commit and redeploy the generated status file if you want `/admin` to show the latest counts.

Expected final `/admin` state:

- Narrator: approved
- Human approvals: `20/20`
- Narration WAVs: `20/20` if receipts/files are present in the generation environment
- MP4 masters: `20/20` if receipts/files are present in the generation environment
- YouTube IDs: `20/20`
- Site activations: `20/20`
- Release gate: ready/complete

Remember: WAV and MP4 binaries are Git-ignored, so a deployment runner may not see them unless receipts or another durable record are used. The authoritative publication proof is the provider receipt plus public playback.

---

# 18. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| **Run workflow** button is missing | Workflow is not on the default branch or you lack write access | Confirm the YAML is on `main`, Actions is enabled, and your account has write access |
| Approval workflow cannot push | Repository or organization policy blocks `GITHUB_TOKEN` writes, or branch protection rejects direct pushes | Permit Actions write access or modify the workflow to open a branch/PR |
| Approval says checklist incomplete | One or more `[ ]` boxes remain | Check every required item and commit the checklist |
| Approval says missing `[HUMAN]` | The line is absent from Markdown, plaintext, or checklist | Add the same truthful observation and commit |
| Approval says script too short | Plaintext is under 900 words | Restore the full final narration |
| Render says script changed after approval | Plaintext SHA-256 no longer matches | Run the approval workflow again for that sequence |
| Kokoro workflow fails during install | Temporary package/network failure or dependency issue | Rerun once; if repeated, inspect the failed install step and dependency log |
| Render workflow exceeds time | GitHub-hosted runner is too slow for the batch | Render 5 or 10 at a time, preserving sequence and output names |
| Artifact is missing | Workflow failed or artifact expired | Open the run logs or rerun the workflow; artifacts are retained for 14 days |
| `ffprobe` is missing | FFmpeg is not installed locally | Install FFmpeg and rerun validation |
| OAuth browser uses wrong Google account | Multiple accounts are signed in | Sign out or use a private browser window, then bootstrap again |
| OAuth produces no refresh token | Prior grant or consent behavior | Revoke the app grant and rerun bootstrap; the script requests offline consent |
| YouTube upload remains private | API project is unaudited or schedule was not accepted | Verify in YouTube Studio; manually schedule or complete the API audit |
| Upload stops mid-batch | Provider/network/quota/file error | Inspect existing receipts first; do not blindly rerun and create duplicates |
| Site sync updates zero items | Receipts lack IDs, article slugs do not match, or files are missing | Inspect receipt JSON and production metadata |
| Site sync fails on `ffprobe` | Local MP4s are absent or FFmpeg is missing | Restore the masters to `production/outputs/` and install FFmpeg |
| Build uses wrong canonical domain | `VITE_SITE_URL` is not set correctly | Set the real production origin before building |
| Cloudflare workflow fails | Missing/invalid secrets, permissions, or build failure | Verify `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, then inspect the first failing step |
| `/admin` counts look old | It is snapshot-based, not live | Regenerate, commit, build, and redeploy |

---

# 19. Final launch acceptance checklist

## Narration and scripts

- [ ] Narrator audition heard on three playback devices.
- [ ] Narrator selection recorded as `human-approved`.
- [ ] All 20 scripts contain a truthful `[HUMAN]` line.
- [ ] All 20 scripts retain sources and factual limits.
- [ ] Human approval ledger passes `20/20`.

## Media

- [ ] Twenty Kokoro WAVs generated.
- [ ] Twenty MP4s mechanically validated.
- [ ] Twenty MP4s human-reviewed.
- [ ] Twenty final masters backed up outside GitHub.

## YouTube

- [ ] Correct Google account authorized.
- [ ] Dry-run receipts inspected.
- [ ] Twenty uploads visible in YouTube Studio.
- [ ] Titles, descriptions, thumbnails, and schedules verified.
- [ ] Twenty real IDs recorded.
- [ ] Every intended public video verified in a signed-out browser.

## Site

- [ ] Public receipts synchronized into canonical records.
- [ ] Generation passes.
- [ ] Validators pass.
- [ ] Tests pass.
- [ ] Typecheck passes.
- [ ] Production build passes.
- [ ] Players, Watch page, JSON-LD, and video sitemap verified.
- [ ] Canonical origin is correct.
- [ ] Cloudflare deployment is healthy.
- [ ] `/admin` remains credentialless and noindex.

---

# 20. Official reference links

- GitHub: manually run a workflow  
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow

- GitHub: download workflow artifacts  
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts

- GitHub: browser-based `github.dev` editor  
  https://docs.github.com/en/codespaces/the-githubdev-web-based-editor

- YouTube Data API: getting started  
  https://developers.google.com/youtube/v3/getting-started

- YouTube Data API: OAuth for desktop/installed apps  
  https://developers.google.com/youtube/v3/guides/auth/installed-apps

- YouTube Data API: video upload endpoint and private restriction notice  
  https://developers.google.com/youtube/v3/docs/videos/insert

- YouTube Data API: video resource and scheduling fields  
  https://developers.google.com/youtube/v3/docs/videos

- Cloudflare: TanStack Start on Workers  
  https://developers.cloudflare.com/workers/framework-guides/web-apps/tanstack-start/

---

# 21. Status boundary

This runbook makes the remaining process executable, but the following outcomes are not complete until you actually perform them:

- Human narrator approval
- Human approval of 20 scripts
- Kokoro execution
- Twenty final WAVs
- Twenty reviewed MP4 masters
- YouTube OAuth authorization
- YouTube upload and scheduling
- Returned live IDs
- Public playback confirmation
- Site synchronization
- Production deployment

Do not mark a phase complete based only on file presence. Use the gate and proof described in each section.
