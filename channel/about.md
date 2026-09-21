# Channel About text — How We Know (@howweknowdeep)

The single source of truth for the channel's public About/description text.
`loop/channel_about.py` reads the text between the markers below and pushes it
to `channels.update` (`part=brandingSettings`) verbatim — so the text has one
place it is written, not a paste into Studio nobody can diff.

Everything between the markers is pushed exactly as written, including line
breaks. Do not add markdown formatting inside the markers — YouTube's About
box is plain text.

<!-- ABOUT:START -->
How do we know what we claim to know? One question per episode, followed back
to the evidence it actually came from — sonar, specimens, and thirty seconds
of footage.

Most of the deep ocean has never been seen. We've mapped Mars better than our
own seafloor. That gap — between what gets stated as fact and what was actually
observed — is the whole subject here.

Episodes run on two tracks. Deep sea on Sundays and Tuesdays: what lives below
the last sunlight and how anyone found out. Materials and manufacturing on
Mondays and Fridays: how steel is hardened, how a silicon wafer is made, why
carbon fiber holds. Whatever the topic, the method is the same. Where did this
number come from? Who measured it? What were they able to see, and what were
they guessing?

Every figure is sourced to named public research — NOAA, MBARI, Woods Hole,
the Smithsonian, NIST, ASTM and ASM International. Uncertainty is stated, not
smoothed over. When the evidence is thin, the episode says so.

New episodes weekly.
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
