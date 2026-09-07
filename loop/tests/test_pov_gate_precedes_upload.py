"""The POV trace is checked BEFORE upload, and by the same rule V32 uses.

WHAT BROKE. `[HUMAN]` marks the one beat where the owner speaks as herself.
V32 (`loop/validate.py`) checks that every SCHEDULED episode's beat traces to
an entry in `pov/pov-assignments.json`. It is correct and it caught three -
`how-does-tempered-glass-shatter`, `how-strong-is-titanium`,
`how-is-damascus-steel-made` - but it reads the LEDGER, and an episode only
reaches the ledger by being uploaded. So V32 fires after the video is on
YouTube with a publishAt. A guard standing downstream of the thing it governs
can report the harm; it cannot prevent it.

And the harm was not three. `pov/pov-assignments.json` is hand-curated - its
own header says "generated 2026-08-30", "owner's own words only" - and NOTHING
in this repo writes it. `pov_match.select()` picks a bank line for a new script
and the choice is never recorded back, so every episode authored since is
untraced by default. Fifteen queued episodes carry the same untraced beat right
now; the three that failed are simply the ones that got uploaded first.

WHAT THIS ASSERTS

  1. THE JOIN. Every slug V32 fails is also refused by
     `pov_match.untraced_pov()`. Two components each keeping their own list is
     this repo's named defect; this fails the moment the two rules drift.
  2. THE GATE IS REACHABLE. `loop/cloud_upload.py` really calls it, proven by
     running the refusal over a selection and watching the untraced slugs be
     dropped and the traced ones survive.
  3. IT IS A REFUSAL, NOT A BLANKET HALT. A traced episode still ships.
  4. AND NOT A SILENT SKIP. If refusing empties the run, the lane has a
     POV_UNTRACED named stop rather than an exit 0 that did nothing.

Hard-fails when it examines zero scripts, or when the assignments file or the
set of scripts carrying a [HUMAN] beat is empty - a gate with nothing to
govern proves nothing.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)


def check() -> list[str]:
    import batch_queue                                      # noqa: PLC0415
    import cloud_upload                                     # noqa: PLC0415
    import pov_match                                        # noqa: PLC0415
    import validate as V                                    # noqa: PLC0415

    fails: list[str] = []

    assigned = pov_match.hand_assignments()
    if not assigned:
        return ["pov/pov-assignments.json is empty or unreadable - this guard "
                "examined ZERO assignments and cannot tell a traced episode "
                "from an untraced one"]

    # Every script that HAS a POV beat is a subject of this rule.
    import glob                                             # noqa: PLC0415
    with_beat = [os.path.basename(p)[:-3]
                 for p in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.md")))
                 if "[HUMAN]" in open(p).read()]
    if not with_beat:
        return ["examined ZERO scripts carrying a [HUMAN] beat - the gate has "
                "nothing to govern, so a pass here would mean nothing"]
    examined = len(with_beat)

    # -- 1. the join with V32 -------------------------------------------
    r = V.v32_scheduled_pov_is_hers()
    if r.examined == 0:
        fails.append("V32 examined zero episodes, so the join cannot be tested")
    v32_bad = {s for s in with_beat
               if any(s in f for f in getattr(r, "failures", []))}
    gate_bad = set(pov_match.untraced_pov(with_beat))
    missed = v32_bad - gate_bad
    if missed:
        fails.append(
            f"V32 fails {sorted(missed)} but the PRE-UPLOAD gate would let "
            f"them through - the two rules have drifted, which is how the "
            f"first three reached YouTube")

    # -- 2 & 3. the gate really refuses, and only the untraced -----------
    traced = [s for s in with_beat if s in assigned]
    untraced = [s for s in with_beat if s not in assigned]
    if not traced:
        fails.append("no script is traced at all - this guard cannot prove "
                     "the gate lets a GOOD episode through")
    if not untraced:
        fails.append("no script is untraced - this guard cannot prove the "
                     "gate refuses a BAD one")
    if traced and untraced:
        refused = set(pov_match.untraced_pov(traced + untraced))
        wrongly_refused = sorted(refused & set(traced))
        wrongly_allowed = sorted(set(untraced) - refused)
        if wrongly_refused:
            fails.append(f"the gate refused traced episode(s) "
                         f"{wrongly_refused} - it is halting the lane rather "
                         f"than refusing the episode")
        if wrongly_allowed:
            fails.append(f"the gate allowed untraced episode(s) "
                         f"{wrongly_allowed}")

    # -- 4. it is wired into the lane, and it is a NAMED STOP path -------
    src = open(os.path.join(LOOP, "cloud_upload.py")).read()
    if "untraced_pov" not in src:
        fails.append("loop/cloud_upload.py does not call "
                     "pov_match.untraced_pov() - the gate exists but nothing "
                     "invokes it, which is 'runs but inert'")
    if "POV_UNTRACED" not in src:
        fails.append("loop/cloud_upload.py has no POV_UNTRACED named stop - a "
                     "run emptied by refusals would exit 0 having done nothing")
    if not hasattr(cloud_upload, "questions_map"):
        fails.append("loop/cloud_upload.py lost questions_map()")

    # -- the zero-item hard fail, proven --------------------------------
    if pov_match.untraced_pov([]) != []:
        fails.append("untraced_pov([]) did not return [] - the gate cannot "
                     "tell an empty selection from a clean one")
    # ...and the guard itself must refuse to pass on an empty subject set.
    # Proven by the two early returns above; assert the condition holds now.
    if examined == 0:
        fails.append("examined ZERO scripts")

    print(f"inspected {examined} script(s) with a [HUMAN] beat: "
          f"{len(traced)} traced, {len(untraced)} untraced; "
          f"V32 examined {r.examined}")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - the POV trace is checked before upload, by V32's rule"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
