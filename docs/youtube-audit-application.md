# YouTube API Services — Compliance Audit Application (ready to file)

**Form:** <https://support.google.com/youtube/contact/yt_api_form>
**Prepared:** 2026-08-30
**Purpose of this document:** every field of the live form, in order, with the answer already written. Work down it linearly and paste. Name and address are filled in. **Two items are marked `[OWNER DECISION]`** — the contact email and the demo-account credentials. Nothing else needs thought.

**Before you start, two blockers:**

1. `https://howweknowdeep.com/terms/` returned **404** when this document was written. The form has a **required** Terms of Service evidence upload. Do not file until that page is live.
2. The channel currently has **0 videos**. See [§ Timing](#timing-when-to-actually-file) — filing after 3–4 public videos exist is a materially stronger application than filing today.

---

## Section 1 — Request Type

### "Select the reason for your request" (required)

Two options only:

| Option | Fits her situation? |
|---|---|
| Complete a compliance audit to request for additional quota | No — she is requesting **no** additional quota |
| Complete a compliance audit to keep current quota (requested to complete re-audit) | No — she has never been audited, and nobody has *requested* a re-audit |

**Neither option describes the actual situation**, which is: videos uploaded through `videos.insert` from an unaudited project are **locked to private** and cannot be made public ([YouTube Help: Videos locked as private](https://support.google.com/youtube/answer/7300965)). The audit is the only way to lift that lock. The dropdown was written for the quota use case and never updated for the upload-lock use case.

**Recommendation: select the first option — "Complete a compliance audit to request for additional quota."**

Reasoning:

- It is the option that routes to a **first-time audit** queue. The second option ("requested to complete re-audit") asserts something untrue — that YouTube asked her to re-audit — and a reviewer can check that in seconds. A false statement on the first field is the worst possible opening.
- The quota field later in the form lets her select **"No change / Default quota (10k quota points)"**, which resolves the mismatch honestly and on the record. The dropdown says what queue she is in; the quota radio says what she is asking for.
- She then states the real reason explicitly in the narrative field (already drafted below), so no reviewer can say she misrepresented her purpose.

---

## Section 2 — Organization and Contact Information

| Field | Answer |
|---|---|
| **Are you applying:** (required) | **As an individual user** |
| **Your Full Legal Name** (required) | `Sequoia L. Taylor` |
| **Your Organization's Legal Name** (required) | `self` — the form's helper text explicitly says: *"If applying as an individual please write 'self'."* Do **not** enter a company name. |
| **Parent Company Name (if applicable)** | `self` |
| **Your Organization's Primary Website** (required) | `https://howweknowdeep.com` |
| **Country** (required) | `United States` |
| **Street Address** (required) | `[OWNER SUPPLIES AT FILING]` — the postal address is never stored in this repo |
| **City** (required) | `[OWNER SUPPLIES AT FILING]` |
| **State/Province** (required) | `[OWNER SUPPLIES AT FILING]` |
| **Postal Code** (required) | `[OWNER SUPPLIES AT FILING]` |
| **Category** (required) | **Education and E-Learning** |
| **Organization Size / Type** (required) | **Independent Developer/Sole Proprietor** |

**On Category.** The dropdown also offers "Media and Entertainment" and "News and Journalism". *Education and E-Learning* is the better fit: the channel explains how things are known, it is not reporting news and not entertainment-first. It also matches the "Education & Research" use-case checkbox available later — but note the deliberate divergence there (see Section 5).

**On the address.** The form requires a full postal address and there is no way to file without one. The owner types it into the form at filing time; it is deliberately not written down here, because this repository is a public-posture codebase and a home address does not belong in one:

```
<full legal name>
<street address>
<city>, <state> <postal code>
United States
```

**No suite or apartment line was supplied.** If the form presents an Address Line 2 / Apt / Suite field, **leave it blank** — do not invent one. If the real address has a unit number, add it before submitting; correspondence about the audit may be sent there.

**Do not enter any business name, DBA, or business address on this form.** The application is filed by Sequoia L. Taylor as an independent developer. Her legal name and address are required and appropriate on a private form to Google; an association with any of her other businesses is not, and must not appear anywhere in the submission.

### Primary Contact Information

| Field | Answer |
|---|---|
| **Name** (required) | `Sequoia L. Taylor` |
| **Email** (required) | `[OWNER DECISION]` — see below |

**Email — needs her decision.** The candidate is **the channel's own Google account (the one that owns @howweknowdeep)**, the account that owns the `@howweknowdeep` channel and the `how-we-know` Google Cloud project. Arguments for using it: the reviewer will cross-check that the applicant controls the channel and the project, and an address that matches both is the cleanest possible signal. Argument against: it is a personal-looking address, though for a sole proprietor that is unremarkable and the form expects it.

**Do not use any address associated with her other businesses.** This property is kept separate from them, and putting one of those addresses on a Google record permanently links them.

If she wants a neutral address, a forwarding alias on the `howweknowdeep.com` domain (e.g. `dev@howweknowdeep.com`) is the stronger choice — it matches the website field and reads as the project's own contact — **provided** it is set up and receiving before filing. An address that bounces kills the application silently.

### Primary Technical Contact / Primary Business Contact

- Tick **"Same as Primary Contact (Name and Email)"** on **both**. She is one person; inventing a second name would be a fabrication, and inventing a role for the same name is padding.

---

## Section 3 — Business Model and Google Contacts

### "Describe your organization's work as it relates to YouTube" (required, 100–5,000 characters)

> Paste the block below verbatim. It is ~3,400 characters, well inside the limit. It states the traction position plainly rather than hiding it — see [§ On "significant independent value"](#on-significant-independent-value) for why that is the right call.

```
I am an independent developer. I operate a single YouTube channel, How We Know
(@howweknowdeep, channel ID UC5vZFZc15DIM6IrFwFgAECg), and a website at
https://howweknowdeep.com. There is no company and no team; I am the only person
involved.

How We Know is an evidence-first explainer channel. Each video answers one
question — how do we know how old the Earth is, how do we know what the core is
made of, how do we know a drug works — and the format is the point: for every
figure stated, the video shows the instrument, proxy, or observation that
produced it, and then states plainly where the evidence stops and inference
begins. Videos end at the edge of what is actually known rather than rounding
uncertainty away.

That editorial rule is enforced mechanically, not just by intention:

- Every script carries a "## Sources" section. A validator in the build pipeline
  rejects any script containing a claim that is not backed by an entry in that
  section. A script that fails the validator does not become a video.
- Visuals are generated from the script itself, so what is shown is tied to what
  is said.
- All imagery is public domain. A rights guard re-hashes every asset immediately
  before use and blocks the build if an asset does not match its recorded hash
  and provenance. This exists specifically so that nothing of uncertain rights
  reaches an upload.

What I want the API for is narrow and I want to describe it accurately rather
than overstate it. I use videos.insert to publish my own finished videos to my
own channel on a schedule, using an OAuth Desktop client that I authorise as the
channel owner. I use channels.list once per run to confirm the credentials are
bound to the correct channel before anything is uploaded, and search.list
occasionally for my own competitive research into how existing videos cover a
topic. The API replaces a manual upload step in a pipeline that is otherwise
already automated. No end users touch the client, no third party authorises
through it, and it handles no data belonging to anyone but me.

I am not requesting additional quota. My expected volume is roughly one video
per week, which is far below the default 10,000 units per day. The reason I am
filing this audit is that videos uploaded through videos.insert from an
unaudited project are locked to private and cannot be made public. The form's
reason dropdown offers only "request additional quota" or "re-audit", and
neither describes my situation, so I have selected the first and am stating the
real reason here: I need uploads from this project not to be locked to private.
I have selected "No change / Default quota" in the quota section accordingly.

On the state of the channel, plainly: as of filing it has no published videos and
no subscribers. It is new. I am not claiming an audience, revenue, partnerships,
or a team, because I have none of those. What exists today is the pipeline, the
sourcing and rights validators described above, and the scripts. I would rather
you evaluate a small, accurate application than an inflated one.
```

**If she files after publishing videos**, replace the final paragraph with the true numbers and drop the "no published videos" sentence. Do not carry the old paragraph forward unedited.

### "Who is your target audience?" (required, multiple select)

Select **General Public**. Select **nothing else** — she has no creator, brand, agency, developer, enterprise, or institutional users, and each extra box is a claim a reviewer can test.

### "How does your API Client monetize or generate revenue?" (multiple select)

Select **"Free service (we do not charge users)"**. Select nothing else.

- The client is a private upload tool. It has no users and charges nobody.
- Do **not** tick "Advertising displayed on pages that contain YouTube content." That question is about *her* pages carrying ads around embedded YouTube content, which is not the case. YouTube's own ads on her videos under the Partner Programme are not what this field is asking about — ticking it would drag her into the follow-up questions about selling ads on or within YouTube content, where the honest answer is "no", and would misdescribe the client.
- Monetisation intent: she intends to apply to the YouTube Partner Programme in due course; the channel is not monetised today. That is a channel matter, not an API Client revenue model, and does not belong in this field.

**Conditional sub-questions** (only appear if "Advertising" is ticked — with the selection above they will not appear):

| Field | Answer if it appears |
|---|---|
| Do you sell advertisements or sponsorships ON or WITHIN YouTube video content or the embedded player? | **No, ads only appear elsewhere on the page** — or **Not applicable** |
| Have you obtained prior written approval from YouTube? | Leave blank / not applicable |

### "Do you currently have a designated Google Partner Manager or YouTube Partner Manager?" (required)

**"No, I do not have a Google representative."** The representative name/email fields will not appear.

### "How did you first learn about the YouTube Data API?"

**Google Developer Documentation.**

### Content Owner ID(s)

**Leave blank.** She does not manage content through the Content Manager / CMS system.

### Google Ads Customer ID(s)

**Leave blank.** She does not manage ad campaigns on anyone's behalf through this client.

---

## Section 4 — API Client Overview and Access Information

| Field | Answer |
|---|---|
| **API Client Name** (required) | `How We Know Publisher` |
| **Does this API Client name contain the word "YouTube"?** (required) | **No, the name does not contain "YouTube"** |
| **Primary Access URL** (required) | `https://howweknowdeep.com` |
| **Privacy Policy URL** (required) | `https://howweknowdeep.com/privacy/` |
| **Terms of Service URL (Optional)** | `https://howweknowdeep.com/terms/` — **verify this returns 200 before filing** |
| **Is your API Client publicly accessible?** (required) | **No** |

**On the client name.** It must not contain "YouTube" — that is an explicit policy rule and the form asks about it directly. `How We Know Publisher` matches the channel and site, contains no Google or YouTube trademark, and describes what the thing does. If the OAuth client in Google Cloud is currently named something else, **rename it to match this exactly** before filing; a mismatch between the form and the consent screen is the kind of small inconsistency that costs a round trip.

**On "publicly accessible" = No.** This is the honest answer: it is a Desktop OAuth client she runs locally against her own channel. Nobody else can sign into it. Answering "Yes" would be false and would invite the reviewer to look for a public product that does not exist.

### Demo Account Credentials (for Review)

**All four of these fields need her attention — see the note below before filling anything in.**

| Field | Status |
|---|---|
| Demo Account Username or Email | `[OWNER DECISION — see note]` |
| Demo Account Password | `[OWNER DECISION — see note]` |
| Login URL (if different from primary URL) | Leave blank |
| Special Instructions for Access (if any) | Draft text below |

**What is being asked for, and why it is a problem here.** The form wants a working login so a reviewer can exercise the client themselves. For a normal SaaS product that is a throwaway demo account. Here there is nothing to log into: the client is a local desktop script that authenticates as the channel owner. **Supplying the credentials the reviewer would need to actually run it means handing over access to the Google account that owns the channel.** Do not do that.

The acknowledgment checkbox makes this worse, not better — it states that by providing demo credentials, **Google is not bound by any terms of service or privacy policy that would normally apply to users of that account**. That is a waiver, and it should never be signed over a real, owned account.

**Recommended handling:** leave the username and password blank, and put this in **Special Instructions for Access**:

```
This API Client is not a public or multi-user application, so there is no demo
account to provide. It is an OAuth Desktop client that I run locally and
authorise as the owner of the channel it uploads to (@howweknowdeep, channel ID
UC5vZFZc15DIM6IrFwFgAECg). The only credentials that would let a reviewer run it
are the credentials to the Google account that owns the channel, which I am not
able to share.

I have instead uploaded screenshots of the full OAuth consent flow, the
requested scopes, the revocation screen, and the upload interface. If any
further evidence would help — a screen recording of an end-to-end run, the
console output of an upload, or the source of the upload client — I will provide
it on request at the contact address above.
```

Fill in the actual contact address if she prefers to repeat it explicitly.

**Acknowledgment checkbox:** tick it only if she ends up supplying credentials. If both credential fields are blank and the form still requires the tick to submit, ticking it is harmless because no account has been handed over — but check whether the form actually blocks submission first.

---

## Section 5 — Use Cases and Quota Extension Details

### "How many project numbers are you adding?" (required)

**`1`**

### Project #1

| Field | Answer |
|---|---|
| **Google Cloud Project Number** (required) | `681552889891` |

> The field validates as numeric only. `681552889891` is the project **number**, not the project ID (`how-we-know`). Do not paste the ID.

### Use Case Category (required, multiple select)

Select **Video Uploading & Account Management** — and nothing else.

- This is the accurate primary category and it is what triggers the **Upload Interface Screenshots** conditional evidence requirement, which she can satisfy.
- Do **not** also tick "Education & Research" even though the *content* is educational. That checkbox describes the API use case, not the subject matter, and in this form it triggers a *Player / Embed* evidence requirement she cannot satisfy — she does not embed the YouTube player anywhere. Ticking a category she cannot evidence is a guaranteed follow-up or rejection.
- Do not tick "Tools for Creators" — the client is not a tool offered to other creators.

### "Does this API Client require users to sign in with their Google Account (OAuth 2.0)?" (required)

**Yes.** She signs in with her own Google Account to authorise the Desktop client. This is true and it triggers the OAuth Flow Screenshots requirement, which she can satisfy.

### Derived Metrics and Data Storage — required agreement checkbox

**Tick it.** The linked policy sections cover derived metrics, data storage limits, and refresh obligations. Her position is genuinely compliant: the client stores an OAuth refresh token for her own account and nothing else — no other user's data, no YouTube metrics stored or derived, no aggregation of channel or video data.

### "Expected API Usage Volume" (required)

**Fewer than 1,000 requests per day.**

At roughly one video per week, actual usage is a handful of requests per week. `videos.insert` costs 1,600 units; `channels.list` costs 1; `search.list` costs 100. A weekly run is well under 2,000 units — a fraction of the 10,000/day default.

### REQUIRED EVIDENCE for Project #1

See [§ Evidence checklist](#evidence-checklist) below. All uploads must be **JPEG, PNG, or PDF** — other formats are explicitly not considered.

### Quota Details — "Select the endpoints that you plan to use"

Tick exactly these three, and nothing else:

- ✅ `youtube.videos.insert`
- ✅ `youtube.channels.list`
- ✅ `youtube.search.list`

> Every ticked endpoint is a claim that she will call it. Ticking anything speculative ("might want playlists later") invites questions she has no answer for. She can file a new audit if the use case genuinely expands.

### "What is the total quota you are requesting for Project #1?" (required)

**No change / Default quota (10k quota points).**

This is the honest answer and it is the single most reviewer-friendly thing in the application: she is asking for compliance clearance, not resources. The "Total Per Day / Peak Per Min / Detailed Justification" sub-fields — including the per-endpoint ones for `search.list` and `videos.insert` — appear **only** under "Above Default quota" and should not be reached.

**If the form nevertheless demands a justification for `videos.insert` or `search.list`:**

```
No quota increase is requested. Expected volume is approximately one upload per
week: one videos.insert call (1,600 units), one channels.list call (1 unit) to
verify the credentials are bound to the correct channel before uploading, and
occasional search.list calls (100 units each) for my own research into how a
topic is already covered. Weekly consumption is well under 2,000 units against a
10,000 unit daily default. Peak per minute is one request; the client uploads a
single video and exits.
```

---

## Evidence checklist

Capture each as a **full-page** screenshot with the **browser URL bar visible** — a reviewer needs to see the domain. PNG or PDF. Name files so the reviewer does not have to guess.

### Required — Privacy Policy screenshots

**Capture from:** `https://howweknowdeep.com/privacy/`

The single most common cause of a failed audit is a privacy policy that does not contain YouTube's mandated elements. Before screenshotting, confirm the page visibly contains all of the following, and capture each in shot:

| Must be visible | Notes |
|---|---|
| A section naming **"YouTube API Services"** | Stating the client uses YouTube API Services |
| A link to the **YouTube Terms of Service** — `https://www.youtube.com/t/terms` | Must be a live link on the page |
| A link to the **Google Privacy Policy** — `https://policies.google.com/privacy` | Must be a live link on the page; this is checked specifically |
| A **data deletion** section | What data is stored, how a user requests deletion, and the commitment to act within **30 days** (the policy guide's stated window) |
| A link to Google's security settings page — `https://myaccount.google.com/permissions` | Where a user revokes the client's access |
| What data the client stores | Truthfully: an OAuth refresh token for the operator's own account, and nothing belonging to any other person |

> If any of these are missing from the live page, that is a **fix-before-filing** item, not a footnote. A policy screenshot missing the Google Privacy Policy link is the classic instant rejection.

### Required — Homepage screenshot showing the Privacy Policy link

**Capture from:** `https://howweknowdeep.com`

Must show the homepage **with the privacy policy link visible in frame** — normally the footer. If the link is below the fold, capture a full-page screenshot so both the page identity and the footer link appear in one image, or supply a two-panel image. The form's wording also asks for **YouTube branding visible**; if the homepage carries a YouTube channel link or icon, include it in the shot.

### Required — Terms of Service documentation

**Capture from:** `https://howweknowdeep.com/terms/`

⚠️ **This URL returned 404 on 2026-08-30.** Another agent is adding the page. **Do not file until it resolves.** Verify with a hard refresh in a logged-out browser before capturing.

### Conditional — OAuth flow screenshots (required, because OAuth = Yes)

Three separate captures, all from a real run:

| # | What to capture | Where from |
|---|---|---|
| 1 | **Consent screen** — showing the app name (`How We Know Publisher`) and the Google account chooser | Run the upload client and screenshot the browser consent page it opens |
| 2 | **Scopes screen** — the permissions page listing exactly what is requested | Same flow, next step. Must visibly show upload and read-only YouTube permissions |
| 3 | **Revocation** — the client's entry under third-party access, with the "Remove Access" control visible | `https://myaccount.google.com/permissions` |

The app name on the consent screen **must match** the "API Client Name" entered on the form. Check this before capturing.

### Conditional — Upload interface screenshots (required, because use case = Video Uploading)

There is no GUI here, and the reviewer needs to see *something* that shows how an upload happens. Capture:

1. **The client running an upload** — terminal output of an actual `videos.insert` run: the command invoked, the file being uploaded, and the returned video ID / success response.
2. **The result on YouTube** — YouTube Studio showing that uploaded video in the channel's content list, so the upload demonstrably lands where she says it does. Capture from `https://studio.youtube.com`.
3. Optionally, **the point in the source where `videos.insert` is called**, with the request body visible — this shows the reviewer exactly what metadata is set, which is more persuasive than a description of it.

Combine these into one PDF if the form accepts a single file per slot.

### Also worth having ready (not uploaded, but likely asked for)

- The **OAuth consent screen configuration** in Google Cloud Console — publishing status "In production", user type "External", and the two scopes listed. Capture from `https://console.cloud.google.com/auth/overview` for project `how-we-know`.
- Confirmation the scopes are exactly `youtube.upload` and `youtube.readonly` — both **sensitive**, neither **restricted**, so no separate Google security assessment applies.

---

## On "significant independent value"

The policy language is that an API Client **"must not mimic or replicate YouTube's core user experiences by recreating features or process flows unless they add significant independent value"** ([Developer Policies guide](https://developers.google.com/youtube/terms/developer-policies-guide)).

**The honest read of her position:**

- **The clause does not really bite here, and that is worth saying.** It exists to stop clients that rebuild YouTube — alternative front-ends, third-party players, replacement upload services offered to other people. Her client does none of that. It uploads her own videos to her own channel. There is no user experience being replicated because there are no users.
- **What is genuinely weak** is not the independent-value clause but the overall picture: a brand-new channel, zero videos, zero subscribers, one person, no revenue, no quota need. There is very little for a reviewer to verify, and very little consequence to them if they decline.
- **What is genuinely strong**, and is the whole case: the pipeline is real and unusually disciplined. A sourcing validator that hard-fails an unsourced claim, and a rights guard that re-hashes every asset before use, are exactly the two things that cause API-uploaded content to become YouTube's problem — unsourced claims and unlicensed imagery. She has mechanised the prevention of both. That is a truthful, checkable, specific thing to put in front of a reviewer, and it is more than most single-operator applications can say.

**What must never appear in this application:** audience numbers, subscriber growth, revenue, partnerships, clients, users, "our team", a company name, planned scale, or any framing that implies the channel is established. Not one of those exists. A reviewer who catches a single inflated claim has grounds to discard the whole submission, and an invented statement here is a false statement made to Google in her name. The application above is deliberately written to be small and true.

---

## Timing: when to actually file

**Filing today is legal, honest, and weak.** Filing after 3–4 videos are published is the same application with actual evidence behind it.

| Consideration | Today | After 3–4 videos |
|---|---|---|
| Upload interface screenshots | Contrived — a test upload of nothing | A real run producing a real published video |
| "The content exists" claim | Scripts only | Verifiable — the reviewer can watch one |
| Sourcing discipline claim | Described | Demonstrable, on the channel |
| Channel looks like | An empty shell | A working, if small, channel |

The videos can be published by hand in the meantime — that is the fallback anyway (see below), and it costs nothing but the manual upload step. **Recommendation: publish 3–4 videos by hand, then file.** If she prefers to file now, the application above is honest as written and nothing in it needs to be softened.

---

## Realistic expectations

- **Google publishes no timeline.** The official documentation says only that *"a member of the API Services team of YouTube will get in touch with you as soon as possible"* — there is no stated SLA, no target window, and no status page ([Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)).
- **Reported outcomes vary from days to months to silence.** Developers on Google's own developer forum have reported filing, cooperating with every instruction from the compliance team, and still receiving no response past their launch deadline ([Google Developer forums thread](https://discuss.google.dev/t/urgent-youtube-api-compliance-audit-no-response-after-critical-deadline-launch-in-jeopardy/191198)). Practitioner write-ups describe weeks of back-and-forth as the normal case for anything that is not filed perfectly ([singhamandeep.com, 2026](https://singhamandeep.com/youtube-data-api-quota-increase-audit/)).
- **Filing does not guarantee a reply.** There is no escalation path, no appeal against silence (the Appeals Form covers a *failed* audit, not an unanswered one), and no way to check queue position. Plan on the assumption that no answer ever arrives, and treat an answer as upside.
- **The fallback is intact and costs almost nothing.** Uploading through the YouTube web interface or app produces a normal public video with no restriction of any kind. The API saves a manual step in an otherwise automated pipeline; it is not load-bearing. Nothing about the channel's schedule needs to wait on this audit.
- **Do not re-file while waiting.** Duplicate submissions for the same project do not speed anything up. If a response asks for more evidence, answer it fully in one reply rather than in pieces.
- **Videos already uploaded via the unaudited project stay private permanently.** Per YouTube's help documentation, a video locked as private due to upload from an unverified API client **cannot be appealed** — it must be re-uploaded through a verified client or by hand ([Videos locked as private](https://support.google.com/youtube/answer/7300965)). So if any test uploads exist and are locked, do not wait on the audit to free them; re-upload them manually.

---

## Summary of what she must supply

Name and address are now supplied and filled in above. **Two decisions remain:**

| # | Field | What is needed |
|---|---|---|
| 1 | **Contact Email** | Decision: the channel's own Google account (the one that owns @howweknowdeep) (owns the channel and the Cloud project) is the candidate, or a `@howweknowdeep.com` alias set up and receiving before filing. **Never** an address tied to any of her other businesses. |
| 2 | **Demo account credentials** | Decision: recommended blank, with the drafted Special Instructions text instead. Do not hand over the account that owns the channel. |

Plus one field to check only if the form shows it:

| # | Field | What is needed |
|---|---|---|
| 3 | Address Line 2 / Apt / Suite, if present | Leave blank unless the real address has a unit number — none was supplied |

**Pre-flight before submitting:**

- [ ] `https://howweknowdeep.com/terms/` returns 200
- [ ] Privacy policy contains all six required elements listed above
- [ ] OAuth client display name in Google Cloud matches `How We Know Publisher`
- [ ] All eight evidence files captured, in PNG or PDF, with URL bars visible
- [ ] Project number entered as `681552889891`, not `how-we-know`
- [ ] Quota radio set to "No change / Default quota"
- [ ] Every narrative field re-read for anything that overstates the channel's current state
