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

# -- the weekly Monday re-weighting is decided once a week, from week 3 ------
import whisper_lane as WL  # noqa: E402
C = WL.cfg()
UTC = dt.timezone.utc
lanes = {"ocean": {"videos_28d": 2, "watch_hours_per_video": 8.0},
         "neville": {"videos_28d": 3, "watch_hours_per_video": 3.0}}
nums = {"first_upload_at": "2026-11-14T02:00:00Z", "lanes": lanes}
S.decide(nums, C, dt.datetime(2026, 11, 24, 5, 0, tzinfo=UTC))            # Mon 23 Nov 23:00 CT: day 10
if "reweight" in nums:
    fails.append(f"re-weighted before 14 days of numbers: {nums['reweight']}")
S.decide(nums, C, dt.datetime(2026, 12, 1, 5, 0, tzinfo=UTC))             # Mon 30 Nov 23:00 CT
rw = nums.get("reweight") or {}
if rw.get("week") != "2026-W49" or rw.get("mix", {}).get("ocean") != 2 or sum(rw.get("mix", {}).values()) != 5:
    fails.append(f"Monday of week 3 did not give ocean the spare night: {rw}")
nums["lanes"] = {"neville": {"videos_28d": 3, "watch_hours_per_video": 99.0}}
S.decide(nums, C, dt.datetime(2026, 12, 3, 5, 0, tzinfo=UTC))             # Wed of the same week
if (nums.get("reweight") or {}).get("mix", {}).get("ocean") != 2:
    fails.append(f"the week's mix was decided twice: {nums.get('reweight')}")
S.decide(nums, C, dt.datetime(2026, 12, 8, 5, 0, tzinfo=UTC))             # the next Monday
if (nums.get("reweight") or {}).get("week") != "2026-W50" or nums["reweight"]["mix"].get("neville") != 2:
    fails.append(f"the next Monday did not decide again: {nums.get('reweight')}")
empty = {"first_upload_at": "2026-11-14T02:00:00Z", "lanes": {}}
line = S.decide(empty, C, dt.datetime(2026, 12, 1, 5, 0, tzinfo=UTC))
if "reweight" in empty or "NOT decided" not in line:
    fails.append(f"a Monday with no measured lane was decided, or said nothing: {line}")

# -- the 48-hour click-rate check: one line, once, never on a missing number --
CSV = ("date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
       "20261114,low,300,2.0\n20261115,low,100,4.0\n20261114,fine,500,6.5\n20261114,few,40,1.0\n20261114,new,400,1.0\n")


class FakeReach:
    created = downloads = 0

    def jobs(self):
        return [{"id": "j1", "reportTypeId": "channel_reach_basic_a1"}] if self.created else []

    def create(self):
        self.created += 1
        return {"id": "j1", "reportTypeId": "channel_reach_basic_a1"}

    def reports(self, job):
        return [{"id": "r1", "createTime": "2026-11-16T00:00:00Z", "startTime": "a", "endTime": "b", "downloadUrl": "u"}]

    def download(self, url):
        self.downloads += 1
        return CSV


api, state = FakeReach(), {}
rates = S.click_rates(api, state)
S.click_rates(api, state)
if api.created != 1 or api.downloads != 1:
    fails.append(f"the reach job was made {api.created} times and its report downloaded {api.downloads} times")
if rates.get("low") != {"impressions": 400, "ctr_pct": 2.5}:
    fails.append(f"the click rate is not impressions-weighted over the days reported: {rates.get('low')}")
now = dt.datetime(2026, 11, 17, 5, 0, tzinfo=UTC)
kit = lambda vid, at="2026-11-14T02:00:00Z": {"video_id": vid, "scheduled_publish_at": at, "title": vid}  # noqa: E731
kits = {"a": kit("low"), "b": kit("fine"), "c": kit("few"), "d": kit("new", "2026-11-16T02:00:00Z"),
        "e": kit("unreported")}
nums = {}
lines = S.click_notices(nums, rates, kits, C, now)
if len(lines) != 1 or '"low"' not in lines[0] or "2.5%" not in lines[0] or "Test & Compare" not in lines[0]:
    fails.append(f"only the 48h+ video under 4% on 100+ impressions should get the line: {lines}")
later = S.click_notices(nums, rates, kits, C, now + dt.timedelta(days=1))
if len(later) != 1 or '"new"' not in later[0]:
    fails.append(f"a day later only the video that just passed 48 hours is told, never the same one twice: {later}")
if S.click_notices({}, {}, kits, C, now) != []:
    fails.append("a video with no reported impressions was judged")
if fails:
    print("FAIL test_whisper_scorecard\n  " + "\n  ".join(fails))
    sys.exit(1)
print("ok test_whisper_scorecard: totals from /channels; Monday re-weighting once a week from week 3; "
      "one swap-the-thumbnail line per video under 4%")
