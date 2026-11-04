"""After a normal Mac night and its push, the Mac checkout is clean - proven in a real repo.

WHAT HAPPENED (CONFIRMED 2026-11-01). `git status` in the Mac checkout showed
21 changes the Mac's own stages wrote and nothing ever committed: stop records
of the pov-repair stage (no lane push named them), stops a refused night wrote
for an earlier week, loop/state/stops/owner_action.json (the footage lane
pushed loop/state/owner_action.json, a path that does not exist), new
audio/<slug>/beats.json (the caption commit stages tracked files only), the
Shorts cutter's renders/<slug>-final.mp4.footage.json records, and
voice/pronounce.py's write-only audio/<slug>/pronunciation.json log. The
nightly housekeeping flagged the checkout every night.

WHAT THIS PROVES, in a throwaway origin + Mac clone carrying this repo's real
.gitignore and loop/mac_sync.py:
  1. After the Mac writes one file of every class above and runs
     `mac_sync.py push --lane batch <the lane's own stop>` - exactly what
     bin/batch-session.sh phase_report runs - `git status --porcelain` is
     EMPTY, and origin holds every tracked-class file.
  2. The batch's footage-lane push names the owner_action path the stage
     really writes (loop/common.py _owner_action_path).
  3. owner_action.json, now pushed by both hosts, merges three-way on a
     rebase: the Mac's CLEAR of one stage survives and the cloud's new stage
     is kept (a union would resurrect the cleared row).
Hard-fails if fewer than six Mac-written files were exercised.

NEGATIVE PROOF (2026-11-01): `+ mac_owned_touched()` removed from the push
set in loop/mac_sync.py main() -> case 1 fails naming the six leftover paths;
the .gitignore line for pronunciation.json removed -> case 1 names it;
merge_owner_action replaced by a plain union -> case 3 fails ("cleared stage
resurrected"). Restored -> green.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
import mac_sync as MS                                     # noqa: E402

fails: list[str] = []


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


def write(repo: Path, rel: str, doc) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1) + "\n")


tmp = Path(tempfile.mkdtemp(prefix="mac-push-clean-"))
origin, cloud, mac = tmp / "origin.git", tmp / "cloud", tmp / "mac"
sh(tmp, "git", "init", "-q", "--bare", "-b", "main", str(origin))
sh(tmp, "git", "clone", "-q", str(origin), str(cloud))
for name in ("mac_sync.py", "common.py", "held.py"):
    (cloud / "loop").mkdir(parents=True, exist_ok=True)
    shutil.copy(LOOP / name, cloud / "loop" / name)
shutil.copy(ROOT / ".gitignore", cloud / ".gitignore")
# What origin already tracks: last week's pov-repair stop and an owner_action
# row the Mac's footage lane will clear tonight.
write(cloud, "loop/state/stops/2026-W42-pov-repair.json", {"code": "POV_ALL_TRACED", "n": 62})
write(cloud, "loop/state/stops/owner_action.json",
      {"imagery-harvest-mac": {"code": "DELEGATED_HARVEST_STALE", "at": "2026-10-15"}})
write(cloud, "audio/old-episode/beats.json", [{"i": 0}])
for repo in (cloud,):
    sh(repo, "git", "config", "user.email", "t@t"); sh(repo, "git", "config", "user.name", "t")
sh(cloud, "git", "add", "-A"); sh(cloud, "git", "commit", "-q", "-m", "base")
sh(cloud, "git", "push", "-q", "origin", "main")
sh(tmp, "git", "clone", "-q", str(origin), str(mac))
sh(mac, "git", "config", "user.email", "t@t"); sh(mac, "git", "config", "user.name", "t")

# ---- a normal night on the Mac: one file of every class the stages write.
wk = MS.week_id()
night = {
    "channel/imagery/shot_lists.json": {"ep": {"subjects": ["snailfish"]}},
    f"loop/state/stops/{wk}-pov-repair.json": {"code": "POV_ALL_TRACED", "n": 63},
    "loop/state/stops/2026-W42-pov-repair.json": {"code": "POV_ALL_TRACED", "n": 64},
    "loop/state/stops/2026-W43-mac-batch.json": {"code": "PULL_FAILED"},
    "loop/state/stops/owner_action.json": {},
    "audio/new-episode/beats.json": [{"i": 0, "narration": "x"}],
    "renders/new-episode-final.mp4.footage.json": {"segments": []},
}
for rel, doc in night.items():
    write(mac, rel, doc)
write(mac, "audio/new-episode/pronunciation.json", {"slug": "new-episode"})
(mac / "audio/new-episode/0000.wav").write_bytes(b"RIFF")          # ignored media
(mac / "renders/new-episode-final.mp4").write_bytes(b"\0")          # ignored media

r = subprocess.run([sys.executable, str(mac / "loop" / "mac_sync.py"), "push", "--lane", "batch",
                    f"loop/state/stops/{wk}-mac-batch.json"],
                   cwd=mac, text=True, capture_output=True)
if r.returncode != 0:
    fails.append(f"1: mac_sync push failed: {r.stdout} {r.stderr}")
left = [ln for ln in sh(mac, "git", "status", "--porcelain", "--untracked-files=all").stdout.splitlines() if ln]
if left:
    fails.append(f"1: the Mac checkout is not clean after the push: {left}")
on_origin = set(sh(mac, "git", "ls-tree", "-r", "--name-only", "origin/main").stdout.split())
missing = sorted(p for p in night if p not in on_origin)
if missing:
    fails.append(f"1: origin lacks Mac-written tracked-class files: {missing}")
if "audio/new-episode/pronunciation.json" in on_origin:
    fails.append("1: the write-only pronunciation log was committed")

# ---- 2. the footage lane's push names the path the stage really writes.
batch = (ROOT / "bin" / "batch-session.sh").read_text()
real = "loop/state/stops/owner_action.json"   # loop/common.py _owner_action_path(), unredirected
harvest_push = [ln for ln in batch.splitlines() if "harvest_runs.json" in ln and "owner_action" in ln]
if not harvest_push or real not in harvest_push[0]:
    fails.append(f"2: the footage lane's push does not name {real}: {harvest_push}")

# ---- 3. owner_action.json merges three-way when both hosts changed it.
base = {"a": {"at": "1"}, "b": {"at": "1"}}
up = {"a": {"at": "1"}, "b": {"at": "1"}, "c": {"at": "2"}}     # cloud adds c
macd = {"b": {"at": "1"}}                                         # Mac clears a
m = MS.TWO_WRITER_MERGE["loop/state/stops/owner_action.json"](up, macd, base)
if "a" in m:
    fails.append(f"3: cleared stage resurrected by the merge: {m}")
if "c" not in m or "b" not in m:
    fails.append(f"3: the merge lost a stage: {m}")

if len(night) < 6:
    fails.append("Rule 0: fewer than six Mac-written files were exercised")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: a Mac push leaves the checkout clean ({len(night)} Mac-written files "
      f"reached origin, the log stayed ignored); owner_action merges three-way")
