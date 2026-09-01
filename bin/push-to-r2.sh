#!/usr/bin/env bash
# Shelve finished renders and thumbnails in Cloudflare R2, so the cloud upload
# lane can publish them without this Mac being awake.
#
#   bin/push-to-r2.sh                      every queued episode
#   bin/push-to-r2.sh 04-why-… 07-why-…    just these
#   bin/push-to-r2.sh --force              re-upload even if identical
#
# WHAT IT PUSHES
#   renders/<slug>-final.mp4       ->  r2://how-we-know-renders/renders/<slug>-final.mp4
#   channel/thumbnails/<slug>.jpg  ->  r2://…/thumbnails/<slug>.jpg
#
# IDEMPOTENT, AND BY CONTENT NOT BY NAME. Each object is skipped only when its
# size AND its sha256 already match the file on this disk. A re-cut episode
# keeps its slug, so skipping on the key alone would leave the old cut shelved
# and the cloud lane would publish that. Every skip prints its reason.
#
# CREDENTIALS. `wrangler` is already logged in on this Mac, so normally nothing
# is needed but CLOUDFLARE_ACCOUNT_ID — and that is not a secret. Put it in
# .env (gitignored) and this script picks it up:
#
#     CLOUDFLARE_ACCOUNT_ID=8d147e242033699dd37c6f5a451f48d2
#
# WITHOUT IT every wrangler r2 command fails with `Authentication error
# [code: 10000]`, which reads exactly like a broken token and is not — wrangler
# falls back to resolving the account through /memberships, which an R2-scoped
# token cannot read. See THE TRAP in loop/r2.py.
#
# EXIT CODES follow the loop's contract: 0 work happened, 3 a NAMED STOP, other
# a genuine failure.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

# The account id is not secret and is the single most common reason this fails,
# so default it here rather than making every caller remember. A real
# environment variable or a line in .env still wins.
export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-8d147e242033699dd37c6f5a451f48d2}"

echo "pushing to R2 as ${R2_BUCKET:-how-we-know-renders}"
echo
echo "── episodes ──────────────────────────────────────────────────────────"
"$PY" loop/r2.py push "$@"
RC=$?

# SHORTS ARE GATED ON ATTRIBUTION, HERE, ON THIS MAC.
#
# V14 (attribution) and V15 (caption crop) read the finished pixels with Apple's
# Vision framework. That does not exist on a Linux runner, so this is the last
# machine that can check them — and loop/r2.py:push_shorts() refuses to shelve
# anything that fails. Nothing unverified reaches R2, so nothing unverified can
# reach YouTube. Expect this to take a minute: it is decoding frames.
echo
echo "── shorts (V14 + V15 must pass before anything is shelved) ───────────"
"$PY" loop/r2.py push-shorts "$@"
SRC=$?
# A stop on either half is a stop. 3 (named) loses to a real failure.
if [ "$SRC" -ne 0 ] && { [ "$RC" -eq 0 ] || [ "$SRC" -ne 3 ]; }; then RC=$SRC; fi

case $RC in
  0) echo "R2 shelf is up to date." ;;
  3) echo "NAMED STOP — see the reason above." ;;
  # A mid-push failure leaves everything already shelved still shelved, and the
  # next run skips those by checksum. Re-running is always the right response.
  *) echo "push FAILED (rc=$RC). Re-run it — this is idempotent, so it resumes "
     echo "from wherever it stopped rather than re-uploading what landed." ;;
esac
exit $RC
