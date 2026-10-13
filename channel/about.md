# Channel About text — How We Know (@howweknowdeep)

The single source of truth for the channel's public About/description text.
`loop/channel_about.py` reads the text between the markers below and pushes it
to `channels.update` (`part=brandingSettings`) verbatim — so the text has one
place it is written, not a paste into Studio nobody can diff.

Everything between the markers is pushed exactly as written, including line
breaks. Do not add markdown formatting inside the markers — YouTube's About
box is plain text.

<!-- ABOUT:START -->
How we know what we know. One question per episode, followed back along the evidence chain: who measured it, how, and what they were guessing.

Right now: {{DOMAINS}} — and more as we go.

Every figure is sourced to named public research, from NOAA, MBARI, Woods Hole and the Smithsonian to NIST, ASTM and ASM International. Uncertainty is stated, not smoothed over; when the evidence is thin, the episode says so.

New episodes every week.
<!-- ABOUT:END -->

## Provenance

- **2026-08-30** — original text, deep-sea only, set at channel launch.
- **2026-09-21** — widened. Owner approval (repo-change `rc_m32h8ze2a4hk37pc`,
  question 2, option A): the "Episodes start in the deep ocean and move
  outward…" paragraph and the single-domain sources sentence are replaced with
  the two-track paragraph and the widened sources line above. The opening
  paragraph, the Mars sentence, and the uncertainty sentences are unchanged —
  confirmed against the live text read from `channels.list` on 2026-09-21
  (`brandingSettings.channel.description`, etag `SutdhNXEysyF_lHvyZmxFZvE48Y`).
- **2026-09-21** — shortened, same day. The widened text above was 1,006
  characters against YouTube's 1,000-character cap on
  `brandingSettings.channel.description`; `channels.update` answered 400 and
  the post-land step of `rc_m32h8ze2a4hk37pc` failed. Trimmed to 953
  characters (repo-change `rc_m33avf9cd0njg79t`, owner approval, plan
  default): "the evidence it actually came from" → "the evidence it came
  from"; "Episodes run on two tracks." → "Two tracks."; the three closing
  method questions folded into one. Both domains, both day pairs, all seven
  named source bodies, the uncertainty sentences and "New episodes weekly."
  are unchanged. `loop/channel_about.py` now refuses before the request if
  the body ever exceeds 1,000 UTF-16 units or contains `<`/`>`, so a future
  edit gets a named refusal instead of a 400.
- **2026-10-13** — rewritten open-ended for three domains (owner instruction
  and refinement, 13 Oct 2026). The two-track paragraph (deep sea and
  materials, with weekday pairs that the three-niche rotation replaced) is
  gone. One line now names the channel's CURRENT domains, generated at push
  time from `{{DOMAINS}}`: `loop/channel_branding.py channel_domains()` reads
  the rotation and allocation in `loop/config.json` and each domain's display
  name from `channel/branding/branding.json`, so a new domain changes this line
  without anyone editing it. The opening now leads with "How we know what we know" and "the evidence chain", the banner's own words (owner, 13 Oct 2026). The sources sentence (same
  seven named bodies) and the uncertainty sentences are kept. Validator V51
  fails if the live description misses any channel domain.
