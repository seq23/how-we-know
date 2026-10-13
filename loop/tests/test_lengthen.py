"""The ten-minute splice: arithmetic, boundary, tail gates, state transitions.

Owner decisions 12-13 Oct 2026 (repackage job 1) and her question "do u have
to re-render the entire videos, can't u just add something on the end".
No live model call and no ffmpeg here: the model, assemble.py and every
ffmpeg/ffprobe call are fixtured; every path is a scratch directory.

  1. arithmetic: an 8-minute body budgets into 10:30-11:30 at >= MIN_WORDS;
     frames_through() reproduces visuals/assemble.py's frame allocation
     exactly, and FPS matches visuals/design.py;
  2. boundary with a fixtured sidecar: the title-card beat's first frame;
     refused (SpliceUnusable) for a beat-count mismatch, an audio_s mismatch,
     estimate timing, narration that is not the plan's, no title card;
  3. splice_script replaces only the cold open and appends the tail;
  4. tail gates: restating the Direct-answer lock fails (>= 30%), no
     next-episode pointer fails, a real tail passes; draft() feeds rejections
     back and retries to a passing pair;
  5. state: remap_audio moves body wavs to their new indices and retires the
     old opening's (nothing deleted); stage_splice waits for narration,
     refuses a render that is not the measured one, refuses a body that is not
     packet-identical, refuses a stitched file under the floor, and on success
     marks `spliced`, records the old render in superseded_renders.json and
     clears render_hold.json;
  6. forward only: a published slug is refused (published_refused) before any
     model call and is never listed as short;
  7. V49 passes on the real repo and fails on a spliced row with no
     superseded record.

NEGATIVE PROOF (run once, 2026-10-13): change frames_through()'s round() to
int() -> case 1 fails against the assemble allocation; restore -> green.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import durations                                              # noqa: E402
import lengthen as L                                          # noqa: E402

fails: list[str] = []
examined = 0
TMP = Path(tempfile.mkdtemp(prefix="lengthen-"))


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


WPM = 144.58
# ------------------------------------------------------------ 1. arithmetic
for body_s in (420.0, 480.0, 540.0):
    b = L.budget(body_s, 45, wpm=WPM)
    total_words = 45 + round(body_s * WPM / 60) + b["tail_words"]
    check(b["in_band"] and L.TARGET_MIN <= b["total_min"] <= L.TARGET_MAX,
          f"body {body_s}s budgets to {b['total_min']} min, outside the band")
    check(total_words >= L.MIN_WORDS, f"body {body_s}s: {total_words} words < MIN_WORDS")
check(L.MIN_WORDS >= math.ceil(L.TARGET_MIN * WPM) - 1,
      f"MIN_WORDS {L.MIN_WORDS} does not cover {L.TARGET_MIN} min at {WPM} wpm")
check(L.needs_lengthening("x", measured_s=9.9 * 60) and
      not L.needs_lengthening("x", measured_s=10.0 * 60),
      "needs_lengthening does not split at the 10:00 floor")
secs = [8.624, 5.477, 2.768, 5.648, 7.1, 3.33, 9.01]
alloc, emitted = [], 0
for i in range(len(secs)):
    due = sum(secs[:i + 1])
    want = math.ceil(due * 30) if i == len(secs) - 1 else int(round(due * 30))
    alloc.append(max(1, want - emitted))
    emitted += alloc[-1]
check(all(L.frames_through(secs, k) == sum(alloc[:k]) for k in range(len(secs) + 1)),
      "frames_through() disagrees with assemble.py's whole-episode allocation")
check("W, H, FPS = 1920, 1080, 30" in (ROOT / "visuals" / "design.py").read_text()
      and L.FPS == 30, "lengthen.FPS does not match visuals/design.py")

# -------------------------------------------------------------- 2. boundary
heads = ["Cold open", "Cold open", "Title card", "Body", "Body", "Body", "Close"]
plan = [{"heading": h, "narration": f"beat {i}", "segment": "text_beat"}
        for i, h in enumerate(heads)]
beats = [{"i": i, "narration": f"beat {i}", "seconds": s} for i, s in enumerate(secs)]
side = {"beats": len(plan), "audio_s": round(sum(secs), 2), "timing": "audio"}
bd = L.boundary(plan, beats, side)
check(bd["k"] == 2 and bd["boundary_frames"] == alloc[0] + alloc[1]
      and bd["total_frames"] == sum(alloc),
      f"the title-card boundary is not assemble's frame: {bd}")
for label, kw in (("beat-count mismatch", dict(side={**side, "beats": 6})),
                  ("audio_s mismatch", dict(side={**side, "audio_s": side["audio_s"] + 1})),
                  ("estimate timing", dict(side={**side, "timing": "estimate"})),
                  ("no sidecar", dict(side=None)),
                  ("narration differs", dict(beats=[dict(b, narration="other") if b["i"] == 4 else b
                                                    for b in beats])),
                  ("no title card", dict(plan=[dict(p, heading="Body") for p in plan]))):
    args = {"plan": plan, "beats": beats, "side": side, **kw}
    try:
        L.boundary(args["plan"], args["beats"], args["side"])
        check(False, f"boundary accepted a {label}")
    except L.SpliceUnusable:
        check(True, "")

# --------------------------------------------------------- 3. splice_script
SCRIPT = """# What is the midnight zone?

**Domain:** deep-sea-ocean-science

## YouTube title

No sunlight reaches below 1,000 meters

## Direct-answer lock

The midnight zone is the ocean layer from 1,000 to 4,000 meters where no sunlight reaches.

## Narration

### Cold open

Old opening sentence. The midnight zone is the ocean layer from 1,000 to 4,000 meters.

### Title card

What is the midnight zone?

### Light runs out

Body paragraph one.

### What to notice in the edit

Body close.

## Sources

- NOAA Ocean Exploration — https://oceanexplorer.noaa.gov/
"""
TAIL = """### What the evidence does not settle

Nobody has mapped how many species hunt below the thermocline, and the honest
census number is a shrug with error bars. Researchers counted lanternfish
schools by sonar and found the echoes ten times larger than the nets suggested,
which is the kind of rounding error biology apologises for. Next time: the fish
that makes its own light. Stay curious - it is cheaper than a submarine."""
NEW_OPEN = ("The last photon of daylight dies long before the seafloor. The "
            "midnight zone is the ocean layer from 1,000 to 4,000 meters where "
            "no sunlight reaches.")
merged = L.splice_script(SCRIPT, NEW_OPEN,
                         TAIL, ["https://www.noaa.gov/"])
check("Old opening sentence" not in merged and "photon of daylight dies" in merged
      and merged.index("Body close.") < merged.index("What the evidence does not settle")
      < merged.index("## Sources") and "https://www.noaa.gov/" in merged
      and "### Title card\n\nWhat is the midnight zone?" in merged
      and "**Lengthened:**" in merged,
      "splice_script changed more than the cold open and the tail")

# ------------------------------------------------------------- 4. tail gates
check(not L.tail_problems(TAIL, SCRIPT), f"a real tail failed: {L.tail_problems(TAIL, SCRIPT)}")
restate = ("### Recap\n\nThe midnight zone is the ocean layer from 1,000 to 4,000 "
           "meters where no sunlight reaches. The ocean layer has no sunlight. "
           "Next time: the trench.")
check(any("restates" in p or "restatement" in p for p in L.tail_problems(restate, SCRIPT)),
      "a tail that restates the Direct-answer lock passed")
nopointer = TAIL.replace("Next time: the fish\nthat makes its own light. ", "")
check("Next time" not in nopointer, "fixture: the pointer was not removed")
check(any("next episode" in p for p in L.tail_problems(nopointer, SCRIPT)),
      "a tail with no next-episode pointer passed")
check(any("budget" in p for p in L.tail_problems(TAIL, SCRIPT, want_words=400)),
      "a tail far under its word budget passed")
check("warmth" in L.TAIL_RULES.lower() and "joke" in L.TAIL_RULES
      and "Next time" in (L.__doc__ or ""), "the tail house rule or its examples are missing")

calls = []
replies = iter([
    f"OPENING:\n{NEW_OPEN}\nTAIL:\n{restate}\nSOURCES:\n",
    f"OPENING:\n{NEW_OPEN}\nTAIL:\n{TAIL}\nSOURCES:\n"])


def fake_ask(messages):
    calls.append(messages)
    return next(replies), "fixture/free", "stop"


L._ask = fake_ask                                             # noqa: SLF001
L.budget = (lambda body_s, open_words, wpm=None, _b=L.budget:  # tail ~70 words
            {**_b(body_s, open_words, wpm), "tail_words": 70})
r = L.draft("fixture-slug", SCRIPT, body_s=480.0, check_urls=False)
check("{{uncertain: VALUE | UNIT | RANGE" in calls[0][0]["content"],
      "the extension prompt does not carry the author's directive menu")
check(r["applied"] and r["attempts"] == 2 and "Rejected" in calls[1][-1]["content"],
      f"draft() did not feed the rejection back and retry to a pass: {r.get('problems')}")

# ------------------------------------------------------------------ 5. state
for name in ("SCRIPTS", "PLANS", "AUDIO", "RENDERS", "CAPTIONS"):
    d = TMP / name.lower()
    d.mkdir()
    setattr(L, name, d)
L.STATE, L.SUPERSEDED, L.HOLD = TMP / "lengthen.json", TMP / "sup.json", TMP / "hold.json"
L.THUMB_OUT = str(TMP / "thumbs")
durations.DURATIONS = TMP / "durations.json"
slug = "fixture-slug"
adir = L.AUDIO / slug
adir.mkdir()
for i in range(7):                       # old plan: 2 opening, 5 body beats
    (adir / f"{i:04d}.wav").write_text(f"old {i}")
rm = L.remap_audio(slug, old_k=2, new_k=3, body_n=5)
check(rm["moved"] == 5 and sorted(rm["retired"]) == ["0000.wav", "0001.wav"]
      and (adir / "0003.wav").read_text() == "old 2"
      and (adir / "0007.wav").read_text() == "old 6"
      and not (adir / "0000.wav").exists()
      and (adir / "superseded" / "pre-lengthen-0000.wav").exists(),
      f"remap_audio did not move the body to its new indices: {rm}")

render = L.RENDERS / f"{slug}-final.mp4"
render.write_bytes(b"old render bytes")
(L.SCRIPTS / f"{slug}.md").write_text(merged)
new_plan = [{"heading": "Cold open", "narration": f"n{i}"} for i in range(3)] + \
           [{"heading": "Body", "narration": f"b{i}"} for i in range(5)] + \
           [{"heading": "Tail", "narration": f"t{i}"} for i in range(2)]
(L.PLANS / f"{slug}.json").write_text(json.dumps(new_plan))
L.HOLD.write_text(json.dumps({"held": {slug: {"why": "9.2 min"}}}))
doc = {"episodes": {slug: {"status": "scripted", "mode": "splice", "new_k": 3,
                           "body_beats": 5, "boundary_frames": 400,
                           "old_render_sha256": L.sha256(render)}}}
r = L.stage_splice(slug, doc=doc)
check(r["status"] == "waiting_narration", f"spliced before the new beats were voiced: {r}")
for i in (0, 1, 2, 8, 9):
    (adir / f"{i:04d}.wav").write_text("new")

ran = []


def fake_assemble(plan_path, out, audio_dir):
    ran.append((json.loads(Path(plan_path).read_text()), sorted(os.listdir(audio_dir))))
    Path(out).write_bytes(b"segment")
    return {}


def fake_run(cmd):
    if cmd[0] == "ffmpeg" and "concat" in cmd:
        Path(cmd[-1]).write_bytes(b"stitched")
    elif cmd[0] == "ffmpeg":
        Path(cmd[-1]).write_bytes(b"body")
    return None


md5 = {"render": [f"r{i}" for i in range(1000)]}
L.ASSEMBLE, L.RUN = fake_assemble, fake_run
L._video_md5s = lambda p: {"open.mp4": ["o"] * 90, "body.mp4": md5["render"][400:],  # noqa: SLF001
                           f"{slug}-final.mp4": (md5["render"] if Path(p) == render
                                                 else ["o"] * 90 + md5["render"][400:] + ["t"] * 60)
                           }.get(Path(p).name, ["t"] * 60)
L._ffprobe_s = lambda p: 655.0                                # noqa: SLF001
render.write_bytes(b"tampered")
r = L.stage_splice(slug, doc=doc)
check(r["status"] == "refused" and "not the one" in r["why"],
      f"spliced onto a render that is not the measured one: {r}")
render.write_bytes(b"old render bytes")
good_md5 = L._video_md5s                                      # noqa: SLF001
L._video_md5s = lambda p: (["x"] * 5 if Path(p).name == "body.mp4" else good_md5(p))  # noqa: SLF001
r = L.stage_splice(slug, doc=doc)
check(r["status"] == "refused" and "byte-identical" in r["why"],
      f"a body that is not packet-identical was accepted: {r}")
L._video_md5s = good_md5                                      # noqa: SLF001
L._ffprobe_s = lambda p: 9.5 * 60                             # noqa: SLF001
r = L.stage_splice(slug, doc=doc)
check(r["status"] == "refused" and "floor" in r["why"],
      f"a stitched render under the floor was accepted: {r}")
L._ffprobe_s = lambda p: 655.0                                # noqa: SLF001
ran.clear()
r = L.stage_splice(slug, doc=doc)
rec = doc["episodes"][slug]
sup = json.loads(L.SUPERSEDED.read_text()) if L.SUPERSEDED.exists() else {}
check(r["status"] == "spliced" and rec["status"] == "spliced"
      and rec["new_seconds"] == 655.0 and render.read_bytes() == b"stitched"
      and sup.get(slug, {}).get("sha256") == rec["old_render_sha256"]
      and slug not in json.loads(L.HOLD.read_text())["held"]
      and (L.RENDERS / "superseded-short" / f"{slug}-final.pre-lengthen.mp4").exists()
      and json.loads(durations.DURATIONS.read_text())["episodes"][slug]["seconds"] == 655.0,
      f"a successful splice did not record its books: {r} / {rec}")
check(len(ran) == 2 and [p["narration"] for p in ran[0][0]] == ["n0", "n1", "n2"]
      and [p["narration"] for p in ran[1][0]] == ["t0", "t1"]
      and ran[1][1] == ["0000.wav", "0001.wav"],
      f"only the opening and the tail were rendered, each with its own wavs: {ran}")
# FORWARD ONLY (owner, 13 Oct 2026): a published slug is refused before any
# model call, whatever its length.
import ledger                                                 # noqa: E402
_saved_led = ledger.LEDGER
ledger.LEDGER = TMP / "ledger.json"
ledger.LEDGER.write_text(json.dumps({"published": [{"slug": slug, "video_id": "V"}],
                                     "queued": []}))
L._ask = lambda m: (_ for _ in ()).throw(AssertionError("model called"))  # noqa: SLF001
r = L.stage_script(slug)
check(r["status"] == "published_refused", f"a published episode was extended: {r}")
check(slug not in L._short_slugs(), "a published slug was listed as short")  # noqa: SLF001
ledger.LEDGER = _saved_led
check(not hasattr(L, "ready_for_reupload"), "the re-upload hand-off still exists")
L.save(doc, L.STATE)                     # the spliced books V49 reads below
# ------------------------------------------- 5b. the hook rule on the queue
# Owner, 13 Oct 2026 (job 2): every QUEUED script opens stake-then-payoff.
# One at the floor but failing the hook is RE-OPENED (new cold open only);
# one under the floor is EXTENDED (new hook + tail). In the cloud the script
# is written and the Mac binds it; the upload lanes hold it until then.
import hashlib                                                # noqa: E402
BAD = SCRIPT.replace("Old opening sentence. ", "Scientists have long wondered "
                     "what lies in the dark water far below the waves where "
                     "sunlight fades and strange animals live in the cold. ")
check(L.needs_reopen(BAD) and not L.needs_reopen(SCRIPT),
      "fixture: the hook rule does not separate the two openings")
saved_state, saved_measured = L.STATE, L._measured_s          # noqa: SLF001
L.STATE = TMP / "lengthen-hook.json"
L.DRAFTS = TMP / "drafts"
L.DRAFTS.mkdir()
L._measured_s = lambda s_: 700.0                              # noqa: SLF001
rslug = "fixture-reopen"
(L.SCRIPTS / f"{rslug}.md").write_text(BAD)
(L.DRAFTS / f"{rslug}.md").write_text(BAD)                    # a carried-over twin
old_plan_r = [{"heading": "Cold open", "narration": "old"},
              {"heading": "Title card", "narration": "t"}]
(L.PLANS / f"{rslug}.json").write_text(json.dumps(old_plan_r))
check(rslug in L.queue_slugs(), f"a hook-failing queued script is not queued for re-open: {L.queue_slugs()}")
check(L.upload_hold(rslug) and "hook rule" in L.upload_hold(rslug),
      f"the upload lanes would ship a script that breaks the hook rule: {L.upload_hold(rslug)}")
asked = []
REOPEN = NEW_OPEN.replace("the seafloor.", "the seafloor, far below the waves.")
L._ask = lambda m: (asked.append(m) or (f"OPENING:\n{REOPEN}\nSOURCES:\n",  # noqa: SLF001
                                         "fixture/free", "stop"))
r = L.stage_script(rslug, cloud=True, check_urls=False)
new_text = (L.SCRIPTS / f"{rslug}.md").read_text()
st_doc = L.load()
rec = st_doc["episodes"].get(rslug) or {}
check(r["status"] == "scripted" and rec.get("mode") == "pending_bind"
      and rec.get("kind") == "reopen" and "TAIL:" not in asked[0][0]["content"]
      and "OPENING:" in asked[0][0]["content"]
      and "VISUAL DIRECTIVES" in asked[0][0]["content"]
      and "photon of daylight dies" in new_text and "Scientists have long" not in new_text
      and "### Title card\n\nWhat is the midnight zone?" in new_text
      and "What the evidence does not settle" not in new_text
      and "**Reopened:**" in new_text and "**Opening:** stake-then-payoff" in new_text
      and (L.DRAFTS / f"{rslug}.md").read_text() == new_text
      and json.loads((L.PLANS / f"{rslug}.json").read_text()) == old_plan_r
      and rec.get("new_script_sha256") == hashlib.sha256(new_text.encode()).hexdigest(),
      f"a cloud hook-only re-open did not write just the new opening: {r} {rec}")
check(rslug not in L.queue_slugs(), "a pending_bind script is re-opened a second time")
check(L.upload_hold(rslug) and "not yet" in L.upload_hold(rslug),
      f"the old cut of a re-opened script could ship before the Mac re-renders: {L.upload_hold(rslug)}")
# THE MAC binds it: no sidecar -> full re-render; the old render is recorded
# and moved aside, the stale plan unlinked, nothing deleted.
rrender = L.RENDERS / f"{rslug}-final.mp4"
rrender.write_bytes(b"old cut with the old opening")
old_sha = L.sha256(rrender)
L._plan_for = lambda p: [{"heading": "Cold open", "narration": "new"},  # noqa: SLF001
                         {"heading": "Title card", "narration": "t"}]
(L.SCRIPTS / f"{rslug}.md").write_text(new_text + "edited after the cloud\n")
b = L.bind(rslug, st_doc)
check(b["status"] == "refused" and rrender.exists(),
      f"bind acted on a script that is not the one the cloud wrote: {b}")
(L.SCRIPTS / f"{rslug}.md").write_text(new_text)
b = L.bind(rslug, st_doc)
sup = json.loads(L.SUPERSEDED.read_text())
check(b["status"] == "full_rerender" and st_doc["episodes"][rslug].get("bound_at")
      and not rrender.exists()
      and (L.RENDERS / "superseded-short" / f"{rslug}-final.pre-lengthen.mp4").exists()
      and sup.get(rslug, {}).get("sha256") == old_sha
      and not (L.PLANS / f"{rslug}.json").exists(),
      f"bind did not retire the old cut and plan: {b}")
L.save(st_doc)
check(L.upload_hold(rslug) is None,
      f"a bound, hook-passing script is still held: {L.upload_hold(rslug)}")
# an EXTENSION in the cloud: new hook + tail, still pending_bind
eslug = "fixture-extend"
(L.SCRIPTS / f"{eslug}.md").write_text(SCRIPT)
L._measured_s = lambda s_: None                               # noqa: SLF001
L._ask = lambda m: (f"OPENING:\n{NEW_OPEN}\nTAIL:\n{TAIL}\nSOURCES:\n",  # noqa: SLF001
                    "fixture/free", "stop")
r = L.stage_script(eslug, cloud=True, check_urls=False)
check(r["status"] == "scripted" and r.get("kind") == "extend"
      and "What the evidence does not settle" in (L.SCRIPTS / f"{eslug}.md").read_text(),
      f"a cloud extension did not write the hook and the tail: {r}")
# V49 holds a cloud re-open to the script it wrote
import validate as V                                          # noqa: E402
(L.SCRIPTS / f"{eslug}.md").write_text(SCRIPT)
res = V.v49_lengthen_splice().as_dict()
check(any("pending_bind" in f for f in res["failures"]),
      f"V49 passed a pending_bind episode whose script changed under it: {res['failures']}")
L.STATE, L._measured_s = saved_state, saved_measured          # noqa: SLF001
# the wiring: both upload lanes hold, the Mac binds before it plans, the
# cloud lane re-opens daily and its scripts are committed
import inspect                                                # noqa: E402
import backfill                                               # noqa: E402
_bf = inspect.getsource(backfill.library_pending)
_cu = (LOOP / "cloud_upload.py").read_text()
_bs = (ROOT / "bin" / "batch-session.sh").read_text()
_ls = (ROOT / "bin" / "loop-stage.sh").read_text()
_wf = (ROOT / ".github" / "workflows" / "loop-repackage.yml").read_text()
_prep = _bs.split("phase_prepare() {", 1)[1]
check("lengthen.upload_hold(slug)" in _bf
      and _bf.index("upload_hold") < _bf.index("found = assets(slug)"),
      "backfill.library_pending does not hold a hook-failing episode before locating it")
check('"HOOK_REOPEN_PENDING"' in _cu and "lengthen.upload_hold(s)" in _cu,
      "the cloud upload lane does not name the hook hold")
check("loop/lengthen.py bind" in _prep
      and _prep.index("loop/lengthen.py bind") < _prep.index("build any missing shot plan"),
      "the Mac does not bind cloud re-opens before it plans and narrates")
check('"$STAGE" = "queue-reopen"' in _ls
      and "git add scripts" in _ls.split('"$STAGE" = "queue-reopen"', 1)[1][:200],
      "loop-stage.sh does not commit the scripts the queue-reopen stage writes")
check("bin/loop-stage.sh queue-reopen loop/queue_reopen.py $ARGS" in _wf,
      "loop-repackage does not run the cloud re-open")


# --------------------------------------------------------------------- 6. V49
import validate as V                                          # noqa: E402
# The REAL repo: every path this module reads goes back to the real tree for
# this one call (a pending_bind record is checked against the real script -
# with SCRIPTS still pointing at the scratch dir it read as a mismatch, the
# day the first cloud re-open landed).
_fixture_paths = {n: getattr(L, n) for n in ("SCRIPTS", "DRAFTS", "PLANS", "AUDIO",
                                              "RENDERS", "CAPTIONS", "STATE")}
L.SCRIPTS, L.DRAFTS, L.PLANS = ROOT / "scripts", LOOP / "drafts", ROOT / "plans"
L.AUDIO, L.RENDERS, L.CAPTIONS = ROOT / "audio", ROOT / "renders", ROOT / "captions"
L.STATE = LOOP / "state" / "lengthen.json"
L._measured_s = saved_measured                                # noqa: SLF001
res = V.v49_lengthen_splice().as_dict()
check(not res["failures"], f"V49 fails on the real repo: {res['failures']}")
for _n, _v in _fixture_paths.items():
    setattr(L, _n, _v)
L.STATE = TMP / "lengthen.json"
saved = V.ROOT
fake_root = TMP / "root"
(fake_root / "loop" / "state").mkdir(parents=True)
(fake_root / "loop" / "state" / "superseded_renders.json").write_text("{}")
(fake_root / "loop" / "state" / "render_hold.json").write_text(json.dumps({"held": {}}))
V.ROOT = fake_root
try:
    res = V.v49_lengthen_splice().as_dict()
    check(any("superseded" in f for f in res["failures"]),
          f"V49 passed a spliced episode with no superseded record: {res['failures']}")
finally:
    V.ROOT = saved

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
