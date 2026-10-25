"""A Mac-state commit that conflicts with the cloud in a two-writer state file
heals on the next pull instead of wedging the Mac for good.

THE INCIDENT (#235). 21 Oct 2026 14:05: boss-os's comment watch ran
loop/comments.py on the Mac and committed loop/state/comments/ledger.json and
loop/state/stops/_streaks.json (9cba7cc). The push was rejected - the cloud
handoff lane had committed the same files - and the retry's rebase conflicted,
so push() aborted and LEFT THE COMMIT ON MAIN. Every later mac_sync pull hit
the same conflict: PULL_FAILED, "the night is refused", four nights with
nothing rendered, and the stop could not leave the Mac because pushing was
the thing failing.

WHAT THIS PROVES, with real git on throwaway repositories:
  1. The 21 Oct state (a local Mac commit + a conflicting upstream commit on
     both files) -> pull() succeeds, HEAD contains origin/main, no rebase is
     left in progress, and BOTH sides' records survive in both files.
  2. A conflict in any other file is still PULL_FAILED, with nothing left
     half-done (no rebase in progress) - the merge is for the named files only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import mac_sync as MS                                     # noqa: E402

fails: list[str] = []
examined = 0
LEDGER = "loop/state/comments/ledger.json"
STREAKS = "loop/state/stops/_streaks.json"


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, text=True, capture_output=True)


def put(repo: Path, rel: str, obj) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


def world():
    t = Path(tempfile.mkdtemp(prefix="macsync-merge-"))
    git(t, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(t, "clone", "-q", str(t / "origin.git"), "seed")
    seed = t / "seed"
    for r in (seed,):
        git(r, "config", "user.email", "t@t"); git(r, "config", "user.name", "t")
    base_ledger = {"channel_id": "C", "seen": {"c1": {"at": "1"}}, "actions": [{"id": "a1"}],
                   "channel_comments": {}, "cursors": {}, "updated": "2026-10-21T00:00:00+00:00"}
    put(seed, LEDGER, base_ledger)
    put(seed, STREAKS, {"cloud-upload": {"code": "X", "count": 1, "last_at": "2026-10-21T01:00:00+00:00"}})
    (seed / "README").write_text("base\n")
    git(seed, "add", "-A"); git(seed, "commit", "-qm", "base"); git(seed, "push", "-q", "origin", "main")
    git(t, "clone", "-q", str(t / "origin.git"), "mac")
    mac = t / "mac"
    git(mac, "config", "user.email", "m@m"); git(mac, "config", "user.name", "m")
    return t, seed, mac, base_ledger


# -- 1. the 21 Oct state heals -----------------------------------------------
t, cloud, mac, base = world()
mac_ledger = dict(base, seen={**base["seen"], "c2": {"at": "2"}},
                  actions=base["actions"] + [{"id": "a-mac"}], updated="2026-10-21T19:05:00+00:00")
put(mac, LEDGER, mac_ledger)
put(mac, STREAKS, {"cloud-upload": {"code": "X", "count": 1, "last_at": "2026-10-21T01:00:00+00:00"},
                   "pov-repair": {"code": "P", "count": 1, "last_at": "2026-10-21T04:00:00+00:00"}})
git(mac, "add", "-A"); git(mac, "commit", "-qm", "comments: Mac state")
cloud_ledger = dict(base, channel_comments={"vid1": {"id": "cc1"}},
                    actions=base["actions"] + [{"id": "a-cloud"}], updated="2026-10-21T20:00:00+00:00")
put(cloud, LEDGER, cloud_ledger)
put(cloud, STREAKS, {"cloud-upload": {"code": "X", "count": 2, "last_at": "2026-10-22T01:00:00+00:00"},
                     "handoff": {"code": "H", "count": 1, "last_at": "2026-10-22T02:00:00+00:00"}})
git(cloud, "add", "-A"); git(cloud, "commit", "-qm", "loop: handoff"); git(cloud, "push", "-q", "origin", "main")
# Precondition: a plain merge of the two commits really does conflict, so the
# rebase the old pull() ran fails exactly as it did on 21 Oct.
git(mac, "fetch", "-q", "origin", "main")
mt = git(mac, "merge-tree", "--write-tree", "--name-only", "HEAD", "origin/main")
if mt.returncode != 1 or LEDGER not in mt.stdout:
    fails.append("fixture does not reproduce the 21 Oct conflict - this test cannot reach what it governs")
os.environ["MAC_SYNC_REPO"] = str(mac)
try:
    ok, msg = MS.pull()
finally:
    os.environ.pop("MAC_SYNC_REPO", None)
examined += 1
if not ok:
    fails.append(f"the 21 Oct state still wedges the Mac: {msg}")
if git(mac, "merge-base", "--is-ancestor", "origin/main", "HEAD").returncode != 0:
    fails.append("after pull, HEAD does not contain origin/main")
if (mac / ".git" / "rebase-merge").exists() or (mac / ".git" / "rebase-apply").exists():
    fails.append("a rebase was left in progress")
led = json.loads((mac / LEDGER).read_text())
ids = [a["id"] for a in led.get("actions", [])]
for need in ("a1", "a-mac", "a-cloud"):
    if need not in ids:
        fails.append(f"comments ledger lost action {need}")
if "c2" not in led.get("seen", {}) or "vid1" not in led.get("channel_comments", {}):
    fails.append("comments ledger lost a keyed record from one side")
st = json.loads((mac / STREAKS).read_text())
if not {"pov-repair", "handoff", "cloud-upload"} <= set(st):
    fails.append(f"_streaks lost a stage: {sorted(st)}")
elif st["cloud-upload"]["count"] != 2:
    fails.append("_streaks kept the older record for a stage both wrote")

# -- 2. any other conflict is still PULL_FAILED, nothing half-done ----------
t, cloud, mac, base = world()
(mac / "README").write_text("mac edit\n"); git(mac, "commit", "-qam", "person edit")
(cloud / "README").write_text("cloud edit\n"); git(cloud, "commit", "-qam", "other edit")
git(cloud, "push", "-q", "origin", "main")
os.environ["MAC_SYNC_REPO"] = str(mac)
try:
    ok, msg = MS.pull()
finally:
    os.environ.pop("MAC_SYNC_REPO", None)
examined += 1
if ok:
    fails.append("a conflict in a person's file was merged away instead of PULL_FAILED")
if (mac / ".git" / "rebase-merge").exists() or (mac / ".git" / "rebase-apply").exists():
    fails.append("a failed pull left a rebase in progress")

print(f"inspected {examined} two-writer pull case(s)")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - a two-writer state conflict heals; anything else still stops")
