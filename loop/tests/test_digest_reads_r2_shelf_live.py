"""The digest's Shorts shelf is read from R2 at render time, never mailed stale.

THE INCIDENT (2026-10-12, W42). The weekly digest at 16:44 UTC said "shelf 2
verified unpublished ... (2 scheduled on YouTube, 0 on R2)". At that moment 38
verified cuts were on R2 (read-only listing, 312 objects under shorts/): the
digest reused the Friday measure lane's count, taken at 15:54:16, and the Mac
pushed all 40 rank-2/3 cuts between 15:54:34 and 16:00:39 (R2 last_modified).
The shorts-cloud lane at 16:01 saw "verified backlog 40 cut(s)" and pulled two.
The count was true when taken; the page gave no time, so it read as current.

WHAT THIS PROVES (fixtures only - no network, writes nothing under loop/state):
  1. render() uses the LIVE R2 count, not channel_verdict.json's: a stale 0 in
     the verdict file and 38 live -> the page says "38 on R2", shelf 40.
  2. When the live read is unavailable the measured count is used, and the page
     prints the time it was MEASURED beside it - never a bare number.
  3. When neither exists the page says R2 was not read - never a guessed zero.
  4. verdict.shorts_cadence() records r2_as_of, and digest_block() prints it.
Negative proof: with r2_shelf_now() reverted to the measured count, 1 fails.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import digest                                              # noqa: E402
import measure                                             # noqa: E402
import verdict as CV                                       # noqa: E402

fails: list[str] = []
examined = 0
NOW = dt.datetime(2026, 10, 12, 16, 44, tzinfo=dt.timezone.utc)
STALE = {"shorts_cadence": {
    "as_of": "2026-10-12T15:54:16+00:00", "r2_verified_unpublished": 0,
    "r2_basis": "R2 listing of shorts/: 152 object(s), 0 verified and not uploaded",
    "r2_as_of": "2026-10-12T15:54:16+00:00", "shelf": 0}}


def page(live: tuple, verdict_file: dict) -> str:
    saved = (measure.r2_shelf_count, CV.read)
    measure.r2_shelf_count = lambda: live
    CV.read = lambda: copy.deepcopy(verdict_file)
    try:
        body, _ = digest.render("2026-W99", NOW)
    finally:
        measure.r2_shelf_count, CV.read = saved
    return body


def shorts_line(body: str) -> str:
    return next((ln for ln in body.splitlines()
                 if ln.startswith("- **Shorts:**")), "")


# 1. live wins over the stale measured count
examined += 1
ln = shorts_line(page((38, "R2 listing of shorts/: 312 object(s), 38 verified "
                           "and not uploaded"), STALE))
if "38 on R2 at 2026-10-12 16:44 UTC" not in ln:
    fails.append(f"1: the digest did not print the live R2 count with its read "
                 f"time: {ln!r}")
if "0 on R2" in ln:
    fails.append(f"1: the digest mailed the stale measured count: {ln!r}")

# 2. live unavailable -> the measured count, stamped with when it was measured
examined += 1
ln = shorts_line(page((None, "R2 credentials are not in this job's "
                             "environment"), STALE))
if "0 on R2 at 2026-10-12 15:54 UTC" not in ln:
    fails.append(f"2: the fallback count is not stamped with its measure time: "
                 f"{ln!r}")

# 3. neither -> says so, never a zero
examined += 1
ln = shorts_line(page((None, "R2 credentials are not in this job's "
                             "environment"), {}))
if "on R2 at" in ln or "R2 not read" not in ln:
    fails.append(f"3: with no R2 count at all the page invented one: {ln!r}")

# 4. the record carries the as-of and the block prints it
examined += 1
sc = CV.shorts_cadence([], 9, NOW, 5, "fixture")
if sc.get("r2_as_of") != NOW.isoformat(timespec="seconds"):
    fails.append(f"4: shorts_cadence() did not stamp r2_as_of: {sc}")
sc = CV.shorts_cadence([], 9, NOW, None, "unread")
if sc.get("r2_as_of") is not None:
    fails.append(f"4: an unread R2 count carries an as-of: {sc}")
sc = CV.shorts_cadence([], 9, NOW, 5, "fixture",
                       r2_as_of="2026-10-09T22:00:00+00:00")
block = "\n".join(CV.digest_block({"shorts_cadence": sc}))
if "5 on R2 at 2026-10-09 22:00 UTC" not in block:
    fails.append(f"4: digest_block() does not print the R2 as-of: {block!r}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s), {len(fails)} failure(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
