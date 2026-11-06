#!/usr/bin/env python3
"""ONE "Allow" click: let the loop upload to the Whisper Almanac channel.

    .venv/bin/python auth/whisper_youtube_auth.py

Reuses the How We Know OAuth client (.secrets/client_secret.json; its
scheduled uploads go public, measured 6 Nov 2026) with the same YouTube
scopes. Sign in as cryptoclearr@gmail.com and, when Google asks which
channel, pick Whisper Almanac (@whisperalmanac) - NOT How We Know Deep.

Saves .secrets/whisper_youtube_token.json (gitignored) and, when `gh` is
signed in, the repo secret WHISPER_YT_TOKEN_JSON for the cloud upload lane.
The channel it was granted for is read back and must be @whisperalmanac, or
nothing is saved (a token for the wrong channel would upload sleep videos to
How We Know).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "auth"))

import tokens as T                                          # noqa: E402
import youtube_auth as Y                                    # noqa: E402

OUT = T.SECRETS / "whisper_youtube_token.json"
HANDLE = "@whisperalmanac"


def main() -> int:
    client = T.load_client()
    if not client:
        print("NAMED STOP [OAUTH_CLIENT_MISSING] no .secrets/client_secret.json on this Mac")
        return 3
    T.EXPECTED_HANDLE = f"{HANDLE} (pick Whisper Almanac on the channel screen)"
    got = Y.consent(client)
    if "error" in got or not got.get("refresh_token"):
        print(f"NAMED STOP [WHISPER_CONSENT_FAILED] {got.get('error') or 'no refresh token came back'}")
        return 3
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                 headers={"Authorization": f"Bearer {got['access_token']}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.loads(r.read()).get("items", [])
    handle = (items[0]["snippet"].get("customUrl") or "").lower() if items else ""
    if handle != HANDLE:
        print(f"NAMED STOP [WHISPER_WRONG_CHANNEL] the grant is for {handle or 'no channel'}, not "
              f"{HANDLE}; nothing saved. Run it again and pick Whisper Almanac.")
        return 3
    tok = {"client_id": client["client_id"], "client_secret": client["client_secret"],
           "refresh_token": got["refresh_token"], "scopes": T.SCOPES, "channel": HANDLE}
    T.safe_write(OUT, tok)
    print(f"saved {OUT.relative_to(ROOT)} for {HANDLE}")
    r = subprocess.run(["gh", "secret", "set", "WHISPER_YT_TOKEN_JSON", "-R", "seq23/how-we-know"],
                       input=json.dumps(tok), text=True, capture_output=True)
    print("saved the WHISPER_YT_TOKEN_JSON repo secret" if r.returncode == 0 else
          f"could not set the repo secret ({r.stderr.strip()[:120]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
