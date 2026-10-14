"""Every tracked file `loop/lengthen.py bind` writes is in the Mac's push set.

WHY (2026-10-14). The 04:00 batch ran `lengthen.py bind`: seven `pending_bind`
episodes became `full_rerender`, their old renders were recorded in
loop/state/superseded_renders.json and a stale plan was unlinked. None of it
left the Mac - the caption commit stages scripts/plans/thumbnails only and the
`mac_sync.py push` fixed list named neither state file. The caption pass then
rewrote a bound script's chapter timestamps, so origin held new script bytes
beside a stale `pending_bind` fingerprint: V49 red on main, and the cloud
upload lane unable to see renders it must refuse.

The fix: loop/mac_sync.py BIND_STATE / bind_paths() ride on every push, and
bin/batch-session.sh pushes straight after the bind. This test:

  1. runs the REAL run_bind() on a scratch tree - one full re-render, one
     splice - snapshots every file before and after, and fails on any changed
     path that git would track (not ignored in this repo) and bind_paths()
     does not name. A new write added to bind() fails here until the push
     set carries it;
  2. checks `mac_sync.py push` hands push() every bind path (behaviourally:
     push() is replaced and its paths captured);
  3. checks the batch pushes the bind before it plans, narrates or captions.

NEGATIVE PROOF (2026-10-14): removing "loop/state/superseded_renders.json"
from mac_sync.BIND_STATE fails case 1 ("bind writes
  loop/state/superseded_renders.json but mac_sync.bind_paths() does not push
  it"); restored -> green.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import durations                                              # noqa: E402
import extend                                                 # noqa: E402
import lengthen as L                                          # noqa: E402
import mac_sync                                               # noqa: E402

fails: list[str] = []
examined = 0


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


T = Path(tempfile.mkdtemp(prefix="bind-push-"))
for d in ("scripts", "loop/drafts", "plans", "audio", "renders", "captions",
          "shorts", "loop/state"):
    (T / d).mkdir(parents=True, exist_ok=True)

saved = {n: getattr(L, n) for n in ("SCRIPTS", "DRAFTS", "PLANS", "AUDIO", "RENDERS",
                                     "CAPTIONS", "STATE", "SUPERSEDED", "HOLD",
                                     "_plan_for", "_decide_mode", "renderable_slugs")}
saved_ext = (extend.AUDIO, extend.SHORTS)
saved_dur = durations.DURATIONS
L.SCRIPTS, L.DRAFTS, L.PLANS = T / "scripts", T / "loop/drafts", T / "plans"
L.AUDIO, L.RENDERS, L.CAPTIONS = T / "audio", T / "renders", T / "captions"
L.STATE = T / "loop/state/lengthen.json"
L.SUPERSEDED = T / "loop/state/superseded_renders.json"
L.HOLD = T / "loop/state/render_hold.json"
extend.AUDIO, extend.SHORTS = T / "audio", T / "shorts"
durations.DURATIONS = T / "loop/state/durations.json"

FULL, SPL = "fixture-full", "fixture-splice"
OLD = [{"heading": "Cold open", "narration": "old open"},
       {"heading": "Title card", "narration": "t"},
       {"heading": "Body", "narration": "body one", "segment": "a"}]
NEW = [{"heading": "Cold open", "narration": "new open, longer"},
       {"heading": "Extra", "narration": "a new beat"},
       {"heading": "Title card", "narration": "t"},
       {"heading": "Body", "narration": "body one", "segment": "a"}]
episodes = {}
for slug in (FULL, SPL):
    text = f"# {slug}\n\nThe new opening the cloud wrote.\n"
    (L.SCRIPTS / f"{slug}.md").write_text(text)
    (L.PLANS / f"{slug}.json").write_text(json.dumps(OLD))
    adir = L.AUDIO / slug
    adir.mkdir()
    (adir / "beats.json").write_text(json.dumps(
        [{"i": i, "narration": b["narration"]} for i, b in enumerate(OLD)]))
    for i in range(len(OLD)):
        (adir / f"{i:03d}.wav").write_bytes(b"RIFF" + bytes([i]))
    (L.RENDERS / f"{slug}-final.mp4").write_bytes(f"old cut of {slug}".encode())
    (T / "shorts" / f"{slug}-short1.mp4").write_bytes(b"short")
    episodes[slug] = {"status": "scripted", "mode": "pending_bind", "kind": "reopen",
                      "new_script_sha256": hashlib.sha256(text.encode()).hexdigest()}
L.save({"episodes": episodes}, L.STATE)
durations._save(durations.DURATIONS, {"episodes": {
    s: {"seconds": 600.0, "source": "fixture"} for s in (FULL, SPL)}})
L.SUPERSEDED.write_text("{}\n")

L._plan_for = lambda p: [dict(b) for b in NEW]                # noqa: SLF001
L.renderable_slugs = lambda: {FULL, SPL}
L._decide_mode = lambda slug, old_plan: (                     # noqa: SLF001
    ("splice", "", {"k": 1, "boundary_frames": 30, "total_frames": 90, "body_s": 3.0})
    if slug == SPL else ("full", "fixture: no sidecar", None))


def snapshot() -> dict[str, str]:
    out = {}
    for p in T.rglob("*"):
        if p.is_file():
            out[p.relative_to(T).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


before = snapshot()
try:
    rc = L.run_bind()
finally:
    after = snapshot()
    for n, v in saved.items():
        setattr(L, n, v)
    extend.AUDIO, extend.SHORTS = saved_ext
    durations.DURATIONS = saved_dur

doc = json.loads((T / "loop/state/lengthen.json").read_text())
st = {s: (r.get("status"), r.get("mode")) for s, r in doc["episodes"].items()}
check(rc == 0 and st.get(FULL) == ("full_rerender", "full")
      and st.get(SPL, (None,))[1] == "splice",
      f"fixture: run_bind did not bind one full and one splice episode: {rc} {st}")

changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
check(len(changed) >= 4, f"fixture: bind changed too few files to prove anything: {changed}")
ignored = set(subprocess.run(
    ["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT, input="\n".join(changed),
    capture_output=True, text=True).stdout.split())
tracked_writes = [p for p in changed if p not in ignored]
pushed = set(mac_sync.bind_paths(T / "loop/state/lengthen.json"))
for must in ("loop/state/lengthen.json", "loop/state/superseded_renders.json",
             f"plans/{FULL}.json", f"plans/{SPL}.json"):
    check(must in tracked_writes, f"fixture: bind did not write {must}: {tracked_writes}")
for p in tracked_writes:
    check(p in pushed, f"bind writes {p} but mac_sync.bind_paths() does not push it - "
                       f"it would stay on the Mac and origin would drift (V49, 2026-10-14)")

# 2. `mac_sync.py push --lane <any>` carries every bind path.
captured: list[list[str]] = []
saved_push, saved_argv = mac_sync.push, sys.argv
mac_sync.push = lambda paths, message: (captured.append(list(paths)) or (True, "fixture"))
sys.argv = ["mac_sync.py", "push", "--lane", "lengthen-bind"]
try:
    mac_sync.main()
finally:
    mac_sync.push, sys.argv = saved_push, saved_argv
real = set(mac_sync.bind_paths())
check(bool(captured) and real <= set(captured[0])
      and set(mac_sync.BIND_STATE) <= set(captured[0]),
      f"mac_sync push omits bind state: {sorted(real - set(captured[0] if captured else []))}")

# 3. the batch pushes the bind before anything plans, narrates or captions.
sh = (ROOT / "bin" / "batch-session.sh").read_text()
i_bind = sh.find("$PY loop/lengthen.py bind")
i_push = sh.find("loop/mac_sync.py push --lane lengthen-bind")
i_plan = sh.find("build any missing shot plan")
i_caps = sh.find("$PY loop/captions_build.py")
check(-1 not in (i_bind, i_push, i_plan, i_caps) and i_bind < i_push < i_plan < i_caps,
      f"batch-session.sh does not push the bind straight after binding "
      f"(bind={i_bind} push={i_push} plan={i_plan} captions={i_caps})")

if examined == 0:
    print("FAIL: examined nothing")
    sys.exit(1)
if fails:
    print(f"FAIL test_bind_state_is_pushed ({len(fails)}/{examined}):")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"ok test_bind_state_is_pushed: {examined} checks; bind's tracked writes "
      f"{tracked_writes} all pushed")
