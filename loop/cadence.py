"""Cadence, publish order, and the runway guard. One place, no hardcoded numbers.

Three owner decisions live here as code reading `loop/config.json`:

**Cadence is 2/week**, escalating to 3 on exactly one condition: the OpenRouter
authoring lane has produced at least one script that passed full validation. Not
"the lane runs" - a validated artifact. The flip is automatic and evidence-gated,
so nobody has to remember to make it. The logic is safe to automate because the
evidence is a fact on disk written only by a passing validator run, never by
intent, and the ceiling from `pov/topic-taxonomy.json` still caps it.

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


def effective(explain: bool = False):
    """The cadence to use this week. Never exceeds the taxonomy ceiling."""
    cfg = config()
    c = cfg["cadence"]
    base = int(c["videos_per_week"])
    ceiling = int(c.get("ceiling", 4))
    esc = c.get("escalation", {})
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

    if n > ceiling:
        reason += f" (capped at the ceiling of {ceiling})"
        n = ceiling
    return (n, reason) if explain else n


# ------------------------------------------------------------ publish order

def publish_order() -> list[str]:
    """The ranked slug order. Raises PublishOrderMissing rather than guessing.

    Tolerant of the shapes the ranking agent might emit - a bare list of slugs,
    a list of objects, or an object wrapping either - because that file is
    another agent's to design. Intolerant of absence.
    """
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
        return slugs

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
    return head + middle + tail


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
    weeks = round(publishable / n, 1) if n else 0.0
    warn = float(cfg["runway"]["warn_weeks"])
    crit = float(cfg["runway"]["critical_weeks"])
    level = "ok"
    if weeks <= crit:
        level = "critical"
    elif weeks <= warn:
        level = "warn"
    return {
        "unpublished_scripts": len(inv),
        "publishable": publishable,
        "basis": basis,
        "videos_per_week": n,
        "weeks_remaining": weeks,
        "warn_below_weeks": warn,
        "critical_below_weeks": crit,
        "level": level,
        "never_go_dark": True,
        "message": {
            "ok": (f"{weeks} weeks of queue at {n}/week "
                   f"({publishable} publishable of {len(inv)} on disk)."),
            "warn": (f"RUNWAY WARNING: only {weeks} weeks of queue left at "
                     f"{n}/week - {publishable} publishable episode(s) of "
                     f"{len(inv)} on disk. Act now, not later: the authoring "
                     f"lane needs lead time and its human fallback needs more."),
            "critical": (f"RUNWAY CRITICAL: {weeks} weeks left at {n}/week - "
                         f"{publishable} publishable episode(s). The channel "
                         f"goes dark within the month unless topics are added."),
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
