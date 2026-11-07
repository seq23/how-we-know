"""`mac_sync.py heartbeat --pending ""` records the run; a malformed count fails.

2026-11-07 08:00 CT: a backfill early stop reported `--pending ''` and
argparse's `type=int` rejected it, so the heartbeat that reports the stop
crashed (exit 2) and the stop never reached the repository. Empty means
"not counted this run" and clears the stale count; "abc" or "-1" must still
fail loudly so a broken caller is never recorded as a count.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["LOOP_DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mac_sync as MS                                     # noqa: E402


def run(tmp: Path, *argv: str) -> int:
    old_hb, old_argv = MS.HEARTBEAT, sys.argv
    MS.HEARTBEAT = tmp / "mac_heartbeat.json"
    sys.argv = ["mac_sync.py", "heartbeat", "--lane", "backfill", *argv]
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return MS.main()
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        MS.HEARTBEAT, sys.argv = old_hb, old_argv


def main() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        if run(tmp, "--ok", "1", "--uploaded", "2", "--pending", "5") != 0:
            fails.append("a numeric --pending was rejected")
        rec = json.loads((tmp / "mac_heartbeat.json").read_text())["backfill"]
        if rec.get("pending") != 5:
            fails.append(f"--pending 5 recorded as {rec.get('pending')!r}")

        # The 2026-11-07 shape: an early named stop, nothing counted.
        rc = run(tmp, "--ok", "0", "--uploaded", "0", "--held", "", "--pending", "")
        rec = json.loads((tmp / "mac_heartbeat.json").read_text())["backfill"]
        if rc != 0:
            fails.append(f"--pending '' exited {rc}; the stop's heartbeat was lost")
        elif rec.get("ok") is not False:
            fails.append("the failed run was not recorded as ok=false")
        elif "pending" in rec:
            fails.append(f"an uncounted run kept the stale pending={rec['pending']!r}")

        for bad in ("abc", "-1", "3.5"):
            if run(tmp, "--ok", "1", "--pending", bad) == 0:
                fails.append(f"malformed --pending {bad!r} was accepted")
    for f in fails:
        print("FAIL:", f)
    if not fails:
        print("OK: empty --pending records the run and clears the count; malformed values fail")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
