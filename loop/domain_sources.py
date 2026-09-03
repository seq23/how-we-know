"""The per-domain narration source allowlist. ONE list per domain, imported
by both the authoring lane and the validator that checks its work.

Before this file existed, `loop/author.py`'s prompt hardcoded the deep-sea
list (NOAA, MBARI, Woods Hole, Smithsonian Ocean, USGS, NASA, Schmidt Ocean)
directly in its system prompt, and `loop/validate.py` kept a SEPARATE,
similar-but-not-identical list (`ORG_NAMES`) for its own soft attribution
check. Two components, each keeping their own list, with nothing linking
them — the exact defect `loop/domains.py`'s own docstring names. A materials
script naming NIST would have been invisible to both: the author was never
told NIST was an acceptable source, and the validator would not have
recognised the name to check for it either.

`loop/config.json`'s own `domains.per_domain_requirements.source_allowlist`
already states the rule this file implements: "Each domain names its own
public bodies... a new domain adds its own and must not inherit NOAA/MBARI,
which publish nothing about its subject." This is that addition.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import domains as _domains  # noqa: E402 -- the one place a domain name may
                            # come from (research/proposed-taxonomy.json)

# Named public institutions that genuinely publish primary material on this
# domain's subject. Every one of these must appear, with a real reachable
# URL, in a script's `## Sources` before the narration may cite it — see
# `loop/validate.py` v6_attribution (soft) and v5/v8 (hard: a script that
# states numbers must carry sources, and every URL is fetched).
ALLOWLIST: dict[str, list[str]] = {
    "deep-sea-ocean-science": [
        "NOAA", "NOAA Ocean Exploration", "MBARI", "WHOI",
        "Woods Hole Oceanographic Institution", "Woods Hole",
        "Smithsonian", "Smithsonian Ocean", "USGS", "NASA", "NSF", "IHO",
        "GEBCO", "Monterey Bay Aquarium Research Institute",
        "Schmidt Ocean Institute", "National Geographic",
        "Guinness World Records", "Ocean Census", "Census of Marine Life",
        "Scripps", "JAMSTEC", "NIWA", "Nature", "Science", "Royal Society",
        "British Antarctic Survey",
    ],
    "materials-and-manufacturing": [
        "NIST", "ASM International", "USGS", "USGS Minerals",
        "Nature Materials", "MIT", "MIT DMSE",
        "MIT Department of Materials Science and Engineering", "Fraunhofer",
        "ASTM International", "IEEE", "Nature", "Science",
    ],
}

# Alternate spellings/domains an attribution check should accept as the same
# body — e.g. narration names "MIT DMSE" but ## Sources links mit.edu.
ALIAS: dict[str, dict[str, str]] = {
    "deep-sea-ocean-science": {
        "WHOI": "Woods Hole", "Woods Hole": "WHOI",
        "MBARI": "Monterey Bay Aquarium Research Institute",
        "Monterey Bay Aquarium Research Institute": "MBARI",
        "Smithsonian": "ocean.si.edu", "NOAA": "noaa.gov", "NASA": "nasa.gov",
    },
    "materials-and-manufacturing": {
        "MIT DMSE": "MIT",
        "MIT Department of Materials Science and Engineering": "MIT",
        "MIT": "mit.edu", "NIST": "nist.gov",
        "ASM International": "asminternational.org",
        "USGS Minerals": "usgs.gov", "USGS": "usgs.gov",
        "Fraunhofer": "fraunhofer.de", "Nature Materials": "nature.com",
        "ASTM International": "astm.org",
    },
}


def known() -> list[str]:
    return sorted(ALLOWLIST)


def for_domain(domain: str) -> list[str]:
    names = ALLOWLIST.get(domain)
    if not names:
        raise KeyError(
            f"{domain!r} has no source allowlist in loop/domain_sources.py. "
            f"Every domain that can author or validate a script needs one; "
            f"{len(ALLOWLIST)} declared: {known()}.")
    return names


def alias_for(domain: str) -> dict[str, str]:
    return ALIAS.get(domain, {})


def require_declared_for_active_domains(cfg: dict) -> None:
    """Guard: every domain with a live cadence allocation has an allowlist.

    Scoped to the domains actually in `loop/config.json`'s `domains.allocation`
    — not the full 20-domain scored taxonomy, which includes niches nobody
    has decided to publish. Raises, never warns; used by the
    domain-abstraction validator.
    """
    active = list(_domains.config_domains(cfg)["allocation"])
    missing = [d for d in active if d not in ALLOWLIST]
    if missing:
        raise KeyError(
            f"no source allowlist for active domain(s): {missing}. "
            f"loop/config.json domains.allocation names {active}; "
            f"loop/domain_sources.py declares {known()}.")


if __name__ == "__main__":
    for d in known():
        print(f"{d}: {len(for_domain(d))} sources")
