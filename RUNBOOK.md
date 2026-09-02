# RUNBOOK

**Say "runbook howweknow" and this is the page.** Everything you personally have to do for
How We Know, and nothing else. Reference detail lives in
[`docs/OPERATING-MANUAL.md`](docs/OPERATING-MANUAL.md); the locked strategy lives
in [`docs/CHANNEL-PLAN.md`](docs/CHANNEL-PLAN.md).

Last true: 2026-09-02.

---

## The whole loop, plainly

```
1.  Cloud writes scripts every Monday                     you: nothing
2.  Runway drops under 4 weeks -> GitHub emails you       you: read the email
3.  You open the Mac and run ONE command                  you: 10 seconds
4.  It narrates and renders, unattended                   you: walk away
5.  Cloud uploads, schedules and publishes                you: nothing
```

**Step 3 is one command:**

```bash
cd ~/GitHub/how-we-know
bin/batch-session.sh
```

That is the only step you are in. Steps 1, 2 and 5 happen whether your laptop is
open, shut, or switched off.

---

## Step 3, in detail

Start it and walk away. What it does:

- It narrates every script that has no audio, renders every episode that has
  audio but no video, and pushes the results out for uploading.
- **~1.2 hours narration + ~12 minutes render per episode.** A full 16-episode
  batch is about **22 hours** — one overnight plus a morning.
- It holds the Mac awake itself (`caffeinate -dimsu`). You do not have to sit here.
- It **skips whatever is already done**, so an interrupted run is re-run, not
  restarted. Closing the lid is survivable; just run it again.
- Preview first if you want: `bin/batch-session.sh --dry-run`

When it finishes it prints `V13 ... CLEAN`. That means no video ends before its
own narration does. If it prints failures, tell Claude — do not upload.

### When the email arrives you still have ~8 episodes airing

The warning fires at **four weeks of runway**, not at zero, so the channel keeps
publishing right through the batch. There is no rush and no gap.

---

## Shorts run themselves

**48 Shorts, 12 weeks of runway, no approval step.** All three ranked chapters
per episode publish automatically at 4/week in the evening slot. You do not
review them.

If you ever spot a bad one, that is the only manual lever:

```bash
.venv/bin/python loop/shorts_approval.py reject <file.mp4>
```

That keeps it off the channel permanently. Nothing needs approving for Shorts to
publish — the veto is the exception, not the workflow.

---

## Everything else happens without you

| | |
|---|---|
| Choosing topics, writing scripts | GitHub, weekly |
| Uploading, scheduling, thumbnails | GitHub *(migrating from the Mac now)* |
| Cutting Shorts | GitHub *(migrating from the Mac now)* |
| Publishing on the day | **YouTube itself** |
| Captions + translated titles | GitHub, daily *(new — see below)* |
| Measuring, monthly review + advice email | GitHub, weekly / monthly |

**Videos already uploaded and dated air on their own.** Your laptop can be shut
for a month and everything scheduled still goes out.

### What is on the Mac right now

One timer: `com.howweknow.backfill`, daily 09:00, uploading the last few of the
original 16. It **stops by itself** when they are done.

Check any time:

```bash
launchctl list | grep howweknow          # what is scheduled on this Mac
bin/batch-session.sh --dry-run           # is there work for me?
```

---

## Reaching people who do not speak English — nothing for you to do

Added 2026-09-02. Two lanes run after a video is up, both free apart from API
quota:

- **The English subtitle file goes to YouTube.** It was always sitting in
  `captions/`, burned into the picture but never uploaded, so YouTube could not
  read it. It matters more than "some viewers turn subtitles on": Studio says
  *"English subtitles are the default source for auto-translation of subtitles
  and audio."* No track meant no auto-translated subtitles and no auto-dubbed
  audio, in any language.
- **The title and description are rewritten in Spanish, Brazilian Portuguese,
  Hindi, Indonesian and German** — as the phrase someone would really type into
  YouTube, not a word-for-word translation. That is what makes an episode
  findable outside English at all.

Both are aimed at one thing: **long-form watch hours before the Partner
Programme threshold doubles from 4,000 to 8,000 on 2026-02-01.**

If you ever want to run them by hand:

```bash
.venv/bin/python loop/captions_lane.py     # upload the subtitle files
.venv/bin/python loop/localize.py          # translated titles + descriptions
```

Both are safe to re-run: they skip everything already done and cost nothing on
a second run.

---

## The publishing rhythm

- **Long-form: Sunday and Tuesday, 10:00 Central.** Pinned in local time, so it
  does not drift when the clocks change.
- **Shorts: 18:00–21:00 local, ~4 a week.** Nearly the inverse window — Shorts
  peak in the evening, long-form in the morning.
- **Shorts do not count toward monetisation.** YouTube's 4,000 watch hours come
  from long-form only. Shorts exist to be found; episodes exist to be watched.

---

## If something looks wrong

- **A video published at the wrong time** — check `loop/state/ledger.json` for its
  `scheduled_publish_at`, then the video in YouTube Studio. The two must agree.
- **A workflow emailed you a failure** — that is the system working. Named stops
  are how it asks for help; each one says what to do in its `unblock:` line.
- **Nothing published when it should have** — check the video is `SCHEDULED` and
  not `private only` in Studio. Private-with-a-date is scheduled; private
  without one never airs.
- **You want a video taken down** — never delete it:
  ```bash
  .venv/bin/python loop/retire.py --slug <slug> --reason "..."
  ```
  It sets the video private, verifies YouTube applied it, and keeps the record so
  the loop does not re-queue it. There is deliberately no delete path.

---

## Things that are true and easy to forget

- **Claude is not part of the running system.** Nothing calls a model to decide
  whether to publish. Close the terminal and the channel keeps going.
- **"Agent" here means a macOS timer**, not an AI. Three were removed on
  2026-09-01; one remains.
- **Upload day is not publish day.** A video can be uploaded weeks before it airs.
- **Uploading straight to public would not work, and would not say so.** The
  Google Cloud app is *in production but not verified*, and YouTube forces
  every upload from an unverified app to PRIVATE. That is exactly why the loop
  uploads private and flips public later against a receipt. It is a
  requirement, not a preference — anyone who "simplifies" it by uploading
  public will find YouTube quietly ignoring them. *(Checked in the Cloud
  console 2026-09-02.)*
- **Three episodes have no footage and never will** — colossal squid, whale fall,
  and surviving pressure. No public-domain video of them exists. They stay
  illustrated rather than mislabelled.
