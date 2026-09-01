# Cloud upload setup — getting the Mac out of the loop

Uploading used to need this laptop awake at 09:00. It no longer does. Finished
renders live in a Cloudflare R2 bucket, and a GitHub Actions workflow pulls the
next one every day, uploads it to YouTube as private-with-a-date, and commits
the ledger back to the repo.

Shorts work the same way, on their own evening schedule.

```
Mac    bin/push-to-r2.sh    renders + thumbnails            ->  R2
                            cut Shorts, ONLY IF V14+V15 pass ->  R2
cloud  loop-upload-cloud.yml   daily   R2 -> YouTube, private, Sun/Tue 10:00 CT
       loop-shorts-cloud.yml   daily   R2 -> YouTube, private, Mon/Wed/Fri/Sat 19:00 CT
repo   loop/state/ledger.json and shorts_ledger.json, committed back
```

---

## What the workflow needs

| Name | Kind | Where it goes | Already done? |
|---|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | **not secret** | written literally in the workflow | ✅ done — nothing to do |
| `CLOUDFLARE_API_TOKEN` | secret | repo secret | ✅ set |
| `YT_OAUTH_CLIENT_JSON` | secret | repo secret | ✅ set |
| `YT_OAUTH_REFRESH_TOKEN` | secret | repo secret | ✅ set |

Both workflows read the same four. Nothing further is needed to run either.

The two YouTube names are not invented here — they are what
`loop/config.json → credentials` declares and what `loop/upload.py` reads when
there is no `.secrets/` directory, which is every GitHub runner.

The bucket **already exists** (`how-we-know-renders`) and the whole finished
library — 16 episodes, ~918 MB of renders plus their thumbnails — is **already
shelved in it**. You do not need to create the bucket or push anything to make
the first run work.

---

## Setting all three: one script

`bin/set-github-secrets.sh` does all of it. **You run it; Claude does not, and
never sees the values.** Every value is read from a file already on this Mac and
piped straight into `gh secret set` — nothing is echoed, nothing is logged, and
nothing is passed as a command-line argument where `ps` could read it.

```bash
cd ~/GitHub/how-we-know
export CLOUDFLARE_API_TOKEN='...'      # note the LEADING SPACE, so zsh keeps it out of history
bin/set-github-secrets.sh
```

It reads `YT_OAUTH_CLIENT_JSON` from `.secrets/client_secret.json` and
`YT_OAUTH_REFRESH_TOKEN` from the `refresh_token` field of
`.secrets/youtube_token.json`, and takes `CLOUDFLARE_API_TOKEN` from your
environment.

### Check what is set, at any time

```bash
bin/set-github-secrets.sh --check
```

It lists the secret names on the repo and the names the workflows need. GitHub
will never show you a value again, and neither will this repo — that is the
point.

### If you need a NEW Cloudflare token

The existing one works and wrangler on this Mac is logged in with it. If you
ever need to replace it:

1. <https://dash.cloudflare.com> → **profile icon**, top right → **My Profile**
2. **API Tokens** → **Create Token** → scroll down → **Create Custom Token**
3. **Token name**: `how-we-know cloud upload`
4. **Permissions**, one row: `Account` · `Workers R2 Storage` · **Edit**
5. **Account Resources**: `Include` · your account
6. **TTL**: leave it. A token that expires stops the upload lane on a date
   nobody wrote down.
7. **Continue to summary** → **Create Token** → **copy it now**, it is shown once

Then re-run `bin/set-github-secrets.sh` with it exported.

> **The trap, and it will cost you twenty minutes if you hit it blind.**
> Without `CLOUDFLARE_ACCOUNT_ID` set, wrangler resolves your account through
> the `/memberships` endpoint, which an R2-scoped token cannot read. Every R2
> command then fails with `Authentication error [code: 10000]` — which reads
> exactly like a missing R2 permission and sends you off to re-issue a token
> that was never the problem. The account id is set literally in both workflows
> and defaulted in `bin/push-to-r2.sh`, so this is already handled. It is
> written down because the error message actively misleads.

> **Do the OAuth publishing-mode check once.** If the Google Cloud project is
> still in **Testing** mode, its refresh tokens expire after **seven days** — so
> the cloud lanes would work for a week and then fail every morning with
> `OAUTH_EXPIRED`. One click fixes it:
>
> console.cloud.google.com → **APIs & Services** → **OAuth consent screen** →
> **PUBLISH APP**
>
> Then `.venv/bin/python auth/youtube_auth.py` once, and re-run
> `bin/set-github-secrets.sh`. After that it stops expiring.

---

## Check the whole thing, without uploading anything

The workflow has a **dry run** that resolves R2, works out which episodes are
pending and what dates they would get, and uploads nothing.

```bash
gh workflow run loop-upload-cloud.yml -f dry_run=true
gh run watch
```

A healthy dry run prints something like:

```
  [note] shelf: r2://how-we-know-renders
  plan  Sun 11 Oct 15:00 UTC  18-why-does-black-smoker-water-not-boil
  plan  Tue 13 Oct 15:00 UTC  04-why-deep-sea-creatures-are-so-scary
  …
--- cloud-upload: OK, 4 unit(s) of work
```

**If a secret is missing the run FAILS on purpose**, opens an issue, and names
the exact variable — `R2_CREDENTIALS_MISSING: CLOUDFLARE_API_TOKEN is not set`,
or `OAUTH_MISSING`. A failed run is the notification; a green run that did
nothing would tell you nothing.

---

## The one thing left: arm the two crons

**Both workflows are disarmed.** `workflow_dispatch` works; the `schedule:`
blocks are commented out in both files. Everything up to the irreversible call
is proven — a real GitHub runner authenticated to R2, resolved the shelf,
computed the same publish slots the Mac computes, and reserved quota — but
**neither lane has yet performed a real upload**, and an unproven lane that
first tries at 14:00 UTC unattended is the wrong way to find out.

### Step 1 — one real episode, watched

```bash
gh workflow run loop-upload-cloud.yml -f limit=1
gh run watch
```

Check it in YouTube Studio: **private**, with a scheduled date, thumbnail
attached. Then confirm the workflow committed the ledger:

```bash
git pull && python3 -c "import json;d=json.load(open('loop/state/ledger.json'));print(len(d['published']),'published')"
```

### Step 2 — arm the episode cron AND unload the Mac agent, in ONE change

Never both armed, never neither. **09:00 America/Chicago IS 14:00 UTC**, so the
Mac's `com.howweknow.backfill` and the workflow's cron fire at the same instant,
each reading its own copy of the ledger — the Mac's local file and the
workflow's committed copy. Both would see the same episode as unpublished and
upload it twice.

```bash
launchctl unload ~/Library/LaunchAgents/com.howweknow.backfill.plist
rm ~/Library/LaunchAgents/com.howweknow.backfill.plist
# then uncomment the `schedule:` block in .github/workflows/loop-upload-cloud.yml
# and commit both in one go
```

### Step 3 — the same for Shorts

There is no competing Mac agent for Shorts, so this one only needs its own first
run:

```bash
gh workflow run loop-shorts-cloud.yml -f dry_run=true
gh workflow run loop-shorts-cloud.yml -f limit=1
# confirm the Short is private with a publishAt, then uncomment the
# `schedule:` block in .github/workflows/loop-shorts-cloud.yml
```

---

## Day to day, on this Mac

After a render finishes, shelve it. That is the only Mac-side step left:

```bash
bin/push-to-r2.sh
```

It is idempotent **by content**, not by name: an object is skipped only when its
size *and* its sha256 already match the file on disk, so a re-cut episode is
re-uploaded and an unchanged one is not. It prints every skip and why. If the
network drops half way, run it again — it resumes.

To see what is on the shelf:

```bash
.venv/bin/python loop/r2.py check
```

---

## Shorts

Five Shorts were cut and none were published. They are the discovery half of the
strategy — roughly 10× the views and ~3× faster subscriber growth when run
alongside long-form — so this is the highest-value thing the migration turns on.

**Their schedule is deliberately not the episode schedule.** Long-form peaks
08:00–11:00 local; Shorts peak 18:00–21:00, very nearly the inverse. A Short
posted on the episode slot lands in the worst part of its own day, so the Shorts
lane owns 19:00 Central on Mon, Wed, Fri and Sat, 4/week.

### Why cutting still happens on this Mac

V14 (attribution) reads the source credit back **off the finished pixels**, and
V15 (caption crop) OCRs the source rows the burned caption plate occupies. Both
go through Apple's **Vision** framework via `research/imagery_video.py:ocr`,
which compiles a Swift helper with `swiftc`. Neither `swiftc` nor Vision exists
on a Linux GitHub runner, and no substitute has been proven against these fonts.

Cutting in Actions would therefore mean running V14 and V15 **nowhere**. That is
not acceptable: an unrun validator is not a passing one, and shipping an
uncredited Short on a monetised channel is the one thing this pipeline may not
do.

So the cut and its verification stay here, and **`bin/push-to-r2.sh` refuses to
shelve a Short unless both validators are green.** Nothing unverified reaches
R2, so nothing unverified can reach YouTube. The scheduling — the part that
actually needed a machine awake every day — is what moved.

```bash
bin/make-shorts.sh --all      # cut rank 1 for every finished episode
bin/push-to-r2.sh             # verifies, then shelves; refuses if V14/V15 fail
```

---

## What changed on this machine

* `com.howweknow.backfill` — **still armed, on purpose, until the cloud lane has
  completed one real upload.** The two must never both be armed and never both
  be off: 09:00 America/Chicago *is* 14:00 UTC, so if the workflow's cron were
  live at the same time, both lanes would read their own copy of
  `loop/state/ledger.json`, see the same episode as unpublished, and upload it
  twice. The cron in `loop-upload-cloud.yml` is commented out for exactly that
  reason; arming it and unloading the Mac agent is **one change, in one commit**.
* `loop/upload.py`'s library fallback — **removed.** The Thursday Mac lane still
  uploads what *this week* rendered against a queue row; it no longer reaches
  into the back catalogue. It ran at 02:00 against whatever ledger was last
  pulled, which is not the ledger the cloud lane writes.
* Nothing else about rendering or the weekly cadence moved.

## Costs

R2 storage is $0.015 per GB-month and **egress is free**. The whole library is
under a gigabyte, so this is roughly **1.5 cents a month**, and the daily pull
costs nothing. Class A operations (the pushes) are $4.50 per million; a full
library push is about forty of them.
