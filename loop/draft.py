"""Monday 06:00 - assemble the week, author what is missing, validate, publish.

Output: `loop/render_queue.json` - the only handoff to the Mac.

Nothing here waits on the owner. Topics were picked automatically on Sunday and
POV lines were matched from her bank, which IS her approved voice. This stage:

1. **Assembles** every picked topic that already has an authored script.
2. **Authors** the rest through `loop/author.py` (OpenRouter). A generated
   script is validated at FULL strength - the validators are not relaxed
   because a machine wrote it, they matter more, and V8 fetches every citation
   because a fabricated URL is an LLM's signature failure.
3. **Validates** the week. Any hard failure trips the circuit breaker.
4. **Publishes the dashboard** at `docs/approve/` - what was picked, what was
   drafted, what it cost, with a Drop button. Read-only by default. Nothing
   blocks on it.

`AUTHOR_REQUIRED` is now the *fallback*, reached only when generation fails or
its output fails validation - not the normal path.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import batch_queue  # noqa: E402 - loop/ is put on sys.path above
import breaker  # noqa: E402
import author  # noqa: E402
import cadence  # noqa: E402
import domains  # noqa: E402
import gate  # noqa: E402
import ledger  # noqa: E402
import pov_match  # noqa: E402
import rank  # noqa: E402 - loop/ is put on sys.path above
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


def rebuild_runway_if_short(st, cfg: dict, per_week: int, used_slugs: list[str],
                            skip_slugs: set[str]) -> None:
    """A runway warning that only ever LOGGED is a warning nobody has to act
    on until it is nearly too late. 2026-09-03: `runway.warn_weeks`/
    `critical_weeks` existed only as a number in a report; nothing ran the
    authoring lane because of it. This does.

    Runs AFTER the week's own selection has already been authored, validated
    and queued — this never competes with or blocks that work, it is purely
    additive. It authors extra inventory for whichever domain(s)
    `cadence.runway()` names as short (or, with no domain data, for the
    aggregate), validates each at full strength, and — only if it clears
    validation — PROMOTES it into `scripts/`, which is the one directory
    `ledger.inventory()` and next week's runway figure actually count.
    `loop/drafts/` alone does not rebuild runway; nothing counts it.

    Bounded at `runway.rebuild_max_extra` (default 3) so a bad week cannot
    spend the whole OpenRouter budget chasing a number. If authoring cannot
    produce even one extra script — no key, an exhausted domain queue, every
    attempt failing validation — that is the fallback-to-human this item asks
    for: a NAMED STOP naming which domain is short, how many weeks remain,
    and the calendar date the channel goes dark for that domain if nothing
    changes. It never trips the circuit breaker and never blocks the week
    already queued above; `never_go_dark` still means nothing here ever halts
    publishing to protect the backlog.
    """
    rw = cadence.runway(per_week)
    short = rw.get("short_domains") or ([] if rw["level"] == "ok" else ["any"])
    if not short:
        st.note(f"runway rebuild: not needed - {rw['message']}")
        return

    # THE WHOLE PUBLISH QUEUE, every research/publish_order*.json, through
    # the same helper rank.py selects from. This read the deep-sea file by
    # name, so a short materials runway could never find a candidate.
    by_dom = domains.by_slug()
    candidates = []
    for row in batch_queue.unwritten_entries():
        slug = row.get("slug")
        if not slug or slug in skip_slugs:
            continue
        # A queued topic with no script has no **Domain:** line yet, so the
        # row (or its file) names the domain - the same fallback
        # domains.queue_depth() uses. by_slug() alone mapped every candidate
        # to None, and a per-domain shortfall could never match one.
        dom = (by_dom.get(slug) or row.get("domain")
               or read_json(ROOT / "research" / row["_domain_file"],
                            default={}).get("domain"))
        if "any" in short or dom in short:
            candidates.append((row, dom))

    # SAME DOMAIN GUARD AS loop/draft.py main() step 0b, applied here too —
    # `short` is meant to name only allocated domains (cadence.runway() reads
    # domains.allocation), but this path also authors and promotes straight
    # to scripts/, so it re-checks rather than trusting that invariant holds.
    alloc = domains.allocation(cfg)
    allocated_candidates = [(row, dom) for row, dom in candidates if dom in alloc]
    for row, dom in candidates:
        if dom not in alloc:
            st.note(f"runway rebuild: {row['slug']} names domain {dom!r}, "
                    f"not in domains.allocation — refused, not authored")
    candidates = allocated_candidates

    cap = int(cfg.get("runway", {}).get("rebuild_max_extra", 3))
    authored, failed = [], []
    for row, dom in candidates[:cap]:
        slug, question = row["slug"], row.get("query", row.get("question", ""))
        try:
            pov = pov_match.select(slug, question, used_slugs)
        except pov_match.NoPovMatch as e:
            failed.append(f"{slug}: no POV line available ({e})")
            continue
        try:
            res = author.draft(question, slug,
                               {"pov_id": pov["pov_id"], "line": pov["line"]},
                               domain=dom or domains.UNSUFFIXED_FILE_DOMAIN)
        except author.AuthorStop as e:
            failed.append(f"{slug}: [{e.code}] {e.message}")
            continue
        draft_path = ROOT / res["path"]
        text = draft_path.read_text(encoding="utf-8")
        item = {"slug": slug, "question": question, "script": res["path"],
                "generated": True}
        passed, report = validate.run_all([item])
        if passed:
            # Evidence is recorded ONLY inside this passed-validators branch —
            # loop/validate_plan.py check 2 enforces exactly this shape (the
            # same one loop/draft.py's own main() flow uses) so an unvalidated
            # script can never unlock the cadence escalation.
            dest = ROOT / "scripts" / f"{slug}.md"
            dest.write_text(text, encoding="utf-8")
            ev = cadence.record_authoring_evidence(
                slug, str(dest.relative_to(ROOT)), report)
            authored.append(slug)
            used_slugs.append(pov["pov_id"])
            # RECORD WHICH BANK LINE THIS EPISODE BORROWED, inside the branch
            # that already promoted the script — so a draft that failed
            # validation never leaves an assignment behind for a script that
            # does not exist. Without this the loop selected a line, cited it
            # in the script, and wrote nothing down; V32 then refused the
            # episode weeks later and asked the owner to approve a line she had
            # already given in an interview.
            pov_match.record_assignment(slug, pov)
        else:
            failed.append(
                f"{slug}: failed validation "
                f"({'; '.join(r['validator'] for r in report if 'FAIL' in r['status'])})")
            continue
        st.work(f"runway rebuild ({dom or 'unattributed'}): authored and "
                f"promoted {slug} to scripts/ — {len(ev['scripts'])} "
                f"validated generated script(s) on record")

    for f in failed:
        st.note(f"runway rebuild: {f}")

    if authored:
        st.note(f"runway rebuild: added {len(authored)} script(s) to "
                f"inventory for {', '.join(short)}")
        return

    # Nothing could be authored. This is the fallback-to-human, named and
    # dated — never a silent "tried and gave up".
    import datetime as _dt                                   # noqa: PLC0415
    dark_by = {}
    for name in short:
        d = rw.get("by_domain", {}).get(name)
        weeks = d["weeks"] if d and d.get("weeks") is not None else \
            rw["weeks_remaining"]
        dark_by[name] = (_dt.date.today() +
                         _dt.timedelta(weeks=weeks)).isoformat()
    st.named_stop(
        "RUNWAY_AUTHORING_FALLBACK",
        f"runway is {rw['level']} for {', '.join(short)} and the authoring "
        f"lane could not add a single script to cover it. "
        f"{'; '.join(failed) or 'no candidate topics were queued for the '
                                'short domain(s) in research/publish_order.json'}",
        detail={"short_domains": short, "by_domain": rw.get("by_domain"),
                "goes_dark_by": dark_by, "failures": failed},
        unblock=(
            "This week's own queue already shipped and is unaffected. "
            + "; ".join(f"{n} needs more scored topics in "
                       f"research/publish_order.json (or a working "
                       f"OPENROUTER_API_KEY if authoring itself is what "
                       f"failed) before {d} or it goes dark"
                       for n, d in dark_by.items())))


def promote_to_scripts(st, item: dict) -> None:
    """A validated, generated script for a PUBLISH-QUEUE topic goes to
    scripts/<slug>.md, the one path bin/batch-session.sh narrates from.

    Called only inside the passed-validators branch. Before the publish-queue
    rule a generated script stayed in loop/drafts/, where nothing on the Mac
    ever reads - it was runway on paper only. Every item that reaches here has
    already passed batch_queue.publish_queue_gate(), so the queue row exists
    and the script is now the last thing the batch needs. A hand-written
    script already at scripts/<slug>.md is never overwritten.
    """
    dest = ROOT / "scripts" / f"{item['slug']}.md"
    if dest.exists():
        st.note(f"{item['slug']}: scripts/ already holds a script; the draft "
                f"was not promoted over it")
        return
    dest.write_text((ROOT / item["script"]).read_text(encoding="utf-8"),
                    encoding="utf-8")
    item["script"] = str(dest.relative_to(ROOT))
    if item.get("pov_id") and item.get("pov_line"):
        pov_match.record_assignment(
            item["slug"], {"pov_id": item["pov_id"], "line": item["pov_line"],
                           "tier": item.get("pov_tier", "transferable")})
    st.work(f"promoted {item['slug']} to {item['script']} - queued in the "
            f"publish order, so the Mac's batch will narrate it")


def main() -> None:
    cfg = config()
    week = week_id()
    per_week, cadence_why = cadence.effective(explain=True)

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

        # ---- 0. ONLY TOPICS ALREADY IN THE PUBLISH QUEUE -------------
        # Owner decision, 2026-09-23. loop/rank.py already selects only from
        # research/publish_order*.json; this is the same gate applied again
        # here, because this is the lane that spends money and writes the
        # hand-off, and a stale or hand-edited next_topics.json must not be
        # able to route around it. On 2026-09-21 this loop authored four
        # mined topics in no publish queue; the Mac's batch reads only that
        # queue, so they could never air. A refusal is printed by name.
        selected = list(topics.get("selected") or [])
        allowed, refused = batch_queue.publish_queue_gate(
            [t.get("slug") for t in selected])
        for slug_, why_ in refused.items():
            print(f"  REFUSE {slug_}: {why_}", flush=True)
        if refused:
            st.note(f"refused {len(refused)} selected topic(s) outside the "
                    f"publish queue: {', '.join(refused)}. Nothing was "
                    f"authored or queued for them; nothing was deleted.")
        selected = [t for t in selected if t.get("slug") in set(allowed)]

        # ---- 0b. ONLY DOMAINS CURRENTLY IN domains.allocation ---------
        # Owner decision, 2026-09-23 (corrected scope). The publish-queue
        # gate above closes the mined-demand path, but it is a QUEUE check,
        # not a DOMAIN check: a row can be genuinely scored and sitting in a
        # real research/publish_order*.json file for a domain that has since
        # been retired from loop/config.json domains.allocation, or that was
        # scored by hand before ever being allocated. Authoring it anyway is
        # exactly how the 2026-09-21 method-evidence/space scripts shipped
        # with no publish slot, no loop/domain_sources.py allowlist and no
        # visuals/domains.py palette (they are held in
        # loop/promotion_holds.json, a separate fix). This is the second,
        # independent gate — see loop/domains.py allocation_gate().
        selected, dom_refused = domains.allocation_gate(selected, cfg)
        for slug_, why_ in dom_refused.items():
            print(f"  REFUSE {slug_}: {why_}", flush=True)
        if dom_refused:
            st.note(f"refused {len(dom_refused)} selected topic(s) outside "
                    f"domains.allocation: {', '.join(dom_refused)}. Nothing "
                    f"was authored or queued for them; nothing was deleted.")
        refused = {**refused, **dom_refused}

        if not selected:
            # Nothing this lane may write. Rebuild runway first: it authors
            # from the publish queue itself when a domain is short, and names
            # RUNWAY_AUTHORING_FALLBACK (loud) when it cannot.
            used_ids = [r.get("pov_id") for r in ledger.load()["published"]
                        if r.get("pov_id")]
            rebuild_runway_if_short(st, cfg, per_week, used_ids, set(refused))
            if st.units:
                # The rebuild wrote publish-queue scripts: real work, an OK
                # run. Nothing above this line calls st.work().
                return
            if batch_queue.unwritten_entries():
                st.named_stop(
                    "NO_SCRIPTS",
                    "the publish queue has topics with no script, but "
                    "loop/next_topics.json selected none of them this week, so "
                    "nothing can be voiced on Tuesday",
                    detail={"unwritten": [r["slug"] for r in
                                          batch_queue.unwritten_entries()],
                            "refused": refused},
                    unblock="Re-run python loop/rank.py so the week is selected "
                            "from the publish queue, then python loop/draft.py.")
            rank.publish_queue_fully_written(st, cadence.runway(per_week),
                                             len(refused))

        # ---- 1. assemble, authoring whatever is missing --------------
        items, unauthored, authored_cost = [], [], 0.0
        for t in selected[:per_week]:
            script = ROOT / t["script"] if t.get("script") else None

            if t.get("needs_authoring") and (script is None or not script.exists()):
                pov = {"pov_id": t.get("pov_id"), "line": t.get("pov_line", "")}
                if not pov["line"]:
                    unauthored.append(t)
                    st.note(f"{t['slug']}: no POV line matched; not authored")
                    continue
                try:
                    # domain=, explicitly — without it author.draft() falls
                    # back to its own DEFAULT_DOMAIN (deep sea) regardless of
                    # what t actually is, which is why the 2026-09-21
                    # method-evidence/space drafts carry
                    # "**Domain:** deep-sea-ocean-science" and were
                    # mislabelled on top of being unqueueable. By this point
                    # allocation_gate() above has already refused anything
                    # outside domains.allocation, so this is always a live
                    # allocated domain.
                    res = author.draft(t["question"], t["slug"], pov,
                                       domain=domains.row_domain(t))
                except author.AuthorStop as e:
                    # Named, expected, and never a crash. The week continues on
                    # whatever inventory covers.
                    unauthored.append({**t, "author_stop": e.code,
                                       "author_message": e.message})
                    # The unblock line carries the provider's own reason
                    # (already key-redacted). Without it the 2026-09-21 log
                    # said only "HTTP 400" and hid "No models provided".
                    st.note(f"{t['slug']}: NAMED STOP [{e.code}] {e.message}"
                            f" — {e.unblock}")
                    continue
                authored_cost += res.get("cost_usd") or 0.0
                script = ROOT / res["path"]
                t["script"] = res["path"]
                t["generated"] = True
                t["author_cost_usd"] = res.get("cost_usd")
                t["author_model"] = res["model"]
                st.work(f"authored {t['slug']} via {res['model']} "
                        f"${res.get('cost_usd')} ({res['words']} words, "
                        f"attempt {res['attempt']})")

            if not script or not script.exists():
                unauthored.append(t)
                continue

            items.append({
                "slug": t["slug"],
                "question": t["question"],
                "script": t["script"],
                "generated": bool(t.get("generated")),
                "author_cost_usd": t.get("author_cost_usd"),
                "author_model": t.get("author_model"),
                "pov_id": t.get("pov_id"),
                "pov_line": t.get("pov_line"),
                "pov_tier": t.get("pov_tier"),
                "pov_matched_by": t.get("pov_matched_by"),
                "work_copy": f"loop/work/{t['slug']}.md",
                "audio_dir": f"audio/{t['slug']}",
                "plan": f"loop/plans/{t['slug']}.json",
                "render": f"renders/{t['slug']}.mp4",
                "source": t.get("source", "authored-inventory"),
                "status": "queued",
            })
            st.work(f"assembled {t['slug']}")

        for t in unauthored:
            p = brief_for(t, week)
            st.work(f"wrote research brief {p.relative_to(ROOT)}")

        if not items:
            st.named_stop(
                "NO_SCRIPTS",
                "zero scripts are available for this week - nothing can be "
                "voiced on Tuesday",
                detail={"unauthored": [t.get("question") for t in unauthored],
                        "author_stops": [t.get("author_stop")
                                         for t in unauthored
                                         if t.get("author_stop")]},
                unblock="Check loop/state/spend.json and the author stop codes. "
                        "The cadence ceiling is never raised to compensate.")

        if len(items) > per_week:
            st.named_stop("CADENCE_CEILING",
                          f"{len(items)} items exceeds the deliberate ceiling "
                          f"of {per_week}")

        # ---- 2. validate -------------------------------------------------
        st.note(f"cadence: {cadence_why}")
        passed, report = validate.run_all(items)

        # The evidence gate for 3/week. Recorded ONLY when a generated script
        # has cleared every hard validator - a validated artifact, never the
        # mere existence of a working API key. This is what makes the
        # escalation safe to automate: the flip reads a fact written by a
        # passing validator run, and the taxonomy ceiling still caps it.
        if passed:
            for it in items:
                if it.get("generated"):
                    promote_to_scripts(st, it)
                    ev = cadence.record_authoring_evidence(
                        it["slug"], it["script"], report)
                    st.work(f"authoring evidence recorded for {it['slug']} - "
                            f"{len(ev['scripts'])} validated generated "
                            f"script(s); cadence may now escalate to "
                            f"{cfg['cadence']['escalation']['to']}/week")
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
                "required": False,
                "mode": "notified, not asked",
                "page": "docs/approve/index.html",
                "state": "auto-approved",
                "override_until": "Tuesday 02:00, when the Mac starts rendering",
            },
            "cadence": {"videos_per_week": per_week, "why": cadence_why},
            "runway": cadence.runway(per_week),
            "authoring": {
                "generated_this_week": sum(1 for i in items if i["generated"]),
                "cost_usd": round(authored_cost, 6),
                "model": author.DEFAULT_MODEL,
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
            # The FALLBACK, not the normal path: generation failed or its
            # output failed validation for these rows.
            st.named_stop(
                "AUTHOR_REQUIRED",
                f"{len(unauthored)} slot(s) could not be authored automatically; "
                f"briefs were written to loop/briefs/. The week still ships "
                f"{len(items)} video(s).",
                detail={"briefs": [t.get("question") for t in unauthored],
                        "stops": [t.get("author_stop") for t in unauthored
                                  if t.get("author_stop")]},
                unblock="Check the stop codes above. If OPENROUTER_KEY_MISSING, "
                        "put the key in .secrets/openrouter_key.txt. If "
                        "DRAFT_FAILED_VALIDATION, the brief in loop/briefs/ is "
                        "ready for a human.")

        # ---- 4. rebuild runway, if it is short --------------------------
        # Only reached once the week's own selection has fully shipped above
        # (either return already happened via NamedStop, or every slot in
        # `items` is queued). Purely additive from here.
        skip_slugs = {i["slug"] for i in items} | {t.get("slug") for t in unauthored}
        used_ids = [r.get("pov_id") for r in ledger.load()["published"]
                   if r.get("pov_id")]
        rebuild_runway_if_short(st, cfg, per_week, used_ids, skip_slugs)


if __name__ == "__main__":
    main()
