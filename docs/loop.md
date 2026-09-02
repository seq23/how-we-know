> **Authority: [`docs/CHANNEL-PLAN.md`](CHANNEL-PLAN.md).** That document is locked. Where this file or the pipeline disagrees with it, the plan wins and the pipeline is wrong until the plan is deliberately changed. `loop/validate_plan.py` enforces the agreement mechanically and runs in CI.

# The weekly loop

A recurring automation loop that publishes four videos a week on **close to
none of the owner's time**. Nothing waits on her: topics are picked
automatically under a hard exclusion gate, scripts are drafted by an LLM and
validated at full strength, and POV lines come from her own interview bank. She
is notified, with an override window, never blocked.

```
              GITHUB ACTIONS  (the brain)              THE MAC  (the muscle)
              free tier, no secrets required           launchd, local weights

 Sun 06:00    rank.py      demand → exclusion gate → PICKS the week
                           POV lines matched from her bank automatically
 Mon 06:00    draft.py     assemble · AUTHOR the shortfall · validate · notify
                             └─▶  loop/render_queue.json
              ── owner: nothing required. Override window open until Tue 02:00 ──
 Tue 02:00                                             loop-tuesday.sh
                                                        pull · voice · plan ·
                                                        render · receipts · push
 Thu 02:00                                             loop-thursday.sh
                                                        upload PRIVATE · receipts
 Fri 09:00    publish.py   flip to public, feed site
 Fri 17:00    measure.py   retention + RPM → Sunday
```

**`loop/render_queue.json` is the only handoff.** There is no server and no
webhook: git is the message bus. Actions commits the queue; the Mac pulls it,
builds against it, and commits receipts back.

The split is not arbitrary. Voice synthesis and rendering stay local because the
model weights are 1–3 GB and, more importantly, **the owner's voice reference is
her biometrics and never leaves her machine.** Everything that is text, JSON or
a decision runs on the free tier.

---

## The owner's involvement: none by default

| When | What she does |
|---|---|
| Any time | Nothing. The week ships. |
| If she wants | Open `docs/approve/` — see what was picked, what was drafted, what it cost. Press **Drop** on anything she does not want. |

She gave blanket topic approval: pick whatever the data says will earn
passively, subject only to hard exclusions. So there is no weekly topic
decision to make. And `pov/pov-bank.json` — 98 lines from her own interview —
**is** her approved voice, so selecting from it is a matching problem, not an
approval. `loop/pov_match.py` does it against all 22 of the bank's tags, and
refuses rather than inventing a line if nothing fits.

The override window runs from Sunday's pick to **Tuesday 02:00**, when the Mac
starts rendering. After that the week is built.

### How the override works with no login and no server

The dashboard is a static file committed to the repo. It has no fetch, no API
key and no form action — `loop/tests/test_cadence_and_gate.py` asserts all
three, and asserts it has not regained an approval gate.

**Drop** opens GitHub's new-issue form with the body prefilled:

```
OVERRIDE 2026-W36

- drop: 03-why-deep-sea-creatures-are-surfacing
```

`loop-override.yml` ingests it, marks the row `dropped`, and closes the issue.
Or `bin/loop-override.sh 2026-W36 --drop <slug>` from the terminal.

---

## The exclusion gate

With topic selection automatic, **`loop/exclusions.py` is the thing carrying
her judgement**, so it is enforcement rather than documentation.
`pov/topic-taxonomy.json` is the authority; `check_authority_coverage()` fails
if the taxonomy ever grows an exclusion the code cannot enforce, so the two
cannot drift.

Her three stated classes, in her words — *nothing adult, nothing morally grey,
nothing with legal exposure: no health/medical, no personal finance, no legal
advice* — plus all 16 taxonomy exclusions and an admitted-domain check.

Two modes, because they are different problems:

* **`decide()` gates topic selection** and is deliberately broad. Refusing one
  candidate out of 2,184 costs nothing; admitting a barred one costs a strike.
* **`decide_body()` gates generated narration** and targets *advice-giving and
  false framing*, not vocabulary. A science script may legitimately say
  "pressure", "risk" or "supplements the sonar record"; it may not tell a
  viewer what to take or buy, and it may not assert a pseudoscientific claim as
  fact. It is debunk-aware, because myth-busting is the channel's house move.

`loop/tests/test_exclusions.py` proves it negatively over 28 barred topics and
10 legitimate ones, asserting each refusal names its rule and each legitimate
topic still passes. **An empty admitted set is a hard failure**, never a pass.

---

## The authoring lane

`loop/author.py` drafts any picked topic that has no script, through OpenRouter.

| | |
|---|---|
| Model | `anthropic/claude-sonnet-4.5` (override with `$OPENROUTER_MODEL`) |
| **Measured cost** | **$0.059 per accepted script** — about $0.24/week, $12/year |
| Key | `.secrets/openrouter_key.txt` or `$OPENROUTER_API_KEY`. One key, no rotation. Never printed, never logged, never committed. |
| Spend log | `loop/state/spend.json` — per draft, from OpenRouter's own reported cost, including rejected attempts |

**Generated scripts are validated at full strength.** They are not trusted more
because the format looks right — an LLM is the most likely source of a
fabricated number or citation in this pipeline, so:

* `visuals/CONTRACT.md` rule 1 is stated in the prompt and enforced by V1.
* Every draft carries its own `## Sources`, and **V8 fetches every URL**. On the
  first real run, **two of five citations from a frontier model were
  plausible-looking 404s.** Dead URLs are fed back into the drafting retry, so
  the model fixes them before the week is built.
* Truncated output is caught. The very first draft ended mid-URL with every
  section present and four good citations — it looked entirely fine.

If the key is missing or the API errors, it takes a **named stop that exits 0**
— never a crash, never silent. `AUTHOR_REQUIRED` is the fallback when
generation fails or its output fails validation, not the normal path.

---

## Rule 0 — no stage may exit 0 having done nothing

Every stage runs inside `common.Stage`, which counts units of real work. Exiting
with zero units is rewritten into a `ZERO_WORK` named stop.

| Exit | Meaning |
|---|---|
| `0` | real work happened, **or** a self-resolving named stop |
| `1` | genuine failure |
| `3` | **NAMED STOP that needs a human** — surfaced as a failed job and an issue |

A named stop always writes `loop/state/stops/<week>-<stage>.json`, prints a
banner and appends to the Actions job summary. Whether it also **fails the job
and opens a `loop-stop` issue** depends on its disposition — a failed run is the
one notification that reaches the owner's inbox for $0, and it is worth exactly
as much as it is rare.

A week that produces zero scripts therefore emails her. It does not silently
no-op.

### Which stops page a human

`loop/stop_policy.json` is the taxonomy, and **needs-a-human is the default**: a
code that nobody has classified stays loud. A stop is downgraded to
*self-resolving* — same banner, same record, same job summary, exit `0` — only
when all three hold:

1. its code is listed in the policy;
2. it can say **when** it resolves (`QUOTA_EXHAUSTED` must carry
   `detail["resets_at"]`, which comes from `quota.next_reset()`, not from prose);
3. it has not fired on more than `max_consecutive` runs of that stage in a row.

The third is the important one. A "self-resolving" stop that never resolves is
an inert lane wearing a reassuring label, so the streak in
`loop/state/stops/_streaks.json` escalates it back to exit 3 — three
quota-blocked days running is a structural shortfall, not a busy afternoon. Any
successful run of the stage clears the streak.

`ZERO_WORK` is never self-resolving. Rule 0 is the one stop that must always
reach a person.

**Why this exists.** Run 33521586490 (2026-09-01) ended with
`NAMED STOP [QUOTA_EXHAUSTED]`, whose own unblock text read *"Nothing to do; the
allowance resets at midnight Pacific and this lane runs daily"* — and exit code
3. A daily lane that exhausts a daily quota does that every single day, and the
one notification channel the loop has was being spent on the outcome that needs
nobody. Guarded by `loop/tests/test_stop_taxonomy.py`, which asserts the exit
codes and the issue behaviour, not the wording.

---

## The circuit breaker

One flag — `loop/state/breaker.json` — halts **publishing** without tearing down
the pipeline. Mining, drafting, validating, voicing and rendering all continue
while it is open, so nothing has to be rebuilt when it is reset.

Trip causes:

| Cause | Set by |
|---|---|
| `strike` | a copyright or community strike, detected by `measure.py`, or by hand |
| `retention` | average view percentage below **30%** for **3 consecutive** videos |
| `validator` | any validator failure in `draft.py`, or any build failure on Tuesday |
| `manual` | the owner |

```bash
python loop/breaker.py status
python loop/breaker.py trip  --cause strike --detail "claim on 04"
python loop/breaker.py reset --note "claim released"
```

Gated on it: `tue-render`, `thu-upload`, `fri-publish`. Deliberately *not*
gated: `sun-rank`, `mon-draft`, `prepare` — `loop/tests/test_breaker.py` asserts
that separation, and proves the whole thing negatively by tripping it, showing
each publishing stage refuse with a named stop, and resetting it.

---

## Validators

`loop/validate.py`, run every Monday before anything is voiced. **Every one
hard-fails when it examined zero items** — a validator that passes an empty loop
is the defect it exists to catch.

| | Checks | Hard? |
|---|---|---|
| V1 | `tests/test_directive_truth.py` — no invented number or name on screen | yes |
| V2 | `tests/test_planner.py` | yes |
| V3 | nothing in the queue touches a hard exclusion, topic **and** narration | yes |
| V4 | one bank-verbatim POV per video, hand-assigned or matched, no reuse inside 12 | yes |
| V5 | no digit-bearing script ships without a real, URL-bearing source list | yes |
| V6 | every body the narration names appears in `## Sources` | **soft** |
| V7 | every queued script plans to real beats | yes |
| V8 | every source URL in a **generated** script actually resolves | yes |

V6 is soft on purpose. A body named in prose whose citation lives in the
companion article is a provenance-record gap, not an invented value — the
pipeline still cannot draw anything the narration does not speak. Halting a
channel's publishing over a bibliography line is how a loop dies of friction.
The gaps are written to `loop/state/attribution_gaps.json`, shown on the
approval page, and clear themselves the moment the lines are added.

Any **hard** failure trips the breaker.

---

## The cadence ceiling

**Four a week, deliberate, never raised to clear a backlog.** The number lives
in two places — `loop/config.json` and `pov/topic-taxonomy.json` — and
`loop/tests/test_cadence_and_gate.py` is the link between them: if they drift,
or if either exceeds four, the tests fail.

Where the four come from, in priority order:

1. **Authored inventory.** `scripts/` holds 20 finished, sourced,
   directive-annotated scripts and nothing has published — five weeks of runway.
   Free and already validated, so they go first.
2. **Mined demand,** from 2,184 real YouTube autocomplete strings, every one
   passed through the exclusion gate. The shortfall goes to the authoring lane.

---

## Competition scoring

The taxonomy's selection rule is *demand ÷ competition*, and competition needs
a YouTube Data API key that does not exist. That no longer stops the week:
demand ranking picks, and the exclusion gate constrains. An unscored ranking is
a **weaker** ranking, not an unsafe one — safety comes from the gate, which is
absolute either way. `next_topics.json` records
`competition_scoring.available: false` so the half-computed ratio is visible.

---

## What is still blocked on OAuth

Uploading and measurement need Google Cloud OAuth that does not exist yet. Both
lanes are **built end to end** and take a named stop when credentials are
absent — never a crash, never a silent skip — and both still do their real work
first:

* `upload.py` composes and writes every video's full YouTube metadata payload
  (title, chaptered description, sources, tags) to
  `loop/receipts/<week>-<slug>-payload.json`, and writes dry-run receipts, so the
  Thursday→Friday handoff is exercised on a normal week rather than for the
  first time on the day it matters.
* `measure.py` recomputes the retention streak from the history on disk, so the
  breaker's retention logic runs weekly whether or not the API is reachable.

### To unblock it

The bootstrap is built and waiting. Full click-path in **`auth/README.md`**;
the short version:

1. Google Cloud console → new project → enable **YouTube Data API v3** and
   **YouTube Analytics API** → OAuth consent screen → add yourself as a test
   user → Credentials → OAuth client ID → **Desktop app** → download the JSON.
2. Save it as exactly `.secrets/client_secret.json` (the whole directory is
   gitignored).
3. Run once and click Allow:

   ```bash
   .venv/bin/python auth/youtube_auth.py
   ```

   It prints **which channel it authorised**. Check that line — authorising the
   wrong Google account is otherwise completely silent.
4. Verify any time with `.venv/bin/python auth/check_auth.py`.
5. For the Actions-side Friday flip only, add `YT_OAUTH_CLIENT_JSON` and
   `YT_OAUTH_REFRESH_TOKEN` as repository secrets. The Mac does not need them —
   it reads `.secrets/`.

Nothing else changes. The next Thursday run uploads.

Two Google behaviours the loop is already designed around, so neither is a
surprise at runtime: an **unverified app has uploads forced private** (which is
the design anyway), and a project left in **Testing mode expires refresh tokens
after 7 days** (publish the app on the consent screen to stop it). An expired
token is a named `OAUTH_EXPIRED` stop, never a retry loop.

---

## Files

| Path | What |
|---|---|
| `loop/config.json` | cadence ceiling, retention floor, credential env names |
| `loop/common.py` | `Stage`, Rule 0, named stops, exit-code contract |
| `loop/breaker.py` | the circuit breaker, and the `guard` every publishing stage calls |
| `loop/ledger.py` | published ledger; never repeat a question; the inventory |
| `loop/exclusions.py` | the hard gate carrying the owner's judgement |
| `loop/pov_match.py` | automatic POV matching across all 22 bank tags |
| `loop/author.py` | the OpenRouter authoring lane, with spend logging |
| `loop/rank.py` | Sunday |
| `loop/draft.py` | Monday — assemble, validate, gate |
| `loop/validate.py` | the seven validators |
| `loop/gate.py` | builds the dashboard at `docs/approve/index.html` |
| `loop/override.py` | ingests an override issue (optional) |
| `loop/prepare.py` | freezes the week into `loop/work/` |
| `loop/receipt.py` | render and upload receipts |
| `loop/upload.py` | Thursday |
| `loop/publish.py` | Friday 09:00 |
| `loop/measure.py` | Friday 17:00 |
| `loop/tests/` | six test files; `run_all.py` fails if it finds none |
| `bin/loop-tuesday.sh` | the Mac's build run |
| `bin/loop-thursday.sh` | the Mac's upload run |
| `bin/loop-stage.sh` | the Actions wrapper: commit, push, issue, fail |
| `bin/loop-override.sh` | show the week, or drop a row, from the terminal |
| `bin/loop-install-launchd.sh` | install the two launchd agents |
| `docs/approve/index.html` | the dashboard — generated, do not hand-edit |
| `auth/youtube_auth.py` | one-time YouTube consent; prints the authorised channel |
| `auth/check_auth.py` | read-only credential status, called before every upload |
| `auth/tokens.py` | credential storage and refresh, stdlib only |
| `auth/README.md` | the console click-path, written for the owner |

State the loop owns: `loop/state/` — breaker, ledger, approvals, stops,
measurement. Receipts: `loop/receipts/`. Frozen week: `loop/work/`.

The loop writes to `loop/site_feed.json` rather than editing `site/`; the site
build reads the feed.

---

## Running it by hand

```bash
python loop/rank.py                       # Sunday
python loop/draft.py                      # Monday
bin/loop-override.sh                      # show the week
bin/loop-override.sh 2026-W36 --drop SLUG # drop one
bin/loop-tuesday.sh --dry-run             # everything but voice, render, push
bin/loop-tuesday.sh                       # the real build
bin/loop-thursday.sh                      # upload (named stop until OAuth)
python loop/publish.py                    # Friday
python loop/measure.py                    # Friday

python loop/tests/run_all.py              # the whole suite
python loop/breaker.py status
```

Every stage is idempotent within a week and safe to re-run.
