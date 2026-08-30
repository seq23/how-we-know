"""The authoring lane: the key stays secret, and generated work is not trusted.

An LLM is the single most likely source of a fabricated number or citation in
this pipeline, so the tests here are about what happens when it is wrong, not
about whether it can write.

  1. The OpenRouter key is unreachable by git, never printed, and never in a
     tracked file.
  2. Every expected failure is a NAMED stop with a fix — never a crash.
  3. The validators are NOT relaxed for generated scripts; V8 fetches every
     citation, and a fabricated URL fails.
  4. Truncated output is caught. The first real draft ended mid-URL with every
     section present and looked completely fine.
  5. Spend is logged per draft, from OpenRouter's own reported cost.

Hard-fails if it examines zero cases. Makes no network calls to OpenRouter.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import author  # noqa: E402

KEY_SHAPES = [r"sk-or-v1-[0-9a-f]{16,}", r"sk-or-[A-Za-z0-9_-]{24,}"]


def check() -> list[str]:
    fails, examined = [], 0

    # ------------------------------------------------ 1. the key is secret
    examined += 1
    r = subprocess.run(["git", "check-ignore", "-q",
                        ".secrets/openrouter_key.txt"], cwd=ROOT)
    if r.returncode != 0:
        fails.append(".secrets/openrouter_key.txt is NOT gitignored")

    examined += 1
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout.splitlines()
    for f in tracked:
        p = ROOT / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            body = p.read_text(errors="ignore")
        except OSError:
            continue
        for shape in KEY_SHAPES:
            if re.search(shape, body):
                fails.append(f"tracked file {f} contains an OpenRouter key")

    # redact_key must never return the key
    examined += 1
    fake = "sk-or-v1-" + "a" * 64
    if fake in author.redact_key(fake) or "aaaa" in author.redact_key(fake):
        fails.append("redact_key() leaked the key")

    # No source file may print the key
    for f in ("author.py",):
        examined += 1
        src = (LOOP / f).read_text()
        for m in re.finditer(r"print\([^)]*\bkey\b[^)]*\)", src):
            if "redact" not in m.group(0):
                fails.append(f"loop/{f} may print the key: {m.group(0)[:60]}")

    # ------------------------------------------------ 2. named stops
    examined += 1
    src = (LOOP / "author.py").read_text()
    for code in ("OPENROUTER_KEY_MISSING", "OPENROUTER_UNAUTHORISED",
                 "OPENROUTER_OUT_OF_CREDIT", "OPENROUTER_RATE_LIMITED",
                 "OPENROUTER_UNREACHABLE", "DRAFT_FAILED_VALIDATION",
                 "TOPIC_EXCLUDED"):
        if code not in src:
            fails.append(f"loop/author.py has no named stop for {code}")

    # Missing key: a named stop, exit 0, never a traceback.
    examined += 1
    p = subprocess.run([sys.executable, str(LOOP / "author.py"), "a test topic"],
                       cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": "/tmp",
                            "OPENROUTER_API_KEY": "",
                            "LOOP_NO_KEYFILE": "1"})
    out = p.stdout + p.stderr
    if "Traceback" in out:
        fails.append(f"author.py crashed with no key instead of stopping:\n"
                     f"{out[-400:]}")

    # ------------------------------------------------ 3. validators not relaxed
    examined += 1
    val = (LOOP / "validate.py").read_text()
    if "v8_source_urls" not in val:
        fails.append("no V8: generated citations are never fetched")
    if "generated" not in val:
        fails.append("validate.py does not distinguish generated scripts")
    # V8 must FAIL a 404, not warn.
    if not re.search(r"404.*\n.*r\.fail|code in \(404, 410\)", val):
        fails.append("V8 does not hard-fail a 404 source URL")
    # No relaxation switch anywhere.
    for f in ("draft.py", "validate.py"):
        examined += 1
        s2 = (LOOP / f).read_text()
        if re.search(r"if .*generated.*:\s*\n\s*(?:return|continue|pass)\s*$",
                     s2, re.M):
            fails.append(f"loop/{f} appears to skip checks for generated "
                         f"scripts — they must run at full strength")

    # V8 probe classifies correctly
    examined += 1
    import validate
    code, _ = validate.probe("https://oceanexplorer.noaa.gov/definitely-not-a-real-page-xyz")
    if code not in (404, 410, 403, 0):
        fails.append(f"probe() returned {code} for a non-existent NOAA page")

    # ------------------------------------------------ 4. truncation caught
    examined += 1
    pov = {"line": "A line.", "pov_id": "pov-001"}
    complete = ("# Q?\n## Direct-answer lock\nx\n## Narration\n"
                "### Producer POV\n[HUMAN] A line.\n" + ("w " * 950) +
                "\n## Human fingerprint gate\n## Chapters\n## Sources\n\n"
                "- NOAA: Facts — https://oceanexplorer.noaa.gov/facts/\n"
                "- WHOI: Ocean — https://www.whoi.edu/know-your-ocean/\n"
                "- GEBCO: Charts — https://www.gebco.net/\n")
    truncated = complete[:complete.rindex("https://www.gebco.net/")]
    if any("truncat" in x for x in author.shape_problems(complete, pov)):
        fails.append("a complete draft was flagged as truncated")
    if not any("truncat" in x for x in author.shape_problems(truncated, pov)):
        fails.append("a TRUNCATED draft was not caught — this is the failure "
                     "mode that looks most like success")

    # The exclusion gate applies to generated prose too.
    examined += 1
    bad = complete.replace("w " * 950, "you should take a supplement. " * 200)
    if not any("exclusion" in x for x in author.shape_problems(bad, pov)):
        fails.append("generated narration giving medical advice was not caught")

    # ------------------------------------------------ 5. spend logged
    examined += 1
    spend = LOOP / "state" / "spend.json"
    if spend.exists():
        d = json.loads(spend.read_text())
        for k in ("total_usd", "drafts"):
            if k not in d:
                fails.append(f"spend log has no {k!r}")
        for row in d.get("drafts", []):
            for k in ("slug", "model", "cost_usd", "accepted"):
                if k not in row:
                    fails.append(f"a spend row has no {k!r}")
                    break
    if "record_spend" not in src:
        fails.append("author.py does not log spend")

    if examined == 0:
        fails.append("examined ZERO authoring cases")
    print(f"inspected {examined} authoring case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - key secret, stops named, generated work validated at "
          "full strength" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
