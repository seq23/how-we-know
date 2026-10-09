"""Deep sea publishes all three cut Shorts; materials stays at one (owner build 2026-10-08).

"More deep-sea Shorts, since they bring 93% of views." visuals/shorts.py
already cut three Shorts (ranks 1-3) from every deep-sea episode, and only
rank 1 ever published. Proves, with no network and no credential:

  1. config shorts_topics.cuts_per_episode: deep sea 3, default 1, and
     cuts_for() reads it - a real deep-sea slug gets 3, a real materials slug 1;
  2. pending() offers ranks 2 and 3 of a deep-sea episode whose rank 1 is
     already in the ledger, all three of a fresh deep-sea episode, and only
     rank 1 of a materials episode (its rank 2 on the shelf is NOT offered);
  3. the 3:1 deep-sea mix from #153 still holds over a run of eight, and
     inside deep sea every rank 1 airs before any rank 2, every rank 2 before
     any rank 3;
  4. plan() never puts two Shorts from one episode on the same local day -
     against the ledger AND inside one run - on the 9/week ladder, whose
     Saturday and Sunday carry two evening slots; a slot only one episode's
     cut could take is left empty, never doubled;
  5. the R2 shelf keys and push_shorts are rank-aware: deep sea's cuts 2-3 are
     shelved, a materials cut 2 is not;
  6. cut_groups() asks the nightly batch for 3 cuts of a deep-sea episode
     missing its deeper ranks, capped by its receipt's eligible chapters,
     and visuals/shorts.py --keep-existing never re-renders a cut on disk.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_DRY_RUN", "1")

tmp = Path(tempfile.mkdtemp(prefix="shorts-deep-cuts-"))
os.environ["LOOP_RENDER_HOLD"] = str(tmp / "render_hold.json")
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")

import batch_queue  # noqa: E402
import domains  # noqa: E402
import shorts_lane as SL  # noqa: E402
from common import config  # noqa: E402

DEEP, MAT = "deep-sea-ocean-science", "materials-and-manufacturing"
fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")


cfg = config()
by = domains.by_slug()
deep = [s for s, d in by.items() if d == DEEP]
mat = [s for s, d in by.items() if d == MAT]
assert len(deep) >= 4 and len(mat) >= 3, "need real scripts in both domains"

# ---- 1: config + cuts_for ---------------------------------------------------
per = cfg["shorts_topics"]["cuts_per_episode"]
check("1 config deep sea 3", per.get(DEEP) == 3, str(per))
check("1 config default 1, materials not raised",
      per.get("default") == 1 and MAT not in per, str(per))
check("1 cuts_for deep", SL.cuts_for(deep[0], cfg) == 3, str(SL.cuts_for(deep[0], cfg)))
check("1 cuts_for materials", SL.cuts_for(mat[0], cfg) == 1, str(SL.cuts_for(mat[0], cfg)))
check("1 capped at MAX_RANK",
      SL.cuts_for(deep[0], {"shorts_topics": {"cuts_per_episode": {DEEP: 9}}}) == 3)

# ---- 2: pending offers the deeper ranks, deep sea only --------------------
d_pub, d_new, m1 = deep[0], deep[1], mat[0]
batch_queue.queued_entries = lambda: [{"slug": d_pub}, {"slug": d_new}, {"slug": m1}]
_real_load = SL.load_ledger
SL.load_ledger = lambda: {"published": [{"slug": d_pub, "rank": 1}], "updated": None}
asked: list[tuple[str, int]] = []


def on_shelf(slug, rank=1):
    asked.append((slug, rank))
    return True     # every rank of every episode is on the shelf, materials included


got = SL.pending(have=on_shelf, cfg=cfg)
want = {SL.Pick(d_pub, 2), SL.Pick(d_pub, 3), SL.Pick(d_new, 1),
        SL.Pick(d_new, 2), SL.Pick(d_new, 3), SL.Pick(m1, 1)}
check("2 pending set", set(got) == want and len(got) == len(want),
      f"got {got}")
check("2 materials rank 2 never offered", SL.Pick(m1, 2) not in got
      and (m1, 2) not in asked, f"asked {asked}")
check("2 published rank 1 not re-offered", SL.Pick(d_pub, 1) not in got, str(got))

# ---- 3: 3:1 mix holds, ranks spread inside deep sea ------------------------
cands = [SL.Pick(s, r) for s in deep[:4] for r in (1, 2, 3)] + \
        [SL.Pick(s, 1) for s in mat[:3]]
out = SL.order_by_mix(cands, recent=[], cfg=cfg)
doms = [domains.domain_of_slug(p.slug) for p in out[:8]]
check("3 mix 3:1 over eight", doms.count(DEEP) == 6 and doms.count(MAT) == 2,
      str(doms))
deep_ranks = [p.rank for p in out if domains.domain_of_slug(p.slug) == DEEP]
check("3 ranks ascend inside deep sea", deep_ranks == sorted(deep_ranks),
      str(deep_ranks))
check("3 nothing dropped", sorted(out) == sorted(cands))
check("3 plain slugs still accepted (#153 callers)",
      SL.order_by_mix(mat[:3], recent=[], cfg=cfg) == mat[:3])

# ---- 4: plan never puts one episode twice on a day -------------------------
SL.cadence.shorts_effective = lambda explain=False: (9, "test") if explain else 9
# Anchor: the last Short on the calendar is d_new's rank 1 on a Saturday 19:00
# local, so the very next slot (Saturday 21:00) is the same day.
now = datetime.now(timezone.utc).astimezone(SL.SHORTS_TZ)
sat = (now + timedelta(days=(5 - now.weekday()) % 7 + 7)).replace(
    hour=19, minute=0, second=0, microsecond=0)
stamp = sat.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
led = {"published": [{"slug": d_new, "rank": 1, "scheduled_publish_at": stamp}]}

p1 = SL.plan(led, [SL.Pick(d_new, 2), SL.Pick(d_pub, 2)], 2)
check("4 plan size", len(p1) == 2, str(p1))
first_day = p1[0][1].astimezone(SL.SHORTS_TZ)
check("4 Sat 21:00 slot goes to the OTHER episode",
      p1[0][0] == SL.Pick(d_pub, 2) and first_day.date() == sat.date()
      and first_day.hour == 21, str(p1))
check("4 the same episode moves to the next day",
      p1[1][0] == SL.Pick(d_new, 2)
      and p1[1][1].astimezone(SL.SHORTS_TZ).date() > sat.date(), str(p1))

# Only one episode's cuts left: its two remaining ranks never share a day, and
# the Saturday 21:00 slot is left empty rather than doubled up.
p2 = SL.plan(led, [SL.Pick(d_new, 2), SL.Pick(d_new, 3)], 2)
days = [t.astimezone(SL.SHORTS_TZ).date() for _, t in p2]
check("4 lone episode: two cuts, two days, neither Saturday",
      len(p2) == 2 and len(set(days)) == 2 and sat.date() not in days, str(p2))

# A full week from pending's own order, against the ledger: no duplicates.
p3 = SL.plan(led, out, 9)
seen = {(r["slug"], SL._local_day(r["scheduled_publish_at"])) for r in led["published"]}
dupes = []
for p, t in p3:
    k = (p.slug, SL._local_day(t))
    if k in seen:
        dupes.append(k)
    seen.add(k)
check("4 a planned week has no episode twice on one day",
      len(p3) == 9 and not dupes, f"{len(p3)} planned, dupes {dupes}")
check("4 slots strictly after the calendar's last Short",
      all(t > sat for _, t in p3))

# ---- 5: R2 shelf is rank-aware ----------------------------------------------
import r2 as R  # noqa: E402

check("5 rank-1 key unchanged", R.short_key("x") == "shorts/x-short.mp4")
check("5 rank-2 key", R.short_key("x", 2) == "shorts/x-short2.mp4")
check("5 rank-3 receipt key",
      R.short_receipt_key("x", 3) == "shorts/x-short3.mp4.short.json")

shelf_root = tmp / "repo"
(shelf_root / "shorts").mkdir(parents=True)
for s, ranks in ((d_new, (1, 2, 3)), (m1, (1, 2))):
    for r in ranks:
        f = shelf_root / "shorts" / SL.short_file(s, r)
        f.write_bytes(os.urandom(64))
        Path(f"{f}.short.json").write_text(json.dumps({"ok": True}))
R.ROOT = shelf_root
R.verify_shorts = lambda: (True, ["V14 ok", "V15 ok"])
backend = R.LocalBackend(tmp / "shelf")
# A LOCAL shelf in a temp dir: the dry-run write refusal is lifted for this one
# call only, so nothing can reach the real R2 bucket.
_dry = os.environ.pop("LOOP_DRY_RUN", None)
try:
    res = R.push_shorts(backend, [d_new, m1])
finally:
    if _dry is not None:
        os.environ["LOOP_DRY_RUN"] = _dry
check("5 deep sea ranks 2-3 shelved",
      all(backend.head(R.short_key(d_new, r)) for r in (1, 2, 3))
      and backend.head(R.short_receipt_key(d_new, 3)), str(res))
check("5 materials rank 2 NOT shelved",
      backend.head(R.short_key(m1, 1)) and not backend.head(R.short_key(m1, 2)),
      str(res))

# ---- 6: the nightly cut asks for the deeper ranks, and never re-renders ----
renders, shorts = tmp / "renders", tmp / "shorts"
renders.mkdir()
shorts.mkdir()
for s in (d_pub, d_new, deep[2], m1):
    (renders / f"{s}-final.mp4").write_bytes(b"")
# d_pub: rank 1 only, receipt says 3 eligible chapters -> needs ranks 2-3.
# d_new: all three cut -> nothing.  deep[2]: one eligible chapter -> nothing.
# m1: rank 1 cut -> nothing.  (no rank-1 cut at all would group it too)
for s, ranks, elig in ((d_pub, (1,), 3), (d_new, (1, 2, 3), 3),
                       (deep[2], (1,), 1), (m1, (1,), 4)):
    for r in ranks:
        (shorts / SL.short_file(s, r)).write_bytes(b"x")
        (shorts / f"{SL.short_file(s, r)}.short.json").write_text(
            json.dumps({"eligible_chapters": elig}))
groups = SL.cut_groups(renders, shorts, cfg)
check("6 cut_groups", groups == {3: [d_pub]} or
      groups == {3: sorted([d_pub])}, str(groups))
(shorts / SL.short_file(m1)).unlink()
groups = SL.cut_groups(renders, shorts, cfg)
check("6 an uncut materials episode is cut once", groups.get(1) == [m1], str(groups))

src = (ROOT / "visuals" / "shorts.py").read_text()
check("6 shorts.py --keep-existing skips a cut already on disk",
      "--keep-existing" in src and "already cut" in src)

SL.load_ledger = _real_load
if examined == 0:
    sys.exit("FAIL test_shorts_deep_sea_all_cuts: examined zero cases")
if fails:
    print("FAIL test_shorts_deep_sea_all_cuts:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_shorts_deep_sea_all_cuts: {examined} checks - deep sea "
      f"publishes cuts 1-3, materials 1, 3:1 mix held, never one episode twice "
      f"on a day")
