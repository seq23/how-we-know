#!/usr/bin/env python3
"""spawn_detached.py - start a command in its OWN SESSION, then exit.

Why this exists
---------------
`nohup CMD & disown` is not enough on this machine. It removes the job from the
launching shell's job table and ignores SIGHUP, but the child keeps the shell's
**process group and session**. Anything that later signals that group - a CI
harness reaping a background task, a terminal closing, a `kill -- -PGID` - takes
the child with it.

That is not theoretical: a narration run was killed twice this way, once at beat
23 of 55, with no traceback in the log. The only trace was a `resource_tracker`
warning at interpreter shutdown, which is what termination looks like from the
inside.

macOS ships no `setsid(1)`, so the usual fix is unavailable. `os.setsid()` is
available from Python, and `subprocess.Popen(start_new_session=True)` calls it in
the child between fork and exec. That puts the job in a brand new session with no
controlling terminal, which is what "detached" actually means.

Usage
-----
  spawn_detached.py LOGFILE COMMAND [ARG ...]

Prints the new session leader's pid. Verify with:
  ps -o pid,pgid,sess,command -p PID      # pgid == pid == its own session
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    log = Path(sys.argv[1])
    cmd = sys.argv[2:]
    log.parent.mkdir(parents=True, exist_ok=True)

    # Append, never truncate: a resumed run must not erase the record of the
    # attempt that died.
    fh = open(log, "ab", buffering=0)
    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=fh,
            start_new_session=True,   # <- os.setsid() in the child. The point.
            close_fds=True,
        )
    finally:
        fh.close()

    print(p.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
