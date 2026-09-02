"""Retire a published video by making it PRIVATE. Nothing here ever deletes.

    .venv/bin/python loop/retire.py --slug 10-what-is-the-deepest-part-of-the-ocean
    .venv/bin/python loop/retire.py --video-id qBeLl0z4s54 --reason "superseded"

Owner policy, 2026-08-31: *"we dont have to delete any videos ever. we can just
private them as a default for ones we no longer want published."*

That policy is the whole module. A retired video keeps its id, its URL, its
comments and its analytics history; it simply stops being visible. Every reason
to pull a video down - superseded by a better cut, a rights question, a factual
error - is served by private, and none of them are served better by destroying
the record. Re-publishing is one flip back.

There is deliberately NO delete path in this repo, and this file must not become
one. If a video genuinely has to be removed, that is a decision a human makes in
the YouTube UI, where the irreversibility is stated on screen.

The ledger keeps the entry and marks it retired rather than dropping the row:
the loop needs to know a slug was published once, or it will cheerfully queue it
again.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import ledger                                   # noqa: E402
import publish as P                             # noqa: E402
import upload as up                             # noqa: E402
from common import Stage, config, now, week_id  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Make a published video private.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug")
    g.add_argument("--video-id")
    ap.add_argument("--reason", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    led = ledger.load()
    rows = led["published"]
    match = [r for r in rows
             if (a.slug and r.get("slug") == a.slug)
             or (a.video_id and r.get("video_id") == a.video_id)]
    if not match:
        which = a.slug or a.video_id
        print(f"no published video matches {which!r}. Published slugs:")
        for r in rows:
            print(f"  {r.get('slug')}  {r.get('video_id')}")
        return 2
    row = match[0]
    vid = row.get("video_id")
    if not vid:
        print(f"{row.get('slug')} has no video_id recorded; nothing to retire.")
        return 2

    with Stage("retire", week_id(),
               zero_work_hint="No video matched, so nothing was changed.") as st:
        cfg = config()
        creds = up.load_credentials(cfg)
        if creds is None:
            st.named_stop("OAUTH_MISSING",
                          f"cannot retire {vid} without OAuth.",
                          unblock="Run auth/youtube_auth.py.")
        token = up.access_token(creds)

        before = P.read_status(token, vid)
        if a.dry_run:
            st.work(f"DRY RUN: would set {vid} ({row.get('slug')}) to private")
            print(f"  current status: {before}")
            return 0

        P.set_privacy(token, vid, "private")

        # Verify against YouTube rather than trusting the call: a 200 that did
        # not change anything is exactly the "runs but inert" failure.
        after = P.read_status(token, vid)
        got = after.get("privacy")
        if got != "private":
            st.named_stop(
                "RETIRE_NOT_APPLIED",
                f"asked YouTube to make {vid} private but it still reports "
                f"privacyStatus={got!r}.",
                detail={"before": before, "after": after},
                unblock="Check the video in YouTube Studio; the API accepted "
                        "the call but did not apply it.")
        st.work(f"{vid} ({row.get('slug')}) is now private")

        row["retired_at"] = now()
        row["retired_reason"] = a.reason or "no longer published"
        row["privacy"] = "private"
        led["updated"] = now()
        (LOOP / "state" / "ledger.json").write_text(
            json.dumps(led, indent=2) + "\n")
        st.work("recorded the retirement in the ledger (row kept, not dropped, "
                "so the loop will not re-queue this slug)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
