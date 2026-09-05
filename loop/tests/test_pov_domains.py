"""A POV line must be reachable for the domain it was recorded for.

`pov_match.score()` multiplied every `tier: specific` line by zero unless the
SUBJECT TEXT matched a deep-sea vocabulary. That was right while the bank held
one interview about one niche. It became wrong on 2026-09-03, when materials
went live, and badly wrong on 2026-09-05, when an eleven-domain interview added
twenty-one specific lines: every one of them was in the bank, none could ever be
selected, and nothing said so - because the transferable fallback always
answers, so a dead line looks exactly like a line that simply did not win.

  1. every `domain` named in the bank is a real taxonomy domain
  2. every `tag` used in the bank has a signal pattern - a tag with no
     vocabulary is a line that can never be selected, which is how
     `evidence-limit` sat dead on three lines
  3. a specific line scores for its OWN domain and zero for another
  4. a legacy specific line (no `domain` field) is still deep sea's
  5. a real materials subject selects a materials line, not the fallback
  6. every domain with specific lines can actually reach one of them
  7. the bank's own rule still holds: no line is invented, NoPovMatch is raised

Hard-fails if it runs zero checks.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import domains as D        # noqa: E402
import pov_match as P      # noqa: E402

CHECKS = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"{label}: {detail or 'failed'}")
    print(f"  ok  {label}")


def main() -> int:
    lines = P.bank()
    check("the bank is not empty", len(lines) > 0)

    known = set(D.known())
    for l in lines:
        if "domain" in l:
            check(f"{l['id']} names a real domain", l["domain"] in known,
                  f"{l['domain']!r} is not in research/proposed-taxonomy.json")

    tags = {l["tag"] for l in lines}
    for tag in sorted(tags):
        check(f"tag {tag!r} has a signal pattern", tag in P._COMPILED,
              "a tag with no vocabulary is a line that can never be selected")

    # 3 + 4 --------------------------------------------- the domain rule itself
    specific = [l for l in lines if l["tier"] == "specific" and "domain" in l]
    check("the bank has domain-tagged specific lines", len(specific) > 0)
    sample = specific[0]
    other = next(d for d in known if d != sample["domain"])
    # a subject its own tag definitely fires on
    subject = {"scale": "how big and how deep", "systems": "how it is made",
               "failure": "why it fails and cracks",
               "confidence": "how strong is it",
               "numbers": "how hot in degrees celsius",
               "unknown": "the hidden thing nobody sees",
               "instruments": "how it is measured and calibrated",
               "earth": "volcano and tectonic plates",
               "deeptime": "fossil and mass extinction",
               "evidence-limit": "how do scientists know, the fossil record",
               "uncertainty": "the forecast and its error bar",
               "policy": "nuclear energy and emissions",
               "risk": "the danger and the failure mode",
               }.get(sample["tag"], "how do we know")
    check(f"{sample['id']} scores for its own domain",
          P.score(sample, subject, sample["domain"]) > 0,
          f"tag {sample['tag']!r} scored 0 on {subject!r} for its own domain")
    check(f"{sample['id']} scores zero for another domain",
          P.score(sample, subject, other) == 0.0,
          f"a {sample['domain']} line was offered to {other}")

    legacy = next((l for l in lines
                   if l["tier"] == "specific" and "domain" not in l), None)
    check("a legacy specific line exists to test", legacy is not None)
    check("a legacy specific line is treated as deep sea's",
          P.line_domain(legacy) == "deep-sea-ocean-science")
    check("and it scores zero for a non-deep-sea domain",
          P.score(legacy, "deep trench midnight zone",
                  "materials-and-manufacturing") == 0.0)

    # 5 ------------------------------------- a real subject, end to end
    pick = P.select("how-strong-is-titanium", "How strong is titanium?",
                    domain="materials-and-manufacturing")
    check("a materials subject selects a materials line",
          pick["tier"] == "specific",
          f"got {pick['pov_id']} [{pick['tier']}] via {pick['matched_by']}")

    # 6 ------------------------- every domain with lines can reach one of them
    by_domain: dict = {}
    for l in specific:
        by_domain.setdefault(l["domain"], []).append(l)
    for dom, group in sorted(by_domain.items()):
        reachable = [l for l in group
                     if P.score(l, " ".join(
                         P.TAG_SIGNALS[l["tag"]]
                         .replace("\\b", " ").replace("|", " ")
                         .split())[:0] or "x", dom) >= 0]
        # the real check: at least one line in the domain scores on a subject
        # built from its own tag's vocabulary
        hit = False
        for l in group:
            probe = P.TAG_SIGNALS[l["tag"]].split("|")[0].replace("\\b", "")
            probe = probe.replace("r\"", "").strip()
            if P.score(l, probe, dom) > 0:
                hit = True
                break
        check(f"{dom} can reach at least one of its {len(group)} line(s)", hit,
              "every specific line in this domain scores zero on its own "
              "tag's own vocabulary")

    # 7 ------------------------------------------- it still refuses to invent
    check("select() raises rather than inventing when nothing is left",
          _raises_when_exhausted())

    if CHECKS == 0:
        raise AssertionError("ran zero checks - an empty test proves nothing")
    print(f"\n{CHECKS} check(s) passed")
    return 0


def _raises_when_exhausted() -> bool:
    every = [l["id"] for l in P.bank()]
    real = P.rotation_window
    P.rotation_window = lambda: len(every) + 1
    try:
        P.select("nothing-like-this-at-all", "qqqq zzzz", every)
        return False
    except P.NoPovMatch:
        return True
    finally:
        P.rotation_window = real


if __name__ == "__main__":
    raise SystemExit(main())
