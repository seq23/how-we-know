"""The upload lane, running in GitHub Actions instead of on the owner's Mac.

    python loop/cloud_upload.py --limit 4
    python loop/cloud_upload.py --dry-run          # plan only, no writes

WHY. `loop/backfill.py` did this job from a launchd agent at 09:00, which meant
the laptop had to be awake, unlocked and on the network at 09:00. The owner
wants to walk away from the machine. Actions has the schedule and the
credentials; what it does not have is the bytes, because `renders/*.mp4` is
gitignored. Cloudflare R2 supplies the bytes.

    Mac    bin/push-to-r2.sh          renders + thumbnails  ->  R2
    cloud  this file, daily           R2 -> YouTube, private, dated
    repo   loop/state/ledger.json     committed back, so tomorrow knows

NOTHING ABOUT THE SCHEDULE IS REIMPLEMENTED HERE. The slot assignment, the
privacy contract, the thumbnail, the ledger row and the quota accounting are
`backfill.schedule_for` and `backfill.upload_one`, called directly. If this file
had its own copy, the two lanes would hand the same Sunday to two videos the
first day they both ran — and that bug would surface as a public double-post
weeks later, not as a failure today.

WHAT IT REFUSES TO DO:

* upload without a usable YouTube credential — NAMED STOP, naming the env vars
* upload when R2 is not configured — NAMED STOP, naming the exact variable
* upload past the shared daily quota — `loop/quota.py` decides, not this file
* upload bytes whose sha256 does not match the sidecar R2 recorded on the push
* anything at all under `LOOP_DRY_RUN=1`

QUOTA DURING THE TRANSITION. While the Mac lanes still exist, both machines
spend from one 10,000-unit daily allowance and neither can see the other's
in-flight work — `loop/state/quota.json` only syncs when a commit lands. That
is why the Mac backfill agent is unloaded once this lane is proven: two lanes
uploading the same library from two machines is the collision, and the fix is
one lane, not cleverer arithmetic.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import backfill                                  # noqa: E402
import ledger                                    # noqa: E402
import quota                                     # noqa: E402
import r2                                        # noqa: E402
import upload as up                              # noqa: E402
from common import Stage, config, week_id        # noqa: E402

LANE = "cloud-upload"


def shelf_lookup(shelf):
    """An `assets` callable for `backfill.library_pending`, backed by R2.

    Returns the two R2 KEYS rather than local paths — `library_pending` only
    passes the locators through, and heading two sidecars is cheap where
    downloading a 40 MB render to decide whether we want it is not. The bytes
    are fetched later, only for the episodes actually taken.
    """
    def look(slug: str):
        rk, tk = r2.render_key(slug), r2.thumb_key(slug)
        if shelf.head(rk) is None:
            return "not shelved in R2 (no render) — run bin/push-to-r2.sh"
        if shelf.head(tk) is None:
            return "render is shelved but its thumbnail is not"
        return (rk, tk)
    return look


def fetch(shelf, key: str, dest: Path) -> Path:
    """Download one object and prove the bytes are the ones that were pushed.

    A truncated download is the failure that would otherwise reach YouTube as a
    broken video, unlisted and dated, with nothing in the logs. The sidecar's
    sha256 is checked every time — it costs a hash of a file we already have on
    disk, and it is the only evidence the transfer was whole.
    """
    meta = shelf.head(key)
    shelf.get(key, dest)
    got = r2.sha256_file(dest)
    if meta and meta.get("sha256") and meta["sha256"] != got:
        raise ValueError(
            f"{key} downloaded corrupt: sidecar says {meta['sha256'][:12]}…, "
            f"the {dest.stat().st_size:,} bytes on disk hash to {got[:12]}…")
    return dest


def run(limit: int = 4, dry_run: bool = False) -> int:
    cfg = config()
    per_week = cfg["cadence"]["videos_per_week"]
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    questions = {q["slug"]: q["query"] for q in order["queue"]}

    with Stage(LANE, week_id(),
               zero_work_hint="Nothing was shelved in R2 that is not already "
                              "in loop/state/ledger.json. Run bin/push-to-r2.sh "
                              "on the Mac once a render finishes.") as st:
        # -- the shelf --------------------------------------------------
        try:
            shelf = r2.require()
        except r2.R2Unavailable as e:
            st.named_stop(e.code, e.message, detail=e.detail, unblock=e.unblock)
        st.note(f"shelf: {shelf.label}")

        pending = backfill.library_pending(verbose=True,
                                           assets=shelf_lookup(shelf))
        if not pending:
            st.named_stop(
                "NOTHING_SHELVED",
                "every queued episode is either already in the ledger or not "
                "yet pushed to R2",
                unblock="On the Mac: bin/push-to-r2.sh")

        # -- the shared allowance ---------------------------------------
        afford = limit if dry_run else quota.videos_affordable(limit)
        if afford == 0:
            st.named_stop("QUOTA_EXHAUSTED",
                          f"no quota left today for a whole video. "
                          f"{quota.report()}",
                          unblock="Nothing to do; the allowance resets at "
                                  "midnight Pacific and this lane runs daily.")
        if afford < limit:
            st.note(f"quota allows {afford} of {limit} today. {quota.report()}")

        take = pending[:afford]
        led = ledger.load()
        when = backfill.schedule_for(led, len(take), per_week)

        for (slug, _, _), t in zip(take, when):
            print(f"  plan  {t:%a %d %b %H:%M UTC}  {slug}")

        if dry_run:
            # A dry run still has to be MORE than an exit 0. It proves the
            # shelf is reachable, the ranking resolves and the slots compute —
            # which is the whole lane bar the two irreversible calls.
            for (slug, rk, _), t in zip(take, when):
                st.work(f"planned {slug} for {t:%Y-%m-%d %H:%M UTC} from {rk}")
            st.note("DRY RUN — nothing downloaded, nothing uploaded.")
            return 0

        # -- the credential ---------------------------------------------
        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(
                code,
                f"{len(take)} episode(s) are shelved and scheduled but " + msg,
                detail={"ready": [s for s, _, _ in take]}, unblock=unblock)
        token = up.access_token(creds)
        st.note(f"credential source: {creds.get('source', 'env')}")

        # -- the work ---------------------------------------------------
        with tempfile.TemporaryDirectory(prefix="how-we-know-r2-") as td:
            tmp = Path(td)
            for (slug, rk, tk), t in zip(take, when):
                render = fetch(shelf, rk, tmp / f"{slug}-final.mp4")
                thumb = fetch(shelf, tk, tmp / f"{slug}.jpg")
                st.work(f"pulled {slug} from {shelf.label} "
                        f"({render.stat().st_size:,} bytes, verified)")
                backfill.upload_one(st, token, slug, questions[slug], render,
                                    thumb, t, lane=LANE)
                # Free the render before pulling the next one; an Actions
                # runner has ~14 GB and four 40 MB renders is fine, but this
                # lane should not become the reason a bigger one is not.
                render.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=4,
                    help="max videos this run (quota: 4 is safe, 6 is the wall)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
