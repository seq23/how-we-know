"""Every video on the channel: embedding allowed, "altered or synthetic content" answered No.

    .venv/bin/python loop/video_settings.py --dry-run   # list what would change
    .venv/bin/python loop/video_settings.py             # apply

OWNER DECISION, 14 Sep 2026: "edit video details on all videos to 'allow embedding' and click No
on the radio button asking about ai use". Both are fields of the video's `status` in the Data API
- `embeddable` and `containsSyntheticMedia` - which is the same field Studio's radio button writes.
One `videos.update` per video that needs it (50 units each), reading the channel's uploads
playlist first so nothing is guessed. Videos already correct are skipped and cost nothing.

The uploaders set both fields at upload from today (loop/upload.py, loop/shorts_lane.py), so this is
the one-time correction of the back catalogue and the check that it stays correct.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "auth"))
sys.path.insert(0, str(ROOT / "loop"))

import tokens                                              # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
WANT = {"embeddable": True, "containsSyntheticMedia": False}
# "paid promotion" answered No as well (owner, 14 Sep 2026). A separate part of the video resource.
WANT_PAID = {"hasPaidProductPlacement": False}
# `containsSyntheticMedia` is WRITE-ONLY in practice: the read never returns it, so it is written on
# every pass and cannot be used to decide whether a video needs a pass. The two readable fields decide.
READABLE = ("embeddable",)


def get(token: str, path: str, params: dict) -> dict:
    req = urllib.request.Request(f"{API}/{path}?{urllib.parse.urlencode(params)}",
                                 headers={"Authorization": f"Bearer {token}"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def every_video(token: str) -> list[dict]:
    ch = get(token, "channels", {"part": "contentDetails", "mine": "true"})["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    page = None
    while True:
        r = get(token, "playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": 50,
                                         **({"pageToken": page} if page else {})})
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        page = r.get("nextPageToken")
        if not page:
            break
    out: list[dict] = []
    for i in range(0, len(ids), 50):
        out += get(token, "videos", {"part": "snippet,status,paidProductPlacementDetails", "id": ",".join(ids[i:i + 50])})["items"]
    return out


def update_status(token: str, video: dict) -> None:
    status = {**video["status"], **WANT}
    # publishAt may only be sent alongside privacyStatus=private, which is how a scheduled video
    # already reads; an already-public video carries no publishAt. Pass through as read.
    body = json.dumps({"id": video["id"], "status": status, "paidProductPlacementDetails": WANT_PAID}).encode()
    req = urllib.request.Request(f"{API}/videos?part=status,paidProductPlacementDetails", data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    urllib.request.urlopen(req, timeout=60).read()


def needs_change(v: dict) -> bool:
    st = v.get("status", {})
    paid = v.get("paidProductPlacementDetails", {}) or {}
    return any(st.get(k) != WANT[k] for k in READABLE) or any(paid.get(k) != w for k, w in WANT_PAID.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="write every video, not only those whose readable fields differ (the AI answer cannot be read back)")
    a = ap.parse_args()
    tok = tokens.load()
    if "access_token" not in tok:
        print(f"credentials unusable: {tok.get('status')}")
        return 3
    token = tok["access_token"]
    videos = every_video(token)
    if not videos:
        print("FAIL: the channel returned zero videos - nothing examined, nothing proven")
        return 1
    todo = [v for v in videos if needs_change(v)] if not a.all else videos
    print(f"{len(videos)} video(s) on the channel; {len(todo)} need a change")
    for v in todo:
        st = v["status"]
        print(f"  {v['id']}  embeddable={st.get('embeddable')}  paid={(v.get('paidProductPlacementDetails') or {}).get('hasPaidProductPlacement')}  {v['snippet']['title'][:60]}")
    if a.dry_run or not todo:
        return 0
    done, failed = 0, []
    for v in todo:
        try:
            update_status(token, v)
            done += 1
        except urllib.error.HTTPError as e:
            failed.append((v["id"], e.code, e.read().decode()[:200]))
            if e.code == 403 and "quota" in str(failed[-1][2]).lower():
                print("quota exhausted for today; re-run tomorrow, it resumes where it stopped")
                break
    print(f"updated {done}; failed {len(failed)}")
    for f in failed:
        print("  ", f)
    # Verify by reading back, never by trusting the write.
    after = [v for v in every_video(token) if needs_change(v)]
    print(f"read back: {len(after)} video(s) still differ on the readable fields (embedding, paid promotion); "
          f"the AI answer is write-only and is checked in Studio")
    return 0 if not after and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
