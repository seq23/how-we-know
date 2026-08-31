# Day-0 Deployment

1. Copy `.env.example` to `.env.local` and replace the provisional Pages URL with the actual production origin.
2. Leave `VITE_GA_MEASUREMENT_ID` empty unless analytics, privacy disclosure, and any required consent controls are ready.
3. Run `npm install` to create the first lockfile from the exact package versions in `package.json`.
4. Run `npm run generate`.
5. Run `npm run validate` and `npm test`.
6. Run `npm run build`.
7. Inspect prerendered question, zone, creature, explorer, and Watch HTML.
8. Exercise the explorer by scrolling, keyboard focus, landmark buttons, range input, mobile width, and reduced-motion mode.
9. Deploy to the selected TanStack Start-compatible host.
10. Confirm `/sitemap.xml`, `/robots.txt`, `/llms.txt`, canonicals and JSON-LD on the public origin.
11. After the first real video is published, confirm the visible player, Watch card, `VideoObject`, and generated `/video-sitemap.xml` entry.

The artifact does not claim a Cloudflare binding, analytics property, YouTube credential, deployment, or provider receipt.
