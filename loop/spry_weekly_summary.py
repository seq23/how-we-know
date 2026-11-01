"""THE SPRY LABS WEEKLY HAND-OFF (owner, 1 Nov 2026).

How We Know's Sunday digest no longer emails the owner. The issue is still opened (the record), but
without the @-mention that made GitHub email it; instead this writes spry-weekly-summary.json
(schema spry-weekly-summary-v1) from the week's .subject line, the workflow uploads it as the
artifact `spry-weekly-summary`, and Boss OS puts a short How We Know section into the one
"Spry Labs weekly" email on Wednesday at 08:15 Central.

    python3 loop/spry_weekly_summary.py <WEEK> [out.json]
    python3 loop/spry_weekly_summary.py --self-check
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = {"🔴": "needs-a-look", "🟡": "watch", "🟢": "fine"}


def summarise(subject: str, week: str, run_url: str | None = None, now: str | None = None) -> dict:
    line = (subject or "").strip().splitlines()[0] if (subject or "").strip() else ""
    if not line:
        raise SystemExit("NAMED STOP [NO_SUBJECT] the digest wrote no verdict line; nothing to hand to Boss OS.")
    mark = line[:1]
    text = line[1:].strip() if mark in STATE else line
    if text.endswith(f" — {week}"):
        text = text[: -len(f" — {week}")]
    return {
        "schema": "spry-weekly-summary-v1", "business": "How We Know", "week": week,
        "generated_at": now or dt.datetime.now(dt.timezone.utc).isoformat(), "run_url": run_url,
        "state": STATE.get(mark, "watch"), "sites": [], "notes": [text],
    }


def self_check() -> None:
    s = summarise("🔴 Shorts stopped: 1 of 9 published — needs you: check the Mac — 2026-W45", "2026-W45")
    assert s["state"] == "needs-a-look" and s["notes"] == ["Shorts stopped: 1 of 9 published — needs you: check the Mac"], s
    assert summarise("🟢 A quiet week — 2026-W45", "2026-W45")["state"] == "fine"
    assert summarise("no mark at all", "2026-W45")["state"] == "watch"
    try:
        summarise("", "2026-W45")
    except SystemExit:
        pass
    else:
        raise AssertionError("an empty verdict was handed on (rule 0)")
    print("spry_weekly_summary self-check: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        sys.exit(0)
    week = sys.argv[1]
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "spry-weekly-summary.json")
    subj = (ROOT / "loop" / "state" / "digest" / f"{week}.subject")
    summary = summarise(subj.read_text() if subj.exists() else "", week, os.environ.get("RUN_URL"))
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"spry weekly summary: {summary['state']} -> {out}")
