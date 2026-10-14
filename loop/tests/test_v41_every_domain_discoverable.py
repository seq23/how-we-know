"""V41 discovery-metadata runs at the merge gate, not only in the daily reach
lane — and every prepared long-form description keeps its domain's tags.

14 Oct 2026: main went red in the 10:00 CT reach lane on V41 for a day after
food-science landed (PRs #195/#210/#219) because nothing at the PR gate ran
V41. Three defects reached main unseen:
  * food-science was allocated with no discovery `tags`/`hashtags`;
  * V41 looked for scripts only in scripts/*.md, so the food episode under
    scripts/food/ was invisible to it;
  * loop/describe.compose (#207) built tags from search phrasings alone, so
    every prepared slug shipped tags carrying none of its domain's own.

This test makes each of those fail a PR:
  1. the real V41 must PASS on the repository as it stands;
  2. negatively, V41 must FAIL when an allocated domain's discovery block is
     removed (no `tags`, no `hashtags`) and when its only scripts are hidden;
  3. every slug in loop/state/descriptions.json whose script names a domain
     gets compose tags carrying at least one of that domain's own tags and
     none of another allocated domain's, inside both tag limits.

Hard-fails when it examines zero prepared slugs.
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)

import describe                                                    # noqa: E402
import discovery                                                   # noqa: E402
import domains                                                     # noqa: E402
import validate                                                    # noqa: E402

fails: list[str] = []
examined = 0

# 1. the real thing passes
r = validate.v41_discovery_metadata()
examined += 1
if not r.ok:
    fails.append(f"V41 fails on the repository: {r.failures}")

cfg = validate.config()
alloc = list(domains.allocation(cfg))
if not alloc:
    fails.append("no allocated domain - examined nothing")

# 2a. negative: strip each allocated domain's discovery block in turn
real_config = validate.config
for name in alloc:
    broken = copy.deepcopy(cfg)
    broken["discovery"]["domains"].pop(name, None)
    validate.config = lambda b=broken: b
    try:
        rr = validate.v41_discovery_metadata()
    finally:
        validate.config = real_config
    examined += 1
    joined = " | ".join(rr.failures)
    for want in (f"{name}: discovery.domains has no `tags`",
                 f"{name}: discovery.domains has no `hashtags`"):
        if want not in joined:
            fails.append(f"V41 did not fail '{want}' with {name}'s discovery "
                         f"block removed - a new domain could land untagged")

# 2b. negative: hide every script of each allocated domain in turn
real_paths = domains.script_paths
for name in alloc:
    kept = [p for p in real_paths() if domains.domain_of_script(p) != name]
    domains.script_paths = lambda k=kept: k
    try:
        rr = validate.v41_discovery_metadata()
    finally:
        domains.script_paths = real_paths
    examined += 1
    if f"{name}: no script on disk carries this domain" not in " | ".join(rr.failures):
        fails.append(f"V41 did not fail with every {name} script hidden - a "
                     f"domain could land with no script to prove its tags")

# 3. every prepared description's tags keep the domain
doc = describe.load()
domain_tags = {d: set(discovery._discovery_block(cfg, d)[0]) for d in alloc}
n_prepared = 0
for slug, rec in sorted((doc.get("episodes") or {}).items()):
    d = domains.domain_of_slug(slug)
    if d not in domain_tags:
        continue
    qs = rec.get("questions") or []
    if len(qs) < describe.MIN_QUESTIONS:
        continue
    n_prepared += 1
    examined += 1
    subj = (rec.get("subject") or "").split()
    tags = describe.compose_tags(slug, [q.rstrip("?").lower() for q in qs] + subj)
    tagset = set(tags)
    if not (tagset & domain_tags[d]):
        fails.append(f"{slug}: composed tags {tags} carry none of {d}'s own")
    for other, ot in domain_tags.items():
        if other != d and tagset & ot:
            fails.append(f"{slug}: composed tags carry {sorted(tagset & ot)} "
                         f"from {other}")
    if not describe._tags_fit(tags):
        fails.append(f"{slug}: composed tags exceed a tag limit")
    if not any(t in tagset for t in (q.rstrip("?").lower() for q in qs)):
        fails.append(f"{slug}: composed tags lost every search phrasing")
if n_prepared == 0:
    fails.append("no prepared description with a known domain - examined "
                 "nothing")

if fails:
    for f in fails:
        print("FAIL:", f)
    sys.exit(1)
print(f"PASS: {examined} check(s) - V41 passes, fails on a stripped domain "
      f"and on hidden scripts for all {len(alloc)} domain(s), and "
      f"{n_prepared} prepared description(s) keep their domain's tags")
