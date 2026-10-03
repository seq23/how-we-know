"""Every writer of `audio/<slug>/beats.json` produces the SAME bytes, and the
committed manifests are already in that form, so a batch night that rewrites
a manifest without changing a value leaves `git status` clean.

CONFIRMED 2026-10-03. The nightly Mac batch (bin/batch-session.sh) ended with
`error: cannot pull with rebase: You have unstaged changes.` and the night's
captions commit never pushed. The working tree showed 34 manifests modified
and `git diff -w -- audio` EMPTY: formatting only. voice/narrate_all.py:332
rewrote every episode's manifest on every run as `json.dumps(rows, indent=1)`
with no trailing newline, while visuals/captions.py:record_durations and
loop/pov_repair.py wrote `json.dumps(rows, indent=2) + "\\n"`. Whichever ran
last won, so HEAD held 38 manifests in one shape and 4 in the other, and each
night flipped them. Beside them `audio/.narrate.lock/pid` - the narrator's
runtime lock - was TRACKED, so the lock's normal release showed as ` D`.

The fix: ONE serializer, `visuals/captions.py:write_beats_manifest`, used by
all three writers, which skips the write when the bytes are unchanged; every
committed manifest re-serialized once; the lock directory untracked and
ignored.

This test proves:
  (a) the helper is idempotent (a second write of unchanged rows writes
      nothing and the bytes are identical), record_durations writes canonical
      bytes and leaves an already-correct file untouched, and loop/pov_repair.py
      binds the very same function; voice/narrate_all.py cannot be imported
      outside the TTS venv, so its source is checked instead: it imports the
      helper and contains no other beats.json write;
  (b) no tracked path lies under audio/.narrate.lock/, the lock directory is
      ignored, and every tracked audio/*/beats.json is byte-for-byte canonical;
  (c) the OTHER half of the same failure: audio/narration_report.json, which
      narrate_all rewrites every run and nothing reads, had sat tracked and
      uncommitted since 2026-09-04 (the batch commits by explicit pathspec),
      so it alone would refuse the next pull. It is untracked and ignored,
      git tracks nothing under audio/ beyond the manifests and two inert
      pre-2026-09 artefacts, and bin/batch-session.sh stages the tracked
      manifests (`git add -u -- audio`) before its commit, so a manifest whose
      plan grew or shrank overnight is committed rather than left dirty.

Hard-fails when it examines zero manifests.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
sys.path.insert(0, os.path.join(ROOT, "visuals"))

import captions as CAP                                          # noqa: E402
import pov_repair                                               # noqa: E402

WRITERS = ("voice/narrate_all.py", "loop/pov_repair.py", "visuals/captions.py")
BATCH = "bin/batch-session.sh"
# Tracked before the "beats.json is the ONE tracked file in audio/" rule, and
# written by nothing that runs nightly. Anything else tracked under audio/ is
# a file some run can dirty without committing.
ALLOWED_TRACKED = {"audio/bed_test.wav", "audio/narration_audit.json"}
# Any serialization of manifest rows that is not the helper.
STRAY_WRITE = re.compile(r"json\.dumps\(\s*rows\b")

SAMPLE_ROWS = [
    {"i": 0, "segment": "hook", "narration": "A fish that is not deformed.",
     "seconds": 11.002666666666666},
    {"i": 1, "segment": "body", "narration": "Pressure, darkness, and us."},
]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def check() -> tuple[int, list[str]]:
    examined = 0
    fails: list[str] = []

    # ---- (a) the writers -------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="how-we-know-beats-") as td:
        p = Path(td) / "ep" / "beats.json"
        wrote = CAP.write_beats_manifest(p, SAMPLE_ROWS)
        first = p.read_bytes()
        examined += 1
        if not wrote:
            fails.append("write_beats_manifest reported no write on a new file")
        if first != CAP.beats_manifest_bytes(SAMPLE_ROWS):
            fails.append("write_beats_manifest did not write canonical bytes")
        if not first.endswith(b"}\n]\n") or b'\n  {\n' not in first:
            fails.append(f"canonical form is not indent=2 + newline: "
                         f"{first[-6:]!r}")
        mtime = p.stat().st_mtime_ns
        if CAP.write_beats_manifest(p, json.loads(first.decode())):
            fails.append("a second write of unchanged rows wrote the file")
        if p.read_bytes() != first or p.stat().st_mtime_ns != mtime:
            fails.append("unchanged rows changed the file's bytes or mtime")

        # record_durations: writes canonical bytes when a value changes, and
        # nothing at all when it would write what is already there.
        real_audio = CAP.AUDIO
        try:
            CAP.AUDIO = Path(td)
            changed = CAP.record_durations("ep", [11.002666666666666, 4.5], {0, 1})
            examined += 1
            if changed != 1:
                fails.append(f"record_durations changed {changed} beats, expected 1")
            after = p.read_bytes()
            rows = json.loads(after.decode())
            if after != CAP.beats_manifest_bytes(rows):
                fails.append("record_durations wrote non-canonical bytes")
            mtime = p.stat().st_mtime_ns
            if CAP.record_durations("ep", [11.002666666666666, 4.5], {0, 1}) != 0:
                fails.append("record_durations re-recorded unchanged durations")
            if p.read_bytes() != after or p.stat().st_mtime_ns != mtime:
                fails.append("record_durations touched an already-correct file")
        finally:
            CAP.AUDIO = real_audio

    # pov_repair binds the same function - an executable check, not prose.
    examined += 1
    if getattr(pov_repair, "write_beats_manifest", None) is not CAP.write_beats_manifest:
        fails.append("loop/pov_repair.py does not write beats.json through "
                     "captions.write_beats_manifest")

    # Source check for all three: no stray serialization of manifest rows.
    for rel in WRITERS:
        src = Path(ROOT, rel).read_text(encoding="utf-8")
        examined += 1
        if "write_beats_manifest" not in src:
            fails.append(f"{rel} never calls write_beats_manifest")
        strays = [ln for ln, line in enumerate(src.splitlines(), 1)
                  if STRAY_WRITE.search(line)
                  and "def beats_manifest_bytes" not in line
                  and "return (json.dumps(rows" not in line]
        if strays:
            fails.append(f"{rel} serializes manifest rows outside the helper "
                         f"at line(s) {strays}")

    # ---- (b) what git holds ----------------------------------------------
    tracked = _git("ls-files", "-z", "--", "audio").split("\0")
    lock = [t for t in tracked if t.startswith("audio/.narrate.lock/")]
    examined += 1
    if lock:
        fails.append(f"narrator lock is tracked: {lock}")
    ignored = subprocess.run(["git", "check-ignore", "-q", "audio/.narrate.lock/pid"],
                             cwd=ROOT).returncode == 0
    if not ignored:
        fails.append("audio/.narrate.lock/ is not in .gitignore")

    manifests = [t for t in tracked if re.fullmatch(r"audio/[^/]+/beats\.json", t)]
    if not manifests:
        fails.append("git tracks zero audio/*/beats.json manifests")
    stray = [t for t in tracked
             if t and t not in manifests and t not in ALLOWED_TRACKED]
    examined += 1
    if stray:
        fails.append(f"git tracks files under audio/ that a run rewrites and "
                     f"the batch never commits: {stray}")
    if subprocess.run(["git", "check-ignore", "-q", "audio/narration_report.json"],
                      cwd=ROOT).returncode != 0:
        fails.append("audio/narration_report.json is not in .gitignore")
    batch = Path(ROOT, BATCH).read_text(encoding="utf-8")
    add = re.search(r"^git add -u -- audio\b", batch, re.M)
    commit = batch.find('git commit -q -m "captions:')
    examined += 1
    if not add or commit < 0 or add.start() > commit:
        fails.append(f"{BATCH} does not stage the tracked manifests "
                     f"(`git add -u -- audio`) before its captions commit")
    for t in manifests:
        examined += 1
        raw = Path(ROOT, t).read_bytes()
        try:
            rows = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            fails.append(f"{t}: unreadable - {e}")
            continue
        if raw != CAP.beats_manifest_bytes(rows):
            fails.append(f"{t}: not in canonical form (indent=2 + trailing "
                         f"newline); re-serialize it with write_beats_manifest")

    return examined, fails


def main() -> int:
    examined, fails = check()
    if examined == 0:
        print("FAIL: examined zero beats manifests or writers")
        return 1
    print(f"inspected {examined} manifest writer(s) and tracked manifest(s)")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("all green - one canonical beats.json serialization, idempotent "
          "writers, lock untracked, every committed manifest already canonical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
