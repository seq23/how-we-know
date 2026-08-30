# YouTube authorisation

One click in a browser, once. After that the loop uploads on its own.

---

## What to do

### 1. In the Google Cloud console

Signed in as **the Gmail that owns @howweknowdeep** — this is the part that
matters, and it is the part that goes wrong silently.

| Step | Where |
|---|---|
| Create a project | console.cloud.google.com → project picker → **New project** |
| Enable the upload API | **APIs & Services → Library** → search *YouTube Data API v3* → **Enable** |
| Enable the stats API | same Library → *YouTube Analytics API* → **Enable** |
| Set up consent | **APIs & Services → OAuth consent screen** → External → fill in name and your email → Save |
| Add yourself as a tester | same screen → **Test users** → add the Gmail that owns the channel |
| Create the credential | **Credentials → Create credentials → OAuth client ID** → Application type: **Desktop app** → Create |
| Download it | the **⬇ Download JSON** button on the credential you just made |

### 2. Put the file here, with exactly this name

```
~/GitHub/how-we-know/.secrets/client_secret.json
```

An API key, if you make one, goes in `.secrets/youtube_api_key.txt` — that one
is optional and only unlocks competition scoring for topic ranking.

The whole `.secrets/` directory is gitignored, so nothing in it can be
committed even by accident.

### 3. Run this

```bash
cd ~/GitHub/how-we-know && .venv/bin/python auth/youtube_auth.py
```

A browser tab opens. Click **Allow**. Done — you never do this again.

---

## What a successful run prints

```
================================================================
  Authorised channel
================================================================
  title       : How We Know
  handle      : @howweknowdeep
  channel id  : UC…
  videos      : 0   subscribers: 0

  ✓ This is @howweknowdeep. Correct account.
```

**Read the handle.** It is the whole reason that block is printed. If it says
anything other than `@howweknowdeep`, the script tells you loudly and in
capitals — you signed in as the wrong Google account, and without that line
you would only have found out after four videos went to somebody else's
channel.

If it is wrong: revoke at [myaccount.google.com/permissions](https://myaccount.google.com/permissions),
delete `.secrets/youtube_token.json`, and run it again signed in as the right
account.

---

## Checking it later

```bash
.venv/bin/python auth/check_auth.py
```

Read-only, changes nothing, safe any time. Tells you whether the credential
works, which channel it is on, how old the refresh token is, and what the
quota costs are. The loop runs this before every upload, so a broken credential
shows up as a sentence rather than as a failed publish at two in the morning.

---

## Two Google behaviours to expect

Neither is a bug and neither needs fixing in a hurry.

**Uploads are forced to private.** An app Google has not verified cannot upload
anything public, whatever it asks for. The loop was built this way regardless —
it uploads private on Thursday, and flips to public on Friday only against a
receipt proving the upload worked. So this costs nothing.

**Refresh tokens expire after 7 days while the project is in Testing.** If you
leave the OAuth consent screen in Testing mode, you will have to re-run
`auth/youtube_auth.py` weekly. To stop that: **OAuth consent screen → PUBLISH
APP**. It stays unverified — which is fine, see above — but tokens stop
expiring.

When a token does expire the loop does not retry into a wall. It stops, names
`OAUTH_EXPIRED`, and prints those two options.

---

## If something is missing

Every failure here prints what is missing and where to put it, and exits
cleanly. There is no stack trace to decode.

| It says | It means |
|---|---|
| `NO_CLIENT` | `client_secret.json` is not in `.secrets/` yet |
| `NO_TOKEN` | the client is there; you have not clicked Allow yet |
| `EXPIRED_REFRESH` | the 7-day Testing expiry — publish the app, or re-run |
| `WRONG_CHANNEL` | you authorised the wrong Google account |
| `invalid_client` | the JSON is from a deleted credential, another project, or is a Web client instead of a Desktop app client |

---

## For reference

| File | What |
|---|---|
| `auth/youtube_auth.py` | the one-time consent flow |
| `auth/check_auth.py` | read-only status check |
| `auth/tokens.py` | shared storage and refresh; used by the loop |
| `.secrets/` | your credentials — gitignored as a whole directory |

No third-party packages are installed for any of this. The flow is stdlib only,
so nothing was added to the shared `.venv`.
