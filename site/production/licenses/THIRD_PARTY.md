# Third-party production dependencies

- **Kokoro-82M:** selected narrator engine. Official repository and model weights are described as Apache-licensed. The model is not bundled in this repository.
- **FFmpeg:** local rendering dependency. FFmpeg is LGPL 2.1+ by default, with GPL terms applying to builds that enable GPL components. The repository does not redistribute the FFmpeg binary.
- **YouTube Data API:** optional provider integration. OAuth credentials are never committed and uploads default to dry-run/private review.
- **External footage:** no external clip is admitted merely because it is hosted by a research institution or stock library. Every external asset requires its own rights record.

The bundled thumbnails, motion loops, and ambient music beds are original project-generated assets and are recorded in `asset-rights-manifest.json`.
