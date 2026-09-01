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
import ledger                                     # noqa: E402
import publish as P                               # noqa: E402
import quota                                      # noqa: E402
import upload as up                               # noqa: E402
from common import Stage, config, now, week_id     # noqa: E402

SHORTS_DIR = ROOT / "shorts"
SHORTS_HOUR_LOCAL = 19          # 19:00, the middle of the 18:00-21:00 peak
SHORTS_TZ = ZoneInfo("America/Chicago")
SHORTS_WEEKDAYS = (0, 2, 4, 5)  # Mon, Wed, Fri, Sat - off the episode days
SHORTS_PER_WEEK = 4
UPLOAD_UNITS, THUMB_UNITS, FLIP_UNITS = 1600, 50, 50
DAILY_UNITS = 10000
LEDGER = LOOP / "state" / "shorts_ledger.json"


def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"published": [], "updated": None}


def save_ledger(d: dict) -> None:
    d["updated"] = now()
    LEDGER.write_text(json.dumps(d, indent=2) + "\n")


def slots(start: datetime, n: int) -> list[datetime]:
    """`n` Short slots on the configured evenings, pinned in LOCAL time.

    Local, not UTC, for the same reason the episode slots are: a fixed UTC hour
    is correct only until the clocks change.
    """
    days = sorted(SHORTS_WEEKDAYS)
    out = []
    cur = start.astimezone(SHORTS_TZ).replace(hour=SHORTS_HOUR_LOCAL, minute=0,
                                              second=0, microsecond=0)
    while len(out) < n:
        if cur.weekday() in days and cur.astimezone(timezone.utc) > start:
            out.append(cur.astimezone(timezone.utc))
        cur += timedelta(days=1)
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
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    done = {r["slug"] for r in load_ledger()["published"]}
    out = []
    for q in order["queue"]:
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
    todo = pending()
    if not todo:
        print("nothing to cut: every finished episode already has a Short.")
        return 0

    afford = quota.videos_affordable(limit)
    if afford == 0:
        print(f"no quota left today for a Short. {quota.report()}")
        return 0
    take = todo[:afford]
    cost = len(take) * (UPLOAD_UNITS + THUMB_UNITS + FLIP_UNITS)

    led = load_ledger()
    when = schedule_for(led, len(take))

    print(f"\n{len(todo)} episode(s) without a Short; taking {len(take)} "
          f"({cost} of {DAILY_UNITS} units), {SHORTS_PER_WEEK}/week\n")
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
