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

Callers keep their own semantics for USABLE output (loop/author.py retries a
draft that fails validation against the SAME free route and then raises
DRAFT_FAILED_VALIDATION, which the Monday lane turns into AUTHOR_REQUIRED).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "llm_routing.json"
API = "https://openrouter.ai/api/v1/chat/completions"

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


def complete(messages: list[dict], key: str, *, preferred: str | None = None,
             timeout: int = 300, temperature: float = 0.4,
             max_tokens: int = 16000) -> dict:
    """Send `messages` to the first free model that answers.

    `preferred` (a lane's configured model) goes first if - and only if - it
    is in the free list; naming a model outside it is refused outright, never
    silently swapped, so a paid model in a variable is seen.
    Returns OpenRouter's response dict; `resp["model_used"]` names the model.
    """
    models = free_models()
    if preferred and preferred.strip() and preferred.strip() not in models:
        raise LLMStop(
            PAID_MODEL_REFUSED,
            f"{preferred.strip()!r} is not in config/llm_routing.json; only "
            f"$0 models may be called",
            "Unset $OPENROUTER_MODEL / $OPENROUTER_COMMENTS_MODEL or set it to "
            "a model listed in config/llm_routing.json.")
    order = ([preferred.strip()] if preferred and preferred.strip() else []) \
        + [m for m in models if m != (preferred or "").strip()]

    failures, codes = [], []
    key_stop_unblock = (
        "The key is revoked, disabled or invalid. Mint a new one at "
        "https://openrouter.ai/settings/keys (a $0 credit limit is fine - "
        "only free models are called) and store it as OPENROUTER_API_KEY "
        "(Actions) and .secrets/openrouter_key.txt (Mac).")
    for model in order:
        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "usage": {"include": True},
            # OpenRouter refuses any endpoint above this price. 0 = free only.
            "provider": {"max_price": {"prompt": 0, "completion": 0}},
        }).encode()
        try:
            resp = _post(body, key, timeout)
        except urllib.error.HTTPError as e:
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
            codes.append(None)
            failures.append(f"{model}: {type(e).__name__}: {str(e)[:120]}")
            continue
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
            codes.append(None)
            failures.append(f"{model}: empty answer")
            continue
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
    print(json.dumps({"snapshot_date": load_config()["snapshot_date"],
                      "models": free_models()}, indent=2))
