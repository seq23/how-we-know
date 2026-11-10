"""An expired wrangler login must not stop the shelf push (10 Nov 2026).

The Mac nightly had no CLOUDFLARE_API_TOKEN, wrangler fell back to her OAuth
login, the login had expired, and the stop read as R2_COMMAND_FAILED
("self-resolving") when it never would resolve. Now: the vault token is used,
and an expired login is named R2_AUTH_FAILED.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP))
for k in ("R2_LOCAL_DIR", "LOOP_DRY_RUN", "CLOUDFLARE_API_TOKEN"):
    os.environ.pop(k, None)
import r2  # noqa: E402

fails = []

# 1. an expired login is named R2_AUTH_FAILED, not the self-resolving R2_COMMAND_FAILED
with tempfile.TemporaryDirectory() as t:
    w = Path(t) / "wrangler"
    w.write_text("#!/bin/sh\necho 'Failed to fetch auth token: 400 Bad Request' >&2\nexit 1\n")
    w.chmod(w.stat().st_mode | stat.S_IEXEC)
    b = r2.WranglerBackend("acct", "bucket", None)
    b._cmd = [str(w)]
    try:
        b._run(["r2", "object", "get", "bucket/k"], tries=1)
        fails.append("expired login did not raise")
    except r2.R2Unavailable as e:
        if e.code != "R2_AUTH_FAILED":
            fails.append(f"expired login raised {e.code}, wanted R2_AUTH_FAILED")

# 2. no token in env -> the vault's token is used, even with no wrangler login
r2.has_wrangler_login = lambda: False
try:
    got = r2.require({"CLOUDFLARE_ACCOUNT_ID": "acct",
                      "R2_VAULT_TOKEN_CMD": "printf vault-token-123"})._token
    if got != "vault-token-123":
        fails.append(f"vault token not used (got {'a token' if got else got!r})")
except r2.R2Unavailable as e:
    fails.append(f"vault token not used: {e.code}")

# 3. an env token still wins
if r2.require({"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "env-tok",
               "R2_VAULT_TOKEN_CMD": "printf vault-token-123"})._token != "env-tok":
    fails.append("env token did not win over the vault")

# 4. no vault -> old behaviour (wrangler login) kept
r2.has_wrangler_login = lambda: True
if r2.require({"CLOUDFLARE_ACCOUNT_ID": "acct", "R2_VAULT_TOKEN_CMD": "exit 3"})._token is not None:
    fails.append("a failed vault read produced a token")

if fails:
    print("FAIL test_r2_expired_login_uses_vault")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_r2_expired_login_uses_vault: vault token used, expired login named R2_AUTH_FAILED")
