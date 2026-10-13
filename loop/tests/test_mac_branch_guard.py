"""The Mac lanes refuse to act off main - driven, not asserted.

2026-10-13: the Mac checkout sat on fix/breaker-resets-in-draft after PR #189
merged. Every lane committed "Mac state" on that branch, `push` sent the local
`main` ref instead of HEAD, four commits never reached main, and the 23:00
batch ran 39 commits behind - it would have voiced the stale versions of 13
reopened scripts. loop/mac_sync.py now refuses off main (pull, push, guard)
and bin/batch-session.sh runs `checkout_guard` before the night begins.

In a throwaway origin + clone (nothing touches this repository's git):
  a. on main and current -> guard passes;
  b. origin moves on -> guard fast-forwards, then passes, HEAD == origin/main;
  c. on another branch -> guard exits 3 with a MAC_NOT_ON_MAIN stop record;
     push refuses and commits NOTHING; pull refuses;
  d. detached HEAD -> refused the same way;
  e. the REAL bin/batch-session.sh, phases stubbed but the guard NOT, on a
     non-main branch -> exit 3, no phase ran, stop recorded; back on main ->
     the night runs every phase;
  f. MAC_NOT_ON_MAIN / MAC_BEHIND_MAIN are classified needs_human and the
     digest counts them as Mac stops.
Hard-fails if it ran zero cases.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
TMP = Path(tempfile.mkdtemp(prefix="mac-branch-guard-"))
fails: list[str] = []
cases = 0


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


def check(cond, msg):
    if not cond:
        fails.append(msg)


origin, cloud, mac = TMP / "origin.git", TMP / "cloud", TMP / "mac"
sh(TMP, "git", "init", "-q", "--bare", "-b", "main", str(origin))
sh(TMP, "git", "clone", "-q", str(origin), str(cloud))
for repo in (cloud,):
    sh(repo, "git", "config", "user.email", "t@t"); sh(repo, "git", "config", "user.name", "t")
(cloud / "loop" / "state" / "stops").mkdir(parents=True)
(cloud / "loop" / "state" / "ledger.json").write_text('{"v": 1}\n')
(cloud / "notes.md").write_text("a\n")
sh(cloud, "git", "add", "-A"); sh(cloud, "git", "commit", "-q", "-m", "base")
sh(cloud, "git", "push", "-q", "origin", "main")
sh(TMP, "git", "clone", "-q", str(origin), str(mac))
sh(mac, "git", "config", "user.email", "t@t"); sh(mac, "git", "config", "user.name", "t")

STOPS = TMP / "stops"
ENV = {**os.environ, "MAC_SYNC_REPO": str(mac), "LOOP_STOPS_DIR": str(STOPS)}
PY = sys.executable


def guard():
    return subprocess.run([PY, str(LOOP / "mac_sync.py"), "guard", "--lane", "mac-batch"],
                          env=ENV, text=True, capture_output=True)


def stop_codes():
    return [json.loads(p.read_text()).get("code") for p in STOPS.glob("*-mac-batch.json")] \
        if STOPS.exists() else []


def head(repo, ref="HEAD"):
    return sh(repo, "git", "rev-parse", ref).stdout.strip()


# -- a. on main, current -> passes ----------------------------------------
cases += 1
r = guard()
check(r.returncode == 0, f"(a) guard refused a current main: {r.stdout}{r.stderr}")
check(stop_codes() == [], f"(a) a passing guard wrote a stop: {stop_codes()}")

# -- b. origin moves on -> fast-forward, then pass ------------------------
cases += 1
(cloud / "notes.md").write_text("a\nb\n")
sh(cloud, "git", "commit", "-qam", "cloud moves on"); sh(cloud, "git", "push", "-q", "origin", "main")
r = guard()
check(r.returncode == 0, f"(b) guard refused instead of fast-forwarding: {r.stdout}{r.stderr}")
check(head(mac) == head(cloud), "(b) after the guard HEAD is not origin/main")

# -- c. another branch -> refused, nothing committed ----------------------
cases += 1
sh(mac, "git", "checkout", "-q", "-b", "fix/merged-long-ago")
before = head(mac)
r = guard()
check(r.returncode == 3, f"(c) guard did not refuse a non-main branch (rc {r.returncode}): {r.stdout}")
check("MAC_NOT_ON_MAIN" in r.stdout and "fix/merged-long-ago" in r.stdout,
      f"(c) the refusal does not name the stop and branch: {r.stdout!r}")
check("MAC_NOT_ON_MAIN" in stop_codes(), f"(c) no MAC_NOT_ON_MAIN stop record: {stop_codes()}")
(mac / "loop" / "state" / "ledger.json").write_text('{"v": "mac"}\n')
os.environ["MAC_SYNC_REPO"] = str(mac)
sys.path.insert(0, str(LOOP))
import mac_sync                                           # noqa: E402
ok, msg = mac_sync.push(["loop/state/ledger.json"], "x: Mac state")
check(not ok and "refused" in msg, f"(c) push off main did not refuse: {ok} {msg}")
check(head(mac) == before, "(c) push off main COMMITTED - the stranding defect is back")
ok, msg = mac_sync.pull()
check(not ok and "not 'main'" in msg, f"(c) pull off main did not refuse: {ok} {msg}")
sh(mac, "git", "checkout", "-q", "--", "loop/state/ledger.json")

# -- d. detached HEAD -> refused ------------------------------------------
cases += 1
sh(mac, "git", "checkout", "-q", "--detach", "main")
r = guard()
check(r.returncode == 3 and "detached HEAD" in r.stdout, f"(d) detached HEAD not refused: {r.stdout!r}")
sh(mac, "git", "checkout", "-q", "fix/merged-long-ago")

# -- e. the REAL batch script refuses off main, runs on main -------------
STUBS = TMP / "stubs.sh"
STUBS.write_text(r'''
L() { echo "$*" >> "$BATCH_TEST_LOG"; }
phase_selfheal(){ L selfheal; }
phase_survey(){ L survey; pending_audio=""; pending_render=""; pending_plan=""; }
phase_prepare(){ L prepare; }
phase_idle(){ return 0; }
hold_awake(){ :; }
phase_narrate(){ L narrate; }
phase_render(){ L render; }
phase_lengthen(){ L lengthen; }
phase_captions(){ L captions; CAPRC=0; }
shelve_shorts(){ L shelve; }
harvest_footage(){ L harvest; }
phase_report(){ L report; }
report_incomplete_night(){ L report_incomplete; }
''')


def night(name):
    d = TMP / name
    d.mkdir()
    env = {k: v for k, v in ENV.items() if k != "XPC_SERVICE_NAME"}
    env.update({"BATCH_NOW": "2026-10-13T23:00", "BATCH_PROGRESS": str(d / "p.json"),
                "BATCH_LOCK": str(d / "batch.lock"), "BATCH_TEST_STUBS": str(STUBS),
                "BATCH_TEST_LOG": str(d / "phases.log"), "BATCH_RENDERS_DIR": str(d / "r")})
    r = subprocess.run(["bash", str(ROOT / "bin" / "batch-session.sh")], env=env,
                       text=True, capture_output=True, timeout=120)
    log = (d / "phases.log").read_text().split() if (d / "phases.log").exists() else []
    return r, log


cases += 1
for p in STOPS.glob("*"):
    p.unlink()
r, log = night("e_branch")
check(r.returncode == 3, f"(e) the batch ran off main (rc {r.returncode}): {r.stdout[-400:]}")
check(log == [], f"(e) phases ran off main: {log}")
check("MAC_NOT_ON_MAIN" in stop_codes(), f"(e) the batch's refusal left no stop record: {stop_codes()}")
cases += 1
sh(mac, "git", "checkout", "-q", "main")
r, log = night("e_main")
check(r.returncode == 0, f"(e) the batch refused on main (rc {r.returncode}): {r.stdout[-400:]}{r.stderr[-400:]}")
check(log[:1] == ["selfheal"] and log[-1:] == ["report"], f"(e) the night did not run on main: {log}")

# -- f. classification -----------------------------------------------------
cases += 1
pol = json.loads((LOOP / "stop_policy.json").read_text())
for code in ("MAC_NOT_ON_MAIN", "MAC_BEHIND_MAIN"):
    check(code in pol["needs_human"], f"(f) {code} is not needs_human in stop_policy.json")
import digest                                             # noqa: E402
check({"MAC_NOT_ON_MAIN", "MAC_BEHIND_MAIN"} <= digest.MAC_CODES, "(f) digest.MAC_CODES lacks the guard's codes")
src = (ROOT / "bin" / "batch-session.sh").read_text()
check("checkout_guard\nBP begin\n" in src, "(f) batch-session.sh no longer runs checkout_guard before BP begin")

if cases == 0:
    fails.append("ran zero cases")
if fails:
    print("FAIL test_mac_branch_guard:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print(f"OK the Mac lanes refuse to act off main: {cases} case(s)")
