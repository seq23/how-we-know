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

## 2026-09-03 (review pass) — a wrong constant reintroduced by the fix that deleted one, and a live production incident folded in

**What happened.** An adversarial review of this branch, before its PR, found
that `loop/durations.py:measure_model()` re-read `## Narration` word counts
fresh off `scripts/*.md` every run, but the SAME commit (`d2b4733`) that
measured 144.58 wpm also rewrote those same 20 scripts (items 2/3). The 17
already-rendered episodes' AUDIO reflects the PRE-edit text — they are
deliberately not re-rendered. Reproduced directly: `loop/durations.py
--refresh`, the module's own documented maintenance command, silently moved
the measured wpm from 144.58 (range 133.52-154.19, correct) to 142.38 (range
129.18-151.95, wrong), the moment it was run after the rewrite. **Fixed**:
`loop/state/durations.json` now freezes `narration_words_at_measurement` per
episode the first time it is measured; `measure_model()` never re-derives it
from current script text once frozen. The 17 existing episodes were
backfilled with the correct (pre-edit) counts. Proven negatively —
`loop/tests/test_durations_frozen_words.py`.

**Separately, real production evidence surfaced mid-review** (not
hypothetical): `loop-upload-cloud` run 33783826056 (success) and `loop-reach`
run 33783829147 (failure, `CAPTIONS_SCOPE_MISSING`) both spent quota and both
committed `loop/state/quota.json` through `bin/loop-stage.sh` a minute apart.
The loser's rebase hit a real conflict; the retry loop could not recover
(retried a push while a rebase was still unmerged, and never checked whether
a push actually landed before falling through). **Fixed**: a git merge
driver for `quota.json` (sums both lanes' real spends instead of
conflicting — `loop/tools/merge_quota_json.py`), and `bin/loop-stage.sh` now
aborts a stuck rebase before retrying and fails the job outright if a push
never lands. Both proven negatively with a real two-clone git race
(`loop/tests/test_shared_state_arbitration.py`).

**The captions failure's actual cause**: not a missing consent — the owner
had already re-consented locally, but the repo secret `YT_OAUTH_REFRESH_TOKEN`
predated `youtube.force-ssl` being added to `T.SCOPES` by a day and was never
updated. `auth/youtube_auth.py` already guarded scope drift on the LOCAL
token (added after an identical incident 2026-08-31); its reach never
extended to the CI credential. **Fixed**: `auth/check_ci_scopes.py`, wired
into all three cloud workflows before any quota is spent, asserts the CI
credential's actual granted scopes (via Google's tokeninfo endpoint) against
`T.SCOPES` directly.

**A regression this branch would otherwise have shipped**: it wires
`loop/arming.py` into all three cloud lanes, gated on
`loop/state/lane_evidence.json` — a file that has never existed anywhere in
this repo's history. All three lanes were proven for real on 2026-09-03
using code that predates `loop/arming.py` existing on `main` (upload-cloud
run 33783826056; shorts-cloud via commit `dc100d2`'s video `HZhm2dXaR9c`;
reach run 33784690518). Left alone, merging would have every lane hit
`LANE_NOT_ARMED_*` on its next scheduled run — a live, working pipeline
silently regressing until a human re-dispatched each lane by hand to
re-prove what was already proven. **Fixed**: seeded `lane_evidence.json`
with all three lanes' real evidence, citing the actual commits/runs/video
IDs, so the merge preserves continuity rather than a false cold start.

**Verified, not fixed (no code changes needed):**
- The 6-of-17-under-8:00 claim (01, 02, 04, 05, 14, 16) — reproduced exactly
  with an independent ffprobe pass.
- `renders/<slug>-final.mp4` (not the bare `.mp4`) is what `loop/r2.py`
  ships — confirmed directly in `loop/r2.py`.
- `floor_avd_seconds=146` does not depend on the wpm figure at all (it is
  derived from measured render SECONDS, which the freezing bug never
  touched) — unaffected by either defect above.
- V21/V22/V23/V24 are registered in `run_all()` and reached through the same
  single entry point (`loop/draft.py`) every pre-existing validator uses —
  no new entry point, no coverage gap.
- No code in this branch's diff sets a video's privacy to public or adds a
  delete path — checked by grepping the full diff for both.

**The defect class, precisely, again**: a measurement and the text it was
measured against drifted apart after the fact, and nothing checked that they
still agreed — the identical shape as the 150-wpm near miss recorded above,
occurring inside the very commit that fixed the first instance of it.

---

## Owner actions still required, dated

See the PR/branch report for the full dated list with automation status for
each. Summarized here for the log: the one item this branch could not close
in code is `OPENROUTER_API_KEY` as a repo secret (confirmed absent via `gh
secret list`) — the owner holds the one key with money and a second must
never be created.

---

## 2026-09-08 — a named stop may no longer arrive as a red build

**What happened.** Run 34236877023 (`loop · daily 09:00 CT · upload from R2`)
exited 3 at 09:13 CT with `CAPTIONS_NOT_READY`, refusing `how-strong-is-graphene`
and instructing the owner to open a laptop and run `python
visuals/captions.py <slug>`. Her instruction in response: *"you need to fix the
how-we-know repo — I should never get a named stop — everything should be
automated. it should self heal."*

**The refusal was correct and was kept.** An episode uploaded with no `.srt` can
never be captioned afterwards — `captions.insert` needs a file — so V16 would be
red for that video forever. Nothing here was fixed by uploading uncaptioned
video or by listing the code in `loop/stop_policy.json` so it goes quiet.

**Root cause, CONFIRMED, and it was not a missing capability.**
`bin/batch-session.sh` narrates, renders, thumbnails, validates and pushes to
R2, and never runs `visuals/captions.py` — that lived in a separate manual
command, `bin/make-captions.sh`. Every episode after the original sixteen
reached the R2 shelf uncaptioned, and the upload gate refused it forever. A
missing wire between two stages that both already existed.

**The route not taken, and why.** The shelved render does carry the narration
(`ffprobe` on `renders/how-strong-is-graphene-final.mp4`: one aac mono 48 kHz
stream), so transcribing it in CI was possible. It was rejected: the cue TEXT
is not unknown — it is `plan[i]["narration"]`, committed and cross-checked
against the script's own `## Narration` block — and ASR would replace
known-exact text with a guess on a channel whose first rule is that nothing on
screen is unsourced. The only datum that ever lived exclusively on the voicing
Mac was per-beat TIMING: a few dozen floats.

**What was built instead.** `visuals/captions.py` records each measured wav
duration into `audio/<slug>/beats.json`, which git already tracks
(`.gitignore` excludes `audio/**/*.wav` and nothing else). The caption track is
now a pure function of the repository, and `loop/captions_build.py` rebuilds it
anywhere. Measured: all 33 narrated episodes rebuild **byte-identically** with
no wav present.

One correction during the work, recorded because it would otherwise look like a
rounding nicety: the durations were first stored to six decimal places, and
`what-is-carbon-fiber-made-of` then rebuilt DIFFERENTLY from the wav-built
track. An SRT timestamp is rounded to the millisecond, and a beat boundary
sitting on a millisecond edge moved across it. Full precision, not rounded.

**The third disposition.** Walking all 97 stop codes the repo can raise gave
three answers, not two. `self_resolving` (nobody acts) and `needs_human` (a
defect) already existed; `owner_action` is new. A revoked consent or a
YouTube-side account flag cannot self-heal and cannot be retried away, and
failing the job every day until she gets to it pages her for something she
cannot clear any faster for having been paged. Those exit 0, are written to the
owner-action file, and print at the TOP of the Sunday digest — and escalate to
red if they outlive their cap, which is what stops "green" from meaning
"ignored".

**Verified:** `loop/tests/test_every_stop_is_classified.py` reports
`examined 97 stop codes: 23 self-resolving, 16 owner-action, 62 needs-a-human`
and hard-fails when a code raised in the source appears in none of them.

**Also found by walking the stops, each a live defect:**

* the circuit breaker had a trip path and **no reset path**. It now re-tests its
  own cause at the top of every guarded lane; `loop/measure.py` clears a
  retention or domain trip the moment its own `breaker_cause()` stops returning
  one. A strike and a manual trip never auto-reset, and a check that cannot run
  fails closed.
* one tripped breaker guarded four lanes and produced four red jobs a day. The
  first stage to stop owns the alarm; the rest name it and stay green. All four
  still halt.
* `breaker.trip("domain", …)` raised `SystemExit: unknown cause 'domain'` —
  "domain" was never in `CAUSES`. A live crash on the path that protects the
  channel from a failing niche, unreachable until materials went live.
* a rendered episode with no thumbnail was **invisible** to the upload lane, not
  blocked by it; five materials episodes were in that state.
* `visuals/thumbs_materials.py` refused to produce anything when it could not
  resolve exactly one verified public-domain image, even though its own
  typographic route B needs no image at all.
* nothing in the repo ever wrote `pov/pov-assignments.json`, so **every episode
  authored after 2026-08-30 arrived with an untraced `[HUMAN]` beat by
  construction** and could never be uploaded. `loop/pov_repair.py` swaps the
  model-written sentence for a real line from her bank (matching, which the POV
  module already does unattended) and records it. It never adds a line TO the
  bank: that is an approval and approvals are hers.

**What still cannot self-heal, and is now green rather than red:** an expired or
revoked YouTube consent, a missing `youtube.force-ssl` scope, a
channel-level `UPLOADS_LOCKED_PRIVATE` flag, an absent or unfunded model or R2
credential, and the one-off `gh workflow run` that arms a new lane. Sixteen
codes in total, all listed under `owner_action` in `loop/stop_policy.json`.

## 2026-09-13 — nine finished episodes shipped nothing for a week, and nothing said so

**What happened.** From 6 September the Mac held nine finished materials
episodes and uploaded none. Five publish slots (9–23 October) stayed empty.
One episode, `why-is-steel-so-strong`, had rendered at 9.90 minutes against
the 10.0-minute floor — six seconds short — and both Mac lanes refused their
*entire* batch on that one failure ("nothing was uploaded this run"). The
self-heal for a short episode (`loop/extend.py`, 5 Sep) had run once on 8 Sep,
been rejected by its own validators, and nothing retried it. From 12 Sep the
daily lane then failed one step earlier, `PULL_FAILED`, on loop-state files
the cloud had started tracking — a code no policy classified — and every stop
it wrote stayed on the Mac's disk, where the Sunday digest, which runs in the
cloud, could not read it. The owner found out by asking.

**Four fixes, each guarded, each proven negatively.**

1. **The gate holds, it does not halt.** `loop/render_gate.py` runs V13/V24,
   writes the failing slugs to `loop/state/render_hold.json`, and both upload
   routes (`backfill.library_pending`, `r2.push`) skip exactly those. The rest
   ship. Its stop is `RENDER_HELD`, a HELD stop naming each slug and why.
   Zero renders examined is `RENDER_GATE_EMPTY`, exit 3.
2. **Self-heal is on the unattended path.** `bin/batch-session.sh` runs
   `extend.py` *first*, so a lengthened script is re-planned, re-voiced and
   re-rendered in the same pass; the daily lane's gate runs it (`--heal`) for
   every slug held under the floor. The retry-on-rejection that worked tonight
   is `extend.py`'s own.
3. **The pull cannot be blocked by loop state.** `loop/mac_sync.py pull` takes
   upstream for any `loop/state/` file the Mac touched (the Mac's copy kept in
   `loop/state/_local/`), and a person's conflicting edit is stashed, named,
   and the tree left clean for tomorrow. `PULL_FAILED`, `REBASE_IN_PROGRESS`,
   `RENDER_GATE_EMPTY`, `RENDER_HELD` and `MAC_NOT_SHIPPING` are classified,
   and the classification audit now scans `bin/*.sh` as well as `loop/*.py`.
4. **The Mac reports to the repository.** Every Mac lane run ends with
   `loop/mac_sync.py heartbeat` + `push`: `loop/state/mac_heartbeat.json` and
   the week's stop files are committed and pushed. `loop/digest.py:mac_stops`
   raises `MAC_NOT_SHIPPING` when finished work has waited longer than
   `mac.unshipped_days` (3), or the Mac has been silent that long with work
   pending.

**Negative proofs, run and recorded in PR #TBD:** the old all-or-nothing
script restored → `test_render_gate_holds_not_halts` fails on three
assertions; `PULL_FAILED` removed from the policy →
`test_every_stop_is_classified` names it; the hold ignored in
`library_pending` → the held slug reappears in the pending list. A plain
`git pull --rebase --autostash` against the fixture in
`test_mac_sync_pull_takes_upstream_state` fails exactly as the Mac's did.

**What was done by hand tonight, once:** `extend.py --slug why-is-steel-so-strong`
(attempt 1 rejected for a directive number the narration never spoke; attempt 2
landed at ~12.5 min), then `bin/batch-session.sh` to re-voice and re-render it.
The remaining eight upload at 4 per day from the next 09:00 run — YouTube's
daily quota, not a choice.

## 2026-09-19 — a hold on a question only a person can answer re-asks it forever

**What happened.** From 2026-09-12 the Saturday footage lane could not run
`research/imagery_video.py` on ubuntu-latest (gates B and C need ffmpeg and
Apple Vision) and took `HARVESTER_TOOLING_ABSENT` as a HELD stop whose
unblock text asked the owner to *decide* where the work runs. She closed #77
on 09-14 with the code unchanged; the hold paged again on 09-19 (run
35420734439, #91) and would have every Saturday. Meanwhile
`channel/imagery/video_rights.json` — 113 rights-cleared clips — existed only
on the Mac, untracked, harvested by hand on 09-01, and nothing scheduled had
ever grown it.

**Decision (b), taken here, not re-opened.** The video harvester runs on the
Mac's nightly batch (`bin/batch-session.sh`), which already has the tooling
and already commits and pushes repo state. (a) — a `runs-on: macos-latest`
job at a 10x minute multiplier on a private repo — is rejected for work the
Mac already does nightly.

**The class, not the instance.**

1. **A harvester declares its host.** `HARVESTER["host"]` names the scheduled
   process that runs it (`loop/footage_lane.py:HOSTS` — `ci`, `mac-batch`).
   Absent means `ci`; an unknown name is a loud error at discovery.
2. **Every host verifies what it does not run.** Each host stamps every
   harvester it ran — ok or not, exit code, output tail, manifest size — into
   `loop/state/harvest_runs.json` and commits it. A delegated harvester with
   a success inside `harvest.delegated_max_age_days` (10) is a verified unit
   of work printed as delegated; a failed run inside the cap is
   `DELEGATED_HARVEST_FAILING` (needs_human); no run inside the cap is
   `DELEGATED_HARVEST_STALE` (owner_action: only she can start a Mac that is
   off; red after 2 Saturdays).
3. **`HARVESTER_TOOLING_ABSENT` is now a wrong declaration** — the host a
   harvester names for itself cannot run it — and stays needs_human.
4. **The manifest never enters git.** V11 re-hashes every record against the
   bytes on disk, so a committed manifest with no clips beside it would fail
   the Monday lane. The stamp's `records` is how the cloud knows the pool
   size.
5. **The batch harvests on idle nights too**, the way it cuts Shorts
   (2026-09-18): it has been idle every night since 09-12. It re-screens
   NOAA's index only every `harvest.interval_days` (6) and passes
   `--refresh` so a cached index cannot hide new posts. Measured on the Mac:
   16 clips in 5m44s with 8 OCR workers, so ~2.3 h for 383 posts; the
   harvester declares a 4 h budget, and the batch runs it under `nice`.

**Guarded by** `loop/tests/test_delegated_harvest_is_verified.py` (39 checks
against a planted harvester and planted stamps) and the rewritten section 4 of
`test_footage_harvest_is_honest.py`. **Negative proofs, run before the PR:**
the idle-path `harvest_footage` call removed → two check-8 failures; `host`
removed from the video harvester's declaration → eleven failures, the first
being the ci lane back on `HARVESTER_TOOLING_ABSENT` exit 3;
`DELEGATED_HARVEST_STALE` removed from the policy →
`test_every_stop_is_classified` names it at its raise site.

## 2026-09-19 — the Shorts A/V budget was a number that matched a comment, and it hid a truncation

**What happened.** `visuals/shorts.py:verify` refused a cut when the video and
audio streams differed by more than one frame (33 ms).
`why-is-carbon-fiber-so-strong` measured 0.039 s and was refused on every
re-cut, so the push path (which correctly reads the receipt) could not shelve
it. Its picture was exactly right: 1605 frames against 53.509 s of narration.

**Measured, not guessed** — every cut in `shorts/` (69 receipts; ffprobe on each
mp4; the WAV total re-summed from each receipt's beats; all AAC 24 kHz, 30 fps,
every stream `start_time` 0.000, so no offset anywhere):

| component | n | min | max | mean | median |
|---|---|---|---|---|---|
| picture − WAV | 69 | −49.3 ms | +0.0 | −17.8 | −18.7 |
| AAC stream − WAV | 69 | −64.3 ms | +0.3 | −10.8 | −0.3 |
| video − audio (the old rule) | 69 | −31.7 ms | +39.0 | −7.0 | −14.3 |

- **Picture:** the 31 cuts made since the last-beat correction are within
  ±16.0 ms — inside the half-frame that `round(narration × FPS)` guarantees.
  The 38 older cuts are up to 1.5 frames short (the defect that correction
  fixed), and the old rule passed every one of them, because…
- **Audio:** bimodal. 46 cuts within ±0.3 ms of the WAV (the MP4 edit list
  trims AAC priming, so the container is sample-exact). 23 cuts truncated
  11–64 ms: `-shortest` stopped the AAC encoder at a 1024-sample (42.7 ms)
  boundary whenever the picture was a few ms shorter than the WAV. The
  last-beat WAVs carry 30–40 ms of trailing silence, so in 7 of the 23 the cut
  ate into the last spoken word's decay. The old rule refused exactly one of
  the 23 — carbon fiber — and for the wrong reason.

**Decision (b): fix the mux, then measure each stream against the narration.**
1. **`-shortest` is gone** from the final mux. It was protecting against a long
   picture that cannot happen (every part is cut to an asserted frame count).
   Re-cut, carbon fiber's audio stream is −0.3 ms against its WAV, picture
   −9.3 ms, 1605 frames.
2. **`av_verdict(video, audio, narration)`** judges the picture on
   `PICTURE_BUDGET_S` = half a frame + 1 ms probe rounding (the construction
   guarantee; a one-frame miscount is at least half a frame away, so this
   catches every miscount where a one-frame budget missed half of them) and
   the audio on `AUDIO_BUDGET_S` = 5 ms (an order of magnitude above the
   0.3 ms residual, below the 11 ms smallest truncation seen). The streams'
   difference is still written to the receipt as `av_drift_s`, information
   only. The receipt now also carries `narration_s`,
   `picture_vs_narration_s` and `audio_vs_narration_s`.
3. **Not re-cut:** the 22 other truncated cuts and the 38 short-picture cuts.
   Their receipts say ok:true and most are published; retiring is private-only
   by rule, and a re-cut is a re-upload. Listed here so the choice is visible,
   not made by omission: the 7 whose last word was clipped are
   `04-…-scary-short3`, `09-…-scariest-short`, `10-…-deepest-part-short2`,
   `15-…-challenger-deep-short`, `16-…-whale-dies-short2`,
   `what-is-concrete-made-of-short`, and carbon fiber (re-cut).

**Guarded by** `loop/tests/test_shorts_av_budget_is_measured.py` (12 planted
verdicts, budgets asserted as derived, `-shortest` asserted absent from the
mux, zero receipts hard-fails). **Negative proof:** old rule and `-shortest`
restored → 17 failures, among them a +1-frame picture error accepted outright
and the 48 ms carbon-fiber truncation "refused" as drift; restored → green.

## 2026-09-21 — the pronunciation lexicon was making words worse, and nothing had ever listened to it

**Trigger.** The owner heard "hypothermal" for "hydrothermal" in the Short
for `20-what-is-the-midnight-zone`. Whisper on that Short's audio track heard
"Hydro-thermal vents", "The Bath-E-Pell A.J. Ike zone" (bathypelagic) and
"local chemo, syn, that, ik, sources" (chemosynthetic).

**Root cause.** Chatterbox has no phoneme input; it reads a respelling as
text. `voice/synth.py`'s LEXICON was written in dictionary style —
`"hy-droh-THUR-mal"`, `"bath-ee-pel-AJ-ic"` — and the model speaks hyphens as
word breaks and a CAPS chunk as spelled-out letters. The table's STYLE was the
defect. `voice/tests/pronunciation_probe.md` was a paragraph to listen to by
ear, and nobody had.

**What was measured.** `voice/tests/pronunciation_probe.py` (new) synthesises
each term in two carrier sentences with the production voice and parameters
and transcribes it with whisper-1. Spoken with NO entry, the model already
says **31 of the 38** lexicon terms correctly — including all three above. The
seven it mangles alone: MBARI, Kaikō, abyssopelagic, Pseudoliparis,
Grimpoteuthis, Kiwa, PLOS.

**Decision.**
1. **An entry exists only for a term the probe hears wrong with no entry.**
   The table drops from 38 entries to 12: five letter-acronyms (ROV, ROVs,
   CTD, GPS, DNA as spaced capitals) and the seven above, each a lowercase
   pseudo-word ("em bar ee", "kai ko", "abisso pelagic", "sudo liparis",
   "grimpo toothis", "kee wah", "ploss"), each probed to a pass.
2. **Every entry is proven, and the proof is code-read.** The probe writes
   `voice/tests/pronunciation_probe.json`; `loop/tests/test_lexicon_respellings.py`
   fails the suite if an entry is missing from the pin, changed since it was
   heard, or was not heard as intended — and, statically, if any respelling
   carries a hyphen or a CAPS chunk. It reads the lexicon with `ast`, not by
   importing `synth` (the render venv has no soundfile).
3. **The gap scan now knows materials.** `voice/audit_narration.py`'s term
   regex covered deep-sea vocabulary only, so a materials script scanned as
   clean. Extended with phases, processes, instruments and the chemical names
   the eighteen materials scripts use; the candidates were screened raw the
   same way (see the PR for the count).
4. **Nothing published was re-narrated or re-uploaded.** Sixteen live
   episodes and their Shorts were narrated under the old table; the ones with
   a term the probe or the owner heard wrong are listed in the PR for a
   separate decision. Retiring is private-only by rule and a re-narration is
   a re-upload.

---

## 2026-09-21 — scope widened to deep sea + materials

**What happened.** Owner instruction: "how-we-know: widen the channel from
deep sea to deep sea + materials." The pipeline was already running
materials-and-manufacturing — 18 episodes uploaded and dated Mon/Fri from
7 September to 6 November, its own source allowlist in
`loop/domain_sources.py`, its own POV top-up done 2026-09-05 — but
`pov/topic-taxonomy.json`'s `admitted_domains` (locked 2026-08-30) still named
deep sea only, and the public About text on YouTube described six domains
that have never aired and omitted the one airing twice a week. The channel had
been publishing outside its own standing admission for two weeks.

**What was already true, unchanged by this entry.** The loop's allocation,
cadence, source allowlist and POV bank needed nothing — this was a scope-record
and guard change, not a pipeline change.

**What this change made true.**
1. `pov/topic-taxonomy.json` gains "Materials science and manufacturing" in
   `admitted_domains`, a new `admitted_domain_ids` map, and this amendment
   entry, satisfying `new_niche_requirement` retroactively via the 2026-09-05
   top-up.
2. `loop/validate_plan.py` gains check 10: every domain in
   `config.json` `domains.allocation` must be admitted, have >=3 allowlisted
   source bodies, have `publish_days`, and have >=1 `tier: specific` POV line
   — `config.json`'s `per_domain_requirements` stated this; nothing read it
   until now. Proven negatively: removing materials from
   `admitted_domain_ids` fails check 10; restoring it passes.
3. `channel/about.md` puts the channel's YouTube About text under version
   control for the first time, with a widened paragraph naming both tracks
   and both source sets; `loop/channel_about.py` pushes it idempotently.
4. `README.md`, `RUNBOOK.md` and `docs/CHANNEL-PLAN.md` updated to state the
   two-domain schedule as present fact rather than a future step.
5. `site/src/lib/taxonomy.ts` gains a `materials` subject so the companion
   site's vocabulary again mirrors the admitted domains, with no navigation
   change until a page carries it — the site's own design rule.

**Deliberately out of scope.** The companion site's materials question pages
— a data-model change (every record needs an ocean zone and a creature today)
plus 18 pages of new sourced copy — are a separate repo-change, not a wording
widening.

**Verified:** see the PR for `loop/validate_plan.py` output (10/10 checks,
including the negative proof of check 10) and the site's own
`npm run validate && npm test && npm run typecheck` output.

---

## 2026-09-21 — hashtags and tags per episode, both domains, backfilled

**What happened.** Owner instruction: "how-we-know: hashtags and tags per
episode, both domains, backfill all videos." Every video on the channel
carried the same seven fixed tags (`deep sea, ocean science, how we know,
evidence, marine biology, explainer, deep ocean`) and no hashtags at all —
including all 18 materials-and-manufacturing episodes and their 31 Shorts,
tagged "marine biology" like everything else. `loop/upload.py:build_payload()`
and `loop/shorts_lane.py:build_payload()` each hardcoded one list, used by
every upload path.

**What this change made true.**
1. `loop/discovery.py` (new) derives tags and hashtags per episode: the
   episode's own subject (its title, question stem stripped), up to 8
   autocomplete-mined queries for its domain that actually occur in its own
   narration (`research/mined_queries.json` / `mined_queries_materials.json`
   — nothing invented), then its domain's tags, then the channel's — from a
   new `discovery` block in `loop/config.json`. Hashtags follow the same
   order, capped at 6, so the three YouTube displays above the title are
   always the episode's subject, its domain, and the channel.
2. `loop/upload.py` and `loop/shorts_lane.py` call it instead of a fixed
   list; a Short inherits its parent episode's tags plus "shorts" /
   "#Shorts".
3. `loop/localize.py` treats the hashtag line as VERBATIM — held out of
   `content_key` and never sent to the model — so backfilling hashtags onto
   the 34 already-localized videos re-translates nothing.
4. `loop/tags_backfill.py` (new) rewrites every live episode and Short —
   metadata only, read-merge-write-whole through `loop/ytmeta.py`, idempotent
   — and carries the same hashtag line onto each video's existing
   localizations in the same write. Wired into `.github/workflows/loop-reach.yml`
   as a third daily lane so a future drift self-heals.
5. `loop/validate.py` V41 proves, for every allocated domain, on a real
   script through the real builders: the domain's own tags appear and no
   other allocated domain's do (the exact shape of the bug this closes); the
   description ends with a 1–60 hashtag line in subject/domain/channel order;
   Shorts carry "shorts" plus the domain's tags; the total tag length holds
   under YouTube's 400-character limit. Proven negatively: blanking
   materials' tags in `config.json` fails V41 with the expected messages;
   restoring it passes.

**Deliberately out of scope.** Titles are untouched — the question IS the
title, and a hashtag in a title suppresses the description's. The site
(howweknowdeep.com) is not YouTube metadata; nothing there changes.

**Verified:** see the PR for `loop/tests/run_all.py` (52/52), `loop/validate.py`
and `loop/validate.py --reach` output (V41 included), the negative proof of
V41, and `loop/tags_backfill.py --dry-run`'s real read-only output against
all 65 live videos (34 episodes, 31 Shorts) — every materials video's
computed tags carry no deep-sea term.

## 2026-09-21 — the About push was a 400, and the real cause was length, not the angle brackets

`rc_m32h8ze2a4hk37pc` landed how-we-know as 4a4de65 and its post-land step,
`loop/channel_about.py`, failed: `HTTP Error 400: Bad Request` from
`channels.update`. The instruction that opened this fix named the angle
brackets in `channel/about.md`'s HTML markers as the cause alongside length.

**What was actually true.** `channel_about.py` pushes only the text between
`<!-- ABOUT:START -->` / `<!-- ABOUT:END -->`, never the markers themselves.
That pushed body was **1,006 UTF-16 units** — 6 over YouTube's 1,000-unit cap
on `brandingSettings.channel.description` — and contained no `<` or `>` at
all. Length alone caused the 400; the brackets were only ever in the markers,
which are never sent. The guard added below still refuses on both, as
instructed — YouTube rejects `<`/`>` outright and nothing should reach the
request carrying one.

**What this change made true.**
1. `channel/about.md`'s pushed body shortened from 1,006 to **953 UTF-16
   units**, same meaning, both domains, both day pairs, all seven named
   source bodies, the uncertainty sentences and "New episodes weekly." kept
   verbatim. Owner approval: repo-change `rc_m33avf9cd0njg79t`, plan default.
2. `loop/channel_about.py` gained `check_description()` — refuses BEFORE any
   request if the body exceeds 1,000 UTF-16 units (YouTube's own count, not
   bytes or code points) or contains `<`/`>`, naming the exact number or
   character rather than surfacing Google's bare 400. Called from
   `merge_branding()` and again at the top of `run()`, right after
   `read_about()`, so the refusal prints before a credential is even loaded.
3. `loop/tests/test_channel_about_refuses_before_request.py` (new, 52→53
   test files) — too-long, exactly-at-cap, `<`, `>`, an astral character
   pushing the UTF-16 count over by one, and an assertion that the repo's own
   `channel/about.md` body passes so it cannot regress past the cap.

**Verified:** `loop/tests/run_all.py` — 53/53 files, the same 9 pre-existing
environment-only failures as an unmodified baseline (missing local
credentials/packages on this dev machine, none touching `channel_about.py`)
and zero new ones. Negative proof, both refusals: reintroducing the old
1,006-unit body fails naming `1013` (the test fixture's own length at the
time), restore passes; inserting a `<` fails naming `'<' at line 18, column
14`, restore passes. `__pycache__` cleared between break and restore.
`LOOP_DRY_RUN=1 .venv/bin/python loop/channel_about.py` still refuses on
missing credentials, not on the text — confirming the guard passes clean
text through.
