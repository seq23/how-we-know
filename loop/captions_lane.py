"""Upload the English caption track that every published episode already has.

    .venv/bin/python loop/captions_lane.py            # insert what is missing
    .venv/bin/python loop/captions_lane.py --limit 4  # smaller quota bite
    .venv/bin/python loop/captions_lane.py --dry-run  # plan and manifest only

## The defect this closes

`captions/` has held a timed `.srt` and `.vtt` for all twenty episodes since
they were narrated. Nothing ever sent them to YouTube — there was no
`captions.insert` call anywhere in this repo, and `loop/upload.py` posts
`part=snippet,status` and nothing more. The captions the viewer sees are
*burned into the picture* by the renderer. They are pixels. YouTube cannot read
them, and neither can anything downstream of them.

## What is actually blocked by that — the part that matters

Not "some viewers cannot turn subtitles on". Observed in the owner's YouTube
Studio on 2026-09-02, stated verbatim by the UI:

    "English subtitles are the default source for auto-translation of
     subtitles and audio."

The English caption track is the SOURCE FILE for auto-translated subtitles in
100+ languages **and for auto-dubbed audio**. With no track, none of it can
fire — not the subtitles, not the dub. The channel is banking watch hours
against a Partner Programme threshold that doubles from 4,000 to 8,000 on
2026-02-01, and non-English reach is the cheapest hours available. This lane is
the thing that unlocks it, and until it runs the whole translation surface is
inert no matter what else is configured.

Two prerequisites, in order:

  1. `snippet.defaultLanguage` set to `en` — without it Studio shows only a
     "Set language" dropdown and the subtitle UI does not exist. That is
     `loop/localize.py`'s job.
  2. an English caption track — this file.

## The scope, and the stop that guards it

`captions.insert` requires `https://www.googleapis.com/auth/youtube.force-ssl`
(or `youtubepartner`). Verified against
developers.google.com/youtube/v3/docs/captions/insert on 2026-09-02. The plain
`https://www.googleapis.com/auth/youtube` scope is **not** enough — that scope
covers `videos.update`, which is why localisation was never blocked and
captions were.

**GRANTED 2026-09-02.** force-ssl was added to `auth/tokens.py` SCOPES,
`auth/youtube_auth.py` detected the drift, forced a fresh consent, and
`.secrets/youtube_token.json` now records all five scopes. This lane runs.

The `CAPTIONS_SCOPE_MISSING` stop below is kept, not vestigial: the grant can
go away again — a revoked consent, a re-created OAuth client, or a runner using
repo secrets minted before this change. If it does, the lane must say so in one
sentence with the exact command, rather than 403ing into a traceback. The stop
is checked BEFORE any spend, from the scopes the credential reports, and again
from the API's own 403 for the case where a credential cannot report them.

## Quota

captions.list 50, captions.insert 400 — so 450 per video, and fifteen live
videos are 6,750 units of a 10,000-unit day. That is most of a day, and it must
never be the reason the upload lane fails halfway through. So this lane spends
through `loop/quota.py` behind `quota.upload_reserve()`: while the day's upload
is still to come, a whole video's allowance is held back and the caption
backfill simply takes fewer, finishing over several daily runs; once an
uploading lane has booked units the reserve is zero, because the thing it was
protecting has already happened. Re-running costs nothing for anything already
recorded.

## Auto-dubbing

A prior research pass claimed YouTube auto-dubbing is "enabled by default for
all eligible creators". On 2026-09-02 no auto-dub toggle could be found
anywhere in this account's Studio — not in Settings -> Upload defaults ->
Advanced, not on the video Details page with advanced settings expanded, not on
the video Languages page. Treat auto-dub as UNVERIFIED on this account. Nothing
here depends on it: the caption track earns its keep through auto-translated
subtitles alone, and is the prerequisite either way.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))

import tokens as auth                             # noqa: E402
import quota                                      # noqa: E402
import upload as up                               # noqa: E402
import ytmeta                                     # noqa: E402
from common import (STATE, Stage, config, now, read_json,  # noqa: E402
                    sha256, week_id, write_json)

LANE = "captions"
STATE_FILE = STATE / "captions.json"
CAPTIONS_DIR = ROOT / "captions"

API = "https://www.googleapis.com/youtube/v3/captions"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/captions"

FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"

# One canonical code, matching what the Studio UI now holds channel-wide.
# NEVER "en-US": half the channel saying en and half en-US is an inconsistency
# nothing would ever report.
LANGUAGE = "en"
TRACK_NAME = "English"

RECONSENT = ".venv/bin/python auth/youtube_auth.py"

SCOPE_UNBLOCK = (
    "ONE browser consent, once, on the Mac:\n"
    f"    {RECONSENT}\n"
    "  Sign in as the account that owns @howweknowdeep and click Allow.\n"
    "  auth/tokens.py already lists youtube.force-ssl in SCOPES, and\n"
    "  youtube_auth.py forces the prompt when the stored token is missing a\n"
    "  scope, so that single run is the entire fix. Nothing else is blocked by\n"
    "  it: titles, descriptions, localizations, scheduling and publishing all\n"
    "  work on the scopes already granted. What IS blocked is the source file\n"
    "  for auto-translated subtitles AND auto-dubbed audio in every language,\n"
    "  which is the channel's cheapest route to Partner Programme watch hours\n"
    "  before the threshold doubles on 2026-02-01.")


# ------------------------------------------------------------------- state

def load_state() -> dict:
    d = read_json(STATE_FILE, default={"videos": {}, "blocked": {},
                                       "updated": None})
    d.setdefault("videos", {})
    d.setdefault("blocked", {})
    return d


def save_state(d: dict) -> None:
    d["updated"] = now()
    write_json(STATE_FILE, d)


def srt_for(slug: str) -> Path:
    return CAPTIONS_DIR / f"{slug}.srt"


def cue_count(path: Path) -> int:
    """How many timed cues the file actually contains.

    A zero-cue SRT is a file that exists and says nothing — exactly the shape
    of "runs but inert". It is refused rather than uploaded.
    """
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if "-->" in line)


# --------------------------------------------------------------- the API

def list_tracks(token: str, video_id: str, timeout: int = 30) -> list[dict]:
    """Existing caption tracks. 50 units. The idempotence check."""
    q = urllib.parse.urlencode({"part": "snippet", "videoId": video_id})
    req = urllib.request.Request(f"{API}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("items") or []


def insert_track(token: str, video_id: str, srt: Path,
                 timeout: int = 120) -> str:
    """captions.insert, multipart. 400 units. Returns the new caption id.

    Hand-rolled multipart/related because this repo takes no third-party HTTP
    dependency (see auth/tokens.py). The shape is Google's documented one:
    a JSON metadata part, then the file part.
    """
    meta = {"snippet": {"videoId": video_id, "language": LANGUAGE,
                        "name": TRACK_NAME, "isDraft": False}}
    boundary = "howweknow-caption-boundary"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(meta).encode("utf-8"), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        srt.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{UPLOAD_API}?uploadType=multipart&part=snippet",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/related; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["id"]


def _is_scope_error(e: urllib.error.HTTPError, detail: str) -> bool:
    return e.code in (401, 403) and (
        "insufficientPermissions" in detail or "forbidden" in detail.lower()
        or "insufficient authentication scopes" in detail.lower())


# ---------------------------------------------------------------- the lane

def run(limit: int = 15, dry_run: bool = False, verify: int = 3) -> int:
    cfg = config()
    state = load_state()

    with Stage(LANE, week_id(),
               zero_work_hint="No live video in loop/state/ledger.json had an "
                              "English .srt in captions/. Narration writes "
                              "those; if the ledger has rows and captions/ "
                              "does not, the render side is what broke.") as st:
        live = ytmeta.live_videos()
        if not live:
            st.named_stop("NOTHING_PUBLISHED",
                          "loop/state/ledger.json lists no live video, so "
                          "there is nothing to caption",
                          unblock="Upload an episode first; this lane runs "
                                  "after the upload lane, never before it.")

        # ---- real work that happens whether or not we can reach YouTube ----
        # Same principle as loop/upload.py composing its payloads under a
        # blocked credential: the moment the scope appears, the first run has
        # nothing left to figure out, and a broken .srt is found today rather
        # than in the middle of a 400-unit call.
        plan, gaps = [], []
        for row in live:
            slug, vid = row["slug"], row["video_id"]
            srt = srt_for(slug)
            if not srt.exists():
                gaps.append(f"{slug}: captions/{slug}.srt does not exist")
                continue
            cues = cue_count(srt)
            if cues == 0:
                gaps.append(f"{slug}: captions/{slug}.srt has zero timed cues")
                continue
            digest = sha256(srt)
            rec = state["videos"].get(vid)
            done = bool(rec and rec.get("caption_id")
                        and rec.get("srt_sha256") == digest)
            plan.append({"slug": slug, "video_id": vid, "srt": str(srt),
                         "cues": cues, "sha256": digest, "already": done})
            st.work(f"verified {slug}: {cues} timed cues, "
                    f"{srt.stat().st_size:,} bytes, sha {digest[:12]}…"
                    + (" (already shipped)" if done else " — NEEDS a track"))
        for g in gaps:
            st.note(g)

        if not plan:
            st.named_stop(
                "NO_CAPTION_FILES",
                f"{len(live)} live video(s) but not one usable .srt in "
                f"captions/",
                detail={"gaps": gaps},
                unblock="Narration writes captions/<slug>.srt. Re-run "
                        "bin/batch-session.sh for the affected episodes.")

        pending = [p for p in plan if not p["already"]]
        shipped = [p for p in plan if p["already"]]
        write_json(STATE / "captions_manifest.json",
                   {"week": week_id(), "at": now(), "plan": plan, "gaps": gaps})

        # ---- the credential ------------------------------------------------
        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code,
                          f"{len(pending)} video(s) need an English caption "
                          f"track but " + msg,
                          detail={"pending": [p["slug"] for p in pending]},
                          unblock=unblock)

        # ---- the scope -----------------------------------------------------
        # Checked BEFORE spending anything. The same information arrives as a
        # 403 after the fact, at 400 units and in the shape of a traceback.
        granted = creds.get("scopes") or []
        if granted and FORCE_SSL not in granted:
            for p in pending:
                state["blocked"][p["video_id"]] = {
                    "slug": p["slug"], "reason": "CAPTIONS_SCOPE_MISSING",
                    "since": now(), "sha256": p["sha256"]}
            state["token_scopes"] = sorted(granted)
            state["token_has_force_ssl"] = False
            save_state(state)
            st.named_stop(
                "CAPTIONS_SCOPE_MISSING",
                f"{len(pending)} episode(s) have a checked, timed English .srt "
                f"ready to send, but this credential was never granted "
                f"{FORCE_SSL}, which captions.insert requires. NOTHING IS "
                f"WRONG WITH THE FILES — what is missing is the source track "
                f"for auto-translated subtitles and auto-dubbed audio, so the "
                f"channel's entire non-English reach is off until one consent "
                f"is given.",
                detail={"pending": [p["slug"] for p in pending],
                        "granted_scopes": sorted(granted),
                        "needs": FORCE_SSL},
                unblock=SCOPE_UNBLOCK)

        token = up.access_token(creds)

        ch = auth.channel(token)
        if not ch["ok"] or not ch["matches_expected"]:
            st.named_stop(
                "WRONG_CHANNEL" if ch["ok"] else "CHANNEL_UNREADABLE",
                f"refusing to write captions: "
                + (f"the credential authorises '{ch.get('title')}', not "
                   f"{auth.EXPECTED_HANDLE}" if ch["ok"] else ch["detail"]),
                unblock="Run: .venv/bin/python auth/check_auth.py")

        # ---- the allowance -------------------------------------------------
        # BOTH irreversible lanes, not just the episode. Captions can wait
        # a day; a 19:00 Shorts slot cannot, and at 9 Shorts a week the
        # evening lane is now the more frequent of the two.
        reserve = quota.deferrable_reserve()
        afford = quota.units_affordable(quota.PER_CAPTION,
                                        min(limit, len(pending)),
                                        reserve=reserve)
        # RECORD EVERY DEFERRAL, INCLUDING WHEN afford IS ZERO. The backfill
        # genuinely spans several days at 450 units a video, and V16 would
        # otherwise be red on every one of them for a lane working exactly as
        # designed - which is how a validator stops being read.
        #
        # But the excuse is BOUNDED: V16 accepts a QUOTA_DEFERRED video only
        # for DEFER_GRACE_DAYS from the day it was FIRST deferred, and `since`
        # is never refreshed. A backfill that stalls goes red on its own,
        # without anyone remembering to check.
        #
        # This runs BEFORE the QUOTA_EXHAUSTED stop, not after: the day the
        # allowance is entirely gone is exactly the day every remaining video
        # is deferred, and a stop raised first would skip the record.
        for pend in pending[afford:]:
            prior = state["blocked"].get(pend["video_id"]) or {}
            state["blocked"][pend["video_id"]] = {
                "slug": pend["slug"], "reason": "QUOTA_DEFERRED",
                "since": (prior.get("since")
                          if prior.get("reason") == "QUOTA_DEFERRED"
                          else now()),          # first deferral wins
                "sha256": pend["sha256"]}
        if pending[afford:]:
            state["token_has_force_ssl"] = True
            state["token_scopes"] = sorted(granted)
            save_state(state)

        if pending and afford == 0:
            st.named_stop(
                "QUOTA_EXHAUSTED",
                f"{len(pending)} episode(s) still need a caption track but "
                f"today's allowance cannot fund one at "
                f"{quota.PER_CAPTION} units while keeping {reserve} back for "
                f"the upload lane. They are recorded as QUOTA_DEFERRED and "
                f"tomorrow's run takes them. "
                f"{quota.report()}",
                unblock="Nothing to do. The allowance resets at midnight "
                        "Pacific and this lane runs daily; the backfill "
                        "finishes over a few days by design.")
        if pending and afford < len(pending):
            st.note(f"quota funds {afford} of {len(pending)} today "
                    f"({quota.PER_CAPTION} units each, {reserve} reserved for "
                    f"the upload lane)")
            # RECORD THE DEFERRAL, with a date. The backfill genuinely spans
            # several days at 450 units a video, and V16 would otherwise be red
            # every one of them for a lane that is working exactly as designed
            # - which is how a validator stops being read.
            #
            # But the excuse is BOUNDED: V16 accepts a QUOTA_DEFERRED video
            # only for DEFER_GRACE_DAYS from the day it was FIRST deferred, and
            # `since` is never refreshed. A backfill that stalls goes red on
            # its own, without anyone remembering to check.


        inserted, confirmed, spent = 0, 0, 0

        for p in pending[:afford]:
            vid, slug = p["video_id"], p["slug"]
            try:
                existing = list_tracks(token, vid)
                spent += quota.CAPTION_LIST
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "ignore")[:400]
                if _is_scope_error(e, detail):
                    quota.spend(spent, LANE)
                    save_state(state)
                    st.named_stop("CAPTIONS_SCOPE_MISSING",
                                  f"YouTube refused captions.list for {slug}: "
                                  f"HTTP {e.code}. The grant is missing "
                                  f"{FORCE_SSL}.",
                                  detail=detail, unblock=SCOPE_UNBLOCK)
                st.note(f"{slug}: captions.list failed {e.code} {detail}")
                continue

            # AN ASR TRACK IS NOT A CAPTION TRACK FOR THIS PURPOSE.
            #
            # Every one of these videos already returns an `en` track from
            # captions.list, and the first version of this lane recorded that
            # as "already shipped" and moved on - a false green that would have
            # satisfied V16 while not one real track existed. Checked on
            # 2026-09-02: `trackKind` is `asr` on all of them. That is
            # YouTube's own speech recognition guessing at the audio.
            #
            # It is not what this channel ships. The .srt in captions/ IS the
            # narration script, timed to the render, with NOAA, MBARI, JAMSTEC
            # and Challenger Deep spelled the way the sources spell them. ASR
            # invents text, and "no invented text" is the one rule this
            # pipeline does not bend. An uploaded standard track also takes
            # precedence over the ASR one, so uploading is the fix, not a
            # duplicate.
            #
            # So only a `standard` track counts as ours.
            asr = [c for c in existing
                   if (c.get("snippet") or {}).get("language") == LANGUAGE
                   and (c.get("snippet") or {}).get("trackKind") == "asr"]
            mine = [c for c in existing
                    if (c.get("snippet") or {}).get("language") == LANGUAGE
                    and (c.get("snippet") or {}).get("trackKind") != "asr"]
            if mine:
                # Already there — recorded but not re-uploaded. Two English
                # tracks on one video is a mess only a human can untangle.
                state["videos"][vid] = {
                    "slug": slug, "caption_id": mine[0]["id"],
                    "language": LANGUAGE, "srt_sha256": p["sha256"],
                    "track_kind": (mine[0]["snippet"] or {}).get("trackKind",
                                                                 "standard"),
                    "source": "found-on-channel", "recorded_at": now()}
                state["blocked"].pop(vid, None)
                confirmed += 1
                st.work(f"{slug}: YouTube already carries an uploaded "
                        f"{LANGUAGE} track ({mine[0]['id']}) — recorded, not "
                        f"duplicated")
                continue
            if asr:
                st.note(f"{slug}: the only {LANGUAGE} track on YouTube is ASR "
                        f"(machine-transcribed). Uploading the real one; it "
                        f"takes precedence.")

            if dry_run:
                st.note(f"DRY RUN: would insert {LANGUAGE} track for {slug} "
                        f"({p['cues']} cues)")
                continue

            try:
                cid = insert_track(token, vid, Path(p["srt"]))
                spent += quota.CAPTION_INSERT
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "ignore")[:400]
                spent += quota.CAPTION_INSERT     # a rejected call still costs
                if _is_scope_error(e, detail):
                    quota.spend(spent, LANE)
                    save_state(state)
                    st.named_stop("CAPTIONS_SCOPE_MISSING",
                                  f"YouTube refused captions.insert for "
                                  f"{slug}: HTTP {e.code}. The grant is "
                                  f"missing {FORCE_SSL}.",
                                  detail=detail, unblock=SCOPE_UNBLOCK)
                st.note(f"{slug}: captions.insert failed {e.code} {detail}")
                continue

            state["videos"][vid] = {
                "slug": slug, "caption_id": cid, "language": LANGUAGE,
                "srt_sha256": p["sha256"], "cues": p["cues"],
                "track_kind": "standard",
                "source": "inserted", "recorded_at": now()}
            state["blocked"].pop(vid, None)
            inserted += 1
            st.work(f"{slug}: uploaded the {LANGUAGE} caption track -> {cid}. "
                    f"Auto-translated subtitles and auto-dubbed audio now have "
                    f"a source.")

        # ---- steady state: VERIFY, do not merely assume ---------------------
        # On a day with nothing to insert this lane still has real work: a
        # track deleted in Studio would otherwise never be noticed, and the
        # state file would keep asserting a reach that no longer exists.
        # Oldest-checked first, budget-capped, so it costs 50 units a video.
        if not dry_run:
            budget = quota.units_affordable(
                quota.CAPTION_LIST, verify,
                reserve=quota.deferrable_reserve() + max(0, spent))
            stale = sorted(shipped,
                           key=lambda p: state["videos"].get(
                               p["video_id"], {}).get("verified_at") or "")
            for p in stale[:budget]:
                vid, slug = p["video_id"], p["slug"]
                try:
                    tracks = list_tracks(token, vid)
                    spent += quota.CAPTION_LIST
                except urllib.error.HTTPError as e:
                    st.note(f"{slug}: verification call failed {e.code}")
                    continue
                ids = {t["id"] for t in tracks}
                rec = state["videos"][vid]
                if rec["caption_id"] in ids:
                    rec["verified_at"] = now()
                    confirmed += 1
                    st.work(f"{slug}: confirmed the {LANGUAGE} track is still "
                            f"on YouTube ({rec['caption_id']})")
                else:
                    rec.pop("caption_id", None)
                    rec["lost_at"] = now()
                    st.work(f"{slug}: the caption track this lane uploaded is "
                            f"GONE from YouTube — recorded as missing so the "
                            f"next run re-uploads it")

        state["token_has_force_ssl"] = True
        state["token_scopes"] = sorted(granted) if granted else \
            state.get("token_scopes")
        save_state(state)
        if spent:
            quota.spend(spent, LANE)
            st.note(f"spent {spent} quota units. {quota.report()}")

        # ---- the inertness tripwire ----------------------------------------
        # Rule 0 already forbids exiting 0 with no units, and the .srt
        # verification above always books units. That is exactly why this
        # separate check exists: without it, a run that reached YouTube and
        # touched nothing at all would still look green on the strength of
        # having read some files off disk.
        if inserted == 0 and confirmed == 0 and not dry_run:
            st.named_stop(
                "CAPTIONS_INERT",
                f"the lane authenticated and then neither uploaded nor "
                f"confirmed a single caption track "
                f"({len(pending)} pending, {len(shipped)} on record). It read "
                f"files off disk and called that a day.",
                detail={"pending": [p["slug"] for p in pending],
                        "shipped": [p["slug"] for p in shipped],
                        "afford": afford},
                unblock="Check loop/state/captions.json against YouTube "
                        "Studio. If the state file claims tracks that are not "
                        "there, delete those rows and re-run.")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=15,
                    help="max caption tracks to insert this run")
    ap.add_argument("--verify", type=int, default=3,
                    help="how many already-shipped tracks to re-check (50 "
                         "units each)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and manifest only; insert nothing")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run, verify=a.verify)


if __name__ == "__main__":
    raise SystemExit(main())
