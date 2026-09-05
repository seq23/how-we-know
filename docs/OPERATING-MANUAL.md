# How We Know — Operating Manual

**Companion to `docs/CHANNEL-PLAN.md`.** The plan says what the channel *is*;
this says how fast it runs, at what times, and what happens without a human.
Guarded facts (cadence, publish source, the pinned-head rule) live in the plan
and are enforced by `loop/validate_plan.py`. This document holds the schedule and
the evidence behind it.

Compiled 2026-09-01. Every figure was read from the repository, the YouTube API,
or a cited study. None are estimates.

**If you are sitting down to do work, you want [`RUNBOOK.md`](../RUNBOOK.md),
not this file.** That page is the one command you run and nothing else. This is
the reference behind it.

Rendered version: https://claude.ai/code/artifact/d441bc8d-478d-4305-b002-2ef3925ca934

---

## 0. Words this document uses precisely

Three different things schedule work, and only two of them are automatic. The
vocabulary matters because two of them are commonly confused.

| Term | What it is | Where it runs | How many |
|---|---|---|---|
| **launchd agent** | a macOS scheduled job, the Mac's equivalent of cron | **this Mac** | **0** |
| **cloud lane** | a GitHub Actions workflow | **GitHub's servers** | 7 |
| **Claude** | an assistant, run by a person having a conversation | nowhere, unattended | 0 |

**Claude is not part of the running system.** Nothing in the loop calls a model
to decide whether to publish, and nothing waits for a person to be at a
keyboard. The one place a language model appears is the monthly review, where it
is asked for an opinion and its answer is applied through a fence
(§3, "The advisory fence"). If nobody ever opens a terminal again, the channel
keeps publishing.

The word *agent* is used in this repository **only** for a launchd job. It does
not mean an AI agent.

### Upload day and publish day are different days

This is the single most confusable thing in the schedule.

- **Publish days are Sunday, Monday, Tuesday and Friday, 10:00 Central.** That
  is when a video becomes visible. **Deep sea publishes Sunday and Tuesday;
  materials-and-manufacturing publishes Monday and Friday.** Each domain has
  its own days and they never overlap, which is what lets a second domain be
  woven into weeks the first has already filled without moving anything: at
  2/week the ladder was exactly Sunday and Tuesday, and raising to 4/week
  ADDED Monday and Friday rather than redistributing the existing days.
- **Upload happens daily and is not a publish day.** The finished video is
  pushed to YouTube **private**, with a `publishAt` stamp and its thumbnail
  attached, and then sits there.

A video uploaded today may not appear for another six weeks. YouTube surfaces it
on its stamped date; no script wakes up to do it.

    Mon 10:00   draft the next script            cloud lane
    by hand     render it, then push-to-r2.sh    Mac, in batches
    daily 14:00 upload private + stamp the date  cloud lane, from R2
        |
        +-----> Sun / Tue 10:00 Central: YouTube publishes it, unattended

Separating the two is what makes the cadence survivable: uploads can happen
whenever the quota and the render pipeline allow, while releases stay on the two
days the evidence in §2 selected.


---

## 1. Launch

**Episode 10, "What is the deepest part of the ocean?", went public on Tuesday
1 September 2026** — video id `sfveDF88ZHo`. It is the channel's first published
video and the start of the schedule below.

Two honest notes about it:

- **It published at 07:30 Central (12:30 UTC), not the 10:00 Central slot** —
  two and a half hours before the intended window. It was a manual replacement
  upload, not a scheduled one: the original upload (`qBeLl0z4s54`)
  had 0.098s of its final word clipped by a frame-quantisation bug, so it was
  re-rendered and re-uploaded the same day. Every video after it is scheduled
  through `publishAt` and lands exactly on the slot.
- **The original was RETIRED, not deleted** — set private via `loop/retire.py`.
  Owner policy, 2026-08-31: *"we dont have to delete any videos ever. we can just
  private them as a default for ones we no longer want published."* There is
  deliberately no delete path in this repository.

Tuesday is one of the two chosen publish days, so the launch day is on-pattern
even though the launch hour was not.

---

## 2. The four cadence decisions

| Decision | Answer | Evidence |
|---|---|---|
| **Long-form frequency** | **4 per week** (raised from 2, owner decision 2026-09-02) | Channels posting 1–3×/week get better per-video views than daily uploaders, so this is deliberately at the top of the band and capped there by the taxonomy ceiling. |
| **Shorts frequency** | **9 per week** (raised from 4; the owner's band is 8–10) | Creators running both formats grow subscribers ~3× faster than single-format channels — and subscribers are the binding constraint, see below. |
| **Long-form time** | **Sunday, Monday, Tuesday & Friday, 10:00 America/Chicago** | Long-form peaks 08:00–11:00 local. Sunday is the strongest day, then Tuesday and Monday; Wednesday and Thursday underperform and the ladder never reaches them. |
| **Shorts time** | **18:00–21:00 local**, 19:00 daily plus a second 21:00 slot on Saturday and Sunday | Shorts peak in the evening — very nearly the inverse of long-form. A Short posted on the episode slot lands in the worst part of its own day. |

Together that is roughly **56 pieces a month**, well inside the 12+/month tier
that grows views ~8× faster — reached by *combining formats*, not by pushing
long-form past what its quality can sustain.

### Why the raise, honestly

**Watch hours are not what blocks monetisation. Subscribers are, by roughly 12×.**
On the measured trajectory this channel clears 4,000 hours (the Standard tier's
bar — 8,000 after 2027-02-01 for a channel not yet admitted) with under 100
subscribers against a 1,000 floor. The nearer gate, Expanded YPP (500
subscribers, 3,000 hours, fan funding without ads), clears its hours target
sooner still and is bound by the same subscriber shortfall. See `loop/ypp.py`
and RUNBOOK.md's "Monetisation, both gates". Two things follow, and the second
matters more than the first:

- **More long-form buys hours she would clear anyway.** It is still worth doing —
  an authored script costs about **$0.06** at the median, so the marginal episode
  is close to free, and runtime multiplies watch hours directly. But it is **not
  the binding lever**, and nothing here should imply otherwise.
- **Shorts are the only cheap lever on subscribers**, and 51 are already cut and
  unpublished — inventory already paid for. **The Shorts half of this decision is
  the half that moves the constraint that actually binds.**

### The activation gate: no date, and nobody has to remember it

Fourteen episodes are uploaded, private and dated, running gaplessly to
**2026-10-20**. They publish exactly as scheduled, and the higher cadence cannot
reach them — not because someone waits until 20 October to flip a flag, but
because of two mechanisms that make it structurally impossible:

1. **The slot allocator only ever hands out dates after the end of the existing
   run.** `backfill.schedule_for` anchors on the last date already on the
   calendar and `slots()` returns only times strictly after it. No lane rewrites
   a row that already carries a `scheduled_publish_at`. At 4/week the first new
   slot is **Friday 23 October 2026** — the day after the existing run ends, so
   the change is gapless as well as harmless.
2. **The 2/week ladder is Sunday and Tuesday and the 4/week ladder starts with
   the same two days.** The days a cadence uses are the first N rungs of an
   evidence-ordered ladder (Sunday, Tuesday, Monday, Friday), so raising the
   cadence adds days rather than moving any.

`validate.v20_cadence_schedule` re-derives the schedule against the live ledger
on every render-gate run and fails if a single date it hands out collides with,
precedes, or duplicates one already scheduled.

### The queue-depth guard: what makes this reversible

**The loop refuses to raise its own cadence when the queue cannot carry it.**
`cadence.queue_supports(n)` measures runway *at the raised rate* — the publish
queue plus everything uploaded and dated but not yet aired — and the raise only
happens when that is still clear of `cadence.scale.requires_runway_weeks`
(4 weeks, the same threshold the runway email uses). Raising cadence shortens
runway; raising into a runway that would immediately warn is how a channel goes
dark, and **breaking cadence reliability costs more than the extra episodes
earn.**

The refusal is not silent. `loop/rank.py` raises a **`CADENCE_SCALE_WITHHELD`**
named stop — an issue and an email — saying the target is 4/week, what the loop
is holding at, and why. Publishing continues at the lower cadence throughout;
nothing goes dark, and the raise re-arms itself the moment the queue can carry
it. It also stands down on its own if the queue thins again, which is what makes
this reversible rather than a one-way risk.

Both halves of the gate must hold: the authoring lane must have produced a
validated script (the existing evidence gate), **and** the queue must be deep
enough. Neither is a date and neither is a flag.

### Why 10:00 Central specifically

10:00 Central is **08:00 Pacific / 10:00 Central / 11:00 Eastern** — the only
hour that sits inside the 08:00–11:00 long-form window in all three mainland US
zones at once.

**The slot is pinned in LOCAL time, not UTC**, in `loop/backfill.py`
(`PUBLISH_HOUR_LOCAL`, `PUBLISH_TZ`, `PUBLISH_WEEKDAY_LADDER`). A fixed UTC hour is
only correct until the clocks change: 15:00 UTC is 10:00 Central during CDT and
09:00 during CST, so from **1 November 2026** every slot would have slid an hour
earlier and put the Pacific coast at 07:00, outside the window the schedule
exists to hit. The audience lives in local time, so the schedule does too — the
UTC stamp moves (15:00 → 16:00) and the local hour stays put.

### The fact that decides the Shorts ratio

**Shorts watch time does not count toward the long-form watch-hours gate.** Standard
YPP requires 1,000 subscribers *and* 4,000 long-form watch hours (Expanded needs
only 500 and 3,000 — see RUNBOOK.md's "Monetisation, both gates"), and only
long-form watch time counts toward either hours figure. Shorts get roughly 10×
the views and contribute nothing to that half. **3,000,000 Shorts views in 90
days IS a separate, alternative route to either tier** — but it is a SEPARATE
path, never a contribution added into the long-form hours total, and
`loop/ypp.py` reports it as such rather than pooling the two.

So Shorts are not a faster route to monetisation — they are the discovery engine
that feeds one. The signal YouTube weights most heavily in 2026 is a viewer
clicking from a Short into a long-form video on the same channel, which is the
shape of this library: every Short is a chapter lifted out of an episode that
continues the thought.

### Sources

- vidIQ, 10.2M channels — upload frequency vs. growth
  https://vidiq.com/blog/post/How-Often-Post-on-Youtube/
- Buffer, 1.8M videos — long-form best days and hours
  https://montage.app/blog/best-time-to-post-on-youtube
- SocialPilot, 301K videos — https://www.socialpilot.co/insights/best-time-to-post-on-youtube
- RecurPost, 2M videos — https://recurpost.com/blog/best-time-to-post-on-youtube/
- Shorts vs long-form subscriber conversion —
  https://www.youtowire.com/blog/youtube-shorts-vs-long-videos-subscribers
- 2026 hybrid strategy —
  https://influenceflow.io/resources/youtube-shorts-and-long-form-video-strategy-the-complete-2026-creators-guide-1/

### These are benchmarks with a shelf life

Every study above is somebody else's audience. As soon as YouTube Studio's "when
your viewers are on YouTube" report has real data behind it, the channel's own
heatmap replaces these numbers; the monthly review is where that swap happens.

**Consistency outweighs all of it.** A predictable schedule is worth ~67% faster
subscriber growth than posting erratically at higher volume — which is the
argument for 2/week forever over 3/week sometimes.

---

## 3. The loop

Every scheduled stage runs in GitHub Actions. Rendering is the only thing left
on the Mac, and it is a batch the owner starts by hand — nothing on the laptop
is scheduled any more.

| When | Stage | Where | What it does |
|---|---|---|---|
| Mon 10:00 | `mon-draft` | Actions | Author the next script from the ranked queue; every figure cited to a named public source; validated before it may proceed. |
| by hand | render | Mac | Narrate, assemble, burn in captions, place rights-cleared footage inside its clean windows. `bin/batch-session.sh`, every ~7.5 weeks. |
| by hand | shelve | Mac | `bin/push-to-r2.sh` — put the finished renders and thumbnails where the cloud can reach them. Idempotent; run it after every batch. |
| **daily 14:00** | **`cloud-upload`** | **Actions** | **Pull the next ranked episode from R2, upload private with its cadence slot and thumbnail, commit the ledger back.** |
| Fri 13:00 | `fri-publish` | Actions | Flip what is due; verify YouTube reports it public; feed the site. |
| Fri 21:00 | `fri-measure` | Actions | Pull retention and watch time; recompute the retention streak; trip the breaker if the floor is breached. |
| Sat 10:00 | `weekly-score` | Actions | Measure demand and competition for candidate questions. Saturated topics are killed outright. |
| Sun 10:00 | `sun-rank` | Actions | Re-order the publish queue by combined score. |
| 1st monthly | `monthly-review` | Actions | Decide from thresholds, ask an LLM for a second opinion, apply within a fence, email the report. |

### launchd agents on this Mac

Two are installed, and only ONE of them narrates. This section was previously headed "No launchd agents.
None." and said the laptop could be shut; that was true from 2026-09-01 until
2026-09-04, when a second domain gave the Mac ~27 hours of narration to get
through and nothing was scheduled to do it.

| Agent | When | What it does |
|---|---|---|
| `com.howweknow.batch` | **daily 23:00** | `bin/batch-session.sh` — narrate every script with no audio, render every episode whose audio is complete, push to R2, then take a NAMED STOP. |
| `com.howweknow.backfill` | daily 09:00 | Upload the next finished episode and date it. Does not narrate. |

**`tuesday` and `thursday` are deliberately NOT installed.** `bin/loop-tuesday.sh` narrates — it calls `bin/run-batch.sh voice` — so installing it puts a second narrator on the machine against a batch that already narrates nightly. Narration cannot be parallelised here: the voice model wants about four cores, so two narrators run at half speed each and race for the same `audio/<slug>/NNNN.wav`. `bin/loop-install-launchd.sh --install` installs the batch and nothing else.

**Why `batch` is daily and why that is not wasteful.** Narration measures at
**0.8 beats a minute** on this M2, so eighteen materials episodes are ~27 hours
of voice — it cannot finish in one night and it will be interrupted.
`bin/batch-session.sh` is resumable by construction: every beat already on disk
is skipped, and an episode is rendered only when its wav count equals its
plan's beat count. A nightly run therefore continues until the queue empties
and then costs about a second. 23:00 is the owner's choice — the voice model
takes roughly four cores, so it starts when she has stopped using the machine.

**Nothing here runs a language model.** Narration and rendering are
deterministic local programs. The only stage that needs one is *authoring* a
new script, and that runs in Actions on Mondays. When the script queue empties,
the batch's own named stop says so in those words — "the shortfall is SCRIPTS,
not audio".

**The duplicate-upload hazard that removed `backfill` in the first place is
still real** and is worth restating: `backfill` and `loop-upload-cloud.yml`
both draw the next episode from the same ranked queue, and the Mac's copy of
`loop/state/ledger.json` only updates when somebody pulls. A launchd job at
09:00 cannot see what a workflow uploaded at 14:00 UTC the day before. If both
are ever live at once, that is the failure to look for first.

Installed with `bin/loop-install-launchd.sh --install`, verified with `--status`.
A plist is XML, so a bare `&&` in the command makes it unparseable — and
`launchctl` still reports "loaded" for a file it cannot parse. Both original
agents shipped that way and would never have fired. Check with `plutil -lint`,
never with launchctl's own word.

### The batch session

`bin/batch-session.sh` is the only thing this Mac is for. It narrates every
queued script without audio, renders every narrated episode without video,
verifies nothing is clipped (V13), and pushes the results out. It holds the
machine awake, skips what is already done, and is re-run rather than restarted
after an interruption. `--dry-run` answers "is there work for me?".

The owner is told to run it by the RUNWAY named stop from `sun-rank` — a cloud
lane, so the email actually leaves the building.

### One account for the quota

Four scheduled jobs spend from the same 10,000-unit daily YouTube allowance and
none of them can see the others. The worst case — a Thursday where the Shorts
lane, the backfill and the weekly upload all fire — came to **10,200 units**.
Nothing would have warned anyone: the last upload would simply have failed
partway through, leaving a half-uploaded video, which is worse than an unstarted
one.

`loop/quota.py` is now the single account. Costs live there and nowhere else
(`videos.insert` 1600, `thumbnails.set` 50, `videos.update` 50, daily 10,000,
with 400 held back as headroom). Every spending lane RESERVES before it starts
and records after it finishes; a lane that cannot afford a whole video takes
fewer or stops cleanly rather than beginning work it cannot finish. The day
boundary is **midnight Pacific**, because that is when YouTube resets — not
local midnight and not UTC.

A `--dry-run` is deliberately NOT quota-gated: it makes no API calls, and being
unable to preview tomorrow's schedule because today's uploads are done would be
a guard blocking the wrong thing.

### One writer owns library uploads — and it is now the cloud

`loop/backfill.py` owns the *logic*: it picks the slug in combined_score order,
assigns the next cadence slot, attaches the thumbnail and writes the ledger.
`loop/cloud_upload.py` does not re-implement any of that — it calls
`backfill.schedule_for()` and `backfill.upload_one()` directly, and differs only
in where the bytes come from. If it had its own copy of the scheduling, the two
would hand the same Sunday to two different videos the first day they both ran,
and that bug surfaces as a public double-post weeks later rather than as a
failure today.

The Thursday Mac lane's **library fallback was removed on 2026-09-01**. It used
to delegate to `backfill.run(limit=1)` when the weekly queue was empty; it now
takes a `NOTHING_RENDERED` named stop that says the back catalogue belongs to
the cloud lane. Same reason as the launchd agent: two machines, one ranked
queue, and only one of them reading a current ledger.

The earlier version of that fallback re-implemented the upload and wrote an
upload receipt but no ledger row — and the backfill filters on the ledger.
Thursday 02:00 would have uploaded an episode and 09:00 would have uploaded it
**again**. Two components each keeping their own list with no link between them.
One writer, one record.

### Where the bytes live

`renders/*.mp4` is gitignored — too large for history, regenerable in ten
minutes — so a cloud runner has the credentials and the schedule but not the
video. Cloudflare R2 is the bridge:

```
Mac    bin/push-to-r2.sh    renders/<slug>-final.mp4       -> r2://how-we-know-renders/renders/…
                            channel/thumbnails/<slug>.jpg  -> r2://…/thumbnails/…
cloud  loop/cloud_upload.py  pulls the one it is about to publish, verifies sha256
```

Driven by `wrangler`, not boto3 — the S3 path needs a second credential (an R2
S3 API token with its own key and secret) where the existing Cloudflare API
token already works. `wrangler r2 object` has only get, put and delete, so each
object is pushed with a `<key>.meta.json` sidecar carrying its size and sha256,
written *after* the object. That sidecar is what makes existence checks cheap
and makes `bin/push-to-r2.sh` idempotent **by content rather than by name** — a
re-cut episode keeps its slug, so name-matching would leave the old cut shelved
forever.

Setup, and the three secrets only the owner can set:
[`docs/CLOUD-UPLOAD-SETUP.md`](CLOUD-UPLOAD-SETUP.md).

### Rule 0

No stage may exit 0 having done nothing. Work done, or a NAMED stop a human
actually sees. `loop/tests/test_named_stops.py` asserts that every lane which can
be blocked names its stop and says how to clear it.

### The advisory fence

The model decides *what*; the loop decides *what is allowed*. It may move
`retention.runtime_minutes` inside **10.0–12.0 minutes**, once a month, with a
cooldown. **The floor was 4.0 until 2026-09-01 and that was a real hole:** the
owner's instruction is that every batch is 10–11 minutes, and a fence whose floor
sat at 4.0 meant one automated monthly review could have walked that instruction
back — by 1.5 minutes a month, in a JSON field, with nobody seeing it. The floor
is an owner decision, not a tuning parameter; `loop/monthly.py` enforces 10.0 and
a test asserts the fence can never dip below it.
It may **not** change cadence, abandon deep sea, or publish anything — those are
reported to the owner and never applied automatically.

### The reach lanes: captions and localizations

Added 2026-09-02, after two defects that had been live since launch and that
nothing in the repo could have reported.

**1. Twenty timed caption files existed and none had ever been uploaded.**
`captions/` has held a `.srt` and a `.vtt` per episode since narration, and
there was no `captions.insert` call anywhere in the repo — `loop/upload.py`
posted `part=snippet,status` and nothing else. The captions viewers see are
*burned into the picture* by the renderer, so they are pixels; YouTube cannot
read them. What that cost is larger than accessibility. YouTube Studio states:
*"English subtitles are the default source for auto-translation of subtitles
and audio."* The English track is the source file for auto-translated subtitles
in 100+ languages **and for auto-dubbed audio**, so with no track none of it can
fire. `loop/captions_lane.py` uploads it. It needs
`https://www.googleapis.com/auth/youtube.force-ssl`, which the plain `youtube`
scope does not cover — granted on 2026-09-02 after one browser re-consent.

**2. `snippet.defaultLanguage` was unset on every video, which gated the whole
translation surface.** The API rejects `localizations` without it, and in Studio
the per-video Languages page renders nothing but a "Set language" dropdown and
a disabled Confirm — no subtitle upload, no translations table, no dubbing
control. `loop/localize.py` sets it to exactly `en` (never `en-US`; a library
split between the two is an inconsistency nothing would report) and writes
localized titles and descriptions in **es, pt-BR, hi, id, de**, prompting for
the phrase a native speaker would actually search rather than a literal
translation. A second model call back-checks each title for a wrong core noun
and either corrects it or refuses the language — it caught Sonnet rendering
"deepest" into Indonesian as *terlaut*, which is not a word.

**The trap both lanes are built around: `videos.update` REPLACES the parts you
name.** Sending `part=snippet,localizations` with a partial snippet erases the
title, description, tags and categoryId of a live video, behind a 200 OK. Every
snippet-bearing write goes through `loop/ytmeta.py`, which reads the live
snippet, merges, sends it back whole, and *refuses* rather than truncating when
it cannot. Validator **V19** fails the build if any other module in `loop/`
issues such a call.

Neither lane may fail an upload. They live in their own workflow
(`.github/workflows/loop-reach.yml`), each in a step that survives the other's
named stop, and validators **V16–V19** and **V26** run as a separate group
(`loop/validate.py --reach`) rather than inside the Monday render gate — a
lagging translation must never be able to halt drafting and, through the
breaker, publishing.

**A deferral is green, and it is loud.** The caption backfill costs 450 units a
video and genuinely spans days, so on any given morning some videos have no
track and no localizations *yet*. Both lanes write a dated `QUOTA_DEFERRED`
receipt into `loop/state/captions.json` and `loop/state/localizations.json`
before they stop, and V16/V17 report those as a **NAMED STOP** — exit 0, with
the code, the count and every affected slug printed. What stays red is a live
video with no track, no localizations and *no recorded reason*: the receipt is
what separates a lane working as designed from a video nobody noticed. The
receipt is written by the lane that deferred, carries the date of the FIRST
deferral, is never refreshed, and expires after `DEFER_GRACE_DAYS` (7) — so a
backfill that has actually stalled goes red on its own.

This is why it matters: on 2026-09-03 the daily 10:00 reach run mailed one red
naming twelve videos. Eleven were correctly deferred with their `.srt` ready;
exactly one had genuinely been missed. The report could not tell them apart, so
the signal that mattered was buried under eleven that did not.

Quota, from Google's published table: `captions.insert` 400 and `captions.list`
50, so 450 a video and 6,750 for the fifteen-video backfill; `videos.list` 1
plus `videos.update` 50, so 51 a video and 765 for the same backfill. Both
spend through `loop/quota.py` behind `quota.upload_reserve()`, which holds a
whole video's allowance back while the day's upload is still to come and
releases it once an uploading lane has booked units. The caption backfill
therefore spreads over several daily runs by design rather than eating the day.

---

## 3a. A script's sections, and where each one actually goes

Added 2026-09-03, because it was previously true but undocumented — the
script markdown has more structure than "narration" and each section has a
different, single destination:

| Section | Goes to | Never |
|---|---|---|
| `## Direct-answer lock` | The description's first line, the thumbnail brief, and the Shorts scorer | **Never spoken.** `voice/script_text.py` narrates only `## Narration`. |
| `## Narration` (including `### Producer POV` and `### What to notice in the edit`) | The rendered audio, verbatim minus `{{directives}}` and headings | — |
| `### Producer POV` `[HUMAN]` line | Spoken, first-person, the owner's own words from the POV bank | Never paraphrased by a model — `loop/author.py`'s prompt requires it verbatim. |
| `### What to notice in the edit` / `### Final editorial note` | Spoken, addressed to the VIEWER in second person (corrected 2026-09-03; used to describe production strategy in third person — "the channel gains engagement", "the pinned comment can" — which is the "narrator reading channel strategy aloud" defect `loop/validate.py` V22 now guards against) | Never third-person meta-commentary about the channel's own business |
| `## Chapters` | A DRAFT for the description; the real timestamps sent to YouTube come from `captions/<slug>.chapters.txt` (real caption timing) when it exists — see `loop/upload.py:build_chapters()` | The script's own estimated timestamps are never sent as-is; they drift from the real render by up to a minute |
| `## Sources` | The description's Sources block, verbatim URLs, fetched and verified by V8 | Never translated or reformatted (see `loop/localize.py`) |

## 3b. The retention breaker is domain-aware

Added 2026-09-03. With a second domain live, "three consecutive videos below
the retention floor" stopped being a single question. `loop/measure.py`
computes a duration streak PER DOMAIN (`domains.split_rows()`,
`domain_streaks()`) and decides the trip cause from the pattern:

- every judgeable domain breaching together → the FORMAT is wrong, runtime
  shortens
- one domain breaching while others hold → that DOMAIN is wrong, its
  allocation moves — the format is untouched

Before this, the breaker had no notion of a domain at all and would have
shortened every episode on the channel because one niche had a bad quarter.

---

## 3c. The niche lifecycle closes itself

Added 2026-09-05. The monthly review had computed `exhausted_domains` and
`next_domain` since 2026-08 and written both into prose that nothing read. A
niche could decay to an empty queue and keep its weekly slots indefinitely, in
a report that named it as finished. Deciding correctly and then discarding the
decision is the "runs but inert" defect one level up.

`loop/domains.lifecycle()` now acts on it, and **outranks** the one-slot
reallocation in the same month — moving a slot between two domains is
meaningless if one of them is finished, and a move computed against the
pre-retirement split would land on a split that no longer exists.

| It retires when | It refuses when |
|---|---|
| the domain's scored queue is below `queue_exhausted_below` (4) | the domain has fewer than `min_episodes_to_judge` (8) measured episodes — a thin queue that early is a scoring backlog, and the answer is to score more topics |
| **and** it has published and been measured | there is no unused domain left in the taxonomy — retirement is a **swap**, never a subtraction, because a channel with fewer domains than slots publishes nothing |

The promoted domain inherits exactly the retired one's slots, so the allocation
still sums to `cadence.ceiling` and `slots_at()` cannot raise on the split it
produced. Everything goes through the same monthly cooldown fence as runtime, so
a wrong retirement is bounded exactly like a wrong slot move.

**A promoted domain arrives with no queue**, and `research/publish_order.py`
gates deep sea while `publish_order_materials.py` gates materials from a list
someone wrote by hand. `research/publish_order_domain.py --domain <name>` closes
that: candidates come from `research/broad_mined.json` — real, autocomplete-
confirmed questions already mined for all 20 domains — screened for the channel's
hard exclusions and for autocomplete tails that are not topics ("…in hindi",
"…dr binocs", "…wobbly life"), then scored through **the same gate**, imported
unchanged. The Saturday scoring lane runs it for any allocated domain with no
queue, so the promotion becomes real on a schedule rather than in a report. Where
the broad 8-seed mine is too thin — space-astronomy yields six candidates from it
— it runs the deeper single-domain mine first, which is free autocomplete and
needs no quota.

Guarded by **V34**, which constructs the month rather than waiting years for one.

## 3d. The Saturday harvest takes its domain list from the allocation

Added 2026-09-05. The harvest lane kept a hardcoded tuple of two harvesters,
both deep sea. `materials-and-manufacturing` went live on 2026-09-03 with half
the weekly slots and the lane never learned it existed:
`research/imagery_materials.py` was invoked by **nothing at all**, and neither
was `research/imagery_species.py`. Two components each keeping their own list,
with no link between them.

The second list is gone. A harvester declares its own contract at module scope —
domain, rights gate, manifest, arguments — and `loop/footage_lane.py` discovers
`research/imagery*.py` by reading that declaration with `ast` (never importing
it; several reach the network at import). It then runs the ones whose domain
holds a slot in `loop/config.json`. **A domain in the allocation with no
harvester is a named stop, not a skip** — skipping quietly is exactly how this
went unnoticed.

The same pass found `imagery_video.py` being run with no arguments, so it
screened the NOAA index and downloaded nothing, every Saturday, while the lane
reported that it had harvested "video clips — the scarce pool". Its declaration
carries `args: ["--harvest"]`.

Guarded by **V33**, asserted behaviourally over the live allocation rather than
by grepping for filenames — a lane that finds the file and never runs it would
pass a grep.

---

## 3e. The editorial gate, decided rather than left to decay

Added 2026-09-05. All 38 scripts carried a section called **Human fingerprint
gate**. Nothing read it. Three of its six bullets asserted a step by a person —
"owner must confirm it sounds natural read aloud", "owner confirmation
required", "Final human watch-through: PENDING until the rendered MP4 exists" —
on a channel explicitly designed to run without its owner. Those episodes aired.
The confirmations never happened and were never going to.

There were two honest resolutions: start performing the review, which is the one
thing this channel exists not to require; or stop claiming it. **The claims are
gone.** What remains is called the **Editorial gate**, and every line in it is a
property the build actually enforces:

| Claim | Enforced by |
|---|---|
| the first-person observation traces to her voice | V4, V32 |
| every number traces to a named public source | V5, V6 |
| the episode states its own uncertainty | V36 |
| the structure is not another episode's | V36 |

"Structural variation" is checkable in the strongest sense available: all 38
labels are distinct, so a duplicate is a template reasserting itself — which is
the first thing that would go wrong, and the last thing anyone would notice.

**This is a decision, not a tidy-up.** The channel now claims a smaller thing and
means it, rather than claiming a larger thing that was quietly false on every
episode it shipped.

---

## 3f. A retired video with a publish date un-retires itself

Found 2026-09-05 while answering "when does the last video go out".

**Two upload lanes wrote one episode twice.** `backfill` on the Mac and
`cloud-upload` in the cloud both uploaded
`02-how-deep-sea-creatures-survive-pressure` on 3 September, three hours apart,
and gave two different video ids **the same 25 October 15:00 slot**. Two
identical videos would have gone public in the same minute. This is the second
time the two lanes have collided.

**Retiring the duplicate did not fix it.** `retire.py` set the video private and
verified private — and its `publishAt` survived untouched. YouTube would have
made it public on 25 October anyway, seven weeks later, with nothing watching.

**A `publishAt` cannot be cleared by omission.** Neither leaving the field out
nor sending an explicit `null` clears it: both return HTTP 200 and leave the
stored value exactly as it was. The only thing that works is moving the video
**off** private and back — `unlisted`, then `private` — which is what
`publish.cancel_schedule()` now does, verified by read-back.

Guarded by **V38**: one live ledger row per slug, and a retired row may not hold
a future publish date without a recorded cancellation. It also asserts the
cancellation is still in `retire.py`, because the API's behaviour here is
counter-intuitive enough to be "simplified" away by someone later.

---

## 3g. The runway counted episodes that had already aired

Found 2026-09-05, from the question "when does the last video go out".

`research/publish_order*.json` is the **scored** list, not the **remaining**
list — a slug stays in it after its episode is made, because that is where its
score and gate verdict live. `domains.queue_depth()` counted every row, so the
whole catalogue was counted twice: deep sea reported **16 queued topics and 8.0
weeks of runway** while all 16 were already uploaded and dated. Its real
remaining queue was **zero**.

That is the worst direction for this number to be wrong in. `runway.warn_weeks`
exists to say *you are running out* before it happens, and it could not see the
end coming: it would have stayed green until the last scheduled episode aired
and the queue was simply empty. The same figure feeds `domains.exhausted()`, so
a decayed niche could never have been detected either.

`queue_depth()` now subtracts anything in the ledger. The immediate reading:

| Domain | Scored | Already made | Remaining | Runway |
|---|---|---|---|---|
| Deep sea | 16 | 16 | **0** | **0.0 wks — critical** |
| Materials | 18 | 3 | 15 | 7.5 wks |

Two things then worked exactly as designed. `lifecycle()` refused to retire deep
sea, naming `QUEUE_DECAYED_BUT_UNMEASURED` — a thin queue with no analytics yet
is a scoring backlog, not a finished niche. And `score.missing_queues()` now
lists deep sea, so the **Saturday lane runs the topic gate for it automatically**;
`publish_order_domain.py` reads deep sea's own deep mine
(`research/mined_queries.json`, named in `DEEP_MINE_OVERRIDE` because it predates
the naming convention) rather than the shallow broad pass.

Guarded by **V39**. Also fixed there: the generic gate was proposing episodes
that already exist, and admitting anything sharing a single over-common seed
word — "deep" matched a quarter of the corpus, which let in *how deep are septic
tanks buried* and *how deep is your love*.

---

## 3h. Narration hands the Mac back at 07:00

Owner decision 2026-09-05. The nightly batch started at 23:00 and had **no stop
time at all** — not in `bin/batch-session.sh`, not in the launchd plist. It ran
until the backlog was finished, which on 5 September meant it was still
generating audio at four in the afternoon on a Saturday, seventeen hours in,
with fifteen hours left to go.

The owner had asked for "22 hrs at 11pm every night until finished" and reasonably
understood that as an overnight window. The start time was implemented; the end
was not.

`narrate_all.py --until HH:MM` now stops the run cleanly, and
`batch-session.sh` passes `07:00`.

**Stopping costs nothing.** The deadline is checked **between** beats, never
during one — a beat takes a couple of minutes and stopping inside it would leave
a `.part.wav` and waste the work. A beat whose wav already exists is skipped, so
the next night resumes exactly where the last one stopped. What it costs is
calendar time; what it buys is a machine that is hers during the working day.

A past time resolves to *tomorrow*, so a run starting at 23:00 stops eight hours
later and one starting at 02:00 stops five hours later — never immediately.
`stopped_at_deadline` is recorded in the narration report, so a morning stop is
visible rather than looking like a crash.

Change the hour with `NARRATION_UNTIL=08:00` in the environment, or edit the
default in `bin/batch-session.sh`.

---

## 4. Incidents worth remembering

Recorded because each was invisible until something specifically looked for it.

- **`-shortest` clipped the last word of every video whose beats rounded down.**
  Episodes 10, 14 and 18 lost 0.098s, 0.014s and 0.122s — speech at −14 dB
  against a −45 dB floor, not silence. Fixed by padding the last beat; guarded by
  validator **V13**, which checks the rendered artefact, not the intention.
- **Chapter lists were being silently discarded.** YouTube drops the *entire*
  chapter list if any two chapters are under 10 seconds apart. All nine narrated
  episodes had at least one such pair — 13 in total. Now merged automatically.
- **The metadata credit lies; the burned-in credit tells the truth.** NOAA clips
  whose `acf.credit` reads "NOAA Ocean Exploration" carry end cards crediting
  GFOE, a contractor. 17 U.S.C. 105 covers federal *employees*. The OCR gate
  rejected 79 clips that the metadata gate passed.
- **`videos.update` needs the full `youtube` scope.** The private→public flip —
  the thing the publish lane exists to do — returned 403 under `youtube.upload`
  alone. Invisible because the first video was uploaded public directly, so the
  flip had never once been exercised.
- **A test uploaded a real video.** `test_named_stops.py` runs `upload.py` with
  credentials read from disk; when the library fallback was added it found a
  finished episode and uploaded it (`MAV4PF056RA`, adopted into the schedule).
  Fixed with `LOOP_DRY_RUN=1`, which suppresses network writes *and* refuses to
  load credentials, so the lane behaves as an un-credentialed machine.
- **`launchctl` reports "loaded" for a plist it cannot parse.** The generator
  emitted a bare `&&` into XML. Both Mac lanes appeared installed and would never
  have fired. Now `&amp;&amp;`, verified with `plutil -lint`.
- **A fixed UTC hour silently drifts across daylight saving.** The publish slot
  was pinned to 15:00 UTC, which is 10:00 Central only until 1 November; after
  that every video would have gone out an hour early, with Pacific at 07:00 and
  outside the target window entirely. Now pinned in `America/Chicago` and
  converted, so the UTC stamp moves and the local hour does not.
- **The runway metric counted a scheduled video as already spent.** It read
  "2.5 weeks — WARNING" while eleven episodes sat uploaded and dated, and would
  have read 0.0 with eight weeks of video queued and airing. An alarm that is
  wrong in the alarming direction is one people learn to ignore. `cadence.runway`
  now counts uploaded-but-not-yet-aired videos as remaining runway.
- **A cadence step was added to a slot search that already advanced.**
  `slots()` returns only slots strictly after its anchor, so adding 3.5 days
  first skipped one — which left **Tue 22 Sep 2026 empty** between Sun 20 and
  Sun 27. A silently dropped publish slot on a channel whose whole argument is a
  predictable cadence. Fixed, and the schedule was re-laid gapless.
- **Repairing that gap briefly scheduled a second video for the same day.** The
  re-grid anchored on `now()` instead of on the last video that had actually
  AIRED, and handed out a slot 80 minutes away on a day that already had a
  release. Caught before it fired. The anchor is now the last aired publish.
- **Every Short was audio-desynced, and the measurement that said otherwise was
  meaningless.** `-t` used as an INPUT option is broken on ffmpeg 8.1.1: asking
  for 3.47s returned 207 frames where 104 were wanted. Every beat after the
  first started seconds late, and `-shortest` hid it by truncating the picture —
  episode 05's cut was 34.13s of video against 30.61s of audio. An earlier
  "A/V drift under one frame, verified" was taken on the already-truncated file:
  a real number measuring the wrong thing. Now cut with `-frames:v <exact>` and
  asserted afterwards.
- **The Short's chrome vanished after the first beat boundary.** x264 tagged some
  segments `bt709` and others `unknown`; `concat -c copy` changed format
  mid-stream, ffmpeg reinitialised the filter graph, and the single-frame chrome
  inputs were already at EOF — so wordmark, credits AND captions disappeared
  from the first cut onward. Fixed by pinning `setparams` in the first pass.
- **A directory scan asked for 3.5 hours of narration for killed episodes.**
  `bin/batch-session.sh` scanned `plans/*.json`, and the demand gate's four
  killed topics still have plan files on disk. It reads the publish queue now.
- **A derived artefact compared against a tree that moved after the derivation.**
  `research/publish_order.json` still carried an owner pin the plan recorded as
  superseded; it simply had not been regenerated.

---

## 4a. Shorts: cropped, not re-rendered

The 16:9 masters carry burned-in captions and a Short burns its own, sized for a
1080x1920 canvas. The first approach was to re-render all sixteen episodes
without captions — about three hours — because the source credit is drawn BELOW
the caption plate and cropping the plate away takes the credit with it.

**That was the wrong solution and the owner rejected it.** The credit is not only
pixels; it is data held in `channel/imagery/rights.json` and
`video_rights.json`. So the band is cropped off and the credit is REDRAWN in the
Short's own chrome, resolved per picked beat. No re-rendering at all.

It also came out better. The old design scaled a 24px credit line by 0.5625 into
the band — about **13px on a phone**. Redrawn in the chrome it is **28px**.

**Cost:** the picture band is **440px instead of 608px**, because the crop
removes 782 of 1080 source rows — 27.6% less picture. That is the real price,
and it strengthens the case for a native 1080x1920 segment library, which would
fill the phone rather than letterboxing a 16:9 slide.

**Guards.** V14 re-resolves every credit from the manifests — never from the
Short's own receipt — and OCRs the credit strip with Apple Vision to prove it is
on screen. V15 proves the crop actually removed the burned captions, using OCR
for the "before" half and pixel comparison for the "after": OCR on the band
would false-fail, because a Short's band legitimately shows the words being
narrated. A beat whose credit cannot be resolved is dropped; if that beat is the
anchor, the Short fails rather than shipping uncredited.


### Shorts supply, and why all three ranks publish

`visuals/shorts.py` ranks each episode's chapters. **Rank measures relevance to
that episode's core question — not how good a Short it makes**, and those are
different things. Episode 01's rank 3 is "Scarce food favors oversized feeding
equipment" (a large mouth, long teeth, hinged jaws, the anglerfish's lure),
which is plainly stronger short-form material than its rank 2 on soft bodies
under pressure. Publishing only ranks 1-2 would have thrown that away for a
reason that does not survive looking at the output.

The genuinely unpublishable category is filtered at SOURCE regardless of rank:
chapters whose heading is production apparatus, and narration that talks about
the video rather than the subject. **That is the guard that matters; rank is
not.**

| Ranks published | Shorts | Runway at 4/week | Runway at 9/week |
|---|---|---|---|
| 1 only | 16 | 4.0 weeks | 1.8 weeks |
| 1-2 | 32 | 8.0 weeks | 3.6 weeks |
| **1-3 (current)** | **51 cut** | **12.8 weeks** | **5.7 weeks** |

**Shorts consume no episode inventory** — they are cut from finished renders, so
more Shorts costs nothing but quota. At the raised 9/week the 51 already cut last
roughly **five to six weeks** rather than twelve, which is the real cost of the
raise and the reason exhaustion is now a named stop rather than a printed line
(`SHORTS_INVENTORY_EXHAUSTED`).

### The vertical Shorts library is deliberately deferred

Shorts currently render as a **608px band inside a 1920px frame** rather than
filling a phone screen. Native vertical would be a real quality improvement and
it is on the roadmap. It is **not** being built now, and that is a decision
rather than an oversight: **51 Shorts are already cut in the current format**,
and re-cutting them would discard work already paid for. The owner's call
(2026-09-02) is to publish the existing 51 first and build the vertical library
only once that inventory is exhausted.

Nothing in the loop transitions to a vertical format on its own when they run
out — that would make a deliberate decision automatic. What happens instead is
the `SHORTS_INVENTORY_EXHAUSTED` named stop, which puts the choice in front of
her with the two options named.

**No approval step.** The owner declined per-Short review (2026-09-01): ranks
1-3 publish automatically. `loop/shorts_approval.py` remains as a VETO only —
naming a file there keeps it off the channel permanently, and records that it
was seen and refused rather than merely never reviewed. Nothing has to be
approved for it to publish.

### One ledger, two upload lanes, no arbitration

Both `bin/loop-backfill-daily.sh` (Mac) and `loop-upload-cloud.yml` (Actions)
decide what is left by reading `loop/state/ledger.json`. Reading separate copies
is how duplicate public videos happen — the Mac's local file and the workflow's
committed copy disagreeing about what has already gone out.

So the Mac lane **pulls before deciding and pushes after acting**, and the cloud
lane commits its own result. Whichever runs first does the work; the other finds
nothing pending. **Neither has to be disarmed and no human has to sequence
them.** A failed pull is a NAMED STOP rather than an upload against a possibly
stale ledger: a duplicate public video is worse than a skipped day, and the next
run picks it up unchanged.


## 5. What runs on the Mac, and what does not

```
1.  Cloud writes scripts every Monday                     owner: nothing
2.  Runway drops under 4 weeks -> GitHub emails her       owner: read the email
3.  She opens the Mac and runs ONE command                owner: 10 seconds
4.  It narrates and renders, unattended                   owner: walks away
5.  Cloud uploads, schedules and publishes                owner: nothing
```

Step 3 is `bin/batch-session.sh`. The operator-facing version of this lives in
[`RUNBOOK.md`](../RUNBOOK.md); everything below is the reasoning behind it.

**Status: 2026-09-01. Uploading is being migrated to GitHub Actions + Cloudflare
R2; this section describes what is true TODAY and is rewritten when that lands.**

| Stage | Where | Needs the Mac awake? |
|---|---|---|
| Score, rank, draft | cloud lane | no |
| Publish flip, measure, monthly review | cloud lane | no |
| **Narration (voice)** | **Mac** | **yes — and it always will** |
| Render | Mac | yes, for now |
| Upload / schedule / thumbnail | Mac | yes, *migrating to cloud* |
| Shorts cutting | Mac | yes, *migrating to cloud* |
| YouTube actually publishing | YouTube | **no** |

### Narration is the one stage that cannot move

Measured, not assumed: **episode 07 took 71 minutes for 67 beats — about 1.2
hours an episode** on this Mac with MPS. GitHub's CPU runners are several times
slower, which puts a single episode near the 6-hour job ceiling and two a week
near the whole free monthly allowance. The voice model is also local.

So the owner returns to the Mac roughly every eight weeks for a narration batch,
and `sun-rank` emails when that is due (see below). Everything else can leave.

### Uploading has no business being on this Mac

It is here only because the finished files are here. The renders are 40 MB each;
staging them in Cloudflare R2 (`how-we-know-renders`, round-trip proven
byte-exact) lets a cloud lane fetch and upload them. Two secrets, not four,
because wrangler authenticates with the account token rather than S3 keys.

**The wrangler trap, recorded because the error points the wrong way:** wrangler
resolves the account through `/memberships`, which this token cannot read, so
every `wrangler r2` command fails with `Authentication error [code: 10000]` —
indistinguishable from a missing R2 permission. Setting `CLOUDFLARE_ACCOUNT_ID`
explicitly skips the lookup. The token was never the problem.

### If the Mac is asleep

launchd fires a missed `StartCalendarInterval` when the machine next wakes, so
nothing is lost — it runs late. Late is harmless here because the publish
schedule runs weeks ahead of the render queue. **Videos already uploaded and
dated keep airing regardless: YouTube publishes them, not this machine.**

### How the owner is told to come back

`sun-rank` runs in the cloud every Sunday and takes a NAMED STOP when the runway
falls below four weeks. A named stop that needs a human exits 3, the workflow
fails, and **GitHub emails on a failed run** — which is the only thing that leaves the machine. It
used to be a `st.note(...)`, written into a report and read by nobody.


### The stops that do NOT email her

Not every named stop is hers to fix. A daily lane that finds the day's YouTube
allowance already spent has nothing for anyone to do: the allowance comes back
at midnight Pacific and the same lane runs again tomorrow. `loop/stop_policy.json`
classifies those as **self-resolving** — the banner, the stop record and the job
summary are identical, but the job stays green and no issue is opened.

Everything else still pages: a missing credential, a failed validator, corrupt
state, `ZERO_WORK`, and any code the policy does not list. And a self-resolving
stop that repeats past its limit (three runs, for the quota) escalates back to a
red job, because at that point it is not resolving itself.

Where to look when a lane is quiet: `loop/state/stops/<week>-<stage>.json` names
the disposition and why, and `loop/state/stops/_streaks.json` says how many runs
in a row it has been like that.
