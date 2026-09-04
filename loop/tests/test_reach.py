"""The reach lanes must catch their own defects — proven by breaking the state.

The two reach lanes (`loop/captions_lane.py`, `loop/localize.py`) put the
channel in front of non-English viewers: an English caption track, which is
what YouTube auto-translates subtitles AND audio from, and localized titles and
descriptions in es, pt-BR, hi, id, de.

Everything they can get wrong is expensive and quiet:

  * a published video with no caption track — no auto-translation can fire, in
    any language, and nothing anywhere says so
  * a published video with no localizations — invisible to non-English search
  * `defaultLanguage` unset — the API rejects localizations and Studio renders
    no subtitle UI at all, so the whole feature area silently does not exist
  * a `videos.update` carrying a PARTIAL snippet — `videos.update` REPLACES the
    parts named in `part=`, so this erases the title, description, tags and
    categoryId of a live video behind a 200 OK
  * the caption lane passing green having uploaded nothing

So each of those is constructed here as a broken state and the failure is shown
to return. A validator that has only ever seen a good day is untested.

Hard-fails if it examines zero behaviours.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import captions_lane                                      # noqa: E402
import localize                                           # noqa: E402
import quota                                              # noqa: E402
import upload as up                                       # noqa: E402
import validate                                           # noqa: E402
import ytmeta                                             # noqa: E402
from common import config                                 # noqa: E402

VID = "TESTVIDEO123"
SLUG = "10-what-is-the-deepest-part-of-the-ocean"          # has a real .srt
FAKE = [{"video_id": VID, "slug": SLUG}]


def with_live(rows):
    """Point every reach validator at a constructed channel."""
    validate._live_videos = lambda: rows                   # noqa: SLF001


def write(tmp, name, obj) -> str:
    p = os.path.join(tmp, name)
    with open(p, "w") as fh:
        json.dump(obj, fh)
    return p


def check() -> list[str]:
    fails, examined = [], 0
    tmp = tempfile.mkdtemp()
    cfg = config()
    real_live = validate._live_videos                      # noqa: SLF001
    real_cap, real_loc = validate.CAPTIONS_STATE, validate.LOCALIZATIONS_STATE
    real_src, real_dir = validate.UPLOAD_SRC, validate.REACH_LOOP_DIR
    real_caps = validate.REACH_CAPTIONS_DIR

    # V16 needs an .srt on disk for the video it is judging. Point it at a
    # fixture the test owns rather than at captions/, so this proves the
    # VALIDATOR's logic and not the state of a directory: an earlier version
    # read the real captions/ and went red on a runner, where the answer was
    # "the file is not checked out", not "the validator is wrong".
    caps = os.path.join(tmp, "captions")
    os.makedirs(caps, exist_ok=True)
    with open(os.path.join(caps, f"{SLUG}.srt"), "w") as fh:
        fh.write("1\n00:00:00,000 --> 00:00:02,000\nHello.\n\n")
    validate.REACH_CAPTIONS_DIR = caps

    try:
        # ---------------------------------------------- zero-item guard
        # A reach validator with no live video governs nothing and must say so.
        with_live([])
        for name, fn in (("V16", validate.v16_caption_track),
                         ("V17", validate.v17_localizations)):
            examined += 1
            r = fn()
            if r.ok:
                fails.append(f"{name} PASSED with no live video — a validator "
                             f"that examines zero items must fail")
            if "examined 0" not in r.status:
                fails.append(f"{name} did not report that it examined zero "
                             f"items")

        with_live(FAKE)

        # ------------------------------------- V16: no caption track at all
        examined += 1
        validate.CAPTIONS_STATE = write(tmp, "cap-empty.json",
                                        {"videos": {}, "blocked": {}})
        r = validate.v16_caption_track()
        if r.ok:
            fails.append("V16 passed a published video with NO English caption "
                         "track — YouTube can auto-translate neither its "
                         "subtitles nor its audio")

        # ------------------------- V16: 'blocked' is honoured, but only while
        # the scope is genuinely missing. An exemption that outlives its reason
        # is how a permanent gap gets a permanent excuse.
        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-blocked.json",
            {"videos": {}, "token_has_force_ssl": False,
             "blocked": {VID: {"slug": SLUG,
                               "reason": "CAPTIONS_SCOPE_MISSING"}}})
        if not validate.v16_caption_track().ok:
            fails.append("V16 failed a video that is blocked on the owner's "
                         "force-ssl consent; that is a named stop, not a defect")

        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-stale.json",
            {"videos": {}, "token_has_force_ssl": True,
             "blocked": {VID: {"slug": SLUG,
                               "reason": "CAPTIONS_SCOPE_MISSING"}}})
        if validate.v16_caption_track().ok:
            fails.append("V16 still excused a missing caption track after the "
                         "force-ssl scope arrived — the exemption outlived the "
                         "thing that justified it")

        # ------------- V16: the quota deferral is real, bounded, and expires
        # The backfill is 450 units a video and spans days. That excuses a gap
        # today; it must never excuse a permanent one.
        import datetime as _dt
        fresh = _dt.datetime.now(_dt.timezone.utc).isoformat()
        stale = (_dt.datetime.now(_dt.timezone.utc)
                 - _dt.timedelta(days=validate.DEFER_GRACE_DAYS + 1)).isoformat()

        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-defer-fresh.json",
            {"videos": {}, "token_has_force_ssl": True,
             "blocked": {VID: {"slug": SLUG, "reason": "QUOTA_DEFERRED",
                               "since": fresh}}})
        if not validate.v16_caption_track().ok:
            fails.append("V16 failed a video deferred to tomorrow for quota; "
                         "the caption backfill legitimately spans days")

        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-defer-stale.json",
            {"videos": {}, "token_has_force_ssl": True,
             "blocked": {VID: {"slug": SLUG, "reason": "QUOTA_DEFERRED",
                               "since": stale}}})
        if validate.v16_caption_track().ok:
            fails.append(f"V16 still excused a caption gap "
                         f"{validate.DEFER_GRACE_DAYS + 1} days after it was "
                         f"deferred — a daily excuse that never expires is a "
                         f"permanent gap with a label on it")

        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-defer-nodate.json",
            {"videos": {}, "token_has_force_ssl": True,
             "blocked": {VID: {"slug": SLUG, "reason": "QUOTA_DEFERRED"}}})
        if validate.v16_caption_track().ok:
            fails.append("V16 excused a deferral with no date on it, which "
                         "can never expire")

        examined += 1
        validate.CAPTIONS_STATE = write(
            tmp, "cap-good.json",
            {"videos": {VID: {"slug": SLUG, "caption_id": "abc",
                              "language": "en"}}, "blocked": {},
             "token_has_force_ssl": True})
        if not validate.v16_caption_track().ok:
            fails.append("V16 failed a video that has a recorded caption track")

        # ------------------------- V16: an .srt that does not exist at all
        # Not the same as "no track uploaded": there is nothing TO upload, and
        # no amount of quota or consent fixes it.
        examined += 1
        empty_caps = os.path.join(tmp, "no-captions")
        os.makedirs(empty_caps, exist_ok=True)
        validate.REACH_CAPTIONS_DIR = empty_caps
        if validate.v16_caption_track().ok:
            fails.append("V16 passed a published video whose .srt does not "
                         "exist — nothing could ever caption it")
        validate.REACH_CAPTIONS_DIR = caps

        # ------------------------------------------- V17: no localizations
        examined += 1
        validate.LOCALIZATIONS_STATE = write(tmp, "loc-none.json", {"videos": {}})
        if validate.v17_localizations().ok:
            fails.append("V17 passed a published video with NO localizations — "
                         "it cannot be found by any non-English search")

        # --------- V17: "deferred for quota" and "nobody noticed" are NOT
        #                the same fact, and must not read the same way.
        #
        # THE 2026-09-03 DEFECT, in one block. That morning the reach lane
        # mailed a FAIL naming twelve videos. Eleven were deferred for quota
        # with their .srt ready -- a lane working exactly as designed -- and
        # exactly one (_fQ3-YI63oQ) was a real gap. The daily red made the
        # eleven and the one indistinguishable, so the mail stopped being
        # read. V16 could already tell them apart; V17 could not, because
        # loop/localize.py never wrote the receipt V16's counterpart relies on.
        #
        # Each assertion below is a direction the fix must NOT be allowed to
        # drift in: green on a fresh deferral, RED on a bare gap, RED when the
        # excuse expires, RED when the excuse has no date to expire from.
        examined += 1
        r = validate.v17_localizations()
        if not r.failures:
            fails.append("V17 did not fail a published video with no "
                         "localizations and NO recorded reason — this is the "
                         "_fQ3-YI63oQ case and it must stay red")
        if r.stops:
            fails.append("V17 raised a NAMED STOP for a video with no "
                         "recorded reason; a stop must name a REAL cause, "
                         "never launder a gap nobody explained")

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-defer-fresh.json",
            {"videos": {}, "blocked": {VID: {"slug": SLUG,
                                             "reason": "QUOTA_DEFERRED",
                                             "since": fresh}}})
        r = validate.v17_localizations()
        if not r.ok:
            fails.append("V17 failed a video the localize lane deliberately "
                         "deferred for quota today — a legitimate stop must "
                         "be GREEN, not red")
        # Rule 0: green is not permission to go quiet. The deferral has to be
        # ON SCREEN, with its code and its count, or this is a silent skip
        # wearing a validator's name.
        if not r.stops:
            fails.append("V17 went green on a deferral without emitting a "
                         "NAMED STOP — a stage may not exit 0 having silently "
                         "said nothing about what stopped")
        elif (r.stops[0]["code"] != "LOCALIZE_QUOTA_DEFERRED"
                or not r.stops[0]["items"]
                or "1 of 1" not in r.stops[0]["message"]):
            fails.append("V17's NAMED STOP does not name the code, the count "
                         "and the affected videos; an unnamed stop is a skip")
        if "STOP" not in r.status:
            fails.append("V17's status hides the named stop behind a plain "
                         "PASS — the whole point is that it stays visible")

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-defer-stale.json",
            {"videos": {}, "blocked": {VID: {"slug": SLUG,
                                             "reason": "QUOTA_DEFERRED",
                                             "since": stale}}})
        if validate.v17_localizations().ok:
            fails.append(f"V17 still excused missing localizations "
                         f"{validate.DEFER_GRACE_DAYS + 1} days after they "
                         f"were deferred — an excuse that never expires is a "
                         f"permanent gap with a label on it")

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-defer-nodate.json",
            {"videos": {}, "blocked": {VID: {"slug": SLUG,
                                             "reason": "QUOTA_DEFERRED"}}})
        if validate.v17_localizations().ok:
            fails.append("V17 excused a deferral with no date on it, which "
                         "can never expire")

        # A deferral receipt must not outlive the gap it excused. If the lane
        # localizes the video but leaves `blocked` behind, V17 would stay
        # quiet about that video forever.
        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-defer-done.json",
            {"videos": {VID: {"slug": SLUG,
                              "languages": validate.REACH_LANGUAGES}},
             "blocked": {VID: {"slug": SLUG, "reason": "QUOTA_DEFERRED",
                               "since": stale}}})
        r = validate.v17_localizations()
        if not r.ok:
            fails.append("V17 failed a fully localized video because a stale "
                         "deferral receipt was left behind")
        if r.stops:
            fails.append("V17 reported a video as deferred when it is "
                         "actually finished — the receipt outlived the gap")

        # ------- THE SOURCE OF THAT RECEIPT. A validator that honours
        # `blocked` is worthless if the lane never writes it, which is exactly
        # the state loop/localize.py shipped in. Two components each keeping
        # their own list with no link between them is how this defect hid.
        examined += 1
        src = open(os.path.join(LOOP, "localize.py")).read()
        marker = 'state["blocked"][row["video_id"]] = {'
        if marker not in src:
            fails.append("loop/localize.py does not record a per-video "
                         "QUOTA_DEFERRED receipt, so V17 can never tell a "
                         "deferral from a gap no matter what it checks")
        else:
            # ORDER IS THE BUG. Recording after the stop records nothing:
            # st.named_stop raises. Prove the write precedes the raise.
            if src.index(marker) > src.index('"QUOTA_EXHAUSTED"'):
                fails.append("loop/localize.py records its deferrals AFTER "
                             "raising QUOTA_EXHAUSTED — named_stop raises, so "
                             "on the day every video is deferred not one "
                             "receipt is ever written. This is the original "
                             "defect, restored.")
        examined += 1
        if 'state["blocked"].pop(vid, None)' not in src:
            fails.append("loop/localize.py never clears a deferral receipt "
                         "when the video is actually localized")

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-partial.json",
            {"videos": {VID: {"slug": SLUG, "languages": ["es", "de"],
                              "default_language": "en"}}})
        if validate.v17_localizations().ok:
            fails.append("V17 passed a video missing hi, id and pt-BR")

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-full.json",
            {"videos": {VID: {"slug": SLUG,
                              "languages": validate.REACH_LANGUAGES,
                              "default_language": "en"}}})
        if not validate.v17_localizations().ok:
            fails.append("V17 failed a fully localized video")

        # --------------------------------------- V18: defaultLanguage unset
        examined += 1
        doctored = os.path.join(tmp, "upload_nodefault.py")
        src = open(os.path.join(LOOP, "upload.py")).read()
        open(doctored, "w").write(
            src.replace('"defaultLanguage": "en", "defaultAudioLanguage": "en"',
                        '"nothing": "here"'))
        validate.UPLOAD_SRC = doctored
        if validate.v18_default_language().ok:
            fails.append("V18 passed an upload payload with no "
                         "snippet.defaultLanguage — every video it uploads "
                         "would be unable to hold a localization, and Studio "
                         "would show no subtitle UI at all")

        # --------------------------------------- V18: en-US instead of en
        examined += 1
        doctored2 = os.path.join(tmp, "upload_enus.py")
        open(doctored2, "w").write(
            src.replace('"defaultLanguage": "en",', '"defaultLanguage": "en-US",'))
        validate.UPLOAD_SRC = doctored2
        if validate.v18_default_language().ok:
            fails.append('V18 passed "en-US"; the canonical value for this '
                         'channel is "en" and a library split between the two '
                         'is a silent inconsistency')

        examined += 1
        validate.UPLOAD_SRC = real_src
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-enus.json",
            {"videos": {VID: {"slug": SLUG,
                              "languages": validate.REACH_LANGUAGES,
                              "default_language": "en-US"}}})
        if validate.v18_default_language().ok:
            fails.append('V18 passed a video that SHIPPED with '
                         'defaultLanguage="en-US"')

        examined += 1
        validate.LOCALIZATIONS_STATE = write(
            tmp, "loc-full2.json",
            {"videos": {VID: {"slug": SLUG,
                              "languages": validate.REACH_LANGUAGES,
                              "default_language": "en"}}})
        if not validate.v18_default_language().ok:
            fails.append("V18 failed the real, correct configuration")

        # ------------------------------- V19: a partial-snippet videos.update
        examined += 1
        pen = os.path.join(tmp, "loop")
        os.makedirs(pen, exist_ok=True)
        with open(os.path.join(pen, "rogue_lane.py"), "w") as fh:
            fh.write('URL = "https://www.googleapis.com/youtube/v3/'
                     'videos?part=snippet,localizations"\n')
        validate.REACH_LOOP_DIR = pen
        if validate.v19_snippet_merge().ok:
            fails.append("V19 passed a module issuing videos.update with "
                         "part=snippet directly — that call REPLACES the "
                         "snippet and would erase the title, description, tags "
                         "and categoryId of a live video")
        validate.REACH_LOOP_DIR = real_dir

        examined += 1
        if not validate.v19_snippet_merge().ok:
            fails.append("V19 failed the real loop/ — no module there should "
                         "be sending a snippet-bearing videos.update outside "
                         "ytmeta.py")

    finally:
        validate._live_videos = real_live                  # noqa: SLF001
        validate.CAPTIONS_STATE, validate.LOCALIZATIONS_STATE = real_cap, real_loc
        validate.UPLOAD_SRC, validate.REACH_LOOP_DIR = real_src, real_dir
        validate.REACH_CAPTIONS_DIR = real_caps

    # ------------------------------------------ the merge itself, directly
    # V19 asserts merge_snippet REFUSES a partial snippet. This asserts the
    # other half: that the body actually put on the wire carries everything.
    examined += 1
    live = {"title": "Why is it dark?", "description": "Because.\nSources:\nx",
            "tags": ["deep sea"], "categoryId": "27",
            "channelId": "UCxxxx", "publishedAt": "2026-01-01T00:00:00Z"}
    body = ytmeta.update_localizations(
        "no-token", VID, dict(live),
        {"es": {"title": "t", "description": "d"}}, dry_run=True)
    for key in ("title", "description", "tags", "categoryId"):
        if body["snippet"].get(key) != live[key]:
            fails.append(f"the videos.update body would have changed {key!r} — "
                         f"that is the metadata-wipe this whole design exists "
                         f"to prevent")
    if body["snippet"].get("defaultLanguage") != "en":
        fails.append('the videos.update body did not carry defaultLanguage="en"')
    if "channelId" in body["snippet"]:
        fails.append("the videos.update body echoed read-only channelId back; "
                     "only the writable properties belong in it")
    if "id" not in body or body["id"] != VID:
        fails.append("the videos.update body has no video id")

    # ---------------------------------------- the description is never mangled
    # A model that reformats a chapter timestamp breaks YouTube's chapter
    # parser; one that "improves" a URL invents a citation. Neither ever
    # reaches the model, and this proves it.
    examined += 1
    desc = ("The answer is 10,935 metres.\n\nChapters\n0:00 Cold open\n"
            "1:19 The best estimate\n\nSources\n"
            "• NOAA Ocean Exploration https://oceanexplorer.noaa.gov/x\n"
            "• GEBCO https://gebco.net/y\n")
    send, keep = localize.split_description(desc)
    for line in send:
        if "http" in line or "•" in line:
            fails.append(f"a URL or source bullet was sent to the model: "
                         f"{line!r}")
        if line.strip().startswith(("0:", "1:")):
            fails.append(f"a chapter TIMESTAMP was sent to the model: {line!r}")
    if "Cold open" not in send:
        fails.append("the chapter LABEL was not sent for translation; a "
                     "non-English viewer would read an English chapter list")
    rebuilt = localize.rebuild_description(desc, keep, ["X"] * len(send))
    for must in ("https://oceanexplorer.noaa.gov/x", "https://gebco.net/y",
                 "0:00 ", "1:19 "):
        if must not in rebuilt:
            fails.append(f"rebuilding the description lost {must!r}")

    # a translation that comes back the wrong length is REFUSED, not patched
    examined += 1
    try:
        localize.parse(json.dumps({"title": "t", "lines": ["a"]}), 3)
        fails.append("localize.parse accepted 1 line where 3 were sent — "
                     "reassembling around that glues a sources block onto a "
                     "sentence")
    except ValueError:
        pass

    # and a title over YouTube's 100 characters is refused rather than sent
    examined += 1
    try:
        localize.parse(json.dumps({"title": "x" * 101, "lines": ["a"]}), 1)
        fails.append("localize.parse accepted a 101-character title; YouTube "
                     "rejects the whole call")
    except ValueError:
        pass

    # ---------------------------------------------- the caption lane's guards
    examined += 1
    cap_src = open(os.path.join(LOOP, "captions_lane.py")).read()
    if "CAPTIONS_INERT" not in cap_src:
        fails.append("loop/captions_lane.py has no CAPTIONS_INERT stop, so a "
                     "run that authenticated and touched nothing would pass "
                     "green on the strength of having read files off disk")
    if "CAPTIONS_SCOPE_MISSING" not in cap_src:
        fails.append("loop/captions_lane.py does not name the force-ssl stop")
    if "force-ssl" not in cap_src:
        fails.append("loop/captions_lane.py does not name the scope it needs")

    examined += 1
    if captions_lane.LANGUAGE != "en" or ytmeta.DEFAULT_LANGUAGE != "en":
        fails.append("the caption track language and the snippet default "
                     "language must both be exactly 'en'")
    if sorted(localize.LANGUAGES) != sorted(validate.REACH_LANGUAGES):
        fails.append(f"loop/localize.py targets {sorted(localize.LANGUAGES)} "
                     f"but V17 validates {sorted(validate.REACH_LANGUAGES)} — "
                     f"two components each keeping their own list")

    # a zero-cue .srt is refused rather than uploaded
    examined += 1
    empty = os.path.join(tmp, "empty.srt")
    open(empty, "w").write("1\n\n2\n\n")
    import pathlib
    if captions_lane.cue_count(pathlib.Path(empty)) != 0:
        fails.append("cue_count did not report an SRT with no timed cues as "
                     "empty")

    # ------------------------------------------------------- quota accounting
    examined += 1
    if (quota.CAPTION_INSERT, quota.CAPTION_LIST, quota.VIDEO_UPDATE) != \
            (400, 50, 50):
        fails.append("the documented YouTube quota costs changed in "
                     "loop/quota.py without this test being updated")
    if quota.PER_CAPTION != quota.CAPTION_LIST + quota.CAPTION_INSERT:
        fails.append("quota.PER_CAPTION does not equal its parts")

    examined += 1
    # the reserve really holds an upload's worth back before one has run...
    saved = quota._load                                    # noqa: SLF001
    try:
        quota._load = lambda: {"day": "x", "spent": 0, "by_lane": {}}
        if quota.upload_reserve() != quota.PER_VIDEO:
            fails.append("quota.upload_reserve() gave nothing back to the "
                         "upload lane on a day it has not yet run")
        if quota.units_affordable(quota.CAPTION_LIST + quota.CAPTION_INSERT,
                                  99, reserve=quota.upload_reserve()) \
                > (quota.DAILY - quota.HEADROOM - quota.PER_VIDEO) // 450:
            fails.append("the caption lane could spend into the upload lane's "
                         "reserve")
        # ...and stops holding it once the upload has happened
        quota._load = lambda: {"day": "x", "spent": 6800,
                               "by_lane": {"backfill": 6800}}
        if quota.upload_reserve() != 0:
            fails.append("quota.upload_reserve() still held quota back for an "
                         "upload that had already run")
    finally:
        quota._load = saved                                # noqa: SLF001

    # ------------------------------------- LOOP_DRY_RUN refuses credentials
    # Not "skips writes" — REFUSES. A test once uploaded a real video to the
    # live channel because a fallback read .secrets/ anyway.
    #
    # Asserted two ways on purpose. The direct one is the property that
    # matters and it holds whatever state the channel is in. The subprocess
    # one proves the lane as a whole survives it — and it deliberately does
    # NOT insist on OAUTH_MISSING specifically: an earlier version did, and it
    # went red the day the localisation backfill finished, because the lane
    # then legitimately reached LOCALIZATIONS_UP_TO_DATE first. A guard whose
    # green depends on the channel being unfinished is testing the wrong thing.
    examined += 1
    saved_dry = up.DRY_RUN
    try:
        up.DRY_RUN = True
        if up.load_credentials(cfg) is not None:
            fails.append("upload.load_credentials RETURNED a credential under "
                         "LOOP_DRY_RUN — every reach lane would then run fully "
                         "authorised against the live channel")
    finally:
        up.DRY_RUN = saved_dry

    for lane in ("captions_lane.py", "localize.py"):
        examined += 1
        env = dict(os.environ, LOOP_DRY_RUN="1", LOOP_NO_DOTENV="1")
        for k in ("YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN"):
            env.pop(k, None)
        r = subprocess.run([sys.executable, os.path.join(LOOP, lane)],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        out = r.stdout + r.stderr
        if r.returncode == 0:
            fails.append(f"loop/{lane} exited 0 under LOOP_DRY_RUN=1 — a "
                         f"silent skip, the exact defect this loop forbids")
        elif r.returncode != 3:
            fails.append(f"loop/{lane} exited {r.returncode} (a crash) under "
                         f"LOOP_DRY_RUN=1 rather than 3:\n{out[-400:]}")
        if "NAMED STOP" not in out:
            fails.append(f"loop/{lane} stopped under LOOP_DRY_RUN=1 without "
                         f"printing a NAMED STOP banner")
        if "Traceback" in out:
            fails.append(f"loop/{lane} raised under LOOP_DRY_RUN=1:\n"
                         f"{out[-400:]}")

    shutil.rmtree(tmp, ignore_errors=True)

    # ------- V26 + CorruptState: the 2026-09-03 crash, in both directions
    #
    # A rebase conflict wrote git markers into loop/state/quota.json; the next
    # step in the same job read it, died with a bare JSONDecodeError, and the
    # video it therefore failed to localize was reported as a content gap. Two
    # things had to be true for that to hurt, and both are checked here: the
    # corrupt file was invisible until something crashed on it, and the crash
    # named neither the file nor the cause.
    import common                                          # noqa: PLC0415

    examined += 1
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "quota.json")
        with open(bad, "w") as fh:
            fh.write('{\n  "day": "2026-09-03",\n' + "<" * 7
                     + ' HEAD\n  "spent": 9500\n' + "=" * 7 + "\n"
                     '  "spent": 600\n' + ">" * 7 + " origin/main\n}\n")
        try:
            common.read_json(bad)
            fails.append("common.read_json parsed a file full of git conflict "
                         "markers without complaint")
        except common.CorruptState as e:
            if "conflict" not in str(e).lower() or "quota.json" not in str(e):
                fails.append("CorruptState does not name the file and the "
                             "conflict — a stop nobody can act on")
        except Exception as e:                              # noqa: BLE001
            fails.append(f"a conflicted state file raised {type(e).__name__} "
                         f"instead of CorruptState — this is the bare "
                         f"JSONDecodeError that named nothing: {e}")

    examined += 1
    try:
        common.read_json.__call__   # noqa: B018
        if not hasattr(common, "CorruptState"):
            raise AttributeError
    except AttributeError:
        fails.append("common has no CorruptState, so a corrupt state file "
                     "cannot become a named stop")

    # Stage must convert it into a NAMED STOP, not let it surface as a crash.
    examined += 1
    src = open(os.path.join(LOOP, "common.py")).read()
    if "STATE_FILE_CORRUPT" not in src:
        fails.append("loop/common.py Stage does not convert CorruptState into "
                     "a STATE_FILE_CORRUPT named stop; the module docstring "
                     "has always claimed corrupt state exits 3 as a named "
                     "stop, and that would be prose, not behaviour")

    # loop/quota.py must go through the guarded reader, not bare json.loads.
    examined += 1
    qsrc = open(os.path.join(LOOP, "quota.py")).read()
    if "json.loads(STATE.read_text())" in qsrc:
        fails.append("loop/quota.py:_load still calls json.loads directly — "
                     "this is the exact line that crashed the localize lane "
                     "on 2026-09-03 with a traceback naming no file")

    # V26 must SEE the corruption rather than wait for a lane to crash on it.
    examined += 1
    if not validate.v26_state_files_readable().ok:
        fails.append("V26 reports the repo's own loop/state/ as unreadable")

    examined += 1
    real_root = validate.ROOT
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "loop", "state"))
        with open(os.path.join(td, "loop", "state", "quota.json"), "w") as fh:
            fh.write('{\n' + "<" * 7 + ' HEAD\n  "spent": 1\n' + "=" * 7
                     + '\n  "spent": 2\n' + ">" * 7 + " x\n}\n")
        validate.ROOT = pathlib.Path(td)
        try:
            if validate.v26_state_files_readable().ok:
                fails.append("V26 passed a loop/state/ containing a git "
                             "conflict marker — the defect that took the "
                             "reach lane down would ship again unseen")
            # Rule 0: it must HARD-FAIL on an empty loop/state/, never pass
            # an empty loop.
            os.remove(os.path.join(td, "loop", "state", "quota.json"))
            empty = validate.v26_state_files_readable()
            # Not just `not empty.ok`: Result.ok already returns False on
            # examined==0, so leaning on it proves nothing about V26 and
            # silently keeps passing if someone sets r.exempt. Demand the
            # EXPLICIT, named hard-fail, which says what was missing.
            if empty.examined != 0:
                fails.append("V26 counted state files that do not exist")
            if not empty.failures:
                fails.append("V26 examined zero state files without raising "
                             "its own hard-failure — it leaned on Result.ok "
                             "alone, which one `r.exempt = True` would undo. "
                             "A guard that governs nothing must say so.")
            if empty.ok:
                fails.append("V26 passed while examining zero state files")
        finally:
            validate.ROOT = real_root

    if examined == 0:
        fails.append("examined ZERO reach behaviours")
    print(f"inspected {examined} reach behaviour(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the reach lanes catch their own defects and refuse to "
          "write a partial snippet" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
