# Narrator Selection Protocol

## Objective
Choose one stable narrator that can sustain 8–12 minute science videos without sounding theatrical, synthetic, rushed, or inconsistent.

## Candidate lane
1. Kokoro is the primary open-weight candidate. Its official repository describes an Apache-licensed 82M model.
2. Piper may be tested only through a currently maintained distribution and voice model with a verified license. The original `rhasspy/piper` repository was archived in 2025, so it is not the default implementation path.
3. A paid voice is not admitted until channel revenue justifies it and commercial terms are recorded.

## Test passage
Generate the same 250–350 word passage for every candidate. It must contain scientific names, meter and foot conversions, percentages, a rhetorical question, and two emotionally neutral corrections of common myths.

## Scoring
Use `narrator-scorecard.csv`. A candidate must score at least 24/30, with no score below 4 for clarity, pronunciation, or long-form consistency.

## Lock rule
After selection, lock engine, model, voice, speed, normalization, pause style, pronunciation dictionary and export settings. Do not rotate voices to solve boredom; solve pacing in the edit.
