"""Weekly - run the demand/competition pass so the queue is never stale.

The owner should never have to ask for this analysis. It runs on the schedule,
ahead of the publish decision, so the queue is always ranked on current data.

**The research agent owns the entrypoint and the file contract; this stage owns
only the schedule.** It invokes the command, then reads the result read-only.
It never writes `research/publish_order.json`.

The failure this guards against is specific: if scoring silently stops running,
the loop keeps publishing in a stale order and looks perfectly healthy while
doing it. That is the "runs but inert" class, so:

* a pass that produces **no scored candidates is a hard failure**, not a pass
* a **stale ranking is loud** - `loop/cadence.py` raises rather than shrugging
* a **quota stop is a legitimate outcome**, surfaced and named, not a failure.
  `search.list` costs 100 units against 10,000/day, so a scoring pass can
  legitimately run out. The previous ranking is left in place when it does -
  yesterday's evidence beats no evidence, right up until it is stale.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))

import cadence  # noqa: E402
from common import ROOT, Stage, config, now, read_json, week_id  # noqa: E402

# THE INTERPRETER IS RESOLVED, NOT ASSUMED. This was hardcoded to
# .venv/bin/python, which exists on the Mac and nowhere else, so
# `loop · Sat 06:00 · score` died every Saturday on the Ubuntu runner with
# FileNotFoundError: .venv/bin/python - a scheduled lane failing not because
# the ranking was wrong but because it was told to run a binary that is not
# there. loop/tests/run_all.py already had this pattern; score.py did not. The
# venv still wins where it exists, because on the Mac it carries numpy and
# Pillow the system python may not.
PY = (str(ROOT / ".venv" / "bin" / "python")
      if (ROOT / ".venv" / "bin" / "python").exists()
      else sys.executable)
TIMEOUT_S = 1800          # the mining pass sleeps between autocomplete calls

QUOTA_MARKERS = re.compile(
    r"quota|quotaExceeded|rateLimitExceeded|dailyLimitExceeded|"
    r"HTTP 403.*quota|exceeded your.*quota", re.I)

# CHECKED BEFORE QUOTA_MARKERS, ALWAYS. research/competition.py's key-absent
# stop explains that the free tier is "10,000 quota units/day", so the word
# "quota" is IN the text of a stop that has nothing to do with quota. On
# 2026-09-12 (run 34687628665 and the 16:27 dispatch after it) that text
# matched QUOTA_MARKERS and a missing YOUTUBE_API_KEY was recorded as
# NEW_DOMAIN_QUOTA - "the next Saturday run retries" - a self-resolving label
# on a state that time cannot resolve. Only she can mint the key.
KEY_ABSENT_MARKERS = re.compile(r"YOUTUBE_API_KEY_ABSENT|no youtube data api key",
                                re.I)

# CHECKED BEFORE EITHER MARKER ABOVE, ALWAYS. Confirmed 2026-09-25: a real
# KeyError in research/publish_order_domain.py crashed on the first
# candidate for BOTH allocated domains, every run, and was classified
# NEW_DOMAIN_QUOTA anyway — something earlier in the same captured stdout
# (research/competition.py's own routine "10,000 quota units/day" progress
# text, not an actual quota problem) matched QUOTA_MARKERS before the
# traceback was ever read. Neither KEY_ABSENT_MARKERS's stop nor
# QUOTA_MARKERS's stop is ever accompanied by a raw Python traceback — both
# are this codebase's own deliberate, well-formed NAMED STOP text — so an
# unhandled exception is checked first and unconditionally: it is the one
# signal here that cannot be a coincidental keyword match.
TRACEBACK_MARKER = re.compile(r"^Traceback \(most recent call last\):", re.M)


def entrypoint() -> Path:
    """The command to run. The file names its own generator; config overrides."""
    cfg = config()["publish_order"]
    raw = read_json(cadence.PUBLISH_ORDER, default={})
    named = raw.get("generator") if isinstance(raw, dict) else None
    for cand in (cfg.get("entrypoint"), named, "research/publish_order.py"):
        if not cand:
            continue
        p = ROOT / str(cand).split()[0]
        if p.exists():
            return p
    return ROOT / str(cfg.get("entrypoint", "research/publish_order.py"))


def missing_queues() -> dict:
    """Allocated domains with no scored publish-order file of their own.

    Keyed by domain, valued by the file the gate would write. Derived from the
    allocation and the files on disk - NOT from a list of domains that need
    scoring, which is the second list this repo keeps discovering it kept.
    """
    import domains as dom                                   # noqa: PLC0415
    import publish_order_domain as pod                      # noqa: PLC0415

    import batch_queue                                      # noqa: PLC0415

    # THIN, NOT ONLY EMPTY (2026-09-25). A queue whose unwritten rows are all
    # repeats of aired episodes has depth on paper and nothing to write, and
    # waiting for depth 0 meant refilling only after the Monday lane had
    # already run dry. A domain is refilled once its unwritten, non-duplicate,
    # non-held topics fall under batch_queue.MIN_UNWRITTEN_TOPICS.
    unwritten = batch_queue.unwritten_by_domain()
    out = {}
    for name in dom.allocation(config()):
        if unwritten.get(name, 0) >= batch_queue.MIN_UNWRITTEN_TOPICS:
            continue
        out[name] = Path(pod.out_path(name))
    return out


# ----------------------------------------------------------------- holds
#
# A HOLD IS DECIDED HERE, NOT BY THE OWNER. loop/promotion_holds.json was
# written on 2026-09-23 as "scripts outside the queue, waiting for her
# promotion decision", and two days later she asked the only question that
# matters about it: why can't these be left somewhere for an automated
# process to pick up and decide on? They can. The loop already owns the one
# decision procedure every queued topic passed - demand ÷ competition through
# research/publish_order.py's gate - and this stage already runs it every
# Saturday. So each held script's own question goes through that same gate
# (research/publish_order_domain.py --query, one measurement, imported
# unchanged) and the answer is acted on:
#
#   passed, or its slug is already a queued row  -> PROMOTED: the script goes
#       to scripts/<slug>.md (the only path the Mac narrates from), a gated
#       row is appended to its domain's publish order, its POV line is
#       recorded, the hold row is removed.
#   killed                                       -> DECLINED: the script moves
#       to loop/drafts/declined/ (never deleted), the hold row is removed.
#   the gate could not run (no key, quota)       -> DEFERRED: the row stays,
#       its gate_deferred count rises; HOLD_GATE_DEFERRALS of them is the
#       HOLD_GATE_FAILED stop, because a hold older than a month of Saturdays
#       is not "waiting", it is stuck.
#
# Every outcome is a dated entry in docs/DECISION-LOG.md, so the decision the
# machine made is as legible as one she would have made.
HOLDS_PATH = ROOT / "loop" / "promotion_holds.json"
DRAFTS_DIR = ROOT / "loop" / "drafts"      # where a held script must live
SCRIPTS_DIR = ROOT / "scripts"
DECLINED_DIR = ROOT / "loop" / "drafts" / "declined"
RESEARCH_DIR = ROOT / "research"
DECISION_LOG = ROOT / "docs" / "DECISION-LOG.md"
HOLD_GATE_DEFERRALS = 4
HOLD_GATE_VERDICT = re.compile(r"^HOLD_GATE_VERDICT (\{.*\})\s*$", re.M)
TITLE_LINE = re.compile(r"^#\s+(.+?)\s*$", re.M)
POV_LINE = re.compile(r"^### Producer POV\s*\n+\s*\[HUMAN\]\s*(.+?)\s*$", re.M)


def read_holds() -> dict:
    doc = read_json(HOLDS_PATH, default={"holds": []})
    for h in doc.get("holds") or []:
        if not h.get("slug") or not h.get("script"):
            raise ValueError(f"{HOLDS_PATH.name}: a hold row must name its "
                             f"slug and script: {h!r}")
    return doc


def write_holds(doc: dict) -> None:
    with open(HOLDS_PATH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def queue_path(domain: str) -> Path:
    """The domain's publish order - research/publish_order_domain.py
    out_path(), spelled here as a path under RESEARCH_DIR so
    loop/tools/write_set.py can read the write target off this module."""
    import publish_order_domain as pod                      # noqa: PLC0415
    return RESEARCH_DIR / f"publish_order_{pod.slug_of_domain(domain)}.json"


def question_of(script_text: str) -> str:
    """The gate's input is the question the script answers: its H1, lowered,
    without the trailing question mark - the same shape research/mine.py
    records autocomplete queries in."""
    m = TITLE_LINE.search(script_text)
    if not m:
        raise ValueError("held script has no '# ' title line")
    return re.sub(r"\s+", " ", m.group(1).rstrip("?.!")).strip().lower()


def gate_query(domain: str, query: str) -> tuple[str, dict]:
    """One question through the one gate. Returns (outcome, payload) where
    outcome is passed | kill | key_absent | quota | traceback | unscored, and
    payload is the scored row for the first two, the output tail otherwise.
    The classification order is score_new_domains()'s, for the same reasons
    it documents: a traceback is checked first because it is the one signal
    that cannot be a keyword coincidence; the key-absent stop's own text says
    'quota', so it is checked before QUOTA_MARKERS."""
    # str(...), not bare names: neither argument is a path, and
    # loop/tools/write_set.py (which follows this entrypoint to find what it
    # writes) reads a bare name or f-string in argv as a possible path and a
    # str() call as not one - the same reason score_new_domains() and
    # research/publish_order_domain.py pass str(budget).
    g = subprocess.run(
        [PY, str(ROOT / "research" / "publish_order_domain.py"),
         "--domain", str(domain), "--query", str(query)],
        cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S)
    gout = (g.stdout or "") + (g.stderr or "")
    tail = {"tail": gout.strip().splitlines()[-6:], "exit": g.returncode}
    if TRACEBACK_MARKER.search(gout):
        return "traceback", tail
    m = HOLD_GATE_VERDICT.search(g.stdout or "")
    if g.returncode == 0 and m:
        rows = json.loads(m.group(1)).get("rows") or []
        if not rows:
            return "unscored", tail
        row = rows[0]
        return ("kill" if row["gate"]["verdict"] == "kill" else "passed", row)
    if KEY_ABSENT_MARKERS.search(gout):
        return "key_absent", tail
    if QUOTA_MARKERS.search(gout):
        return "quota", tail
    return "unscored", tail


def _record_pov(st: Stage, slug: str, script_text: str) -> None:
    """Write down which bank line the promoted script's [HUMAN] beat is.
    Bookkeeping, not consent (loop/pov_match.py record_assignment): the line
    was already chosen from her bank when the script was authored."""
    import pov_match                                        # noqa: PLC0415
    m = POV_LINE.search(script_text)
    if not m:
        st.note(f"{slug}: no '### Producer POV' [HUMAN] line found; V32 "
                f"will ask which bank line it traces to")
        return
    line = m.group(1).strip()
    hit = next((b for b in pov_match.bank()
                if b.get("line", "").strip() == line), None)
    if hit is None:
        st.note(f"{slug}: its POV line is not verbatim in pov/pov-bank.json; "
                f"nothing recorded, V32 will ask")
        return
    if pov_match.record_assignment(
            slug, {"pov_id": hit["id"], "line": line,
                   "tier": hit.get("tier", "transferable")},
            source="promoted by the Saturday gate"):
        st.work(f"recorded {slug} -> {hit['id']} in pov/pov-assignments.json")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:              # a test's scratch outside the repo
        return str(p)


def _append_queue_row(domain: str, row: dict) -> Path:
    path = queue_path(domain)
    doc = read_json(path, default=None)
    if not isinstance(doc, dict) or not isinstance(doc.get("queue"), list):
        raise ValueError(f"{path} is not a publish order this hold can join "
                         f"(no 'queue' list); the domain has no scored queue "
                         f"yet")
    doc["queue"].append(row)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def _log_decisions(entries: list[str]) -> None:
    stamp = now()[:10]
    block = [f"\n## {stamp} — the Saturday gate decided "
             f"{len(entries)} held script(s)\n",
             "**What happened.** `loop/score.py dispose_promotion_holds()` put "
             "each script held in `loop/promotion_holds.json` through the same "
             "demand ÷ competition gate every queued topic passed "
             "(`research/publish_order_domain.py --query`). Owner instruction "
             "2026-09-25: a hold is decided by the loop, never parked for her.\n"]
    block += [f"- {e}" for e in entries]
    block.append(f"\n**Verified.** Stop record and gate output in this run's "
                 f"job log; week {week_id()}.\n")
    with open(DECISION_LOG, "a", encoding="utf-8") as fh:
        fh.write("\n".join(block))


def dispose_promotion_holds(st: Stage) -> None:
    """Decide every hold. See the block comment above HOLDS_PATH."""
    import batch_queue                                      # noqa: PLC0415
    import domains as dom                                   # noqa: PLC0415

    doc = read_holds()
    holds = list(doc.get("holds") or [])
    if not holds:
        st.note("no scripts held in loop/promotion_holds.json")
        return

    allocated = set(dom.allocation(config()))
    queued = {r["slug"]: r for r in batch_queue.queued_entries()}
    keep, decided, defects = [], [], []
    for h in holds:
        # A held script lives at loop/drafts/<slug>.md, by construction (the
        # Monday lane wrote it there); the row's `script` field is checked
        # against that, not trusted, so the paths this stage moves are ones
        # loop/tools/write_set.py can read off DRAFTS_DIR.
        slug = h["slug"]
        src = DRAFTS_DIR / f"{slug}.md"
        if not src.exists() or (ROOT / h["script"]).resolve() != src.resolve():
            defects.append(f"{slug}: a held script must be at "
                           f"loop/drafts/{slug}.md and the hold row must say "
                           f"so; the row names {h['script']!r} and "
                           f"{'the file exists' if src.exists() else 'nothing is there'}")
            keep.append(h)
            continue
        text = src.read_text(encoding="utf-8")
        dest = SCRIPTS_DIR / f"{slug}.md"
        domain = dom.domain_of_script(src)

        # -- the same question as an episode already made ---------------------
        # Checked FIRST, before the already-queued shortcut: the held
        # why-deep-sea-creatures script is "Why do deep sea creatures look so
        # strange?", which is episode 01, "Why deep sea creatures look so
        # weird", and its slug colliding with a queued row would otherwise
        # promote it with no question asked (2026-09-25). A repeat is
        # declined like a gate kill: moved, never deleted, logged.
        if not dest.exists():
            import topic_identity as TI                     # noqa: PLC0415
            try:
                held_q = question_of(text)
            except ValueError:
                held_q = None           # no title: the gate path reports it
            rep = (TI.first_same(TI.question_key(held_q),
                                 batch_queue.made_questions(exclude={slug}))
                   if held_q else None)
            if rep:
                DECLINED_DIR.mkdir(parents=True, exist_ok=True)
                src.replace(DECLINED_DIR / f"{slug}.md")
                st.work(f"declined held {slug}: {held_q!r} is the same "
                        f"question as {rep[0]!r}, already made ({rep[1]}); "
                        f"moved to loop/drafts/declined/")
                decided.append(f"**DECLINED** `{slug}` — {held_q!r} is the "
                               f"same question as {rep[0]!r}, already made "
                               f"({rep[1]}). Moved to "
                               f"`loop/drafts/declined/`, never deleted.")
                continue

        # -- already promoted by hand, or already a queued row that passed --
        if dest.exists() or slug in queued:
            if not dest.exists():
                dest.write_text(text, encoding="utf-8")
            how = ("already at scripts/" if slug in queued and dest.exists()
                   else "its slug is already a queued row that passed the "
                        "gate; the script now exists at scripts/")
            _record_pov(st, slug, text)
            st.work(f"promoted held {slug}: {how}")
            decided.append(f"**PROMOTED** `{slug}` — {how}"
                           + (f" (queued as {queued[slug].get('query')!r})"
                              if slug in queued else ""))
            continue

        # -- outside the plan's allocation: nothing can air it ---------------
        if domain not in allocated:
            DECLINED_DIR.mkdir(parents=True, exist_ok=True)
            src.replace(DECLINED_DIR / f"{slug}.md")
            st.work(f"declined held {slug}: its domain {domain!r} holds no "
                    f"weekly slots in the plan; moved to loop/drafts/declined/")
            decided.append(f"**DECLINED** `{slug}` — domain {domain!r} is not "
                           f"allocated any weekly slots; moved to "
                           f"`loop/drafts/declined/`")
            continue

        # -- the gate ----------------------------------------------------------
        query = question_of(text)
        outcome, payload = gate_query(domain, query)
        if outcome == "passed":
            row = dict(payload, slug=slug)
            row["promoted_from_hold"] = {"held_since": h.get("held_since"),
                                         "decided": now()}
            qp = _append_queue_row(domain, row)
            dest.write_text(text, encoding="utf-8")
            _record_pov(st, slug, text)
            st.work(f"promoted held {slug}: gate passed ({row['gate'].get('reason')}); "
                    f"row appended to {_rel(qp)}, script at scripts/{slug}.md")
            decided.append(f"**PROMOTED** `{slug}` — {row['gate'].get('reason')} "
                           f"Row appended to `{_rel(qp)}`.")
        elif outcome == "kill":
            DECLINED_DIR.mkdir(parents=True, exist_ok=True)
            src.replace(DECLINED_DIR / f"{slug}.md")
            why = payload["gate"].get("reason") or "failed the gate"
            st.work(f"declined held {slug}: {why}; moved to loop/drafts/declined/")
            decided.append(f"**DECLINED** `{slug}` — {why} Moved to "
                           f"`loop/drafts/declined/`, never deleted.")
        elif outcome == "traceback":
            defects.append(f"{slug}: the gate raised an unhandled exception "
                           f"(exit {payload['exit']}): "
                           + " | ".join(payload["tail"]))
            keep.append(h)
        else:
            n = int(h.get("gate_deferred", 0)) + 1
            h = dict(h, gate_deferred=n, gate_deferred_why=outcome)
            keep.append(h)
            st.note(f"{slug}: gate could not run ({outcome}), deferred "
                    f"{n}/{HOLD_GATE_DEFERRALS}; the hold stays")
            if n >= HOLD_GATE_DEFERRALS:
                defects.append(f"{slug}: the gate has been deferred on "
                               f"{outcome} for {n} Saturdays running; the "
                               f"hold is stuck, not waiting")

    if len(keep) != len(holds):
        doc["holds"] = keep
        write_holds(doc)
        st.work(f"loop/promotion_holds.json: {len(holds) - len(keep)} hold(s) "
                f"decided, {len(keep)} remain")
    elif any("gate_deferred" in h for h in keep):
        doc["holds"] = keep
        write_holds(doc)
    if decided:
        _log_decisions(decided)
        st.work(f"docs/DECISION-LOG.md: {len(decided)} decision(s) appended")
    if defects:
        st.named_stop(
            "HOLD_GATE_FAILED",
            f"{len(defects)} held script(s) could not be decided: "
            + "; ".join(defects),
            detail={"defects": defects, "decided": decided},
            unblock="Run research/publish_order_domain.py --domain <domain> "
                    "--query \"<the script's title>\" and read what it "
                    "prints. A traceback is a code defect; a missing key is "
                    "YOUTUBE_API_KEY; a quota stop that lasts a month means "
                    "the Saturday pass is spending the whole allowance "
                    "before the holds get their turn.")


def refresh_primary_ranking(st: Stage) -> None:
    """Run the research agent's scorer and prove the ranking is fresh.

    THIS IS THE LANE'S JOB, AND IT RUNS FIRST. From 2026-09-05 to 09-17 the
    new-domain gate below ran ahead of it and raised its named stop on a
    missing YouTube key, so this function was never reached: the primary
    ranking sat at generated_at 2026-09-05 while two Saturday runs went green
    with a stop that said "retries next week". On 09-16 15:36 UTC the file
    crossed publish_order.staleness_days and `loop · tests` went red on check
    4 of validate_plan.py (run 35230863447) - PublishOrderStale, twelve days.
    The primary scorer needs no YouTube key (it reads the competition file
    already measured for its scripts), so nothing about a keyless runner is a
    reason not to refresh it.
    """
    ep = entrypoint()
    if not ep.exists():
        st.named_stop(
            "SCORER_MISSING",
            f"the scoring entrypoint {ep.relative_to(ROOT)} does not exist",
            unblock="The research agent owns this command. Point "
                    "loop/config.json publish_order.entrypoint at it once "
                    "it lands. The loop will not invent a ranking.")

    before = read_json(cadence.PUBLISH_ORDER, default={})
    before_at = before.get("generated_at") if isinstance(before, dict) else None

    st.note(f"running {ep.relative_to(ROOT)} (owned by the research agent)")
    p = subprocess.run([PY, str(ep)], cwd=ROOT, capture_output=True,
                       text=True, timeout=TIMEOUT_S)
    out = (p.stdout or "") + (p.stderr or "")
    tail = out.strip().splitlines()[-6:]
    for line in tail:
        st.note(f"  scorer: {line[:150]}")

    # A quota stop is a legitimate outcome, not a failure. The previous
    # ranking stays; yesterday's evidence beats none, until it goes stale.
    if QUOTA_MARKERS.search(out):
        st.work("scoring pass ran and reported a quota limit")
        st.named_stop(
            "SCORER_QUOTA",
            "the scoring pass stopped on YouTube Data API quota. "
            "search.list costs 100 units against 10,000/day, so this is an "
            "expected outcome, not a defect. The previous ranking is left "
            "in place.",
            detail={"previous_generated_at": before_at,
                    "scorer_tail": tail},
            unblock="Wait for the daily quota reset; the next weekly run "
                    "picks it up. If it recurs every week, the pass is "
                    "scoring more candidates than the quota allows.")

    if p.returncode != 0:
        st.named_stop(
            "SCORER_FAILED",
            f"the scoring entrypoint exited {p.returncode}",
            detail={"tail": tail},
            unblock="This command belongs to the research agent. The loop "
                    "will not substitute its own ranking.")

    # Rule 0, and the whole point of the stage: a pass that ranked nothing
    # must not report success.
    after = read_json(cadence.PUBLISH_ORDER, default={})
    if not isinstance(after, dict) or not after:
        st.named_stop(
            "NO_RANKING_PRODUCED",
            "the scoring pass exited cleanly but wrote no usable ranking",
            unblock="Check the scorer's own output above.")

    try:
        order = cadence.publish_order()
    except cadence.PublishOrderStale as e:
        st.named_stop(
            "RANKING_STALE_AFTER_SCORING", str(e),
            detail={"generated_at": after.get("generated_at")},
            unblock="The pass ran but did not refresh the timestamp - it "
                    "may have failed silently and left the old file. This "
                    "is the 'runs but inert' case the stage exists to "
                    "catch.")
    except cadence.PublishOrderMissing as e:
        st.named_stop("NO_RANKING_PRODUCED", str(e))

    if not order:
        st.named_stop(
            "NO_SCORED_CANDIDATES",
            "the ranking contains zero scored candidates",
            unblock="A ranking with nothing in it cannot order a publish "
                    "queue. The loop refuses rather than falling back to "
                    "filename order.")

    st.work(f"scored and ranked {len(order)} candidate(s)")
    meta = cadence.order_meta_raw()
    if meta.get("generated_at") == before_at:
        st.note("WARNING: generated_at is unchanged from before the run")
    if meta.get("pinned_head"):
        st.work(f"pinned head honoured, not re-sorted: "
                f"{', '.join(meta['pinned_head'])}")
    if meta.get("saturated_tail"):
        st.work(f"saturated tail pushed last: "
                f"{', '.join(meta['saturated_tail'])}")
    st.work(f"ranking is fresh as of {meta.get('generated_at')}")


def score_new_domains(st: Stage) -> None:
    """Give every domain with an empty queue a scored one.

    A DOMAIN ARRIVES HERE WITH NO QUEUE two ways: the monthly review just
    promoted it, or an established domain's own scored queue has simply been
    fully consumed - `missing_queues()` asks `domains.queue_depth()`, which
    excludes anything already published, so a long-running domain reads
    exactly like a freshly promoted one the day its last queued topic airs.
    Nothing else in the loop will score its topics: research/publish_order.py
    gates deep sea and publish_order_materials.py gates materials from a
    hand-written candidate list. Scoring it here, on the schedule, is what
    keeps every allocated domain fed rather than only the first one whose
    queue happened to run out first.

    ─── EVERY DOMAIN GETS A TURN, EVEN WHEN ONE STOPS ─────────────────────
    `st.named_stop()` raises and `Stage.__exit__` turns that into `sys.exit`
    for the WHOLE stage — correct for a stage with one thing to do, wrong
    here, where `missing_queues()` can return more than one domain. Calling
    it per domain inside the loop meant the FIRST domain's quota stop ended
    the run before the second domain was even attempted: confirmed
    2026-09-25 — deep-sea-ocean-science and materials-and-manufacturing were
    BOTH fully exhausted (every queued topic already published), the
    Saturday run reached deep-sea, hit NEW_DOMAIN_QUOTA, and exited — so
    materials-and-manufacturing, in exactly the same state, was silently
    never even tried, every week, for as long as deep-sea's own
    quota-constrained refill took to finish. One domain's bad day is not a
    reason to skip the other's turn. So every domain in `missing_queues()`
    is attempted here regardless of an earlier one's outcome, and a stop is
    raised ONCE at the end, naming every domain that could not be scored —
    never only the first.

    Same gate, imported unchanged - a new domain's topics are not waved
    through for being new. A quota or key stop is named, not a failure,
    and leaves the domain queueless until it clears. It runs AFTER
    refresh_primary_ranking() on purpose: its stop must never cost the
    channel the ranking every publishing lane reads.
    """
    import batch_queue                                      # noqa: PLC0415
    stops: list[dict] = []
    for dom, path in missing_queues().items():
        st.note(f"{dom} holds weekly slots and has fewer than "
                f"{batch_queue.MIN_UNWRITTEN_TOPICS} unwritten, non-duplicate "
                f"topics queued; mining and running the gate for it")
        g = subprocess.run(
            [PY, str(ROOT / "research" / "publish_order_domain.py"),
             "--domain", dom], cwd=ROOT, capture_output=True, text=True,
            timeout=TIMEOUT_S)
        gout = (g.stdout or "") + (g.stderr or "")
        for line in gout.strip().splitlines()[-4:]:
            st.note(f"  {dom}: {line[:150]}")
        if g.returncode == 0 and path.exists():
            st.work(f"scored a queue for {dom} -> "
                    f"{path.relative_to(ROOT)}")
        elif "NAMED STOP DOMAIN_QUEUE_THIN" in gout:
            # The queue it could build IS written; the stop names the gap.
            if path.exists():
                st.work(f"scored a queue for {dom} -> "
                        f"{path.relative_to(ROOT)} (under the floor)")
            line = next(ln for ln in gout.splitlines()
                        if "NAMED STOP DOMAIN_QUEUE_THIN" in ln)
            stops.append({
                "domain": dom, "code": "DOMAIN_QUEUE_THIN",
                "message": line.split(":", 1)[1].strip(),
                "tail": gout.strip().splitlines()[-4:],
                "unblock": "Add seeds for this domain to "
                    "research/seeds_broad.json or its dedicated seed file "
                    "(research/publish_order_domain.py DEDICATED_SEEDS); the "
                    "next Saturday run mines them. The domain keeps "
                    "publishing whatever it already has queued."})
        elif TRACEBACK_MARKER.search(gout):
            stops.append({
                "domain": dom, "code": "NEW_DOMAIN_UNSCORED",
                "message": f"{dom} holds weekly slots and its first topic "
                    f"gate raised an unhandled exception (exit "
                    f"{g.returncode}), not a quota or key stop. This is a "
                    f"code defect, not a condition that clears on its own — "
                    f"retrying next Saturday cannot fix it.",
                "tail": gout.strip().splitlines()[-6:],
                "unblock": "Run research/publish_order_domain.py --domain "
                    f"{dom} --candidates-only and read the traceback. A "
                    "domain with no queue cannot fill the slots the "
                    "monthly review gave it."})
        elif KEY_ABSENT_MARKERS.search(gout):
            stops.append({
                "domain": dom, "code": "NEW_DOMAIN_KEY_ABSENT",
                "message": f"{dom} holds weekly slots and its first topic "
                    f"gate found no YouTube Data API key in this "
                    f"environment. Competition cannot be measured without "
                    f"one, so the domain has no queue and the drafting lane "
                    f"has nothing to draw from for it.",
                "tail": gout.strip().splitlines()[-4:],
                "unblock": "Add YOUTUBE_API_KEY as a repository secret (a "
                    "Data API v3 key on the Google Cloud project that "
                    "already holds the upload OAuth client; free tier, no "
                    "card). The next Saturday run scores the domain. No "
                    "retry without the key can clear this."})
        elif QUOTA_MARKERS.search(gout):
            stops.append({
                "domain": dom, "code": "NEW_DOMAIN_QUOTA",
                "message": f"{dom} holds weekly slots and its first topic "
                    f"gate stopped on YouTube Data API quota. It has no "
                    f"queue until this runs, and the drafting lane has "
                    f"nothing to draw from for it.",
                "tail": gout.strip().splitlines()[-4:],
                "unblock": "The next Saturday run retries. If it recurs, "
                    "the candidate set is larger than one day's quota - "
                    "lower --budget and let it fill over two weeks."})
        else:
            stops.append({
                "domain": dom, "code": "NEW_DOMAIN_UNSCORED",
                "message": f"{dom} holds weekly slots and its first topic "
                    f"gate exited {g.returncode} without writing a queue.",
                "tail": gout.strip().splitlines()[-6:],
                "unblock": "Run research/publish_order_domain.py --domain "
                    f"{dom} --candidates-only to see what it found. A "
                    "domain with no queue cannot fill the slots the "
                    "monthly review gave it."})

    if stops:
        # THE WORST CODE NAMES THE STOP, EVERY DOMAIN IS IN THE DETAIL. A
        # mix of an absent key and a quota ceiling is still ONE call to
        # named_stop() (it can raise only once) — the code picked is the one
        # that needs the more active fix (a key nobody can wait out beats a
        # quota that clears on its own), and nothing about any domain's stop
        # is dropped: the full per-domain detail rides in `detail["stops"]`.
        rank = {"NEW_DOMAIN_KEY_ABSENT": 0, "NEW_DOMAIN_UNSCORED": 1,
                "NEW_DOMAIN_QUOTA": 2, "DOMAIN_QUEUE_THIN": 3}
        worst = min(stops, key=lambda s: rank.get(s["code"], 1))
        doms = ", ".join(s["domain"] for s in stops)
        st.named_stop(
            worst["code"],
            f"{len(stops)} domain(s) could not be scored this run: {doms}. "
            f"{worst['message']}",
            detail={"stops": stops},
            unblock="; ".join(f"{s['domain']}: {s['unblock']}" for s in stops))


def main() -> None:
    week = week_id()
    with Stage("weekly-score", week,
               zero_work_hint="The scoring entrypoint produced no ranked "
                              "candidate. A scoring pass that ranks nothing "
                              "has done nothing.") as st:
        # Order is the fix. The ranking every publishing lane reads is
        # refreshed before anything that can stop this stage gets to run.
        refresh_primary_ranking(st)
        # Holds are decided against the freshly refreshed ranking and BEFORE
        # score_new_domains(), whose end-of-run stop (a domain that could not
        # be scored) would otherwise end the stage with the holds untouched.
        dispose_promotion_holds(st)
        score_new_domains(st)


if __name__ == "__main__":
    main()
