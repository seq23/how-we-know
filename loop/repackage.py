"""The long-form REPACKAGE lane: new titles and contract thumbnails on the
videos already published. Long-form ONLY; Shorts are untouched.

    python loop/repackage.py apply      [--slugs a b] [--limit N] [--dry-run]
    python loop/repackage.py reschedule [--limit N] [--dry-run]

Owner decisions, 12-13 Oct 2026 (repackage job 1 of 3; job 2 runs `apply` over
every published long-form video). Binding: nothing is privated by niche,
nothing starts over, both niches stay on the one channel.

FORWARD ONLY (owner decision, 13 Oct 2026, later the same day): a published
video is never re-rendered, re-uploaded, extended or privated. Its title and
thumbnail are the ONLY things this repo changes on it, and this lane is the
only place that does. (The re-upload command first built here was removed the
same day, before it had touched anything.)

APPLY. For every slug in loop/state/titles.json whose proposal passed
(checks_passed) and is not yet applied: re-check the title against today's
script (loop/longform_title.py - a title that stopped being true is not
applied), read the live snippet, write the new title onto it with
ytmeta.merge_snippet (videos.update replaces the whole snippet; V19), and set
the contract thumbnail's variant A (visuals/thumb_contract.py chooser) with
thumbnails.set. Cost per video: videos.list 1 + videos.update 50 +
thumbnails.set 50. `applied_at` is written into titles.json; a run stopped by
quota resumes the next day in the same order.

APPLY covers every live long-form video in the ledger - public AND
private-scheduled (not retired).

RESCHEDULE (owner decision 2026-10-13, the three-niche rotation). Every
uploaded, private, still-scheduled long-form video is re-dated onto the next
free slot of its OWN domain's rotation weekdays (cadence.rotation in
loop/config.json): order kept within each domain, at most one a day, never
inside the 24-hour lead. videos.update (part=status) only - 50 units each plus
a 1-unit read-back; nothing is uploaded, deleted or made public. The ledger row
keeps `rescheduled_from`. V20 holds every dated row to the rotation.

QUOTA. Every unit is recorded in loop/state/quota.json under lane
"repackage". A run plans only what fits the day's usable allowance AFTER the
episode upload reserve and the Shorts lane's 3,400 (quota.upload_reserve() +
quota.shorts_reserve()); what does not fit waits for tomorrow
(QUOTA_EXHAUSTED, self-resolving, with resets_at).

CREDENTIALS. The same YT_OAUTH_CLIENT_JSON / YT_OAUTH_REFRESH_TOKEN path as
the cloud lanes (loop/upload.load_credentials), in
.github/workflows/loop-repackage.yml, armed by loop/arming.py like the Shorts
lane.

Guarded by validator V50 (loop/validate.py) and loop/tests/test_repackage.py
(fixtured API; negative proof that the quota guard refuses).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import quota                                               # noqa: E402

LANE = "repackage"

APPLY_UNITS = quota.VIDEO_READ + quota.VIDEO_UPDATE + quota.THUMBNAIL      # 101
APPLY_TITLE_ONLY = quota.VIDEO_READ + quota.VIDEO_UPDATE                  # 51

API = "https://www.googleapis.com/youtube/v3"


def _now() -> datetime:
    return datetime.now(timezone.utc)





def reserve() -> int:
    """What this lane must never touch: the day's episode upload and the
    Shorts lane's 3,400 (two whole Short uploads) until each has run."""
    return quota.upload_reserve() + quota.shorts_reserve()


def affordable(unit_cost: int, want: int) -> int:
    return quota.units_affordable(unit_cost, want, reserve=reserve())






# ------------------------------------------------------------- the client
class YouTube:
    """The calls this lane makes. Tests pass a fixture with the same methods."""

    def __init__(self, token: str):
        self.token = token

    def _req(self, method, path, params, body=None):
        q = urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{API}/{path}?{q}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     **({"Content-Type": "application/json; charset=UTF-8"}
                        if data is not None else {})})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    def video(self, vid: str) -> dict | None:
        items = self._req("GET", "videos", {"part": "snippet,status",
                                            "id": vid}).get("items") or []
        return items[0] if items else None

    def update_snippet(self, vid: str, snippet: dict) -> None:
        self._req("PUT", "videos", {"part": "snippet"},
                  {"id": vid, "snippet": snippet})


    def set_schedule(self, vid: str, publish_at: str) -> None:
        """videos.update part=status: private with a new publishAt (50 units)."""
        import publish as P                                # noqa: PLC0415
        P.set_privacy(self.token, vid, "private", publish_at=publish_at)

    def status(self, vid: str) -> dict:
        import publish as P                                # noqa: PLC0415
        return P.read_status_full(self.token, vid)

    def set_thumbnail(self, vid: str, img: Path) -> None:
        import backfill                                    # noqa: PLC0415
        backfill.set_thumbnail(self.token, vid, img)



def client(st, dry_run: bool):
    import upload as up                                    # noqa: PLC0415
    from common import config                              # noqa: PLC0415
    creds = up.load_credentials(config())
    if not creds or creds.get("unusable"):
        if dry_run:
            return None
        code, msg, unblock = up.credential_stop(creds, config())
        st.named_stop(code, msg, unblock=unblock)
    return YouTube(up.access_token(creds))


# ----------------------------------------------------------------- apply
def apply_plan(slugs: list[str] | None = None) -> list[dict]:
    """Rows of titles.json ready to go onto live videos, in a stable order."""
    import ledger                                          # noqa: PLC0415
    import longform_title as LT                            # noqa: PLC0415
    live = {r["slug"]: r for r in ledger.load()["published"]
            if r.get("video_id") and not r.get("retired_at")}
    out = []
    for slug, row in sorted(LT.load()["titles"].items()):
        if slugs and slug not in slugs:
            continue
        if not row.get("checks_passed") or slug not in live:
            continue                     # queued: the upload lane uses it
        if row.get("applied_at"):
            # A title that went up without its thumbnail (no contract variant
            # existed yet) gets the thumbnail alone once variant A exists -
            # otherwise applied_at would hide it from this lane for good.
            if (not row.get("thumbnail_applied")
                    and row.get("applied_video_id") == live[slug]["video_id"]
                    and thumb_for(slug)):
                out.append({"slug": slug, "video_id": live[slug]["video_id"],
                            "title": row["new_title"],
                            "question": row.get("question"),
                            "thumb_only": True})
            continue
        out.append({"slug": slug, "video_id": live[slug]["video_id"],
                    "title": row["new_title"], "question": row.get("question")})
    return out


def thumb_for(slug: str) -> Path | None:
    sys.path.insert(0, str(ROOT / "visuals"))
    import thumb_contract                                  # noqa: PLC0415
    p = Path(thumb_contract.chooser(slug))
    return p if p.exists() else None


def run_apply(slugs=None, limit: int = 0, dry_run: bool = False, yt=None) -> int:
    from common import Stage, week_id                      # noqa: PLC0415
    import breaker                                         # noqa: PLC0415
    import longform_title as LT                            # noqa: PLC0415
    import ytmeta                                          # noqa: PLC0415
    breaker.guard(f"{LANE}-apply")
    with Stage(f"{LANE}-apply", week_id(),
               zero_work_hint="No proposed title is waiting to be applied.") as st:
        todo = apply_plan(slugs)
        if limit:
            todo = todo[:limit]
        if not todo:
            st.named_stop("REPACKAGE_UP_TO_DATE",
                          "every passing title in loop/state/titles.json is "
                          "already on its live video",
                          unblock="Nothing to do. loop/longform_title.py "
                                  "propose writes new rows; this lane applies "
                                  "them on its next run.")
        fit = affordable(APPLY_UNITS, len(todo))
        if fit < len(todo):
            st.note(f"quota fits {fit} of {len(todo)} today; the rest wait, in "
                    f"order. {quota.report()}")
        if fit == 0:
            st.named_stop("QUOTA_EXHAUSTED",
                          f"{len(todo)} title(s) ready to apply and the day's "
                          f"usable allowance after the upload and Shorts "
                          f"reserves ({reserve()} units) does not fit one",
                          detail={"resets_at": quota.next_reset(),
                                  "waiting": [t["slug"] for t in todo]},
                          unblock="Nothing to do: tomorrow's run resumes where "
                                  "this one stopped.")
        todo = todo[:fit]
        if dry_run:
            for t in todo:
                if t.get("thumb_only"):
                    st.work(f"DRY RUN would thumbnail {t['video_id']} "
                            f"({t['slug']}) with variant A (title already applied)")
                    continue
                st.work(f"DRY RUN would title {t['video_id']} ({t['slug']}) "
                        f"{t['title']!r}" + (" + thumbnail A" if thumb_for(t['slug'])
                                             else " (no contract thumbnail yet)"))
            return 0
        import arming                                      # noqa: PLC0415
        arming.gate(st, LANE)
        yt = yt or client(st, dry_run)
        doc = LT.load()
        import ledger                                      # noqa: PLC0415
        led = ledger.load()
        rows = {r["slug"]: r for r in led["published"]}
        for t in todo:
            if t.get("thumb_only"):
                img = thumb_for(t["slug"])
                yt.set_thumbnail(t["video_id"], img)
                quota.spend(quota.THUMBNAIL, LANE)
                row_ = doc["titles"][t["slug"]]
                row_["thumbnail_applied"] = True
                row_["thumbnail_applied_at"] = _now().isoformat(timespec="seconds")
                st.work(f"{t['video_id']} ({t['slug']}) thumbnailed (variant A; "
                        f"its title went up earlier)")
                continue
            script = (ROOT / "scripts" / f"{t['slug']}.md").read_text(encoding="utf-8")
            why = LT.title_problems(t["title"], script, t.get("question"))
            if why:
                st.note(f"{t['slug']}: not applied, the title no longer passes: "
                        f"{why[0]}")
                continue
            live = yt.video(t["video_id"])
            if not live:
                st.note(f"{t['slug']}: {t['video_id']} not found on the channel")
                quota.spend(quota.VIDEO_READ, LANE)
                continue
            snippet = ytmeta.merge_snippet(live.get("snippet"), title=t["title"])
            yt.update_snippet(t["video_id"], snippet)
            spent = quota.VIDEO_READ + quota.VIDEO_UPDATE
            img = thumb_for(t["slug"])
            if img:
                yt.set_thumbnail(t["video_id"], img)
                spent += quota.THUMBNAIL
            quota.spend(spent, LANE)
            stamp = _now().isoformat(timespec="seconds")
            doc["titles"][t["slug"]]["applied_at"] = stamp
            doc["titles"][t["slug"]]["applied_video_id"] = t["video_id"]
            doc["titles"][t["slug"]]["thumbnail_applied"] = bool(img)
            r = rows.get(t["slug"])
            if r is not None:
                r["title"] = t["title"]
            st.work(f"{t['video_id']} ({t['slug']}) retitled {t['title']!r}"
                    + (" and thumbnailed (variant A)" if img else ""))
        LT.save(doc)
        ledger.save(led)
        if st.units:
            arming.record_success(LANE, detail=f"applied {len(st.units)} "
                                               f"title(s)/thumbnail(s)")
    return 0


# ------------------------------------------------------------- reschedule
def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reschedule_plan(led: dict | None = None) -> list[dict]:
    """Every uploaded, private, still-scheduled long-form video, re-dated onto
    the next free slot of its OWN domain's rotation weekdays.

    Order is kept within each domain (oldest date first gets the earliest new
    slot); the slots these rows vacate do not block them; at most per_day a
    day (one), never earlier than MIN_LEAD_HOURS from now. A row whose domain
    holds no rotation day keeps its date and is reported."""
    import backfill as B                                   # noqa: PLC0415
    import domains                                         # noqa: PLC0415
    import ledger                                          # noqa: PLC0415
    from common import config                              # noqa: PLC0415
    from datetime import timedelta                         # noqa: PLC0415
    led = led or ledger.load()
    now = _now()
    rows = []
    for r in led["published"]:
        st = r.get("scheduled_publish_at")
        if (not st or not r.get("video_id") or r.get("retired_at")
                or r.get("schedule_cancelled_at") or r.get("published_at")
                or r.get("privacy") == "public"):
            continue
        when = datetime.fromisoformat(st.replace("Z", "+00:00"))
        # A video due inside the lead time keeps its date: re-dating one that
        # is about to air would pull a release the audience may already be
        # waiting for. Once it airs it leaves the tail.
        if when > now + timedelta(hours=B.MIN_LEAD_HOURS):
            rows.append((when, r))
    rows.sort(key=lambda x: x[0])
    vacating = {_iso(w).replace("Z", "+00:00") for w, _ in rows}
    taken = {t for t in B.occupied(led) if t not in vacating}
    split = B.domain_weekdays(config(), 0)
    base = now + timedelta(hours=B.MIN_LEAD_HOURS)
    out = []
    for when, r in rows:
        dom = domains.domain_of_slug(r["slug"]) or "deep-sea-ocean-science"
        days = split.get(dom)
        if not days:
            out.append({"slug": r["slug"], "video_id": r["video_id"],
                        "domain": dom, "old": _iso(when), "new": None})
            continue
        t = B.rotation_slots(base, 1, days, taken)[0]
        taken.add(t.isoformat())
        out.append({"slug": r["slug"], "video_id": r["video_id"],
                    "domain": dom, "old": _iso(when), "new": _iso(t)})
    return out


READBACK_WAITS_S = (3, 6, 10, 15, 20)
SLEEP = __import__("time").sleep          # tests replace it


def _pa(status: dict) -> str:
    return (status.get("publishAt") or "").replace(".000Z", "Z")


def run_reschedule(limit: int = 0, dry_run: bool = False, yt=None) -> int:
    """Re-date the scheduled long-form videos onto the rotation (owner
    decision 2026-10-13). videos.update only - 50 units a video; nothing is
    uploaded, deleted or made public."""
    from common import Stage, week_id                      # noqa: PLC0415
    import backfill as B                                   # noqa: PLC0415
    import ledger                                          # noqa: PLC0415
    import breaker                                         # noqa: PLC0415
    breaker.guard(f"{LANE}-reschedule")
    with Stage(f"{LANE}-reschedule", week_id(),
               zero_work_hint="No scheduled video needed re-dating.") as st:
        plan = reschedule_plan()
        moves = [p for p in plan if p["new"] and p["new"] != p["old"]]
        for p in plan:
            print(f"  {p['slug']:<52} {p['old']} -> {p['new'] or 'NO ROTATION DAY'}"
                  f"  ({p['domain']})")
        for p in plan:
            if not p["new"]:
                st.note(f"{p['slug']}: {p['domain']} holds no rotation day; "
                        f"its date is kept")
        if limit:
            moves = moves[:limit]
        if not moves:
            st.named_stop("RESCHEDULE_UP_TO_DATE",
                          f"all {len(plan)} scheduled long-form video(s) already "
                          f"sit on their rotation day",
                          unblock="Nothing to do.")
        fit = affordable(quota.VIDEO_UPDATE + quota.VIDEO_READ * 6, len(moves))
        if fit == 0:
            st.named_stop("QUOTA_EXHAUSTED",
                          f"{len(moves)} video(s) to re-date and no room after "
                          f"the upload and Shorts reserves ({reserve()} units)",
                          detail={"resets_at": quota.next_reset(),
                                  "waiting": [m["slug"] for m in moves]},
                          unblock="Nothing to do: tomorrow's run resumes.")
        moves = moves[:fit]
        if dry_run:
            for m in moves:
                st.work(f"DRY RUN would re-date {m['video_id']} ({m['slug']}) "
                        f"{m['old']} -> {m['new']}")
            return 0
        import arming                                      # noqa: PLC0415
        arming.gate(st, LANE)
        yt = yt or client(st, dry_run)
        led = ledger.load()
        by_id = {r.get("video_id"): r for r in led["published"]}
        for m in moves:
            # READ FIRST: a re-date YouTube already holds (an earlier run's
            # write whose read-back was stale) is recorded, not re-sent.
            got = yt.status(m["video_id"]) or {}
            spent_ = quota.VIDEO_READ
            if _pa(got) != m["new"]:
                yt.set_schedule(m["video_id"], m["new"])
                spent_ += quota.VIDEO_UPDATE
                # THE READ-BACK IS EVENTUALLY CONSISTENT. 2026-10-13, run
                # 38401393843: all ten writes applied, and every immediate
                # read-back still returned the old publishAt - so the lane
                # kept the old dates and called it a failure. Poll briefly.
                for wait in READBACK_WAITS_S:
                    got = yt.status(m["video_id"]) or {}
                    spent_ += quota.VIDEO_READ
                    if _pa(got) == m["new"]:
                        break
                    SLEEP(wait)
            quota.spend(spent_, LANE)
            pa = _pa(got)
            if pa != m["new"] or got.get("privacy") not in (None, "private"):
                st.note(f"{m['slug']}: YouTube reports publishAt={pa!r} "
                        f"privacy={got.get('privacy')!r} after re-dating to "
                        f"{m['new']}; the ledger keeps the old date")
                continue
            r = by_id[m["video_id"]]
            r.setdefault("rescheduled_from", []).append(m["old"])
            r["scheduled_publish_at"] = m["new"]
            r["rescheduled_at"] = _now().isoformat(timespec="seconds")
            ledger.save(led)
            st.work(f"{m['video_id']} ({m['slug']}) re-dated {m['old']} -> "
                    f"{m['new']} ({datetime.fromisoformat(m['new'].replace('Z', '+00:00')).astimezone(B.PUBLISH_TZ):%a %d %b %H:%M %Z})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("apply", "reschedule"))
    ap.add_argument("--slugs", nargs="*")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "reschedule":
        return run_reschedule(a.limit, a.dry_run)
    return run_apply(a.slugs, a.limit, a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
