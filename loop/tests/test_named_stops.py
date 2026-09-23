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
import tempfile as _tempfile

# The lanes this file runs take real named stops, and a stop record goes to
# LOOP_STOPS_DIR or else to the committed loop/state/stops/. run_all.py sets
# it; run on its own, this file wrote stop records into the repo. Default to
# scratch here as well.
os.environ.setdefault("LOOP_STOPS_DIR", _tempfile.mkdtemp(prefix="stops-"))
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
    # NOTHING_PUBLISHABLE is gone: every episode now uploads private with a
    # publishAt and YouTube performs the flip, so that branch became
    # structurally unreachable and the lane was given verification work
    # instead (see loop/publish.py). NO_FLIP_DUE_YET is the halt when no
    # scheduled video has come due yet; SCHEDULED_FLIP_DID_NOT_HAPPEN is the
    # loud one, when a video passed its date and is still private.
    ("publish.py", ("OAUTH_MISSING", "NO_FLIP_DUE_YET", "BREAKER_TRIPPED",
                    "SCHEDULED_FLIP_DID_NOT_HAPPEN")),
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

        # EXIT 0 IS ALLOWED ONLY FOR A SELF-RESOLVING NAMED STOP.
        #
        # This block used to treat exit 0 as proof of a silent skip. That was
        # right when every named stop exited 3, and became wrong when
        # loop/stop_policy.json introduced the self-resolving disposition: a
        # lane that correctly reports "there is nothing due yet" prints the
        # full banner, writes loop/state/stops/, and exits 0 so it does not
        # page a human every day. What must never happen is a lane exiting 0
        # having said NOTHING - so the test now demands the banner in both
        # cases, and demands that a zero exit explicitly declare itself
        # self-resolving. A quiet pass still fails here, which is the property
        # that mattered.
        if r.returncode not in (0, 3):
            fails.append(f"loop/{fname} exited {r.returncode} (a crash) rather "
                         f"than a named stop:\n{out[-600:]}")
            continue
        if "NAMED STOP" not in out:
            fails.append(f"loop/{fname} exited {r.returncode} without printing "
                         f"a NAMED STOP banner — nobody would see it")
            continue
        # Two dispositions may exit 0 now, not one. `owner_action` joined
        # `self_resolving` on 2026-09-08: a credential only the owner can renew
        # cannot self-heal and cannot be retried away, and failing this job
        # every day until she gets to it pages her for something she cannot
        # clear any faster for having been paged. It is green, it is recorded
        # in the owner-action file, and it is printed at the top of the Sunday
        # digest -- and loop/stop_policy.json escalates it to exit 3 if it
        # outlives its cap. The property this line has always protected is
        # unchanged: a zero exit must SAY which of the two it is. A silent
        # pass still fails.
        if r.returncode == 0 and not ("SELF-RESOLVING" in out.upper()
                                      or "WAITING ON THE OWNER" in out.upper()):
            fails.append(f"loop/{fname} exited 0 without declaring the stop "
                         f"self-resolving or waiting on the owner — a zero "
                         f"exit is only legitimate for a stop "
                         f"loop/stop_policy.json classifies")
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
