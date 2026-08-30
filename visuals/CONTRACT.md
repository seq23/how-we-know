# Script → Visual Contract v1

A visual directive sits on its own line **immediately before** the paragraph it
governs. Directives are stripped before narration is synthesised, so they are
never spoken.

    {{stat: 10,935 | METRES | Deeper than Everest is tall | NOAA}}
    NOAA commonly reports Challenger Deep at approximately 10,935 meters…

## Directives

| Directive | Arguments | Renders |
|---|---|---|
| `{{stat: VALUE \| UNIT \| CAPTION \| SOURCE}}` | caption and source optional | one held number |
| `{{descent: TO_M \| LABEL}}` | | continuous fall with live counter |
| `{{compare: NAME=M \| NAME=M}}` | exactly two | above/below sea level |
| `{{zones: HIGHLIGHT}}` | zone name or blank | five-zone cross-section |
| `{{pressure: DEPTH_M}}` | | dial, atm = 1 + m/10 |
| `{{light}}` | | wavelength attenuation |
| `{{map: NAME@LON,LAT \| NAME@LON,LAT}}` | 1–3 points | world map with pins |
| `{{timeline: YEAR=LABEL \| YEAR=LABEL}}` | 2–6 events | dated timeline |
| `{{anatomy: TITLE \| LABEL@X,Y \| LABEL@X,Y}}` | x,y are 0–1 fractions | silhouette with callouts |
| `{{ladder: NAME=M \| NAME=M}}` | 2–6 items | size comparison |
| `{{quote}}` | | the owner's POV line |
| `{{text}}` | | typographic beat |
| `{{ambient}}` | | breathing room |

## Rules

1. **Never write a value that is not already stated in the narration of that
   script.** The directive labels what the prose says; it does not add facts.
2. **A section may carry several directives.** One per paragraph is normal.
3. **Unmarked paragraphs fall back to the prose heuristics** in `planner.py`.
   Markup is a priority signal, not a requirement.
4. **`{{quote}}` is reserved for the Producer POV** and is inserted automatically.
5. If a directive's arguments are malformed or its data is absent, the planner
   **ignores it and falls back** rather than rendering something wrong.
