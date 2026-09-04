# How We Know — the original plan


> **Schedule, cadence evidence and the loop's stage map live in [`docs/OPERATING-MANUAL.md`](OPERATING-MANUAL.md).** This file holds the guarded strategy; that one holds the operating detail and the studies behind the publish times.

**Locked 2026-08-30.** This is the reference document. When something in the pipeline
disagrees with this file, that is drift, and the pipeline is wrong until this file is
deliberately changed.

Every number here was measured, not assumed. Where a decision rests on judgement rather
than evidence, it says so.

---

## The channel

| | |
|---|---|
| Name | **How We Know** |
| Handle | **@howweknowdeep** |
| Channel ID | `UC5vZFZc15DIM6IrFwFgAECg` |
| Site | **https://howweknowdeep.com** |
| Google account | `cryptoclearr@gmail.com` |
| Cloud project | `how-we-know` (681552889891) |

**The premise:** each video answers one question and shows the instrument, the proxy, or
the observation behind every figure — and says plainly where the evidence stops. The
channel is a **method**, not a subject. Deep sea is the beachhead, not the ceiling.

**Hard rule:** nothing here associates with West Peek, Spry, Spry Labs, or `spry.vc`.
Sequoia L. Taylor's legal name appears only on private forms to Google where it is
required. No business cross-links, ever.

---

## Cadence

**Live: 4 long-form videos per week and 9 Shorts per week.** Owner decision,
2026-09-02, raised from 2 and 4; **set live on 2026-09-04** by the owner directly.
Set in `loop/config.json`, never hardcoded. 4 is also the taxonomy ceiling and is
never exceeded.

**Set by hand, not by the gates — and the difference is recorded.** The two
evidence-gated steps below are the AUTOMATIC path and they remain armed. Neither had
fired: both require `authoring_evidence()`, a script the OpenRouter authoring lane
itself produced and validated, and no such script exists yet. Manufacturing that
evidence to open the gate would have been a lie told to a guard, so the number was
set directly instead and `cadence.owner_set` in `loop/config.json` records who chose
it and when. An owner setting a number is a different act from the loop deciding it
has earned it; the config says which one happened. At 4 the automatic steps are
correct no-ops — 4 is also the ceiling, so if they ever fire they can only agree.

**The loop also raises itself in two evidence-gated steps, and neither is a date.**

1. **2 → 3** once the OpenRouter authoring lane has produced at least one script that
   passes full validation. Not "the lane exists" — a validated artifact.
2. **3 → 4** once, additionally, the **queue can carry it**: runway measured at 4/week
   must still be clear of `cadence.scale.requires_runway_weeks`.

**Why the Shorts half matters more.** Watch hours are not the binding constraint —
subscribers are, by roughly **12×**. This channel clears 4,000 hours with under 100
subscribers against a 1,000 floor. So the long-form raise buys hours that were coming
anyway (worth doing: an authored script is ~$0.06 and runtime multiplies hours
directly), while **Shorts are the only cheap lever on subscribers**, and 51 are already
cut and paid for.

**How the raise reaches the calendar: each domain gets its own days.** The ladder is
ranked by evidence — Sunday, Tuesday, Monday, Friday — and a cadence takes the first N
rungs, so raising 2 → 4 **adds** Monday and Friday and leaves Sunday and Tuesday exactly
where they were. `loop/domains.live_slots()` splits the week deep sea 2 / materials 2,
and `backfill.domain_weekdays()` hands deep sea its existing **Sunday and Tuesday** and
materials the two added days, **Monday and Friday**.

Because the two day-sets are disjoint, the second domain is **woven into the weeks the
first has already filled** rather than queued behind them: materials episodes air on
Mondays and Fridays from 7 September alongside a deep-sea run that continues on Sundays
and Tuesdays to 25 October. This replaced the older rule that every new slot must fall
after the last date on the calendar — correct while one domain held every publish day,
and the reason the first three materials episodes were initially dated 27 October to 3
November, a week *after* the last deep-sea episode instead of beside it.

**No dated row moves.** The allocator skips any datetime already spoken for rather than
anchoring past the whole calendar, so an episode already scheduled cannot be re-dated or
double-booked, and no domain can be handed another domain's day.
`validate.v20_cadence_schedule` proves all of that continuously — collision-freedom,
disjoint day-sets, correct weekday per domain, and a 24-hour minimum lead so the owner
can still watch an episode through before it airs — rather than asserting it.

**Why the queue-depth guard exists.** Raising cadence shortens runway. If the queue
cannot sustain 4/week the loop **refuses the raise** and says so as a
`CADENCE_SCALE_WITHHELD` named stop, rather than publishing at the old rate while
everyone believes it scaled. Publishing never halts — **going dark is worse than going
slower**, and the algorithm reads inconsistency as abandonment. The guard stands down on
its own when the queue refills, and re-engages if it thins, which is what makes the
scale reversible rather than a one-way bet.

**Why not 1:** frequency does not create demand, but it does buy more shots on goal.
Twenty videos nobody watches is zero watch hours; the value of frequency is that one
video hitting pulls the rest along.

---

## Topic selection — the gate

**High demand AND low competition. Both. A topic failing either test is killed, not
ranked low.**

- **Demand floor** — below it, excluded outright, never reaches the queue.
- **Saturation ceiling** — if the top-20 search results already answer the question,
  excluded.
- Thresholds are set from the actual distribution in the measured data, not from round
  numbers.
- The gate **hard-fails if it excludes everything**, and never passes a topic on an empty
  check.
- Killed topics are recorded **visibly** in `research/publish_order.json` with the
  measurement that killed them — so a bad kill can be seen and overruled.
- A kill resting on a marginal measurement is marked `killed_provisional`, with a note on
  what would settle it. **Wrongly killing a good topic is invisible** — a flop teaches
  you something, a video never made teaches you nothing.

### The finding that drives everything

> **Every opening is a "why does…" or "how does…" question.
> Every dead end is a "what is a…".**

Measured across all 20 scripts. `what is a frilled shark` and `what is a yeti crab`
returned **20/20 strong title matches, gap signal 0.0** — the questions are solved.
`why does black-smoker water not boil` returned **0/20 strong matches** with a median
incumbent of 2,800 subscribers.

---

## The publish queue

**The publish order is the ranking. There is no hand-picked head.**

Superseded 2026-08-31. Four episodes were pinned earlier that day, chosen from
opportunity data before the combined score existed. Once demand was measured properly,
two of them scored below episodes further down the queue, and the owner removed the pin:
*"why the fuck are we not doing the top 4 by score."*

Current top four, by `combined_score`:

1. What is the deepest part of the ocean — 0.685
2. Why many deep sea creatures are red — 0.562
3. Why deep sea creatures look so weird — 0.561 *(rendered, voiced, approved)*
4. How big is a colossal squid — 0.557

**The scores below #1 are close.** Only the top position is clearly ahead; 2 through 7
sit inside about 0.04 of each other, which is narrower than the measurement is precise.
Read the ordering as a ranking, not as a set of distinctions.

**Never filename order.**

**Killed as saturated:** `what is a frilled shark`, `what is a yeti crab`,
`what is a dumbo octopus`. Being reworked from identification questions into mechanism
questions, mined and scored through the same gate. **A rework that fails the gate kills
the subject** rather than being waved through because art already exists for it.

### Scoring

Two fields, both reported:

- **`opportunity_score`** — room for a new entrant. 50% title gap, 20% small incumbents,
  15% view ceiling, 15% staleness.
- **Combined score** — demand × opportunity, with a floor on each. This is what ranks.

**`seed_hits` is dead.** It measured seed-string length, not demand: 81% of multi-hit
queries got every hit from a–z variants of one seed. Never reintroduce it.

---

## The weekly loop

Runs **without the owner**. No approval step, no queue for her to review.

    mine → trend → score → gate → rank → publish

- Fresh `research/publish_order.json` every week. The queue is **not** frozen — topics
  saturate and trends move. A ranking fixed in August is wrong by October.
- **Quota-aware.** `search.list` costs 100 units against 10,000/day. Named stop on
  exhaustion; **never impute a score.**
- **A missing or stale ranking is a loud named stop — never a silent fallback to
  filename order.** That fallback would keep the loop looking perfectly healthy while
  publishing in a stale order. This is the "runs but inert" failure class and it is the
  single most likely way this plan degrades without anyone noticing.

**Owner involvement target: zero.** Blanket topic approval was given; the gate carries
her judgement. The only standing exclusions are hers: nothing adult, nothing morally
grey, nothing with legal exposure (health, personal finance, legal advice). Those live in
`pov/topic-taxonomy.json` and are not up for revision.

**The POV bank is her approved voice.** `pov/pov-bank.json`, from her own interview.
Selecting from it is a matching problem, not an approval.

---

## Publishing mechanics

**Uploads may land locked-private.** Google's docs say API uploads from an unaudited
project cannot be flipped public and cannot be appealed. **Unverified** — one test upload
settles it. A locked upload must surface as a **detected, named condition**. She must
never believe a video went live when it did not.

**OAuth app is `In production`** — refresh tokens no longer expire after 7 days.

**Two Google processes, deliberately treated differently:**

| | Decision |
|---|---|
| **OAuth app verification** | **Never pursue.** Exempt under 100 users, and it cannot unlock public uploads. Adding a logo is what triggers it — the logo has been removed. |
| **YouTube API compliance audit** | **File it** — the only lever for public API uploads. Free. Drafted at `docs/youtube-audit-application.md`. |

**File the audit only after 3–4 videos are published by hand.** Filing with zero videos
asks a reviewer to trust an empty channel. The application is honest about being small —
no claimed traction, no invented team — and honest is the only version worth filing.

**Never sign the demo-credentials waiver** over the account that owns the channel.

---

## Visuals — show the animal

**Owner note, 2026-08-31, after watching episode 1:** *"I would rather have more
animal pictures — the descriptions are happening and we have no animal photos of what
we are describing."*

Episode 1 was approved with this as the standing correction. **When the narration names
a species, the screen should show it.** Abstractions are the fallback, not the default.

**The imagery is public domain or CC0 only** — the channel is monetised, and CC-BY is
not a public-domain dedication. Every asset is verified live against source metadata and
re-hashed before it is drawn.

**The richest source is the expedition the channel is named after:** the 1887 *Report on
the Deep-Sea Fishes of H.M.S. Challenger*, illustrated by Robert Mintern (d. 1908) —
public domain worldwide, hundreds of species plates. Then NOAA (`PD-USGov-NOAA`, but
watch for burned-in DVR overlays), Smithsonian Open Access (CC0), and BHL scans.

**Credit what the image actually is.** A plate is labelled as a plate, not as a
photograph.

**Some species cannot be illustrated honestly and must not be faked.** *Mesonychoteuthis
hamiltoni* was described in 1925 from stomach contents — no historical plate exists and
every photograph is CC-BY-SA. The same holds for *Kiwa* and for whale falls. **A giant
squid plate captioned "colossal squid" is a lie told in pictures**, and on a channel
called How We Know that is the worst available failure. Where no honest image exists,
the drawn treatment stands and the script says what is and is not known.

## The measurement that could invalidate all of this

After the first four have data: **average view DURATION, in seconds, against each
video's own measured runtime** — never a configured constant. (Corrected 2026-09-03:
this used to divide by a hardcoded `retention.runtime_minutes`, which read 77% of true
retention once real renders diverged from that guess — see `loop/durations.py`.) If
viewers consistently leave in the first two minutes, the format is wrong and everything
above is built on a bad assumption. This must surface prominently, not as a number
buried in JSON.

The runtime TARGET is 10.5 minutes, with a **hard 10-minute floor** enforced on the
rendered file itself (owner decision, 2026-09-03) for every episode after the first 20.
Three places must agree on the speaking rate that turns a word budget into that many
minutes — `loop/config.json` `retention.runtime_minutes`/`runtime_floor_minutes`,
`loop/author.py` `NARRATION_TARGET_WORDS`/`NARRATION_FLOOR_WORDS`, and the MEASURED
speaking rate from `loop/durations.py` (144.58 wpm, range 133.5–154.2, derived from real
renders — never hardcoded) between them. `loop/tests/test_runtime_coherence.py` asserts
they do — by importing the real modules and checking the derivation, not by regexing a
literal number out of source, which is what let 150 wpm survive twenty episodes in the
first place. **A cadence increase may not quietly shorten episodes to hit it.**

**YPP is a real climb, and it now has two gates.** Standard YPP: 4,000 watch hours =
240,000 minutes. At 10.5 minutes and a realistic 40% retention, roughly **57,000
views.** Frequency does not create demand — and hours are not the binding half anyway;
see Cadence above. Expanded YPP (fan funding, no ads) needs only 500 subscribers and
3,000 hours and is materially nearer; see `loop/ypp.py` and RUNBOOK.md's "Monetisation,
both gates". The standard tier's 4,000-hour bar doubles to 8,000 on **2027-02-01** for
any channel not yet admitted — every hour banked before that date is worth two after it.

---

## A second domain: materials-and-manufacturing (added 2026-09-03)

**Runs ON TOP of deep sea, not instead of it, once the 4/week ceiling is reached** — deep
sea keeps Sunday and Tuesday, materials takes Monday and Friday. This is not "when deep
sea ends"; deep sea shows no sign of ending (see below) and keeps its own slots.

- **Why materials, and the honest trade.** It ranks lower than deep sea on demand but
  roughly **4x higher on commercial-intent share** (`research/commercial.json`) — an
  advertiser category deep sea barely touches. The trade, stated plainly: **materials
  converts subscribers roughly 3x slower than deep sea** (10.41 views/subscriber for deep
  sea vs. its own weaker ratio), so it is a revenue lever, not a growth lever.
- **Each domain owns its own source allowlist and visual identity.** Deep sea's approved
  organisations (`ORG_NAMES` in `loop/validate.py`) publish nothing about materials
  science; a new domain must name its own before it can cite anything, and needs its own
  palette and directive mix so a materials episode is visually distinguishable from a
  deep-sea one.
- **`loop/domains.py` is the only place a domain name may come from** —
  `research/proposed-taxonomy.json`'s `ranked_domains`, never invented ad hoc.
  `loop/monthly.py` allocates weekly slots between domains monthly, within the same
  `CHANGE_BOUNDS` fence every other knob respects, and requires **8 published episodes
  with analytics before a domain can be judged at all** — below that, allocation HOLDS,
  it does not average toward an even split.
- **A domain retires on its own scored queue decaying**, not a fixed episode count, and
  rotates to the next-ranked domain in the taxonomy automatically.
- **The format-is-wrong breaker is domain-aware.** Three bad months in ONE domain means
  that domain is wrong, not the format — see "The measurement that could invalidate all
  of this" above.

## When deep sea ends

**Not on a schedule — when the data says it is exhausted.** No sign of that: deep sea is
the only domain in the measured top four that is *rising*, with the highest depth per
query and the most breakout terms. It was chosen by reasoning and the data ratified it.

**Around week 7** the runway guard fires and a ranked list of what comes next is
produced — with two months of *actual* performance data behind it rather than pre-launch
guesses.

**Six of the original ten domains are not supported by the data**: `marine-geology`,
`expedition-history`, `natural-history-adaptation`, `ocean-technology`,
`archaeology-ancient-tech`, `engineering-failure`. The last returned **zero**
method-shaped queries across 54 identical probes — for a channel called How We Know, that
is disqualifying.

**Six domains were missed** and rank well: `physics-fundamentals`,
`materials-and-manufacturing`, `paleontology-extinction`, `infrastructure-megaprojects`,
`logistics-how-things-move`, `measurement-and-dating`. Note the last — smallest surface
but the purest, and it is the channel's own premise as a subject.

**Caveat that still stands:** domain rankings are demand-side only. A domain may rank
high *because* it is saturated. Do not act on that table without scoring competition
first.

---

## Cost

**$0 recurring**, except:

| Item | Cost |
|---|---|
| `howweknowdeep.com` | ~$10–12/year |
| OpenRouter authoring | Per-draft, logged |

Everything else — hosting, rendering, voice, thumbnails, research — is free and stays
free. Voice must remain on MIT-licensed weights; **CC-BY-NC and CPML models are
unusable** because the channel will be monetised.

Imagery is **public domain only**, verified live against licence metadata, with a rights
guard that re-hashes every asset before use. CC-BY is not a public-domain dedication.

---

## What would change this plan

Listed so that changing it is a decision, not a drift:

- **Retention data (average view DURATION, not percentage) showing the format fails in
  EVERY judgeable domain.** Changes runtime and structure. A duration streak in ONE
  domain, with others holding, changes that domain's allocation instead — see "A second
  domain" below.
- **The compliance audit being granted or refused.** Changes whether publishing is
  hands-off or drag-and-drop.
- **Deep-sea demand actually declining** across several weekly measurements — not one.
- **The authoring lane failing to produce a validated script** by ~week 7. Cadence stays
  at 2 and the runway problem becomes real.
- **A test upload landing public.** Would mean the private-lock concern is moot and
  publishing is fully automatic today.
- **Materials-and-manufacturing's scored queue decaying** below
  `domains.queue_exhausted_below` after it starts. It retires and the next-ranked domain
  in `research/proposed-taxonomy.json` takes its slots — never a fixed episode count.
