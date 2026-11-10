"""THE 30-DAY CHECK PER LANE: watch hours and subscribers, How We Know's topics.

    python loop/lane_check.py          # one OUTPUT line per lane; NAMED STOP when not read

Her call 9 Nov 2026 (spry brain): both How We Know long-form nights go to the
Money lane for its 12-video test, "judged at 30 days on watch hours and
subscribers per lane, replacing the 2 Nov 'about 30 long videos per topic,
results decide' rule". This is that check. The Sunday digest shows it
(loop/digest.py lanes_block) where the 30-video table used to be.

  * The window is the test's: from loop/config.json domains.money_test.started
    for check_days (30). Each lane (an allocated domain) is judged on its long
    videos that went public inside the window: how many, views, watch hours,
    subscribers gained - from the Friday measure lane's per-video rows
    (loop/state/measurement.json), the latest row per video.
  * Before the due date a lane reads "30-day check due <date>"; on and after
    it, "30-day check: read".
  * Nothing is estimated. A lane video with no measured row, or a measurement
    file that cannot be read, is "not read" - never 0 - and the check ends on
    the NAMED STOP LANE_CHECK_NOT_READ (self-resolving: the next Friday
    measure writes the rows).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

MEASUREMENT = LOOP / "state" / "measurement.json"
NOT_READ = "not read"


def _day(stamp: str | None) -> dt.date | None:
    if not stamp:
        return None
    try:
        return dt.date.fromisoformat(str(stamp)[:10])
    except ValueError:
        return None


def window(cfg: dict) -> tuple[dt.date, dt.date] | None:
    t = ((cfg.get("domains") or {}).get("money_test")) or {}
    start = _day(t.get("started"))
    if not start:
        return None
    return start, start + dt.timedelta(days=int(t.get("check_days", 30)))


def read_rows(path: Path = MEASUREMENT) -> list[dict] | None:
    """The measure lane's per-video rows, or None when they cannot be read."""
    try:
        rows = json.loads(path.read_text()).get("videos")
    except (OSError, ValueError, AttributeError):
        return None
    return rows if isinstance(rows, list) else None


def check(cfg: dict, published: list[dict], rows: list[dict] | None,
          today: dt.date, domain_of=None) -> list[dict]:
    """One dict per lane: videos, views, watch_hours, subscribers (None = not
    read), the due date and its state."""
    import domains as D                                     # noqa: PLC0415
    win = window(cfg)
    lanes = list(D.allocation(cfg))
    if win is None:
        return [{"lane": ln, "state": "no test window (domains.money_test.started)",
                 "videos": None, "views": None, "watch_hours": None, "subscribers": None,
                 "unread": ["no test window"], "due": None} for ln in lanes]
    start, due = win
    domain_of = domain_of or (lambda slug: D.domain_of_slug(slug))
    latest: dict[str, dict] = {}
    for r in rows or []:
        vid = r.get("video_id")
        if vid and (vid not in latest or str(r.get("at") or "") >= str(latest[vid].get("at") or "")):
            latest[vid] = r
    out = []
    for ln in lanes:
        vids = []
        for e in published:
            when = _day(e.get("scheduled_publish_at") or e.get("published_at") or e.get("uploaded_at"))
            if (e.get("video_id") and not e.get("retired_at") and when
                    and start <= when <= min(due, today) and domain_of(e.get("slug")) == ln):
                vids.append(e["video_id"])
        unread = ["the measurement file could not be read"] if rows is None else \
            [v for v in vids if v not in latest]
        vals = None if unread else [latest[v] for v in vids]
        out.append({
            "lane": ln, "videos": len(vids), "due": due.isoformat(), "unread": unread,
            "views": None if vals is None else int(sum(float(v.get("views") or 0) for v in vals)),
            "watch_hours": None if vals is None else round(
                sum(float(v.get("estimated_minutes_watched") or 0) for v in vals) / 60, 2),
            "subscribers": None if vals is None else int(
                sum(float(v.get("subscribers_gained") or 0) for v in vals)),
            "state": (f"30-day check due {due.isoformat()}" if today < due else "30-day check: read"),
        })
    return out


def fmt(v) -> str:
    return NOT_READ if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def val(r: dict, key: str) -> str:
    """A lane with no long video in the window has nothing to measure: '-'."""
    return "-" if r.get("videos") == 0 and not r.get("unread") else fmt(r.get(key))


def line(r: dict) -> str:
    return (f"{r['lane']}: {fmt(r['videos'])} long video(s) in the test window · watch hours "
            f"{val(r, 'watch_hours')} · subscribers {val(r, 'subscribers')} · views "
            f"{val(r, 'views')} · {r['state']}")


def main() -> int:
    import ledger                                           # noqa: PLC0415
    from common import config                               # noqa: PLC0415
    rows = read_rows()
    res = check(config(), ledger.load().get("published") or [], rows, dt.date.today())
    for r in res:
        print(f"OUTPUT lane check {line(r)}")
    unread = [r for r in res if r["unread"]]
    if unread:
        print(f"NAMED STOP [LANE_CHECK_NOT_READ] {len(unread)} lane(s) not read: "
              + "; ".join(f"{r['lane']}: {r['unread'][0]}" for r in unread)
              + " - the next Friday measure writes the rows")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
