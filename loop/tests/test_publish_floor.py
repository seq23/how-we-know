"""The publishing floor: 7 public a week and one every day, per channel (18 Nov 2026).

  a. the feed parser reads YouTube's Atom feed (ids, titles, published times);
  b. a full week with tomorrow dated is met; 6 in the week, or tomorrow with
     nothing public or dated, is a breach naming the gap;
  c. the schedule is read from the upload records (How We Know ledgers,
     Whisper Almanac kits and their Shorts), never a retired or withdrawn row;
  d. a breach opens ONE issue that @-mentions her and names the channel, the
     gap and the fix; a second day re-mentions the same issue; the day the
     floor is met closes it;
  e. a feed that cannot be read is the named stop, exit 2: never judged on no data;
  f. the config holds the floor at 7 for both channels.
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["OWNER_HANDLE"] = "owner"

import publish_floor as PF  # noqa: E402

fails: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 18, 15, 0, tzinfo=UTC)            # Wed 18 Nov 09:00 CT
FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <title>Ch</title>
 {entries}
</feed>"""


def entry(vid, when):
    return (f"<entry><yt:videoId>{vid}</yt:videoId><title>t {vid}</title>"
            f"<published>{when:%Y-%m-%dT%H:%M:%S+00:00}</published></entry>")


def feed_of(days_ago):
    return FEED.format(entries="".join(entry(f"v{i}", NOW - dt.timedelta(days=d, hours=1))
                                       for i, d in enumerate(days_ago)))


# a. the parser
vids = PF.parse_feed(feed_of([0, 1, 2]))
check(len(vids) == 3 and vids[0]["id"] == "v0" and vids[0]["published"].tzinfo is not None,
      f"(a) the feed was not parsed: {vids}")

# b. the judgement
tomorrow = [NOW + dt.timedelta(days=1)]
full = PF.parse_feed(feed_of([0, 1, 2, 3, 4, 5, 6]))
j = PF.judge(full, tomorrow, NOW, 7)
check(j["ok"] and j["week"] == 7, f"(b) a full week with tomorrow dated is not met: {j}")
j = PF.judge(full[:-1], tomorrow, NOW, 7)
check(not j["ok"] and j["short_by"] == 1, f"(b) six in the week is not a breach: {j}")
j = PF.judge(full, [], NOW, 7)
check(not j["ok"] and [str(d) for d in j["empty_ahead"]] == ["2026-11-19"],
      f"(b) tomorrow with nothing dated is not a breach naming Thu 19 Nov: {j}")
gap = PF.parse_feed(feed_of([0, 1, 3, 4, 5, 6, 6]))
j = PF.judge(gap, tomorrow, NOW, 7)
check([str(d) for d in j["empty_past"]] == ["2026-11-16"], f"(b) the empty day Mon 16 Nov was not named: {j}")

# c. the schedule from the records
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "loop/state").mkdir(parents=True)
    (root / "loop/state/ledger.json").write_text(json.dumps({"published": [
        {"slug": "a", "video_id": "A", "scheduled_publish_at": "2026-11-19T16:00:00Z"},
        {"slug": "b", "video_id": "B", "scheduled_publish_at": "2026-11-20T16:00:00Z", "retired_at": "x"}]}))
    (root / "loop/state/shorts_ledger.json").write_text(json.dumps({"published": [
        {"slug": "c", "video_id": "C", "scheduled_publish_at": "2026-11-21T01:00:00Z"},
        {"slug": "d", "video_id": "D", "scheduled_publish_at": "2026-11-22T01:00:00Z", "withdrawn_at": "x"}]}))
    k = root / "channel/whisper/w1"
    k.mkdir(parents=True)
    (k / "kit.json").write_text(json.dumps({"video_id": "W", "scheduled_publish_at": "2026-11-19T02:00:00Z",
                                            "shorts": [{"video_id": "S", "publish_at": "2026-11-20T01:00:00Z"},
                                                       {"publish_at": "2026-11-21T01:00:00Z"}]}))
    hwk = sorted(f"{t:%d}" for t in PF.scheduled("how-we-know", root))
    wa = sorted(f"{t:%d}" for t in PF.scheduled("whisper-almanac", root))
    check(hwk == ["19", "21"], f"(c) How We Know's dated videos read wrong (retired/withdrawn counted?): {hwk}")
    check(wa == ["19", "20"], f"(c) Whisper Almanac's dated videos read wrong (an unuploaded Short counted?): {wa}")


# d. delivery: open once, re-mention, close
class FakeGH:
    def __init__(self):
        self.issues, self.calls = {}, []

    def __call__(self, cmd, capture_output=True, text=True):
        a = cmd[1:]
        self.calls.append(a)
        out = ""
        if a[:2] == ["issue", "list"]:
            out = json.dumps([{"number": n, "body": b} for n, (b, st) in self.issues.items() if st == "open"])
        elif a[:2] == ["issue", "create"]:
            n = len(self.issues) + 1
            self.issues[n] = (a[a.index("--body") + 1], "open")
        elif a[:2] == ["issue", "close"]:
            n = int(a[2])
            self.issues[n] = (self.issues[n][0], "closed")
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()


gh = FakeGH()
ch = {"name": "How We Know", "lanes": []}
j = PF.judge(full, [], NOW, 7)
breach = PF.alert("how-we-know", ch, j, ["breaker: tripped on domain"], NOW)
r1 = PF.deliver("how-we-know", breach, "", gh)
r2 = PF.deliver("how-we-know", breach, "", gh)
body = gh.issues[1][0]
check(r1 == "opened" and r2 == "re-mentioned #1" and len(gh.issues) == 1,
      f"(d) a breach did not open one issue and re-mention it: {r1}, {r2}, {len(gh.issues)}")
check(body.startswith("@owner") and "How We Know" in body and "Thu 19 Nov" in body and "breaker" in body
      and "STOPPED" in breach[0], f"(d) the alert does not name the channel, the gap and the fix: {body[:200]}")
check(any(c[:2] == ["issue", "comment"] and "@owner" in c[-1] for c in gh.calls),
      "(d) the second day did not @-mention her again")
r3 = PF.deliver("how-we-know", None, "7 of 7", gh)
check(r3 == "closed #1" and gh.issues[1][1] == "closed", f"(d) a met floor did not close the issue: {r3}")
check(PF.deliver("whisper-almanac", None, "ok", gh) == "met", "(d) a met floor with no issue filed something")


# e. an unreadable feed is a named stop, exit 2
def broken(cid):
    raise OSError("feed down")


rc = PF.check(dry_run=True, now=NOW, feed=broken)
check(rc == 2, f"(e) an unreadable feed did not exit 2: {rc}")

# f. the config
c = PF.cfg()
check(set(c["channels"]) == {"how-we-know", "whisper-almanac"}
      and all(int(v.get("per_week", c["per_week"])) >= 7 for v in c["channels"].values()) and c["per_day"] >= 1,
      f"(f) the floor is not 7 a week and 1 a day for both channels: {c}")

if fails:
    print("FAIL test_publish_floor")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_publish_floor: 7 a week and one a day from the public feed; one red issue per channel, "
      "re-mentioned daily, closed when met; an unread feed is a named stop")
