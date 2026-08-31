#!/usr/bin/env python3
"""One-time local OAuth bootstrap. Writes a refresh-token JSON; never commit it."""
import argparse
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = ['https://www.googleapis.com/auth/youtube.upload']


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--client-secrets', required=True)
    ap.add_argument('--output', default='youtube-token.json')
    args = ap.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, SCOPE)
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    payload = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes or SCOPE),
    }
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'Wrote {args.output}. Store it as a secret; do not commit it.')


if __name__ == '__main__':
    main()
