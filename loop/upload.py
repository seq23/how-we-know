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
import receipt as receipts  # noqa: E402
from common import (LOOP, RECEIPTS, ROOT, Stage, config, now,  # noqa: E402
                    read_json, week_id, write_json)

QUEUE = LOOP / "render_queue.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status")

# YouTube's own limits. Exceeding them is a 400 at 3am, so they are enforced here.
TITLE_MAX, DESC_MAX, TAG_TOTAL_MAX = 100, 5000, 400


def load_credentials(cfg) -> dict | None:
    """Return credentials, or None. Never raises: absence is an expected state.

    Two sources, in order:
      1. `.secrets/` on the Mac, via `auth/tokens.py` — the normal path, set up
         once by `auth/youtube_auth.py`.
      2. Repo-secret environment variables, for the Actions-side publish stage.
    """
    res = auth.load()
    if res["status"] == "ok":
        return {"access_token": res["access_token"], "source": "secrets",
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
    # title equals the question record. Fix it here, at upload time: the credential
    # holds youtube.upload and youtube.readonly only, so a title cannot be corrected
    # afterwards - videos.update returns 403 without the broader youtube scope.
    title = item["question"].strip().rstrip("?")
    title = (title[:1].upper() + title[1:] if title else title) + "?"
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1].rsplit(" ", 1)[0] + "?"

    answer = ""
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)\n\s*\n", text, re.S)
    if m:
        answer = re.sub(r"\s+", " ", m.group(1)).strip()

    chapters = []
    ch = re.search(r"## Chapters\s*\n(.*?)(\n## |\Z)", text, re.S)
    if ch:
        for line in ch.group(1).splitlines():
            mm = re.match(r"\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)", line)
            if mm:
                chapters.append(f"{mm.group(1)} {mm.group(2).strip()}")

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

    tags, total = [], 0
    for t in ["deep sea", "ocean science", "how we know", "evidence",
              "marine biology", "explainer", "deep ocean"]:
        if total + len(t) + 1 <= TAG_TOTAL_MAX:
            tags.append(t)
            total += len(t) + 1

    return {
        "snippet": {"title": title, "description": description, "tags": tags,
                    "categoryId": "27"},   # 27 = Education
        # private is the design, not a limitation to work around: an
        # unverified Google app has uploads FORCED private anyway, and the loop
        # flips to public on Friday only against a receipt.
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "embeddable": True, "license": "youtube"},
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
        if not ready:
            st.named_stop(
                "NOTHING_RENDERED",
                "no queue row has a healthy render receipt; there is nothing to "
                "upload this week",
                detail={"statuses": {i["slug"]: i.get("status")
                                     for i in q["items"]}},
                unblock="Run bin/loop-tuesday.sh, or inspect "
                        "loop/state/stops/ for why it produced nothing.")

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
