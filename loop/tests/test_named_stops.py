"""Every credential-blocked lane must NAME its stop — never crash, never skip.

The failure mode this guards against is the one that looks like success: a
stage that finds no credentials, shrugs, and exits 0. That is a silent skip,
and after three weeks of it nobody remembers the channel was supposed to
publish.

So for each blocked lane this asserts the stop is *reachable and named*, by
running the real stage with the credentials deliberately unset.

Hard-fails if it examines zero lanes.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable

# stage file -> the stop code it must reach with no credentials present.
# Each of these is a legitimate halt today, and each must survive as a *named*
# halt rather than degrading into a crash or a pass.
LANES = [
    ("upload.py", ("OAUTH_MISSING", "NOTHING_RENDERED")),
    ("publish.py", ("OAUTH_MISSING", "NOTHING_PUBLISHABLE", "BREAKER_TRIPPED")),
    # OAUTH_REJECTED covers a token Google actively refuses (401/403) as
    # distinct from OAUTH_MISSING (no token on disk at all). The two need
    # different remedies: re-consent vs. first-time grant.
    ("measure.py", ("OAUTH_MISSING", "NOTHING_PUBLISHED", "OAUTH_REJECTED",
                    "NETWORK_UNREACHABLE")),
    # The reach lanes. Both write to live videos — one inserts a caption
    # track, the other rewrites the snippet of every published episode — so
    # both must refuse an absent credential by NAME rather than crashing
    # through it. CAPTIONS_SCOPE_MISSING is the force-ssl consent only the
    # owner can give; it is a legitimate halt, not a failure.
    ("captions_lane.py", ("OAUTH_MISSING", "CAPTIONS_SCOPE_MISSING",
                          "NOTHING_PUBLISHED", "NO_CAPTION_FILES")),
    ("localize.py", ("OAUTH_MISSING", "NOTHING_PUBLISHED",
                     "OPENROUTER_KEY_MISSING", "LOCALIZATIONS_UP_TO_DATE")),
]


def check() -> list[str]:
    fails, examined = [], 0
    env = dict(os.environ)
    for k in ("YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN",
              "YOUTUBE_API_KEY"):
        env.pop(k, None)
    env["LOOP_NO_DOTENV"] = "1"
    # Stripping the env vars is NOT enough isolation: .secrets/youtube_token.json
    # is still on disk and the lanes read it, so this test runs with real
    # credentials against the real channel. On 2026-09-01 that uploaded a video
    # (MAV4PF056RA) the moment upload.py gained a library fallback. Every lane
    # that can write to YouTube must honour this flag.
    env["LOOP_DRY_RUN"] = "1"
    # loop/arming.py gates a SCHEDULED run of upload-cloud/shorts-cloud/reach
    # behind a named LANE_NOT_ARMED_* stop before the lane even reaches its
    # credential check. Simulating workflow_dispatch is what a human proving
    # the lane by hand would do, and it is the meaningful test here too: even
    # a deliberate dispatched run must name ITS credential stop correctly
    # rather than crash, which is what this test actually verifies.
    env["GITHUB_EVENT_NAME"] = "workflow_dispatch"

    for fname, acceptable in LANES:
        examined += 1
        r = subprocess.run([PY, os.path.join(LOOP, fname)],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        out = r.stdout + r.stderr

        if r.returncode == 0:
            fails.append(f"loop/{fname} exited 0 with no credentials — that is "
                         f"a silent skip, the exact defect this loop forbids")
            continue
        if r.returncode != 3:
            fails.append(f"loop/{fname} exited {r.returncode} (a crash) rather "
                         f"than 3 (a named stop):\n{out[-600:]}")
            continue
        if "NAMED STOP" not in out:
            fails.append(f"loop/{fname} exited 3 without printing a NAMED STOP "
                         f"banner — nobody would see it")
        if not any(code in out for code in acceptable):
            fails.append(f"loop/{fname} named a stop, but not one of "
                         f"{acceptable}:\n{out[-400:]}")
        if "unblock" not in out.lower():
            fails.append(f"loop/{fname} named a stop with no way to unblock it")

    if examined == 0:
        fails.append("examined ZERO credential-blocked lanes")
    print(f"inspected {examined} blocked lane(s)")
    return fails


def check_alert_reaches_a_human() -> list[str]:
    """A named stop must actually arrive in someone's inbox.

    Two ways this silently fails, both of which were live on 2026-09-01:

    1. **No @-mention.** GitHub's default notification setting for your OWN
       repositories is "Participating and @mentions". An issue opened by Actions
       is neither, so the issue appears in the repo and no email is sent. The
       stop is then perfectly recorded and perfectly invisible.
    2. **The unblock names a command that no longer exists.** The runway stop
       still told her to run `voice/narrate-all.sh` and `bin/assemble-all.sh`
       after those were replaced by a single `bin/batch-session.sh`. An
       instruction read once every eight weeks is exactly the one nobody
       notices has rotted.
    """
    import os
    fails, examined = [], 0
    stage = open(os.path.join(ROOT, "bin", "loop-stage.sh")).read()
    examined += 1
    if "@${OWNER_HANDLE:-" not in stage and "@seq23" not in stage:
        fails.append("bin/loop-stage.sh does not @-mention the owner, so an "
                     "issue it opens will not email anyone under GitHub's "
                     "default notification settings")
    rank = open(os.path.join(ROOT, "loop", "rank.py")).read()
    import re
    for m in set(re.findall(r"bin/[a-z0-9-]+\.sh", rank)):
        examined += 1
        f = os.path.join(ROOT, m)
        if not os.path.exists(f):
            fails.append(f"loop/rank.py tells the owner to run {m}, which does "
                         f"not exist")
        elif not os.access(f, os.X_OK):
            fails.append(f"loop/rank.py tells the owner to run {m}, which is "
                         f"not executable")
    print(f"inspected {examined} alert-delivery case(s)")
    return fails


if __name__ == "__main__":
    f = check() + check_alert_reaches_a_human()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every blocked lane names its stop and says how to clear it"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
