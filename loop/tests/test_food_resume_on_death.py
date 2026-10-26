"""A food night that dies says why and is resumed the same night - driven, not asserted.

THE INCIDENT (2026-10-25). The food lane was narrating "what-is-inside-chili-
coffee-honey" when the Mac went down (kern.boottime 19:56, no shutdown record
in wtmp). food.log stopped at "[15/19] ... 111.1m" at 19:25 with NO error
line, and nothing re-ran it: com.howweknow.food is calendar-only (Tue + Thu
22:58), so the episode would have waited two days. A session kickstarted it by
hand at 20:29. Separately, `bin/loop-install-launchd.sh --install` unloaded
every agent - and `launchctl unload` kills a running job mid-night.

This drives the REAL bin/food-session.sh with a stub lane (FOOD_TEST_STUBS),
a temporary run record, lock and food log, and a fake clock (FOOD_NOW):

  a. a normal night writes the run record "running" then "exited"; the next
     resume tick is a no-op and runs nothing;
  b. a "running" record whose session is gone (the Mac restarted) -> the death
     is WRITTEN to the food log (FOOD_RUN_DIED, naming the restart), the lane
     is resumed, and its output lands in the food log; the next tick no-ops;
  c. the dead run's session is still alive -> no-op, lane not run;
  d. the batch holds the narration lock -> no-op, lane not run, the death kept
     for the next tick (never two narrators);
  e. the window (07:00, less RESUME_MARGIN_S) has closed -> reported ONCE in
     the food log, not run; MAX_RESUMES reached -> FOOD_RESUME_EXHAUSTED;
     resume-cancel -> never resumed;
  f. a lane killed by SIGKILL -> FOOD_LANE_KILLED named, the record "died",
     and the next tick resumes it; a SIGTERM to the session ->
     FOOD_SESSION_KILLED named and resumable;
  g. the network: net_wait backs off (bounded by NET_BACKOFF / the budget /
     the window) and names FOOD_NETWORK_DOWN; sh_net retries a step that
     failed with the network down and does NOT retry one that failed with it up;
  h. the installer never unloads an agent whose job is running (fake
     launchctl), and loads food-resume.

Hard-fails if it ran zero cases.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
SCRIPT = ROOT / "bin" / "food-session.sh"
sys.path.insert(0, str(LOOP))

fails: list[str] = []
examined = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{label}: {detail}"[:400])


def dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


td = Path(tempfile.mkdtemp(prefix="food-resume-"))
RUN, LOCK, LOG, MARK = td / "food_run.json", td / "batch.lock", td / "food.log", td / "lane-ran"
ENV = {**os.environ, "FOOD_TEST_STUBS": "1", "FOOD_RUN": str(RUN), "BATCH_LOCK": str(LOCK),
       "FOOD_LOG": str(LOG), "FOOD_ERR": str(td / "food.err"),
       "FOOD_TEST_LANE": f"touch {MARK}", "FOOD_NOW": "2026-10-25T20:00"}
ENV.pop("FOOD_SESSION_DRY", None)


def session(*args, **env) -> subprocess.CompletedProcess:
    MARK.unlink(missing_ok=True)
    return subprocess.run(["/bin/bash", str(SCRIPT), *args], capture_output=True, text=True,
                          env={**ENV, **env}, timeout=60)


def rec() -> dict:
    try:
        return json.loads(RUN.read_text())
    except (OSError, ValueError):
        return {}


def died_record(**kw) -> None:
    import food_lane                                           # noqa: PLC0415
    os.environ["FOOD_NOW"] = ENV["FOOD_NOW"]
    r = {"state": "running", "pid": dead_pid(), "started": "2026-10-25T16:40",
         "until": "07:00", "deadline": food_lane.deadline("07:00"), "resumes": 0, **kw}
    RUN.write_text(json.dumps(r))


try:
    # a. a normal night, then a no-op tick
    out = session()
    check("a. normal night runs the lane", out.returncode == 0 and MARK.exists(),
          f"rc={out.returncode} {out.stdout[-200:]} {out.stderr[-200:]}")
    check("a. record exited", rec().get("state") == "exited" and rec().get("rc") == 0, str(rec()))
    out = session("--resume-if-interrupted")
    check("a. tick after a clean night is a no-op", out.returncode == 0 and not MARK.exists()
          and "nothing to resume" in out.stdout, out.stdout[-200:])

    # b. the Mac restarted mid-run -> the death is written, the night resumed
    LOG.write_text("")
    died_record()
    out = session("--resume-if-interrupted", FOOD_BOOT_TIME="2026-10-25T19:56")
    log = LOG.read_text()
    check("b. death written to the food log", "FOOD_RUN_DIED" in log and "restarted at" in log, log[-300:])
    check("b. resumed: lane ran", MARK.exists() and "RESUMING" in out.stdout, out.stdout[-300:])
    check("b. resumed night writes to the food log", "food night RESUMED" in log
          and "food night (stubbed) ended rc=0" in log, log[-300:])
    check("b. record exited after the resume", rec().get("state") == "exited"
          and rec().get("resumes") == 1, str(rec()))
    out = session("--resume-if-interrupted")
    check("b. next tick no-ops", not MARK.exists(), out.stdout[-200:])

    # c. the session is still alive
    alive = subprocess.Popen(["/bin/bash", "-c", "exec -a food-session.sh sleep 30"])
    try:
        time.sleep(0.2)
        died_record(pid=alive.pid)
        out = session("--resume-if-interrupted")
        check("c. live session -> no-op", not MARK.exists() and "is running" in out.stdout
              and rec().get("state") == "running", out.stdout[-200:])
    finally:
        alive.kill()
        alive.wait()

    # d. the batch holds the lock -> never a second narrator
    batch = subprocess.Popen(["/bin/bash", "-c", "exec -a batch-session.sh sleep 30"])
    try:
        time.sleep(0.2)
        LOCK.write_text(str(batch.pid))
        died_record()
        out = session("--resume-if-interrupted")
        check("d. lock held -> no-op", not MARK.exists() and "narrator is running" in out.stdout,
              out.stdout[-200:])
        check("d. the death is kept for the next tick", rec().get("state") == "running", str(rec()))
        out = session()
        check("d. a normal night also refuses", not MARK.exists() and "NAMED STOP" in out.stdout,
              out.stdout[-200:])
    finally:
        batch.kill()
        batch.wait()
        LOCK.unlink(missing_ok=True)
    out = session("--resume-if-interrupted")
    check("d. lock freed -> resumed", MARK.exists(), out.stdout[-200:])

    # e. window closed / exhausted / cancelled
    LOG.write_text("")
    died_record()
    out = session("--resume-if-interrupted", FOOD_NOW="2026-10-26T06:50")
    check("e. window closed -> not run", not MARK.exists() and "window" in out.stdout, out.stdout[-200:])
    check("e. window closed -> reported in the food log", "has closed" in LOG.read_text(),
          LOG.read_text()[-200:])
    out = session("--resume-if-interrupted", FOOD_NOW="2026-10-26T06:50")
    check("e. reported once", LOG.read_text().count("has closed") == 1, LOG.read_text()[-300:])
    died_record(resumes=3)
    out = session("--resume-if-interrupted")
    check("e. exhausted -> named stop, not run", not MARK.exists()
          and "FOOD_RESUME_EXHAUSTED" in out.stdout, out.stdout[-200:])
    died_record()
    subprocess.run([sys.executable, str(LOOP / "food_lane.py"), "resume-cancel"], env=ENV,
                   capture_output=True)
    out = session("--resume-if-interrupted")
    check("e. cancelled -> never resumed", not MARK.exists(), out.stdout[-200:])

    # f. killed lanes and sessions name themselves and are resumable
    killer = td / "kill-self.sh"
    killer.write_text("#!/bin/bash\nkill -9 $$\n")
    killer.chmod(0o755)
    out = session(FOOD_TEST_LANE=str(killer))
    check("f. SIGKILLed lane is named", "FOOD_LANE_KILLED" in out.stdout and "signal 9" in out.stdout,
          out.stdout[-300:])
    check("f. SIGKILLed lane -> record died", rec().get("state") == "died", str(rec()))
    out = session("--resume-if-interrupted")
    check("f. ... and the next tick resumes it", MARK.exists(), out.stdout[-200:])
    p = subprocess.Popen(["/bin/bash", str(SCRIPT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env={**ENV, "FOOD_TEST_LANE": "sleep 3"})
    time.sleep(1.0)
    mid = rec()
    check("f. a live night's record says running, with its own pid",
          mid.get("state") == "running" and mid.get("pid") == p.pid, str(mid))
    p.send_signal(signal.SIGTERM)
    so, _ = p.communicate(timeout=30)
    check("f. SIGTERM to the session is named", "FOOD_SESSION_KILLED" in so, so[-300:])
    check("f. SIGTERM -> record died (resumable)", rec().get("state") == "died", str(rec()))

    # g. the network
    import food_lane as F                                       # noqa: E402
    slept: list[float] = []
    F._sleep = slept.append
    seq = iter([False, False, False, True])
    F.net_up = lambda: next(seq)
    check("g. net_wait returns once the network is back", F.net_wait(budget_s=3600) is True
          and slept == [30, 60, 120], str(slept))
    slept.clear()
    F.net_up = lambda: False
    ok = F.net_wait(budget_s=600)
    check("g. net_wait is bounded by its budget", ok is False and sum(slept) == 600
          and max(slept) <= max(F.NET_BACKOFF), str(slept))
    slept.clear()
    ok = F.net_wait(budget_s=3600, until_ts=time.time() + 100)
    check("g. net_wait never waits past the window", ok is False and sum(slept) <= 100, str(slept))
    calls: list = []
    rcs = iter([1, 1, 0])
    F.sh = lambda args, log=True: (calls.append(args), next(rcs))[1]
    F.net_up = lambda: False
    F.net_wait = lambda budget_s=0, until_ts=None: True
    check("g. sh_net retries a step that failed with the network down",
          F.sh_net(["py", "research/food_footage.py"]) == 0 and len(calls) == 3, str(calls))
    calls.clear()
    rcs = iter([1, 0])
    F.net_up = lambda: True
    check("g. sh_net does not retry a real failure", F.sh_net(["py", "x.py"]) == 1 and len(calls) == 1,
          str(calls))
    calls.clear()
    rcs = iter([1] * 10)
    F.net_up = lambda: False
    check("g. sh_net is bounded", F.sh_net(["py", "x.py"]) == 1 and len(calls) == F.NET_ATTEMPTS,
          str(calls))

    # h. the installer never unloads a running job
    if shutil.which("plutil"):
        home = td / "home"
        (home / "Library" / "LaunchAgents").mkdir(parents=True)
        calls_f = td / "launchctl.calls"
        fake = td / "launchctl"
        fake.write_text("#!/bin/bash\n"
                        f"echo \"$*\" >> {calls_f}\n"
                        "if [ \"$1\" = list ]; then\n"
                        "  [ \"$2\" = com.howweknow.food ] && { echo '{'; echo '\t\"PID\" = 4242;'; echo '};'; exit 0; }\n"
                        "  exit 1\n"
                        "fi\nexit 0\n")
        fake.chmod(0o755)
        out = subprocess.run(["bash", str(ROOT / "bin" / "loop-install-launchd.sh"), "--install"],
                             capture_output=True, text=True, timeout=60,
                             env={**os.environ, "HOME": str(home), "LAUNCHCTL": str(fake)})
        calls_txt = calls_f.read_text() if calls_f.exists() else ""
        check("h. installer ran", out.returncode == 0, out.stdout[-200:] + out.stderr[-200:])
        check("h. a running job is never unloaded",
              "unload" not in "".join(ln for ln in calls_txt.splitlines(True)
                                      if ln.rstrip().endswith("com.howweknow.food.plist"))
              and "DEFERRED com.howweknow.food" in out.stdout, calls_txt + out.stdout[-300:])
        check("h. food-resume is loaded", "load " + str(home / "Library" / "LaunchAgents"
                                                        / "com.howweknow.food-resume.plist") in calls_txt,
              calls_txt[-300:])
    else:
        print("  (h. skipped: no plutil here - the installer is macOS-only)")
finally:
    shutil.rmtree(td, ignore_errors=True)

if examined == 0:
    fails.append("examined ZERO cases - this test cannot reach what it governs")
print(f"inspected {examined} food-resume case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - a food night that dies says why and resumes, one narrator, inside its window")
