# RUNBOOK

**Say "runbook howweknow" and this is the page.** Everything you personally have to do for
How We Know, and nothing else. Reference detail lives in
[`docs/OPERATING-MANUAL.md`](docs/OPERATING-MANUAL.md); the locked strategy lives
in [`docs/CHANNEL-PLAN.md`](docs/CHANNEL-PLAN.md).

Last true: 2026-09-23.

---

## The whole loop, plainly

```
0.  Cloud scores/refills the queue every Saturday          you: nothing
1.  Cloud writes scripts every Monday                       you: nothing
2.  The Mac narrates and renders every night, unattended    you: nothing
3.  Cloud uploads, schedules and publishes                  you: nothing
```

**Nothing here is a step you take.** `com.howweknow.batch`
(`~/Library/LaunchAgents/com.howweknow.batch.plist`) fires on this Mac every
night at **23:00** and runs `bin/batch-session.sh` itself — narrates whatever
has no audio, renders whatever has audio but no video, and pushes the results
to R2 for the cloud to upload. This changed on 2026-09-04, when materials
became a second domain and the batch first needed to run unattended overnight
rather than whenever she happened to start it; before that date step 2 really
was a command she ran. As of this writing (2026-09-23) it is loaded, valid
(`plutil -lint` on both installed plists passes) and running: last night's
`batch.log` shows it fired at 23:00 and completed its pass.

**All you have to do is leave the Mac open at night, plugged in.** A launchd
*Agent* (not a daemon) only fires while a user session is logged in — asleep or
shut down, it does not run. This Mac's `pmset` sleep timer is already set to
`0` on both AC and battery, so it stays awake as long as the lid is open; a
*closed* lid still sleeps it regardless of that setting. If the lid is closed
at 23:00, the batch simply skips that night — nothing breaks, nothing is
lost, and `bin/batch-session.sh` resumes wherever it left off the next time it
gets to run, because it is resumable by construction.

You can still run it by hand any time — to catch up after a few closed-lid
nights, to preview what it would do, or to render a specific week early:

```bash
cd ~/GitHub/how-we-know
bin/batch-session.sh                 # same thing the 23:00 timer runs
bin/batch-session.sh --dry-run       # preview: is there work for me?
bin/batch-session.sh --max-episodes 4   # just this week, not the whole queue
```

Step 1 draws from whatever Saturday's scoring pass (step 0) ranked. If a
domain's queue ever runs fully dry, step 0 is also what refills it — see "A
domain's scored queue running completely dry" below.

---

## The nightly batch, in detail

What the 23:00 timer (or a by-hand run) does:

- It narrates every script that has no audio, renders every episode that has
  audio but no video, and pushes the results out for uploading.
- **~1.2 hours narration + ~12 minutes render per episode.** A full 16-episode
  batch is about **22 hours** — spread automatically across as many nights as
  it takes, since it is resumable and simply picks up where it left off.
- It holds the Mac awake itself (`caffeinate -dimsu`) for the run, and stops
  needing it once it is done for the night.
- It **skips whatever is already done**, so an interrupted run is re-run, not
  restarted. A closed lid one night is survivable; it just continues the next.

When it finishes it prints `V13 ... CLEAN`. That means no video ends before its
own narration does. If it prints failures, tell Claude — do not upload.

### If a runway-warning email ever arrives, it means the nightly batch has fallen behind

The warning fires at **four weeks of runway**, not at zero, so the channel keeps
publishing right through it — there is no rush and no gap. But since rendering
is automatic every night, this email should be rare: it means several nights
in a row the Mac was asleep, shut, or the batch is failing. Check
`launchctl list | grep howweknow` and `tail ~/Library/Logs/how-we-know/batch.err`
first; running `bin/batch-session.sh` by hand catches it up regardless of cause.

---

## Shorts run themselves

**51 Shorts cut, no approval step.** All three ranked chapters per episode
publish automatically in the evening slot. You do not review them.

**They now go out at 9 a week, not 4** (your decision, 2 September). That is
about **five to six weeks of runway** rather than twelve. When the cut ones run
out you get one email — `SHORTS_INVENTORY_EXHAUSTED` — asking you to choose
between cutting more chapters from the existing episodes and moving Shorts to a
proper vertical format. **Nothing switches format on its own**, deliberately:
the 51 already cut are in the current format and re-cutting them would throw
away work you have already paid for.

If you ever spot a bad one, that is the only manual lever:

```bash
.venv/bin/python loop/shorts_approval.py reject <file.mp4>
```

That keeps it off the channel permanently. Nothing needs approving for Shorts to
publish — the veto is the exception, not the workflow.

---

## You should never get a "named stop" email again

Changed 2026-09-08, on your instruction. A named stop used to arrive as a **red
build in your inbox**, whatever it was about. Some of those were worth sending
and most were not — the worst one asked you to open the laptop and type a
command to produce a file the server was already holding every ingredient for.

Every halt this system can take has now been walked and given one of three
answers.

| | What happens | You see |
|---|---|---|
| **It can fix itself** | It does, and the lane carries on | nothing |
| **Only you can fix it** | The run stays **green** | one line at the top of the Sunday email, under **⚠️ Waiting on you** |
| **Something is actually broken** | The run goes red | an email, as before |

Two things follow from that and both are deliberate:

- **A green run is not a silent run.** Anything waiting on you is written down
  and repeated in every Sunday digest until it is cleared.
- **It goes red eventually anyway.** If a "waiting on you" item is still there
  after a few runs — five days for a credential, three for a locked channel —
  it stops being an errand and becomes a stall, and then it does email you.

**What is genuinely yours, and nothing else is:** a YouTube consent that has
expired or been revoked, a channel-level flag from YouTube itself, an API key
with no credit, and the one-off `gh workflow run` that arms a brand-new lane.
That is the whole list.

### What now fixes itself, that did not before

- **Captions.** Every episode's subtitle file is built automatically, in the
  cloud, from what is already in the repository — no laptop involved. The
  batch you run also builds them for anything it narrates, in the same pass.
- **Thumbnails.** A finished episode without one used to be invisible to the
  uploader forever. Any render missing a thumbnail now gets one.
- **The producer POV beat.** Where a script's first-person line was written by
  the model rather than taken from your own interviews, it is swapped for a
  real line from your bank and the episode is rebuilt. Nothing is ever added to
  that bank without you — matching is automatic, approving is not.
- **The circuit breaker.** It re-tests its own cause and closes as soon as the
  cause has passed. It also stops reporting one problem four times.
- **A corrupted internal file.** Restored from the last good copy, silently.
- **A domain's scored queue running completely dry** — every stage of
  `research/publish_order*.json` empty for that domain, not just thin. This is
  worse than the runway warning below (which means "scripts exist, nothing is
  rendered yet") and worse than `CADENCE_SCALE_WITHHELD` (which means "not
  enough runway to raise the rate") — total exhaustion means there is nothing
  queued at any stage for that domain, so `bin/batch-session.sh` has nothing to
  act on even if you run it. `loop/score.py:score_new_domains()`, added
  2026-09-17, fixes this on its own every Saturday: it mines real
  YouTube-autocomplete candidates for any allocated domain with zero queue
  depth and scores them through the same gate every other topic goes through —
  no shortcut for being empty. Since 2026-09-25 it also refills a domain
  whose queue is merely THIN — fewer than 4 unwritten topics that are not
  repeats of episodes already aired — and keeps widening its sources until
  it clears 4, or names `DOMAIN_QUEUE_THIN` (green, three Saturdays before
  it goes red). It retries automatically for up to three
  Saturdays on a quota stop (`NEW_DOMAIN_QUOTA`) before it becomes your
  problem; see "If a domain's queue can't refill itself" below.

### If a domain's queue can't refill itself

`score_new_domains()` retries a stuck domain for up to **three consecutive
Saturdays** (`loop/stop_policy.json`, `NEW_DOMAIN_QUOTA.max_consecutive`) —
green every time, nothing in your inbox, because a YouTube Data API quota stop
is a normal outcome, not a defect (search costs 100 of the 10,000 free daily
units, and this pass can legitimately run out). If the **same code** stops it
a **fourth** week in a row, `loop/common.py:disposition()` escalates it to a
red build and it finally does reach you: the target is too large to mine
within one Saturday's quota, and the fix named in that email is to run
`research/publish_order_domain.py --domain <name>` by hand with a lower
`--budget`, spreading the mine over two weeks instead of one.

**Re-checked 2026-09-23** — still mid-cycle, not stuck, and unchanged since
the 22 Sep audit: the current streak (`loop/state/stops/_streaks.json`) is
`weekly-score` stopping on `NEW_DOMAIN_QUOTA` for `deep-sea-ocean-science`
twice within ISO week 2026-W38 — a `workflow_dispatch` run on **2026-09-18
23:44 UTC** and the scheduled run on **2026-09-19 10:09 UTC** (count 2 of the
3 allowed). An earlier, separate occurrence on 2026-09-12 (`2026-W37`,
consecutive 1 at the time) does not count toward this streak; something
between the two — most likely the 2026-09-17 `sweep/score-refresh-before-
domain-gate` dispatch — ran clean and reset it, which is exactly how a
self-resolving stop is supposed to behave. Nothing has run since 2026-09-19
10:09; the next Saturday run (2026-09-26) is attempt 3 of 3, still green
either way. **One correction to how this looked in the 22 Sep audit:** the
2026-09-19 stop's own recorded tail is a Python `KeyError: 'median_subscribers'`
in `research/publish_order.py`, not an actual 403/quota response from YouTube —
it was classified as `NEW_DOMAIN_QUOTA` because `loop/score.py`'s
`QUOTA_MARKERS` regex matched the word "quota" somewhere else in that run's
combined output, the same false-positive class the code's own comments warn
about for `KEY_ABSENT_MARKERS`. That means the real cause may not clear on
its own the way a genuine quota reset would — worth a look if `weekly-score`
is still stopping on this after 2026-09-26.

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

### If the Mac is holding something back

**One bad episode no longer stops the others.** A render that fails its check —
too short, or clipped — is **held by name** and everything else still uploads.
The short one heals itself (more sourced narration, re-voiced, re-rendered on
the next batch). You see it as one line in the Sunday email:
`RENDER_HELD: why-is-steel-so-strong — 9.90 min, under the floor`. Nothing for
you to do unless the same line is still there a week later.

**The Mac now reports in.** If it has finished episodes and has not shipped
any for three days, the Sunday email says `MAC_NOT_SHIPPING` and names why.
Before 13 September that silence reached nobody.

### What is on the Mac right now

Two timers, both `launchctl`-loaded and `plutil -lint`-valid as of 2026-09-23:

| Agent | When | What it does |
|---|---|---|
| `com.howweknow.batch` | **daily 23:00** | `bin/batch-session.sh` — narrates, renders, shelves to R2. This is step 2 of "The whole loop, plainly" above; see "The nightly batch, in detail". |
| `com.howweknow.backfill` | daily 09:00 | Uploads the last few of the original 16 pre-cloud-upload episodes. It **stops by itself** when they are done; it does not narrate or render. |

Check any time:

```bash
launchctl list | grep howweknow          # what is scheduled on this Mac
bin/batch-session.sh --dry-run           # is there work for me?
tail ~/Library/Logs/how-we-know/batch.log    # did last night's run finish?
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
Programme threshold doubles from 4,000 to 8,000 on 2027-02-01.** (Corrected
2026-09-03 — this page said 2026-02-01, a year early; that date has already
passed and nothing changed, which is itself proof it was a typo, not a real
deadline.) Channels admitted before that date keep the 4,000-hour bar. See
"Monetisation, both gates" below for the nearer one.

A third lane, added 2026-09-21, keeps every video's tags and hashtags derived
from its own domain rather than one fixed list — a materials episode no
longer carries "marine biology". Nothing for you to do; it runs daily and
self-heals a future drift on its own.

If you ever want to run them by hand:

```bash
.venv/bin/python loop/captions_lane.py     # upload the subtitle files
.venv/bin/python loop/localize.py          # translated titles + descriptions
.venv/bin/python loop/tags_backfill.py     # derived tags + hashtags
```

All three are safe to re-run: they skip everything already done and cost
nothing on a second run.

---

## The publishing rhythm

- **Long-form: Sunday, Monday, Tuesday and Friday, 10:00 Central.** Pinned in
  local time, so it does not drift when the clocks change. Sunday and Tuesday
  are deep sea; Monday and Friday are materials-and-manufacturing, live since
  2026-09-07 — see "A second domain" below.
- **Shorts: 18:00–21:00 local, 9 a week.** 19:00 every evening, plus a second
  at 21:00 on Saturday and Sunday. Nearly the inverse window — Shorts peak in
  the evening, long-form in the morning.
- **Shorts do not count toward monetisation.** YouTube's 4,000 watch hours come
  from long-form only. Shorts exist to be found; episodes exist to be watched.

---

## The step up to 4 a week, and when it happens

You raised the cadence to **4 long-form and 9 Shorts a week** on 2 September.
Two things are worth knowing and nothing here needs doing.

- **Nothing already scheduled moves.** Fourteen episodes are uploaded, dated and
  airing through **20 October**. The loop only ever hands out dates *after* the
  last one on the calendar, so the first 4-a-week slot is **Friday 23 October** —
  no gap, no double post, nothing re-dated.
- **It starts itself, when the queue can carry it.** There is no date to
  remember and no switch to flip. The loop goes to 4 a week once it has enough
  finished episodes in hand to keep publishing at that rate for a month. Until
  then it keeps publishing at the lower rate and emails you once, saying so.

If you get an email titled **CADENCE_SCALE_WITHHELD**, that is the loop telling
you it is holding at the lower rate because there are not yet enough *finished*
episodes, only scripts. Nothing is broken and nothing has stopped — the same
nightly `com.howweknow.batch` run above closes this on its own as soon as it
renders enough of the backlog. There is nothing to run by hand; if you want to
speed it up, the same batch command works a week at a time:

```bash
bin/batch-session.sh --max-episodes 4
```

**Rendering is faster now regardless:** it overlaps with narration rather than
waiting for it to finish, so a full batch is about 19 hours instead of 22.

## A second domain, on top of deep sea

Added 2026-09-03, live since 2026-09-07. **Materials-and-manufacturing runs ON
TOP of deep sea, not instead of it** — deep sea keeps Sunday and Tuesday,
materials takes Monday and Friday. Nothing for you to do; the loop decides the
split monthly and writes its reasoning to `loop/state/monthly/<month>.md`.

- **Why a second domain at all.** `research/proposed-taxonomy.json` scored 20
  candidate domains; materials ranks lower on demand than deep sea but has
  roughly 4x the commercial-intent share (`research/commercial.json`) — the
  honest trade is **about 3x slower subscriber acquisition** than deep sea in
  exchange for a category advertisers pay more to reach.
- **Each domain needs its own source allowlist and visual identity.** Deep
  sea's approved organisations (NOAA, MBARI, Woods Hole, ...) publish nothing
  about materials science; a new domain names its own public bodies before it
  can cite anything, and gets its own palette so a materials episode does not
  read as the wrong channel.
- **The loop will not scale to 4/week on an empty second queue.** If materials
  has no scored topics yet, the ceiling holds at whatever deep sea alone can
  carry — it will not "average" the two domains' inventory together and scale
  early on a queue that is not really there.
- **A domain retires on its own queue running dry**, never on a fixed episode
  count, and the next-ranked domain in the taxonomy takes its slots
  automatically.

## Monetisation, both gates

There are two Partner Programme tiers, not one, and the loop now tracks both
— nearest first:

| | subscribers | long-form hours | unlocks |
|---|---|---|---|
| Expanded YPP | 500 | 3,000 | fan funding (memberships, Super Thanks) — no ads |
| Standard YPP | 1,000 | 4,000 → **8,000 on 2027-02-01** | ads, plus everything Expanded unlocks |

Expanded is the nearer gate — half the subscribers, three-quarters of the
hours — and channels admitted before 2027-02-01 keep the lower 4,000-hour
Standard bar for good. **3,000,000 Shorts views in 90 days is a SEPARATE path
to either tier — Shorts views never add into the long-form hours total.**
`loop/ypp.py` reports progress against both tiers and both routes every
monthly review, nearest gate first.

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
- **Every video from 2026-09-03 on has a hard 10-minute floor**, checked
  against the RENDERED file, not just the word count. The first 20 episodes
  predate the rule and run 7.5–8.9 minutes; they are deliberately not
  re-rendered — they're already made, and re-rendering wastes money. Six of
  them are under 8:00 (no mid-rolls run under 8:00 at all): episodes 01, 02,
  04, 05, 14 and 16. Five of the six are already uploaded and dated; that is
  not being changed either.
- **Chapters come from the timed caption file, not the script.** The script's
  own `## Chapters` timestamps are an estimate and drift from the real render
  by anywhere from 2 to 58 seconds; `loop/upload.py` now reads
  `captions/<slug>.chapters.txt` when it exists, which is the same file
  `visuals/captions.py` derives from the actual audio timing.
- **The "What to notice in the edit" narration talks to you, not about the
  channel.** It used to describe production strategy in the third person
  (engagement, monetisation, the pinned comment) — the same transparency is
  still there, rewritten to address the viewer directly.
- **The `## Direct-answer lock` in a script is never spoken.** It feeds the
  description's first line, the thumbnail brief and the Shorts scorer —
  `## Narration` is the only section a viewer ever hears.
