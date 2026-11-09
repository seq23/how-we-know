# Whisper Almanac — master plan and how the lane works

**Current plan: 9 Nov 2026** (her rulings: "i want to reach monetization fastest", "build the neville lane", then Money and a rotating Shinn slot). The 6 Nov plan below it is kept for the how-it-works detail; its cadence is **Superseded**.

## The plan (9 Nov 2026)

**Goal:** YouTube monetisation as fast as possible: **1,000 subscribers + 4,000 watch hours** (12 months).

### Four lanes, per week, until monetised

| Lane | Per week | Length | What it is |
|---|---|---|---|
| **Neville** | 1 | 1 h | A guided whisper built on one Neville Goddard technique (whisper method / inner conversation, SATS, law of assumption, living in the end, revision, feeling is the secret, self-concept, bridge of incidents, imagination creates reality) |
| **Money** | 1 | 1 h | Affirmations in her whisper: billionaire, rich woman, manifest money while you sleep; steady/monthly income as lines inside them |
| **Rotating** | 1 | 1 h | In turn: Florence Scovel Shinn, specific person, Shinn, love, Shinn, self-concept |
| **History** | 2 (floor 1) | 2 h | Sleep science/history rewritten from fact-checked How We Know scripts |
| **Shorts** | none yet | — | **No Almanac Shorts path exists** (How We Know's Shorts cutter is not wired for the Almanac); a later build |

- **Where it lives:** `config/whisper_almanac.json` (`lanes`, `mix`, `teachings`, `affirmations.topics`), read by `loop/whisper_lane.py` (which script the Mac voices next) and `loop/whisper_author.py` (what gets written). No new job: the 23:00 batch and the Wednesday author.

### What the Mac can really make (measured, not guessed)

| Item | Measured / computed | Source |
|---|---|---|
| History episode, voice | **6.8 h** (407.5 min) for 49.5 spoken minutes = 8.2 Mac-min per spoken minute | batch log, night of 7 Nov 2026 |
| History episode, render | **2.7 h** (05:48 to 08:30) for a 1 h 43 min video | file times, 8 Nov |
| 1-hour manifesting video | about **3.3 h** (affirmations: 13 spoken min) to **4.6 h** (teaching: ~22 spoken min) of voice + render | computed from the two rows above |
| Almanac nights | 5 a week (5:2 split with How We Know); voice until 07:00, render after | `loop/night_split.py` |

- **Realistic weekly total: 5 videos (3 manifesting + 2 history)**, one per Almanac night, on a quiet Mac. Under load (20.4 Mac-min per spoken minute, measured 6 Nov) a history episode takes two nights: **4 a week**.
- The supply gate (no new video of a format while 14+ days of it wait) and the storage caps are unchanged.
- **Known blocker, 8 Nov:** the first finished history render failed the final frame check (FRAME_CHECK_FAILED, "no clearly visible animal subject" on dark frames); it is set aside, never uploaded. Nothing is public yet.

### How a video is made (0 steps for her)

1. **Script ($0 free models, Wednesday 14:00 CT):** history from fact-checked How We Know scripts; affirmations line by line; **teaching = a plain explanation in our own words → 2–4 of the teacher's own lines → a long guided section to fall asleep in the wish fulfilled**.
2. **Checks in code:** plain words, no promise, length, distinct; teaching adds the rights and straight-reading checks (`loop/teachings.py`).
3. **Voice:** her cloned whisper (Chatterbox) on the Mac, the lane furthest behind its weekly count first.
4. **Picture:** dim moving footage (history: its own subject; manifesting: the calm deep-sea set).
5. **Upload:** private with a 20:00 CT publish date (history Tue/Thu/Fri, Neville Mon, affirmations Wed/Sun, Shinn Sat), altered-content box ticked.

### Monetisation-safe rules (all in code)

- **Every script different:** an 8-word-run overlap check across all scripts; teaching scripts also differ in **structure** (one of 4 shapes × 12 scenes, never repeating a recent one).
- **Affirmations, never promises:** no amounts, dates, "will make you", "guaranteed", nothing another person will do, no health claims (risk brain ADV; R-ADV-05 no income claims). Titles never say "no ads" or promise anything.
- **Public-domain quotes only** (`config/teacher_rights.json`): Neville's books 1939–1961 checked against the US renewal records on 9 Nov 2026, none renewed; Shinn's 1925 and 1928 books are public domain (pre-1930 rule). *Resurrection* (1966), *The Power of Awareness* (later edition with new matter), his lectures and his voice are **never quoted**. Each quote must match a verified line word for word; the book's own text outside a quote is refused.
- **Credit, no endorsement:** "Techniques from the public-domain writings of Neville Goddard (1905–1972)" (or Shinn), the quoted books, and "Not affiliated with or endorsed by any estate, publisher or organisation."
- **Altered-content box** and the AI-voice line in the first 3 description lines, every upload.

### The 30-day check per lane, and the shift after monetisation

- **Every night** (`loop/whisper_scorecard.py`, in the upload step): the channel's own views, watch hours and subscribers per lane, last 30 days, into `loop/state/whisper_channel.json`. A number YouTube did not return reads "not read", never a guess.
- **Per lane, 30 days after its first public video:** views, watch hours, subscribers (`python loop/whisper_scorecard.py report`).
- **Data rule, no calendar:** the lane with the most watch hours per video (2+ measured videos, against another lane with 2+) takes one slot from the weakest; history never drops below 1.
- **Once monetised** (her channel reads 1,000+ subscribers and 4,000+ watch hours): the mix moves to **history 3 + money 2**; the watch-hour rule still applies.

### Description links

- **Money videos only**, one plain line, her own products, no affiliate framing: Billionaire High Performance Coach (billionairehighperformancecoach.com) and A Player Mode (aplayermode.com).

### What she does

- **Nothing per video.**
- **Once eligible:** apply for the YouTube Partner Program in YouTube Studio (her account).

---

_Below: the 6 Nov 2026 master plan (how the flow, the Mac, storage and uploads work)._

Written 6 Nov 2026 from measured facts (the plan page shown to the owner, in Markdown). The lane's rules, files and stops follow the plan.


Every number here is measured on 6 Nov or computed from a measurement; nothing is uploaded or published.

_Her rulings, 6 Nov_

- Lead lane: sleep science from How We Know's deep sea, food and materials topics; history second. **Superseded 9 Nov 2026** by the four lanes above.

- Dim, moving footage under the How We Know footage rules, never a dark screen.

- The scorecard counts subscribers per 1,000 views, checked at day 30, 60 and 90.

- Nights split 5 Almanac : 2 How We Know long-form; Shorts keep going; re-check 6 Dec 2026.

- No new video of a format while 14+ days of it wait to upload (12 Oct rule, now in code).

## Plan · 1. The flow, script to scheduled upload

Ongoing human steps per video: **0**. One-time steps: the sample, two Allow clicks, monetisation.

| Step | Where | Status | Human |
|---|---|---|---|
| Write the sleep script from fact-checked How We Know scripts ($0 free models) | GitHub Actions, Wed 14:00 CT | New, built | none |
| Plain-words, fact, length and distinct checks | code, every script | New, built | none |
| Whose night: 5 Almanac : 2 How We Know, supply gates first | her Mac, 23:00 batch | New, built | none |
| Voice in her cloned whisper (Chatterbox, $0) | her Mac, narrator lock | New, built | once: record the sample |
| Dim moving footage under the How We Know footage rules | her Mac | New, built | none |
| Title, description (AI line in the first 3), thumbnail, altered-content flag | code | New, built | none |
| Shelve to R2 under the free cap (Drive overflow) | her Mac | Built (shared with How We Know) | once: Drive Allow (safety net) |
| Upload and schedule, straight from the Mac (`loop/whisper_upload.py`) | her Mac, nightly batch step `whisper-upload` | Built 7 Nov 2026 | none (Allow clicked 7 Nov) |
| Measure, scorecard, weekly digest | GitHub Actions + Boss OS | Runs for How We Know; Almanac row added | none |
| Turn on monetisation when eligible | YouTube Studio | her account | once |

## Plan · 2. Her Mac (8 GB, one narrator at a time)

### Measured: Chatterbox on a real 5-minute sleep passage

- Passage: a 582-word sleep passage in the slow register (exaggeration 0.3, cfg 0.3), the How We Know test voice, never her sample; stopped after 91 words because the Mac was shared.

- Pace: **170 words a minute**, faster than a sleep pace, so every chunk is slowed to 0.82 (pitch kept) and long pauses are added in code: 139 words a minute, at no Mac cost.

- Compute: **20.4 minutes of Mac time per spoken minute under load** (load average 9.6 on 8 cores, other agents running). How We Know's own quiet-night measurement is **7.1** (71 minutes for a 10-minute episode); the batch runs alone at night.

### Projected for one episode

- A written episode is about 9,900 words, 1.0 h of speech plus about 0.9 h of pauses (pauses cost no Mac time).

- Voice time: **6.9 hours on a quiet night** (about 0.9 of a 23:00–07:00 night); 20 hours at today's loaded rate.

- Footage render: about 2.4 hours more (computed from How We Know's 12-minute render of a 10-minute video; not yet measured on a whisper reel).

- Weekly affirmations (1,900 words): about 1.3 hours of voice.

### Cadence the Mac can really sustain

- 5 Almanac nights a week, voice plus render: **at most about 4 sleep episodes a week** on quiet nights, plus the affirmation; about 1 a week at today's loaded rate.

- No fix is needed at a quiet-night pace: an episode is under one night of voice. If her own whisper voices slower, keep the 2–3 hour length with longer pauses (free) rather than more words, and never loops; the supply gate stops the Mac making more than 14 days of either channel.

- One narrator, always: the Almanac runs inside the How We Know batch's own lock; a food night on an Almanac day steps aside.

## Plan · 3. Storage

| Item | Measured or computed | Source |
|---|---|---|
| Free disk on the Mac | 11 GiB (after the prune and the review-folder delete) | df, 6 Nov, evening CT |
| How We Know renders/ and footage clips | footage clips 15 GiB; renders 8.4 GiB | du |
| Whisper audio per 2.25 h episode | about 0.35 GB of beat wavs (2 h 03 min, deleted after upload) | 24 kHz 16-bit mono wav beats |
| Whisper video per 2.25 h episode | about 0.9 GB (720p, capped at 900 kb/s) | 720p crf 27 + 96k mono AAC (estimate) |
| R2 bucket now | 9.99 GB of the free 10 GB (680 objects) | wrangler r2 bucket info |
| Google Drive free | 15 GB shared with Gmail and Photos | Google |

- **Finished files:** R2 shelf for upload (as How We Know), under a hard 9.5 GB cap of the free 10 GB.

- **At the cap:** delete R2 copies YouTube confirms are uploaded; then move the renders last in line to Drive (md5-verified, pulled back when next); then NAMED STOP [STORAGE_FREE_CAP]. Never billed.

- **Whisper masters never sit in R2 as-is:** they go from the Mac straight to YouTube in the Almanac upload step (`loop/whisper_upload.py`), so they never take R2 space. The render and its voice wavs are deleted only once YouTube reports the upload `processed`.

- **Local copies:** deleted only once YouTube confirms the upload and R2 holds the identical file; below a 6 GB floor no render starts (NAMED STOP [DISK_LOW]).

- **6 months:** bounded, not growing: uploaded masters are pruned, the supply gate caps the waiting shelf at 14 days per channel, and Whisper keeps at most two episodes on the Mac (about 2.5 GB). The one uncapped item is the footage pool (15 GiB today, 166 clips added on 2 Nov); it is the next storage guard to build.

## Plan · 4. Uploading

- **Quota:** one project, 10,000 units a day, shared. An upload is 1,600 + thumbnail 50. How We Know spent 4,474 units (5 Nov: Shorts 3,400, tags 765, captions 151, handoff 158) on its last measured day. Two Almanac uploads a week fit inside the daily reserve.

- **Audit:** measured 6 Nov: scheduled uploads from this OAuth project went public (3 of 3 checked: public, processed), so it is not locked to private. The Almanac reuses the same client.

- **Her one Allow click:** `.venv/bin/python auth/whisper_youtube_auth.py` on her Mac; pick Whisper Almanac on the channel screen. A grant for the wrong channel is refused and nothing is saved.

- **Altered content:** every upload body sets `status.containsSyntheticMedia = true`; the kit check fails without it, and without the AI-voice line in the first 3 description lines.

- **Publish time:** 20:00 Central, so it is live before bedtime in every US zone (21:00 Eastern, 18:00 Pacific); uploaded private with a publish date, as How We Know does. Sleep episodes on Tuesday and Friday, the affirmation on Sunday (`config/whisper_almanac.json` `upload`).

### The upload step (`loop/whisper_upload.py`, built 7 Nov 2026)

- **Where:** her Mac, every night in the batch (step `whisper-upload`, after the whisper step). It uses no narrator, so the 5:2 night split is unchanged.
- **Only a checked episode:** every lane check again (script rules, kit rules, a measured length), then the final frame check on the finished file (`visuals/frame_check.py`, one frame every 20 s). No credit is burned into the picture (the frame check fails any word on screen); every footage source is credited in the description.
- **Private with a publish date:** the publishAt rides in the upload body itself, with altered content = yes and made for kids = no, so no second status write can reset them. The kit's title, description, chapters and tags go up unchanged.
- **Supply gate:** no new upload of a format while 14+ days of it already wait on YouTube (a green HOLD; the render waits on the Mac).
- **Confirmed before anything is deleted:** the upload is recorded once YouTube lists the id with processing started; the local files go on a later night, once it reads `processed`.
- **Named stops:** WHISPER_YT_TOKEN_INVALID (owner action: her sign-in), UPLOAD_QUOTA (resets by itself), FRAME_CHECK_FAILED (red; the file is set aside, never deleted). Each is in loop/state/stops (the Sunday digest) and puts one line in her morning email's Notices.

## Plan · 5. Videos per week

> **Superseded 9 Nov 2026:** the 6 Nov cadence (2 sleep-science episodes + 1 affirmation a week) is replaced by the four lanes at the top of this page.

- **Recommended: 2 sleep-science episodes and 1 affirmation a week to start; 3 sleep a week from day 30 if day-30 views pass.**

- **Why:** the leaders upload about 3 long videos a week; 2 fits inside the Mac's 5 Almanac nights with margin for renders, and the supply gate holds it to 14 days of shelf. Volume alone does not break out (500-video channels with ~53K subscribers), so titles and the day-30 check come first.

- **Day 30 (6 Dec):** median 150+ views per long episode in its first 14 days, else version B (new titles and thumbnails).

- **Day 60 (5 Jan 2027):** 100+ subscribers and a 300+ view median in 28 days, else switch the lead topic or 60–90 minute episodes.

- **Day 90 (4 Feb 2027):** under 400 subscribers pauses new long episodes (never deletes), keeps 1 affirmation a week.

- Subscribers per 1,000 views is reported beside every check (Boss OS row whisper-almanac-youtube).

## Plan · 6. Monitoring

- **Every step prints an OUTPUT line or a NAMED STOP**; a stop is recorded in loop/state/stops and filed as a GitHub issue when it needs a person.

- **Waiting on you:** WHISPER_SAMPLE_MISSING is green and sits at the top of the Sunday digest with the exact place to save the file.

- **Notes, never red:** a supply-gate HOLD, an Almanac night that falls back to How We Know, Drive not yet consented.

- **Weekly:** the Sunday digest and the Boss OS scorecard (subscribers per 1,000 views, day 30/60/90).

## Plan · 7. Risks

- **Demonetisation for "inauthentic" or reused content:** every video is a distinct script (an 8-word-run overlap check fails a copy), moving footage with a new shot every 20 s, no loops.

- **Reused content:** the footage is public-domain or free-licence, credited on screen; the words are new rewrites of our own fact-checked scripts.

- **AI disclosure:** the altered-content flag and the AI-voice line on every upload; checked in code before a kit is valid.

- **No reach:** the money case's base case is small (about $200–250 a month by month 12); the day 30/60/90 checks decide, not hope.

- **A whisper the clone cannot hold:** judged on the first voiced minutes; the fallback is her recording real whispers, never a paid voice.

