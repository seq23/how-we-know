"""The Peace Be Still library-fill pause (her call, 18 Nov 2026) and its 21-day limit.

  a. a fill file 3 days old pauses the Mac jobs (exit 10) and the floor check
     files NO STOPPED issue for either channel, saying "Paused for the Peace Be
     Still library fill since <date>" instead, and closes an open one;
  b. a fill file 22 days old is IGNORED: the Mac jobs run (exit 0) and the
     floor check opens its STOPPED issue as if there were no pause;
  c. no file: not paused, and the mirror the cloud reads is removed.
"""
import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["OWNER_HANDLE"] = "owner"

import pbs_pause as PB  # noqa: E402
import publish_floor as PF  # noqa: E402

fails: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


class FakeGH:
    def __init__(self, open_issue=False):
        self.created, self.closed = [], []
        self.open = open_issue

    def __call__(self, cmd, capture_output=True, text=True):
        a, out = cmd[1:], ""
        if a[:2] == ["issue", "list"]:
            ch = a[a.index("--search") + 1].split()[0]
            out = json.dumps([{"number": 1, "body": f"<!-- publish-floor:{ch} -->"}] if self.open else [])
        elif a[:2] == ["issue", "create"]:
            self.created.append(a[a.index("--title") + 1])
        elif a[:2] == ["issue", "close"]:
            self.closed.append(a[a.index("--comment") + 1])
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()


def empty_feed(cid):
    return []                                   # nothing public: a breach on both channels


def floor_run(root: Path, gh: FakeGH) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        PF.check(now=NOW, feed=empty_feed, runner=gh, root=root)
    return buf.getvalue()


def setup(age_days: float | None) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    fill = root / "home" / "library-fill.active"
    if age_days is not None:
        fill.parent.mkdir(parents=True)
        fill.write_text(json.dumps({"started": (NOW - dt.timedelta(days=age_days)).isoformat(),
                                    "expected_end": "2026-12-01", "reason": "private words never mirrored"}))
    PB.mirror(PB.read_local(fill), root)        # what the Mac's gate pushes
    return root, fill, td


# a. a fresh pause
root, fill, td = setup(3)
j = PB.judge(PB.read_local(fill), NOW)
check(j["paused"] and "Paused for the Peace Be Still library fill since Sun 15 Nov 2026" in j["line"],
      f"(a) a 3-day-old fill file did not pause: {j}")
mirror = (root / PB.MIRROR_REL).read_text()
check("private words" not in mirror, "(a) the fill file's reason reached the public repo mirror")
gh = FakeGH(open_issue=True)
out = floor_run(root, gh)
check(not gh.created and "STOPPED" not in out, f"(a) a STOPPED alarm fired while paused: {gh.created} {out}")
check(out.count("Paused for the Peace Be Still library fill since") == 2,
      f"(a) the daily line did not say Paused for both channels: {out}")
check(len(gh.closed) == 2 and all("Paused for the Peace Be Still" in c for c in gh.closed),
      f"(a) an open STOPPED issue was not closed with the pause line: {gh.closed}")
td.cleanup()

# b. a stuck fill (22 days): ignored, the alarm fires
root, fill, td = setup(22)
j = PB.judge(PB.read_local(fill), NOW)
check(not j["paused"] and j["stale"], f"(b) a 22-day-old fill file still pauses the Mac jobs: {j}")
gh = FakeGH()
out = floor_run(root, gh)
check(len(gh.created) == 2 and all(t.startswith("STOPPED") for t in gh.created),
      f"(b) a 22-day-old pause silenced the STOPPED alarm: {gh.created} {out}")
td.cleanup()

# c. no file: not paused, mirror removed
root, fill, td = setup(3)
PB.mirror(PB.read_local(root / "absent"), root)
check(not (root / PB.MIRROR_REL).exists(), "(c) the mirror outlived the fill file")
check(not PB.judge(PB.read_local(root / "absent"), NOW)["paused"], "(c) no fill file still pauses")
td.cleanup()

if fails:
    print("FAIL test_pbs_pause")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_pbs_pause: a fill under 21 days pauses voice/render and the STOPPED alarm; "
      "over 21 days it is ignored and STOPPED fires; no file, no pause")
