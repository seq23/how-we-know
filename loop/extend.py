"""Repair short episodes with quiet visual time toward 15 minutes; preserve speech."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import author                                              # noqa: E402
import durations                                           # noqa: E402
import validate                                            # noqa: E402
from common import Stage, config, week_id                  # noqa: E402

SCRIPTS = ROOT / "scripts"
PLANS = ROOT / "plans"
AUDIO = ROOT / "audio"
RENDERS = ROOT / "renders"


def band() -> tuple[float, float, float]:
    r = config()["retention"]
    target = float(r["runtime_minutes"])
    tol = float(r.get("runtime_tolerance_pct", 15.0)) / 100.0
    return target, target * (1 - tol), float(r["runtime_floor_minutes"])


def measured_minutes(slug: str) -> tuple[float | None, str]:
    """The episode's real length, and where the number came from.

    The RENDER is the authority when one exists, because that is the thing that
    airs. Narration audio is the fallback, and it is the number available before
    anything has been rendered -- which is when healing is cheapest.
    """
    d = durations.duration_s(slug)
    if d:
        return d / 60.0, "render"

    # PARTIAL NARRATION IS NOT A SHORT EPISODE. The audio directory fills one
    # beat at a time over hours, so an episode the narrator is halfway through
    # measures as half its length. what-is-concrete-made-of read as 5.09
    # minutes on 1,678 narration words -- about 11.6 minutes of script -- and
    # would have been "healed" by adding material to an episode that was never
    # short. Audio counts only when there is one wav per planned beat.
    adir = AUDIO / slug
    plan = PLANS / f"{slug}.json"
    if adir.is_dir() and plan.exists():
        try:
            beats = len(json.loads(plan.read_text()))
        except (json.JSONDecodeError, TypeError):
            beats = 0
        # `[0-9]*.wav` NOT `*.wav`. An interrupted beat leaves `0079.part.wav`
        # beside the finished files, and a bare glob counts it as narrated --
        # so an episode the narrator was killed halfway through would measure
        # as complete, be judged short, and be extended for no reason.
        wavs = sorted(adir.glob("[0-9]*.wav"))
        if beats and len(wavs) >= beats:
            total = sum(durations.ffprobe_duration(w) or 0.0 for w in wavs)
            if total:
                return total / 60.0, "narration audio (complete)"
        return None, (f"narration incomplete: {len(wavs)} of {beats} beat(s)"
                      if beats else "no plan to count beats against")
    return None, "nothing measured"


def short_episodes(grandfathered: set) -> list[dict]:
    """Every episode measurably under the floor, with what it needs.

    Grandfathered slugs are excluded by name, exactly as V24 excludes them: the
    twenty episodes rendered before the floor existed are a recorded owner
    decision, not a backlog to heal.
    """
    target, _band_min, floor = band()
    out = []
    for path in sorted(SCRIPTS.glob("*.md")):
        slug = path.stem
        if slug in grandfathered:
            continue
        mins, source = measured_minutes(slug)
        if mins is None or mins >= floor:
            continue
        have = durations.narration_words_of(path.read_text(encoding="utf-8"))
        want = durations.narration_words_for(target)
        out.append({"slug": slug, "minutes": round(mins, 2), "source": source,
                    "words_now": have, "words_target": want,
                    "words_needed": max(0, want - have)})
    return out


def split_for_insert(text: str) -> tuple[str, str, str]:
    """(before, closing_section, after) -- where new narration goes.

    New material goes BEFORE the final narration section. Appending after the
    conclusion produces an episode that ends twice, and inserting near the top
    would shift every beat index after it and force the whole episode to be
    re-narrated. This is the one place that costs the fewest beats while still
    reading correctly.
    """
    nar = text.find("## Narration")
    if nar < 0:
        raise ValueError("no '## Narration' section")
    end = text.find("\n## ", nar + 1)
    end = end if end > 0 else len(text)
    body, tail = text[nar:end], text[end:]
    # Sections inside the narration are '### ' headings.
    heads = [m.start() for m in re.finditer(r"\n### ", body)]
    if not heads:
        return text[:nar] + body, "", tail
    last = heads[-1]
    return text[:nar] + body[:last], body[last:], tail


def extend_one(item: dict, st: Stage, dry_run: bool = False) -> dict:
    slug = item["slug"]
    import approved_renders                                    # noqa: PLC0415
    if approved_renders.protected(slug):
        st.note(f"{slug}: owner-approved cut - not extended or re-rendered")
        return {"slug": slug, "applied": False, "approved": True}
    # Assembly measures the existing wavs and inserts quiet picture time.
    # Never request more words merely to satisfy a runtime target.
    if dry_run:
        st.work(f"would extend {slug} with picture time toward 15 minutes")
        return {"slug": slug, "applied": False, "dry_run": True}
    import picture_time
    path = SCRIPTS / f"{slug}.md"
    path.write_text(picture_time.mark(path.read_text(encoding="utf-8")), encoding="utf-8")
    plan = PLANS / f"{slug}.json"
    if plan.exists():
        beats = json.loads(plan.read_text())
        if beats:
            beats[0]["picture_target_s"] = 900
            plan.write_text(json.dumps(beats, indent=2) + "\n")
    render = RENDERS / f"{slug}-final.mp4"
    if render.exists():
        import lengthen
        lengthen.record_superseded(slug, render, "picture time toward 15 minutes")
        keep = RENDERS / "superseded-short"
        keep.mkdir(exist_ok=True)
        shutil.move(str(render), str(keep / render.name))
    durations.forget(slug)
    retire_shorts(slug)
    st.work(f"queued {slug} for picture time toward 15 minutes; speech unchanged")
    return {"slug": slug, "applied": True, "target_seconds": 900,
            "words_before": item.get("words_now"),
            "words_after": item.get("words_now")}


def retire_stale_audio(slug: str, old_narrations: dict | None,
                       audio_dir: Path | None = None,
                       new_plan: list | None = None) -> list[str]:
    """Move aside every wav whose text is no longer the text at its index.

    WHY. Narration is one wav per plan INDEX (audio/<slug>/0000.wav ...), and
    voice/narrate_all.py skips any index that already has a valid wav. An
    extension inserts sections before the closing one, so every beat from the
    insertion point on moves to a new index - and the wavs already sitting at
    those indices were synthesised from the sentences that USED to be there.
    Until 2026-10-03 nothing retired them: the re-render would have spoken the
    old closing lines under the new section's captions, and captions.verify_text
    could not catch it because narrate_all rewrites beats.json from the new
    plan before the render. loop/pov_repair.py already deletes the one wav it
    replaces; this is the same rule for the many.

    `old_narrations` is {index: text the wav at that index was cut from} - the
    plan file before the script changed, or, when that is gone, the tracked
    audio/<slug>/beats.json the last narration run wrote. Returns the file
    names moved. Nothing is deleted: they go to audio/<slug>/superseded/, the
    same place bin/batch-session.sh puts an orphan.
    """
    adir = (audio_dir or AUDIO) / slug
    if not adir.is_dir():
        return []
    if old_narrations is None:
        bj = adir / "beats.json"
        if not bj.exists():
            return []
        try:
            old_narrations = {int(r["i"]): r.get("narration")
                              for r in json.loads(bj.read_text())
                              if isinstance(r, dict) and "i" in r}
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return []
    if new_plan is None:
        sys.path.insert(0, str(ROOT / "visuals"))
        import planner                                     # noqa: PLC0415
        new_plan = planner.plan(str(SCRIPTS / f"{slug}.md"))
    new_text = {i: b.get("narration") for i, b in enumerate(new_plan)}
    moved = []
    keep = adir / "superseded"
    for wav in sorted(adir.glob("[0-9]*.wav")):
        i = int(wav.stem)
        if i in old_narrations and old_narrations[i] == new_text.get(i):
            continue                      # same words at this index: still true
        if i not in old_narrations and i in new_text:
            continue                      # never recorded: nothing to compare
        keep.mkdir(exist_ok=True)
        shutil.move(str(wav), str(keep / wav.name))
        moved.append(wav.name)
    return moved


SHORTS = ROOT / "shorts"


def retire_shorts(slug: str, shorts_dir: Path | None = None) -> list[str]:
    """Move aside every Short cut from this episode's superseded render.

    WHY. bin/push-to-r2.sh runs V14 (attribution) and V15 (caption crop) over
    EVERY receipt in shorts/ before shelving ANY Short, because the Linux
    runner has no Apple Vision and cannot re-check later. A Short's receipt
    resolves its credits through plans/<slug>.json and its crop through
    renders/<slug>-final.mp4. On 2026-10-03 this stage extended three held
    episodes, deleted their plans and moved their renders aside - and left
    their Shorts in place, so that evening's push reported "plans/... is gone;
    the credit its beats require cannot be re-resolved" three times and
    shelved NOTHING, for every episode (SHORTS_UNVERIFIED). The Short of a
    render that no longer exists is not a Short anyone may ship; it goes
    where the render went, and the batch cuts a fresh one from the new render.
    Nothing is deleted.
    """
    sdir = shorts_dir or SHORTS
    if not sdir.is_dir():
        return []
    keep = sdir / "superseded-short"
    moved = []
    for f in sorted(sdir.glob(f"{slug}-short*.mp4")) + \
            sorted(sdir.glob(f"{slug}-short*.mp4.short.json")):
        keep.mkdir(exist_ok=True)
        shutil.move(str(f), str(keep / f.name))
        moved.append(f.name)
    return moved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--retire-stale", metavar="SLUG", default=None,
                    help="only move aside the wavs whose text no longer matches "
                         "the script's plan at their index (uses "
                         "audio/SLUG/beats.json as the record of what was "
                         "voiced); for an episode extended before this check "
                         "existed")
    a = ap.parse_args()
    if a.retire_stale:
        moved = retire_stale_audio(a.retire_stale, None)
        print(f"{a.retire_stale}: {len(moved)} stale wav(s) moved to "
              f"audio/{a.retire_stale}/superseded/"
              + (f": {', '.join(moved)}" if moved else ""))
        shorts = [] if (RENDERS / f"{a.retire_stale}-final.mp4").exists() \
            else retire_shorts(a.retire_stale)
        print(f"{a.retire_stale}: {len(shorts)} Short(s) of the superseded "
              f"render moved to shorts/superseded-short/"
              + (f": {', '.join(shorts)}" if shorts else ""))
        return 0

    target, band_min, floor = band()
    grandfathered = set(config()["retention"]["runtime_floor_grandfathered"])
    with Stage("runtime-self-heal", week_id(),
               zero_work_hint="Nothing was short and nothing was extended. "
                              "That is the healthy state, and it is reported "
                              "rather than exited silently.") as st:
        st.note(f"target {target} min, band {band_min:.1f}-"
                f"{target * 2 - band_min:.1f}, hard floor {floor} min")
        short = short_episodes(grandfathered)
        if a.slug:
            short = [s for s in short if s["slug"] == a.slug]
        if not short:
            st.work(f"every episode outside the {len(grandfathered)} "
                    f"grandfathered ones is over the {floor}-minute floor")
            return 0
        for item in short:
            st.note(f"{item['slug']}: {item['minutes']} min "
                    f"({item['source']}), {item['words_now']} narration "
                    f"words, needs +{item['words_needed']}")
        healed, refused = [], []
        for item in short:
            r = extend_one(item, st, dry_run=a.dry_run)
            (healed if r.get("applied") or r.get("dry_run") else
             refused).append(r)
            if not (r.get("applied") or r.get("dry_run")):
                st.note(f"{r['slug']}: extension refused after "
                        f"{author.MAX_ATTEMPTS} attempts - "
                        f"{r['rejected'][0][:110]}")

        # ONE REFUSAL MUST NOT ABORT THE OTHERS. Each episode is an independent
        # piece of work; stopping the sweep on the first rejection is how a
        # self-healing stage heals one thing a week.
        if refused:
            st.named_stop(
                "EXTENSION_REJECTED",
                f"{len(refused)} of {len(short)} short episode(s) could not be "
                f"extended without failing the checks the original draft "
                f"passed: "
                + "; ".join(f"{r['slug']} ({r['rejected'][0][:70]})"
                            for r in refused),
                detail={"healed": [r["slug"] for r in healed],
                        "refused": {r["slug"]: r["rejected"] for r in refused}},
                unblock="Those scripts are UNCHANGED and still under the "
                        "floor. An episode padded to length with unsourced "
                        "filler is worse than a short one, so this refuses "
                        "rather than lowering the bar to reach a number. The "
                        "rejected drafts are kept for inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
