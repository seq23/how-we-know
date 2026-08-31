# Channel production runbook

## Batch flow

1. Select four `production-ready-unrendered` packages.
2. Recheck article sources and direct-answer lock.
3. Generate Kokoro narration and complete a human audition.
4. Render each video with the assigned original music bed and thumbnail source.
5. Review captions, chapter boundaries, credits, and altered/synthetic-content disclosure.
6. Upload initially as private using YouTube Studio or the dry-run-first upload script.
7. Review the private video on desktop and mobile.
8. Publish or schedule in YouTube Studio.
9. Run `sync_published_video.mjs` with the real public metadata.
10. Regenerate and validate the site before deployment.

## Hard gates

- No external footage enters a render without an admitted rights record.
- No public narration without human audition.
- No `VideoObject` before public video metadata is complete.
- No automatic public upload; API output defaults to private and upload code defaults to dry-run.
