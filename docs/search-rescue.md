# howweknowdeep.com — search rescue diagnosis (2026-11-02)
- CONFIRMED decline: supplied Monday audit says 1,985 → 83 impressions (−96%); these are impressions, not measured visits.
- Start date UNKNOWN: earliest repo GSC snapshot (2026-10-26, window Sep 26–Oct 24) already has only 69 query impressions; Nov 2 snapshot has 55 (Oct 3–31). Exact daily cliff and 1,985 baseline are not in repo.
- Do not reconcile 83 audit vs 55 query totals as identical metrics: windows/aggregation differ; page rows include anonymized queries.
- CONFIRMED inventory: live sitemap has 52 URLs; curl fetched all 52, all final 200, no live 4xx/5xx found (Nov 2).
- Keep 45 URLs; consolidate 3 overlapping scary/weird questions into the weird-anatomy answer and 4 duplicate creature references into their established question answers. Every removed URL gets a 301.
- CONFIRMED thin reference templates: sampled sunlight zone 180 words; anglerfish 202, vampire squid 170, barreleye 170 (whole visible page including chrome).
- CONFIRMED shared template burden: 10 live pages sampled (first 5 sitemap question articles, first 3 creature records, first 2 zones).
- Method: lowercase visible text excluding script/style; five-word shingles shared by ≥5/10 sample pages; shared percentage of each page's unique shingles.
- Question pages: 17.1%,18.8%,18.7%,19.4%,19.9%; zones:41.5%,23.9%; creatures:36.9%,44.8%,42.8%. This measures repeated text, not a Google penalty.
- CONFIRMED overlapping intent: scary, creepiest/deeper and scariest pages explain the same anatomy as weird; dumbo/frilled/colossal/yeti references repeat existing question intent with less explanation.
- SUSPECTED contribution: thin references and intent competition weaken usefulness; no evidence proves these caused Google's decline.
- CONFIRMED page-shape defects: question headings mostly statements; article visible dates lack a publisher byline; creature/zone references lack dates and FAQ; answers follow the dek rather than the H1.
- SUSPECTED contribution: these presentation gaps reduce extractable, attributable answers; Monday audit failed 4/5 pages, but is not causal proof.
- Technical checks: robots allows all crawlers; 10 sampled pages self-canonicalize to final apex slash URLs and have no noindex.
- GSC coverage Nov 2: 48 indexed, 2 discovered, 2 unknown of 52; 0 crawled-not-indexed. Submitted sitemap reports 0 errors/0 warnings, 51 submitted (older fetch).
- curl initial host checks: www and production pages.dev redirects lead to apex; host duplicate defect was repaired Oct 25, not a currently reproduced cause.
- Commit review: site imported Aug 31; canonical slash repair Aug 31; taxonomy widening Sep 21; SEO/meta/host repairs Oct 25; entity graph Oct 30; title fixes Nov 2.
- No site route/template generation spike between Sep 21 and Oct 25 in git history. Late-Oct fixes postdate already-low impressions and cannot establish the earlier cliff's cause.
- Seasonality: not supported by available daily/year-over-year data; no seasonal explanation claimed.
- Fix: shared deploy policy excludes retired routes from sitemap/prerender/navigation and folds their content/sources into surviving answers; raw video inventory remains intact.
- Fix: same policy supplies exact HTTP 301 rules (both slash forms, 14 rules, comfortably below sister site's observed Pages cutoff), middleware and client navigation.
- Fix: answer-first definitions, question H2s, visible sourced FAQ/schema, publisher/dates and one next-step box in shared templates; factual source dates remain unchanged.
- Limitation: no pre-collapse daily GSC series available; recovery can only be measured after this PR is deployed (not authorized here).

The source inventory is retained for video production; content/search-rescue.json controls publication. No search loop writes new website questions; loop/publish.py writes loop/site_feed.json only. New content generation must honor this policy.
