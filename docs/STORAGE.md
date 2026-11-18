# Storage on the Mac: what is kept, what is deleted, what is shelved

Her rulings, 17 Nov 2026: "if its already on youtube i dont want it nor do i
need it"; "we dont have to produce videos so far in advance"; "shelve all clips
and pull them down as needed? and only keep the ones u know you will need for
the week?"; "maybe we just put clips on seq.taylor and videos on cryptoclearr".

| What | Rule | Where in code |
|---|---|---|
| **Uploaded videos** | Deleted once YouTube reports the upload `processed` and its Shorts are cut and uploaded: the master on the Mac, its R2 copy (`renders/<slug>-final.mp4`), and every spare copy (`<slug>-final.mp4.<tag>` such as `.pre-footage-only`, `.below-picture-floor`, `.work`; `renders/superseded-*/<slug>-final*`). A `<slug>-final.mp4.pruned.json` marker stays so it is never re-rendered (a remake re-plans and renders again). Never while a superseded swap is in flight. Whisper Almanac: the render, voice wavs, set-aside copies and uploaded Short files go the same way. | `loop/render_prune.py` `guard` (before every render), `loop/whisper_upload.py` `prune_confirmed` |
| **How far ahead** | No new video of a format while **7+ days** of it are finished and waiting (both channels). A hold is the note `HOLD [SUPPLY_FULL]`, never an error. | `loop/supply_gate.py` `MAX_DAYS`, `config/whisper_almanac.json` `upload.max_days_waiting` |
| **Footage clips** | A clip no render has used for 7 days moves to **`gdrive:Mac-Shelf/clips/`** (the seq.taylor Drive). Drive's size + sha256 must match before the local copy is deleted; the Drive copy is kept when a clip comes back. New harvests stay local until 7 days old. Only recorded footage clips move: never voice references, `loop/state`, manifests, `video_rights.json`, licences or stills. | `loop/shelf.py shelve`, daily from `bin/loop-backfill-daily.sh` (09:00 CT), never while a render runs |
| **Just in time** | A shelved clip stays selectable. After a video's picture is planned and before its first frame, every shelved clip it uses is pulled back (and stamped used); any read of a missing shelved clip fetches it too. | `visuals/footage.py` `prefetch` / `verify(fetch=True)`, `visuals/assemble.py`, `visuals/whisper_render.py`, `visuals/food.py` |
| **Named stops** | `SHELF_UNREACHABLE` (Drive cannot be reached: the render fails loudly, no clip is skipped or drawn instead), `SHELF_DRIVE_FULL` (never spills to another Drive), `SHELF_COPY_CORRUPT`, `SHELF_WAITS_FOR_RENDER` (a note). | `loop/shelf.py`; stop files in `loop/state/stops/<week>-clip-shelf.json` |

- **The record:** `loop/state/shelf.json` (committed by the Mac's pushes):
  `clips` = each shelved clip's remote, size, sha256 and date; `used` = each
  clip's last use by a render.
- **Pull everything back by hand** (from the runner checkout,
  `~/GitHub/.hwk-runner`):

  ```bash
  .venv/bin/python loop/shelf.py pull-all
  ```

  It also recovers clips from Drive if `shelf.json` were ever lost (any
  recorded clip on Drive whose sha256 matches its rights record).
- **See what is shelved:** `.venv/bin/python loop/shelf.py status`.
- Not-yet-uploaded renders are **not** shelved: with the 7-day cap nothing
  waits long enough to need it.
