"""The Monday lane refuses to author a topic outside domains.allocation.

THE GAP. `test_monday_writes_only_publish_queue.py` closed the mined-demand
path: nothing may be authored that is not already in a real
`research/publish_order*.json` file. That is a QUEUE check. It does not catch
a row that IS genuinely scored and sitting in a real publish-order file for a
domain that is not (or is no longer) in `loop/config.json`
`domains.allocation` — a domain retired by `loop/domains.lifecycle()`, or
scored by hand before ever being allocated. Authoring it anyway is exactly
how the four method-evidence/space scripts authored 2026-09-21 shipped with
no publish slot, no `loop/domain_sources.py` allowlist and no
`visuals/domains.py` palette (they are held, not deleted, in
`loop/promotion_holds.json` — a separate, queue-shaped fix). Worse: because
`loop/draft.py` never passed `domain=` to `author.draft()`, every one of
those four scripts was ALSO mislabelled — each carries
`**Domain:** deep-sea-ocean-science`, the author's own default, regardless of
its real subject.

WHAT THIS PROVES:

  1. `domains.row_domain()` resolves a topic/queue row's domain from every
     shape a caller hands it (row's own `domain`, `_domain_file`,
     `queue_file`, or an existing script's own `**Domain:**` line), and falls
     back to deep sea only for the one file that names none of them.
  2. `domains.allocation_gate()` allows every row whose resolved domain holds
     a weekly slot and refuses every row whose domain does not, by name, with
     a reason.
  3. `loop/draft.py` (Monday), handed a real publish-queue row for an
     unallocated domain, refuses it BY NAME, never calls `author.draft()` for
     it, and does not silently default it to deep sea.
  4. `loop/validate.py` V42 (`v42_authored_domain_is_allocated`) passes on
     the real, live `loop/render_queue.json` items and FAILS on a fixture
     script naming an unallocated domain — proved negatively, against a
     scratch file, never against anything committed.

Hard-fails if it examines zero items. Never writes committed state: every
output path is redirected to a temp dir (`loop/tests/run_all.py` checks).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

os.environ.setdefault("LOOP_STOPS_DIR",
                      tempfile.mkdtemp(prefix="domain-allocation-stops-"))

import common                                              # noqa: E402 - loop/ is on sys.path above
import domains                                             # noqa: E402

fails: list[str] = []
examined = 0

CFG = common.config()
ALLOC = domains.allocation(CFG)
UNALLOCATED = "method-evidence"
if UNALLOCATED in ALLOC:
    fails.append(f"fixture domain {UNALLOCATED!r} is actually allocated - "
                 f"pick a different unallocated fixture name")

# --------------------------------------------------------- 1. row_domain()
examined += 1
cases = [
    ({"domain": "materials-and-manufacturing"}, "materials-and-manufacturing",
     "a row's own `domain` key wins"),
    ({"_domain_file": "publish_order_materials.json"},
     "materials-and-manufacturing",
     "_domain_file's own top-level `domain` resolves"),
    ({"queue_file": "publish_order_materials.json"},
     "materials-and-manufacturing",
     "queue_file (loop/rank.py's field name) resolves the same way"),
    ({"_domain_file": "publish_order.json"}, domains.UNSUFFIXED_FILE_DOMAIN,
     "the unsuffixed file, which names no domain anywhere, falls back to "
     "UNSUFFIXED_FILE_DOMAIN"),
    ({"script": "does/not/exist.md"}, domains.UNSUFFIXED_FILE_DOMAIN,
     "a script path that does not exist on disk cannot be read; falls back"),
]
for row, want, why in cases:
    got = domains.row_domain(row)
    if got != want:
        fails.append(f"row_domain({row}) -> {got!r}, want {want!r} ({why})")

# An existing script's own Domain line wins when nothing else names one.
examined += 1
real_script = next(iter(sorted((ROOT / "scripts").glob("*.md"))), None)
if real_script is None:
    fails.append("scripts/ is empty - cannot prove the script-path fallback")
else:
    real_domain = domains.domain_of_script(real_script)
    got = domains.row_domain(
        {"script": str(real_script.relative_to(ROOT))})
    if got != real_domain:
        fails.append(f"row_domain() did not read {real_script.name}'s own "
                     f"**Domain:** line: got {got!r}, script says {real_domain!r}")

# ----------------------------------------------------- 2. allocation_gate()
examined += 1
rows = ([{"slug": f"ok-{d}", "domain": d} for d in ALLOC]
       + [{"slug": "bad-method-evidence", "domain": UNALLOCATED},
          {"slug": "bad-space", "domain": "space-astronomy"}])
allowed, refused = domains.allocation_gate(rows, CFG)
allowed_slugs = {r["slug"] for r in allowed}
if allowed_slugs != {f"ok-{d}" for d in ALLOC}:
    fails.append(f"allocation_gate() allowed {sorted(allowed_slugs)}, wanted "
                 f"exactly the allocated fixture(s) {sorted(f'ok-{d}' for d in ALLOC)}")
for slug in ("bad-method-evidence", "bad-space"):
    if slug not in refused or "domains.allocation" not in refused[slug]:
        fails.append(f"allocation_gate() did not refuse {slug} by name, "
                     f"naming domains.allocation: {refused.get(slug)!r}")

# ------------------------------------------------------ 3. draft.py, sandboxed
def run(body: str, tmp: Path) -> subprocess.CompletedProcess:
    head = f"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, {str(LOOP)!r})
TMP = Path({str(tmp)!r})
import cadence, batch_queue
cadence.runway = lambda per_week=None: {{
    "level": "ok", "weeks_remaining": 6.0, "short_domains": [],
    "by_domain": {{}}, "message": "fixture: 6.0 weeks of queue at 4/week"}}
rc = 0
"""
    tail = """
print("RC", rc)
"""
    env = dict(os.environ, LOOP_STOPS_DIR=str(tmp / "stops"),
               LOOP_DRY_RUN="1", OPENROUTER_API_KEY="")
    (tmp / "stops").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, "-c", head + body + tail],
                          capture_output=True, text=True, env=env,
                          cwd=str(ROOT), timeout=300)


with tempfile.TemporaryDirectory(prefix="domain-allocation-mon-") as td:
    tmp = Path(td)
    fixture_slug = "zz-fixture-unallocated-domain-topic"
    next_topics = {
        "week": "fixture-week",
        "selected": [{
            "slug": fixture_slug,
            "question": "why is the fixture topic unallocated",
            "script": None,
            "source": "publish-queue",
            "domain": UNALLOCATED,
            "queue_file": "publish_order.json",
            "needs_authoring": True,
            "pov_id": "fixture-pov",
            "pov_line": "fixture line, never spoken",
        }],
    }
    (tmp / "next_topics.json").write_text(json.dumps(next_topics))

    examined += 1
    r = run(f"""
import draft, author
draft.TOPICS = Path({str(tmp / "next_topics.json")!r})
draft.QUEUE = TMP / "render_queue.json"
# Make the fixture slug look genuinely QUEUED, so the publish-queue gate
# (already closed) allows it through and this test isolates the NEW,
# domain-allocation gate specifically.
real_entries = batch_queue.queued_entries
batch_queue.queued_entries = lambda: real_entries() + [{{
    "slug": {fixture_slug!r}, "query": "why is the fixture topic unallocated",
    "domain": {UNALLOCATED!r}, "_domain_file": "publish_order.json"}}]
CALLED = []
def _no(*a, **k):
    CALLED.append(a[1] if len(a) > 1 else a)
    raise AssertionError("author.draft called for a domain outside allocation")
author.draft = _no
draft.brief_for = lambda t, w: (_ for _ in ()).throw(
    AssertionError("brief written for a domain-refused topic"))
try:
    draft.main()
except SystemExit as e:
    rc = e.code
print("AUTHORED", CALLED)
print("QUEUE_WRITTEN", draft.QUEUE.exists())
""", tmp / "mon")
    out = r.stdout + r.stderr
    if f"REFUSE {fixture_slug}:" not in out:
        fails.append(f"Monday did not refuse {fixture_slug} by name: "
                     f"{out.strip()[-800:]}")
    if "domains.allocation" not in out:
        fails.append("the refusal does not name domains.allocation as the "
                     f"reason: {out.strip()[-800:]}")
    if "AUTHORED []" not in r.stdout:
        fails.append(f"Monday called the author for a domain outside "
                     f"allocation: {out.strip()[-800:]}")
    if "QUEUE_WRITTEN False" not in r.stdout:
        fails.append("Monday wrote loop/render_queue.json with nothing "
                     "allocated to hand off")
    # What happens NEXT (PUBLISH_QUEUE_FULLY_WRITTEN, or NO_SCRIPTS if the
    # real repo's own backlog happens to be non-empty today) depends on live
    # repo state unrelated to this fixture, so this only proves Rule 0: a
    # NAMED, printed stop — never an unhandled traceback.
    if "NAMED STOP" not in out and "RC 0" not in r.stdout:
        fails.append(f"a fully-refused Monday neither exited 0 nor printed a "
                     f"NAMED STOP - looks like a crash, not Rule 0: "
                     f"{out.strip()[-400:]}")

# ------------------------------------------------------ 4. V42, both ways
import validate                                             # noqa: E402

examined += 1
queue_path = ROOT / "loop" / "render_queue.json"
if not queue_path.exists():
    fails.append("loop/render_queue.json does not exist - cannot prove V42 "
                 "against the real queue")
else:
    real_items = json.loads(queue_path.read_text())["items"]
    res = validate.v42_authored_domain_is_allocated(real_items)
    if res.examined == 0:
        fails.append("V42 examined zero real items")
    if not res.ok:
        fails.append(f"V42 fails against the real, live render queue: "
                     f"{res.failures}")

examined += 1
with tempfile.TemporaryDirectory(prefix="domain-allocation-v42-") as td:
    bad_script = Path(td) / "fixture-outside-allocation.md"
    bad_script.write_text(
        "# Fixture\n\n**Domain:** " + UNALLOCATED + "\n\n"
        "## Narration\n\nFixture only, never queued or committed.\n")
    fixture_items = [{"slug": "fixture-outside-allocation",
                      "script": str(bad_script)}]
    res = validate.v42_authored_domain_is_allocated(fixture_items)
    if res.ok:
        fails.append("V42 passed a fixture script naming an unallocated "
                     "domain - the negative proof failed")
    if not any(UNALLOCATED in f and "domains.allocation" in f
              for f in res.failures):
        fails.append(f"V42's failure does not name the unallocated domain "
                     f"and domains.allocation: {res.failures}")

if examined == 0:
    fails.append("examined ZERO items - this test cannot reach what it governs")
print(f"inspected {examined} item(s): row_domain x6, allocation_gate x1 "
     f"({len(rows)} fixture rows), Monday x1, V42 x2")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - the domain-allocation gate refuses to author outside "
     "domains.allocation, and V42 guards the render queue against it")
