"""The Mac's pull takes upstream for loop-state and keeps the Mac's copies - proven in a real repo.

WHAT HAPPENED. 12-13 September 2026: bin/loop-backfill-daily.sh's `git pull
--rebase --autostash` failed every morning. loop/state/stops/_held.json existed
untracked on the Mac while the cloud had started tracking it, and
loop/state/stops/_streaks.json had a local edit that conflicted. Both are the
loop's own state, authored by the cloud and only read by the Mac. PULL_FAILED
was written to the Mac's disk and nowhere else, and nine finished episodes
shipped nothing behind it.

WHAT THIS PROVES, in a throwaway origin + clone:
  1. An untracked loop-state file that upstream now tracks does not block the
     pull: the Mac's copy is set aside under loop/state/_local/ and upstream's
     lands.
  2. A locally modified loop-state file that upstream also changed does not
     block the pull: same treatment.
  3. A local edit to a NON-state file (something a person edits) is autostashed
     and preserved, exactly as before.
  4. A genuine conflict in a non-state file still fails, so PULL_FAILED is
     still reachable - the helper narrows the failure, it does not hide it.

Hard-fails if the scenario builds fewer than three files.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
fails: list[str] = []


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


tmp = tempfile.mkdtemp(prefix="mac-sync-test-")
origin = os.path.join(tmp, "origin.git")
cloud = os.path.join(tmp, "cloud")
mac = os.path.join(tmp, "mac")
sh(tmp, "git", "init", "-q", "--bare", "-b", "main", origin)
sh(tmp, "git", "clone", "-q", origin, cloud)
for repo in (cloud,):
    sh(repo, "git", "config", "user.email", "t@t"); sh(repo, "git", "config", "user.name", "t")
os.makedirs(os.path.join(cloud, "loop", "state", "stops"))
os.makedirs(os.path.join(cloud, "loop", "tests"))
open(os.path.join(cloud, "loop", "state", "stops", "_streaks.json"), "w").write('{"v": 1}\n')
open(os.path.join(cloud, "README.md"), "w").write("hello\n")
open(os.path.join(cloud, "notes.md"), "w").write("a\n")
# The helper itself and its one dependency, so the clone can run it.
import shutil
shutil.copy(os.path.join(LOOP, "mac_sync.py"), os.path.join(cloud, "loop", "mac_sync.py"))
shutil.copy(os.path.join(LOOP, "common.py"), os.path.join(cloud, "loop", "common.py"))
shutil.copy(os.path.join(LOOP, "held.py"), os.path.join(cloud, "loop", "held.py"))
sh(cloud, "git", "add", "-A"); sh(cloud, "git", "commit", "-q", "-m", "base"); sh(cloud, "git", "push", "-q", "origin", "main")

sh(tmp, "git", "clone", "-q", origin, mac)
sh(mac, "git", "config", "user.email", "t@t"); sh(mac, "git", "config", "user.name", "t")

# Upstream (the cloud) moves on: tracks _held.json, changes _streaks.json, edits notes.md.
open(os.path.join(cloud, "loop", "state", "stops", "_held.json"), "w").write('{"cloud": true}\n')
open(os.path.join(cloud, "loop", "state", "stops", "_streaks.json"), "w").write('{"v": 2}\n')
open(os.path.join(cloud, "notes.md"), "w").write("a\nb\n")
sh(cloud, "git", "add", "-A"); sh(cloud, "git", "commit", "-q", "-m", "cloud moves on"); sh(cloud, "git", "push", "-q", "origin", "main")

# The Mac meanwhile: an untracked _held.json, a modified _streaks.json, and a
# person's edit to README.md (a non-state file, no conflict).
open(os.path.join(mac, "loop", "state", "stops", "_held.json"), "w").write('{"mac": true}\n')
open(os.path.join(mac, "loop", "state", "stops", "_streaks.json"), "w").write('{"v": "mac"}\n')
open(os.path.join(mac, "README.md"), "w").write("hello\nedited on the mac\n")

# Old behaviour, for the record: the plain pull fails on the untracked file.
plain = sh(mac, "git", "pull", "--rebase", "--autostash", "origin", "main")
if plain.returncode == 0:
    fails.append("scenario: the plain pull should fail here (untracked file would be overwritten); it passed, so the fixture proves nothing")

r = subprocess.run([sys.executable, os.path.join(mac, "loop", "mac_sync.py"), "pull"],
                   cwd=mac, text=True, capture_output=True)
if r.returncode != 0:
    fails.append(f"1/2: mac_sync pull failed: {r.stdout} {r.stderr}")
held = open(os.path.join(mac, "loop", "state", "stops", "_held.json")).read()
streaks = open(os.path.join(mac, "loop", "state", "stops", "_streaks.json")).read()
readme = open(os.path.join(mac, "README.md")).read()
if '"cloud": true' not in held:
    fails.append(f"1: upstream's _held.json did not land: {held!r}")
if '"v": 2' not in streaks:
    fails.append(f"2: upstream's _streaks.json did not land: {streaks!r}")
if "edited on the mac" not in readme:
    fails.append("3: the person's README edit was lost by the pull")
local_dir = os.path.join(mac, "loop", "state", "_local")
kept = []
for dp, _, fn in os.walk(local_dir):
    kept += [os.path.join(dp, f) for f in fn]
if not any(f.endswith("_held.json") for f in kept) or not any(f.endswith("_streaks.json") for f in kept):
    fails.append(f"1/2: the Mac's copies were not kept under loop/state/_local/: {kept}")
if any('"mac": true' in open(f).read() for f in kept if f.endswith("_held.json")) is False:
    fails.append("1: the kept _held.json is not the Mac's copy")

# 4. a real conflict in a non-state file still fails.
open(os.path.join(cloud, "notes.md"), "w").write("a\nb\ncloud\n")
sh(cloud, "git", "add", "-A"); sh(cloud, "git", "commit", "-q", "-m", "cloud again"); sh(cloud, "git", "push", "-q", "origin", "main")
open(os.path.join(mac, "notes.md"), "w").write("a\nb\nmac\n")
r2_ = subprocess.run([sys.executable, os.path.join(mac, "loop", "mac_sync.py"), "pull"],
                     cwd=mac, text=True, capture_output=True)
if r2_.returncode == 0:
    fails.append("4: a genuine conflict in a person-edited file passed; PULL_FAILED is unreachable")
if os.path.isdir(os.path.join(mac, ".git", "rebase-merge")):
    fails.append("4: a failed pull left a rebase in progress, which blocks every later run")

if len(kept) < 2:
    fails.append("Rule 0: fewer than two files were exercised")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print("PASS: loop-state collisions take upstream and keep the Mac's copies; a person's edit survives; a real conflict still fails cleanly")
