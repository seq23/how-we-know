#!/usr/bin/env python3
"""PAUSED FOR THE PEACE BE STILL LIBRARY FILL: no new voice or render while the app's library fills.

    python loop/pbs_pause.py gate     # the Mac jobs: exit 10 + PAUSED_FOR_PBS_FILL while paused, else 0
    python loop/pbs_pause.py status   # the same judgement, always exit 0
    python loop/pbs_pause.py hold --pid N   # after the pause: hold the fill's lock while N lives

Her call, 18 Nov 2026: "we can put the YouTube videos on pause while we fill
our library for the app and then add the app into the cadence".

THE CONTRACT IS ONE FILE: ~/.peace-be-still/library-fill.active (JSON:
started, expected_end, reason). The Peace Be Still fill job creates and
removes it; nothing in this repo does.

  * While it exists, every Mac job that VOICES or RENDERS a new How We Know or
    Whisper Almanac video stops at its start with the line
    PAUSED_FOR_PBS_FILL and exit 0, a note, never a failure
    (bin/food-session.sh; bin/batch-session.sh skips its voice, render and
    footage phases). Uploads of finished videos and Short cuts keep running.
  * The cloud cannot see the Mac's home folder, so `gate` mirrors the state
    into loop/state/pbs_fill.json (started and expected_end only; never the
    reason - the repo is public), and the nightly batch pushes it.
    loop/publish_floor.py reads the mirror: while paused it files no STOPPED
    issue for either channel and says "Paused for the Peace Be Still library
    fill since <date>" in its daily line instead.
  * A pause older than 21 days is IGNORED everywhere: the jobs voice and
    render again and STOPPED fires (a stuck fill must not silence the
    channels forever). loop/tests/test_pbs_pause.py.
  * The file removed: the next gate deletes the mirror and everything runs
    that night, with no other change.
  * AFTER THE PAUSE, ONE HEAVY JOB AT A TIME (hostile review 18 Nov 2026): the
    fill job keeps running every 15 minutes after the file is gone (content
    scripts, then Hush Harbor; ~850 MB and four cores each run), and nothing
    stopped it voicing beside Chatterbox on this 8 GB Mac - the swap that cut
    nights to 1-16 beats in Sep/Oct 2026. So a How We Know or Almanac night
    that is NOT paused runs `hold --pid $$`: a background process that takes
    the fill's own lock (~/.peace-be-still/library-fill.lock, the flock
    audio/fill.py and audio/hush_harbor.py already yield to) and keeps it
    until the night's process exits. A fill run already going finishes first
    (the hold waits for it); every later one steps aside until morning.
    While paused the hold takes nothing: the Mac is the fill's.
  * While paused, no Almanac render either: loop/whisper_upload.render_ready
    asks `paused()` (a voiced script waits; the upload of finished renders
    and the Short cuts still run).
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
MIRROR_REL = "loop/state/pbs_fill.json"
MAX_DAYS = 21
PAUSED_EXIT = 10
CODE = "PAUSED_FOR_PBS_FILL"
CT = ZoneInfo("America/Chicago")


def fill_file() -> Path:
    return Path(os.environ.get("PBS_FILL_FILE") or Path.home() / ".peace-be-still" / "library-fill.active")


def _t(x) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=CT)
    except (TypeError, ValueError):
        return None


def lock_file() -> Path:
    return Path(os.environ.get("PBS_FILL_LOCK") or fill_file().parent / "library-fill.lock")


def paused() -> bool:
    """Is the Mac paused for the fill right now (the local file, under 21 days)?"""
    return bool(judge(read_local())["paused"])


def hold(pid: int, poll: float | None = None) -> int:
    """Take the fill's lock and keep it while PID lives (see the docstring).
    A note on every path, exit 0: preparation, never a failure of the night."""
    if paused():
        print("pbs hold: paused for the fill - the lock stays the fill's")
        return 0
    lf = lock_file()
    if not lf.parent.is_dir():
        print(f"pbs hold: no {lf.parent} on this Mac - nothing to hold")
        return 0
    poll = float(os.environ.get("PBS_HOLD_POLL") or 20) if poll is None else poll
    fh = lf.open("a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("pbs hold: a Peace Be Still fill run is mid-way; it finishes, then this night holds "
              "the lock and the next fill runs step aside", flush=True)
        while True:                       # wait for that run, but never outlive the night
            try:
                os.kill(pid, 0)
            except OSError:
                return 0
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(poll)
    print(f"pbs hold: holding {lf.name} while pid {pid} runs (Peace Be Still fill runs wait for morning)",
          flush=True)
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            return 0
        time.sleep(poll)


def read_local(path: Path | None = None) -> dict | None:
    """The fill file as {started, expected_end}, or None when there is none.
    The file existing is the signal: unreadable JSON still pauses, from its mtime."""
    p = path or fill_file()
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    started = _t(d.get("started")) or _dt.datetime.fromtimestamp(p.stat().st_mtime, _dt.timezone.utc)
    return {"started": started.isoformat(), "expected_end": str(d.get("expected_end") or "")[:40]}


def judge(rec: dict | None, now: _dt.datetime | None = None) -> dict:
    """{paused, stale, line}. A record older than MAX_DAYS is stale: not paused."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if not rec:
        return {"paused": False, "stale": False, "line": "not paused for the Peace Be Still library fill"}
    started = _t(rec.get("started")) or now
    since = f"{started.astimezone(CT):%a %d %b %Y}"
    days = (now - started).total_seconds() / 86400
    if days > MAX_DAYS:
        return {"paused": False, "stale": True,
                "line": f"note: the Peace Be Still library-fill pause has been on since {since} "
                        f"({int(days)} days, over {MAX_DAYS}): ignored - every job runs and the floor alarm is live"}
    end = f", expected to end {rec['expected_end']}" if rec.get("expected_end") else ""
    return {"paused": True, "stale": False, "line": f"Paused for the Peace Be Still library fill since {since}{end}"}


def mirror(rec: dict | None, root: Path = ROOT) -> None:
    """Write (or remove) the repo copy the cloud reads. Unchanged is not rewritten."""
    p = root / MIRROR_REL
    if rec is None:
        p.unlink(missing_ok=True)
        return
    body = json.dumps({"_why": "Mirror of the Mac's ~/.peace-be-still/library-fill.active "
                               "(loop/pbs_pause.py); read by loop/publish_floor.py.", **rec}, indent=2) + "\n"
    if not p.exists() or p.read_text() != body:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def repo_status(root: Path = ROOT, now: _dt.datetime | None = None) -> dict:
    """The cloud's view: the mirror the Mac last pushed (PBS_FILL_MIRROR: a
    test's own copy, so a real pause on main never leaks into a test)."""
    mp = Path(os.environ["PBS_FILL_MIRROR"]) if os.environ.get("PBS_FILL_MIRROR") else root / MIRROR_REL
    try:
        rec = json.loads(mp.read_text())
    except (OSError, ValueError):
        rec = None
    return judge(rec, now)


def main(argv: list[str]) -> int:
    if argv[:1] == ["hold"] and len(argv) == 3 and argv[1] == "--pid" and argv[2].isdigit():
        return hold(int(argv[2]))
    if argv[:1] not in (["gate"], ["status"]):
        print(__doc__)
        return 2
    rec = read_local()
    if argv[0] == "gate":
        mirror(rec)
    j = judge(rec)
    if j["paused"]:
        print(f"{CODE}: {j['line']}. No How We Know or Whisper Almanac video is voiced or rendered "
              f"tonight; uploads and Short cuts of finished videos keep running.")
        return PAUSED_EXIT if argv[0] == "gate" else 0
    print(j["line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
