"""The Shorts lane, running in GitHub Actions instead of on the owner's Mac.

    python loop/shorts_cloud.py --limit 2
    python loop/shorts_cloud.py --dry-run

WHY THIS MATTERS MORE THAN IT LOOKS. Five Shorts are cut and none are published.
Shorts are the discovery half of the strategy: roughly 10x the views of
long-form and ~3x faster subscriber growth when both formats run together, and
the signal YouTube weights most heavily is a viewer clicking from a Short into a
long-form video on the same channel — which is the exact shape of this library,
because every Short is a chapter lifted out of an episode that continues the
thought. They are already cut, so they cost nothing but this lane.

    Mac    bin/push-to-r2.sh   cut, VERIFY (V14 + V15), then shelve  ->  R2
    cloud  this file, daily    R2 -> YouTube, private, evening slot
    repo   loop/state/shorts_ledger.json committed back

THE EVENING SLOT IS NOT THE EPISODE SLOT, and this file does not choose it.
`shorts_lane.schedule_for()` does — 19:00 America/Chicago on Mon, Wed, Fri and
Sat. Long-form peaks 08:00-11:00 local and Shorts peak 18:00-21:00, very nearly
the inverse, so a Short scheduled from the episode constant would land in the
worst part of its own day. Nothing about that logic is duplicated here; this
file calls `shorts_lane.schedule_for()` and `shorts_lane.upload_short()` and
differs only in where the bytes come from.

────────────────────────────────────────────────────────────────────────────
WHY THE CUTTING DOES NOT HAPPEN HERE, WHICH IS THE ONE REAL COMPROMISE.

V14 (shorts-attribution) reads the credit back OFF THE FINISHED PIXELS, and
V15 (shorts-caption-crop) OCRs the source rows the caption plate occupies.
Both go through `research/imagery_video.py:ocr`, which compiles a Swift helper
against **Apple's Vision framework**. `swiftc` and Vision do not exist on
ubuntu-latest, and there is no drop-in substitute whose accuracy on these fonts
has been established.

Cutting in Actions would therefore mean running V14 and V15 nowhere. That is
not on the table: an unrun validator is not a passing one, and shipping an
uncredited Short on a monetised channel is the single thing this pipeline may
not do.

So the cut and its verification stay on the Mac — the same machine that already
renders, in the same batch — and `loop/r2.py:push_shorts()` REFUSES TO SHELVE
anything unless both validators are green. Nothing reaches R2 unverified, so
nothing this lane can reach is unverified. The scheduling, which is what
actually needed a machine that is awake every day, is what moved.

If Shorts ever become the primary lane, the answer is a native vertical render
path, not a second OCR engine.
────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import backfill as B                              # noqa: E402
import quota                                      # noqa: E402
import r2                                         # noqa: E402
import shorts_lane as SL                          # noqa: E402
import upload as up                               # noqa: E402
import arming  # noqa: E402
from common import Stage, config, week_id         # noqa: E402

LANE = "shorts-cloud"


def shelf_lookup(shelf):
    """A `have` callable for `shorts_lane.pending`, backed by R2.

    Both the cut AND its receipt, or neither. A Short without its
    `.short.json` is a video nobody can later prove was credited, and the
    receipt is the only record of which beats it used.
    """
    def look(slug: str):
        if shelf.head(r2.short_key(slug)) is None:
            return "not shelved in R2 — run bin/push-to-r2.sh on the Mac"
        if shelf.head(r2.short_receipt_key(slug)) is None:
            # RECORDED, not just refused. An empty selection has two very
            # different causes and one of them is a defect: "nothing has been
            # cut yet" resolves itself on the Mac's next push, while "a cut IS
            # on the shelf and cannot be proved credited" is a broken push that
            # will look identical every single day. Classifying the first as
            # self-resolving without separating the second is exactly the
            # 'inert lane wearing a reassuring label' this repo warns about.
            look.unverified.append(
                (slug, "the cut is shelved but its .short.json receipt is not"))
            return "the cut is shelved but its .short.json receipt is not"
        return True
    look.unverified = []
    return look


def run(limit: int = 2, dry_run: bool = False) -> int:
    cfg = config()

    with Stage(LANE, week_id(),
               zero_work_hint="No verified Short is shelved in R2 that is not "
                              "already in loop/state/shorts_ledger.json. On "
                              "the Mac: bin/make-shorts.sh --all && "
                              "bin/push-to-r2.sh") as st:
        # The schedule fires every day; this decides whether a
        # SCHEDULED run may act. Unarmed, it says so where a human
        # sees it instead of the lane being silently absent.
        arming.gate(st, 'shorts-cloud')
        try:
            shelf = r2.require()
        except r2.R2Unavailable as e:
            st.named_stop(e.code, e.message, detail=e.detail, unblock=e.unblock)
        st.note(f"shelf: {shelf.label}")

        look = shelf_lookup(shelf)
        todo = SL.pending(have=look)
        if not todo and look.unverified:
            st.named_stop(
                "SHORTS_SHELVED_BUT_UNVERIFIED",
                f"{len(look.unverified)} Short(s) are on the R2 shelf and "
                f"cannot be published because their .short.json receipt is "
                f"not: {', '.join(s_ for s_, _ in look.unverified)}. That is a "
                f"broken push, not an empty shelf, and it will look the same "
                f"tomorrow.",
                detail={"unverified": [{"slug": s_, "why": w}
                                       for s_, w in look.unverified]},
                unblock="The receipt is the only record of which beats a Short "
                        "used and who is credited for them, so it is not "
                        "optional. On the Mac: bin/push-to-r2.sh — its "
                        "push-shorts half writes both objects and refuses to "
                        "shelve a cut that fails V14 attribution or V15 "
                        "caption crop.")
        if not todo:
            st.named_stop(
                "NO_SHORTS_SHELVED",
                "every finished episode either already has a Short in the "
                "ledger or has no verified cut on the shelf",
                unblock="On the Mac: bin/make-shorts.sh --all, then "
                        "bin/push-to-r2.sh — which refuses to shelve a Short "
                        "that fails V14 or V15.")

        # The same 10,000-unit daily allowance the episode lane spends from. A
        # Short costs exactly what an episode costs (1,600 insert + 50 thumb +
        # 50 flip); YouTube does not discount the short one.
        afford = (limit if dry_run else
                  quota.videos_affordable(limit,
                                          reserve=quota.upload_reserve()))
        if afford == 0:
            st.named_stop("QUOTA_EXHAUSTED",
                          f"no quota left today for a Short. {quota.report()}",
                          detail={"resets_at": quota.next_reset()},
                          unblock="Nothing to do; the allowance resets at "
                                  "midnight Pacific and this lane runs daily.")
        if afford < limit:
            st.note(f"quota allows {afford} of {limit} today. {quota.report()}")

        take = todo[:afford]
        led = SL.load_ledger()
        when = SL.schedule_for(led, len(take))

        for slug, t in zip(take, when):
            print(f"  plan  {t.astimezone(SL.SHORTS_TZ):%a %d %b %H:%M %Z}  "
                  f"{slug}")

        if dry_run:
            for slug, t in zip(take, when):
                st.work(f"planned Short for {slug} at "
                        f"{t.astimezone(SL.SHORTS_TZ):%Y-%m-%d %H:%M %Z}")
            st.note("DRY RUN — nothing downloaded, nothing uploaded.")
            return 0

        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code,
                          f"{len(take)} verified Short(s) are shelved but "
                          + msg, detail={"ready": take}, unblock=unblock)
        token = up.access_token(creds)

        with tempfile.TemporaryDirectory(prefix="how-we-know-shorts-") as td:
            tmp = Path(td)
            for slug, t in zip(take, when):
                path = tmp / f"{slug}-short.mp4"
                # The receipt travels with the cut. It is not used to decide
                # anything here — V14 already read it on the Mac — but pulling
                # it proves the pair is intact, and a Short whose receipt has
                # gone missing is one nobody can audit later.
                meta = shelf.head(r2.short_receipt_key(slug))
                fetch_verified(shelf, r2.short_key(slug), path)
                st.work(f"pulled {slug} Short from {shelf.label} "
                        f"({path.stat().st_size:,} bytes, verified; receipt "
                        f"{meta['size']} bytes)")
                SL.upload_short(st, token, slug, B.question_for(slug), path, t,
                                lane=LANE)
                path.unlink(missing_ok=True)

        # A real Short just published for real. That is the exact evidence
        # loop/arming.py is waiting for; record it so a scheduled run
        # tomorrow no longer has to stop and ask.
        arming.record_success(
            'shorts-cloud',
            detail=f"published {len(take)} Short(s): {take}")
    return 0


def fetch_verified(shelf, key: str, dest: Path) -> Path:
    """Pull one object and prove the bytes are the ones the Mac verified.

    A truncated download would otherwise reach YouTube as a broken Short,
    scheduled, with nothing in the logs. The sidecar sha256 is the only
    evidence the transfer was whole.
    """
    meta = shelf.head(key)
    shelf.get(key, dest)
    got = r2.sha256_file(dest)
    if meta and meta.get("sha256") and meta["sha256"] != got:
        raise ValueError(
            f"{key} downloaded corrupt: sidecar says {meta['sha256'][:12]}…, "
            f"the {dest.stat().st_size:,} bytes on disk hash to {got[:12]}…")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=2,
                    help="max Shorts this run; 4/week is the cadence")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(limit=a.limit, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
