"""Ingest the owner's approval and stamp the render queue.

The approval page cannot write to the repo — that is the price of being
credentialless — so the return path is a prefilled GitHub issue. This module is
the other end of it: parse the issue body, write
`loop/state/approvals/<week>.json`, and flip every queue row to `approved`.

Body grammar, deliberately forgiving (she may edit it in the GitHub textarea):

    - slug: 01-why-deep-sea-creatures-look-so-weird | pov: bank
    - slug: 02-how-deep-sea-creatures-survive-pressure | pov: script
    APPROVE ALL

A row that is deleted from the body is *not* approved: absent means held, never
assumed. `APPROVE ALL` must be present; without it the stage is a named stop, so
a half-edited issue can never publish anything.

Usage
    python loop/approve.py --week 2026-W36 --body-file body.txt
    python loop/approve.py --week 2026-W36 --all          # local shortcut
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import APPROVALS, LOOP, Stage, now, read_json, write_json  # noqa: E402

QUEUE = LOOP / "render_queue.json"
ROW = re.compile(r"^\s*[-*]?\s*slug:\s*([A-Za-z0-9._-]+)\s*\|\s*pov:\s*(bank|script)\s*$",
                 re.I | re.M)


def parse(body: str) -> tuple[dict, bool]:
    choices = {m.group(1): m.group(2).lower() for m in ROW.finditer(body)}
    approve_all = bool(re.search(r"^\s*APPROVE ALL\s*$", body, re.I | re.M))
    return choices, approve_all


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--body-file")
    ap.add_argument("--all", action="store_true",
                    help="approve every queued row with its default (bank) POV")
    ap.add_argument("--by", default="owner")
    a = ap.parse_args()

    with Stage("approve", a.week,
               zero_work_hint="The render queue held no rows to approve. Run "
                              "loop/draft.py first.") as st:
        queue = read_json(QUEUE, default=None)
        if queue is None:
            st.named_stop("NO_QUEUE", "loop/render_queue.json does not exist",
                          unblock="Run: python loop/draft.py")
        if queue["week"] != a.week:
            st.named_stop(
                "WEEK_MISMATCH",
                f"approval is for {a.week} but the queue is for "
                f"{queue['week']} — refusing to approve a different week's work",
                unblock="Re-open the approval page; it always reflects the "
                        "current queue.")

        if a.all:
            choices = {it["slug"]: "bank" for it in queue["items"]}
            approve_all = True
            st.note("--all: every row approved with its POV bank line")
        else:
            body = Path(a.body_file).read_text() if a.body_file else sys.stdin.read()
            choices, approve_all = parse(body)

        if not approve_all:
            st.named_stop(
                "APPROVE_ALL_MISSING",
                "the approval body did not contain the line 'APPROVE ALL'; "
                "nothing was approved",
                detail={"rows_parsed": len(choices)},
                unblock="Re-open docs/approve/ and press the button, or add the "
                        "line APPROVE ALL to the issue.")

        approved = []
        for it in queue["items"]:
            pick = choices.get(it["slug"])
            if not pick:
                it["status"] = "held"
                st.note(f"{it['slug']}: not present in the approval — held")
                continue
            it["status"] = "approved"
            it["pov_choice"] = pick
            it["pov_final"] = (it.get("pov_bank_line") if pick == "bank"
                               else it.get("pov_script_line"))
            it["approved_at"] = now()
            approved.append(it["slug"])
            st.work(f"approved {it['slug']} (pov: {pick})")

        if not approved:
            st.named_stop(
                "NOTHING_APPROVED",
                "the approval named no row that is in the queue",
                detail={"queue": [i["slug"] for i in queue["items"]],
                        "body_rows": sorted(choices)})

        queue["approval"] = {"required": True,
                             "page": "docs/approve/index.html",
                             "state": "approved",
                             "by": a.by, "at": now(),
                             "approved": approved,
                             "held": [i["slug"] for i in queue["items"]
                                      if i["status"] == "held"]}
        write_json(QUEUE, queue)
        write_json(APPROVALS / f"{a.week}.json",
                   {"week": a.week, "at": now(), "by": a.by,
                    "choices": choices, "approved": approved,
                    "queue_generated": queue["generated"]})
        st.work(f"wrote loop/state/approvals/{a.week}.json "
                f"({len(approved)} approved)")


if __name__ == "__main__":
    main()
