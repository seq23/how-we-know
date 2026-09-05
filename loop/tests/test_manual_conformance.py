"""docs/OPERATING-MANUAL.md must agree with the code it describes.

A document that quietly disagrees with the running system is worse than no
document: it is read, believed, and acted on. The manual states four operating
numbers and a launch video id; every one of them exists somewhere in the code or
the ledger, so every one can be checked rather than trusted.

This asserts BEHAVIOUR-BEARING facts only. Prose is not tested - a validator
that asserts wording rather than behaviour is the defect this repo names
explicitly.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "loop"))

MANUAL = ROOT / "docs" / "OPERATING-MANUAL.md"
RUNBOOK = ROOT / "RUNBOOK.md"
CLAUDEMD = ROOT / "CLAUDE.md"
DAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday"}


def check() -> list[str]:
    fails, examined = [], 0
    if not MANUAL.exists():
        return [f"{MANUAL} does not exist"]
    text = MANUAL.read_text()
    cfg = json.loads((ROOT / "loop" / "config.json").read_text())
    import backfill

    # 1 - stated long-form cadence == loop/config.json
    examined += 1
    per_week = cfg["cadence"]["videos_per_week"]
    if not re.search(rf"\*\*{per_week} per week\*\*", text):
        fails.append(f"manual does not state '{per_week} per week' but "
                     f"loop/config.json cadence.videos_per_week is {per_week}")

    # 2 - stated publish hour == the LOCAL constant the scheduler uses.
    # Checked against the local hour, not a UTC one: the UTC stamp legitimately
    # changes twice a year and a test pinned to it would fail every autumn.
    examined += 1
    if f"{backfill.PUBLISH_HOUR_LOCAL}:00 Central" not in text:
        fails.append(f"manual does not state "
                     f"{backfill.PUBLISH_HOUR_LOCAL}:00 Central but "
                     f"backfill.PUBLISH_HOUR_LOCAL is "
                     f"{backfill.PUBLISH_HOUR_LOCAL}")

    # 3 - the schedule must be pinned to a timezone, not a UTC offset
    examined += 1
    if str(backfill.PUBLISH_TZ) not in text:
        fails.append(f"manual does not name the scheduling timezone "
                     f"{backfill.PUBLISH_TZ}")

    # 3 - stated publish days == the weekdays the scheduler actually uses
    for wd in backfill.PUBLISH_WEEKDAYS:
        examined += 1
        if DAYS[wd] not in text:
            fails.append(f"backfill publishes on {DAYS[wd]} but the manual "
                         f"never names that day")

    # 4 - the launch video named in the manual is really the published one
    examined += 1
    led = json.loads((ROOT / "loop" / "state" / "ledger.json").read_text())
    public = [r for r in led["published"] if r.get("privacy") == "public"]
    for r in public:
        if r["video_id"] not in text:
            fails.append(f"{r['video_id']} is public on the channel but the "
                         f"manual does not mention it")

    # 5 - every INSTALLED launchd agent must be named in the manual, and the
    # manual must not name one that is not installed. The agent table is the
    # thing a reader uses to answer "what needs my laptop awake"; a stale entry
    # sends them looking for a job that does not exist, and a missing one hides
    # a job that does.
    import glob as _glob
    import os as _os
    installed = {_os.path.basename(f).replace(".plist", "")
                 for f in _glob.glob(_os.path.expanduser(
                     "~/Library/LaunchAgents/com.howweknow.*.plist"))}
    for label in sorted(installed):
        examined += 1
        if label not in text:
            fails.append(f"{label} is installed on this machine but the manual "
                         f"never names it")
    for label in re.findall(r"com\.howweknow\.[a-z]+", text):
        examined += 1
        if installed and label not in installed:
            fails.append(f"the manual names {label} but no such launchd agent "
                         f"is installed")

    # 6 - RUNBOOK.md is the page the owner opens when she sits down to work, so
    # the command it tells her to run must exist and be executable. A runbook
    # naming a script that is missing or not runnable is worse than no runbook:
    # it is read at the exact moment there is no patience for debugging.
    examined += 1
    if not RUNBOOK.exists():
        fails.append("RUNBOOK.md does not exist")
    else:
        rb = RUNBOOK.read_text()
        for m in re.findall(r"(bin/[a-z0-9-]+\.sh)", rb):
            examined += 1
            f = ROOT / m
            if not f.exists():
                fails.append(f"RUNBOOK.md tells her to run {m}, which does not exist")
            elif not os.access(f, os.X_OK):
                fails.append(f"RUNBOOK.md tells her to run {m}, which is not executable")
        for m in re.findall(r"(loop/[a-z_]+\.py)", rb):
            examined += 1
            if not (ROOT / m).exists():
                fails.append(f"RUNBOOK.md references {m}, which does not exist")

    # 7 - the documented Shorts rank policy must match the lane's constant.
    # The manual states a supply figure (48 Shorts, 12 weeks) that is derived
    # from MAX_RANK. If someone narrows the lane back to rank 1 the arithmetic
    # in the manual silently becomes a lie, and the runway it promises with it.
    examined += 1
    lane = (ROOT / "loop" / "shorts_lane.py").read_text()
    m = re.search(r"MAX_RANK\s*=\s*(\d+)", lane)
    if not m:
        fails.append("loop/shorts_lane.py has no MAX_RANK; the manual's Shorts "
                     "supply table cannot be checked against anything")
    else:
        mr = int(m.group(1))
        if f"1-{mr} (current)" not in text and f"1-{mr}" not in text:
            fails.append(f"shorts_lane MAX_RANK is {mr} but the manual's supply "
                         f"table does not mark ranks 1-{mr} as current")

    # 8 - CLAUDE.md is what a FRESH session in this directory loads. It is the
    # only thing that makes "runbook" mean anything to a Claude that has never
    # seen this repo, and the only place the hard rules are stated where an
    # agent will actually read them. Every document it points at must exist.
    examined += 1
    if not CLAUDEMD.exists():
        fails.append("CLAUDE.md does not exist - a fresh session in this "
                     "directory would know nothing, and 'runbook' would mean "
                     "nothing")
    else:
        cm = CLAUDEMD.read_text()
        examined += 1
        if "RUNBOOK.md" not in cm:
            fails.append("CLAUDE.md does not point at RUNBOOK.md, so the "
                         "'runbook' trigger does not resolve in a fresh session")
        for m in set(re.findall(r"\(([A-Za-z0-9_./-]+\.md)\)", cm)):
            examined += 1
            if not (ROOT / m).exists():
                fails.append(f"CLAUDE.md links {m}, which does not exist")

    # 9 - no delete path may appear, since the manual promises there is none
    examined += 1
    src = " ".join(p.read_text() for p in (ROOT / "loop").glob("*.py"))
    if re.search(r'method\s*=\s*"DELETE"', src):
        fails.append("the manual states there is no delete path, but loop/ "
                     "contains an HTTP DELETE")

    if examined == 0:
        fails.append("examined 0 facts - this test cannot see what it governs")
    print(f"inspected {examined} manual fact(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print(f"{len(f)} failure(s)" if f else
          "all green - the manual matches the running system")
    raise SystemExit(1 if f else 0)
