"""The thumbnail lane: contract sets for live long-form videos, drama line on $0.

    python loop/thumbs_lane.py            # stage "thumbs", daily in loop-repackage

Owner's lock, 13 Oct 2026: the title stays a clear, short question and the
thumbnail's <=3 words carry the drama or the subject. This stage builds a
contract set (visuals/thumb_contract.py: three variants, one grade, variant A
ships) for every live long-form video whose set is missing or was built for
another title, drafting the drama line on the repo's $0 route (subscription
first) and gating it (thumb_contract.drama_problems). An episode with no
rights-verified picture of its own subject is refused by name and keeps its
thumbnail. `repackage apply` then ships variant A (a rebuilt A goes up alone).
"""
from __future__ import annotations

import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import thumb_contract as TC                                # noqa: E402


def main() -> int:
    import longform_title as LT                            # noqa: PLC0415
    from common import Stage, week_id                      # noqa: PLC0415
    TC.DRAMA_ASK = LT._ask                                 # noqa: SLF001
    with Stage("thumbs", week_id(),
               zero_work_hint="Every live long-form video's thumbnail set "
                              "matches its title.") as st:
        todo = TC.needed_slugs()
        if not todo:
            st.named_stop("THUMBS_UP_TO_DATE",
                          "every live long-form contract set was built for "
                          "today's title", unblock="Nothing to do.")
        refused = []
        for s in todo:
            try:
                r = TC.build_into(s, f"{TC.VARIANTS_DIR}/{s}")
                st.work(f"thumbnail set for {s}: A "
                        f"{r['contract']['variants']['A']['text']!r}")
            except TC.ContractRefused as e:
                refused.append(s)
                st.note(f"refused {s}: {str(e)[:160]}")
        if refused and not st.units:
            st.named_stop("THUMBS_REFUSED",
                          f"{len(refused)} live video(s) have no rights-verified "
                          f"picture of their own subject; they keep their "
                          f"current thumbnail", held_items=sorted(refused),
                          unblock="Nothing to type: harvesting a public-domain "
                                  "image of the subject (research/imagery.py) "
                                  "clears it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
