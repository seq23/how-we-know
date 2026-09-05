# Renders superseded by the runtime self-heal

Four materials episodes rendered at **8.6–9.7 minutes** against a hard
10-minute floor. `loop/extend.py` authored additional sourced narration for each
on 2026-09-05, bringing every script into the 10.2–13.8 minute band, so these
renders no longer match the scripts they came from.

**None was uploaded.** They are moved, not deleted — nothing in this repo
deletes finished work. The MP4s themselves are not committed; only this record
is. The nightly batch re-plans, narrates the beats that moved, and re-renders
each slug because no `-final.mp4` exists for it any more.

| Slug | Old render | Narration before | after | projected |
|---|---|---|---|---|
| how-do-self-healing-materials-work | 8.61 min | 1371 w | 1912 w | ~13.2 min |
| how-hot-does-a-welding-arc-get | 9.71 min | 1423 w | 1916 w | ~13.2 min |
| how-is-3d-printed-metal-made | 9.20 min | 1383 w | 1787 w | ~12.4 min |
| what-is-aerogel-made-of | 9.58 min | 1399 w | 1899 w | ~13.1 min |

Their recorded durations were dropped from `loop/state/durations.json` with
`durations.forget()` — a recorded duration outlives the render it measured, and
leaving it would have made the self-heal see the same four episodes as short
every night and extend them again.
