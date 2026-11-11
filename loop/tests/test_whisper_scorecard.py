"""The nightly scorecard reads the channel's subscriber and view totals from the
Data API's channels resource. 10-11 Nov 2026: it called the bare /youtube/v3 base
(HTTP 404 every night, WHISPER_ANALYTICS_NOT_READ), so no number was ever read."""
import datetime as dt
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP))
import whisper_scorecard as S  # noqa: E402

calls = []


def fake_get(url, token, **q):
    calls.append(url)
    if url.startswith(S.ANALYTICS):
        return {"columnHeaders": [], "rows": []}
    if url != f"{S.DATA}/channels":
        raise AssertionError(f"404: {url}")
    return {"items": [{"statistics": {"subscriberCount": "12", "viewCount": "3400"}}]}


S._get = fake_get
S.lane_videos = lambda now, c: {}
out = S.read("t", dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc), {})
fails = []
if f"{S.DATA}/channels" not in calls:
    fails.append(f"the Data API call is not to /channels: {calls}")
if out.get("subscribers") != 12 or out.get("views") != 3400:
    fails.append(f"totals not read: {out}")
if fails:
    print("FAIL test_whisper_scorecard\n  " + "\n  ".join(fails))
    sys.exit(1)
print("ok test_whisper_scorecard: subscribers and views come from /channels")
