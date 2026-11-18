#!/usr/bin/env python3
"""THE PUBLISHING FLOOR: every channel, 7 public videos a week, one every day.

    python loop/publish_floor.py check            # read, judge, alert (the 09:00 CT upload workflow)
    python loop/publish_floor.py check --dry-run  # read and judge; print the alert, file nothing

Her floor, 18 Nov 2026: "make sure 7 videos go out each week minimum for
each channel" (decided reading: at least 7 PUBLIC videos per channel in any
rolling 7 days AND at least one every day; Shorts count). config/publish_floor.json
holds the numbers.

WHY IT EXISTS. On 18 Nov How We Know had had no Short since 11 Nov and no
long-form scheduled after that morning, and Whisper Almanac had one public
video ever, while every lane that could have said so was a green "held" or
"self-resolving" stop: a domain breaker trip, a starved Shorts shelf, a cut
that failed silently every night. Each lane judged its own step; nothing
judged the channel. This judges the channel, from YouTube's own public feed
(never our ledger), so it sees every cause at once.

  * PUBLIC: youtube.com/feeds/videos.xml?channel_id=... (public uploads,
    Shorts included, no key, no quota): how many went public in the last 7 days.
  * AHEAD: today and tomorrow (Central) must each have a video public or
    dated, read from the upload records (How We Know: loop/state/ledger.json
    and shorts_ledger.json; Whisper Almanac: channel/whisper/*/kit.json).
  * A BREACH IS A RED STOPPED EMAIL: a GitHub issue that @-mentions her (so
    GitHub emails it), naming the channel, the gap and the fix (the lanes'
    own named stops this week, the breaker, the long-form approval gate). It
    is re-mentioned every day the breach lasts (never held), and closed by
    the first check that finds the floor met.
  * A feed that cannot be read is NAMED STOP PUBLISH_FLOOR_NOT_READ, exit 2:
    the floor is never judged on no data.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
CONFIG = ROOT / "config" / "publish_floor.json"
STATE = LOOP / "state"
CT = ZoneInfo("America/Chicago")
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
LABEL = "publish-floor"
NS = {"a": "http://www.w3.org/2005/Atom"}


def cfg() -> dict:
    return json.loads(CONFIG.read_text())


def _t(x) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- what is public
def parse_feed(xml: str) -> list[dict]:
    """The feed's videos: [{id, title, published}]."""
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", NS):
        vid = (e.findtext("{http://www.youtube.com/xml/schemas/2015}videoId") or "").strip()
        pub = _t(e.findtext("a:published", default="", namespaces=NS))
        if vid and pub:
            out.append({"id": vid, "title": (e.findtext("a:title", default="", namespaces=NS) or "").strip(),
                        "published": pub})
    return out


def read_feed(channel_id: str) -> list[dict]:
    req = urllib.request.Request(FEED.format(channel_id), headers={"User-Agent": "how-we-know/publish-floor"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return parse_feed(r.read().decode("utf-8"))


# ------------------------------------------------------------- what is dated
def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def scheduled(channel: str, root: Path = ROOT) -> list[_dt.datetime]:
    """Publish times of every video uploaded private with a date, by our upload records."""
    out: list[_dt.datetime] = []
    if channel == "how-we-know":
        for f, rows in ((root / "loop/state/ledger.json", "published"),
                        (root / "loop/state/shorts_ledger.json", "published")):
            for r in _json(f).get(rows, []):
                if r.get("video_id") and not r.get("retired_at") and not r.get("withdrawn_at"):
                    t = _t(r.get("scheduled_publish_at"))
                    if t:
                        out.append(t)
    elif channel == "whisper-almanac":
        for f in sorted((root / "channel/whisper").glob("*/kit.json")):
            k = _json(f)
            if k.get("video_id") and _t(k.get("scheduled_publish_at")):
                out.append(_t(k["scheduled_publish_at"]))
            for s in k.get("shorts") or []:
                if isinstance(s, dict) and s.get("video_id") and _t(s.get("publish_at")):
                    out.append(_t(s["publish_at"]))
    return out


# ------------------------------------------------------------- the judgement
def judge(public: list[dict], dated: list[_dt.datetime], now: _dt.datetime, per_week: int,
          lookahead_days: int = 2) -> dict:
    """{week: n public in the last 7 days, short_by, empty_past: [days], empty_ahead: [days], ok}."""
    week = [v for v in public if now - _dt.timedelta(days=7) < v["published"] <= now]
    today = now.astimezone(CT).date()
    pub_days = {v["published"].astimezone(CT).date() for v in public if v["published"] <= now}
    dated_days = {t.astimezone(CT).date() for t in dated if t > now}
    empty_past = [today - _dt.timedelta(days=i) for i in range(6, 0, -1)
                  if today - _dt.timedelta(days=i) not in pub_days]
    ahead = [today + _dt.timedelta(days=i) for i in range(lookahead_days)]
    empty_ahead = [d for d in ahead if d not in pub_days and d not in dated_days]
    short_by = max(0, per_week - len(week))
    return {"week": len(week), "per_week": per_week, "short_by": short_by,
            "empty_past": empty_past, "empty_ahead": empty_ahead,
            "next": min((t for t in dated if t > now), default=None),
            "last_public": max((v["published"] for v in public), default=None),
            "ok": short_by == 0 and not empty_ahead}


def _day(d: _dt.date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _ct(t: _dt.datetime | None) -> str:
    return "none" if t is None else f"{t.astimezone(CT):%a %d %b %H:%M} CT"


def fixes(channel: str, ch: dict, now: _dt.datetime, root: Path = ROOT) -> list[str]:
    """What is stopping it: the channel's lanes' named stops this week, and
    (How We Know) the breaker and the long-form approval gate."""
    out = []
    week = f"{now.astimezone(CT):%G-W%V}"
    for lane in ch.get("lanes", []):
        s = _json(root / "loop/state/stops" / f"{week}-{lane}.json")
        if s.get("code") and not str(s["code"]).startswith("BREAKER_TRIPPED"):   # one breaker line below
            out.append(f"{lane}: {s['code']} - {str(s.get('message', ''))[:220]}"
                       + (f" Fix: {str(s.get('unblock'))[:220]}" if s.get("unblock") else ""))
    if channel == "how-we-know":
        b = _json(root / "loop/state/breaker.json")
        if b.get("state") == "tripped":
            out.append(f"breaker: tripped {str(b.get('tripped_at'))[:10]} on {b.get('cause')}: "
                       f"{str(b.get('detail'))[:200]}")
        if b.get("longform_owner_approval_required"):
            appr = _json(root / "channel/approved_renders.json")
            done = {r.get("slug") for r in _json(root / "loop/state/ledger.json").get("published", [])}
            waiting = sorted(s for s in appr if s not in done)
            out.append("long-form approval gate is on: a long-form goes out only once you approve its cut; "
                       + (f"approved and not yet out: {', '.join(waiting)}" if waiting else
                          "every approved cut is already out, so no long-form can be scheduled until you "
                          "approve the next renders"))
    return out or ["no lane recorded a named stop this week: read the nightly batch log on the Mac "
                   "(~/Library/Logs/how-we-know/batch.log)"]


def alert(channel: str, ch: dict, j: dict, fx: list[str], now: _dt.datetime) -> tuple[str, str]:
    name = ch.get("name", channel)
    title = f"STOPPED: {name} is below its floor ({j['week']} of {j['per_week']} public videos this week)"
    gap = [f"- **Public in the last 7 days:** {j['week']} of {j['per_week']}"
           + (f" (short by {j['short_by']})" if j["short_by"] else ""),
           f"- **Last public video:** {_ct(j['last_public'])}",
           f"- **Next dated video:** {_ct(j['next'])}"]
    if j["empty_ahead"]:
        gap.append(f"- **Nothing public or dated for:** {', '.join(_day(d) for d in j['empty_ahead'])}")
    if j["empty_past"]:
        gap.append(f"- **Days with nothing public (last 6):** {', '.join(_day(d) for d in j['empty_past'])}")
    body = "\n".join([f"**{name}: STOPPED.** Her floor is at least {j['per_week']} public videos a week "
                      f"and one every day (Shorts count). Read from YouTube's public feed "
                      f"{now.astimezone(CT):%a %d %b %H:%M} CT.", "", "**The gap**", *gap, "",
                      "**What is stopping it (the fix)**", *[f"- {x}" for x in fx], "",
                      "This issue is mentioned every day the floor is missed and closes itself the "
                      "first day it is met (loop/publish_floor.py)."])
    return title, body


# ------------------------------------------------------------- delivery
def _gh(args: list[str], runner=subprocess.run) -> str:
    r = runner(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


def open_issue(channel: str, runner=subprocess.run) -> int | None:
    out = _gh(["issue", "list", "--state", "open", "--label", LABEL, "--search", f"{channel} in:body",
               "--json", "number,body", "--limit", "20"], runner)
    for r in json.loads(out or "[]"):
        if f"<!-- publish-floor:{channel} -->" in (r.get("body") or ""):
            return int(r["number"])
    return None


def deliver(channel: str, breach: tuple[str, str] | None, met_line: str, runner=subprocess.run) -> str:
    """Open (or re-mention) the channel's STOPPED issue, or close it once met."""
    who = "@" + (os.environ.get("OWNER_HANDLE") or "seq23")
    num = open_issue(channel, runner)
    if breach is None:
        if num is None:
            return "met"
        _gh(["issue", "close", str(num), "--comment", f"Floor met again: {met_line}"], runner)
        return f"closed #{num}"
    title, body = breach
    if num is None:
        text = f"{who}\n\n{body}\n\n<!-- publish-floor:{channel} -->"
        try:
            _gh(["issue", "create", "--title", title, "--body", text, "--label", LABEL], runner)
        except RuntimeError:                               # the label does not exist yet
            _gh(["label", "create", LABEL, "--color", "B60205", "--description",
                 "a channel below her publishing floor"], runner)
            _gh(["issue", "create", "--title", title, "--body", text, "--label", LABEL], runner)
        return "opened"
    _gh(["issue", "comment", str(num), "--body", f"{who} still STOPPED.\n\n{body}"], runner)
    _gh(["issue", "edit", str(num), "--title", title], runner)
    return f"re-mentioned #{num}"


# ------------------------------------------------------------- the run
def check(dry_run: bool = False, now: _dt.datetime | None = None, feed=read_feed,
          runner=subprocess.run, root: Path = ROOT) -> int:
    c = cfg()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    unread, breaches, n = [], 0, 0
    for channel, ch in c["channels"].items():
        try:
            public = feed(ch["channel_id"])
        except Exception as e:                              # noqa: BLE001
            unread.append(f"{channel}: {type(e).__name__}: {str(e)[:120]}")
            continue
        n += 1
        j = judge(public, scheduled(channel, root), now, int(ch.get("per_week", c["per_week"])),
                  int(c.get("lookahead_days", 2)))
        line = (f"{ch.get('name', channel)}: {j['week']} of {j['per_week']} public in 7 days, "
                f"next dated {_ct(j['next'])}"
                + (f", nothing for {', '.join(_day(d) for d in j['empty_ahead'])}" if j["empty_ahead"] else ""))
        print(f"  {'OK     ' if j['ok'] else 'STOPPED'} {line}")
        breach = None
        if not j["ok"]:
            breaches += 1
            breach = alert(channel, ch, j, fixes(channel, ch, now, root), now)
            if dry_run:
                print(breach[0])
                print(breach[1])
        if not dry_run:
            try:
                print(f"    {deliver(channel, breach, line, runner)}")
            except RuntimeError as e:
                unread.append(f"{channel}: the alert could not be filed: {e}")
    for u in unread:
        print(f"NAMED STOP [PUBLISH_FLOOR_NOT_READ] {u}", file=sys.stderr)
    print(f"OUTPUT {n} of {len(c['channels'])} channels judged, {breaches} below the floor")
    return 2 if unread or not n else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check")
    ck.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return check(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
