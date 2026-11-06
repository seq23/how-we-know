"""Keep at most ONE superseded copy of each episode's render.

A long-form master is ~550 MB. Every re-render moves the previous one aside
(never deleted: `.picture-check-failed`, `.below-picture-floor`,
`.pre-...`, `.incomplete...`), and on 2026-11-03 four aside copies of one
episode sat in renders/ while the Mac ran out of memory and disk. This keeps
the newest aside copy per episode and moves the older ones to the Trash
(~/.Trash on the Mac - recoverable, not deleted). The live render and its
`.footage.json` / `.render.json` records are never touched.

    .venv/bin/python loop/render_prune.py [--dry-run]
    .venv/bin/python loop/render_prune.py guard [--floor-gib N] [--dry-run]

THE DISK GUARD (6 Nov 2026). The Mac's data disk reached 100% (1.8 GiB free
of 228) with renders/ at 13 GiB, because nothing ever removed a live render
after its upload: every master of every uploaded episode stayed on disk
forever, and the aside prune above only MOVES copies to the Trash, which is
on the same disk. `guard` runs before every nightly render:

  1. the aside prune above;
  2. prune_uploaded(): a live render is DELETED only when all four hold -
     the ledger has a non-retired upload with a video id, its Shorts are cut
     (ledger `shorts_block`), YouTube itself says the video exists and is
     `processed` (videos.list, one call for every id), and R2 holds the
     identical file (size + sha256, r2.same_as). A marker
     renders/<slug>-final.mp4.pruned.json records what was proven, and the
     batch does not re-render a pruned episode (pruned()) unless its plan
     changes - a remake re-plans, so it still renders. Nothing that is not
     uploaded is ever deleted;
  3. free space below the floor (DISK_FLOOR_GIB, default 6: three times the
     largest render on disk, 1.7 GiB, measured 6 Nov) after pruning is
     NAMED STOP [DISK_LOW], exit 3: the render is not started, so there is
     never a half-written video, and the stop is filed as a `[mac-batch]
     DISK_LOW` issue by loop/mac_batch_stop.py so someone sees it
     (bin/batch-session.sh scans the guard's output with the push's).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDERS = ROOT / "renders"
TRASH = Path.home() / ".Trash"
KEEP = 1
RECORDS = (".footage.json", ".render.json")
ASIDE = re.compile(r"^(?P<slug>.+)-final\.mp4\.(?P<tag>[^/]+)$")


def aside_copies(renders: Path = RENDERS) -> dict[str, list[Path]]:
    """{slug: [aside master copies, newest first]} - records excluded."""
    out: dict[str, list[Path]] = {}
    for p in renders.iterdir() if renders.exists() else []:
        m = ASIDE.match(p.name)
        if not m or not p.is_file() or p.name.endswith(RECORDS):
            continue
        out.setdefault(m.group("slug"), []).append(p)
    for v in out.values():
        v.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def prune(renders: Path = RENDERS, trash: Path = TRASH, keep: int = KEEP,
          dry_run: bool = False) -> list[Path]:
    """Move every aside copy past the newest `keep` (and its records) to `trash`."""
    moved = []
    for slug, copies in aside_copies(renders).items():
        for p in copies[keep:]:
            for q in [p] + [Path(str(p) + r) for r in RECORDS]:
                if q.exists():
                    if not dry_run:
                        trash.mkdir(parents=True, exist_ok=True)
                        dest = trash / q.name
                        if dest.exists():
                            dest = trash / f"{q.name}.{int(q.stat().st_mtime)}"
                        shutil.move(str(q), str(dest))
                    moved.append(q)
    return moved


LIVE = re.compile(r"^(?P<slug>.+)-final\.mp4$")
MARK = ".pruned.json"
FLOOR_GIB = 6.0
LEDGER = ROOT / "loop" / "state" / "ledger.json"
PLANS = ROOT / "plans"


def free_gib(path: Path = ROOT) -> float:
    return shutil.disk_usage(path).free / 2 ** 30


def _sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pruned(slug: str, renders: Path = RENDERS, plans: Path = PLANS) -> bool:
    """True when the live render was pruned after a proven upload and the
    plan has not changed since (a remake re-plans, so it renders again)."""
    m = renders / f"{slug}-final.mp4{MARK}"
    if not m.exists():
        return False
    try:
        rec = json.loads(m.read_text())
    except ValueError:
        return False
    return rec.get("plan_sha256") == _sha(plans / f"{slug}.json")


def uploaded_rows(led: dict) -> dict[str, dict]:
    """slug -> its latest non-retired upload with a video id."""
    out = {}
    for e in led.get("published", []):
        if e.get("video_id") and not e.get("retired_at"):
            out[e["slug"]] = e
    return out


def youtube_status(video_ids: list[str]) -> dict[str, dict]:
    """{video_id: status} for the ids YouTube returns (absent = not found).
    One videos.list call per 50 ids (1 quota unit each)."""
    sys.path.insert(0, str(ROOT / "loop"))
    import urllib.parse                                    # noqa: PLC0415
    import urllib.request                                  # noqa: PLC0415
    import common                                          # noqa: PLC0415
    import upload as up                                    # noqa: PLC0415
    creds = up.load_credentials(common.config())
    if not creds:
        raise RuntimeError("no YouTube credential on this machine")
    token = up.access_token(creds)
    out = {}
    for i in range(0, len(video_ids), 50):
        q = urllib.parse.urlencode({"part": "status", "id": ",".join(video_ids[i:i + 50])})
        req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/videos?{q}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            for it in json.loads(r.read()).get("items", []):
                out[it["id"]] = it.get("status", {})
    return out


def prune_uploaded(renders: Path = RENDERS, led: dict | None = None, bucket=None,
                   yt=youtube_status, plans: Path = PLANS,
                   dry_run: bool = False) -> tuple[list[dict], list[str]]:
    """Delete live renders whose upload is proven on YouTube AND in R2.
    Returns (pruned records, kept reasons)."""
    sys.path.insert(0, str(ROOT / "loop"))
    import r2                                              # noqa: PLC0415
    led = led if led is not None else json.loads(LEDGER.read_text())
    rows = uploaded_rows(led)
    live = []
    for p in sorted(renders.iterdir()) if renders.exists() else []:
        m = LIVE.match(p.name)
        if m and p.is_file():
            live.append((m.group("slug"), p))
    cands = [(s, p) for s, p in live if s in rows and rows[s].get("shorts_block")]
    kept = [f"{s}: not uploaded" for s, _ in live if s not in rows]
    kept += [f"{s}: Shorts not cut yet" for s, _ in live if s in rows and not rows[s].get("shorts_block")]
    if not cands:
        return [], kept
    statuses = yt([rows[s]["video_id"] for s, _ in cands])
    if bucket is None:
        bucket = r2.require()
    done = []
    for slug, p in cands:
        vid = rows[slug]["video_id"]
        st = statuses.get(vid)
        if not st or st.get("uploadStatus") != "processed" or st.get("rejectionReason"):
            kept.append(f"{slug}: YouTube does not confirm {vid} as processed ({st})")
            continue
        same, why = bucket.same_as(p, r2.render_key(slug))
        if not same:
            kept.append(f"{slug}: R2 copy not proven ({why})")
            continue
        rec = {"slug": slug, "video_id": vid, "upload_status": st.get("uploadStatus"),
               "r2_key": r2.render_key(slug), "r2_proof": why, "bytes": p.stat().st_size,
               "plan_sha256": _sha(plans / f"{slug}.json"),
               "pruned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if not dry_run:
            (renders / f"{p.name}{MARK}").write_text(json.dumps(rec, indent=2) + "\n")
            p.unlink()
        done.append(rec)
    return done, kept


def guard(floor_gib: float = FLOOR_GIB, renders: Path = RENDERS, free=free_gib,
          dry_run: bool = False, **kw) -> tuple[int, str]:
    """Prune what is safe, then (0, line) when free >= floor, else
    (3, NAMED STOP [DISK_LOW] line). An unreachable YouTube or R2 never
    deletes anything; it is reported and the floor still decides."""
    before = free()
    moved = prune(renders, dry_run=dry_run) if renders == RENDERS else []
    try:
        done, kept = prune_uploaded(renders, dry_run=dry_run, **kw)
        note = ""
    except Exception as e:                                 # noqa: BLE001
        done, kept, note = [], [], f"; uploaded-render prune skipped ({type(e).__name__}: {str(e)[:120]})"
    freed = sum(r["bytes"] for r in done) / 2 ** 30
    after = free()
    line = (f"disk guard: {after:.1f} GiB free (floor {floor_gib:g}); deleted {len(done)} uploaded "
            f"render(s) proven on YouTube and R2 ({freed:.2f} GiB), moved {len(moved)} aside "
            f"copies; kept {len(kept)}{note}")
    if after >= floor_gib:
        return 0, line
    return 3, (f"NAMED STOP [DISK_LOW] {after:.1f} GiB free on the Mac, below the {floor_gib:g} GiB "
               f"floor after pruning everything safe (was {before:.1f}). No render was started. "
               f"Free space on the Mac (anything outside renders/ that is not hers to keep), "
               f"then the next batch renders on its own. {line}")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    if argv[:1] == ["guard"]:
        floor = float(os.environ.get("DISK_FLOOR_GIB", FLOOR_GIB))
        if "--floor-gib" in argv:
            floor = float(argv[argv.index("--floor-gib") + 1])
        rc, line = guard(floor, dry_run=dry)
        print(line)
        return rc
    if argv[:1] == ["is-pruned"]:
        return 0 if pruned(argv[1]) else 1
    moved = prune(dry_run=dry)
    print(f"render prune: {'would move' if dry else 'moved'} {len(moved)} superseded "
          f"copy file(s) to {TRASH}; at most {KEEP} kept per episode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
