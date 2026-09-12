"""Nothing a loop stage writes may be left behind on the runner.

`bin/loop-stage.sh` stages the stage's output with NARROW pathspecs, on
purpose: the loop must not sweep up a directory it does not own. The cost of
that narrowness is that a stage which writes a TRACKED file no pathspec names
loses the work, and neither of the two ways it shows up says what happened.

CONFIRMED on run 34687628665 (2026-09-12, `loop · Sat 06:00 · score demand ÷
competition`). The scoring pass ran `research/publish_order_domain.py`, which
runs `research/competition.py`, which hit the YouTube Data API quota and wrote
its named stop to `research/competition_stop.json` (competition.py:69,
`STOP_OUT`). That file is TRACKED, and it is read back by `research/propose.py`
(line 61) to explain why a domain has no queue -- but the weekly-score pathspec
named only `research/publish_order*.json`. So it stayed modified-and-unstaged,
and `git pull --rebase` inside `push_with_retries` refused outright:

    error: cannot pull with rebase: You have unstaged changes.
    error: Please commit or stash them.

three times, after which the job died claiming "could not push", naming the
COMMIT rather than the one file that blocked it. The stage itself had exited 0.
A full weekly scoring pass was thrown away, and the log pointed at the wrong
thing.

The other shape of the same defect is worse: when nothing else happens to be
staged, the script prints "no repo changes to commit", exits 0, and the work is
gone under a green tick, where nobody ever looks.

Two changes fixed it, and this test proves BOTH negatively -- each by putting
the defect back one line at a time and showing the failure returns:

1. the weekly-score pathspec now stages `research/competition*.json` as well as
   `research/publish_order*.json`, because the stop file is that stage's output
   just as much as the ranking is.
2. a Rule 0 guard refuses to continue when ANY tracked file is still modified
   after staging, and NAMES it -- so the next stage that outgrows its pathspec
   is a one-line fix with the path printed, not three failed rebases and a
   misleading message. Untracked files are deliberately not covered: scratch
   output and downloaded assets are untracked precisely because they are not
   repo state.

Hard-fails when it examines zero cases.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOOP_STAGE = os.path.join(ROOT, "bin", "loop-stage.sh")

# The one line that arms the Rule 0 guard, and the one line that carries the
# weekly-score pathspec. Substituting either is how this test puts the original
# defect back: a negative proof has to restore the BROKEN state, not simulate
# it. If either string stops appearing verbatim the test fails loudly rather
# than quietly proving nothing.
GUARD_LINE = 'STRAY="$(git diff --name-only 2>/dev/null)"'
GUARD_OFF = 'STRAY=""'
SCORE_PATHSPEC = "git add research/competition*.json 2>/dev/null"
# Restoring the defect = deleting that line. `:` keeps the `if` body legal.
SCORE_PATHSPEC_OLD = ":"


def sh(*args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


def build_repo(td: str, script_text: str) -> tuple[str, str]:
    """A bare origin plus a clone that looks like a fresh Actions checkout.

    Returns (work, origin). The clone carries the real bin/loop-stage.sh (or a
    deliberately broken variant of it), a stub loop/common.py for week_id, and
    a tracked research/competition_stop.json so the stage can MODIFY a tracked
    file rather than create an untracked one -- which is the whole distinction
    under test.
    """
    origin = os.path.join(td, "origin.git")
    work = os.path.join(td, "work")
    sh("git", "init", "-q", "--bare", "-b", "main", origin, cwd=td)
    sh("git", "clone", "-q", origin, work, cwd=td)
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t")):
        sh("git", "config", k, v, cwd=work)

    os.makedirs(os.path.join(work, "bin"), exist_ok=True)
    os.makedirs(os.path.join(work, "loop", "state", "stops"), exist_ok=True)
    os.makedirs(os.path.join(work, "research"), exist_ok=True)
    os.makedirs(os.path.join(work, "docs"), exist_ok=True)

    dst = os.path.join(work, "bin", "loop-stage.sh")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(script_text)
    os.chmod(dst, 0o755)

    with open(os.path.join(work, "loop", "common.py"), "w", encoding="utf-8") as fh:
        fh.write('def week_id():\n    return "2026-W37"\n')
    # Tracked, and written by the stage below -- the production shape.
    with open(os.path.join(work, "research", "competition_stop.json"),
              "w", encoding="utf-8") as fh:
        fh.write('{"status": "none"}\n')
    with open(os.path.join(work, "docs", "keep.md"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    # The real repo ignores these; without it `git add loop` stages the
    # __pycache__ the wrapper's own `from common import week_id` just created,
    # and every case here silently becomes "something was staged" rather than
    # the case it meant to test.
    with open(os.path.join(work, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("__pycache__/\n*.pyc\nstage_under_test.py\n")

    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-q", "-m", "seed", cwd=work)
    sh("git", "push", "-q", "-u", "origin", "main", cwd=work)
    return work, origin


def run_stage(work: str, stage: str, writes: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the real wrapper over a stage that writes the given repo files."""
    payload = "\n".join(
        f'open({p!r}, "w").write({c!r})' for p, c in writes.items())
    stage_py = os.path.join(work, "stage_under_test.py")
    with open(stage_py, "w", encoding="utf-8") as fh:
        fh.write(payload + "\n")
    env = dict(os.environ)
    # The `surface` block is gh-only and must not run here; without a token it
    # is skipped, which is what we want -- this test is about the commit and
    # push halves, not about issue creation.
    env.pop("GITHUB_TOKEN", None)
    env["LOOP_PYTHON"] = sys.executable
    return sh("bash", os.path.join(work, "bin", "loop-stage.sh"),
              stage, "stage_under_test.py", cwd=work, env=env)


def landed(origin: str, path: str, needle: str) -> bool:
    """Did the content actually reach origin? Never inferred from an exit code."""
    r = subprocess.run(["git", "show", f"main:{path}"], cwd=origin,
                       capture_output=True, text=True)
    return r.returncode == 0 and needle in r.stdout


def main() -> int:
    with open(LOOP_STAGE, encoding="utf-8") as fh:
        real = fh.read()

    checks, failures = 0, []

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if ok:
            print(f"  ok  {name}")
        else:
            print(f"  ✗ {name}{(': ' + detail) if detail else ''}")
            failures.append(name)

    # The substitutions this test depends on must still exist verbatim.
    if GUARD_LINE not in real:
        print(f"FAIL: bin/loop-stage.sh no longer contains {GUARD_LINE!r} -- the "
              "Rule 0 guard this test proves is gone or was rewritten. Update "
              "this test deliberately; do not delete the guard.")
        return 1
    if SCORE_PATHSPEC not in real:
        print(f"FAIL: bin/loop-stage.sh no longer contains {SCORE_PATHSPEC!r} -- "
              "the weekly-score stop file would stop being committed again.")
        return 1

    # ---------------------------------------------------------------- 1
    # THE REGRESSION ITSELF. weekly-score writes the competition stop file;
    # it must be committed and must reach origin.
    with tempfile.TemporaryDirectory() as td:
        work, origin = build_repo(td, real)
        r = run_stage(work, "weekly-score",
                      {"research/competition_stop.json": '{"status": "NAMED_STOP"}\n'})
        check("weekly-score exits 0 when it writes research/competition_stop.json",
              r.returncode == 0, f"rc={r.returncode} {r.stderr.strip()[:300]}")
        check("the competition stop file reaches origin",
              landed(origin, "research/competition_stop.json", "NAMED_STOP"),
              "it was written on the runner and never pushed")

    # ---------------------------------------------------------------- 2
    # NEGATIVE PROOF for 1: restore the old pathspec and the same run must
    # fail. Without this, check 1 could pass for reasons unrelated to the fix.
    with tempfile.TemporaryDirectory() as td:
        broken = real.replace(SCORE_PATHSPEC, SCORE_PATHSPEC_OLD, 1)
        work, origin = build_repo(td, broken)
        r = run_stage(work, "weekly-score",
                      {"research/competition_stop.json": '{"status": "NAMED_STOP"}\n'})
        check("with the old pathspec restored, the same run FAILS",
              r.returncode != 0,
              "the defect did not come back, so check 1 proves nothing")
        check("with the old pathspec restored, the stop file never reaches origin",
              not landed(origin, "research/competition_stop.json", "NAMED_STOP"))

    # ---------------------------------------------------------------- 3
    # THE GUARD, on a stage with no pathspec of its own. This is the general
    # case: any future stage that outgrows its pathspec.
    with tempfile.TemporaryDirectory() as td:
        work, origin = build_repo(td, real)
        r = run_stage(work, "mon-draft",
                      {"research/competition_stop.json": '{"status": "STRAY"}\n',
                       "docs/keep.md": "touched\n"})
        out = r.stdout + r.stderr
        check("a stray tracked file fails the stage", r.returncode != 0,
              f"rc={r.returncode}")
        check("and the failure NAMES the file",
              "research/competition_stop.json" in out,
              "the message did not name the path, which is the whole point")
        check("and it does not bury the diagnosis under three failed rebases",
              "cannot pull with rebase" not in out,
              "the push was attempted anyway")

    # ---------------------------------------------------------------- 4
    # NEGATIVE PROOF for 3, in its SILENT shape: neuter the guard, write ONLY
    # an unstaged tracked file, and the run goes green with the work lost.
    with tempfile.TemporaryDirectory() as td:
        broken = real.replace(GUARD_LINE, GUARD_OFF, 1)
        work, origin = build_repo(td, broken)
        r = run_stage(work, "mon-draft",
                      {"research/competition_stop.json": '{"status": "STRAY"}\n'})
        check("with the guard neutered, the same run goes GREEN",
              r.returncode == 0, f"rc={r.returncode}")
        check("with the guard neutered, the work is silently lost",
              not landed(origin, "research/competition_stop.json", "STRAY"),
              "nothing was lost, so the guard is not proven")

    # ---------------------------------------------------------------- 5
    # The guard must not fire on UNTRACKED files. Scratch output, downloaded
    # assets and caches are untracked on purpose; sweeping them in is how the
    # loop would start committing junk, and failing on them would take every
    # harvesting lane red.
    with tempfile.TemporaryDirectory() as td:
        work, origin = build_repo(td, real)
        r = run_stage(work, "mon-draft", {"loop/state/drafted.json": "{}\n"})
        check("an untracked file does not trip the guard", r.returncode == 0,
              f"rc={r.returncode} {r.stderr.strip()[:300]}")

    # ------------------------------------------------------------ Rule 0
    if checks == 0:
        print("FAIL: this test examined zero cases")
        return 1
    print(f"\nexamined {checks} case(s), {len(failures)} failed")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("all green - every tracked file a stage writes is committed, and one "
          "that no pathspec covers fails the stage by name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
