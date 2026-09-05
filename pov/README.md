# POV Bank — Sequoia

Sources: `answers.txt`, POV interview 2026-08-30 (deep sea) ·
`answers-3.txt`, POV interview 2026-09-05 (eleven domains, questions in
`interview-3-broad-domains.md`).
Every line below is derived from a numbered answer the owner gave in her own words,
tightened for spoken narration. Nothing here is invented.

**Rules for use**
- One POV line per video, selected by tag match to the script topic.
- Never reuse a line within 12 videos.
- `tier: specific` lines belong to ONE domain, named in the line's `domain`
  field, and are only offered to an episode in that domain. A specific line with
  no `domain` came from the first interview and is deep sea's.
- `tier: transferable` lines express the owner's general stance and may be used in
  any evidence-based niche.
- If no tag matches, the pipeline takes a NAMED STOP. It does not invent a line.
- Source answer number is recorded on every line so any claim can be traced back.

**A new domain needs its own top-up.** `tier: specific` lines do not transfer to a domain outside deep sea
— they express opinions ABOUT deep-sea topics specifically. Before a second
domain's first publish it needs a ~20-minute POV interview of its own,
recorded in `research/proposed-taxonomy.json`'s `new_niche_requirement`.
`tier: transferable` lines can be used immediately in any evidence-based
niche without a new interview.


## Interview 3 — 2026-09-05

`interview-3-broad-domains.md` asked about **eleven domains in the order
`loop/domains.lifecycle()` would promote them**, so a niche has a voice BEFORE
it is promoted rather than after. Answers in `answers-3.txt`; 37 lines added
(16 transferable, 21 specific across eleven domains). Questions 15b, 16b and 18a
were skipped, which the interview explicitly allows.

**Two defects this exposed, both fixed in `loop/pov_match.py`:**

- `score()` zeroed every `tier: specific` line unless the SUBJECT TEXT matched a
  deep-sea vocabulary. Correct with one interview about one niche; wrong the
  moment a second domain's lines existed. Twenty-four lines were in the bank and
  unreachable. The rule is now about domains.
- The tag `evidence-limit` was used on three lines and had **no signal pattern
  at all**, so it scored zero every time. A tag with no vocabulary is a line
  that can never be selected. Every tag in the bank now has one, and
  `loop/tests/test_pov_domains.py` fails if one ever does not.

Both were invisible because the transferable fallback always answers — a dead
line looks exactly like a line that simply did not win.
