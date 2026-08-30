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

---

# Contract v2 — method, evidence and uncertainty

Added because the narration in this series is mostly *epistemic* prose: how a
measurement is made, what a number does and does not prove, who reports what,
and how sure anyone is. v1 had no visual for any of that, so those paragraphs
fell to `{{text}}` and `{{ambient}}` — which is why informational visuals held
only 27% of runtime. These eight directives render the same sentences as
diagrams, using **only** words the narration already speaks.

Renderers live in `visuals/segments_ext2.py`. Parsing is grafted onto the
planner by `segments_ext2.install()`, which runs on import; a pipeline stage
needs `import segments_ext2` before it plans or assembles.

## Directives

| Directive | Arguments | Renders |
|---|---|---|
| `{{chain: TITLE \| STAGE \| STAGE \| >CONCLUSION}}` | 2–5 stages; `STAGE` may be `LABEL=DETAIL`; `>` line optional | instrument → signal → correction → conclusion |
| `{{uncertain: VALUE \| UNIT \| RANGE \| CONFIDENCE \| CAPTION}}` | `RANGE` is the ± half-width, or `PLUS/MINUS`; last two optional | a value drawn as a band, not a point |
| `{{sources: TITLE \| NAME=CLAIM \| NAME=CLAIM}}` | 2–4 sources | what each named source actually reports |
| `{{steps: TITLE \| STEP \| STEP \| >NOTE}}` | 2–6 steps; `STEP` may be `HEADING=DETAIL` | numbered stages of a method |
| `{{contrast: TERM \| is=X \| not=Y}}` | 1–5 of each; both sides required | what a term includes vs what it does not |
| `{{magnitude: TITLE \| UNIT \| NAME=VALUE \| NAME=VALUE}}` | 2–6 numeric values in one unit | bars on one linear scale from zero |
| `{{define: TERM \| MEANING \| BOUNDARY \| SOURCE}}` | last two optional | a term, its meaning, and its edge |
| `{{checklist: TITLE \| +MET \| -UNMET \| ?OPEN \| >NOTE}}` | 2–6 items; prefix sets the state | criteria resolved one at a time |

## Rules (these extend, and never relax, the v1 rules)

6. **Rule 1 is absolute here.** Every stage, source name, claim, bound,
   confidence level, step, boundary and criterion must appear in that script's
   own narration. These segments look authoritative, so an invented item is
   worse than no visual. If a paragraph has nothing concrete, `{{text}}` or
   `{{ambient}}` remains the correct and honest answer.
7. **`{{uncertain}}` requires a stated range.** A number with no published
   uncertainty is a `{{stat}}`, not an uncertainty bar. Do not infer a range.
8. **`{{sources}}` requires the sources to be named in the prose.** "Some
   accounts say" is not a source. Two figures from the *same* body are a
   `{{sources}}` only if the narration distinguishes them.
9. **`{{magnitude}}` needs one shared unit and a true zero.** Mixed units, or
   values the narration only implies, are disqualifying. For lengths prefer
   `{{ladder}}`, which draws a human for scale.
10. **`{{checklist}}` states are asserted by the narration**, not judged by the
    annotator: `+` only where the prose says the criterion holds, `-` only where
    it says it fails, `?` where it says it is unresolved or must be rechecked.
11. **Paragraph breaks are a visual instruction.** The planner alternates a
    directive with a typographic beat inside one paragraph, so an eight-sentence
    paragraph carrying one directive spends half its runtime on text. Splitting
    it into consecutive paragraphs — each with its own directive, the narration
    unchanged word for word — is how a section earns its visuals. Never change,
    reorder, add to, or remove narration to do this.
12. **Alternate directive types across adjacent paragraphs.** The planner never
    shows one treatment more than twice in a row and will substitute a text beat
    if you repeat one; two different informational directives in sequence both
    survive.

## The guard

`tests/test_directive_truth.py` enforces rule 6 mechanically. For every v2
directive in every script it checks that each **number** and each **proper name**
drawn on screen appears verbatim in that script's own narration, and that the
directive actually **parses and renders** — a directive the planner cannot parse
is silently ignored, so the beat looks annotated and shows nothing new. The test
hard-fails if it inspects zero directives, and treats a directive's title as an
editorial label (numbers still checked) while every later field is a claim.
