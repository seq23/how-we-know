# Whisper Almanac — how the lane works

Faceless YouTube sleep channel **@whisperalmanac**, voiced by the owner's own
cloned whisper. Her rulings (spry brain, 5–6 Nov 2026) are the spec; every one
of them is enforced in code, listed here with where.

| Ruling | Where it lives |
|---|---|
| Lead lane: **sleep science** from How We Know's fact-checked scripts (deep sea, food, materials); history second | `config/whisper_almanac.json` `episodes`; sources must be uploaded How We Know episodes (`whisper_lane.fact_checked`) |
| **Plain words**: no acronyms, long numbers, units, equations, jargon strings; a topic name once, explained; facts never dumbed down | `loop/whisper_words.py` (`--self-test`), run on every script |
| A rewrite **adds no fact**: no new name or number | `whisper_words.fact_problems` |
| **2–3 hours**, slow, pauses added in code | `whisper_lane.estimate_seconds`, `config` `voice`, `lengths` |
| **Every video a distinct script**, no loops | `whisper_words.overlap` (8-word runs, at most 15%) |
| **Dim, moving footage**, How We Know footage rules (new shot ≤ 20 s, no repeat within 3 min, no subject over ~25%) | `visuals/whisper_reel.py` (`reel_problems`), footage from `visuals/footage.episode_pool` |
| Titles: benefit, trigger, moment, **real length** (rounded down, measured) | `whisper_lane.title`, `meta_problems` |
| **AI-voice line in the first 3 description lines; altered-content flag** on every upload | `whisper_lane.description`, `upload_body` (`containsSyntheticMedia`), `meta_problems` |
| Affirmations: **never a guaranteed outcome**, no proof, no health claims | `whisper_lane.affirmation_problems` |
| Her sample **stays on her Mac** (`~/.boss-os/asmr-voice/`) | `whisper_lane.find_sample`; `.gitignore` |
| **5:2 nights**, Almanac : How We Know; gates first; no sample → How We Know (a note) | `loop/night_split.py`, `bin/batch-session.sh` `phase_whisper`, `bin/food-session.sh` |
| **No new video over 14 days of supply** | `loop/supply_gate.py` (How We Know), `night_split.whisper_supply` (Almanac) |

## The machine

1. **Write** — `loop/whisper_author.py` (Actions, Wed 14:00 CT, `loop-whisper-author.yml`):
   each source script is rewritten by the $0 route (`loop/llm_router.py`), checked,
   and sent back with its named problems up to 4 times. Only a whole episode that
   passes every rule is committed to `scripts/whisper/<slug>.md`. Runway cap: two
   sleep scripts and one affirmations script waiting.
2. **Voice** — `voice/whisper_voice.py` (Chatterbox, MIT, `voice/LICENSING.md`) on the
   Mac, inside the batch's lock, one wav per paragraph, resumable night to night.
3. **Picture** — `visuals/whisper_render.py` plans the reel from the measured audio,
   checks it, renders segment by segment at 720p ≤ 900 kb/s (~1 GB per 2.25 h),
   and rewrites the kit (`channel/whisper/<slug>/kit.json`, `thumbnail.png`) with the
   measured length and chapters.
4. **Upload** — not built yet: it needs the one Allow click
   (`auth/whisper_youtube_auth.py`) and goes from the Mac straight to YouTube, so the
   ~1 GB masters never sit in R2. Nothing here uploads or publishes.

## Stops (all classified in `loop/stop_policy.json`)

- `WHISPER_SAMPLE_MISSING` / `_UNUSABLE` — owner_action, green, names the exact file.
- `WHISPER_NOTHING_TO_VOICE`, `_WINDOW_CLOSED`, `_RUNWAY_FULL`, `_SEGMENT_REFUSED`,
  `_FOOTAGE_THIN` — self-resolving notes.
- `WHISPER_SCRIPT_REFUSED`, `_VOICE_FAILED`, `_RENDER_FAILED`, `_REEL_REFUSED`,
  `_AUDIO_INCOMPLETE`, `_RENDER_SHORT`, `_EPISODES_UNPLANNED`, `_NO_SCRIPTS` — red.

## Tests

`loop/tests/test_whisper_lane.py` (rules proven negatively; every committed script
passes), `test_night_split.py`, `test_supply_gate.py`.
