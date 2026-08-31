# Provider deployment runbook

TanStack Start produces `.output/server/index.mjs` and `.output/public`. Cloudflare Workers is the configured target; this is not a Pages `dist` upload.

Required GitHub secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Local sequence:

1. `npm ci`
2. `npm run verify`
3. `npx wrangler deploy`
4. Verify the worker URL, static assets, prerendered routes, sitemap, robots, `llms.txt`, JSON-LD, and interactive explorer.
5. Attach a custom domain only after the worker deployment is healthy.

The repository does not claim that a Cloudflare account, Worker, custom domain, analytics property, Search Console property, or YouTube channel has been created.
