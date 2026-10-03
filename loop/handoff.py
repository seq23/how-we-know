"""Short → episode hand-off, episode → Shorts block, and the two domain playlists.

    .venv/bin/python loop/handoff.py --dry-run   # plan: counts and quota, writes nothing
    .venv/bin/python loop/handoff.py             # apply, idempotently

WHY THIS LANE EXISTS. Owner decision 2026-10-03: the channel's discovery comes
almost entirely from Shorts — ~2,400 of 2,588 views from 34 Shorts, while the
16 measured episodes total 149 views. A Short that does not hand its viewer to
its episode wastes the only traffic the channel has. Four things, all of them
metadata the Data API can write, none of them a Studio click:

  1. SHORT → EPISODE. The first line of every live Short's description is
     `Full episode: https://youtu.be/<episode id> — <Question>?`. Set at upload
     when the episode is already public (loop/shorts_lane.py:build_payload takes
     the id); otherwise the Short ships with the channel link and the row is
     marked `handoff: pending`, and this lane rewrites it the first run after
     the episode goes public, marking it `handoff: done`.
  2. ONE CHANNEL COMMENT per Short — the question and the episode link —
     posted once the Short AND its episode are public, through
     loop/comments.py's gated write with an on-record instruction source. The
     comment id is kept on the Short's ledger row, so it is never posted twice.
     No pinning (decided: API-only, no Studio automation).
  3. EPISODE → SHORTS. Every public episode's description carries a
     "Shorts from this episode:" block listing its public Shorts, kept before
     the hashtag line so loop/discovery.py's round-trip still holds. Rewritten
     whenever a new Short of that episode goes public.
  4. TWO PLAYLISTS, one per allocated domain ("Deep Sea Science", "Materials &
     Manufacturing"), created once and remembered in loop/state/playlists.json;
     every public episode and Short is inserted into its domain's playlist by
     slug→domain (loop/domains.py). Items are added, never removed. A channel
     section per playlist is created when the token may; a refusal is recorded
     in playlists.json as a note, not a stop.

"LIVE" MEANS YOUTUBE SAYS PUBLIC. The ledgers record upload-time privacy
(`private` with a publishAt), so liveness is read from videos.list — 1 unit per
50 ids — never inferred from a timestamp. Thirty of the first 36 Shorts aired
days or weeks BEFORE their episode, so "pending" is the normal state of a new
Short, not an error.

QUOTA. Every write here is 50 units (videos.update, playlistItems.insert,
commentThreads.insert, playlists.insert, channelSections.insert). The lane is
deferrable: it reserves `quota.deferrable_reserve()` for the day's episode
upload and evening Shorts, does what fits in priority order (playlists, Short
links, playlist items, comments, episode blocks), records exactly what it
did, and takes HANDOFF_QUOTA_DEFERRED — self-resolving, the rest is done next
run. The back catalogue (34 Shorts, 18 episodes ≈ 7,000 units) is therefore
expected to complete over two quota days.

RULE 0. Nothing to do is HANDOFF_UP_TO_DATE, self-resolving and explained
upstream (the Shorts lane) when nothing new has gone live. A Short whose
episode is not in the ledger is a note. A refused write that is not a quota
refusal is HANDOFF_WRITE_REJECTED and needs a human.

Runs in the cloud after the Shorts lane and the upload lane each day
(.github/workflows/loop-shorts-cloud.yml, loop-upload-cloud.yml), and on the
Mac by hand. loop/validate.py V46 fails when a Short and its episode have both
been live more than HANDOFF_GRACE_H hours without `handoff: done`, or a live
video is missing from its domain playlist; loop/tests/test_handoff.py proves
the stage against a fake YouTube client.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import comments                                              # noqa: E402
import discovery                                             # noqa: E402
import domains                                               # noqa: E402
import ledger                                                # noqa: E402
import quota                                                 # noqa: E402
import upload as up                                          # noqa: E402
from common import (STATE, Stage, config, now, read_json,    # noqa: E402
                    week_id, write_json)

LANE = "handoff"
API = "https://www.googleapis.com/youtube/v3"
SHORTS_LEDGER = STATE / "shorts_ledger.json"
PLAYLISTS = STATE / "playlists.json"
HANDOFF_STATE = STATE / "handoff.json"

CHANNEL_LINK = "https://youtube.com/@howweknowdeep"
LINK_PREFIX = "Full episode: https://youtu.be/"
BLOCK_HEAD = "Shorts from this episode:"
WRITE_UNITS = 50
READ_UNITS = 1
DESC_MAX = up.DESC_MAX

# Playlist titles. docs/CHANNEL-PLAN.md names no playlists, so these are the
# owner's words from the 2026-10-03 decision. Keyed by the taxonomy's domain
# slug (loop/config.json domains.allocation); a third allocated domain would
# need a title here, and plan() refuses to invent one.
PLAYLIST_TITLES = {
    "deep-sea-ocean-science": "Deep Sea Science",
    "materials-and-manufacturing": "Materials & Manufacturing",
}
PLAYLIST_DESCRIPTIONS = {
    "deep-sea-ocean-science":
        "Evidence-first answers from the deep sea: every episode and every "
        "Short, newest last. Every figure traces to a named public source.",
    "materials-and-manufacturing":
        "Evidence-first answers about materials and how things are made: "
        "every episode and every Short, newest last. Every figure traces to "
        "a named public source.",
}

# Who is on record for the channel comments. loop/comments.py refuses any
# write whose instruction record lacks these three, and the record travels
# into loop/state/comments/ledger.json beside the comment id.
INSTRUCTION = {"instructed_by": "owner",
               "instructed_at": "2026-10-03",
               "source": "loop/handoff: owner decision 2026-10-03"}

# How long a Short and its episode may both be public before V46 calls a
# missing hand-off a defect. The lane runs twice a day; 36h is one missed run
# plus the quota day it may have deferred into.
HANDOFF_GRACE_H = 36


# ----------------------------------------------------------------- composing

def title_of(question: str) -> str:
    """Sentence case plus a question mark — the same shape the uploaders use."""
    t = (question or "").strip().rstrip("?")
    return (t[:1].upper() + t[1:] if t else t) + "?"


def link_line(episode_video_id: str, question: str) -> str:
    return f"{LINK_PREFIX}{episode_video_id} — {title_of(question)}"


def short_description(current: str, episode_video_id: str, question: str) -> str:
    """`current` with the hand-off line as its FIRST line, exactly once.

    An existing hand-off line (any episode id) is replaced, so a corrected
    episode id or question propagates; everything else — the blurb, the
    channel link, howweknowdeep.com, the hashtag line — is kept verbatim.
    """
    lines = (current or "").split("\n")
    while lines and lines[0].startswith(LINK_PREFIX):
        lines.pop(0)
        while lines and lines[0].strip() == "":
            lines.pop(0)
    body = "\n".join(lines).strip("\n")
    out = link_line(episode_video_id, question) + ("\n\n" + body if body else "")
    return out[:DESC_MAX]


def has_link(description: str, episode_video_id: str) -> bool:
    first = (description or "").split("\n", 1)[0]
    return first.startswith(LINK_PREFIX + episode_video_id)


def strip_block(description: str) -> str:
    """`description` without its "Shorts from this episode:" block."""
    lines = description.split("\n")
    out, skipping = [], False
    for line in lines:
        if line.strip() == BLOCK_HEAD:
            skipping = True
            continue
        if skipping:
            if line.strip() == "":
                skipping = False
            continue
        out.append(line)
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip("\n")


def shorts_block(shorts: list[tuple[str, str]]) -> str:
    """shorts: [(title, video_id)] in air order."""
    return "\n".join([BLOCK_HEAD, *[f"• {t} https://youtu.be/{v}" for t, v in shorts]])


def episode_description(current: str, shorts: list[tuple[str, str]]) -> str:
    """`current` with the Shorts block appended after the sources/footer and
    BEFORE the hashtag line, replacing any earlier block. Idempotent."""
    had_hashtags = discovery.is_hashtag_line((current or "").split("\n")[-1])
    hashtags = (current or "").split("\n")[-1] if had_hashtags else ""
    body = strip_block(discovery.strip_hashtag_line(current or ""))
    if shorts:
        body = body.rstrip("\n") + "\n\n" + shorts_block(shorts)
    out = body
    if hashtags:
        out = body.rstrip("\n") + "\n\n" + hashtags
    return out[:DESC_MAX]


def comment_text(episode_video_id: str, question: str) -> str:
    return f"{title_of(question)} Full episode: https://youtu.be/{episode_video_id}"


# ------------------------------------------------------------------- YouTube

class YouTube:
    """The thin client. Tests hand run() a fake with these three methods (named api_* so the
    static write-set audit never confuses them with r2.Backend.put)."""

    def __init__(self, token: str):
        self.token = token

    def _req(self, method: str, path: str, params: dict, body=None):
        q = urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{API}/{path}?{q}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     **({"Content-Type": "application/json; charset=UTF-8"}
                        if data is not None else {})})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    def api_get(self, path: str, params: dict) -> dict:
        return self._req("GET", path, params)

    def api_put(self, path: str, params: dict, body: dict) -> dict:
        return self._req("PUT", path, params, body)

    def api_post(self, path: str, params: dict, body: dict) -> dict:
        return self._req("POST", path, params, body)


def fetch_videos(yt, ids: list[str]) -> tuple[dict[str, dict], int]:
    """id -> {privacy, publishAt, snippet} for every id YouTube still knows.
    1 unit per 50 ids."""
    out, units = {}, 0
    ids = [i for i in dict.fromkeys(ids) if i]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        data = yt.api_get("videos", {"part": "snippet,status", "id": ",".join(chunk)})
        units += READ_UNITS
        for item in data.get("items") or []:
            st = item.get("status") or {}
            out[item["id"]] = {"privacy": st.get("privacyStatus"),
                               "publishAt": st.get("publishAt"),
                               "snippet": item.get("snippet") or {}}
    return out, units


def list_all(yt, path: str, params: dict) -> tuple[list[dict], int]:
    items, units, page = [], 0, None
    while True:
        p = dict(params, maxResults=50)
        if page:
            p["pageToken"] = page
        data = yt.api_get(path, p)
        units += READ_UNITS
        items += data.get("items") or []
        page = data.get("nextPageToken")
        if not page:
            return items, units


# --------------------------------------------------------------------- state

def load_shorts() -> dict:
    d = read_json(SHORTS_LEDGER, default={"published": [], "updated": None})
    d.setdefault("published", [])
    return d


def save_shorts(d: dict) -> None:
    d["updated"] = now()
    write_json(SHORTS_LEDGER, d)


def load_playlists() -> dict:
    d = read_json(PLAYLISTS, default={})
    d.setdefault("playlists", {})
    d.setdefault("sections", {})
    return d


def _public(v: dict | None) -> bool:
    return bool(v) and v.get("privacy") == "public"


def episode_link_for(token: str | None, slug: str, yt=None) -> str | None:
    """The episode id a NEW Short may link to right now, or None.

    Called by loop/shorts_lane.py:upload_short at upload time. None means
    "ship with the channel link and mark the row pending": the episode is not
    in the ledger, not public yet, or could not be read (a network error here
    must never fail an upload). LOOP_DRY_RUN reads nothing.
    """
    if up.DRY_RUN and yt is None:
        return None
    row = next((r for r in ledger.load()["published"]
                if r.get("slug") == slug and r.get("video_id")
                and not r.get("retired_at")), None)
    if not row:
        return None
    try:
        client = yt or YouTube(token)
        got, _ = fetch_videos(client, [row["video_id"]])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    return row["video_id"] if _public(got.get(row["video_id"])) else None


# ---------------------------------------------------------------------- plan

def plan(yt, episodes: list[dict], shorts: list[dict], pl: dict,
         alloc: list[str]) -> dict:
    """Everything the channel needs changed, computed from YouTube's current
    state. Reads only. Returns the plan plus the units the reads cost."""
    units = 0
    ids = [r["video_id"] for r in episodes] + [r["video_id"] for r in shorts]
    live, u = fetch_videos(yt, ids)
    units += u
    ep_by_slug = {r["slug"]: r for r in episodes}
    actions: list[dict] = []
    notes: list[str] = []
    newest = None
    for vid, v in live.items():
        if _public(v) and v.get("publishAt") and (newest is None or v["publishAt"] > newest):
            newest = v["publishAt"]

    # --- playlists: one per allocated domain, found by title before created
    missing = [d for d in alloc if not (pl["playlists"].get(d) or {}).get("id")]
    if missing:
        for d in missing:
            if d not in PLAYLIST_TITLES:
                raise RuntimeError(f"domain {d!r} is allocated but has no "
                                   f"playlist title in loop/handoff.py")
        mine, u = list_all(yt, "playlists", {"part": "snippet", "mine": "true"})
        units += u
        by_title = {(p.get("snippet") or {}).get("title"): p["id"] for p in mine}
        for d in missing:
            found = by_title.get(PLAYLIST_TITLES[d])
            if found:
                actions.append({"kind": "playlist_adopt", "domain": d, "id": found})
            else:
                actions.append({"kind": "playlist_create", "domain": d})

    # --- channel sections, once per playlist that exists
    for d in alloc:
        pid = (pl["playlists"].get(d) or {}).get("id")
        sec = pl["sections"].get(d) or {}
        if pid and not sec.get("id") and not sec.get("refused"):
            actions.append({"kind": "section_create", "domain": d, "playlist": pid})

    # --- Shorts: link line, comment, pending bookkeeping
    for s in shorts:
        v = live.get(s["video_id"])
        if v is None:
            notes.append(f"{s['slug']}: Short {s['video_id']} is not on the channel")
            continue
        ep = ep_by_slug.get(s["slug"])
        if not ep:
            notes.append(f"{s['slug']}: no episode in the ledger for this Short "
                         f"({s['video_id']}); nothing to hand off to")
            continue
        ev = live.get(ep["video_id"])
        if not _public(ev):
            if s.get("handoff") != "pending":
                actions.append({"kind": "mark_pending", "short": s["video_id"]})
            continue
        desc = (v["snippet"] or {}).get("description") or ""
        if not has_link(desc, ep["video_id"]) or s.get("handoff") != "done":
            actions.append({"kind": "short_desc", "short": s["video_id"],
                            "episode": ep["video_id"], "question": ep.get("question", ""),
                            "snippet": v["snippet"],
                            "write": not has_link(desc, ep["video_id"])})
        if _public(v) and not s.get("handoff_comment_id"):
            actions.append({"kind": "comment", "short": s["video_id"],
                            "episode": ep["video_id"], "question": ep.get("question", "")})

    # --- episodes: the Shorts block
    shorts_of: dict[str, list[tuple[str, str]]] = {}
    for s in sorted(shorts, key=lambda r: r.get("scheduled_publish_at") or ""):
        v = live.get(s["video_id"])
        if _public(v):
            title = (v["snippet"] or {}).get("title") or title_of(s["slug"].replace("-", " "))
            shorts_of.setdefault(s["slug"], []).append((title, s["video_id"]))
    for e in episodes:
        v = live.get(e["video_id"])
        if not _public(v):
            continue
        want = shorts_of.get(e["slug"]) or []
        desc = (v["snippet"] or {}).get("description") or ""
        if want and episode_description(desc, want) != desc:
            actions.append({"kind": "episode_desc", "episode": e["video_id"],
                            "shorts": want, "snippet": v["snippet"]})

    # --- playlist membership for every public video with a domain
    members: dict[str, dict[str, str]] = {}      # domain -> video_id -> item id
    need_members = set()
    for row in [*episodes, *shorts]:
        if not _public(live.get(row["video_id"])) or row.get("playlist_item_id"):
            continue
        d = domains.domain_of_slug(row["slug"])
        if d not in alloc:
            notes.append(f"{row['slug']}: domain {d!r} has no playlist")
            continue
        need_members.add(d)
    for d in need_members:
        pid = (pl["playlists"].get(d) or {}).get("id")
        if not pid:
            continue
        items, u = list_all(yt, "playlistItems", {"part": "snippet", "playlistId": pid})
        units += u
        members[d] = {((i.get("snippet") or {}).get("resourceId") or {}).get("videoId"): i["id"]
                      for i in items}
    for kind, rows in (("short", shorts), ("episode", episodes)):
        for row in rows:
            if not _public(live.get(row["video_id"])) or row.get("playlist_item_id"):
                continue
            d = domains.domain_of_slug(row["slug"])
            if d not in alloc:
                continue
            have = members.get(d, {}).get(row["video_id"])
            actions.append({"kind": "playlist_adopt_item" if have else "playlist_insert",
                            "what": kind, "video": row["video_id"], "domain": d,
                            "item": have})

    return {"actions": actions, "notes": notes, "read_units": units,
            "newest_input_at": newest, "live": live}


PRIORITY = {"playlist_adopt": 0, "playlist_create": 1, "section_create": 2,
            "mark_pending": 3, "playlist_adopt_item": 3,
            "short_desc": 4, "playlist_insert": 5, "comment": 6, "episode_desc": 7}


def writes_in(actions: list[dict]) -> int:
    """How many 50-unit writes `actions` need. A playlist creation counts
    twice: apply() makes the playlist's channel section in the same run."""
    return sum(2 if a["kind"] == "playlist_create" else 1 for a in actions
               if a["kind"] in ("playlist_create", "section_create", "comment",
                                "playlist_insert", "episode_desc")
               or (a["kind"] == "short_desc" and a.get("write", True)))


def _snippet_for_update(snippet: dict, description: str) -> dict:
    """A COMPLETE snippet for videos.update — it replaces the whole part."""
    keep = {k: snippet[k] for k in ("title", "description", "tags", "categoryId",
                                    "defaultLanguage", "defaultAudioLanguage")
            if k in snippet}
    if not keep.get("title") or not keep.get("categoryId"):
        raise RuntimeError("live snippet lacks title/categoryId; refusing to "
                           "write a partial snippet")
    keep["description"] = description
    return keep


class QuotaRefused(Exception):
    pass


def _is_quota(e: urllib.error.HTTPError, body: str) -> bool:
    return e.code == 403 and "quota" in body.lower()


def apply(st, yt, token: str, actions: list[dict], budget: int,
          episodes: list[dict], shorts: list[dict], pl: dict, led_c: dict
          ) -> tuple[int, list[dict]]:
    """Apply `actions` in priority order while `budget` writes remain.
    Returns (units spent, actions not applied). Every applied action is
    recorded in the ledgers BEFORE the next write, so a stop mid-way loses
    nothing already done."""
    ep_by_id = {r["video_id"]: r for r in episodes}
    sh_by_id = {r["video_id"]: r for r in shorts}
    spent, left = 0, []
    pending = sorted(actions, key=lambda a: PRIORITY[a["kind"]])
    for i, a in enumerate(pending):
        k = a["kind"]
        try:
            if k == "mark_pending":
                sh_by_id[a["short"]]["handoff"] = "pending"
                st.note(f"{a['short']}: episode not public yet; handoff pending")
                continue
            if k == "playlist_adopt":
                pl["playlists"][a["domain"]] = {"id": a["id"], "title": PLAYLIST_TITLES[a["domain"]],
                                                "adopted_at": now()}
                st.work(f"adopted existing playlist {a['id']} for {a['domain']}")
                continue
            if k == "playlist_adopt_item":
                row = (sh_by_id if a["what"] == "short" else ep_by_id)[a["video"]]
                row["playlist_item_id"] = a["item"]
                row["playlist"] = (pl["playlists"].get(a["domain"]) or {}).get("id")
                st.work(f"{a['video']} already in the {a['domain']} playlist; recorded")
                continue
            needs_write = k != "short_desc" or a.get("write", True)
            if needs_write and budget <= 0:
                left = pending[i:]
                break
            if k == "playlist_create":
                out = yt.api_post("playlists", {"part": "snippet,status"},
                              {"snippet": {"title": PLAYLIST_TITLES[a["domain"]],
                                           "description": PLAYLIST_DESCRIPTIONS[a["domain"]],
                                           "defaultLanguage": "en"},
                               "status": {"privacyStatus": "public"}})
                pl["playlists"][a["domain"]] = {"id": out["id"], "title": PLAYLIST_TITLES[a["domain"]],
                                                "created_at": now()}
                spent += WRITE_UNITS; budget -= 1
                st.work(f"created playlist {out['id']} \"{PLAYLIST_TITLES[a['domain']]}\"")
                # The section was not plannable without the id; make it now
                # rather than leave the shelf half-built for a run.
                if budget > 0:
                    spent += _section(st, yt, pl, a["domain"], out["id"])
                    budget -= 1
                continue
            if k == "section_create":
                spent += _section(st, yt, pl, a["domain"], a["playlist"])
                budget -= 1
                continue
            if k == "short_desc":
                row = sh_by_id[a["short"]]
                if a.get("write", True):
                    desc = short_description(a["snippet"].get("description") or "",
                                             a["episode"], a["question"])
                    yt.api_put("videos", {"part": "snippet"},
                           {"id": a["short"], "snippet": _snippet_for_update(a["snippet"], desc)})
                    spent += WRITE_UNITS; budget -= 1
                row["handoff"] = "done"
                row["handoff_episode"] = a["episode"]
                row["handoff_at"] = now()
                st.work(f"{a['short']}: description now opens with the link to "
                        f"episode {a['episode']}")
                continue
            if k == "playlist_insert":
                pid = (pl["playlists"].get(a["domain"]) or {}).get("id")
                if not pid:
                    left.append(a)
                    continue
                out = yt.api_post("playlistItems", {"part": "snippet"},
                              {"snippet": {"playlistId": pid,
                                           "resourceId": {"kind": "youtube#video",
                                                          "videoId": a["video"]}}})
                spent += WRITE_UNITS; budget -= 1
                row = (sh_by_id if a["what"] == "short" else ep_by_id)[a["video"]]
                row["playlist_item_id"] = out["id"]
                row["playlist"] = pid
                st.work(f"{a['video']} added to the {a['domain']} playlist")
                continue
            if k == "comment":
                row = sh_by_id[a["short"]]
                cid = comments.post_channel_comment(
                    token, a["short"], comment_text(a["episode"], a["question"]),
                    INSTRUCTION, led_c)
                spent += WRITE_UNITS; budget -= 1
                row["handoff_comment_id"] = cid
                row["handoff_comment_at"] = now()
                comments.save_ledger(led_c)
                st.work(f"{a['short']}: channel comment {cid} points at episode {a['episode']}")
                continue
            if k == "episode_desc":
                desc = episode_description(a["snippet"].get("description") or "", a["shorts"])
                yt.api_put("videos", {"part": "snippet"},
                       {"id": a["episode"], "snippet": _snippet_for_update(a["snippet"], desc)})
                spent += WRITE_UNITS; budget -= 1
                row = ep_by_id[a["episode"]]
                row["shorts_block"] = [v for _, v in a["shorts"]]
                row["shorts_block_at"] = now()
                st.work(f"{a['episode']}: description lists {len(a['shorts'])} Short(s)")
                continue
            raise RuntimeError(f"unknown action {k}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if _is_quota(e, body):
                left = pending[i:]
                raise QuotaRefused(f"{k} on {a.get('short') or a.get('episode') or a.get('video') or a.get('domain')}: "
                                   f"HTTP {e.code} {body}") from e
            raise RuntimeError(f"YouTube refused {k} on "
                               f"{a.get('short') or a.get('episode') or a.get('video') or a.get('domain')}: "
                               f"HTTP {e.code} {body}") from e
    return spent, left


def _section(st, yt, pl: dict, domain: str, pid: str) -> int:
    """One channel section showing `pid`. A refusal that is not a quota
    refusal is recorded in playlists.json and is a note — the playlist itself
    is live and linked from every video. Returns units spent."""
    try:
        out = yt.api_post("channelSections", {"part": "snippet,contentDetails"},
                      {"snippet": {"type": "singlePlaylist"},
                       "contentDetails": {"playlists": [pid]}})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        if _is_quota(e, body):
            raise
        pl["sections"][domain] = {"refused": f"HTTP {e.code} {body}",
                                  "playlist": pid, "at": now()}
        st.note(f"channelSections.insert refused for {domain} (HTTP {e.code}); "
                f"recorded, the playlist itself is live")
        return WRITE_UNITS
    pl["sections"][domain] = {"id": out.get("id"), "playlist": pid, "created_at": now()}
    st.work(f"channel section {out.get('id')} shows the {domain} playlist")
    return WRITE_UNITS


def save_all(episodes_doc: dict, shorts_doc: dict, pl: dict, hs: dict) -> None:
    ledger.save(episodes_doc)
    save_shorts(shorts_doc)
    write_json(PLAYLISTS, pl)
    write_json(HANDOFF_STATE, hs)


def run(dry_run: bool = False, yt=None, token: str | None = None) -> int:
    cfg = config()
    alloc = list(domains.allocation(cfg))
    episodes_doc = ledger.load()
    shorts_doc = load_shorts()
    pl = load_playlists()
    episodes = [r for r in episodes_doc["published"]
                if r.get("video_id") and not r.get("retired_at")]
    shorts = [r for r in shorts_doc["published"] if r.get("video_id")]

    if dry_run:
        if yt is None:
            creds = up.load_credentials(cfg)
            if not creds or creds.get("unusable"):
                code, msg, _ = up.credential_stop(creds, cfg)
                print(f"DRY RUN cannot read the channel: {code} — {msg}")
                return 3
            yt = YouTube(up.access_token(creds))
        p = plan(yt, episodes, shorts, pl, alloc)
        by_kind: dict[str, int] = {}
        for a in p["actions"]:
            by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
        public = sum(1 for v in p["live"].values() if _public(v))
        print(f"{len(episodes)} episode(s) and {len(shorts)} Short(s) in the ledgers; "
              f"{public} public on the channel; reads cost {p['read_units']} unit(s)")
        for k in sorted(by_kind, key=lambda k: PRIORITY[k]):
            print(f"  {by_kind[k]:>3}  {k}")
        for n in p["notes"]:
            print(f"  note: {n}")
        writes = writes_in(p["actions"])
        print(f"\n{writes} write(s) × {WRITE_UNITS} = {writes * WRITE_UNITS} units; "
              f"affordable today with the upload/Shorts reserve kept: "
              f"{quota.units_affordable(WRITE_UNITS, writes, reserve=quota.deferrable_reserve())}")
        print("\nDRY RUN - nothing written.")
        return 0

    with Stage(LANE, week_id(),
               zero_work_hint="Every live Short already links to its episode, "
                              "every live video is in its domain playlist.") as st:
        if yt is None:
            creds = up.load_credentials(cfg)
            if not creds or creds.get("unusable"):
                code, msg, unblock = up.credential_stop(creds, cfg)
                st.named_stop(code, msg, unblock=unblock)
            token = up.access_token(creds)
            yt = YouTube(token)
        led_c = comments.load_ledger()
        p = plan(yt, episodes, shorts, pl, alloc)
        for n in p["notes"]:
            st.note(n)
        hs = {"last_run_at": now(), "lane": LANE, "deferred": [],
              "resets_at": None, "notes": p["notes"]}
        writes = writes_in(p["actions"])
        budget = quota.units_affordable(WRITE_UNITS, writes, reserve=quota.deferrable_reserve())
        st.note(f"{len(p['actions'])} action(s), {writes} write(s); "
                f"{budget} affordable today after the upload/Shorts reserve")
        spent, left = p["read_units"], []
        failure = None
        try:
            s, left = apply(st, yt, token or "", p["actions"], budget,
                            episodes, shorts, pl, led_c)
            spent += s
        except QuotaRefused as e:
            failure = ("quota", str(e))
            left = [a for a in p["actions"] if not _done(a, episodes, shorts, pl)]
        except RuntimeError as e:
            failure = ("rejected", str(e))
        # Record first, judge second: whatever happened, what WAS done is kept.
        quota.spend(spent, LANE)
        hs["deferred"] = sorted({a.get("short") or a.get("episode") or a.get("video")
                                 or a.get("domain") for a in left
                                 if a["kind"] != "mark_pending"})
        hs["resets_at"] = quota.next_reset() if left else None
        hs["units_spent"] = spent
        save_all(episodes_doc, shorts_doc, pl, hs)
        if failure and failure[0] == "rejected":
            st.named_stop("HANDOFF_WRITE_REJECTED", failure[1],
                          detail={"deferred": hs["deferred"]},
                          unblock="Everything before the refusal was applied and "
                                  "recorded. Check the scope (youtube) and the id; "
                                  "the next run retries only what is missing.")
        if not st.units and not left:
            # Reads only, or bookkeeping (a Short marked pending). The ledgers
            # are saved above; Rule 0 is answered with a NAMED, self-resolving
            # stop rather than a tick.
            st.named_stop(
                "HANDOFF_UP_TO_DATE",
                f"every public Short links to its episode, every public episode "
                f"lists its Shorts, every public video is in its playlist "
                f"({len(shorts)} Short(s), {len(episodes)} episode(s) examined; "
                f"{sum(1 for a in p['actions'] if a['kind'] == 'mark_pending')} "
                f"Short(s) newly pending on an episode not yet public)",
                detail={"shorts": len(shorts), "episodes": len(episodes),
                        "newest_input_at": p["newest_input_at"]},
                unblock="Nothing to do; this lane runs after every Shorts and "
                        "upload lane run and acts the first time something new is public.")
        if left:
            st.named_stop(
                "HANDOFF_QUOTA_DEFERRED",
                f"{len(left)} action(s) wait for tomorrow's quota; "
                f"{len(st.units)} applied this run"
                + (f" ({failure[1]})" if failure else ""),
                detail={"resets_at": quota.next_reset(), "deferred": hs["deferred"],
                        "newest_input_at": p["newest_input_at"]},
                unblock="Nothing to do; the allowance resets at midnight Pacific "
                        "and this lane runs twice daily. Applied work is recorded.")
    return 0


def _done(a: dict, episodes, shorts, pl) -> bool:
    """Was this planned action already applied (used after a mid-run quota refusal)?"""
    sh = {r["video_id"]: r for r in shorts}
    ep = {r["video_id"]: r for r in episodes}
    k = a["kind"]
    if k in ("playlist_adopt", "playlist_create"):
        return bool((pl["playlists"].get(a["domain"]) or {}).get("id"))
    if k == "section_create":
        s = pl["sections"].get(a["domain"]) or {}
        return bool(s.get("id") or s.get("refused"))
    if k == "mark_pending":
        return True
    if k == "short_desc":
        return sh[a["short"]].get("handoff") == "done"
    if k == "comment":
        return bool(sh[a["short"]].get("handoff_comment_id"))
    if k in ("playlist_insert", "playlist_adopt_item"):
        row = (sh if a["what"] == "short" else ep)[a["video"]]
        return bool(row.get("playlist_item_id"))
    if k == "episode_desc":
        return ep[a["episode"]].get("shorts_block") == [v for _, v in a["shorts"]]
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="read the channel, print the plan and the quota it needs, write nothing")
    a = ap.parse_args()
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
