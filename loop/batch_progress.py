"""The nightly batch's progress file: what makes an interrupted night resumable.

    loop/state/_local/batch_progress.json      (gitignored; this Mac only)

WHY IT EXISTS (owner, 2026-10-12: "no sleep and restart on wake, I need
both"). The Mac never sleeps on AC now, but it can still be unplugged and run
flat, or rebooted, in the middle of the 23:00 batch. Every step of
bin/batch-session.sh already skips work that is on disk (a voiced beat, a
finished render, a Short with its receipt, an R2 object with the same
checksum), so re-running continues rather than restarts. What was missing was
anything that RE-RAN it: a killed batch waited for the next 23:00 and the
night was written off.

So the batch records a unit here as each one completes, and the launchd agent
com.howweknow.batch-resume (every 300 s) runs
`bin/batch-session.sh --resume-if-interrupted`, which asks `gate` below:

  * an incomplete progress file from TONIGHT  -> resume it;
  * no progress file for tonight, 23:00-06:00 -> start tonight's batch (the Mac
    was off at 23:00; launchd fires a missed calendar job on wake from SLEEP,
    never after a power-off or reboot);
  * 09:00-22:00 with an incomplete night      -> do NOT resume: the day's cloud
    lanes own the Mac's outputs. Report it once (heartbeat + the mac-batch
    stop file, BATCH_NIGHT_INCOMPLETE, self-resolving: tonight's batch picks
    the same work up, because the work is idempotent);
  * anything else                             -> nothing to do.

"Tonight" is the window 22:00 -> 09:00 named by the date it began, so a batch
started at 23:00 on the 12th and a resume at 03:00 on the 13th are one night.

BATCH_NOW (YYYY-MM-DDTHH:MM) and BATCH_PROGRESS override the clock and the
path so loop/tests/test_batch_resume_on_wake.py can drive it.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "loop" / "state" / "_local" / "batch_progress.json"

NIGHT_BEGINS = 22        # a batch started at or after this hour is "tonight"
START_FROM = 23          # the scheduled start; a never-started night starts
START_UNTIL = 6          # ... between 23:00 and 06:00 only
CUTOFF = 9               # 09:00: com.howweknow.backfill and the cloud lanes

# gate() exit codes, read by bin/batch-session.sh
GO = 0
NOOP = 10
REPORT = 11


def now() -> _dt.datetime:
    s = os.environ.get("BATCH_NOW")
    return _dt.datetime.fromisoformat(s) if s else _dt.datetime.now()


def path() -> Path:
    return Path(os.environ.get("BATCH_PROGRESS") or DEFAULT)


def night_of(t: _dt.datetime) -> str | None:
    """The date the night containing `t` began, or None in the day window."""
    if t.hour >= NIGHT_BEGINS:
        return t.date().isoformat()
    if t.hour < CUTOFF:
        return (t.date() - _dt.timedelta(days=1)).isoformat()
    return None


def read() -> dict:
    try:
        return json.loads(path().read_text())
    except (OSError, ValueError):
        return {}


def write(p: dict) -> None:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=2) + "\n")
    os.replace(tmp, f)                   # never a half-written progress file


def _stamp() -> str:
    return now().isoformat(timespec="seconds")


def where(p: dict) -> str:
    return f"{p.get('phase') or 'start'}/{p.get('episode') or '-'}"


def gate() -> tuple[int, str]:
    """Should --resume-if-interrupted run the batch now? (code, one line)."""
    t, p = now(), read()
    n = night_of(t)
    if n is None:
        if p and not p.get("complete") and p.get("night") \
                and not p.get("reported_at"):
            p["reported_at"] = _stamp()
            write(p)
            return REPORT, (f"night of {p['night']} stopped at {where(p)} and it "
                            f"is past {CUTOFF:02d}:00 - not resuming; reported")
        return NOOP, f"nothing to resume: outside the night window ({t:%H:%M})"
    if p.get("night") == n:
        if p.get("complete"):
            return NOOP, f"nothing to resume: night of {n} completed"
        return GO, f"resuming night of {n} from {where(p)}"
    if t.hour >= START_FROM or t.hour < START_UNTIL:
        return GO, f"night of {n} never started - starting it now"
    return NOOP, f"nothing to resume: no batch for the night of {n} ({t:%H:%M})"


def begin() -> str:
    """Start or resume tonight's record. Prints the resume line; returns
    the resumed-from position ('' for a fresh night)."""
    t, p = now(), read()
    n = night_of(t) or f"day-{t.date().isoformat()}"
    if p.get("night") == n and not p.get("complete"):
        frm = where(p)
        moved = _set_aside_inflight_render(p)
        p["resumed_from"] = frm
        p.setdefault("resumes", []).append({"at": _stamp(), "from": frm})
        p.pop("rendering", None)
        write(p)
        print(f"  resuming night of {n} from {frm}")
        if moved:
            print(f"  an interrupted render was set aside: {moved}")
        return frm
    write({"night": n, "started_at": _stamp(), "last_completed_at": None,
           "phase": "start", "episode": None, "phases_done": [], "units": [],
           "complete": False})
    return ""


def _set_aside_inflight_render(p: dict) -> str:
    """A render killed mid-mux leaves renders/<slug>-final.mp4 TRUNCATED, and
    render_one skips any slug whose file exists - so the cut-short video would
    be pushed as finished. The progress file names the slug that was being
    assembled; move its output aside (never delete) so it is rendered again."""
    slug = p.get("rendering")
    if not slug:
        return ""
    renders = Path(os.environ.get("BATCH_RENDERS_DIR") or ROOT / "renders")
    out = renders / f"{slug}-final.mp4"
    if not out.exists():
        return ""
    dst = renders / "interrupted" / f"{slug}-final.{now():%Y%m%dT%H%M}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(out), str(dst))
    return str(dst.relative_to(renders.parent))


def mark(phase: str, episode: str | None = None, *, whole: bool = False) -> None:
    p = read()
    p["phase"], p["episode"] = phase, episode
    p["last_completed_at"] = _stamp()
    p.setdefault("units", []).append({"phase": phase, "episode": episode,
                                      "at": p["last_completed_at"]})
    if whole and phase not in p.setdefault("phases_done", []):
        p["phases_done"].append(phase)
    write(p)


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    cmd = a[0] if a else ""
    if cmd == "gate":
        code, line = gate()
        print(line)
        return code
    if cmd == "begin":
        begin()
        return 0
    if cmd == "resumed-from":
        print(read().get("resumed_from") or "")
        return 0
    if cmd == "done":                    # exit 0 if phase a[1] completed
        return 0 if a[1] in (read().get("phases_done") or []) else 1
    if cmd == "phase":                   # a whole phase finished
        mark(a[1], whole=True)
        return 0
    if cmd == "unit":                    # one episode finished in a phase
        mark(a[1], a[2] if len(a) > 2 else None)
        return 0
    if cmd == "rendering":               # in flight: set / clear
        p = read()
        if len(a) > 1 and a[1]:
            p["rendering"] = a[1]
        else:
            p.pop("rendering", None)
        write(p)
        return 0
    if cmd == "set":                     # set KEY VALUE (e.g. caprc)
        p = read()
        p[a[1]] = a[2]
        write(p)
        return 0
    if cmd == "get":
        print(read().get(a[1], a[2] if len(a) > 2 else ""))
        return 0
    if cmd == "complete":
        p = read()
        p.update({"complete": True, "completed_at": _stamp(),
                  "exit_code": int(a[1]) if len(a) > 1 else 0})
        p.pop("rendering", None)
        write(p)
        return 0
    if cmd == "narration-window":       # exit 0 if narration may run now
        until = os.environ.get("NARRATION_UNTIL", "07:00")
        hh, mm = (int(x) for x in until.split(":"))
        t = now()
        return 0 if t.hour >= NIGHT_BEGINS or t.time() < _dt.time(hh, mm) else 1
    if cmd == "report-incomplete":
        return report_incomplete()
    print("usage: batch_progress.py gate|begin|done|phase|unit|rendering|set|"
          "get|complete|narration-window|report-incomplete|resumed-from")
    return 2


def report_incomplete() -> int:
    """Past 09:00 with a night unfinished: the heartbeat and the mac-batch stop
    file say so (self-resolving - tonight's batch continues the same work)."""
    import common as C
    import mac_sync
    p = read()
    msg = (f"The Mac batch for the night of {p.get('night')} was interrupted at "
           f"{where(p)} (last unit {p.get('last_completed_at')}) and had not "
           f"resumed by {CUTOFF:02d}:00. Tonight's 23:00 batch continues it; "
           f"every step skips what is already on disk.")
    mac_sync.heartbeat("batch", False, incomplete_night={
        "night": p.get("night"), "stopped_at": where(p),
        "last_completed_at": p.get("last_completed_at")})
    try:
        with C.Stage("mac-batch") as st:
            st.named_stop("BATCH_NIGHT_INCOMPLETE", msg,
                          unblock="Nothing to do: tonight's batch resumes it. "
                                  "If it repeats, read "
                                  "~/Library/Logs/how-we-know/batch.log.")
    except SystemExit:
        pass
    print(f"  {msg}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
