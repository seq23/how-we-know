"""A quota hold in the tags backfill is a green note; an inert run is still red.

THE INCIDENT. loop-reach on main went red on 6 and 7 Nov 2026 with
TAGS_BACKFILL_INERT. The lane had stopped before its first video on purpose
("keeping 3400 units for today's uploads; the rest run tomorrow"), so it
rewrote nothing and confirmed nothing, and the inert check read that
deliberate hold as "did nothing for no reason". Tomorrow's scheduled run
retries it, so it is a note, never a red main.

WHAT THIS PROVES, in a scratch stops dir with the YouTube calls stubbed:
  1. quota reserved before the first video -> exit 0, stop QUOTA_DEFERRED,
     self_resolving, with every held slug named;
  2. quota available but nothing rewritten or confirmed (videos.list returns
     nothing) -> still exit 3, TAGS_BACKFILL_INERT, needs_human.
Hard-fails if it examines zero cases.
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
ROOT = LOOP.parent
SLUGS = ["01-hold-a", "02-hold-b", "03-hold-c"]


def run(remaining: int) -> tuple[subprocess.CompletedProcess, dict]:
    scratch = tempfile.mkdtemp(prefix="tags-hold-")
    env = dict(os.environ, LOOP_STOPS_DIR=scratch, LOOP_DRY_RUN="1",
               GITHUB_STEP_SUMMARY=os.path.join(scratch, "summary.md"),
               GITHUB_OUTPUT=os.path.join(scratch, "output.txt"))
    code = f"""
import sys; sys.path.insert(0, {str(LOOP)!r})
import tags_backfill as tb, quota, ytmeta
tb.ytmeta.live_videos = lambda: [{{"slug": s, "video_id": "v" + s}} for s in {SLUGS!r}]
tb._shorts_live = lambda: []
tb.up.load_credentials = lambda cfg: {{"ok": True}}
tb.up.access_token = lambda creds: "t"
tb.wanted_for_episode = lambda slug: (["tag"], ["#tag"])
tb.ytmeta.get_video = lambda token, vid: None
quota.remaining = lambda: {remaining}
quota.spend = lambda units, lane: None
quota.report = lambda: "stub quota"
tb.run()
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, env=env, cwd=ROOT, timeout=120)
    recs = list(Path(scratch).glob("*-tags-backfill.json"))
    return r, (json.loads(recs[0].read_text()) if recs else {})


fails: list[str] = []
examined = 0

# 1. a deliberate quota hold is green and names what it holds
r, rec = run(remaining=0)
examined += 1
out = (r.stdout + r.stderr).strip()[-400:]
if r.returncode != 0:
    fails.append(f"quota hold exited {r.returncode}, not 0: {out}")
if rec.get("code") != "QUOTA_DEFERRED" or rec.get("disposition") != "self_resolving":
    fails.append(f"quota hold recorded {rec.get('code')}/{rec.get('disposition')}, "
                 f"want QUOTA_DEFERRED/self_resolving")
held = (rec.get("detail") or {}).get("deferred") or rec.get("held_items") or []
if sorted(held) != SLUGS:
    fails.append(f"quota hold did not name every held slug: {held!r}")

# 2. a run that did nothing for no reason is still red
r, rec = run(remaining=100_000)
examined += 1
out = (r.stdout + r.stderr).strip()[-400:]
if r.returncode != 3:
    fails.append(f"inert run exited {r.returncode}, not 3: {out}")
if rec.get("code") != "TAGS_BACKFILL_INERT":
    fails.append(f"inert run recorded {rec.get('code')}, want TAGS_BACKFILL_INERT")

if examined == 0:
    fails.append("examined zero cases")
for f in fails:
    print("FAIL", f)
print(f"{examined} case(s), {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
