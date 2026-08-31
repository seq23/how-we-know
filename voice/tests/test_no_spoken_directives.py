"""Guard: no {{directive}} text may ever reach the synthesiser.

A directive is a visual instruction (visuals/CONTRACT.md). Speaking one puts
"stat 10,935 METRES Deeper than Everest is tall NOAA" into the narration of a
monetised video. On episode 01 the un-guarded path fed 475 of 1,628 words -
29% of the read - straight to the model.

Two independent paths reach the model, so both are checked:
  * voice/narrate_all.py -> visuals/planner.plan()[i]["narration"]  (per-beat,
    the layout visuals/assemble.py actually consumes)
  * voice/synth.py       -> voice/script_text.read_script()         (whole file)

Hard-fails if it inspects zero scripts or zero directives: a test that examined
nothing must not report green.

Run:  <tts-python> -m pytest voice/tests/test_no_spoken_directives.py -q
      <tts-python> voice/tests/test_no_spoken_directives.py       (no pytest)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "voice"))
sys.path.insert(0, str(ROOT / "visuals"))

MARKUP = re.compile(r"\{\{|\}\}")

SCRIPTS = sorted((ROOT / "scripts").glob("*.md"))


def _directive_lines(md_path):
    return [l.strip() for l in md_path.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("{{")]


def prose_words(md_path):
    """Words of narration PROSE in a script: the Narration section with every
    directive line removed. This is the ground truth a correct read must match."""
    md = md_path.read_text(encoding="utf-8")
    body = md.split("## Narration", 1)[-1].split("\n## ", 1)[0]
    n = 0
    for blk in re.split(r"\n\s*\n", body):
        b = blk.strip()
        if not b or b.startswith("#"):
            continue
        for line in b.split("\n"):
            if not line.strip().startswith("{{"):
                n += len(line.split())
    return n


def directive_words(md_path):
    return sum(len(l.split()) for l in _directive_lines(md_path))


def test_scripts_exist_and_carry_directives():
    assert SCRIPTS, "no scripts found - refusing to pass on an empty loop"
    total = sum(len(_directive_lines(p)) for p in SCRIPTS)
    assert total > 0, "inspected 0 directives - the guard would be vacuous"


def test_planner_beats_are_directive_free():
    import planner
    seen_beats = 0
    for p in SCRIPTS:
        assert _directive_lines(p), f"{p.name} has no directives to strip"
        for i, b in enumerate(planner.plan(str(p))):
            seen_beats += 1
            t = b["narration"]
            assert not MARKUP.search(t), f"{p.name} beat {i}: directive markup in {t!r}"
    assert seen_beats > 0, "inspected 0 beats"


def test_script_text_is_directive_free():
    from script_text import read_script
    seen = 0
    for p in SCRIPTS:
        text = " ".join(read_script(str(p)))
        seen += 1
        assert not MARKUP.search(text), f"{p.name}: directive markup survived read_script"
        # Word count is the decisive test, not a keyword search. CONTRACT rule 1
        # requires a directive to quote the narration verbatim, so a directive's
        # words are ALREADY in the prose - a leak shows up as duplication, which
        # only a count can see. Episode 01 unguarded: 1628 read vs 1150 prose.
        got, want = len(text.split()), prose_words(p)
        assert got <= want * 1.02, (
            f"{p.name}: read_script yields {got} words but the script has {want} "
            f"words of prose ({directive_words(p)} words sit in directives) - "
            f"directive text is being spoken")
    assert seen > 0, "inspected 0 scripts"


def test_prose_word_count_matches_beats():
    """The beats must carry the script's PROSE and nothing else. If directives
    leaked, beat words would exceed prose words; if prose were dropped, they
    would fall far short."""
    import planner
    for p in SCRIPTS:
        assert directive_words(p) > 0, f"{p.name}: no directives - guard vacuous here"
        pw = prose_words(p)
        bw = sum(len(b["narration"].split()) for b in planner.plan(str(p)))
        assert pw > 0, f"{p.name}: no prose"
        assert bw <= pw, (f"{p.name}: beats carry {bw} words but the script has only "
                          f"{pw} words of prose - something non-prose leaked in")
        assert bw >= pw * 0.97, (f"{p.name}: beats carry {bw} of {pw} prose words - "
                                 f"narration is being dropped")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{fails} failure(s) over {len(SCRIPTS)} scripts")
    raise SystemExit(1 if fails else 0)
