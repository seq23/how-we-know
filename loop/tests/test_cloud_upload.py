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

import ledger, quota, r2, upload as up, publish as P, backfill, common

# ---- redirect every piece of persistent state into the sandbox -------------
(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
ledger.LEDGER = TMP / "state" / "ledger.json"
ledger.LEDGER.write_text(json.dumps({"published": [], "queued": [],
                                     "updated": None}))
quota.STATE = TMP / "state" / "quota.json"
backfill.LOOP = TMP
common.STOPS = TMP / "state" / "stops"

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

        # -- 7. nothing shelved is a named stop, not a green no-op ---------
        examined += 1
        r = run("""
rc = 0
try:
    cloud_upload.run(limit=4)
except SystemExit as e:
    rc = e.code
print("RC", rc)
""", dict(base, R2_LOCAL_DIR=str(tmp / "empty-shelf")), tmp)
        if "RC 3" not in r.stdout:
            fails.append("an empty shelf did not produce a NAMED STOP "
                         f"(exit 3): {r.stdout.strip()[-300:]}")
        if "NOTHING_SHELVED" not in (r.stdout + r.stderr):
            fails.append("the empty-shelf stop is not named NOTHING_SHELVED")

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

import quota, r2, upload as up, publish as P, shorts_lane as SL, common

(TMP / "state" / "stops").mkdir(parents=True, exist_ok=True)
SL.LEDGER = TMP / "state" / "shorts_ledger.json"
# Reset per scenario. Each subprocess is an independent run, and a ledger left
# behind by the previous one silently changes which named stop the next one
# takes — an exhausted-quota test that actually exercised "nothing shelved".
SL.LEDGER.write_text(json.dumps({"published": [], "updated": None}))
quota.STATE = TMP / "state" / "quota.json"
common.STOPS = TMP / "state" / "stops"

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
        if "RC 3" not in r.stdout or "NO_SHORTS_SHELVED" not in (r.stdout + r.stderr):
            fails.append("a Short shelved WITHOUT its .short.json receipt was "
                         f"treated as publishable: {r.stdout.strip()[-300:]}")

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
