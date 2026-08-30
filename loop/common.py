"""Shared spine for every loop stage.

Three ideas live here and nothing else should re-implement them.

1. **Rule 0.** A stage may not exit 0 having done nothing. `Stage` counts the
   real units of work a stage performed and, if that count is zero at exit,
   converts the run into a NAMED STOP rather than a silent green tick.

2. **A NAMED STOP is a human-visible outcome, not a skip.** It writes a record
   under `loop/state/stops/`, prints a banner, appends to the Actions job
   summary, and exits 3. The calling workflow turns exit 3 into a GitHub issue
   and a failed job, because a failed job is the one thing that reaches the
   owner's inbox for $0.

3. **Exit codes are the contract.**
       0  real work happened
       1  genuine failure (a bug, a crash, a validator that found a defect)
       3  NAMED STOP  — legitimate, named, and surfaced to a human
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOOP = ROOT / "loop"
STATE = LOOP / "state"
STOPS = STATE / "stops"
APPROVALS = STATE / "approvals"
RECEIPTS = LOOP / "receipts"
BRIEFS = LOOP / "briefs"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_STOP = 3


# ---------------------------------------------------------------- primitives

def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def week_id(when: _dt.date | None = None) -> str:
    """ISO week label, e.g. 2026-W36. The loop's unit of accounting."""
    d = when or _dt.date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is None:
            raise FileNotFoundError(p)
        return default
    with p.open() as fh:
        return json.load(fh)


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=False)
        fh.write("\n")
    tmp.replace(p)
    return p


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def config() -> dict:
    return read_json(LOOP / "config.json")


def summary(text: str) -> None:
    """Append to the Actions job summary when running in CI; harmless locally."""
    dest = os.environ.get("GITHUB_STEP_SUMMARY")
    if dest:
        with open(dest, "a") as fh:
            fh.write(text.rstrip() + "\n")


# ---------------------------------------------------------------- named stop

class NamedStop(Exception):
    """A legitimate, named reason a stage produced nothing.

    Raising this is always better than returning quietly. Never catch it to
    make a workflow green.
    """

    def __init__(self, code: str, message: str, detail=None, unblock: str = ""):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail
        self.unblock = unblock


# ---------------------------------------------------------------- the stage

class Stage:
    """Context manager wrapping one loop stage.

        with Stage("mon-draft") as st:
            ...
            st.work("queued 01-why-deep-sea-creatures-look-so-weird")

    Exiting with `st.units == 0` is Rule 0's tripwire: the stage is rewritten
    into a ZERO_WORK named stop, so an empty loop can never pass as success.
    """

    def __init__(self, name: str, week: str | None = None,
                 zero_work_hint: str = ""):
        self.name = name
        self.week = week or week_id()
        self.units: list[str] = []
        self.notes: list[str] = []
        self.zero_work_hint = zero_work_hint
        self.stop: NamedStop | None = None

    # -- recording ---------------------------------------------------------
    def work(self, what: str) -> None:
        """Record one real unit of work. Only call this after it happened."""
        self.units.append(what)
        print(f"  [work] {what}", flush=True)

    def note(self, what: str) -> None:
        self.notes.append(what)
        print(f"  [note] {what}", flush=True)

    def named_stop(self, code, message, detail=None, unblock="") -> None:
        raise NamedStop(code, message, detail, unblock)

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self):
        print(f"=== loop stage: {self.name}  week {self.week}  {now()} ===",
              flush=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is NamedStop:
            self._emit_stop(exc)
            sys.exit(EXIT_STOP)
        if exc_type is not None:
            return False  # a real crash: let it surface as exit 1
        if not self.units:
            self._emit_stop(NamedStop(
                "ZERO_WORK",
                f"stage '{self.name}' completed without doing anything",
                detail={"notes": self.notes},
                unblock=self.zero_work_hint or
                "Inspect the inputs this stage reads; it found none of them.",
            ))
            sys.exit(EXIT_STOP)
        self._emit_ok()
        return False

    # -- output ------------------------------------------------------------
    def _emit_ok(self):
        self._clear_stop()
        print(f"--- {self.name}: OK, {len(self.units)} unit(s) of work",
              flush=True)
        lines = "\n".join(f"- {u}" for u in self.units)
        summary(f"### {self.name} — OK ({len(self.units)})\n{lines}\n")

    def _emit_stop(self, s: NamedStop):
        rec = {
            "stage": self.name,
            "week": self.week,
            "at": now(),
            "code": s.code,
            "message": s.message,
            "detail": s.detail,
            "unblock": s.unblock,
            "work_done_before_stop": self.units,
            "notes": self.notes,
        }
        write_json(STOPS / f"{self.week}-{self.name}.json", rec)
        banner = (
            "\n"
            "================================================================\n"
            f"  NAMED STOP  [{s.code}]  stage={self.name}  week={self.week}\n"
            f"  {s.message}\n"
            + (f"  unblock: {s.unblock}\n" if s.unblock else "")
            + "================================================================"
        )
        print(banner, flush=True)
        print(banner, file=sys.stderr, flush=True)
        summary(
            f"### 🛑 NAMED STOP — `{s.code}`\n"
            f"**stage** `{self.name}` · **week** `{self.week}`\n\n"
            f"{s.message}\n\n"
            + (f"**To unblock:** {s.unblock}\n" if s.unblock else "")
            + (f"\nWork completed before the stop: {len(self.units)}\n"
               if self.units else "")
        )
        # Machine-readable handle for the workflow that raises the issue.
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"stop_code={s.code}\n")
                fh.write(f"stop_stage={self.name}\n")
                fh.write(f"stop_week={self.week}\n")
                fh.write(f"stop_message={s.message}\n")

    def _clear_stop(self):
        f = STOPS / f"{self.week}-{self.name}.json"
        if f.exists():
            f.unlink()


# ---------------------------------------------------------------- git helper

def git(*args, check=True, cwd=ROOT):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout.strip()


def slugify(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    s = "".join(keep)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")
