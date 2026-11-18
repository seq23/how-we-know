#!/usr/bin/env python3
"""THE CLIP SHELF: footage clips nobody has used for 7 days live on Drive, not the Mac.

    python loop/shelf.py shelve [--dry-run]   # daily (bin/loop-backfill-daily.sh)
    python loop/shelf.py pull-all             # bring EVERY shelved clip back, by hand
    python loop/shelf.py status

Her rulings, 17 Nov 2026: "shelve all clips and pull them down as needed? and
only keep the ones u know you will need for the week?" and "maybe we just put
clips on seq.taylor and videos on cryptoclearr". The footage pool
(channel/imagery/clips, ~600 clips, ~20 GB) was the Mac's biggest space-eater.

  * WHERE: gdrive:Mac-Shelf/clips/ (the seq.taylor Drive, rclone remote
    already authorised on the Mac). One destination, no overflow: a Drive
    short of room is NAMED STOP [SHELF_DRIVE_FULL] and nothing moves.
  * WHAT: only a clip a rights manifest records (channel/imagery/*.json
    `local_file` under clips/, with its sha256) and whose bytes still hash to
    that record - so every shelved clip is one the pipeline can prove and
    re-check. Voice references, loop/state, manifests, video_rights.json,
    licences, stills and anything unrecorded are never shelved
    (shelvable()).
  * WHEN: a clip whose last use is 7+ days ago. Last use = the newest of: the
    moment a render pulled it for a video (stamped in shelf.json `used` by
    need()), and the file's own mtime (harvest or fetch). A new Friday
    harvest stays local until it ages past 7 days. Never while a render runs
    (batch/food lock held or ffmpeg running): that is a note, the next day
    shelves.
  * PROOF BEFORE DELETE: Drive's own size + sha256 for the copy must equal the
    local file's before the local file is deleted. The Drive copy is kept when
    a clip comes back, so re-shelving it later is just the check and the
    delete.
  * THE RECORD: loop/state/shelf.json (committed) - `clips` {name: remote,
    size, sha256, shelved_at} and `used` {name: last use}.
  * SELECTION NEVER NARROWS: footage selection (visuals/footage.verify with
    fetch=False, food.catalogue, whisper_reel, the harvesters' merge checks)
    treats a shelved clip whose record sha matches as AVAILABLE. Bytes are
    fetched just in time: after a video's picture is planned and before its
    first frame is rendered (footage.prefetch, food's shot check), and as a
    safety net wherever a clip's bytes are read (footage.verify fetch=True).
  * DRIVE UNREACHABLE when a clip is needed: NAMED STOP [SHELF_UNREACHABLE];
    the render fails loudly, never skips a clip and never draws instead.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
IMAGERY = ROOT / "channel" / "imagery"
CLIPS = IMAGERY / "clips"
MANIFEST = ROOT / "loop" / "state" / "shelf.json"
LOCK = ROOT / "loop" / "state" / "_local" / "batch.lock"
WARM_DAYS = 7
DRIVE_MARGIN = int(1e9)          # never fill the Drive past its last 1 GB
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v", ".mkv")
RCLONE_TIMEOUT = 1800


class ShelfStop(RuntimeError):
    """A NAMED STOP: the shelf cannot do what was asked. Never a silent skip."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"NAMED STOP [{code}] {message}")


def remote() -> str:
    """gdrive:Mac-Shelf/clips, or a local directory (tests) via SHELF_REMOTE."""
    return os.environ.get("SHELF_REMOTE", "gdrive:Mac-Shelf/clips").rstrip("/")


def _local_remote() -> Path | None:
    r = remote()
    return Path(r) if r.startswith("/") else None


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------- transport
def _rclone(args: list[str], timeout: int = RCLONE_TIMEOUT) -> str:
    try:
        r = subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ShelfStop("SHELF_UNREACHABLE", f"rclone could not reach {remote()} ({type(e).__name__}: "
                        f"{str(e)[:160]}). Nothing was deleted.") from None
    if r.returncode != 0:
        raise ShelfStop("SHELF_UNREACHABLE", f"rclone {args[0]} failed on {remote()}: "
                        f"{(r.stderr or r.stdout).strip()[-240:]}. Nothing was deleted.")
    return r.stdout


def remote_stat(name: str) -> dict | None:
    """{"size", "sha256"} of the Drive copy, as Drive itself reports it."""
    loc = _local_remote()
    if loc is not None:
        p = loc / name
        return {"size": p.stat().st_size, "sha256": sha256_file(p)} if p.is_file() else None
    out = json.loads(_rclone(["lsjson", "--hash", "--hash-type", "sha256", "--files-only",
                              remote(), "--include", "/" + name.replace("[", "\\[")], timeout=300) or "[]")
    for it in out:
        if it.get("Name") == name:
            return {"size": int(it.get("Size") or 0), "sha256": (it.get("Hashes") or {}).get("sha256")}
    return None


def remote_put(src: Path, name: str) -> None:
    loc = _local_remote()
    if loc is not None:
        loc.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, loc / name)
        return
    _rclone(["copyto", str(src), f"{remote()}/{name}"])


def remote_get(name: str, dest: Path) -> None:
    loc = _local_remote()
    if loc is not None:
        if not (loc / name).is_file():
            raise ShelfStop("SHELF_UNREACHABLE", f"{name} is not on the shelf {loc}")
        shutil.copy2(loc / name, dest)
        return
    _rclone(["copyto", f"{remote()}/{name}", str(dest)])


def remote_free() -> int:
    loc = _local_remote()
    if loc is not None:
        if os.environ.get("SHELF_FREE_BYTES"):
            return int(os.environ["SHELF_FREE_BYTES"])
        loc.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(loc).free
    about = json.loads(_rclone(["about", remote().split(":")[0] + ":", "--json"], timeout=120))
    return int(about.get("free") or 0)


# ------------------------------------------------------------- the record
def load(path: Path | None = None) -> dict:
    p = path or MANIFEST
    m = json.loads(p.read_text()) if p.exists() else {}
    m.setdefault("clips", {})
    m.setdefault("used", {})
    return m


def save(m: dict, path: Path | None = None) -> None:
    p = path or MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    m["updated"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    tmp.replace(p)


def _abs(path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else IMAGERY / p


def _clip_name(path) -> str | None:
    """The clip's file name when `path` is inside the clips folder, else None."""
    p = _abs(path)
    return p.name if p.parent.resolve() == CLIPS.resolve() else None


def records(imagery: Path | None = None) -> dict[str, str]:
    """{clip file name: sha256} for every clip a rights manifest records."""
    imagery = imagery or IMAGERY
    out: dict[str, str] = {}

    def walk(x):
        if isinstance(x, dict):
            lf = x.get("local_file")
            if isinstance(lf, str) and lf.startswith("clips/") and x.get("sha256"):
                out.setdefault(Path(lf).name, x["sha256"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for f in sorted(imagery.glob("*.json")):
        try:
            walk(json.loads(f.read_text()))
        except ValueError:
            raise ShelfStop("SHELF_RECORDS_UNREADABLE", f"{f.name} is not valid JSON; "
                            f"nothing is shelved while a rights record cannot be read") from None
    return out


def shelved(path, m: dict | None = None) -> dict | None:
    """The shelf entry for a clip that is NOT on this Mac, else None."""
    name = _clip_name(path)
    if not name:
        return None
    p = _abs(path)
    if p.exists():
        return None
    return (m or load())["clips"].get(name)


def present(path, sha256: str | None = None) -> bool:
    """On this Mac, or on the shelf with the same bytes: selectable either way."""
    p = _abs(path)
    if p.exists():
        return True
    e = shelved(p)
    return bool(e) and (sha256 is None or e.get("sha256") == sha256)


def fetch(path, m: dict | None = None) -> Path:
    """Bring one shelved clip back, sha256-checked against its record."""
    p = _abs(path)
    if p.exists():
        return p
    m = m or load()
    e = m["clips"].get(p.name)
    if not e:
        raise ShelfStop("CLIP_NOT_ON_SHELF", f"{p.name} is neither on this Mac nor on the shelf")
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=p.parent) as td:
        tmp = Path(td) / p.name
        remote_get(p.name, tmp)
        if not tmp.exists() or tmp.stat().st_size != e["size"] or sha256_file(tmp) != e["sha256"]:
            raise ShelfStop("SHELF_COPY_CORRUPT", f"the shelf copy of {p.name} is not the recorded "
                            f"bytes (size/sha256); nothing was rendered from it")
        tmp.replace(p)
    os.utime(p)                    # fresh mtime: it is warm again for 7 days
    return p


def need(paths: list, now: _dt.datetime | None = None) -> int:
    """Just in time: fetch every shelved clip in `paths` and stamp all of
    them used. Called after a video's picture is planned, before its render.
    Returns how many were fetched; raises ShelfStop when Drive cannot serve one."""
    names = [_abs(p) for p in paths]
    names = [p for p in names if _clip_name(p)]
    if not names:
        return 0
    m = load()
    got = 0
    for p in dict.fromkeys(names):
        if not p.exists() and p.name in m["clips"]:
            fetch(p, m)
            got += 1
    stamp = (now or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for p in names:
        m["used"][p.name] = stamp
    save(m)
    if got:
        print(f"  shelf: pulled {got} clip(s) back from {remote()} for this render", flush=True)
    return got


# ------------------------------------------------------------- shelving
def render_running() -> str | None:
    """Why shelving must wait, or None."""
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True,
                             text=True).stdout
        if "batch-session" in cmd or "food-session" in cmd:
            return f"a nightly session holds the render lock (pid {pid})"
    except (OSError, ValueError):
        pass
    if subprocess.run(["pgrep", "-x", "ffmpeg"], capture_output=True).returncode == 0:
        return "ffmpeg is running"
    return None


def shelvable(p: Path, recs: dict[str, str]) -> bool:
    """Only a recorded footage clip in the clips folder. Everything else -
    voice references, state, manifests, licences, stills, an unrecorded file -
    is irreplaceable or unproven here and never leaves the Mac."""
    return (p.is_file() and not p.is_symlink() and p.parent.resolve() == CLIPS.resolve()
            and not p.name.startswith(".") and p.suffix.lower() in VIDEO_EXT and p.name in recs)


def last_used(p: Path, m: dict) -> float:
    t = p.stat().st_mtime
    u = m["used"].get(p.name)
    if u:
        t = max(t, _dt.datetime.fromisoformat(u.replace("Z", "+00:00")).timestamp())
    return t


def shelve(now: _dt.datetime | None = None, dry_run: bool = False, busy=render_running,
           log=print) -> dict:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    why = busy() if busy else None
    if why:
        log(f"note: shelving waits ({why}); the next daily run shelves")
        return {"waited": why, "shelved": 0, "bytes": 0}
    recs = records()
    if not recs:
        raise ShelfStop("SHELF_NO_RECORDS", "no rights manifest records any clip; refusing to "
                        "judge the pool with nothing to check it against")
    m = load()
    cut = now.timestamp() - WARM_DAYS * 86400
    files = sorted(CLIPS.iterdir()) if CLIPS.exists() else []
    cands = [p for p in files if shelvable(p, recs) and last_used(p, m) <= cut]
    warm = sum(1 for p in files if shelvable(p, recs)) - len(cands)
    out = {"shelved": 0, "bytes": 0, "warm": warm, "candidates": len(cands), "skipped": []}
    if dry_run:
        out["bytes"] = sum(p.stat().st_size for p in cands)
        return out
    room = remote_free() - DRIVE_MARGIN
    for p in cands:
        size = p.stat().st_size
        local = sha256_file(p)
        if local != recs[p.name]:
            out["skipped"].append(f"{p.name}: bytes differ from its rights record; stays")
            continue
        r = remote_stat(p.name)
        if not (r and r["size"] == size and r["sha256"] == local):
            if size > room:
                save(m)
                raise ShelfStop("SHELF_DRIVE_FULL", f"{remote()} has {room / 1e9:.1f} GB to spare, "
                                f"{p.name} needs {size / 1e9:.2f} GB; shelved {out['shelved']} so far. "
                                f"Never spilled to another Drive.")
            remote_put(p, p.name)
            room -= size
            r = remote_stat(p.name)
        if not (r and r["size"] == size and r["sha256"] == local):
            out["skipped"].append(f"{p.name}: the Drive copy did not verify ({r}); stays")
            continue
        m["clips"][p.name] = {"remote": remote(), "size": size, "sha256": local,
                              "shelved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
        save(m)                   # the record lands before the local copy goes
        p.unlink()
        out["shelved"] += 1
        out["bytes"] += size
    save(m)
    return out


def remote_names() -> list[str]:
    loc = _local_remote()
    if loc is not None:
        return sorted(p.name for p in loc.iterdir() if p.is_file()) if loc.exists() else []
    return sorted(x for x in _rclone(["lsf", "--files-only", remote()], timeout=300).splitlines() if x)


def pull_all(log=print) -> int:
    """Every clip back on the Mac: each shelf entry, and - should shelf.json
    ever be lost - any recorded clip found on the Drive copy, checked against
    its rights record's sha256."""
    m = load()
    recs = records()
    for name in remote_names():
        if name in recs and name not in m["clips"] and not (CLIPS / name).exists():
            r = remote_stat(name) or {}
            if r.get("sha256") == recs[name]:
                m["clips"][name] = {"remote": remote(), "size": r["size"], "sha256": r["sha256"],
                                    "shelved_at": "recovered"}
    n = 0
    for name in sorted(m["clips"]):
        p = CLIPS / name
        if not p.exists():
            fetch(p, m)
            n += 1
    save(m)
    log(f"OUTPUT pulled {n} clip(s) back from {remote()}")
    return n


def main(argv: list[str]) -> int:
    if argv[:1] == ["shelve"]:
        dry = "--dry-run" in argv
        if dry:
            r = shelve(dry_run=True, busy=None)
            print(f"OUTPUT would shelve {r['candidates']} idle clip(s) ({r['bytes'] / 2**30:.2f} GiB) "
                  f"to {remote()}; {r['warm']} warm clip(s) stay")
            return 0
        sys.path.insert(0, str(LOOP))
        import common as C                                  # noqa: PLC0415
        with C.Stage("clip-shelf", zero_work_hint="no recorded clip was found in "
                     "channel/imagery/clips to judge") as st:
            try:
                r = shelve()
            except ShelfStop as e:
                st.named_stop(e.code, str(e).split("] ", 1)[-1],
                              unblock="Nothing is lost: no local clip is deleted before its Drive copy "
                                      "verifies. The next daily run retries.")
            if r.get("waited"):
                st.named_stop("SHELF_WAITS_FOR_RENDER", f"shelving waits: {r['waited']}",
                              unblock="Nothing to do: the next daily run shelves.")
            m = load()
            on = sum(1 for n in m["clips"] if not (CLIPS / n).exists())
            if r["shelved"] + r["warm"]:
                st.work(f"judged {r['shelved'] + r['warm'] + len(r['skipped'])} clip(s): shelved "
                        f"{r['shelved']} idle 7+ days ({r['bytes'] / 2**30:.2f} GiB) to {remote()}, "
                        f"{r['warm']} warm stay; {on} on the shelf")
            for x in r.get("skipped", [])[:10]:
                st.note(x)
            print(f"OUTPUT shelved {r['shelved']} clip(s) ({r['bytes'] / 2**30:.2f} GiB); "
                  f"{r['warm']} warm; {on} on the shelf")
        return 0
    try:
        if argv[:1] == ["pull-all"]:
            pull_all()
            return 0
        if argv[:1] == ["status"]:
            m = load()
            off = [n for n in m["clips"] if not (CLIPS / n).exists()]
            print(f"OUTPUT {len(off)} clip(s) on the shelf "
                  f"({sum(m['clips'][n]['size'] for n in off) / 2**30:.2f} GiB)")
            return 0
    except ShelfStop as e:
        print(str(e))
        return 3
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
