"""Quarterly — refresh research/proposed-taxonomy.json with current data.

WHY THIS EXISTS. Confirmed 2026-09-25: the ranked candidate-niche list every
future domain swap (loop/domains.lifecycle()) draws from had been touched
exactly once, ever, since its creation on 2026-08-30 — nothing regenerated it.
A domain retiring and being replaced is fully automatic and data-driven; the
DATA IT DRAWS FROM was frozen. That is the same "runs but nothing invokes it"
defect as everything else in this repo's incident history, one level up: the
mechanism that reacts to the data was fine, the mechanism that refreshes the
data did not exist.

WHY QUARTERLY, NOT MORE OFTEN. The demand and trend passes
(research/mine_broad.py, research/trends.py) are keyless and free — Google's
public autocomplete and Trends widget endpoints, no quota. The competition
pass (research/competition.py) is not: search.list costs 100 of the 10,000
daily YouTube Data API units, and a full candidate-domain scan is tens of
searches, a meaningful fraction of a single day's shared budget — the same
budget the daily upload and the weekly per-domain queue refill both need on
the same day. Evergreen educational demand does not shift week to week the
way it would for news or trends content, so quarterly is frequent enough to
matter and infrequent enough to never meaningfully compete for quota.

THE SEQUENCE, AND WHY IT IS NOT CIRCULAR. research/competition.py
--from-proposal reads research/proposed-taxonomy.json's OWN ranked_domains to
know which candidates to measure — which only works because a taxonomy
already exists to refresh. This stage runs demand and trends first (both
free), competition second (reading the EXISTING, not-yet-replaced taxonomy),
then research/propose.py last, deriving a fresh ranking from all three. The
taxonomy this run reads is always one refresh behind the one it writes.

THE METHOD-STEM PASS (broad_method.json) IS DELIBERATELY NOT REFRESHED HERE.
research/propose.py treats it as optional (required=False) — it enriches the
ranking but a refresh runs correctly without it. Its original generation
command was not established with confidence during the 2026-09-25
investigation that built this stage, and guessing at it risks writing a
malformed file propose.py would then silently misread. Refreshing demand,
trends and competition on a real cadence is the load-bearing fix; the
method-stem pass can be added once its exact invocation is confirmed,
without changing anything else here.

BUDGET-CAPPED, DELIBERATELY BELOW THE DAILY CEILING. --budget leaves real
headroom for whatever else spends quota the same day, on the same account,
this run cannot see.

  python loop/taxonomy_refresh.py
  python loop/taxonomy_refresh.py --budget 3000
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, Stage, week_id  # noqa: E402

PY = sys.executable
RESEARCH = ROOT / "research"
TIMEOUT_S = 3600

QUOTA_MARKERS = re.compile(
    r"quota|quotaExceeded|rateLimitExceeded|dailyLimitExceeded|"
    r"HTTP 403.*quota|exceeded your.*quota", re.I)
KEY_ABSENT_MARKERS = re.compile(r"no youtube data api key|key.?absent", re.I)
TRACEBACK_MARKER = re.compile(r"^Traceback \(most recent call last\):", re.M)


def run_step(st: Stage, label: str, args: list[str]) -> tuple[bool, str]:
    """One subprocess step. Returns (ok, combined output). Never raises —
    the caller decides what a failure here means for the whole refresh."""
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True,
                       timeout=TIMEOUT_S)
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.strip().splitlines()[-4:]:
        st.note(f"  {label}: {line[:150]}")
    ok = r.returncode == 0
    if ok:
        st.work(f"{label}: exit 0")
    return ok, out


def classify(label: str, out: str) -> tuple[str, str]:
    """(code, unblock) for a failed step — the same priority order
    loop/score.py uses and for the same reason: a real traceback is the one
    signal here that cannot be a coincidental keyword match."""
    if TRACEBACK_MARKER.search(out):
        return ("TAXONOMY_REFRESH_CRASHED",
                f"{label} raised an unhandled exception. This is a code "
                f"defect, not a condition that clears on its own next "
                f"quarter — read the traceback in the run log.")
    if KEY_ABSENT_MARKERS.search(out):
        return ("TAXONOMY_REFRESH_KEY_ABSENT",
                f"{label} found no YouTube Data API key. Add YOUTUBE_API_KEY "
                f"as a repository secret; the next quarterly run will pick "
                f"it up.")
    if QUOTA_MARKERS.search(out):
        return ("TAXONOMY_REFRESH_QUOTA",
                f"{label} stopped on YouTube Data API quota. Re-run by hand "
                f"once quota resets (workflow_dispatch), or lower --budget "
                f"and let the next quarterly run finish what this one "
                f"could not.")
    return ("TAXONOMY_REFRESH_FAILED",
            f"{label} exited non-zero without a recognised cause. Run it "
            f"directly and read the output.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=4000,
                    help="quota units research/competition.py may spend "
                         "(of 10,000/day) — capped well under the ceiling "
                         "so the same day's daily upload and weekly queue "
                         "refill are never starved by this")
    args = ap.parse_args()

    with Stage("taxonomy-refresh", week_id(),
               zero_work_hint="Every step failed before writing anything; "
                              "research/proposed-taxonomy.json was not "
                              "touched.") as st:
        steps = [
            ("demand (research/mine_broad.py)",
             ["research/mine_broad.py", "research/seeds_broad.json",
              "--out", "research/broad_mined.json", "--force"]),
            ("trends (research/trends.py)",
             ["research/trends.py", "--from-seeds",
              "--seedfile", "research/seeds_broad.json",
              "--out", "research/trends.json", "--force"]),
            ("competition (research/competition.py)",
             ["research/competition.py", "--from-proposal",
              "--budget", str(args.budget),
              "--out", "research/competition.json", "--force"]),
        ]
        for label, rel_args in steps:
            ok, out = run_step(st, label, rel_args)
            if not ok:
                code, unblock = classify(label, out)
                st.named_stop(
                    code,
                    f"{label} failed; research/proposed-taxonomy.json was "
                    f"not regenerated this quarter. The existing ranking "
                    f"stands — stale evidence beats no evidence — and "
                    f"loop/domains.lifecycle() is unaffected until this "
                    f"clears.",
                    detail={"step": label, "tail": out.strip().splitlines()[-6:]},
                    unblock=unblock)

        ok, out = run_step(st, "propose (research/propose.py)",
                           ["research/propose.py"])
        if not ok:
            code, unblock = classify("research/propose.py", out)
            st.named_stop(
                code,
                "Demand, trends and competition all measured cleanly, but "
                "research/propose.py could not synthesise them into a "
                "refreshed taxonomy. The existing ranking stands.",
                detail={"tail": out.strip().splitlines()[-6:]},
                unblock=unblock)

        st.work("refreshed research/proposed-taxonomy.json from current "
                "demand, trend and competition data")


if __name__ == "__main__":
    main()
