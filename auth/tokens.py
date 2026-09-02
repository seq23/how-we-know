"""Credential storage and refresh for the YouTube lanes. Shared by everything.

Design notes worth knowing before changing anything here:

**No third-party dependencies.** The obvious build uses `google-auth-oauthlib`,
which pulls in 22 packages including `cryptography` and `protobuf`. The repo's
`.venv` is shared with a live render, and the loop's upload path needs none of
it: an installed-app OAuth flow is a browser redirect and two HTTPS POSTs. So
this is stdlib, and `google-auth-oauthlib` is used automatically *if it happens
to be installed* — never required.

**Nothing here ever prints a secret.** Every diagnostic goes through `redact()`.
The token file is written 0600 and lives in `.secrets/`, which is gitignored as
a whole directory rather than as a list of filenames.

**Two Google behaviours are designed for, not discovered at runtime:**

* An **unverified app** has its uploads forced to `private`. **This project is
  in production but NOT verified** (checked in the Cloud console 2026-09-02:
  "Publishing status: In production", with a "Your app requires verification"
  banner), so that forcing is live. It costs nothing because the loop uploads
  private by design and flips to public later against a receipt — but that
  design is *required*, not a preference. Anyone who "simplifies" it by
  uploading with `privacyStatus=public` will find YouTube silently ignoring it.
* A project in **Testing** publishing mode issues refresh tokens that expire
  after **7 days**. **This project is NOT in Testing**, so that does not apply
  here — checked 2026-09-02. The handling stays because publishing status can
  be changed back: `load()` reports the state as `expired_refresh` and every
  caller turns it into an actionable message naming the fix, never a retry into
  a wall. Nothing in this repo may state the project IS in Testing; no code
  here can see that setting, and asserting it unchecked has already cost time.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".secrets"
CLIENT_FILE = SECRETS / "client_secret.json"
TOKEN_FILE = SECRETS / "youtube_token.json"
API_KEY_FILE = SECRETS / "youtube_api_key.txt"

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

# youtube.upload to publish; youtube.readonly to confirm which channel we are on.
# yt-analytics.readonly added 2026-08-31. Without it loop/measure.py gets a 403
# every Friday and the measurement lane is inert - no retention, no RPM, and the
# monthly review has nothing to read. Retention is the one measurement that can
# tell us the ~8 minute format is wrong, so a silent 403 there is expensive.
#
# It also needs the YouTube Analytics API enabled on Cloud project 681552889891;
# the scope alone is not enough and the failure looks identical either way.
#
# NOTE: adding a scope invalidates nothing, but the existing refresh token does
# NOT gain it - re-running auth/youtube_auth.py is required, and until that
# happens measure.py will keep 403ing. check_auth.py reports which scopes the
# live token actually carries; trust that over this list.
# youtube (full) is REQUIRED, not a convenience: videos.update - the private ->
# public flip that publish.py exists to perform, and the privacy flip that
# retire.py performs - returns 403 insufficientPermissions under youtube.upload
# alone. Confirmed 2026-09-01 against both a fresh upload and the live video.
#
# This was invisible until now because the channel's first video was uploaded
# with privacyStatus=public directly, so the flip had never once been exercised.
# Every scheduled publish would have failed the same way, weekly, with the
# render and upload lanes reporting green ahead of it.
# youtube.force-ssl added 2026-09-02, and it is the ONLY scope in this list the
# stored token does not already carry. captions.insert accepts force-ssl or
# youtubepartner and nothing else - the plain `youtube` scope does NOT cover it,
# which is why videos.update works today and captions do not. Verified against
# developers.google.com/youtube/v3/docs/captions/insert on 2026-09-02.
#
# What it unblocks is bigger than subtitles. YouTube Studio states it plainly:
# "English subtitles are the default source for auto-translation of subtitles
# and audio." No English caption track means no auto-translated subtitles and no
# auto-dubbed audio, in any language - the channel's cheapest route to Partner
# Programme watch hours before the threshold doubles on 2026-02-01.
#
# Adding it here does NOT break anything already working: the stored token stays
# valid for the four scopes it has, and every lane except loop/captions_lane.py
# runs on those. What it does do is make ONE run of auth/youtube_auth.py grant
# it - that script forces the consent prompt on scope drift (see the note below)
# rather than reporting "already valid".
SCOPES = ["https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]

EXPECTED_HANDLE = "@howweknowdeep"


# --------------------------------------------------------------- redaction

def redact(value: str | None, keep: int = 4) -> str:
    """The only way a credential-adjacent string may reach a log or a screen."""
    if not value:
        return "<absent>"
    s = str(value)
    if len(s) <= keep:
        return "*" * len(s)
    return f"{s[:keep]}…{'*' * 6} ({len(s)} chars)"


def safe_write(path: Path, obj: dict) -> None:
    """Write JSON with owner-only permissions, and never widen them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    os.chmod(path, 0o600)


# ------------------------------------------------------------ client config

def load_client() -> dict | None:
    """The Desktop-app OAuth client she downloads. None if absent."""
    if not CLIENT_FILE.exists():
        return None
    try:
        raw = json.loads(CLIENT_FILE.read_text())
    except json.JSONDecodeError:
        return None
    c = raw.get("installed") or raw.get("web") or raw
    if not c.get("client_id") or not c.get("client_secret"):
        return None
    return {"client_id": c["client_id"], "client_secret": c["client_secret"],
            "kind": "web" if "web" in raw else "installed"}


def api_key() -> str | None:
    if not API_KEY_FILE.exists():
        return None
    k = API_KEY_FILE.read_text().strip()
    return k or None


# -------------------------------------------------------------------- token

def load(refresh: bool = True) -> dict:
    """Resolve a usable access token.

    Returns a dict with `status`, one of:
        ok               access token present and valid
        no_client        client_secret.json is not there yet
        no_token         client is there, consent has never been given
        expired_refresh  the refresh token no longer works (7-day testing mode,
                         a password change, or consent revoked)
        error            anything else, with `detail`

    Never raises, and never puts a secret in the return value except
    `access_token`, which callers use and must not print.
    """
    client = load_client()
    if client is None:
        return {"status": "no_client"}
    if not TOKEN_FILE.exists():
        return {"status": "no_token"}

    try:
        tok = json.loads(TOKEN_FILE.read_text())
    except json.JSONDecodeError:
        return {"status": "error",
                "detail": f"{TOKEN_FILE.name} is not valid JSON"}

    if not tok.get("refresh_token"):
        return {"status": "no_token",
                "detail": "the stored token has no refresh_token; consent must "
                          "be granted again with prompt=consent"}

    # Reuse a still-valid access token; 120s of slack for clock skew.
    if not refresh and tok.get("access_token") and \
            tok.get("expires_at", 0) > time.time() + 120:
        # `scopes` is passed through so callers can detect scope DRIFT, not just
        # expiry. Without it, youtube_auth.py read "not expired" as "authorised"
        # and skipped re-consent after yt-analytics.readonly was added to SCOPES -
        # the token stayed valid for the two scopes it had, the new one was never
        # granted, and measure.py kept returning 403 behind a green auth run.
        return {"status": "ok", "access_token": tok["access_token"],
                "obtained_at": tok.get("obtained_at"),
                "scopes": tok.get("scopes") or [],
                "refresh_token_age_days": _age_days(tok)}

    data = urllib.parse.urlencode({
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    try:
        req = urllib.request.Request(TOKEN_URL, data=data)
        with urllib.request.urlopen(req, timeout=30) as r:
            fresh = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            code = json.loads(body).get("error", "")
        except json.JSONDecodeError:
            code = ""
        # invalid_grant is Google's single answer for expired / revoked /
        # password-changed. It is the 7-day testing-mode expiry in practice.
        if code == "invalid_grant" or "invalid_grant" in body:
            return {"status": "expired_refresh",
                    "refresh_token_age_days": _age_days(tok),
                    "detail": "Google returned invalid_grant"}
        # Anything else is a *client* problem, not a token problem, and has a
        # completely different fix. Name Google's own code — never the body,
        # which can echo request parameters.
        return {"status": "error", "oauth_error": code or f"http_{e.code}",
                "detail": f"Google returned '{code or e.code}' when refreshing"}
    except Exception as e:                     # network, DNS, timeout
        return {"status": "error", "detail": f"{type(e).__name__} refreshing token"}

    tok["access_token"] = fresh["access_token"]
    tok["expires_at"] = time.time() + int(fresh.get("expires_in", 3600))
    tok["last_refreshed"] = time.time()
    safe_write(TOKEN_FILE, tok)
    return {"status": "ok", "access_token": tok["access_token"],
            "obtained_at": tok.get("obtained_at"),
            "scopes": tok.get("scopes") or [],
            "refresh_token_age_days": _age_days(tok)}


def _age_days(tok: dict) -> float | None:
    got = tok.get("obtained_at")
    return round((time.time() - got) / 86400, 1) if got else None


def store(access_token: str, refresh_token: str, expires_in: int,
          scopes: list[str]) -> Path:
    safe_write(TOKEN_FILE, {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + int(expires_in),
        "obtained_at": time.time(),
        "scopes": scopes,
        "note": "Never commit. .secrets/ is gitignored as a whole directory.",
    })
    return TOKEN_FILE


# ------------------------------------------------------------------ channel

def channel(access_token: str) -> dict:
    """Which channel did this token actually authorise?

    The single most valuable call in this module. Authorising the wrong Google
    account is the most common way this goes wrong and is otherwise completely
    silent — the upload succeeds, onto somebody else's channel.
    """
    q = urllib.parse.urlencode({"part": "snippet,contentDetails,statistics",
                                "mine": "true"})
    req = urllib.request.Request(f"{CHANNELS_URL}?{q}",
                                 headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False,
                "detail": f"HTTP {e.code} from channels.list"}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__} from channels.list"}

    items = data.get("items") or []
    if not items:
        return {"ok": False,
                "detail": "the authorised Google account has no YouTube channel"}
    sn = items[0]["snippet"]
    handle = sn.get("customUrl") or ""
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    return {"ok": True, "id": items[0]["id"], "title": sn.get("title"),
            "handle": handle,
            "subscribers": items[0].get("statistics", {}).get("subscriberCount"),
            "videos": items[0].get("statistics", {}).get("videoCount"),
            "matches_expected": handle.lower() == EXPECTED_HANDLE.lower()}


# ------------------------------------------------------------------ messages

def stop_message(status: str, extra: str = "") -> str:
    """The exact words a blocked lane says. One place, so they never diverge."""
    m = {
        "no_client": (
            f"No OAuth client at {CLIENT_FILE}.\n"
            f"  1. console.cloud.google.com → your project → APIs & Services\n"
            f"  2. Enable 'YouTube Data API v3'\n"
            f"  3. Credentials → Create credentials → OAuth client ID\n"
            f"     → Application type: Desktop app\n"
            f"  4. Download the JSON and save it as exactly:\n"
            f"     {CLIENT_FILE}\n"
            f"  5. Run: .venv/bin/python auth/youtube_auth.py"),
        "no_token": (
            "The OAuth client is in place but consent has never been granted.\n"
            "  Run once, click Allow in the browser:\n"
            "    .venv/bin/python auth/youtube_auth.py"),
        "expired_refresh": (
            "The refresh token no longer works. This is expected, not a bug:\n"
            "  a Google Cloud project in *Testing* publishing mode issues\n"
            "  refresh tokens that expire after 7 days.\n"
            "  Fix, in order of preference:\n"
            "    a) console → APIs & Services → OAuth consent screen →\n"
            "       PUBLISH APP (moves it out of Testing; tokens stop expiring)\n"
            "    b) or re-consent weekly: .venv/bin/python auth/youtube_auth.py"),
        "error": ("Could not resolve credentials. Run this for the specific "
                  "reason and its fix:\n"
                  "    .venv/bin/python auth/check_auth.py"),
    }.get(status, f"Unknown credential status: {status}")
    return m + (f"\n  {extra}" if extra else "")


# Google's own OAuth error codes, and what each one actually means here.
OAUTH_ERRORS = {
    "invalid_client": (
        "The OAuth client is wrong or no longer exists.\n"
        "  Usually: client_secret.json is from a deleted credential, from a\n"
        "  different project, or is a Web client where a Desktop app client is\n"
        "  needed. Re-download it from console.cloud.google.com → Credentials."),
    "unauthorized_client": (
        "The client is not authorised for this grant type.\n"
        "  Create an OAuth client of type *Desktop app* and re-download it."),
    "invalid_scope": (
        "A requested scope was rejected. Enable YouTube Data API v3 on the\n"
        "  project, then re-run auth/youtube_auth.py."),
    "access_denied": (
        "Consent was declined, or the account is not a test user on a project\n"
        "  still in Testing mode. Add the account under OAuth consent screen →\n"
        "  Test users, or publish the app."),
}


def error_message(oauth_error: str | None) -> str:
    """Turn Google's terse error code into the fix it implies."""
    if not oauth_error:
        return ("No further detail was returned. Check network access, then "
                "re-run: .venv/bin/python auth/check_auth.py")
    return OAUTH_ERRORS.get(
        oauth_error,
        f"Google returned '{oauth_error}'. Re-run "
        f".venv/bin/python auth/youtube_auth.py to re-consent.")
