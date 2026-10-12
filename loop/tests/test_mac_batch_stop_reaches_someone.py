"""A named stop on the Mac batch reaches the repository and, if it pages, an issue.

bin/batch-session.sh runs under launchd: there is no workflow to turn an exit 3
into an issue. SHORTS_UNVERIFIED (needs_human) ended the nightly push from
21 Sep to 12 Oct 2026 and only batch.log knew. Proves, with a FAKE gh:

  1. scan() finds every `NAMED STOP [CODE]` line, deduped, in order;
  2. a needs_human stop writes loop/state/stops/<week>-mac-batch.json with the
     code, its disposition and a streak, and opens ONE `[mac-batch] <CODE>`
     issue;
  3. the next night, with that issue open, it comments instead of opening a
     second one (dedupe by exact title);
  4. a self-resolving stop writes the record and files nothing;
  5. a night with no stop clears the record;
  6. a gh failure never raises, and main() always exits 0;
  7. batch-session.sh tees the push output, scans it, and mac_sync commits the
     mac-batch stop file; digest.stops_in reads it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
tmp = Path(tempfile.mkdtemp(prefix="mac-batch-stop-"))
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")
os.environ.setdefault("LOOP_DRY_RUN", "1")

import common as C  # noqa: E402
import mac_batch_stop as M  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")


class FakeGh:
    def __init__(self, open_issues=None, fail=False):
        self.calls: list[list[str]] = []
        self.open = list(open_issues or [])
        self.fail = fail

    def __call__(self, args):
        self.calls.append(args)

        class R:
            returncode, stdout, stderr = 0, "", ""
        r = R()
        if self.fail:
            r.returncode, r.stderr = 1, "gh: not logged in"
        elif args[:2] == ["issue", "list"]:
            r.stdout = json.dumps(self.open)
        elif args[:2] == ["issue", "create"]:
            title = args[args.index("--title") + 1]
            self.open.append({"number": 101, "title": title})
            r.stdout = "https://github.com/seq23/how-we-know/issues/101"
        return r

    def verbs(self):
        return [a[1] for a in self.calls]


out = """── shorts (V14 + V15 must pass before anything is shelved) ───
NAMED STOP [SHORTS_UNVERIFIED] V14 (attribution) or V15 (caption crop) failed
NAMED STOP — see the reason above.
NAMED STOP [SHORTS_UNVERIFIED] again
"""
check("1 scan finds one code, deduped",
      M.scan(out) == [("SHORTS_UNVERIFIED",
                       "V14 (attribution) or V15 (caption crop) failed")],
      str(M.scan(out)))

stop_file = Path(os.environ["LOOP_STOPS_DIR"]) / f"{C.week_id()}-mac-batch.json"
gh = FakeGh()
recs = M.report(out, gh=gh)
rec = json.loads(stop_file.read_text()) if stop_file.exists() else {}
check("2 stop file written", rec.get("code") == "SHORTS_UNVERIFIED"
      and rec.get("stage") == "mac-batch" and rec.get("consecutive") == 1, str(rec)[:300])
check("2 needs_human disposition", rec.get("disposition") == "needs_human",
      str(rec.get("disposition")))
check("2 one issue opened, titled [mac-batch] SHORTS_UNVERIFIED",
      gh.verbs() == ["list", "create"]
      and "[mac-batch] SHORTS_UNVERIFIED" in gh.calls[1], str(gh.calls))

gh2 = FakeGh(open_issues=[{"number": 101, "title": "[mac-batch] SHORTS_UNVERIFIED"},
                          {"number": 7, "title": "[mac-batch] SHORTS_UNVERIFIED (old)"}])
M.report(out, gh=gh2)
rec2 = json.loads(stop_file.read_text())
check("3 second night comments on #101, opens nothing",
      gh2.verbs() == ["list", "comment"] and "101" in gh2.calls[1], str(gh2.calls))
check("3 streak counts the second night", rec2.get("consecutive") == 2, str(rec2.get("consecutive")))

gh3 = FakeGh()
M.report("NAMED STOP [NO_SHORTS_CUT] nothing cut yet\n", gh=gh3)
rec3 = json.loads(stop_file.read_text())
pol = C.stop_policy()
green = rec3.get("disposition") in ("self_resolving", "held", "owner_action")
check("4 a green stop is recorded and files nothing",
      rec3.get("code") == "NO_SHORTS_CUT" and (gh3.calls == [] if green else True),
      f"{rec3.get('disposition')} {gh3.calls}")

M.report("pushed 3, skipped 70\nR2 shelf is up to date.\n", gh=FakeGh())
check("5 a clean night clears the record", not stop_file.exists())

bad = FakeGh(fail=True)
try:
    M.report(out, gh=bad)
    raised = None
except Exception as e:  # noqa: BLE001
    raised = e
check("6 a gh failure never raises", raised is None, repr(raised))
f = tmp / "push.out"
f.write_text(out)
check("6 main() exits 0", M.main(["scan", str(f)]) == 0
      and M.main(["scan", str(tmp / "missing")]) == 0)

sh = (ROOT / "bin" / "batch-session.sh").read_text()
check("7 batch-session tees the push and scans it",
      'tee "$PUSH_OUT"' in sh and 'mac_batch_stop.py scan "$PUSH_OUT"' in sh)
check("7 the mac-batch stop file is committed with the batch's push",
      "-mac-batch.json" in sh[sh.find("mac_batch_stop.py scan"):])
import digest  # noqa: E402
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")
M.report(out, gh=FakeGh())
digest.STOPS = Path(os.environ["LOOP_STOPS_DIR"])
seen = [s.get("stage") for s in digest.stops_in(C.week_id())]
check("7 digest.stops_in lists the mac-batch stop", "mac-batch" in seen, str(seen))

if examined == 0:
    print("FAIL test_mac_batch_stop_reaches_someone: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_mac_batch_stop_reaches_someone:")
    for x in fails:
        print(f"  - {x}")
    sys.exit(1)
print(f"OK  test_mac_batch_stop_reaches_someone: {examined} checks - the Mac's "
      f"stops are committed and page through one deduped issue")
