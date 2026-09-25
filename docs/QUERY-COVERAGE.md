# Query coverage: missing search questions (2026-09-25)

Fifteen real "how/why/what" questions in the channel's active domains were checked against every
`research/publish_order*.json` (queue, killed, unmeasured) and the scripts already written. Results:

- 9 are already QUEUED (Mariana Trench depth, what lives in the deep, colossal squid, bioluminescence, microchips,
  titanium, carbon fiber, concrete, graphene).
- 1 is COVERED by a produced script: `scripts/02-how-deep-sea-creatures-survive-pressure.md`.
- 1 was GATED OUT by `research/publish_order.py`: "why does stainless steel not rust" (killed on saturation).
- 4 are MISSING, listed below.

## Why these are listed here and not in the queue

The queue is machine-built by design. Candidates come only from mined YouTube autocomplete
(`research/broad_mined.json`), and `research/publish_order.py` gates them. Hand-adding a phrasing to a publish
order would bypass that gate, and hand-adding a seed would change the locked `docs/CHANNEL-PLAN.md`. So these
four are recorded as research input. When a domain's seed set is next reviewed, each one is a candidate seed.

| query | domain | why missing | source |
|---|---|---|---|
| how much of the ocean is unexplored | deep-sea-ocean-science | no mined candidate | https://oceanservice.noaa.gov/facts/exploration.html |
| how do we know what is at the bottom of the ocean | deep-sea-ocean-science | no mined candidate; closest queued is "what lives in the depths of the ocean" | https://en.wikipedia.org/wiki/Deep_sea |
| how do we know the age of the universe | space-astronomy (mined, not yet allocated a publish order) | domain has no publish order file yet | https://www.youtube.com/watch?v=tCn96DbBnB4 |
| how do we know how old the earth is | not in any allocated domain | no domain covers it | https://www.youtube.com/watch?v=QoS2nB6ibZ4 |
