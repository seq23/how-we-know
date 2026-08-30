"""Receipts — the evidence a stage actually produced what it claims.

The standing rule is that nothing goes public without a receipt proving it
uploaded correctly. Receipts are also how the Mac reports back to Actions: git
is the message bus, so a receipt committed on Tuesday night is what Friday's
workflow reads to decide whether a video may be flipped to public.

A receipt is only ever written **after** the artefact exists and has been
measured. It records size, duration and a content hash, so a later stage can
tell "rendered" from "rendered, then silently truncated".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import LOOP, RECEIPTS, ROOT, now, read_json, sha256, write_json  # noqa: E402

QUEUE = LOOP / "render_queue.json"


def probe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60)
        return round(float(r.stdout.strip()), 2) if r.returncode == 0 else None
    except Exception:
        return None


def render_receipt(slug: str, week: str) -> dict:
    q = read_json(QUEUE)
    it = next((i for i in q["items"] if i["slug"] == slug), None)
    if it is None:
        raise SystemExit(f"{slug} is not in the render queue")
    video = ROOT / it["render"]
    if not video.exists():
        raise SystemExit(f"no rendered video at {video} — refusing to write a "
                         f"receipt for something that does not exist")
    dur = probe_duration(video)
    rec = {
        "kind": "render",
        "week": week,
        "slug": slug,
        "question": it["question"],
        "at": now(),
        "video": it["render"],
        "bytes": video.stat().st_size,
        "duration_s": dur,
        "duration_min": round(dur / 60, 2) if dur else None,
        "sha256": sha256(video),
        "work_copy_sha256": it.get("work_copy_sha256"),
        "pov_choice": it.get("pov_choice"),
        "pov_substituted": it.get("pov_substituted"),
        "planned_beats": it.get("planned_beats"),
        "sources": it.get("source_count"),
    }
    # A one-frame or zero-byte file is a failed render wearing a success mask.
    rec["healthy"] = bool(dur and dur > 60 and rec["bytes"] > 1_000_000)
    write_json(RECEIPTS / f"{week}-{slug}-render.json", rec)
    it["render_receipt"] = f"loop/receipts/{week}-{slug}-render.json"
    it["status"] = "rendered" if rec["healthy"] else "render-suspect"
    write_json(QUEUE, q)
    return rec


def upload_receipt(slug: str, week: str, video_id: str, privacy: str,
                   dry_run: bool = False) -> dict:
    q = read_json(QUEUE)
    it = next((i for i in q["items"] if i["slug"] == slug), None)
    if it is None:
        raise SystemExit(f"{slug} is not in the render queue")
    rec = {
        "kind": "upload",
        "week": week,
        "slug": slug,
        "at": now(),
        "video_id": video_id,
        "privacy": privacy,
        "dry_run": dry_run,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "render_receipt": it.get("render_receipt"),
    }
    write_json(RECEIPTS / f"{week}-{slug}-upload.json", rec)
    it["upload_receipt"] = f"loop/receipts/{week}-{slug}-upload.json"
    it["video_id"] = video_id
    it["privacy"] = privacy
    it["status"] = "uploaded-private" if privacy == "private" else f"uploaded-{privacy}"
    write_json(QUEUE, q)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--slug", required=True)
    r.add_argument("--week", required=True)
    u = sub.add_parser("upload")
    u.add_argument("--slug", required=True)
    u.add_argument("--week", required=True)
    u.add_argument("--video-id", required=True)
    u.add_argument("--privacy", default="private")
    u.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "render":
        rec = render_receipt(a.slug, a.week)
    else:
        rec = upload_receipt(a.slug, a.week, a.video_id, a.privacy, a.dry_run)
    print(json.dumps(rec, indent=2))
    return 0 if rec.get("healthy", True) else 1


if __name__ == "__main__":
    sys.exit(main())
