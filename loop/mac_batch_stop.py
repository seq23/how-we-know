#!/usr/bin/env python3
"""The Mac batch's named stops, made to reach somebody.

WHY THIS EXISTS. bin/batch-session.sh runs under launchd on the Mac. A cloud
lane that exits 3 has a calling workflow that turns the exit into an issue;
the Mac has none. From 21 Sep 2026 the nightly push ended NAMED STOP
[SHORTS_UNVERIFIED] - classified needs_human - and only batch.log knew. No
Short reached R2 and nobody was told.

So, at the end of every batch:

    python loop/mac_batch_stop.py scan <file holding the push's output>

  * every `NAMED STOP [CODE] message` line in that output is recorded through
    the ordinary Stage machinery as stage "mac-batch" - the same record, streak
    and disposition every cloud lane gets - in
    loop/state/stops/<week>-mac-batch.json, which loop/mac_sync.py commits with
    the batch's own push and loop/digest.py reads like any other stop;
  * a stop whose disposition is not green files ONE GitHub issue titled
    `[mac-batch] <CODE>`, or comments on the open one (deduped by title);
  * a night with no stop clears the record (Stage's own success path).

It never fails the batch: the push of what DID pass has already happened, and
a filing error is printed, not raised. Exit code is always 0.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import common as C                                       # noqa: E402

STAGE = "mac-batch"
REPO = "seq23/how-we-know"
STOP_LINE = re.compile(r"NAMED STOP \[([A-Z0-9_]+)\]\s*(.*)")
GREEN = {"self_resolving", "held", "owner_action"}


def scan(text: str) -> list[tuple[str, str]]:
    """(code, message) for every distinct named stop in `text`, in order."""
    out, seen = [], set()
    for line in text.splitlines():
        m = STOP_LINE.search(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), m.group(2).strip()))
    return out


def _gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          timeout=60)


def title_for(code: str) -> str:
    return f"[{STAGE}] {code}"


def file_issue(rec: dict, gh=_gh) -> str:
    """Open `[mac-batch] <CODE>` or comment on the open one. Returns what it did."""
    title = title_for(rec["code"])
    body = (f"**{rec['code']}** on the Mac batch, {rec.get('at', '')[:16]} "
            f"(consecutive {rec.get('consecutive')}).\n\n{rec.get('message', '')}"
            f"\n\nunblock: {rec.get('unblock') or '-'}\n\nRecord: "
            f"`loop/state/stops/{rec.get('week')}-{STAGE}.json`; full output "
            f"in ~/Library/Logs/how-we-know/batch.log on the Mac.")
    r = gh(["issue", "list", "-R", REPO, "--state", "open", "--search",
            f'"{title}" in:title', "--json", "number,title", "--limit", "50"])
    if r.returncode != 0:
        return f"gh issue list failed: {r.stderr.strip()[:200]}"
    try:
        hits = [i for i in json.loads(r.stdout or "[]") if i.get("title") == title]
    except ValueError:
        hits = []
    if hits:
        n = str(hits[0]["number"])
        c = gh(["issue", "comment", n, "-R", REPO, "--body",
                f"{date.today():%Y-%m-%d}: still stopping.\n\n{body}"])
        return (f"commented on #{n}" if c.returncode == 0 else
                f"gh issue comment failed: {c.stderr.strip()[:200]}")
    c = gh(["issue", "create", "-R", REPO, "--title", title, "--body", body])
    return (f"opened {c.stdout.strip()}" if c.returncode == 0 else
            f"gh issue create failed: {c.stderr.strip()[:200]}")


def _record(code: str, message: str, unblock: str = "") -> dict:
    try:
        with C.Stage(STAGE) as st:
            st.named_stop(code, message, unblock=unblock)
    except SystemExit:
        pass
    p = C._stops_dir() / f"{C.week_id()}-{STAGE}.json"
    return json.loads(p.read_text())


def _clear() -> None:
    try:
        with C.Stage(STAGE) as st:
            st.work("the batch's push ended with no named stop")
    except SystemExit:
        pass


def report(text: str, gh=_gh) -> list[dict]:
    """Record every stop in `text`; file an issue for each one that pages."""
    stops = scan(text)
    if not stops:
        _clear()
        return []
    out = []
    for code, msg in stops:
        rec = _record(code, msg or f"{code} on the Mac batch",
                      unblock="Read the '=== batch session' block in "
                              "~/Library/Logs/how-we-know/batch.log on the Mac.")
        if rec.get("disposition") not in GREEN:
            try:
                rec["issue"] = file_issue(rec, gh)
            except Exception as e:                       # noqa: BLE001
                rec["issue"] = f"filing failed: {e}"
            print(f"  mac-batch stop {code}: {rec['disposition']} - {rec['issue']}")
        else:
            print(f"  mac-batch stop {code}: {rec['disposition']} - no issue")
        out.append(rec)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] != "scan":
        print("usage: mac_batch_stop.py scan <output-file>")
        return 0
    try:
        text = Path(argv[1]).read_text(errors="replace")
    except OSError as e:
        print(f"  mac-batch: could not read {argv[1]}: {e}")
        return 0
    try:
        report(text)
    except Exception as e:                               # noqa: BLE001
        print(f"  mac-batch: reporting failed ({e}); the push already ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
