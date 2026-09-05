#!/usr/bin/env bash
# Put one secret on the clipboard so it can be pasted into GitHub's UI.
# Nothing is printed. Values never reach the terminal, a log, or a transcript.
#
#   bin/copy-secret.sh client     -> YT_OAUTH_CLIENT_JSON
#   bin/copy-secret.sh refresh    -> YT_OAUTH_REFRESH_TOKEN
#   bin/copy-secret.sh cloudflare -> CLOUDFLARE_API_TOKEN (from $CLOUDFLARE_API_TOKEN)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
case "${1:-}" in
  client)
    f=.secrets/client_secret.json
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
    pbcopy < "$f"
    echo "clipboard: YT_OAUTH_CLIENT_JSON  ($(wc -c < "$f" | tr -d ' ') bytes from $f)" ;;
  refresh)
    f=.secrets/youtube_token.json
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
    .venv/bin/python -c "
import json,sys
v=json.load(open('$f')).get('refresh_token','')
sys.exit('no refresh_token in $f') if not v else sys.stdout.write(v)" | pbcopy
    echo "clipboard: YT_OAUTH_REFRESH_TOKEN (from $f)" ;;
  cloudflare)
    [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || { echo "CLOUDFLARE_API_TOKEN not in your environment"; exit 2; }
    printf '%s' "$CLOUDFLARE_API_TOKEN" | pbcopy
    echo "clipboard: CLOUDFLARE_API_TOKEN (from your environment)" ;;
  *) echo "usage: bin/copy-secret.sh {client|refresh|cloudflare}"; exit 2 ;;
esac
