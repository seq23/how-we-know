"""A render's measured wpm must not drift when its SCRIPT is edited later.

CONFIRMED 2026-09-03, found during review of this same branch: commit
d2b4733 both (a) deleted a boilerplate sentence and rewrote producer notes to
second person across all 20 scripts, AND (b) measured the voice's wpm from
`## Narration` word counts read fresh off `scripts/*.md` — in that order,
within the same commit. The 17 already-rendered episodes' AUDIO reflects the
PRE-edit text (they are deliberately not re-rendered — re-rendering an
already-paid-for episode buys nothing). Reproduced directly: running
`loop/durations.py --refresh` (the module's own documented maintenance
command) after that edit silently moved the measured wpm from 144.58 (range
133.52-154.19, correct — matches what the audio actually says) to 142.38
(range 129.18-151.95, wrong — an artifact of pairing edited-down text against
unchanged old audio). That number feeds `loop/author.py`'s narration word
budget and `loop/config.json`'s AVD floor derivation for every future
episode. A wrong constant that nothing checked is exactly the defect this
branch exists to delete; corrupting it again on the very next maintenance run
would be the same defect wearing the fix's clothes.

The fix: `loop/state/durations.json` freezes
`narration_words_at_measurement` the first time a slug is measured, and
`loop/durations.py:measure_model()` uses that frozen count forever after,
never a fresh read of scripts/*.md for a slug that already has one. A script
can be edited for captions, voice, or wording any number of times after its
audio is recorded; its measured wpm must not move because of it.

This test proves both directions: an edit to an ALREADY-MEASURED slug's
narration must not change its frozen word count or the pooled wpm; a
genuinely NEW slug (never measured before) must still pick up its real word
count normally, or the freeze would have silently broken authoring new
episodes instead.

Hard-fails when it examines zero slugs.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)


def check() -> tuple[int, list[str]]:
    examined = 0
    fails: list[str] = []

    with tempfile.TemporaryDirectory(prefix="how-we-know-durfreeze-") as td:
        tmp = os.path.join(td, "repo")
        # A minimal standalone copy: durations.py resolves every path off its
        # own file location, so this is the same isolation approach
        # test_cloud_upload.py already uses for loop/arming.py's evidence
        # file, not a new pattern.
        shutil.copytree(os.path.join(ROOT, "loop"),
                        os.path.join(tmp, "loop"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(tmp, "scripts"))
        os.makedirs(os.path.join(tmp, "renders"))

        sys.path.insert(0, os.path.join(tmp, "loop"))
        import importlib
        import durations as D  # noqa: E402
        importlib.reload(D)
        D.ROOT = __import__("pathlib").Path(tmp)
        D.RENDERS = D.ROOT / "renders"
        D.SCRIPTS = D.ROOT / "scripts"
        D.DURATIONS = D.ROOT / "loop" / "state" / "durations.json"
        D.RUNTIME_MODEL = D.ROOT / "loop" / "state" / "runtime_model.json"
        D.MIN_EPISODES_FOR_MODEL = 2
        for p in (D.DURATIONS, D.RUNTIME_MODEL):
            if p.exists():
                p.unlink()

        def make_episode(slug: str, narration_words: int, seconds: float):
            text = ("# t\n\n## Narration\n" + " ".join(["word"] * narration_words)
                    + "\n")
            (D.SCRIPTS / f"{slug}.md").write_text(text, encoding="utf-8")
            # durations.py shells out to ffprobe; stub it so this test needs
            # no real media file, only the freezing/model logic itself.
            D.render_path = lambda s, _p=(D.RENDERS / f"{slug}-final.mp4"): (
                _p if s == slug or True else None)

        # ---- 1. measure two episodes for the first time -----------------
        examined += 1
        (D.RENDERS / "ep-a-final.mp4").write_text("stub")
        (D.RENDERS / "ep-b-final.mp4").write_text("stub")
        make_episode("ep-a", 1000, 400.0)
        make_episode("ep-b", 1000, 400.0)
        D.ffprobe_duration = lambda p: (
            400.0 if "ep-a" in str(p) or "ep-b" in str(p) else None)
        m1 = D.model(refresh=True)
        if m1.get("wpm") != 150.0:
            fails.append(f"initial model wpm={m1.get('wpm')!r}, expected "
                         f"150.0 (1000 words / 400s * 60)")

        frozen_a = D.load()["episodes"]["ep-a"].get(
            "narration_words_at_measurement")
        examined += 1
        if frozen_a != 1000:
            fails.append(f"ep-a's narration_words_at_measurement={frozen_a!r} "
                         f"after its first measurement, expected 1000 - a "
                         f"freshly-measured slug must freeze its real count")

        # ---- 2. edit ep-a's script text DOWN, as item 2/3 did -----------
        examined += 1
        make_episode("ep-a", 400, 400.0)     # same audio, shorter script now
        m2 = D.model(refresh=True)
        frozen_a_after = D.load()["episodes"]["ep-a"].get(
            "narration_words_at_measurement")
        if frozen_a_after != 1000:
            fails.append(f"editing ep-a's script AFTER measurement changed "
                         f"its frozen word count to {frozen_a_after!r} "
                         f"(expected it to stay 1000) - this is the exact "
                         f"2026-09-03 defect: a script edit corrupting an "
                         f"already-measured render's wpm")
        if m2.get("wpm") != 150.0:
            fails.append(f"pooled wpm moved to {m2.get('wpm')!r} after "
                         f"editing an ALREADY-MEASURED script's narration "
                         f"text - expected it to stay 150.0, unaffected by "
                         f"an edit to text that is no longer what the "
                         f"render actually says")

        # ---- 3. a genuinely NEW slug still measures normally -------------
        examined += 1
        (D.RENDERS / "ep-c-final.mp4").write_text("stub")
        make_episode("ep-c", 2000, 400.0)
        D.ffprobe_duration = lambda p: 400.0
        m3 = D.model(refresh=True)
        frozen_c = D.load()["episodes"]["ep-c"].get(
            "narration_words_at_measurement")
        if frozen_c != 2000:
            fails.append(f"ep-c (never measured before) froze "
                         f"{frozen_c!r} words, expected 2000 - the freeze "
                         f"must not prevent a brand-new episode from being "
                         f"measured for real")

    return examined, fails


def main() -> int:
    examined, fails = check()
    if examined == 0:
        print("FAIL: examined zero durations-freezing cases")
        return 1
    print(f"inspected {examined} durations-freezing case(s)")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("all green - an already-measured episode's wpm survives a later "
         "script edit; a new episode still measures for real")
    return 0


if __name__ == "__main__":
    sys.exit(main())
