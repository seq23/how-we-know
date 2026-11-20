"""THE FREE-STORAGE CAP: no job ever writes R2 past 9 GB, and nothing is billed.

R2's free tier is 10 GB PER ACCOUNT. On 6 Nov 2026 this bucket held 9.99 GB;
on 20 Nov the account held 11.17 GB while the cap, reading this bucket alone,
still passed. `used` is now the whole account (r2.account_usage_bytes) and the
floor is 9 GB (her ruling 20 Nov 2026: the main account stays under 9 GB).
Every R2 write goes through loop/r2.py `put`, which calls ensure_room() first:

  1. room needed = used - (the key's current size) + new size - 9 GB floor;
  2. DELETE R2 copies whose YouTube upload is confirmed: a non-retired ledger
     upload with a video id that YouTube reports `processed`, not superseded
     and with no swap in flight (an R2 object is never the only copy of an
     episode that has not aired); an overflow copy in Drive goes with it;
  3. still short: MOVE queued, not-yet-uploaded renders to Google Drive (the
     ones LAST in the upload line first, so the next upload rarely waits on a
     pull-back): copy, verify Drive's md5 against the bytes, and only then
     replace the R2 bytes with a tiny marker. r2.get() pulls a marked render
     back from Drive, sha256-checked, when the upload lane needs it;
  4. still short, or Drive under its own free-space margin, or Drive not yet
     consented (a note, not a red): NAMED STOP [STORAGE_FREE_CAP]; the write
     does not happen, so nothing is ever billed.

Nothing that is not uploaded or safely copied is ever deleted.

THE DAILY CHECK (`python loop/storage_cap.py check`, the 09:00 CT upload
workflow): reads the account total; at or over the floor it opens (or
re-mentions daily) a GitHub issue that @-mentions her, so GitHub emails it,
and closes it the first day the account is back under. An unreadable total
is NAMED STOP [R2_USAGE_UNREADABLE], exit 2, never a guessed zero.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

R2_FLOOR = int(9.0e9)        # account-wide, her ruling 20 Nov 2026
DRIVE_MARGIN = int(1.0e9)       # keep 1 GB of her free 15 GB untouched
MARK = "drive-overflow"


class CapStop(Exception):
    code = "STORAGE_FREE_CAP"


def _ledger() -> dict:
    return json.loads((ROOT / "loop/state/ledger.json").read_text())


def _swaps() -> dict:
    p = ROOT / "loop/state/superseded_swaps.json"
    return json.loads(p.read_text()).get("swaps", {}) if p.exists() else {}


def _queued() -> list[str]:
    import batch_queue                                      # noqa: PLC0415
    return batch_queue.queued_slugs()


def ensure_room(bucket, key: str, add: int, *, floor: int = R2_FLOOR, ledger=None,
                yt=None, drive=None, queued=None, swaps=None, local_renders: Path | None = None,
                log=print) -> list[str]:
    import r2                                               # noqa: PLC0415
    acts: list[str] = []
    used = bucket.usage_bytes()
    prev = (bucket.head(key) or {}).get("size", 0)
    need = used - prev + add - floor
    if need <= 0:
        return acts
    ledger = ledger if ledger is not None else _ledger()
    swaps = swaps if swaps is not None else _swaps()
    rows = {}
    for e in ledger.get("published", []):
        if e.get("video_id") and not e.get("retired_at") and not e.get("superseded_by"):
            rows[e["slug"]] = e
    pending_swap = {s for s, w in swaps.items() if w.get("phase") != "done"}
    # 2. confirmed uploads
    cands = [s for s in rows if s not in pending_swap and r2.render_key(s) != key]
    if cands:
        if yt is None:
            import render_prune                             # noqa: PLC0415
            yt = render_prune.youtube_status
        try:
            st = yt([rows[s]["video_id"] for s in cands])
        except Exception as e:                              # noqa: BLE001
            st = {}
            acts.append(f"note: YouTube could not confirm uploads ({type(e).__name__}); none deleted")
        for s in cands:
            if need <= 0:
                break
            v = st.get(rows[s]["video_id"]) or {}
            if v.get("uploadStatus") != "processed" or v.get("rejectionReason"):
                continue
            h = bucket.head(r2.render_key(s))
            if not h:
                continue
            meta = bucket.meta(r2.render_key(s)) or {}
            bucket.delete(r2.render_key(s))
            if meta.get(MARK) and drive is not None:
                try:
                    drive.delete(meta[MARK])
                except Exception:                           # noqa: BLE001
                    pass
            freed = 0 if meta.get(MARK) else h["size"]
            need -= freed
            acts.append(f"deleted r2 {r2.render_key(s)} ({freed} bytes): {rows[s]['video_id']} processed on YouTube")
    if need <= 0:
        return acts
    # 3. overflow to Drive, last in line first
    if drive is None:
        import gdrive                                       # noqa: PLC0415
        drive = gdrive.Drive() if gdrive.available() else None
    if drive is None:
        acts.append("note: Drive overflow not consented yet (auth/drive_auth.py); falling through")
    else:
        queued = queued if queued is not None else _queued()
        waiting = [s for s in reversed(queued) if s not in rows and r2.render_key(s) != key]
        for s in waiting:
            if need <= 0:
                break
            k = r2.render_key(s)
            h = bucket.head(k)
            meta = bucket.meta(k) or {}
            if not h or meta.get(MARK):
                continue
            try:
                if drive.free_bytes() - h["size"] < DRIVE_MARGIN:
                    acts.append("note: Drive is near its free 15 GB; nothing more moved")
                    break
                with tempfile.TemporaryDirectory() as td:
                    loc = (local_renders or ROOT / "renders") / f"{s}-final.mp4"
                    src = loc if loc.exists() and r2.sha256_file(loc) == h.get("sha256") else None
                    if src is None:
                        src = bucket.get(k, Path(td) / f"{s}.mp4")
                    if r2.sha256_file(src) != h.get("sha256"):
                        continue
                    import gdrive                           # noqa: PLC0415
                    up = drive.upload(src, Path(k).name)
                    if up.get("md5Checksum") != gdrive.md5_file(src):
                        acts.append(f"note: Drive copy of {s} did not verify; R2 kept")
                        continue
                    bucket.replace_with_marker(k, {MARK: up["id"], "sha256": h["sha256"], "size": h["size"]})
                need -= h["size"]
                acts.append(f"moved {k} to Drive ({h['size']} bytes), verified md5; pulled back when next in line")
            except Exception as e:                          # noqa: BLE001
                acts.append(f"note: Drive overflow failed for {s} ({type(e).__name__}); R2 kept")
                break
    if need > 0:
        raise CapStop(f"NAMED STOP [STORAGE_FREE_CAP] R2 needs {need / 1e9:.2f} GB more under its "
                      f"{floor / 1e9:g} GB free floor after deleting every confirmed upload"
                      f"{' and moving what Drive could hold' if drive else ''}; "
                      f"{key} was NOT written, so nothing is billed. " + "; ".join(acts[-3:]))
    for a in acts:
        log(f"  storage cap: {a}")
    return acts
DEPS: dict = {}


# ------------------------------------------------------------- daily check
LABEL = "r2-free-storage"
MARKER = "<!-- r2-free-storage -->"


def check(usage=None, runner=None, dry_run: bool = False, floor: int = R2_FLOOR) -> int:
    import subprocess                                       # noqa: PLC0415
    import r2                                               # noqa: PLC0415
    import publish_floor as PF                              # noqa: PLC0415
    runner = runner or subprocess.run
    try:
        used = usage() if usage else r2.require().usage_bytes()
    except r2.R2Unavailable as e:
        print(f"NAMED STOP [R2_USAGE_UNREADABLE] {e}")
        return 2
    line = f"R2 account total {used / 1e9:.2f} GB (alarm at {floor / 1e9:g} GB of the free 10 GB)"
    print(f"OUTPUT: {line}")
    if dry_run:
        return 0
    try:
        out = PF._gh(["issue", "list", "--state", "open", "--label", LABEL, "--json", "number,body",
                      "--limit", "20"], runner)
    except RuntimeError:
        out = "[]"                                          # the label does not exist yet
    num = next((int(r["number"]) for r in json.loads(out or "[]") if MARKER in (r.get("body") or "")), None)
    if used < floor:
        if num is not None:
            PF._gh(["issue", "close", str(num), "--comment", f"Back under: {line}."], runner)
        return 0
    who = "@" + (os.environ.get("OWNER_HANDLE") or "seq23")
    title = f"R2 at {used / 1e9:.2f} GB: over the 9 GB line of the free 10 GB"
    body = (f"**{line}.** The main Cloudflare account must stay under 9 GB (her ruling 20 Nov 2026). "
            "How We Know writes stop at the floor by themselves (NAMED STOP [STORAGE_FREE_CAP]); the "
            "rest of the account (creator studios, Boss OS documents, other buckets) is not capped by "
            "this repo, so the fix is to clear or move whichever bucket grew. Per-bucket sizes: "
            "`wrangler r2 bucket info <name>`. This issue is re-mentioned daily and closes itself "
            "the first day the account is back under (loop/storage_cap.py check).")
    if num is None:
        text = f"{who}\n\n{body}\n\n{MARKER}"
        try:
            PF._gh(["issue", "create", "--title", title, "--body", text, "--label", LABEL], runner)
        except RuntimeError:
            PF._gh(["label", "create", LABEL, "--color", "B60205", "--description",
                    "the Cloudflare account's R2 storage is over 9 GB"], runner)
            PF._gh(["issue", "create", "--title", title, "--body", text, "--label", LABEL], runner)
        print("alarm: issue opened")
        return 0
    PF._gh(["issue", "comment", str(num), "--body", f"{who} still over.\n\n{body}"], runner)
    PF._gh(["issue", "edit", str(num), "--title", title], runner)
    print(f"alarm: re-mentioned #{num}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["check"]:
        sys.exit(check(dry_run="--dry-run" in sys.argv))
    print("usage: python loop/storage_cap.py check [--dry-run]")
    sys.exit(64)
