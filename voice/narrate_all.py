#!/usr/bin/env python
"""narrate_all.py - generate per-beat narration for every episode script.

Layout
------
`visuals/assemble.py` is the consumer and it defines the contract:

    wav = os.path.join(audio_dir, f"{i:04d}.wav")   # i = index into plan.json
    if os.path.exists(wav): d = probe(wav)          # AUDIO IS THE AUTHORITY

so the deliverable is **one wav per plan beat**, named `0000.wav`, `0001.wav`,
... inside `audio/<episode-slug>/`. A single episode-length wav would NOT work:
assemble mounts each beat's visual to that beat's measured audio duration, and
it only muxes a narration track at all when
`len(audio_clips) == len(plan)`. A short episode directory therefore yields a
SILENT video, not a mistimed one - so completeness per episode is the gate.

Beat text comes from `visuals/planner.plan()`, whose `parse()` already removes
`{{directive}}` lines before it splits sentences. Directives are visual
instructions and are never spoken. (`voice/script_text.py` also strips them now,
for the whole-file `synth.py` path.)

Resumability and safety
-----------------------
* An exclusive lockfile (atomic `mkdir`) stops a second instance. A lock whose
  pid is gone is reclaimed, so a hard crash does not wedge the pipeline.
* Every beat already on disk and passing the level/duration check is SKIPPED, so
  a crash resumes where it stopped instead of restarting a ~30 hour job.
* A beat that fails is retried with fresh seeds, then recorded and skipped; one
  bad sentence must not stall the other 1,186.

Usage
-----
  narrate_all.py --reference voice/reference_A_clean_cond10.wav
  narrate_all.py --only 18 --reference REF.wav
  narrate_all.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import datetime as _dt
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_OFFLINE", "1")   # weights are cached; never phone home

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "visuals"))

from synth import (  # noqa: E402
    LEXICON, apply_lexicon, chunk_paragraph, high_shelf, match_rms,
    rms_dbfs, trim_silence,
)
# visuals/captions.py owns the manifest's ONE serialization (indent=2 + "\n").
# Until 2026-10-03 this file wrote `indent=1` with no newline, so every batch
# night re-formatted every tracked audio/<slug>/beats.json without changing a
# value, and the batch's own `git pull --rebase` then refused the dirty tree.
from captions import write_beats_manifest  # noqa: E402

SR = 24000

SCRIPTS = ROOT / "scripts"
AUDIO = ROOT / "audio"
LOCK = AUDIO / ".narrate.lock"

# A beat shorter than this, or quieter than this, is not a usable take.
MIN_BEAT_S = 0.35
MIN_RMS_DB = -45.0


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------
def acquire_lock() -> None:
    AUDIO.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            LOCK.mkdir()
            (LOCK / "pid").write_text(str(os.getpid()))
            return
        except FileExistsError:
            pidf = LOCK / "pid"
            try:
                pid = int(pidf.read_text().strip())
                os.kill(pid, 0)          # raises if the holder is gone
                # AND IT MUST STILL BE A NARRATOR. `os.kill(pid, 0)` only says
                # SOMETHING owns that pid. After a reboot the lock file still
                # names the pid of a process that died with the machine, and
                # macOS hands that number out again -- to Spotlight, to a
                # helper, to anything. The check then passes, narration refuses
                # to start, and it refuses again every night until a human
                # deletes the directory by hand: a dead lock wearing the face
                # of a correct named stop.
                cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                     capture_output=True, text=True).stdout
                if "narrate_all.py" not in cmd:
                    raise ProcessLookupError(
                        f"pid {pid} is alive but is not a narrator: "
                        f"{cmd.strip()[:60]}")
            except (OSError, ValueError):
                print(f"reclaiming stale lock {LOCK}", file=sys.stderr)
                try:
                    pidf.unlink(missing_ok=True)
                    LOCK.rmdir()
                except OSError:
                    pass
                continue
            print(f"error: another narration run holds {LOCK} (pid {pid}). "
                  f"Refusing to start a second instance.", file=sys.stderr)
            raise SystemExit(3)
    raise SystemExit(3)


def release_lock() -> None:
    try:
        (LOCK / "pid").unlink(missing_ok=True)
        LOCK.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Audio checks
# ---------------------------------------------------------------------------
def inspect(path: Path):
    """(ok, duration_s, rms_dbfs, peak). A technically valid but SILENT file is
    not ok - that is the listen-equivalent check."""
    try:
        if not path.exists() or path.stat().st_size < 100:
            return False, 0.0, -120.0, 0.0
        x, sr = sf.read(str(path), dtype="float32")
        if x.ndim > 1:
            x = x.mean(1)
        if sr != SR or x.size == 0:
            return False, 0.0, -120.0, 0.0
        dur = len(x) / sr
        r = rms_dbfs(x)
        pk = float(np.abs(x).max())
        ok = dur >= MIN_BEAT_S and r > MIN_RMS_DB and pk > 0.01
        return ok, dur, r, pk
    except Exception:
        return False, 0.0, -120.0, 0.0


# Generation order. Inference here runs at ~0.04x realtime on this 8 GB M2, so
# the whole set is a multi-day job: ORDER IS THE DELIVERABLE. Episode 01 first
# so one finished video exists as early as possible, then the owner's next four
# publishes, then everything else.
# The publish order is research/publish_order.json, ranked by combined_score. The
# owner removed an earlier hand-picked head on 2026-08-31 once the score showed two
# of its members ranked below episodes further down: "why the fuck are we not doing
# the top 4 by score." These are the top four, in order. 01 is already complete and
# approved; 14 was mid-generation when this list changed, so it stays ahead of the
# two new entries rather than throwing away work in progress.
PRIORITY = [
    "01-why-deep-sea-creatures-look-so-weird",
    "14-how-big-is-a-colossal-squid",
    "10-what-is-the-deepest-part-of-the-ocean",
    "05-why-many-deep-sea-creatures-are-red",
    "15-how-do-people-reach-challenger-deep",
    "06-why-some-deep-sea-creatures-are-transparent",
    "18-why-does-black-smoker-water-not-boil",
]

# Killed as saturated - 20/20 competing titles already answer these. ~171 beats
# of pure waste avoided. Pass --no-skip to generate them anyway.
SKIP = {
    "11-what-is-a-dumbo-octopus",
    "12-what-is-a-frilled-shark",
    "17-what-is-a-yeti-crab",
}


def episode_slugs(skip=True):
    slugs = sorted(p.stem for p in SCRIPTS.glob("*.md"))
    if skip:
        slugs = [s for s in slugs if s not in SKIP]
    rank = {s: i for i, s in enumerate(PRIORITY)}
    return sorted(slugs, key=lambda s: (rank.get(s, len(PRIORITY)), s))


def build_plans(only=None, skip=True):
    # plans/<slug>.json when it exists, the script otherwise - see
    # planner.plan_for_audio. The render indexes wavs by plan position, so
    # narrating from a different plan than the one on disk voices beats the
    # assembler can never use (and re-voices them every night).
    import planner
    plans = {}
    for slug in episode_slugs(skip):
        if only and not any(slug.startswith(o) for o in only):
            continue
        plans[slug], _source = planner.plan_for_audio(slug)
    return plans


# ---------------------------------------------------------------------------
def verify(plans, quiet=False):
    """Per-episode duration/level table. Returns (rows, complete_slugs)."""
    rows, complete = [], []
    for slug, plan in plans.items():
        n = len(plan)
        durs, rmss, pks, missing, silent = [], [], [], [], []
        for i in range(n):
            ok, d, r, pk = inspect(AUDIO / slug / f"{i:04d}.wav")
            if not ok:
                (silent if (AUDIO / slug / f"{i:04d}.wav").exists() else missing).append(i)
                continue
            durs.append(d); rmss.append(r); pks.append(pk)
        words = sum(len(b["narration"].split()) for b in plan)
        total = sum(durs)
        wpm = words / (total / 60) if total > 0 else 0.0
        rows.append({
            "episode": slug, "beats": n, "have": len(durs),
            "missing": missing, "bad": silent,
            "words": words, "duration_s": round(total, 1),
            "wpm": round(wpm, 1),
            "rms_mean": round(float(np.mean(rmss)), 1) if rmss else None,
            "rms_spread": round(float(max(rmss) - min(rmss)), 1) if rmss else None,
            "peak": round(float(max(pks)), 3) if pks else None,
        })
        if len(durs) == n:
            complete.append(slug)
    if not quiet:
        print(f"\n{'episode':<52}{'beats':>6}{'have':>6}{'words':>7}"
              f"{'mm:ss':>8}{'wpm':>7}{'rms dB':>8}{'spread':>8}{'peak':>7}")
        for r in rows:
            m, s = divmod(int(r["duration_s"]), 60)
            flag = "" if r["have"] == r["beats"] else "  <-- INCOMPLETE"
            print(f"{r['episode']:<52}{r['beats']:>6}{r['have']:>6}{r['words']:>7}"
                  f"{m:>5}:{s:02d}{r['wpm']:>7.1f}"
                  f"{(r['rms_mean'] if r['rms_mean'] is not None else float('nan')):>8.1f}"
                  f"{(r['rms_spread'] if r['rms_spread'] is not None else float('nan')):>8.1f}"
                  f"{(r['peak'] if r['peak'] is not None else float('nan')):>7.3f}{flag}")
    return rows, complete


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default=None, metavar="HH:MM",
                    help="stop cleanly at this local time, BETWEEN beats. The "
                         "run hands the Mac back in the morning and the next "
                         "night resumes exactly where it stopped, because a "
                         "beat whose wav already exists is skipped.")
    ap.add_argument("--reference", default=str(HERE / "reference_A_clean_cond10.wav"))
    ap.add_argument("--only", nargs="*", default=None,
                    help="episode number/slug prefixes, e.g. --only 18 19")
    ap.add_argument("--target-db", type=float, default=-23.0)
    ap.add_argument("--presence-db", type=float, default=3.5)
    ap.add_argument("--exaggeration", type=float, default=0.4)
    ap.add_argument("--cfg-weight", type=float, default=0.4)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--max-words", type=int, default=45)
    ap.add_argument("--pause-sentence", type=float, default=0.16)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--no-skip", action="store_true",
                    help="also generate the saturated episodes in SKIP")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--report", default=str(AUDIO / "narration_report.json"))
    args = ap.parse_args()

    plans = build_plans(args.only, skip=not args.no_skip)
    # Rule 0: a run that found nothing to do must not exit 0.
    if not plans:
        print("error: no episode scripts matched - refusing to exit 0 having "
              "done nothing.", file=sys.stderr)
        return 2
    total_beats = sum(len(p) for p in plans.values())
    if total_beats == 0:
        print("error: 0 beats planned across all scripts.", file=sys.stderr)
        return 2

    if args.verify_only:
        rows, complete = verify(plans)
        Path(args.report).write_text(json.dumps(
            {"rows": rows, "complete": complete}, indent=2))
        return 0 if len(complete) == len(plans) else 1

    acquire_lock()
    try:
        return run(args, plans, total_beats)
    finally:
        release_lock()


def run(args, plans, total_beats) -> int:
    # Which beats still need work? Decide BEFORE loading a 3 GB model.
    todo = []
    for slug, plan in plans.items():
        (AUDIO / slug).mkdir(parents=True, exist_ok=True)
        # Record the exact beat list this audio was cut against. planner.plan()
        # is deterministic (verified byte-identical to plans/*.json apart from
        # JSON tuple->list), but assembly indexes audio by plan position, so the
        # plan that produced the audio is worth keeping next to it.
        # PRESERVE THE MEASURED DURATIONS. This wrote the manifest fresh from
        # the plan every run, which silently deleted the `seconds` field that
        # visuals/captions.py records and loop/captions_build.py depends on --
        # CONFIRMED 2026-09-08: one batch stripped the timings from all 35
        # episodes at once, and nothing would have reported it, because a
        # caption track is only missed at the moment an episode is uploaded,
        # weeks later. audio/<slug>/beats.json is the ONE file in audio/ that
        # git tracks and it is now load-bearing for the cloud: without those
        # numbers the caption track can only be built on this Mac again.
        #
        # A duration is kept only when the wav it measured is still on disk and
        # the words are unchanged. A rewritten beat (loop/pov_repair.py does
        # exactly that) drops its duration, because the old measurement belongs
        # to words nobody will say again.
        mf = AUDIO / slug / "beats.json"
        keep = {}
        if mf.exists():
            try:
                for r in json.loads(mf.read_text()):
                    if isinstance(r, dict) and "seconds" in r:
                        keep[int(r["i"])] = (r.get("narration"), r["seconds"])
            except (ValueError, KeyError, TypeError):
                keep = {}
        rows = []
        for i, b in enumerate(plan):
            row = {"i": i, "segment": b["segment"], "narration": b["narration"]}
            was = keep.get(i)
            if (was and was[0] == b["narration"]
                    and (AUDIO / slug / f"{i:04d}.wav").exists()):
                row["seconds"] = was[1]
            rows.append(row)
        write_beats_manifest(mf, rows)   # canonical bytes; no-op when unchanged
        for i, b in enumerate(plan):
            if not inspect(AUDIO / slug / f"{i:04d}.wav")[0]:
                todo.append((slug, i, b["narration"]))
    print(f"{len(plans)} episodes, {total_beats} beats total, "
          f"{len(todo)} to generate, {total_beats - len(todo)} already done "
          f"(resumed).", flush=True)
    if not todo:
        print("nothing to generate; verifying.")
        verify(plans)
        return 0

    import torch
    from chatterbox.tts import ChatterboxTTS

    torch.set_num_threads(min(4, os.cpu_count() or 4))
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device=args.device)
    print(f"model loaded on {args.device} in {time.time() - t0:.1f}s", flush=True)

    # Condition ONCE for the whole 20-episode run: identical timbre everywhere.
    model.prepare_conditionals(args.reference, exaggeration=args.exaggeration)
    print(f"conditioned on {Path(args.reference).name}", flush=True)

    sil = np.zeros(int(args.pause_sentence * SR), dtype=np.float32)
    failures, truncated = [], []
    t_start = time.time()

    # THE DEADLINE IS CHECKED BETWEEN BEATS, NEVER DURING ONE. A beat takes a
    # couple of minutes; stopping inside it would leave a .part.wav to clean up
    # and waste the work. Stopping between them costs nothing at all, because
    # the next run skips every beat whose wav already exists.
    deadline = None
    if args.until:
        hh, mm = (int(x) for x in args.until.split(":"))
        now = _dt.datetime.now()
        deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if deadline <= now:                 # already past today -> tomorrow
            deadline += _dt.timedelta(days=1)
        print(f"will stop cleanly at {deadline:%a %H:%M} "
              f"({(deadline - now).total_seconds() / 3600:.1f} h from now)",
              flush=True)

    stopped_early = False
    for k, (slug, idx, text) in enumerate(todo, 1):
        if deadline and _dt.datetime.now() >= deadline:
            done = k - 1
            print(f"\nDEADLINE {deadline:%H:%M} reached. Stopping cleanly after "
                  f"{done} beat(s) this run; {len(todo) - done} still to do.",
                  flush=True)
            print("Nothing is lost - the next run skips every beat that already "
                  "has a wav and continues from here.", flush=True)
            stopped_early = True
            break
        out = AUDIO / slug / f"{idx:04d}.wav"
        tmp = out.with_suffix(".part.wav")
        chunks = chunk_paragraph(text, args.max_words) or [text]
        got = None
        for attempt in range(args.retries + 1):
            try:
                pieces = []
                for ci, c in enumerate(chunks):
                    torch.manual_seed(args.seed + idx * 97 + attempt * 7919 + ci)
                    wav = model.generate(
                        apply_lexicon(c, LEXICON), audio_prompt_path=None,
                        exaggeration=args.exaggeration,
                        cfg_weight=args.cfg_weight,
                        temperature=args.temperature)
                    a = wav.squeeze(0).detach().cpu().numpy().astype(np.float32)
                    pk = float(np.abs(a).max())
                    if pk > 1.0:
                        a = a / pk
                    a = trim_silence(a)
                    if len(a) / SR > 39.0:
                        truncated.append(f"{slug}#{idx:04d}")
                    a = match_rms(a, args.target_db)
                    pieces.append(a)
                    if ci < len(chunks) - 1:
                        pieces.append(sil)
                y = np.concatenate(pieces)
                y = high_shelf(y, args.presence_db)
                pk = float(np.abs(y).max())
                if pk > 0.97:
                    y = y * (0.97 / pk)
                sf.write(str(tmp), y, SR, subtype="PCM_16")
                ok, d, r, p = inspect(tmp)
                if not ok:
                    raise RuntimeError(f"take rejected: dur={d:.2f}s rms={r:.1f}dBFS")
                os.replace(tmp, out)     # atomic: a partial file is never resumable-as-done
                got = (d, r)
                break
            except Exception as e:
                tmp.unlink(missing_ok=True)
                print(f"    attempt {attempt + 1} failed on {slug}#{idx:04d}: {e}",
                      file=sys.stderr, flush=True)
                if attempt == args.retries:
                    failures.append({"episode": slug, "beat": idx,
                                     "text": text[:120], "error": str(e),
                                     "trace": traceback.format_exc()[-400:]})
        el = time.time() - t_start
        rate = k / el
        eta = (len(todo) - k) / rate / 3600 if rate > 0 else 0
        if got:
            print(f"[{k}/{len(todo)}] {slug[:34]:<34} #{idx:04d} "
                  f"{got[0]:5.2f}s {got[1]:6.1f}dBFS  "
                  f"elapsed={el/3600:4.2f}h eta={eta:4.2f}h", flush=True)
        else:
            print(f"[{k}/{len(todo)}] {slug[:34]:<34} #{idx:04d} FAILED", flush=True)

    rows, complete = verify(plans)
    report = {
        "stopped_at_deadline": stopped_early,
        "engine": "chatterbox-tts 0.1.7 (ResembleAI/chatterbox, MIT weights)",
        "reference": args.reference,
        "target_rms_dbfs": args.target_db,
        "rows": rows, "complete": complete,
        "failures": failures, "truncated": sorted(set(truncated)),
    }
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(f"\nreport -> {args.report}")
    if failures:
        print(f"FAILURES ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  {f['episode']}#{f['beat']:04d}: {f['error']}", file=sys.stderr)
    print(f"complete episodes: {len(complete)}/{len(plans)}")
    return 0 if len(complete) == len(plans) else 1


if __name__ == "__main__":
    raise SystemExit(main())
