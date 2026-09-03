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
       0  real work happened, OR a SELF-RESOLVING named stop (see below)
       1  genuine failure (a bug, a crash, a validator that found a defect)
       3  NAMED STOP that needs a human — surfaced as a failed job and an issue

4. **Not every named stop needs a human.** `loop/stop_policy.json` is the
   taxonomy. A stop whose code is listed there, which can say WHEN it resolves,
   and which has not repeated past its limit, is *self-resolving*: the banner,
   the stop record and the job summary are identical, but the process exits 0
   so a daily lane hitting a daily quota does not page the owner daily. Every
   other code — a missing credential, a failed validator, corrupt state, and
   ZERO_WORK — stays exit 3. The default is needs-a-human: a code nobody
   classified stays loud.
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
STOP_POLICY = LOOP / "stop_policy.json"
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


# ------------------------------------------------------------ stop taxonomy
#
# WHY THIS EXISTS. Run 33521586490 (2026-09-01, the daily cloud-upload lane)
# ended like this:
#
#   NAMED STOP  [QUOTA_EXHAUSTED]  stage=cloud-upload  week=2026-W36
#   unblock: Nothing to do; the allowance resets at midnight Pacific and this
#            lane runs daily.
#   ##[error]Process completed with exit code 3.
#
# The lane was right about everything except the exit code. It correctly found
# nothing it could do, correctly said so, and then failed the job and opened an
# issue about a condition that fixes itself in a few hours - and would have done
# so again every day. An alarm that fires daily for something nobody can act on
# is how people learn to ignore the alarm that matters.
#
# The fix is NOT "stops exit 0". It is a taxonomy with a needs-a-human default.


def stop_policy() -> dict:
    """The stop taxonomy, or an empty one (which means: everything is loud)."""
    return read_json(STOP_POLICY, default={"self_resolving": {}})


def _stops_dir() -> Path:
    """Where stop records and streaks live. Overridable so a test can watch
    real stages take real stops without writing into the loop's own state."""
    return Path(os.environ.get("LOOP_STOPS_DIR") or STOPS)


def _streaks_path() -> Path:
    return _stops_dir() / "_streaks.json"


def streak_bump(stage: str, code: str) -> int:
    """Count consecutive runs of `stage` that stopped for the same `code`.

    A self-resolving stop that never resolves is not self-resolving; it is an
    inert lane wearing a reassuring label. The streak is what turns the second
    kind back into the first: past the policy's `max_consecutive`, the same code
    escalates to a human. A different code, or any successful run, resets it.
    """
    d = read_json(_streaks_path(), default={})
    prev = d.get(stage) or {}
    count = (prev.get("count", 0) + 1) if prev.get("code") == code else 1
    d[stage] = {"code": code, "count": count,
                "first_at": prev.get("first_at") if count > 1 else now(),
                "last_at": now()}
    write_json(_streaks_path(), d)
    return count


def streak_clear(stage: str) -> None:
    d = read_json(_streaks_path(), default={})
    if d.pop(stage, None) is not None:
        write_json(_streaks_path(), d)


def disposition(stage: str, code: str, detail, streak: int) -> tuple[str, str]:
    """Classify one stop: ("self_resolving" | "needs_human", why).

    Data-driven, and fail-loud in all three directions:
      * a code the policy does not list           -> needs a human
      * a code that cannot say WHEN it resolves   -> needs a human
      * a code that has repeated past its limit   -> needs a human
    """
    rule = (stop_policy().get("self_resolving") or {}).get(code)
    if not rule:
        return ("needs_human",
                f"'{code}' is not in loop/stop_policy.json, so it is treated as "
                f"needing a human. That is the default on purpose.")
    missing = [k for k in rule.get("requires_detail", [])
               if not (isinstance(detail, dict) and detail.get(k))]
    if missing:
        return ("needs_human",
                f"'{code}' resolves itself only when it can say when — and this "
                f"one did not supply {', '.join(missing)} in its detail.")
    cap = int(rule.get("max_consecutive", 3))
    if streak > cap:
        return ("needs_human",
                f"'{code}' has now stopped {stage} on {streak} consecutive runs "
                f"(limit {cap}), so it is not resolving itself. "
                + str(rule.get("escalation", "")))
    return ("self_resolving",
            f"{rule.get('why', '')} (run {streak} of at most {cap} before this "
            f"escalates to a human.)")


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
            sys.exit(self._emit_stop(exc))
        if exc_type is not None:
            return False  # a real crash: let it surface as exit 1
        if not self.units:
            # ZERO_WORK is never self-resolving. Rule 0 is the one stop that
            # must always reach a person: a stage that quietly did nothing is
            # indistinguishable from a stage that is broken.
            sys.exit(self._emit_stop(NamedStop(
                "ZERO_WORK",
                f"stage '{self.name}' completed without doing anything",
                detail={"notes": self.notes},
                unblock=self.zero_work_hint or
                "Inspect the inputs this stage reads; it found none of them.",
            )))
        self._emit_ok()
        return False

    # -- output ------------------------------------------------------------
    def _emit_ok(self):
        self._clear_stop()
        streak_clear(self.name)
        print(f"--- {self.name}: OK, {len(self.units)} unit(s) of work",
              flush=True)
        lines = "\n".join(f"- {u}" for u in self.units)
        summary(f"### {self.name} — OK ({len(self.units)})\n{lines}\n")

    def _emit_stop(self, s: NamedStop) -> int:
        """Record, print and classify one named stop. Returns the exit code.

        SELF-RESOLVING stops exit 0. Everything else exits 3. The record, the
        banner and the job summary are identical either way — this decides who
        gets woken up, never whether the stop is visible.
        """
        streak = streak_bump(self.name, s.code)
        disp, why = disposition(self.name, s.code, s.detail, streak)
        rec = {
            "stage": self.name,
            "week": self.week,
            "at": now(),
            "code": s.code,
            "message": s.message,
            "detail": s.detail,
            "unblock": s.unblock,
            "disposition": disp,
            "disposition_why": why,
            "consecutive": streak,
            "exit_code": EXIT_OK if disp == "self_resolving" else EXIT_STOP,
            "work_done_before_stop": self.units,
            "notes": self.notes,
        }
        write_json(_stops_dir() / f"{self.week}-{self.name}.json", rec)
        verdict = ("SELF-RESOLVING — this run exits 0 and pages nobody"
                   if disp == "self_resolving" else
                   "NEEDS A HUMAN — this run exits 3 and opens an issue")
        banner = (
            "\n"
            "================================================================\n"
            f"  NAMED STOP  [{s.code}]  stage={self.name}  week={self.week}\n"
            f"  {s.message}\n"
            + (f"  unblock: {s.unblock}\n" if s.unblock else "")
            + f"  disposition: {verdict}\n"
            + f"  because: {why}\n"
            + "================================================================"
        )
        print(banner, flush=True)
        print(banner, file=sys.stderr, flush=True)
        summary(
            f"### 🛑 NAMED STOP — `{s.code}`\n"
            f"**stage** `{self.name}` · **week** `{self.week}` · "
            f"**{'self-resolving' if disp == 'self_resolving' else 'needs a human'}**"
            f"\n\n{s.message}\n\n"
            + (f"**To unblock:** {s.unblock}\n" if s.unblock else "")
            + f"\n_{why}_\n"
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
                fh.write(f"stop_disposition={disp}\n")
        return EXIT_OK if disp == "self_resolving" else EXIT_STOP

    def _clear_stop(self):
        f = _stops_dir() / f"{self.week}-{self.name}.json"
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
