"""Replace an untraced first-person beat with one of the owner's real lines.

    .venv/bin/python loop/pov_repair.py            # every unpublished episode
    .venv/bin/python loop/pov_repair.py --dry-run

THE BLOCK THIS CLEARS. `[HUMAN]` marks the one beat where the owner speaks as
herself, and `loop/cloud_upload.py` refuses to upload an episode whose `[HUMAN]`
beat has no entry in `pov/pov-assignments.json`. That refusal is correct and
must stay: on 2026-09-08 eight rendered, captioned, shelved materials episodes
carried beats like

    [HUMAN] I wrote the dislocation-pinning explanation like it covered every
    steel everywhere.

which the authoring model composed. She did not write the script — she does not
operate this channel day to day — so publishing that sentence has the channel
assert something no interview records her saying. No validator may approve it
for her and this file does not try.

WHAT IT DOES INSTEAD, and why it is matching rather than approving.
`pov/pov-bank.json` holds 144 lines drawn from her own interviews. Its own
header, and `loop/pov_match.py`'s, say the same thing: **that bank is her
approved voice, so choosing between its lines is a matching problem and runs
unattended.** `pov_match.select()` already does exactly that for a new script,
and the gap named in its docstring is that "the choice is never recorded back".
This file closes that gap for episodes that are already written: it swaps the
invented sentence for a real one she actually said, records the assignment, and
invalidates the artifacts downstream of the change so the batch rebuilds them.

It never writes a line the bank does not contain, and it never adds a line TO
the bank — adding to the bank is an approval, and approvals are hers. Where
`select()` finds no fit it raises rather than guessing, and the episode keeps
its named stop.

WHAT IT INVALIDATES, and why each one.
Changing the words changes the audio, the video and the caption timing, so all
three must be rebuilt or they would disagree with each other:

    plans/<slug>.json          the beat's narration text, patched in place
    audio/<slug>/NNNN.wav      deleted; narrate_all regenerates just that beat
    audio/<slug>/beats.json    the beat's text and its measured duration
    captions/<slug>.*          deleted; captions_build rebuilds after the render
    renders/<slug>-final.mp4   MOVED to renders/superseded-pov/, never deleted

NOTHING PUBLISHED IS TOUCHED. An episode already in `loop/state/ledger.json` is
skipped outright: its script is what aired, and the honest repair for a live
video is `loop/retire.py`, which sets it private. There is no delete path here
and there must not be one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
# APPENDED, not inserted at 0: visuals/ has its own `domains` module and putting
# it first shadowed loop/domains.py, so domain_of_slug() vanished at runtime.
sys.path.append(str(ROOT / "visuals"))

import batch_queue                                  # noqa: E402
import domains                                      # noqa: E402
import ledger                                       # noqa: E402
import pov_match                                    # noqa: E402
from common import (STATE, Stage, now as _now, read_json,  # noqa: E402
                    week_id, write_json)

LANE = "pov-repair"
SCRIPTS = ROOT / "scripts"
PLANS = ROOT / "plans"
AUDIO = ROOT / "audio"
RENDERS = ROOT / "renders"
CAPTIONS = ROOT / "captions"
SUPERSEDED = RENDERS / "superseded-pov"
SUPERSEDED_INDEX = STATE / "superseded_renders.json"

HUMAN = "[HUMAN]"

# See ranked_lines(): below this a match is one incidental word, not a subject.
SCORE_FLOOR = 2.0


def human_beat(slug: str) -> tuple[str, str] | None:
    """(the whole paragraph, the sentence after the marker), or None."""
    p = SCRIPTS / f"{slug}.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    if HUMAN not in text:
        return None
    for para in text.split("\n\n"):
        if HUMAN in para:
            said = para.split(HUMAN, 1)[1].strip()
            return para, said
    return None


def plan_index(slug: str, said: str) -> int | None:
    """Which beat of plans/<slug>.json carries this text.

    Matched on normalised prose, not on identity: the planner strips the
    `[HUMAN]` marker when it builds the beat, and a script may differ from the
    plan by whitespace alone.
    """
    pj = PLANS / f"{slug}.json"
    if not pj.exists():
        return None
    want = _norm(said)
    plan = json.loads(pj.read_text())
    for i, b in enumerate(plan):
        n = _norm(b.get("narration") or "")
        if n and (n == want or n in want or want in n):
            return i
    return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def ranked_lines(slug: str, subject: str, domain, used):
    """Bank lines that could speak for this episode, best fit first.

    `pov_match.select()` returns ONE line and raises when nothing fits. That is
    the right contract for authoring a new script and the wrong one here: the
    best-scoring line may reshape the episode (see repair_one), and the repair
    needs the next candidate rather than a stop. Same scorer, same rotation
    window, same refusal to invent -- an empty list is a refusal, not a guess.
    """
    # EVERY ID ALREADY ASSIGNED, not just the rotation window.
    #
    # pov/pov-assignments.json's own header states "one POV per video, no
    # reuse", and V40 (loop/validate.py) enforces it across the whole file.
    # The rotation window is a weaker rule for a different purpose - it stops a
    # line recurring inside twelve consecutive videos - and honouring only that
    # handed three lines to a second episode each, all three already spoken by
    # a published deep-sea one. The strictest applicable rule wins; a bank of
    # 144 lines against 34 episodes has room for it.
    recent = set(used) | {a["pov_id"] for a in
                          pov_match.hand_assignments().values()}
    ranked = []
    for l in pov_match.bank():
        if l["id"] in recent:
            continue
        sc = pov_match.score(l, subject, domain)
        # A FLOOR, not just "greater than zero".
        #
        # score() returns a weak positive for a single incidental vocabulary
        # hit, and a weak positive is how "Octopuses impress me. So much of
        # their nervous system runs through their arms" scored 1.0 for
        # why-does-old-iron-not-rust -- on the word "adapt" -- and was picked.
        # It is a real line of hers and it is `tier: transferable`, so nothing
        # below this point would have rejected it; the episode would simply
        # have aired a deep-sea aside in the middle of a rust explanation.
        #
        # 2.0 is the level every other repair on 2026-09-08 reached
        # unassisted, so it is the observed floor for a match that is about
        # the subject rather than about one word in it. Below it, the bank's
        # own transferable fallback answers instead, and if that cannot, the
        # episode keeps its named stop. Refusing is the correct outcome for an
        # episode no line fits.
        if sc < SCORE_FLOOR:
            continue
        # AND IT MUST BE ENTITLED TO SPEAK FOR THIS DOMAIN.
        #
        # score() already zeroes a `tier: specific` line outside its own
        # domain, so anything specific that survives belongs here. A
        # `transferable` line is a different case: the bank's tiering makes it
        # domain-free, but only the tags in pov_match.FALLBACK_TAGS -- evidence,
        # uncertainty, instruments, thesis, numbers, trust, confidence,
        # unknown -- are actually about METHOD. The rest are subject tags, and
        # a subject-tagged transferable line carries its subject with it:
        # "Octopuses impress me. So much of their nervous system runs through
        # their arms" is tagged `adaptation`, scored 2.0 for
        # why-does-old-iron-not-rust on the word "adapt", and would have aired
        # a deep-sea aside in the middle of a rust explanation. Nothing else
        # would have caught it, because the line is genuinely hers and
        # genuinely transferable by tier.
        if l["tier"] == "transferable" and l["tag"] not in pov_match.FALLBACK_TAGS:
            continue
        ranked.append((sc, l))
    ranked.sort(key=lambda t: (-t[0], t[1]["id"]))
    out = [{"pov_id": l["id"], "line": l["line"], "tag": l["tag"],
            "tier": l["tier"], "source_answer": l.get("source_answer"),
            "matched_by": f"tag:{l['tag']} score {sc:.1f}"}
           for sc, l in ranked]
    # THEN the transferable pool, on the bank's own terms. pov_match.select()
    # already falls back to it -- "transferable lines may be used in any
    # evidence-based niche, and every video in this channel is evidence-based
    # by construction" -- and it matters more here than there: a repair also
    # has to find a line that does not reshape the episode, so a seven-line
    # shortlist runs out. Two episodes refused for exactly that before this
    # was added. Ordered after the scored lines, so a real subject match always
    # wins; never before them, which would trade fit for convenience.
    seen = {r["pov_id"] for r in out}
    for tag in pov_match.FALLBACK_TAGS:
        for l in sorted(pov_match.bank(), key=lambda x: x["id"]):
            if (l["tier"] == "transferable" and l["tag"] == tag
                    and l["id"] not in recent and l["id"] not in seen):
                seen.add(l["id"])
                out.append({"pov_id": l["id"], "line": l["line"],
                            "tag": l["tag"], "tier": l["tier"],
                            "source_answer": l.get("source_answer"),
                            "matched_by": f"transferable tag:{l['tag']} "
                                          f"(the bank permits any "
                                          f"evidence-based niche)"})
    return out


def _confined(original: list, trial: list, idx: int) -> bool:
    """Did the replacement change ONLY the beats around the one it replaced?

    Same beat count, and every differing index in one contiguous run that
    contains `idx`. A run that reaches the end of the episode is a reshape
    wearing a contiguous shape, so it is rejected too.
    """
    if len(trial) != len(original):
        return False
    diff = [i for i in range(len(trial))
            if original[i]["narration"] != trial[i]["narration"]]
    if not diff or idx not in diff:
        return False
    if diff != list(range(diff[0], diff[-1] + 1)):
        return False
    return diff[-1] - diff[0] <= 3


def repair_one(slug: str, dry_run: bool = False,
               used_ids: list[str] | None = None) -> dict:
    """Swap one episode's invented POV beat for a bank line. Returns a record."""
    beat = human_beat(slug)
    if beat is None:
        return {"slug": slug, "skipped": "no [HUMAN] beat in the script"}
    para, said = beat

    idx = plan_index(slug, said)
    if idx is None:
        # Refuse rather than guess. Editing the script without editing the beat
        # the audio was generated from would leave the caption text and the
        # voice saying different things, which is the one thing the caption
        # pipeline verifies and must never be made to lie about.
        return {"slug": slug,
                "refused": "the [HUMAN] sentence matches no beat in "
                           f"plans/{slug}.json, so the audio it belongs to "
                           f"cannot be identified"}

    q = {e["slug"]: e.get("query", "") for e in batch_queue.queued_entries()}
    # THE ROTATION WINDOW HAS TO SEE THIS RUN'S OWN PICKS. Passing only the
    # assignments already on disk gave five of the eight episodes the SAME
    # line (pov-119), because each call was the first as far as select() could
    # tell. Five videos in one niche saying one identical sentence is worse
    # than the untraced beat it replaced.
    used = list(used_ids) if used_ids is not None else \
        [a["pov_id"] for a in pov_match.hand_assignments().values()]

    # THE REPLACEMENT MUST NOT RESHAPE THE REST OF THE EPISODE.
    #
    # CONFIRMED THE HARD WAY, 2026-09-08. The first version of this file wrote
    # the new sentence into the script AND patched plans/<slug>.json in place.
    # Those are two different plans. voice/narrate_all.py narrates from
    # planner.plan(script), not from the frozen file, and the planner re-splits
    # the paragraph it just rewrote: a bank line one sentence shorter than the
    # invented one merged two beats into one, every index after it shifted by
    # one, and every wav after that point silently belonged to different words.
    # Four of eight episodes did that -- 167 beats, about twenty hours of
    # narration, to repair one sentence -- and nothing would have reported it
    # except captions.py refusing to write, hours later, for two episodes.
    #
    # So the plan is never patched. The script is edited, the plan is RE-FROZEN
    # from the planner, and a candidate line is accepted only if the re-planned
    # episode has the same beat count and differs from the original ONLY in the
    # beats the [HUMAN] paragraph occupies. Anything else is rejected and the
    # next-best line is tried. That keeps the repair to the two or three beats
    # it should cost, and it is a property of the RESULT rather than a guess
    # about line lengths, so it cannot be defeated by a future planner change.
    import planner                                     # noqa: PLC0415
    sp = SCRIPTS / f"{slug}.md"
    original_text = sp.read_text(encoding="utf-8")
    original_plan = json.loads((PLANS / f"{slug}.json").read_text())

    subject = f"{q.get(slug, '')} {slug.replace('-', ' ')}"
    domain = domains.domain_of_slug(slug)
    pick = fresh = None
    rejected = []
    for cand in ranked_lines(slug, subject, domain, used):
        sp.write_text(original_text.replace(para, f"{HUMAN} {cand['line']}", 1),
                      encoding="utf-8")
        try:
            trial = planner.plan(str(sp))
        except Exception:                              # noqa: BLE001
            trial = None
        if trial and _confined(original_plan, trial, idx):
            pick, fresh = cand, trial
            break
        rejected.append(cand["pov_id"])
    if pick is None:
        sp.write_text(original_text, encoding="utf-8")
        return {"slug": slug,
                "refused": (f"no line in the bank can replace this beat without "
                            f"reshaping the rest of the episode (tried "
                            f"{len(rejected)}). Replacing it anyway would "
                            f"invalidate the narration of every beat after it.")}

    rec = {"slug": slug, "beat": idx, "pov_id": pick["pov_id"],
           "matched_by": pick["matched_by"],
           "was": said[:160], "now": pick["line"][:160],
           "rejected_for_reshaping": rejected}
    if dry_run:
        sp.write_text(original_text, encoding="utf-8")
        rec["dry_run"] = True
        return rec

    # 1 + 2. the script is already written; freeze the plan the planner really
    # produces from it, so the file the assembler reads and the plan the
    # narrator voices are the same object.
    (PLANS / f"{slug}.json").write_text(json.dumps(fresh, indent=2) + "\n",
                                        encoding="utf-8")
    changed = [i for i in range(len(fresh))
               if original_plan[i]["narration"] != fresh[i]["narration"]]
    rec["beats_revoiced"] = changed

    # 3. the audio for that beat, and the manifest entry that describes it
    for i in changed:
        wav = AUDIO / slug / f"{i:04d}.wav"
        if wav.exists():
            wav.unlink()
    bj = AUDIO / slug / "beats.json"
    if bj.exists():
        rows = json.loads(bj.read_text())
        by = {int(r["i"]): r for r in rows if "i" in r}
        for i in changed:
            if i in by:
                by[i]["narration"] = fresh[i]["narration"]
                by[i].pop("seconds", None)   # unvoiced now: not a measurement
        bj.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    # 4. the caption track, which is now timed against words that changed
    for suffix in (".srt", ".vtt", ".chapters.txt", ".timing.json"):
        f = CAPTIONS / f"{slug}{suffix}"
        if f.exists():
            f.unlink()
            rec.setdefault("captions_invalidated", []).append(f.name)

    # 5. the render. MOVED, never deleted -- the same rule the channel has for
    # published video. If the re-render fails, the old cut is still on disk.
    cut = RENDERS / f"{slug}-final.mp4"
    if cut.exists():
        SUPERSEDED.mkdir(parents=True, exist_ok=True)
        # RECORD ITS FINGERPRINT BEFORE MOVING IT, and commit that.
        #
        # THE HAZARD THIS CLOSES, which is the one thing about this repair that
        # could have made things worse. Moving the local render aside does not
        # touch the R2 shelf, and the cloud upload lane reads the SHELF. So the
        # moment the assignment is recorded, the POV gate stops refusing the
        # episode -- and the object the cloud would then pull is the OLD cut,
        # still speaking the sentence she never said. The gate would have been
        # satisfied by a repair the published bytes never received.
        #
        # sha256 is exact and it clears itself: once bin/push-to-r2.sh shelves
        # the re-rendered cut the hash differs and the refusal stops. Nothing
        # is deleted from R2 -- the object is replaced by content, which is how
        # push-to-r2.sh has always worked.
        import r2 as _r2                              # noqa: PLC0415
        sup = read_json(SUPERSEDED_INDEX, default={})
        sup[slug] = {"sha256": _r2.sha256_file(cut),
                     "bytes": cut.stat().st_size,
                     "superseded_at": _now(),
                     "why": "producer POV beat replaced by loop/pov_repair.py"}
        write_json(SUPERSEDED_INDEX, sup)
        cut.replace(SUPERSEDED / cut.name)
        rec["render_superseded"] = f"renders/superseded-pov/{cut.name}"
    side = RENDERS / f"{slug}-final.mp4.render.json"
    if side.exists():
        side.replace(SUPERSEDED / side.name)

    # 6. the assignment, which is the thing the upload gate actually reads
    record_assignment(slug, pick)
    return rec


def record_assignment(slug: str, pick: dict) -> None:
    """Write the match into pov/pov-assignments.json.

    `pov_match.untraced_pov()` reads this file and nothing wrote it, which is
    why every episode authored after 2026-08-30 arrived untraced. Recording a
    MATCH is not approving a line: the line is already in the bank, and the
    bank is her approved voice. Rows carry `matched_by` so a reader can always
    tell a machine match from a hand-curated one.
    """
    p = pov_match.ASSIGNMENTS
    doc = json.loads(p.read_text(encoding="utf-8"))
    rows = [r for r in doc["assignments"] if r.get("video") != slug]
    rows.append({"video": slug, "pov_id": pick["pov_id"],
                 "tier": pick["tier"], "source_answer": pick.get("source_answer"),
                 "line": pick["line"],
                 "matched_by": pick["matched_by"],
                 "recorded_by": "loop/pov_repair.py"})
    doc["assignments"] = sorted(rows, key=lambda r: r["video"])
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def candidates() -> list[str]:
    """Queued, unpublished episodes whose [HUMAN] beat traces to nothing."""
    published = {r["slug"] for r in ledger.load()["published"]}
    return [s for s in pov_match.untraced_pov(batch_queue.queued_slugs())
            if s not in published]


def run(dry_run: bool = False) -> int:
    with Stage(LANE, week_id(),
               zero_work_hint="Every queued, unpublished episode's [HUMAN] beat "
                              "already traces to pov/pov-assignments.json.") as st:
        queued = batch_queue.queued_slugs()
        if not queued:
            st.named_stop(
                "POV_REPAIR_EXAMINED_NOTHING",
                "no queued slugs were found, so this lane examined zero "
                "episodes and cannot claim the POV shelf is clean.",
                unblock="research/publish_order*.json is missing or empty. "
                        "Restore it: git checkout origin/main -- research/")
        st.note(f"examined {len(queued)} queued episode(s)")

        todo = candidates()
        if not todo:
            st.named_stop(
                "POV_ALL_TRACED",
                f"all {len(queued)} queued episode(s) either carry no [HUMAN] "
                f"beat or already trace to pov/pov-assignments.json",
                detail={"examined": len(queued)},
                unblock="Nothing to do. This lane acts again the moment an "
                        "episode is authored with an untraced first-person beat.")

        refused = []
        # Most recent last, exactly as select() documents. Seeded with every
        # assignment already recorded so a repair cannot collide with a line
        # a published episode is already using.
        used = [a["pov_id"] for a in pov_match.hand_assignments().values()]
        for slug in todo:
            rec = repair_one(slug, dry_run=dry_run, used_ids=used)
            if rec.get("pov_id"):
                used.append(rec["pov_id"])
            if rec.get("refused"):
                refused.append((slug, rec["refused"]))
                print(f"  REFUSE {slug}: {rec['refused']}")
                continue
            if rec.get("skipped"):
                st.note(f"{slug}: {rec['skipped']}")
                continue
            st.work(f"{slug}: beat {rec['beat']} now speaks {rec['pov_id']} "
                    f"({rec['matched_by']}) — "
                    f"was {rec['was'][:60]!r}, now {rec['now'][:60]!r}"
                    + ("" if dry_run else "; audio, captions and render "
                                          "invalidated for rebuild"))
        if refused and not st.units:
            st.named_stop(
                "POV_UNREPAIRABLE",
                f"{len(refused)} episode(s) carry an untraced [HUMAN] beat that "
                f"could not be matched to the plan the audio was generated "
                f"from: {', '.join(s for s, _ in refused)}",
                detail={"refused": [{"slug": s, "why": w} for s, w in refused]},
                unblock="The script and plans/<slug>.json have diverged. "
                        "Re-freeze the plan from the script, then re-run this "
                        "lane. Nothing was changed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
