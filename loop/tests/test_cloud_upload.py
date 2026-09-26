"""The cloud upload lane, proven without credentials and without touching YouTube.

Every assertion here is negative-first: the state is broken on purpose, the
failure is shown to return, and then it is restored and shown to pass again. A
validator that only ever sees the working case cannot tell you it still works.

WHAT IS PROVEN

  1. loop/r2.py takes a NAMED STOP naming EXACTLY the variable that is absent,
     with each one removed individually — not a crash, not a silent skip.
  2. LOOP_DRY_RUN=1 refuses to load credentials AND refuses every write, on
     both the real backend and the stub.
  3. The whole upload lane runs end to end against the filesystem stub: it
     shelves, heads, pulls, verifies, schedules, "uploads", thumbnails, writes
     the ledger and spends the quota.
  4. The shared quota is RESERVED, not assumed: a nearly-exhausted day takes
     fewer videos, and an exhausted one takes a named stop instead of a
     half-uploaded video.
  5. Corrupt bytes on the shelf are caught by sha256 before they reach YouTube.
  6. loop/upload.py's repo-secret credential path — the one the Actions side
     depends on and which had never been exercised — is REACHABLE, and its
     absence is a named stop rather than an AttributeError.

WHY SUBPROCESSES. A loop stage ends in `sys.exit`, and the exit code IS the
contract (0 work, 1 failure, 3 named stop). Asserting on the code means running
each scenario as its own process.

NOTHING HERE CAN REACH THE REAL CHANNEL OR THE REAL BUCKET. R2_LOCAL_DIR wins
over credentials inside `r2.require()`, and every YouTube entry point is
replaced with a recorder before the lane is called. A test in this repo has
already uploaded a real video to a real channel once (MAV4PF056RA, 2026-09-01);
that is why the substitutions happen before the import of the lane, not inside
it.
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
PY = sys.executable

# A slug that is really in research/publish_order.json and really has a script,
# so build_payload composes a real body. The bytes are fake; the metadata is not.
SLUG = None


def _pick_slug() -> str:
    order = json.loads((ROOT / "research" / "publish_order.json").read_text())
    for q in order["queue"]:
        if (ROOT / "scripts" / f"{q['slug']}.md").exists():
            return q["slug"]
    raise SystemExit("FAIL: no queued episode has a script — this test cannot "
                     "reach what it governs")


HARNESS = '''
import json, os, sys
from pathlib import Path
LOOP = Path(%(loop)r); ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
TMP = Path(os.environ["TEST_TMP"])

import ledger, quota, r2, upload as up, publish as P, backfill, common, arming

# ---- redirect every piece of persistent state into the sandbox -------------
(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
ledger.LEDGER = TMP / "state" / "ledger.json"
ledger.LEDGER.write_text(json.dumps({"published": [], "queued": [],
                                     "updated": None}))
quota.STATE = TMP / "state" / "quota.json"
backfill.LOOP = TMP
common.STOPS = TMP / "state" / "stops"
# loop/arming.py's own EVIDENCE file, or a "good run" scenario here would
# write PROOF of a real upload into the actual repo state — exactly the kind
# of test writing to production this file's own docstring warns about.
arming.EVIDENCE = TMP / "state" / "lane_evidence.json"

# ---- every irreversible YouTube call, replaced by a recorder ---------------
CALLS = []
up.load_credentials = lambda cfg: {"access_token": "fake", "source": "test"}
up.access_token = lambda creds: "fake-token"
def _upload(token, payload, video):
    CALLS.append(("insert", payload["snippet"]["title"], Path(video).name,
                  Path(video).stat().st_size))
    return "VID%%d" %% len(CALLS)
up.resumable_upload = _upload
P.set_privacy = lambda t, v, p, publish_at=None: CALLS.append(
    ("privacy", v, p, publish_at))
P.read_status = lambda t, v: {"privacy": "private"}
backfill.set_thumbnail = lambda t, v, img: CALLS.append(
    ("thumb", v, Path(img).stat().st_size))
backfill.time.sleep = lambda s: None

import cloud_upload
'''


def snippet(body: str) -> str:
    return HARNESS % {"loop": str(LOOP)} + body


def run(body: str, env_extra: dict, tmp: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("LOOP_DRY_RUN", None)
    env["TEST_TMP"] = str(tmp)
    env["LOOP_NO_DOTENV"] = "1"
    # loop/arming.py gates a SCHEDULED run of an unarmed lane behind a named
    # stop. This harness is testing the lane's own upload/quota/ledger logic,
    # which is exactly what a workflow_dispatch run (the one that proves a
    # lane and arms it) is for — so every scenario here simulates one, the
    # same as a human running `gh workflow run ... ` once by hand.
    env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
    env.update(env_extra)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     dir=tmp) as fh:
        fh.write(snippet(body))
        path = fh.name
    return subprocess.run([PY, path], capture_output=True, text=True,
                          cwd=ROOT, env=env)


def shelve(shelf_dir: Path, slug: str, render_bytes: bytes,
           thumb_bytes: bytes) -> None:
    """Put a fake render and thumbnail on the stub shelf, sidecars and all."""
    sys.path.insert(0, str(LOOP))
    import r2                                              # noqa: PLC0415
    b = r2.LocalBackend(shelf_dir)
    src = shelf_dir / "_src"
    src.mkdir(exist_ok=True)
    (src / "r.mp4").write_bytes(render_bytes)
    (src / "t.jpg").write_bytes(thumb_bytes)
    b.put(src / "r.mp4", r2.render_key(slug))
    b.put(src / "t.jpg", r2.thumb_key(slug))


# ---------------------------------------------------------------------------

def check() -> list[str]:
    fails, examined = [], 0
    slug = _pick_slug()

    with tempfile.TemporaryDirectory(prefix="cloud-upload-test-") as td:
        tmp = Path(td)
        shelf = tmp / "shelf"

        # -- 1. each required variable, absent on its own -------------------
        # Proven ONE AT A TIME. Removing all of them at once would pass even if
        # the message only ever named the first.
        base = {"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "tok"}
        for var in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
            examined += 1
            env = dict(base)
            env[var] = ""
            r = run("""
import r2
# An interactive `wrangler login` on the owner's Mac stands in for the API
# token, and that is correct behaviour — but it would mask the missing-token
# case here, so this scenario is run as a machine with no login: a CI runner.
r2.WRANGLER_LOGINS = ()
try:
    r2.require(env=os.environ)
    print("NO_STOP")
except r2.R2Unavailable as e:
    print("STOP", e.code, "|", e.message, "|", e.unblock)
""", env, tmp)
            out = r.stdout
            if "NO_STOP" in out:
                fails.append(f"r2.require() did not stop with {var} absent")
                continue
            if "R2_CREDENTIALS_MISSING" not in out:
                fails.append(f"{var} absent gave the wrong code: {out.strip()}")
            if var not in out:
                fails.append(f"the stop for a missing {var} does not NAME "
                             f"{var}: {out.strip()}")
            other = [v for v in base if v != var][0]
            if other in out:
                fails.append(f"the stop for a missing {var} also names "
                             f"{other}, which is present")

        # -- 1b. restored: both present, no stop ---------------------------
        examined += 1
        r = run("""
import r2
b = r2.require(env=os.environ)
print("BACKEND", b.kind)
""", dict(base, R2_LOCAL_DIR=str(shelf)), tmp)
        if "BACKEND local" not in r.stdout:
            fails.append("with the stub configured, require() did not return "
                         f"the local backend: {r.stdout.strip()} {r.stderr[-300:]}")

        # -- 2. LOOP_DRY_RUN refuses credentials AND writes ----------------
        examined += 1
        r = run("""
import r2
try:
    r2.require(env=os.environ)
    print("LOADED_CREDENTIALS_UNDER_DRY_RUN")
except r2.R2Unavailable as e:
    print("STOP", e.code)
b = r2.LocalBackend(Path(os.environ["TEST_TMP"]) / "dryshelf")
f = Path(os.environ["TEST_TMP"]) / "x.bin"; f.write_bytes(b"hello")
try:
    b.put(f, "renders/x-final.mp4")
    print("WROTE_UNDER_DRY_RUN")
except r2.R2Unavailable as e:
    print("WRITE_REFUSED", e.code)
print("ON_DISK", (Path(os.environ["TEST_TMP"]) / "dryshelf" /
                  "renders" / "x-final.mp4").exists())
""", dict(base, LOOP_DRY_RUN="1"), tmp)
        if "STOP DRY_RUN_NO_CREDENTIALS" not in r.stdout:
            fails.append("LOOP_DRY_RUN=1 did not refuse to load R2 "
                         f"credentials: {r.stdout.strip()}")
        if "WRITE_REFUSED DRY_RUN_WRITE_REFUSED" not in r.stdout:
            fails.append("LOOP_DRY_RUN=1 did not refuse a write: "
                         f"{r.stdout.strip()}")
        if "ON_DISK False" not in r.stdout:
            fails.append("LOOP_DRY_RUN=1 refused the write but the bytes "
                         "landed anyway")

        # -- 3. the whole lane, end to end, against the stub ---------------
        shelve(shelf, slug, b"\x00" * 4096, b"\xff" * 512)
        stub_env = dict(base, R2_LOCAL_DIR=str(shelf))
        examined += 1
        r = run("""
rc = 0
try:
    cloud_upload.run(limit=1)
except SystemExit as e:
    rc = e.code
led = json.loads(ledger.LEDGER.read_text())
q = json.loads(quota.STATE.read_text())
print("RC", rc)
print("CALLS", json.dumps(CALLS))
print("LEDGER", json.dumps(led["published"]))
print("QUOTA", json.dumps(q))
""", stub_env, tmp)
        out = r.stdout
        if "RC 0" not in out:
            fails.append(f"the lane did not exit 0 on a good run: "
                         f"{out.strip()[-600:]} {r.stderr[-600:]}")
        for want, why in (('"insert"', "no videos.insert was attempted"),
                          ('"privacy"', "the privacy/publishAt call was not made"),
                          ('"thumb"', "the thumbnail was not set")):
            if want not in out:
                fails.append(f"end-to-end: {why}")
        try:
            rows = json.loads(out.split("LEDGER ", 1)[1].split("\n")[0])
        except (IndexError, json.JSONDecodeError):
            rows = []
        if len(rows) != 1:
            fails.append(f"end-to-end: expected 1 ledger row, got {len(rows)}")
        else:
            row = rows[0]
            if row["slug"] != slug:
                fails.append("end-to-end: the ledger recorded the wrong slug")
            if not row.get("scheduled_publish_at"):
                fails.append("end-to-end: the ledger row carries no "
                             "scheduled_publish_at — the slot was not assigned")
            if row.get("privacy") != "private":
                fails.append("end-to-end: the ledger row is not private; this "
                             "lane must never publish on upload")
            if row.get("note", "").split(":")[0] != "cloud-upload":
                fails.append("end-to-end: the ledger row does not say which "
                             "lane uploaded it")
        # 4. the quota was actually spent, under this lane's name
        try:
            q = json.loads(out.split("QUOTA ", 1)[1].split("\n")[0])
        except (IndexError, json.JSONDecodeError):
            q = {}
        if q.get("by_lane", {}).get("cloud-upload") != 1700:
            fails.append(f"end-to-end: the cloud lane did not spend its 1700 "
                         f"units through loop/quota.py: {q}")

        # -- 4b. an exhausted quota is a named stop, not an upload ---------
        # AND IT IS GREEN. Run 33521586490 failed this job daily for a
        # condition whose own unblock text was "nothing to do" — see
        # loop/stop_policy.json. The stop must still be named, still be
        # printed, still refuse to upload; only the exit code changed.
        examined += 1
        r = run("""
import quota as Q
Q.STATE.parent.mkdir(parents=True, exist_ok=True)
Q.STATE.write_text(json.dumps({"day": Q._today(), "spent": 9999,
                               "by_lane": {"other": 9999}}))
rc = 0
try:
    cloud_upload.run(limit=4)
except SystemExit as e:
    rc = e.code
print("RC", rc)
print("CALLS", json.dumps(CALLS))
""", stub_env, tmp)
        out = r.stdout + r.stderr
        if "RC 0" not in r.stdout:
            fails.append("an exhausted quota did not exit 0 as a SELF-RESOLVING "
                         f"stop: {r.stdout.strip()[-400:]}")
        if "QUOTA_EXHAUSTED" not in out:
            fails.append("the exhausted-quota stop is not named QUOTA_EXHAUSTED")
        if "NAMED STOP" not in out:
            fails.append("the exhausted-quota stop printed no NAMED STOP "
                         "banner — exiting 0 without one is a silent skip")
        if "SELF-RESOLVING" not in out:
            fails.append("the exhausted-quota stop did not declare itself "
                         "self-resolving, so a reader cannot tell why a stop "
                         "left the job green")
        if '"insert"' in r.stdout:
            fails.append("THE IMPORTANT ONE: the lane uploaded a video it "
                         "could not afford. Quota is reserved, not assumed.")

        # -- 4c. a partial allowance takes fewer, not none -----------------
        examined += 1
        shelve(shelf, slug, b"\x00" * 4096, b"\xff" * 512)
        r = run("""
import quota as Q
Q.STATE.parent.mkdir(parents=True, exist_ok=True)
# 9600 - 400 headroom = 3400 usable: exactly two whole videos.
Q.STATE.write_text(json.dumps({"day": Q._today(), "spent": 6200,
                               "by_lane": {"other": 6200}}))
print("AFFORDABLE", Q.videos_affordable(4))
""", stub_env, tmp)
        if "AFFORDABLE 2" not in r.stdout:
            fails.append("loop/quota.py did not derate a partial day to two "
                         f"videos: {r.stdout.strip()}")

        # -- 5. corrupt bytes on the shelf never reach YouTube -------------
        examined += 1
        r = run("""
import r2
b = r2.LocalBackend(Path(os.environ["R2_LOCAL_DIR"]))
key = r2.render_key(%(slug)r)
obj = Path(os.environ["R2_LOCAL_DIR"]) / key
obj.write_bytes(b"\\x01" * 4096)      # same length, different bytes
dst = Path(os.environ["TEST_TMP"]) / "pulled.mp4"
try:
    cloud_upload.fetch(b, key, dst)
    print("ACCEPTED_CORRUPT")
except ValueError as e:
    print("REJECTED", str(e)[:80])
""" % {"slug": slug}, stub_env, tmp)
        if "REJECTED" not in r.stdout:
            fails.append("a shelved object whose bytes no longer match its "
                         f"sha256 was accepted: {r.stdout.strip()}")

        # -- 5b. restored: the correct bytes are accepted again ------------
        examined += 1
        shelve(shelf, slug, b"\x00" * 4096, b"\xff" * 512)
        r = run("""
import r2
b = r2.LocalBackend(Path(os.environ["R2_LOCAL_DIR"]))
dst = Path(os.environ["TEST_TMP"]) / "pulled2.mp4"
cloud_upload.fetch(b, r2.render_key(%(slug)r), dst)
print("ACCEPTED", dst.stat().st_size)
""" % {"slug": slug}, stub_env, tmp)
        if "ACCEPTED 4096" not in r.stdout:
            fails.append("after restoring the correct bytes the same fetch "
                         f"still failed: {r.stdout.strip()} {r.stderr[-300:]}")

        # -- 6. the repo-secret credential path, which CI depends on -------
        # loop/upload.py reads .secrets/ first and only falls through to the
        # environment when there is NO OAuth client on disk — which is every
        # GitHub runner. Point the client file at nothing to reproduce a runner,
        # and the env vars must be picked up.
        examined += 1
        r = run("""
import tokens as auth
auth.CLIENT_FILE = Path(os.environ["TEST_TMP"]) / "no-such-client.json"
import importlib, upload as U
U = importlib.reload(U)
U.auth.CLIENT_FILE = auth.CLIENT_FILE
cfg = U.config()
creds = U.load_credentials(cfg)
print("SOURCE", (creds or {}).get("source"))
print("HAS_REFRESH", bool((creds or {}).get("refresh_token")))
print("CLIENT_ID", (creds or {}).get("client_id"))
""", dict(base,
          YT_OAUTH_CLIENT_JSON=json.dumps(
              {"installed": {"client_id": "cid.apps.googleusercontent.com",
                             "client_secret": "csecret"}}),
          YT_OAUTH_REFRESH_TOKEN="1//fake-refresh"), tmp)
        if "SOURCE env" not in r.stdout:
            fails.append("THE ACTIONS-SIDE CREDENTIAL PATH IS INERT: with no "
                         "OAuth client on disk, loop/upload.py did not read "
                         f"YT_OAUTH_* from the environment: {r.stdout.strip()} "
                         f"{r.stderr[-300:]}")
        if "CLIENT_ID cid.apps.googleusercontent.com" not in r.stdout:
            fails.append("the env credential path did not unwrap the "
                         "'installed' block of the OAuth client JSON")
        if "HAS_REFRESH True" not in r.stdout:
            fails.append("the env credential path dropped the refresh token")

        # -- 6b. absent env vars are a NAMED STOP, not an AttributeError ---
        examined += 1
        r = run("""
import tokens as auth
auth.CLIENT_FILE = Path(os.environ["TEST_TMP"]) / "no-such-client.json"
import importlib, upload as U
U = importlib.reload(U)
U.auth.CLIENT_FILE = auth.CLIENT_FILE
cfg = U.config()
creds = U.load_credentials(cfg)
code, msg, unblock = U.credential_stop(creds, cfg)
print("CREDS", creds)
print("CODE", code)
print("NAMES", "YT_OAUTH_CLIENT_JSON" in unblock,
      "YT_OAUTH_REFRESH_TOKEN" in unblock)
""", dict(base, YT_OAUTH_CLIENT_JSON="", YT_OAUTH_REFRESH_TOKEN=""), tmp)
        if "CREDS None" not in r.stdout:
            fails.append("with no client on disk and no env vars, "
                         f"load_credentials did not return None: {r.stdout.strip()}")
        if "CODE OAUTH_MISSING" not in r.stdout:
            fails.append("an absent YouTube credential is not named "
                         f"OAUTH_MISSING: {r.stdout.strip()}")
        if "NAMES True True" not in r.stdout:
            fails.append("the OAUTH_MISSING stop does not name both repo "
                         "secrets the workflow needs")

        # -- 7. nothing shelved is a NAMED stop, not a silent no-op --------
        # It exits 0, not 3, since 2026-09-04: NOTHING_SHELVED is classified
        # self-resolving in loop/stop_policy.json, because the Mac's nightly
        # batch pushes what it renders and an empty shelf is also the finished
        # state once the whole queue is uploaded. Paging a human daily for
        # that spends the one notification channel the loop has on the outcome
        # that needs nobody. What this test still guarantees - and what
        # actually matters - is that the stop is NAMED and reaches the log;
        # a green no-op that said nothing would still fail below.
        examined += 1
        r = run("""
rc = 0
try:
    cloud_upload.run(limit=4)
except SystemExit as e:
    rc = e.code
print("RC", rc)
""", dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf")), tmp)
        out = r.stdout + r.stderr
        if "RC 0" not in r.stdout:
            fails.append("an empty shelf did not exit 0 as a self-resolving "
                         f"stop: {r.stdout.strip()[-300:]}")
        if "NAMED STOP" not in out:
            fails.append("the empty-shelf run printed no NAMED STOP banner — "
                         "a zero exit with no banner is the silent no-op this "
                         "scenario exists to forbid")
        if "SELF-RESOLVING" not in out.upper():
            fails.append("the empty-shelf stop did not declare itself "
                         "self-resolving, so its zero exit is unexplained")
        if "NOTHING_SHELVED" not in out:
            fails.append("the empty-shelf stop is not named NOTHING_SHELVED")

        # -- 7b/7c. an empty shelf whose QUEUE is used up is not the Mac's -
        # Run 35738742706 (2026-09-22) paged "the Mac is not pushing" when
        # every one of the 34 queued episodes was already in the ledger and
        # four freshly authored scripts sat in loop/render_queue.json where
        # the Mac's batch never looks. Both states are reproduced here through
        # the real lane: every queued slug is written into the ledger, and
        # the hand-off file is a fixture with or without a stranded row.
        seed_ledger = """
import batch_queue
# The promotion-hold register is ALWAYS a fixture. It used to fall back to
# the real loop/promotion_holds.json when a scenario said HOLDS = None, and
# the 2026-09-23 scenario below read "today's" real register - until the real
# Saturday gate decided all four holds on 2026-09-26 (4eaed4e) and emptied
# it. Read BEFORE the ledger is seeded, not after.
batch_queue.PROMOTION_HOLDS = TMP / "promotion_holds.json"
batch_queue.PROMOTION_HOLDS.write_text(json.dumps({"holds": HOLDS}))
held_now = set(batch_queue.promotion_holds())
# The queue as it stood on the scenario's day. A slug the real Saturday gate
# has since PROMOTED into a publish order was in no publish order then; left
# in, it would read as "queued with scripts/<slug>.md", i.e. already decided.
_real_queued = batch_queue.queued_slugs
batch_queue.queued_slugs = lambda: [s for s in _real_queued()
                                    if s not in NOT_YET_QUEUED]
led = json.loads(ledger.LEDGER.read_text())
# A HELD SLUG IS NEVER "ALREADY PUBLISHED" IN THIS SIMULATION, whatever
# batch_queue.queued_slugs() happens to contain today. Confirmed 2026-09-25:
# a fresh, unrelated mining pass produced a candidate whose auto-generated
# slug collided with an already-held script (why-deep-sea-creatures), so
# "everything currently queued is published" briefly marked a genuinely
# unpromoted, unpublished hold as published — a fact this fixture invented,
# not one the real ledger ever recorded. A hold's own status is decided by
# loop/promotion_holds.json, never by a coincidence in the queue.
led["published"] = [{"slug": s, "video_id": "V" + str(i), "question": s,
                     "privacy": "private"}
                    for i, s in enumerate(batch_queue.queued_slugs())
                    if s not in held_now]
ledger.LEDGER.write_text(json.dumps(led))
cloud_upload.RENDER_QUEUE = TMP / "render_queue.json"
cloud_upload.RENDER_QUEUE.write_text(json.dumps({"items": ROWS}))
if RUNWAY is not None:
    cloud_upload.cadence.runway = lambda per_week=None: RUNWAY
rc = 0
try:
    cloud_upload.run(limit=4)
except SystemExit as e:
    rc = e.code
print("RC", rc)
"""
        stranded = "a-script-authored-but-never-queued"
        examined += 1
        r = run(f"ROWS = [{{'slug': {stranded!r}, 'status': 'queued'}}]\n"
                "HOLDS = []\nNOT_YET_QUEUED = []\nRUNWAY = None\n"
                + seed_ledger,
                dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf-7b")), tmp)
        out = r.stdout + r.stderr
        if "[AUTHORED_NOT_QUEUED]" not in out:
            fails.append("a used-up queue with a stranded authored script was "
                         "not diagnosed as AUTHORED_NOT_QUEUED: "
                         f"{out.strip()[-400:]}")
        if stranded not in out:
            fails.append("the AUTHORED_NOT_QUEUED stop does not NAME the "
                         "stranded slug")
        if "[NOTHING_SHELVED]" in out or "push-to-r2" in out:
            fails.append("with every queued episode already uploaded, the "
                         "stop still blames the Mac's push (NOTHING_SHELVED "
                         "/ push-to-r2). That was the false page on run "
                         "35738742706")
        if "RC 3" not in r.stdout:
            fails.append("a stranded authored script did not reach a human "
                         "(exit 3). Time cannot fix it, so its first report "
                         f"must page: {r.stdout.strip()[-200:]}")

        examined += 1
        r = run("ROWS = [{'slug': 'gone', 'status': 'dropped'}]\n"
                "HOLDS = []\nNOT_YET_QUEUED = []\nRUNWAY = None\n"
                + seed_ledger,
                dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf-7c")), tmp)
        out = r.stdout + r.stderr
        if "[PUBLISH_QUEUE_UPLOADED]" not in out:
            fails.append("a fully uploaded queue with nothing stranded was not "
                         f"named PUBLISH_QUEUE_UPLOADED: {out.strip()[-400:]}")
        if "RC 0" not in r.stdout or "SELF-RESOLVING" not in out.upper():
            fails.append("a finished upload queue did not exit 0 as a "
                         "self-resolving stop")
        if "push-to-r2" in out:
            fails.append("a finished upload queue still tells the owner to "
                         "run bin/push-to-r2.sh")

        # -- 7d. THE 2026-09-23 STATE, through the real lane -------------
        # Every queued episode uploaded; the four scripts the Monday lane
        # wrote on 2026-09-21 still in loop/render_queue.json as `queued`;
        # the hold register of that day naming them; runway ok. The
        # owner decided these wait for her promotion decision, so this must
        # be a GREEN named stop that names all four - not AUTHORED_NOT_QUEUED
        # paging her, not NOTHING_SHELVED blaming the Mac, not a silent 0.
        today = ["how-do-scientists-know-so-much",
                 "how-do-scientists-know-how-old-something-is",
                 "why-deep-sea-creatures",
                 "how-do-scientists-know-about-other-galaxies"]
        # THE REGISTER AS IT STOOD ON 2026-09-23, frozen verbatim
        # (git show 4eaed4e^:loop/promotion_holds.json), not the live file.
        FROZEN_HOLDS = json.loads(
            (HERE / "fixtures" / "promotion_holds_2026-09-23.json")
            .read_text())["holds"]
        if sorted(h["slug"] for h in FROZEN_HOLDS) != sorted(today):
            fails.append("the frozen 2026-09-23 hold register does not hold "
                         "exactly the four 2026-09-21 scripts")
        examined += 1
        r = run(f"ROWS = {[{'slug': s_, 'status': 'queued'} for s_ in today]!r}\n"
                f"HOLDS = {FROZEN_HOLDS!r}\nNOT_YET_QUEUED = {today!r}\n"
                "RUNWAY = {'level': 'ok', 'weeks_remaining': 6.0, "
                "'message': 'fixture: 6.0 weeks of queue at 4/week'}\n"
                + seed_ledger,
                dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf-7d")), tmp)
        out = r.stdout + r.stderr
        if "[SCRIPTS_AWAITING_PROMOTION]" not in out:
            fails.append("today's state (queue uploaded, four held scripts, "
                         "runway ok) was not SCRIPTS_AWAITING_PROMOTION: "
                         f"{out.strip()[-400:]}")
        if "RC 0" not in r.stdout:
            fails.append("today's held-for-promotion state did not exit 0 - it "
                         "would page the owner daily on a decision she has: "
                         f"{r.stdout.strip()[-200:]}")
        if "SELF-RESOLVING" not in out:
            fails.append("the held-for-promotion stop did not declare itself "
                         "self-resolving (the Saturday gate decides every "
                         "hold since 2026-09-25), so its zero exit is "
                         "unexplained")
        if "NEEDS A SECRET ONLY SHE HOLDS" in out:
            fails.append("the held-for-promotion stop still says it waits on "
                         "the owner; nothing about a hold is hers to decide")
        if "NAMED STOP" not in out:
            fails.append("the held-for-promotion run printed no NAMED STOP "
                         "banner - a silent exit 0 is what Rule 0 forbids")
        for s_ in today:
            if s_ not in out:
                fails.append(f"the held-for-promotion stop does not name {s_}")
        # THE STOP BANNER ONLY, not the whole output. backfill.library_pending()
        # logs a routine, correct, per-candidate "not shelved - run
        # bin/push-to-r2.sh" note for ANY queued slug that genuinely has no
        # render yet - which why-deep-sea-creatures now legitimately is, since
        # its slug also collided with a freshly mined, unrelated candidate
        # (2026-09-25). That note is true and harmless; it is not the
        # diagnosis. A blanket substring search over the full output could not
        # tell the two apart, so it checks only the NAMED STOP banner, where
        # the actual conclusion lives.
        banner = out[out.find("NAMED STOP"):]
        if "[AUTHORED_NOT_QUEUED]" in banner or "push-to-r2" in banner:
            fails.append("held scripts were still reported as stranded, or "
                         "blamed on the Mac's push, IN THE STOP BANNER ITSELF "
                         f"(routine per-candidate logging is expected and is "
                         f"not this): {banner.strip()[:400]}")

        # Same state, runway critical. Since 2026-09-25 (owner's rule:
        # nothing waits on her) the held scripts are decided by the Saturday
        # gate, not by her, so this is automated policy: named, exit 0, and
        # naming every held slug. The critical runway itself is RUNWAY_CRITICAL
        # on the Sunday lane, which is red.
        examined += 1
        r = run(f"ROWS = {[{'slug': s_, 'status': 'queued'} for s_ in today]!r}\n"
                f"HOLDS = {FROZEN_HOLDS!r}\nNOT_YET_QUEUED = {today!r}\n"
                "RUNWAY = {'level': 'critical', 'weeks_remaining': 1.0, "
                "'message': 'fixture: 1.0 week'}\n"
                + seed_ledger,
                dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf-7e")), tmp)
        out = r.stdout + r.stderr
        if ("[SCRIPTS_AWAITING_PROMOTION_RUNWAY_CRITICAL]" not in out
                or "RC 0" not in r.stdout
                or "SELF-RESOLVING" not in out
                or "Saturday" not in out
                or not all(h in out for h in today)):
            fails.append("held scripts with a critical runway were not the "
                         "named, green SCRIPTS_AWAITING_PROMOTION_RUNWAY_"
                         "CRITICAL naming every held slug and the Saturday "
                         f"gate: {out.strip()[-300:]}")

    if examined == 0:
        fails.append("examined ZERO scenarios — this test cannot reach what "
                     "it governs")
    print(f"inspected {examined} cloud-upload scenario(s), episode {slug}")
    return fails




# ---------------------------------------------------------------------------
# The Shorts lane. Same shape, different schedule — and that difference is the
# thing most worth guarding, because inheriting the episode slot would put every
# Short in the worst part of its own day and nothing would look broken.

SHORTS_HARNESS = '''
import json, os, sys
from pathlib import Path
LOOP = Path(%(loop)r); ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
TMP = Path(os.environ["TEST_TMP"])

import quota, r2, upload as up, publish as P, shorts_lane as SL, common, arming

(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
SL.LEDGER = TMP / "state" / "shorts_ledger.json"
# Reset per scenario. Each subprocess is an independent run, and a ledger left
# behind by the previous one silently changes which named stop the next one
# takes — an exhausted-quota test that actually exercised "nothing shelved".
SL.LEDGER.write_text(json.dumps({"published": [], "updated": None}))
quota.STATE = TMP / "state" / "quota.json"
common.STOPS = TMP / "state" / "stops"
# See the matching comment in the episode HARNESS above.
arming.EVIDENCE = TMP / "state" / "lane_evidence.json"

CALLS = []
up.load_credentials = lambda cfg: {"access_token": "fake", "source": "test"}
up.access_token = lambda creds: "fake-token"
def _upload(token, payload, video):
    CALLS.append(("insert", payload["snippet"]["title"], Path(video).name))
    return "SHORT%%d" %% len(CALLS)
up.resumable_upload = _upload
P.set_privacy = lambda t, v, p, publish_at=None: CALLS.append(
    ("privacy", v, p, publish_at))
P.read_status = lambda t, v: {"privacy": "private"}
SL.time.sleep = lambda s: None

import shorts_cloud
'''


def shorts_run(body: str, env_extra: dict, tmp: Path):
    env = dict(os.environ)
    env.pop("LOOP_DRY_RUN", None)
    env["TEST_TMP"] = str(tmp)
    env["LOOP_NO_DOTENV"] = "1"
    # See the matching comment in run() above — this harness exercises the
    # lane's own logic, which needs a simulated workflow_dispatch to get past
    # loop/arming.py's gate on an unarmed lane.
    env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
    env.update(env_extra)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     dir=tmp) as fh:
        fh.write(SHORTS_HARNESS % {"loop": str(LOOP)} + body)
        path = fh.name
    return subprocess.run([PY, path], capture_output=True, text=True,
                          cwd=ROOT, env=env)


def shelve_short(shelf_dir: Path, slug: str) -> None:
    sys.path.insert(0, str(LOOP))
    import r2                                              # noqa: PLC0415
    b = r2.LocalBackend(shelf_dir)
    src = shelf_dir / "_src"
    src.mkdir(exist_ok=True)
    (src / "s.mp4").write_bytes(b"\x00" * 2048)
    (src / "s.json").write_text(json.dumps({"slug": slug, "beats": []}))
    b.put(src / "s.mp4", r2.short_key(slug))
    b.put(src / "s.json", r2.short_receipt_key(slug))


def check_shorts() -> list[str]:
    fails, examined = [], 0
    slug = _pick_slug()
    base = {"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "tok"}

    with tempfile.TemporaryDirectory(prefix="shorts-cloud-test-") as td:
        tmp = Path(td)
        shelf = tmp / "shelf"
        shelve_short(shelf, slug)
        env = dict(base, R2_LOCAL_DIR=str(shelf))

        # -- the lane runs end to end --------------------------------------
        examined += 1
        r = shorts_run("""
rc = 0
try:
    shorts_cloud.run(limit=1)
except SystemExit as e:
    rc = e.code
led = json.loads(SL.LEDGER.read_text())
print("RC", rc)
print("CALLS", json.dumps(CALLS))
print("LEDGER", json.dumps(led["published"]))
print("QUOTA", json.dumps(json.loads(quota.STATE.read_text())))
""", env, tmp)
        out = r.stdout
        if "RC 0" not in out:
            fails.append(f"the Shorts lane did not exit 0 on a good run: "
                         f"{out.strip()[-500:]} {r.stderr[-500:]}")
        try:
            rows = json.loads(out.split("LEDGER ", 1)[1].split("\n")[0])
        except (IndexError, json.JSONDecodeError):
            rows = []
        if len(rows) != 1:
            fails.append(f"Shorts: expected 1 ledger row, got {len(rows)}")
        else:
            row = rows[0]
            if row.get("privacy") != "private":
                fails.append("Shorts: the row is not private; this lane must "
                             "never publish on upload")
            # THE ASSERTION THAT MATTERS. A Short must land in the EVENING
            # window, on a Short day — not on the episode's 10:00 Sun/Tue slot.
            from datetime import datetime
            from zoneinfo import ZoneInfo
            t = datetime.fromisoformat(
                row["scheduled_publish_at"].replace("Z", "+00:00")
            ).astimezone(ZoneInfo("America/Chicago"))
            # The rung set is cadence-derived (loop/shorts_lane.slot_ladder),
            # so assert against the ladder rather than a frozen day list -
            # otherwise raising the Shorts cadence breaks a test that is
            # supposed to be protecting the EVENING WINDOW, not the day count.
            import shorts_lane as _sl                        # noqa: PLC0415
            import cadence as _cad                           # noqa: PLC0415
            rungs = set(_sl.slot_ladder(_cad.shorts_effective()))
            if not 18 <= t.hour <= 21:
                fails.append(f"THE IMPORTANT ONE: the Short is scheduled for "
                             f"{t.hour}:00 Central, outside the 18:00-21:00 "
                             f"evening peak. The episode slot is the worst "
                             f"part of a Short's day.")
            if (t.weekday(), t.hour) not in rungs:
                fails.append(f"the Short landed on weekday {t.weekday()} at "
                             f"{t.hour}:00, which is not a rung of the "
                             f"{_cad.shorts_effective()}/week evening ladder "
                             f"{sorted(rungs)}")
        try:
            q = json.loads(out.split("QUOTA ", 1)[1].split("\n")[0])
        except (IndexError, json.JSONDecodeError):
            q = {}
        if q.get("by_lane", {}).get("shorts-cloud") != 1700:
            fails.append(f"the Shorts lane did not reserve and spend its 1700 "
                         f"units through loop/quota.py: {q}")

        # -- an exhausted quota stops it, it does not upload ---------------
        examined += 1
        shelve_short(shelf, slug)
        r = shorts_run("""
import quota as Q
Q.STATE.parent.mkdir(parents=True, exist_ok=True)
Q.STATE.write_text(json.dumps({"day": Q._today(), "spent": 9999,
                               "by_lane": {"other": 9999}}))
rc = 0
try:
    shorts_cloud.run(limit=2)
except SystemExit as e:
    rc = e.code
print("RC", rc)
print("CALLS", json.dumps(CALLS))
""", env, tmp)
        out = r.stdout + r.stderr
        if "RC 0" not in r.stdout or "QUOTA_EXHAUSTED" not in out:
            fails.append("an exhausted quota did not take a self-resolving "
                         f"QUOTA_EXHAUSTED stop in the Shorts lane: "
                         f"{r.stdout.strip()[-300:]}")
        if "NAMED STOP" not in out or "SELF-RESOLVING" not in out:
            fails.append("the Shorts quota stop left the job green without "
                         "saying so — that is a silent skip, not a named stop")
        if '"insert"' in r.stdout:
            fails.append("the Shorts lane uploaded a Short it could not afford")

        # -- a Short with no receipt is not publishable --------------------
        # The receipt is the only record of which beats were used and where the
        # caption band was cropped. A cut without one cannot be audited, so it
        # must not be treated as shelved.
        examined += 1
        naked = tmp / "naked-shelf"
        sys.path.insert(0, str(LOOP))
        import r2 as R2M                                    # noqa: PLC0415
        b = R2M.LocalBackend(naked)
        (tmp / "s.mp4").write_bytes(b"\x00" * 2048)
        b.put(tmp / "s.mp4", R2M.short_key(slug))
        r = shorts_run("""
rc = 0
try:
    shorts_cloud.run(limit=1)
except SystemExit as e:
    rc = e.code
print("RC", rc)
""", dict(base, R2_LOCAL_DIR=str(naked)), tmp)
        # THE CODE CHANGED, AND THAT IS THE POINT. This used to expect
        # NO_SHORTS_SHELVED, which conflated two states that look identical
        # from an empty selection and are not: "nothing has been cut yet",
        # which the Mac's next push resolves and which is now classified
        # self-resolving, and "a cut IS on the shelf and cannot be proved
        # credited", which is a broken push that will look the same tomorrow.
        # Only the second may be loud, and only the second is asserted here.
        out = r.stdout + r.stderr
        if "RC 3" not in r.stdout or "SHORTS_SHELVED_BUT_UNVERIFIED" not in out:
            fails.append("a Short shelved WITHOUT its .short.json receipt was "
                         f"treated as publishable: {r.stdout.strip()[-300:]}")
        if "NO_SHORTS_SHELVED" in out:
            fails.append("an unverified cut on the shelf reported an EMPTY "
                         "shelf — the self-resolving label would then be worn "
                         "by a broken push, which is the inert-lane defect")

        # -- the attribution gate refuses to shelve on a V14 failure -------
        # Broken on purpose: V14 is replaced with a failing result and the push
        # must refuse. This is the one rule the pipeline may not break, and the
        # Linux runner cannot re-check it, so the gate is the whole guarantee.
        examined += 1
        r = shorts_run("""
import validate as V, r2 as R
class _R:
    name = "V14 shorts-attribution"; examined = 1
    failures = ["credit 'NOAA' is not on screen"]
V.v14_shorts_attribution = lambda: _R()
try:
    R.push_shorts(R.LocalBackend(Path(os.environ["TEST_TMP"]) / "gate"),
                  [%(slug)r])
    print("SHELVED_UNVERIFIED")
except R.R2Unavailable as e:
    print("REFUSED", e.code)
""" % {"slug": slug}, env, tmp)
        if "REFUSED SHORTS_UNVERIFIED" not in r.stdout:
            fails.append("THE IMPORTANT ONE: push_shorts shelved a Short with "
                         f"a FAILING attribution validator: {r.stdout.strip()} "
                         f"{r.stderr[-300:]}")

        # -- restored: with V14 and V15 green the same push proceeds -------
        examined += 1
        r = shorts_run("""
import validate as V, r2 as R
class _R:
    def __init__(s, n): s.name = n; s.examined = 1; s.failures = []
V.v14_shorts_attribution = lambda: _R("V14 shorts-attribution")
V.v15_shorts_caption_crop = lambda: _R("V15 shorts-caption-crop")
out = R.push_shorts(R.LocalBackend(Path(os.environ["TEST_TMP"]) / "gate2"),
                    [%(slug)r])
print("PASSED_GATE", json.dumps(out["verified"]))
""" % {"slug": slug}, env, tmp)
        if "PASSED_GATE" not in r.stdout:
            fails.append("with both validators green the push still refused: "
                         f"{r.stdout.strip()} {r.stderr[-300:]}")

    if examined == 0:
        fails.append("examined ZERO Shorts scenarios")
    print(f"inspected {examined} shorts-cloud scenario(s)")
    return fails


if __name__ == "__main__":
    f = check() + check_shorts()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the cloud upload lane holds, and every write it refuses "
          "to make is a named stop" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
