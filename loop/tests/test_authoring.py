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

    key_guard_broken = False
    # api_key() itself: both env guards win over a key file that exists.
    # This runs FIRST and gates the subprocess below: if the guard is
    # broken, launching author.py against a real key file would pay for a
    # draft to prove it, and the proof must not cost money.
    import os
    import tempfile
    real_keyfile = author.KEY_FILE
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "openrouter_key.txt"
        fake.write_text("sk-or-v1-" + "f" * 64)
        author.KEY_FILE = fake
        try:
            for guard in ("LOOP_NO_KEYFILE", "LOOP_DRY_RUN"):
                examined += 1
                os.environ.pop("OPENROUTER_API_KEY", None)
                os.environ[guard] = "1"
                try:
                    got = author.api_key()
                finally:
                    del os.environ[guard]
                if got is not None:
                    fails.append(f"api_key() read the key file with {guard}=1")
                    key_guard_broken = True
            examined += 1
            saved = {k: os.environ.pop(k) for k in
                     ("LOOP_NO_KEYFILE", "LOOP_DRY_RUN", "OPENROUTER_API_KEY")
                     if k in os.environ}
            try:
                if author.api_key() != fake.read_text().strip():
                    fails.append("api_key() ignored the key file with no "
                                 "guard set — the Mac path is broken")
            finally:
                os.environ.update(saved)
        finally:
            author.KEY_FILE = real_keyfile

    # Missing key: a named stop, exit 0, never a traceback — AND NO SPEND.
    # LOOP_NO_KEYFILE was set here from the first version of this test and
    # nothing in author.py read it, so on a Mac holding
    # .secrets/openrouter_key.txt this "missing key" case quietly made a real
    # two-attempt draft (~$0.12) on every local suite run, 2026-09-05 to
    # 2026-09-21. The spend log and the drafts directory are compared
    # before and after, so the check fails the moment the key is reachable.
    examined += 1
    if key_guard_broken:
        fails.append("skipping the author.py subprocess: api_key() ignores "
                     "LOOP_NO_KEYFILE, so running it would spend money")
    spend_file = LOOP / "state" / "spend.json"
    drafts_dir = LOOP / "drafts"
    spend_before = spend_file.read_bytes() if spend_file.exists() else b""
    drafts_before = set(drafts_dir.glob("*")) if drafts_dir.exists() else set()
    p = None if key_guard_broken else subprocess.run(
        [sys.executable, str(LOOP / "author.py"), "a test topic"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp",
             "OPENROUTER_API_KEY": "", "LOOP_NO_KEYFILE": "1"})
    out = "" if p is None else p.stdout + p.stderr
    if "Traceback" in out:
        fails.append(f"author.py crashed with no key instead of stopping:\n"
                     f"{out[-400:]}")
    if p is not None and "OPENROUTER_KEY_MISSING" not in out:
        fails.append("author.py with LOOP_NO_KEYFILE=1 did not take the "
                     "OPENROUTER_KEY_MISSING stop — the key file was reachable "
                     f"and a real draft may have been paid for:\n{out[-300:]}")
    spend_after = spend_file.read_bytes() if spend_file.exists() else b""
    drafts_after = set(drafts_dir.glob("*")) if drafts_dir.exists() else set()
    if spend_after != spend_before or drafts_after != drafts_before:
        fails.append("the 'missing key' check SPENT MONEY: spend.json or "
                     "loop/drafts/ changed during a run that must not reach "
                     "OpenRouter")

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

    # ------------------------------------------------ 6. the model is never ""
    # GitHub Actions expands an unset repository variable to "" and still sets
    # the env var, so the cloud lane sent `"model": ""` and OpenRouter answered
    # HTTP 400 "No models provided" for all four topics (run 35587241167,
    # 2026-09-21). The Mac never reproduced it: the variable is absent there.
    import urllib.request
    for raw, want in (("", author.DEFAULT_MODEL), ("   ", author.DEFAULT_MODEL),
                      ("vendor/some-model", "vendor/some-model")):
        examined += 1
        os.environ["OPENROUTER_MODEL"] = raw
        try:
            got = author.configured_model()
        finally:
            del os.environ["OPENROUTER_MODEL"]
        if got != want:
            fails.append(f"configured_model() with OPENROUTER_MODEL={raw!r} "
                         f"returned {got!r}, wanted {want!r}")

    # End to end: draft() with the empty variable must hand the resolved
    # default to the HTTP client, and the client must never open a socket
    # with an empty model. No network: urlopen is replaced for the check.
    examined += 1
    sent: list[str] = []

    class _Reached(Exception):
        pass

    def _no_network(*a, **k):
        raise _Reached("urlopen was called")

    real_call, real_open = author.call_openrouter, urllib.request.urlopen

    def _capture(messages, model, key, **kw):
        sent.append(model)
        raise _Reached("captured")

    os.environ["OPENROUTER_MODEL"] = ""
    author.call_openrouter = _capture
    try:
        author.draft("a test question", "a-test-topic",
                     {"pov_id": "t", "line": "I once saw this myself."},
                     key="sk-or-v1-" + "0" * 64)
    except author.AuthorStop:
        pass  # _Reached maps to OPENROUTER_UNREACHABLE: expected
    finally:
        author.call_openrouter = real_call
        del os.environ["OPENROUTER_MODEL"]
    if sent != [author.DEFAULT_MODEL]:
        fails.append(f"draft() with OPENROUTER_MODEL='' sent model {sent!r}; "
                     f"must send {author.DEFAULT_MODEL!r}")

    examined += 1
    urllib.request.urlopen = _no_network
    try:
        author.call_openrouter([{"role": "user", "content": "x"}], "",
                               "sk-or-v1-" + "0" * 64)
        fails.append("call_openrouter('') did not refuse an empty model")
    except ValueError:
        pass
    except _Reached:
        fails.append("call_openrouter('') reached the network with an empty "
                     "model instead of refusing")
    finally:
        urllib.request.urlopen = real_open

    # Siblings: every lane resolves the model through configured_model().
    # A second `os.environ.get("OPENROUTER_MODEL", ...)` is the same defect
    # waiting in another file (localize.py had one). AST, not regex, so a
    # comment or docstring that names the variable is not a reader.
    import ast
    examined += 1
    readers = 0
    for f in sorted(LOOP.glob("*.py")):
        tree = ast.parse(f.read_text(), filename=str(f))
        owners: dict[int, str] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    owners.setdefault(id(n), fn.name)
        for n in ast.walk(tree):
            names = [c.value for c in ast.walk(n) if isinstance(c, ast.Constant)
                     and c.value == "OPENROUTER_MODEL"]
            is_env_read = (
                (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "get" and names)
                or (isinstance(n, ast.Subscript) and names))
            if not is_env_read or "environ" not in ast.dump(n):
                continue
            readers += 1
            if not (f.name == "author.py"
                    and owners.get(id(n)) == "configured_model"):
                fails.append(f"loop/{f.name}:{n.lineno} reads $OPENROUTER_MODEL "
                             f"directly; use author.configured_model()")
    if readers == 0:
        fails.append("no code reads $OPENROUTER_MODEL at all — the override "
                     "is dead and this check examined nothing")

    # ------------------------------------------------ 7. dead citations converge
    # Run 35604701442 (2026-09-21): attempt 1 cited a plausible dead page,
    # attempt 2 replaced it with another plausible dead page, and with
    # MAX_ATTEMPTS=2 the slot fell to AUTHOR_REQUIRED — a red run asking a
    # human to write a script. Two things fix that and both are pinned here:
    # the feedback names a page on the same site that exists, and the loop
    # has enough attempts to use it.
    import validate
    fake_live = {"https://www.mbari.org/": 200,
                 "https://www.whoi.edu/what-we-do/understand/": 200}

    def fake_probe(u, timeout=20):
        return (fake_live.get(u, 404), "ok" if u in fake_live else "http error")

    examined += 1
    got = author.nearest_live_ancestor(
        "https://www.whoi.edu/what-we-do/understand/climate/", fake_probe)
    if got != "https://www.whoi.edu/what-we-do/understand/":
        fails.append(f"nearest_live_ancestor stopped at {got!r}, not the "
                     f"first ancestor that answers 200")
    examined += 1
    got = author.nearest_live_ancestor("https://www.mbari.org/research/", fake_probe)
    if got != "https://www.mbari.org/":
        fails.append(f"nearest_live_ancestor did not reach the site root: {got!r}")
    examined += 1
    if author.nearest_live_ancestor("https://dead.example/a/b/", fake_probe) is not None:
        fails.append("nearest_live_ancestor invented a live page on a dead site")

    examined += 1
    real_probe = validate.probe
    validate.probe = fake_probe
    try:
        fb = author.dead_urls("## Sources\n- MBARI: Research — "
                              "https://www.mbari.org/research/\n")
    finally:
        validate.probe = real_probe
    if len(fb) != 1 or "https://www.mbari.org/ " not in fb[0] + " " \
            or "does exist" not in fb[0]:
        fails.append(f"dead_urls() feedback does not hand back the live "
                     f"ancestor: {fb!r}")

    # Convergence: three dead-citation drafts, a clean fourth, and the slot is
    # authored. Under the old MAX_ATTEMPTS=2 this raised
    # DRAFT_FAILED_VALIDATION. No network, no spend, no file outside a tempdir.
    examined += 1
    calls = {"n": 0}

    def _fake_call(messages, model, key, **kw):
        calls["n"] += 1
        return {"choices": [{"message": {"content": complete},
                             "finish_reason": "stop"}],
                "usage": {"cost": 0.0}}

    def _dead_thrice(text):
        return ([] if calls["n"] >= 4 else
                ["source URL returns HTTP 404 and does not exist: "
                 "https://www.mbari.org/research/"])

    real = (author.call_openrouter, author.dead_urls, author.record_spend,
            author.DRAFTS, author.shape_problems)
    # draft() reports its path relative to ROOT, so the tempdir lives inside
    # the (gitignored) drafts directory rather than /tmp.
    (LOOP / "drafts").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=LOOP / "drafts") as td:
        author.call_openrouter, author.dead_urls = _fake_call, _dead_thrice
        author.record_spend = lambda *a, **k: None
        author.shape_problems = lambda *a, **k: []   # the subject is the budget
        author.DRAFTS = Path(td)
        try:
            res = author.draft("Q?", "converge-test", pov, key="sk-or-v1-" + "0" * 64)
            if res.get("attempt") != 4 or calls["n"] != 4:
                fails.append(f"draft() accepted on attempt {res.get('attempt')} "
                             f"after {calls['n']} call(s); expected the fourth")
        except author.AuthorStop as e:
            fails.append(f"draft() gave up before its fourth attempt: {e.code} "
                         f"— a model that guesses a dead URL twice must still "
                         f"get a chance to cite the live page it was handed")
        finally:
            (author.call_openrouter, author.dead_urls, author.record_spend,
             author.DRAFTS, author.shape_problems) = real

    # ------------------------------------ 8. a directive rejection names the fix
    # Run 36164079633 (2026-09-25): `{{uncertain: 2000000 | species | range
    # 700000 to 2200000 | low confidence}}` over prose that said "2 million"
    # was rejected four times with the fault named and the remedy never, and
    # the slot fell to AUTHOR_REQUIRED. Two things are pinned: the malformed
    # RANGE (prose no parser reads; the renderer silently drops the beat) is
    # itself a rejection, and the feedback the model gets carries the remedy.
    bad = ("# Q?\n## Narration\n"
           "{{uncertain: 2000000 | species | range 700000 to 2200000 | low confidence}}\n"
           "Around 2 million species may live down there.\n"
           "## Human fingerprint gate\n")
    # The RANGE is drawn on screen too, so it is spoken too (V1's rule for
    # every number in a directive, unchanged).
    good = ("# Q?\n## Narration\n"
            "{{uncertain: 2,000,000 | species | 750,000 | low confidence}}\n"
            "Around 2,000,000 species, give or take 750,000, may live down "
            "there.\n"
            "## Human fingerprint gate\n")
    examined += 1
    flags = author.directive_truth_problems(bad)
    if not any(f.startswith("directive draws number '2000000'") for f in flags):
        fails.append(f"an unspoken directive number was not flagged: {flags!r}")
    if not any(f.startswith("uncertain directive's RANGE") for f in flags):
        fails.append(f"a prose RANGE the renderer cannot parse was not "
                     f"flagged: {flags!r}")
    examined += 1
    flags = author.directive_truth_problems(good)
    if flags:
        fails.append(f"a well-formed uncertain directive spoken verbatim was "
                     f"flagged: {flags!r}")

    examined += 1
    seen: list[list[dict]] = []
    drafts_out = iter([bad, good])

    def _fake_call2(messages, model, key, **kw):
        seen.append(messages)
        return {"choices": [{"message": {"content": next(drafts_out)},
                             "finish_reason": "stop"}],
                "usage": {"cost": 0.0}}

    real = (author.call_openrouter, author.dead_urls, author.record_spend,
            author.DRAFTS, author.shape_problems)
    with tempfile.TemporaryDirectory(dir=LOOP / "drafts") as td:
        author.call_openrouter, author.dead_urls = _fake_call2, lambda t: []
        author.record_spend = lambda *a, **k: None
        author.shape_problems = lambda t, p: author.directive_truth_problems(t)
        author.DRAFTS = Path(td)
        try:
            res = author.draft("Q?", "remedy-test", pov, key="sk-or-v1-" + "0" * 64)
            if res.get("attempt") != 2:
                fails.append(f"expected acceptance on attempt 2, got "
                             f"{res.get('attempt')}")
            fb = seen[1][-1]["content"] if len(seen) > 1 else ""
            if author.DIRECTIVE_REMEDY not in fb:
                fails.append("the rejection sent back to the model names the "
                             "fault but not the remedy; a retry loop that "
                             "repeats a diagnosis is paid attempts at the "
                             "same mistake")
        except author.AuthorStop as e:
            fails.append(f"draft() stopped ({e.code}) instead of accepting the "
                         f"corrected second draft")
        finally:
            (author.call_openrouter, author.dead_urls, author.record_spend,
             author.DRAFTS, author.shape_problems) = real

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
