"""Upload the finished library ahead of schedule, private and dated.

    .venv/bin/python loop/backfill.py --limit 4 --dry-run
    .venv/bin/python loop/backfill.py --limit 4

The owner's model from day one: *batch-approve far ahead, then leave it alone.*
This uploads finished renders as PRIVATE with a `publishAt` date computed from
the locked cadence, attaches the built thumbnail, and stops. Nothing goes public
at upload time; each video surfaces on its own date and can be vetoed any time
before it does.

WHY A DEDICATED TOOL. The weekly lane (loop/upload.py) uploads whatever Tuesday
rendered - one or two videos against a queue row. This is the opposite shape: a
finished back catalogue going up all at once, against a quota that cannot take
it in one day. Bending the weekly lane into doing that would make the thing that
runs every week harder to reason about, for a job that happens once.

THE QUOTA IS THE REAL CONSTRAINT, and it is why --limit exists:

    videos.insert        1600 units      thumbnails.set    50
    videos.update          50 units      daily allowance 10000

so six uploads is the ceiling in a day and four is the safe number once the
flips and thumbnails are counted. Exceeding it does not queue - it fails, and a
half-uploaded video is worse than an unstarted one. The script therefore counts
what it is about to spend and refuses to start a video it cannot also thumbnail.

ORDER IS THE RANKING. Episodes go up in research/publish_order.json order, which
is combined_score, which is measured demand over competition. There is no
hand-picked head; that was removed on 2026-08-31.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence                                   # noqa: E402
import ledger                                    # noqa: E402
import quota                                     # noqa: E402
import publish as P                              # noqa: E402
import upload as up                              # noqa: E402
from common import Stage, config, now, week_id   # noqa: E402

UPLOAD_UNITS, THUMB_UNITS, FLIP_UNITS = 1600, 50, 50
DAILY_UNITS = 10000
THUMBS = ROOT / "channel" / "thumbnails"
RENDERS = ROOT / "renders"


def set_thumbnail(token: str, video_id: str, img: Path) -> dict:
    url = ("https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
           f"?videoId={video_id}&uploadType=media")
    req = urllib.request.Request(url, data=img.read_bytes(), method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "image/jpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


# --- WHEN TO PUBLISH -------------------------------------------------------
# Not a guess. Three 2026 studies of long-form YouTube agree on the shape:
#
#   Buffer, 1.8M videos    long-form peaks 08:00-11:00 local; Sunday is the
#                          strongest day (10:00 the single best slot), then
#                          Tuesday and Monday; Wednesday and Thursday UNDERperform
#   SocialPilot, 301K      weekdays 12:00-16:00, weekends 09:00-11:00
#   RecurPost, 2M          weekday 12:00-15:00 for early engagement
#
# They disagree about weekday afternoons; they agree that long-form does well in
# the morning and that Sunday is strong. So: Sunday and Tuesday, 10:00 Central.
#
# 15:00 UTC puts the release at 08:00 Pacific / 10:00 Central / 11:00 Eastern -
# inside the 08:00-11:00 window across all three mainland US zones at once,
# which no other hour does.
#
# SHORTS ARE THE OPPOSITE and must not inherit this: Shorts peak 18:00-21:00.
# A Short scheduled from this constant would land in the worst part of its day.
#
# All of this is a benchmark, not a promise. Once YouTube Studio's "when your
# viewers are on YouTube" report has real data behind it - it needs an audience
# this channel does not have yet - the channel's own heatmap replaces these.
PUBLISH_HOUR_LOCAL = 10        # 10:00 America/Chicago, DST or not
PUBLISH_TZ = ZoneInfo("America/Chicago")
PUBLISH_HOUR_UTC = 15          # what that is during CDT; see slots()

# THE DAYS, IN ORDER OF EVIDENCE, AND THE CADENCE TAKES THE FIRST N.
#
# The same benchmark data that fixed the hour also ranks the days: Sunday is
# strongest, then Tuesday, then Monday; Wednesday and Thursday underperform.
# So the ladder is Sunday, Tuesday, Monday, Friday - and a cadence of N uses
# the first N rungs. That has three properties worth stating:
#
#   * At 2/week it is EXACTLY Sunday and Tuesday, the days the fourteen already
#     scheduled episodes use. Raising cadence therefore changes no existing
#     slot, and the run stays gapless across the change.
#   * It never reaches Wednesday or Thursday, the two measured-weak days, at
#     any cadence the ceiling allows.
#   * Friday, not Saturday, is the fourth rung. Saturday would make Sat-Sun-Mon-
#     Tue four consecutive days and then four silent ones; Friday spaces the
#     week 1-1-3-2, and publish.py's whole argument for spacing is that a burst
#     followed by silence is not a cadence.
#
# Like the hour, this is a benchmark and not a promise: once YouTube Studio's
# "when your viewers are on YouTube" report has real data behind it, the
# channel's own heatmap replaces the ladder.
PUBLISH_WEEKDAY_LADDER = (6, 1, 0, 4)   # Sunday, Tuesday, Monday, Friday
PUBLISH_WEEKDAYS = tuple(PUBLISH_WEEKDAY_LADDER[:2])   # cadence 2: Sun and Tue


class CadenceExceedsLadder(Exception):
    """More slots a week were asked for than there are evidenced days."""


def weekdays_for(per_week: int) -> tuple[int, ...]:
    """The weekdays a cadence of `per_week` publishes on.

    Raises rather than wrapping round. Silently reusing a day would put two
    episodes on one morning and call it a cadence increase, and reaching past
    the ladder would put one on a day the evidence says is weak - both are
    failures that look exactly like success from the outside.
    """
    n = max(1, int(per_week))
    if n > len(PUBLISH_WEEKDAY_LADDER):
        raise CadenceExceedsLadder(
            f"cadence is {n}/week but only {len(PUBLISH_WEEKDAY_LADDER)} "
            f"evidenced publish days exist. Add a day to "
            f"PUBLISH_WEEKDAY_LADDER with the evidence for it - do not let the "
            f"allocator double up a morning or wander onto Wednesday.")
    return tuple(sorted(PUBLISH_WEEKDAY_LADDER[:n]))


def slots(start: datetime, n: int, per_week: int) -> list[datetime]:
    """`n` publish datetimes on the cadence's weekdays, at the fixed hour.

    Cadence comes from loop/config.json through `cadence.effective()`; this
    only decides WHICH days those slots land on, via `weekdays_for`.

    Every slot returned is STRICTLY AFTER `start`, and `schedule_for` passes
    the last date already on the calendar as `start`. That is the whole reason
    a cadence change cannot disturb anything already scheduled: the allocator
    can only ever hand out dates past the end of the existing run.
    """
    days = list(weekdays_for(per_week))
    # Pin the hour in LOCAL time and convert, rather than pinning UTC. A fixed
    # UTC hour is only correct until the clocks change: 15:00 UTC is 10:00
    # Central during CDT and 09:00 during CST, so from 1 November 2026 every
    # slot would slide an hour earlier and put the Pacific coast at 07:00 -
    # outside the 08:00-11:00 window the schedule exists to hit. The audience
    # lives in local time; the schedule has to as well.
    out = []
    cur = start.astimezone(PUBLISH_TZ).replace(hour=PUBLISH_HOUR_LOCAL,
                                               minute=0, second=0, microsecond=0)
    while len(out) < n:
        if cur.weekday() in days and cur.astimezone(timezone.utc) > start:
            out.append(cur.astimezone(timezone.utc))
        cur += timedelta(days=1)
    return out[:n]



def local_assets(slug: str):
    """The Mac's answer to "where are this episode's bytes?".

    Returns `(render, thumbnail)` when both are in hand, or a STRING saying
    which one is not — the caller prints the reason, so a skipped episode is
    never a silent skip.

    Factored out so the cloud lane can answer the same question about a
    Cloudflare R2 bucket without re-deriving what "pending" means. There is one
    definition of pending, in `library_pending`, and two ways to locate bytes.
    """
    render, thumb = RENDERS / f"{slug}-final.mp4", THUMBS / f"{slug}.jpg"
    if not render.exists():
        return "no render yet"
    if not thumb.exists():
        return "no thumbnail built"
    return (render, thumb)


def library_pending(verbose: bool = False,
                    assets=None) -> list[tuple[str, Path, Path]]:
    """Every queued episode that is rendered, thumbnailed and not yet uploaded.

    THE ARTEFACTS ON DISK ARE THE TRUTH, not loop/render_queue.json. The weekly
    queue records what THIS WEEK drafted; it says nothing about a back catalogue
    rendered last month. On 2026-09-01 the queue held 2 rows, neither marked
    rendered, while 13 finished renders sat in renders/ - so the upload lane
    would have reported NOTHING_RENDERED with a full library behind it. That is
    the "two components each keeping their own list with no link" failure.

    Order is research/publish_order.json order, which is combined_score.

    `assets` locates an episode's bytes; it defaults to this machine's disk and
    is swapped for an R2 lookup by loop/cloud_upload.py.
    """
    assets = assets or local_assets
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    done = {r["slug"] for r in ledger.load()["published"]}
    out = []
    for q in order["queue"]:
        slug = q["slug"]
        if slug in done:
            continue
        found = assets(slug)
        if not isinstance(found, tuple):
            if verbose:
                print(f"  skip {slug}: {found}")
            continue
        render, thumb = found
        out.append((slug, render, thumb))
    return out



def schedule_for(led: dict, n: int, per_week: int) -> list[datetime]:
    """The next `n` publish slots, given everything already on the calendar.

    THE ONLY PLACE A SLOT IS ASSIGNED. The Mac lane and the cloud lane both
    call this; if they each computed a base date, the two would hand out the
    same Sunday to different videos the first time they ran on the same day.

    A row already SCHEDULED occupies its slot just as surely as a published
    one. Reading only published_at made the second run hand out dates the first
    run had already taken.
    """
    stamps = []
    for r in led["published"]:
        for k in ("scheduled_publish_at", "published_at"):
            if r.get(k):
                stamps.append(r[k].replace("Z", "+00:00"))
    last = max(stamps, default="")
    base = datetime.now(timezone.utc)
    if last:
        try:
            base = max(base, datetime.fromisoformat(last))
        except ValueError:
            pass
    # slots() already returns only slots STRICTLY AFTER `base`, so adding a
    # cadence step first skips one. That is what left Tue 22 Sep 2026 empty
    # between Sun 20 and Sun 27: base was Sun 20, +3.5 days landed on Wed 23,
    # and the next Sunday/Tuesday after that is Sun 27. A silently dropped
    # publish slot on a channel whose whole argument is a predictable cadence.
    return slots(base, n, per_week)


def upload_one(st, token: str, slug: str, question: str, render: Path,
               thumb: Path, when: datetime, lane: str = "backfill") -> str:
    """Upload one finished episode, schedule it, thumbnail it, record it.

    THE ONLY PLACE A LIBRARY VIDEO IS UPLOADED. The cloud lane calls this with
    files it pulled from R2 rather than files it rendered, and nothing else
    differs — so the schedule, the privacy contract, the thumbnail, the ledger
    row and the quota accounting cannot drift between the two machines.

    `lane` only names who spent the quota, so loop/state/quota.json says which
    machine did the work during the transition.
    """
    item = {"slug": slug, "script": f"scripts/{slug}.md", "question": question}
    payload = up.build_payload(item)
    vid = up.resumable_upload(token, payload, render)
    st.work(f"uploaded {slug} -> {vid} (private)")

    stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    P.set_privacy(token, vid, "private", publish_at=stamp)

    try:
        set_thumbnail(token, vid, thumb)
        st.work(f"thumbnail set on {vid}")
    except urllib.error.HTTPError as e:
        # Never fail an upload over its thumbnail: the video is up and dated,
        # and a missing card is fixable in one later call.
        st.note(f"thumbnail FAILED on {vid}: HTTP {e.code} - fix with "
                f"loop/backfill.py --thumbs-only")

    time.sleep(2)
    got = P.read_status(token, vid)
    if got.get("privacy") != "private":
        st.named_stop("SCHEDULE_NOT_APPLIED",
                      f"{vid} should be private-with-publishAt but "
                      f"reports {got.get('privacy')!r}",
                      unblock="Check the video in YouTube Studio.")

    led = ledger.load()
    led["published"].append({
        "slug": slug, "question": question, "video_id": vid,
        "uploaded_at": now(), "privacy": "private",
        "scheduled_publish_at": stamp,
        "note": f"{lane}: scheduled, not yet public"})
    led["updated"] = now()
    (LOOP / "state" / "ledger.json").write_text(json.dumps(led, indent=2) + "\n")
    quota.spend(UPLOAD_UNITS + THUMB_UNITS + FLIP_UNITS, lane)
    st.work(f"{slug} scheduled for {stamp}")
    return vid


def question_for(slug: str) -> str:
    """The episode's question, from the ranked queue that named it."""
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    for q in order["queue"]:
        if q["slug"] == slug:
            return q["query"]
    raise KeyError(f"{slug} is not in research/publish_order.json")


def run(limit: int = 4, dry_run: bool = False, stage=None) -> int:
    """Upload up to `limit` finished episodes, scheduled and thumbnailed.

    `stage` lets a caller that already owns a Stage (the weekly upload
    lane) record the work in ITS stage rather than opening a second one.
    One code path owns library uploads, so there is exactly one place
    that assigns a slot and exactly one that writes the ledger.
    """
    class _A: pass
    a = _A(); a.limit = limit; a.dry_run = dry_run

    cfg = config()
    # THROUGH cadence.effective(), never the raw config number. This lane
    # assigns publish slots, so reading the floor directly would have kept
    # uploading on the 2/week ladder while every other stage had scaled -
    # two components each keeping their own list, with no link.
    per_week = cadence.effective()
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    queue = [q["slug"] for q in order["queue"]]

    led = ledger.load()
    done = {r["slug"] for r in led["published"]}

    pending = library_pending(verbose=True)

    if not pending:
        print("nothing to upload: every queued episode is already published "
              "or not yet rendered.")
        return 0

    # Ask the shared account, do not assume the day is ours. Three other
    # scheduled lanes spend from the same allowance and none of them can see
    # each other; the worst-case Thursday came to 10,200 of 10,000 before this
    # existed, and the failure mode was a half-uploaded video.
    # A dry run makes no API calls, so it must not be gated on quota - being
    # unable to PREVIEW tomorrow's schedule because today's uploads are done is
    # a guard blocking the wrong thing.
    # Leave the evening's Shorts their slot. At 4 episodes a week this lane
    # can want 6,800 units in one morning, which is the whole usable day once
    # two Shorts and one video's reach lanes are counted.
    afford = (a.limit if a.dry_run else
              quota.videos_affordable(a.limit, reserve=quota.shorts_reserve()))
    if afford == 0:
        print(f"no quota left today for a full video. {quota.report()}")
        return 0
    if afford < a.limit:
        print(f"quota allows {afford} of {a.limit} today. {quota.report()}")
    take = pending[:afford]
    cost = len(take) * (UPLOAD_UNITS + THUMB_UNITS + FLIP_UNITS)

    # Schedule starts one full cadence slot after the most recent publish, so a
    # backfill never lands on top of something already out. One implementation,
    # shared with the cloud lane.
    when = schedule_for(led, len(take), per_week)

    print(f"\n{len(pending)} episode(s) pending; taking {len(take)} this run "
          f"({cost} of {DAILY_UNITS} units), cadence {per_week}/week\n")
    for (slug, _, _), t in zip(take, when):
        print(f"  {t:%a %d %b %H:%M UTC}  {slug}")
    if a.dry_run:
        print("\nDRY RUN - nothing uploaded.")
        return 0

    import contextlib
    ctx = (contextlib.nullcontext(stage) if stage is not None
           else Stage("backfill", week_id(),
                      zero_work_hint="No rendered, thumbnailed, unpublished "
                                     "episode was found."))
    with ctx as st:
        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            # Was a crash: `access_token(None)` raised AttributeError, so an
            # un-credentialled machine failed with a traceback where a named,
            # actionable stop belongs. Rule 0 wants the stop.
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code, f"{len(take)} finished episode(s) are ready but "
                          + msg, detail={"ready": [s for s, _, _ in take]},
                          unblock=unblock)
        token = up.access_token(creds)
        for (slug, render, thumb), t in zip(take, when):
            question = next(q["query"] for q in order["queue"]
                            if q["slug"] == slug)
            upload_one(st, token, slug, question, render, thumb, t,
                       lane="backfill")
    return 0




def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=4,
                    help="max videos this run (quota: 4 is safe, 6 is the wall)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
