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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))

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

# CHECKED BEFORE QUOTA_MARKERS, ALWAYS. research/competition.py's key-absent
# stop explains that the free tier is "10,000 quota units/day", so the word
# "quota" is IN the text of a stop that has nothing to do with quota. On
# 2026-09-12 (run 34687628665 and the 16:27 dispatch after it) that text
# matched QUOTA_MARKERS and a missing YOUTUBE_API_KEY was recorded as
# NEW_DOMAIN_QUOTA - "the next Saturday run retries" - a self-resolving label
# on a state that time cannot resolve. Only she can mint the key.
KEY_ABSENT_MARKERS = re.compile(r"YOUTUBE_API_KEY_ABSENT|no youtube data api key",
                                re.I)


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


def missing_queues() -> dict:
    """Allocated domains with no scored publish-order file of their own.

    Keyed by domain, valued by the file the gate would write. Derived from the
    allocation and the files on disk - NOT from a list of domains that need
    scoring, which is the second list this repo keeps discovering it kept.
    """
    import domains as dom                                   # noqa: PLC0415
    import publish_order_domain as pod                      # noqa: PLC0415

    out = {}
    for name in dom.allocation(config()):
        if dom.queue_depth().get(name, 0) > 0:
            continue
        out[name] = Path(pod.out_path(name))
    return out


def refresh_primary_ranking(st: Stage) -> None:
    """Run the research agent's scorer and prove the ranking is fresh.

    THIS IS THE LANE'S JOB, AND IT RUNS FIRST. From 2026-09-05 to 09-17 the
    new-domain gate below ran ahead of it and raised its named stop on a
    missing YouTube key, so this function was never reached: the primary
    ranking sat at generated_at 2026-09-05 while two Saturday runs went green
    with a stop that said "retries next week". On 09-16 15:36 UTC the file
    crossed publish_order.staleness_days and `loop · tests` went red on check
    4 of validate_plan.py (run 35230863447) - PublishOrderStale, twelve days.
    The primary scorer needs no YouTube key (it reads the competition file
    already measured for its scripts), so nothing about a keyless runner is a
    reason not to refresh it.
    """
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


def score_new_domains(st: Stage) -> None:
    """Give a promoted domain its first scored queue.

    A DOMAIN THE MONTHLY REVIEW PROMOTED ARRIVES WITH NO QUEUE. It holds
    weekly slots from the moment loop/domains.lifecycle() retires the
    domain it replaced, and nothing else in the loop will score its
    topics: research/publish_order.py gates deep sea and
    publish_order_materials.py gates materials from a hand-written
    candidate list. Scoring it here, on the schedule, is what makes the
    promotion real rather than an entry in a report.

    Same gate, imported unchanged - a new domain's topics are not waved
    through for being new. A quota or key stop is named, not a failure,
    and leaves the domain queueless until it clears. It runs AFTER
    refresh_primary_ranking() on purpose: its stop must never cost the
    channel the ranking every publishing lane reads.
    """
    for dom, path in missing_queues().items():
        st.note(f"{dom} holds weekly slots and has no scored queue; "
                f"running the gate for it")
        g = subprocess.run(
            [PY, str(ROOT / "research" / "publish_order_domain.py"),
             "--domain", dom], cwd=ROOT, capture_output=True, text=True,
            timeout=TIMEOUT_S)
        gout = (g.stdout or "") + (g.stderr or "")
        for line in gout.strip().splitlines()[-4:]:
            st.note(f"  {dom}: {line[:150]}")
        if g.returncode == 0 and path.exists():
            st.work(f"scored a first queue for {dom} -> "
                    f"{path.relative_to(ROOT)}")
        elif KEY_ABSENT_MARKERS.search(gout):
            st.named_stop(
                "NEW_DOMAIN_KEY_ABSENT",
                f"{dom} holds weekly slots and its first topic gate found no "
                f"YouTube Data API key in this environment. Competition "
                f"cannot be measured without one, so the domain has no queue "
                f"and the drafting lane has nothing to draw from for it. The "
                f"primary ranking was refreshed before this stop.",
                detail={"domain": dom, "tail": gout.strip().splitlines()[-4:]},
                unblock="Add YOUTUBE_API_KEY as a repository secret (a Data "
                        "API v3 key on the Google Cloud project that already "
                        "holds the upload OAuth client; free tier, no card). "
                        "The next Saturday run scores the domain. No retry "
                        "without the key can clear this.")
        elif QUOTA_MARKERS.search(gout):
            st.named_stop(
                "NEW_DOMAIN_QUOTA",
                f"{dom} holds weekly slots and its first topic gate "
                f"stopped on YouTube Data API quota. It has no queue until "
                f"this runs, and the drafting lane has nothing to draw "
                f"from for it.",
                detail={"domain": dom, "tail": gout.strip().splitlines()[-4:]},
                unblock="The next Saturday run retries. If it recurs, the "
                        "candidate set is larger than one day's quota - "
                        "lower --budget and let it fill over two weeks.")
        else:
            st.named_stop(
                "NEW_DOMAIN_UNSCORED",
                f"{dom} holds weekly slots and its first topic gate exited "
                f"{g.returncode} without writing a queue.",
                detail={"domain": dom, "tail": gout.strip().splitlines()[-6:]},
                unblock="Run research/publish_order_domain.py --domain "
                        f"{dom} --candidates-only to see what it found. A "
                        "domain with no queue cannot fill the slots the "
                        "monthly review gave it.")


def main() -> None:
    week = week_id()
    with Stage("weekly-score", week,
               zero_work_hint="The scoring entrypoint produced no ranked "
                              "candidate. A scoring pass that ranks nothing "
                              "has done nothing.") as st:
        # Order is the fix. The ranking every publishing lane reads is
        # refreshed before anything that can stop this stage gets to run.
        refresh_primary_ranking(st)
        score_new_domains(st)


if __name__ == "__main__":
    main()
