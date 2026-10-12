"""Nothing in this repo may call a paid model (owner, 2026-10-11).

"nothing should be paid ... cut the probes and make them free." The repo's
OpenRouter key has a $0 credit limit; these checks make sure no code tries to
spend anyway, and that every failure of the free route is a named stop.

  A. config/llm_routing.json lists only ':free' models priced 0/0, >=32k
     context, with a snapshot date, max_cost_usd 0, paid_fallback false.
     Proven negatively: a paid row, a missing date, a paid fallback each fail.
  B. No workflow, script or loop module names a paid model or sets a model
     variable: every vendor/model literal in .github/workflows, bin/, scripts/
     and loop/*.py is one of the free models.
  C. The router: a paid model is refused before the network; every request
     names a free model and carries provider.max_price 0; a 429 moves to the
     next free model; HTTP 401 -> OPENROUTER_KEY_DISABLED_OR_INVALID; every
     model 403 -> the same; every model failing -> OPENROUTER_NO_FREE_MODEL;
     a reported cost above 0 -> OPENROUTER_PAID_COST_REFUSED.
  D. The Monday lane: a free model's unusable draft is retried on the free
     route only and ends in DRAFT_FAILED_VALIDATION (-> AUTHOR_REQUIRED);
     a refused key reaches draft() as its own code.

No network. Hard-fails if it examines nothing.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import llm_router as R  # noqa: E402

KEY = "sk-or-v1-" + "0" * 64
VENDORS = ("anthropic", "openai", "google", "meta-llama", "mistralai", "x-ai",
           "deepseek", "qwen", "cohere", "nvidia", "thinkingmachines",
           "moonshotai", "z-ai", "perplexity", "amazon", "microsoft",
           "minimax", "inclusionai", "openrouter", "nousresearch")
MODEL_RE = re.compile(r"""["'\s=]((?:%s)/[A-Za-z0-9._\-]+(?::[a-z]+)?)["'\s]"""
                      % "|".join(re.escape(v) for v in VENDORS))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(text="fine", cost=0):
    return {"choices": [{"message": {"content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                      "cost": cost}}


def _http(code):
    return urllib.error.HTTPError(R.API, code, "x", {}, io.BytesIO(b"{}"))


def check() -> list[str]:
    fails: list[str] = []
    examined = 0

    # --------------------------------------------------------------- A. config
    cfg = json.loads(R.CONFIG.read_text())
    examined += 1
    probs = R.config_problems(cfg)
    if probs:
        fails.append(f"config/llm_routing.json: {probs}")
    if len(cfg.get("models") or []) < 3:
        fails.append("config/llm_routing.json lists fewer than 3 free models; "
                     "one rate limit would stop every lane")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cfg.get("snapshot_date"))):
        fails.append("snapshot_date is not YYYY-MM-DD")
    examined += 1
    if cfg.get("reasoning_max_tokens") != 2000 or cfg.get("max_tokens") != 24000:
        fails.append(f"reasoning_max_tokens/max_tokens are "
                     f"{cfg.get('reasoning_max_tokens')!r}/{cfg.get('max_tokens')!r}"
                     f", pinned at 2000/24000 by the 2026-10-12 bench")
    if "research/free_model_bench/2026-10-12.md" not in " ".join(cfg.get("_why") or []) \
            or "reasoning_max_tokens" not in " ".join(cfg.get("_why") or []):
        fails.append("config _why does not cite the bench for reasoning_max_tokens")
    free = R.free_models()
    # Negative proofs: each break must be caught by config_problems().
    for name, mutate in (
            ("a paid row", lambda c: c["models"][0]["pricing"].update(
                completion="0.000015")),
            ("a non-:free id", lambda c: c["models"][0].update(
                id="anthropic/claude-sonnet-4.5")),
            ("no snapshot date", lambda c: c.pop("snapshot_date")),
            ("a paid fallback", lambda c: c.update(paid_fallback=True)),
            ("a budget above 0", lambda c: c.update(max_cost_usd=5)),
            # Reasoning cap (bench 2026-10-12): uncapped reasoning models
            # spent the whole max_tokens thinking and returned empty text.
            ("no reasoning cap", lambda c: c.pop("reasoning_max_tokens")),
            ("a reasoning cap below OpenRouter's 1024 floor",
             lambda c: c.update(reasoning_max_tokens=500)),
            ("a string reasoning cap",
             lambda c: c.update(reasoning_max_tokens="2000")),
            ("no max_tokens", lambda c: c.pop("max_tokens")),
            ("max_tokens leaving under 16,000 for the script",
             lambda c: c.update(max_tokens=c["reasoning_max_tokens"] + 15000)),
            ("max_tokens above a model's completion limit",
             lambda c: c["models"][0].update(max_completion_tokens=8000))):
        examined += 1
        bad = json.loads(json.dumps(cfg))
        mutate(bad)
        if not R.config_problems(bad):
            fails.append(f"config_problems() accepted {name}")

    # ----------------------------------------------- B. no paid model anywhere
    files = (sorted((ROOT / ".github" / "workflows").glob("*.yml"))
             + sorted(LOOP.glob("*.py"))
             + [p for d in ("bin", "scripts") for p in sorted((ROOT / d).rglob("*"))
                if p.is_file() and p.suffix in ("", ".sh", ".py")])
    seen_models = 0
    # The scan itself must see a paid literal where one is written.
    examined += 1
    if not MODEL_RE.search('  OPENROUTER_MODEL: "anthropic/claude-sonnet-4.5"\n'):
        fails.append("the paid-model scan cannot see a quoted vendor/model id")
    for f in files:
        try:
            text = f.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        examined += 1
        for m in MODEL_RE.finditer(text):
            seen_models += 1
            mid = m.group(1)
            # A comment recording what the repo USED to send is history, not
            # a call. Every live literal must be free.
            line = text[:m.start()].rsplit("\n", 1)[-1] + text[m.start():].split("\n", 1)[0]
            if line.lstrip().startswith("#") or "(was " in line or "Was " in line \
                    or "until then" in line.lower():
                continue
            if mid not in free:
                fails.append(f"{f.relative_to(ROOT)} names {mid}, which is not "
                             f"in config/llm_routing.json")
        if f.suffix == ".yml" and re.search(
                r"^\s*OPENROUTER_(COMMENTS_)?MODEL\s*:", text, re.M):
            fails.append(f"{f.relative_to(ROOT)} sets a model variable; the "
                         f"router owns the model")

    # ---------------------------------------------------------- C. the router
    real_post, real_sleep = R._post, R.time.sleep
    R.time.sleep = lambda s: None
    sent: list[dict] = []

    def run(script, preferred=None):
        """script: list of results per call - a dict (answer) or int (HTTP)."""
        it = iter(script)

        def fake(body, key, timeout):
            sent.append(json.loads(body))
            r = next(it)
            if isinstance(r, int):
                raise _http(r)
            return r
        R._post = fake
        return R.complete([{"role": "user", "content": "x"}], KEY,
                          preferred=preferred)

    try:
        examined += 1
        sent.clear()
        try:
            run([_ok()], preferred="anthropic/claude-sonnet-4.5")
            fails.append("a paid preferred model was sent")
        except R.LLMStop as e:
            if e.code != R.PAID_MODEL_REFUSED or sent:
                fails.append(f"paid model: {e.code}, {len(sent)} request(s)")

        examined += 1
        sent.clear()
        r = run([429, _ok()])
        if r.get("model_used") != free[1]:
            fails.append(f"429 on {free[0]} did not move to {free[1]}")
        for b in sent:
            if b["model"] not in free:
                fails.append(f"router sent non-free model {b['model']}")
            if (b.get("provider") or {}).get("max_price") != {"prompt": 0,
                                                             "completion": 0}:
                fails.append("a request lacks provider.max_price = 0")
            # The reasoning cap rides on every OpenRouter request, in the
            # max_tokens form (effort is not accepted by every listed model;
            # exclude would still spend the budget).
            if b.get("reasoning") != {"max_tokens": cfg["reasoning_max_tokens"]}:
                fails.append(f"a request's reasoning is {b.get('reasoning')!r}, "
                             f"not {{'max_tokens': {cfg['reasoning_max_tokens']}}}")
            if b.get("max_tokens") != cfg["max_tokens"]:
                fails.append(f"a request's max_tokens is {b.get('max_tokens')}, "
                             f"not config's {cfg['max_tokens']}")
        if not sent:
            fails.append("no request body examined for the reasoning cap")

        for script, want, name in (
                ([401], R.KEY_DISABLED, "HTTP 401"),
                ([403] * len(free), R.KEY_DISABLED, "403 from every model"),
                ([429] * len(free), R.NO_FREE_MODEL, "429 from every model"),
                ([_ok("")] * len(free), R.NO_FREE_MODEL, "empty answers"),
                ([_ok(cost=0.0123)], R.PAID_COST_REFUSED, "a non-zero cost")):
            examined += 1
            sent.clear()
            try:
                run(script)
                fails.append(f"{name}: no stop raised")
            except R.LLMStop as e:
                if e.code != want:
                    fails.append(f"{name}: raised {e.code}, expected {want}")
            except StopIteration:
                fails.append(f"{name}: router called more models than listed")
    finally:
        R._post = real_post

    # ------------------------------------------------------ D. the Monday lane
    import author  # noqa: E402
    if author.DEFAULT_MODEL != free[0]:
        fails.append(f"author.DEFAULT_MODEL is {author.DEFAULT_MODEL}, not the "
                     f"first free model")
    real = (author.dead_urls, author.record_spend, author.DRAFTS,
            author.shape_problems)
    (LOOP / "drafts").mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=LOOP / "drafts") as td:
            author.dead_urls = lambda t: []
            author.record_spend = lambda *a, **k: None
            author.shape_problems = lambda *a, **k: ["unusable: no sections"]
            author.DRAFTS = Path(td)
            pov = {"pov_id": "t", "line": "I once saw this myself."}

            examined += 1
            sent.clear()
            R._post = lambda body, key, timeout: (sent.append(json.loads(body))
                                                  or _ok("junk"))
            try:
                author.draft("Q?", "free-unusable", pov, key=KEY)
                fails.append("an unusable free draft was accepted")
            except author.AuthorStop as e:
                if e.code != "DRAFT_FAILED_VALIDATION":
                    fails.append(f"unusable free draft -> {e.code}, expected "
                                 f"DRAFT_FAILED_VALIDATION (-> AUTHOR_REQUIRED)")
            if len(sent) != author.MAX_ATTEMPTS:
                fails.append(f"unusable draft made {len(sent)} calls, expected "
                             f"{author.MAX_ATTEMPTS}")
            if any(b["model"] not in free for b in sent):
                fails.append("the authoring retry sent a non-free model")

            examined += 1

            def _refused(body, key, timeout):
                raise _http(401)
            R._post = _refused
            try:
                author.draft("Q?", "free-refused", pov, key=KEY)
                fails.append("a refused key drafted anyway")
            except author.AuthorStop as e:
                if e.code != R.KEY_DISABLED:
                    fails.append(f"refused key -> {e.code}, expected {R.KEY_DISABLED}")
    finally:
        R._post, R.time.sleep = real_post, real_sleep
        (author.dead_urls, author.record_spend, author.DRAFTS,
         author.shape_problems) = real

    # Every new code is classified.
    policy = json.loads((LOOP / "stop_policy.json").read_text())
    for code in (R.KEY_DISABLED, R.NO_FREE_MODEL, R.PAID_MODEL_REFUSED,
                 R.PAID_COST_REFUSED):
        examined += 1
        if not any(code in (policy.get(s) or {}) for s in
                   ("self_resolving", "owner_action", "needs_human")):
            fails.append(f"{code} is not classified in loop/stop_policy.json")

    if seen_models == 0:
        fails.append("found no model literal anywhere - the paid-model scan "
                     "examined nothing")
    if examined == 0:
        fails.append("examined ZERO routing cases")
    print(f"inspected {examined} routing case(s), {seen_models} model literal(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - $0 models only, every failure named" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
