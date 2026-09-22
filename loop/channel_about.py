"""Push channel/about.md to the channel's public About text.

    .venv/bin/python loop/channel_about.py             # push if different
    .venv/bin/python loop/channel_about.py --dry-run    # compose, write nothing
    LOOP_DRY_RUN=1 .venv/bin/python loop/channel_about.py   # refuse credentials too

Run by hand from the Mac, with the loop's existing OAuth (the plain
`youtube` scope already covers `channels.update`). Not part of the weekly
loop — the About text does not change on a schedule, so this is a lever, not
a lane.

## Why a file, not a paste into Studio

`channel/about.md` is the one place the text is written; this script is the
one place it is read from and the one place it is sent. A paste into Studio
has no diff and no history. `docs/DECISION-LOG.md` records why the text
changed; this script's job is only to make what is live match what is on
disk.

## The same REPLACE trap `loop/ytmeta.py` exists for

`channels.update?part=brandingSettings` REPLACES `brandingSettings.channel`
wholesale from the body sent, exactly like `videos.update` does for a
video's snippet. Sending only `{"description": "..."}` would erase the
channel's title, keywords and country. So this reads the full live
`brandingSettings.channel` object immediately before writing, merges in only
`description`, and refuses to send anything that dropped a property the live
object had.

## Idempotent

If the live description already equals `channel/about.md`, nothing is
written — a re-run costs one read and confirms drift has not crept back in.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))

import tokens as auth  # noqa: E402
import upload as up  # noqa: E402
from common import config  # noqa: E402

ABOUT_FILE = ROOT / "channel" / "about.md"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

MARKER_START = "<!-- ABOUT:START -->"
MARKER_END = "<!-- ABOUT:END -->"

# YouTube caps brandingSettings.channel.description at 1,000 UTF-16 code
# units (what the API counts, not bytes or code points — identical for this
# text today, but an emoji or other astral character counts as 2) and
# rejects '<' or '>' outright. channels.update answers 400 to either, after
# the fact, with no detail — this repo's own push hit exactly that on
# 2026-09-21 at 1,006 units. Refusing here means the failure names the
# number and the character instead of a bare 400 from Google.
MAX_DESCRIPTION = 1000
FORBIDDEN_CHARS = "<>"

DRY_RUN = os.environ.get("LOOP_DRY_RUN") == "1"

# What channels.update REPLACES wholesale if it is not sent back. `title` is
# required by the API; the rest are not, and that is exactly why a partial
# body loses them silently.
CARRIED = ("title", "description", "keywords", "unsubscribedTrailer",
           "defaultLanguage", "country")


class MergeRefused(Exception):
    """A merge that would have written a partial brandingSettings.channel,
    or a description YouTube would reject."""


def check_description(text: str) -> None:
    """Refuse BEFORE any request if `text` would 400 against
    channels.update — over YouTube's 1,000-unit cap, or containing '<'/'>'.
    Counts UTF-16 code units, matching YouTube's own count."""
    for lineno, line in enumerate(text.split("\n"), start=1):
        for col, ch in enumerate(line, start=1):
            if ch in FORBIDDEN_CHARS:
                raise MergeRefused(
                    f"DESCRIPTION_HAS_ANGLE_BRACKET: {ch!r} at line "
                    f"{lineno}, column {col}")
    units = len(text.encode("utf-16-le")) // 2
    if units > MAX_DESCRIPTION:
        over = units - MAX_DESCRIPTION
        raise MergeRefused(
            f"DESCRIPTION_TOO_LONG: {units} characters, limit "
            f"{MAX_DESCRIPTION} ({over} over)")


def read_about() -> str:
    if not ABOUT_FILE.exists():
        sys.exit(f"FATAL: {ABOUT_FILE} does not exist")
    text = ABOUT_FILE.read_text()
    if MARKER_START not in text or MARKER_END not in text:
        sys.exit(f"FATAL: {ABOUT_FILE} is missing {MARKER_START!r} / "
                 f"{MARKER_END!r} — nothing to push")
    body = text.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0]
    return body.strip("\n")


def read_channel(token: str) -> dict:
    """The CURRENT server-side channel object. Always read immediately before
    a write — merging onto a cached copy would revert a manual Studio edit."""
    q = urllib.parse.urlencode({"part": "brandingSettings,snippet",
                                "mine": "true"})
    req = urllib.request.Request(f"{CHANNELS_URL}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    items = data.get("items") or []
    if not items:
        sys.exit("FATAL: channels.list (mine=true) returned no channel")
    return items[0]


def merge_branding(current: dict, description: str) -> dict:
    """Build a COMPLETE brandingSettings.channel from the live one, plus the
    new description. Refuses rather than truncating."""
    check_description(description)
    if not isinstance(current, dict) or not current.get("title"):
        raise MergeRefused(
            "no brandingSettings.channel with a title was read back; "
            "refusing to write one from nothing")
    merged = {k: current[k] for k in CARRIED if k in current}
    merged["description"] = description
    if not merged.get("title"):
        raise MergeRefused("the merged brandingSettings.channel lost 'title'")
    for k in ("keywords", "country"):
        if k in current and k not in merged:
            raise MergeRefused(f"the merged brandingSettings.channel dropped "
                               f"{k!r}")
    return merged


def push(token: str, channel_id: str, current_branding: dict,
        description: str, dry_run: bool) -> dict:
    branding = merge_branding(current_branding, description)
    body = {"id": channel_id, "brandingSettings": {"channel": branding}}
    if dry_run:
        return body
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{CHANNELS_URL}?part=brandingSettings", data=data, method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    return body


def run(dry_run: bool) -> int:
    wanted = read_about()
    try:
        check_description(wanted)
    except MergeRefused as e:
        print(f"FATAL [{e}]: refusing to push a description YouTube would "
              f"reject with a 400 — fix {ABOUT_FILE} and re-run.")
        return 1
    cfg = config()

    if DRY_RUN and not dry_run:
        print("LOOP_DRY_RUN=1 — behaving as an un-credentialed machine "
              "would; use --dry-run to compose against a real credential "
              "without writing.")
        return 0

    creds = up.load_credentials(cfg)
    if not creds or creds.get("unusable"):
        code, msg, unblock = up.credential_stop(creds, cfg)
        print(f"FATAL [{code}]: {msg}\n{unblock}")
        return 1

    token = up.access_token(creds)
    ch = auth.channel(token)
    if not ch["ok"] or not ch["matches_expected"]:
        print("FATAL: refusing to rewrite the About text: "
              + (f"the credential authorises '{ch.get('title')}', not "
                 f"{auth.EXPECTED_HANDLE}" if ch["ok"] else ch["detail"]))
        return 1

    live = read_channel(token)
    channel_id = live["id"]
    current_desc = ((live.get("brandingSettings") or {}).get("channel") or
                    {}).get("description") or ""

    if current_desc.strip() == wanted.strip():
        print(f"About text already matches {ABOUT_FILE} — nothing to write.")
        return 0

    branding = (live.get("brandingSettings") or {}).get("channel") or {}
    body = push(token, channel_id, branding, wanted, dry_run=dry_run)
    if dry_run:
        print(f"--dry-run: composed a COMPLETE brandingSettings.channel "
              f"({len(body['brandingSettings']['channel'])} properties) — "
              f"sent nothing.")
        return 0

    print(f"Wrote a new About text to {ch['title']} ({channel_id}).")

    # Re-read and verify, rather than trusting the 200 OK.
    verify = read_channel(token)
    got = ((verify.get("brandingSettings") or {}).get("channel") or
          {}).get("description") or ""
    if got.strip() != wanted.strip():
        print("FATAL: re-read after the write does not match "
             f"{ABOUT_FILE} — the push did not land as sent.")
        return 1
    print("Verified: a fresh channels.list read shows the new text live.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="read live, compose the body, write nothing")
    a = ap.parse_args()
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
