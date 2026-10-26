# Repo Identity

Brand: How We Know

Repo: `how-we-know`

Main domain: `howweknowdeep.com`

Canonical URL: `https://howweknowdeep.com`

Channel: `@howweknowdeep` on YouTube — the site and the channel are one publication
with one editorial standard and one correction process.

Category: Evidence-first reference publication (deep ocean, and the other domains
in the channel's rotation).

Stack: TanStack Start, prerendered, on Cloudflare Pages (project `how-we-know`).
Host canonicalisation lives in `site/functions/_middleware.js`; `site/public/_redirects`
is path rules only, because Pages never reads the Host header there.

Deploys: `.github/workflows/site-check.yml` builds and validates `site/` on every
pull request that touches it, and deploys the build it proved when `main` moves.

Persistence: GitHub-native JSON and Markdown. No user accounts, no customer data.

Why this file exists: until 2026-10-25 nothing in the repository declared which
domain it serves, so `grep -ril "<domain>" ~/GitHub/*/REPO_IDENTITY.md` — the
mapping step of every audit repair run — found nothing, and the repo had to be
identified by hand each time.
