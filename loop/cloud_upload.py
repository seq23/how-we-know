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
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence                               # noqa: E402
import backfill                                  # noqa: E402
import batch_queue                               # noqa: E402
import captions_lane                             # noqa: E402
import ledger                                    # noqa: E402
import pov_match                                 # noqa: E402
import quota                                     # noqa: E402
import r2                                        # noqa: E402
import upload as up                              # noqa: E402
import arming  # noqa: E402
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


def questions_map() -> dict[str, str]:
    """slug -> the episode's question, for EVERY domain's queue.

    Module level and named so a test can assert the join this lane depends on
    without standing up the whole lane: the set of slugs
    `backfill.library_pending` may select must be a subset of the keys here.
    See loop/tests/test_upload_queue_sources_agree.py.
    """
    return {q["slug"]: q.get("query") for q in batch_queue.queued_entries()}


def run(limit: int = 4, dry_run: bool = False) -> int:
    cfg = config()
    # THROUGH cadence.effective(). See the note in loop/backfill.py:library():
    # this lane assigns the publish slot, so it must see the same cadence the
    # drafting and ranking stages do.
    per_week = cadence.effective()
    # THE SAME LIST THE PLANNER SELECTS FROM, not a second one. This read
    # `research/publish_order.json` by name while `backfill.library_pending`
    # (below) selects from `batch_queue.queued_entries()`, which globs
    # `research/publish_order*.json`. The moment a second domain got its own
    # queue file the two diverged: the planner could pick any of 34 slugs and
    # this map held 16, so run 34038288267 pulled 50,982,483 verified bytes of
    # `how-is-a-silicon-wafer-made` out of R2 and then died on
    # `questions[slug]` with a bare KeyError - AFTER the download, BEFORE the
    # upload. Every materials episode was unreachable by this lane.
    #
    # `queued_entries()` already carries `query` on the row for exactly this
    # reason (see its docstring), so there is nothing to look up elsewhere.
    questions = questions_map()

    with Stage(LANE, week_id(),
               zero_work_hint="Nothing was shelved in R2 that is not already "
                              "in loop/state/ledger.json. Run bin/push-to-r2.sh "
                              "on the Mac once a render finishes.") as st:
        # The schedule fires every day; this decides whether a
        # SCHEDULED run may act. Unarmed, it says so where a human
        # sees it instead of the lane being silently absent.
        arming.gate(st, 'upload-cloud')
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
        # Reserve the evening's Shorts - see loop/quota.shorts_reserve().
        afford = (limit if dry_run else
                  quota.videos_affordable(limit,
                                          reserve=quota.shorts_reserve()))
        if afford == 0:
            # NAME WHO SPENT IT. This stop fired on 2026-09-01 (run
            # 33521586490) and the message said only "no quota left", so it
            # read as a fault in this lane. It was not: the Mac's launchd
            # backfill agent had already spent the day at 09:00, which is the
            # documented dual-lane transition, not a bug. A stop that does not
            # name its cause gets triaged from scratch every time it fires.
            others = ", ".join(
                f"{k} {v}" for k, v in sorted(
                    (quota._load().get("by_lane") or {}).items())  # noqa: SLF001
                if k != LANE) or "nothing else"
            st.named_stop("QUOTA_EXHAUSTED",
                          f"no quota left today for a whole video "
                          f"({quota.PER_VIDEO} units). Already spent today by: "
                          f"{others}. {quota.report()}",
                          detail={"pending": [s for s, _, _ in pending],
                                  # WHEN it resolves, not just that it does.
                                  # loop/stop_policy.json will not treat a
                                  # quota stop as self-resolving without this.
                                  "resets_at": quota.next_reset()},
                          unblock="Usually nothing to do — the allowance "
                                  "resets at midnight Pacific and this lane "
                                  "runs daily, so tomorrow's run picks up "
                                  "exactly where this one stopped. If the "
                                  "spending lane above is 'backfill', the "
                                  "Mac's launchd agent com.howweknow.backfill "
                                  "is still uploading the same library from "
                                  "the other side. Two lanes on one 10,000-"
                                  "unit allowance is the documented transition "
                                  "state, not a fault: unload the Mac agent "
                                  "once this lane has uploaded once, watched.")
        if afford < limit:
            st.note(f"quota allows {afford} of {limit} today. {quota.report()}")

        take = pending[:afford]

        # BELT AND BRACES, AND IT NAMES THE SLUG. The two lists above are now
        # one list, so this cannot fire from the divergence that produced run
        # 34038288267. It exists because the FAILURE MODE was the problem, not
        # only the divergence: a slug the planner selected but the title map
        # could not answer for died as a bare `KeyError` from the middle of a
        # loop, after a 50 MB download, with nothing in the log naming what was
        # wrong. Any future reason a queue row loses its `query` - a hand-edited
        # publish-order file, a new domain file written by a different agent -
        # stops here instead, named, before a single byte is fetched.
        #
        # This is a REFUSAL, not a skip: it does not drop the offending slug and
        # upload the rest, because a queued, rendered, shelved episode that
        # cannot state its own title is a broken queue, not a finished one.
        untitled = [s_ for s_, _, _ in take if not questions.get(s_)]
        if untitled:
            st.named_stop(
                "QUEUE_ROW_HAS_NO_QUESTION",
                f"{len(untitled)} episode(s) are shelved and selected for "
                f"upload but carry no `query` in any research/publish_order*"
                f".json: {', '.join(untitled)}. The title of a video comes from "
                f"that field, so this lane will not upload them.",
                detail={"untitled": untitled,
                        "queue_files": [p_.name for p_ in
                                        batch_queue.publish_order_files()],
                        "queue_size": len(questions)},
                unblock="Add a `query` to each slug's row in the "
                        "research/publish_order*.json file that queues it - it "
                        "is the episode's question and becomes its title. If a "
                        "slug should not be published at all, remove its row "
                        "from the queue file rather than leaving it untitled.")

        # -- the POV gate, BEFORE the upload ----------------------------
        # `[HUMAN]` is the one beat where the owner speaks as herself. V32
        # checks that every SCHEDULED episode's beat traces to
        # pov/pov-assignments.json, but it reads the ledger, and an episode
        # only reaches the ledger by being uploaded - so V32 can report the
        # harm and cannot prevent it. Three episodes went up before it spoke
        # (run 34035963724); fifteen more in the queue carry the same untraced
        # beat today. This asks V32's question one step earlier, where refusing
        # is still free.
        #
        # REFUSE THE EPISODE, NOT THE LANE. An untraced episode must not go to
        # YouTube; the twenty that are properly traced must still ship. Each
        # refusal is printed by name - this is not a silent `continue` - and if
        # refusing empties the run entirely it becomes a NAMED STOP rather than
        # an exit 0 that did nothing (Rule 0).
        untraced = set(pov_match.untraced_pov([s_ for s_, _, _ in take]))
        if untraced:
            for slug in sorted(untraced):
                print(f"  REFUSE {slug}: its [HUMAN] Producer POV has no entry "
                      f"in pov/pov-assignments.json")
            st.note(f"refused {len(untraced)} episode(s) with an untraced "
                    f"first-person POV: {', '.join(sorted(untraced))}. They "
                    f"stay on the shelf; nothing is deleted.")
            take = [t for t in take if t[0] not in untraced]
        if untraced and not take:
            st.named_stop(
                "POV_UNTRACED",
                f"every episode ready to upload today carries a first-person "
                f"[HUMAN] Producer POV with no entry in "
                f"pov/pov-assignments.json: {', '.join(sorted(untraced))}. "
                f"Uploading one would be the channel asserting she said "
                f"something no interview records her saying.",
                detail={"untraced": sorted(untraced),
                        "assignments": str(pov_match.ASSIGNMENTS
                                           .relative_to(ROOT)),
                        "bank": str(pov_match.BANK.relative_to(ROOT))},
                unblock="Two honest ways, and a validator may not do either "
                        "for her.\n\n"
                        "1. She reads the [HUMAN] line in scripts/<slug>.md, "
                        "and if it is hers it is recorded in "
                        "pov/pov-bank.json with `source: owner-approved "
                        "<date>` and given an entry in "
                        "pov/pov-assignments.json - the precedent set on "
                        "2026-09-05 for how-are-microchips-made, "
                        "how-does-quenching-harden-steel and "
                        "how-do-self-healing-materials-work (pov-099..101).\n\n"
                        "2. The episode is re-cut without the beat.\n\n"
                        "Nothing is deleted either way: the renders stay on "
                        "the shelf and this lane picks them up the run after "
                        "the assignment lands.")

        # -- the CAPTIONS gate, BEFORE the upload -----------------------
        # Exactly the POV gate's shape, for exactly the POV gate's reason, on
        # the other artifact an episode cannot air without.
        #
        # V16 caption-track reads the LEDGER too, so it also speaks only after
        # the video is on YouTube. CONFIRMED on run 34041348292: V16 went
        # PASS(examined 20) on 09-05 and FAIL(3)(examined 22) on 09-06 with no
        # commit between them. Nothing regressed — the upload lane put
        # how-does-tempered-glass-shatter, how-strong-is-titanium and
        # how-is-damascus-steel-made on the calendar at 2026-09-05T21:36Z with
        # no captions/<slug>.srt in the repo, and the lane went red the day
        # they counted. A lane that only fails once the video is live can
        # report the gap; it cannot prevent it.
        #
        # The .srt is not optional and not recoverable in the cloud: it is
        # derived from the narration WAVs by visuals/captions.py, and
        # audio/**/*.wav is gitignored, so it can only be made on the machine
        # that voiced the episode. If it is not committed before the upload, no
        # track can ever be inserted for that video and V16 is red forever.
        # Refusing here is the last moment refusing is free.
        #
        # REFUSE THE EPISODE, NOT THE LANE — same contract as the POV gate.
        uncaptioned = captions_lane.uncaptioned([s_ for s_, _, _ in take])
        if uncaptioned:
            for slug_, why in uncaptioned:
                print(f"  REFUSE {slug_}: {why}")
            st.note(f"refused {len(uncaptioned)} episode(s) with no usable "
                    f"English .srt: "
                    f"{', '.join(s for s, _ in uncaptioned)}. They stay on the "
                    f"shelf; nothing is deleted.")
            blocked = {s for s, _ in uncaptioned}
            take = [t for t in take if t[0] not in blocked]
        if uncaptioned and not take:
            st.named_stop(
                "CAPTIONS_NOT_READY",
                f"every episode ready to upload today would air with no "
                f"English caption track, because no usable captions/<slug>.srt "
                f"is committed for it: "
                f"{', '.join(s for s, _ in uncaptioned)}. Uploading one would "
                f"schedule a video this repo can never caption.",
                detail={"uncaptioned": [{"slug": s, "why": w}
                                        for s, w in uncaptioned],
                        "captions_dir": str(captions_lane.CAPTIONS_DIR
                                            .relative_to(ROOT))},
                unblock="The .srt is derived from the narration audio, which "
                        "only exists on the Mac that voiced the episode:\n\n"
                        "  python visuals/captions.py <slug>\n\n"
                        "then commit captions/<slug>.srt (and the .vtt, "
                        ".chapters.txt and .timing.json it writes beside it). "
                        "This lane picks the episode up on the run after they "
                        "land. Nothing is deleted meanwhile: the render stays "
                        "on the R2 shelf.")

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

        # A real upload just happened for real, against the live channel.
        # That is exactly the evidence loop/arming.py is waiting for; record
        # it so a scheduled run tomorrow no longer has to stop and ask.
        arming.record_success(
            'upload-cloud',
            detail=f"uploaded and scheduled {len(take)} episode(s): "
                   f"{[s for s, _, _ in take]}")
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
