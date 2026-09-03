"""Backfill corrected chapters onto videos already published — metadata only.

    .venv/bin/python loop/chapters_backfill.py             # apply
    .venv/bin/python loop/chapters_backfill.py --dry-run    # show, write nothing

## Why this exists

`loop/upload.py:build_chapters()` now prefers `captions/<slug>.chapters.txt`
(real timing) and, failing that, a corrected derivation from the script that
drops the "Title card" chapter and merges any gap under YT_MIN_CHAPTER_S
(10.0s). That only fixes what gets uploaded FROM NOW ON. Every video already
live carries the OLD, broken chapter list in its description — drifted
timestamps, and on 11 of 20 episodes a sub-10-second "Title card" chapter
that makes YouTube discard the entire list, silently, with no error anywhere.

This lane rewrites the `Chapters` block of each live video's description to
the corrected list, via `videos.update`, and touches NOTHING else.

## Three rules that make this safe to run unattended

1. **Metadata only, never privacy.** This module never calls
   `videos.update` with `status` and never imports `loop/publish.py`. A video
   already public stays public; a video still private stays private. Chapters
   are the only thing that changes.
2. **Read, merge, write back whole.** Every write goes through
   `loop/ytmeta.py:merge_snippet`, which reads the CURRENT live snippet
   immediately before writing and refuses to send a partial one — the same
   discipline `loop/localize.py` already follows, because `videos.update`
   REPLACES the parts you name rather than patching them.
3. **Idempotent.** The description's `Chapters` block is compared to the
   freshly computed one BEFORE any network write. Identical -> skipped, no
   quota spent, safe to run twice, three times, or on a cron. Only a video
   whose live chapters actually differ from the computed list is touched.

A description with no recognisable `Chapters` block (an old format, or a hand
edit in Studio) is left alone and reported, never guessed at — inventing a
Chapters section in a description that never had one is a bigger change than
this lane is allowed to make unsupervised.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))

import quota                                      # noqa: E402
import upload as up                                # noqa: E402
import ytmeta                                      # noqa: E402
from common import Stage, config, week_id          # noqa: E402

LANE = "chapters-backfill"

CHAPTERS_BLOCK = re.compile(r"(^|\n)Chapters\n((?:.*\n)*?)(\n|\Z)")


def chapters_block_of(description: str) -> tuple[str, str] | None:
    """(full_matched_block, chapter_lines) or None if no `Chapters` block."""
    m = CHAPTERS_BLOCK.search(description)
    if not m:
        return None
    return m.group(0), m.group(2)


def replace_chapters(description: str, new_chapters: list[str]) -> str | None:
    """Swap ONLY the chapter lines inside an existing `Chapters` block.

    Returns None if the description has no recognisable block — the caller
    must treat that as "cannot safely backfill", not as "nothing to do".
    """
    found = chapters_block_of(description)
    if found is None:
        return None
    block, _ = found
    lead, trail = block[:1], block[-1:] if block.endswith("\n") else ""
    new_block = lead + "Chapters\n" + "\n".join(new_chapters) + "\n\n"
    return description[:description.index(block)] + new_block + \
        description[description.index(block) + len(block):]


def run(limit: int = 50, dry_run: bool = False) -> int:
    config()
    with Stage(LANE, week_id(),
               zero_work_hint="Every live video's Chapters block already "
                              "matches loop/upload.py:build_chapters() — "
                              "nothing to backfill.") as st:
        live = ytmeta.live_videos()
        if not live:
            st.named_stop("NOTHING_PUBLISHED",
                          "loop/state/ledger.json lists no live video",
                          unblock="Upload an episode first.")

        creds = up.load_credentials(config())
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, config())
            st.named_stop(code, msg, unblock=unblock)
        token = up.access_token(creds)

        touched, skipped, no_block, spent = 0, 0, [], 0
        for row in live[:limit]:
            slug, vid = row["slug"], row["video_id"]
            script = ROOT / "scripts" / f"{slug}.md"
            if not script.exists():
                st.note(f"{slug}: no script on disk, skipped")
                continue
            wanted = up.build_chapters(slug, script.read_text(encoding="utf-8"))
            if not wanted:
                st.note(f"{slug}: no chapters computed, nothing to backfill")
                continue

            current = ytmeta.get_video(token, vid, part="snippet")
            spent += quota.VIDEO_READ
            if not current or not current.get("snippet"):
                st.note(f"{slug}: videos.list returned nothing for {vid}")
                continue
            desc = current["snippet"].get("description") or ""

            found = chapters_block_of(desc)
            if found is None:
                no_block.append(slug)
                st.note(f"{slug}: description has no recognisable Chapters "
                        f"block — left alone, not guessed at")
                continue
            _, live_lines = found
            live_list = [l for l in live_lines.split("\n") if l.strip()]
            if live_list == wanted:
                skipped += 1
                continue          # already correct — no write, no quota spent

            new_desc = replace_chapters(desc, wanted)
            if new_desc is None or len(new_desc) > up.DESC_MAX:
                st.note(f"{slug}: computed description would be invalid "
                        f"({'too long' if new_desc else 'no block'}), skipped")
                continue

            if dry_run:
                st.work(f"DRY RUN would rewrite chapters for {slug} ({vid}): "
                        f"{len(live_list)} -> {len(wanted)} chapter(s)")
                continue

            merged = ytmeta.merge_snippet(current["snippet"],
                                          description=new_desc)
            import json, urllib.request                    # noqa: PLC0415
            body = json.dumps({"id": vid, "snippet": merged}).encode()
            req = urllib.request.Request(
                f"{ytmeta.VIDEOS}?part=snippet", data=body, method="PUT",
                headers={"Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=UTF-8"})
            with urllib.request.urlopen(req, timeout=60) as r:
                r.read()
            spent += quota.VIDEO_UPDATE
            touched += 1
            st.work(f"{slug} ({vid}): rewrote chapters, "
                    f"{len(live_list)} -> {len(wanted)} chapter(s)")

        if spent:
            quota.spend(spent, LANE)
            st.note(f"spent {spent} quota units. {quota.report()}")
        if no_block:
            st.note(f"{len(no_block)} video(s) had no recognisable Chapters "
                    f"block and were left alone: {no_block}")
        if touched == 0 and skipped == 0 and not dry_run:
            st.named_stop(
                "CHAPTERS_BACKFILL_INERT",
                "authenticated and rewrote no video's chapters and confirmed "
                "none already correct",
                detail={"no_block": no_block},
                unblock="Check loop/state/ledger.json against YouTube Studio; "
                        "every live video should have either a matching "
                        "Chapters block or appear in no_block above.")
        st.note(f"{touched} rewritten, {skipped} already correct, "
                f"{len(no_block)} had no recognisable block")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
