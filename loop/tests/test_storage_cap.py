"""The free-storage cap, in order, and it never deletes what is not uploaded or
safely copied (6 Nov 2026: R2 held 9.99 GB of its free 10).

  1. at the floor, R2 copies of CONFIRMED uploads go first (YouTube says
     processed); an upload YouTube does not confirm, or one mid-swap, stays;
  2. still short: the queued render LAST in the upload line moves to Drive,
     verified by md5, and r2.get() pulls it back byte-identical;
  3. Drive not consented, or near its free 15 GB, or a copy that does not
     verify: nothing unsafe happens, and the write is NAMED STOP
     [STORAGE_FREE_CAP] - the object is NOT written, so nothing is billed.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r2  # noqa: E402
import storage_cap as SC  # noqa: E402

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


class FakeDrive:
    def __init__(self, free=10 ** 12, corrupt=False):
        self.files, self.free, self.corrupt = {}, free, corrupt

    def free_bytes(self):
        return self.free - sum(len(b) for b in self.files.values())

    def upload(self, path, name):
        b = Path(path).read_bytes()
        fid = f"f{len(self.files)}"
        self.files[fid] = b
        md5 = hashlib.md5(b"x" if self.corrupt else b).hexdigest()
        return {"id": fid, "md5Checksum": md5, "size": len(b)}

    def download(self, fid, dest):
        Path(dest).write_bytes(self.files[fid])
        return dest

    def delete(self, fid):
        self.files.pop(fid, None)


def world(td: Path):
    shelf = r2.LocalBackend(td / "shelf")
    src = td / "src"
    src.mkdir()
    body = {}
    for s, n in (("up-a", 3000), ("up-b", 3000), ("swap-c", 3000), ("q1", 2000), ("q2", 2000), ("q3", 2000)):
        f = src / f"{s}.mp4"
        f.write_bytes(os.urandom(n))
        body[s] = hashlib.sha256(f.read_bytes()).hexdigest()
        shelf.put(f, r2.render_key(s))
    led = {"published": [{"slug": "up-a", "video_id": "va"}, {"slug": "up-b", "video_id": "vb"},
                         {"slug": "swap-c", "video_id": "vc"}]}
    deps = dict(ledger=led, queued=["q1", "q2", "q3"], local_renders=td / "none",
                swaps={"swap-c": {"phase": "uploading"}},
                yt=lambda ids: {"va": {"uploadStatus": "processed"}, "vb": {"uploadStatus": "uploaded"},
                                "vc": {"uploadStatus": "processed"}})
    new = src / "new.mp4"
    new.write_bytes(os.urandom(2500))
    return shelf, deps, new, body


def safe(shelf, drive, body, label):
    """Every object that is not a confirmed upload is still in R2 or Drive, intact."""
    for s in ("up-b", "swap-c", "q1", "q2", "q3"):
        k = r2.render_key(s)
        m = shelf.meta(k) or {}
        if m.get(SC.MARK):
            ok = drive is not None and hashlib.sha256(drive.files.get(m[SC.MARK], b"")).hexdigest() == body[s]
        else:
            ok = (shelf.head(k) or {}).get("sha256") == body[s]
        check(ok, f"{label}: {s} is no longer safely held")


def put(shelf, new, floor):
    os.environ["R2_FREE_FLOOR_BYTES"] = str(floor)
    try:
        shelf.put(new, "renders/new-final.mp4")
        return None
    except r2.R2Unavailable as e:
        return e
    finally:
        os.environ.pop("R2_FREE_FLOOR_BYTES", None)


# 1. a small shortfall: only the confirmed upload is deleted
with tempfile.TemporaryDirectory() as td:
    shelf, deps, new, body = world(Path(td))
    drive = FakeDrive()
    SC.DEPS = dict(deps, drive=drive)
    e = put(shelf, new, shelf.usage_bytes() + 2500 + 4096 - 1000)
    check(e is None, f"(1) a write that fits after clearing a confirmed upload was refused: {e}")
    check(shelf.head(r2.render_key("up-a")) is None, "(1) the confirmed upload was not cleared")
    check(not drive.files, "(1) Drive was used before the confirmed uploads were cleared")
    safe(shelf, drive, body, "(1)")

# 2. a big shortfall: then the LAST in line goes to Drive, and comes back intact
with tempfile.TemporaryDirectory() as td:
    shelf, deps, new, body = world(Path(td))
    drive = FakeDrive()
    SC.DEPS = dict(deps, drive=drive)
    e = put(shelf, new, shelf.usage_bytes() + 2500 + 4096 - 4500)
    check(e is None, f"(2) overflow to Drive did not make room: {e}")
    moved = [s for s in ("q1", "q2", "q3") if (shelf.meta(r2.render_key(s)) or {}).get(SC.MARK)]
    check(moved == ["q3"], f"(2) moved {moved}, wanted only the last in line ['q3']")
    back = Path(td) / "back.mp4"
    shelf.get(r2.render_key("q3"), back)
    check(hashlib.sha256(back.read_bytes()).hexdigest() == body["q3"], "(2) the pull-back is not byte-identical")
    safe(shelf, drive, body, "(2)")

# 3. Drive not consented: a note, then STORAGE_FREE_CAP, the write not made
with tempfile.TemporaryDirectory() as td:
    shelf, deps, new, body = world(Path(td))
    SC.DEPS = dict(deps)
    import gdrive  # noqa: E402
    real_avail, gdrive.available = gdrive.available, (lambda: False)
    e = put(shelf, new, shelf.usage_bytes() + 2500 + 4096 - 4500)
    gdrive.available = real_avail
    check(e is not None and e.code == "STORAGE_FREE_CAP", f"(3) no Drive and no room was not STORAGE_FREE_CAP: {e}")
    check(shelf.head("renders/new-final.mp4") is None, "(3) the refused write landed anyway (a bill)")
    safe(shelf, None, body, "(3)")

# 4. Drive near its free 15 GB, and 5. a Drive copy that does not verify
for label, drive in (("(4) Drive full", FakeDrive(free=SC.DRIVE_MARGIN)), ("(5) bad copy", FakeDrive(corrupt=True))):
    with tempfile.TemporaryDirectory() as td:
        shelf, deps, new, body = world(Path(td))
        SC.DEPS = dict(deps, drive=drive)
        e = put(shelf, new, shelf.usage_bytes() + 2500 + 4096 - 4500)
        check(e is not None and e.code == "STORAGE_FREE_CAP", f"{label}: not STORAGE_FREE_CAP: {e}")
        check(all(not (shelf.meta(r2.render_key(s)) or {}).get(SC.MARK) for s in ("q1", "q2", "q3")),
              f"{label}: R2 bytes were replaced without a verified Drive copy")
        safe(shelf, drive, body, label)
SC.DEPS = {}

if fails:
    print("FAIL test_storage_cap")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_storage_cap: confirmed uploads first, then Drive (last in line, verified), then STORAGE_FREE_CAP; nothing unsafe deleted")
