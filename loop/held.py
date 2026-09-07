"""A halt that only a human can clear must page her ONCE, not every day.

WHY THIS EXISTS
---------------
`loop/stop_policy.json` already separates a stop that fixes ITSELF (the quota
resets at midnight, so exit 0) from one that needs a person (exit 3, a failed
job, an issue). That taxonomy has a hole, and the hole is the whole of the
owner's daily red mail.

On 2026-09-07 the 09:00 lane took `NAMED STOP [CAPTIONS_NOT_READY]`: two
episodes had no `captions/<slug>.srt`, so it refused to schedule a video it
could never caption. That refusal is CORRECT and it is not self-resolving — the
`.srt` is derived from narration audio that exists only on the owner's Mac, so
nothing in the cloud can ever produce it. Exit 3, red job, issue opened. Right.

And then it did exactly the same thing on the next run. And it would have done
it every day until she got to her Mac, on a fact she already knew, in an issue
that was already open, with nothing new in it. That is the SAME defect run
33521586490 taught this repo — an alarm that fires daily for something the
reader cannot act on today is how the alarm that matters gets ignored — wearing
a different hat: not "nobody needs to act" but "the person who must act has
already been told".

So there are three dispositions, not two:

    self_resolving  time fixes it.               exit 0, quiet, banner.
    held            a HUMAN fixes it, and she    exit 0, LOUD banner naming
                    has already been told.       what is held, since when,
                                                 and which issue tracks it.
    needs_human     everything else.             exit 3, red job, issue.

WHAT MAKES THIS GENERIC, AND NOT ANOTHER PER-CODE EXEMPTION
-----------------------------------------------------------
This repo has been bitten four times in eight days by fixes shaped as "and
also exempt V13, V14, V15" — each one correct for those names and useless for
the next validator that hit the same wall. So `held` is NOT a list of codes.
It is a property of the stop itself, and any stop in any lane earns it by
having that property:

    A stop may be held only if it can NAME EXACTLY WHAT IT IS WAITING ON
    and SAY HOW TO CLEAR IT.

    st.named_stop(CODE, message, unblock="...", held_items=[...])

`held_items` is a list of stable identifiers — slugs, video ids, file paths.
That list is the identity of the hold, and it is what makes "already reported"
a decidable question rather than a vibe. A stop with no `held_items`, or with
no `unblock` text, is never held: it stays exit 3. Forgetting to name your
items leaves you LOUD, which is the same direction the default in
stop_policy.json already fails in.

WHEN A HELD STOP GOES LOUD AGAIN
--------------------------------
Silence is bounded in four independent ways, because a hold that can never be
heard from again is just Rule 0's "runs but inert" with a friendlier banner:

  1. THE FIRST TIME. There is no ledger entry, so it pages. Always.
  2. GROWTH. Any identifier not in the reported set is a new problem, so the
     whole stop pages again with the new items named. Six uncaptioned episodes
     is not the same news as two.
  3. THE ISSUE CLOSED. Closing the stop issue is the owner saying "handled".
     If the condition is still there on the next run, that is worth knowing,
     so it pages. (Best effort: checked through `gh` when it is available, and
     the hold is trusted when it is not — see `_issue_is_open`.)
  4. THE CLOCK. A hold re-reports every `reminder_days` (default 7) no matter
     what. A stop that has been held for a fortnight is a fact about the
     channel, not a fact about today's run.

Nothing here is ever silent: a held run prints the full HELD STOP banner to
the log and the job summary. It exits 0. That is the only difference.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
from pathlib import Path

# Imported lazily by loop/common.py; keep this module free of loop imports so
# it can be exercised on its own.

DEFAULT_REMINDER_DAYS = 7


# --------------------------------------------------------------- the ledger

def ledger_path(stops_dir) -> Path:
    """Where the record of what has already been reported lives.

    Beside the stop records, so `bin/loop-stage.sh`'s `git add loop` commits it
    with everything else and tomorrow's runner — a fresh checkout with no
    memory — can read what yesterday's already said.
    """
    return Path(stops_dir) / "_held.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except ValueError:
        # A corrupt ledger must not silence a stop. Losing the record means
        # every hold reads as NEW, which pages — the safe direction.
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def key(stage: str, code: str) -> str:
    return f"{stage}::{code}"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _parse(stamp: str | None) -> _dt.datetime | None:
    if not stamp:
        return None
    try:
        when = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=_dt.timezone.utc)


def days_since(stamp: str | None) -> float | None:
    when = _parse(stamp)
    if when is None:
        return None
    return round((_now() - when).total_seconds() / 86400, 1)


# ------------------------------------------------------------ the issue check

def _issue_is_open(number, repo: str | None = None) -> bool:
    """Best effort: is the issue that tracks this hold still open?

    TRUSTS THE HOLD WHEN IT CANNOT TELL. `gh` exists on an Actions runner and
    generally not on the Mac's cron, and a network blip is not news. Returning
    False on "I could not check" would page the owner daily for the exact
    reason this module exists, so an unanswerable question leaves the hold
    intact and the banner says the issue state was not verified.
    """
    if not number:
        return False
    argv = ["gh", "issue", "view", str(number), "--json", "state",
            "--jq", ".state"]
    if repo:
        argv += ["--repo", repo]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except Exception:                       # noqa: BLE001 - never break a stop
        return True
    if r.returncode != 0:
        return True
    return r.stdout.strip().upper() != "CLOSED"


# ------------------------------------------------------------- the decision

def reminder_days(policy: dict, code: str) -> int:
    held = (policy or {}).get("held") or {}
    per_code = (held.get("codes") or {}).get(code) or {}
    try:
        return int(per_code.get("reminder_days",
                                held.get("reminder_days",
                                         DEFAULT_REMINDER_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_REMINDER_DAYS


def classify(stops_dir, policy: dict, stage: str, code: str,
             held_items, unblock: str) -> tuple[str, str, dict]:
    """Decide whether this stop is HELD (exit 0) or must page (exit 3).

    Returns ("held" | "page", why, entry). `entry` is the ledger row as it
    should be after this run — the caller persists it with `record()` so that
    the record of "she has been told" is written by exactly one place.
    """
    items = sorted({str(i) for i in (held_items or [])})
    entry = dict(_read(ledger_path(stops_dir)).get(key(stage, code)) or {})
    stamp = _now().isoformat(timespec="seconds")

    base = {
        "stage": stage,
        "code": code,
        "items": items,
        "first_reported_at": entry.get("first_reported_at") or stamp,
        "last_seen_at": stamp,
        "issue": entry.get("issue"),
        "reported_run": entry.get("reported_run"),
        "last_reported_at": entry.get("last_reported_at"),
        "reports": int(entry.get("reports") or 0),
    }

    def page(why: str) -> tuple[str, str, dict]:
        # A stop that pages RESETS the clock and adopts the current item set,
        # so the next run compares against what was actually reported.
        row = dict(base)
        row["last_reported_at"] = stamp
        row["reports"] = base["reports"] + 1
        if not entry:
            row["first_reported_at"] = stamp
        return ("page", why, row)

    if not items:
        return page(
            f"'{code}' did not name what it is waiting on (no held_items), so "
            f"this run cannot tell a repeat from a new problem. A stop that "
            f"cannot be identified is never held.")
    if not (unblock or "").strip():
        return page(
            f"'{code}' named {len(items)} item(s) but no way to clear them. A "
            f"held stop exits 0, so its unblock text is the only instruction "
            f"the owner gets — without it the hold would be silent.")
    if not entry:
        return page(
            f"'{code}' is holding on {len(items)} item(s) that have never been "
            f"reported. The first report is always loud.")

    fresh = [i for i in items if i not in set(entry.get("items") or [])]
    if fresh:
        return page(
            f"'{code}' is now holding on {len(fresh)} item(s) nobody has been "
            f"told about ({', '.join(fresh[:6])}"
            f"{'…' if len(fresh) > 6 else ''}). A hold that grows is new news.")

    issue = entry.get("issue")
    if not issue:
        return page(
            f"'{code}' was reported on "
            f"{entry.get('last_reported_at') or entry.get('first_reported_at')}"
            f" but no issue number was ever recorded against it, so this run "
            f"cannot tell the owner where it is tracked. Reporting again is "
            f"the only honest option.")
    if not _issue_is_open(issue, os.environ.get("GITHUB_REPOSITORY")):
        return page(
            f"issue #{issue} tracked this hold and has been CLOSED, but "
            f"'{code}' is still holding on {len(items)} item(s). A closed "
            f"issue means handled; this is not handled.")

    cap = reminder_days(policy, code)
    since_report = days_since(entry.get("last_reported_at")
                              or entry.get("first_reported_at"))
    if since_report is not None and since_report >= cap:
        return page(
            f"'{code}' has been held for {since_report:.1f} day(s) without "
            f"changing, past the {cap}-day reminder. Silence is bounded: a "
            f"hold this old is reported again so it cannot be forgotten.")

    held_for = days_since(entry.get("first_reported_at"))
    row = dict(base)
    return ("held", (
        f"'{code}' has been held on exactly these {len(items)} item(s) since "
        f"{entry.get('first_reported_at')}"
        + (f" ({held_for:.1f} day(s))" if held_for is not None else "")
        + f", it is tracked by issue #{issue}, and nothing about it has "
          f"changed since it was reported. The owner has already been told. "
          f"This run exits 0 and pages nobody; it goes loud again the moment "
          f"the list grows, if #{issue} is closed, or "
        + (f"{max(cap - since_report, 0):.1f} day(s) from now"
           if since_report is not None else f"after {cap} day(s)")
        + " regardless."), row)


def record(stops_dir, entry: dict) -> None:
    """Persist one decision. Called for BOTH outcomes.

    A held run still writes, because `last_seen_at` is what distinguishes a
    hold that is still happening from a stale row.
    """
    path = ledger_path(stops_dir)
    data = _read(path)
    data[key(entry["stage"], entry["code"])] = entry
    _write(path, data)


def record_issue(stops_dir, stage: str, code: str, number) -> bool:
    """Attach the issue number the wrapper just opened to the hold.

    Without this the next run has no tracker to name, and `classify` pages
    rather than pretend — see the `not issue` branch above.
    """
    path = ledger_path(stops_dir)
    data = _read(path)
    row = data.get(key(stage, code))
    if not row:
        return False
    try:
        row["issue"] = int(number)
    except (TypeError, ValueError):
        return False
    data[key(stage, code)] = row
    _write(path, data)
    return True


def clear(stops_dir, stage: str) -> None:
    """A stage that did real work is holding on nothing. Drop its rows.

    Symmetrical with `streak_clear`: the next hold in this stage starts from
    zero and is therefore loud, which is what a recurrence should be.
    """
    path = ledger_path(stops_dir)
    data = _read(path)
    doomed = [k for k, v in data.items() if (v or {}).get("stage") == stage]
    if not doomed:
        return
    for k in doomed:
        data.pop(k)
    _write(path, data)


def open_holds(stops_dir) -> dict:
    """Every hold currently on record, by key.

    Read by validators (see `loop/validate.py` V16) so a defect a lane has
    ALREADY escalated does not get re-reported by a second component as if it
    were news. One fact, one alarm.
    """
    return _read(ledger_path(stops_dir))


def held_items_for(stops_dir, code: str) -> set:
    """Every identifier currently held under `code`, across all stages."""
    out: set = set()
    for row in open_holds(stops_dir).values():
        if (row or {}).get("code") == code:
            out.update(row.get("items") or [])
    return out


def covering_hold(stops_dir) -> dict:
    """identifier -> the hold that has ALREADY escalated it, for any code.

    ONE FACT, ONE ALARM. The five uncaptioned episodes were reported by the
    upload lane as CAPTIONS_NOT_READY *and*, separately, failed V16 on the
    reach lane the following hour - two red jobs, two mails, one problem, and
    neither of them anything the owner could do twice. A second component that
    notices the same identifier should say "already escalated, tracked by
    #N", not raise it again.

    Only holds that carry an ISSUE NUMBER cover anything: an unreported hold
    has escalated nothing, so a validator leaning on it would be hiding a
    defect behind a record no human has ever seen.
    """
    out: dict = {}
    for row in open_holds(stops_dir).values():
        row = row or {}
        if not row.get("issue"):
            continue
        for item in row.get("items") or []:
            out.setdefault(item, row)
    return out


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    stops = os.environ.get("LOOP_STOPS_DIR") or str(
        Path(__file__).resolve().parent / "state" / "stops")
    if len(sys.argv) >= 5 and sys.argv[1] == "--record-issue":
        ok = record_issue(stops, sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"held: issue #{sys.argv[4]} recorded against "
              f"{sys.argv[2]}::{sys.argv[3]}" if ok else
              f"held: no hold on record for {sys.argv[2]}::{sys.argv[3]}")
        raise SystemExit(0 if ok else 1)
    print(json.dumps(open_holds(stops), indent=2, sort_keys=True))
