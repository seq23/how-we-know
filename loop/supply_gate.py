#!/usr/bin/env python3
"""THE SUPPLY GATE: no new video of a format while 14+ days of it wait to upload.

    python loop/supply_gate.py check longform|shorts   # exit 0 open, 10 HOLD; one line
    python loop/supply_gate.py report                  # every format: supply, rate, days, opens on

Her rule (12 Oct 2026; enforced in code 6 Nov 2026): over 14 days of supply,
make none of that format; free the Mac's night for the other work. On 6 Nov
the Mac had 33 days of long-form waiting (14 renders at 0.43 uploads a day)
and was still narrating more every night.

SUPPLY is what is MADE and not yet uploaded - never scripts alone:
  * longform: queued episodes (loop/batch_queue) not in the published ledger
    whose render exists, or whose narration is complete (every plan beat has
    a wav). Counting scripts would deadlock: a held night uploads nothing, the
    measured rate falls toward zero, and the gate would never reopen.
  * shorts: Shorts cut into shorts/ and not in loop/state/shorts_ledger.json.

RATE is the format's REAL upload rate: uploads in the last 28 days / 28
(long-form: ledger `uploaded_at`; Shorts: shorts ledger `uploaded_at`). With
none in 28 days the floor is one a week, so a fresh shelf cannot read as
infinite supply and hold forever.

A HOLD is a NOTE, never a red: `HOLD: 33 days of supply, making none`, exit
10, which the sessions read as "skip making this format tonight". The gate
reopens on its own as uploads drain the shelf.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

MAX_DAYS = 14.0
WINDOW_DAYS = 28
FLOOR_RATE = 1 / 7          # per day, when nothing uploaded in the window
HOLD_EXIT = 10


def _ts(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def rate(times: list[str | None], now: _dt.datetime) -> tuple[float, int]:
    n = sum(1 for s in times if (t := _ts(s)) and 0 <= (now - t).days < WINDOW_DAYS)
    return (n / WINDOW_DAYS if n else FLOOR_RATE), n


def longform_made(root: Path = ROOT, queued: list[str] | None = None,
                  ledger: dict | None = None) -> list[str]:
    if queued is None:
        import batch_queue                                  # noqa: PLC0415
        queued = batch_queue.queued_slugs()
    ledger = ledger if ledger is not None else json.loads((root / "loop/state/ledger.json").read_text())
    up = {e["slug"] for e in ledger.get("published", []) if not e.get("retired_at")}
    made = []
    for s in queued:
        if s in up:
            continue
        if (root / "renders" / f"{s}-final.mp4").exists() or \
                (root / "renders" / f"{s}-final.mp4.pruned.json").exists():
            made.append(s)
            continue
        plan = root / "plans" / f"{s}.json"
        if plan.exists():
            n = len(json.loads(plan.read_text()))
            if n and all((root / "audio" / s / f"{i:04d}.wav").exists() for i in range(n)):
                made.append(s)
    return made


def shorts_made(root: Path = ROOT, sledger: dict | None = None) -> list[str]:
    sledger = sledger if sledger is not None else json.loads((root / "loop/state/shorts_ledger.json").read_text())
    pub = {e.get("file") for e in sledger.get("published", [])}
    return sorted(os.path.basename(f) for f in glob.glob(str(root / "shorts" / "*.mp4"))
                  if os.path.basename(f) not in pub)


def verdict(fmt: str, made: int, per_day: float, uploads: int, now: _dt.datetime,
            max_days: float = MAX_DAYS) -> dict:
    days = made / per_day
    opens = None
    if days >= max_days:
        # supply drains at per_day: under max_days once made < max_days * per_day
        need = made - max_days * per_day
        opens = (now + _dt.timedelta(days=need / per_day + 1)).date().isoformat()
    line = (f"HOLD: {days:.0f} days of {fmt} supply, making none "
            f"({made} made and waiting, {uploads} uploaded in {WINDOW_DAYS} days; "
            f"opens about {opens})" if opens else
            f"open: {days:.1f} days of {fmt} supply ({made} waiting at {per_day:.2f}/day), "
            f"under {max_days:g}")
    return {"format": fmt, "made": made, "per_day": round(per_day, 3), "uploads_28d": uploads,
            "days": round(days, 1), "hold": bool(opens), "opens_on": opens, "line": line}


def check(fmt: str, now: _dt.datetime | None = None, root: Path = ROOT, **kw) -> dict:
    """`lane` (long-form only): judge ONE topic on its own supply - what it
    has made and not uploaded against its own upload pace, never slower than
    `per_week` (its planned nights). 13 Nov 2026: 12 deep-sea and materials
    long-forms made before the Money test held both Money nights until 22
    Nov, with no Money video made at all."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if fmt == "longform":
        led = kw.get("ledger") or json.loads((root / "loop/state/ledger.json").read_text())
        made = longform_made(root, kw.get("queued"), led)
        ups = led.get("published", [])
        lane = kw.get("lane")
        if lane:
            if kw.get("domain_of") is None:
                import domains as D                         # noqa: PLC0415
            domain_of = kw.get("domain_of") or (lambda s: D.domain_of_slug(s))
            made = [s for s in made if domain_of(s) == lane]
            ups = [e for e in ups if domain_of(e.get("slug")) == lane]
            fmt = f"{lane} long-form"
        per, n = rate([e.get("uploaded_at") for e in ups], now)
        if lane:
            per = max(per, float(kw.get("per_week") or 0) / 7)
    elif fmt == "shorts":
        sl = kw.get("sledger") or json.loads((root / "loop/state/shorts_ledger.json").read_text())
        made = shorts_made(root, sl)
        per, n = rate([e.get("uploaded_at") for e in sl.get("published", [])], now)
    else:
        raise ValueError(f"unknown format {fmt!r}")
    return verdict(fmt, len(made), per, n, now)


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "check":
        v = check(argv[1])
        print(v["line"])
        return HOLD_EXIT if v["hold"] else 0
    if argv[:1] == ["report"]:
        for f in ("longform", "shorts"):
            print(check(f)["line"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
