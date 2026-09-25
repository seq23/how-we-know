"""The Monday lane writes ONLY topics already in the publish queue.

THE INCIDENT. On 2026-09-21 loop/rank.py filled the week's shortfall from
MINED demand (autocomplete strings that never passed the demand gate) and
loop/draft.py authored four of them into loop/drafts/ and
loop/render_queue.json. None was in any research/publish_order*.json. The
Mac's nightly batch reads only the publish queue, so they could never be
narrated, the shelf ran dry, and the upload lane paged (run 35738742706).

THE OWNER'S DECISION (2026-09-23, 06:05 CDT): the Monday lane writes only
topics already in the publish queue. The four scripts are not queued for the
Mac and not deleted; they are held for her promotion decision
(loop/promotion_holds.json), and the upload lane treats them as a known hold,
green and named, not a daily page.

WHAT THIS PROVES, against the real repo state, in scratch directories only:

  1. batch_queue.publish_queue_gate(): every real publish-queue slug that is
     not held is allowed; every held slug and every slug outside the queue is
     refused, each with a reason.
  2. loop/rank.py (Sunday selection) selects nothing outside the publish
     queue from today's real backlog. With the queue fully written it writes
     an empty week and takes PUBLISH_QUEUE_FULLY_WRITTEN (exit 0, named). A
     fixture queue row with no script IS selected, as `publish-queue`.
  3. loop/draft.py (Monday) handed today's stale next_topics.json (the four
     mined topics) refuses all four BY NAME, never calls the author, never
     writes loop/render_queue.json, and takes PUBLISH_QUEUE_FULLY_WRITTEN
     (exit 0, named - Rule 0).
  4. The upload lane, on today's real state with the real hold register and
     an ok runway, is the GREEN named stop SCRIPTS_AWAITING_PROMOTION naming
     all four held slugs; a NEW script outside the queue still pages.

Hard-fails if it examines zero items. Never writes committed state: every
output path is redirected to a temp dir (loop/tests/run_all.py checks).
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
                      tempfile.mkdtemp(prefix="monday-queue-only-stops-"))

import batch_queue                                         # noqa: E402 - loop/ is on sys.path above
import cloud_upload as CU                                  # noqa: E402 - loop/ is on sys.path above
import common                                              # noqa: E402 - loop/ is on sys.path above
import ledger                                              # noqa: E402 - loop/ is on sys.path above

fails: list[str] = []
examined = 0

HELD = ["how-do-scientists-know-so-much",
        "how-do-scientists-know-how-old-something-is",
        "why-deep-sea-creatures",
        "how-do-scientists-know-about-other-galaxies"]

# ---------------------------------------------------------------- 1. the gate
queued = batch_queue.queued_slugs()
holds = batch_queue.promotion_holds()
if not queued:
    fails.append("the real publish queue is empty - nothing to examine")
if sorted(holds) != sorted(HELD):
    fails.append(f"loop/promotion_holds.json does not hold exactly the four "
                 f"2026-09-21 scripts: {sorted(holds)}")
for s in HELD:
    if not (ROOT / holds.get(s, {}).get("script", "missing")).exists():
        fails.append(f"held script for {s} is gone - holds retire by flag, "
                     f"never by deletion")
mined = "how-do-scientists-know-what-a-mined-topic-is"
allowed, refused = batch_queue.publish_queue_gate(queued + HELD + [mined])
examined += len(queued) + len(HELD) + 1
if allowed != [s for s in queued if s not in holds]:
    fails.append("the gate did not allow exactly the non-held publish-queue "
                 "slugs, in order")
for s in HELD + [mined]:
    if s not in refused or not refused[s]:
        fails.append(f"the gate did not refuse {s} with a reason")
if "promotion" not in refused.get(HELD[0], ""):
    fails.append("a held slug's refusal does not say it awaits promotion")
if "publish_order" not in refused.get(mined, ""):
    fails.append("an unqueued slug's refusal does not name the publish queue")


# --------------------------------------------------- stage runner (sandboxed)
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


with tempfile.TemporaryDirectory(prefix="monday-queue-only-") as td:
    tmp = Path(td)

    # ------------------------------------------ 2a. Sunday, today's state
    examined += 1
    r = run("""
import rank
rank.OUT = TMP / "next_topics.json"
rank.ROOT = TMP   # only used to print OUT relative to it
try:
    rank.main()
except SystemExit as e:
    rc = e.code
doc = json.loads(rank.OUT.read_text()) if rank.OUT.exists() else None
print("SELECTED", json.dumps(None if doc is None else
      [[s["slug"], s["source"]] for s in doc["selected"]]))
print("ADVISORY", 0 if doc is None else len(doc["advisory_candidates"]))
""", tmp / "sun")
    out = r.stdout + r.stderr
    sel_line = next((l for l in r.stdout.splitlines()
                     if l.startswith("SELECTED ")), "SELECTED null")
    sel = json.loads(sel_line[len("SELECTED "):])
    if sel is None:
        fails.append(f"rank.py wrote no week at all: {out.strip()[-600:]}")
    else:
        q = set(queued)
        outside = [s for s, _ in sel if s not in q or s in holds]
        if outside:
            fails.append(f"rank.py selected topics outside the publish queue: "
                         f"{outside}")
        if any(src == "mined-demand" for _, src in sel):
            fails.append("rank.py still selects mined-demand topics")
        if not batch_queue.unwritten_entries() and sel:
            fails.append(f"the queue is fully written, yet rank.py selected "
                         f"{sel}")
    if not batch_queue.unwritten_entries():
        if "[PUBLISH_QUEUE_FULLY_WRITTEN]" not in out:
            fails.append("a fully written queue did not name "
                         f"PUBLISH_QUEUE_FULLY_WRITTEN on Sunday: "
                         f"{out.strip()[-600:]}")
        if "RC 0" not in r.stdout:
            fails.append("Sunday with a fully written queue did not exit 0: "
                         f"{r.stdout.strip()[-200:]}")

    # --------------------------- 2b. Sunday, a queue row with no script
    #
    # Isolated from real production depth in BOTH directions rank.py can be
    # starved from: rank.py fills weekly slots FIRST from ledger.inventory()
    # (already-authored, unpublished scripts), THEN from
    # batch_queue.unwritten_entries() (best-first over the WHOLE real
    # backlog). A real mon-draft/sun-rank run against this same repo grows
    # both on any given day - inventory competing for the same `per_week`
    # slots, and a deeper real backlog simply outranking this fixture within
    # unwritten_entries() - either one silently starves the fixture's slot.
    # Neither is a regression; it is live state this case must not depend on.
    # Zeroing both isolates the ONE thing this case actually tests: that an
    # unwritten publish-queue row is selected for authoring.
    examined += 1
    r = run("""
import rank, ledger
ledger.inventory = lambda: []
fixture = {"slug": "zz-fixture-unwritten-topic", "query":
           "why is the fixture topic unwritten", "_domain_file":
           "publish_order.json"}
batch_queue.unwritten_entries = lambda: [fixture]
rank.OUT = TMP / "next_topics.json"
rank.ROOT = TMP   # only used to print OUT relative to it
try:
    rank.main()
except SystemExit as e:
    rc = e.code
doc = json.loads(rank.OUT.read_text())
print("SELECTED", json.dumps([[s["slug"], s["source"], s["needs_authoring"]]
                              for s in doc["selected"]]))
""", tmp / "sun2")
    out = r.stdout + r.stderr
    sel_line = next((l for l in r.stdout.splitlines()
                     if l.startswith("SELECTED ")), "SELECTED []")
    sel = json.loads(sel_line[len("SELECTED "):])
    if ["zz-fixture-unwritten-topic", "publish-queue", True] not in sel:
        fails.append(f"an unwritten publish-queue row was not selected for "
                     f"authoring: {sel} {out.strip()[-400:]}")
    if "[PUBLISH_QUEUE_FULLY_WRITTEN]" in out:
        fails.append("PUBLISH_QUEUE_FULLY_WRITTEN fired while the queue had an "
                     "unwritten row")

    # ------------------------------ 3. Monday, that week's stale next_topics
    #
    # A FROZEN FIXTURE, NOT loop/next_topics.json ITSELF. The first version of
    # this case read the live file directly - it happened to be exactly the
    # four 2026-09-21 mined topics on the day this test was written, and nothing
    # kept it that way. The very next real Sunday-rank run (scheduled weekly,
    # and confirmed 2026-09-25 to also fire on a manual workflow_dispatch)
    # legitimately replaces "selected" with that week's real choices - which is
    # the correct, intended behaviour of loop/rank.py, not a regression. A test
    # that reads live, weekly-mutating state as though it were fixed evidence
    # breaks itself on a schedule it does not control. This is the exact
    # content research/proposed at week 2026-W38 (git show 55e671d), the real
    # incident this whole file exists to pin - captured once, verbatim, so the
    # case it tests can never again depend on what real Sunday last wrote.
    examined += 1
    STALE_NEXT_TOPICS = json.dumps({
        "week": "2026-W38",
        "selected": [
            {"slug": "how-do-scientists-know-so-much",
             "question": "how do scientists know so much",
             "script": "loop/drafts/how-do-scientists-know-so-much.md",
             "source": "mined-demand", "needs_authoring": True,
             "pov_id": "pov-058",
             "pov_line": "'Scientists say' is almost meaningless on its own. "
                         "Which scientists? How many? Was it one paper? Was "
                         "it replicated?"},
            {"slug": "how-do-scientists-know-how-old-something-is",
             "question": "how do scientists know how old something is",
             "script": "loop/drafts/how-do-scientists-know-how-old-something-is.md",
             "source": "mined-demand", "needs_authoring": True,
             "pov_id": "pov-059",
             "pov_line": "I'm not anti-science. I'm against using science "
                         "as a magic authority word that means nobody has "
                         "to show their work."},
            {"slug": "why-deep-sea-creatures",
             "question": "why deep sea creatures",
             "script": "loop/drafts/why-deep-sea-creatures.md",
             "source": "mined-demand", "needs_authoring": True,
             "pov_id": "pov-001",
             "pov_line": "When I picture the deep ocean I don't see blue "
                         "water or fish. I see black. A massive amount of "
                         "black space where you can't tell what's beside "
                         "you or beneath you."},
            {"slug": "how-do-scientists-know-about-other-galaxies",
             "question": "how do scientists know about other galaxies",
             "script": "loop/drafts/how-do-scientists-know-about-other-galaxies.md",
             "source": "mined-demand", "needs_authoring": True,
             "pov_id": "pov-060",
             "pov_line": "Science is a process. It is not a person behind "
                         "a curtain handing down permanent answers."},
        ],
    })
    stale_sel = [t["slug"] for t in json.loads(STALE_NEXT_TOPICS)["selected"]]
    if sorted(stale_sel) != sorted(HELD):
        fails.append(f"the frozen stale fixture does not match the four "
                     f"held slugs: {sorted(stale_sel)}")
    r = run("""
import draft, author, common
# Isolated from real backlog depth: with all 4 selected slugs refused (held),
# draft.py checks batch_queue.unwritten_entries() to tell "queue genuinely
# fully written" (PUBLISH_QUEUE_FULLY_WRITTEN, green) apart from "topics
# exist unauthored but next_topics.json picked none of them" (NO_SCRIPTS,
# needs_human) - see loop/draft.py's own selected-empty branch. This case
# means to prove the FIRST, exactly the state the real repo was in when the
# 2026-09-21 incident happened; a real backlog grown since (mon-draft/
# sun-rank dispatches) must not flip this case into testing the second.
batch_queue.unwritten_entries = lambda: []
draft.TOPICS = TMP / "next_topics.json"
draft.TOPICS.write_text(%r)
draft.QUEUE = TMP / "render_queue.json"
CALLED = []
def _no(*a, **k):
    CALLED.append(a[1] if len(a) > 1 else a)
    raise AssertionError("author.draft called for a refused topic")
author.draft = _no
draft.brief_for = lambda t, w: (_ for _ in ()).throw(
    AssertionError("brief written for a refused topic"))
try:
    draft.main()
except SystemExit as e:
    rc = e.code
print("AUTHORED", CALLED)
print("QUEUE_WRITTEN", draft.QUEUE.exists())
""" % STALE_NEXT_TOPICS, tmp / "mon")
    out = r.stdout + r.stderr
    for s in stale_sel:
        if f"REFUSE {s}:" not in out:
            fails.append(f"Monday did not refuse {s} by name")
    if "AUTHORED []" not in r.stdout:
        fails.append(f"Monday called the author for a topic outside the "
                     f"publish queue: {out.strip()[-400:]}")
    if "QUEUE_WRITTEN False" not in r.stdout:
        fails.append("Monday wrote loop/render_queue.json with nothing in the "
                     "publish queue to hand off")
    if "[PUBLISH_QUEUE_FULLY_WRITTEN]" not in out or "RC 0" not in r.stdout:
        fails.append("Monday with nothing it may write did not take the named, "
                     f"green PUBLISH_QUEUE_FULLY_WRITTEN: {out.strip()[-600:]}")
    for s in HELD:
        if s in stale_sel and s not in out.split("PUBLISH_QUEUE_FULLY_WRITTEN")[-1]:
            fails.append(f"the Monday stop does not name held script {s}")

# ------------------------------------------------ 4. the upload lane's verdict
examined += 1
done = {r["slug"] for r in ledger.load()["published"]}
rows = [{"slug": s, "status": "queued"} for s in HELD]
ok_rw = {"level": "ok", "weeks_remaining": 6.0, "message": "6.0 weeks"}
# Simulate "every queued episode is uploaded" as production would actually
# reach that state - the real ledger plus every queued slug that is not
# itself a held name. NOT `done | set(queued)` outright: a held slug can
# coincidentally collide with a queue candidate's auto-generated slug (real,
# confirmed 2026-09-25 - see cloud_upload.py's own comment on why-deep-
# sea-creatures) while never having a real published episode. Unioning the
# full raw `queued` in would mark that held-and-coincidentally-queued slug
# "uploaded" by name alone, which production's real ledger read never does.
simulated_done = done | (set(queued) - set(holds))
why = CU.diagnose_empty_shelf(queued, simulated_done, set(), rows,
                              promotion_held=holds, runway=ok_rw)
if why["code"] != "SCRIPTS_AWAITING_PROMOTION":
    fails.append(f"today's held state is {why['code']}, not "
                 f"SCRIPTS_AWAITING_PROMOTION")
if sorted(why["held_items"] or []) != sorted(HELD):
    fails.append(f"the hold does not name exactly the four: {why['held_items']}")
d, _ = common.disposition(CU.LANE, why["code"], why["detail"], 1,
                          held_items=why["held_items"], unblock=why["unblock"])
if d != "self_resolving":
    fails.append(f"SCRIPTS_AWAITING_PROMOTION is {d} on its first run, not the "
                 f"green self_resolving - since 2026-09-25 the Saturday gate "
                 f"decides every hold (loop/score.py dispose_promotion_holds), "
                 f"so this state clears on its own and must neither page her "
                 f"nor wait on her")
examined += 1
why = CU.diagnose_empty_shelf(queued, simulated_done, set(),
                              rows + [{"slug": "a-new-stray", "status": "queued"}],
                              promotion_held=holds, runway=ok_rw)
if why["code"] != "AUTHORED_NOT_QUEUED" or why["held_items"] != ["a-new-stray"]:
    fails.append(f"a NEW script outside both the queue and the hold register "
                 f"did not page as AUTHORED_NOT_QUEUED naming only it: "
                 f"{why['code']} {why['held_items']}")

if examined == 0:
    fails.append("examined ZERO items - this test cannot reach what it governs")
print(f"inspected {examined} item(s): {len(queued)} queued slug(s), "
      f"{len(HELD)} held, Sunday x2, Monday x1, upload x2")
for f in fails:
    print(f"  ✗ {f}")
if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print("all green - the Monday lane writes only publish-queue topics, and the "
      "held scripts are a named green stop")
