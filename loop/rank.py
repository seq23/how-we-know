"""Sunday 06:00 — mine demand, rank, propose next week's four topics.

Output: `loop/next_topics.json`, the thing the owner spends five minutes on.

Two sources feed the week, in strict priority order:

1. **Authored inventory.** `scripts/` currently holds 20 finished, sourced,
   directive-annotated scripts and nothing has published yet — five weeks of
   runway at the cadence ceiling. While inventory covers the week, the week is
   fully scored already: those questions were chosen and approved by the owner
   when the scripts were written. No competition score is needed to ship them.

2. **Mined demand.** `research/topic_backlog.json` — 2,184 real YouTube
   autocomplete strings, filtered against the approved taxonomy. Demand is
   real. **Competition is not measurable without a YouTube Data API key**, and
   the standing rule is that the loop never publishes against an unscored
   topic list. So mined candidates are emitted as *advisory* — ranked by demand
   with `scored: false` — and the shortfall lane takes a NAMED STOP instead of
   quietly promoting demand evidence into a publishing decision.

The stage always writes the candidate list, so it is never "exit 0 having done
nothing": ranking 2,184 real queries is real work even in the week it also
stops.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger  # noqa: E402
from common import (LOOP, ROOT, Stage, config, now, read_json,  # noqa: E402
                    week_id, write_json)

BACKLOG = ROOT / "research" / "topic_backlog.json"
TAXONOMY = ROOT / "pov" / "topic-taxonomy.json"
OUT = LOOP / "next_topics.json"

# The 16 hard exclusions, expressed as the surface forms an autocomplete string
# would actually carry. Kept alongside the taxonomy, never instead of it.
EXCLUSION_PATTERNS = {
    "Adult or sexual content": r"\b(sex|porn|nude|nsfw|erotic)\b",
    "Drugs, substances, or paraphernalia": r"\b(drug|cocaine|weed|vape|opioid|meth)\b",
    "Firearms, weapons, explosives": r"\b(gun|rifle|firearm|bomb|explosive|ammo)\b",
    "Gambling, betting, trading signals": r"\b(bet|betting|casino|gambl|odds|trading signal)\b",
    "Medical, health, dietary, supplement or mental-health advice":
        r"\b(cure|treat(?:ment)?|symptom|diagnos|supplement|dosage|diet|therapy|depression|anxiety)\b",
    "Financial, investment, tax or legal advice":
        r"\b(invest|stock|crypto|tax|lawsuit|sue|attorney|lawyer)\b",
    "Named living private individuals as subject matter": r"\bnet worth\b",
    "Named companies framed critically": r"\b(scam|fraud|exposed|lawsuit against)\b",
    "Active political controversy, elections, partisan framing":
        r"\b(election|vote|democrat|republican|president|senate|partisan)\b",
    "Religion framed as true or false": r"\b(god|bible|quran|creationis|genesis flood)\b",
    "Conspiracy, cryptid, paranormal, pseudoscience":
        r"\b(conspiracy|cryptid|mermaid|megalodon alive|bermuda triangle|alien|ufo|nessie|loch ness|ghost|haunted|paranormal|flat earth)\b",
    "Recent tragedy involving identifiable victims": r"\b(victims? name|last words|bodies recovered)\b",
    "True crime involving identifiable victims or perpetrators":
        r"\b(murder|killer|homicide|serial killer|true crime)\b",
    "Third-party footage that is not license-cleared": r"\b(full episode|documentary download|leaked footage)\b",
    "Content directed at children (COPPA)": r"\b(for kids|nursery|toddler|baby shark|preschool)\b",
    "Dangerous acts, stunts, replicable harm": r"\b(how to make|diy bomb|challenge gone wrong|stunt)\b",
}


def excluded(query: str):
    """Return the exclusion a query touches, or None. Never auto-published."""
    q = query.lower()
    for name, pat in EXCLUSION_PATTERNS.items():
        if re.search(pat, q):
            return name
    return None


def demand_score(row: dict) -> float:
    """Demand only. Deliberately NOT called a rank: without a competition
    denominator this is half of the ratio the taxonomy's selection rule names.
    """
    s = float(row.get("seed_hits", 1))
    if row.get("is_question"):
        s *= 1.6           # question-form queries are what this channel answers
    w = int(row.get("words", 0))
    if 4 <= w <= 9:
        s *= 1.25          # specific enough to answer in one video
    elif w < 4:
        s *= 0.55          # "why deep sea" is a category, not a question
    return round(s, 2)


def rank_candidates(limit: int = 40) -> tuple[list[dict], dict]:
    d = read_json(BACKLOG)
    seen_q = ledger.published_questions()
    inv_q = {ledger.normalise(s["question"]) for s in ledger.all_scripts()}
    out, skipped = [], {"already_published": 0, "already_authored": 0,
                        "excluded": 0}
    for row in d["queries"]:
        q = row["query"]
        n = ledger.normalise(q)
        if n in seen_q:
            skipped["already_published"] += 1
            continue
        if n in inv_q:
            skipped["already_authored"] += 1
            continue
        ex = excluded(q)
        if ex:
            skipped["excluded"] += 1
            continue
        out.append({
            "query": q,
            "domain": row.get("domain"),
            "seed_hits": row.get("seed_hits"),
            "is_question": row.get("is_question"),
            "demand_score": demand_score(row),
            "competition": None,
            "scored": False,
        })
    out.sort(key=lambda r: -r["demand_score"])
    return out[:limit], skipped


def main() -> None:
    cfg = config()
    per_week = cfg["cadence"]["videos_per_week"]
    week = week_id()
    have_yt_key = bool(os.environ.get(
        cfg["credentials"]["youtube_data_api_key_env"], "").strip())

    with Stage("sun-rank", week,
               zero_work_hint="research/topic_backlog.json produced no usable "
                              "candidates and scripts/ held no unpublished "
                              "script. Re-run research/mine.py.") as st:

        inv = ledger.inventory()
        st.note(f"authored inventory: {len(inv)} unpublished script(s)")

        candidates, skipped = rank_candidates()
        st.work(f"ranked {len(candidates)} mined candidates by demand "
                f"(skipped {skipped})")

        selection = [{
            "slug": s["slug"],
            "question": s["question"],
            "script": s["path"],
            "source": "authored-inventory",
            "scored": True,
            "scored_by": "owner approval at authoring time",
        } for s in inv[:per_week]]

        for s in selection:
            st.work(f"proposed {s['slug']}")

        shortfall = per_week - len(selection)
        doc = {
            "week": week,
            "generated": now(),
            "videos_per_week": per_week,
            "cadence_ceiling_note":
                "Deliberate. Never raised to clear a backlog.",
            "selected": selection,
            "shortfall": shortfall,
            "inventory_remaining": max(0, len(inv) - len(selection)),
            "competition_scoring": {
                "available": have_yt_key,
                "why": "Needs a YouTube Data API key. Until one exists the "
                       "mined list below is demand evidence only and is never "
                       "auto-promoted into a publishing decision.",
            },
            "advisory_candidates": candidates,
            "candidate_skips": skipped,
            "owner_action": "Open docs/approve/ — approve, or swap any row for "
                            "an advisory candidate. Five minutes.",
        }
        write_json(OUT, doc)
        st.work(f"wrote {OUT.relative_to(ROOT)}")

        if shortfall > 0:
            st.named_stop(
                "COMPETITION_UNSCORED",
                f"{shortfall} of {per_week} slot(s) would have to come from the "
                f"mined list, and competition is unscored. The mined candidates "
                f"are written to next_topics.json as advisory; they are not "
                f"promoted to the queue.",
                detail={"shortfall": shortfall,
                        "inventory_remaining": len(inv),
                        "top_advisory": [c["query"] for c in candidates[:8]]},
                unblock="Either add a YOUTUBE_API_KEY repo secret so the "
                        "demand÷competition ratio can be computed, or pick the "
                        "shortfall rows by hand on the approval page. The week "
                        "still ships with whatever inventory covers.",
            )


if __name__ == "__main__":
    main()
