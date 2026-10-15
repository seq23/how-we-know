"""When measured timing moves, every caption file derived from it moves WITH it.

WHY (2026-10-15). `loop · tests` went red on main at 563b01d:
test_chapters_from_render found captions/how-deep-can-whales-dive.chapters.txt
saying 0:35 / 2:17 where the render says 0:39 / 2:21. The batch had re-narrated
the episode (a full re-render), loop/captions_build.py:record_durations wrote
the new wav durations into audio/<slug>/beats.json, and NOTHING rewrote the
.chapters.txt, .srt, .vtt or .timing.json beside it - the track builder only
builds MISSING tracks. Sixteen episodes' tracks were stale the same way. Two
components each kept their own copy of the timeline and only one was updated.

The fix: visuals/captions.py:derived_stale() says when an episode's caption
files no longer describe its measured timeline, and
loop/captions_build.py:sync_measured() records durations, rebuilds every stale
track (all episodes with a plan, not just the queue) and stages both in ONE
set, which the batch commits as one commit and pushes. This test:

  1. a fresh fixture is left byte-for-byte alone and nothing is staged;
  2. THE INCIDENT, Mac shape: one beat re-narrated longer (wavs on disk) ->
     beats.json, chapters.txt, .srt, .vtt and .timing.json all change, the
     chapters equal the measured list, every changed file is in
     captions_build.artifacts(slug), all staged in one call, script untouched;
  3. cloud shape (no wavs, beats.json moved by a pushed commit) with an EMPTY
     selection: the episode is still rebuilt - published episodes are covered;
  4. captions_build.run() goes through sync_measured, and the batch runs
     captions_build before its caption commit.

NEGATIVE PROOF (2026-10-15): making refresh_stale() return [] fails cases 2
and 3 ("chapters.txt still says 0:39 ..."); restored -> green.
"""
from __future__ import annotations

import ast
import hashlib
import shutil
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import captions as CAP                                        # noqa: E402
import captions_build as CB                                   # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


SLUG = "how-deep-can-whales-dive"
saved = {n: getattr(CAP, n) for n in ("SCRIPTS", "PLANS", "AUDIO", "RENDERS", "OUT")}
saved_stage, saved_cap = CB.stage_artifacts, CB._cap
staged_calls: list[list[str]] = []


def snapshot(t: Path) -> dict[str, str]:
    return {str(p.relative_to(t)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in t.rglob("*") if p.is_file() and p.suffix != ".wav"}


def fixture() -> Path:
    t = Path(tempfile.mkdtemp(prefix="cap-follow-"))
    for d in ("scripts", "plans", "audio", "renders", "captions"):
        (t / d).mkdir()
    shutil.copy(ROOT / "plans" / f"{SLUG}.json", t / "plans")
    shutil.copy(ROOT / "scripts" / f"{SLUG}.md", t / "scripts")
    (t / "audio" / SLUG).mkdir()
    shutil.copy(ROOT / "audio" / SLUG / "beats.json", t / "audio" / SLUG)
    for suf in (".srt", ".vtt", ".chapters.txt", ".timing.json",
                ".chapters.handwritten.txt"):
        src = ROOT / "captions" / f"{SLUG}{suf}"
        if src.exists():
            shutil.copy(src, t / "captions")
    CAP.SCRIPTS, CAP.PLANS, CAP.AUDIO = t / "scripts", t / "plans", t / "audio"
    CAP.RENDERS, CAP.OUT = t / "renders", t / "captions"
    return t


def write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(1000)
        w.writeframes(b"\x80" * round(seconds * 1000))


def rel_artifacts() -> set[str]:
    return {str(p.relative_to(ROOT)) for p in CB.artifacts(SLUG)}


CB._cap = lambda: CAP
CB.stage_artifacts = lambda slugs: staged_calls.append(list(slugs)) or []
temps = []
try:
    # ---- 1: fresh -> untouched ------------------------------------------
    T = fixture(); temps.append(T)
    check(CAP.derived_stale(SLUG) is None,
          f"1 the committed {SLUG} caption files are not the measured timeline: "
          f"{CAP.derived_stale(SLUG)}")
    before = snapshot(T)
    staged_calls.clear()
    got = CB.sync_measured([SLUG], note=lambda *_: None)
    check(got == [] and staged_calls == [] and snapshot(T) == before,
          f"1 a fresh episode was rewritten or staged: {got} {staged_calls}")

    # ---- 2: the incident, Mac shape --------------------------------------
    T = fixture(); temps.append(T)
    plan, _ = CAP.load_plan(SLUG)
    rec = CAP.recorded_durations(SLUG)
    check(len(rec) == len(plan), f"2 fixture beats.json is not fully measured "
                                 f"({len(rec)}/{len(plan)})")
    for i in range(len(plan)):
        write_wav(T / "audio" / SLUG / f"{i:04d}.wav",
                  rec.get(i, 1.0) + (4.0 if i == 3 else 0.0))
    old_ch = (T / "captions" / f"{SLUG}.chapters.txt").read_text()
    before = snapshot(T)
    staged_calls.clear()
    got = CB.sync_measured([SLUG], note=lambda *_: None)
    after = snapshot(T)
    changed = {k for k in after if before.get(k) != after[k]}
    want = CAP.chapters_file_text(CAP.measured_chapters(SLUG))
    new_ch = (T / "captions" / f"{SLUG}.chapters.txt").read_text()
    check(new_ch == want and new_ch != old_ch,
          f"2 chapters.txt did not follow the re-narration: still "
          f"{new_ch.splitlines()[1:3]}, measured {want.splitlines()[1:3]}")
    for f in (f"audio/{SLUG}/beats.json", f"captions/{SLUG}.chapters.txt",
              f"captions/{SLUG}.srt", f"captions/{SLUG}.vtt",
              f"captions/{SLUG}.timing.json"):
        check(f in changed, f"2 {f} did not change with the measured timing")
    check(f"scripts/{SLUG}.md" not in changed,
          "2 the script was rewritten (a bound script's bytes are lengthen's "
          "fingerprint)")
    check(changed <= rel_artifacts(),
          f"2 wrote files the commit set does not carry: "
          f"{sorted(changed - rel_artifacts())}")
    check(got == [SLUG] and staged_calls == [[SLUG]],
          f"2 durations and derived files were not staged together in one "
          f"call: returned {got}, staged {staged_calls}")
    check(CAP.derived_stale(SLUG) is None, "2 still stale after the rebuild")

    # ---- 3: cloud shape, empty selection ---------------------------------
    T = fixture(); temps.append(T)
    import json                                               # noqa: PLC0415
    bj = T / "audio" / SLUG / "beats.json"
    rows = json.loads(bj.read_text())
    rows[3]["seconds"] = float(rows[3]["seconds"]) + 6.0
    CAP.write_beats_manifest(bj, rows)
    check(bool(CAP.derived_stale(SLUG)),
          "3 derived_stale() did not notice beats.json moving under the track")
    staged_calls.clear()
    got = CB.sync_measured([], note=lambda *_: None)
    new_ch = (T / "captions" / f"{SLUG}.chapters.txt").read_text()
    check(new_ch == CAP.chapters_file_text(CAP.measured_chapters(SLUG)),
          f"3 chapters.txt still says {new_ch.splitlines()[1:3]} after a "
          f"pushed timing change")
    check(got == [SLUG] and staged_calls == [[SLUG]],
          f"3 an episode outside the selection was not rebuilt and staged: "
          f"{got} {staged_calls}")
finally:
    for n, v in saved.items():
        setattr(CAP, n, v)
    CB.stage_artifacts, CB._cap = saved_stage, saved_cap
    for t in temps:
        shutil.rmtree(t, ignore_errors=True)

# ---- 4: wiring ---------------------------------------------------------------
src = (LOOP / "captions_build.py").read_text()
run_fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "run")
called = {c.func.id for c in ast.walk(run_fn)
          if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
check("sync_measured" in called and "record_durations" not in called,
      f"4 captions_build.run() records durations without sync_measured: {called}")
batch = (ROOT / "bin" / "batch-session.sh").read_text()
i_build = batch.find("$PY loop/captions_build.py")
i_commit = batch.find('git commit -q -m "captions: tracks and measured beat timings')
check(0 <= i_build < i_commit,
      "4 bin/batch-session.sh does not run captions_build before its caption commit")

if examined == 0:
    print("FAIL test_caption_files_follow_timing: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_caption_files_follow_timing:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_caption_files_follow_timing: {examined} checks - caption files "
      f"follow measured timing and ship with it")
