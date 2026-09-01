#!/usr/bin/env bash
# Push the local credentials into GitHub Actions secrets. YOU run this; Claude
# does not, and never sees the values.
#
#   bin/set-github-secrets.sh              # set them
#   bin/set-github-secrets.sh --check      # say what is set, print no values
#
# Every value is read from a file already on this Mac and piped straight into
# `gh secret set`. Nothing is echoed, nothing is written to a log, nothing is
# passed as a command-line argument (which would show in `ps`).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

need_gh() { command -v gh >/dev/null || { echo "gh CLI not installed"; exit 2; }; }
need_gh
gh auth status >/dev/null 2>&1 || { echo "gh is not logged in — run: gh auth login"; exit 2; }

if [ "${1:-}" = "--check" ]; then
  echo "secrets currently set on this repo:"
  gh secret list | awk '{print "  " $1}'
  echo
  echo "needed by .github/workflows/loop-upload-cloud.yml:"
  echo "  CLOUDFLARE_API_TOKEN  YT_OAUTH_CLIENT_JSON  YT_OAUTH_REFRESH_TOKEN"
  echo "  (GITHUB_TOKEN is provided automatically — you never set it)"
  exit 0
fi

set_from_file() {   # $1 = secret name, $2 = file
  if [ ! -f "$2" ]; then echo "  SKIP $1 — $2 not found"; return; fi
  gh secret set "$1" < "$2" && echo "  set $1 (from $2)"
}
set_from_json_field() {  # $1 = secret name, $2 = file, $3 = json field
  if [ ! -f "$2" ]; then echo "  SKIP $1 — $2 not found"; return; fi
  .venv/bin/python -c "
import json,sys
v=json.load(open('$2')).get('$3','')
if not v: sys.exit('  MISSING field $3 in $2')
sys.stdout.write(v)" | gh secret set "$1" && echo "  set $1 (from $2:$3)"
}

echo "setting GitHub Actions secrets for $(gh repo view --json nameWithOwner -q .nameWithOwner)"
set_from_file        YT_OAUTH_CLIENT_JSON   .secrets/client_secret.json
set_from_json_field  YT_OAUTH_REFRESH_TOKEN .secrets/youtube_token.json refresh_token

if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
  printf '%s' "$CLOUDFLARE_API_TOKEN" | gh secret set CLOUDFLARE_API_TOKEN \
    && echo "  set CLOUDFLARE_API_TOKEN (from your environment)"
else
  echo
  echo "  CLOUDFLARE_API_TOKEN is not in your environment. Set it for one command"
  echo "  without it being saved to shell history (note the leading space):"
  echo
  echo "     export CLOUDFLARE_API_TOKEN='...' && bin/set-github-secrets.sh"
  echo
fi

echo
echo "verifying:"
gh secret list | awk '{print "  " $1}'
