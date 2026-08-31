# How We Know — companion site

Companion reference site for the **How We Know** YouTube channel
([@howweknowdeep](https://youtube.com/@howweknowdeep)).

Staging: <https://staging.how-we-know.pages.dev>

No production domain has been chosen. Canonical URLs point at the Pages origin
until the owner picks one.

## What this is

A question-shaped reference library. The atomic unit is a **question page**: what a
person searches, what a video answers, and what an LLM cites. Everything else —
subjects, methods, zones, creatures, the depth explorer — is navigation over that set.

- 20 canonical question pages, each paired 1:1 with a production script
- 5 ocean zones, 11 creature records, an interactive Challenger Deep explorer
- Every question page carries a `subject` and a `method` (see below)
- Machine-readable surfaces: `sitemap.xml`, `robots.txt`, `llms.txt`
- A no-login `/admin` operations page, excluded from discovery

## The two axes

Every question record carries two orthogonal first-class fields, defined in
`src/lib/taxonomy.ts` and enforced by `scripts/validate-taxonomy.mjs`:

- **`subject`** — how a reader browses (`deep-sea`, `marine-geology`, …). The
  vocabulary mirrors the admitted domains in `pov/topic-taxonomy.json`.
- **`method`** — how the answer is known (`measured-by-instrument`,
  `inferred-from-proxy`, `observed-once`, `dated-by-decay`,
  `reconstructed-from-fragments`). This is the axis that links pages *across*
  subjects and drives `/methods`.

A subject or method appears in navigation only once a published page carries it.
The vocabulary constrains the field; it is never a set of empty shelves.

URLs are deliberately **not** subject-rooted. `/questions/<slug>` survives adding a
subject; `/deep-sea/<slug>` would force a migration and break every inbound link.

## Scale components

`src/lib/scale.ts` is a unit-agnostic magnitude axis — bands, landmarks, markers,
formatting and lookup. The depth explorer is one configured instance of it
(`oceanDepthAxis` in `src/lib/explorer.ts`). A future axis supplies its own unit
and range rather than a rewrite.

## Sourcing rules

- Every figure traces to a named public source (NOAA, MBARI, Woods Hole,
  Smithsonian, Te Papa, peer-reviewed records) via `content/sources.json`.
- Where a page and its production script disagree, **the script wins**.
- An unsupported claim is removed rather than given a citation.

## Commands

```bash
npm install
npm run generate     # admin snapshot + sitemap/robots/llms.txt
npm run validate     # 12 structural validators
npm test             # 13 contract tests
npm run typecheck    # tsc --noEmit
npm run build        # all of the above, then vite build + prerender
```

`npm run build` runs the whole gate and prerenders all 50 routes to
`.output/public`.

## Launch switches — `site-flags.json`

All launch gating lives in **one file**, `site-flags.json`, read by both the app and
the node generators. Do not hardcode any of these anywhere else; a validator
(`scripts/validate-launch-flags.mjs`) fails the build if you do.

| Flag | Now | What it controls |
|---|---|---|
| `searchIndexingEnabled` | `false` | **The noindex switch.** `false` emits `<meta name="robots" content="noindex,follow">` on every page *and* serves `robots.txt` with `Disallow: /`. Flip to `true`, `npm run build`, redeploy. That is the whole operation. |
| `canonicalOrigin` | `https://how-we-know.pages.dev` | Absolute origin used by every canonical tag, OG URL, sitemap entry and `llms.txt` line. Change this one value if a custom domain is ever chosen. |
| `customDomainLive` | `false` | Activates `www → apex` and `*.pages.dev → apex` 301s in `public/_redirects`. Only relevant once a custom domain exists; `false` while the site serves from `*.pages.dev`. |
| `webAnalyticsToken` | `""` | Cloudflare Web Analytics beacon token (cookieless, no consent banner). Empty means no beacon is emitted. Paste the token from Cloudflare dash → Web Analytics. |

The validator proves the HTML meta tag and `robots.txt` can never disagree, and
that every sitemap URL is on the canonical apex.

## Choosing a domain later

No custom domain is attached, and none should be attached without the owner's
direct instruction. When a domain is chosen, the only change needed is
`canonicalOrigin` in `site-flags.json` — every canonical tag, OG URL, sitemap
entry and `llms.txt` line derives from it. Then:

```bash
npx wrangler pages domain add <domain> --project-name how-we-know
# set canonicalOrigin, and customDomainLive: true, in site-flags.json
npm run build
npx wrangler pages deploy .output/public --project-name how-we-know --branch staging
```

## Deploying

Staging is a Cloudflare Pages **preview** deployment on the `staging` branch of
the `how-we-know` project. No custom domain is attached.

```bash
npm run build
npx wrangler pages deploy .output/public \
  --project-name how-we-know --branch staging
```

`wrangler.jsonc` additionally describes the app as a Worker with static assets
(`npm run deploy`), which is the alternative target if server-side rendering is
ever needed for a non-prerendered route.

## Truth boundary

The owner has not certified that the first-person observations in the scripts are
personally true. No script is marked human-approved, and no final-master
watch-through is claimed. The repository contains no fabricated voice output,
YouTube IDs, upload receipts, or public-video claims. Video records stay dormant
until a video is confirmed public.
