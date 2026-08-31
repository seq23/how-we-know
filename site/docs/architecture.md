# Architecture

## Product surfaces

1. Static/prerendered reference site.
2. Interactive surface-to-Challenger-Deep explorer.
3. Faceless YouTube production operating system.
4. Shared canonical question, evidence, video, rights, and measurement records.

## Runtime

All public editorial content is local JSON rendered through TanStack Start routes. No database, login, admin panel, form backend, or provider mutation is required. Dynamic question, zone, and creature routes plus the static explorer and Watch routes are explicitly included in the prerender page inventory.

The depth explorer server-renders its complete semantic shell and upgrades after hydration. Browser scrolling drives the live readout; the reference pages and route links remain present without JavaScript.

Analytics is disabled unless `VITE_GA_MEASUREMENT_ID` is configured. The browser classifier stores a session-level source classification and can emit a dedicated analytics event without changing the editorial runtime.

## Data ownership

- `content/questions.json`: question/article/video contract.
- `content/sources.json`: source registry.
- `content/zones.json`: depth conventions and zone facts.
- `content/creatures.json`: creature records.
- `content/traffic-sources.json`: observable traffic-source rules.
- `production/asset-rights-manifest.json`: admitted production assets.
- `production/video-queue.json`: channel sequence and state.
- `data/measurement/kpi-contract.json`: metric-separation law.
- `data/measurement/observations.json`: externally evidenced observations only.

## Static generation

`npm run generate` creates:

- the canonical sitemap;
- robots directives;
- `llms.txt`;
- a video sitemap only when at least one question has a complete published-video record.

## Failure boundaries

A missing question route, source ID, related record, traffic rule, measurement contract, or published-video field fails structural validation. An unpublished record cannot carry a video ID. A published video must preserve the exact query title and direct-answer description line. A production asset cannot be approved if commercial use is false or required credit is absent.

## Credentialless owner operations surface

`/admin` is a static owner guide, not a runtime command center. It is intentionally absent from public navigation, sitemap, and `llms.txt`, and carries `noindex, nofollow, noarchive` metadata.

The page stores only a public `owner/repository` string in browser local storage. GitHub remains the authenticated action boundary. Links open exact workflows, editable files, folders, receipts, and runbooks. The site never receives a GitHub token, YouTube token, OAuth file, or provider secret.

Readiness counters are generated into `content/admin-status.json` from committed repository artifacts. They report the deployed snapshot and never claim live workflow or provider state.
