"""One-time YouTube consent. Run once; the loop never asks again.

    .venv/bin/python auth/youtube_auth.py

It opens a Google consent screen, she clicks **Allow**, and the refresh token is
written to `.secrets/youtube_token.json` (0600, gitignored). Every later run —
and every loop stage — refreshes silently and never re-prompts unless the token
is genuinely revoked or expired.

The last thing it prints is the one line that matters: **which channel it
actually authorised.** Authorising the wrong Google account is the most common
way this goes wrong, and nothing else in the pipeline would ever tell you.

Implementation: a stdlib loopback flow with PKCE. `google-auth-oauthlib` is used
automatically if it is installed, but it is not required — it pulls 22 packages
into a venv that is shared with a live render, and none of them are needed to
upload.

If `client_secret.json` is absent this prints exactly what is missing and where
to put it, then **exits 0**: nothing is broken, she simply has not dropped the
file yet. It is a named stop with an audience of one, standing at the terminal.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tokens as T  # noqa: E402

DONE_HTML = b"""<!doctype html><meta charset=utf-8>
<title>How We Know - authorised</title>
<style>body{font:16px -apple-system,sans-serif;background:#0b1620;color:#e8f1f6;
display:grid;place-items:center;height:100vh;margin:0;text-align:center}
b{color:#57c7e3}</style>
<div><h1>Authorised</h1><p>You can close this tab and return to the terminal.
<br>The channel it authorised is printed there - <b>please check it.</b></p></div>
"""


def banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def named_stop(status: str, extra: str = "") -> int:
    """A named stop with a human standing right there. Exits 0 by design: this
    is an interactive helper, not a scheduled stage, and the work it did was
    telling her precisely what to do next."""
    banner(f"NAMED STOP  [{status.upper()}]")
    print(T.stop_message(status, extra))
    print("=" * 64 + "\n")
    return 0


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class Catcher(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):                                   # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Catcher.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DONE_HTML)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *a):                          # silence the access log
        pass


def consent(client: dict) -> dict:
    port = free_port()
    redirect = f"http://127.0.0.1:{port}"
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(24)

    url = T.AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(T.SCOPES),
        "access_type": "offline",
        # Force a refresh token even if this account consented before.
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    banner("Opening the Google consent screen")
    print("  Sign in as the Google account that owns "
          f"{T.EXPECTED_HANDLE}, then click Allow.")
    print("  If the browser does not open, paste this URL yourself:\n")
    print(f"  {url}\n")
    print("  Waiting for the redirect… (Ctrl-C to abort)")

    srv = http.server.HTTPServer(("127.0.0.1", port), Catcher)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        return {"error": "aborted at the terminal"}
    finally:
        srv.server_close()

    got = Catcher.result
    if got.get("state") != state:
        return {"error": "state mismatch — the redirect did not come from the "
                         "request this script made. Nothing was saved."}
    if "error" in got:
        return {"error": f"Google returned: {got['error']}"}
    if "code" not in got:
        return {"error": "no authorisation code came back"}

    data = urllib.parse.urlencode({
        "code": got["code"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(T.TOKEN_URL, data=data), timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            why = json.loads(body).get("error_description") or \
                  json.loads(body).get("error")
        except json.JSONDecodeError:
            why = f"HTTP {e.code}"
        return {"error": f"token exchange failed: {why}"}


def try_google_lib(client_file: Path):
    """Use google-auth-oauthlib if it is already installed. Never install it."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return None
    print("  (google-auth-oauthlib is installed; using it)")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), T.SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    return {"access_token": creds.token, "refresh_token": creds.refresh_token,
            "expires_in": 3600}


def main() -> int:
    banner("How We Know — YouTube authorisation")
    print(f"  client : {T.CLIENT_FILE}")
    print(f"  token  : {T.TOKEN_FILE}")
    print(f"  scopes : {', '.join(s.rsplit('/', 1)[1] for s in T.SCOPES)}")

    client = T.load_client()
    if client is None:
        if T.CLIENT_FILE.exists():
            return named_stop(
                "no_client",
                f"{T.CLIENT_FILE.name} exists but has no client_id/client_secret "
                f"— it may be an API key file or a Web client rather than a "
                f"Desktop app client.")
        return named_stop("no_client")

    if client["kind"] == "web":
        print("\n  Note: this is a *Web application* client. A Desktop app "
              "client is the\n  supported type for this flow; continuing, but "
              "if Google rejects the\n  redirect URI, create a Desktop app "
              "client instead.")
    print(f"  client_id: {T.redact(client['client_id'], 12)}")

    # Already authorised? Then this run must not re-prompt - UNLESS the stored
    # token is missing a scope T.SCOPES now asks for.
    #
    # 2026-08-31: yt-analytics.readonly was added to T.SCOPES so loop/measure.py
    # could pull retention. Re-running this script printed "A valid token is
    # already stored - not re-prompting" and exited 0, because "valid" was being
    # read as "not expired". The token was indeed valid - for the two scopes it
    # already had - so the new scope was never granted and measure.py kept
    # returning 403. A check that passes while the thing it guards is wrong.
    #
    # Google does not widen an existing grant. A new scope needs a new consent,
    # so scope drift must force the prompt.
    existing = T.load()
    if existing["status"] == "ok":
        granted = set(existing.get("scopes") or [])
        missing = [s for s in T.SCOPES if s not in granted] if granted else []
        if granted and missing:
            print("\n  A stored token exists, but it is missing "
                  f"{len(missing)} scope(s) this build now requires:")
            for s in missing:
                print(f"    - {s.rsplit('/', 1)[1]}")
            print("  Google will not widen an existing grant, so re-consenting now.")
        else:
            print("\n  A valid token is already stored — not re-prompting.")
            return report(existing["access_token"], existing)
    if existing["status"] == "expired_refresh":
        print("\n  The stored refresh token has expired; re-consenting now.")

    result = try_google_lib(T.CLIENT_FILE) or consent(client)
    if "error" in result:
        banner("NAMED STOP  [CONSENT_NOT_COMPLETED]")
        print(f"  {result['error']}")
        print("  Nothing was written. Re-run when ready:")
        print("    .venv/bin/python auth/youtube_auth.py")
        print("=" * 64 + "\n")
        return 0

    if not result.get("refresh_token"):
        banner("NAMED STOP  [NO_REFRESH_TOKEN]")
        print("  Google returned an access token but no refresh token, so the\n"
              "  loop could not renew it unattended.\n"
              "  Revoke this app at myaccount.google.com/permissions and re-run;\n"
              "  a fresh consent always returns one.")
        print("=" * 64 + "\n")
        return 0

    path = T.store(result["access_token"], result["refresh_token"],
                   result.get("expires_in", 3600), T.SCOPES)
    print(f"\n  refresh token saved to {path} (mode 0600, gitignored)")
    print(f"  refresh token: {T.redact(result['refresh_token'])}")
    return report(result["access_token"], {"refresh_token_age_days": 0.0})


def report(access_token: str, meta: dict) -> int:
    """Print which channel this actually authorised. The point of the script."""
    ch = T.channel(access_token)
    banner("Authorised channel")
    if not ch["ok"]:
        print(f"  Could not read the channel: {ch['detail']}")
        print("  The token was saved, but until this resolves the upload lane\n"
              "  will not run. Check that the account owns a YouTube channel.")
        print("=" * 64 + "\n")
        return 0

    print(f"  title       : {ch['title']}")
    print(f"  handle      : {ch['handle'] or '(none set)'}")
    print(f"  channel id  : {ch['id']}")
    print(f"  videos      : {ch['videos']}   subscribers: {ch['subscribers']}")

    if ch["matches_expected"]:
        print(f"\n  ✓ This is {T.EXPECTED_HANDLE}. Correct account.")
    else:
        print("\n  " + "!" * 58)
        print(f"  !! WRONG ACCOUNT. Expected {T.EXPECTED_HANDLE}, "
              f"got {ch['handle'] or '(no handle)'}.")
        print("  !! Videos would upload to the WRONG CHANNEL.")
        print("  !! Fix: revoke at myaccount.google.com/permissions,")
        print(f"  !!      delete {T.TOKEN_FILE.name}, and re-run signed in as")
        print(f"  !!      the account that owns {T.EXPECTED_HANDLE}.")
        print("  " + "!" * 58)

    print("\n  Two Google behaviours to expect, both designed for:")
    print("   • An unverified app has uploads forced to PRIVATE. The loop")
    print("     uploads private first and flips to public later, so this is free.")
    print("   • A project in Testing mode expires refresh tokens after 7 days.")
    print("     Publish the app on the OAuth consent screen to stop that.")
    print("\n  Next: .venv/bin/python auth/check_auth.py")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
