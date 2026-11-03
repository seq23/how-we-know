"""No lane calls Claude (owner via the coordinator, 2026-11-04).

The router answers from Gemini's free tier, then the $0 OpenRouter roster,
and when none of them answers it is a NAMED STOP - never the Claude CLI, never
a paid API, even with a Claude token in the environment. No workflow installs
the Claude CLI or hands a lane the Claude token. No network, no real CLI.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
import llm_router as R  # noqa: E402

fails, examined = [], 0
cfg = R.load_config()
examined += 1
if cfg.get("subscription_route"):
    fails.append("config/llm_routing.json still carries a subscription_route")
os.environ[R.SUBSCRIPTION_ENV] = "sk-ant-oat01-TEST-must-never-be-used"
examined += 1
if R.subscription_available():
    fails.append("the subscription tier is available with a token set")

ran = []
real_run, real_post, real_gem = subprocess.run, R._post, R._gemini_try
subprocess.run = lambda *a, **k: ran.append(a[0] if a else k.get("args")) or (_ for _ in ()).throw(
    AssertionError("a subprocess was started"))
R._post = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("free model down"))
R._gemini_try = lambda *a, **k: (None, "free tier down")
os.environ["GEMINI_API_KEY"] = "test"
examined += 1
try:
    R.complete([{"role": "user", "content": "Say ok."}], "or-key", timeout=30)
    fails.append("complete() answered with every free route down")
except R.LLMStop as e:
    if "NO_FREE_MODEL" not in str(e):
        fails.append(f"the stop is not the named no-free-model stop: {e}")
except AssertionError as e:
    fails.append(f"complete() tried the Claude CLI: {e}")
finally:
    subprocess.run, R._post, R._gemini_try = real_run, real_post, real_gem
if any("claude" in str(c) for c in ran):
    fails.append(f"claude was invoked: {ran}")

for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
    examined += 1
    text = wf.read_text()
    for bad in ("@anthropic-ai/claude-code", "CLAUDE_CODE_OAUTH_TOKEN", "claude -p"):
        if bad in text:
            fails.append(f"{wf.name} still carries {bad!r}")

for f in fails:
    print("FAIL:", f)
print(f"no-claude route: {examined} check(s), {len(fails)} failure(s)")
sys.exit(1 if fails or examined < 4 else 0)
