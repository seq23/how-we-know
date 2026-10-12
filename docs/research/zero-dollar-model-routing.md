# $0 Model Routing

Repo copy of the research page https://claude.ai/artifact/V3mv9fNxg8DmsB3tLpxmLG (v1.4, 12 Oct 2026).
The page is the living version; this copy is refreshed when it changes. The code decides, this explains.

## 1. The route, in order

1. **Her Claude subscription, through Claude Code's headless CLI.** Prepaid, no per-call bill. A
   long-lived OAuth token from `claude setup-token` (valid one year; created 12 Oct 2026, expires
   12 Oct 2027) sits in the repo secret `CLAUDE_CODE_OAUTH_TOKEN`. The call:
   `claude -p --output-format json --model opus --max-turns 1 --tools "" --no-session-persistence --system-prompt "…"`
   with the user content on stdin, run from an empty temp directory. About 650 input tokens, seconds
   to answer. Do not pass `--bare`: on CLI 2.1.296 it ignores the OAuth token. Lanes with a short job
   ceiling keep their own shorter call timeout.
2. **Gemini free tier, her own AI Studio key** (`GEMINI_API_KEY`, the pitch-lab project's). Google's
   OpenAI-compatible endpoint; models tried in order 3.5 Flash, 3.5 Flash-Lite, 3 Flash preview,
   2.5 Flash, 2.5 Flash-Lite; falls through on a rate limit or error. Ahead of OpenRouter because
   Gemini Flash writes long-form far better than any `:free` model there. Free-tier prompts may be
   used by Google to improve its products: channel scripts only, never anything confidential.
3. **The $0 OpenRouter list, in measured order** (`config/llm_routing.json` is the roster;
   `loop/state/llm_route_ledger.json` reorders it by pass rate and latency; `python3 loop/llm_router.py standing`).
4. **Never**: an API key billed per call, a paid model, an OpenAI subscription (no API access, Codex
   sign-in does not run headless), or any route that trains on confidential input.

Decisions: 11 Oct 2026 "nothing should be paid, cut the probes and make them free"; 12 Oct 2026 "use my
claude subscription usage in advance of the $0 openrouter"; 12 Oct 2026 "make it much longer so this
doesn't happen again" (the Monday authoring budget, `loop/draft.py` `AUTHORING_BUDGET_MIN`).

## 2. OpenRouter free-tier limits

| | |
|---|---|
| Per minute | 20 requests to `:free` models |
| Per day, default | 50 for an account that has bought under $10 of credits in its lifetime |
| Per day, upgraded | 1,000 once the account has ever bought $10 or more; permanent |
| Scope | per account across every key |
| 503 "overloaded" | Google's answer when a Gemini model has no spare capacity; free-tier traffic is shed first. Transient, not the key (sibling models answered in the same minute). The router skips it in seconds; the ledger records it, so a model that keeps refusing drops below the ones that answer |
| Quiet window | unpublished by any provider; by business hours across the US, Europe and India the lightest load is roughly 02:00–06:00 UTC. Owner decision 12 Oct 2026: the Monday lane runs at 05:00 UTC |
| This account | **1,000/day**, confirmed 12 Oct 2026 from `GET /api/v1/auth/key` (`is_free_tier: false`); a $0 key limit still serves free models |

## 3. The live roster, 12 Oct 2026

15 free text models served (`GET /api/v1/models`, id ends `:free`, price 0/0). Benched for long scripts:
gemma-4-31b, nemotron-3.5-lightning, inkling, dots-3-note-preview, gemma-4-26b, apodex-1.1-mini,
nemotron-3-super, nemotron-3-ultra. Skipped: inkling-small, nemotron-3-nano-omni, poolside laguna
(code), cohere north-mini-code (code), nemotron-3.5-content-safety, liquid lfm-2.5-2.6b (too small).
Not free on OpenRouter at all: the open-weight models the writing boards rate highest (Kimi K2.6/K3,
GLM-5.x, DeepSeek V4, Qwen3.8).

## 4. What we have measured

**Production, Mon 12 Oct 2026 (run 38235183608):** Ultra answered empty (5 min lost); Super wrote
~1,025 words against a ~1,300-word floor and cited a dead URL; the job was cancelled by a 31-minute
ceiling set on a paid model's median. Fixed by #159/#161: 210-minute authoring budget, 230 ceiling.

**Bench, 12 Oct 2026** (`loop/bench_free_models.py`, results `research/free_model_bench/2026-10-12.md`):
no free model wrote a passing script. gemini-2.5-flash came closest (every draft over the floor,
stopped only by two dead source links). nemotron-3-ultra cleared the floor at 5–10 minutes a draft,
stopped by broken visual cues. gemma-4-31b/26b were rate-limited every time; inkling refuses
non-agentic callers (403); nemotron-3.5-lightning and dots-3-note answered empty; gemini-3.5-flash 503.
**No draft failed on length alone, so the "expand to 2x" idea does not apply**; the failures are dead
citations and broken directives. Reasoning models on OpenRouter think until the 16,000-token limit and
return empty text (`finish_reason=length`); the request needs a reasoning cap.

## 5. What the web says

No source measures free models on long-form writing; guides rank by context length and usage and
disagree on which ids exist. Creative-writing boards are led by Claude Opus 5.5 and Fable 5; the best
open-weight writers are not free on OpenRouter. Reasoning models are not better writers.

## 6. Other $0 routes

Google AI Studio (now tier 2), Groq (30/min, 1,000/day, ~200K tokens/day), Cerebras (card-required
trial since July 2026, 8K context), Cloudflare Workers AI (10,000 neurons/day, short calls only).

## 7. The pattern for any repo

One router; config is the roster, the ledger is the order; the budget lives in code and the ceiling is
derived from it (how-we-know: 05:00 UTC start, 480-minute budget, 500 ceiling, before the 14:00 UTC upload lane); run the heavy lane in the quiet window (02:00–06:00 UTC) and let the ledger confirm; a failed draft is a brief, not a red build; bench before trusting; every lane that
can reach the router gets the secrets (a test derives the set by tracing real calls); the runbook
describes, the tests decide. Reference implementation: this repo (`loop/llm_router.py`,
`config/llm_routing.json`, `loop/bench_free_models.py`, `loop/tests/test_llm_routing.py`,
`test_mon_draft_authoring_budget.py`, `test_measured_fallback.py`, RUNBOOK "Lanes", "Model route",
"Fallback standing", "Free model bench").

Sources: OpenRouter limits docs; OpenRouter free-models collection; TrueFoundry on the free tier;
Surfmind, Ruben Torney, Lamjin Lab guides; BenchLeader LMArena creative board; LLM Learner rankings;
Featherless; OpenRouter "free LLM APIs compared"; Continuum Code; CostBench.
