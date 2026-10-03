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
import cadence

import datetime as _dt
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
READ = "https://www.googleapis.com/youtube/v3/videos"


def read_status(token: str, video_id: str) -> dict:
    """What YouTube actually says about this video right now."""
    q = urllib.parse.urlencode({"part": "status,snippet", "id": video_id})
    req = urllib.request.Request(f"{READ}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    items = data.get("items") or []
    if not items:
        return {"found": False}
    st = items[0].get("status", {})
    return {"found": True,
            "privacy": st.get("privacyStatus"),
            "upload_status": st.get("uploadStatus"),
            "rejection_reason": st.get("rejectionReason"),
            "made_for_kids": st.get("madeForKids"),
            "title": items[0].get("snippet", {}).get("title")}


def set_privacy(token: str, video_id: str, privacy: str,
                publish_at: str | None = None) -> None:
    """Flip a video, or schedule it.

    `publish_at` is an RFC3339 UTC timestamp. YouTube requires privacyStatus to
    stay `private` alongside it; the video goes public by itself at that moment.
    Passing publish_at with privacyStatus=public is rejected by the API.
    """
    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = privacy
    body = json.dumps({"id": video_id, "status": status}).encode()
    req = urllib.request.Request(API, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8"})
    urllib.request.urlopen(req, timeout=60).read()


def cancel_schedule(token: str, video_id: str) -> str | None:
    """Remove a pending publishAt. Returns the stamp it cleared, or None.

    A `publishAt` CANNOT BE CLEARED BY OMISSION, and this cost a real
    near-miss on 2026-09-05. A duplicate upload was retired -- set private,
    verified private -- and it kept its 2026-10-25 publishAt, so YouTube would
    have made it public on that date anyway, beside the copy that was supposed
    to air. "Retired" would have un-retired itself seven weeks later.

    Neither omitting the field nor sending it as an explicit `null` clears it:
    both return HTTP 200 and leave the stored value exactly as it was. The only
    thing that works is moving the video OFF private and back, which is what
    this does. Verified against the live API on both duplicates.
    """
    st = read_status_full(token, video_id)
    if not st.get("publishAt"):
        return None
    stamp = st["publishAt"]
    # Off private, then back. Each call is verified; a 200 that changed
    # nothing is exactly the failure this exists to catch.
    set_privacy(token, video_id, "unlisted")
    set_privacy(token, video_id, "private")
    after = read_status_full(token, video_id)
    if after.get("publishAt"):
        raise RuntimeError(
            f"{video_id} still carries publishAt={after['publishAt']} after "
            f"the unlisted round-trip. It would go public on that date.")
    # THE SECOND FLIP CAN BE ACCEPTED AND NOT APPLIED. 2026-10-03, unscheduling
    # qPnBKYAR3ps: both PUTs returned 200, publishAt was gone, and the video
    # read back UNLISTED - visible to anyone with the link, for a cut this
    # function exists to keep off the channel. One more private flip took.
    # Re-apply and re-read rather than trust the 200.
    if after.get("privacy") != "private":
        set_privacy(token, video_id, "private")
        after = read_status_full(token, video_id)
        if after.get("privacy") != "private":
            raise RuntimeError(
                f"{video_id} reports privacyStatus={after.get('privacy')!r} "
                f"after the unlisted round-trip; it should be private.")
    return stamp


def read_status_full(token: str, video_id: str) -> dict:
    """read_status() plus publishAt, which it does not return.

    Kept separate rather than widening read_status(), whose shape several
    stages already destructure.
    """
    q = urllib.parse.urlencode({"part": "status", "id": video_id})
    req = urllib.request.Request(f"{READ}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    items = data.get("items") or []
    if not items:
        return {"found": False}
    st = items[0].get("status", {})
    return {"found": True, "privacy": st.get("privacyStatus"),
            "publishAt": st.get("publishAt")}


def verify_scheduled_flips(st, cfg) -> None:
    """Every video whose publishAt has passed must actually be public.

    The counterpart to uploading private-with-a-date: YouTube owns the flip, so
    something has to check that it performed it. Reads the ledger, asks YouTube
    for the live status of every row whose scheduled time is in the past, and
    fails loudly on any that is still private.

    Rule 0: this examines rows and says how many. If the ledger holds no past
    due row at all it takes a NAMED STOP rather than exiting 0 quietly - a
    verifier that checked nothing has proved nothing.
    """
    import ledger as _led                                  # noqa: PLC0415
    import datetime as _d                                  # noqa: PLC0415

    rows = _led.load()["published"]
    now_utc = _d.datetime.now(_d.timezone.utc)
    due = []
    for r in rows:
        stamp = r.get("scheduled_publish_at")
        if not stamp:
            continue
        when = _d.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when <= now_utc:
            due.append((r, when))

    if not due:
        st.named_stop(
            "NO_FLIP_DUE_YET",
            f"{len(rows)} episode(s) are on the calendar and none has reached "
            f"its publishAt yet, so there is no flip to verify.",
            detail={"next": min((r.get("scheduled_publish_at") for r in rows
                                 if r.get("scheduled_publish_at")), default="")},
            unblock="Nothing is wrong. This lane verifies flips AFTER they are "
                    "due; the first one is at the timestamp above.")

    creds = up.load_credentials(cfg)
    if not creds or creds.get("unusable"):
        st.named_stop(
            "OAUTH_MISSING",
            f"{len(due)} scheduled flip(s) are due and cannot be verified "
            f"without OAuth.",
            unblock="Run .venv/bin/python auth/youtube_auth.py on the Mac, or "
                    "set the repo secrets.")
    token = up.access_token(creds)

    bad = []
    for r, when in due:
        vid = r.get("video_id")
        if not vid:
            continue
        got = read_status(token, vid)
        st.work(f"{r['slug']}: due {when:%Y-%m-%d %H:%M}Z, YouTube reports "
                f"{got.get('privacy')}")
        if got.get("privacy") != "public":
            bad.append(f"{r['slug']} ({vid}) was due at "
                       f"{when:%Y-%m-%dT%H:%M:%SZ} but YouTube still reports "
                       f"{got.get('privacy')!r}")

    if bad:
        st.named_stop(
            "SCHEDULED_FLIP_DID_NOT_HAPPEN",
            f"{len(bad)} of {len(due)} scheduled video(s) passed their publish "
            f"time and are still not public: " + "; ".join(bad),
            detail={"videos": bad},
            unblock="Check the credential's scopes first - videos.update needs "
                    "the full `youtube` scope and 403s silently without it. "
                    "Then flip by hand in YouTube Studio; the calendar already "
                    "says these aired.")
    st.note(f"verified {len(due)} scheduled flip(s); all public")


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

        # She will hand-publish the first few through YouTube Studio, both to
        # test the lock and to strengthen the pending compliance audit. Those
        # videos already exist and are already public; the loop records them
        # and moves on rather than trying to upload or flip them again.
        hand = [it for it in q["items"]
                if it.get("hand_published") or it.get("status") == "published"]
        for it in hand:
            if it.get("status") != "published":
                it["status"] = "published"
            if it.get("video_id"):
                ledger.record_published(it["slug"], it["question"],
                                        it["video_id"],
                                        it.get("upload_receipt", "hand-published"))
            st.note(f"{it['slug']}: already on the channel - not re-uploaded")

        eligible, blocked = [], {}
        for it in q["items"]:
            if it in hand:
                continue
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
            # NOT A STOP ANY MORE, because there is real work here and this
            # lane had stopped doing any.
            #
            # This branch used to raise NOTHING_PUBLISHABLE, and by 2026-09-04
            # it did so every single Friday. The reason is structural, not
            # transient: every episode is now uploaded PRIVATE with a
            # `publishAt` stamp and YouTube makes it public itself at that
            # moment, so nothing is ever left for a Friday flip to flip. The
            # ledger proves it - zero rows carry neither a schedule nor an air
            # date. A weekly lane that can never have anything to do is the
            # "runs but inert" defect, and its unblock text had already gone
            # stale ("once OAuth exists"; OAuth has existed since 2026-09-01).
            #
            # Adding the code to loop/stop_policy.json would have made it
            # silently green forever - an inert lane wearing a reassuring
            # label, which is the one thing that file's own header warns
            # against. So the lane is given the job the new model actually
            # needs doing: PROVE THE SCHEDULED FLIPS HAPPENED.
            #
            # That is not busywork. This repo has already been bitten by a
            # flip that failed silently - videos.update needs the full
            # `youtube` scope and 403s without it, and it stayed invisible for
            # weeks because the first video had been uploaded public directly.
            # A video whose publishAt passed and which is still private is
            # invisible in exactly the same way: the calendar says it aired,
            # the channel says nothing.
            return verify_scheduled_flips(st, cfg)

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
        # SPACE THE WEEK. This loop used to flip every eligible video at once, so
        # a cadence of 2/week meant both landing at 09:00 Friday - which is not a
        # cadence, it is a burst followed by six silent days. The algorithm reads
        # consistency, and a viewer who subscribes after one video should not get
        # the next one the same morning.
        #
        # The first goes public now; each subsequent one is scheduled 7/cadence
        # days out (3 days at cadence 2, 2 at cadence 3). Order follows
        # research/publish_order.json, which is already the ranking - so the
        # strongest video takes the live slot rather than whichever happened to
        # finish uploading first.
        per_week = max(1, int(cadence.effective()))
        spacing_days = max(1, round(7 / per_week))
        now = _dt.datetime.now(_dt.timezone.utc)

        flipped, locked, scheduled = [], [], []
        for n, (it, rec) in enumerate(eligible):
            publish_at = None
            if n:
                publish_at = (now + _dt.timedelta(days=n * spacing_days)) \
                    .replace(microsecond=0).isoformat().replace("+00:00", "Z")
            try:
                set_privacy(token, rec["video_id"], "public", publish_at)
                if publish_at:
                    it["status"] = "scheduled"
                    it["publish_at"] = publish_at
                    scheduled.append({"slug": it["slug"], "publish_at": publish_at})
                    st.note(f"{it['slug']}: scheduled for {publish_at}")
                    continue
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")[:300]
                if "forbidden" in body.lower() or e.code == 403:
                    locked.append({"slug": it["slug"],
                                   "video_id": rec["video_id"],
                                   "why": f"HTTP {e.code}: {body[:160]}"})
                    it["status"] = "locked-private"
                    st.note(f"{it['slug']}: flip REFUSED - {e.code}")
                    continue
                st.note(f"{it['slug']}: flip failed {e.code} {body}")
                continue

            # VERIFY. An unaudited project can accept the privacy PUT and leave
            # the video private anyway - the request succeeds and nothing is
            # public. Never report a video live on the strength of a 200.
            after = read_status(token, rec["video_id"])
            if after.get("privacy") != "public":
                locked.append({"slug": it["slug"], "video_id": rec["video_id"],
                               "why": f"the API accepted the flip but YouTube "
                                      f"still reports privacyStatus="
                                      f"{after.get('privacy')!r}",
                               "upload_status": after.get("upload_status"),
                               "rejection_reason": after.get("rejection_reason")})
                it["status"] = "locked-private"
                it["privacy"] = after.get("privacy")
                st.note(f"{it['slug']}: LOCKED - accepted but still "
                        f"{after.get('privacy')}")
                continue

            it["privacy"] = "public"
            it["status"] = "published"
            it["published_at"] = now()
            ledger.record_published(it["slug"], it["question"],
                                    rec["video_id"], it["upload_receipt"])
            flipped.append(it)
            st.work(f"public: {it['slug']} -> {rec['video_id']}")

        if locked:
            write_json(LOOP / "state" / "locked_uploads.json",
                       {"at": now(), "week": week, "locked": locked,
                        "meaning": "Google will not let this project's API "
                                   "uploads go public. Reported by Google as "
                                   "not appealable for an unaudited project.",
                        "workaround": "Publish these by hand in YouTube Studio. "
                                      "The loop will detect them as already "
                                      "public and stop trying."})

        if not flipped:
            st.named_stop(
                "UPLOADS_LOCKED_PRIVATE" if locked else "FLIP_FAILED",
                (f"{len(locked)} upload(s) cannot be made public: the project "
                 f"is not audited, so YouTube keeps API uploads private. "
                 f"NOTHING WENT LIVE." if locked
                 else "every privacy flip failed"),
                detail={"locked": locked, "blocked": blocked},
                unblock=("Publish these by hand in YouTube Studio - the loop "
                         "detects hand-published videos and will not re-upload "
                         "them. Longer term, complete the Google API "
                         "compliance audit. This is a detected condition, not "
                         "a silent success: no video is reported live unless "
                         "YouTube confirms privacyStatus=public."
                         if locked else "See the blocked reasons above."))

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
