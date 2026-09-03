# Decision log

Dated entries only. Every date and commit hash below was checked against
`git log`, not recalled — see each entry's "Verified" line. This file is
append-only; correct a past entry with a new dated entry that says what
changed, never by editing history.

---

## 2026-08-30 — the short launch catalogue

**What happened.** `f43faf9` ("How We Know: production system") added all 20
scripts, the render engine, the POV bank, the topic taxonomy and the mined
backlog in one commit.

**Verified:** `git log --diff-filter=A -- scripts/*.md` shows all 20 files
were added in `f43faf9`, dated 2026-08-30 (`git show -s --format=%ad
--date=short f43faf9`).

---

## 2026-09-01 — the 10.5-minute runtime decision

**What happened.** `819f663` ("Every batch from here is 10-11 minutes, and
the three places that decide it now agree") raised the runtime target from a
shorter figure to 10.5 minutes, reasoning that YPP's 4,000-hour bar is
long-form watch HOURS, so runtime multiplies directly into the metric that
gates monetisation.

**Verified:** `git show -s --format="%an %ad %s" 819f663` — Sequoia Taylor,
2026-09-01.

**What it got wrong, and why it is a NEAR MISS, not an incident.** The
decision computed the word budget and the retention floor from an assumed
150 wpm speaking rate and divided retention by the same `runtime_minutes`
constant it had just changed — three places that "agreed" with each other
and with nothing measured. The real, measured rate (`loop/durations.py`,
ffprobe against `renders/*-final.mp4`) is 144.58 wpm, range 133.5–154.2
across the 17 finished episodes. **It never produced a wrong video**: the 20
scripts had already been narrated and rendered before this commit landed
(all renders dated 2026-08-30/2026-08-31, before `819f663`'s 2026-09-01
19:33 timestamp), so the wrong constant was never used to author or accept a
script. It DID feed a wrong number into `loop/measure.py`'s retention floor
comparison and would have tripped the format-is-wrong breaker on a healthy
format the first time real analytics arrived — caught before that happened,
not after. **The existing short catalogue (51 rendered Shorts, cut from the
20 episodes) is not a symptom of this defect either** — Shorts are exempt
from the runtime target entirely and were cut from already-rendered
long-form video, not authored against the wrong word budget.

**The defect class, precisely.** Agreement between call sites was mistaken
for correctness, because nothing compared any of them against a measured
render. Three numbers matching each other is not evidence; it is three
copies of the same unchecked guess.

---

## 2026-09-02 — the duplicate-upload ledger fix, and the domain question

**What happened.** `8a787a2` ("Retire the duplicate upload so the ledger
stops counting 16 videos") — verified 2026-09-02. Separately, the owner
asked for a 12-month content plan; the right answer was that the loop should
decide monthly, on measured evidence, not that a plan should be locked a
year out. That question is what items 6–8 below answer in code
(`loop/domains.py`, `loop/monthly.py`, `loop/ypp.py`) rather than in a
document that would go stale the way the 150 wpm guess did.

---

## 2026-09-03 — the runtime-measurement fix, the hard 10-minute floor, the second domain, and items 6–8

**What happened, in one session, this branch:**

1. **`loop/durations.py`** replaces every hardcoded speaking-rate guess with
   a measurement: 144.58 wpm derived from real renders, cached in
   `loop/state/runtime_model.json`, re-derivable only with `--refresh` on a
   machine that has the bytes.
2. **`loop/measure.py`** stops dividing by a configured constant and
   computes average view percentage against each video's OWN measured
   duration; the breaker's trip cause moves from percentage to average view
   DURATION (`floor_avd_seconds`), because percentage stops being comparable
   the moment the catalogue holds both ~8-minute and >=10-minute episodes.
3. **A hard 10-minute floor**, owner decision 2026-09-03, enforced on
   RENDERED DURATION (`loop/validate.py` V24) as well as narration word
   count (`loop/author.py` `NARRATION_FLOOR_WORDS`) — not word count alone,
   because word count and minutes disagreeing at an unmeasured wpm is
   exactly what produced the near miss above. **The existing 20 episodes are
   NOT re-rendered.** Owner's reasoning, stated plainly: they are already
   made, and re-rendering wastes money. `retention.runtime_floor_
   grandfathered` in `loop/config.json` names them by slug so the guard
   holds the line going forward without re-litigating renders already paid
   for. Six of the seventeen finished renders are under 8:00 (01, 02, 04,
   05, 14, 16 — measured against `renders/*-final.mp4`, the file actually
   uploaded) and are not being re-rendered either.
4. **Materials-and-manufacturing** is added as a second domain, running on
   top of deep sea once the 4/week ceiling is reached (deep sea Sun/Tue,
   materials Mon/Fri) — see `research/commercial-axis.md`
   (2026-09-03, commit `22d982c`) for the measurement behind the choice.
5. **Items 6–8**: `loop/domains.py` (the one place a domain name may come
   from), `loop/monthly.py` (per-domain retention, allocation bounded to one
   slot a month, an 8-episode minimum sample before a domain can be judged),
   `loop/ypp.py` (Expanded YPP + the 2027-02-01 doubling of the standard
   tier's hour bar), all reporting the nearer gate first — written because
   the honest answer to "give me a 12-month plan" was that the loop decides
   monthly, not that a document should guess a year out.

---

## Research recorded, with its evidential quality

Every claim below is marked CONFIRMED (this session or a cited prior one,
with a stated method) or SUSPECTED (plausible, sourced, but not
independently re-verified here). Nothing is asserted as fact past what its
own source claims for itself.

### RPM by content category

**SUSPECTED — a planning figure, not a fact.** AIR Media-Tech (a
multi-channel network) reports an Education & Science category median RPM
around **$10.22**, against roughly **$2.30** as an all-niche average,
drawn from a claimed sample on the order of 300 channels / 3,595 monetized
channel-months over a recent twelve-month window. This is an MCN reporting
on **its own client base** — selection-biased by construction (channels an
MCN signs are not a random sample of YouTube), and this session did not
independently re-verify the exact sample window or figures against AIR
Media-Tech's own publication. Treat the $10.22 figure as a directional
planning input, never as this channel's expected RPM. **No source with a
disclosed, non-selection-biased sample measures CPM/RPM by category** — this
is the same conclusion `research/commercial-axis.md` reached independently
on 2026-09-03 by checking every keyword/CPC data source available on this
machine and finding none (see that file's "What could not be measured"
section, CONFIRMED unavailable by direct check, not by absence of effort).

### Commercial intent by domain

**CONFIRMED**, `research/commercial.json` + `research/commercial-axis.md`,
2026-09-03: 13,365 clean queries across all 20 candidate domains, identical
modifier list, identical denominator, no new network requests. Deep sea:
**0.011** commercial-intent share (98.9% zero-commercial). Materials-and-
manufacturing: **0.047**, roughly 4x deep sea's rate, with the most diverse
commercial surface of any domain measured (education, career and tooling
categories all present). The file's own caveat, preserved here rather than
dropped: **intent language is not a bid.** No bid is observed anywhere in
this work; it measures the surface an advertiser could want, not evidence
any advertiser wants it.

### Deep sea's subscriber-conversion strength

**CONFIRMED**, `research/competition.json` via `research/commercial-axis.md`'s
combined table: deep sea measures **10.41 views per subscriber**, roughly
**3x** the next-best domain in the 20-domain comparison. This is why deep
sea stays the subscriber engine even though it is 3rd on aggregate demand
and the weakest domain measured on commercial intent — it is the reason a
video travels without an existing audience carrying it, which matters most
at zero subscribers. The same file flags this figure's relevance as
**expiring**: it is decisive before an audience exists and much less
decisive once one does, so it should not be re-used to justify future niche
decisions without re-measuring.

### Script research — the direct-answer lock, and hook-shape research

**CONFIRMED** (this session, by reading `voice/script_text.py`): the
`## Direct-answer lock` section of a script is never spoken. `voice/
script_text.py:extract_narration()` reads only the `## Narration` section;
the lock feeds the description's first line, the thumbnail brief and the
Shorts scorer instead. See `docs/OPERATING-MANUAL.md` §3a for the full
per-section destination table.

**SUSPECTED, cited with its own sample size**: Le Quéré & Matias (2025)
report a curvilinear relationship between headline/hook framing and
engagement across **8,977 headline experiments**, implying an interior
optimum (too little hook and too much hook both underperform a middle
ground) rather than "more hook is always better." This session did not
re-run or independently reproduce that experiment set; it is recorded as a
cited external finding with its sample size stated, not as something this
channel has measured about its own videos. **Nobody has measured video hook
SHAPE (as opposed to headline text) on YouTube, and structurally nobody
outside YouTube can**: YouTube Studio's own A/B testing surface tests only
thumbnails and titles, never the first 30 seconds of a video as a variable —
so any claim about optimal video-hook shape specifically (not headline text)
is, at best, inference from adjacent research, never a direct measurement.

---

## Rejected figures — recorded by name so they cannot return

Each of these was considered and rejected. Recording them here is the guard:
the next reader who encounters one of these numbers in the wild should find
it here first.

- **"3–5 subscribers per 1,000 views."** No traceable origin found. Claims
  attributed to this rule of thumb across sources span roughly 0.3% to 20%
  conversion — a range so wide it asserts nothing. Rejected as unsourced.
- **"55% of viewers drop off by 60 seconds."** Appears in vendor marketing
  material with no stated method, no sample, no channel category. Rejected
  as unsourced.
- **"Chapters give 12% higher retention."** Commonly attributed to a Tubular
  Labs study. **No such study could be located.** Rejected as a fabricated
  citation — the exact failure class this repo's own directive-truth
  validator (`loop/validate.py` V1, `tests/test_directive_truth.py`) exists
  to catch when an LLM does it inside a script; this is the same failure
  mode occurring in secondary research instead, and it belongs on this list
  for the same reason.
- **Face-vs-faceless-channel conversion-rate claims.** Every version of this
  figure traced back to a faceless-video AI tool vendor's own marketing —
  i.e., a company selling faceless-channel software citing a number that
  makes its own product look necessary. Rejected as vendor-interested and
  unsourced.

---

## Owner actions still required, dated

See the PR/branch report for the full dated list with automation status for
each. Summarized here for the log: the one item this branch could not close
in code is `OPENROUTER_API_KEY` as a repo secret (confirmed absent via `gh
secret list`) — the owner holds the one key with money and a second must
never be created.
