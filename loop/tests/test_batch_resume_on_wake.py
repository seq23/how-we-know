"""An interrupted night resumes on wake - driven, not asserted.

Owner, 2026-10-12: "no sleep and restart on wake, I need both". The Mac no
longer sleeps on AC; this is the other half. A reboot or a flat battery in the
middle of the 23:00 batch used to write the night off until the next 23:00.
Now bin/batch-session.sh records each completed unit in a progress file and
launchd's com.howweknow.batch-resume (every 300 s) runs it with
--resume-if-interrupted. See loop/batch_progress.py.

This drives the REAL script with a fake clock (BATCH_NOW), a temporary
progress file and lock, and fake phases (BATCH_TEST_STUBS) that only log:

  a. no progress file, outside 23:00-06:00 -> no-op, nothing created;
     no progress file at 01:00 -> the never-started night starts and completes;
  b. an incomplete same-night file -> resumes from the recorded phase, the
     phases recorded done are NOT re-run, the report carries resumed_from, the
     night is marked complete, and the next tick is a no-op; a render killed
     mid-mux is set aside, never left to pass as finished;
  c. past 09:00 with the night incomplete -> no resume; reported ONCE;
  d. a live batch holds the lock -> no-op (resume mode) / named stop (normal);
     a stale lock (dead pid) is taken over.
  e. narration never runs past 07:00 on a resume (the cap is a wall clock);
  f. the plist is pinned: label, StartInterval 300, the program, RunAtLoad;
  g. the incomplete-night report reaches the heartbeat and the stop file.

Hard-fails if it ran zero cases.
"""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
SCRIPT = ROOT / "bin" / "batch-session.sh"
TMP = Path(tempfile.mkdtemp(prefix="batch-resume-"))
fails: list[str] = []
cases = 0

STUBS = TMP / "stubs.sh"
STUBS.write_text(r'''
L() { echo "$*" >> "$BATCH_TEST_LOG"; }
phase_selfheal(){ L selfheal; }
phase_survey(){ L survey; pending_audio="slug-a:3/9"; pending_render=""; pending_plan=""; }
phase_prepare(){ L prepare; }
phase_idle(){ return 0; }
hold_awake(){ :; }
phase_narrate(){ L narrate; }
phase_render(){ L render; }
phase_captions(){ L captions; CAPRC=0; }
shelve_shorts(){ L shelve; }
harvest_footage(){ L harvest; }
phase_report(){ L "report resumed_from=$RESUMED_FROM"; }
report_incomplete_night(){ L report_incomplete; }
''')


def run(now: str, *args: str, progress: dict | None = None, name: str,
        extra_env: dict | None = None) -> tuple[subprocess.CompletedProcess,
                                                 list[str], Path, Path]:
    d = TMP / name
    d.mkdir()
    prog, log = d / "batch_progress.json", d / "phases.log"
    if progress is not None:
        prog.write_text(json.dumps(progress))
    env = {k: v for k, v in os.environ.items() if k != "XPC_SERVICE_NAME"}
    env.update({"BATCH_NOW": now, "BATCH_PROGRESS": str(prog),
                "BATCH_LOCK": str(d / "batch.lock"),
                "BATCH_TEST_STUBS": str(STUBS), "BATCH_TEST_LOG": str(log),
                "BATCH_RENDERS_DIR": str(d / "renders")})
    env.update(extra_env or {})
    r = subprocess.run(["bash", str(SCRIPT), *args], env=env, text=True,
                       capture_output=True, timeout=60)
    lines = log.read_text().split("\n")[:-1] if log.exists() else []
    return r, lines, prog, d


def again(d: Path, now: str, *args: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    env = {k: v for k, v in os.environ.items() if k != "XPC_SERVICE_NAME"}
    env.update({"BATCH_NOW": now, "BATCH_PROGRESS": str(d / "batch_progress.json"),
                "BATCH_LOCK": str(d / "batch.lock"),
                "BATCH_TEST_STUBS": str(STUBS), "BATCH_TEST_LOG": str(d / "phases.log"),
                "BATCH_RENDERS_DIR": str(d / "renders")})
    r = subprocess.run(["bash", str(SCRIPT), *args], env=env, text=True,
                       capture_output=True, timeout=60)
    log = d / "phases.log"
    return r, (log.read_text().split("\n")[:-1] if log.exists() else [])


def check(cond: bool, msg: str) -> None:
    if not cond:
        fails.append(msg)


INCOMPLETE = {"night": "2026-10-12", "started_at": "2026-10-12T23:00:04",
              "last_completed_at": "2026-10-13T01:40:00", "phase": "render",
              "episode": "slug-a", "phases_done": ["narrate", "render"],
              "units": [], "complete": False}
ALL = ["selfheal", "survey", "prepare", "narrate", "render", "captions",
       "shelve", "harvest"]

# -- a. no progress file -> no-op (day, 22:30 and 07:00) ------------------
for i, now in enumerate(["2026-10-13T14:00", "2026-10-12T22:30", "2026-10-13T07:00"]):
    cases += 1
    r, log, prog, _ = run(now, "--resume-if-interrupted", name=f"a{i}")
    check(r.returncode == 0, f"(a {now}) exit {r.returncode}: {r.stdout}{r.stderr}")
    check(log == [], f"(a {now}) a phase ran with no progress file: {log}")
    check(not prog.exists(), f"(a {now}) a no-op created the progress file")
    check("nothing to resume" in r.stdout, f"(a {now}) no no-op line: {r.stdout!r}")

# -- a'. never-started night at 01:00 -> starts it ------------------------
cases += 1
r, log, prog, _ = run("2026-10-13T01:00", "--resume-if-interrupted", name="a_start")
check(r.returncode == 0, f"(a') exit {r.returncode}: {r.stderr}")
check("never started" in r.stdout, f"(a') no start line: {r.stdout!r}")
check(log[:-1] == ALL and log[-1] == "report resumed_from=",
      f"(a') the never-started night did not run every phase: {log}")
p = json.loads(prog.read_text()) if prog.exists() else {}
check(p.get("night") == "2026-10-12" and p.get("complete") is True,
      f"(a') night not recorded complete: {p}")
check(set(ALL) - {"selfheal", "survey", "prepare"} <= set(p.get("phases_done", [])),
      f"(a') phases not recorded done: {p.get('phases_done')}")

# -- b. incomplete same-night -> resume, done phases skipped --------------
cases += 1
r, log, prog, d = run("2026-10-13T02:30", "--resume-if-interrupted",
                      progress=INCOMPLETE, name="b")
check(r.returncode == 0, f"(b) exit {r.returncode}: {r.stderr}")
check("resuming night of 2026-10-12 from render/slug-a" in r.stdout,
      f"(b) no resume line: {r.stdout!r}")
check("narrate" not in log and "render" not in log,
      f"(b) a phase recorded done tonight was RE-RUN on resume: {log}")
check(log == ["selfheal", "survey", "prepare", "captions", "shelve", "harvest",
              "report resumed_from=render/slug-a"],
      f"(b) the resume did not finish the night from the recorded phase: {log}")
p = json.loads(prog.read_text())
check(p.get("complete") is True and p.get("resumed_from") == "render/slug-a",
      f"(b) resumed night not completed / resumed_from not kept: {p}")
check(p.get("started_at") == INCOMPLETE["started_at"],
      "(b) a resume restarted the night's record instead of continuing it")
cases += 1
r2, log2 = again(d, "2026-10-13T02:35", "--resume-if-interrupted")
check(r2.returncode == 0 and log2 == log and "completed" in r2.stdout,
      f"(b) the next tick after a resumed night was not a no-op: {r2.stdout!r} {log2}")

# -- b'. a render killed mid-mux is set aside on resume -------------------
cases += 1
inflight = dict(INCOMPLETE, phases_done=["narrate"], phase="narrate",
                episode=None, rendering="slug-b")
dd = TMP / "b_inflight" / "renders"
dd.mkdir(parents=True)
(dd / "slug-b-final.mp4").write_bytes(b"truncated")
r, log, prog, d = run("2026-10-13T03:00", "--resume-if-interrupted",
                      progress=inflight, name="b_inflight_run",
                      extra_env={"BATCH_RENDERS_DIR": str(dd)})
check(not (dd / "slug-b-final.mp4").exists(),
      "(b') a render killed mid-mux was left in place to pass as finished")
check(any((dd / "interrupted").glob("slug-b-final.*.mp4")),
      "(b') the interrupted render was not moved aside (it must never be deleted)")
check("render" in log, f"(b') the render phase did not re-run after an in-flight kill: {log}")

# -- c. past 09:00 with the night incomplete -> reported once, no resume --
cases += 1
r, log, prog, d = run("2026-10-13T09:30", "--resume-if-interrupted",
                      progress=INCOMPLETE, name="c")
check(r.returncode == 0, f"(c) exit {r.returncode}: {r.stderr}")
check(log == ["report_incomplete"], f"(c) past 09:00 must report, never resume: {log}")
p = json.loads(prog.read_text())
check(p.get("reported_at") and not p.get("complete"),
      f"(c) incomplete night not marked reported: {p}")
r2, log2 = again(d, "2026-10-13T09:35", "--resume-if-interrupted")
check(log2 == ["report_incomplete"], f"(c) reported more than once: {log2}")

# -- d. a running batch holds the lock -> no-op ---------------------------
cases += 1
holder = subprocess.Popen(["bash", "-c", "exec -a batch-session-holder sleep 30"])
try:
    dl = TMP / "d"
    dl.mkdir()
    (dl / "batch.lock").write_text(f"{holder.pid}\n")
    (dl / "batch_progress.json").write_text(json.dumps(INCOMPLETE))
    r, log = again(dl, "2026-10-13T02:30", "--resume-if-interrupted")
    check(r.returncode == 0 and log == [] and "already running" in r.stdout,
          f"(d) resumed alongside a running batch: {r.stdout!r} {log}")
    r, log = again(dl, "2026-10-13T02:30")
    check(r.returncode == 0 and log == [] and "another batch session" in r.stdout,
          f"(d) a normal run started a second batch: {r.stdout!r} {log}")
finally:
    holder.kill()
    holder.wait()
cases += 1
r, log = again(dl, "2026-10-13T02:31", "--resume-if-interrupted")
check("narrate" not in log and "captions" in log,
      f"(d) a stale lock (dead pid) blocked the resume: {r.stdout!r} {log}")
check(not (dl / "batch.lock").exists(), "(d) the lock outlived the batch")

# -- e. narration never runs past the 07:00 cap on a resume ---------------
for now, want in [("2026-10-13T07:30", 1), ("2026-10-13T02:00", 0),
                  ("2026-10-12T23:30", 0), ("2026-10-13T06:59", 0)]:
    cases += 1
    rc = subprocess.run([sys.executable, str(LOOP / "batch_progress.py"),
                         "narration-window"], env={**os.environ, "BATCH_NOW": now,
                         "NARRATION_UNTIL": "07:00"}).returncode
    check(rc == want, f"(e) narration-window at {now} = {rc}, want {want}")
src = SCRIPT.read_text()
check('if [ -n "${pending_audio// }" ] && ! narration_allowed; then' in src,
      "(e) phase_narrate no longer consults narration_allowed")

# -- f. the plist ---------------------------------------------------------
cases += 1
out = subprocess.run(["bash", str(ROOT / "bin" / "loop-install-launchd.sh"),
                      "--plist", "batch-resume"], capture_output=True, text=True)
try:
    pl = plistlib.loads(out.stdout.encode())
except Exception as e:                                   # noqa: BLE001
    pl = {}
    fails.append(f"(f) batch-resume plist does not parse: {e}")
check(pl.get("Label") == "com.howweknow.batch-resume", f"(f) label: {pl.get('Label')}")
check(pl.get("StartInterval") == 300, f"(f) StartInterval: {pl.get('StartInterval')}")
check("StartCalendarInterval" not in pl, "(f) the resume agent must be an interval")
prog_args = pl.get("ProgramArguments") or []
check(bool(prog_args) and prog_args[-1].endswith(
          "/bin/batch-session.sh --resume-if-interrupted"),
      f"(f) program: {prog_args}")
check(pl.get("RunAtLoad") is True, "(f) RunAtLoad must be true (check at login)")
inst = (ROOT / "bin" / "loop-install-launchd.sh").read_text()
check('AGENT_NAMES="batch nightquit batch-resume"' in inst
      and 'print_one batch-resume > "$AGENTS/com.howweknow.batch-resume.plist"' in inst,
      "(f) --install does not write and load com.howweknow.batch-resume")

# -- g. the incomplete-night report reaches heartbeat + stop file ---------
cases += 1
stops = TMP / "stops"
stops.mkdir()
os.environ["LOOP_STOPS_DIR"] = str(stops)
gp = TMP / "g_progress.json"
gp.write_text(json.dumps(INCOMPLETE))
os.environ["BATCH_PROGRESS"] = str(gp)
sys.path.insert(0, str(LOOP))
import batch_progress as BPm                              # noqa: E402
import mac_sync                                           # noqa: E402
mac_sync.HEARTBEAT = TMP / "mac_heartbeat.json"
BPm.report_incomplete()
hb = json.loads(mac_sync.HEARTBEAT.read_text())
check((hb.get("batch") or {}).get("incomplete_night", {}).get("night") == "2026-10-12",
      f"(g) heartbeat does not note the incomplete night: {hb.get('batch')}")
recs = [json.loads(f.read_text()) for f in stops.glob("*-mac-batch.json")]
check(any(r.get("code") == "BATCH_NIGHT_INCOMPLETE" for r in recs),
      f"(g) no BATCH_NIGHT_INCOMPLETE stop record: {recs}")
mac_sync.heartbeat("batch", True, resumed_from="")
hb = json.loads(mac_sync.HEARTBEAT.read_text())
check("incomplete_night" not in hb["batch"] and "resumed_from" not in hb["batch"],
      f"(g) a finished night did not clear the incomplete/resumed facts: {hb['batch']}")

if cases == 0:
    fails.append("ran zero cases")
if fails:
    print("FAIL test_batch_resume_on_wake:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print(f"OK an interrupted night resumes on wake: {cases} case(s)")
