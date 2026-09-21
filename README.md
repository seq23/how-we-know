# How We Know

Production system for the **How We Know** YouTube channel — `@howweknowdeep`.

An evidence-first explainer channel — deep sea (Sunday, Tuesday) and materials
and manufacturing (Monday, Friday). Every on-screen figure traces to a named
public source, and the visual pipeline is built so that it *cannot* display a
value that is not present in the sourced script.

## Layout

| Path | Contents |
|---|---|
| `scripts/` | 38 narration scripts, two domains, annotated with `{{visual}}` directives |
| `visuals/` | The render engine — see below |
| `pov/` | Owner POV bank (98 lines), per-video assignments, approved topic taxonomy |
| `research/` | Topic miner and the mined/filtered backlog |
| `channel/` | Trailer script and channel brand assets |
| `voice/` | Voice reference audio (**gitignored** — back up separately) |
| `renders/` | Output video (**gitignored** — regenerable) |
| `source/` | Original interview answers and baseline archive |

## The render engine

```
script.md  ──▶  planner.py  ──▶  plan.json  ──▶  assemble.py  ──▶  video.mp4
                    │                                  │
              CONTRACT.md                      segments.py
              (visual directives)              segments_ext.py
                                               design.py
```

- **`design.py`** — palette, type, ocean zones, easing. Change identity here, nowhere else.
- **`segments.py` / `segments_ext.py`** — 13 segment renderers, ~7 ms/frame at 1080p.
- **`planner.py`** — script → visual plan. Directive → heading → heuristic priority.
- **`assemble.py`** — plan + narration audio → MP4. **Audio is the timing authority.**
- **`brand.py`** — channel avatar, banner, watermark.

## Rules this system enforces

1. **Never display an unsourced value.** If a directive needs a number the script
   does not state, the planner falls back rather than inventing one.
2. **Malformed directives degrade safely** — they are ignored, never rendered wrong.
3. **No visual treatment persists past 2 consecutive beats** (`destagnate`).
4. **Audio timing wins.** Visuals are cut to measured narration length, so picture
   and voice cannot drift.

## Run

```bash
python visuals/planner.py scripts/10-*.md plan.json
python visuals/assemble.py plan.json renders/out.mp4 --audio-dir audio/10/
```
