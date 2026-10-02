"""Build the caption track an episode is missing, wherever the lane is running.

    .venv/bin/python loop/captions_build.py            # heal everything queued
    .venv/bin/python loop/captions_build.py --slug how-strong-is-graphene
    .venv/bin/python loop/captions_build.py --dry-run

WHY THIS EXISTS
---------------
On 2026-09-08 run 34236877023 (`loop · daily 09:00 CT · upload from R2`) exited
3 with

    REFUSE how-strong-is-graphene: captions/how-strong-is-graphene.srt does not exist
    NAMED STOP [CAPTIONS_NOT_READY] stage=cloud-upload week=2026-W37
    unblock: ... python visuals/captions.py <slug>   [on the Mac]

The refusal was right — an episode uploaded without an `.srt` can never be
captioned, because `captions.insert` needs a file and the file is derived from
audio the cloud does not have. What was wrong is that a lane asked the owner to
run a command. A derived artifact that a machine can rebuild is not a reason to
page a human.

ROOT CAUSE, CONFIRMED
---------------------
`bin/batch-session.sh` — the one command the owner runs — narrates, renders,
thumbnails, validates and pushes to R2. It never runs `visuals/captions.py`,
and it commits nothing. `bin/make-captions.sh` existed the whole time as a
SEPARATE manual command. So every episode produced after the original sixteen
reached the R2 shelf with no caption track and no way for the cloud to make
one, and the upload gate then refused it forever. Not a missing capability: a
missing wire between two stages that both already existed.

WHY NOT ASR ON THE R2 RENDER
----------------------------
The shelved render DOES carry the narration (confirmed by ffprobe on
`renders/how-strong-is-graphene-final.mp4`: one aac mono 48 kHz stream), so
transcribing it in CI is possible. It is still the wrong tool:

  * the caption TEXT is not unknown. It is `plan[i]["narration"]`, committed in
    `plans/<slug>.json` and cross-checked against the script's own `##
    Narration` block. ASR would REPLACE known-exact text with a guess, on a
    channel whose first rule is that nothing on screen is unsourced;
  * the only datum that was ever missing is per-beat TIMING — a few dozen
    floats — and a transcript recovers that less accurately than the wav
    lengths themselves already do;
  * it would add a model download and minutes of CPU to a daily lane.

So the timings are persisted instead. `visuals/captions.py:record_durations()`
writes each measured wav duration into `audio/<slug>/beats.json`, which git
already tracks (`.gitignore` excludes `audio/**/*.wav` and nothing else). Once
those numbers are committed, the caption track is a pure function of the
repository and THIS lane can rebuild it anywhere — on the Mac, on a runner,
inside the upload lane a second before the gate that used to refuse.

WHAT IT REFUSES TO DO
---------------------
Build a caption track from the planner's word-count ESTIMATE. That would put
cues on screen at times the voice does not speak, and it would satisfy the
upload gate while doing it — a green light bought by weakening the check. An
episode with no measured timing anywhere is the one case this lane cannot heal,
and it says so by name.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import batch_queue                                # noqa: E402
import captions_lane                              # noqa: E402
from common import Stage, week_id                 # noqa: E402

LANE = "captions-build"

# The files one healed episode produces. Committed together: a .srt whose
# .timing.json did not land is a track nothing can audit.
def artifacts(slug: str) -> list[Path]:
    return [
        ROOT / "captions" / f"{slug}.srt",
        ROOT / "captions" / f"{slug}.vtt",
        ROOT / "captions" / f"{slug}.chapters.txt",
        ROOT / "captions" / f"{slug}.timing.json",
        ROOT / "captions" / f"{slug}.chapters.handwritten.txt",
        ROOT / "audio" / slug / "beats.json",
        ROOT / "scripts" / f"{slug}.md",
    ]


def _cap():
    """visuals/captions.py, imported late.

    It pulls in `planner` and `voice/script_text`, and on a runner that import
    is worth paying only when there is something to build. Importing it at
    module scope would also make `loop/cloud_upload.py` — which imports this
    file unconditionally — fail at import time on any machine missing one of
    those, turning a caption gap into a crash in an unrelated lane.
    """
    import captions as CAP                         # noqa: PLC0415
    return CAP


# --------------------------------------------------------------- selection

def timing_source(slug: str) -> tuple[str, int, int]:
    """(source, measured_beats, total_beats) for one slug, without building.

    `source` is `visuals/captions.py:beat_durations()`'s verdict: "audio" (wavs
    are here), "recorded" (durations committed in beats.json), "partial", or
    "estimate". Only the first two may produce a track.
    """
    CAP = _cap()
    try:
        plan, _ = CAP.load_plan(slug)
    except (SystemExit, FileNotFoundError) as e:
        # No script, no plan, or a 0-beat plan: a verdict about THIS slug,
        # never a crash of the stage. load_plan() names a missing script as a
        # SystemExit now; FileNotFoundError stays caught because the planner
        # does its own open() calls and one slug's missing file must not cost
        # every other episode its caption track and the night its Shorts.
        return (f"unplannable: {e}", 0, 0)
    _, source, measured = CAP.beat_durations(slug, plan)
    return (source, measured, len(plan))


def buildable(slugs) -> tuple[list[str], list[tuple[str, str]]]:
    """Split `slugs` into (can be captioned now, cannot and why).

    Only slugs that are ACTUALLY missing a usable track are considered, and
    "usable" is `captions_lane.uncaptioned()` — the one rule the upload gate
    and the caption upload lane already share. A third opinion about what
    counts as captioned is exactly the defect that let three episodes air
    without a track.
    """
    missing = dict(captions_lane.uncaptioned(list(slugs)))
    can, cannot = [], []
    for slug in sorted(missing):
        source, measured, total = timing_source(slug)
        if source in ("audio", "recorded"):
            can.append(slug)
        else:
            cannot.append((
                slug,
                f"{missing[slug]}, and its timing source is {source!r} "
                f"({measured}/{total} beats measured). A caption track timed "
                f"off the planner's word-count estimate would put cues on "
                f"screen at times the voice does not speak, so this lane will "
                f"not write one."))
    return can, cannot


# ----------------------------------------------------------------- the work

def build_one(slug: str) -> dict:
    """Write the caption artifacts for one slug. Raises on anything unexpected."""
    CAP = _cap()
    return CAP.process(slug, write_script=True, verbose=False)


def stage_artifacts(slugs) -> list[str]:
    """`git add` exactly the files this lane wrote, by name.

    Explicit pathspecs, never `git add -A`: this runs inside `bin/loop-stage.sh`,
    whose commit step picks up whatever is already in the index, and inside the
    Mac batch, where the working tree routinely holds unrelated untracked media.
    """
    staged = []
    for slug in slugs:
        for p in artifacts(slug):
            if not p.exists():
                continue
            rel = str(p.relative_to(ROOT))
            r = subprocess.run(["git", "add", "--", rel], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode == 0:
                staged.append(rel)
    return staged


def record_durations(slugs, *, note=print) -> list[str]:
    """Persist measured wav durations for every slug whose audio is on THIS
    machine, whether or not it needs captioning.

    Captioning already records them for the episode it builds, but that only
    covers episodes with a missing track. The twenty-five already-captioned
    episodes were narrated before `beats.json` carried a `seconds` field, so
    their manifests hold text and no timing — and the day one of them is re-cut
    the cloud would be back to "only the Mac can caption this". Running here
    makes the invariant total: on the Mac, every narrated episode's committed
    manifest carries the timing its caption track was built from.

    A no-op wherever the wavs are absent, which is every cloud runner.
    """
    CAP = _cap()
    touched = []
    for slug in slugs:
        try:
            plan, _ = CAP.load_plan(slug)
        except (SystemExit, FileNotFoundError):   # unwritten or unplannable
            continue
        idx = CAP.wav_indices(slug, plan)
        if not idx:
            continue
        durs, _, _ = CAP.beat_durations(slug, plan)
        n = CAP.record_durations(slug, durs, idx)
        if n:
            touched.append(slug)
            note(f"recorded {n} measured beat duration(s) into "
                 f"audio/{slug}/beats.json")
    return touched


def heal(slugs, *, note=print, stage_git: bool = True) -> dict:
    """Caption every slug in `slugs` that is missing a track and can have one.

    Returns {"built": [...], "unhealable": [(slug, why)], "staged": [...]}.
    Safe to call with an empty selection — it builds nothing and says so. It is
    the CALLER's job to decide whether having nothing to do is acceptable;
    this function never takes a stop, because `loop/cloud_upload.py` calls it
    mid-lane where a stop would abandon uploads that are perfectly fine.
    """
    can, cannot = buildable(slugs)
    built = []
    for slug in can:
        rec = build_one(slug)
        built.append(slug)
        note(f"captioned {slug}: {rec['cues']} cues, {rec['beats']} beats, "
             f"timing={rec['timing']}, "
             f"{rec['duration_s'] / 60:.1f} min"
             + (f", recorded {rec['durations_recorded']} wav duration(s) into "
                f"audio/{slug}/beats.json" if rec.get("durations_recorded")
                else ""))
    staged = stage_artifacts(built) if (built and stage_git) else []
    return {"built": built, "unhealable": cannot, "staged": staged}


def run(slugs=None, dry_run: bool = False) -> int:
    # WRITTEN rows only. The queue carries the Monday lane's unwritten topics
    # too, and an episode with no script has no caption gap this lane can
    # judge - it is not narrated, not rendered, and not the Mac's to caption.
    # Reading the whole queue is what crashed every batch from 2026-09-26.
    selection = list(slugs) if slugs else batch_queue.written_slugs()
    with Stage(LANE, week_id(),
               zero_work_hint="Every queued episode already has a usable "
                              "captions/<slug>.srt. That is the finished "
                              "state, not a fault.") as st:
        # A GUARD THAT EXAMINES ZERO ITEMS MUST HARD-FAIL. An empty publish
        # queue is not "nothing to caption", it is "this lane could not read
        # the queue", and the two look identical from a green tick.
        if not selection:
            st.named_stop(
                "CAPTIONS_BUILD_EXAMINED_NOTHING",
                "no queued slug has a script at scripts/<slug>.md, so this "
                "lane examined zero episodes. It refuses to report a clean "
                "caption shelf it never looked at.",
                detail={"queue_files": [p.name for p in
                                        batch_queue.publish_order_files()],
                        "queued_unwritten": len(batch_queue.queued_slugs())},
                unblock="research/publish_order*.json is missing, empty, or "
                        "holds only unwritten topics (the Monday lane's). "
                        "Restore it: git checkout origin/main -- research/ "
                        "scripts/")
        st.note(f"examined {len(selection)} queued, written episode(s)")

        can, cannot = buildable(selection)
        for slug, why in cannot:
            print(f"  CANNOT BUILD {slug}: {why}")

        if dry_run:
            for slug in can:
                source, measured, total = timing_source(slug)
                st.work(f"would caption {slug} from {source} timing "
                        f"({measured}/{total} beats measured)")
            if not can:
                st.note("DRY RUN — nothing to build.")
        else:
            res = heal(can, note=st.work)
            recorded = record_durations(
                [s for s in selection if s not in can], note=st.work)
            if recorded:
                stage_artifacts(recorded)
            if res["staged"] or recorded:
                st.note(f"staged {len(res['staged'])} caption file(s) and "
                        f"{len(recorded)} manifest(s) for commit")
            can = can or recorded          # recording timing IS work

        if not can:
            if cannot:
                # NOT self-resolving and deliberately so: an episode with no
                # measured timing anywhere is the one caption gap a machine
                # cannot close, and the only honest fix is narration.
                st.named_stop(
                    "CAPTIONS_UNBUILDABLE",
                    f"{len(cannot)} queued episode(s) have no caption track "
                    f"and no measured narration timing to build one from: "
                    f"{', '.join(s for s, _ in cannot)}",
                    detail={"unbuildable": [{"slug": s, "why": w}
                                            for s, w in cannot]},
                    unblock="These episodes have never been narrated, or their "
                            "audio/<slug>/beats.json was never committed. Run "
                            "bin/batch-session.sh on the Mac: it narrates, "
                            "records the measured beat durations into "
                            "beats.json and commits them, after which this lane "
                            "builds the track by itself.")
            st.named_stop(
                "CAPTIONS_UP_TO_DATE",
                f"all {len(selection)} queued episode(s) already carry a usable "
                f"captions/<slug>.srt",
                detail={"examined": len(selection)},
                unblock="Nothing to do. This lane does real work again the "
                        "moment an episode is narrated without a track.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slug", action="append", dest="slugs",
                    help="one slug (repeatable); default is every queued slug")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(slugs=a.slugs, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
