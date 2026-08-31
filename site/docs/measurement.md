# Measurement Phase

## Purpose

Measure owned production and external outcomes without conflating them.

The canonical metric classes live in `data/measurement/kpi-contract.json`. Empty observations live in `data/measurement/observations.json`; an empty file is truthful because no external provider or manual observation has been connected yet.

## Optional analytics integration

Set `VITE_GA_MEASUREMENT_ID` to enable the browser analytics loader. Leave it empty to ship without analytics.

When enabled, the site records a `traffic_source_classified` event with:

- `traffic_surface`: `ai-assistant`, `organic-search`, `youtube`, `referral`, or `direct`;
- `traffic_source_detail`: the matched source rule or referring host;
- `source_identifiable`: whether the browser exposed enough evidence to classify the visit;
- referrer host and UTM fields when available.

Rules are stored in `content/traffic-sources.json`. The registry includes major assistant surfaces, search engines, and YouTube. It is an attribution aid, not proof that all AI traffic is visible.

## Attribution limitation

Browsers, apps, assistants, privacy tools, redirects, and copied links can suppress or replace the HTTP referrer. Unidentified direct traffic must remain direct/unidentifiable; it must not be reclassified as AI traffic by assumption.

## External evidence receipt

A verified citation or surfacing observation should retain:

- observation ID;
- provider or source;
- observed timestamp;
- query or prompt;
- surfaced or cited URL;
- result type;
- screenshot, export, API receipt, or other evidence location;
- reviewer;
- verification status.

No external observation is included in this artifact.
