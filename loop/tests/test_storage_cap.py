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

# 6. the cap reads the WHOLE ACCOUNT (R2's free 10 GB is per account): 20 Nov
#    2026 the account held 11.17 GB while this bucket alone read 2.87 GB.
def fake_api(buckets, broken=None):
    def fetch(url):
        if url.endswith("/usage"):
            n = url.rsplit("/", 2)[-2]
            return {"result": {} if n == broken else {"payloadSize": str(buckets[n]), "metadataSize": "0"}}
        return {"result": {"buckets": [{"name": n} for n in buckets]}}
    return fetch


acct = {"how-we-know-renders": 2_870_000_000, "creator-studios-hadiyah-files": 5_384_000_000,
        "boss-os-documents": 795_000_000}
got = r2.account_usage_bytes("a", "t", fetch=fake_api(acct))
check(got == sum(acct.values()), f"(6) account usage {got} is not the sum of every bucket {sum(acct.values())}")
for label, f in (("one bucket unreadable", fake_api(acct, broken="boss-os-documents")),
                 ("no buckets listed", fake_api({}))):
    try:
        r2.account_usage_bytes("a", "t", fetch=f)
        check(False, f"(6) {label}: judged on a partial or guessed total")
    except r2.R2Unavailable as e:
        check(e.code == "R2_USAGE_UNREADABLE", f"(6) {label}: wrong code {e.code}")
check(SC.R2_FLOOR <= 9_000_000_000, f"(6) the floor {SC.R2_FLOOR} is above her 9 GB line")


# 7. the daily check: alarm (issue @-mentioning her) at the line, close when under,
#    NAMED STOP when the total cannot be read.
class GH:
    def __init__(self, open_=()):
        self.calls, self.open_ = [], list(open_)

    def __call__(self, argv, **_):
        self.calls.append(argv[1:3])
        out = json.dumps([{"number": n, "body": SC.MARKER} for n in self.open_]) if argv[1:3] == ["issue", "list"] else ""
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()


gh = GH()
SC.check(usage=lambda: 9_000_000_000, runner=gh)
check(["issue", "create"] in gh.calls, f"(7) 9.00 GB did not open the alarm issue: {gh.calls}")
gh = GH(open_=[42])
SC.check(usage=lambda: 9_400_000_000, runner=gh)
check(["issue", "comment"] in gh.calls and ["issue", "create"] not in gh.calls, f"(7) an open alarm was not re-mentioned: {gh.calls}")
gh = GH(open_=[42])
SC.check(usage=lambda: 8_200_000_000, runner=gh)
check(["issue", "close"] in gh.calls, f"(7) back under 9 GB did not close the alarm: {gh.calls}")
gh = GH()
SC.check(usage=lambda: 8_200_000_000, runner=gh)
check(not [c for c in gh.calls if c[1] in ("create", "comment")], f"(7) under the line still alarmed: {gh.calls}")


def unreadable():
    raise r2.R2Unavailable("R2_USAGE_UNREADABLE", "x")


check(SC.check(usage=unreadable, runner=GH()) == 2, "(7) an unreadable total was not NAMED STOP exit 2")


# 8. the nightly push never re-shelves what the cap just cleared: the uploaded
#    cut (Damascus, re-shelved 18 Nov after its 8 Nov upload) or a superseded cut.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    st = root / "loop" / "state"
    st.mkdir(parents=True)
    st.joinpath("ledger.json").write_text(json.dumps({"published": [
        {"slug": "up", "video_id": "v1", "uploaded_at": "2026-11-08T15:06:08+00:00"},
        {"slug": "gone", "video_id": "v2", "uploaded_at": "2026-11-08T15:06:08+00:00", "retired_at": "2026-11-09"},
        {"slug": "swapping", "video_id": "v3", "uploaded_at": "2026-11-08T15:06:08+00:00"}]}))
    st.joinpath("superseded_swaps.json").write_text(json.dumps({"swaps": {"swapping": {"phase": "uploading"}}}))
    old = root / "old.mp4"
    old.write_bytes(b"superseded-cut")
    st.joinpath("superseded_renders.json").write_text(json.dumps({"retired-ep": {
        "sha256": "0" * 64, "bytes": 1, "also": [{"sha256": hashlib.sha256(old.read_bytes()).hexdigest(),
                                                 "bytes": old.stat().st_size}]}}))
    done = r2.uploaded_renders(root)
    check(set(done) == {"up"}, f"(8) live uploads {sorted(done)}, wanted only ['up'] (retired and mid-swap excluded)")
    f = root / "r.mp4"
    f.write_bytes(b"cut")
    os.utime(f, (1762560000, 1762560000))                  # 8 Nov 2025: before the upload
    check(bool(r2._not_needed("up", f, done, root)), "(8) the uploaded cut would be re-shelved")
    os.utime(f, (1795000000, 1795000000))                  # after the upload: a remake
    check(not r2._not_needed("up", f, done, root), "(8) a remake newer than the upload would NOT ship")
    check(not r2._not_needed("swapping", f, done, root), "(8) a mid-swap cut would not be shelved")
    check(bool(r2._not_needed("retired-ep", old, done, root)), "(8) a superseded cut would be re-shelved")
    check(not r2._not_needed("retired-ep", f, done, root), "(8) a new cut of a superseded episode would not ship")

if fails:
    print("FAIL test_storage_cap")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_storage_cap: account-wide total, 9 GB floor; confirmed uploads first, then Drive, then STORAGE_FREE_CAP; daily alarm opens/closes; the push never re-shelves an uploaded or superseded cut")
