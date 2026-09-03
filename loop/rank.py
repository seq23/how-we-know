"""Sunday 06:00 - mine demand, rank, and PICK next week's four topics.

The owner gave blanket topic approval: pick whatever the data says will earn
passively, subject only to hard exclusions. So this stage decides, and she is
notified rather than asked. Nothing waits on her.

Two sources feed the week:

1. **Authored inventory.** `scripts/` holds finished, sourced, human-written
   scripts that have not published yet. Free and already validated, so they go
   first.
2. **Mined demand.** `research/topic_backlog.json` - 2,184 real YouTube
   autocomplete strings. Every candidate passes `loop/exclusions.py`, the hard
   programmatic gate that now carries her judgement. The shortfall is handed to
   the authoring lane on Monday.

Competition scoring still needs a YouTube Data API key. Its absence no longer
stops the week: demand ranking picks, the exclusion gate constrains, and the
`competition_scoring.available` flag records that the ratio was half-computed.
An unscored ranking is a weaker ranking, not an unsafe one - safety comes from
the gate, which is absolute either way.

**Rule 0 here means: an empty admitted set is a hard failure, not a pass.**
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadence  # noqa: E402
import exclusions  # noqa: E402
import ledger  # noqa: E402
import pov_match  # noqa: E402
from common import (LOOP, ROOT, Stage, config, now, read_json,  # noqa: E402
                    week_id, write_json)

BACKLOG = ROOT / "research" / "topic_backlog.json"
TAXONOMY = ROOT / "pov" / "topic-taxonomy.json"
OUT = LOOP / "next_topics.json"

# The plan's measured finding, restated: "Every opening is a 'why does...' or
# 'how does...' question. Every dead end is a 'what is a...'." Measured across
# all 20 scripts - "what is a frilled shark" returned 20/20 strong title
# matches, "why does black-smoker water not boil" returned 0/20.
MECHANISM_Q = re.compile(r"^(why|how)\b", re.I)
IDENTITY_Q = re.compile(r"^what (?:is|are) (?:a|an|the)\b", re.I)


def shape_score(row: dict) -> float:
    """Question SHAPE, not demand. Deliberately not called demand_score.

    `seed_hits` is dead and must stay dead: it counted how many a-z variants of
    one seed string produced a hit, so it measured seed-string length rather
    than demand - 81% of multi-hit queries got every hit from variants of a
    single seed. The plan retires it and this function does not touch it.

    Real demand and competition are measured by the research agent's weekly
    scoring pass, which writes research/publish_order.json. Until a candidate
    has been through that pass it carries NO demand measurement, and this score
    only orders the queue of things to send for scoring. Every row it produces
    is marked `demand_measured: false` so nothing downstream can mistake shape
    for demand.
    """
    q = row.get("query", "")
    s = 1.0
    if MECHANISM_Q.match(q):
        s *= 2.0           # the shape that consistently found an opening
    elif IDENTITY_Q.match(q):
        s *= 0.4           # the shape that was consistently already answered
    elif row.get("is_question"):
        s *= 1.2
    w = int(row.get("words", 0))
    if 4 <= w <= 9:
        s *= 1.25          # specific enough to answer in one video
    elif w < 4:
        s *= 0.55          # "why deep sea" is a category, not a question
    return round(s, 3)


def rank_candidates(limit: int = 40) -> tuple[list[dict], dict, list[dict]]:
    d = read_json(BACKLOG)
    seen_q = ledger.published_questions()
    inv_q = {ledger.normalise(s["question"]) for s in ledger.all_scripts()}
    out, refusals = [], []
    skipped = {"already_published": 0, "already_authored": 0, "excluded": 0}
    for row in d["queries"]:
        q = row["query"]
        n = ledger.normalise(q)
        if n in seen_q:
            skipped["already_published"] += 1
            continue
        if n in inv_q:
            skipped["already_authored"] += 1
            continue
        d = exclusions.decide(q, row.get("domain"))
        if not d.admitted:
            skipped["excluded"] += 1
            refusals.append({"query": q, "rule": d.rule, "matched": d.matched})
            continue
        out.append({
            "query": q,
            "domain": row.get("domain"),
            "seed_hits": row.get("seed_hits"),
            "is_question": row.get("is_question"),
            # NOT demand. Shape only, until the weekly scoring pass measures it.
            "shape_score": shape_score(row),
            "demand_measured": False,
            "competition": None,
            "scored": False,
            "note": "shape_score orders candidates for SCORING, never for "
                    "publishing. Demand and competition come from "
                    "research/publish_order.json.",
        })
    out.sort(key=lambda r: -r["shape_score"])
    return out[:limit], skipped, refusals


def main() -> None:
    cfg = config()
    per_week, cadence_why = cadence.effective(explain=True)
    week = week_id()
    have_yt_key = bool(os.environ.get(
        cfg["credentials"]["youtube_data_api_key_env"], "").strip())

    with Stage("sun-rank", week,
               zero_work_hint="research/topic_backlog.json produced no admitted "
                              "candidate and scripts/ held no unpublished "
                              "script. Re-run research/mine.py.") as st:

        st.note(f"cadence: {cadence_why}")

        # Publish order is another agent's file and is READ ONLY here. Its
        # absence is a named stop, never a fallback to filename order.
        try:
            inv, order_meta = cadence.ordered_inventory()
        except cadence.PublishOrderStale as e:
            # Loud, not invisible. A stale ranking is the dangerous case: the
            # loop would keep publishing in last month's order and look
            # perfectly healthy doing it.
            st.named_stop(
                "PUBLISH_ORDER_STALE", str(e),
                detail={"threshold_days":
                        config()["publish_order"]["staleness_days"],
                        "meta": cadence.order_meta_raw()},
                unblock="Run the weekly scoring stage: "
                        ".venv/bin/python loop/score.py (Actions runs it every "
                        "Saturday). The loop will not publish against a "
                        "ranking this old.")
        except cadence.PublishOrderMissing as e:
            st.named_stop(
                "PUBLISH_ORDER_MISSING", str(e),
                detail={"expected": str(cadence.PUBLISH_ORDER.relative_to(ROOT))},
                unblock="research/publish_order.json ranks the scripts on "
                        "demand/competition with title coverage weighted 50%. "
                        "It is generated by another agent. Until it exists the "
                        "loop will not pick a publish sequence - it refuses "
                        "rather than defaulting to episode order.")
        st.note(f"publish order: {order_meta['ranked']} ranked, "
                f"{order_meta['unranked']} unranked, from {order_meta['source']}")
        if order_meta["unranked"]:
            st.note(f"{order_meta['unranked']} unpublished script(s) are not in "
                    f"the ranking; they queue AFTER every ranked entry, never "
                    f"promoted to the front")

        # The runway guard. Loud and early, and it never halts publishing -
        # stopping the channel to protect the backlog would be going dark.
        rw = cadence.runway(per_week)
        st.note(f"runway: {rw['message']}")

        candidates, skipped, refusals = rank_candidates()
        st.work(f"ranked {len(candidates)} admitted candidates by demand; "
                f"the exclusion gate refused {skipped['excluded']}")

        # ---- pick automatically. She is notified, not asked. ----
        selection = [{
            "slug": s_["slug"],
            "question": s_["question"],
            "script": s_["path"],
            "source": "authored-inventory",
            "publish_rank": s_.get("publish_rank"),
            "front_loaded": s_.get("front_loaded", False),
            "needs_authoring": False,
        } for s_ in inv[:per_week]]

        for c in candidates:
            if len(selection) >= per_week:
                break
            slug = re.sub(r"[^a-z0-9]+", "-", c["query"].lower()).strip("-")[:60]
            selection.append({
                "slug": slug,
                "question": c["query"],
                "script": f"loop/drafts/{slug}.md",
                "source": "mined-demand",
                "domain": c.get("domain"),
                "shape_score": c["shape_score"],
                "seed_hits_provenance_only": c.get("seed_hits"),
                "needs_authoring": True,
            })

        # Rule 0, and the owner's judgement, both land here: an empty admitted
        # set is a hard failure. It never degrades into publishing nothing
        # quietly, and it never degrades into publishing something ungated.
        if not selection:
            st.named_stop(
                "NO_ADMITTED_TOPICS",
                f"zero topics survived selection: {len(inv)} inventory scripts "
                f"and {len(candidates)} admitted candidates. The exclusion gate "
                f"refused {skipped['excluded']}.",
                detail={"skipped": skipped,
                        "sample_refusals": refusals[:10]},
                unblock="Re-run research/mine.py for fresh candidates, or widen "
                        "research/seeds.json. The gate is not the thing to "
                        "loosen.")

        # Match a POV line to every pick now, so Monday has nothing to decide.
        used = [r.get("pov_id") for r in ledger.load()["published"]]
        try:
            selection = pov_match.select_week(selection, used)
        except pov_match.NoPovMatch as e:
            st.named_stop("NO_POV_MATCH", str(e),
                          unblock="Add lines to pov/pov-bank.json, or wait for "
                                  "the rotation window to clear. The pipeline "
                                  "does not invent a POV line.")

        for s_ in selection:
            st.work(f"picked {s_['slug']} "
                    f"({s_['source']}, pov {s_['pov_id']})")

        doc = {
            "week": week,
            "generated": now(),
            "videos_per_week": per_week,
            "cadence_ceiling_note": "Deliberate. Never raised to clear a backlog.",
            "selection_mode": "automatic",
            "owner_involvement": "notified, not asked",
            "selected": selection,
            "to_author": sum(1 for s_ in selection if s_["needs_authoring"]),
            "inventory_remaining": max(0, len(inv) - sum(
                1 for s_ in selection if not s_["needs_authoring"])),
            "cadence": {"videos_per_week": per_week, "why": cadence_why},
            "publish_order": order_meta,
            "runway": rw,
            "gate": {
                "authority": "pov/topic-taxonomy.json",
                "enforced_by": "loop/exclusions.py",
                "refused_this_week": skipped["excluded"],
                "refusals_sample": refusals[:15],
            },
            "competition_scoring": {
                "available": have_yt_key,
                "why": "Needs a YouTube Data API key. Without it the ranking is "
                       "demand-only - a weaker ranking, not an unsafe one. "
                       "Safety comes from the exclusion gate, which is absolute "
                       "either way.",
            },
            "advisory_candidates": candidates,
            "candidate_skips": skipped,
            "override": {
                "how": "Open docs/approve/ and press Drop, or run "
                       "bin/loop-override.sh <week> <slug>",
                "closes": "Tuesday 02:00, when the Mac starts rendering",
            },
        }
        write_json(OUT, doc)
        st.work(f"wrote {OUT.relative_to(ROOT)} - {len(selection)} picked, "
                f"{doc['to_author']} to author")

        # THE QUEUE-DEPTH GUARD, surfaced. The owner raised the target to
        # 4/week on 2026-09-02; the loop raises itself only when the queue can
        # carry it. When the raise is armed - the authoring lane has proved
        # itself - but the queue cannot, that refusal must reach a human. The
        # alternative is a channel that quietly publishes at the old rate while
        # everyone believes it scaled, which is this repo's "runs but inert"
        # failure class wearing a cadence label.
        #
        # Like the runway stop below, it is raised AFTER the week is written,
        # so it costs the week nothing. Publishing continues at the lower
        # cadence; nothing goes dark.
        scale = cfg["cadence"].get("scale", {})
        want = int(scale.get("to", per_week))
        if (scale.get("automatic") and cadence.authoring_evidence()
                and want > per_week and rw["level"] == "ok"):
            ok_to_scale, why_not = cadence.queue_supports(want)
            if not ok_to_scale:
                st.named_stop(
                    "CADENCE_SCALE_WITHHELD",
                    f"the cadence target is {want}/week but the loop is "
                    f"holding at {per_week}/week: {why_not}",
                    detail={"target": want, "holding_at": per_week,
                            "runway_at_target": cadence.runway(want)},
                    unblock=(
                        "Nothing is broken and nothing has stopped - the "
                        f"channel keeps publishing at {per_week}/week and "
                        "every episode already scheduled airs on its own "
                        "date.\n\n"
                        "The raise arms ITSELF the moment the queue can carry "
                        "it. To bring that forward, add runway: let the "
                        "authoring lane run (it writes "
                        f"{per_week} script(s) a week now, {want} once it "
                        "scales), then narrate and render them on the Mac with "
                        "bin/batch-session.sh. Scripts alone are not runway - "
                        "a rendered episode is.\n\n"
                        "If you would rather scale on a thinner queue, lower "
                        "cadence.scale.requires_runway_weeks in "
                        "loop/config.json. That is a real trade: it buys "
                        "episodes now against the risk of a gap later, and a "
                        "gap costs more than the extra episodes earn."))

        # Surfaced LAST and deliberately: the week is already written, so this
        # warns without costing the week. It is a named stop, which means an
        # issue and an email - weeks ahead of running out, not on the week it
        # happens.
        if rw["level"] in ("warn", "critical"):
            st.named_stop(
                f"RUNWAY_{rw['level'].upper()}",
                rw["message"],
                detail=rw,
                unblock=(
                    "TWO things, and the second is easy to miss.\n\n"
                    "1. Refill scripts: the authoring lane (loop/author.py) "
                    "writes them, or add them by hand.\n\n"
                    "2. BATCH THE VOICE AND RENDER YOURSELF. Those stages "
                    "cannot run in GitHub Actions - the voice model is local "
                    "and the upload credential lives in .secrets/, not in "
                    "GitHub - and the Mac-side launchd jobs are deliberately "
                    "NOT installed (decided 2026-08-31: a 6am job on a laptop "
                    "that sleeps would fail quietly some weeks). A script "
                    "existing does NOT mean a video exists. One overnight "
                    "pass produces roughly eight weeks:\n\n"
                    "    cd ~/GitHub/how-we-know\n"
                    "    ./voice/narrate-all.sh\n"
                    "    nohup caffeinate -i -m bash bin/assemble-all.sh &\n\n"
                    "The week above still ships - publishing is never halted "
                    "to protect the backlog, because that IS going dark."))


if __name__ == "__main__":
    main()
