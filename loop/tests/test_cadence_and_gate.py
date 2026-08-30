"""The two invariants that protect the loop from its owner's good intentions.

**The cadence ceiling.** `pov/topic-taxonomy.json` sets the CEILING at four a
week. `loop/config.json` sets the OPERATING cadence, currently two, escalating
to three on evidence. Two components each keeping their own number with no link
between them is exactly how a ceiling quietly becomes five, so this test is the
link: the operating cadence and the escalated cadence must both sit at or under
the taxonomy's ceiling, and the ceiling recorded in config must match it.

**The dashboard never blocks.** There is no approval step: topics are picked
automatically under the hard exclusion gate and POV lines come from the owner's
own bank. The page is a notification with an override, so this asserts it stays
credentialless and self-contained AND that nothing in the pipeline waits on it.

Hard-fails if it examines zero items.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PAGE = os.path.join(ROOT, "docs", "approve", "index.html")

CEILING = 4


def check() -> list[str]:
    fails, examined = [], 0

    # ---------------------------------------------------- cadence ceiling
    cfg = json.load(open(os.path.join(LOOP, "config.json")))
    tax = json.load(open(os.path.join(ROOT, "pov", "topic-taxonomy.json")))
    a = cfg["cadence"]["videos_per_week"]
    esc = cfg["cadence"]["escalated"]
    recorded = cfg["cadence"]["ceiling"]
    b = tax["cadence"]["videos_per_week"]
    examined += 3
    if recorded != b:
        fails.append(f"ceiling drift: loop/config.json records a ceiling of "
                     f"{recorded}, pov/topic-taxonomy.json says {b}")
    if a > b:
        fails.append(f"operating cadence {a} exceeds the taxonomy ceiling {b}")
    if esc > b:
        fails.append(f"escalated cadence {esc} exceeds the taxonomy ceiling {b}")
    if a > CEILING or esc > CEILING:
        fails.append(f"cadence raised above {CEILING}; the ceiling is "
                     f"deliberate and never raised to clear a backlog")
    if not cfg["cadence"].get("deliberate"):
        fails.append("loop/config.json no longer marks the ceiling deliberate")

    # The queue itself must never exceed it.
    qpath = os.path.join(LOOP, "render_queue.json")
    if os.path.exists(qpath):
        q = json.load(open(qpath))
        examined += 1
        # The queue may hold up to the ESCALATED cadence, never past the ceiling.
        if len(q.get("items", [])) > b:
            fails.append(f"render_queue.json holds {len(q['items'])} items, "
                         f"over the ceiling of {b}")

    # Nothing may block on the dashboard.
    for f in ("prepare.py", "draft.py"):
        examined += 1
        src = open(os.path.join(LOOP, f)).read()
        if "NOT_APPROVED" in src or "APPROVE_ALL_MISSING" in src:
            fails.append(f"loop/{f} still blocks waiting for approval")

    # Nothing in the loop may write a larger number.
    for f in ("rank.py", "draft.py"):
        examined += 1
        src = open(os.path.join(LOOP, f)).read()
        if re.search(r"videos_per_week\s*=\s*\d", src):
            fails.append(f"loop/{f} hardcodes videos_per_week instead of "
                         f"reading the config")

    # ------------------------------------------------------ the gate is small
    if not os.path.exists(PAGE):
        fails.append("docs/approve/index.html does not exist — there is no "
                     "approval gate")
    else:
        examined += 1
        html = open(PAGE).read()
        if len(html) > 120_000:
            fails.append(f"the approval page is {len(html)} bytes; a gate that "
                         f"large is not a five-minute page")
        # Credentialless: it must not depend on a token, a login or a fetch.
        for bad, why in (
            (r"\bfetch\s*\(", "it fetches at runtime — the page must be "
                              "self-contained and work offline"),
            (r"XMLHttpRequest", "it makes a runtime request"),
            (r"api[_-]?key", "it references an API key"),
            (r"Authorization", "it references an auth header"),
            (r"<form[^>]+action=", "it posts to a server"),
        ):
            if re.search(bad, html, re.I):
                fails.append(f"approval page is not credentialless: {why}")
        # It must carry the week's data inline, and offer one approve-all path.
        if "const DATA" not in html:
            fails.append("the approval page has no inlined week data")
        if "OVERRIDE" not in html:
            fails.append("the dashboard offers no override path")
        if "waiting on you" not in html:
            fails.append("the dashboard does not state that nothing waits on her")
        # The page must not have regained an approval gate.
        if re.search(r"Approve all|approval required", html, re.I):
            fails.append("the dashboard has regained an approval gate; "
                         "selection is automatic now")
        n_cards = html.count('class="card"')
        if n_cards == 0:
            fails.append("the approval page shows zero videos")
        if n_cards > CEILING + 2:
            fails.append(f"the approval page shows {n_cards} cards; the gate "
                         f"must stay one page")

    if examined == 0:
        fails.append("examined ZERO items")
    print(f"inspected {examined} invariant(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - ceiling held at 4, gate credentialless and small"
          if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
