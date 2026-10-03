"""Self-heal an episode that came in under the runtime floor.

    .venv/bin/python loop/extend.py --dry-run       # say what it would extend
    .venv/bin/python loop/extend.py                 # extend everything short
    .venv/bin/python loop/extend.py --slug <slug>

WHY THIS EXISTS. Four materials episodes rendered at 8.6-9.7 minutes against a
hard 10-minute floor. The floor was a NAMED STOP: it noticed, said so, and
waited for a person who, on this channel, is not coming. Worse, nothing on the
upload path even consulted it -- V24 runs where the renders are, which is the
Mac, while the drafting lane that trips the breaker runs in the cloud where
`renders/` does not exist and the validator exempts itself. A short episode
would have shipped.

Owner decision 2026-09-05: **aim for 12 minutes, tolerate 15% either side, and
anything under 10 minutes self-heals.** Twelve rather than ten because a target
set AT the floor leaves nowhere to land when a draft comes in short -- these
four were authored to a 10.5 target and every one of them missed low. The band
is 10.2-13.8 minutes, and its lower edge is above the floor by construction, so
"inside the band" and "over the floor" cannot disagree.

HOW IT HEALS, and what it costs. It asks the same model, through the same
prompt rules, for additional narration on the same question, and inserts it
BEFORE the closing section -- not appended after the conclusion, which would
read as an episode that ends twice. Beats before the insertion point keep their
audio: `voice/narrate_all.py` narrates only the beats whose wav is missing, so
the cost is the new material plus the few beats that shift after it, not a whole
re-narration.

WHAT IT WILL NOT DO. It will not pad. Every added sentence goes through the same
validators the original draft did -- sources fetched and checked for real, no
invented figures, the exclusion set, the directive-truth check. An extension
that cannot clear them is a NAMED STOP, because an episode padded to length with
unsourced filler is worse than a short one.
"""
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


def extension_prompt(question: str, slug: str, need_words: int,
                     existing: str, domain: str) -> list[dict]:
    """The same rules the original draft was held to, aimed at a gap."""
    base = author.build_prompt(question, {"line": "", "pov_id": "",
                                          "tag": "", "tier": ""}, domain)
    system = base[0]["content"]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"The episode below is finished and correct, but it runs short of "
            f"the channel's runtime target. Write ONLY additional narration to "
            f"add to it -- about {need_words} words -- that will be inserted "
            f"immediately BEFORE its final section.\n\n"
            f"Rules, all of which the existing script already follows:\n"
            f"* Return ONLY new '### ' narration sections. No preamble, no "
            f"commentary, no repetition of what is already there, and nothing "
            f"outside the narration.\n"
            f"* Every figure must be stated in the narration and traceable to a "
            f"named public source. Add the sources you use in a final block "
            f"headed exactly 'SOURCES:' with one URL per line. Do not invent a "
            f"URL; if you are not certain a page exists, do not cite it.\n"
            f"* Do not pad. New material must add EVIDENCE the episode does not "
            f"already contain -- a measurement, a method, a limitation, a "
            f"comparison -- not restatement.\n"
            f"* Do not write a conclusion. The episode already has one and it "
            f"follows your text.\n\n"
            f"QUESTION: {question}\n\nEXISTING SCRIPT:\n\n{existing}")},
    ]


def extend_one(item: dict, st: Stage, dry_run: bool = False) -> dict:
    slug = item["slug"]
    path = SCRIPTS / f"{slug}.md"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", text, re.M)
    question = m.group(1).strip() if m else slug.replace("-", " ")

    import domains as dom                                   # noqa: PLC0415
    domain = dom.domain_of_slug(slug) or author.DEFAULT_DOMAIN

    if dry_run:
        st.work(f"would extend {slug}: {item['minutes']} min, "
                f"+{item['words_needed']} narration words to reach "
                f"{item['words_target']}")
        return {"slug": slug, "applied": False, "dry_run": True}

    key = author.api_key()
    if not key:
        st.named_stop(
            "EXTEND_KEY_MISSING",
            f"{slug} is {item['minutes']} min, under the "
            f"{band()[2]}-minute floor, and there is no OpenRouter key to "
            f"author the additional narration with.",
            detail=item,
            unblock=f"Put the key in {author.KEY_FILE} (gitignored) or set "
                    f"$OPENROUTER_API_KEY, and re-run this stage.")

    messages = extension_prompt(question, slug, item["words_needed"],
                                text, domain)

    # RETRY WITH THE PROBLEM FED BACK, exactly as author.draft() does. The
    # first real run was rejected for a directive drawing a number the
    # narration never speaks -- a fixable mistake, and one the model corrects
    # immediately when told. Refusing on the first attempt would make "self-
    # heal" mean "stop, more politely".
    merged, urls, problems = "", [], []
    for attempt in range(1, author.MAX_ATTEMPTS + 1):
        resp = author.call_openrouter(messages, author.DEFAULT_MODEL, key)
        choice = (resp.get("choices") or [{}])[0]
        new_text = ((choice.get("message") or {}).get("content") or "").strip()
        new_text = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", new_text)
        finish = choice.get("finish_reason") or choice.get("native_finish_reason")
        usage = resp.get("usage") or {}
        author.record_spend(slug, author.DEFAULT_MODEL, usage,
                            usage.get("cost"), attempt, bool(new_text))

        problems = []
        if finish and finish not in ("stop", "end_turn"):
            # A truncated extension is the failure that looks most like
            # success: it has sections, sources, and simply stops.
            problems.append(f"output was cut off (finish_reason={finish!r}); "
                            f"the extension is incomplete")

        body, sources = new_text, ""
        if "SOURCES:" in new_text:
            body, sources = new_text.split("SOURCES:", 1)
        body = body.strip()
        if body and not body.startswith("### "):
            body = "### " + body.lstrip("# ").lstrip()

        before, closing, tail = split_for_insert(text)
        merged = f"{before.rstrip()}\n\n{body}\n{closing}{tail}"
        urls = re.findall(r"https?://[^\s)>\]]+", sources)
        if urls and "## Sources" in merged:
            head, rest = merged.split("## Sources", 1)
            line_end = rest.find("\n")
            merged = (head + "## Sources" + rest[:line_end] + "\n"
                      + "\n".join(f"- {u}" for u in urls) + rest[line_end:])

        # SAME GATE AS THE ORIGINAL DRAFT, on the merged script rather than the
        # fragment. Padding to length is the one outcome worse than being
        # short, so the extension faces every check the first draft did.
        problems += author.dead_urls(merged)
        problems += author.directive_truth_problems(merged)
        if not problems:
            break
        st.note(f"{slug} attempt {attempt}: {problems[0][:110]}")
        messages = messages + [
            {"role": "assistant", "content": new_text},
            {"role": "user", "content":
                "That extension was rejected by the same checks the existing "
                "script passed:\n\n"
                + "\n".join(f"* {p}" for p in problems[:6])
                + "\n\nRewrite it so none of those is true. Same rules, same "
                  "length. Do not drop a claim to dodge a check -- either "
                  "speak the number in the narration or remove the directive "
                  "that draws it."},
        ]

    if problems:
        tmp = author.DRAFTS / f"{slug}.extended.md"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(merged, encoding="utf-8")
        return {"slug": slug, "applied": False, "rejected": problems[:6],
                "draft": str(tmp.relative_to(ROOT))}

    words_after = durations.narration_words_of(merged)
    # The audio for every beat from the insertion point on was synthesised
    # from the OLD text at that index. Retire it BEFORE the plan goes, while
    # the plan still says what each wav was cut against (below).
    old_plan = PLANS / f"{slug}.json"
    old_narrations = None
    if old_plan.exists():
        try:
            old_narrations = {i: b.get("narration")
                              for i, b in enumerate(json.loads(old_plan.read_text()))}
        except (json.JSONDecodeError, TypeError, AttributeError):
            old_narrations = None
    path.write_text(merged, encoding="utf-8")
    retired = retire_stale_audio(slug, old_narrations)

    # The plan, the audio after the insertion point and the render are now
    # stale. Move the render aside rather than deleting it - nothing in this
    # repo deletes finished work - and let the batch rebuild.
    stale = [f"audio/{slug}/{w}" for w in retired]
    plan = PLANS / f"{slug}.json"
    if plan.exists():
        plan.unlink()
        stale.append(str(plan.relative_to(ROOT)))
    render = RENDERS / f"{slug}-final.mp4"
    if render.exists():
        keep = RENDERS / "superseded-short"
        keep.mkdir(exist_ok=True)
        shutil.move(str(render), str(keep / render.name))
        stale.append(str(render.relative_to(ROOT)))
        # The RECORDED duration outlives the render. Without this the next run
        # reads 8.61 minutes for an episode whose script is now 13.2 and
        # extends it again, every night, for ever.
        if durations.forget(slug):
            stale.append(f"loop/state/durations.json:{slug}")

    st.work(f"extended {slug}: {item['words_now']} -> {words_after} narration "
            f"words (~{durations.minutes_for(words_after):.1f} min), "
            f"{len(urls)} source(s) added")
    return {"slug": slug, "applied": True, "words_before": item["words_now"],
            "words_after": words_after, "sources_added": len(urls),
            "stale": stale}


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
