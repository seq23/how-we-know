"""The food lane's Mac half: footage, voice, render, stitch - then shelve.

    .venv/bin/python loop/food_lane.py run [--until 07:00] [--slug S]
    .venv/bin/python loop/food_lane.py status
    .venv/bin/python loop/food_lane.py resume-gate      # com.howweknow.food-resume
    .venv/bin/python loop/food_lane.py resume-cancel    # a deliberate stop: never resume it
    .venv/bin/python loop/food_lane.py net-wait [--budget S]

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
(window closed - the next food night resumes); 3 named stop; 5 no network
after the bounded wait (resumable).

A NIGHT THAT DIES IS RESUMED, AND SAYS WHY (2026-10-25). The Mac went down
mid-narration (kern.boottime 19:56, no shutdown record; the food log stopped at
beat 15/19 of chili at 19:25 with no error line) and nothing re-ran the lane:
com.howweknow.food is calendar-only, so the episode would have waited for the
next Tuesday. A process that dies with its machine cannot log its own death,
so the RUN RECORD (loop/state/_local/food_run.json) does it for it:
bin/food-session.sh writes it "running" once it holds the narration lock and
"exited" on every exit it lives to see (a signal, or a lane killed by one,
leaves it "died"). com.howweknow.food-resume (every 300 s, and at login) asks
`resume-gate`: a "running" record whose session is gone is a death - the line
saying so, and the boot time when the Mac restarted, goes into the food log -
and it is resumed while the dead run's own --until window (07:00) has at least
RESUME_MARGIN_S left, at most MAX_RESUMES times per window, always through the
same lock as the batch, so there is never a second narrator.

NETWORK WAITS, IT DOES NOT KILL. A step that fails while the network is down
(footage, stills, voice's whisper download) waits for it with a bounded backoff
(NET_BACKOFF, NET_BUDGET_S, never past the window) and is retried; the session
script does the same around its git pull, R2 push and report push.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
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

# The render venv when it exists, else this interpreter (loop/tests/run_all.py's
# rule, V28). The voice venv has no fallback on purpose: torch and chatterbox
# live only there, so its absence is the named stop FOOD_TTS_MISSING below.
_VENV = ROOT / ".venv" / "bin" / "python"
PY = str(_VENV) if _VENV.exists() else sys.executable
PY_TTS = str(ROOT / ".venv-tts" / "bin" / "python")
REFERENCE = ROOT / "voice" / "reference_A_clean_cond10.wav"
WORK = ROOT / "renders" / "food"
STATE = ROOT / "loop" / "state" / "_local" / "food_lane.json"
RUN = Path(os.environ.get("FOOD_RUN") or ROOT / "loop" / "state" / "_local" / "food_run.json")
FOOD_LOG = Path(os.environ.get("FOOD_LOG")
                or Path.home() / "Library" / "Logs" / "how-we-know" / "food.log")
MAX_REROLLS = 3
MAX_HARVEST_PASSES = 4
RESUME_MARGIN_S = 15 * 60      # less window than this left: not worth a model load
MAX_RESUMES = 3                # per narration window; then a named stop
GATE_GO, GATE_NOOP, GATE_REPORT = 0, 10, 11
NET_HOSTS = (("github.com", 443), ("1.1.1.1", 443))
NET_BACKOFF = (30, 60, 120, 240, 300)       # seconds; the last repeats
NET_BUDGET_S = 30 * 60
NET_ATTEMPTS = 4               # tries of one step across network outages


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


def _now() -> datetime:
    """The wall clock; FOOD_NOW (YYYY-MM-DDTHH:MM) lets the tests drive it."""
    s = os.environ.get("FOOD_NOW")
    return datetime.fromisoformat(s) if s else datetime.now()


def deadline(until: str | None) -> float | None:
    if not until:
        return None
    hh, mm = (int(x) for x in until.split(":"))
    now = _now()
    stop = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= now:
        stop += timedelta(days=1)
    return stop.timestamp()


def sh(args: list[str], log: bool = True) -> int:
    if log:
        say("$ " + " ".join(str(a) for a in args))
    return subprocess.call([str(a) for a in args], cwd=ROOT)


# ---------------------------------------------------------------- network

def net_up() -> bool:
    for host, port in NET_HOSTS:
        try:
            socket.create_connection((host, port), timeout=5).close()
            return True
        except OSError:
            continue
    return False


def _sleep(s: float) -> None:
    time.sleep(s)


def net_wait(budget_s: float = NET_BUDGET_S, until_ts: float | None = None) -> bool:
    """True once the network answers; False (with a named line) after budget_s
    of bounded backoff, or sooner when the narration window would close."""
    if net_up():
        return True
    say(f"network is down; waiting for it (backoff {NET_BACKOFF}s, up to {int(budget_s // 60)} min)")
    waited, i = 0.0, 0
    while waited < budget_s:
        d = min(NET_BACKOFF[min(i, len(NET_BACKOFF) - 1)], budget_s - waited)
        if until_ts and time.time() + d >= until_ts:
            break
        _sleep(d)
        waited += d
        i += 1
        if net_up():
            say(f"network is back after {int(waited)}s")
            return True
    say(f"NAMED STOP [FOOD_NETWORK_DOWN]: no network after {int(waited)}s of waiting; "
        f"com.howweknow.food-resume retries this run while its window lasts")
    return False


def sh_net(args: list, until_ts: float | None = None, attempts: int = NET_ATTEMPTS) -> int:
    """sh(), but a failure while the network is down waits and retries instead
    of ending the night. A failure with the network UP is returned as it is."""
    rc = 1
    for k in range(attempts):
        rc = sh(args)
        if rc in (0, 4) or net_up():
            return rc
        say(f"  {Path(str(args[1])).name} exited {rc} with the network down "
            f"(try {k + 1}/{attempts}); waiting to retry")
        if k == attempts - 1 or not net_wait(until_ts=until_ts):
            break
    return rc


# ---------------------------------------------------------------- the run record

def _run_read() -> dict:
    try:
        return json.loads(RUN.read_text())
    except (OSError, ValueError):
        return {}


def _run_write(rec: dict) -> None:
    RUN.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUN.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1) + "\n")
    tmp.replace(RUN)


def _stamp(ts: float | None = None) -> str:
    return (datetime.fromtimestamp(ts) if ts else _now()).isoformat(timespec="minutes")


def run_begin(pid: int, until: str | None) -> dict:
    prev = _run_read()
    dl = deadline(until)
    same = prev.get("deadline") == dl and prev.get("state") in ("died", "running")
    rec = {"state": "running", "pid": pid, "started": _stamp(), "until": until,
           "deadline": dl, "resumes": prev.get("resumes", 0) if same else 0}
    _run_write(rec)
    return rec


def run_end(rc: int) -> dict:
    """Every exit the session lives to see. A lane killed by a signal (rc >
    128) and a network-down stop (5) are deaths, resumable; the rest exited."""
    rec = _run_read()
    rec.update({"ended": _stamp(), "rc": rc})
    if rc > 128:
        rec.update(state="died", why=f"the session ended on signal {rc - 128}")
    elif rc == 5:
        rec.update(state="died", why="no network after the bounded wait")
    else:
        rec["state"] = "exited"
    _run_write(rec)
    return rec


def _alive(pid) -> bool:
    """The pid is a live food session (a pid reused after a reboot is not)."""
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        pass
    cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                         capture_output=True, text=True).stdout
    return "food-session" in cmd


def boot_time() -> float | None:
    s = os.environ.get("FOOD_BOOT_TIME")
    if s:
        return datetime.fromisoformat(s).timestamp()
    out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True).stdout
    try:
        return float(out.split("sec =")[1].split(",")[0])
    except (IndexError, ValueError):
        return None


def _to_food_log(line: str) -> None:
    """The death is written where the dead night's own lines are."""
    try:
        FOOD_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FOOD_LOG.open("a") as f:
            f.write(f"{_now():%F %H:%M} food-resume: {line}\n")
    except OSError:
        pass


def resume_gate() -> tuple[int, str]:
    rec = _run_read()
    st = rec.get("state")
    if st not in ("running", "died"):
        return GATE_NOOP, f"nothing to resume (last food run: {st or 'none recorded'})"
    if st == "running":
        if _alive(rec.get("pid")):
            return GATE_NOOP, f"food session pid {rec.get('pid')} is running"
        started = rec.get("started", "?")
        bt = boot_time()
        try:
            restarted = bt is not None and bt > datetime.fromisoformat(started).timestamp()
        except ValueError:
            restarted = False
        why = (f"the Mac restarted at {_stamp(bt)} (power loss, a crash or a forced restart)"
               if restarted else "it was killed outright (SIGKILL, or its launchd job was unloaded)")
        line = (f"FOOD_RUN_DIED: food session pid {rec.get('pid')} (started {started}) "
                f"ended with no exit line: {why}")
        rec.update(state="died", why=why, died_seen=_stamp())
        _run_write(rec)
        _to_food_log(line)
        print(line, flush=True)
    dl = rec.get("deadline")
    if dl and _now().timestamp() >= dl - RESUME_MARGIN_S:
        rec["state"] = "expired"
        _run_write(rec)
        line = (f"the interrupted food run's window ({rec.get('until')}) has closed; "
                f"the next food night resumes it from disk")
        _to_food_log(line)
        return GATE_REPORT, line
    if rec.get("resumes", 0) >= MAX_RESUMES:
        rec["state"] = "exhausted"
        _run_write(rec)
        line = (f"NAMED STOP [FOOD_RESUME_EXHAUSTED]: resumed {MAX_RESUMES} times in this window "
                f"and it died again ({rec.get('why')}); the next food night resumes it from disk")
        _to_food_log(line)
        return GATE_REPORT, line
    rec["resumes"] = rec.get("resumes", 0) + 1
    _run_write(rec)
    return GATE_GO, (f"RESUMING the interrupted food run (died: {rec.get('why')}; "
                     f"resume {rec['resumes']}/{MAX_RESUMES}, window to {rec.get('until')})")


def resume_cancel() -> int:
    rec = _run_read()
    rec.update(state="cancelled", cancelled=_stamp())
    _run_write(rec)
    print("food run marked cancelled: com.howweknow.food-resume will not resume it")
    return 0


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
    # every bed sound the preset can pick, on disk BEFORE hours of footage and
    # voice (25 Oct: the night died at the first render, after five hours,
    # on a sizzle .ogg this checkout never harvested)
    import food_sound                                        # noqa: PLC0415
    try:
        got = food_sound.ensure()
    except food_sound.SoundMissing as exc:
        say(f"NAMED STOP [FOOD_SOUND_MISSING]: {exc}")
        return 3
    if got:
        say(f"  fetched the missing food sounds: {', '.join(got)}")
    end = deadline(until)
    st = _load()
    # THE SCRIPT IS PART OF THE KEY (2026-10-26, run 40328601655). The chili/
    # coffee/honey episode stitched at 32.6 min, outside the contract; its
    # script was trimmed and its spec moved to channel/specs/superseded/, which
    # puts it back in flight. A state keyed on the slug alone would skip every
    # stage and re-stitch the OLD voice. A changed script, or a finished run
    # whose spec is gone, re-plans, re-voices and re-renders in a fresh work
    # dir; footage and stills belong to the kits, not the script, and stand.
    sha = hashlib.sha256(script.read_bytes()).hexdigest()[:12]
    spec_p = ROOT / "channel" / "specs" / f"{ep}.json"
    if st.get("slug") != ep:
        st = {"slug": ep, "started": datetime.now().isoformat(timespec="seconds"), "stages": {}}
    elif st.get("script_sha", sha) != sha or ("stitch" in st["stages"] and not spec_p.exists()):
        kept = {k: v for k, v in st["stages"].items() if k in ("footage", "stills")}
        say(f"  {ep}: the script changed or its stitched spec was superseded; "
            f"re-planning, re-voicing and re-rendering (footage and stills kept)")
        st = {"slug": ep, "started": datetime.now().isoformat(timespec="seconds"), "stages": kept}
    if st.get("script_sha") is None and st["stages"].get("plans"):
        st["script_sha"] = sha          # a run already under way: keep its work dir
        st["work"] = str(WORK / ep)
    st.setdefault("script_sha", sha)
    work = Path(st.setdefault("work", str(WORK / ep / sha)))
    voice_root = work / "voice"
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
            rc = sh_net([PY, "research/food_footage.py", "--harvest", "--segments", ",".join(segs)],
                        until_ts=end)
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
                rc = sh_net([PY, "visuals/food_stills.py", dg["key"], dg["prompt"]], until_ts=end)
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
                rc = sh_net(args, until_ts=end)
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
        # THE RUNTIME GATE, before hours of rendering (2026-10-26): the voice
        # IS the episode's length (the stitch matched it to 0.01 s), so a
        # narration outside check_episode's window is known here, not after
        # the stitch where only V55 on main would say so.
        lo, hi = FE.EPISODE_MINUTES
        if not lo <= off / 60 <= hi:
            say(f"NAMED STOP [FOOD_RUNTIME_OFF_CONTRACT]: {ep} narrates {off / 60:.1f} min, "
                f"outside {lo:.0f}-{hi:.0f}; nothing rendered. Trim scripts/food/{ep}.md with "
                f"food_author.fit (the lane's own rule) - a changed script re-voices it")
            return 3
        done("voice", minutes=round(off / 60, 2))
    # ---- render pieces (each skips a finished, unchanged piece itself)
    if "render" not in st["stages"]:
        rc = sh([PY, "visuals/food_episode.py", "render", script, voice_root, work])
        if rc != 0:
            say(f"NAMED STOP [FOOD_PIECE_CONTRACT]: a piece fails the food preset contract: "
                f"{FE.render_failure(work)}")
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


def _named_death(signum, _frame) -> None:
    say(f"NAMED STOP [FOOD_LANE_KILLED]: the lane received {signal.Signals(signum).name}; "
        f"the run record says so and com.howweknow.food-resume picks it up")
    raise SystemExit(128 + signum)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    until = argv[argv.index("--until") + 1] if "--until" in argv else None
    slug = argv[argv.index("--slug") + 1] if "--slug" in argv else None
    if cmd == "run":
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, _named_death)
        return run(slug, until)
    if cmd == "run-begin":
        run_begin(int(argv[argv.index("--pid") + 1]), until)
        return 0
    if cmd == "run-end":
        run_end(int(argv[argv.index("--rc") + 1]))
        return 0
    if cmd == "resume-gate":
        rc, line = resume_gate()
        print(line)
        return rc
    if cmd == "resume-cancel":
        return resume_cancel()
    if cmd == "net-up":
        return 0 if net_up() else 1
    if cmd == "net-wait":
        budget = float(argv[argv.index("--budget") + 1]) if "--budget" in argv else NET_BUDGET_S
        return 0 if net_wait(budget, deadline(until)) else 5
    if cmd == "status":
        return status()
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(main(sys.argv[1:]))
