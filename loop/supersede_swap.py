"""Swap a private, scheduled upload whose render was superseded AFTER it went up.

WHY (2026-10-15). how-deep-can-a-sperm-whale-go was uploaded by the Mac's
backfill lane at 2026-10-13T14:05Z as hh5mMno-Iis (private, publishAt
2026-11-09T16:00Z). The Mac's ledger row did not reach origin/main until #215
(19:34Z), so the cloud queue-reopen run at 14:44Z read a ledger WITHOUT it:
loop/lengthen.py published_slugs() did not contain the slug, queue_slugs()
treated it as still queued, and the episode was re-opened with a new cold open.
The Mac bound it at 2026-10-14T04:00Z (full re-render; the old cut recorded in
loop/state/superseded_renders.json). Nothing anywhere handled "already uploaded
privately, then superseded": YouTube kept the OLD opening and would have
published it on 9 Nov, and the hook rework was wasted.

Owner rule (13 Oct 2026): the queue and future uploads get the new hook; a video
already PUBLIC is never re-uploaded or privated. A private, scheduled video is
queue. So this lane step, run by loop/cloud_upload.py before the day's new
uploads and from the same quota order:

  1. finds ledger rows whose render was superseded after their upload
     (superseded_at > uploaded_at), not retired, not already swapped;
  2. NEVER touches a public one (ledger says public, its date has passed, or
     YouTube reads it back public) - it is named and left alone;
  3. uploads the new render (R2 shelf, sha-verified, never the superseded cut)
     PRIVATE with no date, same title as the live video, description and
     chapters rebuilt by upload.build_payload from the new timeline, thumbnail;
  4. waits (bounded) for it to read back `processed`; if it does not, the
     swap resumes on the next run from loop/state/superseded_swaps.json;
  5. dates the new video with the SAME publishAt, verifies it, inserts its
     English caption track;
  6. makes the old video private with NO publishAt (publish.cancel_schedule) and
     verifies it - NEVER deletes (retire.py: there is no delete path here);
  7. repoints the ledger (new row; old row retired as superseded_duplicate with
     `schedule_was`), Shorts hand-off targets and the caption record.

Quota: SWAP_UNITS through quota.units_affordable with the same reserve the
episode lane uses. Not affordable or not shelved yet -> carried to tomorrow.
If tomorrow's run would be too late for the publish time, the named stop
SUPERSEDED_SWAP_LATE (needs_human) reaches the owner.

Pinned by loop/tests/test_supersede_swap.py.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ledger                                              # noqa: E402
import quota                                               # noqa: E402
from common import LOOP, now, read_json, write_json        # noqa: E402

STATE = LOOP / "state" / "superseded_swaps.json"
SUPERSEDED = LOOP / "state" / "superseded_renders.json"
SHORTS_LEDGER = LOOP / "state" / "shorts_ledger.json"

# One swap end to end: videos.insert, thumbnail, the new video's publishAt,
# its caption track, the old video's private flip and the unlisted->private
# round-trip that clears its publishAt (publish.cancel_schedule), plus reads.
SWAP_UNITS = (quota.UPLOAD + quota.THUMBNAIL + quota.PRIVACY_FLIP
              + quota.CAPTION_INSERT + 3 * quota.VIDEO_UPDATE + 30)   # 2,280

# The lane runs daily; a swap still waiting when its publish time is closer
# than one run away will not make it unattended.
NEXT_RUN_MARGIN = timedelta(hours=30)

PROCESS_WAIT_S = 900
PROCESS_POLL_S = 20


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_state() -> dict:
    d = read_json(STATE, default={"swaps": {}})
    d.setdefault("swaps", {})
    return d


def is_public(row: dict, at: datetime) -> bool:
    """Public by the ledger's own account: never swapped."""
    if row.get("privacy") == "public" or row.get("published_at"):
        return True
    when = _ts(row.get("scheduled_publish_at"))
    return bool(when and when <= at)


def candidates(led: dict, superseded: dict) -> list[dict]:
    """Ledger rows whose render was superseded after they were uploaded."""
    out = []
    for r in led.get("published") or []:
        if (not r.get("video_id") or r.get("retired_at")
                or r.get("status") == "superseded_duplicate"):
            continue
        sup = superseded.get(r.get("slug") or "")
        if not sup:
            continue
        up_at, sup_at = _ts(r.get("uploaded_at")), _ts(sup.get("superseded_at"))
        if up_at and sup_at and sup_at > up_at:
            out.append(r)
    return out


class Api:
    """The real YouTube calls. A test passes its own object of this shape."""

    def __init__(self, token: str):
        self.token = token

    def status(self, vid):
        import publish as P                                # noqa: PLC0415
        full = P.read_status_full(self.token, vid)
        if full.get("found"):
            full.update({k: v for k, v in P.read_status(self.token, vid).items()
                         if k not in full})
        return full

    def payload(self, slug, question):
        import domains as _dom                             # noqa: PLC0415
        import upload as up                                # noqa: PLC0415
        sp = _dom.script_of(slug)
        root = LOOP.parent
        return up.build_payload({"slug": slug, "question": question,
                                 "script": (str(sp.relative_to(root)) if sp
                                            else f"scripts/{slug}.md")})

    def upload(self, payload, render: Path) -> str:
        import upload as up                                # noqa: PLC0415
        return up.resumable_upload(self.token, payload, render)

    def thumbnail(self, vid, img: Path):
        import backfill                                    # noqa: PLC0415
        backfill.set_thumbnail(self.token, vid, img)

    def schedule(self, vid, stamp):
        import publish as P                                # noqa: PLC0415
        P.set_privacy(self.token, vid, "private", publish_at=stamp)

    def make_private(self, vid):
        import publish as P                                # noqa: PLC0415
        P.set_privacy(self.token, vid, "private")

    def cancel_schedule(self, vid):
        import publish as P                                # noqa: PLC0415
        return P.cancel_schedule(self.token, vid)

    def insert_caption(self, vid, srt: Path) -> str:
        import captions_lane                               # noqa: PLC0415
        return captions_lane.insert_track(self.token, vid, srt)


def _srt(slug: str) -> Path | None:
    import captions_lane                                   # noqa: PLC0415
    p = captions_lane.srt_for(slug)
    return p if p.exists() and captions_lane.cue_count(p) > 0 else None


def _wait_processed(api, vid, sleep=time.sleep, wait_s=PROCESS_WAIT_S) -> bool:
    waited = 0
    while True:
        s = api.status(vid)
        if s.get("upload_status") == "processed":
            return True
        if s.get("upload_status") in ("failed", "rejected", "deleted"):
            return False
        if waited >= wait_s:
            return False
        sleep(PROCESS_POLL_S)
        waited += PROCESS_POLL_S


def _repoint(old: str, new: str, slug: str, srt: Path | None, cid: str | None,
             lane: str) -> list[str]:
    """Everything keyed on the old video id now names the new one."""
    done = []
    led = ledger.load()
    for r in led["published"]:
        if r.get("video_id") == old and not r.get("retired_at"):
            stamp = r.pop("scheduled_publish_at", None)
            r["schedule_was"] = stamp
            r["schedule_cancelled_at"] = now()
            r["privacy"] = "private"
            r["status"] = "superseded_duplicate"
            r["retired_at"] = now()
            r["retired_reason"] = ("render superseded after upload; replaced "
                                   f"by {new} (loop/supersede_swap.py)")
            r["superseded_by"] = new
            new_row = {k: v for k, v in r.items()
                       if k in ("slug", "question", "title")}
            new_row.update({"video_id": new, "uploaded_at": now(),
                            "privacy": "private", "scheduled_publish_at": stamp,
                            "replaces": old,
                            "note": f"{lane}: re-upload of the superseded "
                                    f"render, scheduled, not yet public"})
            led["published"].append(new_row)
            done.append(f"ledger: {slug} now {new}; {old} retired as "
                        f"superseded_duplicate (schedule_was {stamp})")
            break
    ledger.save(led)

    sh = read_json(SHORTS_LEDGER, default=None)
    if sh:
        n = 0
        for r in sh.get("published") or []:
            if r.get("handoff_episode") == old:
                r["handoff_episode"] = new
                r["handoff"] = "pending"
                n += 1
        if n:
            write_json(SHORTS_LEDGER, sh)
            done.append(f"shorts: {n} hand-off target(s) {old} -> {new}")

    if cid and srt:
        import captions_lane                               # noqa: PLC0415
        cs = captions_lane.load_state()
        cs["videos"][new] = {
            "slug": slug, "caption_id": cid, "language": captions_lane.LANGUAGE,
            "srt_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
            "cues": captions_lane.cue_count(srt), "track_kind": "standard",
            "source": "inserted", "recorded_at": now()}
        captions_lane.save_state(cs)
        done.append(f"captions: {new} track {cid} recorded")
    return done


def _scheduled(got: dict, stamp: str) -> bool:
    return (got.get("privacy") == "private"
            and (got.get("publishAt") or "")[:19] == stamp[:19])


def _retired(got: dict) -> bool:
    return got.get("privacy") == "private" and not got.get("publishAt")


def _read_until(api, vid: str, done, lane: str, sleep) -> dict:
    """Read `vid` until `done(status)` or publish.READBACK_WAITS_S runs out.

    A write YouTube applied can read back stale for seconds (see the list's
    comment in publish.py); one immediate read is not a verdict.
    """
    import publish as P                                    # noqa: PLC0415
    got = api.status(vid)
    quota.spend(quota.VIDEO_READ, lane)
    for wait in P.READBACK_WAITS_S:
        if done(got):
            break
        sleep(wait)
        got = api.status(vid)
        quota.spend(quota.VIDEO_READ, lane)
    return got


def _finish(st, api, rec: dict, lane: str, sleep=time.sleep) -> bool:
    """Date the new video, caption it, retire the old one, repoint. True = done."""
    old, new, stamp, slug = rec["old"], rec["new"], rec["stamp"], rec["slug"]
    live_old = api.status(old)
    if live_old.get("privacy") == "public":
        st.note(f"SWAP ABANDONED {slug}: {old} went public before the swap "
                f"finished; it is never privated. {new} stays private, undated.")
        rec["phase"] = "abandoned_old_public"
        return True
    # READ FIRST: a resumed swap whose earlier write applied (and read back
    # stale) is not re-sent.
    got = api.status(new)
    quota.spend(quota.VIDEO_READ, lane)
    if not _scheduled(got, stamp):
        api.schedule(new, stamp)
        quota.spend(quota.PRIVACY_FLIP, lane)
        got = _read_until(api, new, lambda g: _scheduled(g, stamp), lane, sleep)
    if not _scheduled(got, stamp):
        st.named_stop("SUPERSEDED_SWAP_NOT_SCHEDULED",
                      f"{new} (new cut of {slug}) should be private with "
                      f"publishAt {stamp} but reads {got}. {old} is untouched "
                      f"and still scheduled.",
                      unblock="Check both videos in YouTube Studio.")
    cid, srt = None, _srt(slug)
    if srt:
        try:
            cid = api.insert_caption(new, srt)
            quota.spend(quota.CAPTION_INSERT, lane)
        except Exception as e:                             # noqa: BLE001
            st.note(f"{slug}: caption insert on {new} failed ({e}); the "
                    f"captions lane inserts it from the ledger")
    api.make_private(old)
    cleared = api.cancel_schedule(old)
    quota.spend(3 * quota.VIDEO_UPDATE, lane)
    after = _read_until(api, old, _retired, lane, sleep)
    if not _retired(after):
        st.named_stop("SUPERSEDED_SWAP_OLD_NOT_RETIRED",
                      f"{old} (old cut of {slug}) should be private with no "
                      f"publishAt but reads {after}; {new} is scheduled for "
                      f"{stamp}, so both could air.",
                      unblock=f"Set {old} to private and clear its schedule "
                              f"in YouTube Studio. Never delete it.")
    st.work(f"{slug}: {old} privated, publishAt {cleared or stamp} cleared; "
            f"never deleted")
    for line in _repoint(old, new, slug, srt, cid, lane):
        st.work(line)
    rec["phase"] = "done"
    rec["done_at"] = now()
    return True


def run(st, *, api_factory, shelf_look, fetch, tmp: Path, lane: str,
        reserve: int, dry_run: bool = False, at: datetime | None = None,
        sleep=time.sleep, wait_s: int = PROCESS_WAIT_S) -> dict:
    """The lane step. Returns what it did, by slug, for the caller and tests."""
    at = at or datetime.now(timezone.utc)
    led = ledger.load()
    sup = read_json(SUPERSEDED, default={})
    state = load_state()
    out = {"swapped": [], "public": [], "waiting": {}, "inflight": []}
    api = None

    for row in candidates(led, sup):
        slug, old = row["slug"], row["video_id"]
        stamp = row.get("scheduled_publish_at")
        if is_public(row, at):
            out["public"].append(slug)
            st.note(f"{slug}: {old} is public; its render was superseded after "
                    f"upload but a public video is never re-uploaded or "
                    f"privated (owner, 13 Oct 2026). Left as is.")
            continue
        if not stamp:
            out["waiting"][slug] = "no scheduled_publish_at on the ledger row"
            continue
        rec = state["swaps"].get(slug)
        if rec and rec.get("old") == old and rec.get("phase") == "uploaded":
            if dry_run:
                out["waiting"][slug] = "DRY RUN: would resume the swap"
                continue
            api = api or api_factory()
            if not _wait_processed(api, rec["new"], sleep, wait_s):
                out["waiting"][slug] = f"{rec['new']} is not processed yet"
                out["inflight"].append(slug)
                continue
            _finish(st, api, rec, lane, sleep)
            write_json(STATE, state)
            out["swapped"].append(slug)
            continue

        loc = shelf_look(slug)
        if isinstance(loc, str):
            out["waiting"][slug] = f"new render not shelved: {loc}"
            continue
        if not _srt(slug):
            out["waiting"][slug] = f"captions/{slug}.srt missing or empty"
            continue
        if not dry_run and quota.units_affordable(SWAP_UNITS, 1, reserve=reserve) < 1:
            out["waiting"][slug] = (f"quota: a swap costs {SWAP_UNITS} units; "
                                    f"{quota.report()}")
            continue
        if dry_run:
            out["waiting"][slug] = f"DRY RUN: would swap {old} for the new cut"
            continue

        api = api or api_factory()
        live = api.status(old)
        if not live.get("found"):
            out["waiting"][slug] = f"{old} not found on YouTube"
            continue
        if live.get("privacy") == "public":
            out["public"].append(slug)
            st.note(f"{slug}: {old} reads back PUBLIC; never swapped.")
            continue
        payload = api.payload(slug, row.get("question") or slug)
        payload["snippet"]["title"] = live.get("title") or row.get("title") \
            or payload["snippet"]["title"]
        rk, tk = loc
        render = fetch(rk, tmp / f"{slug}-final.mp4")
        thumb = fetch(tk, tmp / f"{slug}.jpg")
        new = api.upload(payload, render)
        quota.spend(quota.UPLOAD, lane)
        st.work(f"{slug}: uploaded the re-rendered cut -> {new} (private, "
                f"undated) to replace {old}")
        try:
            api.thumbnail(new, thumb)
            quota.spend(quota.THUMBNAIL, lane)
        except Exception as e:                             # noqa: BLE001
            st.note(f"thumbnail FAILED on {new}: {e}")
        render.unlink(missing_ok=True)
        rec = {"slug": slug, "old": old, "new": new, "stamp": stamp,
               "phase": "uploaded", "uploaded_at": now()}
        state["swaps"][slug] = rec
        write_json(STATE, state)
        if not _wait_processed(api, new, sleep, wait_s):
            out["waiting"][slug] = f"{new} is not processed yet; resumes next run"
            out["inflight"].append(slug)
            continue
        _finish(st, api, rec, lane, sleep)
        write_json(STATE, state)
        out["swapped"].append(slug)

    stamps = {r["slug"]: _ts(r.get("scheduled_publish_at"))
              for r in candidates(led, sup)}
    late = {s: w for s, w in out["waiting"].items()
            if not w.startswith("DRY RUN") and stamps.get(s)
            and stamps[s] - at < NEXT_RUN_MARGIN}
    for s, w in out["waiting"].items():
        st.note(f"SUPERSEDED SWAP WAITING {s}: {w}")
    if late:
        st.named_stop(
            "SUPERSEDED_SWAP_LATE",
            f"{len(late)} private video(s) still carry a superseded cut and "
            f"publish before this lane runs again: "
            + "; ".join(f"{s} ({w})" for s, w in sorted(late.items())),
            detail={"late": late}, held_items=sorted(late),
            unblock="Re-run loop-upload-cloud once the reason above is "
                    "cleared, or move the old video's publish date in Studio. "
                    "Never delete it.")
    return out
