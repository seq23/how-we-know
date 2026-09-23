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
* **A harvester requires host tooling THE HOST IT IS DECLARED TO RUN ON does
  not have.** The video harvester's gates B and C read burned-in credits with
  Apple's Vision framework off frames ffmpeg pulls from the clip; ubuntu-latest
  has neither. CONFIRMED on runs 33943991250 and 34672456430: every clip that
  passed the rights gate then failed on a missing `ffmpeg`, the screener
  labelled the exception "gate A-credit", and the lane wrote "the pool is
  unchanged" for a pool that had never held a single clip. That is
  `HARVESTER_TOOLING_ABSENT`, a defect in the declaration, and it stays red.
  It never substitutes an OCR engine and never accepts a clip unverified;
  loop/r2.py:verify_shorts records why.
* **A harvester DELEGATED to another host has not been run there.** See
  below.

WHERE A HARVESTER RUNS IS PART OF ITS DECLARATION. From 2026-09-12 to
2026-09-19 the video harvester was reported as "unrunnable" on the Linux
runner and HELD on issue #77; the owner closed the issue, the hold paged again
the next Saturday (#91), and would have every Saturday forever, because a
hold is a question and nothing in the code could answer it. The answer is in
the code now: a HARVESTER declares `host` - the scheduled process that runs it
- and the lane on any host splits the registry into the harvesters it RUNS and
the harvesters it VERIFIES. `research/imagery_video.py` declares
`host: "mac-batch"`: bin/batch-session.sh runs this lane nightly on the Mac,
which has ffmpeg, swiftc and Vision, and pushes the result. The Saturday lane
on ubuntu-latest sees it as DELEGATED, not unrunnable, and checks that the
Mac is actually doing the work.

HOW THE LINUX LANE SEES THE MAC'S WORK. The manifest itself
(channel/imagery/video_rights.json) never enters git - the clips are 5 GB on
the Mac and in R2, and V11 re-hashes every record against the bytes on disk,
so a committed manifest with no clips beside it would fail the Monday lane.
What crosses is loop/state/harvest_runs.json: every host stamps each harvester
it ran (when, exit code, how many records its manifest now holds, the tail of
its output) and commits that file - bin/loop-stage.sh's `git add loop` on the
runner, loop/mac_sync.py push on the Mac. A delegated harvester whose stamp
shows a success within `harvest.delegated_max_age_days` is VERIFIED and counted
as a unit of this lane's work, printed in the summary as delegated. One whose
last run within the cap FAILED is `DELEGATED_HARVEST_FAILING` (a defect; red).
One with no run inside the cap at all is `DELEGATED_HARVEST_STALE` (the host
has not run; only the owner can start a Mac that is off - owner_action, green,
top of the digest, red after its cap). A guard that cannot reach what it
governs is the defect class this repo names most; this is the reach.

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
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence                                   # noqa: E402
import domains                                   # noqa: E402
import host_tools                                # noqa: E402
from common import Stage, config, read_json, week_id, write_json  # noqa: E402

RESEARCH = ROOT / "research"
IMAGERY = ROOT / "channel" / "imagery"
RIGHTS = IMAGERY / "rights.json"
VIDEO_RIGHTS = IMAGERY / "video_rights.json"

HARVESTER_GLOB = "imagery*.py"

# ---------------------------------------------------------------- hosts
#
# THE SCHEDULED PROCESSES THAT RUN THIS LANE, by name. A harvester declares
# which one runs it (`host` in its HARVESTER literal; absent means "ci"). The
# lane is started with `--host <name>` by each of them, runs the harvesters
# declared for that host, and VERIFIES the rest through loop/state/
# harvest_runs.json. One table, so a harvester cannot name a host that nothing
# schedules: an unknown name is a loud error at discovery, never a quiet
# "delegated to nowhere" - which would be the exact gap #77 fell into.
HOSTS = {
    "ci": {
        "what": "the Saturday GitHub Actions lane (.github/workflows/"
                "loop-imagery-harvest.yml, ubuntu-latest, 04:00 UTC)",
        "stage": "imagery-harvest",
        "start": "gh workflow run loop-imagery-harvest.yml",
    },
    "mac-batch": {
        "what": "the Mac's nightly batch (bin/batch-session.sh, launchd "
                "com.howweknow.batch at 23:00 local; it has ffmpeg, swiftc "
                "and Apple Vision)",
        "stage": "imagery-harvest-mac",
        "start": "wake the Mac (launchd fires the missed 23:00 batch on wake) "
                 "or run bin/batch-session.sh on it by hand",
    },
}
DEFAULT_HOST = "ci"

# Per-harvester run stamps, one file, written by every host and committed by
# every host: bin/loop-stage.sh `git add loop` on the runner, loop/mac_sync.py
# push on the Mac. It is the only thing about a delegated harvest that crosses
# hosts - see the docstring for why the manifest itself does not.
STAMPS = LOOP / "state" / "harvest_runs.json"


def _stamps_path() -> Path:
    """Overridable the way LOOP_STOPS_DIR is, so a test can run a real lane
    against planted stamps without writing the loop's own state."""
    return Path(os.environ.get("LOOP_HARVEST_STAMPS") or STAMPS)

STAMPS_WHY = (
    "Written by loop/footage_lane.py on every host that runs a harvester, "
    "keyed by the harvester's path. A host that does NOT run a harvester reads "
    "this to verify the host that does is doing it: a success inside "
    "harvest.delegated_max_age_days (loop/config.json) is fresh; a failed run "
    "inside the cap is DELEGATED_HARVEST_FAILING; nothing inside the cap is "
    "DELEGATED_HARVEST_STALE. The video manifest never enters git (the clips "
    "are on the Mac and in R2, and V11 re-hashes every record against the "
    "bytes on disk), so `records` here is how the cloud knows the pool size.")


class UnknownHarvestHost(Exception):
    """A harvester declared a host this lane has no schedule for."""


def host_of(h: dict) -> str:
    name = h.get("host", DEFAULT_HOST)
    if name not in HOSTS:
        raise UnknownHarvestHost(
            f"{h.get('rel', '?')} declares host {name!r}, which is not a host "
            f"loop/footage_lane.py knows a schedule for (known: "
            f"{', '.join(sorted(HOSTS))}). A harvester delegated to a host "
            f"nothing runs is a harvester nothing runs.")
    return name


def harvest_policy(cfg: dict | None = None) -> dict:
    """The two numbers this lane reads from loop/config.json, with the reason."""
    hv = (cfg or config()).get("harvest") or {}
    return {"delegated_max_age_days": int(hv.get("delegated_max_age_days", 10)),
            "interval_days": int(hv.get("interval_days", 6))}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _when(iso) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def stamps(path: Path | None = None) -> dict:
    """Every harvester's last run, keyed by its rel path. `_why` stripped."""
    d = read_json(path or _stamps_path(), default={})
    return {k: v for k, v in d.items() if not k.startswith("_")
            and isinstance(v, dict)}


def stamp(rel: str, host: str, ok: bool, exit_code: int, records: int | None,
          tail: list[str], path: Path | None = None,
          when: dt.datetime | None = None) -> dict:
    """Record one harvester run on this host. Never called on a dry run."""
    path = path or _stamps_path()
    d = read_json(path, default={})
    d.setdefault("_why", STAMPS_WHY)
    rec = dict(d.get(rel) or {})
    at = (when or _utcnow()).isoformat(timespec="seconds")
    rec.update({"host": host, "last_run_at": at, "ok": bool(ok),
                "exit": int(exit_code), "week": week_id(), "records": records,
                "tail": list(tail)[-6:]})
    if ok:
        rec["last_success_at"] = at
    d[rel] = rec
    write_json(path, d)
    return rec


def delegated_status(h: dict, st: dict, now: dt.datetime | None = None,
                     max_age_days: int | None = None) -> dict:
    """What THIS host can say about a harvester another host runs.

    Pure over (harvester, stamps, now). `state` is one of:
      fresh    a success inside the cap - verified, counts as this lane's work
      failing  the host ran it inside the cap and it did not succeed - a defect
      stale    no run inside the cap at all - the host has not been running
    """
    now = now or _utcnow()
    cap = max_age_days if max_age_days is not None \
        else harvest_policy()["delegated_max_age_days"]
    rec = st.get(h["rel"]) or {}
    ok_at, run_at = _when(rec.get("last_success_at")), _when(rec.get("last_run_at"))
    ok_age = (now - ok_at).total_seconds() / 86400 if ok_at else None
    run_age = (now - run_at).total_seconds() / 86400 if run_at else None
    if ok_age is not None and ok_age <= cap:
        state = "fresh"
    elif run_age is not None and run_age <= cap:
        state = "failing"
    else:
        state = "stale"
    return {"rel": h["rel"], "host": host_of(h), "state": state, "cap_days": cap,
            "last_success_at": rec.get("last_success_at"),
            "last_run_at": rec.get("last_run_at"),
            "success_age_days": None if ok_age is None else round(ok_age, 1),
            "run_age_days": None if run_age is None else round(run_age, 1),
            "records": rec.get("records"), "exit": rec.get("exit"),
            "tail": rec.get("tail") or []}


def due(h: dict, st: dict, now: dt.datetime | None = None,
        interval_days: int | None = None) -> tuple[bool, float | None]:
    """(is it time to run this harvester again here?, days since it last did).

    The Mac's batch is nightly and the harvest re-screens NOAA's whole index,
    so a harvester is re-run only after `harvest.interval_days`. Never run is
    always due.
    """
    now = now or _utcnow()
    interval = interval_days if interval_days is not None \
        else harvest_policy()["interval_days"]
    ok_at = _when((st.get(h["rel"]) or {}).get("last_success_at"))
    if not ok_at:
        return True, None
    age = (now - ok_at).total_seconds() / 86400
    return age >= interval, round(age, 1)


def lost_since_stamp(h: dict, st: dict, host: str) -> tuple[int, int | None] | None:
    """(records this host stamped, records its manifest holds now) when the
    manifest LOST records since this host last harvested - else None.

    WHY. The shrink check in run() compares the pool before and after ONE run,
    so a manifest that vanishes BETWEEN runs is invisible to it, and due()
    reads only the stamp's date. CONFIRMED 2026-09-23: #101 untracked
    channel/imagery/video_rights.json, the Mac's next `git pull` deleted the
    working copy (a pull that removes a tracked file removes it from disk,
    gitignore or not), and for two nights the lane printed "harvested 3.0
    day(s) ago ... not re-run tonight" over a manifest that did not exist.
    Every Short cut from that footage then failed V14 against credits
    re-resolved without it, and push_shorts shelved nothing.

    Only this host's own stamp is compared: a delegated harvester's manifest
    is absent here by design.
    """
    rec = st.get(h["rel"]) or {}
    stamped = rec.get("records")
    if rec.get("host") != host or not isinstance(stamped, int) or stamped <= 0:
        return None
    now = _count(ROOT / h["manifest"])
    if now is not None and now >= stamped:
        return None
    return stamped, now


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


def run(dry_run: bool = False, host: str = DEFAULT_HOST) -> int:
    if host not in HOSTS:
        raise UnknownHarvestHost(
            f"--host {host!r} is not a host this lane knows (known: "
            f"{', '.join(sorted(HOSTS))})")
    cfg = config()
    policy = harvest_policy(cfg)
    harvesters, uncovered = harvesters_for(cfg)
    before = pool(harvesters)
    with Stage(HOSTS[host]["stage"], week_id(),
               zero_work_hint="No harvester in research/ could be run on this "
                              "host and none is delegated elsewhere. This "
                              "lane exists to grow the cleared pool ahead of "
                              "demand; a run that harvests nothing has done "
                              "nothing, whatever it exits with.") as st:
        d = demand()
        alloc = domains.allocation(cfg)
        # Split by declared host BEFORE anything runs. An unknown host name is
        # a crash, not a stop: it is a defect in a declaration, and it must
        # not be reported as "delegated" to a process that does not exist.
        local = [h for h in harvesters if host_of(h) == host]
        delegated = [h for h in harvesters if host_of(h) != host]
        st.note(f"allocation: " + ", ".join(f"{k} {v}" for k, v in alloc.items())
                + f" -> {len(harvesters)} scheduled harvester(s): "
                f"{len(local)} run here on {host}, {len(delegated)} delegated")
        for h in delegated:
            st.note(f"{h['rel']} is delegated to {host_of(h)} "
                    f"({HOSTS[host_of(h)]['what']}); verified below, not run")
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
        not_due = 0
        st_before = stamps()
        # (harvester rel, [missing tool descriptions]) for every harvester
        # DECLARED FOR THIS HOST that this host cannot run to completion. That
        # is a defect in the declaration - the host it names cannot do the
        # job - and it is reported as one after the runnable harvesters have
        # done their work.
        unrunnable: list[tuple[str, list[str]]] = []
        for h in local:
            rel = h["rel"]
            gate, what = h.get("gate"), h.get("what", rel)
            path = h["path"]
            if not path.exists():
                st.note(f"{rel} is not in this checkout — skipped ({what})")
                continue
            # BEFORE the gate check and before spawning: a harvester that
            # cannot finish screening on this host must not start. Run
            # anyway, it turns every environment error into a rejection that
            # reads like a rights decision (run 34672456430: 379/379 "gate
            # A-credit", all of them FileNotFoundError('ffmpeg')).
            missing = host_tools.missing(h.get("requires"))
            if missing:
                for m in missing:
                    st.note(f"{rel}: this host lacks {m}")
                unrunnable.append((rel, missing))
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
            is_due, age = due(h, st_before, interval_days=policy["interval_days"])
            lost = lost_since_stamp(h, st_before, host)
            if lost:
                # Self-heal, not a page: re-harvest now, through every gate.
                # Nothing is re-accepted without screening - the harvester
                # re-runs gates A, B and C on each clip, and its stamp says
                # whether that worked for the other host to verify.
                is_due = True
                st.work(f"{rel}: {h['manifest']} holds "
                        + ("nothing (absent)" if lost[1] is None
                           else f"{lost[1]} record(s)")
                        + f" but this host stamped {lost[0]} at its last "
                        f"harvest - provenance was lost between runs; "
                        f"re-harvesting now instead of waiting for "
                        f"harvest.interval_days")
            if not is_due:
                # A nightly host does not re-screen a whole public index
                # nightly. Said out loud with the date, so "not due" can
                # never be mistaken for "not wired".
                st.note(f"{rel}: harvested {age} day(s) ago on {host}; due "
                        f"again after {policy['interval_days']} (loop/config."
                        f"json harvest.interval_days) - not re-run tonight")
                not_due += 1
                continue
            # The harvester's own budget. Measured 2026-09-19 on the Mac:
            # the video screener OCRs 16 clips in 5m44s with 8 workers, so
            # NOAA's 383-post index is ~2.3 hours - the old flat hour would
            # have timed the delegated harvest out on every run and reported
            # DELEGATED_HARVEST_FAILING for a harvester that was working.
            budget = int(h.get("timeout_seconds") or 3600)
            try:
                r = subprocess.run([sys.executable, str(path), *args],
                                   capture_output=True, text=True, cwd=ROOT,
                                   timeout=budget)
                rc, out = r.returncode, r.stdout + r.stderr
            except subprocess.TimeoutExpired as exc:
                rc = 124
                out = (f"{exc.stdout or ''}{exc.stderr or ''}\n"
                       f"{rel} exceeded its {budget}s harvest budget "
                       f"(HARVESTER timeout_seconds)")
            tail = out.strip().splitlines()[-6:]
            for line in tail:
                st.note(f"  {rel}: {line}")
            # THE STAMP IS WRITTEN WHATEVER HAPPENED. A host that only stamps
            # its successes reads, from the other host, exactly like a host
            # that never ran - and those are different stops.
            stamp(rel, host, ok=(rc == 0), exit_code=rc,
                  records=_count(ROOT / h["manifest"]), tail=tail)
            if rc != 0:
                # A harvester that could not reach its source has not failed
                # the channel - it has failed to add anything this week, and
                # the pool is unchanged. Note it; the shrink check below is
                # what would catch real damage, and the other host's
                # verification is what catches a run of these.
                st.note(f"{rel} exited {rc}; the pool is unchanged")
                continue
            st.work(f"harvested {what} through {shown}")
            ran += 1

        # ---- VERIFY WHAT IS DELEGATED. This is the guard reaching what it
        # governs: the host that does not run a harvester reads the stamp of
        # the host that does. Fresh is a unit of work; the two ways it can be
        # wrong are two different stops, raised after the pool report.
        st_now = stamps()
        verified: list[dict] = []
        failing: list[dict] = []
        stale: list[dict] = []
        for h in delegated:
            v = delegated_status(h, st_now,
                                 max_age_days=policy["delegated_max_age_days"])
            {"fresh": verified, "failing": failing, "stale": stale}[v["state"]].append(v)
        for v in verified:
            st.work(f"verified {v['rel']} is harvesting on {v['host']} "
                    f"(delegated): last success {v['last_success_at']} "
                    f"({v['success_age_days']} day(s) ago), "
                    + ("pool size unknown" if v["records"] is None
                       else f"{v['records']} record(s)")
                    + f" - within the {v['cap_days']}-day cap")

        if not ran and not unrunnable and not delegated and not not_due:
            # If every harvester was UNRUNNABLE rather than absent, the stop
            # below says so by name, and one that is merely not due yet is
            # noted above; NO_HARVESTER is for a checkout with nothing to run
            # at all.
            st.named_stop(
                "NO_HARVESTER",
                "no rights-checked harvester exists in this checkout for any "
                "allocated domain, so the cleared pool cannot grow. At the "
                "current cadence every episode beyond the existing pool would "
                "be illustrated by default rather than by decision.",
                detail={"allocation": alloc, "host": host,
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
            line = f"cleared pool after: {key} " + (
                "absent" if n is None else f"{n} record(s)")
            if n is None:
                # Absent HERE. If a delegated host stamped a size for this
                # manifest, that is the pool - say so beside the absence.
                for v in verified + failing + stale:
                    h = next((x for x in delegated if x["rel"] == v["rel"]), None)
                    if h and h.get("manifest") == key and v["records"] is not None:
                        line += (f" here; {v['records']} record(s) on "
                                 f"{v['host']} as of {v['last_run_at']}")
            st.note(line)

        if unrunnable:
            # A DEFECT, not a hold: the harvester's own declaration names THIS
            # host as the one that runs it, and this host cannot. Time does
            # not install ffmpeg or Vision, and a hold on a question the code
            # can now answer (`host`) is how #77 paged every Saturday.
            # held_items name the harvester AND each missing tool, so a new
            # harvester or a new requirement pages and an unchanged one does
            # not. Raised after the work above so it is recorded
            # (work_done_before_stop) and the shrink check still ran.
            items = sorted(f"{rel} needs {m.split(':', 1)[0]}"
                           for rel, ms in unrunnable for m in ms)
            st.named_stop(
                "HARVESTER_TOOLING_ABSENT",
                f"{len(unrunnable)} harvester(s) declared for host {host!r} "
                f"cannot run on it: " + "; ".join(
                    f"{rel} requires {', '.join(m.split(':', 1)[0] for m in ms)}"
                    for rel, ms in unrunnable)
                + ". Its manifest cannot grow from here, and every clip it would "
                f"have screened was neither accepted nor rejected. The other "
                f"{ran} harvester(s) ran and their pools are committed.",
                detail={"unrunnable": {rel: ms for rel, ms in unrunnable},
                        "host": host, "platform": sys.platform, "pool": after},
                held_items=items,
                unblock="The declaration is wrong about where this can run. "
                        "Set `host` in its HARVESTER literal to a host that "
                        "has the tooling (known: "
                        + ", ".join(f"{k} = {v['what']}" for k, v in HOSTS.items())
                        + "), or add the tool to that host's image. Do NOT "
                        "install a different OCR engine and do NOT accept "
                        "clips unverified; loop/r2.py:verify_shorts records "
                        "why both were rejected.")

        if failing:
            st.named_stop(
                "DELEGATED_HARVEST_FAILING",
                f"{len(failing)} delegated harvester(s) ran on their host "
                f"inside the {policy['delegated_max_age_days']}-day cap and did "
                f"not succeed: " + "; ".join(
                    f"{v['rel']} on {v['host']} exited {v['exit']} at "
                    f"{v['last_run_at']} (last success: "
                    f"{v['last_success_at'] or 'never'})" for v in failing)
                + ". The host is running; the harvester is not finishing. "
                f"Its pool is not growing and the stamp's output tail says why.",
                detail={"failing": failing, "host": host,
                        "stamps": str(STAMPS.relative_to(ROOT))},
                unblock="Read `tail` for that harvester in "
                        "loop/state/harvest_runs.json and fix the harvester "
                        "or the host it runs on; then let its next scheduled "
                        "run stamp a success.")

        if stale:
            st.named_stop(
                "DELEGATED_HARVEST_STALE",
                f"{len(stale)} delegated harvester(s) have not been run by "
                f"their host inside the {policy['delegated_max_age_days']}-day "
                f"cap: " + "; ".join(
                    f"{v['rel']} on {v['host']} (last run: "
                    f"{v['last_run_at'] or 'never'}; last success: "
                    f"{v['last_success_at'] or 'never'})" for v in stale)
                + ". This host cannot run it and the host that can has been "
                f"silent, so the pool it feeds has stopped growing.",
                detail={"stale": stale, "host": host,
                        "stamps": str(STAMPS.relative_to(ROOT))},
                unblock="; ".join(sorted({
                    f"{v['host']}: {HOSTS[v['host']]['start']}" for v in stale}))
                        + ". The next run there stamps loop/state/"
                          "harvest_runs.json and this clears on its own.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="check the gates and report the pool; harvest nothing")
    ap.add_argument("--host", default=DEFAULT_HOST, choices=sorted(HOSTS),
                    help="which scheduled process this is: it runs the "
                         "harvesters declared for that host and verifies "
                         "the rest (default: ci)")
    a = ap.parse_args()
    return run(dry_run=a.dry_run, host=a.host)


if __name__ == "__main__":
    raise SystemExit(main())
