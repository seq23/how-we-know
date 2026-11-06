"""The weekly measure asks Analytics at most 50 video ids per call.

2026-11-06 (run 42302022393): 55 videos in one `video==` filter returned
HTTP 400 invalidFilters and the whole week went unmeasured. This fakes the
API's real limit and proves every one of 55 videos comes back measured.
"""
import io
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure as M  # noqa: E402

calls = []


def fake(token, ids, metrics, dimensions="video", start="2020-01-01"):
    calls.append(len(ids or []))
    if ids and len(ids) > 50:
        raise urllib.error.HTTPError("u", 400, "invalidFilters", {}, io.BytesIO(b"{}"))
    return {"columnHeaders": [{"name": "video"}, {"name": metrics.split(",")[0]}],
            "rows": [[i, 1] for i in (ids or [])]}


M._analytics_call = fake
ids = [f"v{i}" for i in range(55)]
data = M.fetch_analytics("t", ids)
got = {r[0] for r in data.get("rows", [])}
fails = []
if got != set(ids):
    fails.append(f"{len(got)} of 55 videos measured")
if max(calls) > 50:
    fails.append(f"a call carried {max(calls)} ids (limit 50)")
if fails:
    print("FAIL test_measure_filter_chunks: " + "; ".join(fails))
    sys.exit(1)
print(f"ok test_measure_filter_chunks: 55 videos in {len(calls)} calls of at most 50")
