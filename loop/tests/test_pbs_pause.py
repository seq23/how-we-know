"""The Peace Be Still library-fill pause (her call, 18 Nov 2026), held until the fill is done
(her ruling 21 Nov 2026: "YT channels still on pause until PBS audio fills are done!!!").

  a. a fill file 3 days old pauses the Mac jobs (exit 10) and the floor check
     files NO STOPPED issue for either channel, saying "Paused for the Peace Be
     Still library fill since <date>" instead, and closes an open one;
  b. a fill file 30 days old STILL pauses (no auto-expiry): the gate exits 10,
     the floor check files no STOPPED issue, and the line names the pause, its
     start date and its days, and says it is long-running; the Sunday digest
     names it too;
  c. no file: not paused, and the mirror the cloud reads is removed;
  g. a corrupt record (bad JSON locally, or a corrupt mirror in the cloud)
     still pauses and says NAMED STOP [PBS_FILL_RECORD_CORRUPT]: never
     "not paused";
  d. while paused the Almanac upload step renders nothing (a voiced script
     waits); with no pause the same call renders it;
  e. not paused, `hold --pid` takes the fill's own flock (a fill run started
     now steps aside) and lets it go when that pid ends; paused, it takes
     nothing;
  f. the whisper.cpp model is looked up outside ~/Library/Caches (a disk
     clean-up empties that) and the shared ~/.cache/whisper copy is reused.
"""
import contextlib
import fcntl
import importlib
import subprocess
import time
import datetime as dt
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["OWNER_HANDLE"] = "owner"

import pbs_pause as PB  # noqa: E402
import publish_floor as PF  # noqa: E402
import digest as DG  # noqa: E402

fails: list[str] = []
CORRUPT = "PBS_FILL_RECORD_CORRUPT"


def check(ok, msg):
    if not ok:
        fails.append(msg)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


class FakeGH:
    def __init__(self, open_issue=False):
        self.created, self.closed = [], []
        self.open = open_issue

    def __call__(self, cmd, capture_output=True, text=True):
        a, out = cmd[1:], ""
        if a[:2] == ["issue", "list"]:
            ch = a[a.index("--search") + 1].split()[0]
            out = json.dumps([{"number": 1, "body": f"<!-- publish-floor:{ch} -->"}] if self.open else [])
        elif a[:2] == ["issue", "create"]:
            self.created.append(a[a.index("--title") + 1])
        elif a[:2] == ["issue", "close"]:
            self.closed.append(a[a.index("--comment") + 1])
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()


def empty_feed(cid):
    return []                                   # nothing public: a breach on both channels


def floor_run(root: Path, gh: FakeGH) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        PF.check(now=NOW, feed=empty_feed, runner=gh, root=root)
    return buf.getvalue()


def setup(age_days: float | None) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    fill = root / "home" / "library-fill.active"
    if age_days is not None:
        fill.parent.mkdir(parents=True)
        fill.write_text(json.dumps({"started": (NOW - dt.timedelta(days=age_days)).isoformat(),
                                    "expected_end": "2026-12-01", "reason": "private words never mirrored"}))
    PB.mirror(PB.read_local(fill), root)        # what the Mac's gate pushes
    return root, fill, td


# a. a fresh pause
root, fill, td = setup(3)
j = PB.judge(PB.read_local(fill), NOW)
check(j["paused"] and "Paused for the Peace Be Still library fill since Sun 15 Nov 2026" in j["line"],
      f"(a) a 3-day-old fill file did not pause: {j}")
mirror = (root / PB.MIRROR_REL).read_text()
check("private words" not in mirror, "(a) the fill file's reason reached the public repo mirror")
gh = FakeGH(open_issue=True)
out = floor_run(root, gh)
check(not gh.created and "STOPPED" not in out, f"(a) a STOPPED alarm fired while paused: {gh.created} {out}")
check(out.count("Paused for the Peace Be Still library fill since") == 2,
      f"(a) the daily line did not say Paused for both channels: {out}")
check(len(gh.closed) == 2 and all("Paused for the Peace Be Still" in c for c in gh.closed),
      f"(a) an open STOPPED issue was not closed with the pause line: {gh.closed}")
td.cleanup()

# b. a long fill (30 days): still paused, still named, the alarm stays quiet
root, fill, td = setup(30)
j = PB.judge(PB.read_local(fill), NOW)
check(j["paused"], f"(b) a 30-day-old fill file no longer pauses the Mac jobs: {j}")
check("since Mon 19 Oct 2026, 30 days" in j["line"] and "still paused until the fill finishes" in j["line"],
      f"(b) a 30-day pause is not named with its start, days and long-running note: {j['line']}")
r = subprocess.run([sys.executable, str(HERE.parent / "pbs_pause.py"), "gate"],
                   env=dict(os.environ, PBS_FILL_FILE=str(fill), PBS_FILL_MIRROR=str(root / "m.json")),
                   capture_output=True, text=True, timeout=30)
check(r.returncode == PB.PAUSED_EXIT and PB.CODE in r.stdout,
      f"(b) the gate let a long-running fill voice and render: rc {r.returncode} {r.stdout}{r.stderr}")
gh = FakeGH(open_issue=True)
out = floor_run(root, gh)
check(not gh.created and "STOPPED" not in out.replace("STOPPED issue", ""),
      f"(b) a 30-day pause fired the STOPPED alarm: {gh.created} {out}")
check(out.count("30 days") >= 2, f"(b) the floor line did not name the 30-day pause: {out}")
dl = "\n".join(DG.pause_lines(NOW, root))
check("Paused for the Peace Be Still library fill since" in dl and "30 days" in dl,
      f"(b) the Sunday digest does not name the pause: {dl!r}")
td.cleanup()

# c. no file: not paused, mirror removed
root, fill, td = setup(3)
PB.mirror(PB.read_local(root / "absent"), root)
check(not (root / PB.MIRROR_REL).exists(), "(c) the mirror outlived the fill file")
check(not PB.judge(PB.read_local(root / "absent"), NOW)["paused"], "(c) no fill file still pauses")
check(not PB.repo_status(root, NOW)["paused"], "(c) no mirror still pauses the cloud")
check(DG.pause_lines(NOW, root) == [], "(c) the digest names a pause that is not on")
td.cleanup()

# g. a corrupt record pauses, loudly
root, fill, td = setup(3)
fill.write_text("{not json")
j = PB.judge(PB.read_local(fill), NOW)
check(j["paused"] and CORRUPT in j["line"],
      f"(g) a corrupt fill file did not pause loudly: {j}")
fill.write_text(json.dumps({"reason": "no started"}))
j = PB.judge(PB.read_local(fill), NOW)
check(j["paused"] and CORRUPT in j["line"], f"(g) a fill file with no started did not pause loudly: {j}")
(root / PB.MIRROR_REL).write_text("{half a mirr")
j = PB.repo_status(root, NOW)
check(j["paused"] and CORRUPT in j["line"], f"(g) a corrupt mirror read as not paused in the cloud: {j}")
gh = FakeGH()
out = floor_run(root, gh)
check(not gh.created and CORRUPT in out, f"(g) a corrupt mirror un-paused the floor alarm or hid itself: {out}")
td.cleanup()

# d. no Almanac render while paused (loop/whisper_upload.render_ready)
sys.path.insert(0, str(HERE.parent.parent / "visuals"))
import whisper_upload as WU  # noqa: E402


class St:
    def __init__(self):
        self.notes, self.works = [], []

    def note(self, m):
        self.notes.append(m)

    def work(self, m):
        self.works.append(m)


td = tempfile.TemporaryDirectory()
fill = Path(td.name) / "library-fill.active"
fill.write_text(json.dumps({"started": dt.datetime.now(UTC).isoformat()}))
orig_ready = WU.WL.ready_to_render
WU.WL.ready_to_render = lambda c=None: ["neville-x-01"]
calls: list[str] = []
os.environ["PBS_FILL_FILE"] = str(fill)
st = St()
n = WU.render_ready(st, renderer=lambda s: calls.append(s) or 1)
check(n == 0 and not calls, f"(d) an Almanac render ran while paused for the fill: {calls}")
check(any("PAUSED_FOR_PBS_FILL" in x and "neville-x-01" in x for x in st.notes),
      f"(d) the paused night did not name the voiced episode it left: {st.notes}")
fill.unlink()
st = St()
WU.render_ready(st, renderer=lambda s: calls.append(s) or 1)
check(calls == ["neville-x-01"], f"(d) with no pause the voiced episode was not rendered: {calls}")
WU.WL.ready_to_render = orig_ready

# e. the hold on the fill's lock
lock = Path(td.name) / "library-fill.lock"
env = dict(os.environ, PBS_FILL_FILE=str(fill), PBS_FILL_LOCK=str(lock), PBS_HOLD_POLL="0.1")
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
holder = subprocess.Popen([sys.executable, str(HERE.parent / "pbs_pause.py"), "hold", "--pid", str(sleeper.pid)],
                          env=env, stdout=subprocess.PIPE, text=True)


def fill_run_gets_lock() -> bool:
    with lock.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


deadline = time.time() + 10
while time.time() < deadline and not (lock.exists() and not fill_run_gets_lock()):
    time.sleep(0.1)
check(lock.exists() and not fill_run_gets_lock(),
      "(e) a fill run could take its lock while a How We Know night held it")
sleeper.kill()
sleeper.wait()
try:
    holder.wait(timeout=10)
except subprocess.TimeoutExpired:
    holder.kill()
    fails.append("(e) the hold outlived the night's pid")
check(fill_run_gets_lock(), "(e) the fill's lock stayed held after the night ended")
fill.write_text(json.dumps({"started": dt.datetime.now(UTC).isoformat()}))
r = subprocess.run([sys.executable, str(HERE.parent / "pbs_pause.py"), "hold", "--pid", str(os.getpid())],
                   env=env, capture_output=True, text=True, timeout=20)
check(r.returncode == 0 and "stays the fill's" in r.stdout,
      f"(e) while paused the hold did not leave the lock to the fill: {r.stdout}{r.stderr}")
os.environ.pop("PBS_FILL_FILE", None)
td.cleanup()

# f. the whisper.cpp model outside ~/Library/Caches
with tempfile.TemporaryDirectory() as h:
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = h
    os.environ.pop("HWK_WHISPER_MODEL", None)
    sys.path.insert(0, str(HERE.parent.parent / "voice"))
    import pronounce as PR  # noqa: E402
    m = importlib.reload(PR).WHISPER_MODEL
    check("Library/Caches" not in str(m), f"(f) the whisper model still defaults into ~/Library/Caches: {m}")
    shared = Path(h) / ".cache/whisper/ggml-small.en.bin"
    shared.parent.mkdir(parents=True)
    with shared.open("wb") as fh:
        fh.truncate(487_614_201)           # sparse: the real file's size, no disk
    m = importlib.reload(PR).WHISPER_MODEL
    check(m == shared, f"(f) the shared ~/.cache/whisper model was not reused: {m}")
    if old_home is not None:
        os.environ["HOME"] = old_home

if fails:
    print("FAIL test_pbs_pause")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_pbs_pause: a fill pauses voice/render and the STOPPED alarm at any age (30 days "
      "still paused and named, digest too); no file, no pause; a corrupt record pauses loudly")
