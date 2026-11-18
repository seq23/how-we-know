#!/usr/bin/env python3
"""PAUSED FOR THE PEACE BE STILL LIBRARY FILL: no new voice or render while the app's library fills.

    python loop/pbs_pause.py gate     # the Mac jobs: exit 10 + PAUSED_FOR_PBS_FILL while paused, else 0
    python loop/pbs_pause.py status   # the same judgement, always exit 0

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
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
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
    """The cloud's view: the mirror the Mac last pushed."""
    try:
        rec = json.loads((root / MIRROR_REL).read_text())
    except (OSError, ValueError):
        rec = None
    return judge(rec, now)


def main(argv: list[str]) -> int:
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
