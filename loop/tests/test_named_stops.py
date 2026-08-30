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
    ("measure.py", ("OAUTH_MISSING", "NOTHING_PUBLISHED")),
]


def check() -> list[str]:
    fails, examined = [], 0
    env = dict(os.environ)
    for k in ("YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN",
              "YOUTUBE_API_KEY"):
        env.pop(k, None)
    env["LOOP_NO_DOTENV"] = "1"

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


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - every blocked lane names its stop and says how to clear it"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
