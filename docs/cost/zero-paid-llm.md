# Zero paid LLM calls (2026-10-11)

Owner policy, verbatim: **"nothing should be paid … cut the probes and make them free."**

The repo's OpenRouter key (shared with the site loops) now has a **$0 monthly
credit limit**: a paid model call answers HTTP 403 "Key limit exceeded" (probed
2026-10-11). Free (`:free`, $0/$0) models still answer on it.

## What was paid, and what it is now

| Call site | Runs from | Schedule | Was | Now |
|---|---|---|---|---|
| `loop/draft.py` → `author.draft()` (writes the week's scripts) | `loop-mon-draft.yml` | Mon 10:00 UTC | `anthropic/claude-sonnet-4.5` (`vars.OPENROUTER_MODEL` unset → default) | free route |
| `loop/extend.py` (lengthens an episode under the runtime floor) | `com.howweknow.batch` → `bin/batch-session.sh`; `com.howweknow.backfill` → `loop/render_gate.py --heal` | nightly 23:00 / daily 09:00 (Mac) | `anthropic/claude-sonnet-4.5` | free route |
| `loop/localize.py` (translates titles/descriptions + back-check) | `loop-reach.yml` | daily 15:00 UTC | `anthropic/claude-sonnet-4.5` | free route |
| `loop/advise.py` (monthly advisory paragraph) | `loop-monthly-review.yml` → `loop/monthly.py` | 1st of month 07:12 UTC | `anthropic/claude-sonnet-4.5` | free route |
| `loop/comments.py` (comment classifier) | manual / `loop/handoff.py` path; no schedule | — | `anthropic/claude-haiku-4.5` | free route |
| `loop/discovery.py` / `loop/tags_backfill.py` | `loop-reach.yml` | daily | no model (keyless by design) | unchanged |
| `~/bin/shorts-arm.sh` (`com.seq.shorts-arm`) | launchd | — | Claude Code CLI on the subscription, not OpenRouter | out of scope |

Measured from `loop/state/spend.json`: **180 authoring/extension calls, $10.38
total** (Aug $1.34, Sep $8.84, Oct $0.20), all Sonnet 4.5. Localisation
cached 194 Sonnet translations. The rest of the key's $98.84 this month is the
site loops, not this repo.

## How it is enforced

- **`config/llm_routing.json`** — the only models any lane may call: an ordered
  list of `:free` models priced $0/$0 with ≥32k context, a `snapshot_date`,
  `max_cost_usd: 0`, `paid_fallback: false`. Snapshot 2026-10-11:
  1. `nvidia/nemotron-3-ultra-550b-a55b:free`
  2. `nvidia/nemotron-3-super-120b-a12b:free`
  3. `google/gemma-4-31b-it:free`
  4. `google/gemma-4-26b-a4b-it:free`

  (`thinkingmachines/inkling:free` is listed at $0 but answers 403 "only
  available on agentic harnesses" to this key, so it is excluded.)
- **`loop/llm_router.py`** — the one HTTP client. Every request carries
  `provider.max_price = 0`; a model outside the list is refused before the
  network; a reported cost above $0 fails loudly. `author.call_openrouter()`
  delegates to it, so every lane is covered.
- **`OPENROUTER_MODEL` repo variable: removed from the workflow.** The router
  owns the model (the variable was never set; it fell through to Sonnet).
  `$OPENROUTER_MODEL` still overrides on a machine, but only to another free model.

## Named stops

| Code | Meaning | Class |
|---|---|---|
| `OPENROUTER_KEY_DISABLED_OR_INVALID` | 401, or 401/402/403 from every free model | owner_action (credential) |
| `OPENROUTER_NO_FREE_MODEL` | every free model failed (rate limit, outage, empty) | self_resolving, pages after 3 |
| `OPENROUTER_PAID_MODEL_REFUSED` | something named a non-free model | needs_human (config defect) |
| `OPENROUTER_PAID_COST_REFUSED` | OpenRouter billed a "free" model | needs_human (refresh the list) |

**The Monday lane keeps its "could not author" semantics.** A free model's
unusable draft is retried with the rejection fed back (same free route,
`author.MAX_ATTEMPTS`), then `DRAFT_FAILED_VALIDATION` → the week's
`AUTHOR_REQUIRED` note, brief in `loop/briefs/`, topic re-selected next Monday.
Never a paid retry. If *every* slot failed for the key or for no free model,
the week's stop carries that code instead of `AUTHOR_REQUIRED`.

Guarded by `loop/tests/test_llm_routing.py` (config shape + negative proofs, no
paid literal or model variable in workflows/scripts/loop, router behaviour,
Monday-lane fallback).

## Refreshing the list

`curl -s https://openrouter.ai/api/v1/models` (no key), keep `:free` text models
with prompt and completion price 0 and context ≥ 32k, strongest general
instruct model first, update `snapshot_date`, run the test.
