"""Weekly - run the demand/competition pass so the queue is never stale.

The owner should never have to ask for this analysis. It runs on the schedule,
ahead of the publish decision, so the queue is always ranked on current data.

**The research agent owns the entrypoint and the file contract; this stage owns
only the schedule.** It invokes the command, then reads the result read-only.
It never writes `research/publish_order.json`.

The failure this guards against is specific: if scoring silently stops running,
the loop keeps publishing in a stale order and looks perfectly healthy while
doing it. That is the "runs but inert" class, so:

* a pass that produces **no scored candidates is a hard failure**, not a pass
* a **stale ranking is loud** - `loop/cadence.py` raises rather than shrugging
* a **quota stop is a legitimate outcome**, surfaced and named, not a failure.
  `search.list` costs 100 units against 10,000/day, so a scoring pass can
  legitimately run out. The previous ranking is left in place when it does -
  yesterday's evidence beats no evidence, right up until it is stale.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadence  # noqa: E402
from common import ROOT, Stage, config, now, read_json, week_id  # noqa: E402

# THE INTERPRETER IS RESOLVED, NOT ASSUMED. This was hardcoded to
# .venv/bin/python, which exists on the Mac and nowhere else, so
# `loop · Sat 06:00 · score` died every Saturday on the Ubuntu runner with
# FileNotFoundError: .venv/bin/python - a scheduled lane failing not because
# the ranking was wrong but because it was told to run a binary that is not
# there. loop/tests/run_all.py already had this pattern; score.py did not. The
# venv still wins where it exists, because on the Mac it carries numpy and
# Pillow the system python may not.
PY = (str(ROOT / ".venv" / "bin" / "python")
      if (ROOT / ".venv" / "bin" / "python").exists()
      else sys.executable)
TIMEOUT_S = 1800          # the mining pass sleeps between autocomplete calls

QUOTA_MARKERS = re.compile(
    r"quota|quotaExceeded|rateLimitExceeded|dailyLimitExceeded|"
    r"HTTP 403.*quota|exceeded your.*quota", re.I)


def entrypoint() -> Path:
    """The command to run. The file names its own generator; config overrides."""
    cfg = config()["publish_order"]
    raw = read_json(cadence.PUBLISH_ORDER, default={})
    named = raw.get("generator") if isinstance(raw, dict) else None
    for cand in (cfg.get("entrypoint"), named, "research/publish_order.py"):
        if not cand:
            continue
        p = ROOT / str(cand).split()[0]
        if p.exists():
            return p
    return ROOT / str(cfg.get("entrypoint", "research/publish_order.py"))


def main() -> None:
    week = week_id()
    with Stage("weekly-score", week,
               zero_work_hint="The scoring entrypoint produced no ranked "
                              "candidate. A scoring pass that ranks nothing "
                              "has done nothing.") as st:

        ep = entrypoint()
        if not ep.exists():
            st.named_stop(
                "SCORER_MISSING",
                f"the scoring entrypoint {ep.relative_to(ROOT)} does not exist",
                unblock="The research agent owns this command. Point "
                        "loop/config.json publish_order.entrypoint at it once "
                        "it lands. The loop will not invent a ranking.")

        before = read_json(cadence.PUBLISH_ORDER, default={})
        before_at = before.get("generated_at") if isinstance(before, dict) else None

        st.note(f"running {ep.relative_to(ROOT)} (owned by the research agent)")
        p = subprocess.run([PY, str(ep)], cwd=ROOT, capture_output=True,
                           text=True, timeout=TIMEOUT_S)
        out = (p.stdout or "") + (p.stderr or "")
        tail = out.strip().splitlines()[-6:]
        for line in tail:
            st.note(f"  scorer: {line[:150]}")

        # A quota stop is a legitimate outcome, not a failure. The previous
        # ranking stays; yesterday's evidence beats none, until it goes stale.
        if QUOTA_MARKERS.search(out):
            st.work("scoring pass ran and reported a quota limit")
            st.named_stop(
                "SCORER_QUOTA",
                "the scoring pass stopped on YouTube Data API quota. "
                "search.list costs 100 units against 10,000/day, so this is an "
                "expected outcome, not a defect. The previous ranking is left "
                "in place.",
                detail={"previous_generated_at": before_at,
                        "scorer_tail": tail},
                unblock="Wait for the daily quota reset; the next weekly run "
                        "picks it up. If it recurs every week, the pass is "
                        "scoring more candidates than the quota allows.")

        if p.returncode != 0:
            st.named_stop(
                "SCORER_FAILED",
                f"the scoring entrypoint exited {p.returncode}",
                detail={"tail": tail},
                unblock="This command belongs to the research agent. The loop "
                        "will not substitute its own ranking.")

        # Rule 0, and the whole point of the stage: a pass that ranked nothing
        # must not report success.
        after = read_json(cadence.PUBLISH_ORDER, default={})
        if not isinstance(after, dict) or not after:
            st.named_stop(
                "NO_RANKING_PRODUCED",
                "the scoring pass exited cleanly but wrote no usable ranking",
                unblock="Check the scorer's own output above.")

        try:
            order = cadence.publish_order()
        except cadence.PublishOrderStale as e:
            st.named_stop(
                "RANKING_STALE_AFTER_SCORING", str(e),
                detail={"generated_at": after.get("generated_at")},
                unblock="The pass ran but did not refresh the timestamp - it "
                        "may have failed silently and left the old file. This "
                        "is the 'runs but inert' case the stage exists to "
                        "catch.")
        except cadence.PublishOrderMissing as e:
            st.named_stop("NO_RANKING_PRODUCED", str(e))

        if not order:
            st.named_stop(
                "NO_SCORED_CANDIDATES",
                "the ranking contains zero scored candidates",
                unblock="A ranking with nothing in it cannot order a publish "
                        "queue. The loop refuses rather than falling back to "
                        "filename order.")

        st.work(f"scored and ranked {len(order)} candidate(s)")
        meta = cadence.order_meta_raw()
        if meta.get("generated_at") == before_at:
            st.note("WARNING: generated_at is unchanged from before the run")
        if meta.get("pinned_head"):
            st.work(f"pinned head honoured, not re-sorted: "
                    f"{', '.join(meta['pinned_head'])}")
        if meta.get("saturated_tail"):
            st.work(f"saturated tail pushed last: "
                    f"{', '.join(meta['saturated_tail'])}")
        st.work(f"ranking is fresh as of {meta.get('generated_at')}")


if __name__ == "__main__":
    main()
