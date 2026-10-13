"""The Mac's two lanes pull before they act and report after - without a human.

    .venv/bin/python loop/mac_sync.py pull          # bring main up to date, safely
    .venv/bin/python loop/mac_sync.py heartbeat --lane backfill --uploaded 4 --held 1
    .venv/bin/python loop/mac_sync.py push          # commit + push the Mac's state files

WHY THE PULL NEEDED A BRAIN. bin/loop-backfill-daily.sh ran `git pull --rebase
--autostash` and, when that failed, wrote PULL_FAILED and exited. From 12
September 2026 it failed every morning: a loop-state file the cloud had started
tracking (loop/state/stops/_held.json) existed untracked on the Mac, and a
tracked one (_streaks.json) had a local edit that conflicted. Both are the
LOOP'S OWN STATE - files the cloud lanes author and the Mac only reads - so the
right answer was always "take upstream". Nothing did, PULL_FAILED was not in
loop/stop_policy.json, the stop file never left the Mac, and nine finished
episodes sat unshipped behind a message nobody was shown.

`pull` fetches, then for every path under loop/state/ that upstream changed and
the Mac also touched (modified OR untracked), moves the Mac's copy aside to
loop/state/_local/<stamp>/ and takes upstream's. The Mac's authoritative files
- the ledger and quota it writes after uploading - are committed by the lane
that wrote them before the next pull, so they are never in that set. Then it
runs the same `git pull --rebase --autostash`. If THAT still fails it is a real
conflict in something a human edited, and PULL_FAILED is now a classified stop.

WHY THE HEARTBEAT EXISTS. Every stop the cloud lanes take is committed with
their state and read by loop/digest.py from the repository. The Mac's stops
were written to loop/state/stops/ and stayed on the Mac, so the digest - which
runs in the cloud - could not see that the Mac had nine finished renders and
had shipped none of them for a week. `heartbeat` writes loop/state/mac_heartbeat.json
naming when each Mac lane last ran, last succeeded, and what it was holding;
`push` commits it with the lane's stop file and pushes. The digest then reads
both, and raises MAC_NOT_SHIPPING when the Mac has finished work it has not
shipped for longer than `mac.unshipped_days` in loop/config.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

from common import read_json, week_id, write_json                # noqa: E402

HEARTBEAT = ROOT / "loop" / "state" / "mac_heartbeat.json"
LOCAL = ROOT / "loop" / "state" / "_local"
STATE_PREFIX = "loop/state/"


def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    # MAC_SYNC_REPO: tests only - lets loop/tests/test_mac_branch_guard.py run
    # the REAL bin/batch-session.sh against a throwaway clone's branch.
    return subprocess.run(["git", *args], cwd=os.environ.get("MAC_SYNC_REPO") or ROOT, text=True,
                          capture_output=True, check=check)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")



# ---------------------------------------------------------------- branch guard
#
# 2026-10-13. Every Mac lane commits on WHATEVER BRANCH THE CHECKOUT IS ON and
# then runs `git push origin main` - which pushes the LOCAL `main` ref, not
# HEAD. The checkout had been left on fix/breaker-resets-in-draft after PR
# #189 merged, so four "Mac state" commits (backfill, batch, imagery-harvest,
# captions) piled up on a dead branch, `push` reported nothing wrong, and the
# 23:00 batch ran from code and scripts 39 commits behind main: it would have
# voiced and rendered the stale versions of the 13 reopened scripts. So:
# pull() and push() refuse off main, and `guard` (run by bin/batch-session.sh
# before the night begins) refuses the whole batch unless the checkout is on
# main and holds origin/main after a fetch + fast-forward, writing a NAMED
# STOP otherwise. Proved by loop/tests/test_mac_branch_guard.py.

MAIN = "main"


def current_branch() -> str:
    """The checked-out branch, or "" for a detached HEAD."""
    return _git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def off_main_reason() -> str:
    b = current_branch()
    if b == MAIN:
        return ""
    where = f"branch {b!r}" if b else "a detached HEAD"
    return (f"the Mac checkout is on {where}, not {MAIN!r}; a lane run here "
            f"would act on that branch's files and strand its commits off main")


def _stop_dir() -> Path:
    return Path(os.environ.get("LOOP_STOPS_DIR") or ROOT / "loop" / "state" / "stops")


def write_stop(lane: str, code: str, message: str, unblock: str) -> Path:
    d = _stop_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{week_id()}-{lane}.json"
    path.write_text(json.dumps({
        "stage": lane, "week": week_id(), "at": _now(), "code": code,
        "message": message, "unblock": unblock, "disposition": "needs_human",
        "disposition_why": f"'{code}' is classified needs_human in "
                           f"loop/stop_policy.json: a defect, not a wait.",
        "exit_code": 3, "work_done_before_stop": [], "notes": []}, indent=2) + "\n")
    return path


def guard(lane: str) -> tuple[bool, str]:
    """Refuse unless the checkout is on main and up to date with origin/main."""
    reason = off_main_reason()
    if reason:
        path = write_stop(
            lane, "MAC_NOT_ON_MAIN", reason + ". Refusing the whole run.",
            f"cd {ROOT} && git status, commit or move anything uncommitted, "
            f"then: git checkout {MAIN} && git pull --ff-only. "
            f"Any commits on that branch must reach main by a PR first.")
        return False, f"NAMED STOP [MAC_NOT_ON_MAIN]: {reason} (recorded -> {path})"
    ok, msg = pull()
    if not ok:
        path = write_stop(lane, "PULL_FAILED",
                          f"could not bring {MAIN} up to date before the run: {msg}",
                          f"cd {ROOT} && git pull --rebase origin {MAIN}; resolve what it reports.")
        return False, f"NAMED STOP [PULL_FAILED]: {msg} (recorded -> {path})"
    if _git("merge-base", "--is-ancestor", f"origin/{MAIN}", "HEAD").returncode != 0:
        path = write_stop(lane, "MAC_BEHIND_MAIN",
                          f"after the pull, HEAD does not contain origin/{MAIN}",
                          f"cd {ROOT} && git pull --ff-only origin {MAIN}")
        return False, f"NAMED STOP [MAC_BEHIND_MAIN]: HEAD lacks origin/{MAIN} (recorded -> {path})"
    return True, f"on {MAIN}, up to date with origin/{MAIN}: {msg}"


# ---------------------------------------------------------------- pull

def upstream_changed(base: str = "origin/main") -> set[str]:
    r = _git("diff", "--name-only", "HEAD", base)
    return {p for p in r.stdout.split("\n") if p}


def local_touched() -> tuple[set[str], set[str]]:
    """(modified tracked, untracked) paths, from `git status --porcelain`."""
    modified, untracked = set(), set()
    for line in _git("status", "--porcelain", "--untracked-files=all").stdout.split("\n"):
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.add(path)
        elif code.strip():
            modified.add(path)
    return modified, untracked


def set_aside(paths: list[str]) -> list[str]:
    """Move the Mac's copies of loop-state files out of the way, keeping them."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    kept = []
    for p in paths:
        src = ROOT / p
        if not src.exists():
            continue
        dst = LOCAL / stamp / p[len(STATE_PREFIX):]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        kept.append(str(dst.relative_to(ROOT)))
    return kept


def pull(base: str = "origin/main") -> tuple[bool, str]:
    """Bring main up to date. Returns (ok, message). Never raises."""
    if off_main_reason():
        return False, off_main_reason()
    f = _git("fetch", "origin", "main")
    if f.returncode != 0:
        return False, "fetch failed: " + (f.stderr.strip().splitlines() or ["?"])[-1]
    changed = upstream_changed(base)
    modified, untracked = local_touched()
    collide = sorted(p for p in changed
                     if p.startswith(STATE_PREFIX)
                     and (p in modified or p in untracked))
    notes = []
    if collide:
        kept = set_aside(collide)
        # A tracked file moved aside reads as deleted; restore it from HEAD so the
        # rebase sees a clean path and then takes upstream's version.
        tracked = [p for p in collide if p in modified]
        if tracked:
            _git("checkout", "--", *tracked)
        notes.append(f"took upstream for {len(collide)} loop-state file(s) the "
                     f"Mac had touched; the Mac's copies are in {LOCAL.relative_to(ROOT)}/")
    r = _git("pull", "--rebase", "--autostash", "origin", "main")
    if r.returncode != 0:
        tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-2:]
        # Leave nothing half-done: a stranded rebase blocks every later run.
        _git("rebase", "--abort")
        return False, "; ".join(notes + ["pull --rebase failed: " + " / ".join(tail)])
    # A PERSON'S EDIT THAT CONFLICTS is the one thing left that can go wrong,
    # and git handles it quietly: the autostash fails to re-apply, exit 0, the
    # edit is kept in `git stash list` and the working tree is left with
    # conflict markers in it. Left like that, every later pull fails on the
    # markers. So the conflicted files are restored to upstream - the person's
    # version is safe in the stash and named here - and this run is PULL_FAILED
    # so a human resolves it, while tomorrow's run finds a clean tree.
    unmerged = [p for p in _git("diff", "--name-only", "--diff-filter=U").stdout.split("\n") if p]
    if unmerged:
        _git("checkout", "HEAD", "--", *unmerged)
        return False, "; ".join(notes + [
            f"a local edit conflicts with upstream in {', '.join(unmerged)}; the edit is "
            f"kept in `git stash list` and the file(s) are at upstream's version"])
    return True, "; ".join(notes + [(r.stdout.strip().splitlines() or ["up to date"])[-1]])


# ---------------------------------------------------------------- heartbeat

def heartbeat(lane: str, ok: bool, **facts) -> dict:
    """Record one Mac lane's run. `ok` means it finished what it set out to do."""
    hb = read_json(HEARTBEAT, default={})
    rec = hb.get(lane) or {}
    rec.update({"last_run_at": _now(), "week": week_id(), "ok": bool(ok)})
    if ok:
        rec["last_success_at"] = rec["last_run_at"]
    rec.update({k: v for k, v in facts.items() if v is not None and v != ""})
    # An EMPTY string clears a fact: `resumed_from` is set only on a night
    # the batch resumed after an interruption, and must not outlive it.
    for k in [k for k, v in facts.items() if v == ""]:
        rec.pop(k, None)
    if ok:
        rec.pop("incomplete_night", None)   # a finished run supersedes it
    hb[lane] = rec
    hb["renders_finished"] = len(glob.glob(str(ROOT / "renders" / "*-final.mp4")))
    hb["updated"] = _now()
    write_json(HEARTBEAT, hb)
    return hb


# ---------------------------------------------------------------- push

def push(paths: list[str], message: str) -> tuple[bool, str]:
    """Commit exactly these paths (if changed) and push. Never `git add -A`."""
    if off_main_reason():
        # Committing here and pushing `main` is exactly how four Mac-state
        # commits were stranded on a dead branch (2026-10-13). Commit nothing.
        return False, "refused, nothing committed: " + off_main_reason()
    # A stop file a stage CLEARED is gone from disk but still tracked; its
    # deletion must be committed too, or origin keeps a resolved stop forever.
    tracked = {p for p in paths
               if _git("ls-files", "--error-unmatch", "--", p).returncode == 0}
    existing = [p for p in paths if (ROOT / p).exists() or p in tracked]
    if not existing:
        return True, "nothing to commit"
    _git("add", "-A", "--", *existing)
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return True, "nothing changed"
    c = _git("commit", "-q", "-m", message)
    if c.returncode != 0:
        return False, "commit failed: " + c.stderr.strip()[-200:]
    p = _git("push", "origin", "main")
    if p.returncode != 0:
        # The cloud committed meanwhile. Rebase onto it once and retry; the
        # files here are the Mac's own, so a rebase cannot lose anyone's work.
        r = _git("pull", "--rebase", "--autostash", "origin", "main")
        if r.returncode != 0:
            _git("rebase", "--abort")
            return False, "push failed and the rebase to retry it failed; next run rebases"
        p = _git("push", "origin", "main")
        if p.returncode != 0:
            return False, "push failed twice; next run retries"
    return True, "pushed"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull")
    g = sub.add_parser("guard")
    g.add_argument("--lane", required=True)
    h = sub.add_parser("heartbeat")
    h.add_argument("--lane", required=True)
    h.add_argument("--ok", type=int, default=1)
    h.add_argument("--uploaded", type=int, default=None)
    h.add_argument("--held", default=None,
                   help="comma-separated slugs the render gate is holding")
    h.add_argument("--pending", type=int, default=None,
                   help="finished episodes still to ship after this run")
    h.add_argument("--resumed-from", default=None,
                   help="phase/episode an interrupted night resumed from "
                        "(empty clears it); see loop/batch_progress.py")
    p = sub.add_parser("push")
    p.add_argument("--lane", required=True)
    p.add_argument("paths", nargs="*")
    a = ap.parse_args()

    if a.cmd == "pull":
        ok, msg = pull()
        print(f"  {'pulled' if ok else 'PULL FAILED'}: {msg}")
        return 0 if ok else 3
    if a.cmd == "guard":
        ok, msg = guard(a.lane)
        print(f"  {msg}" if ok else msg)
        return 0 if ok else 3
    if a.cmd == "heartbeat":
        held = [s for s in (a.held or "").split(",") if s]
        hb = heartbeat(a.lane, bool(a.ok), uploaded=a.uploaded, held=held,
                       pending=a.pending, resumed_from=a.resumed_from)
        print(f"  heartbeat: {a.lane} ok={bool(a.ok)} renders_finished="
              f"{hb['renders_finished']} held={len(held)}")
        return 0
    if a.cmd == "push":
        wk = week_id()
        paths = list(a.paths) + [
            str(HEARTBEAT.relative_to(ROOT)),
            f"loop/state/stops/{wk}-{a.lane}.json",
            f"loop/state/stops/{wk}-render-gate.json",
            "loop/state/render_hold.json",
            "loop/state/stops/_held.json",
        ]
        ok, msg = push(sorted(set(paths)), f"{a.lane}: Mac state {dt.date.today():%Y-%m-%d}")
        print(f"  {msg}")
        return 0 if ok else 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
