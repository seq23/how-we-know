"""The three-niche rotation: one long-form a day, each weekday owned by a domain.

Owner decision, 13 Oct 2026 (docs/CHANNEL-PLAN.md "Three-niche schedule"),
as changed by her Money-test call of 9 Nov 2026 (loop/config.json
domains.money_test): Mon/Thu deep sea, Tue/Fri materials, Wed/Sat
money-and-business; food-science long-forms PAUSED (allocation 0, no weekday),
so a food episode is never given a slot on any day; Sunday none, 10:00 local,
per_day 1.

  1. the config map is exactly that, the pin (videos_per_week 6) matches the
     mapped days, and live_slots()/domain_weekdays() read it;
  2. schedule_slugs() puts each episode on its OWN domain's day, one a day,
     never Sunday, never a Money day while a Money episode is ready, never
     inside the 24 h lead; a slug whose domain holds no day (paused food)
     gets None (left on the shelf, nothing borrowed);
  3. LONG_FORM_PER_DAY=2 allows a second slot only at a second configured
     time - with one time configured it changes nothing (never two at 10:00);
  4. V20 fails an episode dated since the rotation on another domain's day
     (deep sea or paused food on a Money Wednesday), holds (named stop) one
     dated before it, and passes the real repo.

NEGATIVE PROOF (run once, 2026-10-13): map "wed" to deep-sea in
backfill.rotation_days -> case 2 fails; restore -> green. Re-run 2026-11-10
for the Money rotation: map "sat" back to food-science in loop/config.json
(allocation food 1, money 1) -> case 1, "paused food was given a slot" and
"a weekday is still mapped to paused food-science" fail; restore -> green.
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


DEEP, MAT, FOOD, MONEY = ("deep-sea-ocean-science", "materials-and-manufacturing",
                          "food-science", "money-and-business")
cfg = common.config()
rot = cfg["cadence"]["rotation"]
check(rot["weekdays"] == {"mon": DEEP, "tue": MAT, "wed": MONEY, "thu": DEEP,
                          "fri": MAT, "sat": MONEY, "sun": None}
      and rot["per_day"] == 1 and rot["slot_times_local"] == ["10:00"],
      f"the rotation is not the owner's: {rot}")
check(cfg["cadence"]["videos_per_week"] == 6 == len(B.rotation_days(cfg)),
      "videos_per_week does not match the rotation's mapped days")
check(D.live_slots(cfg) == {DEEP: 2, MAT: 2, FOOD: 0, MONEY: 2}
      and B.domain_weekdays(cfg, 6) == {DEEP: (0, 3), MAT: (1, 4), MONEY: (2, 5),
                                        FOOD: ()},
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
    # Its own rotation day - or, since 2 Nov 2026 (any-topic fill), an EMPTY
    # Money day within BORROW_DAYS, because no Money episode is in this run.
    # Never Sunday, never inside the lead, always the slot time.
    own = B.rotation_days(cfg).get(lt.weekday()) == dom
    borrowed = (lt.weekday() in (2, 5)
                and t <= now + timedelta(days=B.BORROW_DAYS, hours=B.MIN_LEAD_HOURS))
    check((own or borrowed) and lt.weekday() != 6
          and f"{lt:%H:%M}" == "10:00" and t >= now + timedelta(hours=24),
          f"{slug} ({dom}) got {lt:%a %d %b %H:%M}: not its rotation day nor an "
          f"empty Money day within {B.BORROW_DAYS} days, or Sunday, or inside the lead")
check(len(days_seen) == len(set(days_seen)), "two episodes landed on one day")
# A topic with an episode READY keeps its days: with a Money slug in the run,
# no other topic is given a Money day, and the Money episode gets one.
_money = [x for x in D.by_slug() if D.domain_of_slug(x) == MONEY][:1]
if _money:
    w3 = B.schedule_slugs(empty, [deep[0], deep[1], _money[0]], 6)
    check(all(x.astimezone(B.PUBLISH_TZ).weekday() not in (2, 5) for x in w3[:2]),
          "a deep-sea episode took a Money day while a Money episode was ready")
    check(w3[2] is not None and w3[2].astimezone(B.PUBLISH_TZ).weekday() in (2, 5),
          f"the ready Money episode did not get a Wed/Sat slot: {w3[2]}")
else:
    check(False, "no Money slug found to prove a ready topic keeps its days")
# The paused domain never takes a slot: a ready food episode gets None, on
# its own and alongside other topics, and no weekday is mapped to food.
_food = [x for x in D.by_slug() if D.domain_of_slug(x) == FOOD][:2]
if _food:
    w4 = B.schedule_slugs(empty, [_food[0], deep[0], _food[-1]], 6)
    check(w4[0] is None and w4[2] is None and w4[1] is not None,
          f"paused food was given a slot: {w4}")
    check(FOOD not in B.rotation_days(cfg).values(),
          "a weekday is still mapped to paused food-science")
else:
    check(False, "no food slug found to prove the paused domain takes no slot")
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
while future.astimezone(B.PUBLISH_TZ).weekday() != 2:      # a Wednesday (Money)
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
              f"V20 passed a deep-sea episode dated on a Money Wednesday: {res}")
    else:
        check(not any("rotation day" in f for f in res["failures"]) and
              any(s_["code"] == "OFF_ROTATION_RESCHEDULE_PENDING" for s_ in res["stops"]),
              f"V20 did not hold a pre-rotation row for reschedule: {res}")

# The paused domain cannot hold a dated slot either: a food row dated since
# the rotation on a Money Wednesday fails V20.
if _food:
    fake.write_text(json.dumps({"published": [{
        "slug": _food[0], "video_id": "F", "privacy": "private",
        "uploaded_at": "2026-11-10T00:00:00+00:00", "scheduled_publish_at": stamp}],
        "queued": []}))
    ledger.LEDGER = fake
    try:
        res = V.v20_cadence_schedule().as_dict()
    finally:
        ledger.LEDGER = saved
    check(bool(res["failures"]),
          f"V20 passed a paused food episode dated on a Money Wednesday: {res}")

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

# Historical stamps are not future work; a hidden future slot or an invalid
# active stamp must still fail. This regression fails the pre-fix V20.
saved_tail = __import__("cadence").scheduled_tail
import cadence as C
for label, stamp_, hidden, want in (
    ("past", "2026-01-01T16:00:00Z", False, False),
    ("hidden-future", _slot(3), True, True),
    ("invalid", "not-a-date", True, True),
):
    fake.write_text(json.dumps({"published": [dict(row, video_id="TAIL", scheduled_publish_at=stamp_)], "queued": []}))
    ledger.LEDGER = fake
    if hidden:
        C.scheduled_tail = lambda: []
    try:
        res = V.v20_cadence_schedule().as_dict()
    finally:
        ledger.LEDGER = saved
        C.scheduled_tail = saved_tail
    check(bool(res["failures"]) == want, f"V20 {label}: {res['failures']}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
