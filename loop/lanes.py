"""THE LANE LIST: every scheduled lane of the loop, and the runner that fires it.

Validator V73 (loop/validate.py v73_every_lane_has_a_runner) holds the
repository to this list, both ways:

  * every lane here has a RUNNER that exists and is SCHEDULED - a workflow
    with an uncommented `cron:` that invokes the lane's entry, or a launchd
    agent the installer (bin/loop-install-launchd.sh) writes with a
    StartCalendarInterval/StartInterval whose command invokes the entry; on
    this Mac, that agent is also loaded;
  * every scheduled workflow and every installer agent is a lane here, so the
    list cannot fall behind what actually runs;
  * every domain the rotation gives a weekday to (loop/config.json
    cadence.rotation) has a lane that AUTHORS it and a lane that RENDERS it.

The defect class is "exists but nothing invokes it". Found 2026-10-25: food
(How We Know: Food, owner-approved 13 Oct) had its Wednesday and Saturday
rotation slots, its pipeline (visuals/food_episode.py) and its upload contract
(backfill.food_hold) - and no runner. Its episodes appeared only when a
session ran the pipeline by hand; five topics waited with nothing to make them.

`makes`: "author" (writes a script), "render" (turns a script into a shelved
video), or None (measures, publishes, reports). `domains`: the rotation
domains an author/render lane makes; None for the others.
"""
from __future__ import annotations

DEEP = "deep-sea-ocean-science"
MATS = "materials-and-manufacturing"
FOOD = "food-science"

LANES: dict[str, dict] = {
    # ---- the cloud (GitHub Actions)
    "mon-draft":        {"runner": "workflow", "file": "loop-mon-draft.yml", "entry": "loop/draft.py",
                         "makes": "author", "domains": [DEEP, MATS]},
    "food-author":      {"runner": "workflow", "file": "loop-food-author.yml",
                         "entry": "loop/food_author.py", "makes": "author", "domains": [FOOD]},
    "demand":           {"runner": "workflow", "file": "loop-demand.yml", "entry": "loop/demand.py"},
    "fri-measure":      {"runner": "workflow", "file": "loop-fri-measure.yml", "entry": "loop/measure.py"},
    "fri-publish":      {"runner": "workflow", "file": "loop-fri-publish.yml", "entry": "loop/publish.py"},
    "imagery-harvest":  {"runner": "workflow", "file": "loop-imagery-harvest.yml",
                         "entry": "loop/footage_lane.py"},
    "monthly-review":   {"runner": "workflow", "file": "loop-monthly-review.yml", "entry": "loop/monthly.py"},
    "taxonomy-refresh": {"runner": "workflow", "file": "loop-quarterly-taxonomy-refresh.yml",
                         "entry": "loop/taxonomy_refresh.py"},
    "reach":            {"runner": "workflow", "file": "loop-reach.yml", "entry": "loop/captions_lane.py"},
    "repackage":        {"runner": "workflow", "file": "loop-repackage.yml", "entry": "loop/longform_title.py"},
    "sat-score":        {"runner": "workflow", "file": "loop-sat-score.yml", "entry": "loop/score.py"},
    "shorts-cloud":     {"runner": "workflow", "file": "loop-shorts-cloud.yml", "entry": "loop/shorts_cloud.py"},
    "sun-digest":       {"runner": "workflow", "file": "loop-sun-digest.yml", "entry": "loop/digest.py"},
    "sun-rank":         {"runner": "workflow", "file": "loop-sun-rank.yml", "entry": "loop/rank.py"},
    "upload-cloud":     {"runner": "workflow", "file": "loop-upload-cloud.yml", "entry": "loop/cloud_upload.py"},
    # ---- the cloud: the website's own lanes (not episode work, so they make
    # ---- nothing; they measure the deployed site and what search engines see)
    "search-console":   {"runner": "workflow", "file": "search-console-daily.yml",
                         "entry": "site/scripts/search-console-truth.mjs"},
    "site-live-check":  {"runner": "workflow", "file": "site-post-deploy-check.yml",
                         "entry": "site/scripts/validate-live-host.mjs"},
    # ---- this Mac (launchd, bin/loop-install-launchd.sh)
    "batch":            {"runner": "launchd", "agent": "batch", "entry": "bin/batch-session.sh",
                         "makes": "render", "domains": [DEEP, MATS]},
    "batch-resume":     {"runner": "launchd", "agent": "batch-resume", "entry": "bin/batch-session.sh"},
    "nightquit":        {"runner": "launchd", "agent": "nightquit", "entry": "bin/night-quit.sh"},
    "backfill":         {"runner": "launchd", "agent": "backfill", "entry": "bin/loop-backfill-daily.sh"},
    "food":             {"runner": "launchd", "agent": "food", "entry": "bin/food-session.sh",
                         "makes": "render", "domains": [FOOD]},
    "food-resume":      {"runner": "launchd", "agent": "food-resume", "entry": "bin/food-session.sh"},
}
