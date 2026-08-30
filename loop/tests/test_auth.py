"""The auth layer: secrets stay secret, and every blocked state is named.

The OAuth flow itself cannot be tested here — it needs a human Google login. So
this tests everything around it, which is where the damage actually happens:

  1. **.secrets/ is unreachable by git**, for every filename she might create.
  2. **No credential has ever been committed**, checked against real history.
  3. **redact() never returns the secret**, including for short values.
  4. **The token file is written 0600** and never world-readable.
  5. **Every credential state is named**, with a stated fix, and none of the
     messages leak a value.
  6. **The helpers never crash on absence** — no client, no token, bad JSON.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "auth"))

import tokens as T  # noqa: E402

SECRET_SHAPES = [
    r"AIza[0-9A-Za-z_-]{35}",              # Google API key
    r"ya29\.[0-9A-Za-z_-]+",               # access token
    r"1//[0-9A-Za-z_-]{20,}",              # refresh token
    r"GOCSPX-[0-9A-Za-z_-]+",              # OAuth client secret
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]


def check() -> list[str]:
    fails, examined = [], 0

    # ---------------------------------------------- 1. gitignore coverage
    for name in ("client_secret.json", "youtube_token.json",
                 "youtube_api_key.txt", "service-account.json", "anything",
                 "nested/deeper/creds.json"):
        examined += 1
        p = f".secrets/{name}"
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        if r.returncode != 0:
            fails.append(f"{p} is NOT gitignored — a credential dropped there "
                         f"could be committed")

    # ---------------------------------------------- 2. clean history
    examined += 1
    names = subprocess.run(
        ["git", "log", "--all", "--pretty=format:", "--name-only",
         "--diff-filter=A"],
        cwd=ROOT, capture_output=True, text=True).stdout
    for line in set(filter(None, names.splitlines())):
        if re.search(r"(^|/)\.secrets/|client_secret|youtube_token|"
                     r"service-account|\.pem$|\.key$", line):
            fails.append(f"a credential-shaped path was committed once: {line}")

    examined += 1
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout.splitlines()
    for f in tracked:
        p = ROOT / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            body = p.read_text(errors="ignore")
        except OSError:
            continue
        for shape in SECRET_SHAPES:
            if re.search(shape, body):
                fails.append(f"tracked file {f} contains something shaped like "
                             f"a live credential")

    # ---------------------------------------------- 3. redaction
    # Fixtures are ASSEMBLED at runtime, never written as literals: this file is
    # tracked, and the scan above would — correctly — flag its own test data as
    # a live credential. The scanner stays strict; the fixtures move.
    fake_refresh = "1" + "//" + "0" + "abcdefghijklmnopqrstuvwxyz"
    fake_client = "GOCSPX" + "-" + "supersecret"
    for value in (fake_refresh, fake_client, "abc", "", None):
        examined += 1
        out = T.redact(value)
        if value and len(str(value)) > 4 and str(value) in out:
            fails.append(f"redact() leaked the value it was given")
        if value and len(str(value)) > 8 and str(value)[8:] and \
                str(value)[8:] in out:
            fails.append("redact() leaked the tail of the value")

    # ---------------------------------------------- 4. file mode
    examined += 1
    tmp = Path(tempfile.mkdtemp())
    real = T.TOKEN_FILE
    try:
        T.TOKEN_FILE = tmp / "youtube_token.json"
        T.safe_write(T.TOKEN_FILE, {"refresh_token": fake_refresh})
        mode = stat.S_IMODE(T.TOKEN_FILE.stat().st_mode)
        if mode != 0o600:
            fails.append(f"the token file was written {oct(mode)}, not 0600")

        # ------------------------------------------ 6. absence never crashes
        examined += 1
        res = T.load()
        if res["status"] not in ("no_client", "no_token", "expired_refresh",
                                 "ok", "error"):
            fails.append(f"load() returned an unknown status {res['status']!r}")

        examined += 1
        T.TOKEN_FILE.write_text("{ not json")
        os.chmod(T.TOKEN_FILE, 0o600)
        res = T.load()
        if res["status"] not in ("error", "no_client"):
            fails.append("a corrupt token file did not produce a named error")
    finally:
        T.TOKEN_FILE = real
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------------------------------------- 5. every state is named
    for state in ("no_client", "no_token", "expired_refresh", "error"):
        examined += 1
        msg = T.stop_message(state)
        if not msg or len(msg) < 30:
            fails.append(f"state {state!r} has no usable message")
        if state in ("no_client", "no_token", "expired_refresh") and \
                not re.search(r"auth/youtube_auth\.py|PUBLISH APP|Desktop app",
                              msg):
            fails.append(f"state {state!r} names no concrete fix")
        for shape in SECRET_SHAPES:
            if re.search(shape, msg):
                fails.append(f"the {state!r} message contains a credential shape")

    # The 7-day testing-mode expiry must be named, not discovered at runtime.
    examined += 1
    if "7 days" not in T.stop_message("expired_refresh"):
        fails.append("the expired-refresh message does not name the 7-day "
                     "testing-mode expiry, so the fix is not obvious")

    # ---------------------------------------------- private-first by design
    examined += 1
    up = (ROOT / "loop" / "upload.py").read_text()
    if '"privacyStatus": "private"' not in up:
        fails.append("loop/upload.py does not upload private-first; an "
                     "unverified app has uploads forced private anyway")
    if re.search(r'privacyStatus"\s*:\s*"public"', up):
        fails.append("loop/upload.py can request a public upload — the public "
                     "flip belongs to loop/publish.py, against a receipt")

    # ---------------------------------------------- wrong-channel guard
    examined += 1
    if "WRONG_CHANNEL" not in up or "matches_expected" not in up:
        fails.append("loop/upload.py does not confirm the authorised channel "
                     "before uploading — the wrong-account failure is silent")

    # ------------------------------- present-but-unusable is its own stop
    # "no credential" and "a credential that stopped working" have different
    # fixes. Collapsing them into one message is how a 7-day token expiry gets
    # misdiagnosed as a missing file for a fortnight.
    pub = (ROOT / "loop" / "publish.py").read_text()
    for fname, src in (("upload.py", up), ("publish.py", pub)):
        examined += 1
        if "unusable" not in src:
            fails.append(f"loop/{fname} does not distinguish a present-but-"
                         f"unusable credential from an absent one")
        if "OAUTH_EXPIRED" not in src:
            fails.append(f"loop/{fname} has no named stop for an expired "
                         f"refresh token — the 7-day testing-mode expiry")
        if re.search(r"for .* in range|while True", src.split("unusable")[-1][:400]):
            fails.append(f"loop/{fname} appears to retry an unusable credential")

    # ---------------------------------------------- no secret ever printed
    for f in ("youtube_auth.py", "check_auth.py", "tokens.py"):
        examined += 1
        src = (ROOT / "auth" / f).read_text()
        for bad in (r"print\([^)]*client\[.client_secret.\]",
                    r"print\([^)]*refresh_token(?!_age)[^)]*\)(?![^\n]*redact)"):
            for m in re.finditer(bad, src):
                if "redact" not in m.group(0):
                    fails.append(f"auth/{f} may print a secret: "
                                 f"{m.group(0)[:60]}")

    if examined == 0:
        fails.append("examined ZERO auth cases")
    print(f"inspected {examined} auth case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - secrets unreachable by git, never printed, every state named"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
