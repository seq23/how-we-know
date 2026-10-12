"""Her Claude subscription answers first; the $0 route is the fallback.

Owner, 2026-10-12: "use my claude subscription usage in advance of the $0
openrouter". loop/llm_router.py asks the headless Claude Code CLI first when
$CLAUDE_CODE_OAUTH_TOKEN is set, and falls through to the $0 OpenRouter list
on any failure. These checks pin that, with subprocess and HTTP patched (no
network, no CLI):

  a. env set + CLI answers -> the subscription dict, ZERO OpenRouter calls.
  b. env set + CLI fails (non-zero exit / is_error / empty / bad JSON /
     no binary / timeout) -> a free model answers, never a raise.
  c. env ABSENT -> no subprocess at all.
  d. the token never appears in argv or in anything printed.
  e. config/llm_routing.json subscription_route shape (and its negatives).
  f. the lanes: every workflow whose stage can reach llm_router.complete()
     (derived from the CALL graph of loop/*.py, not a hand-kept list)
     installs the pinned CLI and passes the secret to that stage; no other
     workflow passes it. A new lane that calls the router without the secret
     fails here.
  g. a retry naming "claude-subscription/opus" as preferred is not refused.

Hard-fails if it examines nothing.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
WORKFLOWS = ROOT / ".github" / "workflows"
sys.path.insert(0, str(LOOP))

import llm_router as R  # noqa: E402

TOKEN = "sk-ant-oat01-TEST-TOKEN-must-never-print-0123456789"
PIN = "@anthropic-ai/claude-code@2.1.296"
SECRET_LINE = "CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
MSGS = [{"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Say ok."}]


class _Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _cli_ok(text="ok from opus"):
    return _Proc(0, json.dumps({
        "type": "result", "subtype": "success", "result": text,
        "is_error": False, "num_turns": 1, "total_cost_usd": 0.56,
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 600,
                  "cache_read_input_tokens": 0, "output_tokens": 4}}))


def _free_ok(body, key, timeout):
    model = json.loads(body)["model"]
    return {"choices": [{"message": {"content": f"free answer from {model}"},
                         "finish_reason": "stop"}],
            "usage": {"cost": 0}}


def _post_forbidden(body, key, timeout):
    raise AssertionError("OpenRouter was called although the subscription "
                         "tier answered")


@contextlib.contextmanager
def patched(run, which="/usr/local/bin/claude", post=_free_ok, env=True):
    calls = []

    def fake_run(argv, **kw):
        calls.append((list(argv), kw))
        if isinstance(run, BaseException):
            raise run
        return run

    saved = (R.subprocess.run, R.shutil.which, R._post,
             os.environ.get(R.SUBSCRIPTION_ENV))
    R.subprocess.run = fake_run
    R.shutil.which = lambda name: which
    R._post = post
    if env:
        os.environ[R.SUBSCRIPTION_ENV] = TOKEN
    else:
        os.environ.pop(R.SUBSCRIPTION_ENV, None)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            yield calls, buf
    finally:
        R.subprocess.run, R.shutil.which, R._post = saved[:3]
        if saved[3] is None:
            os.environ.pop(R.SUBSCRIPTION_ENV, None)
        else:
            os.environ[R.SUBSCRIPTION_ENV] = saved[3]


# ---- (f) the lanes, derived from the call graph ----------------------------
def router_reaching_modules() -> set[str]:
    """Modules with a function that (transitively) calls
    llm_router.complete(). Call graph, not import graph: many lanes import
    author.py for its helpers without ever calling a model."""
    trees = {p.stem: ast.parse(p.read_text()) for p in LOOP.glob("*.py")}
    reach = {("llm_router", "complete")}
    changed = True
    while changed:
        changed = False
        for mod, tree in trees.items():
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if (mod, fn.name) in reach:
                    continue
                for n in ast.walk(fn):
                    if not isinstance(n, ast.Call):
                        continue
                    f = n.func
                    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                        target = (f.value.id, f.attr)
                    elif isinstance(f, ast.Name):
                        target = (mod, f.id)
                    else:
                        continue
                    if target in reach:
                        reach.add((mod, fn.name))
                        changed = True
                        break
    return {m for m, _ in reach}


def steps(text: str) -> list[str]:
    """Each `- ` step block under a job's steps:, as text."""
    out, cur, indent = [], None, None
    for line in text.splitlines():
        m = re.match(r"^(\s*)- (?:name|uses|id|if|run|env|with|shell)\b", line)
        if m and (indent is None or len(m.group(1)) == indent):
            indent = len(m.group(1))
            if cur is not None:
                out.append("\n".join(cur))
            cur = [line]
        elif cur is not None:
            if line.strip() and not line.startswith(" " * (indent + 1)) \
                    and not line.lstrip().startswith("#"):
                out.append("\n".join(cur))
                cur, indent = None, None
                continue
            cur.append(line)
    if cur is not None:
        out.append("\n".join(cur))
    return out


def lane_problems(mods: set[str]) -> tuple[list[str], list[str]]:
    """(problems, the derived lane list)."""
    out, lanes = [], []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        raw = wf.read_text()
        text = "\n".join(l for l in raw.splitlines()
                         if not l.lstrip().startswith("#"))
        runs = {m for m in mods if re.search(rf"loop/{m}\.py\b", text)}
        has_secret = "secrets.CLAUDE_CODE_OAUTH_TOKEN" in text
        if not runs:
            if has_secret:
                out.append(f"{wf.name} passes CLAUDE_CODE_OAUTH_TOKEN but runs "
                           f"no stage that reaches llm_router")
            continue
        lanes.append(wf.name)
        if PIN not in text:
            out.append(f"{wf.name} runs {sorted(runs)} (reaches llm_router) "
                       f"but does not install {PIN}")
        if re.search(r"@anthropic-ai/claude-code(?!@\d+\.\d+\.\d+)", text):
            out.append(f"{wf.name} installs an unpinned @anthropic-ai/claude-code")
        # The secret must sit in the env of every step whose run: invokes a
        # router-reaching stage. Text-split into steps (no pyyaml needed here:
        # test_workflows.py already proves every file parses).
        for step in steps(text):
            code = "\n".join(l for l in step.splitlines()
                             if not l.lstrip().startswith("#"))
            hit = {m for m in mods if re.search(rf"loop/{m}\.py\b", code)}
            if hit and SECRET_LINE not in step:
                name = re.search(r"name:\s*(.+)", step)
                out.append(f"{wf.name} step {name.group(1).strip() if name else '?'!r} "
                           f"runs {sorted(hit)} without {SECRET_LINE}")
    return out, lanes


def check() -> list[str]:
    fails: list[str] = []
    examined = 0

    # (a) the subscription answers; OpenRouter is never touched.
    with patched(_cli_ok(), post=_post_forbidden) as (calls, buf):
        try:
            resp = R.complete(MSGS, "or-key")
        except AssertionError as e:
            resp = {}
            fails.append(f"(a) {e}")
    examined += 1
    if resp.get("model_used") != R.SUBSCRIPTION_MODEL_USED \
            or resp.get("route") != "claude-subscription":
        fails.append(f"(a) model_used {resp.get('model_used')!r}, expected "
                     f"{R.SUBSCRIPTION_MODEL_USED}")
    if ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") \
            != "ok from opus":
        fails.append("(a) the CLI's result is not choices[0].message.content")
    if (resp.get("usage") or {}).get("cost") != 0:
        fails.append("(a) the subscription answer must carry usage.cost == 0")
    if len(calls) != 1:
        fails.append(f"(a) expected one CLI call, saw {len(calls)}")
    else:
        argv, kw = calls[0]
        if "--bare" in argv:
            fails.append("(a) --bare never reads the OAuth token; the tier "
                         "would be inert")
        for flag in ("-p", "--tools", "--no-session-persistence",
                     "--system-prompt", "--max-turns"):
            if flag not in argv:
                fails.append(f"(a) CLI argv lacks {flag}")
        if argv[argv.index("--system-prompt") + 1] != "Be brief.":
            fails.append("(a) the system messages are not the --system-prompt")
        if kw.get("input") != "Say ok.":
            fails.append(f"(a) stdin is {kw.get('input')!r}, expected the user turn")

    # A multi-turn exchange is rendered in order with roles.
    examined += 1
    _, user = R._render_turns(MSGS + [
        {"role": "assistant", "content": "DRAFT-1"},
        {"role": "user", "content": "FIX-IT"}])
    if not (user.index("user:") < user.index("DRAFT-1") < user.index("FIX-IT")
            and "assistant:" in user):
        fails.append("(a) multi-turn messages are not rendered in order with roles")

    # (b) every CLI failure falls through to a free model.
    free = R.free_models()
    cases = {
        "non-zero exit": dict(run=_Proc(1, "", f"auth failed for {TOKEN}")),
        "is_error": dict(run=_Proc(0, json.dumps(
            {"is_error": True, "result": "Not logged in"}))),
        "empty result": dict(run=_Proc(0, json.dumps(
            {"is_error": False, "result": "  "}))),
        "bad JSON": dict(run=_Proc(0, "not json")),
        "no binary": dict(run=_cli_ok(), which=None),
        "timeout": dict(run=subprocess.TimeoutExpired(["claude"], 600)),
    }
    for name, kw in cases.items():
        examined += 1
        with patched(**kw) as (calls, buf):
            try:
                resp = R.complete(MSGS, "or-key")
            except Exception as e:                  # noqa: BLE001
                fails.append(f"(b) {name}: raised {type(e).__name__}: {e}")
                continue
        if resp.get("model_used") not in free:
            fails.append(f"(b) {name}: model_used {resp.get('model_used')!r} is "
                         f"not a free model")
        if "[claude-route]" not in buf.getvalue() \
                or "falling back to the $0 route" not in buf.getvalue():
            fails.append(f"(b) {name}: no [claude-route] fallback line")
        if name == "no binary" and calls:
            fails.append("(b) no binary: subprocess still called")
        # (d) the token never printed, even when the CLI echoes it.
        if TOKEN in buf.getvalue():
            fails.append(f"(d) {name}: the token appeared in printed output")
        for argv, _ in calls:
            if any(TOKEN in a for a in argv):
                fails.append(f"(d) {name}: the token appeared in argv")

    # (c) env absent -> no subprocess at all, free route as before.
    examined += 1
    with patched(_cli_ok(), env=False) as (calls, buf):
        resp = R.complete(MSGS, "or-key")
    if calls:
        fails.append("(c) CLAUDE_CODE_OAUTH_TOKEN absent but the CLI was run")
    if resp.get("model_used") not in free:
        fails.append("(c) env absent: the free route did not answer")
    if "[claude-route]" in buf.getvalue():
        fails.append("(c) env absent: a [claude-route] line was printed")

    # Short caller timeouts are honoured (a 6-minute lane is not held 10).
    examined += 1
    if R.subscription_timeout(300) != 600 or R.subscription_timeout(90) != 90:
        fails.append("(a) subscription_timeout: 300 -> 600, 90 -> 90 expected")

    # (d) argv of the success path, and its printed output.
    examined += 1
    with patched(_cli_ok()) as (calls, buf):
        R.complete(MSGS, "or-key")
    if any(TOKEN in a for argv, _ in calls for a in argv) or TOKEN in buf.getvalue():
        fails.append("(d) the token appeared in argv or output on success")

    # (e) config shape, with negatives.
    cfg = R.load_config()
    sr = cfg.get("subscription_route") or {}
    examined += 1
    if sr.get("provider") != "claude-code" or \
            sr.get("env") != "CLAUDE_CODE_OAUTH_TOKEN" or \
            sr.get("model") != R.SUBSCRIPTION_MODEL:
        fails.append(f"(e) subscription_route is {sr!r}")
    if cfg.get("max_cost_usd") != 0 or cfg.get("paid_fallback") is not False:
        fails.append("(e) the $0 posture changed")
    for bad in ({"provider": "anthropic-api", "env": "CLAUDE_CODE_OAUTH_TOKEN",
                 "model": "opus"},
                {"provider": "claude-code", "env": "ANTHROPIC_API_KEY",
                 "model": "opus"},
                {"provider": "claude-code", "env": "CLAUDE_CODE_OAUTH_TOKEN",
                 "model": ""}):
        examined += 1
        if not R.config_problems(dict(cfg, subscription_route=bad)):
            fails.append(f"(e) config_problems accepts {bad!r}")

    # (f) the lanes.
    mods = router_reaching_modules()
    examined += 1
    for must in ("author", "draft", "localize", "advise"):
        if must not in mods:
            fails.append(f"(f) the call graph lost {must}.py - the derivation "
                         f"is broken")
    probs, lanes = lane_problems(mods)
    fails += [f"(f) {p}" for p in probs]
    if "loop-mon-draft.yml" not in lanes:
        fails.append("(f) loop-mon-draft.yml is not among the derived lanes")
    # Negative: a lane without the secret is seen.
    examined += 1
    import tempfile
    global WORKFLOWS
    real = WORKFLOWS
    with tempfile.TemporaryDirectory() as d:
        Path(d, "x.yml").write_text(
            "jobs:\n  j:\n    steps:\n      - name: s\n"
            "        run: bin/loop-stage.sh x loop/localize.py\n")
        WORKFLOWS = Path(d)
        try:
            neg, _ = lane_problems(mods)
        finally:
            WORKFLOWS = real
    if len(neg) < 2:
        fails.append("(f) a router lane without the pin and secret was not seen")

    # (g) a retry naming the subscription tier is not refused.
    examined += 1
    with patched(_Proc(1, "", "down")) as (calls, buf):
        try:
            resp = R.complete(MSGS, "or-key", preferred=R.SUBSCRIPTION_MODEL_USED)
            if resp.get("model_used") not in free:
                fails.append("(g) the retry did not reach a free model")
        except R.LLMStop as e:
            fails.append(f"(g) preferred={R.SUBSCRIPTION_MODEL_USED!r} raised {e.code}")

    if examined == 0:
        fails.append("examined ZERO subscription-route cases")
    print(f"inspected {examined} subscription-route case(s); lanes: "
          f"{', '.join(lanes)}")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - subscription first, $0 behind it" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
