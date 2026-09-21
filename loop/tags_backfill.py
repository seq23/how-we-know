"""Backfill derived tags and a hashtag line onto every live video — metadata only.

    .venv/bin/python loop/tags_backfill.py             # apply
    .venv/bin/python loop/tags_backfill.py --dry-run    # show, write nothing

## Why this exists

Owner instruction, 2026-09-21: every video on the channel carried the same
seven deep-sea tags and no hashtags at all — including the 18
materials-and-manufacturing episodes, tagged "marine biology" like everything
else. `loop/upload.py` and `loop/shorts_lane.py` now derive tags and
hashtags per episode, from `loop/discovery.py`, on every NEW upload; this
lane rewrites the back catalogue to match, once, and then runs daily in
`.github/workflows/loop-reach.yml` so a future drift self-heals.

"All videos" means episodes AND Shorts: a Short's tags and hashtags are its
parent episode's plus "shorts" / "#Shorts" — the same value
`loop/shorts_lane.py:build_payload` computes for a new one, recomputed here
rather than read off the cut file, so the two can never drift apart.

## Three rules that make this safe to run unattended

1. **Metadata only, never privacy.** This module never calls `videos.update`
   with `status` and never imports `loop/publish.py`. A video already public
   stays public; a video still private stays private.
2. **Read, merge, write back whole.** Every write goes through
   `loop/ytmeta.py:merge_snippet`, which reads the CURRENT live snippet
   immediately before writing — the same discipline `loop/localize.py` and
   `loop/chapters_backfill.py` already follow, because `videos.update`
   REPLACES the parts you name rather than patching them. Any existing
   localizations are carried in the SAME write, their descriptions gaining
   the same English hashtag line with no model call — the hashtag line is
   VERBATIM, exactly as `loop/localize.py:translate()` treats it.
3. **Idempotent.** A video whose live tags and hashtag line already match
   the computed ones is skipped before any write — no quota spent, safe to
   run twice, or on a cron.

**Tags and hashtags are DERIVED, not curated.** Any hand edit made to a
video's tags in YouTube Studio is replaced by this lane — there is one
source of truth (the script, `loop/config.json`'s `discovery` block, and
`loop/discovery.py`), never two.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))

import discovery                                   # noqa: E402
import domains                                      # noqa: E402
import quota                                        # noqa: E402
import upload as up                                 # noqa: E402
import ytmeta                                        # noqa: E402
from common import Stage, config, read_json, week_id  # noqa: E402

LANE = "tags-backfill"
SHORTS_LEDGER = LOOP / "state" / "shorts_ledger.json"


def _shorts_live() -> list[dict]:
    d = read_json(SHORTS_LEDGER, default={"published": []})
    return [r for r in d.get("published", []) if r.get("video_id")]


def wanted_for_episode(slug: str) -> tuple[list[str], list[str]] | None:
    """(tags, hashtags) for one episode, or None if it cannot be resolved."""
    script = ROOT / "scripts" / f"{slug}.md"
    if not script.exists():
        return None
    domain = domains.domain_of_slug(slug)
    if not domain:
        return None
    text = script.read_text(encoding="utf-8")
    return discovery.tags_for(slug, text, domain), discovery.hashtags_for(slug, text, domain)


def wanted_for_short(slug: str) -> tuple[list[str], list[str]] | None:
    """(tags, hashtags) for a Short cut from `slug`'s episode — same shape
    `loop/shorts_lane.py:build_payload` computes for a brand-new one."""
    base = wanted_for_episode(slug)
    if base is None:
        return None
    ep_tags, ep_hashtags = base
    tags, total = [], 0
    for t in ["shorts", *ep_tags]:
        if total + len(t) + 1 > discovery.TAG_TOTAL_MAX:
            continue
        tags.append(t)
        total += len(t) + 1
    hashtags = ["#Shorts", *ep_hashtags][:discovery.HASHTAG_MAX]
    return tags, hashtags


def _rewrite_localizations(localizations: dict, hashtags: list[str]) -> dict:
    out = {}
    for lang, loc in localizations.items():
        desc = loc.get("description") or ""
        out[lang] = {**loc,
                    "description": discovery.add_hashtag_line(
                        discovery.strip_hashtag_line(desc), hashtags)[:up.DESC_MAX]}
    return out


def run(limit: int = 200, dry_run: bool = False) -> int:
    config()
    with Stage(LANE, week_id(),
               zero_work_hint="Every live video's tags and hashtag line "
                              "already match loop/discovery.py — nothing to "
                              "backfill.") as st:
        rows = ([("episode", r["slug"], r["video_id"]) for r in ytmeta.live_videos()]
                + [("short", r["slug"], r["video_id"]) for r in _shorts_live()])
        if not rows:
            st.named_stop("NOTHING_PUBLISHED",
                          "no live episode or Short is recorded",
                          unblock="Upload an episode or cut a Short first.")

        creds = up.load_credentials(config())
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, config())
            st.named_stop(code, msg, unblock=unblock)
        token = up.access_token(creds)

        touched, skipped, no_domain, spent = 0, 0, [], 0
        for kind, slug, vid in rows[:limit]:
            wanted = (wanted_for_short(slug) if kind == "short"
                     else wanted_for_episode(slug))
            if wanted is None:
                no_domain.append(slug)
                st.note(f"{slug}: no script on disk or no known domain — "
                        f"left alone, not guessed at")
                continue
            want_tags, want_hashtags = wanted
            want_line = discovery.hashtag_line(want_hashtags)

            current = ytmeta.get_video(token, vid)
            spent += quota.VIDEO_READ
            if not current or not current.get("snippet"):
                st.note(f"{slug}: videos.list returned nothing for {vid}")
                continue
            snippet = current["snippet"]
            live_tags = snippet.get("tags") or []
            live_desc = snippet.get("description") or ""
            live_line = live_desc.split("\n")[-1] if live_desc else ""

            if live_tags == want_tags and live_line == want_line:
                skipped += 1
                continue

            new_desc = discovery.add_hashtag_line(
                discovery.strip_hashtag_line(live_desc), want_hashtags)[:up.DESC_MAX]

            if dry_run:
                st.work(f"DRY RUN would rewrite {kind} {slug} ({vid}): "
                        f"{len(live_tags)} -> {len(want_tags)} tag(s), "
                        f"hashtag line {live_line!r} -> {want_line!r}")
                continue

            merged = ytmeta.merge_snippet(snippet, tags=want_tags,
                                          description=new_desc)
            localizations = _rewrite_localizations(
                current.get("localizations") or {}, want_hashtags)

            body: dict = {"id": vid, "snippet": merged}
            part = "snippet"
            if localizations:
                body["localizations"] = localizations
                part = "snippet,localizations"
            req = urllib.request.Request(
                f"{ytmeta.VIDEOS}?part={part}", data=json.dumps(body).encode(),
                method="PUT",
                headers={"Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=UTF-8"})
            with urllib.request.urlopen(req, timeout=60) as r:
                r.read()
            spent += quota.VIDEO_UPDATE
            touched += 1
            st.work(f"{kind} {slug} ({vid}): rewrote "
                    f"{len(live_tags)} -> {len(want_tags)} tag(s) and the "
                    f"hashtag line"
                    + (f", carrying {len(localizations)} localization(s)"
                       if localizations else ""))

        if spent:
            quota.spend(spent, LANE)
            st.note(f"spent {spent} quota units. {quota.report()}")
        if no_domain:
            st.note(f"{len(no_domain)} video(s) had no script on disk or no "
                    f"known domain and were left alone: {no_domain}")
        if touched == 0 and skipped == 0 and not dry_run:
            st.named_stop(
                "TAGS_BACKFILL_INERT",
                "authenticated and rewrote no video's tags and confirmed "
                "none already correct",
                detail={"no_domain": no_domain},
                unblock="Check loop/state/ledger.json and "
                        "loop/state/shorts_ledger.json against YouTube "
                        "Studio; every live video should have either "
                        "matching tags or appear in no_domain above.")
        st.note(f"{touched} rewritten, {skipped} already correct, "
                f"{len(no_domain)} had no resolvable domain")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
