# RUNBOOK

> **Nothing waits on the owner. A finding becomes an action with a measurement, never a question. Only a secret or an account she alone holds may stop, and that stop is green and self-explaining.**

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

**At 22:55 the Mac quits Chrome, Signal and Spotify by itself** (`com.howweknow.nightquit`, your decision of 2026-10-03): this is an 8 GB machine and the voice model was swapping behind Chrome on five of seven nights. Reopen them in the morning; Chrome restores your tabs.

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
about **five to six weeks of runway** rather than twelve. The Mac's nightly
batch cuts Shorts from every newly rendered episode, so the shelf refills
itself; Shorts stay in the current cut format (decided 2026-09-25 and logged,
not pending on you). `SHORTS_INVENTORY_EXHAUSTED` is a green note, not a
question.

If you ever spot a bad one, that is the only manual lever:

```bash
.venv/bin/python loop/shorts_approval.py reject <file.mp4>
```

That keeps it off the channel permanently. Nothing needs approving for Shorts to
publish — the veto is the exception, not the workflow.

**Every Short hands its viewer to its episode — nothing for you to do.**
Decided 3 October: almost all of the channel's views come from Shorts, so each
one now points home. Twice a day, after the morning upload lane and the evening
Shorts lane, `loop/handoff.py` reads what is public on the channel and makes
sure that:

- every public Short's description **opens with `Full episode: https://youtu.be/…`**
  and the episode's question (a Short that goes out before its episode airs
  waits as `pending` and is finished the run after the episode goes public);
- every public Short carries **one comment from the channel** with the same
  question and link — once, never pinned, recorded so it is never repeated;
- every public episode's description ends with a **"Shorts from this episode:"**
  list;
- every public video is in its domain playlist — **Deep Sea Science** or
  **Materials & Manufacturing** — and each playlist has a channel section.

It spends YouTube quota only after the day's upload and Shorts are safe, so a
big day finishes the next morning (`HANDOFF_QUOTA_DEFERRED`, green).
`HANDOFF_UP_TO_DATE` is the normal quiet result. Validator V46 fails only when a
Short and its episode have both been public for a day and a half with no link.
To see the plan without writing anything:

```bash
.venv/bin/python loop/handoff.py --dry-run
```

---

## You should never get a "named stop" email again

Changed 2026-09-08, on your instruction. A named stop used to arrive as a **red
build in your inbox**, whatever it was about. Some of those were worth sending
and most were not — the worst one asked you to open the laptop and type a
command to produce a file the server was already holding every ingredient for.

Every halt this system can take is one of three things (`loop/stop_classes.py`,
validator V45, checks every one):

| | What happens | You see |
|---|---|---|
| **Automated policy** | The loop acts on a written rule and logs it | nothing, or a line in the Sunday email |
| **A key or account only you hold** | The run stays **green** | one line at the top of the Sunday email, under **🔑 Needs your key or account** |
| **Something is actually broken** | The run goes red | an email |

**Nothing waits on a decision from you.** A finding becomes an action with a
measurement: the 2026-09-25 retention finding became the opening rule
(`loop/opening.py`: the payoff in the first 30 seconds of every new script,
compared against the old videos after four weeks, switched automatically if it
does not win).

**What is genuinely yours, and nothing else is:** a YouTube consent that has
expired or been revoked, a channel-level flag from YouTube itself, an API key
or account with no credit, a repository secret a new lane needs, and the Mac
being awake with its lid open at 23:00. That is the whole list.

**The one email you did get, and what it meant (2026-10-03).** GitHub mailed you
an issue titled `loop: shorts-cloud needs you` after the cloud Shorts lane found
an empty shelf seven nights running (`NO_SHORTS_SHELVED`). That is the third row
of the table: something was actually broken, and it was on the Mac. The nightly
batch was dying at its captions step for six nights and never reached the step
that cuts and shelves Shorts (fixed at source in #137: a caption failure is now
one episode's gap, never the night's). An empty shelf always means the Mac did
not get that far — `grep 'shorts: cut what is rendered' ~/Library/Logs/how-we-know/batch.log`
shows which nights did. The stop clears itself the first night the batch gets
through; the issue is closed by hand once it has.

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

**A held episode's Short waits with it** (since 2026-10-03, #138 and #140). The
Shorts lane used to ignore the hold, so a Short could go public days before the
episode it points back to existed on the channel. Now a held episode's Short is
skipped, and if one was already uploaded it sits **private with no date**,
flagged in the Shorts ledger. The evening after the episode's hold lifts, the
lane dates that Short into its next slot by itself. Nothing is deleted and
nothing is yours to do.

**The Mac now reports in.** If it has finished episodes and has not shipped
any for three days, the Sunday email says `MAC_NOT_SHIPPING` and names why.
Before 13 September that silence reached nobody.

**"Nothing shelved" names what it can see** (since 2026-10-03, #143). The
cloud's 09:00 CT upload lane says `NOTHING_SHELVED` when queued episodes are
neither uploaded nor on the R2 shelf. For a week it blamed "narration, render
or push" while the real gap was a finished deep-sea episode pushed **without a
thumbnail** — the batch only knew how to build materials thumbnails. Every
domain builds its own now (`visuals/thumbs_for.py`, one table, tested), and the
stop's **first line** is the blocker the cloud can prove: `N render(s) shelved
without a thumbnail: <slugs>` when that is the case, then the Mac's own
heartbeat (when the batch last ran, how many renders are finished, what the
gate holds), then whatever is genuinely still being narrated or rendered. A Mac
that is producing but behind the queue reads as behind, not stuck. Still
nothing for you to do; it tells whoever reads it where to look.

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

## Lanes

Every scheduled lane, in the order of a week. Times are Central daylight time
(one hour earlier in winter, CST); the UTC cron the workflow actually carries is
in brackets. "Calls a model?" is derived from code, not kept by hand:
`loop/tests/test_claude_subscription_route.py` walks the call graph of
`loop/*.py` to `llm_router.complete()` and fails if this column disagrees with it,
and `loop/tests/test_runbook_lanes.py` fails if a `loop-state` workflow has no row.

| Lane | When | What it does | Calls a model? |
|---|---|---|---|
| `loop-sat-score` | Sat 05:00 (`0 10 * * 6`) | Runs the research agent's demand/competition pass so the publish order is re-derived on current data every week. | no |
| `loop-sun-rank` | Sun 05:00 (`0 10 * * 0`) | The brain half of the loop: mines demand, ranks it, and proposes the week. | no |
| `loop-sun-digest` | Sun 11:00 (`0 16 * * 0`) | The one email a week that arrives when nothing is wrong. | no |
| `loop-mon-draft` | Sun night 00:00 (`0 5 * * 1`) | Builds `loop/render_queue.json` (the only handoff to the Mac), authors any topic that has no script yet, and rebuilds the dashboard. | yes |
| Mac render batch | daily 23:00 on her Mac (launchd, `bin/loop-install-launchd.sh` → `bin/batch-session.sh`) | Narrates every script that has no audio, renders every episode that has audio but no video, and pushes the results out for uploading; it reads `loop/render_queue.json`. | yes — `loop/extend.py` heals short episodes; the $0 route only, the Mac holds no subscription token |
| `loop-upload-cloud` | daily 09:00 (`0 14 * * *`) | Pulls the next pending episode's render and thumbnail from Cloudflare R2 and uploads it to YouTube as private with its publish date. | no |
| `loop-reach` | daily 10:00 (`0 15 * * *`) | Non-English reach plus discovery metadata: English captions, localized titles and descriptions, tags. | yes (localization) |
| `loop-shorts-cloud` | daily 18:00 (`0 23 * * *`) | Pulls a verified Short from R2 and uploads it to YouTube as private with its evening slot. | no |
| `loop-fri-publish` | Fri 08:00 (`0 13 * * 5`) | Flips private uploads to public, but only against a receipt proving the upload happened. | no |
| `loop-fri-measure` | Fri 16:00 (`0 21 * * 5`) | Pulls retention and RPM, writes measurement, and can trip the circuit breaker. | no |
| `loop-imagery-harvest` | Fri 23:00 (`0 4 * * 6`) | Grows the rights-cleared footage pool ahead of demand. | no |
| `loop-quarterly-taxonomy-refresh` | 1st of Jan/Apr/Jul/Oct 03:00 (`0 8 1 1,4,7,10 *`) | Refreshes the ranked candidate-niche taxonomy the next domain is drawn from. | no |
| `loop-override` | manual (an issue opened or edited) | The veto path: a row dropped from the dashboard opens a prefilled issue and this ingests it. | no |
| `loop-monthly-review` | 1st 02:12 (`12 7 1 * *`) — its own `main-automation` queue | Reads a month of measurement and says what to change. | yes (the advisory) |

Every lane above except the Mac batch and the monthly review shares the one
`loop-state` concurrency queue, and GitHub keeps only one waiting run per group,
so a long lane can push the next waiting one out of the queue. That is why the
Monday authoring budget ends well before the 09:00 upload lane.

## Model route

The order, decided in code (`loop/llm_router.py`, `config/llm_routing.json`):

1. **Your Claude subscription first**, through the headless Claude Code CLI,
   whenever the lane carries `CLAUDE_CODE_OAUTH_TOKEN`. Prepaid; no per-call
   bill.
2. **Your Google AI Studio key, free tier only, second** (`gemini_route` in
   `config/llm_routing.json`), whenever the lane carries `GEMINI_API_KEY`.
   Models are tried in the listed order through Google's OpenAI-compatible
   endpoint; a 403/404/429, timeout or empty answer skips to the next with one
   `[gemini-route] skipped …` line, and the tier never stops a lane.
   **Data rule:** free-tier Gemini prompts may be used by Google to improve its
   products, so this tier is fine for channel scripts and **never for anything
   confidential (LP names, deal terms)**. The router is the only door to a
   model here, and this repo holds nothing confidential.
3. **The $0 OpenRouter list third** (`config/llm_routing.json` `models`), if
   the tiers above are missing or fail for any reason. Gemini and OpenRouter
   models are ranked together by the measured standing below, so a
   rate-limited Gemini day drops Gemini under a good OpenRouter model on its
   own.
4. **Never an API key, never a paid model.** `max_cost_usd` is 0 and
   `paid_fallback` is false; a reported cost above 0 is a named stop.

**Why:** your decisions of 11 Oct 2026 ("nothing should be paid") and 12 Oct
2026 ("use my claude subscription usage in advance of the $0 openrouter").

**Which lanes carry it:** every workflow whose stage can reach the router. The
list is not kept here; `loop/tests/test_claude_subscription_route.py` derives it
from the code and fails if any such lane lacks the pinned CLI or either secret
(`CLAUDE_CODE_OAUTH_TOKEN`, `GEMINI_API_KEY`), or if any other lane passes one. The "Calls a model?" column above is the
same derivation.

**Rotating the token** (valid one year; the current one was created 12 Oct
2026, so it expires **12 Oct 2027**):

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN -R seq23/how-we-know
```

**When it is missing or expired** nothing breaks and nothing emails you: every
call falls through to the $0 route on its own. The trace is one
`[claude-route] … — falling back to the $0 route` line in the stage log, and the
print-only step **"Probe the Claude subscription tier"** in each lane shows
`success is_error=False 'ok'` when the token works.

### Fallback standing

The order of the free models (Gemini when keyed, then the OpenRouter list) is
**measured, not guessed**. `config/llm_routing.json` is the roster; the ledger
only reorders it and never adds a model.

- **What is recorded:** every free-model call outcome (answered, empty, error,
  rate-limited, timeout) and every Monday draft verdict (passed, failed
  validation) lands in `loop/state/llm_route_ledger.json`, last 20 per model,
  with time, latency and lane. Never a prompt, draft, key or the subscription.
- **How it ranks** (last 12 events per model; pass rate = passed ÷ judged,
  where judged = passed + failed validation + empty + error + timeout +
  rate-limited; an answer with no verdict yet counts as neither):
  1. **MEASURED-GOOD** — at least 4 judged, pass rate ≥ 0.5: best pass rate
     first, then fastest.
  2. **UNMEASURED** — fewer than 4 judged: config order.
  3. **MEASURED-BAD** — at least 4 judged, pass rate < 0.5: best pass rate first.
  No data at all = exactly the config order. A lane's preferred model (the one
  that answered the last attempt on a topic) still goes first unless it is
  MEASURED-BAD; then it keeps its measured place.
- **See it:** `python3 loop/llm_router.py standing`. The Monday lane prints the
  same table (`[free-route standing]` lines) at stage start, so each run log
  shows the order it used.
- **Seed (12 Oct 2026):** the config order is the starting point,
  with `nvidia/nemotron-3-ultra-550b-a55b:free` moved to the bottom because on
  run 38235183608 it returned an empty answer and cost the Monday lane ~5
  minutes before the route moved on. The ledger started empty; the first runs
  measure the rest.
- **The pin:** `loop/tests/test_measured_fallback.py`. Concurrent lanes'
  ledger commits merge as a union (`loop/tools/merge_route_ledger.py`).

**The Monday authoring budget** (PR #159): `AUTHORING_BUDGET_MIN` in
`loop/draft.py` is the wall-clock budget for everything the Monday lane
authors; no draft attempt starts past it, and the job ceiling in
`loop-mon-draft.yml` is that budget + 20 minutes.
`loop/tests/test_mon_draft_authoring_budget.py` pins the two together. The
budget must end before the 09:00 upload lane, which waits behind it in the
`loop-state` queue. Read the numbers from those two files; this page describes,
the code decides.

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

- **Claude is not part of the running system's decisions.** A model (your
  Claude subscription first — see *Model route*) writes and translates scripts,
  but nothing calls a model to decide whether to publish. Close the terminal and the channel keeps going.
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

## Free model bench

- **What it measures:** which $0 models can actually write a script. `loop/bench_free_models.py`
  sends two real topics that need authoring (one per allocated domain) to each candidate with the
  real prompt (`author.build_prompt`) and judges them with the real checks (`author.shape_problems`,
  `author.dead_urls`, finish_reason): one draft, one correction turn built exactly as `author.draft()`
  builds it, then up to 6 "go 2x" expansion turns on the best draft that failed on length alone.
  Every request is pinned to the model under test (no fall-through), carries max price 0, and
  stops the bench if a cost above 0 is reported. Gemini (Google AI Studio free tier,
  `.secrets/gemini_key.txt`) is benched alongside the OpenRouter `:free` models.
- **How to run:** `.venv/bin/python loop/bench_free_models.py` (the judges need numpy; the venv has
  it, and a zero-cost preflight stops before any request if it is missing). `--dry-run` prints the
  plan; `--rerank <json>` rewrites the outputs with 0 requests. Hard cap 60 OpenRouter requests
  plus 8 Gemini per run. The key is not on OpenRouter's free tier (`is_free_tier` false: credits
  were bought once, so `:free` models allow 1,000 requests/day, 20/min).
- **When to re-run:** whenever `config/llm_routing.json`'s roster changes, or a new `:free` model
  appears at https://openrouter.ai/api/v1/models.
- **Results:** `research/free_model_bench/<date>.{json,md}`, also copied to
  `~/GitHub/.wt/free_model_bench_latest.json`. `loop/tests/test_free_model_bench.py` pins them.
- **Verdict, 12 Oct 2026:** nothing at $0 passed: no draft failed on length alone, so lengthening
  is not the fix; the drafts that clear the 1,446-word floor fail on dead citations and unparseable
  directives. Closest is `gemini-2.5-flash` (~19 s, two dead URLs from a pass); six of eleven models
  never returned a script, mostly because hidden reasoning ate the whole 16,000-token budget.
