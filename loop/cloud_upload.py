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
import captions_build                            # noqa: E402
import captions_lane                             # noqa: E402
import ledger                                    # noqa: E402
import pov_match                                 # noqa: E402
import quota                                     # noqa: E402
import r2                                        # noqa: E402
import upload as up                              # noqa: E402
import arming  # noqa: E402
from common import Stage, config, read_json, week_id  # noqa: E402

LANE = "cloud-upload"


def shelf_lookup(shelf):
    """An `assets` callable for `backfill.library_pending`, backed by R2.

    Returns the two R2 KEYS rather than local paths — `library_pending` only
    passes the locators through, and heading two sidecars is cheap where
    downloading a 40 MB render to decide whether we want it is not. The bytes
    are fetched later, only for the episodes actually taken.
    """
    superseded = read_json(ROOT / "loop" / "state" / "superseded_renders.json",
                           default={})

    def look(slug: str):
        rk, tk = r2.render_key(slug), r2.thumb_key(slug)
        meta = shelf.head(rk)
        if meta is None:
            return "not shelved in R2 (no render) — run bin/push-to-r2.sh"
        # THE SHELF CAN HOLD A CUT THIS REPO HAS ALREADY REPLACED.
        #
        # loop/pov_repair.py rewrites a script's [HUMAN] beat, records the
        # assignment, and moves the local render aside for rebuilding. It
        # cannot touch R2. So between the repair and the Mac's next push, the
        # POV gate is satisfied — the assignment exists — while the bytes on
        # the shelf are the OLD cut, still speaking the sentence she never
        # said. Refusing on the recorded sha256 is exact, and it clears itself:
        # the re-rendered cut hashes differently, so the refusal ends the
        # moment the real repair reaches the shelf. Nothing is deleted; the
        # object is replaced by content, as push-to-r2.sh has always done.
        old = (superseded.get(slug) or {}).get("sha256")
        if old and meta.get("sha256") == old:
            return (f"the shelved render is the cut that was superseded on "
                    f"{superseded[slug].get('superseded_at', '?')[:10]} "
                    f"({superseded[slug].get('why', 'replaced')}). The Mac has "
                    f"not pushed the rebuilt cut yet — bin/push-to-r2.sh")
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


# WHAT MONDAY'S AUTHORING LANE HANDED OFF. Module level so a test can point it
# at a fixture.
RENDER_QUEUE = LOOP / "render_queue.json"

# Rows loop/draft.py writes that are still waiting to be narrated and rendered.
# Later statuses (rendered, uploaded-private, scheduled, published, dropped) are
# past the hand-off or were removed on purpose.
NOT_YET_BUILT = ("queued", "approved")


def diagnose_empty_shelf(queued: list[str], done: set[str], held: set[str],
                         handoff: list[dict] | None,
                         promotion_held: dict | None = None,
                         runway: dict | None = None,
                         refused: set | None = None) -> dict:
    """WHY the shelf holds nothing to upload, worked out from state this lane
    can already read. Returns the named stop to raise.

    WHY THIS EXISTS. From 2026-09-15 to 2026-09-22 this lane said
    NOTHING_SHELVED eight days running and then paged (#105) with "the Mac is
    not pushing - bin/push-to-r2.sh is failing, or com.howweknow.batch is not
    firing". Both were working. The batch had pushed all 34 renders; its own
    log said "pushed 0, skipped 68 already identical". All 34 episodes in
    research/publish_order*.json were already in the ledger, uploaded and
    dated. The shelf was empty because the PUBLISH QUEUE was used up, and that
    was visible from here the whole time. One code covered three different
    states, and the page blamed the only one that was not true.

    There are three states, and each gets its own code:

      NOTHING_SHELVED       queued episodes are not in the ledger and not on
                            the shelf. They are still waiting on the Mac
                            (narration, render or push). This is the only
                            state where the Mac is the one to check.
      AUTHORED_NOT_QUEUED   every queued episode is uploaded, and the authoring
                            lane has written scripts that are in no
                            research/publish_order*.json. bin/batch-session.sh
                            (the only narrator installed) reads only those
                            files, so nothing will ever narrate these scripts.
                            Time does not fix that. A person has to, so it is
                            needs_human. It names the slugs (held_items), so it
                            pages once and then waits in HELD until the list
                            changes.
      SCRIPTS_AWAITING_PROMOTION
                            every queued episode is uploaded, nothing new is
                            stranded, the runway still exists, and scripts
                            are held OUTSIDE the queue on purpose
                            (loop/promotion_holds.json) until the owner
                            decides whether to promote them. Her decision,
                            already known to her: owner_action, GREEN, carried
                            to the digest, never a daily page. (Owner
                            decision 2026-09-23.)
      SCRIPTS_AWAITING_PROMOTION_RUNWAY_CRITICAL
                            the same, but the runway is critical or could not
                            be computed, so the held decision is now what
                            stands between the channel and going dark.
                            needs_human, with held_items.
      PUBLISH_QUEUE_UPLOADED  every queued episode is uploaded and nothing is
                            stuck upstream. The lane is done until new work
                            arrives. Self-resolving, with a cap.

    Episodes held by the render gate are left out of "waiting on the Mac". The
    gate reports them in its own lane (RENDER_HELD). Counting them here would
    blame the Mac for a hold the gate put in place on purpose.
    """
    if not queued:
        # Zero rows. batch_queue already raises when no FILE exists; a file
        # with an empty queue must not read as "finished" either.
        return {"code": "PUBLISH_QUEUE_EMPTY",
                "message": "research/publish_order*.json exists but holds zero "
                           "queued rows, so this lane has nothing to compare "
                           "the shelf against. An empty queue looks the same "
                           "as a deleted one.",
                "detail": {"queued": 0},
                "unblock": "Restore the queue rows from origin/main, or re-run "
                           "the research/publish_order*.py that writes them.",
                "held_items": None}

    queued_set = set(queued)
    held_q = sorted(s for s in queued if s in held and s not in done)
    # PROMOTION-HELD SLUGS ARE NEVER "WAITING ON THE MAC" EITHER, for the
    # same reason they are never "already promoted" just because they are
    # coincidentally queued (below): the Mac has no real scripts/<slug>.md
    # for one regardless of whether its slug also appears in a
    # research/publish_order*.json row, because loop/draft.py's own gate
    # refuses to author a held slug in the first place. Read early so both
    # this check and the promotion-hold check below agree on one register.
    promotion_holds_now = set(promotion_held or {})
    awaiting_mac = [s for s in queued
                    if s not in done and s not in held
                    and s not in promotion_holds_now]
    if awaiting_mac:
        return {"code": "NOTHING_SHELVED",
                "message": f"{len(awaiting_mac)} queued episode(s) are not in "
                           f"the ledger and not on the R2 shelf, so they are "
                           f"still waiting on the Mac (narration, render or "
                           f"push): {', '.join(awaiting_mac[:8])}"
                           f"{' ...' if len(awaiting_mac) > 8 else ''}",
                "detail": {"awaiting_mac": awaiting_mac,
                           "render_gate_held": held_q,
                           "queued": len(queued), "uploaded": len(done & queued_set)},
                "unblock": "On the Mac: read the '=== batch session' block in "
                           "~/Library/Logs/how-we-know/batch.log. 'to narrate' "
                           "and 'to render' list these slugs until they are "
                           "built; bin/push-to-r2.sh shelves them afterwards.",
                "held_items": None}

    # Everything queued is uploaded (or held by the gate). Look upstream.
    if handoff is None:
        return {"code": "NO_QUEUE",
                "message": "every queued episode is uploaded, and "
                           "loop/render_queue.json (the Monday authoring "
                           "lane's hand-off) does not exist, so this lane "
                           "cannot tell whether new scripts are waiting "
                           "upstream.",
                "detail": {"queued": len(queued),
                           "uploaded": len(done & queued_set)},
                "unblock": "Restore loop/render_queue.json from origin/main, "
                           "or re-run the Monday lane (loop/draft.py).",
                "held_items": None}
    holds = promotion_held or {}
    # A hold whose slug has since been UPLOADED is over regardless. A hold
    # whose slug is merely queued is over ONLY if scripts/<slug>.md now
    # exists - real promotion means copying the held draft there (the `how`
    # text below says so), and only that write is evidence a decision was
    # actually made.
    #
    # `s not in queued_set` ALONE is not that evidence. Confirmed 2026-09-25:
    # research/publish_order_deep_sea_ocean_science.json's own topic-mining
    # pass produced a FRESH, unrelated candidate whose auto-generated slug
    # (slug_of()) happened to collide with why-deep-sea-creatures, a script
    # already held since 2026-09-23 awaiting her decision. The two are not
    # the same thing - one is an unpromoted draft in loop/drafts/, the other
    # a brand-new candidate with no script at all - but "in queued_set" could
    # not tell them apart, so the hold silently stopped being reported the
    # moment the collision landed, with nothing that looked like a decision
    # ever having been made.
    active_holds = sorted(
        s for s in holds
        if s not in done
        and not (s in queued_set and (ROOT / "scripts" / f"{s}.md").exists()))
    # A slug loop/batch_queue.py refused on read - the same question as an
    # episode already made, or another channel's topic (2026-09-25) - is
    # out of the queue by a DECISION, named in refused_entries(), not
    # stranded by a lane routing around the gate. Paging a person to
    # "queue it" would ask them to publish the duplicate.
    decided = set(refused or ())
    orphans = sorted({
        str(it.get("slug")) for it in handoff
        if it.get("slug") and it.get("status") in NOT_YET_BUILT
        and it["slug"] not in queued_set and it["slug"] not in done
        and it["slug"] not in holds and it["slug"] not in decided})
    base = {"queued": len(queued), "uploaded": len(done & queued_set),
            "render_gate_held": held_q, "promotion_held": active_holds}
    if orphans:
        return {"code": "AUTHORED_NOT_QUEUED",
                "message": f"Nothing is on the shelf because every one of the "
                           f"{len(queued)} episodes in research/publish_order*"
                           f".json is already uploaded. The Mac is not the "
                           f"problem. The shortfall is upstream: "
                           f"{len(orphans)} script(s) the Monday authoring lane "
                           f"wrote to loop/render_queue.json are in no "
                           f"publish_order file ({', '.join(orphans)}). "
                           f"bin/batch-session.sh, the only narrator installed "
                           f"on the Mac, reads only research/publish_order*.json "
                           f"and scripts/<slug>.md, so these scripts will never "
                           f"be narrated, rendered or uploaded.",
                "detail": dict(base, authored_not_queued=orphans,
                               handoff="loop/render_queue.json"),
                "unblock": "A decision for a person: either queue these slugs "
                           "(copy loop/drafts/<slug>.md to scripts/<slug>.md and "
                           "add a row with `slug` and `query` to a "
                           "research/publish_order*.json), or hold them for a "
                           "promotion decision by adding them to "
                           "loop/promotion_holds.json. Since 2026-09-23 "
                           "loop/rank.py and loop/draft.py select only "
                           "publish-queue topics, so a new script here means "
                           "something routed around that gate. Until then the "
                           "channel airs only what is already scheduled; see "
                           "the runway in loop/render_queue.json.",
                "held_items": orphans}
    if active_holds:
        level = (runway or {}).get("level")
        runway_msg = (runway or {}).get("message") or "runway could not be computed"
        hold_detail = dict(base, runway_level=level,
                           runway_weeks=(runway or {}).get("weeks_remaining"),
                           holds="loop/promotion_holds.json")
        how = ("Nothing for a person: the next Saturday weekly-score run "
               "(loop/score.py dispose_promotion_holds) puts each held "
               "script's question through the same demand-and-competition "
               "gate every queued topic passed, then promotes it (script into "
               "scripts/, row into its domain's publish order) or declines it "
               "(script into loop/drafts/declined/, hold removed, logged in "
               "docs/DECISION-LOG.md). Nothing is deleted either way.")
        if level in ("ok", "warn"):
            return {"code": "SCRIPTS_AWAITING_PROMOTION",
                    "message": f"Nothing to upload: every one of the "
                               f"{len(queued)} episodes in research/"
                               f"publish_order*.json is already uploaded and "
                               f"dated, and the runway exists ({runway_msg}). "
                               f"{len(active_holds)} script(s) are held outside "
                               f"the queue awaiting the Saturday gate's "
                               f"promotion decision: {', '.join(active_holds)}. "
                               f"They are not queued for the Mac and not "
                               f"deleted; loop/score.py decides each one on "
                               f"its next run. The Mac is not the problem.",
                    "detail": hold_detail,
                    "unblock": how,
                    "held_items": active_holds}
        return {"code": "SCRIPTS_AWAITING_PROMOTION_RUNWAY_CRITICAL",
                "message": f"Nothing to upload: every queued episode is "
                           f"already uploaded, and the runway is "
                           f"{level or 'unknown'} ({runway_msg}). "
                           f"{len(active_holds)} script(s) held awaiting the "
                           f"Saturday gate's promotion decision "
                           f"({', '.join(active_holds)}) are now what stands "
                           f"between the channel and going dark.",
                "detail": hold_detail,
                "unblock": how,
                "held_items": active_holds}
    return {"code": "PUBLISH_QUEUE_UPLOADED",
            "message": f"every one of the {len(queued)} episodes in "
                       f"research/publish_order*.json is already uploaded"
                       + (f" or held by the render gate ({', '.join(held_q)})"
                          if held_q else "")
                       + ", and nothing authored is waiting outside the queue. "
                         "This lane is finished until a new episode is queued "
                         "and shelved.",
            "detail": dict(base, authored_not_queued=[]),
            "unblock": "Nothing to do in this lane. New work arrives when an "
                       "episode enters research/publish_order*.json and the "
                       "Mac shelves it.",
            "held_items": None}


def handoff_rows() -> list[dict] | None:
    """loop/render_queue.json's rows, or None if the file does not exist.

    None and [] mean different things. A missing file is not "nothing is
    stuck upstream"; it means the upstream check could not be done at all.
    diagnose_empty_shelf() raises NO_QUEUE for it, so it is never read as
    finished."""
    if not RENDER_QUEUE.exists():
        return None
    return list((read_json(RENDER_QUEUE, default={}) or {}).get("items") or [])


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
            # NAME THE STATE, don't guess it. See diagnose_empty_shelf().
            import render_gate                             # noqa: PLC0415
            why = diagnose_empty_shelf(
                batch_queue.queued_slugs(),
                {r["slug"] for r in ledger.load()["published"]},
                render_gate.held_slugs(),
                handoff_rows(),
                promotion_held=batch_queue.promotion_holds(),
                runway=cadence.runway(per_week),
                refused={r["slug"] for r in batch_queue.refused_entries()})
            st.named_stop(why["code"], why["message"], detail=why["detail"],
                          unblock=why["unblock"],
                          held_items=why["held_items"])

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
        # WHY, not just WHICH. `untraced_reasons()` distinguishes "no entry"
        # from "an entry that names a line this repo cannot honour" (a
        # tier:specific line from another domain, a pov_id the bank does not
        # have, text that has drifted from the bank's). Both refuse the
        # episode; they need opposite fixes, and a refusal that misnames its
        # cause sends someone to add a row that is already there.
        slugs_ = [s_ for s_, _, _ in take]
        untraced = set(pov_match.untraced_pov(slugs_))
        why_untraced = pov_match.untraced_reasons(slugs_)
        if untraced:
            for slug in sorted(untraced):
                print(f"  REFUSE {slug}: {why_untraced[slug]}")
            st.note(f"refused {len(untraced)} episode(s) with an untraced "
                    f"first-person POV: {', '.join(sorted(untraced))}. They "
                    f"stay on the shelf; nothing is deleted.")
            take = [t for t in take if t[0] not in untraced]
        if untraced and not take:
            st.named_stop(
                "POV_UNTRACED",
                f"every episode ready to upload today carries a first-person "
                f"[HUMAN] Producer POV with no entry in "
                f"pov/pov-assignments.json, or one this repo cannot "
                f"honour: "
                + "; ".join(f"{s} — {why_untraced[s]}"
                            for s in sorted(untraced)) + ". "
                f"Uploading one would be the channel asserting she said "
                f"something no interview records her saying.",
                detail={"untraced": sorted(untraced),
                        "assignments": str(pov_match.ASSIGNMENTS
                                           .relative_to(ROOT)),
                        "bank": str(pov_match.BANK.relative_to(ROOT))},
                # Same shape as CAPTIONS_NOT_READY above, and deliberately so:
                # only she can approve a POV line, so this halt is hers to
                # clear and the second morning's identical report is noise.
                held_items=sorted(untraced),
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
        #
        # SELF-HEAL FIRST. Everything above this line was written when the .srt
        # could only be made on the Mac that voiced the episode. It no longer
        # can: `visuals/captions.py` records each measured wav duration into
        # `audio/<slug>/beats.json`, which git tracks, so the caption track is
        # now a pure function of the repository and this runner can build it in
        # about a second. On 2026-09-08 run 34236877023 refused
        # how-strong-is-graphene, exited 3 and asked the owner to open a laptop
        # and type a command — for an artifact the runner was holding every
        # input to. Build it, then judge what is left.
        #
        # The gate below is UNCHANGED and still the last word. Healing can only
        # ever remove a reason to refuse; nothing here can pass an episode the
        # gate would have blocked, because the gate re-asks
        # `captions_lane.uncaptioned()` afterwards against the files on disk.
        healed = captions_build.heal([s_ for s_, _, _ in take], note=st.note)
        for slug_ in healed["built"]:
            st.work(f"built the missing caption track for {slug_} in the cloud "
                    f"from committed beat timings — no Mac involved")
        for slug_, why_ in healed["unhealable"]:
            print(f"  CANNOT HEAL {slug_}: {why_}")

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
                # WHAT THIS STOP IS WAITING ON, by name. Naming the slugs is
                # what lets loop/held.py tell "the same two episodes, still"
                # from "a third one just joined them", so a hold can never go
                # quiet about a problem that grew.
                held_items=sorted(s for s, _ in uncaptioned),
                unblock="NOTHING TO TYPE, and this is no longer the common "
                        "case. The premise this stop was written on - that the "
                        "caption track exists only on the Mac that voiced the "
                        "episode - stopped being true on 2026-09-08. This lane "
                        "now BUILDS a missing track itself "
                        "(loop/captions_build.py) from the beat timings "
                        "committed in audio/<slug>/beats.json, so the only way "
                        "to reach this stop is an episode whose narration was "
                        "never measured at all: no beats.json, or only part of "
                        "one, which means it was never fully voiced. The next "
                        "bin/batch-session.sh on the Mac narrates it, records "
                        "the durations and commits them, after which this lane "
                        "captions and uploads it unattended. Nothing is "
                        "deleted meanwhile: the render stays on the R2 shelf.")

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
