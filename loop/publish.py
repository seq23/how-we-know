"""Friday 09:00 — flip private uploads to scheduled/public, and feed the site.

Three hard preconditions, each of which is a named stop rather than a crash:

1. The circuit breaker is closed. One flag halts this stage and nothing else.
2. Every video being flipped has an **upload receipt** with a real video ID.
   A row with a dry-run receipt is never flipped — that is what "nothing goes
   public without a receipt proving it uploaded correctly" means mechanically.
3. Its render receipt says `healthy`. A one-frame MP4 that uploaded cleanly is
   still not a video.

The site is fed by writing `loop/site_feed.json`, not by editing `site/`. The
site build reads the feed; the loop does not reach into another component's
files to change them.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import breaker  # noqa: E402
import ledger  # noqa: E402
import upload as up  # noqa: E402
from common import LOOP, ROOT, Stage, config, now, read_json, write_json, week_id  # noqa: E402

QUEUE = LOOP / "render_queue.json"
FEED = LOOP / "site_feed.json"
API = "https://www.googleapis.com/youtube/v3/videos?part=status"


def set_privacy(token: str, video_id: str, privacy: str) -> None:
    body = json.dumps({"id": video_id,
                       "status": {"privacyStatus": privacy,
                                  "selfDeclaredMadeForKids": False}}).encode()
    req = urllib.request.Request(API, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8"})
    urllib.request.urlopen(req, timeout=60).read()


def main() -> None:
    cfg = config()
    week = week_id()
    breaker.guard("fri-publish")

    with Stage("fri-publish", week,
               zero_work_hint="No row carried an upload receipt with a video "
                              "ID. Thursday's upload lane produced nothing.") as st:
        q = read_json(QUEUE, default=None)
        if q is None:
            st.named_stop("NO_QUEUE", "loop/render_queue.json does not exist")

        eligible, blocked = [], {}
        for it in q["items"]:
            rp = it.get("upload_receipt")
            rr = it.get("render_receipt")
            if not rp:
                blocked[it["slug"]] = "no upload receipt"
                continue
            rec = read_json(ROOT / rp)
            if rec.get("dry_run") or not rec.get("video_id"):
                blocked[it["slug"]] = "upload receipt is a dry run (no video ID)"
                continue
            if not rr or not read_json(ROOT / rr).get("healthy"):
                blocked[it["slug"]] = "render receipt is not healthy"
                continue
            eligible.append((it, rec))

        for slug, why in blocked.items():
            st.note(f"{slug}: not flipped — {why}")

        if not eligible:
            st.named_stop(
                "NOTHING_PUBLISHABLE",
                "no video has a receipt proving it uploaded correctly, so "
                "nothing is being made public",
                detail=blocked,
                unblock="Run bin/loop-thursday.sh once OAuth exists. Until "
                        "then this stop is the correct outcome, not a failure.")

        creds = up.load_credentials(cfg)
        if creds and creds.get("unusable"):
            import sys as _s
            _s.path.insert(0, str(ROOT / "auth"))
            import tokens as auth
            st.named_stop(
                {"expired_refresh": "OAUTH_EXPIRED",
                 "no_token": "OAUTH_NOT_CONSENTED"}.get(creds["unusable"],
                                                        "OAUTH_UNUSABLE"),
                f"{len(eligible)} video(s) hold valid upload receipts but the "
                f"stored credential is not usable ({creds['unusable']}). They "
                f"stay private until it is fixed — which is the safe direction.",
                unblock=auth.stop_message(creds["unusable"]))
        if creds is None:
            st.named_stop(
                "OAUTH_MISSING",
                f"{len(eligible)} video(s) hold valid upload receipts but no "
                f"OAuth credentials are available to flip them public",
                unblock="Run .venv/bin/python auth/youtube_auth.py on the Mac, "
                        "or set the repo secrets. See docs/loop.md § OAuth.")

        token = up.access_token(creds)
        flipped = []
        for it, rec in eligible:
            try:
                set_privacy(token, rec["video_id"], "public")
            except urllib.error.HTTPError as e:
                st.note(f"{it['slug']}: flip failed "
                        f"{e.code} {e.read().decode('utf-8','ignore')[:300]}")
                continue
            it["privacy"] = "public"
            it["status"] = "published"
            it["published_at"] = now()
            ledger.record_published(it["slug"], it["question"],
                                    rec["video_id"], it["upload_receipt"])
            flipped.append(it)
            st.work(f"public: {it['slug']} -> {rec['video_id']}")

        if not flipped:
            st.named_stop("FLIP_FAILED",
                          "every privacy flip failed", detail=blocked)

        write_json(QUEUE, q)

        # ---- feed the site, without touching site/ ----------------------
        feed = read_json(FEED, default={"videos": []})
        known = {v["video_id"] for v in feed["videos"]}
        for it in flipped:
            vid = it.get("video_id") or ""
            if vid in known:
                continue
            feed["videos"].append({
                "slug": it["slug"], "question": it["question"],
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published_at": it["published_at"],
                "script": it["script"], "week": week,
            })
        feed["updated"] = now()
        feed["note"] = ("Written by loop/publish.py. The site build reads this; "
                        "the loop never edits site/ directly.")
        write_json(FEED, feed)
        st.work(f"updated loop/site_feed.json ({len(feed['videos'])} video(s))")


if __name__ == "__main__":
    main()
