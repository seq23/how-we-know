"""Apply an owner override. Optional, and nothing waits for it.

Topic selection is automatic and POV lines come from her own bank, so there is
no approval step any more. What remains is a veto: if she looks at the week and
does not want one of the four, she drops it.

    bin/loop-override.sh                          # show the week
    bin/loop-override.sh 2026-W36 --drop <slug>   # drop one
    python loop/override.py --week W --body-file issue.txt

The dashboard's Drop button opens a prefilled GitHub issue titled
`OVERRIDE <week>`; a workflow ingests it. Body grammar, forgiving:

    - drop: 03-why-deep-sea-creatures-are-surfacing
    - drop: 04-why-deep-sea-creatures-are-so-scary

The window closes at Tuesday 02:00, when the Mac starts rendering. After that
the week is already built and a drop is a no-op on that week's render - so the
stage says so rather than pretending.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import APPROVALS, LOOP, Stage, now, read_json, write_json  # noqa: E402

QUEUE = LOOP / "render_queue.json"
ROW = re.compile(r"^\s*[-*]?\s*drop:\s*([A-Za-z0-9._-]+)\s*$", re.I | re.M)


def parse(body: str) -> list[str]:
    return [m.group(1) for m in ROW.finditer(body)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--body-file")
    ap.add_argument("--drop", action="append", default=[])
    ap.add_argument("--by", default="owner")
    a = ap.parse_args()

    with Stage("override", a.week,
               zero_work_hint="The override named no row that is in the queue. "
                              "Nothing was changed, which is the safe outcome.") as st:
        queue = read_json(QUEUE, default=None)
        if queue is None:
            st.named_stop("NO_QUEUE", "loop/render_queue.json does not exist",
                          unblock="Run: python loop/draft.py")
        if queue["week"] != a.week:
            st.named_stop(
                "WEEK_MISMATCH",
                f"the override is for {a.week} but the queue holds "
                f"{queue['week']} - refusing to touch a different week",
                unblock="Overrides apply to the current queue only.")

        drops = list(a.drop)
        if a.body_file:
            drops += parse(Path(a.body_file).read_text())
        elif not drops and not sys.stdin.isatty():
            drops += parse(sys.stdin.read())
        drops = [d for d in dict.fromkeys(drops)]

        if not drops:
            st.named_stop("NO_DROPS_NAMED",
                          "the override named nothing to drop",
                          unblock="Use --drop <slug>, or list '- drop: <slug>' "
                                  "lines in the issue body.")

        known = {i["slug"] for i in queue["items"]}
        applied, unknown = [], [d for d in drops if d not in known]
        for it in queue["items"]:
            if it["slug"] in drops:
                it["status"] = "dropped"
                it["dropped_by"] = a.by
                it["dropped_at"] = now()
                applied.append(it["slug"])
                st.work(f"dropped {it['slug']}")

        for u in unknown:
            st.note(f"{u!r} is not in this week's queue - ignored")

        if not applied:
            st.named_stop("NOTHING_DROPPED",
                          "none of the named rows are in this week's queue",
                          detail={"named": drops, "queue": sorted(known)})

        remaining = [i for i in queue["items"] if i["status"] != "dropped"]
        queue["override"] = {"by": a.by, "at": now(), "dropped": applied,
                             "remaining": len(remaining)}
        write_json(QUEUE, queue)
        write_json(APPROVALS / f"{a.week}-override.json",
                   {"week": a.week, "at": now(), "by": a.by,
                    "dropped": applied, "ignored": unknown,
                    "remaining": len(remaining)})
        st.work(f"{len(applied)} dropped, {len(remaining)} still queued")

        if not remaining:
            st.note("every row was dropped; the week will ship nothing, which "
                    "the Tuesday stage will surface as a named stop")


if __name__ == "__main__":
    main()
