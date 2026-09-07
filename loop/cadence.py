"""Cadence, publish order, and the runway guard. One place, no hardcoded numbers.

Three owner decisions live here as code reading `loop/config.json`:

**Cadence starts at 2/week and raises itself in two evidence-gated steps.** The
first is to 3, on exactly one condition: the OpenRouter authoring lane has
produced at least one script that passed full validation. Not "the lane runs" -
a validated artifact. The second is to the owner's 4/week target, and it adds a
QUEUE-DEPTH condition: the runway measured *at the raised rate* must still be
level `ok`. Both flips are automatic and evidence-gated, so nobody has to
remember to make them. The logic is safe to automate because the evidence is a
fact on disk written only by a passing validator run, never by intent, and the
ceiling from `pov/topic-taxonomy.json` still caps it.

**Why the 4/week raise is gated on runway rather than on a date.** Fourteen
episodes are uploaded, private and dated, running Sunday and Tuesday at 10:00
Central gaplessly through 2026-10-20, and they must publish exactly as
scheduled. A hand-flipped flag on 20 October is a promise someone has to keep.
What protects those rows is structural instead: `backfill.schedule_for` anchors
every new slot AFTER the last date already on the calendar, and no lane ever
rewrites a row that already has one - so a cadence change literally cannot
re-date, re-order or re-upload anything already scheduled. It can only govern
episodes that do not exist yet. `validate.v20_cadence_schedule` proves that
continuously by re-deriving the slots and refusing any drift.

Raising cadence SHORTENS runway, so `queue_supports()` asks the only question
that matters - "would the channel still have runway if it published this fast?"
- and refuses the raise otherwise, as a NAMED reason rather than a silent
publish at the old rate. That makes the scale self-arming *and* self-reversing:
it cannot fire into a thin queue, and it stands down on its own if the queue
thins again. Breaking cadence reliability costs more than the extra episodes
earn.

**Publish order comes from `research/publish_order.json`** - regenerated weekly
by the research agent's own entrypoint, and read-only here. Three ways it can be
wrong, all of which are NAMED STOPS rather than fallbacks:

* **Absent.** Publishing episode 01 first because a file was missing is exactly
  the failure this policy exists to prevent.
* **Stale.** Topics saturate and trends move; a ranking older than
  `publish_order.staleness_days` predates a full cycle. A loop publishing in a
  stale order looks perfectly healthy while doing it - the "runs but inert"
  failure class - so staleness is loud, not invisible.
* **Empty.** A scoring pass that produced no ranked candidate has done nothing,
  and Rule 0 applies to it like any other stage.

Two features of the file are respected rather than recomputed. A **pinned head**
is an owner override and is never re-sorted past; it falls away by itself once
those episodes publish. A **saturated tail** - episodes the top 20 search results
already answer completely - is pushed to the end.

**The runway guard never goes dark.** It reports remaining inventory in weeks at
the *current* cadence and warns early. It deliberately never trips the circuit
breaker - halting publishing to protect the backlog would be going dark to avoid
going dark.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger  # noqa: E402
from common import LOOP, ROOT, config, now, read_json, write_json  # noqa: E402

PUBLISH_ORDER = ROOT / "research" / "publish_order.json"
EVIDENCE = LOOP / "state" / "authoring_evidence.json"


class PublishOrderMissing(Exception):
    """research/publish_order.json is absent or unusable. Never a fallback."""


class PublishOrderStale(Exception):
    """The ranking is older than the staleness threshold. Loud, not invisible."""


PIN_KEYS = ("pinned", "pinned_head", "pin", "owner_pinned", "manual_override",
            "pinned_publish_first", "owner_override")
SATURATED_KEYS = ("saturated_publish_late_or_not_at_all", "saturated",
                  "saturated_tail", "publish_late")
# Schema v1.1.0: `queue` IS the contract and is already ordered with the owner's
# pinned head at positions 1-4. It is never re-sorted here. `killed` lists topics
# the demand/saturation gate excluded outright - the plan is explicit that a
# failing topic is KILLED, not ranked low, so a killed episode must never reach
# the queue by any route.
KILLED_KEYS = ("killed", "excluded", "rejected")


# --------------------------------------------------------------- escalation

def authoring_evidence() -> dict | None:
    """The artifact that unlocks 3/week, or None.

    Written only by `record_authoring_evidence()`, which is called only after a
    generated script has passed every hard validator. A working API key is not
    evidence; a validated script is.
    """
    # read_json treats default=None as "raise if missing", so use {} here.
    ev = read_json(EVIDENCE, default={})
    if not ev or not ev.get("scripts"):
        return None
    return ev


def record_authoring_evidence(slug: str, script: str, validators: list) -> dict:
    """Record that a GENERATED script passed full validation.

    Called from the drafting stage after `validate.run_all` returns clean. The
    caller must have confirmed the script is generated and that every hard
    validator passed - this function records, it does not judge.
    """
    ev = read_json(EVIDENCE, default={"scripts": [], "first_at": None})
    if any(s["slug"] == slug for s in ev["scripts"]):
        return ev
    ev["scripts"].append({
        "slug": slug, "script": script, "at": now(),
        "validators": [{"validator": v["validator"], "status": v["status"]}
                       for v in validators],
    })
    ev["first_at"] = ev["first_at"] or now()
    ev["unlocks"] = ("cadence escalation to "
                     f"{config()['cadence']['escalation']['to']}/week")
    write_json(EVIDENCE, ev)
    return ev


class QueueTooThin(Exception):
    """The queue cannot sustain the cadence being asked for. Named, not silent."""


def queue_supports(per_week: int) -> tuple[bool, str]:
    """Can the queue sustain `per_week`? The guard that makes scaling safe.

    THIS IS THE QUEUE-DEPTH GUARD. It refuses to raise cadence when the topic
    queue holds less runway than the cadence requires, and it says so in words a
    human reads - never by quietly publishing at the old rate, and never by
    breaking the gapless schedule already on the calendar.

    "Enough runway" is defined at the RAISED rate, not the current one, because
    that is the rate the queue would actually be spent at. The floor is
    `cadence.scale.requires_runway_weeks`, which defaults to the same
    `runway.warn_weeks` the loop already emails about: raising cadence into a
    runway that would immediately warn is how a channel goes dark.

    Hard-fails on zero items. A queue holding nothing is not "runway ok because
    the loop is empty" - it is the emptiest possible reason to refuse.
    """
    cfg = config()
    scale = cfg["cadence"].get("scale", {})
    need = float(scale.get("requires_runway_weeks", cfg["runway"]["warn_weeks"]))
    r = runway(per_week)
    depth = r["publishable"] + r.get("scheduled_not_yet_aired", 0)
    if depth <= 0:
        return False, (f"the publish queue holds ZERO episodes ({r['basis']}), "
                       f"so there is nothing to publish {per_week}/week from. "
                       f"A guard that examined nothing has failed, not passed.")
    if r["weeks_remaining"] <= need:
        return False, (f"{depth} episode(s) is {r['weeks_remaining']} weeks at "
                       f"{per_week}/week, at or below the {need:g}-week floor. "
                       f"Raising cadence shortens runway; raising into a runway "
                       f"that would immediately warn is how a channel goes "
                       f"dark. Publishing continues at the lower cadence - "
                       f"nothing stops, and the raise re-arms itself as soon as "
                       f"authoring refills the queue.")
    return True, (f"{depth} episode(s) is {r['weeks_remaining']} weeks at "
                  f"{per_week}/week, clear of the {need:g}-week floor "
                  f"({r['basis']})")


def effective(explain: bool = False):
    """The cadence to use this week. Never exceeds the taxonomy ceiling."""
    cfg = config()
    c = cfg["cadence"]
    base = int(c["videos_per_week"])
    ceiling = int(c.get("ceiling", 4))
    esc = c.get("escalation", {})
    scale = c.get("scale", {})
    reason = f"configured default ({base}/week)"
    n = base

    if esc.get("automatic") and authoring_evidence():
        want = int(esc.get("to", base))
        if want > n:
            n = want
            ev = authoring_evidence()
            reason = (f"escalated to {n}/week: the authoring lane has produced "
                      f"{len(ev['scripts'])} validated script(s), first at "
                      f"{ev['first_at']}")

    # ---- the owner's 4/week scale, gated on QUEUE DEPTH, not on a date ----
    # Deliberately AFTER the escalation step and deliberately not a flag: this
    # arms itself the moment the queue can carry it and stands down on its own
    # if it cannot. It never touches a slot already assigned - see the module
    # docstring and validate.v20_cadence_schedule.
    if scale.get("automatic") and authoring_evidence():
        want = int(scale.get("to", n))
        if want > n:
            ok, why = queue_supports(want)
            # 2026-09-03: with materials-and-manufacturing added, the honest
            # gate is whether BOTH domains that would carry a slot at `want`
            # can refill themselves, not just the aggregate total - see
            # domains.domains_support(). Checked second, after the cheap
            # aggregate check, and its message is APPENDED rather than
            # replacing the aggregate one so a human sees which check failed.
            if ok:
                import domains as D                          # noqa: PLC0415
                need = float(scale.get("requires_runway_weeks",
                                       cfg["runway"]["warn_weeks"]))
                dok, dwhy = D.domains_support(cfg, want, need)
                if not dok:
                    ok, why = False, f"{why}; {dwhy}"
            if ok:
                reason = f"scaled to {want}/week (owner decision): {why}"
                n = want
            else:
                reason += (f"; NOT scaled to {want}/week - {why}")

    if n > ceiling:
        reason += f" (capped at the ceiling of {ceiling})"
        n = ceiling
    return (n, reason) if explain else n


def shorts_effective(explain: bool = False):
    """Shorts per week. Configuration, NOT derived from the episode cadence.

    Shorts are a different lane with a different job. They do not count toward
    the 4,000 watch hours - long-form does - so they buy nothing on the half of
    the Partner Programme threshold that hours measure. What they buy is
    SUBSCRIBERS, which research put at roughly 12x more binding than hours on
    this channel, and they cost nothing to make because the inventory is already
    cut. That is why this number moves independently and moves further.

    It is deliberately NOT gated on the cut-Short inventory. That inventory is
    on the Mac's disk and in R2, and the cloud lane that assigns slots cannot
    always see it - a cadence that silently depends on which machine ran is
    worse than a loud stop. Exhaustion is a NAMED STOP in `shorts_lane.run()`
    instead, and `shorts_runway_weeks()` reports the number long before then.
    """
    c = config()["cadence"]
    floor = int(c.get("shorts_floor", 4))
    want = int(c.get("shorts_per_week", floor))
    n = max(floor, want)
    why = (f"{n} Shorts/week from loop/config.json (floor {floor}). "
           f"Own evening ladder, never the episode slot.")
    return (n, why) if explain else n


def scheduled_tail() -> list[dict]:
    """Every episode uploaded and DATED but not yet aired, oldest slot first.

    The 14 rows this returns today are the gapless Sunday/Tuesday run through
    2026-10-20. They are read-only to every lane in this repo: nothing re-dates
    a row that already carries `scheduled_publish_at`, and the slot allocator
    anchors past the last of them. This function exists so a guard can prove
    that rather than assert it.
    """
    import datetime as _dt
    out = []
    try:
        rows = ledger.load()["published"]
    except Exception:                       # noqa: BLE001 - never break a guard
        return []
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    for r in rows:
        stamp = r.get("scheduled_publish_at")
        if not stamp or r.get("privacy") == "public":
            continue
        try:
            when = _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when > now_utc:
            out.append({"slug": r["slug"], "video_id": r.get("video_id"),
                        "scheduled_publish_at": stamp, "when": when})
    return sorted(out, key=lambda r: r["when"])


# ------------------------------------------------------------ publish order

def publish_order() -> list[str]:
    """The ranked slug order. Raises PublishOrderMissing rather than guessing.

    Tolerant of the shapes the ranking agent might emit - a bare list of slugs,
    a list of objects, or an object wrapping either - because that file is
    another agent's to design. Intolerant of absence.
    """
    # EVERY domain's queue, merged. This function read research/publish_order.json
    # alone, so on 2026-09-04 it returned 16 deep-sea slugs and `publishable`
    # came out ZERO while eighteen scored, scripted and planned materials
    # episodes sat on disk - three of them already rendered. The runway warning
    # then read "0 publishable episode(s) of 22 on disk", which is a channel
    # reporting that it is out of inventory while holding eight weeks of it.
    # The merge is loop/batch_queue.py, the same one definition bin/ uses; the
    # staleness and shape checks below still run against the primary file,
    # which is the one the ranking agent regenerates weekly.
    try:
        import batch_queue                                 # noqa: PLC0415
        merged = batch_queue.queued_slugs()
    except Exception:
        merged = None

    if not PUBLISH_ORDER.exists():
        raise PublishOrderMissing(
            f"{PUBLISH_ORDER.relative_to(ROOT)} does not exist. The loop will "
            f"NOT fall back to filename order - publishing episode 01 first "
            f"because a file was missing is the exact failure this policy "
            f"exists to prevent.")
    try:
        raw = read_json(PUBLISH_ORDER)
    except Exception as e:
        raise PublishOrderMissing(
            f"{PUBLISH_ORDER.relative_to(ROOT)} is not valid JSON: {e}")

    # Staleness. Checked before shape, because a perfectly-shaped ranking from
    # six weeks ago is the more dangerous of the two failures - it looks fine.
    if isinstance(raw, dict):
        gen = raw.get("generated_at") or raw.get("generated") or raw.get("at")
        limit = float(config()["publish_order"].get("staleness_days", 10))
        if gen:
            try:
                import datetime as _dt
                when = _dt.datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=_dt.timezone.utc)
                age = (_dt.datetime.now(_dt.timezone.utc) - when).days
                if age > limit:
                    raise PublishOrderStale(
                        f"{PUBLISH_ORDER.relative_to(ROOT)} was generated "
                        f"{age} days ago, past the {limit:.0f}-day threshold. "
                        f"Topics saturate and trends move; publishing against "
                        f"a ranking this old is publishing against last "
                        f"month's evidence.")
            except PublishOrderStale:
                raise
            except (ValueError, TypeError):
                pass  # unparseable timestamp is not itself a reason to stop

    rows = raw
    if isinstance(raw, dict):
        for key in ("order", "publish_order", "ranked", "queue", "scripts",
                    "videos", "items", "episodes"):
            if isinstance(raw.get(key), list):
                rows = raw[key]
                break
        else:
            raise PublishOrderMissing(
                f"{PUBLISH_ORDER.relative_to(ROOT)} is a JSON object with no "
                f"recognisable list of scripts (looked for: order, "
                f"publish_order, ranked, queue, scripts, videos, items)")
    if not isinstance(rows, list) or not rows:
        raise PublishOrderMissing(
            f"{PUBLISH_ORDER.relative_to(ROOT)} contains no ranked entries")

    slugs = []
    for row in rows:
        if isinstance(row, str):
            slugs.append(row.removesuffix(".md"))
            continue
        if isinstance(row, dict):
            for key in ("slug", "script", "name", "file", "id", "video"):
                v = row.get(key)
                if isinstance(v, str) and v:
                    slugs.append(Path(v).name.removesuffix(".md"))
                    break
            else:
                continue
    if not slugs:
        raise PublishOrderMissing(
            f"{PUBLISH_ORDER.relative_to(ROOT)} has entries but none carry a "
            f"slug (looked for: slug, script, name, file, id, video)")
    slugs = list(dict.fromkeys(slugs))  # preserve rank, drop duplicates

    if not isinstance(raw, dict):
        return _with_other_domains(slugs, merged)

    # ---- honour the pinned head. An owner override is never re-sorted. ----
    pinned = []
    if config()["publish_order"].get("honour_pin", True):
        for key in PIN_KEYS:
            v = raw.get(key)
            if isinstance(v, list) and v:
                pinned = [_slug_of(x) for x in v]
                pinned = [p for p in pinned if p]
                break

    # ---- push the saturated tail to the end ----
    saturated = []
    for key in SATURATED_KEYS:
        v = raw.get(key)
        if isinstance(v, list) and v:
            saturated = [_slug_of(x) for x in v]
            saturated = [p for p in saturated if p]
            break

    head = [p for p in pinned if p in slugs]
    tail = [s for s in saturated if s in slugs and s not in head]
    middle = [s for s in slugs if s not in head and s not in tail]
    return _with_other_domains(head + middle + tail, merged)


def _with_other_domains(ranked: list[str], merged: list[str] | None) -> list[str]:
    """Append every OTHER domain's gated queue after the primary ranking.

    Appended, not interleaved, and deliberately: the two files' scores are not
    comparable. `research/publish_order.py`'s gate thresholds were set by the
    20-episode deep-sea distribution and materials imports them unchanged, so a
    materials combined_score and a deep-sea combined_score are on the same
    SCALE but were not ranked against each other, and pretending otherwise
    would silently re-order a deep-sea queue the owner has been publishing
    from. Appending keeps every existing rank exactly where it was and puts a
    second domain's topics next in line - which, with deep sea's queue fully
    published or scheduled, is the whole difference between eighteen episodes
    being publishable and being invisible.

    The pinned head and the saturated tail still come from the primary file
    only; another domain has no pin, and its own gate already dropped its
    saturated topics before they reached its queue.
    """
    if not merged:
        return ranked
    seen = set(ranked)
    return ranked + [s for s in merged if s not in seen]


def _slug_of(entry) -> str | None:
    if isinstance(entry, str):
        return Path(entry).name.removesuffix(".md")
    if isinstance(entry, dict):
        for key in ("slug", "script", "name", "file", "id", "video"):
            v = entry.get(key)
            if isinstance(v, str) and v:
                return Path(v).name.removesuffix(".md")
    return None


def order_meta_raw() -> dict:
    """What the ranking file says about itself. Read-only, never written."""
    raw = read_json(PUBLISH_ORDER, default={})
    if not isinstance(raw, dict):
        return {}
    pinned, saturated = [], []
    for key in PIN_KEYS:
        if isinstance(raw.get(key), list) and raw[key]:
            pinned = [_slug_of(x) for x in raw[key]]
            break
    for key in SATURATED_KEYS:
        if isinstance(raw.get(key), list) and raw[key]:
            saturated = [_slug_of(x) for x in raw[key]]
            break
    return {"generated_at": raw.get("generated_at"),
            "generator": raw.get("generator"),
            "status": raw.get("_status"),
            "episodes_ranked": raw.get("episodes_ranked"),
            "pinned_head": [p for p in pinned if p],
            "saturated_tail": [s for s in saturated if s]}


def killed_slugs() -> set[str]:
    """Topics the demand/saturation gate excluded. Never publishable."""
    raw = read_json(PUBLISH_ORDER, default={})
    if not isinstance(raw, dict):
        return set()
    for key in KILLED_KEYS:
        v = raw.get(key)
        if isinstance(v, list):
            return {s for s in (_slug_of(x) for x in v) if s}
    return set()


def ordered_inventory() -> tuple[list[dict], dict]:
    """Unpublished scripts, in publish-queue order. Raises if the file is absent.

    Only what the ranking actually queued is publishable. An episode the gate
    KILLED is excluded outright, not appended at the end - "failing either axis
    kills the topic; it is not ranked low" is the plan's wording, and appending
    it after the ranked entries would publish it eventually anyway.

    An unpublished script that is neither queued nor killed is reported as
    `unranked` and is NOT queued either: the loop does not promote a script the
    scorer has not seen.
    """
    inv = {s["slug"]: s for s in ledger.inventory()}
    order = publish_order()
    killed = killed_slugs()
    front = config()["publish_order"]["front_load"]

    # THE QUEUE IS AUTHORITATIVE. Three of the four owner-pinned episodes also
    # appear in `killed` and carry gate_overridden=true - the file is saying
    # "the gate would have killed this, publish it anyway because the owner
    # pinned it". Filtering the queue against `killed` destroys the pinned head,
    # which is the one thing that must never be re-sorted or dropped.
    ranked, seen = [], set()
    for rank, slug in enumerate(order, 1):
        if slug in inv:
            ranked.append({**inv[slug], "publish_rank": rank,
                           "front_loaded": rank <= front,
                           "gate_overridden": slug in killed})
            seen.add(slug)

    # `killed` only governs PROMOTION: an episode the gate excluded never enters
    # the queue by the back door. It never removes anything already queued.
    unranked = sorted(s for s in inv if s not in seen and s not in killed)
    meta = {"ranked": len(ranked),
            "unranked": len(unranked),
            "unranked_slugs": unranked,
            "killed_not_queued": sorted(s for s in inv
                                        if s in killed and s not in seen),
            "queued_despite_kill": sorted(s for s in seen if s in killed),
            "order_entries": len(order),
            "source": str(PUBLISH_ORDER.relative_to(ROOT)),
            **order_meta_raw()}
    return ranked, meta


# ------------------------------------------------------------ runway guard

def runway(per_week: int | None = None) -> dict:
    """Weeks of PUBLISHABLE queue remaining at the current cadence.

    Counted from the queue, not from the raw script count. The gate kills a
    large share of the inventory, so "scripts on disk" overstates the runway -
    which is the more dangerous direction to be wrong in.
    """
    cfg = config()
    n = per_week or effective()
    inv = ledger.inventory()
    try:
        queued, _ = ordered_inventory()
        publishable = len(queued)
        basis = "publish queue"
    except (PublishOrderMissing, PublishOrderStale):
        publishable = len(inv)
        basis = "unpublished scripts (no usable ranking)"
    # A video that is uploaded and DATED is still runway - it has not aired yet.
    # Counting it as consumed the moment it is uploaded made this read 2.5 weeks
    # on 2026-09-01 while eleven episodes sat scheduled through mid-October, and
    # it would have read 0.0 once the backfill finished, with eight weeks of
    # video queued and airing. An alarm that is wrong in the alarming direction
    # is one people learn to ignore, which is worse than no alarm.
    #
    # ONE COUNTER, SHARED WITH THE PER-DOMAIN FIGURE BELOW. This loop used to
    # live here and a second, subtly different one lived in
    # domains.domain_runway() - which counted only the un-uploaded queue and so
    # reported deep sea at 0.0 weeks/critical while 14 of its episodes were
    # uploaded and dated across the next 7 weeks. That false critical is what
    # RUNWAY_CRITICAL fired on every Sunday (run 34026361219).
    #
    # Merging them also fixed a second, quieter error in THIS copy: it had no
    # `retired_at` check, so 02-how-deep-sea-creatures-survive-pressure - a
    # duplicate upload retired on 2026-09-05 with its publishAt cancelled on
    # the live API - was still counted as a week of inventory. That is an alarm
    # wrong in the REASSURING direction, which is the worse half.
    ahead_by_domain = {}
    try:
        import domains as _D                                # noqa: PLC0415
        ahead_by_domain = _D.scheduled_ahead_by_domain()
    except Exception:                       # noqa: BLE001 - never break the guard
        ahead_by_domain = {}
    scheduled_ahead = sum(ahead_by_domain.values())

    weeks = round((publishable + scheduled_ahead) / n, 1) if n else 0.0
    warn = float(cfg["runway"]["warn_weeks"])
    crit = float(cfg["runway"]["critical_weeks"])
    level = "ok"
    if weeks <= crit:
        level = "critical"
    elif weeks <= warn:
        level = "warn"

    # 2026-09-03: a single global number cannot say WHICH domain is short.
    # Deep sea and materials are projected to exhaust within a week of each
    # other; the aggregate figure above would still read "ok" right up until
    # both hit zero in the same week, having never named either one.
    by_domain, worst_domain_level = {}, "ok"
    try:
        import domains as D                                   # noqa: PLC0415
        by_domain = D.domain_runway(cfg, n)
        order = {"ok": 0, "warn": 1, "critical": 2, "not_active": -1}
        worst_domain_level = max(
            (v["level"] for v in by_domain.values()), key=lambda l: order[l],
            default="ok")
        if worst_domain_level == "not_active":
            worst_domain_level = "ok"
    except Exception:                       # noqa: BLE001 - never break the guard
        by_domain = {}

    # The reported level is the WORSE of the aggregate and any single active
    # domain's level - an aggregate that reads "ok" while one domain is
    # already critical is exactly the number this per-domain check exists to
    # stop hiding behind.
    order = {"ok": 0, "warn": 1, "critical": 2}
    if order.get(worst_domain_level, 0) > order.get(level, 0):
        level = worst_domain_level
    short_domains = [n_ for n_, v in by_domain.items()
                     if v["level"] in ("warn", "critical")]

    domain_clause = (
        f" By domain: {'; '.join(v['message'] for k, v in by_domain.items() if v['level'] != 'not_active')}."
        if by_domain else "")

    return {
        "unpublished_scripts": len(inv),
        "publishable": publishable,
        "scheduled_not_yet_aired": scheduled_ahead,
        "basis": basis,
        "videos_per_week": n,
        "weeks_remaining": weeks,
        "warn_below_weeks": warn,
        "critical_below_weeks": crit,
        "level": level,
        "by_domain": by_domain,
        "short_domains": short_domains,
        "never_go_dark": True,
        "message": {
            "ok": (f"{weeks} weeks of queue at {n}/week "
                   f"({publishable} publishable of {len(inv)} on disk)."
                   f"{domain_clause}"),
            "warn": (f"RUNWAY WARNING: only {weeks} weeks of queue left at "
                     f"{n}/week - {publishable} publishable episode(s) of "
                     f"{len(inv)} on disk. Act now, not later: the authoring "
                     f"lane needs lead time and its human fallback needs "
                     f"more.{domain_clause}"),
            "critical": (f"RUNWAY CRITICAL: {weeks} weeks left at {n}/week - "
                         f"{publishable} publishable episode(s). The channel "
                         f"goes dark within the month unless topics are "
                         f"added.{domain_clause}"),
        }[level],
    }


if __name__ == "__main__":
    n, why = effective(explain=True)
    print(f"cadence : {n}/week - {why}")
    ev = authoring_evidence()
    print(f"evidence: {len(ev['scripts']) if ev else 0} validated generated "
          f"script(s)")
    r = runway(n)
    print(f"runway  : {r['level'].upper()} - {r['message']}")
    try:
        rows, meta = ordered_inventory()
        print(f"order   : {meta}")
        for s in rows[:6]:
            print(f"   {str(s['publish_rank'] or '-'):>3}. {s['slug']}"
                  + ("   [front-loaded]" if s["front_loaded"] else ""))
    except PublishOrderMissing as e:
        print(f"order   : NAMED STOP - {e}")
