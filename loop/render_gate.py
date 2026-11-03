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


# ---------------------------------------------------------------- picture floor
#
# CONFIRMED 2026-11-02 (hostile review, finding 1): 41 of 54 renders since
# mid-October carried no moving footage, 13 of them already scheduled, and
# this gate passed all 93 it examined - V13 and V24 measure length and
# clipping, never pictures. So a third result: the share of a render's beats
# that show a picture (its receipt's footage beats, plus the verified stills
# its plan placed). Below PICTURE_FLOOR the render is HELD and, with --heal or
# --picture-heal, moved aside and its plan dropped, so the next nightly batch
# re-plans it pictures-first and re-renders it from the same narration.
# FALLBACK, never a loop: a render made AFTER its picture heal airs as is,
# because the night already did the best the picture library allows.
PICTURE_FLOOR = 0.12          # the 15 Oct renders, the last ones with footage
STILL_SEGMENTS = {"species_image", "material_image"}
RENDERS = Path(os.environ.get("HWK_RENDERS") or ROOT / "renders")
PICTURE_HEAL = Path(os.environ.get("LOOP_PICTURE_HEAL")
                    or ROOT / "loop" / "state" / "picture_heal.json")


def picture_share(slug: str, renders: Path | None = None,
                  plans: Path | None = None) -> float | None:
    """Share of the render's beats that show a picture, or None if unmeasurable."""
    renders = renders or RENDERS
    rp, pp = renders / f"{slug}-final.mp4.render.json", (plans or ROOT / "plans") / f"{slug}.json"
    rec = json.loads(rp.read_text()) if rp.exists() else None
    plan = json.loads(pp.read_text()) if pp.exists() else None
    beats = (rec or {}).get("beats") or (len(plan) if plan else 0)
    if not beats:
        return None
    foot = int(((rec or {}).get("footage") or {}).get("footage_beats") or 0)
    # A plan re-written AFTER the render (a pictures-first re-plan) says
    # nothing about what that render shows: count its stills only if it is
    # older than the render.
    mp4 = renders / f"{slug}-final.mp4"
    stale = plan and mp4.exists() and pp.stat().st_mtime > mp4.stat().st_mtime
    stills = 0 if stale else sum(1 for b in (plan or []) if b.get("segment") in STILL_SEGMENTS)
    return min(1.0, (foot + stills) / beats)


def picture_floor(slugs: list[str], renders: Path | None = None,
                  plans: Path | None = None, heals: dict | None = None) -> dict:
    """A validator-shaped result: one `<slug>: picture floor ...` per failure."""
    renders = renders or RENDERS
    heals = read_json(PICTURE_HEAL, default={}) if heals is None else heals
    fails, examined, notes = [], 0, []
    for slug in slugs:
        f = renders / f"{slug}-final.mp4"
        if not f.exists():
            continue
        share = picture_share(slug, renders, plans)
        if share is None:
            continue
        examined += 1
        if share >= PICTURE_FLOOR:
            continue
        healed_at = (heals.get(slug) or {}).get("at_epoch")
        if healed_at and f.stat().st_mtime > healed_at:
            notes.append(f"{slug}: {share:.0%} pictures after its re-render; airs as is")
            continue
        fails.append(f"{slug}: picture floor: {share:.0%} of beats show a picture, "
                     f"under {PICTURE_FLOOR:.0%} - re-render pictures-first")
    return {"name": "picture-floor", "examined": examined, "failures": fails,
            "notes": notes}


def unaired_slugs() -> list[str]:
    """Queued renders not yet on YouTube (or taken off it to be re-made)."""
    import batch_queue                                         # noqa: PLC0415
    import ledger                                              # noqa: PLC0415
    import domains                                             # noqa: PLC0415
    live = {r["slug"] for r in ledger.load()["published"]
            if not r.get("withdrawn_at")}
    # Food builds its pictures in its own lane (visuals/food_episode.py: food
    # footage and kits), judged by the food contract, not this floor.
    return [s for s in batch_queue.queued_slugs() if s not in live
            and domains.domain_of_slug(s) != "food-science"]


def picture_heal(slugs: list[str], st, renders: Path | None = None) -> list[str]:
    """Move each render aside and drop its plan, so tonight re-renders it."""
    import hashlib                                             # noqa: PLC0415
    import time                                                # noqa: PLC0415
    renders = renders or RENDERS
    heals = read_json(PICTURE_HEAL, default={})
    sup_path = ROOT / "loop" / "state" / "superseded_renders.json"
    sup = read_json(sup_path, default={})
    moved = []
    for slug in slugs:
        f = renders / f"{slug}-final.mp4"
        if not f.exists():
            continue
        import approved_renders                                # noqa: PLC0415
        if approved_renders.protected(slug, renders):
            st.note(f"{slug}: owner-approved cut - never moved aside")
            continue
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        rec = {"sha256": h.hexdigest(), "bytes": f.stat().st_size,
               "superseded_at": time.strftime("%Y-%m-%d"),
               "why": "below the picture floor; re-rendered pictures-first"}
        old = sup.get(slug)
        if old and old.get("sha256") != rec["sha256"]:
            old.setdefault("also", []).append(rec)
        else:
            sup[slug] = rec
        f.rename(renders / f"{slug}-final.mp4.below-picture-floor")
        (ROOT / "plans" / f"{slug}.json").unlink(missing_ok=True)
        heals[slug] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "at_epoch": time.time(), "sha256": rec["sha256"]}
        moved.append(slug)
        st.work(f"{slug}: below the picture floor - render moved aside, plan "
                f"dropped; tonight's batch re-plans and re-renders it")
    write_json(sup_path, sup)
    write_json(PICTURE_HEAL, heals)
    return moved


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
    pic = [s for s in slugs if any("picture floor" in r for r in reasons[s])]
    if pic:
        picture_heal(pic, st)
    for slug in slugs:
        if slug in pic:
            continue
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
    ap.add_argument("--picture-heal", action="store_true",
                    help="heal (re-render) only; the nightly batch runs this before planning")
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
    if a.picture_heal:
        # The nightly batch, BEFORE it plans: re-render whatever is below the
        # picture floor tonight. Picture failures only; the hold file is left
        # to the full gate later in the night.
        r = picture_floor(unaired_slugs())
        for n in r["notes"]:
            print(f"  {n}")
        bad = sorted({f.split(": ", 1)[0] for f in r["failures"]})
        if not bad:
            print(f"picture floor: {r['examined']} unaired render(s), none below "
                  f"{PICTURE_FLOOR:.0%}")
            return 0
        with Stage("render-gate-pictures", week_id()) as st:
            picture_heal(bad, st)
        return 0
    if a.from_json:
        results = json.load(open(a.from_json))
    else:
        import validate                                          # noqa: PLC0415
        results = [validate.v13_render_not_clipped().as_dict(),
                   validate.v24_render_duration_floor().as_dict(),
                   picture_floor(unaired_slugs())]
    return run(results, heal=a.heal)


if __name__ == "__main__":
    raise SystemExit(main())
