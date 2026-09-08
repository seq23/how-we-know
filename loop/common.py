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

# Dispositions that do NOT fail the job. Named once: three places used to test
# `disp == "self_resolving"` and a fourth disposition would have failed jobs in
# whichever of them was missed.
GREEN_DISPOSITIONS = ("self_resolving", "owner_action")


# ---------------------------------------------------------------- primitives

def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def week_id(when: _dt.date | None = None) -> str:
    """ISO week label, e.g. 2026-W36. The loop's unit of accounting."""
    d = when or _dt.date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# A git conflict marker at the start of a line. loop/state/*.json is derived
# accounting that several cloud lanes rebase onto main within the same minute,
# so this is the realistic way one of them becomes unparseable -- write_json
# below is atomic (tmp + replace), so a half-written file is not.
CONFLICT_MARKER = ("<" * 7, "=" * 7, ">" * 7)


class CorruptState(Exception):
    """A state file exists but cannot be read as JSON.

    CONFIRMED 2026-09-03, run 33783829147: a rebase conflict on
    loop/state/quota.json left conflict markers in the working tree, and the
    NEXT step in the same job -- the localize lane, on unrelated work -- died
    at `json.loads(STATE.read_text())` with a bare JSONDecodeError reading
    "Expecting property name enclosed in double quotes: line 6 column 1". That
    traceback names neither the file nor the cause, and the video it failed to
    localize was then reported by V17 as a content gap.

    A corrupt state file is a real halt and deserves a real name. The module
    docstring above has always said corrupt state exits 3 as a named stop;
    this is what makes that true. Stage.__exit__ converts it.
    """

    def __init__(self, path, why: str):
        super().__init__(f"{path}: {why}")
        self.path = str(path)
        self.why = why


def restore_from_origin(path) -> str | None:
    """Put one tracked, DERIVED state file back the way origin/main has it.

    THE SELF-HEAL FOR CorruptState. The stop this replaces already knew the
    answer — its own unblock text was `git checkout origin/main -- <path>` —
    and it made a human type it. These files are derived accounting (the
    ledger, the quota, the streaks); the committed copy is authoritative and
    losing an unpushed local edit to a file that is a diff rather than JSON
    loses nothing that was readable anyway.

    Deliberately narrow, and it is the narrowness that makes it safe:
      * only paths under loop/state/, so a corrupt script or plan is untouched;
      * only files git already TRACKS, so a file that exists solely on this
        machine is never silently deleted;
      * `git fetch` first, so "origin/main" is not a stale ref;
      * and it VERIFIES the restored bytes parse as JSON before claiming to
        have healed anything. A restore that restores garbage is worse than
        the stop.

    Returns a note describing what it did, or None if it could not heal.
    """
    p = Path(path).resolve()
    try:
        rel = p.relative_to(ROOT)
    except ValueError:
        return None
    if not str(rel).startswith("loop/state/"):
        return None
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(rel)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        if tracked.returncode != 0:
            return None
        branch = os.environ.get("GITHUB_REF_NAME") or "main"
        subprocess.run(["git", "fetch", "--quiet", "origin", branch],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
        for ref in (f"origin/{branch}", "HEAD"):
            r = subprocess.run(["git", "checkout", ref, "--", str(rel)],
                               cwd=ROOT, capture_output=True, text=True,
                               timeout=60)
            if r.returncode != 0:
                continue
            try:
                json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue          # the committed copy is bad too: do not lie
            return f"restored {rel} from {ref}"
    except (subprocess.SubprocessError, OSError):
        return None
    return None


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is None:
            raise FileNotFoundError(p)
        return default
    text = p.read_text()
    why = None
    for line in text.splitlines():
        if line.startswith(CONFLICT_MARKER):
            why = ("it still contains git conflict markers. A lane rebased "
                   "onto a concurrent write and the conflict was never "
                   "resolved, so this file is a diff, not JSON")
            break
    if why is None:
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            why = f"it is not valid JSON ({e})"

    # HEAL BEFORE STOPPING. Every previous version of this raised immediately
    # and printed the one-line fix for a person to run; the file is derived and
    # committed, so the machine can run it. Only if the restore fails — or
    # restores something equally unreadable — is this still a named stop.
    healed = restore_from_origin(p)
    if healed:
        print(f"  [heal] {p.name} was unreadable ({why}); {healed}", flush=True)
        return json.loads(p.read_text())
    raise CorruptState(p, why)


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


# THE THIRD DISPOSITION, added 2026-09-08 on the owner's instruction: "I should
# never get a named stop -- everything should be automated. It should self heal."
#
# Taken literally that would mean deleting the taxonomy, and it must not: some
# halts are correct and some conditions genuinely cannot be healed by a machine
# (a revoked consent, a platform-side account flag). What she is actually
# describing is the failure mode where a CORRECT halt is delivered as a RED CI
# run in her inbox. Two answers, and they are different:
#
#   self_resolving  nobody need do anything. Green, silent, capped.
#   owner_action    only she can clear it, and no amount of retrying will.
#                   ALSO GREEN -- a red run every day for a thing she will fix
#                   when she next sits down is the worst of both -- but it is
#                   written into loop/state/owner_action.json and printed at the
#                   TOP of the Sunday digest, so the fact reaches her as
#                   information rather than as a failed build.
#   needs_human     a defect. Red, as before, and still the default.
#
# The escalation cap is what keeps owner_action honest: an external block that
# is still there after `max_consecutive` runs is no longer "she will get to it",
# it is a stall, and it goes red.
def _owner_action_path() -> Path:
    """Where the owner-action record lives.

    Inside `_stops_dir()` deliberately, so `LOOP_STOPS_DIR` redirects it the
    same way it redirects stop records. The test suite runs real stages that
    take real stops; without this, a local `run_all.py` would write a live
    "waiting on you" row into the committed state and it would appear at the
    top of her next digest. That exact class of leak already cost a day once,
    through _streaks.json.
    """
    return _stops_dir() / "owner_action.json"


def _match_rule(section, code: str):
    """One section's rule for `code`, exact first, then a `PREFIX*` wildcard.

    Wildcards exist for the two code FAMILIES the loop generates rather than
    writes: `LANE_NOT_ARMED_<LANE>` from loop/arming.py and
    `ANALYTICS_HTTP_<status>` from loop/measure.py. Without them a new lane or
    a new HTTP status would silently take the needs-a-human default and page
    her — the failure this taxonomy exists to prevent, arriving through the one
    door the taxonomy could not name in advance. Exact keys always win, so
    `ANALYTICS_HTTP_5*` can be transient while `ANALYTICS_HTTP_403` is not.
    """
    if not section:
        return None
    if code in section:
        return section[code]
    best = None
    for key, rule in section.items():
        if key.endswith("*") and code.startswith(key[:-1]):
            if best is None or len(key) > len(best[0]):
                best = (key, rule)
    return best[1] if best else None


def disposition(stage: str, code: str, detail, streak: int) -> tuple[str, str]:
    """Classify one stop: ("self_resolving"|"owner_action"|"needs_human", why).

    Data-driven, and fail-loud in all three directions:
      * a code the policy does not list           -> needs a human
      * a code that cannot say WHEN it resolves   -> needs a human
      * a code that has repeated past its limit   -> needs a human
    """
    policy = stop_policy()
    kind, rule = "self_resolving", _match_rule(policy.get("self_resolving"), code)
    if not rule:
        kind, rule = "owner_action", _match_rule(policy.get("owner_action"), code)
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
    if kind == "owner_action":
        return ("owner_action",
                f"{rule.get('why', '')} Only she can clear this, and retrying "
                f"cannot, so the run stays GREEN and the fact is carried to the "
                f"top of the Sunday digest instead of into her inbox as a failed "
                f"build. (run {streak} of at most {cap} before this escalates.)")
    return ("self_resolving",
            f"{rule.get('why', '')} (run {streak} of at most {cap} before this "
            f"escalates to a human.)")


def owner_action_record(rec: dict) -> None:
    """Persist one owner_action stop so something other than a job log carries it.

    Keyed by stage, because a stage has at most one live blocking condition and
    the newest is the true one. Committed by bin/loop-stage.sh with the rest of
    loop/, so the digest reads it from the repository rather than from a runner
    that no longer exists.
    """
    p = _owner_action_path()
    d = read_json(p, default={})
    d[rec["stage"]] = {k: rec.get(k) for k in
                       ("code", "message", "unblock", "at", "week",
                        "consecutive")}
    write_json(p, d)


def owner_action_clear(stage: str) -> None:
    """The stage worked. Whatever was blocking it is gone; stop reporting it."""
    p = _owner_action_path()
    d = read_json(p, default={})
    if d.pop(stage, None) is not None:
        write_json(p, d)


def owner_actions() -> dict:
    """Everything currently waiting on the owner. Read by loop/digest.py."""
    return read_json(_owner_action_path(), default={})


# ---------------------------------------------------------------- the stage


def _same_stream(a, b) -> bool:
    """True when stdout and stderr land in the SAME place for a reader.

    Two cases, not one:

    * the Mac cron wrapper redirects with `2>&1`, so the two descriptors are
      literally the same open file and `st_dev`/`st_ino` match;
    * GitHub Actions gives a step SEPARATE pipes that it then merges into one
      log. The inodes differ, so the check above said "not the same" and every
      NAMED STOP banner was printed twice - confirmed in run 34035963724, where
      the two copies interleave line by line, which is what two writers to one
      log looks like. Alarm noise on the one message that has to stay readable.

    There is no third stream to preserve on Actions: the job log IS the error
    pane, so writing once is not hiding anything.
    """
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    try:
        sa, sb = os.fstat(a.fileno()), os.fstat(b.fileno())
        return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)
    except Exception:                       # noqa: BLE001 - never break a stop
        return False

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
        if exc_type is CorruptState:
            # NOT a crash, and above all not this lane's fault: some other
            # lane left a state file unreadable and this one is the next to
            # touch it. Name the file, because "JSONDecodeError line 6" sends
            # a human to read a traceback and this sends them to `git
            # checkout` one path.
            sys.exit(self._emit_stop(NamedStop(
                "STATE_FILE_CORRUPT",
                f"{exc.path} could not be read: {exc.why}. This stage did "
                f"nothing; it refuses to spend quota or write YouTube "
                f"metadata while the accounting it depends on is unreadable.",
                detail={"path": exc.path},
                unblock=f"Restore the file from the last good commit: "
                        f"git checkout origin/main -- {exc.path} — then "
                        f"re-run this lane. Nothing is lost; these files are "
                        f"derived.")))
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
        owner_action_clear(self.name)
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
            "exit_code": EXIT_OK if disp in GREEN_DISPOSITIONS else EXIT_STOP,
            "work_done_before_stop": self.units,
            "notes": self.notes,
        }
        write_json(_stops_dir() / f"{self.week}-{self.name}.json", rec)
        if disp == "owner_action":
            owner_action_record(rec)
        else:
            owner_action_clear(self.name)
        verdict = {
            "self_resolving":
                "SELF-RESOLVING — this run exits 0 and pages nobody",
            "owner_action":
                "WAITING ON THE OWNER — this run exits 0 and does NOT page "
                "her; it is recorded in loop/state/owner_action.json and "
                "appears at the top of the Sunday digest",
        }.get(disp, "NEEDS A HUMAN — this run exits 3 and opens an issue")
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
        # Both streams, so the stop is visible whether a reader is watching
        # stdout or only the error pane. But the cron wrapper captures with
        # `2>&1`, which merges them and printed every banner TWICE - alarm noise
        # on the one message that has to stay readable. If the two descriptors
        # are literally the same file, write once.
        print(banner, flush=True)
        if not _same_stream(sys.stdout, sys.stderr):
            print(banner, file=sys.stderr, flush=True)
        label = {"self_resolving": "self-resolving",
                 "owner_action": "waiting on the owner (green)"}.get(
                     disp, "needs a human")
        summary(
            f"### 🛑 NAMED STOP — `{s.code}`\n"
            f"**stage** `{self.name}` · **week** `{self.week}` · "
            f"**{label}**"
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
        return EXIT_OK if disp in GREEN_DISPOSITIONS else EXIT_STOP

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
