"""Every narration passes the pronunciation layer, and every hard word it
clears was LISTENED TO.

2026-10-20, a viewer on "Why Is Deep Sea Light Blue?" (13-how-does-
bioluminescence-work-in-the-deep-sea): "AI had a stroke trying to say
'bioluminescence.'" Local whisper.cpp on that episode's beat wavs heard
"Biolu Min ESS Ents". The beats were voiced 2026-08-31 through the old
hyphen/CAPS lexicon; #99 removed that style but left bioluminescence unproven,
gave new scripts no check at all, and let Shorts re-air the old wavs.

Guards (no torch, no network, no whisper needed):
  1. ROUTING   both production narrators (voice/narrate_all.py,
               voice/food_voice.py) hand model.generate() pronounce.prepare(...)
               and run pronounce.job_check before voicing; synth.py's CLI uses
               the effective lexicon. Zero call sites found = failure.
  2. DETECTION hard_words() flags the words that have bitten this channel and
               not ordinary ones.
  3. PROOF     the committed raw_ok pin holds bioluminescence/bioluminescent
               and every row re-verifies (two readings, each heard as the word).
               Learned respellings (loop/state/pronunciation_learned.json) obey
               the model-readable style and re-verify the same way.
  4. RESPELL   every rule-made candidate is model-readable (no hyphen, no CAPS).
  5. LEGACY    a wav older than the #99 cutover whose narration holds an old
               respelling is stale, a newer one is not; visuals/shorts.py drops
               stale beats before cutting.
  6. NO PAID   the probe has no api.openai.com path left.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "voice"))

import pronounce  # noqa: E402

MUST_FLAG = ("bioluminescence", "bioluminescent", "phytoplankton", "chlorophyll",
             "chemosynthetic", "bathypelagic", "hydrothermal", "Saccharomyces",
             "Maillard")
MUST_NOT_FLAG = ("water", "everyone", "because", "light", "ocean", "scientists",
                 "temperature")


def _generate_args(path: Path) -> list[ast.AST]:
    tree = ast.parse(path.read_text(), filename=str(path))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "generate" and n.args:
            out.append(n.args[0])
    return out


def _is_prepare(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
        and node.func.attr == "prepare" and getattr(node.func.value, "id", "") == "pronounce"


def check_routing() -> list[str]:
    fails = []
    for rel in ("voice/narrate_all.py", "voice/food_voice.py"):
        p = ROOT / rel
        args = _generate_args(p)
        if not args:
            fails.append(f"{rel}: no model.generate() call found - examined zero call sites")
        for a in args:
            if not _is_prepare(a):
                fails.append(f"{rel}: model.generate() is handed {ast.unparse(a)!r}, "
                             f"not pronounce.prepare(...) - it skips the pronunciation layer")
        if "pronounce.job_check(" not in p.read_text():
            fails.append(f"{rel}: never runs pronounce.job_check - new hard words go unheard")
    src = (ROOT / "voice/synth.py").read_text()
    if "pronounce.effective_lexicon()" not in src:
        fails.append("voice/synth.py CLI does not use pronounce.effective_lexicon()")
    return fails


def check_detection() -> list[str]:
    fails = []
    text = " ".join(MUST_FLAG + MUST_NOT_FLAG)
    got = {w.lower() for w in pronounce.hard_words(text)}
    for w in MUST_FLAG:
        if w.lower() not in got:
            fails.append(f"hard_words() misses {w!r}")
    for w in MUST_NOT_FLAG:
        if w.lower() in got:
            fails.append(f"hard_words() flags the ordinary word {w!r}")
    return fails


def _verify_rows(label: str, term: str, row: dict, respelling: str | None = None) -> list[str]:
    fails = []
    rs = row.get("readings") or []
    if row.get("ok") is not True:
        fails.append(f"{label} {term!r}: ok is not true")
    if len(rs) < len(pronounce.CARRIERS):
        fails.append(f"{label} {term!r}: {len(rs)} reading(s), need {len(pronounce.CARRIERS)}")
    for r in rs:
        ok, _ = pronounce.heard(term, r.get("heard", ""))
        if not ok:
            fails.append(f"{label} {term!r}: pinned transcript {r.get('heard')!r} "
                         f"does not contain the word")
        if respelling is not None and respelling not in r.get("spoken_text", ""):
            fails.append(f"{label} {term!r}: reading was not spoken as {respelling!r}")
    return fails


def check_proof() -> list[str]:
    fails = []
    pin = json.loads(pronounce.PIN.read_text())
    raw = pin.get("raw_ok") or {}
    if not raw:
        return ["voice/tests/pronunciation_probe.json has no raw_ok proofs - examined zero"]
    for need in ("bioluminescence", "bioluminescent"):
        if need not in raw:
            fails.append(f"{need!r} has no raw_ok proof: nothing has heard the model say it")
    for term, row in raw.items():
        fails += _verify_rows("raw_ok", term, row)
        if term in pronounce.curated():
            fails.append(f"raw_ok {term!r} also has a curated entry - one or the other")
    lr = pronounce.learned()
    for term, row in lr["respell"].items():
        resp = row.get("respelling", "")
        if not pronounce.style_ok(resp):
            fails.append(f"learned {term!r} -> {resp!r}: not a model-readable respelling")
        fails += _verify_rows("learned", term, row, resp)
    for term, row in lr["raw_ok"].items():
        fails += _verify_rows("learned raw_ok", term, row)
    return fails


def check_respell() -> list[str]:
    fails = []
    for w in MUST_FLAG + ("xenophyophore", "Grimpoteuthis", "foraminifera",
                          "caramelization", "trimethylamine", "Galápagos"):
        cands = pronounce.respell_candidates(w)
        if not cands:
            fails.append(f"respell_candidates({w!r}) offers nothing")
        for c in cands:
            if not pronounce.style_ok(c):
                fails.append(f"respell_candidates({w!r}) made {c!r}: hyphen/CAPS style")
    return fails


def check_legacy() -> list[str]:
    fails = []
    leg = json.loads(pronounce.LEGACY.read_text())
    if "bioluminescence" not in (leg.get("lexicon") or {}):
        return ["voice/lexicon_legacy.json lacks the pre-#99 bioluminescence entry"]
    narr = "Bioluminescence is light produced by a chemical reaction."
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "0004.wav")
        Path(wav).write_bytes(b"RIFF")
        os.utime(wav, (1788220000, 1788220000))   # 2026-08-31, before the cutover
        if pronounce.stale_legacy_beat(narr, wav) != ["bioluminescence"]:
            fails.append("a 2026-08-31 bioluminescence beat is not flagged stale")
        if pronounce.stale_legacy_beat("The water is blue.", wav):
            fails.append("a legacy beat with no old respelling is flagged stale")
        os.utime(wav, None)
        if pronounce.stale_legacy_beat(narr, wav):
            fails.append("a beat voiced after the cutover is flagged stale")
    shorts = (ROOT / "visuals/shorts.py").read_text()
    if "drop_stale_voice(picked, by_index)" not in shorts:
        fails.append("visuals/shorts.py make_short never drops legacy-voiced beats")
    return fails


def check_blocked_cuts() -> list[str]:
    """Already-cut, not-yet-aired Shorts that carry legacy voice never upload."""
    fails = []
    path = ROOT / "loop/state/shorts_voice_blocked.json"
    cuts = json.loads(path.read_text()).get("cuts") or []
    if not cuts:
        return ["loop/state/shorts_voice_blocked.json lists zero cuts"]
    keys = {(c["slug"], int(c["rank"])) for c in cuts}
    if ("13-how-does-bioluminescence-work-in-the-deep-sea", 2) not in keys:
        fails.append("the ep-13 rank-2 cut (legacy 'bioluminescence') is not blocked")
    tree = ast.parse((ROOT / "loop/shorts_lane.py").read_text())
    pend = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and n.name == "pending"), None)
    if pend is None or "voice_blocked()" not in ast.unparse(pend) \
            or "in blocked" not in ast.unparse(pend):
        fails.append("loop/shorts_lane.pending() does not skip voice_blocked() cuts")
    return fails


def check_no_paid() -> list[str]:
    src = (ROOT / "voice/tests/pronunciation_probe.py").read_text()
    return ["pronunciation_probe.py still calls the paid whisper-1 API"] \
        if "api.openai.com" in src else []


def check() -> list[str]:
    return (check_routing() + check_detection() + check_proof() + check_respell()
            + check_legacy() + check_blocked_cuts() + check_no_paid())


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    pin = json.loads(pronounce.PIN.read_text())
    print(f"inspected 2 narrators, {len(pin.get('raw_ok') or {})} raw_ok proof(s), "
          f"{len(pronounce.curated())} curated + {len(pronounce.learned()['respell'])} learned respelling(s)")
    print("all green - every narration passes the pronunciation layer" if not f
          else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
