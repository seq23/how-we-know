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
       0  real work happened, OR a SELF-RESOLVING named stop, OR a HELD one
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

5. **Not every stop that needs a human needs her TWICE.** Some halts only a
   person can clear — an episode whose caption file can only be made on her
   Mac. Those are correctly exit 3 the first time and correctly NOT exit 3 the
   fifth morning in a row, on an unchanged fact, in an issue that is already
   open. A stop that names exactly what it waits on (`held_items=`) and how to
   clear it (`unblock=`) becomes *held* once it has been reported: exit 0, and
   a HELD STOP banner naming what is held, since when and which issue tracks
   it. It goes loud again the instant the list grows, if the issue is closed,
   or after the policy's reminder window. See `loop/held.py`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Every loop entrypoint already runs with loop/ on sys.path, so the plain
# import is the normal path. The fallback is for an importer that reached
# common.py some other way: a bare ImportError here would turn the stop
# machinery itself into a crash, which is the one failure mode this file
# exists to prevent.
try:
    import held
except ImportError:                                        # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import held

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

# How each disposition heads its Actions job summary. Named once: three of them
# now exit 0, and a reader who sees "NAMED STOP" over a green job learns to
# distrust the banner rather than the state.
_SUMMARY_HEAD = {"self_resolving": "🛑 NAMED STOP",
                 "held": "⏸️ HELD STOP",
                 "owner_action": "🔑 NEEDS YOUR KEY OR ACCOUNT"}

# Dispositions that do NOT fail the job. Named once: three places used to test
# `disp == "self_resolving"` and a fourth disposition would have failed jobs in
# whichever of them was missed.
GREEN_DISPOSITIONS = ("self_resolving", "held", "owner_action")


def label_of(disp: str) -> str:
    return {"self_resolving": "self-resolving",
            "held": "held, already reported",
            "owner_action": "needs a secret only she holds"}.get(disp, "needs a human")


def annotation(level: str, title: str, message: str) -> str:
    """One GitHub Actions workflow command (`::warning title=...::...`).

    Escaped per the workflow-command spec so a message with a newline, a
    colon or a comma cannot end the command early and drop the rest."""
    def esc(v: str, prop: bool = False) -> str:
        v = v.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        if prop:
            v = v.replace(":", "%3A").replace(",", "%2C")
        return v
    return f"::{level} title={esc(title, True)}::{esc(message)}"


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


def _dry_run_refuses(p: Path) -> bool:
    """LOOP_DRY_RUN=1 writes nothing into the committed loop/state/.

    WHY. The flag already meant "no writes": no upload, no R2 put, no
    credential. It did not cover the lane's own state files. The test suite
    runs real lanes under it (test_named_stops.py, test_reach.py), and each
    run rewrote the committed loop/state/measurement.json and
    captions_manifest.json with a test run's view of the channel. A later
    loop-stage commit would have shipped that as real state.

    Stop records are the one exception. They live under _stops_dir(), which
    LOOP_STOPS_DIR already points at a scratch directory, and a named stop
    has to be recorded even in a dry run."""
    if os.environ.get("LOOP_DRY_RUN") != "1":
        return False
    try:
        rp = p.resolve()
        rp.relative_to(STATE.resolve())
    except ValueError:
        return False
    try:
        rp.relative_to(_stops_dir().resolve())
        return False
    except ValueError:
        return True


def write_json(path, obj):
    p = Path(path)
    if _dry_run_refuses(p):
        print(f"  [dry-run] not writing {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}"
              f" (LOOP_DRY_RUN=1 never touches committed loop/state/)",
              file=sys.stderr)
        return p
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

    `held_items` is how a stop that only a HUMAN can clear earns the right to
    stop paging her daily once she has been told. It is a list of stable
    identifiers — slugs, video ids, paths — naming exactly what the stop is
    waiting on. Supplying it is what makes "already reported, unchanged" a
    decidable question; a stop that does not supply it stays loud on every
    run. See loop/held.py for the whole rule.
    """

    def __init__(self, code: str, message: str, detail=None, unblock: str = "",
                 held_items=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail
        self.unblock = unblock
        self.held_items = list(held_items) if held_items else []


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
    "needs your key or account" row into the committed state and it would appear at the
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


# BOTH ANSWERS TO "DO NOT PAGE HER AGAIN", AND THEY ARE NOT THE SAME ANSWER.
#
# `held` (loop/held.py, landed on main the same day) is the GENERIC one: any
# stop in any lane earns it by naming exactly what it waits on and how to clear
# it, and it pages ONCE and then stays quiet until the hold grows or goes
# stale. `owner_action` is the CLASSIFIED one: a short list of codes that only
# she can clear -- a revoked consent, a locked channel, an unfunded key -- which
# never page at all, because a red build tells her nothing she cannot read in
# Sunday's digest and she cannot act on it any faster for having been woken.
#
# They compose rather than compete. owner_action is consulted first for the
# sixteen codes it names; every other human-clearable stop falls through to the
# hold, which is open to all of them. Nothing is classified in both.
def disposition(stage: str, code: str, detail, streak: int,
                held_items=None, unblock: str = "") -> tuple[str, str]:
    """Classify one stop: ("self_resolving" | "held" | "needs_human", why).

    Data-driven, and fail-loud in every direction:
      * a code the policy does not list           -> needs a human, UNLESS it
                                                     is an already-reported,
                                                     unchanged HOLD
      * a code that cannot say WHEN it resolves   -> needs a human
      * a code that has repeated past its limit   -> needs a human
      * a hold that is new, has grown, has lost   -> needs a human
        its issue, or is past its reminder

    ORDER MATTERS. `self_resolving` is checked first because time fixing a
    thing beats a person fixing it; `held` is only ever reached by a stop that
    would otherwise have paged.
    """
    policy = stop_policy()
    kind, rule = "self_resolving", _match_rule(policy.get("self_resolving"), code)
    if not rule:
        kind, rule = "owner_action", _match_rule(policy.get("owner_action"), code)
    if not rule:
        # THE HOLD. Not an exemption for this code — an offer open to every
        # code in every lane, on one condition: the stop must name exactly
        # what it waits on and how to clear it. See loop/held.py.
        verdict, why, entry = held.classify(
            _stops_dir(), policy, stage, code, held_items, unblock)
        held.record(_stops_dir(), entry)
        if verdict == "held":
            return ("held", why)
        return ("needs_human",
                f"'{code}' is not in loop/stop_policy.json, so it is treated as "
                f"needing a human. That is the default on purpose. " + why)
    missing = [k for k in rule.get("requires_detail", [])
               if not (isinstance(detail, dict) and detail.get(k))]
    if missing:
        return ("needs_human",
                f"'{code}' resolves itself only when it can say when — and this "
                f"one did not supply {', '.join(missing)} in its detail.")
    cap = int(rule.get("max_consecutive", 3))
    if streak > cap:
        upstream = _upstream_explains(stage, rule, detail, streak)
        if upstream:
            return ("self_resolving", upstream)
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


# AN IDLE LANE DOWNSTREAM OF AN IDLE LANE IS NOT A SECOND FAULT (2026-09-26).
#
# Run 36152459224 paged: LOCALIZATIONS_UP_TO_DATE on 9 consecutive days, over
# its cap of 8, whose escalation reads "an eight-day streak means either
# publishing has stopped or this lane can no longer SEE new videos". Neither
# was a finding. The ledger had not grown since 2026-09-15 because the upload
# lane had nothing to upload - and that lane had been saying so every day in
# its own classified stops (NOTHING_SHELVED, which paged on its own cap on
# 09-22, then SCRIPTS_AWAITING_PROMOTION). The localize lane's day counter was
# a second clock on the upload lane's condition, keyed to a cadence it cannot
# see (episodes are uploaded in batches ahead of their air dates, so a week
# with no upload is normal while the runway lasts). Two components each
# keeping their own count of one fact; the one that cannot see the reason
# paged.
#
# A rule may therefore name its `upstream_stage`: the lane whose output is
# this lane's only input. Past its cap such a stop stays green ONLY while
# ALL of these hold, each read from committed state, never assumed:
#   * the stop's detail carries `newest_input_at` - the newest input it could
#     see (a stop that cannot say is escalated, as before);
#   * that input is OLDER than this streak's first idle run: nothing new has
#     arrived since the lane last had work. If something HAD arrived and the
#     lane still found nothing to do, that is the blind-lane case the cap
#     exists for, and it pages;
#   * the upstream stage is itself mid-streak on a named stop right now, so
#     its own classified stop, with its own cap, is what reports the idle.
#     An upstream whose last run succeeded (no streak) yet delivered nothing
#     here is unexplained, and pages;
#   * the streak is inside `max_consecutive_upstream_idle`, an outer bound so
#     that an upstream flipping between codes can never keep this quiet
#     forever.
def _upstream_explains(stage: str, rule: dict, detail, streak: int):
    up = rule.get("upstream_stage")
    if not up:
        return None
    outer = int(rule.get("max_consecutive_upstream_idle", 0))
    if streak > outer:
        return None
    newest = detail.get("newest_input_at") if isinstance(detail, dict) else None
    streaks = read_json(_streaks_path(), default={})
    began = (streaks.get(stage) or {}).get("first_at")
    up_rec = streaks.get(up) or {}
    if not newest or not began or not up_rec.get("code"):
        return None
    try:
        from datetime import datetime as _dt                # noqa: PLC0415
        arrived_since = (_dt.fromisoformat(str(newest).replace("Z", "+00:00"))
                         >= _dt.fromisoformat(str(began).replace("Z", "+00:00")))
    except ValueError:
        return None                     # an unreadable time explains nothing
    if arrived_since:
        return None
    return (f"{stage} has had nothing to do on {streak} consecutive runs "
            f"(past its own limit of {rule.get('max_consecutive')}), and "
            f"that is explained upstream, not here: its newest input is "
            f"from {newest}, before this idle streak began ({began}), and "
            f"{up} is itself stopped on {up_rec['code']} "
            f"({up_rec.get('count')} consecutive run(s) since "
            f"{up_rec.get('first_at')}). That lane's own classified stop "
            f"and cap report the idle. This stays green for at most "
            f"{outer} consecutive runs.")


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

    def named_stop(self, code, message, detail=None, unblock="",
                   held_items=None) -> None:
        raise NamedStop(code, message, detail, unblock, held_items)

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
        # A stage that did real work is holding on nothing. Dropping its rows
        # is what makes a RECURRENCE loud: the next time this stage holds, it
        # has never been reported, so it pages. Symmetrical with the streak.
        held.clear(_stops_dir(), self.name)
        print(f"--- {self.name}: OK, {len(self.units)} unit(s) of work",
              flush=True)
        lines = "\n".join(f"- {u}" for u in self.units)
        summary(f"### {self.name} — OK ({len(self.units)})\n{lines}\n")

    def _emit_stop(self, s: NamedStop) -> int:
        """Record, print and classify one named stop. Returns the exit code.

        SELF-RESOLVING and HELD stops exit 0. Everything else exits 3. The
        record, the banner and the job summary are identical either way — this
        decides who gets woken up, never whether the stop is visible.
        """
        streak = streak_bump(self.name, s.code)
        disp, why = disposition(self.name, s.code, s.detail, streak,
                                held_items=s.held_items, unblock=s.unblock)
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
            "held_items": sorted(s.held_items),
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
            "self_resolving": "SELF-RESOLVING — this run exits 0 and pages nobody",
            "held": "HELD — already reported and unchanged, so this run exits 0 "
                    "and pages nobody. It is NOT resolved.",
            "owner_action":
                "NEEDS A SECRET ONLY SHE HOLDS — this run exits 0 and does NOT page her; "
                "it is recorded in the owner-action file and appears at the TOP "
                "of the Sunday digest. It is NOT resolved.",
        }.get(disp, "NEEDS A HUMAN — this run exits 3 and opens an issue")
        # A HELD stop is exit 0, so the banner is the ONLY thing standing
        # between it and a silent skip. It says HELD STOP, not NAMED STOP, so
        # nobody reading a log can mistake "she has been told" for "it is
        # fixed", and it lists every item it is waiting on by name.
        # `held` renames the banner because "NAMED STOP" over a green job
        # reads as a contradiction. `owner_action` does NOT: it is still a
        # named stop in every sense, it simply never pages, and two test
        # suites plus every runbook grep for that exact token. The verdict and
        # label lines below carry the difference.
        head = "HELD STOP " if disp == "held" else "NAMED STOP"
        holding = ""
        if disp == "held" and s.held_items:
            hold_rec = held.open_holds(_stops_dir()).get(
                held.key(self.name, s.code)) or {}
            since = hold_rec.get("first_reported_at")
            age = held.days_since(since)
            holding = (
                f"  HELD SINCE {since}"
                + (f" ({age:.1f} day(s))\n" if age is not None else "\n")
                + (f"  TRACKED BY issue #{hold_rec['issue']}\n"
                   if hold_rec.get("issue") else "")
                + f"  WAITING ON {len(s.held_items)} item(s):\n"
                + "".join(f"    - {i}\n" for i in sorted(s.held_items)))
        banner = (
            "\n"
            "================================================================\n"
            f"  {head}  [{s.code}]  stage={self.name}  week={self.week}\n"
            f"  {s.message}\n"
            + holding
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
        # A GREEN named stop is still a named stop: in Actions it carries a
        # warning annotation on the run page, with the unblock text (which
        # names the file to read), so "green" never reads as "nothing here".
        # Red stops keep exit 3 and the issue; they need no annotation.
        if disp in GREEN_DISPOSITIONS:
            print(annotation("warning", f"{s.code} ({label_of(disp)})",
                             s.message + (f" -- {s.unblock}" if s.unblock
                                          else "")), flush=True)
        label = {"self_resolving": "self-resolving",
                 "held": "HELD — already reported, unchanged",
                 "owner_action": "needs a secret only she holds (green, never paged)"
                 }.get(
                     disp, "needs a human")
        summary(
            f"### {_SUMMARY_HEAD.get(disp, '🛑 NAMED STOP')} — "
            f"`{s.code}`\n"
            f"**stage** `{self.name}` · **week** `{self.week}` · "
            f"**{label}**"
            f"\n\n{s.message}\n\n"
            + (("**Waiting on:**\n"
                + "".join(f"- `{i}`\n" for i in sorted(s.held_items))
                + "\n") if disp == "held" and s.held_items else "")
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
                # Heredoc form: a message with a newline in it (FORMAT_PROBLEM
                # wraps its figures) is otherwise an "Invalid format" that
                # fails the whole step - a GREEN stop turned red by its own
                # hand-off (PR #128's CI, 2026-09-25).
                delim = f"STOP_MESSAGE_{os.getpid()}_EOF"
                fh.write(f"stop_message<<{delim}\n{s.message}\n{delim}\n")
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
