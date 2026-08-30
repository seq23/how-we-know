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

**2 videos per week.** Set in `loop/config.json`, not hardcoded.

**Escalates to 3/week automatically** on one condition: the OpenRouter authoring lane
has produced at least one script that passes full validation. Not "the lane exists" — a
validated artifact. The loop flips itself; the owner does not decide it.

**Why 2 and not 3:** 17 scripts at 2/week is ~8.5 weeks, which is enough runway for the
authoring lane to prove itself. At 3/week the backlog burns in under 6 weeks, and if
authoring is not ready the channel goes dark. **Going dark is worse than going slower** —
the algorithm reads inconsistency as abandonment.

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

**Pinned head** — owner override, marked as such, falls away once published:

1. How big is a colossal squid
2. How do people reach Challenger Deep
3. Why does black-smoker water not boil
4. Why some deep sea creatures are transparent

Everything after position 4 ranks by combined score. **Never filename order.**

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

## The measurement that could invalidate all of this

After the first four have data: **average view duration against the ~7.5 minute
runtime.** If viewers consistently leave in the first two minutes, the format is wrong
and everything above is built on a bad assumption. This must surface prominently, not as
a number buried in JSON.

**YPP is a real climb:** 4,000 watch hours = 240,000 minutes. At 7.5 minutes and a
realistic 40% retention, roughly **80,000 views.** Frequency does not create demand.

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

- **Retention data showing the 7.5-minute format fails.** Changes runtime and structure.
- **The compliance audit being granted or refused.** Changes whether publishing is
  hands-off or drag-and-drop.
- **Deep-sea demand actually declining** across several weekly measurements — not one.
- **The authoring lane failing to produce a validated script** by ~week 7. Cadence stays
  at 2 and the runway problem becomes real.
- **A test upload landing public.** Would mean the private-lock concern is moot and
  publishing is fully automatic today.
