"""The measure lane must survive an analytics response with no revenue column.

THE DEFECT THIS GUARDS. Run 34648295527 (2026-09-11) was the first Friday on
which YouTube Analytics returned ROWS for the channel's videos. Every retention
metric was there. `estimatedRevenue` was not: it is a monetary metric served by
a separate call that fetch_analytics() already downgrades to a note when Google
rejects it (no monetary scope, pre-YPP channel), so the column was never merged
in. The row parser then did `d["estimatedRevenue"]` one line after
`d.get("estimatedRevenue")`, and the lane died on a KeyError after recording
nothing - the previous Friday had passed only because the rows were empty.

Fixtures are drawn from the fixture set below, one per response SHAPE, so the
guard covers the class (a column the API may or may not serve) rather than the
instance. Hard-fails if it examines zero fixtures.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import measure                                             # noqa: E402

PUB = [{"video_id": "vidAAAAAAAA", "slug": "nonexistent-slug-for-guard"}]
WEEK = "2026-W37"

CORE = [{"name": "video"}, {"name": "views"},
        {"name": "estimatedMinutesWatched"}, {"name": "averageViewDuration"},
        {"name": "averageViewPercentage"}]

# name -> (response, expected estimated_revenue, expected rpm)
FIXTURES = {
    # The shape that killed the lane: rows present, revenue column absent.
    "rows_without_revenue_column": (
        {"columnHeaders": CORE,
         "rows": [["vidAAAAAAAA", 250, 900, 216.0, 41.2]],
         "revenue_unavailable": "HTTP 401 - needs yt-analytics-monetary.readonly"},
        None, None),
    # The shape the code was written for: revenue merged in.
    "rows_with_revenue_column": (
        {"columnHeaders": CORE + [{"name": "estimatedRevenue"}],
         "rows": [["vidAAAAAAAA", 250, 900, 216.0, 41.2, 1.25]]},
        1.25, 5.0),
    # Monetised but zero revenue on a video: rpm is a real 0.0, not None.
    "rows_with_zero_revenue": (
        {"columnHeaders": CORE + [{"name": "estimatedRevenue"}],
         "rows": [["vidAAAAAAAA", 250, 900, 216.0, 41.2, 0]]},
        0, 0.0),
    # Revenue present but zero views: no division, rpm not derivable.
    "rows_with_revenue_and_no_views": (
        {"columnHeaders": CORE + [{"name": "estimatedRevenue"}],
         "rows": [["vidAAAAAAAA", 0, 0, 0.0, 0.0, 0]]},
        0, None),
    # A response with no columnHeaders at all (empty report): zero records.
    "no_rows_no_headers": ({}, None, None),
}


def check(fixtures: dict) -> int:
    if not fixtures:
        print("FAIL: test_measure_revenue_optional examined ZERO fixtures")
        return 1
    failures = 0
    for name, (resp, want_rev, want_rpm) in fixtures.items():
        try:
            recs = measure.video_records(resp, PUB, WEEK)
        except Exception as e:                             # noqa: BLE001
            print(f"FAIL [{name}]: video_records raised {type(e).__name__}: {e}")
            failures += 1
            continue
        if not resp.get("rows"):
            if recs:
                print(f"FAIL [{name}]: expected no records, got {recs}")
                failures += 1
            else:
                print(f"ok   [{name}]: no rows -> no records")
            continue
        rec = recs[0]
        for key in ("video_id", "views", "average_view_percentage",
                    "estimated_minutes_watched", "average_view_duration_s"):
            if key not in rec:
                print(f"FAIL [{name}]: retention field {key} missing")
                failures += 1
        if rec["video_id"] != "vidAAAAAAAA":
            print(f"FAIL [{name}]: video_id {rec['video_id']!r}")
            failures += 1
        if rec.get("estimated_revenue") != want_rev:
            print(f"FAIL [{name}]: estimated_revenue "
                  f"{rec.get('estimated_revenue')!r} != {want_rev!r}")
            failures += 1
        if rec.get("rpm") != want_rpm:
            print(f"FAIL [{name}]: rpm {rec.get('rpm')!r} != {want_rpm!r}")
            failures += 1
        # None must stay None: a reader that treats "not measured" as 0 is
        # the next defect. Check the type, not just equality (0 == False).
        if want_rpm is None and rec.get("rpm") is not None:
            print(f"FAIL [{name}]: rpm should be None (not measured)")
            failures += 1
        if not failures:
            print(f"ok   [{name}]: revenue={rec['estimated_revenue']!r} "
                  f"rpm={rec['rpm']!r} retention={rec['average_view_percentage']}")
    print(f"examined {len(fixtures)} fixture(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    fixtures = FIXTURES
    if os.environ.get("MEASURE_GUARD_EMPTY_FIXTURES"):
        fixtures = {}                                      # prove the tripwire
    return check(fixtures)


if __name__ == "__main__":
    sys.exit(main())
