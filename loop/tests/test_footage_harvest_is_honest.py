"""The footage lane may not report an environment failure as a rights outcome,
and the species manifest on main must be the last VERIFIED set, whole.

CONFIRMED on run 34672456430 (2026-09-12, `loop · Sat 04:00 UTC · grow the
rights-cleared footage pool`, issue #77), two defects under one red run:

1. research/imagery_video.py rejected 379 of 379 NOAA video posts at "gate
   A-credit". Not one of them was a rights decision. Gates B and C read the
   burned-in credit with Apple's Vision framework off frames ffmpeg pulls from
   the clip; ubuntu-latest has neither, so every clip that PASSED gate A then
   raised FileNotFoundError('ffmpeg') inside screen(), and screen() gave every
   exception the default label "A-credit". The same 100% rejection is in run
   33943991250 a week earlier, counted as [work]. channel/imagery/video_rights.json
   has never existed. Reproduced locally: strip ffmpeg from PATH and a clip the
   gate accepts on this Mac comes back "A-credit | screening error: ... 'ffmpeg'".

   Now: the harvester DECLARES what it requires of the host (`requires` in its
   HARVESTER literal), loop/host_tools.py is the one table that probes those
   names, the lane checks it BEFORE spawning the harvester, a screener exception
   is labelled E-screening-error and never a gate, and a host that cannot run
   the harvester takes a HELD stop naming the harvester and each missing tool.
   The other harvesters still run. Nothing is loosened: no OCR substitute, no
   clip accepted unverified.

2. channel/imagery/species.json on main was the HALF-WRITTEN manifest the
   failing run committed (28e3a56): 29 records and four entries in `failures`.
   #79 fixed the write-before-raise and restored rights.json, and did not
   restore species.json. It is restored here from 22629d4 -- the last set that
   verified -- and every record is re-checked against the bytes on disk. A
   manifest with a non-empty `failures` list is a partial index, and the lane's
   own docstring says the pool only ever accumulates.

2026-09-19, section 4 rewritten: the tooling stop above was HELD as a
question for the owner (macOS runner, or the Mac's batch?) and a hold can only
re-ask - #77 closed, #91 opened. The harvester now declares `host: mac-batch`
and the Linux lane verifies the Mac's stamp instead of holding. Section 4 pins
that; loop/tests/test_delegated_harvest_is_verified.py pins the class.

Every check hard-fails on an empty set. Negative proofs restore each defect and
show the failure return.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
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
IMAGERY = os.path.join(ROOT, "channel", "imagery")
SPECIES = os.path.join(IMAGERY, "species.json")
RIGHTS = os.path.join(IMAGERY, "rights.json")
VIDEO_SRC = os.path.join(RESEARCH, "imagery_video.py")
LANE_SRC = os.path.join(LOOP, "footage_lane.py")
PY = sys.executable

for p in (LOOP, RESEARCH):
    if p not in sys.path:
        sys.path.insert(0, p)

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {name}")
    else:
        print(f"  ✗ {name}{(': ' + detail) if detail else ''}")
        fails.append(name)


def sha_of(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def path_without(tool: str) -> str:
    """A PATH on which `tool` does not resolve, keeping everything else.

    Real absence, not a mock: the harvester and the lane both ask
    shutil.which(), and this is what the Linux runner's PATH answers.
    """
    keep = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and not os.path.exists(os.path.join(d, tool)):
            keep.append(d)
    return os.pathsep.join(keep)


def harvesters() -> list[dict]:
    """Every research/imagery*.py HARVESTER literal, read with ast."""
    out = []
    for name in sorted(os.listdir(RESEARCH)):
        if not (name.startswith("imagery") and name.endswith(".py")):
            continue
        path = os.path.join(RESEARCH, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "HARVESTER"
                    for t in node.targets):
                spec = dict(ast.literal_eval(node.value))
                spec["rel"] = f"research/{name}"
                spec["src"] = open(path, encoding="utf-8").read()
                out.append(spec)
    return out


def load_video_module(source: str, tag: str):
    """Import a (possibly mutated) copy of imagery_video.py as a fresh module.

    Written next to the real file so its own `HERE`-relative imports and
    paths resolve identically; removed afterwards.
    """
    path = os.path.join(RESEARCH, f"_iv_{tag}.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    try:
        spec = importlib.util.spec_from_file_location(f"_iv_{tag}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.remove(path)


# A row exactly as discover() shapes it, with a credit gate A accepts offline
# (live=False skips the item-page read). Nothing here touches the network:
# with ffmpeg absent, one() raises before the first request.
GATE_A_PASSING_ROW = {
    "post_id": 1, "item_url": "https://oceanexplorer.noaa.gov/x",
    "title": "Deep-sea snailfish", "description": "",
    "acf_credit": "NOAA Ocean Exploration", "date": "2026-01-01",
    "files": [{"attachment_id": 1, "url": "https://example.invalid/a.mp4",
               "width": 1920, "height": 1080, "seconds": 30, "bytes": 1}],
}


def main() -> int:
    global examined

    # ================================================== 1. species manifest
    species = json.load(open(SPECIES, encoding="utf-8"))
    rights = json.load(open(RIGHTS, encoding="utf-8"))
    assets = species.get("assets") or []
    if not assets:
        print("FAIL: species.json holds zero assets; nothing to verify")
        return 1
    examined += len(assets)
    check("species.json carries no failures (a manifest with failures is the "
          "half-written index run 34672456430 committed)",
          species.get("failures") == [],
          f"failures={species.get('failures')!r}")
    check("species.json asset_count agrees with its assets",
          species.get("asset_count") == len(assets),
          f"{species.get('asset_count')} vs {len(assets)}")
    bad = []
    for a in assets:
        got = sha_of(os.path.join(IMAGERY, a["local_file"]))
        if got != a.get("sha256"):
            bad.append((a["local_file"], "absent" if got is None else "sha mismatch"))
    check(f"all {len(assets)} species records verify against the bytes on disk",
          not bad, str(bad))
    by_id = {int(r["local_file"].split("__")[1]): r for r in rights["assets"]}
    from_rights = [a for a in assets if a.get("origin") == "rights.json"]
    check("species.json holds rights.json-origin records (else this check is empty)",
          bool(from_rights))
    unresolved = []
    for a in from_rights:
        mid = int(a["local_file"].split("__")[1])
        r = by_id.get(mid)
        if not r or r["sha256"] != a["sha256"]:
            unresolved.append(mid)
    check(f"every one of {len(from_rights)} rights.json-origin species records "
          "resolves to a rights record with the same sha256", not unresolved,
          f"unresolved media ids: {unresolved}")
    # The four the run lost, by id. If any of these go missing again, the
    # message names them rather than a count.
    lost = {12013, 15248, 16065, 28649}
    present = {int(a["local_file"].split("__")[1]) for a in from_rights}
    check("the four records run 34672456430 dropped (12013 15248 16065 28649) "
          "are back", lost <= present, f"still missing: {sorted(lost - present)}")

    # ================================================ 2. requires declared
    hs = harvesters()
    if not hs:
        print("FAIL: found zero HARVESTER declarations under research/")
        return 1
    examined += len(hs)
    import host_tools                                      # noqa: PLC0415
    for h in hs:
        needs = set()
        if re.search(r"\bffmpeg\b", h["src"]):
            needs.add("ffmpeg")
        if re.search(r"\bocr\(|swiftc|import Vision", h["src"]):
            needs.add("vision-ocr")
        declared = set(h.get("requires") or [])
        check(f"{h['rel']}: every host tool its source uses is in `requires` "
              f"(uses {sorted(needs) or 'none'})", needs <= declared,
              f"declared {sorted(declared)}")
        try:
            host_tools.missing(declared)
            probeable = True
        except host_tools.UnknownHostTool as exc:
            probeable = False
            detail = str(exc)
        check(f"{h['rel']}: every name in `requires` has a probe in "
              "loop/host_tools.py", probeable, locals().get("detail", ""))
    check("an unknown requirement is a loud error, never a quiet pass",
          _raises(host_tools.UnknownHostTool,
                  lambda: host_tools.missing(["tesseract"])))
    check("the video harvester declares both ffmpeg and vision-ocr",
          any(h["rel"] == "research/imagery_video.py"
              and {"ffmpeg", "vision-ocr"} <= set(h.get("requires") or [])
              for h in hs))
    import footage_lane as _fl                             # noqa: PLC0415
    check("the video harvester declares host mac-batch (the only scheduled "
          "process with ffmpeg and Vision) and re-fetches NOAA's index",
          any(h["rel"] == "research/imagery_video.py"
              and h.get("host") == "mac-batch"
              and "--refresh" in (h.get("args") or [])
              for h in hs))
    for h in hs:
        check(f"{h['rel']}: its host is one loop/footage_lane.py schedules",
              not _raises(_fl.UnknownHarvestHost, lambda h=h: _fl.host_of(h)))
    check("a harvester requiring host tooling names a host that HAS it, or "
          "the ci lane would take HARVESTER_TOOLING_ABSENT every Saturday",
          all(_fl.host_of(h) != "ci" for h in hs if h.get("requires")))

    # ================================================= 3. screen() labels
    src = open(VIDEO_SRC, encoding="utf-8").read()
    no_ffmpeg = path_without("ffmpeg")
    saved = os.environ["PATH"]
    os.environ["PATH"] = no_ffmpeg
    try:
        assert shutil.which("ffmpeg") is None, "PATH still resolves ffmpeg"
        V = load_video_module(src, "fixed")
        acc, rej = V.screen([dict(GATE_A_PASSING_ROW)], workers=1, live=False)
        examined += 1
        check("with ffmpeg absent, a gate-A-passing clip is rejected as "
              "E-screening-error, not as a rights gate",
              not acc and len(rej) == 1 and rej[0]["gate"] == V.SCREENING_ERROR
              and "ffmpeg" in rej[0]["reason"],
              f"acc={len(acc)} rej={rej and {k: rej[0].get(k) for k in ('gate', 'reason')}}")
        msg = _systemexit_message(lambda: V.harvest([], rej))
        check("RULE 0 names SCREENING ERRORS when that is why nothing was accepted",
              msg is not None and "SCREENING ERRORS" in msg and "ffmpeg" in msg,
              str(msg)[:160])
        check("missing_tooling() reports ffmpeg on this PATH",
              any(m.startswith("ffmpeg:") for m in V.missing_tooling()),
              str(V.missing_tooling()))
        # ---- NEGATIVE PROOF: put the mislabel back, one line at a time.
        # (a) wrap() drops the gate from its screening-error record
        broken_a = src.replace(
            'return None, {"reason": f"screening error: {exc}",\n'
            '                          "gate": SCREENING_ERROR}',
            'return None, {"reason": f"screening error: {exc}"}')
        # (b) and the collector defaults it to A-credit again
        broken_b = broken_a.replace(
            'if "gate" not in r:\n'
            '                    raise RuntimeError(f"screen(): rejection without a gate: {r}")',
            'r.setdefault("gate", "A-credit")')
        check("negative proof mutates the source (both substitutions took)",
              broken_a != src and broken_b != broken_a)
        B = load_video_module(broken_b, "broken")
        acc, rej = B.screen([dict(GATE_A_PASSING_ROW)], workers=1, live=False)
        check("negative proof: with the defect restored the same clip is "
              "reported as gate A-credit (the run-34672456430 mislabel)",
              not acc and rej and rej[0]["gate"] == "A-credit",
              f"{rej and rej[0].get('gate')}")
        msg = _systemexit_message(lambda: B.harvest([], rej))
        check("negative proof: and RULE 0 then blames the gate, not the host",
              msg is not None and "SCREENING ERRORS" not in msg)

        # (c) the CLI refuses before any request on a host that cannot finish
        r = subprocess.run([PY, VIDEO_SRC, "--audit", "--limit", "1"],
                           capture_output=True, text=True, cwd=ROOT,
                           env=dict(os.environ, PATH=no_ffmpeg), timeout=120)
        check("`imagery_video.py --audit` on a host without ffmpeg exits 78 and "
              "names HARVESTER_TOOLING_ABSENT before discovering anything",
              r.returncode == 78 and "HARVESTER_TOOLING_ABSENT" in r.stderr
              and "multimedia posts" not in r.stdout,
              f"rc={r.returncode} stderr={r.stderr[:200]!r}")

        # ============================================ 4. the lane's verdict
        # STRENGTHENED 2026-09-19. Until then this section pinned that the
        # Linux lane took HARVESTER_TOOLING_ABSENT for the video harvester and
        # earned a HOLD on it. That hold was a question ("where should the
        # Vision work run?") and a hold can only re-ask: the owner closed #77,
        # it paged again as #91, and would have every Saturday. The harvester
        # now DECLARES its host (mac-batch) and the Linux lane VERIFIES it
        # through loop/state/harvest_runs.json. What this pins now:
        #   * ffmpeg absent as ci -> the video harvester is not spawned, not
        #     held, and not a tooling stop; it is reported as delegated;
        #   * the verdict is the STAMP's: fresh -> green with the harvest
        #     counted as verified work; absent -> DELEGATED_HARVEST_STALE.
        # test_delegated_harvest_is_verified.py covers the rest of the class.
        stops = tempfile.mkdtemp(prefix="hwk-footage-stops-")
        stamps_p = os.path.join(stops, "harvest_runs.json")
        # No gh either: nothing here may depend on the live state of a real
        # issue (loop/held.py:_issue_is_open trusts the hold without gh).
        lane_path = os.pathsep.join(
            d for d in no_ffmpeg.split(os.pathsep)
            if not os.path.exists(os.path.join(d, "gh")))
        env = dict(os.environ, PATH=lane_path, LOOP_STOPS_DIR=stops,
                   LOOP_HARVEST_STAMPS=stamps_p)
        env.pop("GITHUB_REPOSITORY", None)     # never ask gh about a real issue
        import datetime as _dt                                 # noqa: PLC0415
        fresh_at = (_dt.datetime.now(_dt.timezone.utc)
                    - _dt.timedelta(days=1)).isoformat(timespec="seconds")
        json.dump({"research/imagery_video.py": {
            "host": "mac-batch", "last_run_at": fresh_at,
            "last_success_at": fresh_at, "ok": True, "exit": 0,
            "records": 113, "tail": []}}, open(stamps_p, "w"))
        r1 = subprocess.run([PY, LANE_SRC, "--dry-run", "--host", "ci"],
                            capture_output=True, text=True, cwd=ROOT, env=env,
                            timeout=300)
        stopfiles = [f for f in os.listdir(stops) if f.endswith("-imagery-harvest.json")]
        examined += 1
        check("ci lane with ffmpeg absent and a fresh Mac stamp takes NO stop "
              "and exits 0", r1.returncode == 0 and not stopfiles,
              f"rc={r1.returncode} stops={stopfiles} tail={r1.stdout[-400:]!r}")
        check("the video harvester is reported as delegated to mac-batch",
              "research/imagery_video.py is delegated to mac-batch" in r1.stdout)
        check("and never spawned on this host (no gate line, no tooling line)",
              "research/imagery_video.py: rights gate" not in r1.stdout
              and "research/imagery_video.py: this host lacks" not in r1.stdout)
        check("the Mac's harvest is counted as VERIFIED work with its pool size",
              "[work] verified research/imagery_video.py is harvesting on "
              "mac-batch (delegated)" in r1.stdout and "113 record(s)" in r1.stdout,
              r1.stdout[-600:])
        check("the pool report names the Mac's count beside the local absence",
              "video_rights.json absent here; 113 record(s) on mac-batch" in r1.stdout)
        check("the three ci harvesters still ran (dry) first",
              r1.stdout.count("[work] would harvest") == 3)
        check("HARVESTER_TOOLING_ABSENT is not raised for a delegated harvester",
              "HARVESTER_TOOLING_ABSENT" not in r1.stdout)

        # Now take the stamp away: the SAME host, SAME PATH, and the verdict
        # flips to a named stop about the Mac - not about ffmpeg.
        json.dump({}, open(stamps_p, "w"))
        r2 = subprocess.run([PY, LANE_SRC, "--dry-run", "--host", "ci"],
                            capture_output=True, text=True, cwd=ROOT, env=env,
                            timeout=300)
        stopfiles = [f for f in os.listdir(stops) if f.endswith("-imagery-harvest.json")]
        rec = json.load(open(os.path.join(stops, stopfiles[0]))) if stopfiles else {}
        check("with no Mac stamp the ci lane takes DELEGATED_HARVEST_STALE",
              rec.get("code") == "DELEGATED_HARVEST_STALE",
              f"rc={r2.returncode} code={rec.get('code')} tail={r2.stdout[-400:]!r}")
        check("which is owner_action: green, recorded, at the top of the digest",
              r2.returncode == 0 and rec.get("disposition") == "owner_action"
              and "NEEDS A SECRET ONLY SHE HOLDS" in r2.stdout,
              f"rc={r2.returncode} disposition={rec.get('disposition')}")
        check("the stop says how to start the host, not which binary is missing",
              "bin/batch-session.sh" in (rec.get("unblock") or "")
              and "ffmpeg" not in (rec.get("unblock") or ""), str(rec.get("unblock")))
        check("the runnable harvesters still ran first (work_done_before_stop)",
              len(rec.get("work_done_before_stop") or []) >= 3,
              str(rec.get("work_done_before_stop")))
        shutil.rmtree(stops, ignore_errors=True)

        # ---- NEGATIVE PROOF for the lane: with every probe answering
        # "present" AND the Mac's stamp fresh, the ci lane runs its three
        # harvesters, verifies the fourth, and takes no stop.
        import footage_lane                                # noqa: PLC0415
        saved_tools = dict(host_tools.HOST_TOOLS)
        for k, (d, _) in saved_tools.items():
            host_tools.HOST_TOOLS[k] = (d, lambda: True)
        stops2 = tempfile.mkdtemp(prefix="hwk-footage-stops2-")
        stamps2 = os.path.join(stops2, "harvest_runs.json")
        json.dump({"research/imagery_video.py": {
            "host": "mac-batch", "last_run_at": fresh_at,
            "last_success_at": fresh_at, "ok": True, "exit": 0,
            "records": 113, "tail": []}}, open(stamps2, "w"))
        os.environ["LOOP_STOPS_DIR"] = stops2
        os.environ["LOOP_HARVEST_STAMPS"] = stamps2
        try:
            rc = footage_lane.run(dry_run=True, host="ci")
            took_stop = False
        except SystemExit as exc:
            rc, took_stop = exc.code, True
        finally:
            host_tools.HOST_TOOLS.clear()
            host_tools.HOST_TOOLS.update(saved_tools)
            os.environ.pop("LOOP_STOPS_DIR", None)
            os.environ.pop("LOOP_HARVEST_STAMPS", None)
        check("negative proof: with the tooling present and the Mac fresh the "
              "ci lane takes no stop, runs its own three and verifies the "
              "fourth", rc == 0 and not took_stop
              and not [f for f in os.listdir(stops2) if "imagery-harvest" in f],
              f"rc={rc} stop={took_stop}")
        shutil.rmtree(stops2, ignore_errors=True)
    finally:
        os.environ["PATH"] = saved

    # ================================================== 5. classified
    policy = json.load(open(os.path.join(LOOP, "stop_policy.json"), encoding="utf-8"))
    check("HARVESTER_TOOLING_ABSENT is a held code with a reminder cadence",
          isinstance(policy.get("held", {}).get("codes", {})
                     .get("HARVESTER_TOOLING_ABSENT", {}).get("reminder_days"), int))
    check("HARVESTER_TOOLING_ABSENT stays needs_human (a wrong host declaration "
          "is a defect; it may not go quiet)",
          "HARVESTER_TOOLING_ABSENT" in policy.get("needs_human", {})
          and "HARVESTER_TOOLING_ABSENT" not in policy.get("self_resolving", {})
          and "HARVESTER_TOOLING_ABSENT" not in policy.get("owner_action", {}))
    check("DELEGATED_HARVEST_STALE is owner_action with a cap and an escalation",
          isinstance(policy.get("owner_action", {}).get("DELEGATED_HARVEST_STALE", {})
                     .get("max_consecutive"), int)
          and bool(policy["owner_action"]["DELEGATED_HARVEST_STALE"].get("escalation")))
    check("DELEGATED_HARVEST_FAILING is needs_human (the host ran it and it broke)",
          "DELEGATED_HARVEST_FAILING" in policy.get("needs_human", {})
          and "DELEGATED_HARVEST_FAILING" not in policy.get("owner_action", {})
          and "DELEGATED_HARVEST_FAILING" not in policy.get("self_resolving", {}))
    check("CLEARED_POOL_SHRANK stays needs_human (a shrink is a defect, never held)",
          "CLEARED_POOL_SHRANK" in policy.get("needs_human", {})
          and "CLEARED_POOL_SHRANK" not in policy.get("held", {}).get("codes", {})
          and "CLEARED_POOL_SHRANK" not in policy.get("self_resolving", {}))

    print(f"\nexamined {examined} item(s), {len(fails)} failure(s)")
    if examined == 0:
        print("FAIL: examined nothing")
        return 1
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        return 1
    return 0


def _raises(exc_type, fn) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:                                      # noqa: BLE001
        return False
    return False


def _systemexit_message(fn):
    try:
        fn()
    except SystemExit as exc:
        return str(exc.code)
    return None


if __name__ == "__main__":
    sys.exit(main())
