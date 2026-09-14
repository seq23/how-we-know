"""The render gate HOLDS the episode that fails; it does not halt the ones that pass.

    .venv/bin/python loop/render_gate.py            # judge, write the hold, exit 0
    .venv/bin/python loop/render_gate.py --heal     # ...and start self-heal for each held one
    .venv/bin/python loop/render_gate.py --show     # print the current hold and exit

WHAT WENT WRONG, and the exact shape of it. From 6 September 2026 the daily
Mac upload lane (bin/loop-backfill-daily.sh) and the nightly batch
(bin/batch-session.sh) each asked V13 and V24 and, on ANY failure, refused to
ship ANYTHING: "nothing was uploaded this run". One materials episode,
why-is-steel-so-strong, had rendered at 9.90 minutes against a 10.0-minute
floor - six seconds short - and eight finished, passing episodes sat behind it
for a week. Five publish slots (9-23 October) went unfilled. The self-heal for a
short episode already existed (loop/extend.py); it had run once, been rejected,
and nothing retried it. That is the "one bad file deleting half her morning"
defect, and this module is the fix for its upload half.

WHAT THIS DOES INSTEAD.

  * Runs the same two validators. Every failure names a slug (`<slug>: ...`),
    so the failing slugs are collected into a HOLD and written to
    loop/state/render_hold.json. Both upload routes consult it:
    loop/backfill.py:library_pending skips held slugs, and loop/r2.py:push
    refuses to shelve them, so a held render can reach YouTube by no path.
    Everything not held ships as before.
  * With --heal, each slug held for being under the floor is handed to
    loop/extend.py, which authors sourced narration and drops the stale plan
    so the next batch pass re-plans, re-voices only the moved beats and
    re-renders. extend.py already retries a rejected extension once with the
    validator's objection in the prompt; the retry that worked on 13 Sep is
    the same one this invokes every day.
  * The stop it emits is RENDER_HELD - a HELD stop in the repo's taxonomy
    (loop/held.py): it names exactly what is waiting (held_items=) and how it
    clears (unblock=), so it is loud once, silent while unchanged, and loud
    again if the held set grows. "8 uploaded, 1 held: why-is-steel-so-strong
    (9.90 min)" is a sentence; "nothing was uploaded" was not.

RULE 0. If both validators examined zero renders on a machine that holds
renders, that is RENDER_GATE_EMPTY, a real defect, exit 3 - never a clean pass.
A validator that looked at nothing has proved nothing.

TESTABLE WITHOUT A RENDER. --from-json takes a file holding the two validator
results as dicts, and HWK_EXTEND_CMD replaces the heal command, so
loop/tests/test_render_gate_holds_not_halts.py plants a sub-floor episode
among passing ones and proves the others ship and the heal is invoked.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

from common import Stage, read_json, week_id, write_json      # noqa: E402

# Overridable so the test suite never writes the loop's own hold (run_all.py
# does the same for the stops directory with LOOP_STOPS_DIR).
HOLD = Path(os.environ.get("LOOP_RENDER_HOLD") or ROOT / "loop" / "state" / "render_hold.json")


def _slug_of(failure: str) -> str | None:
    """`<slug>: reason` -> slug. A failure that names no slug holds nothing."""
    head, sep, _ = failure.partition(": ")
    if not sep or " " in head or not head:
        return None
    return head


def judge(results: list[dict]) -> dict:
    """Pure. Turn validator results into {held: {slug: [reasons]}, examined, unnamed}."""
    held: dict[str, list[str]] = {}
    unnamed: list[str] = []
    examined = 0
    for d in results:
        examined += int(d.get("examined") or 0)
        for f in d.get("failures") or d.get("fails") or []:
            slug = _slug_of(f)
            if slug is None:
                unnamed.append(f)
            else:
                held.setdefault(slug, []).append(f)
    return {"held": held, "examined": examined, "unnamed": unnamed}


def load_hold() -> dict:
    return read_json(HOLD, default={"held": {}, "at": None, "week": None})


def held_slugs() -> set[str]:
    """What the two upload routes ask. Missing file = nothing held."""
    return set((load_hold().get("held") or {}).keys())


def _heal(slugs: list[str], reasons: dict[str, list[str]], st: Stage) -> None:
    """Start the self-heal for each slug held under the floor. Never raises:
    a refused extension is reported, and the hold stands either way."""
    cmd = os.environ.get("HWK_EXTEND_CMD")
    base = cmd.split() if cmd else [sys.executable, str(LOOP / "extend.py")]
    for slug in slugs:
        under_floor = any("under the" in r and "floor" in r for r in reasons[slug])
        if not under_floor:
            st.note(f"{slug}: held for a clipped render, which extend.py cannot "
                    f"fix - it needs a re-render (delete renders/{slug}-final.mp4 "
                    f"and run bin/batch-session.sh)")
            continue
        r = subprocess.run(base + ["--slug", slug], cwd=ROOT,
                           capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
        if r.returncode == 0:
            st.work(f"self-heal started for {slug}: {tail[0]}")
        else:
            st.note(f"self-heal refused for {slug} (rc={r.returncode}): {tail[0]}")


def run(results: list[dict], heal: bool, write: bool = True) -> int:
    verdict = judge(results)
    held = verdict["held"]
    with Stage("render-gate", week_id(),
               zero_work_hint="Both validators ran and every render passed; "
                              "this stage records that as work.") as st:
        if verdict["examined"] == 0:
            st.named_stop(
                "RENDER_GATE_EMPTY",
                "V13 and V24 examined zero renders between them, on a machine "
                "that is supposed to hold renders. A gate that looked at nothing "
                "has passed nothing.",
                detail={"results": [d.get("name") for d in results]},
                unblock="Check renders/*-final.mp4 exist and that loop/validate.py "
                        "can probe them (ffprobe on PATH). Nothing was shipped.")
        for f in verdict["unnamed"]:
            st.note(f"validator failure names no slug, so it holds nothing: {f}")
        if write:
            write_json(HOLD, {"held": held, "week": week_id(),
                              "at": __import__("datetime").datetime.now(
                                  __import__("datetime").timezone.utc).isoformat()})
        if not held:
            st.work(f"render gate CLEAN: {verdict['examined']} render(s) examined, "
                    f"nothing held")
            return 0
        st.note(f"{len(held)} render(s) held, {verdict['examined'] - len(held)} "
                f"pass and ship as normal")
        if heal:
            _heal(sorted(held), held, st)
        items = [f"{s} - {'; '.join(r.split(': ', 1)[-1] for r in held[s])}"
                 for s in sorted(held)]
        st.named_stop(
            "RENDER_HELD",
            f"{len(held)} finished render(s) held back; every other finished "
            f"episode ships this run. Held: " + ", ".join(sorted(held)),
            detail={"held": held, "examined": verdict["examined"]},
            unblock="A render under the floor heals itself: extend.py has been "
                    "asked for more sourced narration and the next "
                    "bin/batch-session.sh re-voices and re-renders it. A clipped "
                    "render needs re-rendering. The hold lifts on the run after "
                    "the validators pass.",
            held_items=items)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heal", action="store_true",
                    help="start loop/extend.py for each slug held under the floor")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--from-json", default=None,
                    help="tests: a file holding the validator results as a list of dicts")
    a = ap.parse_args()
    if a.show:
        h = load_hold()
        for s, why in sorted((h.get("held") or {}).items()):
            print(f"  HELD {s}: {'; '.join(why)}")
        print(f"{len(h.get('held') or {})} held (as of {h.get('at')})")
        return 0
    if a.from_json:
        results = json.load(open(a.from_json))
    else:
        import validate                                          # noqa: PLC0415
        results = [validate.v13_render_not_clipped().as_dict(),
                   validate.v24_render_duration_floor().as_dict()]
    return run(results, heal=a.heal)


if __name__ == "__main__":
    raise SystemExit(main())
