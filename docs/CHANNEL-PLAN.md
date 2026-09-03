# How We Know — the original plan

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

**Target: 4 long-form videos per week and 9 Shorts per week.** Owner decision,
2026-09-02, raised from 2 and 4. Set in `loop/config.json`, never hardcoded. 4 is also
the taxonomy ceiling and is never exceeded.

**The loop raises itself in two evidence-gated steps, and neither is a date.**

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

**Why it does not start now.** Fourteen episodes are uploaded, private and dated,
publishing gaplessly to 2026-10-20. The slot allocator only ever issues dates *after*
the last one already on the calendar, and no lane rewrites a scheduled row — so the new
cadence can only govern episodes that do not exist yet. The first 4/week slot is Friday
23 October 2026. `validate.v20_cadence-schedule` proves this continuously rather than
asserting it.

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

After the first four have data: **average view duration against the ~10.5 minute
runtime.** If viewers consistently leave in the first two minutes, the format is wrong
and everything above is built on a bad assumption. This must surface prominently, not as
a number buried in JSON.

The runtime floor is 10.5 minutes and three places must agree on it —
`loop/config.json` `retention.runtime_minutes`, `loop/author.py` `TARGET_WORDS = 2750`,
and the measured 150 words/minute between them. `loop/tests/test_runtime_coherence.py`
asserts they do, and **a cadence increase may not quietly shorten episodes to hit it.**

**YPP is a real climb:** 4,000 watch hours = 240,000 minutes. At 10.5 minutes and a
realistic 40% retention, roughly **57,000 views.** Frequency does not create demand —
and hours are not the binding half anyway; see Cadence above.

---

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

- **Retention data showing the 10.5-minute format fails.** Changes runtime and structure.
- **The compliance audit being granted or refused.** Changes whether publishing is
  hands-off or drag-and-drop.
- **Deep-sea demand actually declining** across several weekly measurements — not one.
- **The authoring lane failing to produce a validated script** by ~week 7. Cadence stays
  at 2 and the runway problem becomes real.
- **A test upload landing public.** Would mean the private-lock concern is moot and
  publishing is fully automatic today.
