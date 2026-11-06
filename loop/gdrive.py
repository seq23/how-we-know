"""Google Drive, drive.file scope only: the free overflow shelf for renders.

One folder, "How We Know + Whisper Almanac overflow", in the Google account
that owns both YouTube channels. The token comes from
auth/drive_auth.py (.secrets/drive_token.json on the Mac, GDRIVE_TOKEN_JSON in
Actions). No token = `available()` is False, and loop/storage_cap.py treats
the Drive step as a note. Never paid: free_bytes() reads the account's own
quota and the cap keeps a margin under the free 15 GB.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".secrets" / "drive_token.json"
FOLDER = "How We Know + Whisper Almanac overflow"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
CHUNK = 32 * 1024 * 1024


def _token_record() -> dict | None:
    raw = os.environ.get("GDRIVE_TOKEN_JSON", "").strip()
    if raw:
        return json.loads(raw)
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def available() -> bool:
    return _token_record() is not None


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Drive:
    def __init__(self, rec: dict | None = None):
        self.rec = rec or _token_record()
        if not self.rec:
            raise RuntimeError("no Drive token (auth/drive_auth.py has not been run)")
        self._access = None
        self._folder = None

    def _token(self) -> str:
        if not self._access:
            data = urllib.parse.urlencode({
                "client_id": self.rec["client_id"], "client_secret": self.rec["client_secret"],
                "refresh_token": self.rec["refresh_token"], "grant_type": "refresh_token"}).encode()
            with urllib.request.urlopen(urllib.request.Request(
                    "https://oauth2.googleapis.com/token", data=data), timeout=30) as r:
                self._access = json.loads(r.read())["access_token"]
        return self._access

    def _req(self, url, data=None, method=None, headers=None, raw=False):
        h = {"Authorization": f"Bearer {self._token()}", **(headers or {})}
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        r = urllib.request.urlopen(req, timeout=600)
        return r if raw else json.loads(r.read() or b"{}")

    def free_bytes(self) -> int:
        q = self._req(f"{API}/about?fields=storageQuota")["storageQuota"]
        return int(q.get("limit", 0)) - int(q.get("usage", 0))

    def folder(self) -> str:
        if self._folder:
            return self._folder
        q = urllib.parse.quote(f"name = '{FOLDER}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        hits = self._req(f"{API}/files?q={q}&fields=files(id)").get("files", [])
        if hits:
            self._folder = hits[0]["id"]
        else:
            body = json.dumps({"name": FOLDER, "mimeType": "application/vnd.google-apps.folder"}).encode()
            self._folder = self._req(f"{API}/files", body, "POST", {"Content-Type": "application/json"})["id"]
        return self._folder

    def upload(self, path: Path, name: str) -> dict:
        """Resumable upload; returns {id, md5Checksum, size}."""
        path = Path(path)
        size = path.stat().st_size
        meta = json.dumps({"name": name, "parents": [self.folder()]}).encode()
        r = self._req(f"{UPLOAD}?uploadType=resumable&fields=id,md5Checksum,size", meta, "POST",
                      {"Content-Type": "application/json", "X-Upload-Content-Length": str(size)}, raw=True)
        loc = r.headers["Location"]
        with open(path, "rb") as f:
            off = 0
            while True:
                chunk = f.read(CHUNK)
                end = off + len(chunk) - 1
                req = urllib.request.Request(loc, data=chunk, method="PUT", headers={
                    "Content-Range": f"bytes {off}-{end}/{size}" if chunk else f"bytes */{size}"})
                try:
                    resp = urllib.request.urlopen(req, timeout=600)
                    return json.loads(resp.read())
                except urllib.error.HTTPError as e:
                    if e.code != 308:
                        raise
                off = end + 1

    def download(self, file_id: str, dest: Path) -> Path:
        r = self._req(f"{API}/files/{file_id}?alt=media", raw=True)
        with open(dest, "wb") as f:
            for b in iter(lambda: r.read(1 << 20), b""):
                f.write(b)
        return dest

    def delete(self, file_id: str) -> None:
        self._req(f"{API}/files/{file_id}", method="DELETE", raw=True)
