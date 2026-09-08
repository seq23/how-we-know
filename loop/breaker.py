"""The circuit breaker.

One flag halts **publishing** — upload and the public flip — without tearing
down the rest of the pipeline. Mining, drafting, validating, voicing and
rendering all continue while it is open, so the week's work still accumulates
and nothing has to be rebuilt when the breaker is reset.

Trip causes, all three from the brief:
  strike      a copyright or community strike on the channel
  retention   average view percentage below the floor for N consecutive videos
  validator   any validator failure in the drafting stage

Usage
    python loop/breaker.py status
    python loop/breaker.py trip  --cause validator --detail "test_directive_truth failed"
    python loop/breaker.py reset --note "fixed the directive in script 07"
    python loop/breaker.py guard --stage thu-upload      # exit 3 if tripped
"""
from __future__ import annotations

import argparse
import sys

from common import (STATE, EXIT_OK, EXIT_STOP, Stage, now, read_json,
                    write_json, summary)

FLAG = STATE / "breaker.json"

CAUSES = {
    "strike": "A copyright or community-guidelines strike on the channel.",
    "retention": "Average view percentage below the floor for consecutive videos.",
    # ADDED 2026-09-08, and it was a live crash, not a tidy-up.
    # loop/measure.py:breaker_cause() has returned {"cause": "domain"} since
    # the niche/format split was written, and both of its call sites do
    # `breaker.trip("retention" if cause["cause"] == "format" else "domain")`.
    # "domain" was not in this dict, so that call raised
    # `SystemExit: unknown cause 'domain'` from inside the measure Stage - a
    # bare non-zero exit, no named stop, no breaker actually tripped, on the
    # exact path that exists to protect the channel from a failing niche. It
    # was unreachable while deep sea was the only domain and became reachable
    # the day materials-and-manufacturing went live.
    "domain": "One domain is below the duration floor while others hold. The "
              "niche is not working, not the format.",
    "validator": "A validator failed. Nothing publishes against a failed validator.",
    "manual": "Tripped by hand by the owner.",
}

# Causes a machine may clear by re-testing the condition. `strike` and `manual`
# are deliberately absent: a strike is cleared by YouTube and a hand-thrown
# breaker is a decision, and re-testing neither is something code can do.
AUTO_RESETTABLE = ("validator", "retention", "domain")

CLOSED = {"state": "closed", "tripped_at": None, "cause": None,
          "detail": None, "history": []}


def load() -> dict:
    return read_json(FLAG, default=dict(CLOSED))


def is_tripped() -> bool:
    return load().get("state") == "tripped"


def trip(cause: str, detail: str) -> dict:
    if cause not in CAUSES:
        raise SystemExit(f"unknown cause {cause!r}; one of {sorted(CAUSES)}")
    b = load()
    if b["state"] == "tripped":
        # Already open. Record the additional cause; do not lose the first one.
        b.setdefault("also", []).append(
            {"at": now(), "cause": cause, "detail": detail})
    else:
        b.update({"state": "tripped", "tripped_at": now(),
                  "cause": cause, "detail": detail})
        b.setdefault("history", []).append(
            {"event": "trip", "at": now(), "cause": cause, "detail": detail})
    write_json(FLAG, b)
    return b


def reset(note: str) -> dict:
    b = load()
    was = b.get("cause")
    b.setdefault("history", []).append(
        {"event": "reset", "at": now(), "cleared_cause": was, "note": note})
    b.update({"state": "closed", "tripped_at": None, "cause": None,
              "detail": None})
    b.pop("also", None)
    b.pop("reported_by", None)      # the cascade owner belongs to one trip only
    write_json(FLAG, b)
    return b


def recheck(b: dict) -> tuple[bool, str]:
    """Is the condition that tripped the breaker still true?

    (still_tripped, evidence). FAILS CLOSED in every uncertain case: if the
    check cannot be run at all, the answer is "still tripped", because a
    breaker that opens itself on the strength of a check that did not execute
    is worse than one that stays shut.
    """
    cause = b.get("cause")
    if cause not in AUTO_RESETTABLE:
        return True, (f"cause {cause!r} is not machine-checkable — a strike is "
                      f"cleared by YouTube and a manual trip is a decision")

    if cause == "validator":
        # Re-run the SAME validator set that tripped it (loop/draft.py calls
        # validate.run_all on the render queue). Not a subset, not a proxy.
        try:
            import validate                              # noqa: PLC0415
            from common import ROOT as _ROOT             # noqa: PLC0415
            q = read_json(_ROOT / "loop" / "render_queue.json", default=None)
            if not q or not q.get("items"):
                return True, ("the render queue is empty or unreadable, so the "
                              "validators cannot be re-run against anything. A "
                              "check that examined zero items may not clear a "
                              "breaker")
            ok, rows = validate.run_all(q["items"])
        except Exception as e:                           # noqa: BLE001
            # A missing package reads exactly like a failing validator in this
            # repo (PIL twice, numpy once). An unrun validator is not a passing
            # one, and it is certainly not grounds to resume publishing.
            return True, (f"the validators could not be run here ({type(e).__name__}: "
                          f"{e}), so nothing has been proven. Staying tripped")
        if ok:
            return False, f"all {len(rows)} validators pass again"
        bad = [r["validator"] for r in rows if "FAIL" in r.get("status", "")]
        return True, f"{len(bad)} validator(s) still failing: {', '.join(bad)}"

    # retention / domain. The measurement lane is the only thing entitled to
    # say retention recovered — it costs API quota and it already computes the
    # answer — so it clears the breaker itself (see loop/measure.py). Reaching
    # here means no measurement has contradicted the trip yet.
    return True, ("retention and domain trips are cleared by the weekly "
                  "measurement lane the moment its own breaker_cause() stops "
                  "returning a cause; no measurement since the trip has done so")


def autoreset() -> dict | None:
    """Re-test the tripped condition and close the breaker if it has passed.

    THE DEFECT THIS CLOSES. The breaker had a trip path and no automatic reset
    path at all, so a validator failure fixed in the very next commit left
    publishing halted until someone typed `loop/breaker.py reset`. Four lanes
    guard on it, so one stale flag presented as four red lanes every day and
    read as four separate problems.
    """
    b = load()
    if b.get("state") != "tripped":
        return None
    still, why = recheck(b)
    if still:
        return {"reset": False, "why": why}
    out = reset(f"automatic: {why} (cause was {b.get('cause')}: "
                f"{str(b.get('detail'))[:200]})")
    print(f"  [heal] circuit breaker RESET automatically — {why}", flush=True)
    summary(f"### ✅ Circuit breaker reset automatically\n{why}\n")
    return {"reset": True, "why": why, "breaker": out}


def clear_if(cause: str, note: str) -> dict | None:
    """Close the breaker if it is open for exactly `cause`, and only then.

    Called by the lane that OWNS the evidence — loop/measure.py for retention
    and domain — so the reset happens where the recovery is observed instead of
    waiting for a human to notice. Never touches a strike or a manual trip, and
    never touches a trip thrown for a different reason.
    """
    b = load()
    if b.get("state") != "tripped" or b.get("cause") != cause:
        return None
    if b.get("also"):
        # More than one thing tripped it. Clearing one is not clearing the
        # breaker, and silently doing so would resume publishing against a
        # cause nobody re-tested.
        print(f"  breaker stays tripped: {cause} cleared, but it also holds "
              f"{[a['cause'] for a in b['also']]}", flush=True)
        return None
    out = reset(f"automatic: {note}")
    print(f"  [heal] circuit breaker RESET automatically — {note}", flush=True)
    summary(f"### ✅ Circuit breaker reset automatically\n{note}\n")
    return out


def guard(stage_name: str) -> None:
    """Called at the top of every publishing stage.

    Three things happen here, in order:

    1. TRY TO HEAL. `autoreset()` re-tests the tripped condition; if it has
       passed, the breaker closes and this stage proceeds normally. Most trips
       in this repo's history were validator failures that were fixed within
       hours and left the flag standing for days.

    2. IF IT IS REALLY TRIPPED, STOP — every guarded lane, exactly as before.
       Nothing publishes against a live breaker.

    3. REPORT IT ONCE. Four lanes call this. Before, one flag produced four red
       jobs and four issue comments a day, which reads as four problems and
       triages as four. The FIRST stage to stop on a given trip owns the alarm
       and goes red; the others take a stop that names it and stay green. They
       are just as halted — the difference is only who wakes the owner.
    """
    b = load()
    if b.get("state") != "tripped":
        return
    healed = autoreset()
    if healed and healed.get("reset"):
        return
    b = load()

    owner = b.get("reported_by")
    if not owner:
        b["reported_by"] = {"stage": stage_name, "at": now(),
                            "tripped_at": b.get("tripped_at")}
        write_json(FLAG, b)
        owner = b["reported_by"]
    # A trip that was reset and re-thrown must be re-reported: the owner record
    # is only valid for the trip it was written against.
    elif owner.get("tripped_at") != b.get("tripped_at"):
        owner = {"stage": stage_name, "at": now(),
                 "tripped_at": b.get("tripped_at")}
        b["reported_by"] = owner
        write_json(FLAG, b)

    first = owner.get("stage") == stage_name
    with Stage(stage_name) as st:
        st.named_stop(
            "BREAKER_TRIPPED" if first else "BREAKER_TRIPPED_ALREADY_REPORTED",
            f"publishing is halted: {b.get('cause')} — {b.get('detail')}"
            + ("" if first else
               f". This is the SAME trip the '{owner.get('stage')}' stage "
               f"already raised; one flag halts four lanes and it is one "
               f"problem, not four."),
            detail={**b, "recheck": (healed or {}).get("why")},
            unblock=("This clears itself: the breaker is re-tested at the top "
                     "of every guarded lane and closes the moment the cause "
                     "has passed. A validator trip closes as soon as the "
                     "validators pass; a retention or domain trip closes on "
                     "the next weekly measurement that no longer sees the "
                     "breach. It stays open only for a strike or a manual "
                     "trip — for those: "
                     "python loop/breaker.py reset --note \"<what you fixed>\""),
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("autoreset")
    t = sub.add_parser("trip")
    t.add_argument("--cause", required=True, choices=sorted(CAUSES))
    t.add_argument("--detail", required=True)
    r = sub.add_parser("reset")
    r.add_argument("--note", required=True)
    g = sub.add_parser("guard")
    g.add_argument("--stage", required=True)
    a = ap.parse_args()

    if a.cmd == "status":
        b = load()
        state = b.get("state", "closed")
        print(f"breaker: {state.upper()}")
        if state == "tripped":
            print(f"  cause  : {b['cause']} — {CAUSES.get(b['cause'], '')}")
            print(f"  detail : {b['detail']}")
            print(f"  since  : {b['tripped_at']}")
            for extra in b.get("also", []):
                print(f"  also   : {extra['cause']} — {extra['detail']}")
            print("  publishing is HALTED; drafting and rendering continue.")
            summary(f"### ⛔ Circuit breaker TRIPPED — {b['cause']}\n{b['detail']}\n")
            return EXIT_STOP
        print(f"  {len(b.get('history', []))} event(s) in history")
        return EXIT_OK

    if a.cmd == "autoreset":
        out = autoreset()
        if out is None:
            print("breaker: CLOSED — nothing to reset")
        elif out["reset"]:
            print(f"breaker RESET automatically: {out['why']}")
        else:
            print(f"breaker stays TRIPPED: {out['why']}")
        return EXIT_OK

    if a.cmd == "trip":
        b = trip(a.cause, a.detail)
        print(f"breaker TRIPPED: {b['cause']} — {b['detail']}")
        print("publishing is halted. Drafting and rendering are unaffected.")
        summary(f"### ⛔ Circuit breaker TRIPPED — {a.cause}\n{a.detail}\n")
        return EXIT_OK

    if a.cmd == "reset":
        reset(a.note)
        print(f"breaker reset: {a.note}")
        return EXIT_OK

    if a.cmd == "guard":
        guard(a.stage)
        print(f"breaker closed; {a.stage} may proceed")
        return EXIT_OK

    return 1  # unreachable: argparse requires a subcommand


if __name__ == "__main__":
    sys.exit(main())
