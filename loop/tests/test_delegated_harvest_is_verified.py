"""A harvester delegated to another host is VERIFIED there, not held here.

WHAT HAPPENED. From 2026-09-12 the Saturday footage lane (ubuntu-latest) could
not run research/imagery_video.py - gates B and C need ffmpeg and Apple Vision
- and took HARVESTER_TOOLING_ABSENT as a HELD stop asking the owner where the
work should run (#77). She closed the issue on 09-14; the hold paged again on
09-19 (#91) and would have every Saturday forever, because a hold on a
question only a person can answer cannot clear itself. The owner's standing
instruction in loop/stop_policy.json: "I should never get a named stop --
everything should be automated. It should self heal."

THE FIX IS A CLASS, NOT AN EXEMPTION. A HARVESTER declares `host` - the
scheduled process that runs it (loop/footage_lane.py:HOSTS). Every host runs
what is declared for it and VERIFIES the rest through the stamps in
loop/state/harvest_runs.json. This file pins the class against a planted
harvester and planted stamps, never the live ones:

  1. delegated + fresh stamp            -> no stop, exit 0, counted as verified
                                           work and printed as delegated
  2. delegated + no run inside the cap  -> DELEGATED_HARVEST_STALE, owner_action
                                           (green), and RED past its cap
  3. delegated + failed run in the cap  -> DELEGATED_HARVEST_FAILING, exit 3
  4. NOT delegated + tooling missing    -> HARVESTER_TOOLING_ABSENT, still red
  5. the host that owns a harvester RUNS it and STAMPS it, whatever it exits,
     and does not re-run one inside harvest.interval_days
  6. an empty registry is a stop, never a green "nothing delegated"
  7. an unknown host name is a loud error at discovery
  8. bin/batch-session.sh runs the lane as mac-batch on BOTH its paths and
     pushes the stamp with explicit paths - never channel/imagery
  9. every code above is classified where the taxonomy says

Negative proofs: 2 and 3 are 1 with the stamp changed; 4 is the same lane and
the same PATH as 1 with only the declaration's host changed. Hard-fails if it
examines nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
RESEARCH = os.path.join(ROOT, "research")
LANE_SRC = os.path.join(LOOP, "footage_lane.py")
PY = sys.executable
sys.path.insert(0, LOOP)

import footage_lane as FL   # noqa: E402
import host_tools           # noqa: E402

fails: list[str] = []
examined = 0
PROBE = "imagery_zzprobe.py"          # sorts after the real four; globbed by the lane
PROBE_REL = f"research/{PROBE}"


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if ok:
        print(f"  ok  {name}")
    else:
        print(f"  ✗ {name}{(': ' + detail) if detail else ''}")
        fails.append(name)


def iso(days_ago: float) -> str:
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(days=days_ago)).isoformat(timespec="seconds")


def plant_probe(host: str, requires: list[str], exit_code: int = 0) -> None:
    """A harvester that declares `host`, does no network, and exits as told."""
    src = f'''"""Planted by loop/tests/test_delegated_harvest_is_verified.py. Delete me."""
import sys
HARVESTER = {{
    "domain": "deep-sea-ocean-science",
    "gate": "probe_gate",
    "manifest": "channel/imagery/zzprobe-does-not-exist.json",
    "args": [],
    "scheduled": True,
    "what": "a planted probe harvester",
    "requires": {requires!r},
    "host": {host!r},
}}


def probe_gate():
    return True


if __name__ == "__main__":
    print("probe ran on", sys.platform)
    sys.exit({exit_code})
'''
    with open(os.path.join(RESEARCH, PROBE), "w", encoding="utf-8") as fh:
        fh.write(src)


def unplant() -> None:
    try:
        os.remove(os.path.join(RESEARCH, PROBE))
    except FileNotFoundError:
        pass


def path_without(*tools: str) -> str:
    keep = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and not any(os.path.exists(os.path.join(d, t)) for t in tools):
            keep.append(d)
    return os.pathsep.join(keep)


def run_lane(host: str, stamps: dict, stops: str, path: str | None = None,
             dry_run: bool = True) -> tuple[int, str, dict]:
    """Run the real lane as a subprocess against planted stamps. Returns
    (rc, stdout, stop record or {})."""
    stamps_p = os.path.join(stops, "harvest_runs.json")
    json.dump(stamps, open(stamps_p, "w"))
    env = dict(os.environ, LOOP_STOPS_DIR=stops, LOOP_HARVEST_STAMPS=stamps_p,
               LOOP_DRY_RUN="1")
    env.pop("GITHUB_REPOSITORY", None)          # never ask gh about a real issue
    if path is not None:
        env["PATH"] = path
    args = [PY, LANE_SRC, "--host", host] + (["--dry-run"] if dry_run else [])
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, env=env,
                       timeout=300)
    stage = FL.HOSTS[host]["stage"]
    recs = [f for f in os.listdir(stops) if f.endswith(f"-{stage}.json")]
    rec = json.load(open(os.path.join(stops, recs[0]))) if recs else {}
    return r.returncode, r.stdout + r.stderr, rec


def main() -> int:
    hosts = sorted(FL.HOSTS)
    if len(hosts) < 2:
        print("FAIL: fewer than two hosts in loop/footage_lane.py:HOSTS; "
              "delegation cannot be exercised")
        return 1
    other = next(h for h in hosts if h != "ci")
    policy = FL.harvest_policy()
    cap = policy["delegated_max_age_days"]
    interval = policy["interval_days"]
    no_tools = path_without("ffmpeg", "gh")
    # The real video harvester is delegated to the Mac. Give it a fresh stamp
    # in every planted stamps file below so its verdict never leaks into the
    # probe's: this file is about the CLASS, and the probe is the instance.
    VIDEO_FRESH = {"research/imagery_video.py": {
        "host": "mac-batch", "last_run_at": iso(1), "last_success_at": iso(1),
        "ok": True, "exit": 0, "records": 113, "tail": []}}

    try:
        # ---------------------------------------------------- 1. fresh
        plant_probe(host=other, requires=["ffmpeg"])
        stops = tempfile.mkdtemp(prefix="hwk-deleg-1-")
        stamps = dict(VIDEO_FRESH, **{PROBE_REL: {
            "host": other, "last_run_at": iso(cap - 1),
            "last_success_at": iso(cap - 1), "ok": True, "exit": 0,
            "records": 7, "tail": ["probe ran"]}})
        rc, out, rec = run_lane("ci", stamps, stops, path=no_tools)
        check("1: a delegated harvester with a fresh stamp yields NO stop and "
              "the ci lane is green", rc == 0 and not rec,
              f"rc={rc} code={rec.get('code')} tail={out[-500:]!r}")
        check("1: it is printed as delegated, with its host, in the run",
              f"{PROBE_REL} is delegated to {other}" in out)
        check("1: the verification is a unit of work naming host, age and pool",
              re.search(rf"\[work\] verified {re.escape(PROBE_REL)} is harvesting "
                        rf"on {other} \(delegated\).*7 record\(s\)", out) is not None,
              out[-500:])
        check("1: the probe was never spawned or tooling-checked on ci",
              f"{PROBE_REL}: this host lacks" not in out
              and f"{PROBE_REL}: rights gate" not in out)
        shutil.rmtree(stops, ignore_errors=True)

        # ---------------------------------------------------- 2. stale
        stops = tempfile.mkdtemp(prefix="hwk-deleg-2-")
        stamps = dict(VIDEO_FRESH, **{PROBE_REL: {
            "host": other, "last_run_at": iso(cap + 1),
            "last_success_at": iso(cap + 1), "ok": True, "exit": 0,
            "records": 7, "tail": []}})
        rc, out, rec = run_lane("ci", stamps, stops, path=no_tools)
        check("2: a stamp older than the cap yields DELEGATED_HARVEST_STALE",
              rec.get("code") == "DELEGATED_HARVEST_STALE",
              f"rc={rc} code={rec.get('code')} tail={out[-400:]!r}")
        check("2: which is owner_action - green, recorded, never a red build "
              "for a Mac that is off", rc == 0
              and rec.get("disposition") == "owner_action"
              and "WAITING ON THE OWNER" in out,
              f"rc={rc} disp={rec.get('disposition')}")
        check("2: the stop names the host and how to start it",
              other in rec.get("message", "")
              and FL.HOSTS[other]["start"] in rec.get("unblock", ""),
              rec.get("unblock", ""))
        check("2: the stop record carries the stale harvester's stamp facts",
              any(v.get("rel") == PROBE_REL and v.get("state") == "stale"
                  for v in (rec.get("detail") or {}).get("stale", [])),
              str(rec.get("detail")))
        rc_a, _, rec_a = run_lane("ci", {}, stops, path=no_tools)
        check("2: NO stamp at all (never run) is stale too, not fresh",
              rc_a == 0 and rec_a.get("code") == "DELEGATED_HARVEST_STALE",
              f"rc={rc_a} code={rec_a.get('code')}")
        # Escalation: the same stop on consecutive runs goes RED past its cap.
        pol = json.load(open(os.path.join(LOOP, "stop_policy.json")))
        max_c = int(pol["owner_action"]["DELEGATED_HARVEST_STALE"]["max_consecutive"])
        shutil.rmtree(stops, ignore_errors=True)
        stops = tempfile.mkdtemp(prefix="hwk-deleg-2b-")
        rcs = [run_lane("ci", stamps, stops, path=no_tools)[0]
               for _ in range(max_c + 1)]
        check(f"2: green for {max_c} consecutive run(s), then RED - a Mac silent "
              f"for that long is no longer an errand",
              rcs[:max_c] == [0] * max_c and rcs[max_c] == 3, str(rcs))
        shutil.rmtree(stops, ignore_errors=True)

        # ---------------------------------------------------- 3. failing
        stops = tempfile.mkdtemp(prefix="hwk-deleg-3-")
        stamps = dict(VIDEO_FRESH, **{PROBE_REL: {
            "host": other, "last_run_at": iso(1),
            "last_success_at": iso(cap + 5), "ok": False, "exit": 78,
            "records": 7, "tail": ["HARVESTER_TOOLING_ABSENT: ..."]}})
        rc, out, rec = run_lane("ci", stamps, stops, path=no_tools)
        check("3: a FAILED run inside the cap yields DELEGATED_HARVEST_FAILING",
              rec.get("code") == "DELEGATED_HARVEST_FAILING",
              f"rc={rc} code={rec.get('code')}")
        check("3: which is a defect: needs_human, exit 3",
              rc == 3 and rec.get("disposition") == "needs_human",
              f"rc={rc} disp={rec.get('disposition')}")
        check("3: the stop names the exit code and where the output tail is",
              "exited 78" in rec.get("message", "")
              and "harvest_runs.json" in rec.get("unblock", ""),
              rec.get("message", ""))
        shutil.rmtree(stops, ignore_errors=True)

        # ---------------------------------------------------- 4. not delegated
        # NEGATIVE PROOF of the class boundary: the same lane, the same PATH,
        # the same missing tool - only the declaration's host changes.
        plant_probe(host="ci", requires=["ffmpeg"])
        stops = tempfile.mkdtemp(prefix="hwk-deleg-4-")
        rc, out, rec = run_lane("ci", dict(VIDEO_FRESH), stops, path=no_tools)
        check("4: a harvester declared for THIS host that this host cannot run "
              "still takes HARVESTER_TOOLING_ABSENT",
              rec.get("code") == "HARVESTER_TOOLING_ABSENT",
              f"rc={rc} code={rec.get('code')} tail={out[-400:]!r}")
        check("4: red on first report (needs_human), naming harvester and tool",
              rc == 3 and rec.get("disposition") == "needs_human"
              and f"{PROBE_REL} needs ffmpeg" in (rec.get("held_items") or []),
              f"rc={rc} disp={rec.get('disposition')} held={rec.get('held_items')}")
        check("4: its unblock points at the declaration's `host`, not at a "
              "decision for the owner",
              "`host`" in rec.get("unblock", "") and "Decide" not in rec.get("unblock", ""),
              rec.get("unblock", ""))
        shutil.rmtree(stops, ignore_errors=True)

        # ---------------------------------------------------- 5. the owner runs and stamps
        # In-process with every tool probe answering "present", so this holds
        # on a Linux runner too; the real video harvester is NOT DUE (fresh
        # planted stamp) so nothing reaches NOAA. The probe is spawned for
        # real and exits as told; the stamp must say so either way.
        plant_probe(host=other, requires=["ffmpeg"], exit_code=0)
        saved_tools = dict(host_tools.HOST_TOOLS)
        for k, (d, _) in saved_tools.items():
            host_tools.HOST_TOOLS[k] = (d, lambda: True)
        stops = tempfile.mkdtemp(prefix="hwk-deleg-5-")
        stamps_p = os.path.join(stops, "harvest_runs.json")
        ci_fresh = {rel: {"host": "ci", "last_run_at": iso(1),
                          "last_success_at": iso(1), "ok": True, "exit": 0,
                          "records": 1, "tail": []}
                    for rel in ("research/imagery.py",
                                "research/imagery_materials.py",
                                "research/imagery_species.py")}
        json.dump(dict(VIDEO_FRESH, **ci_fresh), open(stamps_p, "w"))
        os.environ["LOOP_STOPS_DIR"] = stops
        os.environ["LOOP_HARVEST_STAMPS"] = stamps_p
        os.environ["LOOP_DRY_RUN"] = "1"
        try:
            try:
                rc = FL.run(dry_run=False, host=other)
            except SystemExit as exc:
                rc = exc.code
            got = FL.stamps(stamps_p)
            probe_rec = got.get(PROBE_REL) or {}
            check("5: the owning host runs the probe for real and exits 0",
                  rc == 0, f"rc={rc}")
            check("5: and STAMPS it: host, ok, exit, week, last_success_at",
                  probe_rec.get("host") == other and probe_rec.get("ok") is True
                  and probe_rec.get("exit") == 0 and probe_rec.get("week")
                  and FL._when(probe_rec.get("last_success_at")) is not None,
                  str(probe_rec))
            check("5: a harvester inside harvest.interval_days is NOT re-run "
                  "(the real video harvester, stamped fresh, was skipped by name)",
                  FL.stamps(stamps_p)["research/imagery_video.py"]["last_run_at"]
                  == VIDEO_FRESH["research/imagery_video.py"]["last_run_at"])
            # and a FAILING probe is stamped as failing, not skipped
            plant_probe(host=other, requires=["ffmpeg"], exit_code=7)
            json.dump(dict(VIDEO_FRESH, **ci_fresh), open(stamps_p, "w"))
            try:
                rc2 = FL.run(dry_run=False, host=other)
            except SystemExit as exc:
                rc2 = exc.code
            bad = FL.stamps(stamps_p).get(PROBE_REL) or {}
            check("5: a harvester that exits non-zero is stamped ok=false with "
                  "its exit code and output tail - the other host can tell "
                  "'failing' from 'silent'",
                  bad.get("ok") is False and bad.get("exit") == 7
                  and "last_success_at" not in bad and bad.get("tail"),
                  str(bad))
            check("5: and the owning host itself stays green on it (the pool "
                  "is unchanged; the other host's verification is the alarm)",
                  rc2 == 0, f"rc={rc2}")
            # the freshness the OTHER host would now compute from that stamp
            st = FL.delegated_status({"rel": PROBE_REL, "host": other},
                                     FL.stamps(stamps_p), max_age_days=cap)
            check("5: delegated_status() reads that stamp as 'failing'",
                  st["state"] == "failing" and st["exit"] == 7, str(st))
            check(f"5: interval_days ({interval}) is below the cap ({cap}): a "
                  f"healthy host can never look stale",
                  0 < interval < cap)
        finally:
            host_tools.HOST_TOOLS.clear()
            host_tools.HOST_TOOLS.update(saved_tools)
            for k in ("LOOP_STOPS_DIR", "LOOP_HARVEST_STAMPS", "LOOP_DRY_RUN"):
                os.environ.pop(k, None)
        shutil.rmtree(stops, ignore_errors=True)
        unplant()

        # ---------------------------------------------------- 6. empty registry
        stops = tempfile.mkdtemp(prefix="hwk-deleg-6-")
        os.environ["LOOP_STOPS_DIR"] = stops
        saved_glob = FL.HARVESTER_GLOB
        FL.HARVESTER_GLOB = "zz-no-such-harvester-*.py"
        try:
            try:
                rc = FL.run(dry_run=True, host="ci")
                code = None
            except SystemExit as exc:
                rc = exc.code
                recs = [f for f in os.listdir(stops) if f.endswith("-imagery-harvest.json")]
                code = json.load(open(os.path.join(stops, recs[0])))["code"] if recs else None
        finally:
            FL.HARVESTER_GLOB = saved_glob
            os.environ.pop("LOOP_STOPS_DIR", None)
        check("6: pointed at an EMPTY registry the lane hard-fails by name "
              "(DOMAIN_HAS_NO_HARVESTER, exit 3) rather than verifying nothing",
              rc == 3 and code == "DOMAIN_HAS_NO_HARVESTER", f"rc={rc} code={code}")
        shutil.rmtree(stops, ignore_errors=True)
        check("6: delegated_status() on an empty stamps file is 'stale', never "
              "'fresh'", FL.delegated_status(
                  {"rel": "research/imagery_video.py", "host": "mac-batch"},
                  {}, max_age_days=cap)["state"] == "stale")

        # ---------------------------------------------------- 7. unknown host
        try:
            FL.host_of({"rel": "research/x.py", "host": "a-laptop-nobody-schedules"})
            loud = False
        except FL.UnknownHarvestHost:
            loud = True
        check("7: a harvester naming a host the lane has no schedule for is a "
              "loud error, never 'delegated to nowhere'", loud)
        try:
            FL.run(dry_run=True, host="nope")
            loud = False
        except FL.UnknownHarvestHost:
            loud = True
        check("7: --host with an unknown name refuses before the stage opens", loud)

        # ---------------------------------------------------- 8. the batch wires it
        batch = open(os.path.join(ROOT, "bin", "batch-session.sh")).read()
        if "harvest_footage()" not in batch:
            check("8: bin/batch-session.sh defines harvest_footage", False)
        else:
            b0 = batch.find("harvest_footage()")
            b1 = batch.find("\n}\n", b0)
            body = batch[b0:b1]
            check("8: harvest_footage runs loop/footage_lane.py --host mac-batch",
                  "loop/footage_lane.py --host mac-batch" in body)
            check("8: and pushes loop/state/harvest_runs.json through "
                  "loop/mac_sync.py push with explicit paths",
                  "loop/mac_sync.py push" in body
                  and "loop/state/harvest_runs.json" in body)
            check("8: and pulls first, so the cloud's stamps it verifies are current",
                  "loop/mac_sync.py pull" in body
                  and body.find("mac_sync.py pull") < body.find("footage_lane.py"))
            check("8: it never stages channel/imagery (5 GB of clips) or -A",
                  "channel/imagery" not in body and "add -A" not in body
                  and "add --all" not in body)
            stop_at = batch.find("NAMED STOP: nothing to do.")
            exit_at = batch.find("\n  exit 0\n", stop_at)
            block = batch[stop_at:exit_at] if stop_at >= 0 else ""
            check("8: the nothing-to-do path calls harvest_footage before its "
                  "exit 0 (the batch has been idle every night since 09-12)",
                  re.search(r"^\s*harvest_footage\s*$", block, re.M) is not None)
            calls = re.findall(r"^\s*harvest_footage\s*$", batch, re.M)
            check("8: the narrate-or-render path calls it too",
                  len(calls) >= 2, f"{len(calls)} call(s)")
            # Invocation lines, not comments: `$PY loop/footage_lane.py ...`.
            check("8: no bare footage_lane.py invocation outside the function",
                  all(b0 <= m.start() <= b1 for m in
                      re.finditer(r"^\s*(?:nice\s+-n\s+\d+\s+)?\$PY\s+loop/footage_lane\.py",
                                  batch, re.M))
                  and re.search(r"^\s*(?:nice\s+-n\s+\d+\s+)?\$PY\s+loop/footage_lane\.py",
                                body, re.M) is not None)
        wf = open(os.path.join(ROOT, ".github", "workflows",
                               "loop-imagery-harvest.yml")).read()
        check("8: the Saturday workflow runs the lane as host ci",
              "loop/footage_lane.py --host ci" in wf)

        # ---------------------------------------------------- 9. classified
        pol = json.load(open(os.path.join(LOOP, "stop_policy.json")))
        check("9: DELEGATED_HARVEST_STALE is owner_action only",
              "DELEGATED_HARVEST_STALE" in pol["owner_action"]
              and "DELEGATED_HARVEST_STALE" not in pol["needs_human"]
              and "DELEGATED_HARVEST_STALE" not in pol["self_resolving"])
        check("9: DELEGATED_HARVEST_FAILING is needs_human only",
              "DELEGATED_HARVEST_FAILING" in pol["needs_human"]
              and "DELEGATED_HARVEST_FAILING" not in pol["owner_action"]
              and "DELEGATED_HARVEST_FAILING" not in pol["self_resolving"])
        check("9: HARVESTER_TOOLING_ABSENT is needs_human and NOT self_resolving",
              "HARVESTER_TOOLING_ABSENT" in pol["needs_human"]
              and "HARVESTER_TOOLING_ABSENT" not in pol["self_resolving"])
        check("9: loop/config.json carries the two harvest numbers with a reason",
              isinstance(FL.config().get("harvest", {}).get("_why"), str)
              and cap > 0 and interval > 0)
    finally:
        unplant()
        for k in ("LOOP_STOPS_DIR", "LOOP_HARVEST_STAMPS", "LOOP_DRY_RUN"):
            os.environ.pop(k, None)

    print(f"\nexamined {examined} item(s), {len(fails)} failure(s)")
    if examined == 0:
        print("FAIL: examined nothing")
        return 1
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
