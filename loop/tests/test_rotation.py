"""The three-niche rotation: one long-form a day, each weekday owned by a domain.

Owner decision, 13 Oct 2026 (docs/CHANNEL-PLAN.md "Three-niche schedule"):
Mon/Thu deep sea, Tue/Fri materials, Wed/Sat food-science (mapped ahead of its
registration - its days stay EMPTY), Sunday none, 10:00 local, per_day 1.

  1. the config map is exactly that, the pin (videos_per_week 6) matches the
     mapped days, and live_slots()/domain_weekdays() read it;
  2. schedule_slugs() puts each episode on its OWN domain's day, one a day,
     never Sunday, never a food day, never inside the 24 h lead; a slug whose
     domain holds no day gets None (left on the shelf, nothing borrowed);
  3. LONG_FORM_PER_DAY=2 allows a second slot only at a second configured
     time - with one time configured it changes nothing (never two at 10:00);
  4. V20 fails an episode dated since the rotation on another domain's day,
     holds (named stop) one dated before it, and passes the real repo.

NEGATIVE PROOF (run once, 2026-10-13): map "wed" to deep-sea in
backfill.rotation_days -> case 2 "never a food day" fails; restore -> green.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"
os.environ.pop("LONG_FORM_PER_DAY", None)

import backfill as B                                          # noqa: E402
import common                                                 # noqa: E402
import domains as D                                           # noqa: E402
import ledger                                                 # noqa: E402

fails: list[str] = []
examined = 0
TMP = Path(tempfile.mkdtemp(prefix="rotation-"))


def check(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


DEEP, MAT, FOOD = ("deep-sea-ocean-science", "materials-and-manufacturing",
                   "food-science")
cfg = common.config()
rot = cfg["cadence"]["rotation"]
check(rot["weekdays"] == {"mon": DEEP, "tue": MAT, "wed": FOOD, "thu": DEEP,
                          "fri": MAT, "sat": FOOD, "sun": None}
      and rot["per_day"] == 1 and rot["slot_times_local"] == ["10:00"],
      f"the rotation is not the owner's: {rot}")
check(cfg["cadence"]["videos_per_week"] == 6 == len(B.rotation_days(cfg)),
      "videos_per_week does not match the rotation's mapped days")
check(D.live_slots(cfg) == {DEEP: 2, MAT: 2}
      and B.domain_weekdays(cfg, 6) == {DEEP: (0, 3), MAT: (1, 4)},
      f"live_slots/domain_weekdays do not read the rotation: "
      f"{D.live_slots(cfg)} {B.domain_weekdays(cfg, 6)}")

# ----------------------------------------------------------- 2. scheduling
deep = [s for s in ("02-how-deep-sea-creatures-survive-pressure",
                    "04-why-deep-sea-creatures-are-so-scary",
                    "13-how-does-bioluminescence-work-in-the-deep-sea")]
mat = ["what-is-kevlar-made-of", "why-is-steel-so-strong", "what-is-concrete-made-of"]
empty = {"published": [], "queued": []}
slugs = [deep[0], mat[0], deep[1], mat[1], deep[2], mat[2], "no-such-slug-domainless"]
when = B.schedule_slugs(empty, slugs, 6)
now = datetime.now(timezone.utc)
days_seen = []
for slug, t in zip(slugs, when):
    if slug == "no-such-slug-domainless":
        continue
    lt = t.astimezone(B.PUBLISH_TZ)
    dom = D.domain_of_slug(slug)
    days_seen.append(lt.date())
    check(B.rotation_days(cfg).get(lt.weekday()) == dom and lt.weekday() not in (2, 5, 6)
          and f"{lt:%H:%M}" == "10:00" and t >= now + timedelta(hours=24),
          f"{slug} ({dom}) got {lt:%a %d %b %H:%M}: not its rotation day, or a "
          f"food/Sunday day, or inside the lead")
check(len(days_seen) == len(set(days_seen)), "two episodes landed on one day")
check(when[-1] is not None,
      "a slug with no script fell to no domain (it is treated as deep sea)")
cfg_food = {**cfg, "domains": {**cfg["domains"], "allocation": {DEEP: 2, MAT: 2}}}
check(B.domain_weekdays(cfg_food, 6).get(FOOD) is None,
      "an unregistered mapped domain was handed days")

# ------------------------------------------------------- 3. LONG_FORM_PER_DAY
os.environ["LONG_FORM_PER_DAY"] = "2"
w2 = B.schedule_slugs(empty, [deep[0], deep[1]], 6)
check(w2[0].date() != w2[1].date() or w2[0] != w2[1],
      "LONG_FORM_PER_DAY=2 with one slot time put two episodes at the same minute")
os.environ.pop("LONG_FORM_PER_DAY")

# --------------------------------------------------------------------- 4. V20
import validate as V                                          # noqa: E402
res = V.v20_cadence_schedule().as_dict()
check(not res["failures"], f"V20 fails on the real repo: {res['failures']}")
saved = ledger.LEDGER
fake = TMP / "ledger.json"
future = now + timedelta(days=10)
while future.astimezone(B.PUBLISH_TZ).weekday() != 2:      # a Wednesday (food)
    future += timedelta(days=1)
stamp = future.astimezone(B.PUBLISH_TZ).replace(hour=10, minute=0, second=0,
                                                microsecond=0)
stamp = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for uploaded, want in (("2026-10-20T00:00:00+00:00", "fail"),
                       ("2026-10-01T00:00:00+00:00", "held")):
    fake.write_text(json.dumps({"published": [{
        "slug": deep[0], "video_id": "X", "privacy": "private",
        "uploaded_at": uploaded, "scheduled_publish_at": stamp}], "queued": []}))
    ledger.LEDGER = fake
    try:
        res = V.v20_cadence_schedule().as_dict()
    finally:
        ledger.LEDGER = saved
    if want == "fail":
        check(any("rotation day" in f for f in res["failures"]),
              f"V20 passed a deep-sea episode dated on a food Wednesday: {res}")
    else:
        check(not any("rotation day" in f for f in res["failures"]) and
              any(s_["code"] == "OFF_ROTATION_RESCHEDULE_PENDING" for s_ in res["stops"]),
              f"V20 did not hold a pre-rotation row for reschedule: {res}")

# ---------------------------------------- 5. V20: duplicates and Sundays
# Job 2 (2026-10-13): 02-how-deep-sea-creatures-survive-pressure read as
# scheduled Thu 22 Oct AND Sun 25 Oct and V20 passed. Each of these must fail,
# even for rows dated before the rotation (those are otherwise only HELD).
def _slot(weekday: int) -> str:
    t = now + timedelta(days=10)
    while t.astimezone(B.PUBLISH_TZ).weekday() != weekday:
        t += timedelta(days=1)
    t = t.astimezone(B.PUBLISH_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


OLD = "2026-09-03T14:00:00+00:00"
row = {"slug": deep[0], "privacy": "private", "uploaded_at": OLD}
cases = (
    ("duplicate", [dict(row, video_id="A1", scheduled_publish_at=_slot(3)),
                   dict(row, video_id="A2", scheduled_publish_at=_slot(0))],
     "scheduled 2 times"),
    ("sunday", [dict(row, video_id="A1", scheduled_publish_at=_slot(6))],
     "Sunday carries no long-form slot"),
    ("retired-dated", [dict(row, video_id="A1", scheduled_publish_at=_slot(3)),
                       dict(row, video_id="A2", scheduled_publish_at=_slot(6),
                            retired_at=OLD)],
     "still carries scheduled_publish_at"),
    ("superseded-clean", [dict(row, video_id="A1", scheduled_publish_at=_slot(3)),
                          dict(row, video_id="A2", retired_at=OLD,
                               status="superseded_duplicate",
                               schedule_was=_slot(6))],
     None),
)
for name, rows_, want in cases:
    fake.write_text(json.dumps({"published": rows_, "queued": []}))
    ledger.LEDGER = fake
    try:
        res = V.v20_cadence_schedule().as_dict()
    finally:
        ledger.LEDGER = saved
    if want:
        check(any(want in f for f in res["failures"]),
              f"V20 passed the {name} case: {res['failures']}")
    else:
        check(not any(k in f for f in res["failures"] for k in
                      ("scheduled 2 times", "Sunday", "still carries")),
              f"V20 failed a clean superseded duplicate: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
