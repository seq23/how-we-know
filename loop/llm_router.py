"""The ONE route to a language model in this repo, and it only goes to $0 models.

Owner policy, 2026-10-11, verbatim: "nothing should be paid ... cut the probes
and make them free." The repo's OpenRouter key now has a $0 monthly credit
limit, so a paid model call can only fail; this module makes sure none is ever
attempted, and that a free call which somehow costs money is loud.

    config/llm_routing.json   the ordered list of $0 models (snapshot-dated)
    complete(messages, key)   tries them in order; returns the first answer

Rules, each enforced here rather than written down:

  * Only models in config/llm_routing.json are sent. A caller (or
    $OPENROUTER_MODEL) naming anything else is refused BEFORE the network:
    OPENROUTER_PAID_MODEL_REFUSED.
  * Every request carries `provider.max_price = 0`, so OpenRouter itself
    refuses to route to a paid endpoint even if a listed model changes price.
  * Every response's reported cost must be 0. Non-zero is
    OPENROUTER_PAID_COST_REFUSED - raised, never logged-and-continued.
  * HTTP 401 is the key itself (OpenRouter: "User not found"):
    OPENROUTER_KEY_DISABLED_OR_INVALID at once. 402/403 can be per-model
    (2026-10-11: a listed ':free' model answered 403 "only available on
    agentic harnesses") so they move to the next model - but when EVERY model
    was refused with 401/402/403, the key is what is refused, and that is
    OPENROUTER_KEY_DISABLED_OR_INVALID too.
  * Any other failure on one model (404, 429, 5xx after the transient
    retries, a dropped connection, an empty answer) moves to the next free
    model. When every free model has failed: OPENROUTER_NO_FREE_MODEL.
  * There is no paid fallback. `paid_fallback` in the config must be false.
  * Owner 2026-10-12: "use my claude subscription usage in advance of the $0
    openrouter". When $CLAUDE_CODE_OAUTH_TOKEN is set and a `claude` binary is
    on PATH, the headless Claude Code CLI (her prepaid subscription, no
    per-call bill) is asked FIRST. Any failure there prints one
    [claude-route] line and falls through to the $0 list unchanged; it never
    raises and is never a stop. Without the variable no subprocess is run.
  * Owner 2026-10-12: her Google AI Studio key, FREE TIER ONLY, is the
    second tier. When $GEMINI_API_KEY is set, config `gemini_route.models`
    (ids "gemini/<model>") join the front of the $0 roster, called through
    Google's OpenAI-compatible endpoint. Any 403/404/429/5xx, timeout or
    empty answer skips to the next model with one [gemini-route] line; the
    tier never raises and is never a stop. Without the variable no Gemini
    request is made. The key is sent only in the Authorization header -
    never argv, a log line or the ledger.
    DATA RULE: free-tier Gemini prompts may be used by Google to improve its
    products. This tier is for channel scripts only and never for anything
    confidential (LP names, deal terms). This router is the only door to a
    model in this repo, and this repo holds nothing confidential.
  * Owner 2026-10-12: the $0 fallback ORDER is measured, not guessed. Every
    free-model call outcome (answered / empty / error / rate_limited /
    timeout) and every structural verdict loop/author.py reaches on an
    answer (passed / failed_validation, via record_validation) lands in
    loop/state/llm_route_ledger.json, last LEDGER_KEEP per model. standing()
    ranks the roster (the Gemini models when the key is set, then the
    config's OpenRouter models) from their last STANDING_WINDOW events, so
    a rate-limited Gemini day drops it below a good OpenRouter model:
      MEASURED-GOOD  >= 4 judged events and pass_rate >= 0.5 (pass_rate
                     desc, then median latency asc)
      UNMEASURED     <  4 judged events (config order)
      MEASURED-BAD   >= 4 judged events and pass_rate < 0.5 (pass_rate desc)
    pass_rate = passed / (passed + failed_validation + empty + error +
    timeout + rate_limited); "judged" = that denominator. An answer with no
    verdict yet counts as neither, so it never makes a model measured. No data anywhere = exactly the config order. The config list
    is the roster; the ledger only reorders it, never adds a model.
    complete() walks standing() order. A caller's `preferred` model still
    goes first UNLESS it is MEASURED-BAD; a BAD preferred model loses the
    preference and keeps its measured place - after every MEASURED-GOOD
    (and UNMEASURED) model. The subscription tier is never ranked or
    recorded. Pinned by loop/tests/test_measured_fallback.py.

Callers keep their own semantics for USABLE output (loop/author.py retries a
draft that fails validation against the SAME free route and then raises
DRAFT_FAILED_VALIDATION, which the Monday lane turns into AUTHOR_REQUIRED).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "llm_routing.json"
API = "https://openrouter.ai/api/v1/chat/completions"
# The Gemini free tier (owner 2026-10-12): Google's OpenAI-compatible door.
GEMINI_API = ("https://generativelanguage.googleapis.com/v1beta/openai/"
              "chat/completions")
GEMINI_ENV = "GEMINI_API_KEY"
GEMINI_PREFIX = "gemini/"
GEMINI_ROUTE_NAME = "gemini-free-tier"
# The measured fallback order (owner 2026-10-12). LLM_ROUTE_LEDGER redirects
# it (loop/tests/run_all.py points it at a temp file so tests never write the
# real one).
LEDGER = Path(os.environ.get("LLM_ROUTE_LEDGER")
              or ROOT / "loop" / "state" / "llm_route_ledger.json")
LEDGER_KEEP = 20
STANDING_WINDOW = 12
STANDING_MIN_EVENTS = 4
STANDING_GOOD_RATE = 0.5
CALL_OUTCOMES = ("answered", "empty", "error", "rate_limited", "timeout")
VERDICT_OUTCOMES = ("passed", "failed_validation")
FAIL_OUTCOMES = ("failed_validation", "empty", "error", "timeout",
                 "rate_limited")

TRANSIENT_HTTP_CODES = (500, 502, 503, 504)
TRANSIENT_RETRIES = 3
TRANSIENT_BACKOFF_S = 2.0
KEY_INVALID_CODES = (401,)
KEY_REFUSED_CODES = (401, 402, 403)

KEY_DISABLED = "OPENROUTER_KEY_DISABLED_OR_INVALID"
NO_FREE_MODEL = "OPENROUTER_NO_FREE_MODEL"
PAID_MODEL_REFUSED = "OPENROUTER_PAID_MODEL_REFUSED"
PAID_COST_REFUSED = "OPENROUTER_PAID_COST_REFUSED"
# Codes that mean "no model call will succeed this run" - a lane should stop
# rather than try its next item.
FATAL_CODES = (KEY_DISABLED, NO_FREE_MODEL, PAID_MODEL_REFUSED,
               PAID_COST_REFUSED)


class LLMStop(Exception):
    """A named, expected failure of the model route."""

    def __init__(self, code: str, message: str, unblock: str = "",
                 detail: object = None):
        super().__init__(f"[{code}] {message}")
        self.code, self.message, self.unblock = code, message, unblock
        self.detail = detail


class RoutingConfigError(ValueError):
    """config/llm_routing.json is malformed or names a model that costs money."""


def _is_zero(v: object) -> bool:
    try:
        return float(v) == 0.0
    except (TypeError, ValueError):
        return False


def config_problems(cfg: dict) -> list[str]:
    """Everything wrong with a routing config. Empty list = valid."""
    out = []
    if not str(cfg.get("snapshot_date") or "").strip():
        out.append("no snapshot_date")
    if cfg.get("max_cost_usd") != 0:
        out.append(f"max_cost_usd is {cfg.get('max_cost_usd')!r}, must be 0")
    if cfg.get("paid_fallback") is not False:
        out.append("paid_fallback must be false")
    models = cfg.get("models") or []
    if not models:
        out.append("no models listed")
    floor = cfg.get("min_context_length") or 32000
    seen = set()
    for m in models:
        mid = (m or {}).get("id") or ""
        if not mid:
            out.append("a model row has no id")
            continue
        if mid in seen:
            out.append(f"{mid} listed twice")
        seen.add(mid)
        if not mid.endswith(":free"):
            out.append(f"{mid} is not a ':free' variant")
        p = m.get("pricing") or {}
        for k in ("prompt", "completion"):
            if not _is_zero(p.get(k)):
                out.append(f"{mid} pricing.{k} is {p.get(k)!r}, must be 0")
        for k, v in p.items():
            if not _is_zero(v):
                out.append(f"{mid} pricing.{k} is {v!r}, must be 0")
        if (m.get("context_length") or 0) < floor:
            out.append(f"{mid} context {m.get('context_length')} < {floor}")
    gr = cfg.get("gemini_route")
    if gr is not None:
        if not isinstance(gr, dict):
            out.append("gemini_route must be an object")
        else:
            if gr.get("provider") != "google-ai-studio":
                out.append("gemini_route.provider must be 'google-ai-studio'")
            if gr.get("env") != GEMINI_ENV:
                out.append(f"gemini_route.env must be {GEMINI_ENV!r}")
            if gr.get("free_tier_only") is not True:
                out.append("gemini_route.free_tier_only must be true")
            gm = gr.get("models")
            if not isinstance(gm, list) or not gm or not all(
                    isinstance(m, str) and m.strip() and "/" not in m
                    for m in gm):
                out.append("gemini_route.models must be a non-empty list of "
                           "bare Gemini model names")
    sr = cfg.get("subscription_route")
    if sr is not None:
        if not isinstance(sr, dict):
            out.append("subscription_route must be an object")
        else:
            if sr.get("provider") != "claude-code":
                out.append("subscription_route.provider must be 'claude-code'")
            if sr.get("env") != "CLAUDE_CODE_OAUTH_TOKEN":
                out.append("subscription_route.env must be "
                           "'CLAUDE_CODE_OAUTH_TOKEN' (never an API key)")
            if not str(sr.get("model") or "").strip():
                out.append("subscription_route.model is empty")
    return sorted(set(out))


def load_config(path: Path | None = None) -> dict:
    cfg = json.loads((path or CONFIG).read_text())
    problems = config_problems(cfg)
    if problems:
        raise RoutingConfigError(f"{(path or CONFIG).name}: "
                                 + "; ".join(problems))
    return cfg


def free_models() -> list[str]:
    return [m["id"] for m in load_config()["models"]]


def default_model() -> str:
    return free_models()[0]


def is_free(model: str) -> bool:
    return (model or "").strip() in free_models()


def reported_cost(resp: dict) -> float | None:
    usage = resp.get("usage") or {}
    cost = usage.get("cost")
    if cost is None and usage.get("cost_details"):
        cost = usage["cost_details"].get("upstream_inference_cost")
    return cost


def _post(body: bytes, key: str, timeout: int) -> dict:
    """One model, with retries for transient server errors only."""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/seq23/how-we-know",
        "X-Title": "How We Know - free model route",
    }
    last: Exception | None = None
    for attempt in range(1, TRANSIENT_RETRIES + 1):
        req = urllib.request.Request(API, data=body, method="POST",
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if attempt > 1:
                    print(f"[self-heal] OpenRouter call succeeded on attempt "
                          f"{attempt}/{TRANSIENT_RETRIES}", flush=True)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in TRANSIENT_HTTP_CODES or attempt == TRANSIENT_RETRIES:
                raise
            last = e
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if attempt == TRANSIENT_RETRIES:
                raise
            last = e
        print(f"[self-heal] OpenRouter attempt {attempt}/{TRANSIENT_RETRIES} "
              f"failed ({type(last).__name__}: {last}); retrying",
              flush=True)
        time.sleep(TRANSIENT_BACKOFF_S * attempt)
    raise last  # pragma: no cover


# ---- the subscription tier (owner 2026-10-12) ------------------------------
SUBSCRIPTION_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
SUBSCRIPTION_MODEL = "opus"
SUBSCRIPTION_MODEL_USED = "claude-subscription/opus"
SUBSCRIPTION_TIMEOUT_S = 600
CLAUDE_CLI_VERSION = "2.1.296"


def _subscription_command(system: str) -> list[str]:
    """The headless CLI call. NOT --bare: --bare reads only ANTHROPIC_API_KEY
    and never the OAuth token (verified 2026-10-12 with CLI 2.1.296), so it
    would make this tier inert. The flags below keep the context minimal
    instead (~650 tokens for a one-line prompt, measured): our own system
    prompt, no tools, no settings files, no MCP, no skills, run from an empty
    directory so no CLAUDE.md is discovered. The token travels only in the
    environment, never in argv."""
    return ["claude", "-p", "--output-format", "json",
            "--model", SUBSCRIPTION_MODEL, "--max-turns", "1",
            "--tools", "", "--no-session-persistence",
            "--setting-sources", "", "--strict-mcp-config",
            "--disable-slash-commands",
            "--exclude-dynamic-system-prompt-sections",
            "--system-prompt", system]


def _render_turns(messages: list[dict]) -> tuple[str, str]:
    """system = every system message joined; user = the rest in order. A
    single user turn goes as-is; a multi-turn exchange (author.draft() appends
    the rejected draft and the corrections) is rendered 'user:'/'assistant:'."""
    system = "\n\n".join(str(m.get("content") or "") for m in messages
                          if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    if len(rest) == 1 and rest[0].get("role") == "user":
        return system, str(rest[0].get("content") or "")
    user = "\n\n".join(f"{m.get('role') or 'user'}:\n{m.get('content') or ''}"
                        for m in rest)
    return system, user


def _scrub(text: str) -> str:
    tok = os.environ.get(SUBSCRIPTION_ENV) or ""
    text = (text or "").replace("\n", " ").strip()
    if tok:
        text = text.replace(tok, "<token>")
    return text[:200]


def subscription_timeout(caller_timeout: int) -> int:
    """600 s for the long authoring calls (author.draft() asks for 300 on
    OpenRouter); a caller that asked for less (localize 90/180, comments and
    advise 120) keeps its own, so a short-ceiling lane (loop-reach.yml: 6 min)
    is never held past its job budget by a hung CLI before the fallback."""
    return SUBSCRIPTION_TIMEOUT_S if caller_timeout >= 300 else max(30, caller_timeout)


def _subscription_complete(messages: list[dict],
                           caller_timeout: int = 300) -> dict | None:
    """Her Claude subscription, or None (and one log line) on any failure.
    Never raises; never called when the env var is absent."""
    if not (os.environ.get(SUBSCRIPTION_ENV) or "").strip():
        return None
    # The config is the switch too: no subscription_route, no tier.
    if not load_config().get("subscription_route"):
        return None
    fall = " — falling back to the $0 route"
    limit = subscription_timeout(caller_timeout)
    try:
        if not shutil.which("claude"):
            print(f"[claude-route] no `claude` binary on PATH{fall}", flush=True)
            return None
        system, user = _render_turns(messages)
        with tempfile.TemporaryDirectory(prefix="claude-route-") as cwd:
            proc = subprocess.run(_subscription_command(system), input=user,
                                  capture_output=True, text=True,
                                  timeout=limit,
                                  env=os.environ, cwd=cwd)
        if proc.returncode != 0:
            print(f"[claude-route] exit {proc.returncode}: "
                  f"{_scrub(proc.stderr or proc.stdout)}{fall}", flush=True)
            return None
        out = json.loads(proc.stdout or "")
        result = str(out.get("result") or "")
        if out.get("is_error") or not result.strip():
            why = "is_error" if out.get("is_error") else "empty result"
            print(f"[claude-route] {why}: {_scrub(result)}{fall}", flush=True)
            return None
    except subprocess.TimeoutExpired:
        print(f"[claude-route] timed out after {limit}s{fall}",
              flush=True)
        return None
    except Exception as e:                          # noqa: BLE001
        print(f"[claude-route] {type(e).__name__}: {_scrub(str(e))}{fall}",
              flush=True)
        return None
    usage = dict(out.get("usage") or {})
    pin = sum(int(usage.get(k) or 0) for k in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    pout = int(usage.get("output_tokens") or 0)
    usage.update({"prompt_tokens": pin, "completion_tokens": pout,
                  "total_tokens": pin + pout,
                  # The CLI's total_cost_usd is a nominal figure under a
                  # subscription, not a charge; kept for the record only.
                  "nominal_cost_usd": out.get("total_cost_usd"),
                  "cost": 0})
    print(f"[claude-route] answered by {SUBSCRIPTION_MODEL_USED}", flush=True)
    return {"choices": [{"message": {"role": "assistant", "content": result},
                         "finish_reason": "stop"}],
            "usage": usage, "model_used": SUBSCRIPTION_MODEL_USED,
            "route": "claude-subscription"}


# ---- the Gemini free tier (owner 2026-10-12) -------------------------------
def gemini_models() -> list[str]:
    """"gemini/<model>" ids, in config order - empty unless the key is set."""
    if not os.environ.get(GEMINI_ENV, "").strip():
        return []
    gr = load_config().get("gemini_route") or {}
    return [GEMINI_PREFIX + m.strip() for m in gr.get("models") or []
            if isinstance(m, str) and m.strip()]


def roster() -> list[str]:
    """Every model complete() may walk: Gemini (when keyed), then the $0 list."""
    return gemini_models() + free_models()


def _gemini_post(body: bytes, key: str, timeout: int) -> dict:
    req = urllib.request.Request(GEMINI_API, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _gemini_try(model: str, messages: list[dict], timeout: int,
                temperature: float) -> tuple[dict | None, str]:
    """One Gemini model -> (response, "") or (None, why). Never raises."""
    key = os.environ.get(GEMINI_ENV, "").strip()
    name = model[len(GEMINI_PREFIX):]
    body = json.dumps({"model": name, "messages": messages,
                       "temperature": temperature}).encode()
    t0 = time.monotonic()
    try:
        resp = _gemini_post(body, key, timeout)
    except Exception as e:                          # noqa: BLE001
        _record(model, _call_outcome(e), time.monotonic() - t0)
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = e.read().decode("utf-8", "ignore")[:120]
            except Exception:                       # noqa: BLE001
                detail = ""
            why = f"HTTP {e.code} {detail}"
        else:
            why = f"{type(e).__name__}: {str(e)[:120]}"
        why = why.replace(key, "<key>") if key else why
        print(f"[gemini-route] skipped {model}: {why.splitlines()[0] if why else ''}",
              flush=True)
        return None, why
    latency = time.monotonic() - t0
    choice = ((resp or {}).get("choices") or [{}])[0]
    if not ((choice.get("message") or {}).get("content") or "").strip():
        _record(model, "empty", latency)
        print(f"[gemini-route] skipped {model}: empty answer", flush=True)
        return None, "empty answer"
    _record(model, "answered", latency)
    usage = dict(resp.get("usage") or {})
    usage["cost"] = 0          # free tier; Google reports no cost field
    resp["usage"] = usage
    resp["model_used"] = model
    resp["route"] = GEMINI_ROUTE_NAME
    return resp, ""

# ---- the measured fallback order (owner 2026-10-12) ------------------------
def _lane() -> str:
    lane = os.environ.get("LOOP_STAGE", "").strip()
    if lane:
        return lane
    return os.path.basename(sys.argv[0] or "") or "unknown"


def read_ledger() -> dict:
    try:
        data = json.loads(Path(LEDGER).read_text())
    except (OSError, ValueError):
        return {"models": {}}
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        return {"models": {}}
    return data


def _record(model: str, outcome: str, latency_s: float | None = None) -> None:
    """Append one outcome for a free model. Never raises: the ledger is
    measurement, and a write failure must not cost a lane its answer. Only
    a model id, an outcome word, a latency and a lane name are stored -
    never a prompt, a draft, a key or the subscription tier."""
    model = (model or "").strip()
    if not model or model == SUBSCRIPTION_MODEL_USED:
        return
    if outcome not in CALL_OUTCOMES + VERDICT_OUTCOMES:
        return
    try:
        data = read_ledger()
        ev = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "outcome": outcome,
              "latency_s": (round(float(latency_s), 1)
                            if latency_s is not None else None),
              "lane": _lane()}
        rows = data["models"].setdefault(model, [])
        rows.append(ev)
        data["models"][model] = rows[-LEDGER_KEEP:]
        data["_why"] = ("Measured $0 fallback order (owner 2026-10-12). "
                        "Written by loop/llm_router.py; ranked by "
                        "`python3 loop/llm_router.py standing`. See RUNBOOK.md "
                        "'Fallback standing'.")
        Path(LEDGER).parent.mkdir(parents=True, exist_ok=True)
        Path(LEDGER).write_text(json.dumps(data, indent=2, sort_keys=True)
                                + "\n")
    except Exception as e:                          # noqa: BLE001
        print(f"[free-route] route ledger not written: {type(e).__name__}",
              flush=True)


def record_validation(model: str, ok: bool) -> None:
    """loop/author.py's structural verdict on an answer this route gave."""
    _record(model, "passed" if ok else "failed_validation")


def standing(models: list[str] | None = None,
             ledger: dict | None = None) -> list[dict]:
    """The config's free models in measured order (see the module docstring).
    Each row: model, bucket, events, pass_rate, median_latency_s, last."""
    models = list(models if models is not None else roster())
    data = ledger if ledger is not None else read_ledger()
    rows = []
    for i, m in enumerate(models):
        evs = (data.get("models") or {}).get(m) or []
        window = evs[-STANDING_WINDOW:]
        passed = sum(1 for e in window if e.get("outcome") == "passed")
        failed = sum(1 for e in window if e.get("outcome") in FAIL_OUTCOMES)
        judged = passed + failed
        rate = passed / judged if judged else None
        lats = [e["latency_s"] for e in window
                if isinstance(e.get("latency_s"), (int, float))]
        n = len(window)
        # Bucketed on JUDGED events: an answer with no verdict yet (a lane
        # that does not validate, or a draft still being checked) is neither
        # a pass nor a failure, so it cannot make a model measured.
        if judged < STANDING_MIN_EVENTS:
            bucket = "UNMEASURED"
        elif (rate or 0.0) >= STANDING_GOOD_RATE:
            bucket = "MEASURED-GOOD"
        else:
            bucket = "MEASURED-BAD"
        rows.append({"model": m, "bucket": bucket, "events": n,
                     "judged": judged,
                     "pass_rate": rate,
                     "median_latency_s": (statistics.median(lats)
                                          if lats else None),
                     "last": (evs[-1].get("outcome") if evs else None),
                     "_config_index": i})
    inf = float("inf")
    good = sorted((r for r in rows if r["bucket"] == "MEASURED-GOOD"),
                  key=lambda r: (-(r["pass_rate"] or 0.0),
                                 r["median_latency_s"]
                                 if r["median_latency_s"] is not None else inf,
                                 r["_config_index"]))
    unmeasured = [r for r in rows if r["bucket"] == "UNMEASURED"]
    bad = sorted((r for r in rows if r["bucket"] == "MEASURED-BAD"),
                 key=lambda r: (-(r["pass_rate"] or 0.0), r["_config_index"]))
    out = good + unmeasured + bad
    for r in out:
        r.pop("_config_index", None)
    return out


def route_order(preferred: str | None = None,
                rows: list[dict] | None = None) -> list[str]:
    """standing() order with `preferred` placed by the documented rule."""
    rows = rows if rows is not None else standing()
    order = [r["model"] for r in rows]
    pref = (preferred or "").strip()
    if not pref or pref not in order:
        return order
    bucket = next(r["bucket"] for r in rows if r["model"] == pref)
    if bucket == "MEASURED-BAD":
        # Loses its preference: it keeps its measured place, after every
        # MEASURED-GOOD and UNMEASURED model.
        return order
    order.remove(pref)
    return [pref] + order


def standing_lines(rows: list[dict] | None = None) -> list[str]:
    rows = rows if rows is not None else standing()
    out = []
    for i, r in enumerate(rows, 1):
        rate = "-" if r["pass_rate"] is None else f"{r['pass_rate']:.2f}"
        lat = ("-" if r["median_latency_s"] is None
               else f"{r['median_latency_s']:.1f}s")
        out.append(f"{i}. {r['model']}  {r['bucket']}  "
                   f"events={r['events']} (judged {r['judged']})  "
                   f"pass_rate={rate}  median_latency={lat}  "
                   f"last={r['last'] or '-'}")
    return out


def _call_outcome(e: BaseException) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return "rate_limited" if e.code == 429 else "error"
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(e, urllib.error.URLError) and isinstance(
            getattr(e, "reason", None), (TimeoutError, socket.timeout)):
        return "timeout"
    return "error"


def complete(messages: list[dict], key: str, *, preferred: str | None = None,
             timeout: int = 300, temperature: float = 0.4,
             max_tokens: int = 16000) -> dict:
    """Send `messages` to the first free model that answers.

    `preferred` (a lane's configured model) goes first if - and only if - it
    is in the free list; naming a model outside it is refused outright, never
    silently swapped, so a paid model in a variable is seen.
    The free models are walked in measured order (standing()); a MEASURED-
    BAD `preferred` model is not moved first - it keeps its measured place,
    after the MEASURED-GOOD (and UNMEASURED) ones.
    Every call outcome is written to the route ledger.
    Returns OpenRouter's response dict; `resp["model_used"]` names the model.
    """
    models = free_models()
    # The subscription tier's own name is not an OpenRouter model: a caller
    # that recorded it (author.draft() retries with model_used) gets the
    # normal free order behind the subscription tier, never a refusal.
    if preferred and preferred.strip() == SUBSCRIPTION_MODEL_USED:
        preferred = None
    sub = _subscription_complete(messages, timeout)
    if sub is not None:
        return sub
    gem = gemini_models()
    # A retry naming a Gemini model while the key is absent goes back to the
    # normal order; it is not a paid model, so it is not refused.
    if preferred and preferred.strip().startswith(GEMINI_PREFIX) \
            and preferred.strip() not in gem:
        preferred = None
    models = gem + models
    if preferred and preferred.strip() and preferred.strip() not in models:
        raise LLMStop(
            PAID_MODEL_REFUSED,
            f"{preferred.strip()!r} is not in config/llm_routing.json; only "
            f"$0 models may be called",
            "Unset $OPENROUTER_MODEL / $OPENROUTER_COMMENTS_MODEL or set it to "
            "a model listed in config/llm_routing.json.")
    order = route_order(preferred, standing(models))

    failures, codes = [], []
    key_stop_unblock = (
        "The key is revoked, disabled or invalid. Mint a new one at "
        "https://openrouter.ai/settings/keys (a $0 credit limit is fine - "
        "only free models are called) and store it as OPENROUTER_API_KEY "
        "(Actions) and .secrets/openrouter_key.txt (Mac).")
    for model in order:
        if model in gem:
            resp, why = _gemini_try(model, messages, timeout, temperature)
            if resp is not None:
                if failures:
                    print(f"[free-route] answered by {model} after: "
                          + " | ".join(failures), flush=True)
                return resp
            failures.append(f"{model}: {why[:120]}")
            continue
        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "usage": {"include": True},
            # OpenRouter refuses any endpoint above this price. 0 = free only.
            "provider": {"max_price": {"prompt": 0, "completion": 0}},
        }).encode()
        t0 = time.monotonic()
        try:
            resp = _post(body, key, timeout)
        except urllib.error.HTTPError as e:
            _record(model, _call_outcome(e), time.monotonic() - t0)
            detail = e.read().decode("utf-8", "ignore")[:200].replace(key, "<key>")
            if e.code in KEY_INVALID_CODES:
                raise LLMStop(KEY_DISABLED,
                              f"OpenRouter refused the key (HTTP {e.code}) on "
                              f"free model {model}",
                              key_stop_unblock, detail) from None
            codes.append(e.code)
            failures.append(f"{model}: HTTP {e.code} {detail[:120]}")
            continue
        except Exception as e:                      # noqa: BLE001
            _record(model, _call_outcome(e), time.monotonic() - t0)
            codes.append(None)
            failures.append(f"{model}: {type(e).__name__}: {str(e)[:120]}")
            continue
        latency = time.monotonic() - t0
        cost = reported_cost(resp)
        if cost is not None and not _is_zero(cost):
            raise LLMStop(
                PAID_COST_REFUSED,
                f"OpenRouter reported cost ${cost} for {model}; this repo may "
                f"spend $0",
                "A listed model is no longer free. Refresh "
                "config/llm_routing.json from https://openrouter.ai/api/v1/models.",
                {"model": model, "cost": cost})
        choice = (resp.get("choices") or [{}])[0]
        if not ((choice.get("message") or {}).get("content") or "").strip():
            _record(model, "empty", latency)
            codes.append(None)
            failures.append(f"{model}: empty answer")
            continue
        _record(model, "answered", latency)
        if failures:
            print(f"[free-route] answered by {model} after: "
                  + " | ".join(failures), flush=True)
        resp["model_used"] = model
        return resp
    if codes and all(c in KEY_REFUSED_CODES for c in codes):
        raise LLMStop(KEY_DISABLED,
                      f"OpenRouter refused the key on all {len(order)} free "
                      f"models", key_stop_unblock, failures)
    raise LLMStop(
        NO_FREE_MODEL,
        f"none of the {len(order)} free models answered",
        "Usually a free-tier rate limit or an outage; the lane retries on its "
        "next schedule. If it repeats, refresh config/llm_routing.json.",
        failures)


if __name__ == "__main__":
    if sys.argv[1:2] == ["standing"]:
        print(f"free-route standing (ledger: {Path(LEDGER).name}; "
              f"order used by complete()):")
        for line in standing_lines():
            print("  " + line)
        raise SystemExit(0)
    print(json.dumps({"snapshot_date": load_config()["snapshot_date"],
                      "models": free_models()}, indent=2))
