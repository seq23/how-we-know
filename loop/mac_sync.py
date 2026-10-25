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


def _repo() -> Path:
    return Path(os.environ.get("MAC_SYNC_REPO") or ROOT)


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


# ---------------------------------------------------------------- two-writer state

# LOOP-STATE FILES TWO HOSTS WRITE, AND HOW TO MERGE THEM (2026-10-25, #235).
# The Mac commits loop/state/comments/ledger.json (boss-os's comment watch runs
# loop/comments.py here, then `mac_sync.py push --lane comments`) and the cloud
# handoff lane writes the same file when it posts a channel comment; both bump
# loop/state/stops/_streaks.json. On 21 Oct 2026 14:05 the Mac's commit
# (9cba7cc) could not push, its rebase conflicted with the cloud's handoff
# commit, push() aborted and LEFT THE COMMIT ON MAIN - and from then every
# pull() failed on the same conflict: PULL_FAILED, "the night is refused",
# four nights with nothing rendered, and a stop file that could not reach
# origin because the push was the thing failing. Both writers only ADD to
# these files (keyed records, append-only lists), so a merge that keeps both
# sides' records is exact, not a guess. Only these named files are merged;
# any other conflict is still PULL_FAILED. Guarded by
# loop/tests/test_mac_sync_two_writer_merge.py.

def _merge_records(a: dict, b: dict, newer_key: str | None = None) -> dict:
    out = dict(a)
    for k, v in b.items():
        if k not in out:
            out[k] = v
        elif isinstance(out[k], dict) and isinstance(v, dict):
            if newer_key and (str(v.get(newer_key) or "") > str(out[k].get(newer_key) or "")):
                out[k] = v
            elif not newer_key:
                out[k] = _merge_records(out[k], v)
        elif isinstance(out[k], list) and isinstance(v, list):
            seen = {json.dumps(x, sort_keys=True) for x in out[k]}
            out[k] = out[k] + [x for x in v if json.dumps(x, sort_keys=True) not in seen]
        elif isinstance(v, str) and isinstance(out[k], str) and k in ("updated", "last_at"):
            out[k] = max(out[k], v)
    return out


def merge_comments_ledger(upstream: dict, mac: dict) -> dict:
    """Every record either side holds: cursors/seen/channel_comments keyed by
    id (the Mac's newer sweep wins a shared key), actions/sweeps appended."""
    out = _merge_records(upstream, mac)
    for k in ("cursors", "seen", "instructions", "channel_comments"):
        if isinstance(mac.get(k), dict) and isinstance(upstream.get(k), dict):
            out[k] = {**upstream[k], **mac[k]}
    return out


def merge_streaks(upstream: dict, mac: dict) -> dict:
    """Keyed by stage; each host owns its own stages. A stage both touched
    keeps the record with the later last_at."""
    return _merge_records(upstream, mac, newer_key="last_at")


TWO_WRITER_MERGE = {
    "loop/state/comments/ledger.json": merge_comments_ledger,
    "loop/state/stops/_streaks.json": merge_streaks,
}


def _resolve_two_writer_rebase(max_steps: int = 50) -> tuple[bool, list[str]]:
    """Inside a stopped rebase: merge every conflicted path that is in
    TWO_WRITER_MERGE and continue, until the rebase finishes. Returns
    (finished, merged paths). Any other conflicted path -> (False, ...) and
    the caller aborts. Stage 2 is upstream (the base being rebuilt), stage 3
    the Mac's commit being replayed."""
    merged: list[str] = []
    for _ in range(max_steps):
        unmerged = [p for p in _git("diff", "--name-only", "--diff-filter=U").stdout.split("\n") if p]
        if not unmerged:
            c = _git("-c", "core.editor=true", "rebase", "--continue")
            if c.returncode == 0 and not _rebase_in_progress():
                return True, merged
            if not _rebase_in_progress():
                return False, merged
            continue
        if any(p not in TWO_WRITER_MERGE for p in unmerged):
            return False, merged
        for p in unmerged:
            try:
                up = json.loads(_git("show", f":2:{p}").stdout or "{}")
                mac = json.loads(_git("show", f":3:{p}").stdout or "{}")
            except ValueError:
                return False, merged
            write_json(_repo() / p, TWO_WRITER_MERGE[p](up, mac))
            _git("add", "--", p)
            merged.append(p)
    return False, merged


def _rebase_in_progress() -> bool:
    gd = _git("rev-parse", "--git-dir").stdout.strip() or ".git"
    gdp = Path(gd) if Path(gd).is_absolute() else _repo() / gd
    return (gdp / "rebase-merge").exists() or (gdp / "rebase-apply").exists()


def _rebase_onto_upstream() -> tuple[bool, str]:
    """`git pull --rebase --autostash origin main`, healing a two-writer
    loop-state conflict instead of failing on it."""
    r = _git("pull", "--rebase", "--autostash", "origin", "main")
    if r.returncode == 0:
        return True, (r.stdout.strip().splitlines() or ["up to date"])[-1]
    if _rebase_in_progress():
        done, merged = _resolve_two_writer_rebase()
        if done:
            return True, (f"merged both writers' records in {', '.join(sorted(set(merged)))} "
                          f"and rebased the Mac's commits onto origin/main")
        _git("rebase", "--abort")
    tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-2:]
    return False, "pull --rebase failed: " + " / ".join(tail)


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
    ok, rmsg = _rebase_onto_upstream()
    if not ok:
        # Leave nothing half-done: a stranded rebase blocks every later run.
        if _rebase_in_progress():
            _git("rebase", "--abort")
        return False, "; ".join(notes + [rmsg])
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
    return True, "; ".join(notes + [rmsg])


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

# EVERY TRACKED FILE `loop/lengthen.py bind` CAN WRITE, so every push carries
# them. 2026-10-14: the 04:00 batch bound seven cloud re-opens (pending_bind ->
# full_rerender, old renders recorded in superseded_renders.json, a stale plan
# unlinked) and nothing pushed that state. Origin kept `pending_bind` records
# beside script bytes the caption pass then changed: V49 red on main, and the
# cloud upload lane blind to superseded renders it must refuse. The bind is the
# Mac's authoritative write, so - like the ledger and quota - it is committed
# before the next pull, never left for `pull` to set aside.
# Guarded by loop/tests/test_bind_state_is_pushed.py, which runs bind() on a
# fixture and fails on any tracked file it writes that bind_paths() omits.
BIND_STATE = (
    "loop/state/lengthen.json",
    "loop/state/superseded_renders.json",
    "loop/state/durations.json",       # durations.forget() on a full re-render
)


def bind_paths(state: Path | None = None) -> list[str]:
    """BIND_STATE plus plans/<slug>.json of every episode bind() has bound
    (it rewrites the plan on a splice and unlinks it on a full re-render).
    push() keeps only paths that exist or are tracked, and stages nothing
    that did not change."""
    try:
        doc = json.loads((state or ROOT / BIND_STATE[0]).read_text())
    except (OSError, ValueError):
        doc = {}
    slugs = sorted(s for s, r in (doc.get("episodes") or {}).items()
                   if isinstance(r, dict) and r.get("bound_at"))
    return list(BIND_STATE) + [f"plans/{s}.json" for s in slugs]


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
        ok, rmsg = _rebase_onto_upstream()
        if not ok:
            return False, f"push failed and the rebase to retry it failed ({rmsg}); next run rebases"
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
            # what the narrator's pronunciation gate learned (voice/pronounce.py);
            # only the Mac writes it, so every Mac push carries it
            "loop/state/pronunciation_learned.json",
        ] + bind_paths()
        ok, msg = push(sorted(set(paths)), f"{a.lane}: Mac state {dt.date.today():%Y-%m-%d}")
        print(f"  {msg}")
        return 0 if ok else 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
