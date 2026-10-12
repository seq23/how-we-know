"""Free model bench: which $0 OpenRouter models can actually write a script?

    python3 loop/bench_free_models.py            # runs it (<= 60 requests)
    python3 loop/bench_free_models.py --dry-run  # prints the plan, 0 requests

Every model in config/llm_routing.json `models`, in list order, drafts two real
topics that need authoring (one deep-sea, one from the other allocated domain)
with the REAL prompt (author.build_prompt) and is judged by the REAL checks
(author.shape_problems + author.dead_urls + finish_reason). One draft, then -
if it failed - one correction turn built exactly as author.draft() builds it.

Each request is PINNED to the model under test (llm_router.complete would fall
through to other free models, which would credit the wrong model). The body
is complete()'s: same messages, temperature, max price 0, and a reported cost
above 0 stops the bench. One HTTP request per call - no retries.

Then (owner, 2026-10-12, "go 2x"): the best length_only draft gets up to two
EXPANSION turns from the same model and one from a different model.

Writes research/free_model_bench/<date>.{json,md} and
../.wt/free_model_bench_latest.json. Never writes loop/state/. Never logs the key.
Re-run whenever config/llm_routing.json's roster changes.
"""
from __future__ import annotations

import argparse, datetime as dt, json, os, re, statistics, sys, time, urllib.error
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
import author, domains, llm_router, pov_match  # noqa: E402

CAP = 60   # account bought credits once: 1000 ':free' requests/day, 20/min
SLEEP_S = 5
OUT = ROOT / "research" / "free_model_bench"
SHARED = Path.home() / "GitHub" / ".wt" / "free_model_bench_latest.json"
FLOOR = author.NARRATION_FLOOR_WORDS
MODELS_API = "https://openrouter.ai/api/v1/models"
# Benched, in priority order (coordinator research, 2026-10-12): every ':free'
# text model OpenRouter served that day that could plausibly write long-form
# prose. The rest of the ':free' list (code-only, content-safety, tiny) is
# recorded as skipped with that reason. Ids outside config/llm_routing.json are
# pinned here so the measured-fallback order can add the winners to the config.
BENCH = json.loads((OUT / "candidates.json").read_text())["models"]
RETRY_CATS = {"length_only", "structure", "dead_url", "truncated"}  # all but empty/error
EXPAND_SAME, EXPAND_CROSS = 3, 3                        # <= 6 expansion requests


def key_tier(key: str) -> dict:
    """OpenRouter's own account facts (is_free_tier, limits). Read-only, not a chat request."""
    import urllib.request
    req = urllib.request.Request("https://openrouter.ai/api/v1/auth/key",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read()).get("data", {})
        return {k: d.get(k) for k in ("is_free_tier", "limit", "limit_remaining", "usage", "rate_limit")}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


def free_listing() -> dict[str, str]:
    """Every ':free' id OpenRouter lists priced 0/0 -> its name. No key, no chat quota."""
    import urllib.request
    with urllib.request.urlopen(MODELS_API, timeout=30) as r:
        data = json.loads(r.read()).get("data", [])
    return {m["id"]: m.get("name", "") for m in data if m["id"].endswith(":free")
            and all(llm_router._is_zero((m.get("pricing") or {}).get(k, "1"))
                    for k in ("prompt", "completion"))}


def topics() -> list[dict]:
    """One deep-sea topic from next_topics.json, one from the other allocated domain."""
    out = []
    nt = json.loads((LOOP / "next_topics.json").read_text())
    for t in nt.get("selected", []):
        if t.get("needs_authoring") and t.get("pov_line"):
            out.append({"slug": t["slug"], "question": t["question"],
                        "domain": domains.row_domain(t),
                        "pov": {"pov_id": t.get("pov_id"), "line": t["pov_line"]}})
            break
    have = {o["domain"] for o in out}
    alloc = domains.allocation(json.loads((LOOP / "config.json").read_text()))
    for dom in alloc:
        if dom in have:
            continue
        # the PRODUCTION queue first; if it is fully authored, the domain's
        # generated queue is where the next unauthored topic comes from.
        qs = [json.loads(f.read_text()) for f in sorted((ROOT / "research").glob("publish_order_*.json"))]
        rows = [r for d in sorted(qs, key=lambda d: d.get("_status") != "PRODUCTION")
                if d.get("domain") == dom for r in d.get("queue", [])]
        for r in rows:
            if (ROOT / "scripts" / f"{r['slug']}.md").exists():
                continue
            q = r.get("question") or r["query"]
            pov = pov_match.select(r["slug"], q, [], domain=dom)
            out.append({"slug": r["slug"], "question": q, "domain": dom,
                        "pov": {"pov_id": pov["pov_id"], "line": pov["line"]}})
            break
    return out


def words_of(text: str) -> int:
    nar = author.narration_text(text)
    return len(re.sub(r"\{\{[^}]*\}\}", " ", nar).split())


def sections(text: str) -> dict[str, int]:
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("#"):
            cur = line.strip()
            out.setdefault(cur, 0)
        elif cur:
            out[cur] += len(line.split())
    return out


def category(problems: list[str], finish, empty: bool) -> str:
    if empty:
        return "empty_or_error"
    if not problems:
        return "passed"
    if any(p.startswith("output was cut off") for p in problems):
        return "truncated"
    if any(p.startswith("source URL") for p in problems):
        return "dead_url"
    if all(p.startswith("narration is only") for p in problems):
        return "length_only"
    return "structure"


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_KEY_FILE = author.KEY_FILE.parent / "gemini_key.txt"
GEMINI = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3-flash-preview"]
GEMINI_CAP, GEMINI_SLEEP_S = 8, 7                       # Google free tier: < 10/min


def gemini_key() -> str | None:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k and GEMINI_KEY_FILE.exists():
        k = GEMINI_KEY_FILE.read_text().strip()
    return k or None


def gemini_post(body: bytes, key: str, timeout: int) -> dict:
    import urllib.request
    req = urllib.request.Request(GEMINI_API, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Bench:
    """One HTTP request per call. `reasoning` "low" caps hidden thinking: on
    2026-10-12 the production body (no reasoning field) let nemotron-3-super
    spend all 16,000 completion tokens on reasoning and return empty content."""

    def __init__(self, key: str, cap: int = CAP, reasoning: str = "default",
                 gkey: str | None = None):
        self.key, self.used, self.cap, self.reasoning = key, 0, cap, reasoning
        self.gkey, self.gused = gkey, 0

    def call(self, model: str, messages: list[dict], pov: dict) -> dict:
        row = {"model": model, "latency_s": None, "words": 0, "finish_reason": None,
               "problems": [], "passed": False, "outcome": None}
        gem = model.startswith("gemini-")
        if (self.gused >= GEMINI_CAP) if gem else (self.used >= self.cap):
            row.update(outcome="skipped_cap", category="empty_or_error")
            return row
        time.sleep(GEMINI_SLEEP_S if gem else SLEEP_S)
        b = {"model": model, "messages": messages, "max_tokens": 16000, "temperature": 0.4}
        if gem:
            self.gused += 1
            key, post = self.gkey, gemini_post
            if self.reasoning != "default":
                b["reasoning_effort"] = self.reasoning
        else:
            self.used += 1
            key, post = self.key, llm_router._post
            b |= {"usage": {"include": True},
                  "provider": {"max_price": {"prompt": 0, "completion": 0}}}
            if self.reasoning != "default":
                b["reasoning"] = {"effort": self.reasoning}
        body = json.dumps(b).encode()
        t0 = time.monotonic()
        try:
            resp = post(body, key, 300)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:160].replace(key, "<key>")
            row.update(latency_s=round(time.monotonic() - t0, 1), outcome=f"http_{e.code}",
                       error=detail, category="empty_or_error")
            return row
        except Exception as e:  # noqa: BLE001
            row.update(latency_s=round(time.monotonic() - t0, 1), outcome="error",
                       error=f"{type(e).__name__}: {str(e)[:120]}".replace(key, "<key>"),
                       category="empty_or_error")
            return row
        row["latency_s"] = round(time.monotonic() - t0, 1)
        cost = llm_router.reported_cost(resp)
        if cost is not None and not llm_router._is_zero(cost):
            raise SystemExit(f"STOP: OpenRouter reported cost {cost} for {model}")
        served = str(resp.get("model") or "")
        row["model_served"] = served
        if served and not gem and served.split(":")[0] != model.split(":")[0]:
            row.update(outcome="fell_through", category="empty_or_error")
            return row
        choice = (resp.get("choices") or [{}])[0]
        text = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "",
                      ((choice.get("message") or {}).get("content") or "").strip())
        finish = choice.get("finish_reason") or choice.get("native_finish_reason")
        u = resp.get("usage") or {}
        row.update(finish_reason=finish, completion_tokens=u.get("completion_tokens"),
                   reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens"))
        if not text:
            row.update(outcome="empty", category="empty_or_error",
                       error=f"empty content, finish_reason={finish}, "
                             f"reasoning_tokens={row['reasoning_tokens']}")
            return row
        problems = author.shape_problems(text, pov) + author.dead_urls(text)
        if finish and finish not in ("stop", "end_turn"):
            problems.insert(0, f"output was cut off (finish_reason={finish!r}); "
                               f"the draft is incomplete")
        row.update(words=words_of(text), problems=problems, passed=not problems,
                   outcome="answered", category=category(problems, finish, False),
                   head=text[:200], _text=text)
        return row


def correction(messages, text, problems):
    """Exactly author.draft()'s correction turn."""
    remedy = ("\n\n" + author.DIRECTIVE_REMEDY
              if any(p.startswith("directive draws") or p.startswith("uncertain directive")
                     for p in problems) else "")
    return messages + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": "That draft was rejected by the automated checks:\n"
         + "\n".join(f"- {p}" for p in problems) + remedy
         + "\n\nOutput the corrected full script and nothing else."}]


def expand_msgs(messages, text):
    return messages + [{"role": "assistant", "content": text}, {"role": "user", "content":
        f"The script is {words_of(text)} words; the floor is {FLOOR} words at "
        f"{author.WPM} wpm. Do not rewrite it. Expand the thinnest two sections with "
        f"concrete, sourced detail and output the full script with every existing "
        f"line kept."}]


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def rank(rows, roster):
    out = []
    for m in roster:
        rs = [r for r in rows if r["model"] == m and r["phase"] != "expansion"]
        ws = [r["words"] for r in rs if r["words"]]
        # A truncated draft's word count is not a script's length, and words
        # past the floor buy nothing: the ratio counts complete drafts, capped at 1.
        full = [r for r in rs if r["words"] and r["category"] != "truncated"]
        near = min(full, key=lambda r: len(r["problems"]), default=None)
        out.append({"model": m, "passes": sum(r["passed"] for r in rs), "attempts": len(rs),
                    "median_words": med(ws),
                    "best_floor_ratio": round(min(1.0, max([r["words"] for r in full] or [0]) / FLOOR), 3),
                    "fewest_problems": len(near["problems"]) if near else None,
                    "nearest_miss": near["problems"] if near else None,
                    "median_latency_s": med([r["latency_s"] for r in rs if r["words"]]),
                    "categories": {c: sum(r["category"] == c for r in rs)
                                   for c in sorted({r["category"] for r in rs})}})
    out.sort(key=lambda s: (-s["passes"], -s["best_floor_ratio"],
                            s["fewest_problems"] if s["fewest_problems"] is not None else 1e9,
                            s["median_latency_s"] or 1e9))
    return out


def verdict(ranking, exps):
    dead = [s["model"] for s in ranking if not s["median_words"]]
    tail = (f" {len(dead)} of {len(ranking)} benched models never returned a script at "
            f"all (hidden reasoning used the whole 16,000-token budget, upstream 429, or 403)."
            if dead else "")
    return _verdict(ranking, exps) + tail


def _verdict(ranking, exps):
    if any(s["passes"] for s in ranking):
        w = ranking[0]
        return (f"A single model clears the floor: {w['model']} passed {w['passes']} of "
                f"{w['attempts']} attempts with the real prompt and the real checks.")
    same = [e for e in exps if e["passed"] and e["kind"] == "same_model"]
    cross = [e for e in exps if e["passed"] and e["kind"] == "cross_model"]
    if same:
        return (f"No single model clears it in one go, but an expansion pass does: "
                f"{same[0]['model']} lengthened its own draft from {same[0]['words_before']} "
                f"to {same[0]['words_after']} words and passed every check.")
    if cross:
        return (f"Only a two-model combination clears it: {cross[0]['drafted_by']} drafts "
                f"and {cross[0]['model']} expands ({cross[0]['words_before']} -> "
                f"{cross[0]['words_after']} words).")
    best = ranking[0] if ranking else {}
    why = ("no expansion pass rescued a draft" if exps else
           "no draft failed on length alone, so the expansion (\"go 2x\") pass had "
           "nothing to lengthen - length is not what stops these models")
    miss = "; ".join(p[:70] for p in (best.get("nearest_miss") or [])[:3])
    return (f"Nothing at $0 clears it yet: no model passed and {why}. Closest was "
            f"{best.get('model')} ({best.get('best_floor_ratio')} of the {FLOOR}-word "
            f"floor, median {best.get('median_latency_s')} s), whose best draft failed "
            f"only on {best.get('fewest_problems')} problem(s): {miss}.")


def markdown(res) -> str:
    L = [f"# Free model bench - {res['date']}", "",
         f"Requests used: {res['requests_used']} of {res.get('cap', CAP)}"
         f" on OpenRouter (+{res.get('prior_aborted_requests', 0)} by aborted runs), "
         f"{res.get('gemini_requests_used', 0)} on Gemini. Reasoning effort: "
         f"{res.get('reasoning', 'default')}. Floor: {FLOOR} narration words "
         f"at {author.WPM} wpm. Status: {res['bench_status']}"
         + (f" ({res['not_run_reason']})" if res.get("not_run_reason") else "") + ".", "",
         "| model | topic | attempt | words | latency s | passed | category | first problem |",
         "|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        fp = (r["problems"][0] if r["problems"] else r.get("error") or "").replace("|", "/")[:90]
        L.append(f"| {r['model']} | {r['topic']} | {r['phase']} | {r['words']} | "
                 f"{r['latency_s']} | {r['passed']} | {r['category']} | {fp} |")
    L += ["", "## Ranked summary", "",
          "| rank | model | passes/attempts | median words | best/floor | fewest problems | median latency s | categories |",
          "|---|---|---|---|---|---|---|---|"]
    for i, s in enumerate(res["ranking"], 1):
        cats = ", ".join(f"{k} {v}" for k, v in s["categories"].items())
        L.append(f"| {i} | {s['model']} | {s['passes']}/{s['attempts']} | {s['median_words']} | "
                 f"{s['best_floor_ratio']} | {s['fewest_problems']} | {s['median_latency_s']} | {cats} |")
    if res["expansions"]:
        L += ["", "## Expansion passes (\"go 2x\")", "",
              "| kind | drafted by | expanded by | words before | words after | passed | grew most | first problem |",
              "|---|---|---|---|---|---|---|---|"]
        for e in res["expansions"]:
            fp = (e["problems"][0] if e["problems"] else e.get("error") or "").replace("|", "/")[:80]
            L.append(f"| {e['kind']} | {e['drafted_by']} | {e['model']} | {e['words_before']} | "
                     f"{e['words_after']} | {e['passed']} | {e.get('grew')} | {fp} |")
    if res.get("prior_rows"):
        L += ["", "## Earlier today: the production body (no reasoning cap)", ""] + [
            f"- `{r['model']}`: {r['outcome']}" + (f" - {r['note']}" if r.get("note") else "")
            for r in res["prior_rows"]]
    if res.get("skipped"):
        L += ["", "## Skipped", ""] + [f"- `{k}`: {v}" for k, v in res["skipped"].items()]
    win = res["ranking"][0]["model"] if res["ranking"] else None
    L += ["", f"**Winner:** `{win}`", "", "## Verdict", "", res["verdict"], ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rerank", metavar="JSON",
                    help="re-rank and rewrite the outputs from an existing results file, 0 requests")
    ap.add_argument("--cap", type=int, default=CAP,
                    help=f"requests this run may spend (<= {CAP}; lower it if some were spent today)")
    ap.add_argument("--reasoning", default="low", choices=["default", "low", "medium"],
                    help="hidden-reasoning effort; 'default' = the production body exactly")
    ap.add_argument("--prior-file", help="JSON list of rows from an aborted run today, kept as evidence")
    ap.add_argument("--prior-requests", type=int, default=0,
                    help="requests an aborted run already spent today, recorded in the JSON")
    a = ap.parse_args()
    cap = min(a.cap, CAP)
    if a.rerank:
        return write(json.loads(Path(a.rerank).read_text()))
    listing = free_listing()
    roster = [m for m in BENCH if m in listing]
    skipped = {m: "not listed as a $0 ':free' model today" for m in BENCH if m not in listing}
    skipped |= {m: "not benched: code-only, content-safety or too small for a 1,500-word script"
                for m in listing if m not in BENCH}
    tps = topics()
    # Preflight the judges at zero cost: a missing dependency (numpy, via the
    # directive parser) must stop the bench BEFORE a request, not after one.
    author.shape_problems("# preflight\n## Narration\nok\n", tps[0]["pov"])
    print(f"bench {len(roster)}: {roster}\nskipped {len(skipped)}\ntopics: "
          f"{[(t['slug'], t['domain']) for t in tps]}\nplan: {len(tps)} topics x {len(roster)} models, a "
          f"correction for {sorted(RETRY_CATS)}, both topics for every model, "
          f"then up to {EXPAND_SAME + EXPAND_CROSS} expansion turns; cap {cap}")
    if a.dry_run:
        return
    date = dt.date.today().isoformat()
    res = {"date": date, "roster": roster, "config_roster": llm_router.free_models(),
           "floor_words": FLOOR, "wpm": author.WPM, "cap": cap,
           "prior_aborted_requests": a.prior_requests, "reasoning": a.reasoning,
           "prior_rows": json.loads(Path(a.prior_file).read_text()) if a.prior_file else [],
           "topics": [{k: t[k] for k in ("slug", "question", "domain")} | {"pov_id": t["pov"]["pov_id"]}
                      for t in tps], "rows": [], "expansions": [], "skipped": skipped,
           "bench_status": "ran", "not_run_reason": None}
    key = author.api_key()
    if not key:
        res.update(bench_status="not_run", not_run_reason="no OpenRouter key")
        res["skipped"] |= {m: "no OpenRouter key" for m in roster}
    else:
        llm_router.TRANSIENT_RETRIES = 1        # one HTTP request per call, no retries
        gk = gemini_key()
        b = Bench(key, cap, a.reasoning, gk)

        def cell(m, t):
            msgs = author.build_prompt(t["question"], t["pov"], t["domain"])
            r = b.call(m, msgs, t["pov"]) | {"topic": t["slug"], "phase": "draft", "_msgs": msgs}
            res["rows"].append(r)
            print(f"{m} {t['slug']} draft: {r['outcome']} {r['words']}w {r['category']}", flush=True)
            if r["category"] in RETRY_CATS:
                r2 = b.call(m, correction(msgs, r["_text"], r["problems"]), t["pov"])
                r2 |= {"topic": t["slug"], "phase": "correction", "_msgs": msgs}
                res["rows"].append(r2)
                print(f"{m} {t['slug']} correction: {r2['outcome']} {r2['words']}w {r2['category']}", flush=True)
            return [x for x in res["rows"] if x["model"] == m and x["topic"] == t["slug"]]

        res["account"] = key_tier(key) | {"note": "credits were bought once, so ':free' "
                                          "models allow 1000 requests/day and 20/min"}
        for t in tps:
            for m in roster:
                cell(m, t)
        gem_full = None
        if not gk:
            res["skipped"]["gemini"] = "skipped, no key"
        else:
            # first Gemini model that answers gets the full protocol; the rest one attempt
            for g in GEMINI:
                if gem_full is None:
                    rs = cell(g, tps[0])
                    if any(x["outcome"] == "answered" for x in rs):
                        gem_full = g
                        res["roster"].append(g)
                        for t in tps[1:]:
                            cell(g, t)
                    else:
                        res["roster"].append(g)
                else:
                    msgs = author.build_prompt(tps[0]["question"], tps[0]["pov"], tps[0]["domain"])
                    r = b.call(g, msgs, tps[0]["pov"]) | {"topic": tps[0]["slug"], "phase": "draft"}
                    res["rows"].append(r)
                    res["roster"].append(g)
            for r in res["rows"]:
                if r["model"].startswith("gemini-") and r["outcome"] in ("http_429", "http_403"):
                    r["note"] = "not on free tier / rate-limited"
        lo = [r for r in res["rows"] if r["category"] == "length_only"]
        if lo:
            best = max(lo, key=lambda r: r["words"])
            t = next(t for t in tps if t["slug"] == best["topic"])
            others = ([gem_full] if gem_full else []) + [
                m for m in (s["model"] for s in rank(res["rows"], res["roster"]))
                if m not in (best["model"], gem_full)]
            jobs = [(best["model"], "same_model")] * EXPAND_SAME \
                + [(o, "cross_model") for o in others[:EXPAND_CROSS]]
            cur = best["_text"]
            for m, kind in jobs:
                if kind == "same_model" and any(e["passed"] or e["outcome"] != "answered"
                                                for e in res["expansions"]):
                    continue                     # passed already, or the model stopped answering
                src = cur if kind == "same_model" else best["_text"]
                e = b.call(m, expand_msgs(best["_msgs"], src), t["pov"])
                before, after = sections(src), sections(e.get("_text", ""))
                grew = max(after, key=lambda s: after[s] - before.get(s, 0)) if after else None
                res["expansions"].append(e | {"kind": kind, "drafted_by": best["model"],
                                              "topic": best["topic"], "words_before": words_of(src),
                                              "words_after": e["words"], "grew": grew})
                print(f"expand {kind} {m}: {words_of(src)}->{e['words']} {e['category']}", flush=True)
                if kind == "same_model" and e.get("_text"):
                    cur = e["_text"]
        res["requests_used"] = b.used
        res["gemini_requests_used"] = b.gused
        for m in roster:
            if not any(r["model"] == m for r in res["rows"]):
                res["skipped"][m] = "request cap reached before this model"

    res.setdefault("requests_used", 0)
    for r in res["rows"] + res["expansions"]:
        r.pop("_text", None); r.pop("_msgs", None)
    write(res)


def write(res: dict) -> None:
    date = res["date"]
    res["ranking"] = rank(res["rows"], res["roster"]) if res["rows"] else []
    res["verdict"] = (verdict(res["ranking"], res["expansions"]) if res["rows"]
                      else f"The bench did not run: {res['not_run_reason']}.")
    OUT.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(res, indent=2)
    if "sk-" in blob:
        raise SystemExit("STOP: a key-like string reached the results; not writing")
    (OUT / f"{date}.json").write_text(blob + "\n")
    (OUT / f"{date}.md").write_text(markdown(res))
    SHARED.parent.mkdir(parents=True, exist_ok=True)
    SHARED.write_text(blob + "\n")
    print(f"wrote {OUT / date}.json/.md; requests {res['requests_used']}\n{res['verdict']}")


if __name__ == "__main__":
    main()
