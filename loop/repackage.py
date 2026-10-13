"""The long-form REPACKAGE lane: new titles and thumbnails on live videos, and
longer cuts re-uploaded as new videos. Long-form ONLY; Shorts are untouched.

    python loop/repackage.py apply    [--slugs a b] [--limit N] [--dry-run]
    python loop/repackage.py reupload [--slugs a b] [--limit N] [--dry-run]

Owner decisions, 12-13 Oct 2026 (repackage job 1 of 3; job 2 runs this over
every published and queued long-form video). Binding: nothing is privated by
niche, nothing starts over, both niches stay on the one channel.

APPLY. For every slug in loop/state/titles.json whose proposal passed
(checks_passed) and is not yet applied: re-check the title against today's
script (loop/longform_title.py - a title that stopped being true is not
applied), read the live snippet, write the new title onto it with
ytmeta.merge_snippet (videos.update replaces the whole snippet; V19), and set
the contract thumbnail's variant A (visuals/thumb_contract.py chooser) with
thumbnails.set. Cost per video: videos.list 1 + videos.update 50 +
thumbnails.set 50. `applied_at` is written into titles.json.

REUPLOAD. For every episode loop/lengthen.py has SPLICED to 10:30-11:30 that is
already published, in two phases across runs:
  1. upload the new render (pulled from R2, its sha256 must equal the one
     lengthen.json recorded) as a NEW video - its own title (the long-form
     formula), description, tags, variant-A thumbnail - private with a
     publishAt at the next free REPACKAGE SLOT. Slots are fixed local times
     (loop/config.json repackage.slot_times_local, America/Chicago), at most
     LONG_FORM_PER_DAY a day (repackage.long_form_per_day, default 2 - the
     owner's choice, hers to change), never a slot already past or closer than
     min_lead_hours. 1,600 + 50 + 50 units.
  2. once YouTube reports the new id PUBLIC: re-point loop/state/ledger.json's
     row to it (old id kept in `replaced_video_ids`), re-point every Short's
     `handoff_episode` in shorts_ledger.json (set back to pending so the
     hand-off lane re-links its description), move the playlist membership
     (the new id is inserted; the old row stays, hidden once private,
     because this repo has no HTTP DELETE), and make the OLD video PRIVATE via videos.update
     - verified, never deleted (CLAUDE.md: there is no delete path here).
     old -> new is recorded in loop/state/repackage.json. ~102 units.
When no spliced episode is waiting, the lane does nothing and says so
(REPACKAGE_NO_BACKLOG, green): the channel's standing 4-a-week cadence is the
upload lane's and is never touched by this one, so the drain "drops back"
by itself the day the backlog is empty.

QUOTA. Every unit is recorded in loop/state/quota.json under lane
"repackage". A run plans only what fits the day's usable allowance AFTER the
episode upload reserve and the Shorts lane's 3,400 (quota.upload_reserve() +
quota.shorts_reserve()); what does not fit waits for tomorrow, in the same
order (QUOTA_EXHAUSTED, self-resolving, with resets_at). It never starts a
video it cannot finish.

CREDENTIALS. The same YT_OAUTH_CLIENT_JSON / YT_OAUTH_REFRESH_TOKEN path as
the cloud lanes (loop/upload.load_credentials); the API calls run in
.github/workflows/loop-repackage.yml, the renders come from the Mac via R2. The
lane is armed by loop/arming.py exactly like the Shorts lane: the first run is
a dispatch with limit=1.

Guarded by validator V50 (loop/validate.py) and loop/tests/test_repackage.py
(fixtured API; negative proof that the quota guard refuses).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import quota                                               # noqa: E402

LANE = "repackage"
STATE = LOOP / "state" / "repackage.json"
SHORTS_LEDGER = LOOP / "state" / "shorts_ledger.json"
PLAYLISTS = LOOP / "state" / "playlists.json"
LEDGER = LOOP / "state" / "ledger.json"

APPLY_UNITS = quota.VIDEO_READ + quota.VIDEO_UPDATE + quota.THUMBNAIL      # 101
APPLY_TITLE_ONLY = quota.VIDEO_READ + quota.VIDEO_UPDATE                  # 51
REUPLOAD_UNITS = quota.UPLOAD + quota.THUMBNAIL + quota.PRIVACY_FLIP      # 1700
PROMOTE_UNITS = (quota.VIDEO_READ + 50 + quota.PRIVACY_FLIP
                 + quota.VIDEO_READ)                                      # 102

DEFAULTS = {"long_form_per_day": 2, "slot_times_local": ["11:00", "15:00",
                                                         "13:00", "17:00"],
            "tz": "America/Chicago", "min_lead_hours": 2}
API = "https://www.googleapis.com/youtube/v3"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def settings() -> dict:
    from common import config                              # noqa: PLC0415
    s = dict(DEFAULTS)
    s.update((config().get("repackage") or {}))
    env = os.environ.get("LONG_FORM_PER_DAY", "").strip()
    if env.isdigit():
        s["long_form_per_day"] = int(env)
    return s


def reserve() -> int:
    """What this lane must never touch: the day's episode upload and the
    Shorts lane's 3,400 (two whole Short uploads) until each has run."""
    return quota.upload_reserve() + quota.shorts_reserve()


def affordable(unit_cost: int, want: int) -> int:
    return quota.units_affordable(unit_cost, want, reserve=reserve())


# ------------------------------------------------------------------ state
def _read(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _write(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def load() -> dict:
    d = _read(STATE, {})
    d.setdefault("reuploads", {})
    d.setdefault("replaced", {})
    return d


def save(d: dict) -> None:
    d["updated"] = _now().isoformat(timespec="seconds")
    _write(STATE, d)


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

    def set_status(self, vid: str, privacy: str, publish_at: str | None = None) -> None:
        import publish as P                                # noqa: PLC0415
        P.set_privacy(self.token, vid, privacy, publish_at=publish_at)

    def set_thumbnail(self, vid: str, img: Path) -> None:
        import backfill                                    # noqa: PLC0415
        backfill.set_thumbnail(self.token, vid, img)

    def upload(self, payload: dict, video: Path) -> str:
        import upload as up                                # noqa: PLC0415
        return up.resumable_upload(self.token, payload, video)

    def playlist_insert(self, pid: str, vid: str) -> str:
        out = self._req("POST", "playlistItems", {"part": "snippet"},
                        {"snippet": {"playlistId": pid, "resourceId": {
                            "kind": "youtube#video", "videoId": vid}}})
        return out["id"]


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
        if not row.get("checks_passed") or row.get("applied_at"):
            continue
        if slug not in live:
            continue                     # queued: the upload lane uses it
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
                st.work(f"DRY RUN would title {t['video_id']} ({t['slug']}) "
                        f"{t['title']!r}" + (" + thumbnail A" if thumb_for(t['slug'])
                                             else " (no contract thumbnail yet)"))
            return 0
        yt = yt or client(st, dry_run)
        doc = LT.load()
        import ledger                                      # noqa: PLC0415
        led = ledger.load()
        rows = {r["slug"]: r for r in led["published"]}
        for t in todo:
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
    return 0


# -------------------------------------------------------------- reupload
def slots(n: int, taken: set[str], now: datetime | None = None,
          cfg: dict | None = None) -> list[datetime]:
    """The next `n` free repackage slots, at fixed local times, at most
    long_form_per_day a day, none already past or inside the lead time."""
    c = cfg or settings()
    tz = ZoneInfo(c["tz"])
    per_day = max(0, int(c["long_form_per_day"]))
    times = list(c["slot_times_local"])[:per_day]
    if not times or n <= 0:
        return []
    now = now or _now()
    earliest = now + timedelta(hours=float(c["min_lead_hours"]))
    out: list[datetime] = []
    day = now.astimezone(tz).date()
    for _ in range(366):
        for t in times:
            hh, mm = (int(x) for x in t.split(":"))
            s = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            if s <= earliest or _iso(s) in taken:
                continue
            out.append(s)
            if len(out) == n:
                return out
        day += timedelta(days=1)
    return out


def backlog(slugs=None) -> list[str]:
    import lengthen                                        # noqa: PLC0415
    import ledger                                          # noqa: PLC0415
    pub = {r["slug"] for r in ledger.load()["published"]
           if r.get("video_id") and not r.get("retired_at")}
    doc = load()
    return [s for s in lengthen.ready_for_reupload()
            if s in pub and s not in doc["reuploads"]
            and (not slugs or s in slugs)]


def taken_slots() -> set[str]:
    import ledger                                          # noqa: PLC0415
    t = {r.get("scheduled_publish_at") for r in ledger.load()["published"]}
    t |= {r.get("scheduled_publish_at") for r in load()["reuploads"].values()}
    return {x for x in t if x}


def promote(st, yt, doc: dict, slug: str, rec: dict) -> bool:
    """Phase 2: the new id is public -> re-point everything, private the old."""
    import ledger                                          # noqa: PLC0415
    new, old = rec["new_video_id"], rec["old_video_id"]
    v = yt.video(new)
    spent = quota.VIDEO_READ
    if not v or (v.get("status") or {}).get("privacyStatus") != "public":
        quota.spend(spent, LANE)
        return False
    led = ledger.load()
    row = next((r for r in led["published"] if r.get("slug") == slug
                and r.get("video_id") == old), None)
    pl = _read(PLAYLISTS, {}).get("playlists") or {}
    import domains                                         # noqa: PLC0415
    pid = (pl.get(domains.domain_of_slug(slug) or "") or {}).get("id")
    new_item = None
    if pid:
        new_item = yt.playlist_insert(pid, new)
        spent += 50
    # The old video's playlist row is LEFT, not removed: this repo has no HTTP
    # DELETE anywhere (docs/OPERATING-MANUAL.md, test_manual_conformance), and
    # YouTube hides a private video from everyone but the owner in a playlist.
    yt.set_status(old, "private")
    spent += quota.PRIVACY_FLIP
    after = yt.video(old)
    spent += quota.VIDEO_READ
    quota.spend(spent, LANE)
    if not after or (after.get("status") or {}).get("privacyStatus") != "private":
        st.note(f"{slug}: asked YouTube to make the old video {old} private and "
                f"it reports {((after or {}).get('status') or {}).get('privacyStatus')!r};"
                f" retried next run")
        rec["old_private_pending"] = True
    stamp = _now().isoformat(timespec="seconds")
    if row is not None:
        row.setdefault("replaced_video_ids", []).append(
            {"video_id": old, "replaced_at": stamp, "privated": not rec.get("old_private_pending")})
        row["video_id"] = new
        row["privacy"] = "public"
        row["scheduled_publish_at"] = rec["scheduled_publish_at"]
        row["title"] = rec.get("title") or row.get("title")
        if new_item:
            row["playlist_item_id"] = new_item
            row["playlist"] = pid
        else:
            row.pop("playlist_item_id", None)
        row["note"] = f"repackage: longer cut re-uploaded as {new}; {old} private"
        led["updated"] = stamp
        ledger.save(led)
    sh = _read(SHORTS_LEDGER, {"published": []})
    moved = 0
    for s in sh.get("published") or []:
        if s.get("handoff_episode") == old or (s.get("slug") == slug
                                               and s.get("handoff") == "done"):
            s["handoff_episode"] = new
            s["handoff"] = "pending"
            moved += 1
    if moved:
        _write(SHORTS_LEDGER, sh)
    rec.update({"phase": "replaced", "replaced_at": stamp,
                "shorts_repointed": moved})
    doc["replaced"][old] = new
    st.work(f"{slug}: {new} is public; ledger, {moved} Short hand-off(s) and "
            f"the playlist now point at it; {old} set private (never deleted)")
    return True


def run_reupload(slugs=None, limit: int = 0, dry_run: bool = False, yt=None,
                 shelf=None) -> int:
    from common import Stage, week_id                      # noqa: PLC0415
    import arming                                          # noqa: PLC0415
    import breaker                                         # noqa: PLC0415
    import lengthen                                        # noqa: PLC0415
    import ledger                                          # noqa: PLC0415
    breaker.guard(f"{LANE}-reupload")
    with Stage(f"{LANE}-reupload", week_id(),
               zero_work_hint="No lengthened episode is waiting.") as st:
        if not dry_run:
            arming.gate(st, LANE)
        doc = load()
        waiting = {s: r for s, r in doc["reuploads"].items()
                   if r.get("phase") == "scheduled"}
        due = {s: r for s, r in waiting.items()
               if r.get("scheduled_publish_at", "") <= _iso(_now())}
        todo = backlog(slugs)
        if limit:
            todo = todo[:limit]
        if not todo and not waiting:
            st.named_stop("REPACKAGE_NO_BACKLOG",
                          "no lengthened episode is waiting to be re-uploaded",
                          unblock="Nothing to do. loop/lengthen.py splices "
                                  "episodes on the Mac; this lane re-uploads "
                                  "each one the run after it is shelved. The "
                                  "standing 4-a-week cadence is unaffected.")
        if dry_run:
            when = slots(len(todo), taken_slots())
            for s, t in zip(todo, when):
                st.work(f"DRY RUN would re-upload {s} for {_iso(t)} "
                        f"(slot {t:%a %H:%M %Z})")
            for s in due:
                st.work(f"DRY RUN would promote {s} if "
                        f"{waiting[s]['new_video_id']} is public")
            if not todo and not due:
                st.work(f"DRY RUN: {len(waiting)} re-upload(s) scheduled, none "
                        f"due yet")
            return 0
        yt = yt or client(st, dry_run)
        # -- phase 2 first: promotions are cheap and finish earlier work.
        fit_p = affordable(PROMOTE_UNITS, len(due))
        for s in list(due)[:fit_p]:
            promote(st, yt, doc, s, doc["reuploads"][s])
            save(doc)
        # -- phase 1
        fit = affordable(REUPLOAD_UNITS, len(todo))
        if todo and fit == 0:
            save(doc)
            st.named_stop("QUOTA_EXHAUSTED",
                          f"{len(todo)} lengthened episode(s) ready to "
                          f"re-upload and the day's usable allowance after the "
                          f"upload and Shorts reserves ({reserve()} units) "
                          f"does not fit one",
                          detail={"resets_at": quota.next_reset(),
                                  "waiting": todo},
                          unblock="Nothing to do: tomorrow's run resumes where "
                                  "this one stopped.")
        if fit < len(todo):
            st.note(f"quota fits {fit} of {len(todo)} re-uploads today. "
                    f"{quota.report()}")
        todo = todo[:fit]
        when = slots(len(todo), taken_slots())
        if len(when) < len(todo):
            todo = todo[:len(when)]
        if todo:
            if shelf is None:
                import r2                                  # noqa: PLC0415
                try:
                    shelf = r2.require()
                except r2.R2Unavailable as e:
                    st.named_stop(e.code, e.message, detail=e.detail,
                                  unblock=e.unblock)
            led = {r["slug"]: r for r in ledger.load()["published"]
                   if r.get("video_id") and not r.get("retired_at")}
            ldoc = lengthen.load()
            import upload as up                            # noqa: PLC0415
            import r2                                      # noqa: PLC0415
            with tempfile.TemporaryDirectory(prefix="repackage-") as td:
                for slug, t in zip(todo, when):
                    want = ldoc["episodes"][slug].get("new_render_sha256")
                    meta = shelf.head(r2.render_key(slug))
                    if not meta or meta.get("sha256") != want:
                        st.note(f"{slug}: the shelved render is not the spliced "
                                f"cut yet (want sha {str(want)[:12]}); the Mac's "
                                f"next push shelves it")
                        continue
                    render = shelf.get(r2.render_key(slug), Path(td) / f"{slug}.mp4")
                    img = thumb_for(slug)
                    if img is None:
                        tk = r2.thumb_key(slug)
                        if shelf.head(tk) is None:
                            st.note(f"{slug}: no thumbnail anywhere; held")
                            continue
                        img = shelf.get(tk, Path(td) / f"{slug}.jpg")
                    item = {"slug": slug, "script": f"scripts/{slug}.md",
                            "question": led[slug].get("question") or slug}
                    try:
                        payload = up.build_payload(item)
                    except up.TitleRefused as e:
                        st.note(f"{slug}: held, {e}")
                        continue
                    vid = yt.upload(payload, render)
                    stamp = _iso(t)
                    yt.set_status(vid, "private", publish_at=stamp)
                    yt.set_thumbnail(vid, img)
                    quota.spend(REUPLOAD_UNITS, LANE)
                    doc["reuploads"][slug] = {
                        "old_video_id": led[slug]["video_id"],
                        "new_video_id": vid, "scheduled_publish_at": stamp,
                        "uploaded_at": _now().isoformat(timespec="seconds"),
                        "title": payload["snippet"]["title"],
                        "render_sha256": want, "phase": "scheduled"}
                    ldoc["episodes"][slug]["reuploaded_at"] = \
                        doc["reuploads"][slug]["uploaded_at"]
                    save(doc)
                    lengthen.save(ldoc)
                    render.unlink(missing_ok=True)
                    st.work(f"{slug}: longer cut uploaded as {vid}, private, "
                            f"public at {stamp}; {led[slug]['video_id']} stays "
                            f"live until then")
        save(doc)
        if not st.units and waiting:
            st.named_stop("REUPLOAD_AWAITING_SLOT",
                          f"{len(waiting)} re-upload(s) scheduled and not yet "
                          f"public: " + ", ".join(sorted(waiting)),
                          detail={"resets_at": quota.next_reset()},
                          unblock="Nothing to do: each is promoted the first "
                                  "run after its slot.")
        if st.units:
            arming.record_success(LANE, detail=f"{len(st.units)} unit(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("apply", "reupload"))
    ap.add_argument("--slugs", nargs="*")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "apply":
        return run_apply(a.slugs, a.limit, a.dry_run)
    return run_reupload(a.slugs, a.limit, a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
