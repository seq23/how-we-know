"""Comment watch: sweep the channel's comments, propose, and ACT only on record.

    .venv/bin/python loop/comments.py sweep [--out digest.json] [--limit-videos N]
    .venv/bin/python loop/comments.py act --instructions instructions.json

Two verbs, one ledger.

**sweep** lists every top-level comment on every upload of the channel since
the ledger's per-video cursor, classifies the new ones in ONE model call per
batch (negative / question / praise / spam / other), records each as SEEN in
`loop/state/comments/ledger.json` so it is never reported twice, and writes a
JSON digest of the NEGATIVE and QUESTION items with a proposed action and a
drafted reply. A pronunciation or narration complaint also carries a
`product_note` ("pronunciation: <term>") - that is a real signal for the
narration lexicon and is the one thing in a bad comment worth keeping.

**act** applies per-comment instructions. It is the ONLY write path to
YouTube in this module and it is gated: every instruction must carry who gave
it and when (`instructed_by`, `instructed_at`, `source`), the comment must be
one the sweep already recorded, and the action must be one of hide / reply /
ignore. Anything else is a NAMED STOP before any network call. `hide` is
`comments.setModerationStatus=rejected` - the same thing the owner's manual
delete-from-Studio does, and reversible from Studio's "Held for review" tab,
which a real delete is not. `reply` is `comments.insert` as the channel. Every
applied action is recorded in the ledger against its instruction record.
`loop/tests/test_comment_watch.py` proves the gate negatively.

Account: the channel's own Google account (the channel's own Google account), through
the same `.secrets/` token every other lane uses. Nothing here names any other
business, and `test_comment_watch.py` greps this file to keep it that way.

Cost. commentThreads.list and playlistItems.list are 1 quota unit each;
setModerationStatus and comments.insert are 50. Spend is recorded through
loop/quota.py under the lane name `comments`. The classifier is the cheapest
model the repo's OpenRouter route offers; one call per batch of up to
CLASSIFY_BATCH comments, ~256 input tokens per comment. `LOOP_DRY_RUN=1`
refuses credentials and every write, exactly as upload.py does.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import author                                                 # noqa: E402
import quota                                                  # noqa: E402
import upload as up                                           # noqa: E402
from common import (STATE, Stage, config, now, read_json,     # noqa: E402
                    week_id, write_json)

CHANNEL_ID = "UC5vZFZc15DIM6IrFwFgAECg"
# YouTube's uploads playlist is the channel id with the UC prefix swapped for UU.
UPLOADS_PLAYLIST = "UU" + CHANNEL_ID[2:]

COMMENTS_DIR = STATE / "comments"
LEDGER = COMMENTS_DIR / "ledger.json"
DIGEST_DEFAULT = COMMENTS_DIR / "digest.json"

API = "https://www.googleapis.com/youtube/v3"
CLASSES = ("negative", "question", "praise", "spam", "other")
ACTIONS = ("hide", "reply", "ignore")
REPORTED = ("negative", "question")
CLASSIFY_BATCH = 40
# The cheapest model on the repo's route. Classification of a forty-comment
# batch is a few hundred output tokens; author.DEFAULT_MODEL (Sonnet) would
# cost ~5x for the same label. Overridable, never empty (see
# author.configured_model for why an empty variable is "unset").
CLASSIFY_MODEL = (os.environ.get("OPENROUTER_COMMENTS_MODEL", "").strip()
                  or "anthropic/claude-haiku-4.5")
UNIT_LIST, UNIT_WRITE = 1, 50

DRY_RUN = os.environ.get("LOOP_DRY_RUN") == "1"


# ------------------------------------------------------------------ ledger

def _empty_ledger() -> dict:
    return {"channel_id": CHANNEL_ID, "cursors": {}, "seen": {},
            "instructions": {}, "actions": [], "sweeps": [],
            "updated": None}


def load_ledger() -> dict:
    d = read_json(LEDGER, default={})
    if not d:
        return _empty_ledger()
    base = _empty_ledger()
    base.update(d)
    return base


def save_ledger(led: dict) -> None:
    led["updated"] = now()
    COMMENTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(LEDGER, led)


# ------------------------------------------------------------------ YouTube

def _get(token: str, path: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}/{path}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _write(token: str, path: str, params: dict, body: dict | None) -> dict:
    """THE ONLY network write in this module. act() reaches it only through
    apply_instruction(), which has already checked the instruction record."""
    if DRY_RUN:
        raise RuntimeError("LOOP_DRY_RUN=1: refusing a YouTube write")
    q = urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{API}/{path}?{q}", data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def list_uploads(token: str, limit: int | None = None) -> tuple[list[dict], int]:
    """Every video on the uploads playlist: [{video_id, title, published_at}].
    Returns the list and the quota units spent."""
    out, units, page = [], 0, None
    while True:
        params = {"part": "snippet,status", "playlistId": UPLOADS_PLAYLIST,
                  "maxResults": 50}
        if page:
            params["pageToken"] = page
        data = _get(token, "playlistItems", params)
        units += UNIT_LIST
        for it in data.get("items") or []:
            sn = it.get("snippet") or {}
            vid = (sn.get("resourceId") or {}).get("videoId")
            if not vid:
                continue
            out.append({"video_id": vid, "title": sn.get("title") or "",
                        "published_at": sn.get("publishedAt") or "",
                        "privacy": (it.get("status") or {}).get("privacyStatus")})
            if limit and len(out) >= limit:
                return out, units
        page = data.get("nextPageToken")
        if not page:
            return out, units


def list_new_threads(token: str, video_id: str, since: str | None
                     ) -> tuple[list[dict], int, str | None]:
    """Top-level comments on one video newer than `since` (RFC3339), newest
    first. Stops paging as soon as a page ends older than the cursor. Returns
    (comments, units, newest_published_at). A video with comments disabled
    answers 403 commentsDisabled; that is not new comments, and not a fault."""
    out, units, page, newest = [], 0, None, None
    while True:
        params = {"part": "snippet", "videoId": video_id, "order": "time",
                  "maxResults": 100, "textFormat": "plainText"}
        if page:
            params["pageToken"] = page
        try:
            data = _get(token, "commentThreads", params)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            if e.code == 403 and "commentsDisabled" in body:
                return [], units + UNIT_LIST, None
            raise
        units += UNIT_LIST
        older_seen = False
        for th in data.get("items") or []:
            top = ((th.get("snippet") or {}).get("topLevelComment") or {})
            sn = top.get("snippet") or {}
            pub = sn.get("publishedAt") or ""
            if newest is None or pub > newest:
                newest = pub
            if since and pub <= since:
                older_seen = True
                continue
            out.append({
                "comment_id": top.get("id"),
                "video_id": video_id,
                "author": sn.get("authorDisplayName") or "",
                "author_channel_id": ((sn.get("authorChannelId") or {})
                                      .get("value")),
                "text": sn.get("textOriginal") or sn.get("textDisplay") or "",
                "published_at": pub,
                "like_count": sn.get("likeCount", 0),
                "reply_count": (th.get("snippet") or {}).get("totalReplyCount", 0),
            })
        page = data.get("nextPageToken")
        if not page or older_seen:
            return out, units, newest


# --------------------------------------------------------------- classifier

SYSTEM = (
    "You triage YouTube comments for an evidence-first science channel. "
    "For each comment return exactly one JSON object per input id. "
    "Classes: negative (criticism, complaint, hostility, or a factual "
    "challenge), question (asks the channel something answerable), praise, "
    "spam (links, self-promotion, bots, off-topic solicitation), other. "
    "For negative and question comments propose one action: hide (only for "
    "abuse, slurs, harassment, or spam-like content - never for mere "
    "disagreement), reply, or ignore. Draft `proposed_reply` only when the "
    "action is reply: at most two short sentences, polite, factual, never "
    "defensive, never argumentative, no emoji, no hashtags, signed as nobody "
    "(the channel replies as itself). If a comment complains about how a "
    "word or name was pronounced, or about the narration voice or pacing, "
    "set `product_note` to 'pronunciation: <term>' (or 'narration: <issue>'). "
    "Output ONLY a JSON array; no prose."
)


def _prompt(batch: list[dict]) -> list[dict]:
    rows = [{"id": c["comment_id"], "video": c.get("video_title", ""),
             "text": c["text"][:1200]} for c in batch]
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                "Schema per item: {\"id\": str, \"class\": one of "
                f"{list(CLASSES)}, \"proposed_action\": one of "
                f"{list(ACTIONS)} or null, \"proposed_reply\": str or null, "
                "\"product_note\": str or null}\n\nComments:\n"
                + json.dumps(rows, ensure_ascii=False)}]


def parse_classification(raw: str, ids: list[str]) -> dict[str, dict]:
    """Parse the model's array, or raise. Never invents a class: a missing or
    malformed row is an error the caller names, not a silent 'other'."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    arr = json.loads(text)
    if not isinstance(arr, list):
        raise ValueError("classifier did not return a JSON array")
    out: dict[str, dict] = {}
    for row in arr:
        cid = row.get("id")
        cls = row.get("class")
        if cid not in ids or cls not in CLASSES:
            raise ValueError(f"classifier row unusable: {row!r}")
        act = row.get("proposed_action")
        if cls in REPORTED and act not in ACTIONS:
            raise ValueError(f"reported class without an action: {row!r}")
        out[cid] = {"class": cls,
                    "proposed_action": act if cls in REPORTED else None,
                    "proposed_reply": (row.get("proposed_reply") or None)
                    if act == "reply" else None,
                    "product_note": row.get("product_note") or None}
    missing = [i for i in ids if i not in out]
    if missing:
        raise ValueError(f"classifier omitted {len(missing)} id(s): "
                         f"{missing[:3]}")
    return out


def classify(batch: list[dict], key: str, model: str) -> tuple[dict, float]:
    out = author.call_openrouter(_prompt(batch), model, key, timeout=120,
                                 temperature=0.0)
    raw = out["choices"][0]["message"]["content"]
    cost = (out.get("usage") or {}).get("cost") or 0.0
    return parse_classification(raw, [c["comment_id"] for c in batch]), cost


# ------------------------------------------------------------------- sweep

def build_digest(led: dict, new_ids: list[str]) -> dict:
    items = []
    for cid in new_ids:
        rec = led["seen"][cid]
        if rec["class"] not in REPORTED:
            continue
        items.append({k: rec.get(k) for k in (
            "comment_id", "video_id", "video_title", "author", "text",
            "published_at", "class", "proposed_action", "proposed_reply",
            "product_note")})
    by_class = {}
    for cid in new_ids:
        c = led["seen"][cid]["class"]
        by_class[c] = by_class.get(c, 0) + 1
    return {"generated_at": now(), "channel_id": CHANNEL_ID,
            "new_comments": len(new_ids), "by_class": by_class,
            "items": items}


def sweep(out_path: Path, limit_videos: int | None) -> int:
    cfg = config()
    with Stage("comment-watch", week_id(),
               zero_work_hint="No upload on the channel had a comment newer "
                              "than the ledger's cursor.") as st:
        creds = up.load_credentials(cfg)
        if creds is None or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code, msg, unblock=unblock)
        token = up.access_token(creds)
        key = author.api_key()
        if not key:
            st.named_stop("OPENROUTER_KEY_MISSING",
                          "no OpenRouter key; comments cannot be classified",
                          unblock="Put the key in .secrets/openrouter_key.txt "
                                  "or set $OPENROUTER_API_KEY.")

        led = load_ledger()
        try:
            videos, units = list_uploads(token, limit_videos)
        except urllib.error.URLError as e:
            st.named_stop("NETWORK_UNREACHABLE", f"playlistItems.list: {e}")
        st.note(f"{len(videos)} upload(s) on the channel")

        fresh: list[dict] = []
        titles = {v["video_id"]: v["title"] for v in videos}
        newest_by_video: dict[str, str] = {}
        for v in videos:
            vid = v["video_id"]
            since = led["cursors"].get(vid)
            try:
                got, u, newest = list_new_threads(token, vid, since)
            except urllib.error.URLError as e:
                st.named_stop("NETWORK_UNREACHABLE",
                              f"commentThreads.list {vid}: {e}")
            units += u
            if newest:
                newest_by_video[vid] = newest
            for c in got:
                if c["comment_id"] in led["seen"]:
                    continue
                c["video_title"] = titles.get(vid, "")
                fresh.append(c)
        quota.spend(units, "comments")
        st.note(f"{len(fresh)} new comment(s); {units} quota unit(s)")

        if not fresh:
            # Advance cursors anyway: nothing new means every existing
            # comment is older than what we have seen.
            for vid, newest in newest_by_video.items():
                led["cursors"][vid] = max(led["cursors"].get(vid) or "", newest)
            led["sweeps"].append({"at": now(), "videos": len(videos),
                                  "new": 0, "units": units})
            save_ledger(led)
            write_json(out_path, build_digest(led, []))
            st.named_stop(
                "NO_NEW_COMMENTS",
                f"every comment on {len(videos)} upload(s) was already in the "
                f"ledger",
                detail={"videos": len(videos), "digest": str(out_path)},
                unblock="Nothing to do; the next weekly sweep reads again.")

        cost, new_ids = 0.0, []
        for i in range(0, len(fresh), CLASSIFY_BATCH):
            batch = fresh[i:i + CLASSIFY_BATCH]
            try:
                labels, c = classify(batch, key, CLASSIFY_MODEL)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                st.named_stop("COMMENT_CLASSIFIER_UNUSABLE",
                              f"the classifier's answer could not be used: {e}",
                              unblock="Nothing was recorded for this batch; "
                                      "re-run. If it repeats, the model or "
                                      "prompt changed shape.")
            except urllib.error.URLError as e:
                st.named_stop("OPENROUTER_UNREACHABLE", str(e))
            cost += c
            for cmt in batch:
                rec = dict(cmt)
                rec.update(labels[cmt["comment_id"]])
                rec["seen_at"] = now()
                led["seen"][cmt["comment_id"]] = rec
                new_ids.append(cmt["comment_id"])
                st.work(f"classified {cmt['comment_id']} on {cmt['video_id']} "
                        f"as {rec['class']}")
        for vid, newest in newest_by_video.items():
            led["cursors"][vid] = max(led["cursors"].get(vid) or "", newest)
        digest = build_digest(led, new_ids)
        led["sweeps"].append({"at": now(), "videos": len(videos),
                              "new": len(new_ids), "reported": len(digest["items"]),
                              "units": units, "cost_usd": cost,
                              "model": CLASSIFY_MODEL})
        save_ledger(led)
        write_json(out_path, digest)
        st.note(f"digest: {len(digest['items'])} item(s) to report "
                f"({digest['by_class']}); classifier ${cost:.4f} on "
                f"{CLASSIFY_MODEL}; written to {out_path}")
    return 0


# --------------------------------------------------------------------- act

REQUIRED_RECORD = ("instructed_by", "instructed_at", "source")


class Unbacked(Exception):
    """An instruction that no one is on record as having given."""


def assert_backed(comment_id: str, ins: dict, led: dict) -> None:
    """The gate. Raises Unbacked unless this instruction names who gave it,
    when, and through what channel, names a legal action, and refers to a
    comment the sweep actually recorded. Nothing below this line is reached
    by a write that has not passed here - test_comment_watch.py proves it."""
    if not isinstance(ins, dict):
        raise Unbacked(f"{comment_id}: instruction is not an object")
    missing = [k for k in REQUIRED_RECORD if not str(ins.get(k) or "").strip()]
    if missing:
        raise Unbacked(f"{comment_id}: instruction record lacks "
                       f"{', '.join(missing)}")
    if ins.get("action") not in ACTIONS:
        raise Unbacked(f"{comment_id}: action {ins.get('action')!r} is not one "
                       f"of {ACTIONS}")
    if ins["action"] == "reply" and not str(ins.get("reply_text") or "").strip():
        raise Unbacked(f"{comment_id}: reply without reply_text")
    if comment_id not in led["seen"]:
        raise Unbacked(f"{comment_id}: not a comment this ledger has swept")


def apply_instruction(token: str, comment_id: str, ins: dict, led: dict
                      ) -> tuple[str, int]:
    """Apply ONE backed instruction. Returns (what happened, units spent)."""
    assert_backed(comment_id, ins, led)
    rec = led["seen"][comment_id]
    record = {"comment_id": comment_id, "video_id": rec.get("video_id"),
              "action": ins["action"], "reply_text": ins.get("reply_text"),
              "instructed_by": ins["instructed_by"],
              "instructed_at": ins["instructed_at"], "source": ins["source"],
              "note": ins.get("note"), "applied_at": now()}
    led["instructions"][comment_id] = {k: ins.get(k) for k in
                                       ("action", "reply_text", "instructed_by",
                                        "instructed_at", "source", "note")}
    if ins["action"] == "ignore":
        record["result"] = "ignored"
        led["actions"].append(record)
        rec["acted"] = record
        return "ignored (no change on YouTube)", 0
    if ins["action"] == "hide":
        _write(token, "comments/setModerationStatus",
               {"id": comment_id, "moderationStatus": "rejected"}, None)
        record["result"] = "hidden (moderationStatus=rejected)"
        led["actions"].append(record)
        rec["acted"] = record
        return record["result"], UNIT_WRITE
    out = _write(token, "comments", {"part": "snippet"},
                 {"snippet": {"parentId": comment_id,
                              "textOriginal": ins["reply_text"].strip()}})
    reply_id = out.get("id")
    if not reply_id:
        raise RuntimeError(f"comments.insert for {comment_id} returned no id")
    record["result"] = f"replied ({reply_id})"
    record["reply_id"] = reply_id
    led["actions"].append(record)
    rec["acted"] = record
    return record["result"], UNIT_WRITE


def act(instructions_path: Path) -> int:
    cfg = config()
    with Stage("comment-act", week_id(),
               zero_work_hint="No instruction was applied.") as st:
        ins_all = read_json(instructions_path, default={})
        if not isinstance(ins_all, dict) or not ins_all:
            st.named_stop("INSTRUCTIONS_UNREADABLE",
                          f"{instructions_path} is not a non-empty JSON object "
                          f"of comment_id -> instruction",
                          unblock="Write {comment_id: {action, reply_text?, "
                                  "instructed_by, instructed_at, source}}.")
        led = load_ledger()
        # EVERY instruction is checked before ANY is applied: a batch with one
        # unbacked line applies nothing, so a partial run cannot leave half
        # the owner's reply done and the rest silently dropped.
        for cid, ins in ins_all.items():
            try:
                assert_backed(cid, ins, led)
            except Unbacked as e:
                st.named_stop("INSTRUCTION_UNBACKED", str(e),
                              detail={"comment_id": cid},
                              unblock="Every instruction must name "
                                      "instructed_by, instructed_at and source, "
                                      "a legal action, and a swept comment. "
                                      "Nothing was applied.")
        pending = {cid: ins for cid, ins in ins_all.items()
                   if not led["seen"][cid].get("acted")}
        for cid in ins_all:
            if cid not in pending:
                st.note(f"{cid}: already acted "
                        f"({led['seen'][cid]['acted'].get('result')}); skipped")
        if not pending:
            st.named_stop("INSTRUCTIONS_ALREADY_APPLIED",
                          f"all {len(ins_all)} instruction(s) were applied on "
                          f"an earlier run",
                          unblock="Nothing to do; the ledger already holds "
                                  "each action.")

        creds = up.load_credentials(cfg)
        if creds is None or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code, msg, unblock=unblock)
        token = up.access_token(creds)
        units, results = 0, []
        for cid, ins in pending.items():
            try:
                what, u = apply_instruction(token, cid, ins, led)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")[:300]
                save_ledger(led)
                quota.spend(units, "comments")
                st.named_stop("COMMENT_ACTION_REJECTED",
                              f"YouTube refused {ins['action']} on {cid}: "
                              f"HTTP {e.code} {body}",
                              detail={"applied_before_stop": results},
                              unblock="Actions before this one were applied "
                                      "and recorded. Check the scope "
                                      "(youtube.force-ssl) and the comment id.")
            units += u
            results.append({"comment_id": cid, "result": what})
            st.work(f"{cid}: {what} (instructed by {ins['instructed_by']} via "
                    f"{ins['source']})")
        quota.spend(units, "comments")
        save_ledger(led)
        write_json(COMMENTS_DIR / "last_act.json",
                   {"at": now(), "results": results})
    return 0


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--out", default=str(DIGEST_DEFAULT))
    s.add_argument("--limit-videos", type=int, default=None)
    a_ = sub.add_parser("act")
    a_.add_argument("--instructions", required=True)
    a = ap.parse_args()
    if a.cmd == "sweep":
        return sweep(Path(a.out), a.limit_videos)
    return act(Path(a.instructions))


if __name__ == "__main__":
    raise SystemExit(main())
