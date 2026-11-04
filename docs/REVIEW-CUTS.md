# Local review cuts (3 Nov 2026)

`HWK_REVIEW_CUT=1` makes `visuals/frame_check.py` report every variety finding
instead of raising. Missing shot records, subject visibility, text and pillarbox
checks still fail. The production variety rule itself is unchanged.

From the code worktree:

```sh
HWK_REVIEW_CUT=1 /Users/sequoiataylor/GitHub/how-we-know/.venv/bin/python visuals/review_batch.py /Users/sequoiataylor/GitHub/how-we-know
```

This one-off command extracts the eight variety-failed slugs from the original
batch log. It checks each retained batch master, then remuxes its exact video
and narration packets into `renders/review-2026-11-03/<slug>-review.mp4`.
It finishes that episode's baseline H.264/AAC 360p phone copy (under 25 MB,
faststart) and appends all variety findings to `findings.txt` before starting
the next episode. Existing outputs are refused; a directory lock prevents
concurrent review batches. It never regenerates narration or changes an
approved cut. Only the worktree's free vision route is used.

With the flag enabled, assembler output is restricted to new `-review.mp4`
files in a `review-*` directory; R2 writes, upload and automated state pushes
are refused. Review paths are also refused by R2/upload after the flag is
unset. The one behavior test is `loop/tests/test_review_cut.py`, discovered
by `loop/tests/run_all.py`.
