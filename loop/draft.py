"""Monday 06:00 — assemble the week, validate it, publish the approval gate.

Output: `loop/render_queue.json` — **the only handoff to the Mac.** Git is the
message bus; there is no server and no webhook. Whatever this file says on
Tuesday 02:00 is what gets voiced and rendered.

The stage does three things:

1. **Assemble.** For each approved topic, resolve the authored script, its POV
   assignment, its sources and its planned beat count. Where a topic has no
   authored script, write a research brief and take an AUTHOR_REQUIRED named
   stop for that row only — the rest of the week still ships.

2. **Validate.** Run all six validators (`loop/validate.py`). *Any* failure
   trips the circuit breaker with cause `validator`, which halts publishing
   while leaving drafting and rendering intact.

3. **Gate.** Regenerate `docs/approve/index.html` with this week's four rows
   inlined, so the owner's approval is one page, four POV confirmations and one
   button.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import breaker  # noqa: E402
import gate  # noqa: E402
import ledger  # noqa: E402
import validate  # noqa: E402
from common import (BRIEFS, LOOP, ROOT, Stage, config, now,  # noqa: E402
                    read_json, week_id, write_json)

QUEUE = LOOP / "render_queue.json"
TOPICS = LOOP / "next_topics.json"


def brief_for(topic: dict, week: str) -> Path:
    """A research brief for a topic with no authored script.

    Deterministic and source-anchored: it carries the mined demand evidence,
    the taxonomy domain, the eligible POV lines and the directive budget. It
    states no facts of its own, because the pipeline's first rule is that a
    number reaches the screen only through the script's own sourced narration.
    """
    bank = read_json(ROOT / "pov" / "pov-bank.json")["lines"]
    used = {a["pov_id"] for a in
            read_json(ROOT / "pov" / "pov-assignments.json")["assignments"]}
    free = [l for l in bank if l["id"] not in used]
    doc = {
        "week": week,
        "question": topic["question"],
        "domain": topic.get("domain"),
        "demand_evidence": {
            "source": "research/topic_backlog.json (real YouTube autocomplete)",
            "seed_hits": topic.get("seed_hits"),
            "demand_score": topic.get("demand_score"),
            "competition": "UNSCORED — needs YOUTUBE_API_KEY",
        },
        "must_obey": [
            "Every on-screen number and proper name appears verbatim in this "
            "script's own narration (visuals/CONTRACT.md rule 6).",
            "Every digit-bearing sentence maps to a named public source listed "
            "under ## Sources.",
            "No claim of expertise, credentials or professional advice.",
            "State uncertainty and evidence limits explicitly.",
            "Structure must differ from the previous video's shape.",
        ],
        "required_sections": ["# <question>", "## Direct-answer lock",
                              "## Narration", "## Human fingerprint gate",
                              "## Chapters", "## Sources"],
        "eligible_pov_lines": [{"id": l["id"], "tag": l["tag"],
                                "tier": l["tier"], "line": l["line"]}
                               for l in free[:12]],
        "directive_reference": "visuals/CONTRACT.md",
        "note": "Authoring is the one lane a workflow cannot do for $0. Write "
                "this script locally, drop it in scripts/, add its POV row to "
                "pov/pov-assignments.json, and next Monday picks it up as "
                "inventory automatically.",
    }
    p = BRIEFS / f"{week}-{topic.get('slug') or topic['question'][:40]}.json"
    write_json(p, doc)
    return p


def main() -> None:
    cfg = config()
    week = week_id()
    per_week = cfg["cadence"]["videos_per_week"]

    with Stage("mon-draft", week,
               zero_work_hint="loop/next_topics.json selected nothing. Run "
                              "loop/rank.py, or check the authored inventory "
                              "in scripts/.") as st:

        topics = read_json(TOPICS, default=None)
        if topics is None:
            st.named_stop("NO_TOPICS", "loop/next_topics.json does not exist",
                          unblock="Run: python loop/rank.py")
        if topics["week"] != week:
            st.note(f"next_topics.json is for {topics['week']}, today is {week}"
                    " — using it anyway (a re-run inside the same cycle)")

        # ---- 1. assemble -------------------------------------------------
        items, unauthored = [], []
        for t in topics["selected"][:per_week]:
            script = ROOT / t["script"] if t.get("script") else None
            if not script or not script.exists():
                unauthored.append(t)
                continue
            items.append({
                "slug": t["slug"],
                "question": t["question"],
                "script": t["script"],
                "work_copy": f"loop/work/{t['slug']}.md",
                "audio_dir": f"audio/{t['slug']}",
                "plan": f"loop/plans/{t['slug']}.json",
                "render": f"renders/{t['slug']}.mp4",
                "source": t.get("source", "authored-inventory"),
                "pov_needs_confirmation": False,
                "status": "pending-approval",
            })
            st.work(f"assembled {t['slug']}")

        for t in unauthored:
            p = brief_for(t, week)
            st.work(f"wrote research brief {p.relative_to(ROOT)}")

        if not items:
            st.named_stop(
                "NO_APPROVED_SCRIPTS",
                "zero scripts are available for this week — nothing can be "
                "voiced on Tuesday",
                detail={"unauthored": [t.get("question") for t in unauthored],
                        "inventory_remaining": topics.get("inventory_remaining")},
                unblock="Author the briefs in loop/briefs/ into scripts/, or "
                        "reduce the week deliberately. The cadence ceiling is "
                        "never raised to compensate.")

        if len(items) > per_week:  # belt and braces; the slice above prevents it
            st.named_stop("CADENCE_CEILING",
                          f"{len(items)} items exceeds the deliberate ceiling "
                          f"of {per_week}")

        # ---- 2. validate -------------------------------------------------
        passed, report = validate.run_all(items)
        for row in report:
            st.note(f"{row['status']:<16} {row['validator']} "
                    f"(examined {row['examined']})")
            for f in row["failures"]:
                print(f"      ✗ {f}", flush=True)
        st.work(f"ran {len(report)} validators over {len(items)} item(s)")

        queue = {
            "week": week,
            "generated": now(),
            "videos_per_week": per_week,
            "breaker": breaker.load().get("state", "closed"),
            "validators": report,
            "validators_passed": passed,
            "approval": {
                "required": True,
                "page": "docs/approve/index.html",
                "state": "pending",
                "file": f"loop/state/approvals/{week}.json",
            },
            "items": items,
            "unauthored": [t.get("question") for t in unauthored],
        }
        write_json(QUEUE, queue)
        st.work(f"wrote {QUEUE.relative_to(ROOT)} with {len(items)} item(s)")

        # ---- 3. the gate -------------------------------------------------
        page = gate.build(queue, topics)
        st.work(f"rebuilt approval page {Path(page).relative_to(ROOT)}")

        if not passed:
            breaker.trip("validator",
                         "; ".join(f"{r['validator']}={r['status']}"
                                   for r in report if "FAIL" in r["status"]))
            st.named_stop(
                "VALIDATOR_FAILED",
                "a validator failed; the circuit breaker is now tripped and "
                "publishing is halted. Drafting and rendering are untouched.",
                detail=[r for r in report if "FAIL" in r["status"]],
                unblock="Fix the failure, re-run python loop/draft.py, then "
                        "python loop/breaker.py reset --note \"…\"")

        if unauthored:
            st.named_stop(
                "AUTHOR_REQUIRED",
                f"{len(unauthored)} slot(s) had no authored script; briefs were "
                f"written to loop/briefs/. The week still ships "
                f"{len(items)} video(s).",
                detail={"briefs": [t.get("question") for t in unauthored]},
                unblock="Author the briefs into scripts/ and add their POV rows "
                        "to pov/pov-assignments.json.")


if __name__ == "__main__":
    main()
