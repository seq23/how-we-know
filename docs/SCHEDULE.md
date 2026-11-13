# Schedule

Every scheduled GitHub Actions job in this repo. Times are Central (America/Chicago): each
`schedule:` entry carries `timezone: America/Chicago`, which GitHub Actions honours, so the clock
change in March and November no longer moves a job. Rebalanced 1 Nov 2026 (owner-approved weekly
schedule); see the notes below for what moved.

| Job | Workflow | When | Cron |
|---|---|---|---|
| site · entity backlink watch | `entity-backlink-watch.yml` | Thu 07:00 CT | `0 7 * * 4` |
| loop · daily demand + Mon 08:30 CT email | `loop-demand.yml` | every day 08:30 CT | `30 8 * * *` |
| loop · Mon+Thu 14:00 CT · food author (next food episode, $0) | `loop-food-author.yml` | Mon + Thu 14:00 CT | `0 14 * * 1,4` |
| loop · daily 14:00 CT · whisper almanac author (sleep, teaching and affirmation scripts, $0) | `loop-whisper-author.yml` | daily 14:00 CT | `0 14 * * *` |
| loop · Fri 17:00 · measure | `loop-fri-measure.yml` | Fri 16:00 CT | `0 16 * * 5` |
| loop · Fri 09:00 · flip to public | `loop-fri-publish.yml` | Fri 08:00 CT | `0 8 * * 5` |
| loop · Sat 04:00 UTC · grow the rights-cleared footage pool | `loop-imagery-harvest.yml` | Fri 23:00 CT | `0 23 * * 5` |
| loop · Mon 00:00 CT · draft, validate, gate | `loop-mon-draft.yml` | Mon 00:00 CT | `0 0 * * 1` |
| loop · 1st 07:00 · monthly review | `loop-monthly-review.yml` | day 1 of every month 02:12 CT | `12 2 1 * *` |
| loop · Quarterly · refresh the candidate-niche taxonomy | `loop-quarterly-taxonomy-refresh.yml` | day 1 of months 1,4,7,10 03:00 CT | `0 3 1 1,4,7,10 *` |
| loop · daily 10:00 CT · reach (captions + localizations + tags) | `loop-reach.yml` | every day 10:00 CT | `0 10 * * *` |
| loop · daily 18:30 CT (+ 03:30 CT apply) · long-form repackage (titles + thumbnails) | `loop-repackage.yml` | every day 18:30 CT | `30 18 * * *` |
| loop · daily 18:30 CT (+ 03:30 CT apply) · long-form repackage (titles + thumbnails) | `loop-repackage.yml` | Sun, Tue–Sat 03:30 CT | `30 3 * * 0,2-6` |
| loop · Sat 06:00 · score demand ÷ competition | `loop-sat-score.yml` | Sat 05:00 CT | `0 5 * * 6` |
| loop · daily 18:00 CT · publish a Short from R2 | `loop-shorts-cloud.yml` | every day 18:00 CT | `0 18 * * *` |
| loop · Sun 12:00 · weekly digest | `loop-sun-digest.yml` | Sun 11:00 CT | `0 11 * * 0` |
| loop · Sun 06:00 · rank topics | `loop-sun-rank.yml` | Sun 05:00 CT | `0 5 * * 0` |
| loop · daily 09:00 CT · upload from R2 | `loop-upload-cloud.yml` | every day 09:00 CT | `0 9 * * *` |
| search console · daily truth, coverage and sitemap status | `search-console-daily.yml` | every day 04:40 CT | `40 4 * * *` |
| site · post-deploy live check | `site-post-deploy-check.yml` | every day 06:20 CT | `20 6 * * *` |

## Weekly windows

- **Saturday 04:00–08:00 CT is the weekly-upkeep window for every Spry Labs side business**
  (owner ruling, 1 Nov 2026): weekly maintenance, refresh and metrics jobs run there, staggered
  at least 15 minutes apart, never two in the same slot. Publishing, link checks and
  self-healing are not upkeep and keep their own days.

## Moved on 1 Nov 2026
- Site entity backlink watch: Monday → Thursday 07:00 CT.
- The video loop keeps its own order (Fri publish / measure, Sat score, Sun rank and digest, Mon draft);
  RUNBOOK.md has each lane. Its crons are now Central all year.
