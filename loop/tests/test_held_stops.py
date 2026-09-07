"""A halt only the owner can clear must page her ONCE — and never go silent.

THE DEFECT THIS GUARDS. On 2026-09-07 the 09:00 upload lane took `NAMED STOP
[CAPTIONS_NOT_READY]` because two episodes had no `captions/<slug>.srt`. That
refusal is correct: the `.srt` is derived from narration audio that exists only
on the owner's Mac, so no cloud run can ever produce one, and uploading would
schedule a video the repo can never caption. It exited 3, went red and opened
an issue — also correct, the first time.

It would then have done exactly the same thing every morning, on an unchanged
fact, in an issue that was already open. That is the same lesson as run
33521586490 (a daily lane paging daily for a daily quota) with a different
cause: not "nobody needs to act" but "the person who must act has already been
told". `loop/held.py` is the fix and this is its guard.

Four sections, each asserting BEHAVIOUR and each with the broken state
restored so the failure is shown to return:

  A. The contract, driven through a REAL `Stage`. First report exits 3.
     Reported-and-unchanged exits 0 with a HELD STOP banner naming the items,
     the date and the issue. GROWN, ISSUE CLOSED, PAST THE REMINDER, NO
     ITEMS, NO UNBLOCK and AFTER A GOOD RUN all exit 3 again.

  B. It is a CLASS, not an exemption. Two stop codes with identical shape are
     treated identically — one of them named nowhere in the policy — and the
     decision path contains no stop code at all. This is the section that
     fails if someone "fixes" the next lane by adding its code to a list, the
     way V5, then V9-V15, then V13-V15, then V32 were each fixed for their own
     names and left the next one to hit the same wall.

  C. `bin/loop-stage.sh` for real, against a scratch repo and a recording
     `gh`: the `loop-stop` label is created, the issue number is written back
     into the hold, and the SECOND run of the same stop is green and posts
     NOTHING.

  D. V16 and V17 lean on a hold only when it has really been reported, and
     both still hard-fail when they examine zero videos.

Hard-fails if any section examines zero cases.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
PY = sys.executable
sys.path.insert(0, LOOP)

import held                                                # noqa: E402

# A real stage taking a real stop, driven by env vars. Not a mock of Stage:
# the point is to watch the actual context manager choose an actual exit code.
HARNESS = r'''
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "loop"))
from common import Stage
items = json.loads(os.environ.get("ITEMS") or "[]")
unblock = os.environ.get("UNBLOCK", "")
code = os.environ.get("CODE", "GUARD_HOLD")
with Stage("guard-stage", None, zero_work_hint="nothing to read") as st:
    if os.environ.get("DO_WORK"):
        st.work("did one real thing")
    else:
        st.named_stop(code, "a halt only a human can clear",
                      detail={"items": items}, unblock=unblock,
                      held_items=items)
'''

# `gh`, answering whatever the case wants. loop/held.py asks it whether the
# issue tracking a hold is still open; a real network call would make this
# guard slow, flaky and unable to exercise the CLOSED branch at all.
FAKE_GH = r'''#!/bin/sh
if [ -n "${GH_CALLS:-}" ]; then echo "$@" >> "$GH_CALLS"; fi
case "$1 $2" in
  "issue view") echo "${GH_ISSUE_STATE:-OPEN}"; exit 0 ;;
  "label list")  cat "${GH_LABELS:-/dev/null}"; exit 0 ;;
  "issue list")  exit 0 ;;
  "issue create") echo "https://github.com/seq23/how-we-know/issues/${GH_NEW_ISSUE:-777}"; exit 0 ;;
esac
exit 0
'''


def _fakebin(td):
    binf = os.path.join(td, "fakebin")
    os.makedirs(binf, exist_ok=True)
    gh = os.path.join(binf, "gh")
    with open(gh, "w") as fh:
        fh.write(FAKE_GH)
    os.chmod(gh, 0o755)
    return binf


def _run(harness, stops, env_extra, binf):
    env = dict(os.environ, REPO=ROOT, LOOP_STOPS_DIR=stops,
               PATH=binf + os.pathsep + os.environ["PATH"], **env_extra)
    env.pop("DO_WORK", None)
    for k, v in env_extra.items():
        env[k] = v
    r = subprocess.run([PY, harness], capture_output=True, text=True,
                       env=env, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def _ledger(stops):
    p = held.ledger_path(stops)
    return json.loads(p.read_text()) if os.path.exists(p) else {}


def _code_only(path: str) -> str:
    """The file with every comment and string literal removed.

    The whole point of section B1 is "no stop code in the DECISION". held.py
    talks about CAPTIONS_NOT_READY at length in its docstring, because that is
    the incident it was written for, and prose is not behaviour. Tokenising
    keeps the assertion about what the code does.
    """
    import tokenize                                        # noqa: PLC0415
    out = []
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    return " ".join(out)


# ----------------------------------------------------------------- section A

def a_the_contract():
    """First loud, then held, and loud again for every kind of change."""
    fails, examined = [], 0
    ITEMS = json.dumps(["how-is-a-silicon-wafer-made",
                        "what-is-a-semiconductor-made-of"])
    UNBLOCK = "python visuals/captions.py <slug> on the Mac, then commit."

    with tempfile.TemporaryDirectory() as td:
        harness = os.path.join(td, "harness.py")
        with open(harness, "w") as fh:
            fh.write(HARNESS)
        binf = _fakebin(td)
        stops = os.path.join(td, "stops")
        os.makedirs(stops)
        base = {"ITEMS": ITEMS, "UNBLOCK": UNBLOCK, "CODE": "GUARD_HOLD"}

        # 1. THE FIRST REPORT IS ALWAYS LOUD.
        examined += 1
        rc, out = _run(harness, stops, base, binf)
        if rc != 3:
            fails.append(f"the FIRST report of a hold exited {rc}, expected 3 "
                         f"— a problem nobody has been told about must page"
                         f"\n{out[-500:]}")
        if "NAMED STOP" not in out:
            fails.append("the first report printed no NAMED STOP banner")

        # 2. REPORTED, BUT WITH NO ISSUE RECORDED. A hold that cannot name
        #    where it is tracked must not claim it is tracked.
        examined += 1
        rc, out = _run(harness, stops, base, binf)
        if rc != 3:
            fails.append(f"a hold with no issue number recorded exited {rc}, "
                         f"expected 3 — it would have gone green while "
                         f"pointing the owner at nothing\n{out[-500:]}")

        # 3. THE ISSUE ARRIVES -> HELD. This is the whole point.
        examined += 1
        if not held.record_issue(stops, "guard-stage", "GUARD_HOLD", 4242):
            fails.append("held.record_issue() found no hold to attach #4242 "
                         "to, so bin/loop-stage.sh could never attach one "
                         "either")
        rc, out = _run(harness, stops, base, binf)
        if rc != 0:
            fails.append(f"an already-reported, unchanged hold exited {rc}, "
                         f"expected 0 — this is the daily red mail the whole "
                         f"mechanism exists to stop\n{out[-800:]}")
        # ...and green must never be silent (Rule 0).
        examined += 1
        for must in ("HELD STOP", "HELD SINCE", "#4242",
                     "how-is-a-silicon-wafer-made",
                     "what-is-a-semiconductor-made-of"):
            if must not in out:
                fails.append(f"a HELD run exited 0 without printing {must!r}. "
                             f"A green run that does not say what is still "
                             f"broken is a silent skip wearing a label.")
        if "NOT resolved" not in out:
            fails.append("the HELD banner never says the stop is NOT "
                         "resolved, so a reader can mistake it for a fix")

        # 4. GROWTH IS NEW NEWS.
        examined += 1
        grown = dict(base, ITEMS=json.dumps(json.loads(ITEMS)
                                            + ["how-strong-is-titanium"]))
        rc, out = _run(harness, stops, grown, binf)
        if rc != 3:
            fails.append(f"a hold that GREW by an episode exited {rc}, "
                         f"expected 3 — a third broken episode is not the "
                         f"same news as two\n{out[-500:]}")
        if "how-strong-is-titanium" not in out:
            fails.append("the re-report did not name the item that was new")

        # 5. SHRINKING IS NOT. Two of the three fixed, one left: still held,
        #    because nobody needs telling that a problem got smaller.
        examined += 1
        held.record_issue(stops, "guard-stage", "GUARD_HOLD", 4242)
        rc, out = _run(harness, stops,
                       dict(base, ITEMS=json.dumps(["how-strong-is-titanium"])),
                       binf)
        if rc != 0:
            fails.append(f"a hold that SHRANK exited {rc}, expected 0 — "
                         f"progress is not a new alarm\n{out[-500:]}")

        # 6. ...but the shrunk set is what is now on record, so growing BACK
        #    to something already reported once still pages.
        examined += 1
        rc, out = _run(harness, stops, base, binf)
        if rc != 3:
            fails.append(f"a hold that grew back to a previously-reported "
                         f"item exited {rc}, expected 3 — the ledger kept a "
                         f"stale, larger item set and would stay quiet on a "
                         f"regression\n{out[-500:]}")

        # 7. THE ISSUE IS CLOSED -> loud. Closing it is the owner saying
        #    "handled"; the condition says otherwise.
        examined += 1
        held.record_issue(stops, "guard-stage", "GUARD_HOLD", 4242)
        rc, _ = _run(harness, stops, base, binf)            # settle to held
        rc, out = _run(harness, stops, dict(base, GH_ISSUE_STATE="CLOSED"),
                       binf)
        if rc != 3:
            fails.append(f"a hold whose tracking issue was CLOSED exited "
                         f"{rc}, expected 3 — the owner marked it handled and "
                         f"it is not\n{out[-500:]}")

        # 8. THE REMINDER. Silence is bounded even when nothing changes.
        examined += 1
        held.record_issue(stops, "guard-stage", "GUARD_HOLD", 4242)
        rc, _ = _run(harness, stops, base, binf)
        data = _ledger(stops)
        row = data[held.key("guard-stage", "GUARD_HOLD")]
        cap = held.reminder_days(json.load(open(os.path.join(
            LOOP, "stop_policy.json"))), "GUARD_HOLD")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cap + 1)
        row["last_reported_at"] = old.isoformat(timespec="seconds")
        data[held.key("guard-stage", "GUARD_HOLD")] = row
        with open(held.ledger_path(stops), "w") as fh:
            json.dump(data, fh)
        rc, out = _run(harness, stops, base, binf)
        if rc != 3:
            fails.append(f"a hold {cap + 1} days old and unchanged exited "
                         f"{rc}, expected 3 — a hold that can never be heard "
                         f"from again is inert with a friendly banner"
                         f"\n{out[-500:]}")

        # 9. NO ITEMS -> never held. The precondition, proven by removing it.
        examined += 1
        nameless = os.path.join(td, "stops-nameless")
        os.makedirs(nameless)
        for i in (1, 2, 3):
            rc, out = _run(harness, nameless,
                           dict(base, ITEMS="[]", CODE="GUARD_NAMELESS"), binf)
            if rc != 3:
                fails.append(f"run {i} of a stop that names NOTHING exited "
                             f"{rc}, expected 3 — a stop that cannot say what "
                             f"it waits on can never be told apart from a new "
                             f"one, so it must stay loud forever"
                             f"\n{out[-400:]}")

        # 10. NO UNBLOCK -> never held. A held run exits 0, so its unblock
        #     text is the only instruction the owner ever gets.
        examined += 1
        mute = os.path.join(td, "stops-mute")
        os.makedirs(mute)
        for i in (1, 2, 3):
            rc, out = _run(harness, mute,
                           dict(base, UNBLOCK="", CODE="GUARD_MUTE"), binf)
            if rc != 3:
                fails.append(f"run {i} of a stop with no unblock text exited "
                             f"{rc}, expected 3 — held and silent about how "
                             f"to clear it is the worst of both\n{out[-400:]}")

        # 11. A GOOD RUN CLEARS THE HOLD, so a RECURRENCE is loud.
        examined += 1
        held.record_issue(stops, "guard-stage", "GUARD_HOLD", 4242)
        _run(harness, stops, base, binf)                    # settle to held
        _run(harness, stops, dict(base, DO_WORK="1"), binf)  # a real run
        if _ledger(stops).get(held.key("guard-stage", "GUARD_HOLD")):
            fails.append("a stage that did real work left its hold on record, "
                         "so the NEXT occurrence of the same halt would be "
                         "silently held instead of reported")
        rc, out = _run(harness, stops, base, binf)
        if rc != 3:
            fails.append(f"the same halt recurring after a successful run "
                         f"exited {rc}, expected 3\n{out[-400:]}")

    return fails, examined


# ----------------------------------------------------------------- section B

def b_a_class_not_an_exemption():
    """The same shape gets the same answer, whatever the code is called."""
    fails, examined = [], 0

    # B1. No stop CODE may appear anywhere in the decision path. This repo has
    #     shipped "and also exempt <name>" four times in eight days; each one
    #     was correct for its names and useless for the next lane. A literal
    #     code here would be the fifth.
    examined += 1
    decision = _code_only(os.path.join(LOOP, "held.py"))
    codes = set(re.findall(r"\b[A-Z][A-Z0-9]{3,}(?:_[A-Z0-9]+)+\b", decision))
    # This module's own constants and the env vars it reads, not stop codes.
    codes -= {"DEFAULT_REMINDER_DAYS", "GITHUB_REPOSITORY", "LOOP_STOPS_DIR"}
    if codes:
        fails.append(f"loop/held.py mentions stop code(s) {sorted(codes)} in "
                     f"the code that decides whether a stop may be held. That "
                     f"is a per-code exemption, which is the temp fix this "
                     f"repo has now been bitten by four times.")

    # B2. Behaviour, not prose: a code the policy has never heard of is held
    #     on exactly the same terms as the one it does name.
    with tempfile.TemporaryDirectory() as td:
        harness = os.path.join(td, "harness.py")
        with open(harness, "w") as fh:
            fh.write(HARNESS)
        binf = _fakebin(td)
        for code in ("CAPTIONS_NOT_READY",       # named in stop_policy.json
                     "NEVER_HEARD_OF_THIS_ONE"):  # named nowhere at all
            examined += 1
            stops = os.path.join(td, f"stops-{code}")
            os.makedirs(stops)
            env = {"ITEMS": json.dumps(["ep-one"]),
                   "UNBLOCK": "do the thing on the Mac", "CODE": code}
            rc1, _ = _run(harness, stops, env, binf)
            held.record_issue(stops, "guard-stage", code, 99)
            rc2, out2 = _run(harness, stops, env, binf)
            if (rc1, rc2) != (3, 0):
                fails.append(
                    f"[{code}] first/second run exited ({rc1}, {rc2}), "
                    f"expected (3, 0). Two stops with identical shape must "
                    f"get identical treatment — otherwise this is an "
                    f"allowlist by another name.\n{out2[-400:]}")

    # B3. The policy may TUNE a hold, never GRANT or DENY one. The only keys
    #     a code entry is allowed to carry are documentation and a clock.
    examined += 1
    policy = json.load(open(os.path.join(LOOP, "stop_policy.json")))
    allowed = {"reminder_days", "why"}
    for code, rule in ((policy.get("held") or {}).get("codes") or {}).items():
        extra = set(rule) - allowed
        if extra:
            fails.append(f"loop/stop_policy.json held.codes.{code} carries "
                         f"{sorted(extra)}. Only {sorted(allowed)} are "
                         f"allowed: the moment this file can say WHICH codes "
                         f"may be held, it is an exemption list.")

    return fails, examined


# ----------------------------------------------------------------- section C

def c_the_wrapper():
    """bin/loop-stage.sh: label, issue number written back, then green."""
    fails, examined = [], 0
    if not shutil.which("git"):
        fails.append("git is not on PATH, so the wrapper cannot be exercised")
        return fails, examined

    with tempfile.TemporaryDirectory() as td:
        remote = os.path.join(td, "remote.git")
        work = os.path.join(td, "work")
        subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
        os.makedirs(os.path.join(work, "bin"))
        os.makedirs(os.path.join(work, "loop", "state", "stops"))
        os.makedirs(os.path.join(work, "docs"))
        for src in ("bin/loop-stage.sh", "loop/common.py", "loop/held.py",
                    "loop/stop_policy.json"):
            shutil.copy(os.path.join(ROOT, src), os.path.join(work, src))
        os.chmod(os.path.join(work, "bin", "loop-stage.sh"), 0o755)
        with open(os.path.join(work, "loop", "stage.py"), "w") as fh:
            fh.write(HARNESS)
        binf = _fakebin(td)
        labels = os.path.join(td, "labels")
        with open(labels, "w") as fh:
            fh.write("bug\nenhancement\n")     # exactly what the repo had:
            #                                    ten defaults, no loop-stop

        env0 = dict(os.environ,
                    PATH=binf + os.pathsep + os.environ["PATH"],
                    REPO=work, LOOP_PYTHON=PY, GITHUB_TOKEN="fake",
                    GH_LABELS=labels, GH_NEW_ISSUE="4242",
                    ITEMS=json.dumps(["ep-one", "ep-two"]),
                    UNBLOCK="python visuals/captions.py <slug> on the Mac",
                    CODE="GUARD_HOLD",
                    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        env0.pop("LOOP_STOPS_DIR", None)   # the wrapper's real committed path
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "add", "."],
                    ["git", "commit", "-q", "-m", "base"],
                    ["git", "remote", "add", "origin", remote],
                    ["git", "push", "-q", "-u", "origin", "main"]):
            subprocess.run(cmd, cwd=work, check=True, env=env0,
                           capture_output=True)

        def stage(**extra):
            calls = os.path.join(td, f"gh-calls-{len(os.listdir(td))}")
            open(calls, "w").close()
            env = dict(env0, GH_CALLS=calls, **extra)
            r = subprocess.run(["bin/loop-stage.sh", "guard-stage",
                                "loop/stage.py"], cwd=work, env=env,
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr, open(calls).read()

        # 1. FIRST RUN: red, an issue is opened, and the label it needs to
        #    dedupe by is created because the repo did not have it.
        examined += 1
        rc, out, calls = stage()
        if rc != 3:
            fails.append(f"the wrapper exited {rc} on a hold's first report, "
                         f"expected 3\n{out[-600:]}")
        if "label create loop-stop" not in calls:
            fails.append(
                "bin/loop-stage.sh did not create the loop-stop label when it "
                "was absent. CONFIRMED on the real repo 2026-09-07: the label "
                "never existed, so `gh issue list --label loop-stop` matched "
                "nothing and every stop opened a NEW issue (#17 and #20 are "
                "one cloud-upload stop; #26 and #29 one mon-draft stop). "
                "\"Already reported\" is undecidable while that is true.")
        if "issue create" not in calls:
            fails.append("the wrapper opened no issue for a stop that pages")

        # 2. THE NUMBER IS WRITTEN BACK. Without this the next run has no
        #    tracker to name and deliberately pages instead.
        examined += 1
        ledger = os.path.join(work, "loop", "state", "stops", "_held.json")
        if not os.path.exists(ledger):
            fails.append("the wrapper left no _held.json for tomorrow's "
                         "runner — a fresh checkout has no other memory")
        else:
            row = json.load(open(ledger)).get(
                held.key("guard-stage", "GUARD_HOLD")) or {}
            if row.get("issue") != 4242:
                fails.append(f"the wrapper recorded issue {row.get('issue')!r} "
                             f"against the hold, expected 4242 — it opened an "
                             f"issue and then forgot which one")
            r = subprocess.run(["git", "log", "--oneline", "-3"], cwd=work,
                               capture_output=True, text=True, env=env0)
            if "#4242" not in r.stdout:
                fails.append(f"the issue number was never committed, so it "
                             f"exists only on this runner:\n{r.stdout}")

        # 3. SECOND RUN: green, and NOTHING is posted.
        examined += 1
        rc, out, calls = stage()
        if rc != 0:
            fails.append(f"the wrapper exited {rc} on an already-reported, "
                         f"unchanged hold, expected 0 — this is the daily red "
                         f"mail\n{out[-800:]}")
        if "issue create" in calls or "issue comment" in calls:
            fails.append(f"the wrapper posted to the issue tracker on a HELD "
                         f"run: {calls!r}. A second copy of the same news in "
                         f"another channel is the same defect.")
        if "HELD STOP" not in out:
            fails.append("the wrapper swallowed the HELD STOP banner, so the "
                         "green run says nothing about what is still broken")

    return fails, examined


# ----------------------------------------------------------------- section D

def d_validators_lean_only_on_real_reports():
    """V16/V17: a hold covers a video only when it was genuinely reported."""
    fails, examined = [], 0
    import validate                                         # noqa: PLC0415

    real_live = validate._live_videos                       # noqa: SLF001
    real_caps = validate.REACH_CAPTIONS_DIR
    real_cap_state = validate.CAPTIONS_STATE
    real_stops = os.environ.get("LOOP_STOPS_DIR")
    tmp = tempfile.mkdtemp()
    try:
        caps = os.path.join(tmp, "captions")
        os.makedirs(caps)
        validate.REACH_CAPTIONS_DIR = caps          # deliberately EMPTY: the
        #                                             episode has no .srt
        state = os.path.join(tmp, "captions.json")
        with open(state, "w") as fh:
            json.dump({"videos": {}, "blocked": {},
                       "token_has_force_ssl": True}, fh)
        validate.CAPTIONS_STATE = state
        row = {"video_id": "VID1", "slug": "ep-no-srt", "privacy": "public"}
        validate._live_videos = lambda: [row]               # noqa: SLF001

        stops = os.path.join(tmp, "stops")
        os.makedirs(stops)
        os.environ["LOOP_STOPS_DIR"] = stops

        # D1. NEGATIVE PROOF. No hold at all: the missing .srt is a hard
        #     failure, exactly as it was before any of this existed.
        examined += 1
        r = validate.v16_caption_track()
        if r.ok or not any("ep-no-srt" in f for f in r.failures):
            fails.append(f"V16 did not FAIL an episode with no .srt and no "
                         f"hold covering it: {r.status} {r.failures}")

        # D2. A hold with NO ISSUE NUMBER covers nothing. An unreported hold
        #     has escalated nothing, so leaning on it would hide the defect
        #     behind a record no human has ever seen.
        examined += 1
        held.record(stops, {"stage": "cloud-upload", "code": "CAPTIONS_NOT_READY",
                            "items": ["ep-no-srt"], "issue": None,
                            "first_reported_at": "2026-09-07T00:00:00+00:00"})
        r = validate.v16_caption_track()
        if r.ok:
            fails.append("V16 went green on a hold that carries no issue "
                         "number — nobody has been told, so there is nothing "
                         "for it to defer to")

        # D3. A REPORTED hold: green, and loud about it.
        examined += 1
        held.record_issue(stops, "cloud-upload", "CAPTIONS_NOT_READY", 71)
        r = validate.v16_caption_track()
        if not r.ok:
            fails.append(f"V16 still failed an episode already escalated by "
                         f"the upload lane and tracked by an open issue: "
                         f"{r.failures}")
        blob = json.dumps(r.as_dict())
        for must in ("CAPTION_SOURCE_HELD", "ep-no-srt", "#71"):
            if must not in blob:
                fails.append(f"V16 went green without reporting {must!r}. A "
                             f"deferred alarm that says nothing is a skip.")

        # D4. RULE 0. Zero videos examined is a failure, not a pass, in both.
        examined += 1
        validate._live_videos = lambda: []                  # noqa: SLF001
        for fn in (validate.v16_caption_track, validate.v17_localizations):
            res = fn()
            if res.ok or res.examined != 0:
                fails.append(f"{res.name} examined {res.examined} and "
                             f"reported {res.status} on an EMPTY channel — a "
                             f"validator that passes having looked at nothing "
                             f"is not passing")
    finally:
        validate._live_videos = real_live                   # noqa: SLF001
        validate.REACH_CAPTIONS_DIR = real_caps
        validate.CAPTIONS_STATE = real_cap_state
        if real_stops is None:
            os.environ.pop("LOOP_STOPS_DIR", None)
        else:
            os.environ["LOOP_STOPS_DIR"] = real_stops
        shutil.rmtree(tmp, ignore_errors=True)

    return fails, examined


def main() -> int:
    total, allf = 0, []
    for name, fn in (("the held contract", a_the_contract),
                     ("class, not exemption", b_a_class_not_an_exemption),
                     ("the workflow wrapper", c_the_wrapper),
                     ("the reach validators", d_validators_lean_only_on_real_reports)):
        f, n = fn()
        print(f"inspected {n} case(s) — {name}")
        total += n
        allf += f
    if total == 0:
        print("FAIL: this guard examined ZERO cases, so it proved nothing")
        return 1
    if allf:
        print(f"\nFAIL ({len(allf)}):")
        for f in allf:
            print(f"  ✗ {f}")
        return 1
    print("all green — a reported hold is green and loud, and every kind of "
          "change makes it loud and red again")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
