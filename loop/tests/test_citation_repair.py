#!/usr/bin/env python3
"""Citation repair turn + the one rejection classifier (bench 2026-10-12).

The nearest miss in research/free_model_bench/2026-10-12.md (gemini-2.5-flash)
cleared the length floor every time and was stopped only by dead source
links. author.draft() now answers a rejection whose ONLY problems are
dead_urls() findings with a targeted repair turn instead of the generic
"corrected full script" turn. This pins:

  a. attempt 1 = a full script with two dead URLs, attempt 2 = the same script
     with live URLs -> accepted on attempt 2, and the second request's last
     user turn is the repair prompt (names both URLs, "change nothing else"),
     not the generic one; the repair is re-checked by shape_problems() and
     dead_urls();
  b. a dead URL alongside a shape problem, or a truncated draft, gets the
     generic turn - never the repair;
  c. a repair that still has a dead URL is retried inside MAX_ATTEMPTS and
     then stops as DRAFT_FAILED_VALIDATION;
  d. author.rejection_category is the bench's classifier
     (bench_free_models.category delegates to it) and classifies every
     bench row the way the committed 2026-10-12 bench recorded it.

No network. Hard-fails if it examines nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
os.environ.pop("GEMINI_API_KEY", None)

import llm_router as R  # noqa: E402
import author  # noqa: E402

KEY = "sk-or-v1-" + "0" * 64
DEAD = ["https://dead.example.org/a", "https://dead.example.org/b"]
LIVE = ["https://live.example.org/a", "https://live.example.org/b"]
SCRIPT = ("# T\n\nnarration\n\n## Sources\n- " + "\n- ".join(DEAD)
          + "\n- https://live.example.org/c\n")
FIXED = SCRIPT.replace(DEAD[0], LIVE[0]).replace(DEAD[1], LIVE[1])


def _ok(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0}}


def _fake_dead(text):
    return [f"source URL returns HTTP 404 and does not exist: {u} - replace "
            f"it with a page you are certain of, or drop the claim it "
            f"supports." for u in DEAD if u in text]


def check() -> list[str]:
    fails: list[str] = []
    examined = 0
    real = (R._post, R.LEDGER, author.dead_urls, author.shape_problems,
            author.record_spend, author.DRAFTS, author.opening.mark)
    sent: list[dict] = []
    pov = {"pov_id": "t", "line": "I once saw this myself."}

    def script(*answers):
        it = iter(answers)
        sent.clear()

        def fake(body, key, timeout):
            sent.append(json.loads(body))
            return next(it)
        R._post = fake

    def last_user(i):
        return [m for m in sent[i]["messages"] if m["role"] == "user"][-1]["content"]

    try:
        (LOOP / "drafts").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOOP / "drafts") as td:
            R.LEDGER = Path(td) / "ledger.json"
            author.DRAFTS = Path(td)
            author.record_spend = lambda *a, **k: None
            author.opening.mark = lambda text, v: text
            author.dead_urls = _fake_dead
            shape_calls: list[str] = []

            def shape(text, pov, extra=None):
                shape_calls.append(text)
                return list(extra or [])
            author.shape_problems = shape

            # (a) dead URLs only -> repair turn -> accepted on attempt 2
            examined += 1
            script(_ok(SCRIPT), _ok(FIXED))
            out = author.draft("Q?", "repair-a", pov, key=KEY)
            if out.get("attempt") != 2:
                fails.append(f"(a) accepted on attempt {out.get('attempt')}, expected 2")
            if len(sent) != 2:
                fails.append(f"(a) {len(sent)} requests, expected 2")
            else:
                u = last_user(1)
                if not u.startswith("These 2 source URLs are dead: ") \
                        or not all(d in u for d in DEAD) \
                        or "change nothing else in the script" not in u \
                        or "same publisher or an equivalent primary source" not in u:
                    fails.append(f"(a) attempt 2's last user turn is not the "
                                 f"repair prompt: {u[:160]!r}")
                if "That draft was rejected by the automated checks" in u:
                    fails.append("(a) the generic correction turn was sent")
                if sent[1]["messages"][-2] != {"role": "assistant", "content": SCRIPT.strip()}:
                    fails.append("(a) the repair turn does not carry the draft it repairs")
            if shape_calls[-1:] != [FIXED.strip()]:
                fails.append("(a) the repaired script was not re-checked by shape_problems()")
            if Path(ROOT / out["path"]).read_text() != FIXED.strip():
                fails.append("(a) the accepted draft is not the repaired script")

            # (b) dead URL + a shape problem -> generic turn
            examined += 1
            author.shape_problems = lambda t, p: (shape_calls.append(t) or
                                                  ([] if t == FIXED.strip() else
                                                   ["missing section '## Hook'"]))
            script(_ok(SCRIPT), _ok(FIXED))
            author.draft("Q?", "repair-b", pov, key=KEY)
            if len(sent) < 2 or "That draft was rejected by the automated checks" \
                    not in last_user(1) or "source URLs are dead:" in last_user(1):
                fails.append("(b) a shape problem beside a dead URL did not get "
                             "the generic correction turn")
            author.shape_problems = shape

            # (b2) truncated draft with dead URLs -> generic turn
            examined += 1
            script(_ok(SCRIPT, finish="length"), _ok(FIXED))
            author.draft("Q?", "repair-b2", pov, key=KEY)
            if len(sent) < 2 or "source URLs are dead:" in last_user(1):
                fails.append("(b) a truncated draft got the citation repair turn")

            # (c) the repair still dead -> retried, then DRAFT_FAILED_VALIDATION
            examined += 1
            script(*[_ok(SCRIPT)] * author.MAX_ATTEMPTS)
            try:
                author.draft("Q?", "repair-c", pov, key=KEY)
                fails.append("(c) a draft whose links stayed dead was accepted")
            except author.AuthorStop as e:
                if e.code != "DRAFT_FAILED_VALIDATION":
                    fails.append(f"(c) stopped as {e.code}")
            if len(sent) != author.MAX_ATTEMPTS:
                fails.append(f"(c) {len(sent)} requests, expected {author.MAX_ATTEMPTS}")
    finally:
        (R._post, R.LEDGER, author.dead_urls, author.shape_problems,
         author.record_spend, author.DRAFTS, author.opening.mark) = real

    # (d) one classifier for the lane and the bench
    import bench_free_models as B  # noqa: E402
    examined += 1
    probe = (["source URL is unreachable (x): https://a.org/"], None, False)
    if B.category(*probe) != author.rejection_category(*probe) != "dead_url":
        fails.append("(d) the bench's category() is not author.rejection_category")
    res = json.loads((ROOT / "research/free_model_bench/2026-10-12.json").read_text())
    n = 0
    for r in res["rows"]:
        if r.get("outcome") != "answered":
            continue
        n += 1
        got = author.rejection_category(r["problems"], r.get("finish_reason"), False)
        if got != r["category"]:
            fails.append(f"(d) {r['model']}/{r['topic']}/{r['phase']}: "
                         f"{got} != bench {r['category']}")
    if n == 0:
        fails.append("(d) classified ZERO bench rows")
    for want, probs in (("length_only", ["narration is only 900 words"]),
                        ("structure", ["missing section '## Hook'"]),
                        ("truncated", ["output was cut off (x)", "source URL x"]),
                        ("dead_url", ["source URL x", "narration is only 9"])):
        examined += 1
        if author.rejection_category(probs) != want:
            fails.append(f"(d) {probs} -> {author.rejection_category(probs)}, expected {want}")
    if author.repairable_urls(["source URL x: https://a.org/", "narration is only 9"]):
        fails.append("(d) a dead URL beside a length problem was called repairable")

    if examined == 0:
        fails.append("examined ZERO repair cases")
    print(f"inspected {examined} citation-repair case(s), {n} bench row(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - dead links get a repair turn, one classifier"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
