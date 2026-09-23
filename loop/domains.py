"""Domains — the dimension the loop could not previously see.

`loop/monthly.py` decided cadence, runtime and whether the format was wrong. It
had no notion of a domain at all, which was survivable while the channel
published one subject and stops being survivable the moment it publishes two:
with deep sea and materials both live, three bad months in ONE of them is a bad
NICHE, and the format breaker would have called it a bad FORMAT and shortened
every episode on the channel.

Four rules, and they exist to stop the defect this repo keeps producing — two
components each keeping their own list with nothing linking them:

1.  **`research/proposed-taxonomy.json` is the only source of domain names.**
    Nothing here, in `loop/config.json` or in a script may name a domain that is
    absent from `ranked_domains`. There is one list.
2.  **An episode carries its own domain**, as `**Domain:**` front matter in its
    script. A published video reaches its domain through the ledger's slug, so
    the join is script -> slug -> video_id and there is no second mapping to
    drift.
3.  **A domain cannot be judged below a minimum sample.** Eight published
    episodes WITH analytics. Below that the monthly review takes a named stop
    and holds the allocation exactly as it is — it does not fall back to an even
    split, which is a decision disguised as a default.
4.  **A domain retires when its scored topic queue decays**, not on an episode
    count. `research/publish_order.json` already gates topics on demand and
    saturation; when a domain's surviving queue falls below
    `domains.queue_exhausted_below`, that domain is exhausted and the next
    domain in the taxonomy's own ranking takes its slots.

Why eight, for rule 3: the monthly review may move an allocation by one slot,
and one slot out of four is a 25% swing. Eight episodes is the point at which a
single unlucky topic moves a domain's mean retention by roughly a tenth of the
spread between the current best and worst episode, so the swing is larger than
the noise it is answering. Below eight, holding is the honest answer and the
named stop says so out loud.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

TAXONOMY = ROOT / "research" / "proposed-taxonomy.json"
PUBLISH_ORDER = ROOT / "research" / "publish_order.json"
SCRIPTS = ROOT / "scripts"

# Every domain's gated queue lives in its OWN research/publish_order*.json --
# research/publish_order.json for deep sea (the original, unsuffixed file,
# kept as the stable name so nothing that already reads it breaks),
# research/publish_order_materials.json for materials-and-manufacturing, and
# so on for whatever comes after. queue_depth() below merges all of them
# rather than reading PUBLISH_ORDER alone, which is exactly the defect this
# module's docstring names: "two components each keeping their own list with
# nothing linking them." One glob, not one hardcoded filename.
PUBLISH_ORDER_GLOB = "publish_order*.json"

DOMAIN_LINE = re.compile(r"^\*\*Domain:\*\*\s*([a-z0-9-]+)\s*$", re.M)


class UnknownDomain(Exception):
    """A domain name that the scored taxonomy does not contain.

    Never downgraded to a warning. An unknown domain means someone invented a
    niche instead of reading the 20 that were measured, and every allocation
    decision made about it would be about nothing.
    """


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


# ------------------------------------------------------------- the one list

def ranked() -> list[dict]:
    """The scored domains, best first. The taxonomy's own order, not ours."""
    rows = _read(TAXONOMY).get("ranked_domains") or []
    return sorted(rows, key=lambda d: -float(
        (d.get("demand_over_competition") or {}).get("score")
        or d.get("demand_side_score") or 0))


def known() -> list[str]:
    return [d["domain"] for d in ranked()]


def require_known(name: str) -> str:
    if name not in known():
        raise UnknownDomain(
            f"{name!r} is not in research/proposed-taxonomy.json ranked_domains. "
            f"The scored taxonomy is the only place a domain name may come "
            f"from; there are {len(known())} of them.")
    return name


def score(name: str) -> dict:
    require_known(name)
    d = next(x for x in ranked() if x["domain"] == name)
    return {
        "domain": name,
        "demand_side_score": d.get("demand_side_score"),
        "demand_over_competition": (d.get("demand_over_competition") or {}).get("score"),
        "in_current_taxonomy": d.get("in_current_taxonomy"),
    }


def next_unused(active: list[str]) -> str | None:
    """The next-ranked domain that is not already running."""
    for name in known():
        if name not in active:
            return name
    return None


# --------------------------------------------------- episodes carry a domain

def domain_of_script(path: Path) -> str | None:
    m = DOMAIN_LINE.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def domain_of_slug(slug: str, default: str | None = None) -> str | None:
    p = SCRIPTS / f"{slug}.md"
    if not p.exists():
        return default
    return domain_of_script(p) or default


def by_slug() -> dict[str, str]:
    out = {}
    for p in sorted(SCRIPTS.glob("*.md")):
        d = domain_of_script(p)
        if d:
            out[p.stem] = d
    return out


def domain_of_video(video_id: str, ledger_published: list[dict],
                    default: str | None = None) -> str | None:
    """video_id -> slug -> script -> domain. One join, no second table."""
    slug = next((p["slug"] for p in ledger_published
                 if p.get("video_id") == video_id), None)
    return domain_of_slug(slug, default) if slug else default


# The one file with no `domain` field anywhere in it, by convention — see
# PUBLISH_ORDER above ("the original, unsuffixed file, kept as the stable
# name"). Every file `research/publish_order_domain.py` writes for a
# materials-style or later domain carries `domain` at the top level; this is
# the fallback for the one file that predates that convention.
UNSUFFIXED_FILE_DOMAIN = "deep-sea-ocean-science"


def row_domain(row: dict) -> str:
    """Best-effort domain for a topic/queue ROW that may have no script yet.

    Callers hand this two different shapes of dict and neither reliably
    carries a `domain` key:

      * a raw row from `loop/batch_queue.queued_entries()`, keyed
        `_domain_file` for the `research/publish_order*.json` it came from;
      * a `loop/next_topics.json` selection (`loop/rank.py`'s output), which
        renames that same thing to `queue_file`, or — for an already-authored
        "authored-inventory" pick — carries neither and only a `script` path
        to an existing file that already has its own `**Domain:**` line.

    `research/publish_order.json` itself has never carried a `domain` field,
    row or top-level, because it predates materials-and-manufacturing being a
    second domain. Order of resolution:

      1. the row's own `domain` key,
      2. the domain file's own top-level `domain` key (`_domain_file` or
         `queue_file`, whichever is present),
      3. the domain line of `script`, if that path already exists on disk,
      4. `UNSUFFIXED_FILE_DOMAIN`, for the one file/path that names none of
         the above.

    This is what `loop/draft.py` calls BEFORE a script may exist, so it
    cannot rely on `domain_of_script()` alone — the point is to know the
    domain in time to refuse authoring it.
    """
    if row.get("domain"):
        return row["domain"]
    domain_file = row.get("_domain_file") or row.get("queue_file")
    if domain_file:
        doc = _read_json_default(ROOT / "research" / domain_file)
        if doc.get("domain"):
            return doc["domain"]
    script = row.get("script")
    if script:
        p = ROOT / script
        if p.exists():
            d = domain_of_script(p)
            if d:
                return d
    return UNSUFFIXED_FILE_DOMAIN


def _read_json_default(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def allocation_gate(rows: list[dict], cfg: dict) -> tuple[list[dict], dict[str, str]]:
    """Refuse to author any row whose domain holds no weekly slot.

    2026-09-23. Four scripts ('how-do-scientists-know-so-much' and three
    others, method-evidence and space subjects that were never promoted)
    were authored on 2026-09-21 by a since-closed mined-demand path and are
    held in `loop/promotion_holds.json` — but that hold is a publish-queue
    check (`batch_queue.publish_queue_gate`), not a domain check. A row CAN
    sit in a real `research/publish_order*.json` file — scored, gated,
    genuinely queued — for a domain that has since been retired from
    `loop/config.json` `domains.allocation`, or that was scored by hand
    before ever being allocated. Authoring it anyway ships a domain with no
    publish slot, no `loop/domain_sources.py` allowlist and no
    `visuals/domains.py` palette. This is the second, independent gate: it
    checks the DOMAIN, not the QUEUE.

    Returns (allowed_rows, {slug: reason}) — same shape as
    `batch_queue.publish_queue_gate`.
    """
    alloc = allocation(cfg)
    allowed, refused = [], {}
    for row in rows:
        dom = row_domain(row)
        if dom in alloc:
            allowed.append(row)
        else:
            refused[row.get("slug", "<no-slug>")] = (
                f"domain {dom!r} is not in loop/config.json "
                f"domains.allocation ({sorted(alloc)}) — no publish slot, "
                f"no source allowlist and no palette for it yet")
    return allowed, refused


# ------------------------------------------------------------- allocation

def config_domains(cfg: dict) -> dict:
    d = cfg.get("domains")
    if not d:
        raise KeyError("loop/config.json has no `domains` block")
    for name in d.get("allocation", {}):
        require_known(name)
    return d


def allocation(cfg: dict) -> dict[str, int]:
    """Slots per domain AT THE CADENCE CEILING. Not this week's split."""
    return {k: int(v) for k, v in config_domains(cfg)["allocation"].items()}


def slots_total(cfg: dict) -> int:
    return sum(allocation(cfg).values())


def slots_at(cfg: dict, per_week: int) -> dict[str, int]:
    """The domain split AT A GIVEN weekly rate — not necessarily this week's.

    `live_slots()` below is this for `cadence.videos_per_week`; `cadence.py`'s
    scale-to-4 gate needs the split at a rate it is only CONSIDERING moving
    to, before it commits, which is why this takes the rate as a parameter
    rather than always reading it off the config.

    Largest ceiling share first, so a domain never loses its last live slot to
    rounding while a smaller one keeps one.
    """
    alloc = allocation(cfg)
    ceiling = int(cfg["cadence"]["ceiling"])
    total = sum(alloc.values()) or 1
    if total != ceiling:
        raise ValueError(
            f"domains.allocation sums to {total} but cadence.ceiling is "
            f"{ceiling}. The allocation is expressed at the ceiling; if they "
            f"disagree the live split is arithmetic on a number nobody owns.")
    order = sorted(alloc, key=lambda d: (-alloc[d], d))
    out = {d: 0 for d in alloc}
    left = int(per_week)
    for d in order:
        take = min(alloc[d], left)
        out[d] = take
        left -= take
    return out


def live_slots(cfg: dict) -> dict[str, int]:
    """This week's actual split, derived from the cadence rather than stored.

    The allocation is expressed once, at `cadence.ceiling`, and the live split
    falls out of `cadence.videos_per_week`. Storing both would be the defect
    this module exists to prevent: the cadence escalates itself from 2 to 3 to
    4 on evidence, and a second stored split would silently stop agreeing with
    it the first time it moved.
    """
    return slots_at(cfg, int(cfg["cadence"]["videos_per_week"]))


def domains_support(cfg: dict, per_week: int, need_weeks: float) -> tuple[bool, str]:
    """Can EVERY domain that would carry a slot at `per_week` refill itself?

    The aggregate queue-depth guard (`cadence.queue_supports`) answers "is
    there enough inventory in total" — which stopped being the honest question
    the moment a second domain started supplying its own inventory. Two
    domains at 2/week each is not the same runway as one domain holding all
    four slots' worth of topics; a materials queue that has decayed to zero
    would be invisible to the aggregate check as long as deep sea alone still
    covers the total.

    So this checks EACH domain that would hold a live slot at `per_week`
    against the SAME `need_weeks` floor the aggregate check uses, using its
    own queue depth divided by its own slot count. A domain assigned zero
    slots at this rate is not checked — it supplies nothing to refill.

    Hard-fails (returns False) on a domain with slots but zero surviving
    queue; that is the emptiest possible reason to refuse, not a pass on an
    empty loop.
    """
    slots = slots_at(cfg, per_week)
    depth = queue_depth()
    short = []
    for name, n in slots.items():
        if n <= 0:
            continue
        d = depth.get(name, 0)
        weeks = d / n if n else 0.0
        if d <= 0:
            short.append(f"{name}: 0 queued topics with {n} slot(s)/week")
        elif weeks <= need_weeks:
            short.append(f"{name}: {d} queued topic(s) / {n} slot(s) = "
                        f"{weeks:.1f} weeks, at or below the {need_weeks:g}-"
                        f"week floor")
    if short:
        return False, ("not every domain that would carry a slot at "
                       f"{per_week}/week can refill itself: "
                       + "; ".join(short))
    active = {n: s for n, s in slots.items() if s > 0}
    return True, (f"every domain carrying a slot at {per_week}/week clears "
                  f"the {need_weeks:g}-week floor on its OWN queue: "
                  + ", ".join(f"{n} ({depth.get(n, 0)}/{s}/wk)"
                             for n, s in active.items()))


def min_episodes_to_judge(cfg: dict) -> int:
    return int(config_domains(cfg)["min_episodes_to_judge"])


def queue_exhausted_below(cfg: dict) -> int:
    return int(config_domains(cfg)["queue_exhausted_below"])


def _publish_order_files() -> list[Path]:
    return sorted(ROOT.glob(f"research/{PUBLISH_ORDER_GLOB}"))


def queue_depth(include_published: bool = False) -> dict[str, int]:
    """Surviving, gated topics per domain, from EVERY publish-order file.

    research/publish_order*.json files are READ ONLY from the loop. Each
    domain scores its own candidates against the same gate
    (`research/publish_order.py`'s, imported not reimplemented — see
    research/publish_order_materials.py) and writes its own file; a slug
    counted here that is not from a QUEUE entry never happened, and a slug
    whose script disagrees with the file it came from is caught by
    `domain_of_slug`, not silently trusted. Merging across files, rather than
    reading `research/publish_order.json` alone, is what lets a second
    domain's queue become visible at all.
    """
    out: dict[str, int] = {}
    seen_slugs: set[str] = set()

    # A TOPIC ALREADY UPLOADED IS NOT INVENTORY. The publish-order files are
    # the SCORED list, not the remaining list -- a slug stays in them after its
    # episode is made, because that is where the score and the gate verdict
    # live. Counting them as queue depth double-counted the entire catalogue:
    # on 2026-09-05 deep sea read 16 topics and 8.0 weeks of runway while every
    # one of those 16 was already uploaded and dated. Its true remaining queue
    # was ZERO, and `runway.warn_weeks` would never have fired -- the guard
    # that exists to say "you are running out" could not see the end coming.
    published: set[str] = set()
    if not include_published:
        try:
            import ledger                                  # noqa: PLC0415
            published = {r["slug"] for r in ledger.load()["published"]}
        except Exception:                                  # never break a count
            published = set()

    for path in _publish_order_files():
        q = _read(path).get("queue") or []
        for row in q:
            slug = row.get("slug")
            if not slug or slug in seen_slugs:
                continue                      # a slug counts once, however
                                               # many files mention it
            seen_slugs.add(slug)
            if slug in published:
                continue                      # already made; not inventory
            # THE SCRIPT IS THE AUTHORITY, THE FILE IS THE FALLBACK. A queued
            # topic has no script yet by definition, and until 2026-09-05 that
            # did not matter: the two live domains had scripts on disk for
            # every queued slug, so `domain_of_slug` always answered. A domain
            # the monthly review PROMOTES has a scored queue and not one
            # script, so every row would map to None and the domain would read
            # as depth 0 - out of runway on the day it started, and (because
            # loop/score.py gates on exactly this number) re-running its whole
            # topic gate every Saturday for ever.
            #
            # The file's own `domain` field answers instead, checked against
            # the taxonomy so a typo cannot invent a domain. Where a script
            # exists it still wins, and `domain_of_slug` is what catches a
            # script that disagrees with the file it came from.
            d = domain_of_slug(slug)
            if not d:
                claimed = row.get("domain") or _read(path).get("domain")
                if claimed in known():
                    d = claimed
            if d:
                out[d] = out.get(d, 0) + 1
    return out


def exhausted(cfg: dict, published_slugs: list[str] | None = None) -> list[str]:
    """Domains whose scored queue has DECAYED past the point of being worth a slot.

    Decayed, not empty. A domain that has never published anything has an empty
    queue because nobody has scored topics for it yet, and calling that
    "exhausted" would retire a niche on its first day — the exact opposite of
    what queue decay is supposed to detect. Exhaustion requires that the domain
    actually ran.
    """
    floor = queue_exhausted_below(cfg)
    depth = queue_depth()
    started = set()
    for slug in (published_slugs if published_slugs is not None
                 else list(by_slug())):
        d = domain_of_slug(slug)
        if d:
            started.add(d)
    return [d for d in allocation(cfg)
            if d in started and depth.get(d, 0) < floor]


# ------------------------------------------------------- per-domain evidence

def split_rows(rows: list[dict], ledger_published: list[dict],
               default: str | None = None) -> dict[str, list[dict]]:
    """Measurement rows grouped by the domain of the video they describe."""
    out: dict[str, list[dict]] = {}
    for r in rows:
        d = domain_of_video(r.get("video_id"), ledger_published, default)
        out.setdefault(d or "unattributed", []).append(r)
    return out


def evidence(rows: list[dict], cfg: dict) -> dict:
    """Retention, AVD and view totals for one domain's measured episodes."""
    measured = [r for r in rows if r.get("average_view_duration_s")]
    views = sum(r.get("views") or 0 for r in rows)
    if not measured:
        return {"measured": 0, "views": views, "avd_s": None, "avp": None,
                "judgeable": False,
                "why": "no episode in this domain has analytics yet"}
    avd = sum(float(r["average_view_duration_s"]) for r in measured) / len(measured)
    avps = [float(r["average_view_percentage"]) for r in measured
            if r.get("average_view_percentage") is not None]
    need = min_episodes_to_judge(cfg)
    return {
        "measured": len(measured),
        "views": views,
        "avd_s": round(avd, 1),
        "avp": round(sum(avps) / len(avps), 1) if avps else None,
        "judgeable": len(measured) >= need,
        "why": (None if len(measured) >= need else
                f"{len(measured)} measured episode(s), below the "
                f"{need}-episode floor this domain must clear before its "
                f"allocation may be changed"),
    }


def reallocate(cfg: dict, per_domain: dict[str, dict]) -> dict:
    """Move at most one weekly slot between domains, from measured evidence.

    Bounded exactly like every other knob the monthly review touches:

      * a domain below the minimum sample is HELD, never averaged away
      * at most one slot moves in a month, so a wrong call costs one episode
      * no domain is left with zero slots by a reallocation - dropping a domain
        to nothing is retirement, and retirement is decided by queue decay, not
        by one month of retention
    """
    alloc = allocation(cfg)
    judgeable = {d: e for d, e in per_domain.items()
                 if e.get("judgeable") and d in alloc}
    held = [d for d in alloc if d not in judgeable]

    if len(judgeable) < 2:
        return {
            "applied": False, "allocation": alloc, "held": held,
            "stop": "INSUFFICIENT_DOMAIN_EVIDENCE",
            "why": (f"{len(judgeable)} of {len(alloc)} domain(s) clear the "
                    f"{min_episodes_to_judge(cfg)}-episode floor, so there is "
                    f"nothing to compare. The allocation is held exactly as it "
                    f"is — it is NOT reset to an even split, which would be a "
                    f"decision disguised as a default."),
        }

    best = max(judgeable, key=lambda d: judgeable[d]["avd_s"])
    worst = min(judgeable, key=lambda d: judgeable[d]["avd_s"])
    if best == worst or alloc.get(worst, 0) <= 1:
        return {"applied": False, "allocation": alloc, "held": held,
                "why": (f"{worst} already holds its last slot; a domain is "
                        f"retired on queue decay, never by reallocation.")
                if alloc.get(worst, 0) <= 1 else
                "one judgeable domain; nothing to move"}

    spread = judgeable[best]["avd_s"] - judgeable[worst]["avd_s"]
    threshold = float(config_domains(cfg).get("reallocate_avd_spread_s", 30))
    if spread < threshold:
        return {"applied": False, "allocation": alloc, "held": held,
                "why": (f"{best} leads {worst} by {spread:.0f}s of average view "
                        f"duration, under the {threshold:.0f}s spread that "
                        f"justifies moving a slot.")}

    new = dict(alloc)
    new[worst] -= 1
    new[best] = new.get(best, 0) + 1
    return {
        "applied": True, "allocation": new, "from": alloc, "held": held,
        "moved": {"from": worst, "to": best, "slots": 1},
        "why": (f"{best} holds viewers {spread:.0f}s longer per view than "
                f"{worst} across {judgeable[best]['measured']} and "
                f"{judgeable[worst]['measured']} measured episodes. One weekly "
                f"slot moves; the rest of the allocation stands."),
    }


# ----------------------------------------------------------- niche lifecycle

def lifecycle(cfg: dict, per_domain: dict[str, dict],
              published_slugs: list[str] | None = None) -> dict:
    """RETIRE a decayed domain and PROMOTE the next-ranked one into its slots.

    `reallocate()` moves at most one slot between domains that are already
    running. It deliberately cannot end a domain — it refuses to take a
    domain's last slot, and says so. That left the lifecycle open at both ends:
    `exhausted()` and `next_unused()` were computed every month, written into
    the report as prose, and acted on by nobody. A niche could decay to nothing
    and the allocation would still be feeding it, month after month, in a report
    that said out loud which domain was finished.

    This closes it. The decision is the same shape `reallocate()` returns, and
    it goes through the SAME cooldown fence in monthly.apply_allocation(), so a
    wrong retirement is bounded exactly like a wrong slot move.

    What it will not do, and why:

      * **Retire on an empty queue alone.** `exhausted()` already requires that
        the domain actually published something. This adds a second floor: the
        domain must have `min_episodes_to_judge` MEASURED episodes. A queue that
        is thin after three episodes is a scoring backlog, and the honest fix is
        to score more topics, not to end the niche.
      * **Retire the last domain.** Retirement is only ever a SWAP. With no
        replacement in the taxonomy the allocation is held and the stop is
        named, because a channel with no domain publishes nothing.
      * **Retire more than one domain a month.** One swap, so a wrong call costs
        one domain's slots and is visible before the next one.
      * **Change the slot total.** The promoted domain inherits exactly the
        retired domain's slots, so the allocation still sums to `cadence.ceiling`
        and `slots_at()` does not raise.
    """
    alloc = allocation(cfg)
    ex = exhausted(cfg, published_slugs)
    if not ex:
        return {"applied": False, "allocation": alloc,
                "why": (f"no allocated domain has decayed below the "
                        f"{queue_exhausted_below(cfg)}-topic queue floor.")}

    need = min_episodes_to_judge(cfg)
    ready = [d for d in ex if (per_domain.get(d) or {}).get("measured", 0) >= need]
    if not ready:
        thin = {d: (per_domain.get(d) or {}).get("measured", 0) for d in ex}
        return {
            "applied": False, "allocation": alloc,
            "stop": "QUEUE_DECAYED_BUT_UNMEASURED",
            "why": (f"{', '.join(ex)} has a queue below the "
                    f"{queue_exhausted_below(cfg)}-topic floor but only "
                    f"{thin} measured episode(s), under the {need} this domain "
                    f"must clear before it may be ended. A thin queue this "
                    f"early is a scoring backlog, not a finished niche — the "
                    f"answer is to score more topics for it, not to retire it."),
            "retire_candidates": ex,
        }

    # Deterministic: the weakest holder of viewers among the decayed domains,
    # ties broken by name so two runs of the same month agree.
    retire = min(ready, key=lambda d: ((per_domain[d].get("avd_s") or 0.0), d))
    promote = next_unused(list(alloc))
    if not promote:
        return {
            "applied": False, "allocation": alloc,
            "stop": "NO_REPLACEMENT_DOMAIN",
            "why": (f"{retire} has decayed past the queue floor with "
                    f"{per_domain[retire]['measured']} measured episode(s), but "
                    f"every domain in research/proposed-taxonomy.json is "
                    f"already running. Retirement here is a SWAP, never a "
                    f"subtraction — a channel with fewer domains than slots "
                    f"publishes nothing — so the allocation is held."),
            "retire_candidates": ready,
        }

    new = {d: n for d, n in alloc.items() if d != retire}
    new[promote] = new.get(promote, 0) + alloc[retire]
    return {
        "applied": True, "allocation": new, "from": alloc,
        "retired": retire, "promoted": promote,
        "moved": {"from": retire, "to": promote, "slots": alloc[retire]},
        "why": (f"{retire}'s scored queue has decayed to "
                f"{queue_depth().get(retire, 0)} topic(s), below the "
                f"{queue_exhausted_below(cfg)} floor, after "
                f"{per_domain[retire]['measured']} measured episode(s). Its "
                f"{alloc[retire]} weekly slot(s) pass to {promote}, the "
                f"next-ranked domain in research/proposed-taxonomy.json "
                f"(demand {score(promote)['demand_side_score']}). Retirement "
                f"is decided by queue decay, never by one month of retention."),
    }


# --------------------------------------------------------- per-domain runway

def scheduled_ahead_by_domain() -> dict[str, int]:
    """Episodes UPLOADED, dated and not yet aired, per domain.

    THIS IS INVENTORY. It is the most finished inventory the channel has: the
    video exists, it is on YouTube, it is private with a publishAt, and it will
    air on its own without anyone doing anything. `cadence.runway()` has
    counted it in aggregate since 2026-09-05, with a comment saying an alarm
    that is wrong in the ALARMING direction is one people learn to ignore.

    `domain_runway()` below never got that fix, and the result was exactly the
    predicted failure. On 2026-09-06 (run 34026361219) deep-sea-ocean-science
    had 15 episodes uploaded and dated across the next 7.5 weeks and a
    publish-order queue of 0, because a slug leaves the queue the moment it is
    made. Per-domain runway read `queued: 0` -> `0.0 weeks` -> `critical`; the
    "worse of aggregate and any domain" rule promoted that to the channel; and
    the Sunday lane raised RUNWAY_CRITICAL and exited 3 EVERY WEEK over a
    channel with 8.2 weeks of finished, scheduled video in hand.

    One function, used by both callers, so the aggregate and the per-domain
    figure cannot disagree about what inventory is again.
    """
    import datetime as _dt                                  # noqa: PLC0415
    out: dict[str, int] = {}
    try:
        import ledger as _led                               # noqa: PLC0415
        now_utc = _dt.datetime.now(_dt.timezone.utc)
        slug_domain = by_slug()
        for r in _led.load()["published"]:
            stamp = r.get("scheduled_publish_at")
            if not stamp or r.get("retired_at"):
                continue
            when = _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if when <= now_utc or r.get("privacy") == "public":
                continue                    # already aired; not inventory
            d = slug_domain.get(r.get("slug", ""))
            if d:
                out[d] = out.get(d, 0) + 1
    except Exception:                       # noqa: BLE001 - never break a guard
        return {}
    return out


def domain_runway(cfg: dict, per_week: int | None = None) -> dict[str, dict]:
    """Weeks of queue remaining, PER DOMAIN — a single global number is not
    enough once two domains draw down independently.

    2026-09-03: deep sea and materials-and-manufacturing are projected to
    exhaust within a week of each other (~2026-10-26) while sharing one
    aggregate runway figure that would say nothing about which is actually
    short. Each domain's weeks-remaining is its own queue_depth() divided by
    its own live slot count — the same arithmetic `cadence.runway()` does in
    aggregate, just not pooled across domains that do not share inventory.

    A domain with zero live slots this week is reported with `weeks: None`
    (not zero) — it is not "out of runway", it simply is not being drawn from
    yet, which is a different claim entirely.
    """
    slots = live_slots(cfg) if per_week is None else slots_at(cfg, per_week)
    depth = queue_depth()
    ahead = scheduled_ahead_by_domain()
    warn = float(cfg["runway"]["warn_weeks"])
    crit = float(cfg["runway"]["critical_weeks"])
    out = {}
    for name, n in slots.items():
        d = depth.get(name, 0)
        a = ahead.get(name, 0)
        if n <= 0:
            out[name] = {"slots_per_week": 0, "queued": d,
                         "scheduled_ahead": a, "weeks": None,
                         "level": "not_active",
                         "message": f"{name}: 0 slots/week this week, not "
                                    f"drawing from its queue"}
            continue
        # QUEUED PLUS ALREADY-DATED. See scheduled_ahead_by_domain(): a domain
        # whose whole queue has been made, uploaded and dated is the most
        # finished a domain gets, not the emptiest.
        weeks = round((d + a) / n, 1)
        level = ("critical" if weeks <= crit else
                 "warn" if weeks <= warn else "ok")
        out[name] = {"slots_per_week": n, "queued": d, "scheduled_ahead": a,
                     "weeks": weeks, "level": level,
                     "message": f"{name}: {weeks} week(s) at {n}/week "
                                f"({d} queued, {a} already dated)"}
    return out


def main() -> int:
    from common import config                               # noqa: PLC0415
    cfg = config()
    print(f"{len(known())} scored domain(s) in research/proposed-taxonomy.json")
    for name, slots in allocation(cfg).items():
        s = score(name)
        print(f"  {name:<34} {slots} slot(s)  demand {s['demand_side_score']}  "
              f"queue {queue_depth().get(name, 0)}")
    ex = exhausted(cfg)
    print(f"exhausted: {ex or 'none'}")
    print(f"next unused: {next_unused(list(allocation(cfg)))}")
    counts: dict[str, int] = {}
    for d in by_slug().values():
        counts[d] = counts.get(d, 0) + 1
    print(f"episodes by domain: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
