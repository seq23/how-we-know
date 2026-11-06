#!/usr/bin/env python3
"""ONE consent click: let the loop keep overflow renders in her Google Drive.

    .venv/bin/python auth/drive_auth.py

Reuses the existing Google OAuth client (.secrets/client_secret.json, the
same one YouTube uses) and asks for ONE scope: drive.file - the loop can see
and change only the files it creates itself (the folder "How We Know +
Whisper Almanac overflow"), never anything else in her Drive. Sign in with
the Google account that owns both YouTube channels.

Saves .secrets/drive_token.json (gitignored) and, when `gh` is signed in,
the repo secret GDRIVE_TOKEN_JSON so the cloud upload lane can pull a render
back. Until this has run, the Drive step of loop/storage_cap.py is a note and
falls through to NAMED STOP [STORAGE_FREE_CAP].
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "auth"))

import tokens as T                                          # noqa: E402
import youtube_auth as Y                                    # noqa: E402

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
OUT = T.SECRETS / "drive_token.json"
ACCOUNT = "the Google account that owns both channels"


def main() -> int:
    client = T.load_client()
    if not client:
        print("NAMED STOP [OAUTH_CLIENT_MISSING] no .secrets/client_secret.json on this Mac")
        return 3
    T.SCOPES = [DRIVE_SCOPE]          # this consent asks for Drive only
    T.EXPECTED_HANDLE = ACCOUNT
    got = Y.consent(client)
    if "error" in got or not got.get("refresh_token"):
        print(f"NAMED STOP [DRIVE_CONSENT_FAILED] {got.get('error') or 'no refresh token came back'}")
        return 3
    tok = {"client_id": client["client_id"], "client_secret": client["client_secret"],
           "refresh_token": got["refresh_token"], "scope": DRIVE_SCOPE, "account": ACCOUNT}
    T.safe_write(OUT, tok)
    print(f"saved {OUT.relative_to(ROOT)} (drive.file only)")
    r = subprocess.run(["gh", "secret", "set", "GDRIVE_TOKEN_JSON", "-R", "seq23/how-we-know"],
                       input=json.dumps(tok), text=True, capture_output=True)
    print("saved the GDRIVE_TOKEN_JSON repo secret" if r.returncode == 0 else
          f"could not set the repo secret ({r.stderr.strip()[:120]}); the Mac still works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
