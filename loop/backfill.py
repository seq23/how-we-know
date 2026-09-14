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


# A slot is never assigned closer than this to now. Not an arbitrary buffer:
# every script's own fingerprint gate ends "Final human watch-through: PENDING
# until the rendered MP4 exists", and a video dated two hours out is one the
# owner cannot watch before the channel publishes it. Weaving a second domain
# into the current week made this reachable for the first time - the materials
# ladder's next free Friday was the same day the episodes were uploaded.
MIN_LEAD_HOURS = 24


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


def domain_weekdays(cfg: dict, per_week: int) -> dict[str, tuple[int, ...]]:
    """Which weekdays each domain publishes on, at `per_week`.

    The ladder is ranked by evidence and a cadence takes the first N rungs;
    this splits those N rungs between the domains using `domains.live_slots`,
    which is already the one place the weekly split is expressed. Rungs are
    handed out IN LADDER ORDER, strongest first, and the domain that already
    holds slots keeps the ones it has.

    At 2/week that is deep sea on (Sun, Tue) and materials on nothing. At
    4/week deep sea keeps EXACTLY (Sun, Tue) and materials takes the two rungs
    the raise added, (Mon, Fri). That property is the whole reason a cadence
    raise can weave a second domain into the existing weeks instead of queuing
    it behind them: the new domain is never assigned a day the old one is
    already publishing on, so no existing slot can be contended for and none
    has to move.
    """
    import domains as _dom                                 # noqa: PLC0415
    ladder = list(PUBLISH_WEEKDAY_LADDER[:max(1, int(per_week))])
    split = _dom.slots_at(cfg, int(per_week))
    # Deterministic order: the domain with the most slots first, ties broken
    # by name, so the same cadence always produces the same assignment.
    out: dict[str, tuple[int, ...]] = {}
    for name in sorted(split, key=lambda d: (-split[d], d)):
        take, ladder = ladder[:split[name]], ladder[split[name]:]
        out[name] = tuple(sorted(take))
    return out


def occupied(led: dict) -> set[str]:
    """Every publish datetime already spoken for, scheduled or aired.

    A slot is taken whether the video went out or is merely dated; reading
    only published_at is what made a second run hand out dates the first had
    already taken.
    """
    out = set()
    for r in led.get("published", []):
        for k in ("scheduled_publish_at", "published_at"):
            v = r.get(k)
            if v:
                out.add(v.replace("Z", "+00:00"))
    return out


def slots(start: datetime, n: int, per_week: int,
          days: tuple[int, ...] | None = None,
          taken: set[str] | None = None) -> list[datetime]:
    """`n` publish datetimes on the cadence's weekdays, at the fixed hour.

    Cadence comes from loop/config.json through `cadence.effective()`; this
    only decides WHICH days those slots land on, via `weekdays_for`.

    Every slot returned is STRICTLY AFTER `start`, and `schedule_for` passes
    the last date already on the calendar as `start`. That is the whole reason
    a cadence change cannot disturb anything already scheduled: the allocator
    can only ever hand out dates past the end of the existing run.
    """
    days = list(days if days is not None else weekdays_for(per_week))
    taken = taken or set()
    # Pin the hour in LOCAL time and convert, rather than pinning UTC. A fixed
    # UTC hour is only correct until the clocks change: 15:00 UTC is 10:00
    # Central during CDT and 09:00 during CST, so from 1 November 2026 every
    # slot would slide an hour earlier and put the Pacific coast at 07:00 -
    # outside the 08:00-11:00 window the schedule exists to hit. The audience
    # lives in local time; the schedule has to as well.
    out = []
    cur = start.astimezone(PUBLISH_TZ).replace(hour=PUBLISH_HOUR_LOCAL,
                                               minute=0, second=0, microsecond=0)
    guard = 0
    while len(out) < n:
        guard += 1
        if guard > 4000:                       # ~11 years of days; never loops
            raise CadenceExceedsLadder(
                f"could not find {n} free slot(s) on weekdays {days} after "
                f"{start.isoformat()} - the calendar is saturated")
        if cur.weekday() in days and cur.astimezone(timezone.utc) > start:
            u = cur.astimezone(timezone.utc)
            # SKIP A SLOT SOMEONE ELSE HOLDS rather than anchoring past the
            # whole calendar. Anchoring past the last date was correct while
            # one domain held every publish day, and became wrong the moment a
            # second domain got its own days: it queued eighteen materials
            # episodes behind a deep-sea run that ends 20 October, so the first
            # materials video would have aired a week after the last deep-sea
            # one instead of alongside it. Skipping occupied slots instead
            # gives deep sea the same dates it already gets - its Sun/Tue are
            # taken through 20 October, so its next free one is after that -
            # while letting materials fill the Mon/Fri that were never used.
            if u.isoformat() not in taken:
                out.append(u)
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
    # EVERY domain's queue. Reading research/publish_order.json by name meant
    # this lane could not see a materials episode at all: eighteen were scored,
    # scripted and planned and three were rendered, and none of them could be
    # assigned a publish slot because the scheduler was looking in one file.
    # loop/batch_queue.py is the one definition, the same one bin/ and
    # cadence.publish_order() use.
    import batch_queue                                     # noqa: PLC0415
    import render_gate                                     # noqa: PLC0415
    done = {r["slug"] for r in ledger.load()["published"]}
    # THE HOLD, not a halt. A render V13/V24 refused is skipped HERE, by name,
    # and everything else stays pending - see loop/render_gate.py for the week
    # eight finished episodes waited behind one that was six seconds short.
    held = render_gate.held_slugs()
    out = []
    for q in batch_queue.queued_entries():
        slug = q["slug"]
        if slug in done:
            continue
        if slug in held:
            if verbose:
                print(f"  HELD {slug}: refused by the render gate; heals or "
                      f"re-renders before it can ship (loop/state/render_hold.json)")
            continue
        found = assets(slug)
        if not isinstance(found, tuple):
            if verbose:
                print(f"  skip {slug}: {found}")
            continue
        render, thumb = found
        out.append((slug, render, thumb))
    return out



def schedule_for(led: dict, n: int, per_week: int,
                 domain: str | None = None) -> list[datetime]:
    """The next `n` publish slots, given everything already on the calendar.

    THE ONLY PLACE A SLOT IS ASSIGNED. The Mac lane and the cloud lane both
    call this; if they each computed a base date, the two would hand out the
    same Sunday to different videos the first time they ran on the same day.

    A row already SCHEDULED occupies its slot just as surely as a published
    one. Reading only published_at made the second run hand out dates the first
    run had already taken.
    """
    taken = occupied(led)
    days = None
    if domain:
        try:
            days = domain_weekdays(config(), per_week).get(domain)
        except Exception:                                  # noqa: BLE001
            days = None
        if not days:
            # A domain with no live slot at this cadence gets none. Falling
            # back to the full ladder would put it on another domain's day.
            raise CadenceExceedsLadder(
                f"{domain!r} holds no publish slot at {per_week}/week, so no "
                f"date can be assigned to it. Raise the cadence or change the "
                f"allocation in loop/domains.py - do not put it on another "
                f"domain's day.")
    base = datetime.now(timezone.utc) + timedelta(hours=MIN_LEAD_HOURS)
    # slots() already returns only slots STRICTLY AFTER `base`, so adding a
    # cadence step first skips one. That is what left Tue 22 Sep 2026 empty
    # between Sun 20 and Sun 27: base was Sun 20, +3.5 days landed on Wed 23,
    # and the next Sunday/Tuesday after that is Sun 27. A silently dropped
    # publish slot on a channel whose whole argument is a predictable cadence.
    return slots(base, n, per_week, days=days, taken=taken)


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
    """The episode's question, from the ranked queue that named it.

    Across every domain's queue: this raised KeyError for any materials slug
    while it read one file, and the question becomes the video's title, so the
    upload would have failed at titling after the render was paid for.
    """
    import batch_queue                                     # noqa: PLC0415
    for q in batch_queue.queued_entries():
        if q["slug"] == slug:
            return q["query"]
    raise KeyError(f"{slug} is in no research/publish_order*.json queue")


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
    import batch_queue                                     # noqa: PLC0415
    queue = batch_queue.queued_slugs()

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

    # PER DOMAIN, because each domain has its own publish days. Allocating
    # from the whole ladder would hand a materials episode a Sunday - deep
    # sea's day - and the two domains would contend for slots the moment both
    # had inventory. schedule_for() already skips occupied dates, so building
    # the assignment domain by domain and recording each date as it is taken
    # keeps the two runs interleaved and collision-free.
    #
    # A domain with no live slot at this cadence is not scheduled at all; it is
    # named and skipped, rather than quietly borrowing another domain's day.
    import domains as _dom                                 # noqa: PLC0415
    by_dom: dict[str, list] = {}
    for row in take:
        d = _dom.domain_of_slug(row[0]) or "deep-sea-ocean-science"
        by_dom.setdefault(d, []).append(row)

    assigned: dict[str, datetime] = {}
    held = occupied(led)
    for d, rows in sorted(by_dom.items()):
        try:
            days = domain_weekdays(cfg, per_week).get(d)
        except Exception:                                  # noqa: BLE001
            days = None
        if not days:
            print(f"  SKIP {len(rows)} {d} episode(s): that domain holds no "
                  f"publish slot at {per_week}/week.")
            continue
        base = datetime.now(timezone.utc) + timedelta(hours=MIN_LEAD_HOURS)
        for row, t in zip(rows, slots(base, len(rows), per_week,
                                      days=days, taken=held)):
            assigned[row[0]] = t
            held.add(t.isoformat())

    take = [row for row in take if row[0] in assigned]
    when = [assigned[row[0]] for row in take]
    if not take:
        print("no episode could be assigned a slot at this cadence.")
        return 0

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
            # question_for() is the one lookup, and it spans every domain's
            # queue. This site had its own inline `order["queue"]` scan - a
            # fourth copy of the same read in one file - which is why it kept
            # working for deep sea and raised for materials.
            question = question_for(slug)
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


def reschedule(slugs: list[str], domain: str, dry_run: bool = False) -> int:
    """Move already-uploaded, not-yet-aired episodes onto their domain's days.

    WHY THIS EXISTS. The three finished materials episodes were uploaded on
    2026-09-04, while the cadence was still 2/week and the allocator still
    anchored every new slot past the END of the calendar. They were therefore
    dated 27 Oct, 1 Nov and 3 Nov - on Sunday and Tuesday, deep sea's own days,
    a week AFTER the last deep-sea episode rather than woven alongside it. The
    owner's instruction was the opposite: two materials days a week, running
    with the deep-sea run, not extending past it.

    Re-dating is not deleting and not re-uploading. The video ID, the file, the
    thumbnail and the description are untouched; only `status.publishAt` moves,
    through `publish.set_privacy`, which is the one place this repo sets a
    schedule. Nothing here can reach a video that has already aired: a row with
    `published_at`, or whose stamp is in the past, is refused outright, because
    a video the audience has already seen is not reschedulable and pretending
    otherwise would silently unpublish it.

    Freeing those Sunday and Tuesday slots also hands them back to deep sea,
    which is why its next free date moves from 8 November to 27 October when
    this runs.
    """
    import publish as _pub                                 # noqa: PLC0415
    from common import config as _config                   # noqa: PLC0415

    cfg = _config()
    per_week = cadence.effective()
    led = ledger.load()
    rows = {r["slug"]: r for r in led["published"]}

    targets = []
    for slug in slugs:
        r = rows.get(slug)
        if r is None:
            raise KeyError(f"{slug} is not in the ledger; it was never uploaded")
        if r.get("published_at"):
            raise ValueError(
                f"{slug} has already aired ({r['published_at']}) - it is not "
                f"reschedulable. Re-dating an aired video would unpublish it.")
        stamp = r.get("scheduled_publish_at")
        if not stamp:
            raise ValueError(f"{slug} carries no scheduled_publish_at")
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when <= datetime.now(timezone.utc):
            raise ValueError(
                f"{slug} was due to air at {stamp}, which has passed; refusing "
                f"to move it.")
        targets.append((slug, r))

    # The slots these rows currently hold are being VACATED, so they must not
    # count as occupied when the new ones are chosen - otherwise an episode
    # could be blocked by its own old date.
    vacating = {r["scheduled_publish_at"].replace("Z", "+00:00")
                for _, r in targets}
    taken = occupied(led) - vacating
    days = domain_weekdays(cfg, per_week).get(domain)
    if not days:
        raise CadenceExceedsLadder(
            f"{domain!r} holds no publish slot at {per_week}/week")
    base = datetime.now(timezone.utc) + timedelta(hours=MIN_LEAD_HOURS)
    when = slots(base, len(targets), per_week, days=days, taken=taken)

    print(f"{len(targets)} episode(s) to re-date onto {domain} days "
          f"{tuple(days)} at {per_week}/week:")
    for (slug, r), t in zip(targets, when):
        old = r["scheduled_publish_at"]
        print(f"  {slug:<36} {old}  ->  "
              f"{t.astimezone(PUBLISH_TZ):%a %d %b %H:%M %Z}")
    if dry_run:
        print("\nDRY RUN - nothing changed.")
        return 0

    creds = up.load_credentials(cfg)
    token = up.access_token(creds)
    moved = 0
    for (slug, r), t in zip(targets, when):
        stamp = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _pub.set_privacy(token, r["video_id"], "private", publish_at=stamp)
        # READ BACK. The API accepting a PUT is not evidence that the date
        # applied - this repo has already been bitten once by trusting a 200
        # over a re-read (the private->public flip that 403'd silently).
        got = _pub.read_status(token, r["video_id"])
        if got.get("privacy") != "private":
            raise AssertionError(
                f"{slug}: after re-dating, YouTube reports privacy "
                f"{got.get('privacy')!r}, not 'private'")
        r["scheduled_publish_at"] = stamp
        moved += 1
        print(f"  moved {slug} -> {stamp}")
    ledger.save(led)
    if moved == 0:
        print("NAMED STOP: nothing was re-dated.")
        return 3
    print(f"\n{moved} episode(s) re-dated; ledger updated.")
    return 0
