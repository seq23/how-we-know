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
import ast
import json
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence                                   # noqa: E402
import domains                                   # noqa: E402
from common import Stage, config, week_id        # noqa: E402

RESEARCH = ROOT / "research"
IMAGERY = ROOT / "channel" / "imagery"
RIGHTS = IMAGERY / "rights.json"
VIDEO_RIGHTS = IMAGERY / "video_rights.json"

HARVESTER_GLOB = "imagery*.py"


class NoHarvesterForDomain(Exception):
    """A domain holds a weekly slot and nothing harvests imagery for it."""


def declared_harvesters() -> list[dict]:
    """Every research/imagery*.py that declares a HARVESTER contract.

    Read with `ast`, never imported: discovery must not execute a harvester,
    and several of these modules reach the network at module scope.

    This replaces a hardcoded tuple of two deep-sea harvesters. That tuple was
    the whole reason research/imagery_materials.py and imagery_species.py were
    wired to NO lane at all — a second domain went live and the lane that feeds
    it never learned the domain existed. The file declares its own domain; the
    lane asks the allocation which domains are running. There is one list, and
    it is the one in loop/config.json.
    """
    out = []
    for path in sorted(RESEARCH.glob(HARVESTER_GLOB)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "HARVESTER" not in names:
                continue
            try:
                spec = ast.literal_eval(node.value)
            except ValueError:
                continue
            spec = dict(spec)
            spec["path"] = path
            spec["rel"] = f"research/{path.name}"
            out.append(spec)
    return out


def harvesters_for(cfg: dict) -> tuple[list[dict], list[str]]:
    """The scheduled harvesters for domains that currently hold a slot.

    Returns (harvesters, domains_with_none). A domain in the allocation with no
    harvester is NOT skipped quietly — it is the second return value, and the
    caller takes a named stop on it. Skipping quietly is how this lane spent
    weeks feeding one domain out of two.
    """
    alloc = domains.allocation(cfg)
    found = [h for h in declared_harvesters() if h.get("scheduled", True)]
    picked = [h for h in found if h.get("domain") in alloc]
    covered = {h["domain"] for h in picked}
    return picked, [d for d in alloc if d not in covered]


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


def _count(path: Path) -> int | None:
    """Records in one manifest, or None if it does not exist / cannot be read."""
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if isinstance(d, list):
        return len(d)
    for key in ("assets", "clips", "entries", "accepted", "index"):
        if isinstance(d.get(key), list):
            return len(d[key])
    return None


def pool(harvesters: list[dict] | None = None) -> dict:
    """How much cleared material exists right now, per manifest.

    Keyed by the manifest each harvester declares rather than by a fixed pair
    of paths, so a new domain's pool is counted — and its shrink detected — the
    moment its harvester declares itself. The old two-key {imagery, video}
    shape could not report a materials pool at all.
    """
    hs = declared_harvesters() if harvesters is None else harvesters
    out = {h["manifest"]: _count(ROOT / h["manifest"]) for h in hs}
    # Kept so a caller (and the report) can still speak of the two original
    # deep-sea pools by name.
    out.setdefault("channel/imagery/rights.json", _count(RIGHTS))
    out.setdefault("channel/imagery/video_rights.json", _count(VIDEO_RIGHTS))
    return out


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
    cfg = config()
    harvesters, uncovered = harvesters_for(cfg)
    before = pool(harvesters)
    with Stage("imagery-harvest", week_id(),
               zero_work_hint="No harvester in research/ could be run. This "
                              "lane exists to grow the cleared pool ahead of "
                              "demand; a run that harvests nothing has done "
                              "nothing, whatever it exits with.") as st:
        d = demand()
        alloc = domains.allocation(cfg)
        st.note(f"allocation: " + ", ".join(f"{k} {v}" for k, v in alloc.items())
                + f" -> {len(harvesters)} scheduled harvester(s)")
        for path_key, n in sorted(before.items()):
            st.note(f"cleared pool before: {path_key} "
                    + ("absent" if n is None else f"{n} record(s)"))
        st.note(f"demand at the current cadence: {d['videos_per_week']}/week, "
                f"{d['episodes']} episode(s) over the next {d['weeks']} weeks. "
                f"An episode with no cleared footage is illustrated, which is "
                f"a legitimate outcome and never a reason to widen the gate.")

        if uncovered:
            # NOT a skip. A domain publishing weekly with nothing harvesting
            # for it is the failure that let materials run for a week on a pool
            # nothing was topping up.
            st.named_stop(
                "DOMAIN_HAS_NO_HARVESTER",
                f"{', '.join(uncovered)} hold(s) a weekly slot in "
                f"loop/config.json's allocation and no research/imagery*.py "
                f"declares a scheduled HARVESTER for it. Its cleared pool "
                f"cannot grow, and every episode it publishes beyond the "
                f"existing pool is illustrated by default rather than by "
                f"decision.",
                detail={"allocation": alloc,
                        "harvesters": [h["rel"] for h in harvesters],
                        "uncovered": uncovered},
                unblock="Add a HARVESTER declaration (domain, gate, manifest, "
                        "args, what) to the harvester for that domain, or "
                        "write one. The lane finds harvesters by that "
                        "declaration; it does not keep a list of its own.")

        ran = 0
        for h in harvesters:
            rel = h["rel"]
            gate, what = h.get("gate"), h.get("what", rel)
            path = h["path"]
            if not path.exists():
                st.note(f"{rel} is not in this checkout — skipped ({what})")
                continue
            if gate:
                try:
                    assert_rights_gate(rel, gate)
                except RightsGateMissing as e:
                    st.named_stop(
                        "RIGHTS_GATE_MISSING", str(e),
                        unblock=f"Restore the {gate}() allowlist in {rel} "
                                f"before anything harvested through it is "
                                f"used. Nothing was harvested on this run.")
                st.note(f"{rel}: rights gate {gate}() present")
            args = list(h.get("args") or [])
            shown = " ".join([rel] + args)
            if dry_run:
                st.work(f"would harvest {what} through {shown}")
                ran += 1
                continue
            r = subprocess.run([sys.executable, str(path), *args],
                               capture_output=True, text=True, cwd=ROOT,
                               timeout=3600)
            tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
            for line in tail:
                st.note(f"  {rel}: {line}")
            if r.returncode != 0:
                # A harvester that could not reach its source has not failed
                # the channel - it has failed to add anything this week, and
                # the pool is unchanged. Note it; the shrink check below is
                # what would catch real damage.
                st.note(f"{rel} exited {r.returncode}; the pool is unchanged")
                continue
            st.work(f"harvested {what} through {shown}")
            ran += 1

        if not ran:
            st.named_stop(
                "NO_HARVESTER",
                "no rights-checked harvester exists in this checkout for any "
                "allocated domain, so the cleared pool cannot grow. At the "
                "current cadence every episode beyond the existing pool would "
                "be illustrated by default rather than by decision.",
                detail={"allocation": alloc,
                        "declared": [h["rel"] for h in declared_harvesters()],
                        "pool": before},
                unblock="A harvester declares itself with a module-level "
                        "HARVESTER dict naming its domain, its rights gate and "
                        "its manifest. If one is missing from main, land it — "
                        "a scheduled lane with nothing to run is worse than no "
                        "lane.")

        after = pool(harvesters)
        for key in sorted(set(before) | set(after)):
            b, a = before.get(key), after.get(key)
            if b is None or a is None:
                continue
            if a < b:
                st.named_stop(
                    "CLEARED_POOL_SHRANK",
                    f"{key} went from {b} record(s) to {a}. Records only ever "
                    f"accumulate here — neither gate may delete the other's — "
                    f"so this is provenance being lost, not a harvest result.",
                    detail={"before": before, "after": after},
                    unblock="Restore the manifest from git and find what "
                            "removed the records before harvesting again. A "
                            "clip whose provenance no longer resolves must not "
                            "be used, and must not be silently re-accepted.")
            if a > b:
                st.work(f"{key} grew {b} -> {a}")
        for key, n in sorted(after.items()):
            st.note(f"cleared pool after: {key} "
                    + ("absent" if n is None else f"{n} record(s)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="check the gates and report the pool; harvest nothing")
    a = ap.parse_args()
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
