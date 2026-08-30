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
    "validator": "A validator failed. Nothing publishes against a failed validator.",
    "manual": "Tripped by hand by the owner.",
}

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
    write_json(FLAG, b)
    return b


def guard(stage_name: str) -> None:
    """Called at the top of every publishing stage.

    Exits 3 (NAMED STOP) if the breaker is tripped. It does not raise a bare
    exception, because a tripped breaker is a correct, expected state — it must
    read as a named halt, never as a crash.
    """
    b = load()
    if b.get("state") != "tripped":
        return
    with Stage(stage_name) as st:
        st.named_stop(
            "BREAKER_TRIPPED",
            f"publishing is halted: {b.get('cause')} — {b.get('detail')}",
            detail=b,
            unblock="Fix the underlying cause, then: "
                    "python loop/breaker.py reset --note \"<what you fixed>\"",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
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
