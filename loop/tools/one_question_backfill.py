"""ONE QUESTION PER VIDEO - the one-off retitle of the 19 videos of 25 Oct-2 Nov 2026.

    LOOP_DRY_RUN=1 python loop/tools/one_question_backfill.py --dry-run   # plan only
    python loop/tools/one_question_backfill.py                            # apply + read back
    python loop/tools/one_question_backfill.py --verify                   # read back only

Owner, 2 Nov 2026 (approved from the mock-up): the 1 long-form video and 18
Shorts published 25 Oct-2 Nov are retitled to EXACTLY the titles below, matched
by slug in loop/state/ledger.json / shorts_ledger.json (the row uploaded on or
after 25 Oct). videos.update, title only - the live snippet is read and merged
(ytmeta.merge_snippet), so the description, tags and category stay. The
long-form video also gets its new question-photo thumbnail. Nothing is
re-rendered, re-uploaded or deleted; videos uploaded before 25 Oct are not
touched.

THE MEASUREMENT IS NOT JUDGED ON OLD VIEWS: the long-form row in
loop/state/titles.json gets `applied_at` = now (loop/demand.py packaging_pass_at
starts its window there), and every Short's ledger row keeps `title_was` and
`retitled_at`. The record of the run is loop/state/one_question_backfill.json.

Idempotent: a video whose live title already reads the approved title is
verified, not updated again. Quota: 1 read + 50 update per video, +50 for the
thumbnail (~1,020 units), through the repackage lane's reserve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

WINDOW_FROM = "2026-10-25"
WINDOW_TO = "2026-11-03"          # exclusive; uploads of 2 Nov UTC included
RECORD = LOOP / "state" / "one_question_backfill.json"
LANE = "repackage"

# (kind, slug, approved title) - the owner's list, verbatim.
APPROVED = [
    ("long", "is-damascus-steel-better", "Are Damascus knives better?"),
    ("short", "is-damascus-steel-better", "Is Damascus steel really better?"),
    ("short", "why-does-rice-get-sticky", "Why does rice get sticky?"),
    ("short", "why-does-meat-need-to-rest-after-cooking", "Why does meat need to rest after cooking?"),
    ("short", "how-does-butter-get-made-from-cream", "How is butter made from cream?"),
    ("short", "why-is-my-bread-not-rising", "Why is my bread not rising?"),
    ("short", "why-does-steak-taste-better-seared", "Why does steak taste better seared?"),
    ("short", "why-does-chocolate-taste-so-good", "Why does chocolate taste so good?"),
    ("short", "how-deep-can-a-sperm-whale-go", "How deep can a sperm whale dive?"),
    ("short", "why-deep-sea-creatures-are-creepers", "Why do deep-sea creatures look so creepy?"),
    ("short", "what-lives-in-mariana-trench", "What lives at the bottom of the Mariana Trench?"),
    ("short", "05-why-many-deep-sea-creatures-are-red", "Why are so many deep-sea creatures red?"),
    ("short", "10-what-is-the-deepest-part-of-the-ocean", "How deep is the deepest part of the ocean?"),
    ("short", "18-why-does-black-smoker-water-not-boil", "Why doesn't water at deep-sea vents boil?"),
    ("short", "02-how-deep-sea-creatures-survive-pressure", "How do deep-sea creatures survive the pressure?"),
    ("short", "how-do-scientists-know-about-other-galaxies", "How do scientists know about other galaxies?"),
    ("short", "how-do-scientists-know-how-old-something-is", "How do scientists know how old something is?"),
    ("short", "why-deep-sea-fish-die-when-brought-to-surface", "Why do deep-sea fish die at the surface?"),
    ("short", "how-do-scientists-know-so-much", "How do we know so much about the deep ocean?"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _in_window(row: dict) -> bool:
    return WINDOW_FROM <= (row.get("uploaded_at") or "")[:10] < WINDOW_TO


def resolve(led: dict | None = None, sled: dict | None = None) -> list[dict]:
    """Each approved title -> exactly one ledger row in the window. Raises,
    naming every slug that resolves to none or to several."""
    import ledger                                          # noqa: PLC0415
    import shorts_lane as SL                               # noqa: PLC0415
    led = led if led is not None else ledger.load()
    sled = sled if sled is not None else SL.load_ledger()
    shorts = {r.get("video_id") for r in sled.get("published") or []}
    out, bad = [], []
    for kind, slug, title in APPROVED:
        rows = (sled if kind == "short" else led).get("published") or []
        hits = [r for r in rows if r.get("slug") == slug and r.get("video_id")
                and _in_window(r) and not r.get("retired_at")
                and (kind == "short" or r["video_id"] not in shorts)]
        if len(hits) != 1:
            bad.append(f"{kind} {slug}: {len(hits)} ledger rows in the window")
            continue
        out.append({"kind": kind, "slug": slug, "title": title,
                    "video_id": hits[0]["video_id"], "row": hits[0]})
    if bad:
        raise SystemExit("ONE_QUESTION_BACKFILL_UNRESOLVED: " + "; ".join(bad))
    return out


def _check_titles() -> list[str]:
    import titles                                          # noqa: PLC0415
    return [f"{t!r}: {p[0]}" for _k, _s, t in APPROVED
            for p in [titles.one_question_problems(t)] if p]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(dry_run: bool = False, verify_only: bool = False, yt=None) -> int:
    from common import Stage, week_id                      # noqa: PLC0415
    import quota                                           # noqa: PLC0415
    import repackage                                       # noqa: PLC0415
    import ytmeta                                          # noqa: PLC0415
    with Stage("one-question-backfill", week_id(),
               zero_work_hint="All 19 approved titles were already live.") as st:
        bad = _check_titles()
        if bad:
            st.named_stop("ONE_QUESTION_TITLE_INVALID", "; ".join(bad))
        items = resolve()
        if len(items) != len(APPROVED):
            st.named_stop("ONE_QUESTION_BACKFILL_UNRESOLVED",
                          f"{len(items)} of {len(APPROVED)} resolved")
        if dry_run:
            for it in items:
                st.work(f"DRY RUN would title {it['kind']} {it['video_id']} "
                        f"({it['slug']}): {it['row'].get('title')!r} -> {it['title']!r}")
            return 0
        yt = yt or repackage.client(st, dry_run)
        record = json.loads(RECORD.read_text()) if RECORD.exists() else {"videos": {}}
        import ledger                                      # noqa: PLC0415
        import shorts_lane as SL                           # noqa: PLC0415
        import longform_title as LT                        # noqa: PLC0415
        led, sled, tdoc = ledger.load(), SL.load_ledger(), LT.load()
        need = 0 if verify_only else sum(51 for _ in items) + 50
        if not verify_only and repackage.affordable(need, 1) < 1:
            st.named_stop("QUOTA_EXHAUSTED",
                          f"the backfill needs ~{need} units and today's "
                          f"allowance after the reserves does not fit it",
                          unblock="Nothing to type: run it again after the "
                                  "midnight-PT quota reset.")
        failed = []
        for it in items:
            vid = it["video_id"]
            live = yt.video(vid)
            quota.spend(quota.VIDEO_READ, LANE)
            if not live:
                failed.append(f"{vid} ({it['slug']}) not found on the channel")
                continue
            was = (live.get("snippet") or {}).get("title")
            if was != it["title"] and not verify_only:
                snippet = ytmeta.merge_snippet(live["snippet"], title=it["title"])
                yt.update_snippet(vid, snippet)
                quota.spend(quota.VIDEO_UPDATE, LANE)
                back = yt.video(vid)
                quota.spend(quota.VIDEO_READ, LANE)
                got = ((back or {}).get("snippet") or {}).get("title")
                desc_same = ((back or {}).get("snippet") or {}).get("description") == \
                    live["snippet"].get("description")
            else:
                got, desc_same = was, True
            ok = got == it["title"]
            prev = record["videos"].get(vid) or {}
            record["videos"][vid] = {
                "kind": it["kind"], "slug": it["slug"], "approved": it["title"],
                "title_was": prev.get("title_was") or was,
                "read_back": got, "applied": ok, "description_unchanged": desc_same,
                "retitled_at": prev.get("retitled_at") or (_now() if ok else None),
                "verified_at": _now()}
            if not ok:
                failed.append(f"{vid} ({it['slug']}) reads back {got!r}")
                continue
            stamp = record["videos"][vid]["retitled_at"]
            if it["kind"] == "short":
                for r in sled["published"]:
                    if r.get("video_id") == vid:
                        r.setdefault("title_was", r.get("title"))
                        r["title"] = it["title"]
                        r.setdefault("retitled_at", stamp)
            else:
                for r in led["published"]:
                    if r.get("video_id") == vid:
                        r["title"] = it["title"]
                row = tdoc["titles"].get(it["slug"]) or {}
                if row.get("new_title") != it["title"] or not row.get("applied_at"):
                    tdoc["titles"][it["slug"]] = {
                        **row, "slug": it["slug"], "new_title": it["title"],
                        "checks_passed": True, "problems": [],
                        "model": "owner (one-question backfill, 2 Nov 2026)",
                        "applied_at": stamp, "applied_video_id": vid,
                        "previous": {"new_title": row.get("new_title"),
                                     "applied_at": row.get("applied_at")}}
                if not verify_only:
                    _thumbnail(st, yt, it, tdoc, record)
            st.work(f"{it['kind']} {vid} ({it['slug']}) reads back {got!r}")
        record["run_at"] = _now()
        record["read_back_ok"] = sum(1 for v in record["videos"].values() if v["applied"])
        RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        ledger.save(led)
        SL.save_ledger(sled)
        LT.save(tdoc)
        if failed:
            st.named_stop("ONE_QUESTION_BACKFILL_PARTIAL",
                          f"{len(failed)} of {len(items)} did not read back the "
                          f"approved title: " + "; ".join(failed),
                          unblock="Nothing to type: re-running is idempotent.")
    return 0


def _thumbnail(st, yt, it: dict, tdoc: dict, record: dict) -> None:
    """The long-form video's question-photo thumbnail (variant A)."""
    import quota                                           # noqa: PLC0415
    import thumb_contract as TC                            # noqa: PLC0415
    slug = it["slug"]
    r = TC.build_question_into(slug, f"{TC.VARIANTS_DIR}/{slug}", title=it["title"])
    problems = TC.verify(slug)
    if problems:
        st.named_stop("ONE_QUESTION_THUMB_INVALID", "; ".join(problems))
    img = Path(r["chosen"])
    shutil.copyfile(img, ROOT / "channel" / "thumbnails" / f"{slug}.jpg")
    row = tdoc["titles"][slug]
    if row.get("thumbnail_sha256") == _sha(img) and row.get("thumbnail_applied"):
        return
    yt.set_thumbnail(it["video_id"], img)
    quota.spend(quota.THUMBNAIL, LANE)
    row["thumbnail_applied"] = True
    row["thumbnail_sha256"] = _sha(img)
    row["thumbnail_applied_at"] = _now()
    record["videos"][it["video_id"]]["thumbnail"] = {
        "file": str(img.relative_to(ROOT)), "sha256": row["thumbnail_sha256"],
        "photo": r["contract"]["variants"]["A"]["source"]}
    st.work(f"{it['video_id']} ({slug}) thumbnail set: question-photo variant A")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    return run(dry_run=a.dry_run, verify_only=a.verify)


if __name__ == "__main__":
    raise SystemExit(main())
