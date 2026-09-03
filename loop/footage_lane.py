"""Grow the rights-cleared imagery and footage pool AHEAD of demand.

    .venv/bin/python loop/footage_lane.py --dry-run
    .venv/bin/python loop/footage_lane.py

WHY THIS EXISTS, AND WHY NOW. Footage is the real scarcity on this channel. The
cleared pool is small - a handful of video entries beside the still imagery -
and at 2 episodes a week that was survivable because harvesting happened
whenever somebody remembered. At 4 a week it is not: the pool would be behind
demand permanently, and the failure would be invisible, because the pipeline
degrades *gracefully* into an illustrated episode rather than breaking.

ILLUSTRATED IS NOT A FAILURE. Three episodes have no public-domain footage and
never will - colossal squid, whale fall, surviving pressure - and they ship
illustrated rather than mislabelled. That is deliberate and it stays. So a small
pool is NOT a named stop here: this lane exists to make the pool grow on a
schedule, not to hold the channel hostage to it.

WHAT IS A NAMED STOP:

* **No harvester could be run at all.** A scheduled lane that harvests nothing,
  week after week, exiting 0, is the "runs but inert" failure this repo names
  explicitly.
* **The cleared pool SHRANK.** Records only ever accumulate - the manifest
  writer is explicit that neither gate may delete the other's records - so a
  smaller pool means something removed cleared provenance, which is a defect
  and not a harvest result.
* **The rights gate is missing from a harvester.** See below.

THE ONE THING THIS LANE MAY NEVER DO IS RELAX THE RIGHTS CHECK TO INCREASE
SUPPLY. The gate is an allowlist: the credit line on the item page must resolve
to NOAA and nobody else, and anything ambiguous is dropped. Roughly 40% of
deep-sea items on a .gov host are credited to third parties who are not federal.
This lane therefore refuses to run a harvester whose source no longer contains
that gate - `assert_rights_gate()` - because the cheapest way to "fix" a thin
pool is to widen the gate, and that is the one change this pipeline may not make.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence                                   # noqa: E402
from common import Stage, week_id                # noqa: E402

RESEARCH = ROOT / "research"
IMAGERY = ROOT / "channel" / "imagery"
RIGHTS = IMAGERY / "rights.json"
VIDEO_RIGHTS = IMAGERY / "video_rights.json"

# Each harvester, and the gate its source MUST still contain. The second element
# is not decoration: it is what makes "relax the check to get more clips" fail
# loudly instead of quietly succeeding.
HARVESTERS = (
    ("research/imagery.py", "credit_is_noaa_only",
     "still imagery — NOAA Ocean Exploration, plus a hand-verified "
     "public-domain set"),
    ("research/imagery_video.py", "credit_is_noaa_only",
     "video clips — the scarce pool"),
)


class RightsGateMissing(Exception):
    """A harvester lost its provenance gate. Never harvest through it."""


def assert_rights_gate(rel: str, gate: str) -> None:
    """Refuse to run a harvester whose NOAA-only gate is gone."""
    src = (ROOT / rel).read_text()
    if gate not in src:
        raise RightsGateMissing(
            f"{rel} no longer contains {gate}() — the allowlist that requires "
            f"a credit line to resolve to NOAA and nobody else. Widening the "
            f"gate is the cheapest way to make a thin pool look healthy and "
            f"the one change this pipeline may not make. A clip whose "
            f"provenance does not resolve to NOAA alone does not get used.")


def pool() -> dict:
    """How much cleared material exists right now, by kind."""
    def count(path: Path) -> int | None:
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        if isinstance(d, list):
            return len(d)
        for key in ("assets", "clips", "entries", "accepted"):
            if isinstance(d.get(key), list):
                return len(d[key])
        return None

    return {"imagery": count(RIGHTS), "video": count(VIDEO_RIGHTS)}


def demand(weeks: int = 8) -> dict:
    """What the CURRENT cadence will ask of the pool over `weeks`.

    Reported, never enforced. An episode with no cleared footage is illustrated,
    which is a legitimate outcome - so this number exists to make a shortfall
    visible early, not to gate anything.
    """
    per_week = cadence.effective()
    return {"videos_per_week": per_week, "weeks": weeks,
            "episodes": per_week * weeks}


def run(dry_run: bool = False) -> int:
    before = pool()
    with Stage("imagery-harvest", week_id(),
               zero_work_hint="No harvester in research/ could be run. This "
                              "lane exists to grow the cleared pool ahead of "
                              "demand; a run that harvests nothing has done "
                              "nothing, whatever it exits with.") as st:
        d = demand()
        st.note(f"cleared pool before: {before['imagery']} imagery record(s), "
                f"{before['video']} video record(s)")
        st.note(f"demand at the current cadence: {d['videos_per_week']}/week, "
                f"{d['episodes']} episode(s) over the next {d['weeks']} weeks. "
                f"An episode with no cleared footage is illustrated, which is "
                f"a legitimate outcome and never a reason to widen the gate.")

        ran = 0
        for rel, gate, what in HARVESTERS:
            path = ROOT / rel
            if not path.exists():
                st.note(f"{rel} is not in this checkout — skipped ({what})")
                continue
            try:
                assert_rights_gate(rel, gate)
            except RightsGateMissing as e:
                st.named_stop(
                    "RIGHTS_GATE_MISSING", str(e),
                    unblock=f"Restore the {gate}() allowlist in {rel} before "
                            f"anything harvested through it is used. Nothing "
                            f"was harvested on this run.")
            st.note(f"{rel}: rights gate {gate}() present")
            if dry_run:
                st.work(f"would harvest {what} through {rel}")
                ran += 1
                continue
            r = subprocess.run([sys.executable, str(path)],
                               capture_output=True, text=True, cwd=ROOT,
                               timeout=3600)
            tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
            for line in tail:
                st.note(f"  {rel}: {line}")
            if r.returncode != 0:
                # A harvester that could not reach NOAA has not failed the
                # channel - it has failed to add anything this week, and the
                # pool is unchanged. Note it; the shrink check below is what
                # would catch real damage.
                st.note(f"{rel} exited {r.returncode}; the pool is unchanged")
                continue
            st.work(f"harvested {what} through {rel}")
            ran += 1

        if not ran:
            st.named_stop(
                "NO_HARVESTER",
                "no rights-checked harvester exists in this checkout, so the "
                "cleared pool cannot grow. At the current cadence every "
                "episode beyond the existing pool would be illustrated by "
                "default rather than by decision.",
                detail={"looked_for": [h[0] for h in HARVESTERS],
                        "pool": before},
                unblock="research/imagery.py is the still-imagery harvester "
                        "and research/imagery_video.py the video one. If "
                        "either is missing from main, land it — a scheduled "
                        "lane with nothing to run is worse than no lane.")

        after = pool()
        for kind in ("imagery", "video"):
            b, a = before[kind], after[kind]
            if b is None or a is None:
                continue
            if a < b:
                st.named_stop(
                    "CLEARED_POOL_SHRANK",
                    f"the cleared {kind} pool went from {b} record(s) to {a}. "
                    f"Records only ever accumulate here — neither gate may "
                    f"delete the other's — so this is provenance being lost, "
                    f"not a harvest result.",
                    detail={"before": before, "after": after},
                    unblock="Restore the manifest from git and find what "
                            "removed the records before harvesting again. A "
                            "clip whose provenance no longer resolves must not "
                            "be used, and must not be silently re-accepted.")
            if a > b:
                st.work(f"cleared {kind} pool grew {b} -> {a}")
        st.note(f"cleared pool after: {after['imagery']} imagery record(s), "
                f"{after['video']} video record(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="check the gates and report the pool; harvest nothing")
    a = ap.parse_args()
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
