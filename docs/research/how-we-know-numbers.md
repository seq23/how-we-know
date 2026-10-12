# How We Know Numbers

Repo copy of https://claude.ai/artifact/RrPVjRUBf8WDxSy7Cq5Qgf (v1.3, 12 Oct 2026, final for the day). Numbers from the live
YouTube Analytics API and the repo's own state. The page is the living version.

## 1. The channel, 90 days to 11 Oct 2026

- **Views** 3,080: Shorts 2,854 (93%), long-form 215.
- **Watch time** 831 minutes. Long-form average view duration 137 s against a 146 s floor; 11 of 18
  measured episodes lose the average viewer inside two minutes. Loop verdict since W39: FORMAT PROBLEM.
- **Subscribers** 26 gained, 1 lost; 18 of the 26 arrived 3–4 Oct.
- **Partner Program** 4 of 3,000 watch hours; 25 of 500 subscribers.
- **Long-form per video** median 6.5 lifetime views over 20 measured. Best: quenching steel 45,
  silicon wafer 22, self-healing materials 19, creepier deeper 19, titanium 17.
- **Inventory** 45 scripts; 39 finished episodes, all uploaded (23 aired since 1 Sep, 15 dated through
  8 Nov); 81 Short cuts on the Mac, 38 published; 13 deep-sea and 24 materials topics ranked but unwritten.
- **Cost** ~1.4 Mac-hours per episode; cash $0 since 3 Oct; quota 2,201 units per episode, 1,700 per Short.

## 2. Why views fell

| ISO week | Shorts published | Shorts views | Long-form views | Subs |
|---|---|---|---|---|
| W36 | 6 | 814 | 2 | 2 |
| W37 | 14 | 1,013 | 15 | 2 |
| W38 | 11 | 369 | 63 | 2 |
| W39 | 3 | 181 | 34 | 0 |
| W40 | 3 | 231 | 60 | 18 |
| W41 | 1 | 246 | 41 | 2 |

Views track Shorts output almost one for one; long-form never passed 63 views in a week at any
cadence. On 21 Sep the Mac's nightly batch first stopped on a Shorts validator (two cuts with the wrong
footage credit, one with its caption band) and refused to shelve any Short while those three failed.
Target 9 a week; output fell to 1.

## 3. Why nothing told you

1. **The Mac's stop had nowhere to go.** SHORTS_UNVERIFIED is "needs a human", but the batch runs under
   launchd; the issue-and-email path exists only inside GitHub Actions. It went to `batch.log` nightly.
2. **The cloud lane called an empty shelf normal.** NO_SHORTS_SHELVED is self-resolving with a 7-day cap;
   three Shorts slipped through on 3 Oct and reset the count.
3. **The Sunday digest's verdict never counted Shorts.** They appeared only under "self-resolving
   stops: normal operation, page nobody".

## 4. What changes (12 Oct 2026)

Shelf decoupled (a bad cut holds only itself); the three cuts fixed at source; **drain at 2 a day**
(owner's call) while the verified shelf holds two weeks or more, then 9 a week; the Mac files a deduped
issue and commits a stop record on a needs-human stop; empty-shelf stop escalates after 2 days; a
dry-shelf stop when the trailing week is under target; the digest shows Shorts published vs target and
shelf depth, yellow one short week, red two; measurement repaired (monthly review month boundary,
append-only history, opening-experiment eligibility, per-Short metrics, CTR where the API allows, a
weekly channel verdict).

**The writing lane moves into the quiet window** (owner's idea, 12 Oct): Gemini 3.5 Flash answered 503
"overloaded" at 10:03 and 10:13 UTC, when Europe and India are at work and free-tier traffic is shed
first. The Monday draft cron moves from 10:00 UTC (5 a.m. Central) to 05:00 UTC (midnight Central,
Sunday night into Monday), still after Sunday's rank lane. The slot before the 9 a.m. Central upload lane
widens from 4 h to 9 h, so the authoring budget rises from 210 to 480 minutes (ceiling 500). The route
ledger timestamps every outcome; two or three Mondays will show whether the 503s went away.

**Landed by the end of 12 Oct:** shelf decoupled and drain 2/day at 19:00 and 21:00 CT (#169; 40 Shorts
pushed to R2, backlog about 10 days); Monday lane at 05:00 UTC, budget 480, ceiling 500 (#171); Shorts and
a channel verdict in the digest (#166); plain-words digest subject, worst problem first, with the action
(#177, #182: W39–W41 read "🟢 Stalled" under red bodies because a variable was reused); every stop code has
a plain sentence; the Mac never sleeps on AC (`pmset -c disablesleep 1`; on battery a closed lid still
sleeps it) and the nightly batch resumes on wake (#175; the CI sweep's resume lives in seq-bin); the monthly
email (#176). W42 digest, issue #183: "🔴 Publishing is halted: the safety switch tripped Mon 12 Oct because
a quality check failed — needs you: check the Mac's nightly batch — 2026-W42". First monthly email, issue
#179: "Monthly: 7 episodes + 4 Shorts published in October so far (to 12 Oct); no pivot rule triggered".

## 5. Long-form cadence: the research

Owner decision 2 Sep 2026: 4 a week, the ceiling. Reviewed 12 Oct: **4 holds.**

- AIR Media-Tech 2026, 18,000 channels, Education niche (134 channels, 100K–1M monthly views):
  median subscribers by uploads/month 2–5 → 116K; 5–10 → 114K; 10–20 → 108K; 20–40 → 58K. Four a
  week (17/month) is inside the flat zone, below the cliff.
- OverseerOS, 168 breakout channels: long-form breakouts under 10K subs posted a median 13/month;
  survivors only.
- vidIQ, 10.2M channels above 1K subs: more uploads correlate with faster growth at every tier.
- Guides: consistency over volume. No study measured long-form-only growth under 1K subscribers.

## 6. Pivot and format changes

Nothing is ever deleted; uploads are private and dated; a dated episode can be re-dated without
re-uploading; the cadence is one config value. A niche change touches the taxonomy ranking, per-domain
queues, allocation, source allowlists and palette, and ~20 minutes of POV interview; renders stay valid.
Adding to the picture means re-rendering (~12 min each, audio kept) and a new upload; metadata changes
need no re-render. Existing rules: topic kill at title-gap ≤ 0.3 or demand < 0.16; domain swap when its
queue decays below 4 after 8 measured episodes; slot moves need 8 measured each and a 30 s AVD spread;
opening test keeps a variant only if its AVD beats the old cohort. No channel-level keep/kill/pivot rule
exists yet; the weekly verdict block (#166) is the first step, and the monthly email (#176) reports every
existing rule with its numbers each month, which is how the pivot research reaches the owner.
