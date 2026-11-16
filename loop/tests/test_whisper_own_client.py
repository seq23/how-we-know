"""Whisper Almanac signs in with its OWN OAuth client (16 Nov 2026).

Its uploads must bill Google Cloud project whisper-almanac-uploads, never How
We Know's quota. Proved: auth/whisper_youtube_auth.py hands Google the
Almanac's client, and with no Almanac client it stops (OAUTH_CLIENT_MISSING)
rather than falling back to How We Know's, even when that one exists.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "auth"))
import tokens as T                                          # noqa: E402
import whisper_youtube_auth as W                            # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="whisper-client-"))
hwk, wa = tmp / "client_secret.json", tmp / "client_secret_whisper.json"
hwk.write_text(json.dumps({"installed": {"client_id": "hwk-id", "client_secret": "x"}}))
T.CLIENT_FILE, T.WHISPER_CLIENT_FILE = hwk, wa
seen: list[str] = []
W.Y.consent = lambda client: seen.append(client["client_id"]) or {"error": "stopped by the test"}

fails = []
rc = W.main()
if rc != 3 or seen:
    fails.append(f"no Almanac client: want a stop and no consent, got rc={rc}, consent with {seen}")
wa.write_text(json.dumps({"installed": {"client_id": "whisper-id", "client_secret": "y"}}))
rc = W.main()
if seen != ["whisper-id"]:
    fails.append(f"consent used {seen}, not the Almanac's own client")
if fails:
    raise SystemExit("FAIL:\n  " + "\n  ".join(fails))
print("PASS: the Almanac signs in with its own client, never How We Know's (2 checks)")
