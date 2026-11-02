# Hostile-review leftovers — behavior coverage

- Withdrawn inventory: `test_hostile_leftovers.py::test_withdrawn_inventory`
  exercises the real queue and ledger selectors with one withdrawn and one live
  row. The final verification batch also restores the old selectors temporarily
  and requires this test to fail, then restores the fix.
- Picture lengthening: `test_hostile_leftovers.py::test_picture_time_preserves_voice_and_caption_gaps`
  verifies a 900-second timeline, unchanged speech, and captions ending before
  quiet intervals. `test_lengthen.py` verifies cloud binding requests no tail
  or model for a runtime-only repair. Existing floor and stale-audio tests stay.
- Food: `test_hostile_leftovers.py::test_food_waits_for_date_even_after_render`
  covers undated, withdrawn-date and active-date states for both selectors.
- Tags reserve: `test_hostile_leftovers.py::test_tags_leave_reserve_unspent`
  exercises the real upkeep loop just below and exactly at the read/update
  budget boundary, checking requests and actual quota debited.
- Titles: `site/tests/page-title.test.mjs` covers query-first generation and
  trimming. Length observations are notes; missing metadata still fails.
- Runner: `test_runner_clone.py` parses all six plist previews and creates and
  updates a clone against a temporary local remote. It never invokes launchctl.
