"""The ONE safe way to write a video's snippet, and the one list of live videos.

## Why this file exists at all

`videos.update` is a REPLACE, not a patch. Google's own reference says it
plainly: *"if your request does not specify a value for a property that already
has a value, the property's existing value will be deleted."* The parts you
name in `part=` are rewritten wholesale from the body you send.

So a request of

    PUT videos?part=snippet,localizations
    {"id": "...", "snippet": {"defaultLanguage": "en"}, "localizations": {...}}

does not "add a default language". It **erases the title, the description, the
tags and the categoryId of a live video** and leaves it untitled in Education's
place. On this channel that would be fifteen episodes at once, silently, with a
200 OK in the log.

There is exactly one correct shape — read, merge, write back whole — and it
lives here so no lane can get it wrong twice. `loop/validate.py` V19 fails the
build if any other module in `loop/` issues a snippet-bearing `videos.update`.

## The second trap: defaultLanguage

`localizations` are rejected outright unless `snippet.defaultLanguage` is set —
the API's own error is *"the request is trying to add localized video details
without specifying the default language of the video details"*. It is not
listed as a required property anywhere, so it is easy to omit and get a 400
that names something else. `merge_snippet` sets it, and V18 guards it.

Scopes: `videos.list` and `videos.update` are both covered by the plain
`https://www.googleapis.com/auth/youtube` scope this channel's token already
carries. Confirmed against the API reference and the stored grant on
2026-09-02. Nothing in this file needs `force-ssl`; only captions do.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import ledger  # noqa: E402

VIDEOS = "https://www.googleapis.com/youtube/v3/videos"

DEFAULT_LANGUAGE = "en"

# The snippet properties videos.update will destroy if they are not sent back.
# `title` and `categoryId` are required by the API; the other two are not, and
# that is precisely why they are the ones that get lost.
CARRIED = ("title", "description", "tags", "categoryId",
           "defaultLanguage", "defaultAudioLanguage")


class MergeRefused(Exception):
    """A merge that would have written a partial snippet. Never a 200 OK."""


# ------------------------------------------------------------------ reading

def get_video(token: str, video_id: str, part: str = "snippet,localizations",
              timeout: int = 30) -> dict | None:
    """The CURRENT server-side truth for one video. `None` if it is gone.

    Always call this immediately before an update. Merging onto a cached copy
    reintroduces the whole bug: the cache is what the repo last wrote, not what
    the channel currently says, and the difference is somebody's manual edit in
    Studio which the merge would then revert.
    """
    q = urllib.parse.urlencode({"part": part, "id": video_id})
    req = urllib.request.Request(f"{VIDEOS}?{q}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    items = data.get("items") or []
    return items[0] if items else None


# ------------------------------------------------------------------ merging

def merge_snippet(current: dict, default_language: str = DEFAULT_LANGUAGE,
                  **changes) -> dict:
    """Build a COMPLETE snippet from the live one, plus `changes`.

    Refuses rather than truncates. If the snippet handed in has no title or no
    categoryId, the live video either does not exist or was read with the wrong
    `part` — and sending the result would blank the real one. That is a
    MergeRefused, not a best effort.

    Returns a new dict; `current` is never mutated.
    """
    if not isinstance(current, dict):
        raise MergeRefused("no snippet was read back from videos.list; "
                           "refusing to write one from nothing")
    for required in ("title", "categoryId"):
        if not current.get(required):
            raise MergeRefused(
                f"the live snippet has no {required!r}. videos.update would "
                f"replace the whole snippet, so writing this would erase the "
                f"video's metadata. Read it again with part=snippet.")

    merged = {k: current[k] for k in CARRIED if k in current}
    merged.update(changes)
    merged["defaultLanguage"] = merged.get("defaultLanguage") or default_language
    merged.setdefault("defaultAudioLanguage", default_language)

    # The tripwire, restated where it cannot be skipped: whatever the caller
    # asked for, the four destroyable properties must still be on their way out.
    for required in ("title", "categoryId"):
        if not merged.get(required):
            raise MergeRefused(f"the merged snippet lost {required!r}")
    if "description" in current and "description" not in merged:
        raise MergeRefused("the merged snippet dropped the description")
    if "tags" in current and "tags" not in merged:
        raise MergeRefused("the merged snippet dropped the tags")
    return merged


def update_localizations(token: str, video_id: str, current_snippet: dict,
                         localizations: dict, timeout: int = 60,
                         dry_run: bool = False) -> dict:
    """Write `localizations` back beside a COMPLETE, merged snippet.

    Returns the body that was sent, so a caller can record and a test can
    assert on it without a network. Under `dry_run` it composes and validates
    the body and sends nothing — the composition is the part worth exercising.
    """
    snippet = merge_snippet(current_snippet)
    body = {"id": video_id, "snippet": snippet, "localizations": localizations}
    if dry_run:
        return body
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{VIDEOS}?part=snippet,localizations", data=data, method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()
    return body


# ------------------------------------------------------- the live video list

def live_videos() -> list[dict]:
    """Every video the channel currently has up, from the one ledger.

    Retired rows are excluded: `loop/retire.py` keeps them (there is no delete
    path) but they are private forever, and captioning or localising a retired
    video spends quota on something nobody can see. A row superseded by another
    is retired, so this returns each episode once.
    """
    rows = ledger.load()["published"]
    return [r for r in rows if r.get("video_id") and not r.get("retired_at")]


if __name__ == "__main__":
    for row in live_videos():
        print(f"{row['video_id']}  {row.get('privacy','?'):<8} {row['slug']}")
