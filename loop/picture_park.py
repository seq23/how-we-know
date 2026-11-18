#!/usr/bin/env python3
"""FOOTAGE SELF-HEAL, THEN PARK: a voiced long-form that cannot get its picture never blocks the channel.

    python loop/picture_park.py heal              # before the render sweep: widen each failing episode's search
    python loop/picture_park.py record SLUG LOG   # a render failed: counts the night if LOG says NO_SUBJECT_PICTURE
    python loop/picture_park.py ok SLUG           # a render passed: a parked episode rejoins the queue
    python loop/picture_park.py skip              # slugs the render sweep leaves alone tonight (parked, retry not due)
    python loop/picture_park.py settle            # park / retire, one morning line each; every night, paused or not
    python loop/picture_park.py show

The owner, 18 Nov 2026: "this should not involve me it should self heal: 9
recorded episodes fail every night because there aren't enough cleared
pictures of their subjects." They were voiced, so loop/supply_gate.py counted
them as made-and-waiting (14 made, 33 days of supply, the 7-day cap holding
new long-forms until ~15 Dec), and they failed NO_SUBJECT_PICTURE every night
from 3 Nov.

  1. HEAL. A night after a footage failure, `heal` widens THAT episode's
     search through the harvesters the repo already uses, under their own
     licence gates (nothing here loosens one): research/wide_footage.py (NOAA
     OER + Commons PD/CC0) with more results per subject each failed night,
     research/imagery_stock_video.py (Pixabay/Mixkit free licence, wording
     re-checked) with a higher per-episode cap, and, from the second failed
     night, a RELATED-SUBJECT widening of its shot list (visuals/shot_list.py
     widen: more filmable subjects of the same title, free route). A Money
     episode tops up the Money set (money imagery only, her 9 Nov call).
     Generic b-roll is NOT added: the long-form picture is only moving
     imagery of the subject (owner, 3 Nov 2026; visuals/longform_picture.py).
  2. PARK. PARK_AFTER failed nights in a row (no pass in between) -> parked:
     out of the supply count (supply_gate.longform_made) and out of the
     render sweep, never deleted, its voice kept, and one line in her
     morning Notices: "parked: <title> - not enough cleared footage; retried
     <dates>". Every RETRY_EVERY days a parked episode is healed and tried
     again; one that renders rejoins the queue (a "rejoined" line).
  3. RETIRE. Parked RETIRE_AFTER days -> retired: a note, still not deleted;
     no more retries.

Rule 0: `settle` always prints one OUTPUT line with the counts; floor 0,
because a night with nothing failing for footage is a real result. State:
loop/state/picture_park.json (Mac-owned, pushed by loop/mac_sync.py). Proven
by loop/tests/test_picture_park.py.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

STATE = Path(os.environ.get("LOOP_PICTURE_PARK") or ROOT / "loop" / "state" / "picture_park.json")
PARK_AFTER = 3          # failed nights in a row
RETRY_EVERY = 7         # days between retries of a parked episode
RETIRE_AFTER = 60       # days parked
FOOTAGE_FAIL = "NO_SUBJECT_PICTURE"


def night(now: _dt.datetime | None = None) -> str:
    """A night belongs to the evening it starts on (02:00 Wed is Tuesday's)."""
    now = now or _dt.datetime.now()
    return ((now - _dt.timedelta(days=1)).date() if now.hour < 12 else now.date()).isoformat()


def load(path: Path | None = None) -> dict:
    p = path or STATE
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def save(state: dict, path: Path | None = None) -> None:
    p = path or STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


def _eps(state: dict) -> dict:
    return state.setdefault("episodes", {})


def parked(state: dict | None = None) -> set[str]:
    """Slugs out of the supply count: parked or retired."""
    state = load() if state is None else state
    return {s for s, e in _eps(state).items() if e.get("parked_at")}


def _last_try(e: dict) -> str:
    return max([e.get("parked_at") or ""] + list(e.get("fails") or []) + list(e.get("retries") or []))


def retry_due(e: dict, today: str) -> bool:
    if not e.get("parked_at") or e.get("retired_at"):
        return False
    last = _dt.date.fromisoformat(_last_try(e))
    return (_dt.date.fromisoformat(today) - last).days >= RETRY_EVERY


def skip(state: dict | None = None, today: str | None = None) -> list[str]:
    """What the render sweep leaves alone tonight."""
    state = load() if state is None else state
    today = today or night()
    return sorted(s for s, e in _eps(state).items()
                  if e.get("parked_at") and not retry_due(e, today))


def _path(sub: str) -> None:
    """APPEND, never prepend: visuals/ has its own domains.py, and a prepended
    path would shadow loop/domains.py for everything imported after it."""
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.append(p)


def title_of(slug: str) -> str:
    try:
        _path("visuals")
        import shot_list as SL                                 # noqa: PLC0415
        return SL.title_of(slug)
    except Exception:                                          # noqa: BLE001
        return slug


def _note(state: dict, text: str) -> None:
    state.setdefault("pending_notes", []).append(text)


def _dates(e: dict) -> str:
    ds = sorted(set(list(e.get("fails") or []) + list(e.get("retries") or [])))
    short = [_dt.date.fromisoformat(d).strftime("%-d %b") for d in ds]
    return ", ".join(short[:2] + ["..."] + short[-2:]) if len(short) > 5 else ", ".join(short)


# ------------------------------------------------------------------ events
def record_fail(state: dict, slug: str, reason: str, today: str) -> str:
    e = _eps(state).setdefault(slug, {"fails": []})
    e["reason"] = reason[:240]
    if e.get("parked_at"):
        if today not in (e.get("retries") or []) and today != e["parked_at"]:
            e.setdefault("retries", []).append(today)
        return "retry failed; stays parked"
    if today not in e["fails"]:
        e["fails"].append(today)
    return f"footage short, night {len(e['fails'])} of {PARK_AFTER}"


def record_ok(state: dict, slug: str, today: str) -> str:
    e = _eps(state).pop(slug, None)
    if not e:
        return "nothing recorded"
    if e.get("parked_at"):
        _note(state, f"rejoined: {title_of(slug)} - enough cleared footage found; "
                     f"it rendered on {today} and is back in the queue")
        state.setdefault("rejoined", {})[slug] = today
        return "healed: rejoins the queue"
    return "healed before parking"


def settle(state: dict, today: str) -> dict:
    """Park PARK_AFTER nights in a row; retire RETIRE_AFTER days parked."""
    out = {"parked_new": [], "retired_new": [], "failing": 0}
    for slug, e in sorted(_eps(state).items()):
        if not e.get("parked_at"):
            out["failing"] += 1
            if len(set(e.get("fails") or [])) >= PARK_AFTER:
                e["parked_at"] = today
                out["parked_new"].append(slug)
                _note(state, f"parked: {title_of(slug)} - not enough cleared footage; "
                             f"retried {_dates(e)}")
        elif not e.get("retired_at") and (
                _dt.date.fromisoformat(today) - _dt.date.fromisoformat(e["parked_at"])).days >= RETIRE_AFTER:
            e["retired_at"] = today
            out["retired_new"].append(slug)
            _note(state, f"retired: {title_of(slug)} - parked {RETIRE_AFTER} days without enough "
                         f"cleared footage; kept on the Mac with its voice, never deleted")
    eps = _eps(state)
    out["parked"] = sorted(s for s, e in eps.items() if e.get("parked_at") and not e.get("retired_at"))
    out["retired"] = sorted(s for s, e in eps.items() if e.get("retired_at"))
    out["retry_due"] = sorted(s for s, e in eps.items() if retry_due(e, today))
    return out


def flush_notes(state: dict, send=None) -> list[str]:
    """Each pending line once into her morning Notices; a line that could not
    be written stays pending for the next night."""
    if send is None:
        import whisper_upload as WU                            # noqa: PLC0415
        send = WU.morning_line
    left, said = [], []
    for line in state.get("pending_notes") or []:
        r = str(send(line))
        (said if r.startswith("morning line written") else left).append(line)
        print(f"  {line}  [{r}]")
    state["pending_notes"] = left
    return said


# ------------------------------------------------------------------ the heal
def to_heal(state: dict, today: str) -> list[str]:
    """Failing (not parked) episodes, and parked ones whose weekly retry is due."""
    return sorted(s for s, e in _eps(state).items()
                  if (not e.get("parked_at") and e.get("fails")) or retry_due(e, today))


def widen(slug: str, tries: int) -> list[str]:
    """One widening pass for one episode through the repo's own harvesters,
    each under its own licence gate. Every step is best-effort: a step that
    fails is said and the next one still runs."""
    import domains as D                     # loop/domains.py, before the paths below  # noqa: PLC0415
    _path("research")
    _path("visuals")
    done = []
    dom = D.domain_of_slug(slug)
    if dom == "money-and-business":
        try:
            import imagery_stock_video as STOCK                # noqa: PLC0415
            STOCK.harvest_money(per=6 + 3 * tries)
            done.append(f"money set +{3 * tries}/subject")
        except (Exception, SystemExit) as e:                   # noqa: BLE001
            done.append(f"money set: {str(e)[:80]}")
        return done
    if tries >= 2:
        try:
            import shot_list as SL                             # noqa: PLC0415
            added = SL.widen(slug)
            done.append(f"shot list +{len(added)} related subject(s)")
        except (Exception, SystemExit) as e:                   # noqa: BLE001
            done.append(f"shot list widen: {str(e)[:80]}")
    try:
        import wide_footage as WF                              # noqa: PLC0415
        r = WF.harvest([slug], per_subject=min(16, 4 + 4 * tries))
        done.append(f"NOAA/Commons +{r['new']} clip(s)")
    except (Exception, SystemExit) as e:                       # noqa: BLE001
        done.append(f"NOAA/Commons: {str(e)[:80]}")
    try:
        import imagery_stock_video as STOCK                    # noqa: PLC0415
        STOCK.SHOT_LIST_CAP = max(STOCK.SHOT_LIST_CAP, 24 + 12 * tries)
        STOCK.harvest([slug])
        done.append(f"stock cap {STOCK.SHOT_LIST_CAP}")
    except (Exception, SystemExit) as e:                       # noqa: BLE001
        done.append(f"stock: {str(e)[:80]}")
    return done


def heal(state: dict, today: str, widen_fn=None) -> dict:
    widen_fn = widen_fn or widen
    healed = {}
    for slug in to_heal(state, today):
        e = _eps(state)[slug]
        tries = len(set(e.get("fails") or [])) + len(e.get("retries") or [])
        steps = widen_fn(slug, tries)
        e.setdefault("widened", []).append({"night": today, "steps": steps})
        e["widened"] = e["widened"][-6:]
        healed[slug] = steps
    return healed


# ------------------------------------------------------------------ CLI
def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    state, today = load(), night()
    if cmd == "record" and len(argv) >= 2:
        log = Path(argv[2]) if len(argv) > 2 else None
        text = log.read_text(errors="replace") if log and log.exists() else ""
        if FOOTAGE_FAIL not in text:
            print(f"  picture park: {argv[1]} failed for another reason; not counted")
            return 0
        line = next((ln for ln in reversed(text.splitlines()) if FOOTAGE_FAIL in ln), FOOTAGE_FAIL)
        print(f"  picture park: {argv[1]}: {record_fail(state, argv[1], line.strip(), today)}")
        save(state)
        return 0
    if cmd == "ok" and len(argv) == 2:
        r = record_ok(state, argv[1], today)
        if r != "nothing recorded":
            print(f"  picture park: {argv[1]}: {r}")
            save(state)
        return 0
    if cmd == "skip":
        print(" ".join(skip(state, today)))
        return 0
    if cmd == "heal":
        h = heal(state, today)
        save(state)
        for s, steps in h.items():
            print(f"  heal {s}: {'; '.join(steps)}")
        print(f"OUTPUT picture-heal: {len(h)} episode(s) widened")
        return 0
    if cmd == "settle":
        r = settle(state, today)
        said = flush_notes(state)
        save(state)
        print(f"OUTPUT picture-park: {len(r['parked'])} parked ({len(r['parked_new'])} new), "
              f"{r['failing'] - len(r['parked_new'])} failing and healing, "
              f"{len(r['retry_due'])} retry due, {len(r['retired'])} retired "
              f"({len(r['retired_new'])} new); {len(said)} morning line(s)")
        return 0
    if cmd == "show":
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
