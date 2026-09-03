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


def queue_depth() -> dict[str, int]:
    """Surviving, gated topics per domain, from the ranking that already exists.

    `research/publish_order.json` is READ ONLY from the loop. Its `queue` holds
    the topics that passed the demand and saturation gates; the domain comes off
    each entry's own script, so a topic and its domain cannot disagree.
    """
    q = _read(PUBLISH_ORDER).get("queue") or []
    out: dict[str, int] = {}
    for row in q:
        slug = row.get("slug")
        if not slug:
            continue
        d = domain_of_slug(slug)
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
