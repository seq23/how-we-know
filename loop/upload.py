"""Thursday 02:00, on the Mac — upload each rendered video as PRIVATE.

Built end to end. It resolves credentials, builds the real request body from
the script's own metadata, and calls the YouTube Data API resumable upload.

**Google Cloud OAuth does not exist yet.** When credentials are absent this
takes a NAMED STOP — never a crash, never a silent skip — and still does its
real work: it composes and writes every video's metadata payload to
`loop/receipts/<week>-<slug>-payload.json`, so the moment credentials appear the
first run has nothing left to figure out. It also writes dry-run receipts, so
the handoff to Friday is exercised on a normal week rather than for the first
time on the day it matters.

Credentials, when they exist (repo secrets or a local `.env`, both gitignored):
    YT_OAUTH_CLIENT_JSON     the OAuth client, as JSON
    YT_OAUTH_REFRESH_TOKEN   a refresh token for the channel account

Nothing here ever sets a video public. The public flip is a separate stage,
gated on a receipt, and it runs on Friday.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))

import tokens as auth  # noqa: E402
import breaker  # noqa: E402
import discovery  # noqa: E402
import domains  # noqa: E402
import receipt as receipts  # noqa: E402
from common import (LOOP, RECEIPTS, ROOT, Stage, config, now,  # noqa: E402
                    read_json, week_id, write_json)

QUEUE = LOOP / "render_queue.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status,paidProductPlacementDetails")

# YouTube's own limits. Exceeding them is a 400 at 3am, so they are enforced here.
TITLE_MAX, DESC_MAX, TAG_TOTAL_MAX = 100, 5000, 400


def load_credentials(cfg) -> dict | None:
    """Return credentials, or None. Never raises: absence is an expected state.

    Two sources, in order:
      1. `.secrets/` on the Mac, via `auth/tokens.py` — the normal path, set up
         once by `auth/youtube_auth.py`.
      2. Repo-secret environment variables, for the Actions-side publish stage.
    """
    # LOOP_DRY_RUN means "behave exactly as an un-credentialed machine would".
    # Stripping env vars is not enough - .secrets/ is on disk and auth.load()
    # reads it, so a test that meant to run credential-less was in fact running
    # fully authorised against the live channel. Refusing the credential here is
    # what makes every downstream lane take its real, named, un-credentialed
    # path instead.
    if DRY_RUN:
        return None

    res = auth.load()
    if res["status"] == "ok":
        # `scopes` is carried through because the caption lane needs to know,
        # BEFORE it spends 400 units, whether this grant includes force-ssl.
        # A 403 after the fact is the same information at 400x the price, and
        # it arrives as a traceback rather than as a named stop.
        return {"access_token": res["access_token"], "source": "secrets",
                "scopes": res.get("scopes") or [],
                "refresh_token_age_days": res.get("refresh_token_age_days")}
    if res["status"] in ("no_token", "expired_refresh", "error"):
        # A present-but-unusable credential is NOT the same as no credential.
        # Carry the reason so the caller can name the right stop.
        return {"unusable": res["status"], "source": "secrets"}

    env = os.environ
    dotenv = ROOT / ".env"
    if dotenv.exists() and not env.get("LOOP_NO_DOTENV"):
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
    client_raw = env.get(cfg["credentials"]["youtube_oauth_client_env"], "").strip()
    refresh = env.get(cfg["credentials"]["youtube_oauth_refresh_env"], "").strip()
    if not client_raw or not refresh:
        return None
    try:
        client = json.loads(client_raw)
    except json.JSONDecodeError:
        return None
    c = client.get("installed") or client.get("web") or client
    if not c.get("client_id") or not c.get("client_secret"):
        return None
    return {"client_id": c["client_id"], "client_secret": c["client_secret"],
            "refresh_token": refresh, "source": "env"}


def credential_stop(creds, cfg) -> tuple[str, str, str]:
    """`(code, message, unblock)` for a lane that has no usable credential.

    One wording, shared. The library lane and the cloud lane both ran into
    `access_token(None)` raising AttributeError — a traceback where a named,
    actionable stop belongs — and each was about to invent its own message for
    the same three states.
    """
    if creds and creds.get("unusable"):
        code = {"expired_refresh": "OAUTH_EXPIRED",
                "no_token": "OAUTH_NOT_CONSENTED"}.get(creds["unusable"],
                                                       "OAUTH_UNUSABLE")
        return (code,
                f"the stored credential is not usable ({creds['unusable']}). "
                f"Not retried — retrying an invalid_grant never succeeds.",
                auth.stop_message(creds["unusable"]))
    c = cfg["credentials"]["youtube_oauth_client_env"]
    r = cfg["credentials"]["youtube_oauth_refresh_env"]
    return ("OAUTH_MISSING",
            "no YouTube credential is available on this machine",
            f"On the Mac: .venv/bin/python auth/youtube_auth.py. "
            f"In GitHub Actions there is no .secrets/, so the lane reads the "
            f"repo secrets {c} and {r} — set both "
            f"(see docs/CLOUD-UPLOAD-SETUP.md) and confirm the workflow step "
            f"passes them through as env.")


def access_token(creds: dict) -> str:
    """Resolve a bearer token from whichever credential shape we were handed."""
    if creds.get("access_token"):
        return creds["access_token"]
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"], "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


# ------------------------------------------------------------------ metadata

# --- the dry-run guard ----------------------------------------------------
# loop/tests/test_named_stops.py EXECUTES this module with live credentials to
# check that a blocked lane names its stop. That was harmless only while the
# lane had nothing to do. On 2026-09-01 a library fallback was added here, the
# test ran, the fallback found a finished episode, and it UPLOADED IT
# (MAV4PF056RA) - a real write to a real channel, from a test.
#
# The lesson is not "be careful with tests". It is that a module which performs
# irreversible external writes must be able to be asked not to, and every test
# that runs it must ask. LOOP_DRY_RUN=1 suppresses every network WRITE while
# leaving all the reads, the payload composition and the stop logic intact -
# which is exactly what the test is there to exercise.
DRY_RUN = os.environ.get("LOOP_DRY_RUN") == "1"


# YouTube silently discards the ENTIRE chapter list if any one chapter is
# under 10 seconds. Matches visuals/captions.py's own YT_MIN_CHAPTER_S, which
# is the actual source of truth once captions/<slug>.chapters.txt exists.
YT_MIN_CHAPTER_S = 10.0


def _parse_ts(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def _fmt_ts(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _enforce_min_gap(rows: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop any chapter whose gap to the NEXT one is under YT_MIN_CHAPTER_S.

    Merging forward (dropping the short chapter rather than its neighbour)
    keeps the first chapter at 0:00, which YouTube also requires, and keeps
    every surviving label attached to real content rather than shifting a
    later label's start time.
    """
    if not rows:
        return rows
    out = [rows[0]]
    for secs, label in rows[1:]:
        if secs - out[-1][0] < YT_MIN_CHAPTER_S:
            continue          # too close to the previous chapter — drop it
        out.append((secs, label))
    # A dropped final chapter can leave the second-to-last one under the
    # floor against nothing after it; that is fine — nothing follows it to
    # collide with, so its own duration is however long the video runs.
    return out


def build_chapters(slug: str, script_text: str) -> list[str]:
    """The chapter list actually sent to YouTube, timing-correct.

    PREFERRED: `captions/<slug>.chapters.txt`, which visuals/captions.py
    derives from the real caption timing (not the script's ESTIMATED
    timestamps) and already enforces YT_MIN_CHAPTER_S. That is "the computed
    file" — loop/upload.py used to regex `## Chapters` out of the script
    instead and ignore it, which is how ep08 says 7:48 in the script for a
    render that actually lands the chapter at 8:45, and how 11 of 20 scripts
    ship a sub-10-second chapter that makes YouTube discard the WHOLE list.

    FALLBACK, only when that file does not exist yet: the script's own
    `## Chapters` section, with the same two defects corrected in place —
    the "Title card" chapter is dropped (it exists to mark a beat in the
    script, not something a viewer would ever seek to) and any chapter under
    YT_MIN_CHAPTER_S from its neighbour is merged away rather than shipped.
    This keeps upload correct even before a caption file has been generated
    for a given episode.
    """
    computed = ROOT / "captions" / f"{slug}.chapters.txt"
    rows: list[tuple[int, str]] = []
    if computed.exists():
        for line in computed.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            mm = re.match(r"(\d{1,2}(?::\d{2}){1,2})\s+(.*)", line)
            if mm:
                rows.append((_parse_ts(mm.group(1)), mm.group(2).strip()))
    else:
        ch = re.search(r"## Chapters\s*\n(.*?)(\n## |\Z)", script_text, re.S)
        if ch:
            for line in ch.group(1).splitlines():
                mm = re.match(r"\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)", line)
                if not mm:
                    continue
                label = mm.group(2).strip()
                if label == "Title card":
                    continue
                rows.append((_parse_ts(mm.group(1)), label))
        rows = _enforce_min_gap(rows)
    if rows and rows[0][0] != 0:
        rows[0] = (0, rows[0][1])          # YouTube requires the first at 0:00
    return [f"{_fmt_ts(secs)} {label}" for secs, label in rows]


def build_payload(item: dict) -> dict:
    """Compose the video's YouTube metadata from the script itself.

    Every line comes from the script or from `loop/config.json`. Nothing is
    invented here — the same rule the render pipeline enforces on screen.
    """
    path = ROOT / item.get("work_copy", item["script"])
    text = path.read_text() if path.exists() else (ROOT / item["script"]).read_text()

    # Sentence case. The question arrives from research/publish_order.json, whose
    # `query` field is a lowercase search string - it is a query, not a headline.
    # Uploading it verbatim put "what is the deepest part of the ocean?" on the
    # channel, which the site's own video contract caught by asserting the video
    # title equals the question record. Fix it here, at upload time, because
    # getting it right once is cheaper than correcting it after.
    #
    # CORRECTION, 2026-09-02. This comment used to end: "the credential holds
    # youtube.upload and youtube.readonly only, so a title cannot be corrected
    # afterwards - videos.update returns 403 without the broader youtube scope."
    # That was true when it was written and has been false since 2026-09-01,
    # when the full `https://www.googleapis.com/auth/youtube` scope was added to
    # auth/tokens.py SCOPES and granted. Checked again on 2026-09-02 against
    # .secrets/youtube_token.json, which records all four scopes as granted:
    # youtube, youtube.upload, youtube.readonly, yt-analytics.readonly.
    #
    # So a title CAN be corrected afterwards, today, with no re-consent —
    # loop/publish.py and loop/retire.py already call videos.update, and
    # loop/localize.py writes the snippet back whole. The stale sentence had
    # already cost one researcher a wrong recommendation; it is left quoted
    # here so the next person recognises it if they meet it in an old branch.
    #
    # (Captions are the different case: captions.insert needs force-ssl, which
    # the plain youtube scope does NOT cover. See loop/captions_lane.py.)
    title = item["question"].strip().rstrip("?")
    title = (title[:1].upper() + title[1:] if title else title) + "?"
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1].rsplit(" ", 1)[0] + "?"

    answer = ""
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)\n\s*\n", text, re.S)
    if m:
        answer = re.sub(r"\s+", " ", m.group(1)).strip()

    slug = item.get("slug") or path.stem
    chapters = build_chapters(slug, text)

    sources = []
    sb = re.search(r"## Sources\s*\n(.*?)(\n## |\Z)", text, re.S)
    if sb:
        for line in sb.group(1).splitlines():
            if line.strip().startswith("-"):
                sources.append(line.strip()[1:].strip())

    parts = [answer, ""]
    if chapters:
        parts += ["Chapters", *chapters, ""]
    if sources:
        parts += ["Sources — every figure in this video traces to one of these:",
                  *[f"• {s}" for s in sources], ""]
    parts += ["Evidence-first explainers. Every on-screen number comes from a "
              "named public source stated in the narration."]
    description = "\n".join(parts)[:DESC_MAX]

    # Tags and hashtags are DERIVED per episode from its own domain and
    # subject — owner instruction, 2026-09-21. See loop/discovery.py: no
    # fixed list here any more, and a materials episode no longer ships
    # tagged "marine biology".
    domain = domains.domain_of_slug(slug)
    tags = discovery.tags_for(slug, text, domain)
    hashtags = discovery.hashtags_for(slug, text, domain)
    description = discovery.add_hashtag_line(description, hashtags)[:DESC_MAX]

    return {
        # defaultLanguage is NOT cosmetic and NOT optional here.
        #
        # Observed in the owner's YouTube Studio on 2026-09-02: with the video
        # language unset, the per-video Languages page renders only a "Set
        # language" dropdown and a disabled Confirm button. No subtitle upload,
        # no translations table, no dubbing control at all. Unset language gates
        # the ENTIRE subtitles-and-translation surface, and all 16 videos were
        # in that state. The API mirrors it: videos.update rejects
        # `localizations` outright unless snippet.defaultLanguage is set.
        #
        # The value is exactly "en", never "en-US". "English" (en) is what the
        # Studio UI now holds as the channel default, and a channel where some
        # videos say en and others en-US is an inconsistency nothing would ever
        # report. One canonical value; loop/validate.py V18 asserts it.
        #
        # defaultAudioLanguage says the narration itself is English, which is
        # what an auto-dub would be translating FROM.
        "snippet": {"title": title, "description": description, "tags": tags,
                    "categoryId": "27",    # 27 = Education
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        # private is the design, not a limitation to work around: an
        # unverified Google app has uploads FORCED private anyway, and the loop
        # flips to public on Friday only against a receipt.
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "embeddable": True, "license": "youtube",
                   # OWNER DECISION, 14 Sep 2026: every video allows embedding and answers
                   # YouTube's "altered or synthetic content" question NO. Set at upload so no
                   # video ever needs the two fields fixed by hand in Studio again; the same
                   # two fields are asserted on the whole back catalogue by loop/video_settings.py.
                   "containsSyntheticMedia": False},
        # And "paid promotion" answered No, same decision, same day.
        "paidProductPlacementDetails": {"hasPaidProductPlacement": False},
    }


# -------------------------------------------------------------------- upload

def resumable_upload(token: str, payload: dict, video: Path) -> str:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(UPLOAD_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(video.stat().st_size),
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        session = r.headers["Location"]
    with video.open("rb") as fh:
        put = urllib.request.Request(session, data=fh.read(), method="PUT",
                                     headers={"Content-Type": "video/mp4"})
        with urllib.request.urlopen(put, timeout=3600) as r2:
            return json.loads(r2.read())["id"]


def main() -> None:
    cfg = config()
    week = week_id()
    breaker.guard("thu-upload")   # exits 3 if publishing is halted

    with Stage("thu-upload", week,
               zero_work_hint="No rendered video carried a healthy render "
                              "receipt. Tuesday produced nothing to upload.") as st:
        q = read_json(QUEUE, default=None)
        if q is None:
            st.named_stop("NO_QUEUE", "loop/render_queue.json does not exist")

        ready = [it for it in q["items"]
                 if it.get("status") == "rendered" and it.get("render_receipt")]

        # FALL BACK TO THE LIBRARY ON DISK - by DELEGATING, not duplicating.
        # The weekly queue records what THIS WEEK drafted. It is silent about a
        # back catalogue, so an empty queue is not an empty channel: on
        # 2026-09-01 it held two unrendered rows while thirteen finished renders
        # sat in renders/.
        #
        # loop/backfill.py owns library uploads end to end - it picks the slug in
        # combined_score order, assigns the next cadence slot, attaches the
        # thumbnail and WRITES THE LEDGER. Re-implementing any of that here would
        # recreate the exact defect this repo keeps hitting: two components each
        # keeping their own list with no link between them. The first draft of
        # this fallback did precisely that, uploading without a ledger row, so
        # the daily backfill agent would have re-uploaded the same episode hours
        # later. One writer, one record.
        # THE FALLBACK IS GONE, DELIBERATELY, AND THIS IS WHY.
        #
        # It used to delegate to `backfill.run(limit=1)` here. From 2026-09-01
        # library uploads belong to the CLOUD lane
        # (.github/workflows/loop-upload-cloud.yml -> loop/cloud_upload.py),
        # which draws from the same ranked order and the same ledger.
        #
        # Two machines cannot both hold that job. This one runs from launchd at
        # 02:00 against whatever `loop/state/ledger.json` was last PULLED —
        # launchd does not `git pull` — so a Thursday run could not see an
        # episode the cloud lane uploaded on Monday, and would upload it again.
        # A duplicate video on a channel whose whole argument is a predictable
        # cadence is not a recoverable error: the second one is public before
        # anyone looks.
        #
        # The Mac keeps the WEEKLY lane, which uploads what this week rendered
        # against a queue row. It no longer touches the back catalogue.
        if not ready:
            pending = []
            try:
                import backfill
                pending = [s for s, _, _ in backfill.library_pending()]
            except Exception:                     # noqa: BLE001
                pass
            st.named_stop(
                "NOTHING_RENDERED",
                "no queue row has a healthy render receipt. "
                + (f"{len(pending)} finished episode(s) are waiting, but the "
                   f"back catalogue is the CLOUD lane's job now, not this "
                   f"one." if pending else
                   "The finished library holds nothing unpublished either."),
                detail={"statuses": {i["slug"]: i.get("status")
                                     for i in q["items"]},
                        "library_pending": pending},
                unblock=("Run bin/loop-tuesday.sh to render this week's "
                         "episode. For the back catalogue: push it with "
                         "bin/push-to-r2.sh and let the daily "
                         "loop-upload-cloud workflow take it — never run "
                         "loop/backfill.py alongside that workflow."))

        # Payloads are real work and are composed whether or not we can upload.
        payloads = {}
        for it in ready:
            p = build_payload(it)
            payloads[it["slug"]] = p
            write_json(RECEIPTS / f"{week}-{it['slug']}-payload.json", p)
            st.work(f"composed upload payload for {it['slug']} "
                    f"({len(p['snippet']['description'])} chars, "
                    f"{len(p['snippet']['tags'])} tags)")

        creds = load_credentials(cfg)

        # A credential that is PRESENT but UNUSABLE is a different stop from a
        # credential that was never created, and it has a different fix. Both
        # are expected states; neither is a crash.
        if creds and creds.get("unusable"):
            for it in ready:
                receipts.upload_receipt(it["slug"], week, video_id="",
                                        privacy="private", dry_run=True)
            code = {"expired_refresh": "OAUTH_EXPIRED",
                    "no_token": "OAUTH_NOT_CONSENTED"}.get(
                        creds["unusable"], "OAUTH_UNUSABLE")
            st.named_stop(
                code,
                f"{len(ready)} video(s) are ready but the stored credential is "
                f"not usable ({creds['unusable']}). Not retried — retrying an "
                f"invalid_grant never succeeds.",
                detail={"ready": [i["slug"] for i in ready]},
                unblock=auth.stop_message(creds["unusable"]))

        if creds is None:
            for it in ready:
                receipts.upload_receipt(it["slug"], week, video_id="",
                                        privacy="private", dry_run=True)
            st.named_stop(
                "OAUTH_MISSING",
                f"{len(ready)} video(s) are rendered, validated and have their "
                f"metadata composed, but no Google Cloud OAuth credentials "
                f"exist, so nothing was uploaded. This is the one lane blocked "
                f"on a secret only the owner can create.",
                detail={"ready": [i["slug"] for i in ready],
                        "needs": [cfg["credentials"]["youtube_oauth_client_env"],
                                  cfg["credentials"]["youtube_oauth_refresh_env"]]},
                unblock="Create a Google Cloud project, enable the YouTube Data "
                        "API v3, make an OAuth desktop client, authorise the "
                        "channel account once, then put the client JSON and the "
                        "refresh token in .env on the Mac (gitignored). "
                        "See docs/loop.md § OAuth.")

        token = access_token(creds)

        # Confirm WHICH channel this token owns before sending a single byte.
        # Uploading four videos to the wrong channel is silent and expensive.
        ch = auth.channel(token)
        if not ch["ok"]:
            st.named_stop("CHANNEL_UNREADABLE",
                          f"could not confirm the authorised channel: "
                          f"{ch['detail']}",
                          unblock="Run: .venv/bin/python auth/check_auth.py")
        if not ch["matches_expected"]:
            st.named_stop(
                "WRONG_CHANNEL",
                f"the credential authorises '{ch['title']}' "
                f"({ch['handle'] or 'no handle'}), not {auth.EXPECTED_HANDLE}. "
                f"Nothing was uploaded.",
                detail={"channel_id": ch["id"], "handle": ch["handle"]},
                unblock="Revoke at myaccount.google.com/permissions, delete "
                        ".secrets/youtube_token.json, and re-run "
                        ".venv/bin/python auth/youtube_auth.py signed in as the "
                        "account that owns the channel.")
        st.note(f"authorised channel confirmed: {ch['title']} {ch['handle']}")

        uploaded = 0
        for it in ready:
            video = ROOT / it["render"]
            if not video.exists():
                st.note(f"{it['slug']}: {it['render']} is missing — skipped")
                continue
            try:
                vid = resumable_upload(token, payloads[it["slug"]], video)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "ignore")[:600]
                if e.code in (403,) and "uploadLimitExceeded" in detail:
                    st.named_stop("UPLOAD_QUOTA",
                                  "YouTube upload quota exceeded",
                                  detail=detail,
                                  unblock="Wait for the daily quota reset; the "
                                          "queue is unchanged and will resume.")
                st.note(f"{it['slug']}: upload failed {e.code} {detail}")
                continue
            receipts.upload_receipt(it["slug"], week, vid, "private")
            uploaded += 1
            st.work(f"uploaded {it['slug']} as PRIVATE -> {vid}")

        if uploaded == 0:
            st.named_stop("UPLOAD_FAILED",
                          "credentials resolved but no video uploaded",
                          detail={"ready": [i["slug"] for i in ready]})


if __name__ == "__main__":
    main()
