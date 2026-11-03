"""A domain's graphics never appear in another domain's video.

    python visuals/plan_domain.py check          # every plan vs its domain (V77)
    python visuals/plan_domain.py sweep          # THE MAC: repair + retire stale renders

WHY (CONFIRMED 2026-11-01, the owner's screenshot): the Short "Why does rice
get sticky" showed the deep-sea "CHALLENGER DEEP ... METRES" depth gauge on a
food episode. plans/why-does-rice-get-sticky.json had two `depth_descent`
beats with empty args - drawn with their ocean defaults - because
visuals/planner.py chose its signal table at import from HWK_DOMAIN (unset in
the batch's plan step, default deep sea) and had no food row at all. Four
materials plans carry the same defect. The planner now plans from the script's
own **Domain:** line; this module is the guard that holds wherever a plan is
used:

  * visuals/assemble.py refuses to render a plan with a foreign segment;
  * visuals/shorts.py drops a foreign beat from a cut (refuses if it is the
    answer beat), so no Short carries one;
  * `sweep` (bin/batch-session.sh, before rendering) re-plans a foreign plan of
    any episode whose long-form is not yet uploaded - beat for beat, the audio
    is kept - and retires its render (recorded in
    loop/state/superseded_renders.json, which the cloud upload refuses by
    sha256), so it is re-rendered clean; it also retires any render whose
    sha256 is already recorded as superseded;
  * validator V77 fails any foreign plan of a not-yet-uploaded episode. A
    long-form video already live is never re-rendered (forward only, owner
    13 Oct 2026); its plan is reported, not failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLANS = ROOT / "plans"
RENDERS = ROOT / "renders"
STATE = ROOT / "loop" / "state"
SUPERSEDED = STATE / "superseded_renders.json"

DEEP = "deep-sea-ocean-science"
MAT = "materials-and-manufacturing"
FOOD = "food-science"

# Which domains may draw each domain-specific segment. A segment absent here
# is domain-agnostic (text, cards, ambient, evidence devices).
SEGMENT_DOMAINS: dict[str, set[str]] = {
    "depth_descent": {DEEP}, "light_attenuation": {DEEP},
    "pressure_gauge": {DEEP}, "zone_column": {DEEP}, "world_map": {DEEP},
    "anatomy_callout": {DEEP}, "species_image": {DEEP},
    # the device renderers read the ACTIVE domain's device (visuals/domains.py
    # DEVICES): materials' heat scale, food's kitchen scale.
    "thermal_ascent": {MAT, FOOD}, "process_column": {MAT, FOOD},
    "material_image": {MAT},
}
# Agnostic segments whose DEFAULT arguments are ocean figures: drawn with no
# arguments they show "11,034 METRES" / Everest vs Challenger Deep.
OCEAN_DEFAULTS = {"stat_card": ("value", "unit"), "comparison": ("a_label", "b_label")}


def foreign(plan: list[dict], domain: str) -> list[tuple[int, str, str]]:
    """[(beat index, segment, why)] for every beat that draws another domain's
    graphic in a `domain` video."""
    out = []
    for i, b in enumerate(plan or []):
        seg = b.get("segment")
        owners = SEGMENT_DOMAINS.get(seg)
        if owners is not None and domain not in owners:
            out.append((i, seg, f"{seg} belongs to {sorted(owners)}"))
            continue
        need = OCEAN_DEFAULTS.get(seg)
        if need and domain != DEEP and not all((b.get("args") or {}).get(k) for k in need):
            out.append((i, seg, f"{seg} without {need} draws its ocean defaults"))
    return out


def domain_of(slug: str) -> str:
    sys.path.insert(0, str(ROOT / "loop"))
    import importlib.util                                  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("_loop_domains", ROOT / "loop" / "domains.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.domain_of_slug(slug) or DEEP


def uploaded_longform() -> set[str]:
    try:
        led = json.loads((STATE / "ledger.json").read_text())
    except (OSError, ValueError):
        return set()
    return {r["slug"] for r in led.get("published") or [] if r.get("video_id") and not r.get("withdrawn_at")}


def check(plans_dir: Path | None = None, live: set[str] | None = None) -> dict:
    """{"examined", "bad": {slug: [...]}, "live": {slug: [...]}}"""
    plans_dir = plans_dir or PLANS
    live = uploaded_longform() if live is None else live
    out = {"examined": 0, "bad": {}, "live": {}}
    for p in sorted(plans_dir.glob("*.json")):
        try:
            plan = json.loads(p.read_text())
        except ValueError:
            continue
        if not isinstance(plan, list):
            continue
        out["examined"] += 1
        f = foreign(plan, domain_of(p.stem))
        if f:
            out["live" if p.stem in live else "bad"][p.stem] = f
    return out


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _retire_render(slug: str, why: str, sup: dict) -> str | None:
    cut = RENDERS / f"{slug}-final.mp4"
    if not cut.exists():
        return None
    import sys as _sys                                         # noqa: PLC0415
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loop"))
    import approved_renders                                    # noqa: PLC0415
    if approved_renders.protected(slug):
        return None
    sha = _sha(cut)
    prev = sup.get(slug)
    if not (prev and prev.get("sha256") == sha):
        rec = {"sha256": sha, "bytes": cut.stat().st_size,
               "superseded_at": __import__("datetime").date.today().isoformat(),
               "why": why}
        if prev:
            rec["previous"] = [*(prev.get("previous") or []),
                               {k: v for k, v in prev.items() if k != "previous"}]
        sup[slug] = rec
    dest = RENDERS / "superseded-domain"
    dest.mkdir(parents=True, exist_ok=True)
    cut.replace(dest / cut.name)
    return sha


def sweep() -> int:
    """THE MAC. Repair every not-yet-uploaded plan that draws another domain's
    graphics, and retire renders whose sha256 is recorded as superseded."""
    sys.path.insert(0, str(HERE))
    import planner                                         # noqa: PLC0415
    sup = json.loads(SUPERSEDED.read_text()) if SUPERSEDED.exists() else {}
    live = uploaded_longform()
    done, refused = [], []
    for slug, bad in check(live=live)["bad"].items():
        sys.path.insert(0, str(ROOT / "loop"))
        script = ROOT / "scripts" / f"{slug}.md"
        if not script.exists():
            script = ROOT / "scripts" / "food" / f"{slug}.md"
        old = json.loads((PLANS / f"{slug}.json").read_text())
        try:
            new = planner.plan(str(script))
        except Exception as e:                             # noqa: BLE001
            refused.append((slug, f"re-plan failed: {e}"))
            continue
        same = len(new) == len(old) and all(
            a.get("narration") == b.get("narration") for a, b in zip(new, old))
        if not same or foreign(new, domain_of(slug)):
            refused.append((slug, "the re-planned beats do not match the narrated "
                                  "ones (or still draw a foreign graphic)"))
            continue
        for a, b in zip(new, old):            # keep each beat's measured timing
            a["seconds"] = b.get("seconds", a.get("seconds"))
        (PLANS / f"{slug}.json").write_text(json.dumps(new, indent=2) + "\n")
        _retire_render(slug, "plan drew another domain's graphics "
                             "(visuals/plan_domain.py)", sup)
        done.append(slug)
        print(f"  re-planned {slug}: {len(bad)} foreign beat(s) replaced")
    for slug, rec in sorted(sup.items()):
        cut = RENDERS / f"{slug}-final.mp4"
        if cut.exists() and slug not in live and _sha(cut) == rec.get("sha256"):
            _retire_render(slug, rec.get("why", "superseded"), sup)
            done.append(slug)
            print(f"  retired the superseded render of {slug} (re-rendered next)")
    if done:
        SUPERSEDED.write_text(json.dumps(sup, indent=2) + "\n")
    for slug, why in refused:
        print(f"  PLAN_DOMAIN_UNREPAIRABLE {slug}: {why}")
    if not done and not refused:
        print("PLAN_DOMAIN_CLEAN: no unpublished plan draws another domain's "
              "graphics and no superseded render is on disk")
    return 3 if refused else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["sweep"]:
        return sweep()
    r = check()
    for slug, bad in sorted(r["live"].items()):
        print(f"  LIVE (forward only, not re-rendered) {slug}: "
              f"{sorted({s for _, s, _ in bad})}")
    for slug, bad in sorted(r["bad"].items()):
        print(f"  FAIL {slug}: {[f'beat {i} {w}' for i, _, w in bad][:4]}")
    if not r["examined"]:
        print("FAIL: no plan examined")
        return 1
    print(f"{r['examined']} plan(s) examined, {len(r['bad'])} draw another "
          f"domain's graphics")
    return 1 if r["bad"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
