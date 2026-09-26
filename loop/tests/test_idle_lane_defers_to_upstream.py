"""An idle lane downstream of an idle lane is green; a BLIND one still pages.

THE INCIDENT. Run 36152459224 (2026-09-25, reach lane) exited 3 on
LOCALIZATIONS_UP_TO_DATE: nine consecutive days with nothing to localize,
over a cap of eight. The ledger had not grown since 2026-09-15 because the
upload lane had nothing to upload, and that lane said so every day in its
own classified stops (NOTHING_SHELVED, which paged on its own cap on 09-22,
then SCRIPTS_AWAITING_PROMOTION). The localize lane's counter was a second
clock on the upload lane's condition. loop/common.py _upstream_explains()
now lets a rule that names its `upstream_stage` stay green past its cap
ONLY when the idle is provably upstream's.

WHAT THIS PROVES, with common.disposition() against a scratch stops dir:
  1. the 2026-09-25 state (real timestamps from loop/state) past the cap is
     self_resolving, and says it is upstream's, naming the upstream code;
  2. a video that arrived AFTER the idle streak began, with the lane still
     finding nothing to do, pages (the blind-lane case the cap exists for);
  3. an upstream whose last run SUCCEEDED (no streak) pages;
  4. a stop that cannot say what its newest input is pages;
  5. past `max_consecutive_upstream_idle` it pages whatever upstream says;
  6. inside the cap it is self_resolving exactly as before;
  7. every rule naming `upstream_stage` names a stage that really exists
     and carries an outer bound, and the lane that raises the code puts
     `newest_input_at` in its detail;
  8. end to end: the real loop/localize.py on the real repo state, with a
     scratch copy of the committed streaks, exits 0 on day 10 (was exit 3).

Hard-fails if it examines zero cases. Never writes committed state.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent

SCRATCH = Path(tempfile.mkdtemp(prefix="idle-upstream-"))
os.environ["LOOP_STOPS_DIR"] = str(SCRATCH / "stops")
(SCRATCH / "stops").mkdir()
sys.path.insert(0, str(LOOP))
import common  # noqa: E402

CODE, STAGE, UP = "LOCALIZATIONS_UP_TO_DATE", "localize", "cloud-upload"
# The committed state behind run 36152459224, verbatim.
BEGAN = "2026-09-17T15:11:15+00:00"
NEWEST = "2026-09-15T14:01:58+00:00"
UP_REC = {"code": "SCRIPTS_AWAITING_PROMOTION", "count": 4,
          "first_at": "2026-09-23T11:31:17+00:00",
          "last_at": "2026-09-25T14:14:01+00:00"}


def seed(upstream: dict | None) -> None:
    d = {STAGE: {"code": CODE, "count": 9, "first_at": BEGAN,
                 "last_at": "2026-09-25T15:11:30+00:00"}}
    if upstream:
        d[UP] = upstream
    (SCRATCH / "stops" / "_streaks.json").write_text(json.dumps(d))


def disp(streak: int, detail) -> tuple[str, str]:
    return common.disposition(STAGE, CODE, detail, streak)


def check() -> list[str]:
    fails, examined = [], 0
    rule = common.stop_policy()["self_resolving"].get(CODE) or {}
    cap = int(rule.get("max_consecutive", 0))
    outer = int(rule.get("max_consecutive_upstream_idle", 0))
    if rule.get("upstream_stage") != UP or not cap or outer <= cap:
        return [f"{CODE} no longer names upstream_stage={UP!r} with an outer "
                f"bound above its cap: {rule!r}"]
    ok = {"videos": ["x"], "newest_input_at": NEWEST}

    # 1. the incident, past the cap: green, and says why
    examined += 1
    seed(UP_REC)
    d, why = disp(cap + 1, ok)
    if d != "self_resolving":
        fails.append(f"the 2026-09-25 state (nothing uploaded since before the "
                     f"idle streak, {UP} mid-streak) still pages: {d}: {why}")
    elif UP not in why or UP_REC["code"] not in why:
        fails.append(f"the green verdict does not name {UP} and its stop: {why}")

    # 2. something arrived during the streak and the lane saw nothing: blind
    examined += 1
    seed(UP_REC)
    d, why = disp(cap + 1, dict(ok, newest_input_at="2026-09-20T09:00:00+00:00"))
    if d != "needs_human":
        fails.append(f"a video uploaded after the idle streak began, with the "
                     f"lane still up to date, did not page: {d}")

    # 3. upstream's last run succeeded (no streak) and nothing reached us
    examined += 1
    seed(None)
    d, _ = disp(cap + 1, ok)
    if d != "needs_human":
        fails.append(f"with {UP} not stopped, an idle streak past the cap did "
                     f"not page: {d}")

    # 4. no newest_input_at: cannot prove anything, so it pages
    examined += 1
    seed(UP_REC)
    d, _ = disp(cap + 1, {"videos": ["x"]})
    if d != "needs_human":
        fails.append(f"a stop with no newest_input_at stayed green past the "
                     f"cap: {d}")

    # 5. the outer bound
    examined += 1
    seed(UP_REC)
    d, _ = disp(outer + 1, ok)
    if d != "needs_human":
        fails.append(f"past max_consecutive_upstream_idle ({outer}) it still "
                     f"did not page: {d}")
    d, _ = disp(outer, ok)
    if d != "self_resolving":
        fails.append(f"at exactly the outer bound ({outer}) it paged early: {d}")

    # 6. inside the cap nothing changed
    examined += 1
    seed(None)
    d, _ = disp(cap, {"videos": ["x"]})
    if d != "self_resolving":
        fails.append(f"inside its cap {CODE} is no longer self_resolving: {d}")

    # 7. every upstream declaration is real, bounded, and fed
    policy = common.stop_policy().get("self_resolving") or {}
    declared = {c: r for c, r in policy.items()
                if isinstance(r, dict) and r.get("upstream_stage")}
    if not declared:
        fails.append("no rule declares upstream_stage - the guard governs "
                     "nothing")
    stages = set()
    for path in sorted(LOOP.glob("*.py")):
        for n in ast.walk(ast.parse(path.read_text())):
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and getattr(n.targets[0], "id", None) == "LANE"
                    and isinstance(n.value, ast.Constant)):
                stages.add(n.value.value)
    for c, r in declared.items():
        examined += 1
        if r["upstream_stage"] not in stages:
            fails.append(f"{c} names upstream_stage {r['upstream_stage']!r}, "
                         f"which no loop/*.py LANE is")
        if int(r.get("max_consecutive_upstream_idle", 0)) <= int(
                r.get("max_consecutive", 0)):
            fails.append(f"{c} has no outer bound above its cap")
        raisers = [p for p in LOOP.glob("*.py")
                   if f'"{c}"' in p.read_text()]
        if not raisers or not all("newest_input_at" in p.read_text()
                                  for p in raisers):
            fails.append(f"{c} is raised by {[p.name for p in raisers]}, which "
                         f"do not all put newest_input_at in its detail - the "
                         f"upstream check would always escalate, or never run")

    # 8. the real lane, the real repo state, day 10
    examined += 1
    stops = SCRATCH / "lane-stops"
    shutil.copytree(ROOT / "loop" / "state" / "stops", stops)
    streaks = json.loads((stops / "_streaks.json").read_text())
    streaks[STAGE] = {"code": CODE, "count": 9, "first_at": BEGAN,
                      "last_at": "2026-09-25T15:11:30+00:00"}
    streaks[UP] = UP_REC
    (stops / "_streaks.json").write_text(json.dumps(streaks))
    ledger = json.loads((ROOT / "loop" / "state" / "ledger.json").read_text())
    live = [r for r in ledger["published"]
            if r.get("video_id") and not r.get("retired_at")]
    newest = max(r.get("uploaded_at") or r.get("published_at") or ""
                 for r in live)
    env = dict(os.environ, LOOP_STOPS_DIR=str(stops), LOOP_DRY_RUN="1",
               GITHUB_ACTIONS="", OPENROUTER_API_KEY="")
    r = subprocess.run([sys.executable, str(LOOP / "localize.py")],
                       capture_output=True, text=True, env=env, cwd=str(ROOT),
                       timeout=300)
    out = r.stdout + r.stderr
    if f"[{CODE}]" not in out:
        # The real state has moved on (a new upload is not localized yet, or
        # the lane now has work). Then the lane is not idle and case 8 has
        # nothing to prove - but it must not silently pass either.
        if "[work]" not in out and r.returncode != 0:
            fails.append(f"the real localize lane neither idled nor worked: "
                         f"exit {r.returncode}: {out.strip()[-500:]}")
        else:
            print(f"  (case 8: the real lane is not idle today - exit "
                  f"{r.returncode}; cases 1-7 carry the proof)")
    elif newest >= BEGAN:
        print("  (case 8: a video was uploaded after the 09-17 streak began; "
              "the real lane correctly does not claim upstream)")
    elif r.returncode != 0 or "SELF-RESOLVING" not in out:
        fails.append(f"the real localize lane on day 10 of an upstream-"
                     f"explained idle did not exit 0 self-resolving: exit "
                     f"{r.returncode}: {out.strip()[-600:]}")

    if examined == 0:
        fails.append("examined ZERO cases - this test cannot reach what it "
                     "governs")
    print(f"inspected {examined} idle-upstream case(s), "
          f"{len(declared)} rule(s) declaring an upstream")
    return fails


if __name__ == "__main__":
    try:
        f = check()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for x in f:
        print(f"  ✗ {x}")
    print("all green - an idle lane defers to its idle upstream, and a blind "
          "one still pages" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
