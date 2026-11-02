"""Take scheduled long-form episodes with no pictures OFF the schedule, to be re-made.

    .venv/bin/python loop/owner_hold.py unschedule            # dry run: list them
    .venv/bin/python loop/owner_hold.py unschedule --apply    # do it

WHY (owner, 2026-11-02): "I'm really concerned we fix this group: including 13
already scheduled through 30 Nov. We need to take all these off the schedule and
re do them and [don't] let any more go out until all hostile review items
fixed." The hostile review found 41 of 54 renders since mid-October carry no
moving footage (renders/<slug>-final.mp4.footage.json all null, or no record at
all because the render predates footage placement, #284).

What it does, per scheduled, not-yet-public long-form ledger row whose render
has no footage:
  1. NEVER touches a public video: it reads the status back first and skips one
     that is public (named, left alone).
  2. Clears the publishAt and keeps the video private (publish.cancel_schedule,
     verified by reading it back). Nothing is deleted: there is no delete path.
  3. Moves the ledger row from `published` to `withdrawn` (row kept, with
     `schedule_was`), so the slug is pending again: loop/batch_queue.py queues
     it, the Mac re-renders it, the upload lanes upload the NEW cut and the
     calendar dates it once the long-form hold lifts.
  4. Records the old cut in loop/state/superseded_renders.json, so the old
     bytes on the R2 shelf can never be uploaded in its place.

Quota: about 160 units a video (reads plus the unlisted->private round trip);
it stops before a video it cannot afford and the rest wait for tomorrow.
Pinned by loop/tests/test_owner_hold_longform.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import ledger                                     # noqa: E402
from common import Stage, now, read_json, week_id, write_json  # noqa: E402

SUPERSEDED = LOOP / "state" / "superseded_renders.json"
# The renders live on the Mac checkout; a worktree points here with HWK_RENDERS.
RENDERS = Path(os.environ.get("HWK_RENDERS") or ROOT / "renders")
REASON = "owner hold 2 Nov 2026: re-render with pictures (hostile review)"
UNITS_PER_VIDEO = 160
LANE = "owner-hold"


def _ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def footage_beats(slug: str, renders: Path | None = None) -> int | None:
    """Beats of the render that carry moving footage; None if no record."""
    rec = (renders or RENDERS) / f"{slug}-final.mp4.footage.json"
    if not rec.exists():
        return None
    beats = (json.loads(rec.read_text()).get("beats") or {})
    vals = beats.values() if isinstance(beats, dict) else beats
    return sum(1 for v in vals if v)


def candidates(led: dict, at: datetime, footage=footage_beats) -> list[dict]:
    """Scheduled, not-yet-aired, not-retired long-form rows with no footage."""
    out = []
    for r in led.get("published", []):
        when = _ts(r.get("scheduled_publish_at"))
        if not r.get("video_id") or r.get("retired_at") or when is None or when <= at:
            continue
        if r.get("privacy") == "public":
            continue
        if not footage(r["slug"]):            # None (no record) or 0 beats
            out.append(r)
    return out


def withdraw(led: dict, video_id: str, schedule_was: str | None) -> dict:
    """Mark the row for THIS video withdrawn, in place. Pure; returns the row.

    By video_id, never by slug: a slug can carry an older retired duplicate
    (how-deep-can-a-sperm-whale-go has hh5mMno-Iis before F684ebB13gg), and
    matching the first slug row marked the wrong video on 2026-11-02.

    The row stays in `published`, retired (as loop/retire.py leaves one), so
    every lane that looks a video id up still finds it and none spends quota
    on it; `withdrawn_at` is what marks it for re-making.
    """
    row = next(r for r in led["published"] if r.get("video_id") == video_id)
    row.pop("scheduled_publish_at", None)
    row.update({"privacy": "private", "schedule_was": schedule_was,
                "retired_at": now(), "retired_reason": REASON,
                "withdrawn_at": now(), "withdrawn_reason": REASON})
    return row


def record_superseded(slug: str, renders: Path | None = None) -> dict | None:
    f = (renders or RENDERS) / f"{slug}-final.mp4"
    if not f.exists():
        return None
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    sup = read_json(SUPERSEDED, default={})
    rec = {"sha256": h.hexdigest(), "bytes": f.stat().st_size,
           "superseded_at": now()[:10], "why": REASON}
    old = sup.get(slug)
    if old and old.get("sha256") != rec["sha256"]:
        # KEEP the earlier refused cut (V49 checks it): both stay refused.
        if all(a.get("sha256") != rec["sha256"] for a in old.get("also", [])):
            old.setdefault("also", []).append(rec)
    else:
        sup[slug] = rec
    write_json(SUPERSEDED, sup)
    return sup[slug]


def unschedule(apply: bool, only: list[str]) -> int:
    import publish as P                          # noqa: PLC0415
    import quota                                 # noqa: PLC0415
    import upload as up                          # noqa: PLC0415
    from common import config                    # noqa: PLC0415

    with Stage(LANE, week_id(),
               zero_work_hint="No scheduled long-form episode lacks footage; "
                              "nothing needed taking off the schedule.") as st:
        led = ledger.load()
        rows = candidates(led, datetime.now(timezone.utc))
        if only:
            rows = [r for r in rows if r["slug"] in only]
        for r in rows:
            print(f"  {r['scheduled_publish_at'][:10]}  {r['slug']}  {r['video_id']}")
        if not apply:
            st.work(f"DRY RUN: {len(rows)} episode(s) would come off the schedule")
            return 0
        creds = up.load_credentials(config())
        if creds is None:
            st.named_stop("OAUTH_MISSING", "cannot unschedule without OAuth.",
                          unblock="Run auth/youtube_auth.py.")
        token = up.access_token(creds)
        done = []
        for r in rows:
            if quota.remaining() < UNITS_PER_VIDEO:
                st.work(f"quota: stopped before {r['slug']}; the rest run tomorrow")
                break
            vid = r["video_id"]
            before = P.read_status_full(token, vid)
            if before.get("privacy") == "public":
                st.work(f"{r['slug']} ({vid}) is PUBLIC - left alone")
                quota.spend(1, LANE)
                continue
            stamp = P.cancel_schedule(token, vid) or r.get("scheduled_publish_at")
            after = P.read_status_full(token, vid)
            quota.spend(UNITS_PER_VIDEO, LANE)
            if after.get("privacy") != "private" or after.get("publishAt"):
                st.named_stop("OWNER_HOLD_NOT_APPLIED",
                              f"{vid} reads {after} after unscheduling",
                              detail={"before": before, "after": after})
            led = ledger.load()
            withdraw(led, r["video_id"], stamp)
            ledger.save(led)
            record_superseded(r["slug"])
            done.append((r["slug"], stamp))
            st.work(f"{r['slug']} ({vid}): off the schedule (was {stamp}); "
                    f"private, kept; queued to re-render")
        print(json.dumps(done, indent=1))
        # A SECOND, DELAYED READ of every withdrawn video. 2026-11-02:
        # X2_UfcYnXwc read private/no-date straight after its round trip and
        # read its old publishAt again minutes later, so one read is not
        # proof. Re-do the round trip once for any that kept a date.
        import time as _t                        # noqa: PLC0415
        verify_withdrawn(token, P, quota, sleep=_t.sleep, st=st)
    return 0


def verify_cmd() -> int:
    import publish as P                          # noqa: PLC0415
    import quota                                 # noqa: PLC0415
    import time as _t                            # noqa: PLC0415
    import upload as up                          # noqa: PLC0415
    from common import config                    # noqa: PLC0415
    with Stage(LANE, week_id(), zero_work_hint="no withdrawn videos to verify") as st:
        token = up.access_token(up.load_credentials(config()))
        verify_withdrawn(token, P, quota, sleep=_t.sleep, st=st, settle_s=0)
    return 0


def verify_withdrawn(token, P, quota, sleep, st, settle_s: int = 60) -> list[str]:
    """Re-read every withdrawn video after `settle_s`; redo any still dated."""
    sleep(settle_s)
    bad = []
    for r in [r for r in ledger.load()["published"] if r.get("withdrawn_at")]:
        got = P.read_status_full(token, r["video_id"])
        quota.spend(1, LANE)
        if got.get("publishAt") or got.get("privacy") != "private":
            P.set_privacy(token, r["video_id"], "unlisted")
            P.set_privacy(token, r["video_id"], "private")
            quota.spend(100, LANE)
            sleep(settle_s)
            got = P.read_status_full(token, r["video_id"])
            if got.get("publishAt") or got.get("privacy") != "private":
                bad.append(r["slug"])
    if bad:
        st.named_stop("OWNER_HOLD_NOT_APPLIED",
                      f"still dated or not private after a second round trip: {bad}",
                      detail={"slugs": bad})
    st.work(f"re-read {sum(1 for r in ledger.load()['published'] if r.get('withdrawn_at'))} withdrawn video(s) "
            f"after {settle_s}s: all private, no date")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unschedule")
    u.add_argument("--apply", action="store_true")
    u.add_argument("--slug", action="append", default=[])
    sub.add_parser("verify")
    a = ap.parse_args()
    if a.cmd == "verify":
        return verify_cmd()
    return unschedule(a.apply, a.slug)


if __name__ == "__main__":
    raise SystemExit(main())
