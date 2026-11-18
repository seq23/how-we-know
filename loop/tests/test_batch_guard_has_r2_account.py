"""The nightly disk guard can reach R2: bin/batch-session.sh exports
CLOUDFLARE_ACCOUNT_ID before its first render_prune call.

17 Nov 2026: the guard skipped every prune with R2_CREDENTIALS_MISSING
(the 23:00 batch never set the account id, unlike the food night), so no
uploaded render was ever freed and the night stopped at DISK_LOW.
Runs the script's own lines up to the guard in a clean env and reads the
variable back, so it fails if the export moves after the guard or goes.
"""
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
lines = (ROOT / "bin/batch-session.sh").read_text().splitlines()
guard = next(i for i, l in enumerate(lines) if "render_prune.py guard" in l)
exports = [l for l in lines[:guard] if l.startswith("export CLOUDFLARE_ACCOUNT_ID=")]
if not exports:
    sys.exit("FAIL: no CLOUDFLARE_ACCOUNT_ID export before the first render_prune guard")
env = {k: v for k, v in os.environ.items() if k != "CLOUDFLARE_ACCOUNT_ID"}
got = subprocess.run(["bash", "-c", exports[-1] + '; printf %s "$CLOUDFLARE_ACCOUNT_ID"'],
                     env=env, capture_output=True, text=True).stdout
if len(got) != 32:
    sys.exit(f"FAIL: account id resolves to {got!r}")
print("ok: batch guard has the R2 account id")
