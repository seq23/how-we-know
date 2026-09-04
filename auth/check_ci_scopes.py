"""Does the CI credential actually carry every scope T.SCOPES asks for?

    python3 auth/check_ci_scopes.py

CONFIRMED 2026-09-03: `loop-reach` failed with NAMED STOP
`CAPTIONS_SCOPE_MISSING` — YouTube refused `captions.list` for want of
`youtube.force-ssl`. It was not a missing consent. The owner HAD re-consented
locally (`.secrets/youtube_token.json`, granted 2026-09-03, carries
force-ssl); the repo secret `YT_OAUTH_REFRESH_TOKEN` was minted 2026-09-01,
a day before `auth/tokens.py` added force-ssl to `T.SCOPES`, and was never
updated to match.

`auth/youtube_auth.py` (~line 207) already guards exactly this — it forces a
re-prompt when the LOCAL token is missing a scope in `T.SCOPES`, because the
identical failure happened once before, 2026-08-31, with
`yt-analytics.readonly`. That guard's reach stops at the local token. It has
no way to see the CI secret, so the same bug recurred one layer out — a guard
that cannot reach what it governs, the same class that caused a real
production failure elsewhere the same day (an npm-script guard that never saw
a lane invoked through a JS runner).

This is the counterpart: it resolves credentials EXACTLY the way
`loop/upload.py:load_credentials()`'s env-var fallback does (the path CI
actually takes — there is no `.secrets/` on a runner), refreshes an access
token, and asks Google's own tokeninfo endpoint which scopes that token
actually carries — never a timestamp comparison between the secret and the
local file, which is a proxy and would have been wrong here too (dates alone
don't prove a scope was granted or was not).

`T.SCOPES` (`auth/tokens.py`) is asserted against directly, never copied into
a second list here — a second list of scopes would be the exact defect this
guards against, one level up.

Never prints the token, the refresh token, or the client secret, in any form.

Exit codes:
    0  every scope in T.SCOPES is present on the CI credential
    3  NAMED STOP — a scope is missing, or the credential could not be
       resolved/refreshed at all (never a silent pass on that)
    1  the CI secrets are not configured (nothing to check here — run this
       from a workflow that has them; see the module docstring)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tokens as T  # noqa: E402

TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"


def _load_ci_credential() -> dict | None:
    """Mirrors loop/upload.py:load_credentials()'s env-var branch exactly —
    that is the ONLY path CI takes, since there is no .secrets/ on a runner.
    Kept independent of loop/ (auth/ has no dependency on it) rather than
    imported, to avoid a cross-package import for two small dict lookups.
    """
    client_raw = os.environ.get("YT_OAUTH_CLIENT_JSON", "").strip()
    refresh = os.environ.get("YT_OAUTH_REFRESH_TOKEN", "").strip()
    if not client_raw or not refresh:
        return None
    try:
        client = json.loads(client_raw)
    except json.JSONDecodeError:
        return None
    c = client.get("installed") or client.get("web") or client
    if not c.get("client_id") or not c.get("client_secret"):
        return None
    return {"client_id": c["client_id"], "client_secret": c["client_secret"],
            "refresh_token": refresh}


def _refresh_access_token(creds: dict) -> str | None:
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(T.TOKEN_URL, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError):
        return None


def _granted_scopes(access_token: str) -> list[str] | None:
    """Ask Google which scopes this SPECIFIC access token actually carries —
    the real condition, not a proxy. Returns None if the lookup itself fails
    (never an empty list standing in for "unknown"; the caller must be able
    to tell "no scopes" apart from "could not ask").
    """
    url = f"{TOKENINFO_URL}?{urllib.parse.urlencode({'access_token': access_token})}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            info = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        return None
    scope_str = info.get("scope", "")
    return scope_str.split() if scope_str else []


def missing_scopes(granted: list[str]) -> list[str]:
    """Every scope in T.SCOPES (the single source of truth) not present in
    `granted`. Split out from main() so a test can assert against it without
    a network call — the credential-resolution and tokeninfo calls above are
    the only parts that need a real network.
    """
    granted_set = set(granted)
    return [s for s in T.SCOPES if s not in granted_set]


def main() -> int:
    creds = _load_ci_credential()
    if creds is None:
        print("check_ci_scopes: YT_OAUTH_CLIENT_JSON / YT_OAUTH_REFRESH_TOKEN "
              "are not both set in the environment — nothing to check here. "
              "This is expected on the Mac (auth/check_auth.py covers that "
              "path); it is NOT expected inside a workflow that carries "
              "these secrets.")
        return 1

    access_token = _refresh_access_token(creds)
    if access_token is None:
        print("NAMED STOP  [CI_YOUTUBE_TOKEN_REFRESH_FAILED]")
        print("  The CI refresh token (YT_OAUTH_REFRESH_TOKEN) could not be "
              "exchanged for an access token at all — it may be revoked or "
              "the client secret may be wrong. This is a harder failure than "
              "a missing scope: no scope could be checked because no token "
              "could be obtained.")
        print("  unblock: run auth/youtube_auth.py, confirm it succeeds, "
              "then update the YT_OAUTH_REFRESH_TOKEN repo secret with the "
              "new refresh token from .secrets/youtube_token.json.")
        return 3

    granted = _granted_scopes(access_token)
    if granted is None:
        print("NAMED STOP  [CI_YOUTUBE_SCOPE_CHECK_UNREACHABLE]")
        print("  Got an access token but Google's tokeninfo endpoint could "
              "not be reached to read its scopes. Treating this as a "
              "failure, not a pass — an unreachable check is not evidence "
              "the scopes are correct.")
        return 3
    if not granted:
        print("NAMED STOP  [CI_YOUTUBE_SCOPE_CHECK_EMPTY]")
        print("  Got an access token and a response from tokeninfo, but it "
              "reported zero granted scopes. That is itself wrong for any "
              "usable credential, so this fails rather than passing on an "
              "empty list.")
        return 3

    missing = missing_scopes(granted)
    print(f"check_ci_scopes: CI credential carries {len(granted)} scope(s); "
          f"checked against {len(T.SCOPES)} in auth/tokens.py:T.SCOPES")
    if missing:
        print("\nNAMED STOP  [CI_YOUTUBE_SCOPE_MISSING]")
        print(f"  The CI credential (YT_OAUTH_REFRESH_TOKEN) is missing "
              f"{len(missing)} scope(s) auth/tokens.py:T.SCOPES now requires:")
        for s in missing:
            print(f"    - {s}")
        print("  Google does not widen an existing grant — a new scope needs "
              "a new consent. This is the exact failure that produced "
              "CAPTIONS_SCOPE_MISSING on 2026-09-03: the owner re-consented "
              "locally but the CI secret was never updated to match.")
        print("  unblock: run auth/youtube_auth.py locally (it will force a "
              "re-prompt because the scope is missing), then copy the new "
              "refresh_token out of .secrets/youtube_token.json into the "
              "YT_OAUTH_REFRESH_TOKEN repo secret. Never print or commit the "
              "token itself.")
        return 3

    print("all scopes present — the CI credential matches T.SCOPES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
