"""The topic miner's ladder, and its zero-candidate case, on a FIXTURE catalogue.

WHY THIS FILE (2026-10-12). test_topic_selection_refuses_near_duplicates.py
section 7 pinned the LIVE deep-sea catalogue three times ("clears the floor",
"at least one candidate", then "any shortfall walked every rung"), and the
loop consumed each pin by making episodes. The miner's behaviour is tested
here on a catalogue this file owns, so it can neither be consumed nor pass by
luck:

  1. A healthy fixture domain: rephrasings of an episode already made are
     refused, a distinct question survives, a question only the DEDICATED seed
     vocabulary admits is added by the dedicated rung (its count goes up), and
     under the floor every read-only rung logs its count and the network rung
     says it was skipped.
  2. A fixture domain whose every mined question is already made yields ZERO
     candidates, and the miner NAMES it: `--no-network` exits NAMED_STOP (3)
     printing "NAMED STOP DOMAIN_QUEUE_THIN ... has 0", writes no queue file,
     and the stop line is the shape loop/score.py parses. Before this fix the
     zero case raised a bare FATAL that score.py filed as NEW_DOMAIN_UNSCORED
     ("a code defect") - the live deep-sea state on 2026-10-12.
  3. `--candidates-only --no-network` on the same fixture prints the stop too.

No network (the fresh-mine rung is never reached). Writes only to a temp dir.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "research"))
os.environ.setdefault("LOOP_DRY_RUN", "1")

import batch_queue                                         # noqa: E402
import ledger                                              # noqa: E402
import publish_order_domain as pod                         # noqa: E402
import topic_identity as T                                 # noqa: E402

fails: list[str] = []
examined = 0
DOM = "deep-sea-ocean-science"
MADE = [("08-what-creatures-live-in-the-deep-sea",
         "what creatures live in the deep sea"),
        ("10-what-is-the-deepest-part-of-the-ocean",
         "what is the deepest part of the ocean")]
REPEATS = ["what lives in the depths of the ocean", "what lives in the deep sea",
           "what lives in the sea", "how deep is the mariana trench",
           "how deep is the ocean"]
DISTINCT = "what lives in mariana trench"
DEDICATED_ONLY = "how hot is a hydrothermal vent"
# Autocomplete collisions that share no seed word: refused, and they keep a
# seed word like "mariana" under GENERIC_DF in a corpus this small, as it is
# in the real broad mine.
OFF_DOMAIN = ["how do volcanoes form", "why is the sky blue",
              "how do magnets work", "what is a black hole",
              "how do bees make honey"]


def rows(qs: list[str]) -> list[dict]:
    return [{"query": q, "question": True, "noise": False, "excluded": False,
             "probe_hits": 100 - i} for i, q in enumerate(qs)]


def fixture(broad_qs: list[str], cache_qs: list[str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="miner-fixture-"))
    (d / "broad_mined.json").write_text(json.dumps({"domains": {DOM: {
        "queries": rows(broad_qs),
        "provenance": {"seeds": ["deep sea", "ocean", "mariana trench"]}}}}))
    (d / pod.DEEP_MINE_OVERRIDE[DOM]).write_text(
        json.dumps({"queries": rows(cache_qs)}))
    (d / pod.DEDICATED_SEEDS[DOM]).write_text(
        json.dumps({"seeds": ["hydrothermal vent", "whale fall"]}))
    return d


@contextlib.contextmanager
def catalogue(d: Path):
    saved = (pod.HERE, pod.BROAD, pod.made_question_keys, ledger.load)
    pod.HERE, pod.BROAD = str(d), str(d / "broad_mined.json")
    pod.made_question_keys = lambda: [(q, T.question_key(q)) for _, q in MADE]
    ledger.load = lambda: {"published": [{"slug": s, "question": q}
                                         for s, q in MADE],
                           "queued": [], "updated": None}
    try:
        yield
    finally:
        pod.HERE, pod.BROAD, pod.made_question_keys, ledger.load = saved


def run_main(argv: list[str]) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["publish_order_domain.py", *argv]
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pod.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else f"SystemExit({e.code!r})"
    finally:
        sys.argv = saved
    return code, out.getvalue() + err.getvalue()


floor = batch_queue.MIN_UNWRITTEN_TOPICS
READ_ONLY_RUNGS = ("broad mine, broad seeds", "deep-mine cache, broad seeds",
                   "broad mine, dedicated seeds",
                   "deep-mine cache, dedicated seeds")

# ------------------------------------------------------- 1. healthy fixture
d = fixture(REPEATS + [DISTINCT, DEDICATED_ONLY] + OFF_DOMAIN,
            ["what lives in the deep", DISTINCT])
log: list = []
with catalogue(d), contextlib.redirect_stdout(io.StringIO()):
    cands, killed = pod.candidates(DOM, network=False, log=log)
by_rung = {ln.split(":")[0]: ln for ln in log}
examined += 1
if not cands:
    fails.append(f"1: a fixture domain with distinct questions yielded ZERO "
                 f"candidates: {log}")
for q in REPEATS + ["what lives in the deep"]:
    examined += 1
    if q in cands:
        fails.append(f"1: {q!r} repeats an episode already made, admitted")
for q in OFF_DOMAIN:
    examined += 1
    if q in cands:
        fails.append(f"1: {q!r} shares no seed word, admitted")
examined += 1
if DISTINCT not in cands:
    fails.append(f"1: the distinct question {DISTINCT!r} was refused: {cands}")
examined += 1
if DEDICATED_ONLY not in cands:
    fails.append(f"1: {DEDICATED_ONLY!r}, admitted only by the dedicated seed "
                 f"vocabulary, is missing: {cands} {log}")
line = by_rung.get("broad mine, dedicated seeds", "")
examined += 1
try:
    a, b = (int(x) for x in line.split(": ")[1].split(" candidate")[0]
            .split(" -> "))
    if b <= a:
        fails.append(f"1: the dedicated-seed rung added nothing: {line!r}")
except (IndexError, ValueError):
    fails.append(f"1: the dedicated-seed rung did not log its count: {log}")
for q in cands:
    examined += 1
    if T.first_same(T.question_key(q), [(x, T.question_key(x))
                                        for _, x in MADE]):
        fails.append(f"1: candidate {q!r} repeats an episode already made")
    if T.is_vague(T.question_key(q)):
        fails.append(f"1: candidate {q!r} names no subject")
if len(cands) < floor:
    for rung in READ_ONLY_RUNGS:
        examined += 1
        if rung not in by_rung:
            fails.append(f"1: under the floor, yet rung {rung!r} never ran: "
                         f"{log}")
    examined += 1
    if "skipped (read-only run)" not in by_rung.get("fresh autocomplete mine",
                                                    ""):
        fails.append(f"1: the network rung did not say it was skipped: {log}")
else:
    fails.append(f"1: the fixture cleared the floor of {floor}; it must sit "
                 f"under it to exercise the ladder")

# ------------------------------------------------------- 2. zero candidates
d0 = fixture(REPEATS, ["what lives in the deep", "how deep is challenger deep"])
log0: list = []
with catalogue(d0), contextlib.redirect_stdout(io.StringIO()):
    cands0, _ = pod.candidates(DOM, network=False, log=log0)
examined += 1
if cands0:
    fails.append(f"2: a domain whose every question is made yielded "
                 f"{cands0}; the fixture is wrong, not the code")
with catalogue(d0):
    code, out = run_main(["--domain", DOM, "--no-network"])
examined += 1
if code != pod.NAMED_STOP:
    fails.append(f"2: zero candidates exited {code!r}, not NAMED_STOP "
                 f"({pod.NAMED_STOP}): {out.strip()[-300:]}")
stop = next((ln for ln in out.splitlines()
             if "NAMED STOP DOMAIN_QUEUE_THIN" in ln), "")
examined += 1
if not stop or f"{DOM} has 0 " not in stop:
    fails.append(f"2: zero candidates did not name DOMAIN_QUEUE_THIN with the "
                 f"domain and 0: {out.strip()[-300:]}")
elif not stop.split(":", 1)[1].strip():
    fails.append(f"2: the stop line has no message for loop/score.py: {stop!r}")
examined += 1
if "FATAL" in out:
    fails.append(f"2: zero candidates still raised a bare FATAL: {out[-200:]}")
examined += 1
if Path(pod.out_path(DOM)).name in os.listdir(d0) or \
        any(p.name.startswith("publish_order") for p in d0.iterdir()):
    fails.append("2: zero candidates wrote a queue file - RULE 0, an empty "
                 "queue must never be written")

# ------------------------------------------- 3. the read-only look names it
with catalogue(d0):
    code, out = run_main(["--domain", DOM, "--candidates-only", "--no-network"])
examined += 1
if "NAMED STOP DOMAIN_QUEUE_THIN" not in out or f"{DOM} has 0 " not in out:
    fails.append(f"3: --candidates-only on zero candidates did not print the "
                 f"thin stop: {out.strip()[-300:]}")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} item(s), {len(fails)} failure(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
