"""The pronunciation lexicon is written in a style the voice model speaks, and
every entry has been LISTENED TO.

2026-09-21. The owner heard "hypothermal" for "hydrothermal" in the Short for
`20-what-is-the-midnight-zone`; Whisper on the same audio heard "Bath-E-Pell
A.J. Ike" for bathypelagic and "chemo, syn, that, ik" for chemosynthetic.
Chatterbox has no phoneme input - it reads a respelling as TEXT - so a
dictionary-style respelling ("bath-ee-pel-AJ-ic": hyphens, CAPS stress) is
spoken as spelled-out letters and separate words. Two guards, neither of
which needs torch, soundfile or a network:

  1. STYLE. No respelling contains a hyphen or a run of two or more capitals,
     unless the key is a true acronym (NOAA, ROV, CTD...), which is spelled
     out as spaced single letters.
  2. PROOF. voice/tests/pronunciation_probe.json - written only by
     voice/tests/pronunciation_probe.py after synthesising each term and
     transcribing it with whisper-1 - lists every current LEXICON key with
     ok=true and the SAME respelling. Change a respelling and this fails until
     the probe has heard the new one. A pinned term that is no longer in the
     lexicon fails too (a stale pin is not a proof).

The lexicon is read with ast, not imported: voice/synth.py imports soundfile
at module level and the render venv does not have it - an unrun validator
must not read as a passing one.

Hard-fails on an empty lexicon or an empty pin.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SYNTH = ROOT / "voice" / "synth.py"
PIN = ROOT / "voice" / "tests" / "pronunciation_probe.json"

ACRONYM = re.compile(r"^[A-Z]{2,}s?$")


def lexicon() -> dict[str, str]:
    tree = ast.parse(SYNTH.read_text(), filename=str(SYNTH))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "LEXICON" and node.value is not None:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "LEXICON" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("voice/synth.py has no LEXICON assignment")


def style_problems(term: str, respelling: str) -> list[str]:
    out = []
    if ACRONYM.match(term):
        body = re.sub(r"'?s$", "", respelling) if term.endswith("s") else respelling
        if not re.fullmatch(r"(?:[A-Z] )*[A-Z]", body) \
                and not re.fullmatch(r"[a-z]+(?: [a-z]+)*", respelling):
            out.append(f"{term!r}: an acronym is spaced single capitals "
                       f"('R O V') or lowercase pseudo-words ('em bar ee'), "
                       f"not {respelling!r}")
        return out
    if "-" in respelling:
        out.append(f"{term!r} -> {respelling!r}: hyphens are read as "
                   f"separate words; write one lowercase pseudo-word")
    if re.search(r"[A-Z]{2,}", respelling):
        out.append(f"{term!r} -> {respelling!r}: a CAPS stress chunk is "
                   f"read as letters; the model has no stress notation")
    if respelling[1:] != respelling[1:].lower():
        out.append(f"{term!r} -> {respelling!r}: capitals after the first "
                   f"letter are read as letters")
    return out


def check() -> list[str]:
    fails: list[str] = []
    lex = lexicon()
    if not lex:
        return ["LEXICON is empty - this test examined zero entries"]

    # 1. style
    for term, resp in lex.items():
        fails += style_problems(term, resp)

    # 2. proof
    if not PIN.exists():
        return fails + [f"{PIN.relative_to(ROOT)} is missing: no entry has "
                        f"been listened to. Run voice/tests/pronunciation_probe.py"]
    pin = json.loads(PIN.read_text())
    terms = pin.get("terms") or {}
    if not terms:
        return fails + ["the pronunciation pin lists zero terms"]
    for term, resp in lex.items():
        row = terms.get(term)
        if row is None:
            fails.append(f"{term!r} is in LEXICON but was never probed - run "
                         f"pronunciation_probe.py --only {term}")
            continue
        if row.get("respelling") != resp:
            fails.append(f"{term!r}: LEXICON says {resp!r} but the proof heard "
                         f"{row.get('respelling')!r} - re-run the probe")
        if row.get("ok") is not True:
            fails.append(f"{term!r}: the probe did NOT hear it as intended "
                         f"({[r.get('heard') for r in row.get('readings', [])]})")
        if len(row.get("readings") or []) < 2:
            fails.append(f"{term!r}: fewer than two carrier readings pinned")
    for term in terms:
        if term not in lex:
            fails.append(f"{term!r} is pinned but no longer in LEXICON - stale "
                         f"proof; re-run the probe in full")

    print(f"inspected {len(lex)} lexicon entr(y/ies) against "
          f"{len(terms)} pinned proof(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every respelling is model-readable and has been heard"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
