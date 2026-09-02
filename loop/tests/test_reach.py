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

        # ------------------------------------------- V17: no localizations
        examined += 1
        validate.LOCALIZATIONS_STATE = write(tmp, "loc-none.json", {"videos": {}})
        if validate.v17_localizations().ok:
            fails.append("V17 passed a published video with NO localizations — "
                         "it cannot be found by any non-English search")

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
