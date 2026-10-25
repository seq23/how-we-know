"""The food lane's Mac half: footage, voice, render, stitch - then shelve.

    .venv/bin/python loop/food_lane.py run [--until 07:00] [--slug S]
    .venv/bin/python loop/food_lane.py status

Called by bin/food-session.sh (launchd com.howweknow.food, Tue and Thu 22:58),
never by hand in the normal course. It renders the episode loop/food_author.py
wrote (scripts/food/<slug>.md, "in flight" until its spec exists) through the
SAME commands the first food episode was made with (visuals/food_episode.py
docstring), in order, each resumable from what is on disk:

    footage   research/food_footage.py --harvest --segments <the kits>
              (>= 10 real clips a segment; hands measured by Apple Vision)
    stills    visuals/food_stills.py: one diagram still per kit ($0 Workers AI);
              a failure only skips the {{cross_section}} device
    plans     visuals/food_episode.py plans
    voice     .venv-tts voice/food_voice.py per piece, --until the window's end;
              then the one-voice check over the WHOLE episode, outlier beats
              re-drawn (food_episode.reroll), up to MAX_REROLLS rounds
    render    visuals/food_episode.py render (pieces), each held to food.check
    stitch    visuals/food_episode.py stitch -> renders/<slug>-final.mp4 and
              channel/specs/<slug>.json (the episode contract, check_episode)

Rule 0: every exit is work done or a named line the session log and the
heartbeat carry. Exit codes: 0 stitched and contract holds; 4 unfinished
(window closed - the next food night resumes); 3 named stop.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "voice"))

PY = str(ROOT / ".venv" / "bin" / "python")
PY_TTS = str(ROOT / ".venv-tts" / "bin" / "python")
REFERENCE = ROOT / "voice" / "reference_A_clean_cond10.wav"
WORK = ROOT / "renders" / "food"
STATE = ROOT / "loop" / "state" / "_local" / "food_lane.json"
MAX_REROLLS = 3
MAX_HARVEST_PASSES = 4


def say(msg: str) -> None:
    print(f"{datetime.now():%F %H:%M} food-lane: {msg}", flush=True)


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1) + "\n")


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def deadline(until: str | None) -> float | None:
    if not until:
        return None
    hh, mm = (int(x) for x in until.split(":"))
    now = datetime.now()
    stop = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= now:
        stop += timedelta(days=1)
    return stop.timestamp()


def sh(args: list[str], log: bool = True) -> int:
    if log:
        say("$ " + " ".join(str(a) for a in args))
    return subprocess.call([str(a) for a in args], cwd=ROOT)


def episode(slug: str | None) -> str | None:
    import food_author                                       # noqa: PLC0415
    flight = food_author.in_flight()
    if slug:
        return slug
    return flight[0] if flight else None


def run(slug: str | None, until: str | None) -> int:
    import food                                              # noqa: PLC0415
    import food_episode as FE                                # noqa: PLC0415
    import food_voice                                        # noqa: PLC0415
    ep = episode(slug)
    if not ep:
        say("NAMED STOP [FOOD_NOTHING_TO_RENDER]: no authored food episode is waiting "
            "(loop/food_author.py, Mondays in the cloud, writes the next one)")
        return 3
    script = ROOT / "scripts" / "food" / f"{ep}.md"
    if not script.exists():
        say(f"NAMED STOP [FOOD_SCRIPT_MISSING]: {script.relative_to(ROOT)} is not on this Mac "
            f"(pull main)")
        return 3
    end = deadline(until)
    st = _load()
    if st.get("slug") != ep:
        st = {"slug": ep, "started": datetime.now().isoformat(timespec="seconds"), "stages": {}}
    work, voice_root = WORK / ep, WORK / ep / "voice"
    work.mkdir(parents=True, exist_ok=True)
    paras = food.parse(script)
    pcs = food.pieces(paras)
    order = FE.piece_order(pcs)
    segs = [p for p in order if p not in ("open", "tail")]
    say(f"episode {ep}: pieces {order}")

    def done(stage: str, **facts) -> None:
        st["stages"][stage] = {"at": datetime.now().isoformat(timespec="seconds"), **facts}
        _save(st)

    # ---- footage
    if "footage" not in st["stages"]:
        rc = 1
        for n in range(MAX_HARVEST_PASSES):          # 20 downloads a pass (food_footage.MAX_PER_RUN)
            rc = sh([PY, "research/food_footage.py", "--harvest", "--segments", ",".join(segs)])
            if rc == 0:
                break
        if rc != 0:
            say(f"NAMED STOP [FOOD_FOOTAGE_SHORT]: fewer than 10 real clips for a segment of {ep} "
                f"after {MAX_HARVEST_PASSES} passes; widen its kit (channel/food_kits/)")
            return 3
        done("footage")
    # ---- stills (optional per kit)
    if "stills" not in st["stages"]:
        for s in segs:
            kit = food.KITS.get(s) or {}
            dg = kit.get("diagram") or {}
            if dg.get("key"):
                rc = sh([PY, "visuals/food_stills.py", dg["key"], dg["prompt"]])
                if rc != 0:
                    say(f"  {s}: no diagram still ({rc}); its {{{{cross_section}}}} shows footage")
        done("stills")
    # ---- plans
    plans_dir = work / "plans"
    if "plans" not in st["stages"]:
        made = FE.plans(script, plans_dir)
        done("plans", beats=made)
    # ---- voice, piece by piece, then the one-voice check across the episode
    if "voice" not in st["stages"]:
        if not Path(PY_TTS).exists():
            say(f"NAMED STOP [FOOD_TTS_MISSING]: {PY_TTS} does not exist (see bin/batch-session.sh "
                f"for the rebuild line)")
            return 3
        for attempt in range(MAX_REROLLS + 1):
            for p in order:
                vd = voice_root / p
                plan_p = plans_dir / f"plan-{p}.json"
                n = len(json.loads(plan_p.read_text()))
                have = len(list(vd.glob("[0-9][0-9][0-9][0-9].json"))) if vd.exists() else 0
                if have >= n and (vd / "beats.json").exists():
                    continue
                if end and time.time() >= end:
                    say(f"UNFINISHED: narration window closed before {p}; the next food night resumes")
                    return 4
                args = [PY_TTS, "voice/food_voice.py", plan_p, vd, "--reference", REFERENCE]
                if until:
                    args += ["--until", until]
                rc = sh(args)
                if rc == 4:
                    say(f"UNFINISHED: narration window closed inside {p}; the next food night resumes")
                    return 4
                if rc != 0:
                    say(f"NAMED STOP [FOOD_VOICE_FAILED]: food_voice.py exited {rc} on {p}")
                    return 3
            measures, offsets, off = [], [], 0.0
            for p in order:
                m = food_voice.measure(voice_root / p)
                measures.append(m)
                offsets.append(off)
                off += max((b["start_s"] + b["total_s"] for b in m.get("beats") or []), default=0.0)
            whole = FE.combine_voice(measures, offsets)
            probs = food_voice.check(whole)
            bad = sorted({int(x.split()[1]) for x in probs if x.startswith("beat ")})
            if not probs:
                break
            if attempt == MAX_REROLLS or not bad:
                say(f"NAMED STOP [FOOD_VOICE_CONTRACT]: {probs[:3]}")
                return 3
            k = 0
            for p, m in zip(order, measures):
                nb = len(m.get("beats") or [])
                local = [i - k for i in bad if k <= i < k + nb]
                if local:
                    FE.reroll(plans_dir / f"plan-{p}.json", voice_root / p, local, attempt + 1)
                    say(f"  re-drawing {p} beats {local} (round {attempt + 1})")
                k += nb
        done("voice")
    # ---- render pieces (each skips a finished, unchanged piece itself)
    if "render" not in st["stages"]:
        rc = sh([PY, "visuals/food_episode.py", "render", script, voice_root, work])
        if rc != 0:
            say(f"NAMED STOP [FOOD_PIECE_CONTRACT]: a piece fails the food preset contract "
                f"(see the lines above)")
            return 3
        done("render")
    # ---- stitch + spec
    final = ROOT / "renders" / f"{ep}-final.mp4"
    rc = sh([PY, "visuals/food_episode.py", "stitch", script, voice_root, work, final])
    spec = ROOT / "channel" / "specs" / f"{ep}.json"
    done("stitch", rc=rc, spec=str(spec.relative_to(ROOT)) if spec.exists() else None)
    if rc != 0:
        say(f"NAMED STOP [FOOD_EPISODE_CONTRACT]: {ep} stitched but fails the episode contract; "
            f"the upload lane holds it by name (backfill.food_hold)")
        return 3
    say(f"READY FOR UPLOAD: renders/{ep}-final.mp4 + channel/specs/{ep}.json (contract holds)")
    return 0


def status() -> int:
    st = _load()
    print(json.dumps(st or {"state": "no food night has run"}, indent=1))
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    until = argv[argv.index("--until") + 1] if "--until" in argv else None
    slug = argv[argv.index("--slug") + 1] if "--slug" in argv else None
    if cmd == "run":
        return run(slug, until)
    if cmd == "status":
        return status()
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(main(sys.argv[1:]))
