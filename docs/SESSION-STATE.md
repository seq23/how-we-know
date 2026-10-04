# Where things stand — 2026-08-31, 10:07 CDT

Written so this survives a disconnect. This file plus `docs/CHANNEL-PLAN.md` is
everything needed to continue. Supersedes the 2026-08-30 18:55 version of this file.

---

## THE DECISION THAT GATES EVERYTHING

**Nothing publishes until imagery lands.** Owner decision, 2026-08-31.

**Why it cannot be deferred:** YouTube does not allow replacing a video file. A published
video can only be deleted and re-uploaded, which loses its URL, views, watch time and any
ranking earned. So "publish now, add imagery later" is not retrofitting — it is throwing
the first four videos away and starting over. The first four are also what the algorithm
uses to decide what the channel is.

**The trigger for that decision** — owner, after watching episode 1 and approving it:

> *"I would rather have more animal pictures — the descriptions are happening and we have
> no animal photos of what we are describing."*

She is right. The narration names species and the screen shows abstractions.

---

## Publish order — the ranking, no hand-picked head

An earlier hand-picked head of four was **removed** on 2026-08-31. Those four were chosen
from opportunity data before the combined score existed, and two of them ranked below
episodes further down. Owner: *"why the fuck are we not doing the top 4 by score."*

| # | Episode | Score | Voice | Imagery |
|---|---|---|---|---|
| 1 | `10-what-is-the-deepest-part-of-the-ocean` | 0.685 | not started | pending |
| 2 | `05-why-many-deep-sea-creatures-are-red` | 0.562 | not started | pending |
| 3 | `01-why-deep-sea-creatures-look-so-weird` | 0.561 | **55/55 done** | pending |
| 4 | `14-how-big-is-a-colossal-squid` | 0.557 | **29 of ~55** | **no honest image exists** |

**Only #1 is clearly ahead.** Positions 2–7 sit within ~0.04 of each other, which is
narrower than the measurement is precise — demand rests mostly on incumbent view counts,
and Trends returned NOT QUOTABLE for most of these. Read it as a ranking, not as
distinctions.

**Never generate** `11-what-is-a-dumbo-octopus`, `12-what-is-a-frilled-shark`,
`17-what-is-a-yeti-crab` — killed as saturated (18–20 of 20 competing titles already
answer them).

Authority: `research/publish_order.json`, `_status: PRODUCTION`.

---

## Running right now

**Voice** — `pid` in `voice/narrate-all.sh`, detached with `caffeinate`, resumable.
Priority list in `voice/narrate_all.py` is `01, 14, 10, 05, …`. ~2.5 min per beat,
~55 beats per episode, so **~2 hours per episode**. Three episodes outstanding ≈ 5–6 hours
from 10:07 CDT.

Resume if it dies: `cd ~/GitHub/how-we-know && ./voice/narrate-all.sh`
It skips completed beats. **Do not restart it on a whim** — check what is on disk first.

**Imagery** — an agent is building a species→image index from public-domain sources,
scoped to the four episodes above first. Not yet reported.

---

## Imagery rules — these are not negotiable

- **Public domain or CC0 only.** The channel is monetised; CC-BY is not a public-domain
  dedication. Verify live against source metadata, never a filename or caption.
- **Best source: the 1887 *Report on the Deep-Sea Fishes of H.M.S. Challenger*** —
  illustrator Robert Mintern d. 1908, PD worldwide, hundreds of species plates. Then NOAA
  (`PD-USGov-NOAA`, watch for burned-in DVR overlays), Smithsonian Open Access (CC0), BHL.
- **Credit what the image actually is** — `CHALLENGER REPORT PLATE, 1887`, never
  "photograph".
- **Some species cannot be illustrated honestly and must not be faked.**
  *Mesonychoteuthis hamiltoni* (colossal squid) was described in 1925 from stomach
  contents — no historical plate exists, every photograph is CC-BY-SA. Same for *Kiwa*
  and whale falls. **A giant squid plate captioned "colossal squid" is a lie told in
  pictures**, and on a channel called How We Know that is the worst available failure.
  Where nothing honest exists, the drawn treatment stands.

---

## The trap that nearly shipped a mute video

`assemble.py` muxes narration **only if the audio beat count exactly equals the plan
segment count**. A missing or mismatched plan does not error — **it silently produces a
video with no sound.**

Episode 1's plan did not exist (`plans/` started at 05; the first four were rendered
before plans were saved). Regenerated with:

```bash
.venv/bin/python -c "
import sys,json; sys.path.insert(0,'visuals')
import planner
p = planner.plan('scripts/01-why-deep-sea-creatures-look-so-weird.md')
json.dump(p, open('plans/01-why-deep-sea-creatures-look-so-weird.json','w'), indent=2)
print(len(p))"
```

**Check plan count against beat count before every assembly.** The planner is
deterministic, so it reproduces the plan the silent render used.

Assemble:
```bash
.venv/bin/python visuals/assemble.py \
  plans/<slug>.json renders/<slug>-with-voice.mp4 --audio-dir audio/<slug>
```

Verify audio is real, not just present:
```bash
ffmpeg -hide_banner -i <file> -af volumedetect -f null - 2>&1 | grep mean_volume
```
Episode 1 read `mean_volume: -22.9 dB`, `max_volume: -3.8 dB`.

---

## Episode 1 — approved

`renders/01-with-voice.mp4` · 7 min 44 s · 23 MB · h264 + aac · 55/55 beats, none silent
or truncated · levels flat at −22.9 dBFS.

Owner watched it and approved, with the imagery note above as the standing correction.

**It still needs imagery and a re-render before publishing.**

---

## After the four are rendered

1. **Show her one re-rendered episode.** Imagery is a real visual change and gets the same
   gate the voice did. If it is wrong, find out on one video, not four permanent ones.
2. **One API test upload set to `public`.** This settles whether uploads land locked —
   Google's docs say API uploads from an unaudited project cannot be flipped public and
   cannot be appealed, but the docs conflate two review processes and field reports are
   mixed. **Five minutes, $0, ends the question.**
3. **If it lands public:** fully automated, no audit needed.
   **If it lands locked:** she hand-publishes 4 (1–2 live, rest scheduled), and the
   compliance audit is filed when the 4th goes live — see the memory note
   `youtube-audit-after-fourth-video` and `docs/youtube-audit-application.md` (433 lines,
   paste-ready).
4. Also test whether `videos.update` works on a hand-uploaded video. If it does, the worst
   case is drag-and-drop plus fully automated metadata.

---

## Done and verified

- **howweknowdeep.com** live — apex canonical, valid cert, `noindex` until videos publish,
  soft-404 fixed.
- **YouTube OAuth** authorised to `@howweknowdeep` (channel ID `UC5vZFZc15DIM6IrFwFgAECg`),
  app **In production** so refresh tokens no longer expire. Consent-screen logo removed —
  a logo is what triggers brand verification, which is the process to **never** pursue.
- **API key** live, restricted, in `.secrets/` (gitignored, verified against full history).
- **All 20 episodes competition-scored.**
- **20/20 thumbnails**, 17 on verified public-domain imagery.
- **20/20 silent renders** — they need re-assembling with `--audio-dir` and imagery.
- **Loop built and guarded** — 2/week cadence, auto-escalation on a validated generated
  script, runway guard, retention checkpoint, locked-upload detection.
- **`docs/CHANNEL-PLAN.md`** is the locked strategy, enforced by `loop/validate_plan.py`.
- **Legal pages audit-grade**; audit application drafted.
- **sprylabs-hpc-site**: 9 PRs merged, all lanes green, CI ~34 min → **6m41s**.
- **local-guides-citation-velocity**: green. A 4-day wedge cleared — `cadence_gate.js`
  wrote its ledger from read-only jobs, so it never persisted and the comparison could
  never advance. `weekly_cap` now reports instead of blocking, per the owner: pages an
  external citation-intelligence pass says should exist ship regardless of cadence
  planning.

## Still open

- **KDP** — 7 books awaiting Amazon, 5 not created.
- **`privacyContactEmail`** empty in `site/site-flags.json`. Candidate
  the channel's own Google account (the one that owns @howweknowdeep); a `@howweknowdeep.com` alias would be better.
- `validate:retired-route-references` is 121s of the 297s sprylabs shard stage — the next
  CI lever, bigger than sharding was.

---

## Machine notes

**This Mac sleeps after 1 minute of idle and it killed two agents mid-run.** Hold all
three assertions for long jobs:

```bash
nohup caffeinate -d -i -m -s -u -t 28800 >/dev/null 2>&1 & disown
```
Verify with `pmset -g assertions | grep Prevent`. `PreventSystemSleep` is the one that
was missing.

**8 GB RAM.** The voice model needs ~2 GB resident; below that it pages and runs ~15×
slower. **One heavy job at a time.** A reboot after long uptime recovered ~2.5 GB (wired
memory had drifted to 3.6 GB over 16 days).

**`nohup … & disown` does not fully detach** — the harness reaping a background task takes
the job with it. `voice/spawn_detached.py` uses `os.setsid()` and prints pid/pgid/sess as
proof. macOS has no `setsid(1)`.

---

## Corrections I made, recorded so they are not repeated

- Reported a render as running when it had died. **Verify a process, do not assume it.**
- Diagnosed the voice slowdown as CPU-vs-GPU. It was **memory**; MPS was engaged
  throughout.
- Spawned a duplicate agent because I assumed the first had exited. **Run `ListAgents`
  before spawning.**
- Merged to `main` while a branch was open, causing an 8-conflict mess I then resolved
  wrong and reverted. **Batch the merges.**
- Told her private-then-publish was a fine fallback before learning the lock **cannot be
  appealed**.
- Leaned on `seed_hits` as demand; it measured seed-string length.
- Let a gate kill 13 of 20 episodes on autocomplete counts — a collection artefact, not
  demand. Corrected to an audience-based signal; runway went 5 → 8 weeks.
- **Preserved a hand-picked publish head after building the score that contradicted it.**
  The point of measuring is to let the measurement decide.
