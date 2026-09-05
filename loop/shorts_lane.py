"""Cut and publish Shorts from the finished episodes.

    .venv/bin/python loop/shorts_lane.py --limit 2 --dry-run
    .venv/bin/python loop/shorts_lane.py --limit 2

WHY SHORTS EXIST ON THIS CHANNEL, precisely. The Partner Programme needs 1,000
subscribers AND 4,000 watch hours, and **Shorts watch time does not count toward
the hours** - only long-form does. Shorts get roughly 10x the views and
contribute nothing to that half. So they are not a faster route to monetisation;
they are the discovery engine that feeds one, and the signal YouTube weights most
heavily is a viewer moving from a Short into a long-form video on the same
channel. Every Short here is a chapter lifted out of an episode that continues
the thought, which is exactly that shape.

THE SCHEDULE IS DELIBERATELY NOT THE EPISODE SCHEDULE. Long-form peaks 08:00-11:00
local; Shorts peak 18:00-21:00 - very nearly the inverse. A Short posted on the
episode slot lands in the worst part of its own day, so this lane owns its own
hour and its own days. See docs/OPERATING-MANUAL.md section 2.

WHAT IS AUTOMATED AND WHAT IS NOT. visuals/shorts.py ranks each episode's
chapters against that episode's own direct-answer lock. Rank 1 was correct on
every episode checked and is cut unattended. Ranks 2+ are NOT trustworthy enough
to publish blind - one of them is a hedge chapter, another is an editorial note -
so this lane takes rank 1 only. Deeper cuts stay a human's call via
`bin/make-shorts.sh --dry-run --count 3`.

THE SOURCE IS THE FINISHED EPISODE, AND ONLY THAT. The 16:9 masters carry
burned-in captions, and a Short burns its own sized for a 1080x1920 canvas.
visuals/shorts.py crops the master's caption band off the source frame before
scaling it, and redraws the source credit that crop removes from
channel/imagery/rights.json and channel/imagery/video_rights.json. So there is no
second, unburned master to render or keep in step: this lane no longer renders
anything. It selects, cuts, uploads and schedules.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import backfill as B                              # noqa: E402
import batch_queue                                # noqa: E402
import cadence                                    # noqa: E402
import ledger                                     # noqa: E402
import publish as P                               # noqa: E402
import quota                                      # noqa: E402
import shorts_approval                            # noqa: E402
import upload as up                               # noqa: E402
from common import Stage, config, now, week_id     # noqa: E402

SHORTS_DIR = ROOT / "shorts"
SHORTS_HOUR_LOCAL = 19          # 19:00, the middle of the 18:00-21:00 peak
SHORTS_TZ = ZoneInfo("America/Chicago")

# THE EVENING LADDER, IN ORDER OF USE, AND THE CADENCE TAKES THE FIRST N.
#
# Each rung is (weekday, local hour), Monday=0. Every hour on it is inside the
# 18:00-21:00 evening peak, and none of them is the 10:00 episode slot - a
# Short posted on the long-form schedule lands in the worst part of its own day,
# which is the reason this lane owns its own scheduler at all.
#
#   rungs 1-4  Mon, Wed, Fri, Sat at 19:00   - exactly the 4/week schedule that
#                                              was already running, unchanged
#   rungs 5-7  Sun, Tue, Thu at 19:00        - fills the week out to daily
#   rungs 8-9  Sat, Sun at 21:00             - the second slot goes on the two
#                                              weekend evenings, where short-form
#                                              consumption is highest and a
#                                              21:00 post is still inside the
#                                              stated peak
#
# 9/week is the middle of the owner's 8-10 band. Raising the number in
# loop/config.json moves it; going past rung 9 is a NAMED refusal, not a
# wrap-around, because doubling up an evening is not a cadence increase.
SHORTS_SLOT_LADDER = ((0, 19), (2, 19), (4, 19), (5, 19),
                      (6, 19), (1, 19), (3, 19),
                      (5, 21), (6, 21))
SHORTS_WEEKDAYS = tuple(sorted({wd for wd, _ in SHORTS_SLOT_LADDER[:4]}))
UPLOAD_UNITS, THUMB_UNITS, FLIP_UNITS = 1600, 50, 50
DAILY_UNITS = 10000
LEDGER = LOOP / "state" / "shorts_ledger.json"


class ShortsCadenceExceedsLadder(Exception):
    """More evening slots a week were asked for than the ladder defines."""


def slot_ladder(per_week: int) -> tuple[tuple[int, int], ...]:
    """The (weekday, hour) rungs a Shorts cadence of `per_week` uses."""
    n = max(1, int(per_week))
    if n > len(SHORTS_SLOT_LADDER):
        raise ShortsCadenceExceedsLadder(
            f"{n} Shorts a week were asked for but the evening ladder defines "
            f"{len(SHORTS_SLOT_LADDER)} rungs. Add a rung with the evidence "
            f"for it - do not stack two Shorts on one evening slot.")
    return SHORTS_SLOT_LADDER[:n]


def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"published": [], "updated": None}


def save_ledger(d: dict) -> None:
    d["updated"] = now()
    LEDGER.write_text(json.dumps(d, indent=2) + "\n")


def slots(start: datetime, n: int, per_week: int | None = None) -> list[datetime]:
    """`n` Short slots on the cadence's evenings, pinned in LOCAL time.

    Local, not UTC, for the same reason the episode slots are: a fixed UTC hour
    is correct only until the clocks change.

    Every slot is STRICTLY AFTER `start`, and `schedule_for` passes the last
    Short already on the calendar - so raising the Shorts cadence hands out new
    evenings past the end of the existing run and never re-dates one.
    """
    if per_week is None:
        per_week = cadence.shorts_effective()
    rungs = slot_ladder(per_week)
    by_day: dict[int, list[int]] = {}
    for wd, hour in rungs:
        by_day.setdefault(wd, []).append(hour)
    for hours in by_day.values():
        hours.sort()

    out: list[datetime] = []
    day = start.astimezone(SHORTS_TZ).replace(hour=0, minute=0, second=0,
                                              microsecond=0)
    guard = 0
    while len(out) < n:
        guard += 1
        if guard > 400:                     # ~57 weeks; never spin forever
            raise ShortsCadenceExceedsLadder(
                f"could not place {n} Short slot(s) from a {len(rungs)}-rung "
                f"ladder - the ladder is empty or unreachable")
        for hour in by_day.get(day.weekday(), ()):
            when = day.replace(hour=hour)
            if when.astimezone(timezone.utc) > start:
                out.append(when.astimezone(timezone.utc))
                if len(out) == n:
                    break
        day += timedelta(days=1)
    return out


def schedule_for(led: dict, n: int) -> list[datetime]:
    """The next `n` EVENING slots, given every Short already on the calendar.

    THE ONLY PLACE A SHORT'S SLOT IS ASSIGNED. The Mac lane and the cloud lane
    both call this. It is deliberately not `backfill.schedule_for`: that one
    hands out 10:00 Central on Sunday and Tuesday, and a Short posted there
    lands in the worst part of its own day.
    """
    stamps = [r["scheduled_publish_at"].replace("Z", "+00:00")
              for r in led["published"] if r.get("scheduled_publish_at")]
    anchor = max([datetime.now(timezone.utc)] +
                 [datetime.fromisoformat(s) for s in stamps])
    return slots(anchor, n)


def upload_short(st, token: str, slug: str, question: str, path: Path,
                 when: datetime, lane: str = "shorts") -> str:
    """Upload one cut Short, schedule it, record it, spend the quota.

    THE ONLY PLACE A SHORT IS UPLOADED. loop/shorts_cloud.py calls this with a
    file it pulled from R2 rather than one it cut, and nothing else differs —
    so the evening slot, the privacy contract, the ledger row and the quota
    accounting cannot drift between the two machines.
    """
    payload = build_payload(slug, question)
    vid = up.resumable_upload(token, payload, path)
    stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    P.set_privacy(token, vid, "private", publish_at=stamp)
    time.sleep(2)
    got = P.read_status(token, vid)
    if got.get("privacy") != "private":
        st.named_stop("SHORT_SCHEDULE_NOT_APPLIED",
                      f"{vid} should be private-with-publishAt but "
                      f"reports {got.get('privacy')!r}",
                      unblock="Check the Short in YouTube Studio.")
    led = load_ledger()
    led["published"].append({
        "slug": slug, "video_id": vid, "file": path.name,
        "uploaded_at": now(), "privacy": "private",
        "scheduled_publish_at": stamp, "rank": 1, "lane": lane})
    save_ledger(led)
    quota.spend(UPLOAD_UNITS + THUMB_UNITS + FLIP_UNITS, lane)
    st.work(f"{slug} Short scheduled for {stamp}")
    return vid


def local_short(slug: str):
    """This Mac's answer to "is there a cut Short for this episode?"."""
    if not (ROOT / "renders" / f"{slug}-final.mp4").exists():
        return "no finished render to cut from"
    return True


def pending(have=None) -> list[str]:
    """Finished episodes that have no Short published yet.

    Publish order, so the Shorts follow the same ranking the episodes do.
    `have` locates the material; it defaults to this machine's disk and is
    swapped for an R2 lookup by loop/shorts_cloud.py.
    """
    have = have or local_short
    # EVERY DOMAIN'S QUEUE, NOT JUST DEEP SEA'S. This read
    # `research/publish_order.json` by name, so materials-and-manufacturing was
    # invisible to the Shorts lane from the day it went live: on 2026-09-05 the
    # library held 51 Shorts, every one of them deep sea, while eleven rendered
    # materials episodes had no Short cut at all. loop/batch_queue.py is the one
    # definition of the publish queue across domains, and V27 exists to stop
    # exactly this -- it simply had not been pointed at this module.
    done = {r["slug"] for r in load_ledger()["published"]}
    out = []
    for q in batch_queue.queued_entries():
        slug = q["slug"]
        if slug in done:
            continue
        found = have(slug)
        if found is not True:
            continue
        out.append(slug)
    return out



def cut(slug: str) -> Path | None:
    """Cut rank 1 for this episode. Returns the file, or None if it refused."""
    r = subprocess.run([str(ROOT / "bin" / "make-shorts.sh"), slug],
                       capture_output=True, text=True, cwd=ROOT)
    made = sorted(SHORTS_DIR.glob(f"{slug}-short*.mp4"))
    if r.returncode != 0 or not made:
        print(f"  {slug}: shorts.py refused (rc={r.returncode})")
        tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
        for line in tail:
            print(f"    {line}")
        return None
    return made[0]


def build_payload(slug: str, question: str) -> dict:
    """Metadata for a Short. Deliberately NOT the episode's description.

    A Short carries a pointer back to the episode, because a viewer moving from
    a Short into long-form is the whole reason this lane exists. It does not
    repeat the full source list: the episode holds that, and a Short's
    description is read in a scroll.
    """
    title = question.strip().rstrip("?")
    title = (title[:1].upper() + title[1:] if title else title) + "?"
    desc = ("Evidence-first answers from the deep sea. This is one chapter — "
            "the full episode shows the instrument, the proxy and the "
            "observation behind every figure.\n\n"
            "Full episodes: https://youtube.com/@howweknowdeep\n"
            "howweknowdeep.com\n\n#Shorts")
    return {"snippet": {"title": title[:100], "description": desc,
                        "tags": ["deep sea", "ocean science", "how we know",
                                 "shorts", "marine biology"],
                        "categoryId": "27"},
            "status": {"privacyStatus": "private",
                       "selfDeclaredMadeForKids": False,
                       "embeddable": True, "license": "youtube"}}


def run(limit: int = 2, dry_run: bool = False) -> int:
    cfg = config()
    # KEPT FROM UPSTREAM, and not optional: `per_week` and `cadence_why` are
    # both read further down (the SHORTS_INVENTORY_EXHAUSTED stop quotes the
    # cadence, and the take line prints the explanation). The stashed side
    # replaced this line entirely, which would have raised NameError on the
    # first run that reached either.
    per_week, cadence_why = cadence.shorts_effective(explain=True)

    # ALL THREE RANKS PUBLISH AUTOMATICALLY. Owner's call, 2026-09-01: she does
    # not want to approve Shorts one at a time.
    #
    # Rank measures RELEVANCE TO THE EPISODE'S CORE QUESTION, not how good a
    # Short it makes, and those are different things. Episode 01's rank 3 is
    # "Scarce food favors oversized feeding equipment" - a large mouth, long
    # teeth, hinged jaws, the anglerfish's lure - which is plainly stronger
    # short-form material than its rank 2 on soft bodies under pressure. Cutting
    # rank 3 off would have thrown that away for a reason that does not survive
    # looking at the output.
    #
    # The genuinely unpublishable category is filtered at SOURCE regardless of
    # rank: visuals/shorts.py drops chapters whose heading is production
    # apparatus and whose narration talks about the video rather than the
    # subject. That is the guard that matters; rank is not.
    #
    # Supply: 16 episodes x 3 ranks = 48 Shorts = 12 weeks at 4/week, against a
    # 7.5-week episode runway. Comfortably ahead, and Shorts consume no episode
    # inventory.
    #
    # loop/shorts_approval.py is still honoured as a VETO: anything explicitly
    # rejected there is skipped. Nothing has to be approved for it to publish.
    MAX_RANK = 3

    def _rank(path):
        stem = path.stem
        return 1 if stem.endswith("-short") else int(stem.rsplit("-short", 1)[1])

    todo = []
    for t in pending():
        for f in sorted(SHORTS_DIR.glob(f"{t}-short*.mp4")):
            try:
                r = _rank(f)
            except ValueError:
                continue
            if r <= MAX_RANK and not shorts_approval.is_rejected(f.name):
                todo.append(t)
                break

    # The stashed side also carried its own `if not todo:` here, printing a
    # sentence and returning 0. It is DROPPED rather than merged, for three
    # reasons: the Rule 0 named stop immediately below already handles the
    # same condition and handles it better (a print that exits 0 is the exact
    # "runs but inert" shape that stop was written to replace); it was written
    # before the cadence raise and quoted no cadence; and its message said
    # "rank 3 is kept on disk and never published", contradicting the comment
    # directly above it in the same hunk. Keeping it would have restored a
    # claim the owner reversed on 2026-09-01.
    if not todo:
        # RULE 0. This used to print a sentence and exit 0, which is exactly the
        # "runs but inert" shape: a channel that has published its last cut
        # Short would look green here forever. At 4/week the 51 cut Shorts were
        # twelve weeks away from that; at 9/week they are under six, so the
        # difference between a print and a stop is now weeks, not months.
        #
        # It is a STOP, not a transition. What to do when the cut inventory runs
        # out - native vertical or more chapters off the existing masters - is
        # the owner's decision to make deliberately, and this stop is what puts
        # it in front of her rather than a mechanism that fires on its own.
        with Stage("shorts", week_id()) as st:
            st.named_stop(
                "SHORTS_INVENTORY_EXHAUSTED",
                "no cut Short is waiting to publish: every finished episode "
                f"already has one on the calendar, at {per_week}/week.",
                unblock="Nothing is broken and nothing has stopped - the "
                        "Shorts already scheduled keep airing. This is the "
                        "decision point: either cut more chapters from the "
                        "existing masters (bin/make-shorts.sh --count 3), or "
                        "decide whether Shorts move to a native vertical "
                        "format. That is deliberately NOT automatic.")
        return 0

    # The day's long-form upload comes first. `videos_affordable` used to be
    # called with no reserve here, so a Shorts run early in the day could take
    # the allowance the episode upload needed and the episode - the one lane
    # that cannot be deferred - would fail partway through. See loop/quota.py.
    afford = quota.videos_affordable(limit, reserve=quota.upload_reserve())
    if afford == 0:
        print(f"no quota left today for a Short after reserving "
              f"{quota.upload_reserve()} units for the day's episode upload. "
              f"{quota.report()}")
        return 0
    take = todo[:afford]
    cost = len(take) * (UPLOAD_UNITS + THUMB_UNITS + FLIP_UNITS)

    led = load_ledger()
    when = schedule_for(led, len(take))

    print(f"\n{len(todo)} episode(s) without a Short; taking {len(take)} "
          f"({cost} of {DAILY_UNITS} units). {cadence_why}\n")
    for slug, t in zip(take, when):
        print(f"  {t.astimezone(SHORTS_TZ):%a %d %b %H:%M %Z}  {slug}")
    if dry_run:
        print("\nDRY RUN - nothing cut or uploaded.")
        return 0

    with Stage("shorts", week_id(),
               zero_work_hint="No finished episode (renders/<slug>-final.mp4) "
                              "yielded a Short: shorts.py refused every "
                              "candidate.") as st:
        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            # Was `access_token(None)` -> AttributeError: a traceback where a
            # named, actionable stop belongs.
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code, f"{len(take)} Short(s) are ready but " + msg,
                          detail={"ready": take}, unblock=unblock)
        token = up.access_token(creds)
        for slug, t in zip(take, when):
            path = cut(slug)
            if path is None:
                st.note(f"{slug}: no Short produced; left for the next run")
                continue
            st.work(f"cut {path.name}")
            upload_short(st, token, slug, B.question_for(slug), path, t)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
