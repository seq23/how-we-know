# How We Know — read this first

Faceless, evidence-first YouTube channel (`@howweknowdeep`, howweknowdeep.com),
designed to run without its owner. She is Sequoia Taylor; she decides, she does
not operate it day to day.

## "runbook howweknow" is a trigger phrase

**If she says "runbook howweknow" — or just "runbook" while in this repo — open
[`RUNBOOK.md`](RUNBOOK.md) and work from it.** That is her operator page. As of
2026-09-23 the loop, including rendering (`com.howweknow.batch`, nightly on
this Mac), is fully automatic — there is no longer a command she has to run,
only things worth knowing if a nightly run has fallen behind. She reads it
after weeks away, so keep it short and operator-facing.

The project name is part of the trigger because other repos will have runbooks
too. The convention is `runbook <project>` -> that repo's `RUNBOOK.md`.

| Document | What it is |
|---|---|
| [`RUNBOOK.md`](RUNBOOK.md) | What SHE does — as of 2026-09-23, nothing routine. Start here. |
| [`docs/OPERATING-MANUAL.md`](docs/OPERATING-MANUAL.md) | How it works, and why the numbers are what they are. |
| [`docs/CHANNEL-PLAN.md`](docs/CHANNEL-PLAN.md) | Locked strategy. Guarded by `loop/validate_plan.py`. Drift means the pipeline is wrong, not the plan. |
| [`docs/DECISION-LOG.md`](docs/DECISION-LOG.md) | Dated decisions, near misses, research with its evidential quality, and rejected figures. Append-only. |

## How she wants to be answered

Bullets and tables with the **key phrase bolded**, never paragraphs. Prose only
as a single framing line before a list. **Decide and fix — never hand back a
"flagged, not fixed" list.** Where two options exist, pick the better one, do it,
and say what you chose and why.

## Rules that are not up for debate

- **Never delete a YouTube video.** Retire it with `loop/retire.py`, which sets
  it private and verifies YouTube applied it. There is deliberately **no delete
  path in this repo** and it must not gain one.
- **Public-domain imagery only** — the channel is monetised, and CC-BY is not a
  public-domain dedication. Stripping or omitting attribution is the one thing
  this pipeline may not do. If a credit cannot be resolved, drop the beat.
- **No invented figures.** Every on-screen number is stated in the narration and
  traced to a named public source.
- **Rule 0: no stage may exit 0 having done nothing.** Work done, or a NAMED stop
  a human actually sees.
- **Guard every fix** with a registered validator, and prove it negatively:
  restore the broken state, show the failure returns, restore again. A validator
  that examines zero items must hard-fail, not pass on an empty loop.

## Run tests with

```bash
python3 loop/tests/run_all.py     # 15 files; launches each test from .venv
```

## Traps that have already cost hours — each one reported as something else

- **A missing package reads as a failing validator.** PIL twice, numpy once. An
  unrun validator is not a failing one. `run_all.py` launches every test from
  `.venv/bin/python` for this reason.
- **`launchctl` says "loaded" for a plist it cannot parse.** A bare `&&` in the
  command makes the XML invalid; both agents appeared installed and would never
  have fired. Verify with `plutil -lint`, never with launchctl's own word.
- **`wrangler r2` fails with `Authentication error [code: 10000]` that looks
  exactly like a missing R2 permission.** It is not: wrangler resolves the
  account via `/memberships`, which the token cannot read. Set
  `CLOUDFLARE_ACCOUNT_ID=8d147e242033699dd37c6f5a451f48d2` and it works.
- **`videos.update` needs the full `youtube` scope**, not `youtube.upload`. The
  private→public flip 403s otherwise, and it stayed invisible for weeks because
  the first video was uploaded public directly.
- **`estimatedRevenue` is a monetary metric.** Requesting it beside ordinary
  analytics fails the WHOLE call with a misleading 401.
- **`-t` as an ffmpeg INPUT option is broken on 8.1.1** — it returns the wrong
  frame count. Cut with `-frames:v <exact>` and assert afterwards.
- **A negative proof can "fail to restore" when nothing is wrong.** Break a
  module, run the test, restore it and run again inside the same second and
  Python reuses the stale `__pycache__`: source mtime and size both match what
  the `.pyc` recorded, so it never recompiles and the failure appears to
  persist through a correct restore. It cost twenty minutes on 2026-09-02.
  `find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +`, or sleep
  a second between the break and the restore.
- **Tests can write to the real channel.** `LOOP_DRY_RUN=1` suppresses network
  writes AND refuses to load credentials; every test that runs a lane must set
  it. One did not, and uploaded a real video.

## Before trusting a constraint

Ask what would have to be true for it to be unavoidable, then check whether it
is — **including constraints reported by a subagent.** A claim framed as a
rights or safety limit is the easiest kind to accept without testing, and doing
so cost three hours of unnecessary re-rendering on 2026-09-01.
