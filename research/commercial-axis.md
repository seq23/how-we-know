# The commercial axis — what could be measured, and what could not

**Status: PROPOSAL and measurement. `pov/topic-taxonomy.json` is unchanged and
not touched by this work.** Everything here sits beside
`research/proposed-taxonomy.json`, in the same advisory position.

Written 2026-09-03, to answer one question before a second content domain is
chosen: **which of the 20 candidate domains have real advertiser demand behind
them, and does deep sea?**

---

## The headline, before the method

- **No per-domain RPM figure appears anywhere in this work, and none should be
  invented.** YouTube RPM is not publicly measurable at niche granularity. The
  only published figure that covers this material is a coarse
  *Education & Science* bucket whose internal spread is 8.4× ($2.31–$19.50
  around a $10.22 median). A single number drawn from inside that band tells
  you nothing.
- **Advertiser bid density (CPC) could not be measured at all.** No
  keyword-cost source exists on this machine. Three routes were tested and all
  three are confirmed closed — see *What could not be measured* below. That
  cell is **left empty**, not filled with an estimate.
- **Audience geography WAS measured**, worldwide, for all 20 domains, by the
  same 8 seeds that produced each domain's demand score. See
  `research/geography.json`.
- **Commercial-intent surface WAS measured**, over the 13,365 clean queries
  already mined into `research/broad_mined.json`. See
  `research/commercial.json`.

Both of the latter are **proxies**, and they are labelled as proxies
throughout. Neither is RPM. The gap is stated in each file.

---

## What could not be measured, and why

### 1. Keyword cost (CPC). CONFIRMED unavailable.

A full sweep of this machine found **no API integration to any keyword tool** —
no Ahrefs, SEMrush, Moz, Google Ads / Keyword Planner, DataForSEO, Serpstat,
SpyFu, Ubersuggest, KeywordsEverywhere, SE Ranking or Similarweb. Specifically:

| Checked | Result |
|---|---|
| `~/.zshrc`, `~/.zprofile`, live shell env | no keyword-tool variables |
| `google-ads.yaml`, any `developer_token` | absent from the machine |
| `~/.config/gcloud` | credentials present, no AdWords/Google Ads scopes |
| macOS Keychain, 1Password CLI | no vendor entries; `op` not installed |
| `how-we-know/.secrets/` | OpenRouter + YouTube only |
| `~/.zsh_history` | zero commands referencing any keyword vendor |

The portfolio's prior **"volume × 12 × CPC" annual-value proxy** was located.
It is **not live code**. Its inputs are `data/demand/measured_demand.json`
files across six sibling repos, all populated from **one hand-run SEMrush
export dated 2026-08-24**, covering roughly 21 queries with a non-zero CPC
across the entire portfolio — employment-verification, HRT, webinar-production
and Memphis-events terms. **None of it touches any of these 20 domains, and
there is no refresh path.** Reusing it here would be borrowing an unrelated
spreadsheet's authority.

> This is the point at which the honest move is to stop rather than
> substitute. A modelled CPC would have looked exactly like a measurement in
> the final table, and would have been the single most load-bearing number in
> the decision.

### 2. Search-ad presence as a stand-in for CPC. CONFIRMED closed.

If bid *prices* are unavailable, bid *presence* would still answer the question
the brief calls out as mattering most — the share of queries **nobody bids on
at all**. Two free routes were tested against live endpoints on 2026-09-03:

| Route | Method | Result |
|---|---|---|
| **Bing SERP** | fetched `bing.com/search` for commercial and curiosity queries; counted ad containers | **No ads served to an unauthenticated client.** `car insurance quote` — the most commercially contested query available — returned the identical ad-free template as `anglerfish` across **5 repeat trials each**. The signal is a constant, so it carries no information. |
| **DuckDuckGo HTML** | fetched `html.duckduckgo.com/html/`; counted `result--ad` blocks | **Worked for exactly 2 queries, then a CAPTCHA.** Verified after a 45-second pause: *"Please complete the following challenge… Select all squares containing a duck."* Unusable at any scale, let alone 13,365 queries. |

Both are recorded as CONFIRMED negatives with the method stated, rather than as
"we looked and there was nothing".

### 3. The channel's own audience geography. Genuinely unavailable, not yet.

The strongest possible evidence for the geography question would be
`@howweknowdeep`'s own YouTube Analytics — real viewers of real deep-sea
videos. `loop/state/measurement.json` currently shows **0 videos measured**
(`retention_checkpoint: no_data`). There is no audience data to read yet. This
is the one gap that **closes by itself**: once episodes have run, the channel's
own country breakdown replaces the Trends proxy entirely and should be
preferred over it.

---

## What WAS measured

### Axis A — audience geography (`research/geography.py`)

- **Source:** Google Trends `explore` + `comparedgeo`, worldwide, `today 12-m`,
  COUNTRY resolution. Free, keyless, the endpoints behind the Trends UI.
- **Budget:** exactly the 8 seeds that produced each domain's record in
  `broad_mined.json`. Same seeds, same window, same resolution, all 20 domains.
- **The metric:** `tier1_skew = mean(index over a fixed Tier-1 basket) /
  mean(index over a fixed Tier-3 basket)`.

**What it is not.** Trends normalises each country's interest against *that
country's own* total search volume. It is a **per-searcher propensity**, not a
headcount. It therefore **cannot** say "X% of this audience is Tier 1" — that
would need per-country search volumes Trends does not expose. It can only say
which domains lean more Tier-1 than which others, measured identically. The
first raw pull for `deep sea` ranked **American Samoa** first: that is the
metric working as designed, and exactly why it must not be read as audience
share.

**The basket membership is a stated convention, not a measurement.** It encodes
the widely-reported ordering of ad rates by market. Every per-country index is
retained in `geography.json` so a reader can disagree and recompute.

### Axis B — commercial-intent surface (`research/commercial.py`)

Advertisers bid where buying, hiring and enrolling language appears. So: across
each domain's clean mined queries, what share carry commercial-intent language
at all, and in which advertiser category?

- **13,365 clean queries examined**, all 20 domains, identical modifier list,
  identical denominator, **no new network requests**.
- **The `zero_commercial_share` is the load-bearing number**, not the mean. A
  domain nobody expresses any buying, hiring or enrolling intent around is a
  domain with an audience and no product behind it.

**Three gaps that stay open, and are recorded in the file:**

1. **Intent language is not a bid.** No bid is observed anywhere in this work.
   It measures the surface an advertiser could want, not any advertiser
   wanting it.
2. **The corpus is YouTube autocomplete, not Google web search.** Commercial
   intent is systematically under-represented there — people buy on Google and
   browse on YouTube. Absolute rates are low across the board; **only the
   ordering between domains carries information.**
3. **The explainer viewer and the commercial searcher** are linked by
   inference, not observation.

**The modifier list was corrected against its own output.** A first pass was
inspected query by query and six term groups were removed as false positives —
`vs / versus / comparison` (the commonest explainer format on YouTube:
*"angler fish vs shark"*, *"container ship vs pirates"* — it was **20 of deep
sea's 42 hits**), `company` (matched *"anglerfish in animal company"*, a VR
game), `class` (the biological rank), `simulator` (games), bare `kit` (*"how
it's made kit kat"*), and `school`. Every removal is recorded in
`commercial.json` with the observed false positive quoted, so the correction
can be checked rather than trusted.

**The correction cut against the comfortable answer.** It moved deep sea *down*
from 0.031 to 0.011 and ocean technology from 0.049 to 0.032 — the domains
whose scores it would have been convenient to protect.

---

## The combined table — all four axes

Sorted by the new commercial axis. **The two right-hand columns are the new
work; they are proxies, not RPM.**

| domain | demand | opportunity (n) | views/sub | Tier-1 skew | commercial rate | zero-commercial | named advertiser category |
|---|---|---|---|---|---|---|---|
| logistics-how-things-move | 0.385 | 0.511 (4q) | 0.15 | 1.38 | **0.092** | 90.8% | career, education |
| materials-and-manufacturing | **0.659** | 0.624 (6q) | 3.16 | 1.40 | **0.047** | 95.3% | education *(+ tooling, career)* |
| paleontology-extinction | 0.442 | 0.650 (6q) | 0.66 | 1.85 | 0.042 | 95.8% | education |
| archaeology-ancient-tech | 0.294 | 0.233 (2q) | 0.65 | 2.09 | 0.039 | 96.1% | education |
| energy-and-power | 0.291 | 0.665 (2q) | 2.41 | 2.09 | 0.037 | 96.3% | career |
| ocean-technology | 0.296 | 0.488 (2q) | 3.36 | 4.34 | 0.032 | 96.8% | local service *(contaminated — see below)* |
| engineering-failure | 0.198 | 0.648 (1q) | 1.23 | 2.32 | 0.027 | 97.3% | **none** |
| space-astronomy | **0.738** | 0.650 (6q) | 0.81 | 1.80 | 0.016 | 98.4% | education |
| measurement-and-dating | 0.348 | 0.615 (4q) | 0.56 | *(empty — 2/8 seeds)* | 0.014 | 98.6% | **none** |
| earth-science-geology-volcano | 0.352 | 0.613 (4q) | 1.34 | 1.57 | 0.013 | 98.8% | **none** |
| natural-history-adaptation | 0.306 | 0.653 (2q) | 0.32 | 1.01 | 0.013 | 98.8% | **none** |
| physics-fundamentals | **0.736** | 0.506 (6q) | 1.05 | 1.16 | 0.012 | 98.8% | education |
| **deep-sea-ocean-science** | **0.673** | 0.635 (6q) | **10.41** | 1.68 | **0.011** | **98.9%** | **none** |
| animal-senses-cognition | 0.286 | 0.638 (2q) | 1.50 | 1.74 | 0.010 | 99.0% | **none** |
| polar-extreme-environments | 0.250 | 0.580 (1q) | 1.82 | 2.83 | 0.008 | 99.2% | **none** |
| marine-geology | 0.320 | 0.633 (4q) | 0.45 | 1.65 | 0.006 | 99.4% | **none** |
| weather-and-storms | 0.340 | 0.397 (4q) | 0.20 | 2.01 | 0.006 | 99.4% | **none** |
| expedition-history | 0.307 | **0.722** (2q) | 2.06 | 2.35 | 0.004 | 99.7% | **none** |
| infrastructure-megaprojects | 0.413 | 0.567 (4q) | 1.42 | *(empty — 2/8 seeds)* | 0.002 | 99.8% | **none** |
| incident-analysis | 0.432 | 0.644 (6q) | 3.85 | 4.20 | 0.001 | 99.9% | **none** |

**Column provenance and equality of budget — they are not the same:**

| axis | source | equal budget? |
|---|---|---|
| demand | `proposed-taxonomy.json` | **yes** — 8 seeds, 216 requests each |
| opportunity | `competition.json` | **NO** — 1 to 6 queries per domain; the file itself says "treat a 2-query domain as a smoke test, not a measurement" |
| views/sub | `competition.json`, median views ÷ median subs | **NO** — same unequal sample |
| Tier-1 skew | `geography.json` (new) | **yes** — the same 8 seeds, all 20 domains |
| commercial rate | `commercial.json` (new) | **yes** — 13,365 clean queries, identical modifier list |

**Two cells are deliberately empty.** `measurement-and-dating` and
`infrastructure-megaprojects` returned usable region data for only 2 of 8
seeds — below the floor of 3. They are not scored 0 and must not be ranked as
if they were measured.

### Views-per-subscriber has an expiry date

It measures **how far a video travels without an audience carrying it** — the
ratio of what incumbents' videos get to how many subscribers they have. That is
decisive at zero subscribers, because it is the only way the first videos are
seen at all. It is **much less decisive once an audience exists**, and a
second-niche decision is made *after* she has one. Deep sea's 10.41 — three
times the next domain — is the single strongest number in this table and it is
the one whose relevance is expiring. It should not carry the second-niche
decision the way it carried the first.

---

## The geography finding

**Deep sea was suspected to be globally diffuse. It is not.** Measured at
**1.68** — Tier-1 leaning, 12th of the 18 measurable domains. The suspicion is
refuted, not confirmed.

But the more useful finding is the shape of the whole column:

- **Every measurable domain scored above 1.0.** The lowest were
  `natural-history-adaptation` at 1.01 and `physics-fundamentals` at 1.16 —
  those are the genuinely globally diffuse ones. Nothing is Tier-3 weighted.
- **The spread is real but not decisive between neighbours.** 1.16 to 4.34 is a
  3.7× range across the column, but a 1.68 versus a 1.80 is noise.
- **Deep sea is mid-pack, not a liability.** Choosing a second domain to escape
  a Tier-3 audience would be solving a problem that was not measured to exist.

The prior pass's suspicion — that geography plausibly outweighs the niche label
entirely — **survives** as a general claim about RPM, but does not single out
deep sea as the loser.

---

## Commercial follow-through — judged and stated

This section is **JUDGEMENT informed by the measured language**, not
measurement. Labelled as such.

| verdict | domains | the judgement |
|---|---|---|
| **A named advertiser category with real depth** | materials-and-manufacturing, logistics-how-things-move, energy-and-power | Course platforms and universities for materials (34 education queries: *"ic fabrication course"*, *"material science engineering lecture"*, semiconductor exam/revision terms); employers and maritime recruiters for logistics (39 career queries: *"cargo ship jobs salary"*, *"container ship interview questions"*); nuclear employers and operator-training for energy (*"nuclear reactor operator training"*, *"nuclear power plant job"*). Equipment suppliers appear too (*"semiconductor manufacturing equipment"*, *"wafer fabrication equipment"*). These are audiences with an industry attached. |
| **A thin but real education category** | paleontology-extinction, archaeology-ancient-tech, space-astronomy, physics-fundamentals | Enrolment language exists — syllabus, exam, degree, lecture — but at 1.2–4.2% and with no employer or supplier behind it. Publishers and ed-tech, not industry. |
| **Curiosity with no product behind it** | **deep-sea-ocean-science**, incident-analysis, expedition-history, weather-and-storms, marine-geology, polar-extreme-environments, animal-senses-cognition, natural-history-adaptation, earth-science-geology-volcano, engineering-failure, measurement-and-dating, infrastructure-megaprojects | No advertiser category clears even 10 queries. These are audiences an advertiser has nothing to sell to. It is a legitimate verdict and it applies to the current niche. |

**On deep sea specifically. 98.9% of its 1,358 clean queries carry no
commercial language whatsoever.** The 15 that do are *"deep sea jobs"*,
*"marine science careers"*, *"marine science a level"* — and two of them are
*"marine science chittagong university"* and *"marine science job sector in
bangladesh"*, i.e. the small commercial surface that does exist is itself
Tier-3. **Deep sea is curiosity with no product behind it.** That is not an
argument against the channel — a large, cheap, well-travelling audience is
worth having — but it is an argument against expecting the *first* niche to
carry the revenue, and a reason the second one should be chosen differently.

**Incident-analysis is the sharpest warning in the table.** Strong demand
(0.432), strong opportunity, 3.85 views/sub, the second-highest Tier-1 skew
(4.20) — and **99.9%** zero-commercial, one query out of 713. A domain can look
excellent on every audience axis and have nobody to sell to.

---

## Recommendation

**Take `materials-and-manufacturing` as the second domain.**

- **It is the only domain that is top-4 on demand AND has a named advertiser
  category with depth.** Demand 0.659 (2nd of 20), opportunity 0.624 on a full
  6-query sample, views/sub 3.16 (3rd), Tier-1 skew 1.40, commercial rate 0.047
  (2nd, and the top domain on that axis is weak everywhere else).
- **Its commercial surface is the most diverse of any domain** — education,
  career and tooling all present, meaning course platforms, employers *and*
  equipment suppliers. Every other high-commercial domain has exactly one.
- **It is already flagged as missed by the current taxonomy** in
  `proposed-taxonomy.json`, so this is not a new claim, only a newly-supported
  one.
- **It shares the method spine.** "How are microchips made", "why is steel
  stronger" are *how-we-know* questions; the tier-specific POV lines will need
  the ~20-minute top-up interview the taxonomy already requires, but the
  evidence-first format transfers without modification.

**Runner-up: `energy-and-power`** — the strongest career signal after logistics
and 2.41 views/sub, but its opportunity score rests on **2 queries** and should
be re-measured before it is trusted.

**Rejected despite scoring well:** `logistics-how-things-move` tops the
commercial axis by 2×, and it is the wrong choice — **views/sub of 0.15, the
worst in the table**, and demand 0.385. Its videos do not travel. Advertiser
interest in an audience you cannot reach is worth nothing.

**Not recommended on this evidence:** `space-astronomy` and
`physics-fundamentals`, the two demand leaders. Both are near the bottom of the
commercial axis (98.4% and 98.8% zero-commercial), and physics is the second
most globally diffuse domain measured. They would repeat the first niche's
pattern — a large audience with nothing behind it.

---

## The figures I would not bet on

Stated plainly, because the recommendation should not rest on them.

- **Any opportunity score with n ≤ 2.** That is `engineering-failure` (1
  query), `polar-extreme-environments` (1), and `expedition-history`,
  `archaeology-ancient-tech`, `energy-and-power`, `ocean-technology`,
  `natural-history-adaptation`, `animal-senses-cognition` (2 each).
  `expedition-history` leads the whole opportunity column at 0.722 **on two
  queries**. The source file already warns about this; the warning has not been
  carried into any downstream table until now.
- **`ocean-technology`'s numbers are contaminated by a homonym.** Its Tier-1
  skew of 4.34 — the highest measured — and its "local service" advertiser
  category both come substantially from **water pumps**, not ocean technology:
  *"submersible pump repair"*, *"submersible motor repair"*, *"submersible vs
  monoblock"*. The seed `submersible` does not mean what the domain means.
  **I would discard this row rather than rank it.**
- **`incident-analysis`'s skew of 4.20 rests on 3 usable seeds**, 2 more having
  returned no Tier-3 data at all. Directionally right, numerically soft.
- **Every absolute commercial rate.** The corpus is YouTube autocomplete, where
  commercial intent is under-represented. A 4.7% rate does not mean 4.7% of
  that audience is in-market. **Only the ordering is informative**, and even
  the ordering compresses badly below ~1%: the gap between 0.006 and 0.004 is
  not a finding.
- **The Tier-1/Tier-3 basket membership.** A stated convention, not measured.
  Every per-country index is kept in `geography.json` so the ratio can be
  recomputed against a different basket.
- **Anything at all resembling RPM.** There is none here, and the two proxies
  in this table are separated from realised revenue by advertiser bid density
  (unmeasured), ad load, seasonality, video length and watch time.

## What would actually close the gap

- **The channel's own YouTube Analytics country breakdown**, once episodes have
  run. It replaces the geography proxy with a measurement of real viewers and
  costs nothing. `loop/state/measurement.json` shows 0 videos measured today.
- **One month of Google Ads Keyword Planner access**, which would make CPC and
  volume measurable directly and turn the empty column into a real one. It is
  the only genuinely missing capability, and it is cheap.
