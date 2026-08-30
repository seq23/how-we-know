# The weekly loop

A recurring automation loop that publishes four videos a week on roughly
**twenty minutes of the owner's time**.

```
              GITHUB ACTIONS  (the brain)              THE MAC  (the muscle)
              free tier, no secrets required           launchd, local weights

 Sun 06:00    rank.py      demand → next_topics.json
 Sun  5 min   ── owner: approve or swap ──────────────────────────────────────
 Mon 06:00    draft.py     assemble · validate · gate
                             └─▶  loop/render_queue.json
 Mon 15 min   ── owner: confirm 4 POV lines, Approve all ────────────────────
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

## The owner's twenty minutes

| When | Minutes | What she does |
|---|---|---|
| Sunday | 5 | Skim `loop/next_topics.json`, or the top of the approval page. Swap a topic if one is wrong. Usually nothing. |
| Monday | 15 | Open **`docs/approve/`**. Four cards. For each, pick which POV line is actually hers. Press **Approve all**. |

That is the entire commitment. Everything else is either automated or a named
stop that emails her.

### How approval works with no login and no server

The approval page is a static file committed to the repo. It has no fetch, no
API key and no form action — `loop/tests/test_cadence_and_gate.py` asserts all
three, so it cannot quietly acquire them.

A static page cannot write to a repo. Giving it a token would end the
credentialless property, so instead **Approve all** opens GitHub's own new-issue
form with the title and body prefilled:

```
APPROVE 2026-W36

- slug: 01-why-deep-sea-creatures-look-so-weird | pov: bank
- slug: 02-how-deep-sea-creatures-survive-pressure | pov: script
…
APPROVE ALL
```

She is already signed in to GitHub, so it is one further click. The
`loop-approve.yml` workflow ingests the issue, writes
`loop/state/approvals/<week>.json`, stamps every queue row `approved`, and
closes the issue. Only issues opened by the repository owner are honoured.

If the button is ever blocked, the same block is on the page to copy, and
`bin/loop-approve.sh` does it from the terminal.

**A row absent from the body is held, not approved.** `APPROVE ALL` must be
present; a half-edited issue approves nothing.

---

## Rule 0 — no stage may exit 0 having done nothing

Every stage runs inside `common.Stage`, which counts units of real work. Exiting
with zero units is rewritten into a `ZERO_WORK` named stop.

| Exit | Meaning |
|---|---|
| `0` | real work happened |
| `1` | genuine failure |
| `3` | **NAMED STOP** — legitimate, named, and surfaced to a human |

A named stop writes `loop/state/stops/<week>-<stage>.json`, prints a banner,
appends to the Actions job summary, opens or updates a `loop-stop` issue, and
**fails the job on purpose** — a failed run is the one notification that reaches
the owner's inbox for $0.

A week with zero approved scripts therefore emails her. It does not silently
no-op.

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
| V3 | nothing in the queue touches one of the 16 hard exclusions | yes |
| V4 | one bank-verbatim POV per video, no reuse inside 12 | yes |
| V5 | no digit-bearing script ships without a real, URL-bearing source list | yes |
| V6 | every body the narration names appears in `## Sources` | **soft** |
| V7 | every queued script plans to real beats | yes |

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
   Those questions were already chosen and approved by the owner when the
   scripts were written, so no competition score is needed to ship them.
2. **Mined demand,** from 2,184 real YouTube autocomplete strings. Advisory
   only — see below.

---

## Why the topic list is a named stop

The taxonomy's selection rule is *demand ÷ competition*. Competition needs a
YouTube Data API key that does not exist. The standing rule is that the loop
never publishes against an unscored topic list, so `rank.py` emits mined
candidates as **advisory**, marked `scored: false`, and takes a
`COMPETITION_UNSCORED` named stop for any slot that would have to come from
them.

While inventory covers the week — the next five weeks — this stop never fires
and Sunday runs green.

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
| `loop/rank.py` | Sunday |
| `loop/draft.py` | Monday — assemble, validate, gate |
| `loop/validate.py` | the seven validators |
| `loop/gate.py` | builds `docs/approve/index.html` |
| `loop/approve.py` | ingests the approval issue |
| `loop/prepare.py` | freezes the week into `loop/work/` |
| `loop/receipt.py` | render and upload receipts |
| `loop/upload.py` | Thursday |
| `loop/publish.py` | Friday 09:00 |
| `loop/measure.py` | Friday 17:00 |
| `loop/tests/` | six test files; `run_all.py` fails if it finds none |
| `bin/loop-tuesday.sh` | the Mac's build run |
| `bin/loop-thursday.sh` | the Mac's upload run |
| `bin/loop-stage.sh` | the Actions wrapper: commit, push, issue, fail |
| `bin/loop-approve.sh` | approve from the terminal |
| `bin/loop-install-launchd.sh` | install the two launchd agents |
| `docs/approve/index.html` | the gate — generated, do not hand-edit |
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
bin/loop-approve.sh                       # approve locally
bin/loop-tuesday.sh --dry-run             # everything but voice, render, push
bin/loop-tuesday.sh                       # the real build
bin/loop-thursday.sh                      # upload (named stop until OAuth)
python loop/publish.py                    # Friday
python loop/measure.py                    # Friday

python loop/tests/run_all.py              # the whole suite
python loop/breaker.py status
```

Every stage is idempotent within a week and safe to re-run.
