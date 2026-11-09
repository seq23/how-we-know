"""Whisper Almanac's picture gate and footage: a sleep picture is judged as one.

W45 (9 Nov 2026): How We Know's every-frame documentary gate failed the
Almanac's dimmed sleep render on one frame of bare seabed, so the channel could
never upload. Proves, with stub judges and readers (no network, no model):
  1. How We Know's gate fails a mostly-ambient sleep picture (the defect);
  2. the Almanac's gate (visuals/whisper_frame_check.py) passes it;
  3. the Almanac's gate still fails ONE text frame, ONE near-black frame
     (measured luma, not the model), ONE graphic/CG frame, a subject share
     under the configured minimum, and no model answering is
     FRAME_CHECK_UNAVAILABLE;
  4. How We Know's gate is unchanged: one non-subject frame still fails it
     and its judge still answers (pass, why);
  5. the upload step uses the Almanac's gate;
  6. manifesting lanes (her call 9 Nov 2026): their subject is their calm
     footage set, never deep sea; Money takes the money-luxury set; their
     reel pool is only that set's clips; a manifesting kit rendered without
     its set is refused for upload and goes back in the render queue;
  7. dimming stops at a luma floor, never black.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

from PIL import Image  # noqa: E402

import frame_check as FC  # noqa: E402
import whisper_frame_check as WFC  # noqa: E402
import whisper_lane as WL  # noqa: E402
import whisper_reel as REEL  # noqa: E402
import whisper_upload as WU  # noqa: E402

fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    return None


tmp = Path(tempfile.mkdtemp(prefix="whisper-gate-"))
try:
    def frame(name, rgb):
        p = tmp / f"{name}.jpg"
        Image.new("RGB", (768, 432), rgb).save(p)
        return str(p)

    # A 20-frame sleep picture: 12 show the subject (60%), 8 are dim open water.
    subj = [frame(f"s{i}", (20, 60, 70)) for i in range(12)]
    amb = [frame(f"a{i}", (10, 35, 50)) for i in range(8)]
    black = frame("black", (1, 2, 3))
    si, ai = iter(subj), iter(amb)
    order = [next(ai) if i % 5 in (1, 3) else next(si) for i in range(20)]
    frames = [(1.0 + 20 * i, p) for i, p in enumerate(order)]
    shows = set(subj)
    no_text = lambda paths: {}                                                    # noqa: E731
    CFG = {"subject_share_min": 0.5, "near_black_luma": 6.0}

    def hwk_judge(paths, subject):            # the documentary judge: subject or fail
        return [(p in shows, "subject" if p in shows else "open water, no animal") for p in paths]

    def sleep_judge(paths, subject, graphic=frozenset()):
        return [{"real_footage": True, "graphic_or_text": p in graphic,
                 "subject_visible": p in shows, "why": "x"} for p in paths]

    # 1. the defect: How We Know's gate fails the mostly-ambient sleep video
    e = raises(lambda: FC.check_frames(frames, "isopod", judge=hwk_judge, reader=no_text),
               FC.PictureCheckFailed)
    check("How We Know's gate fails a mostly-ambient sleep picture", e is not None and len(e.failures) == 8)

    # 2. the Almanac's gate passes it
    try:
        r = WFC.check_frames(frames, "isopod", judge=sleep_judge, reader=no_text, cfg=CFG)
        check("the Almanac gate passes a 60%-subject sleep picture",
              r["frames"] == 20 and r["subject_share"] == 0.6, r)
    except FC.PictureCheckFailed as ex:
        check("the Almanac gate passes a 60%-subject sleep picture", False, str(ex))

    # 3. its hard fails
    one_text = lambda paths: {paths[7]: "SUBSCRIBE"}                              # noqa: E731
    e = raises(lambda: WFC.check_frames(frames, "isopod", judge=sleep_judge, reader=one_text, cfg=CFG),
               FC.PictureCheckFailed)
    check("ONE text frame fails it", e is not None and "text on screen" in str(e), e)

    dark = list(frames)
    dark[4] = (dark[4][0], black)
    e = raises(lambda: WFC.check_frames(dark, "isopod", judge=sleep_judge, reader=no_text, cfg=CFG),
               FC.PictureCheckFailed)
    check("ONE near-black frame fails it (measured luma, the judge passes it)",
          e is not None and "near-black" in str(e) and len(e.failures) == 1, e)

    e = raises(lambda: WFC.check_frames(
        frames, "isopod", judge=lambda p, s: sleep_judge(p, s, graphic={frames[2][1]}),
        reader=no_text, cfg=CFG), FC.PictureCheckFailed)
    check("ONE graphic / CG filler frame fails it", e is not None and "graphic" in str(e), e)

    thin = [(t, amb[0] if i < 12 else p) for i, (t, p) in enumerate(frames)]
    e = raises(lambda: WFC.check_frames(thin, "isopod", judge=sleep_judge, reader=no_text, cfg=CFG),
               FC.PictureCheckFailed)
    check("a subject share under the minimum fails it (SUBJECT_SHARE_LOW)",
          e is not None and "SUBJECT_SHARE_LOW" in str(e), e)

    check("the minimum is read from config/whisper_almanac.json",
          WFC.gate_cfg()["subject_share_min"] == 0.5 and WFC.gate_cfg()["near_black_luma"] > 0)

    e = raises(lambda: WFC.check_frames(frames, "isopod", judge=lambda p, s: None, reader=no_text,
                                        cfg=CFG), FC.FrameCheckUnavailable)
    check("no model answering is FRAME_CHECK_UNAVAILABLE, never a pass", e is not None)

    real_ask = FC.ask_vision
    seen = {}
    FC.ask_vision = lambda fr, prompt, valid=None: seen.update(valid=valid) or None
    WFC.gemini_judge(subj[:2], "isopod")
    v = seen.get("valid")
    check("the judge answers with separate fields (a combined 'pass' is refused)",
          v is not None and not v([{"pass": True}])
          and v([{"real_footage": True, "graphic_or_text": False, "subject_visible": False}]))

    # 4. How We Know's gate is unchanged
    one_off = [(t, p) for t, p in frames if p in shows] + [(999.0, amb[0])]
    e = raises(lambda: FC.check_frames(one_off, "isopod", judge=hwk_judge, reader=no_text),
               FC.PictureCheckFailed)
    check("How We Know: one non-subject frame still fails the render",
          e is not None and len(e.failures) == 1 and e.failures[0][0] == 999.0, e)
    FC.ask_vision = lambda fr, prompt, valid=None: [{"pass": True, "why": "a"}, {"pass": False, "why": "b"}]
    check("How We Know's judge still answers (pass, why)",
          FC.gemini_judge(subj[:2], "isopod") == [(True, "a"), (False, "b")])
    FC.ask_vision = real_ask

    # 5. the upload step runs the Almanac gate
    called = {}
    real_check, real_fc_check = WFC.check, FC.check
    WFC.check = lambda video, subject, *a, **k: called.setdefault("whisper", subject) or {"frames": 1}
    FC.check = lambda video, subject, *a, **k: called.setdefault("hwk", subject) or {"frames": 1}
    WU.subject = (lambda real: (lambda slug, c: "isopod"))(WU.subject)
    try:
        WU.frame_check(Path("x.mp4"), "slug", {})
    finally:
        WFC.check, FC.check = real_check, real_fc_check
    check("whisper_upload.frame_check uses the Almanac gate", called == {"whisper": "isopod"}, called)

    # 6. manifesting footage
    import importlib                                                              # noqa: PLC0415
    importlib.reload(WU)
    C = WL.cfg()
    real_parse = WL.parse
    scripts = {
        "money": {"kind": "affirmations", "meta": {"theme": "billionaire"}, "title": "m",
                  "segments": [{"source": "08-what-creatures-live-in-the-deep-sea"}]},
        "nev": {"kind": "neville", "meta": {}, "title": "n",
                "segments": [{"source": "08-what-creatures-live-in-the-deep-sea"}]},
        "love": {"kind": "affirmations", "meta": {"theme": "love"}, "title": "l", "segments": []},
    }
    WL.parse = lambda path: {**scripts[Path(path).stem], "slug": Path(path).stem}
    try:
        sm, sn = WU.subject("money", C), WU.subject("nev", C)
        deep = ("deep", "isopod", "creature", "jelly", "squid", "sea cucumber", "anglerfish")
        check("Money's frame-check subject is its luxury set, no deep sea",
              WL.footage_set(WL.parse("money.md"), C) == "money-luxury" and "yacht" in sm
              and not any(w in sm.lower() for w in deep), sm)
        check("Neville's frame-check subject is calm night footage, no deep sea",
              WL.footage_set(WL.parse("nev.md"), C) == "calm-night" and "candlelight" in sn
              and not any(w in sn.lower() for w in deep), sn)
        check("the rotating lane takes calm night footage",
              WL.footage_set(WL.parse("love.md"), C) == "calm-night")
        check("a sleep history script keeps its own episode footage",
              WL.footage_set({"kind": "sleep", "meta": {}}, C) is None)
        import shot_list                                                          # noqa: PLC0415
        real_subjects = shot_list.subjects
        shot_list.subjects = lambda slug: []
        scripts["hist"] = {"kind": "sleep", "meta": {}, "title": "h",
                           "segments": [{"source": "08-what-creatures-live-in-the-deep-sea"}]}
        try:
            sh = WU.subject("hist", C)
        finally:
            shot_list.subjects = real_subjects
        check("a sleep source with no shot list still names a subject (never empty)",
              "creatures live in the deep sea" in sh, sh)
    finally:
        WL.parse = real_parse

    assets = ([{"local_file": f"y{i}", "subject": "a yacht at sunset", "calm_set": "money-luxury",
                "seconds": 30.0} for i in range(3)]
              + [{"local_file": f"j{i}", "subject": "gold and jewelry close-ups", "calm_set": "money-luxury",
                  "seconds": 30.0} for i in range(3)]
              + [{"local_file": "short", "subject": "a yacht at sunset", "calm_set": "money-luxury",
                  "seconds": 9.0},
                 {"local_file": "traffic", "post_id": "pixabay:2165", "subject": "a luxury car interior",
                  "calm_set": "money-luxury", "seconds": 30.0},
                 {"local_file": "c0", "subject": "candlelight", "calm_set": "calm-night", "seconds": 30.0},
                 {"local_file": "deep", "subject": "isopod", "title": "isopod", "source": "pixabay"}])
    pool = REEL.pool("calm:money-luxury", assets, C)
    check("the Money reel pool is only money-luxury clips that hold a shot and are not refused, interleaved",
          [a["local_file"] for a in pool] == ["y0", "j0", "y1", "j1", "y2", "j2"],
          [a["local_file"] for a in pool])

    base = {"kind": "affirmations", "lane": "money", "length_basis": "measured",
            "body": {"status": {"selfDeclaredMadeForKids": False}}}
    WL.script_problems = lambda path, others=None, c=None: []
    WL.meta_problems = lambda k, s, c=None: []
    probs_old = WU.lane_problems("m", base, C)
    probs_new = WU.lane_problems("m", {**base, "footage_set": "money-luxury"}, C)
    probs_cross = WU.lane_problems("m", {**base, "footage_set": "calm-night"}, C)
    check("a manifesting kit with no footage set (deep sea) is refused for upload",
          any(p.startswith("WRONG_FOOTAGE_SET") for p in probs_old), probs_old)
    check("a Money kit rendered with the money-luxury set is not refused", probs_new == [], probs_new)
    check("a Money kit rendered with the calm-night set is refused",
          any(p.startswith("WRONG_FOOTAGE_SET") for p in probs_cross), probs_cross)

    WL.KITS = tmp / "kits"
    WL.WORK = tmp / "work"
    (WL.KITS / "money").mkdir(parents=True)
    (WL.KITS / "money" / "kit.json").write_text(json.dumps({"kind": "affirmations"}))
    WL.video_path("money").parent.mkdir(parents=True, exist_ok=True)
    WL.video_path("money").write_bytes(b"mp4")
    mp = {**scripts["money"], "slug": "money"}
    check("a manifesting render with deep-sea footage goes back in the render queue",
          WL.wrong_footage(mp, C) is True)
    (WL.KITS / "money" / "kit.json").write_text(json.dumps({"footage_set": "money-luxury"}))
    check("...and one rendered with its set does not", WL.wrong_footage(mp, C) is False)

    # 7. dim, never black
    b = lambda f: float(f.split("brightness=")[1].split(":")[0])                  # noqa: E731
    check("a bright cut is dimmed fully", b(REEL.dim_for(200.0)) == -REEL.DIM_MAX)
    check("a dark cut is dimmed only to the floor, never below it",
          b(REEL.dim_for(40.0)) * 255 + 40.0 >= REEL.DIM_FLOOR - 0.5 and b(REEL.dim_for(10.0)) == 0.0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if examined == 0:
    print("FAIL: examined nothing")
    raise SystemExit(1)
if fails:
    print(f"\n{len(fails)} of {examined} failed:")
    for f in fails:
        print("  " + f)
    raise SystemExit(1)
print(f"\nall {examined} checks pass")
