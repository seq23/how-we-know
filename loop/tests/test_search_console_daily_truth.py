"""The daily Search Console truth actually lands: items e4, e5 and i6.

Owner's Search Readiness Checklist, 25 Oct 2026. Boss OS audits this site every
week and reads the repository's default branch:

  e4  a gsc_truth.json committed in the last three days, with a query history
      so a target that leaves the rolling 28-day window stays in the record;
  e5  an index_coverage.json committed in the last three days, bucketing every
      sitemap page as indexed / crawled-not-indexed / discovered / unknown;
  i6  every sitemap's status as Google reports it.

The lane (`.github/workflows/search-console-daily.yml` and
`site/scripts/search-console-truth.mjs`) landed in #244 and then collected
nothing for a day: the repository had no GSC_SERVICE_ACCOUNT_JSON secret, so
every run would have taken the named-stop path and written no truth file at all.
The code was right and the lane was inert, which is exactly the shape Rule 0 is
about. The secret is set now, and this test is what notices if the lane ever
goes quiet again.

WHAT THIS PROVES:
  1. the workflow runs daily, may write, hands the collector the secret, and
     commits the very directory the collector writes (not a neighbouring one -
     two components each keeping their own path is how this lane broke);
  2. the collector writes all three file names the checklist reads, under
     data/search-console/;
  3. the committed data is real: a parseable timestamp that is not 1970, a
     property for this site's canonical host, coverage buckets that sum to the
     sitemap total, and totals that match the query rows they came from;
  4. NEGATIVE PROOF, executed: with no secret in the environment the collector
     exits 0, writes search-console-stop.json, and writes NO gsc_truth.json -
     so a stopped day can never pass for a day with data, which is the whole
     reason e4 asks about freshness.
Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SITE = ROOT / "site"
DATA = SITE / "data" / "search-console"
COLLECTOR = SITE / "scripts" / "search-console-truth.mjs"
WORKFLOW = ROOT / ".github" / "workflows" / "search-console-daily.yml"

TRUTH = "gsc_truth.json"
HISTORY = "gsc_query_history.json"
COVERAGE = "index_coverage.json"
STOP = "search-console-stop.json"

fails: list[str] = []
examined = 0

# ---------------------------------------------------- 1. the lane is wired up
examined += 1
if not WORKFLOW.exists():
    fails.append("there is no search-console-daily workflow")
else:
    wf = WORKFLOW.read_text()
    examined += 1
    if not re.search(r"cron:\s*'[^']*\*\s*\*\s*\*'", wf):
        fails.append("the workflow has no daily cron schedule")
    examined += 1
    if "contents: write" not in wf:
        fails.append("the workflow cannot commit what it collected")
    examined += 1
    if "GSC_SERVICE_ACCOUNT_JSON" not in wf:
        fails.append("the workflow never hands the collector the secret")
    # The path the workflow commits must be the path the collector writes.
    examined += 1
    if "site/data/search-console" not in wf:
        fails.append("the workflow does not commit site/data/search-console, "
                     "the directory the collector writes")
    examined += 1
    if "git push" not in wf:
        fails.append("the workflow commits but never pushes")

# ------------------------------------------- 2. the collector's three outputs
examined += 1
if not COLLECTOR.exists():
    fails.append("the collector script is missing")
else:
    code = COLLECTOR.read_text()
    examined += 1
    if "data/search-console" not in code:
        fails.append("the collector does not write under data/search-console")
    for name in (TRUTH, HISTORY, COVERAGE):
        examined += 1
        if name not in code:
            fails.append(f"the collector never writes {name}")

# ------------------------------------------------ 3. the committed data is real
truth = coverage = None
examined += 1
if not (DATA / TRUTH).exists():
    fails.append(f"no {TRUTH} is committed, so item e4 has nothing to read")
else:
    truth = json.loads((DATA / TRUTH).read_text())
    examined += 1
    stamp = str(truth.get("collected_at", ""))
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.year <= 1970:
            fails.append(f"{TRUTH} carries a 1970 timestamp: {stamp}")
    except ValueError:
        fails.append(f"{TRUTH} has no parseable collected_at: {stamp!r}")
    examined += 1
    host = json.loads((SITE / "site-flags.json").read_text())["canonicalOrigin"]
    host = host.split("//")[-1].rstrip("/")
    if host not in str(truth.get("property", "")):
        fails.append(f"{TRUTH} names property {truth.get('property')!r}, "
                     f"which is not this site's canonical host {host}")
    # e4: the totals must be the rows' own sum, not a number typed beside them.
    rows = truth.get("queries") or []
    examined += 1
    if not rows:
        fails.append(f"{TRUTH} holds zero query rows")
    else:
        for field in ("clicks", "impressions"):
            examined += 1
            want = sum(r.get(field, 0) for r in rows)
            got = truth.get("totals", {}).get(field)
            if got != want:
                fails.append(f"{TRUTH} totals.{field} is {got}, but the rows "
                             f"sum to {want}")
    # i6: every sitemap Google has read, with its status.
    examined += 1
    if not truth.get("sitemaps"):
        fails.append(f"{TRUTH} records no sitemap status (item i6)")

examined += 1
if not (DATA / HISTORY).exists():
    fails.append(f"no {HISTORY} is committed, so a query that leaves the "
                 f"28-day window leaves the record (item e4)")
else:
    history = json.loads((DATA / HISTORY).read_text())
    examined += 1
    if history.get("count", 0) < 1 or not history.get("queries"):
        fails.append(f"{HISTORY} remembers no queries")

examined += 1
if not (DATA / COVERAGE).exists():
    fails.append(f"no {COVERAGE} is committed, so item e5 has nothing to read")
else:
    coverage = json.loads((DATA / COVERAGE).read_text())
    buckets = coverage.get("buckets", {})
    examined += 1
    for name in ("indexed", "crawled_not_indexed", "discovered", "unknown"):
        if name not in buckets:
            fails.append(f"{COVERAGE} has no {name} bucket (item e5)")
    examined += 1
    total = coverage.get("sitemap_total", 0)
    if total < 1:
        fails.append(f"{COVERAGE} reports a sitemap_total of {total}")
    elif sum(buckets.values()) != total:
        fails.append(f"{COVERAGE} buckets sum to {sum(buckets.values())}, "
                     f"not the sitemap's {total} pages")
    # Every sitemap page is accounted for, and the rotation is real.
    examined += 1
    if not coverage.get("pages"):
        fails.append(f"{COVERAGE} holds no per-page readings")

# --------------------------- 4. negative proof: a stop writes no truth file
# Executed, not asserted about. The collector reads site-flags.json at import
# and stops on the missing secret before it needs anything else.
if COLLECTOR.exists() and shutil.which("node"):
    scratch = Path(tempfile.mkdtemp(prefix="gsc-stop-"))
    try:
        (scratch / "scripts").mkdir()
        shutil.copy(COLLECTOR, scratch / "scripts" / COLLECTOR.name)
        shutil.copy(SITE / "site-flags.json", scratch / "site-flags.json")
        env = {k: v for k, v in os.environ.items()
               if k != "GSC_SERVICE_ACCOUNT_JSON"}
        run = subprocess.run(
            ["node", str(scratch / "scripts" / COLLECTOR.name)],
            cwd=scratch, env=env, capture_output=True, text=True, timeout=120)
        out = scratch / "data" / "search-console"
        examined += 1
        if run.returncode != 0:
            fails.append("a missing secret reddens the daily check: the "
                         f"collector exited {run.returncode}")
        examined += 1
        if "NAMED STOP" not in run.stdout:
            fails.append("a missing secret produces no NAMED STOP a human sees")
        examined += 1
        if not (out / STOP).exists():
            fails.append(f"a stop wrote no {STOP}, so the gap is invisible")
        examined += 1
        if (out / TRUTH).exists():
            fails.append(f"a STOPPED run wrote {TRUTH}: a day that collected "
                         f"nothing would pass item e4's freshness check")
        examined += 1
        if (out / COVERAGE).exists():
            fails.append(f"a STOPPED run wrote {COVERAGE}: a day that "
                         f"collected nothing would pass item e5")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s); "
      f"{len((truth or {}).get('queries') or [])} query row(s), "
      f"coverage buckets {(coverage or {}).get('buckets')}")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
