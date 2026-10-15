"""A live caption track whose local source was rebuilt is REPLACED on YouTube.

WHY (2026-10-15). PR #226 rebuilt sixteen episodes' .srt/.vtt/.timing.json
from measured timing, but loop/captions_lane.py only ever INSERTED: once a
video had a track it was done for good, and a changed sha went down the insert
path, where captions.list found the OLD track and re-recorded it under the NEW
file's hash ("found-on-channel"). Seven public videos (episodes 20, 07, 08, 09,
19, 04, 16) kept captions timed to an older cut while the state file claimed
the re-timed ones were live.

The fix (captions_lane.build_plan / stale_tracks / replace_stale): a track this
lane uploaded is replaced with captions.update (same caption id, no second
English track, no other language touched) when the local file's sha differs
from the sha that was uploaded - but ONLY when the live video's duration
matches the timeline the local track was built for (how-do-self-healing-
materials-work's live cut is the old 517s render while its timing is 709s),
and only within REPLACE_DAILY_CAP units a day, after the upload lanes' reserve.

This test, with the YouTube calls stubbed and quota.json in a temp dir:
  1. a stale track on a duration-matched video is replaced, by its recorded
     caption id, and its recorded sha becomes the local file's;
  2. a duration-mismatched video is NEVER replaced and is named with the reason;
  3. found-on-channel rows, ASR rows and up-to-date rows are never touched;
  4. a moved sha is NOT a pending insert (the old false-green path);
  5. the cap: 6 ready, ample quota -> 4 replaced (1,800 of 2,000 units); a
     second run the same day replaces nothing more; total <= REPLACE_DAILY_CAP;
  6. the reserve: with the upload lanes' reserve unspent and little left,
     nothing is replaced (publishing is never starved);
  7. public videos go first;
  8. a 404 on update records the track as lost so the insert path restores it.

NEGATIVE PROOF (2026-10-15): making stale_tracks() return [] fails cases 1, 5
and 7; dropping the duration check in replace_skip_reason() fails case 2;
setting REPLACE_DAILY_CAP = 10**6 fails case 5. Restored -> green.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import captions_lane as CL                                  # noqa: E402
import quota                                                # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


class St:
    def __init__(self):
        self.notes, self.works = [], []

    def note(self, m):
        self.notes.append(m)

    def work(self, m):
        self.works.append(m)


TMP = Path(tempfile.mkdtemp(prefix="cap-replace-"))
saved = {"dir": CL.CAPTIONS_DIR, "update": CL.update_track,
         "meta": CL.live_meta, "stale": CL.local_track_stale,
         "qstate": quota.STATE}
CL.CAPTIONS_DIR = TMP / "captions"
CL.CAPTIONS_DIR.mkdir()
quota.STATE = TMP / "quota.json"
CL.local_track_stale = lambda slug: None
calls: list[str] = []
missing_ids: set[str] = set()


def fake_update(token, caption_id, srt, timeout=120):
    calls.append(caption_id)
    if caption_id in missing_ids:
        raise urllib.error.HTTPError("u", 404, "captionNotFound", {},
                                     io.BytesIO(b"captionNotFound"))
    return {"id": caption_id}


CL.update_track = fake_update
META: dict[str, dict] = {}
CL.live_meta = lambda token, ids, timeout=30: {i: META[i] for i in ids
                                               if i in META}


def iso(sec: float) -> str:
    s = int(round(sec))
    return f"PT{s // 60}M{s % 60}S"


def episode(slug: str, timeline_s: float, text: str = "new") -> None:
    (CL.CAPTIONS_DIR / f"{slug}.srt").write_text(
        f"1\n00:00:00,000 --> 00:00:02,000\n{text} {slug}\n", encoding="utf-8")
    (CL.CAPTIONS_DIR / f"{slug}.timing.json").write_text(
        json.dumps({"duration_s": timeline_s}), encoding="utf-8")


def world(n_ok: int, extra: bool = True):
    """n_ok stale+matched videos, plus one mismatch, one found, one current."""
    META.clear()
    live, state = [], {"videos": {}, "blocked": {}}
    for i in range(n_ok):
        slug, vid = f"ep-{i:02d}", f"VID{i:02d}"
        episode(slug, 480.0 + i)
        live.append({"slug": slug, "video_id": vid})
        state["videos"][vid] = {"slug": slug, "caption_id": f"CAP{i:02d}",
                                "srt_sha256": "old", "source": "inserted",
                                "track_kind": "standard"}
        META[vid] = {"id": vid, "contentDetails": {"duration": iso(480.0 + i)},
                     "status": {"privacyStatus":
                                "public" if i >= n_ok - 2 else "private"}}
    if extra:
        # the self-healing shape: live cut 517s, local timing 709s
        episode("how-do-self-healing-materials-work", 708.699)
        live.append({"slug": "how-do-self-healing-materials-work",
                     "video_id": "eJSCm5sk5AA"})
        state["videos"]["eJSCm5sk5AA"] = {
            "slug": "how-do-self-healing-materials-work", "caption_id": "CAPSH",
            "srt_sha256": "old", "source": "inserted",
            "track_kind": "standard"}
        META["eJSCm5sk5AA"] = {"id": "eJSCm5sk5AA",
                               "contentDetails": {"duration": "PT8M37S"},
                               "status": {"privacyStatus": "public"}}
        for slug, vid, src in (("found", "VIDF", "found-on-channel"),
                               ("current", "VIDC", "inserted")):
            episode(slug, 400.0)
            live.append({"slug": slug, "video_id": vid})
            state["videos"][vid] = {"slug": slug, "caption_id": f"CAP{vid}",
                                    "srt_sha256": "old", "source": src,
                                    "track_kind": "standard"}
            META[vid] = {"id": vid, "contentDetails": {"duration": iso(400)},
                         "status": {"privacyStatus": "public"}}
        state["videos"]["VIDC"]["srt_sha256"] = CL.sha256(
            CL.CAPTIONS_DIR / "current.srt")
    return live, state


def fresh_quota(spent_by: dict[str, int]) -> None:
    quota.STATE.write_text(json.dumps(
        {"day": quota._today(), "spent": sum(spent_by.values()),  # noqa: SLF001
         "by_lane": spent_by}))


try:
    # ---------------------------------------------------- 1-3, 5, 7
    # Upload lanes have run today (both reserves stand down), 7,000 left.
    fresh_quota({"cloud-upload": 1700, "shorts": 900})
    live, state = world(6)
    plan, gaps = CL.build_plan(live, state)
    check(not gaps, f"fixture gaps: {gaps}")

    # 4. a moved sha must NOT look like a missing track
    pending = [p for p in plan if not p["already"]]
    check(not pending, "4 a re-timed .srt on a video that HAS a track was "
                       f"planned as a fresh insert: {[p['slug'] for p in pending]}"
                       " - the insert path re-records the OLD live track")

    st = St()
    calls.clear()
    out = CL.replace_stale("tok", plan, state, st)
    check(len(out["replaced"]) == 4,
          f"5 cap: 6 ready + ample quota should replace exactly 4 "
          f"(2000 // {quota.CAPTION_UPDATE}), replaced {out['replaced']}")
    check(set(calls) <= {f"CAP{i:02d}" for i in range(6)},
          f"3 a non-stale / found-on-channel / mismatched track was updated: "
          f"{calls}")
    check("CAPSH" not in calls,
          "2 the duration-mismatched video (live 517s, track 709s) was "
          "REPLACED - its captions are now mis-timed the other way")
    check("how-do-self-healing-materials-work" in out["skipped"]
          and "517s" in out["skipped"].get(
              "how-do-self-healing-materials-work", ""),
          f"2 the mismatched video is not named with its reason: "
          f"{out['skipped']}")
    check("CAPVIDF" not in calls and "CAPVIDC" not in calls,
          "3 a found-on-channel or up-to-date track was overwritten")
    check(calls[:2] == ["CAP04", "CAP05"],
          f"7 public videos must be replaced first; order was {calls}")
    vid_of = {r["slug"]: r["video_id"] for r in live}
    cap_of = {v: r["caption_id"] for v, r in state["videos"].items()}
    for slug in out["replaced"]:
        rec = state["videos"][vid_of[slug]]
        check(rec["srt_sha256"] == CL.sha256(CL.CAPTIONS_DIR / f"{slug}.srt")
              and rec["source"] == "replaced"
              and rec["caption_id"] == cap_of[vid_of[slug]],
              f"1 {slug}: replaced but the record does not carry the new sha "
              f"under the SAME caption id: {rec}")
    booked = quota._load()["by_lane"].get(CL.REPLACE_LANE, 0)  # noqa: SLF001
    check(booked == 4 * quota.CAPTION_UPDATE <= CL.REPLACE_DAILY_CAP,
          f"5 replacement spend booked {booked}, want "
          f"{4 * quota.CAPTION_UPDATE} and <= {CL.REPLACE_DAILY_CAP}")
    check(len(out["deferred"]) == 2,
          f"5 the 2 over the cap must be carried, got {out['deferred']}")

    # 5b. same day, second run: the cap already spent -> nothing more
    calls.clear()
    plan, _ = CL.build_plan(live, state)
    out2 = CL.replace_stale("tok", plan, state, St())
    check(not calls and not out2["replaced"],
          f"5 a second run the same day went past the daily cap: {calls}")
    check(len(out2["deferred"]) == 2, "5 leftovers not carried on run 2")

    # 5c. next day: the leftovers finish
    fresh_quota({"cloud-upload": 1700, "shorts": 900})
    calls.clear()
    out3 = CL.replace_stale("tok", plan, state, St())
    check(sorted(out3["replaced"]) == ["ep-02", "ep-03"],
          f"5 next day should finish the 2 carried, got {out3['replaced']}")
    left = [p["slug"] for p in
            CL.stale_tracks(CL.build_plan(live, state)[0], state)]
    check(left == ["how-do-self-healing-materials-work"],
          f"1 stale live track(s) never replaced: {left}")

    # ---------------------------------------------------- 6 the reserve
    # No upload lane has spent: deferrable_reserve() holds 1,700 + 3,400.
    fresh_quota({"captions": 5000})
    live, state = world(3, extra=False)
    calls.clear()
    out = CL.replace_stale("tok", CL.build_plan(live, state)[0], state, St())
    check(not calls,
          f"6 replacements spent into the upload lanes' reserve: {calls}")
    check(len(out["deferred"]) == 3, "6 reserve-deferred tracks not carried")

    # ---------------------------------------------------- 8 a 404
    fresh_quota({"cloud-upload": 1700, "shorts": 900})
    live, state = world(1, extra=False)
    missing_ids.add("CAP00")
    CL.replace_stale("tok", CL.build_plan(live, state)[0], state, St())
    missing_ids.clear()
    rec = state["videos"]["VID00"]
    check("caption_id" not in rec and rec.get("lost_at"),
          f"8 a 404 on update did not record the track as lost: {rec}")
    check(not CL.build_plan(live, state)[0][0]["already"],
          "8 a lost track is not handed back to the insert path")

    # ---------------------------------------------------- the duration parse
    check(CL.iso_seconds("PT8M37S") == 517 and CL.iso_seconds("PT1H2S") == 3602
          and CL.iso_seconds("") is None,
          "iso_seconds mis-parses YouTube durations")

    # ---------------------------------------------------- run() wires it in
    src = (LOOP / "captions_lane.py").read_text(encoding="utf-8")
    run_src = src[src.index("def run("):]
    check("replace_stale(" in run_src,
          "run() never calls replace_stale - the replacement is inert")
    check(run_src.index("insert_track(") < run_src.index("replace_stale("),
          "replacements must run AFTER the inserts")
finally:
    CL.CAPTIONS_DIR = saved["dir"]
    CL.update_track = saved["update"]
    CL.live_meta = saved["meta"]
    CL.local_track_stale = saved["stale"]
    quota.STATE = saved["qstate"]

if examined == 0:
    print("FAIL test_caption_live_tracks_replaced: examined nothing")
    sys.exit(1)
if fails:
    print(f"FAIL test_caption_live_tracks_replaced ({len(fails)}/{examined}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"PASS test_caption_live_tracks_replaced ({examined} checks)")
