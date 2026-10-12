"""The $0 fallback ORDER is measured, not guessed (owner 2026-10-12).

"yes do the measured fallback PR too." Run 38235183608 (Mon 12 Oct 2026)
walked config/llm_routing.json in its written order: the first model
(nvidia/nemotron-3-ultra-550b-a55b:free) returned an EMPTY answer and cost the
lane ~5 minutes before the router moved on; the second answered every time
with drafts that never passed; the rest were never reached. loop/llm_router.py
now writes every free-model outcome and every structural verdict to
loop/state/llm_route_ledger.json and walks standing() order. This pins:

  a. an empty ledger -> exactly the config order;
  b. model 2 GOOD, model 1 BAD, model 3 UNMEASURED -> [2, 3, 1]; buckets
     count JUDGED events only (an answer with no verdict is neither);
     (proven negatively: with the sort broken this case fails);
  c. a MEASURED-BAD preferred model goes AFTER the GOOD ones, not first (it
     keeps its measured place, after UNMEASURED too);
     a non-BAD preferred model still goes first;
  d. complete() with model 1 answering empty -> the ledger records
     {empty} for model 1 and {answered} for model 2, bounded at 20 events;
  e. record_validation(ok=False) lands as failed_validation (True -> passed),
     and loop/author.py calls it right after record_spend;
  f. the ledger never holds a key ("sk-"), a prompt or a draft body, and
     never the subscription tier;
  g. config: Ultra is last and `_why` cites run 38235183608 and standing();
  h. the ledger is in mon-draft's static write set and a stage pathspec
     covers it, and its union merge driver is registered and merges;
  i. a seeded ledger (if committed) reproduces the bench ranking it was
     seeded from through standing();
  j. Gemini free tier (owner 2026-10-12): GEMINI_API_KEY absent -> no
     Gemini request; key set and 429 on model 1 -> model 2 answers with
     usage.cost 0 and model_used "gemini/<model>"; every Gemini model failing
     -> the OpenRouter loop runs; Gemini outcomes land in the ledger and
     standing() ranks them like any model; the key is never logged or stored;
     gemini_route config shape (and its negatives).

No network, no live model. Hard-fails on zero examined cases.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(LOOP / "tools"))
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)   # no subscription tier here
os.environ.pop("GEMINI_API_KEY", None)            # set per case below

import llm_router as R  # noqa: E402
import merge_route_ledger as MRL  # noqa: E402
import write_set as W  # noqa: E402

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b:free"
KEY = "sk-or-v1-" + "0" * 64
DRAFT = "SECRET-DRAFT-BODY narration paragraph that must never be stored"


def _ev(outcome, lat=10.0):
    return {"ts": "2026-10-12T00:00:00Z", "outcome": outcome,
            "latency_s": lat, "lane": "test"}


def _ok(text="fine"):
    return {"choices": [{"message": {"content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0}}


def check_b(order_fn) -> str | None:
    models = ["m1", "m2", "m3"]
    led = {"models": {
        "m1": [_ev("answered"), _ev("failed_validation")] * 4,   # 0/4 -> BAD
        "m2": [_ev("answered"), _ev("passed")] * 4,              # 4/4 -> GOOD
        "m3": [_ev("passed")],                                   # 1 -> UNMEASURED
    }}
    got = order_fn(models, led)
    if got != ["m2", "m3", "m1"]:
        return f"(b) GOOD/UNMEASURED/BAD order: got {got}, expected ['m2', 'm3', 'm1']"
    return None


def check() -> tuple[list[str], int]:
    fails: list[str] = []
    n = 0
    tmp = Path(tempfile.mkdtemp(prefix="measured-fallback-"))
    real_ledger, real_post, real_gpost = R.LEDGER, R._post, R._gemini_post

    def order(models, led):
        return [r["model"] for r in R.standing(models, led)]

    try:
        # (a) empty ledger -> config order
        n += 1
        cfg_models = R.free_models()
        if order(cfg_models, {"models": {}}) != cfg_models:
            fails.append("(a) an empty ledger did not give the config order")
        R.LEDGER = tmp / "absent.json"
        if [r["model"] for r in R.standing()] != cfg_models:
            fails.append("(a) a missing ledger file did not give the config order")

        # (b) GOOD -> UNMEASURED -> BAD
        n += 1
        msg = check_b(order)
        if msg:
            fails.append(msg)
        # negative proof: a sort that keeps config order must FAIL (b)
        n += 1
        if check_b(lambda models, led: list(models)) is None:
            fails.append("(b) negative proof: config order passed the GOOD-first case")
        # GOOD ties broken by latency; BAD by pass_rate
        n += 1
        led = {"models": {
            "slow": [_ev("passed", 90)] * 4, "fast": [_ev("passed", 5)] * 4,
            "bad0": [_ev("empty")] * 4,
            "bad1": [_ev("passed")] + [_ev("error")] * 3}}
        got = order(["bad0", "slow", "bad1", "fast"], led)
        if got != ["fast", "slow", "bad1", "bad0"]:
            fails.append(f"(b) tie-breaks: got {got}")
        # only the last 12 events count
        n += 1
        led = {"models": {"m": [_ev("failed_validation")] * 8 + [_ev("passed")] * 12}}
        r = R.standing(["m"], led)[0]
        if r["events"] != 12 or r["judged"] != 12 or r["pass_rate"] != 1.0 or r["bucket"] != "MEASURED-GOOD":
            fails.append(f"(b) window of 12 not applied: {r}")

        # (c) preferred
        n += 1
        led = {"models": {"m1": [_ev("empty")] * 4, "m2": [_ev("passed")] * 4,
                          "m4": [_ev("passed", 50)] * 4}}
        rows = R.standing(["m1", "m2", "m3", "m4"], led)
        got = R.route_order("m1", rows)
        if got != ["m2", "m4", "m3", "m1"]:
            fails.append(f"(c) BAD preferred not placed after GOOD: {got}")
        got = R.route_order("m3", rows)
        if got[0] != "m3":
            fails.append(f"(c) UNMEASURED preferred not first: {got}")
        got = R.route_order("m4", rows)
        if got[0] != "m4":
            fails.append(f"(c) GOOD preferred not first: {got}")

        # (d) complete(): model 1 empty -> {empty}, model 2 -> {answered}
        n += 1
        R.LEDGER = tmp / "ledger.json"
        m1, m2 = cfg_models[0], cfg_models[1]
        R.LEDGER.write_text(json.dumps({"models": {}}))

        def fake(body, key, timeout):
            model = json.loads(body)["model"]
            return _ok("") if model == m1 else _ok(DRAFT)
        R._post = fake
        resp = R.complete([{"role": "user", "content": "PROMPT-TEXT " + DRAFT}], KEY)
        led = json.loads(R.LEDGER.read_text())
        if resp.get("model_used") != m2:
            fails.append(f"(d) answered by {resp.get('model_used')}, expected {m2}")
        if [e["outcome"] for e in led["models"].get(m1, [])] != ["empty"]:
            fails.append(f"(d) model 1 events: {led['models'].get(m1)}")
        if [e["outcome"] for e in led["models"].get(m2, [])] != ["answered"]:
            fails.append(f"(d) model 2 events: {led['models'].get(m2)}")
        ev = (led["models"].get(m2) or [{}])[0]
        if set(ev) != {"ts", "outcome", "latency_s", "lane"}:
            fails.append(f"(d) event fields: {sorted(ev)}")
        for _ in range(3):
            R.complete([{"role": "user", "content": "x"}], KEY)
        # after 4 empties model 1 is MEASURED-BAD and goes last; model 2's
        # unjudged answers keep it UNMEASURED (neither pass nor fail)
        n += 1
        st = {r["model"]: r for r in R.standing()}
        if st[m1]["bucket"] != "MEASURED-BAD" or st[m2]["bucket"] != "UNMEASURED":
            fails.append(f"(d) buckets after 4 empties: {st[m1]['bucket']}, "
                         f"{st[m2]['bucket']}")
        for _ in range(25):
            R._record(m2, "answered", 1.0)
        led = json.loads(R.LEDGER.read_text())
        if len(led["models"][m2]) != 20 or len(led["models"][m1]) != 4:
            fails.append(f"(d) not bounded at 20: {len(led['models'][m1])}, "
                         f"{len(led['models'][m2])}")
        if R.route_order()[-1] != m1:
            fails.append(f"(d) an all-empty model is not last: {R.route_order()}")
        seen = []
        R._post = lambda body, key, timeout: (seen.append(json.loads(body)["model"])
                                              or _ok(DRAFT))
        R.complete([{"role": "user", "content": "x"}], KEY, preferred=m1)
        if seen[:1] == [m1]:
            fails.append("(d) a MEASURED-BAD preferred model was still tried first")

        # (e) record_validation
        n += 1
        R.LEDGER = tmp / "verdict.json"
        R.record_validation("m-x", False)
        R.record_validation("m-x", True)
        got = [e["outcome"] for e in json.loads(R.LEDGER.read_text())["models"]["m-x"]]
        if got != ["failed_validation", "passed"]:
            fails.append(f"(e) record_validation outcomes: {got}")
        src = (LOOP / "author.py").read_text()
        if not re.search(r"record_spend\(slug, model, usage, cost, attempt, not problems\)"
                         r"\n(?:\s*#.*\n)*\s*llm_router\.record_validation\(model, not problems\)",
                         src):
            fails.append("(e) loop/author.py does not call llm_router.record_validation "
                         "right after record_spend")

        # (f) no key, prompt, draft, or subscription tier in the ledger
        n += 1
        R.record_validation(R.SUBSCRIPTION_MODEL_USED, True)
        R._record(R.SUBSCRIPTION_MODEL_USED, "answered", 1.0)
        for p in tmp.glob("*.json"):
            text = p.read_text()
            for bad in ("sk-", "SECRET-DRAFT", "PROMPT-TEXT",
                        R.SUBSCRIPTION_MODEL_USED, "claude-subscription"):
                if bad in text:
                    fails.append(f"(f) {p.name} contains {bad!r}")
        real = ROOT / "loop" / "state" / "llm_route_ledger.json"
        if real.exists():
            text = real.read_text()
            for bad in ("sk-", "claude-subscription", "content"):
                if bad in text:
                    fails.append(f"(f) the committed ledger contains {bad!r}")

        # (g) config seed
        n += 1
        cfg = json.loads(R.CONFIG.read_text())
        ids = [m["id"] for m in cfg["models"]]
        bench = cfg.get("seeded_from_bench")
        if not bench and ids[-1] != ULTRA:
            fails.append(f"(g) {ULTRA} is not last in config models: {ids}")
        why = " ".join(cfg.get("_why") or [])
        if "38235183608" not in why or "standing()" not in why:
            fails.append("(g) config _why does not cite run 38235183608 and standing()")
        if R.config_problems(cfg):
            fails.append(f"(g) config problems: {R.config_problems(cfg)}")
        if cfg.get("max_cost_usd") != 0 or cfg.get("paid_fallback") is not False \
                or not cfg.get("subscription_route") or not cfg.get("min_context_length"):
            fails.append("(g) a config pin was lost")

        # (h) write set + merge driver
        n += 1
        table = W.pathspecs()
        a = W.audit("mon-draft", "loop/draft.py", table, W.tracked_files())
        pats = [t.pattern for t in a["targets"]]
        led_rel = "loop/state/llm_route_ledger.json"
        if led_rel not in pats:
            fails.append(f"(h) mon-draft's write set does not include {led_rel}")
        if not W.covered(led_rel, a["specs"]):
            fails.append(f"(h) no mon-draft pathspec covers {led_rel}")
        attrs = (ROOT / ".gitattributes").read_text()
        if not re.search(r"^loop/state/llm_route_ledger\.json\s+merge=route-ledger-union\s*$",
                         attrs, re.M):
            fails.append("(h) .gitattributes does not register the ledger merge driver")
        if "merge.route-ledger-union.driver" not in (ROOT / "bin" / "loop-stage.sh").read_text():
            fails.append("(h) bin/loop-stage.sh does not set merge.route-ledger-union.driver")
        ours = {"models": {"a": [dict(_ev("passed"), ts="2026-10-12T01:00:00Z")]}}
        theirs = {"models": {"a": [dict(_ev("empty"), ts="2026-10-12T00:30:00Z")],
                             "b": [_ev("error")] * 1}}
        mg = MRL.merge(ours, theirs)
        if [e["outcome"] for e in mg["models"]["a"]] != ["empty", "passed"] \
                or "b" not in mg["models"]:
            fails.append(f"(h) union merge lost an event: {mg}")
        big = {"models": {"a": [dict(_ev("passed"), ts=f"2026-10-12T00:{i:02d}:00Z")
                                for i in range(30)]}}
        if len(MRL.merge(big, {"models": {}})["models"]["a"]) != 20:
            fails.append("(h) merged ledger not bounded at 20")

        # (i) a bench-seeded committed ledger reproduces the bench ranking
        if bench:
            n += 1
            bench_rank = cfg["seeded_from_bench"].get("ranking") or []
            seeded = json.loads(real.read_text()) if real.exists() else {"models": {}}
            got = [r["model"] for r in R.standing(ids, seeded)]
            measured = [m for m in got if m in bench_rank]
            if measured != [m for m in bench_rank if m in measured] or not measured:
                fails.append(f"(i) seeded ledger order {got} != bench ranking {bench_rank}")

        # (j) the Gemini free tier
        GKEY = "AIza" + "G" * 35
        gem_ids = ["gemini/" + m for m in cfg["gemini_route"]["models"]]
        gsent, osent = [], []

        def gpost(script):
            def f(body, key, timeout):
                b = json.loads(body)
                gsent.append((b, key))
                step = script.pop(0) if script else 429
                if isinstance(step, int):
                    raise urllib.error.HTTPError(R.GEMINI_API, step, "x", {},
                                                 io.BytesIO(b'{"error":"quota"}'))
                return step
            return f

        def opost(body, key, timeout):
            osent.append(json.loads(body)["model"])
            return _ok(DRAFT)
        R._post = opost
        n += 1
        R.LEDGER = tmp / "gem-absent.json"
        R._gemini_post = gpost([_ok("gem")])
        resp = R.complete([{"role": "user", "content": "x"}], KEY)
        if gsent or not resp.get("model_used") in cfg_models:
            fails.append(f"(j) key absent but Gemini was called ({len(gsent)}) "
                         f"or no OpenRouter answer ({resp.get('model_used')})")
        if R.gemini_models():
            fails.append("(j) gemini_models() non-empty with the key absent")
        os.environ["GEMINI_API_KEY"] = GKEY
        try:
            n += 1
            R.LEDGER = tmp / "gem-429.json"
            gsent.clear(); osent.clear()
            R._gemini_post = gpost([429, {"choices": [{"message": {"content": "gem answer"},
                                                       "finish_reason": "stop"}],
                                          "usage": {"prompt_tokens": 3}}])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                resp = R.complete([{"role": "user", "content": "x"}], KEY,
                                  temperature=0.3)
            log = buf.getvalue()
            if resp.get("model_used") != gem_ids[1] or osent:
                fails.append(f"(j) 429 on Gemini model 1: answered by "
                             f"{resp.get('model_used')}, OpenRouter calls {osent}")
            if (resp.get("usage") or {}).get("cost") != 0:
                fails.append("(j) a Gemini answer must carry usage.cost == 0")
            b0 = gsent[0][0] if gsent else {}
            if b0.get("model") != cfg["gemini_route"]["models"][0] \
                    or "temperature" not in b0 or "messages" not in b0:
                fails.append(f"(j) Gemini body: {sorted(b0)} model={b0.get('model')}")
            if any(k != GKEY for _, k in gsent):
                fails.append("(j) the Gemini key was not the one sent")
            if log.count("[gemini-route]") != 1 or GKEY in log:
                fails.append(f"(j) expected one [gemini-route] line, no key: {log!r}")
            led = json.loads(R.LEDGER.read_text())
            if [e["outcome"] for e in led["models"].get(gem_ids[0], [])] != ["rate_limited"] \
                    or [e["outcome"] for e in led["models"].get(gem_ids[1], [])] != ["answered"]:
                fails.append(f"(j) Gemini ledger outcomes: {led['models']}")

            n += 1
            R.LEDGER = tmp / "gem-allfail.json"
            gsent.clear(); osent.clear()
            R._gemini_post = gpost([404, 403, 429, 500, _ok("")])
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                resp = R.complete([{"role": "user", "content": "x"}], KEY)
            if len(gsent) != len(gem_ids) or resp.get("model_used") != cfg_models[0]:
                fails.append(f"(j) all Gemini failing: {len(gsent)} Gemini calls, "
                             f"answered by {resp.get('model_used')}")
            led = json.loads(R.LEDGER.read_text())
            outs = [led["models"][g][0]["outcome"] for g in gem_ids]
            if outs != ["error", "error", "rate_limited", "error", "empty"]:
                fails.append(f"(j) all-fail Gemini outcomes: {outs}")
            if GKEY in R.LEDGER.read_text() or "AIza" in R.LEDGER.read_text():
                fails.append("(j) the Gemini key reached the ledger")

            # a rate-limited Gemini day drops it below a good OpenRouter model
            n += 1
            led = {"models": {gem_ids[0]: [_ev("rate_limited")] * 4,
                              cfg_models[1]: [_ev("passed")] * 4}}
            got = [r["model"] for r in R.standing(R.roster(), led)]
            if got[0] != cfg_models[1] or got[-1] != gem_ids[0]:
                fails.append(f"(j) rate-limited Gemini not demoted: {got}")
            # a retry naming a Gemini model while the key is set is honoured
            n += 1
            R.LEDGER = tmp / "gem-pref.json"
            gsent.clear()
            R._gemini_post = gpost([_ok("gem")])
            resp = R.complete([{"role": "user", "content": "x"}], KEY,
                              preferred=gem_ids[2])
            if not gsent or gsent[0][0]["model"] != cfg["gemini_route"]["models"][2]:
                fails.append("(j) preferred Gemini model was not tried first")
        finally:
            os.environ.pop("GEMINI_API_KEY", None)
        n += 1
        R.LEDGER = tmp / "gem-pref-nokey.json"
        try:
            resp = R.complete([{"role": "user", "content": "x"}], KEY,
                              preferred=gem_ids[0])
            if resp.get("model_used") not in cfg_models:
                fails.append("(j) Gemini preferred without key did not reach OpenRouter")
        except R.LLMStop as e:
            fails.append(f"(j) Gemini preferred without the key raised {e.code}")
        n += 1
        for bad in ({"free_tier_only": False}, {"env": "GOOGLE_API_KEY"},
                    {"provider": "vertex"}, {"models": []},
                    {"models": ["google/gemini-2.5-flash"]}):
            c2 = json.loads(json.dumps(cfg))
            c2["gemini_route"].update(bad)
            if not R.config_problems(c2):
                fails.append(f"(j) config negative not caught: {bad}")
        src = (LOOP / "llm_router.py").read_text()
        if not re.search(r"never\s+for\s+anything\s+confidential", src):
            fails.append("(j) the Gemini data rule is missing from the router docstring")

        # the CLI prints the table and exits 0
        n += 1
        env = dict(os.environ, LLM_ROUTE_LEDGER=str(tmp / "cli-empty.json"))
        p = subprocess.run([sys.executable, str(LOOP / "llm_router.py"), "standing"],
                           capture_output=True, text=True, env=env, cwd=ROOT)
        lines = [ln for ln in p.stdout.splitlines() if re.match(r"\s+\d+\. ", ln)]
        if p.returncode != 0 or len(lines) != len(cfg_models) \
                or any(m not in ln for m, ln in zip(cfg_models, lines)):
            fails.append(f"CLI standing: rc={p.returncode} out={p.stdout[-300:]!r}")
    finally:
        R.LEDGER, R._post, R._gemini_post = real_ledger, real_post, real_gpost
    if n == 0:
        fails.append("examined ZERO measured-fallback cases")
    return fails, n


if __name__ == "__main__":
    f, n = check()
    print(f"examined {n} measured-fallback case(s)")
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the $0 fallback order is measured" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
