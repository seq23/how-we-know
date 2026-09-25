"""Arming — how a scheduled lane earns its cron instead of waiting for one.

Three lanes shipped with their `cron:` lines commented out and this reason
written above them:

    DISARMED until this lane has completed a real upload end to end.

**That condition can never be met.** The lane cannot complete a real run because
it never runs, and nothing was watching for the day it could. Three lanes were
in that state at once — the upload lane, the Shorts lane and the reach lane —
and the visible cost is 51 rendered Shorts that have never published while
Shorts views are one of the three routes to the Partner Programme.

A commented cron is also invisible. Nothing reports it, no stage fails because
of it, and the only way to discover it is to read the YAML. That is the
"exists but nothing invokes it" defect class, and this repo has produced it
three times.

**The fix is not to uncomment.** The caution was right: two schedulers drawing
from one queue really would double-upload. What was missing is the counterpart
to `loop/state/authoring_evidence.json` — a way for the lane to record that it
has proven itself, and a cron that reads that record.

So:

  * the cron is UNCOMMENTED and fires on schedule;
  * before it does anything, the lane asks `is_armed()`;
  * unarmed, on a schedule trigger, it stops with a NAMED STOP that says
    exactly what to dispatch — visible, in the issue tracker, once, not a
    silent no-op every night;
  * a `workflow_dispatch` run is always allowed, because that is a human
    deliberately proving the lane;
  * a dispatched run that completes end to end calls `record_success()`, and
    the next scheduled run finds itself armed.

The lane arms itself the first time it demonstrably works, and until then the
reason it is not running is a thing the owner is told rather than a comment
nobody reads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

EVIDENCE = ROOT / "loop" / "state" / "lane_evidence.json"

# Every lane whose cron is gated on its own first successful run. A lane that is
# not here is not gated; a cron that is commented out for any lane at all is a
# validator failure (V26), so this is the only legitimate way to hold one back.
LANES = {
    "upload-cloud": {
        "workflow": "loop-upload-cloud.yml",
        "proves": "uploaded and scheduled at least one real episode from R2",
        "secrets": ["YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN",
                    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        "also": ("the Mac agent com.howweknow.backfill must be unloaded in the "
                 "same change — two schedulers on one queue is the failure this "
                 "gate exists to prevent"),
    },
    "shorts-cloud": {
        "workflow": "loop-shorts-cloud.yml",
        "proves": "published at least one real Short from R2",
        "secrets": ["YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN",
                    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        "also": "",
    },
    "reach": {
        "workflow": "loop-reach.yml",
        "proves": "uploaded one caption track and one set of localizations",
        "secrets": ["YT_OAUTH_CLIENT_JSON", "YT_OAUTH_REFRESH_TOKEN",
                    "OPENROUTER_API_KEY"],
        "also": ("captions.insert additionally needs the youtube.force-ssl "
                 "scope, which the plain youtube scope does not cover"),
    },
}


def _load() -> dict:
    try:
        return json.loads(EVIDENCE.read_text())
    except (OSError, ValueError):
        return {"lanes": {}}


def require_lane(lane: str) -> dict:
    if lane not in LANES:
        raise KeyError(f"{lane!r} is not a gated lane; known: "
                       f"{', '.join(sorted(LANES))}")
    return LANES[lane]


def is_armed(lane: str) -> bool:
    require_lane(lane)
    rec = _load()["lanes"].get(lane) or {}
    return bool(rec.get("proven_at"))


def record_success(lane: str, detail: str = "") -> dict:
    """The lane proved itself. Called only after a run that really did the thing.

    Never called from a dry run: `LOOP_DRY_RUN=1` suppresses external writes, so
    a dry run has proven nothing and recording it would arm a cron on the
    strength of a rehearsal.
    """
    require_lane(lane)
    if os.environ.get("LOOP_DRY_RUN") == "1":
        return {"lane": lane, "recorded": False,
                "why": "LOOP_DRY_RUN=1 — a dry run proves nothing and must "
                       "never arm a schedule"}
    from common import now                                  # noqa: PLC0415
    data = _load()
    data["lanes"][lane] = {
        "proven_at": now(),
        "proves": LANES[lane]["proves"],
        "detail": detail,
    }
    data["updated"] = now()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return {"lane": lane, "recorded": True}


def dispatched() -> bool:
    """True when a human deliberately started this run."""
    return os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


def missing_secrets(lane: str) -> list[str]:
    """The lane's required secrets absent from this environment."""
    return [k for k in require_lane(lane)["secrets"]
            if not os.environ.get(k, "").strip()]


def gate(st, lane: str) -> None:
    """Let an unarmed lane arm itself; stop only on a missing secret.

    NOTHING WAITS ON THE OWNER (her rule, 2026-09-25). This used to hold every
    scheduled run of an unarmed lane until she ran `gh workflow run` by hand
    once. That run proved nothing a scheduled run with the same secrets does
    not prove, so a scheduled run with every required secret present IS the
    arming run: it proceeds, and `record_success()` arms the lane when it
    completes. A dispatched run passes as before. The one thing only she can
    supply - a repository secret - is the one thing that still stops it, by
    name.
    """
    if is_armed(lane) or dispatched():
        return
    missing = missing_secrets(lane)
    if not missing:
        print(f"arming: {lane} has never completed a real run; this scheduled "
              f"run is its arming run (every required secret is present)",
              flush=True)
        return
    spec = require_lane(lane)
    st.named_stop(
        f"LANE_NOT_ARMED_{lane.upper().replace('-', '_')}",
        f"the {lane} lane has never completed a real run and cannot arm "
        f"itself: {', '.join(missing)} is not set for this environment.",
        detail={"workflow": spec["workflow"], "proves": spec["proves"],
                "secrets_required": spec["secrets"], "missing": missing,
                "also": spec["also"]},
        unblock=(f"Add {', '.join(missing)} as repository secret(s). The next "
                 f"scheduled run arms the lane itself"
                 + (f". {spec['also']}" if spec["also"] else ".")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="LANE")
    ap.add_argument("--record", metavar="LANE")
    ap.add_argument("--detail", default="")
    a = ap.parse_args()
    if a.record:
        print(json.dumps(record_success(a.record, a.detail)))
        return 0
    if a.check:
        armed = is_armed(a.check)
        print("armed" if armed else "unarmed")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"armed={'true' if armed else 'false'}\n")
        return 0
    for lane in sorted(LANES):
        print(f"{lane:<16} {'ARMED' if is_armed(lane) else 'unarmed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
