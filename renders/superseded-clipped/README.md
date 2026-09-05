# Renders superseded by the frame-allocation fix

These four were built before 2026-09-05, when `visuals/assemble.py` rounded each
beat's duration to a whole frame independently. Over sixty-odd beats that dropped
50–90 ms of picture, and the final `-shortest` mux trimmed the tail of the last
spoken beat — V13 caught all four.

**None was uploaded.** They are kept, not deleted, so the defect stays
reproducible; the nightly batch re-renders each slug because no `-final.mp4`
exists for it any more. Delete nothing here by hand — compare a re-render
against one of these if the clipping ever returns.

| Slug | Audio | Old video | Short by |
|---|---|---|---|
| how-does-tempered-glass-shatter | 603.283s | 603.233s | −0.049s |
| how-is-damascus-steel-made | 613.317s | 613.233s | −0.084s |
| how-strong-is-graphene | 619.760s | 619.700s | −0.060s |
| what-is-carbon-fiber-made-of | 603.181s | 603.100s | −0.081s |
