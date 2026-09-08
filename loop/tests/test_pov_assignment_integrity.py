"""pov/pov-assignments.json may not say anything the bank disagrees with.

THE DEFECT THIS GUARDS, CONFIRMED. Commit 581feec (2026-09-07) recorded the
owner's three approved MATERIALS lines under pov-102, pov-103 and pov-104 —
ids the bank holds as `tier: transferable` lines about being wrong and about
distrusting complexity, with COMPLETELY DIFFERENT TEXT. Each row was wrong
twice: it claimed `tier: "specific"` where the bank says transferable, and it
carried her real materials words under an id whose bank text is something
else. The second is the one that reached YouTube — the words in the script
traced to NOTHING, which is the channel asserting she said something her bank
does not record under that id.

Every consumer called those episodes traced, because every one of them asked
only whether a row EXISTS:

    select()             honoured the row, unchecked
    untraced_pov()       counted its presence as a trace
    record_assignment()  appended to the file, unchecked
    V32                  counted its presence as a trace

The only thing that noticed was ONE hardcoded end-to-end case in
loop/tests/test_pov_domains.py naming ONE slug:

    pick = P.select("how-strong-is-titanium", ...)
    check("a materials subject selects a materials line", pick["tier"] == "specific")

…and it noticed only incidentally, because `select()` returns the BANK's tier
rather than the row's. The same mistake on any of the other twenty-eight rows
would have passed in silence. Section E therefore puts the mismatch on
episodes that case never looks at and proves this guard still finds it — a
guard that works only because a sibling test happens to name the right slug is
not a guard.

The cross-domain rule (`SPECIFIC_LINE_WRONG_DOMAIN`) is the same hole's other
half: `pov_match.score()` refuses to let a tier:specific line cross domains,
and a hand assignment skips scoring entirely, so nothing enforced that rule on
the one path a human writes by hand.

Five sections, each asserting behaviour, each restoring the broken state:

  A. Every defect the predicate names is really detected, one doctored row at
     a time — and a clean file yields none.
  B. THE JOIN. All four consumers reach the same verdict from the same
     predicate: select() refuses, untraced_pov() refuses, record_assignment()
     will not write it, and V32 stops calling it traced.
  C. V40 over the real file, plus its zero-item hard fail proven against an
     empty input set.
  D. The negative proof at full scale: the three real 581feec rows, verbatim,
     detected AND refused by select().
  E. …and the same class of mismatch caught on episodes test_pov_domains.py's
     hardcoded case never looks at.

Hard-fails if any section examines zero cases.
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import pov_match as P                                       # noqa: E402
import validate as V                                        # noqa: E402

ASSIGNMENTS = os.path.join(ROOT, "pov", "pov-assignments.json")


def rows():
    with open(ASSIGNMENTS, encoding="utf-8") as fh:
        return json.load(fh)["assignments"]


def bank_by_id():
    return {l["id"]: l for l in P.bank()}


def _a_specific_line_from(domain):
    """One tier:specific bank line belonging to `domain`."""
    for l in P.bank():
        if l["tier"] == "specific" and P.line_domain(l) == domain:
            return l
    return None


def _materials_row(rs):
    """A real assignment whose episode is a materials episode."""
    for a in rs:
        if P._domain_of(a["video"]) == "materials-and-manufacturing":   # noqa: SLF001
            return a
    return None


# ----------------------------------------------------------------- section A

def a_each_defect_is_detected():
    fails, examined = [], 0
    rs = rows()
    bank = bank_by_id()

    # A0. The real file is clean, so every failure below is the doctoring and
    #     not a pre-existing mess this guard would report forever.
    examined += 1
    live = P.assignment_defects(rows=rs)
    if live:
        fails.append(f"the committed pov/pov-assignments.json already has "
                     f"defects, so this guard cannot tell its own doctoring "
                     f"apart from them: {live}")

    victim = _materials_row(rs)
    if victim is None:
        fails.append("no materials episode is assigned at all, so the "
                     "cross-domain case cannot be built on a real episode — "
                     "this guard would be testing nothing")
        return fails, examined

    deep = _a_specific_line_from(P.LEGACY_SPECIFIC_DOMAIN)
    if deep is None:
        fails.append("the bank holds no deep-sea tier:specific line, so the "
                     "cross-domain case cannot be built")
        return fails, examined

    CASES = [
        ("POV_ID_NOT_IN_BANK",
         {"pov_id": "pov-999999"},
         "select() silently ignores an unknown id and matches a DIFFERENT "
         "line, so the file names one line and the script carries another"),
        ("TIER_DISAGREES_WITH_BANK",
         {"tier": "transferable" if bank[victim["pov_id"]]["tier"] == "specific"
                  else "specific"},
         "the tier is what decides whether the domain rule applies at all"),
        ("LINE_TEXT_DISAGREES_WITH_BANK",
         {"line": "Words she never said in any interview."},
         "a drifted copy is the channel asserting she said something the "
         "bank does not record"),
        ("SPECIFIC_LINE_WRONG_DOMAIN",
         {"pov_id": deep["id"], "tier": deep["tier"], "line": deep["line"]},
         "a deep-sea tier:specific line on a materials episode, which "
         "score() rates 0.0 and would never choose — the rule a hand "
         "assignment skips by never being scored"),
    ]
    for code, patch, why in CASES:
        examined += 1
        doctored = copy.deepcopy(rs)
        for a in doctored:
            if a["video"] == victim["video"]:
                a.update(patch)
        got = {d["code"] for d in P.assignment_defects(rows=doctored)}
        if code not in got:
            fails.append(f"{code} was NOT detected. {why}. Doctored "
                         f"{victim['video']} with {patch!r}; the predicate "
                         f"reported {sorted(got) or 'nothing at all'}.")

    # Reuse is a property of the FILE, so it needs two rows, not one.
    examined += 1
    doctored = copy.deepcopy(rs)
    if len(doctored) < 2:
        fails.append("fewer than two assignments on file, so reuse cannot be "
                     "constructed")
    else:
        doctored[1]["pov_id"] = doctored[0]["pov_id"]
        doctored[1]["tier"] = doctored[0]["tier"]
        doctored[1]["line"] = doctored[0]["line"]
        got = {d["code"] for d in P.assignment_defects(rows=doctored)}
        if "POV_ID_REUSED" not in got:
            fails.append(f"POV_ID_REUSED was not detected when one line was "
                         f"assigned to two videos, which is the rule "
                         f"pov/pov-assignments.json states in its own header. "
                         f"Got {sorted(got) or 'nothing'}.")

    return fails, examined


# ----------------------------------------------------------------- section B

def b_every_consumer_asks_the_same_question():
    """Four code paths, one predicate. This is what stops them drifting."""
    fails, examined = [], 0
    rs = rows()
    victim = _materials_row(rs)
    deep = _a_specific_line_from(P.LEGACY_SPECIFIC_DOMAIN)
    if victim is None or deep is None:
        fails.append("cannot build the cross-domain case (see section A)")
        return fails, examined

    slug = victim["video"]
    bad = {"video": slug, "pov_id": deep["id"], "tier": deep["tier"],
           "line": deep["line"], "source": "doctored by the guard"}

    real_hand = P.hand_assignments
    real_defective = P.defective_assignments
    try:
        # 1. select() must REFUSE rather than silently match something else.
        examined += 1
        P.hand_assignments = lambda: {slug: bad}
        try:
            got = P.select(slug, "How strong is titanium?")
            fails.append(
                f"select() honoured a hand assignment naming a "
                f"{P.line_domain(deep)} tier:specific line for a "
                f"materials episode and returned {got['pov_id']} "
                f"({got['matched_by']}). That is 581feec, unchanged.")
        except P.NoPovMatch as e:
            if "SPECIFIC_LINE_WRONG_DOMAIN" not in str(e):
                fails.append(f"select() refused, but not by name: {e}")

        # 2. the PRE-UPLOAD gate must refuse it, with the real reason.
        examined += 1
        script = os.path.join(ROOT, "scripts", f"{slug}.md")
        if not os.path.exists(script):
            fails.append(f"scripts/{slug}.md is missing, so the gate cannot "
                         f"be exercised on a real episode")
        else:
            P.defective_assignments = lambda slugs=None: {
                slug: [{"code": "SPECIFIC_LINE_WRONG_DOMAIN", "why": "doctored"}]}
            why = P.untraced_reasons([slug])
            if slug not in why:
                fails.append(
                    "pov_match.untraced_pov() still calls a defective "
                    "assignment a trace, so loop/cloud_upload.py would upload "
                    "the episode and only V32 would notice — after it is on "
                    "YouTube, which is exactly how the first three got there")
            elif "SPECIFIC_LINE_WRONG_DOMAIN" not in why[slug]:
                fails.append(f"the gate refused {slug} without naming the "
                             f"defect: {why[slug]!r}")

        # 3. V32 must stop counting it as traced.
        examined += 1
        r = V.v32_scheduled_pov_is_hers()
        if r.examined == 0:
            fails.append("V32 examined zero episodes, so the join with it "
                         "cannot be tested at all")
        elif r.ok and any(a["video"] == slug for a in rs):
            # The doctored slug is scheduled or aired; if it is still ahead,
            # V32 must now fail it.
            import datetime as dt                            # noqa: PLC0415
            import ledger as led                             # noqa: PLC0415
            ahead = any(row.get("slug") == slug
                        and row.get("scheduled_publish_at")
                        and dt.datetime.fromisoformat(
                            row["scheduled_publish_at"].replace("Z", "+00:00"))
                        > dt.datetime.now(dt.timezone.utc)
                        for row in led.load()["published"])
            if ahead:
                fails.append(
                    f"V32 passed while {slug} is scheduled ahead with a "
                    f"defective assignment — it is still asking only whether "
                    f"a row EXISTS")
    finally:
        P.hand_assignments = real_hand
        P.defective_assignments = real_defective

    # 4. record_assignment() must not WRITE one. The only automatic writer:
    #    a rule enforced on read alone lets the loop manufacture the row every
    #    reader then has to reject.
    examined += 1
    src = open(os.path.join(LOOP, "pov_match.py"), encoding="utf-8").read()
    body = src[src.index("def record_assignment"):]
    body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
    if "assignment_defects" not in body:
        fails.append("pov_match.record_assignment() does not consult "
                     "assignment_defects() before appending, so the loop can "
                     "still write the exact row every consumer rejects")

    return fails, examined


# ----------------------------------------------------------------- section C

def c_v40_over_the_real_file():
    fails, examined = [], 0

    examined += 1
    r = V.v40_pov_assignment_integrity()
    if r.examined == 0:
        fails.append("V40 examined ZERO assignments against the committed "
                     "file — it cannot reach what it governs")
    if not r.ok:
        fails.append(f"V40 fails on the committed file: {r.failures}")

    # THE ZERO-ITEM HARD FAIL, proven against an actual empty input set.
    examined += 1
    real_read = V.read_json
    try:
        V.read_json = lambda path, default=None: {"assignments": []}
        empty = V.v40_pov_assignment_integrity()
        if empty.ok:
            fails.append("V40 PASSED on a file listing zero assignments. A "
                         "validator that examines nothing has not found "
                         "nothing wrong; it has proved nothing.")
        if "examined 0" not in empty.status:
            fails.append(f"V40 reported {empty.status!r} on an empty file "
                         f"rather than saying it examined zero items")
    finally:
        V.read_json = real_read

    # …and it is actually RUN. A validator nothing invokes is inert.
    examined += 1
    src = open(os.path.join(LOOP, "validate.py"), encoding="utf-8").read()
    runner = src[src.index("def run_all("):]
    runner = runner[:runner.index("\ndef ")]
    if "v40_pov_assignment_integrity()" not in runner:
        fails.append("run_all() does not call v40_pov_assignment_integrity — "
                     "defined but never invoked is this repo's named defect")

    return fails, examined


# ----------------------------------------------------------------- section D

# The three rows EXACTLY as commit 581feec wrote them, copied in verbatim
# rather than read from git: 581feec is reachable from no branch, so a fresh
# CI checkout cannot fetch it and a guard that shelled out to `git show` would
# quietly examine nothing on the only machine that matters.
HISTORICAL_581FEEC = [
        {
            "video": "how-does-tempered-glass-shatter",
            "pov_id": "pov-102",
            "tier": "specific",
            "source": "owner-approved 2026-09-07",
            "line": "I almost opened on the moment of impact, because that's the dramatic beat. But impact doesn't decide the fracture pattern — the cooling process already did, weeks earlier. I moved the real event to where it actually happens."
        },
        {
            "video": "how-strong-is-titanium",
            "pov_id": "pov-103",
            "tier": "specific",
            "source": "owner-approved 2026-09-07",
            "line": "I kept trying to land on one number for 'how strong,' because that's what the title promises. There isn't one. Tensile, yield, specific and fatigue strength are four different answers, and I wrote them as four."
        },
        {
            "video": "how-is-damascus-steel-made",
            "pov_id": "pov-104",
            "tier": "specific",
            "source": "owner-approved 2026-09-07",
            "line": "I nearly treated historical and modern Damascus steel as one material made two ways. They're not — they're two different materials separated by a lost century of technique. Conflating them was the actual error to avoid here."
        }
    ]


def d_the_real_581feec_rows():
    """The historical defect, verbatim, must go red and name what is wrong.

    Each row records tier "specific" while the bank holds pov-102/103/104 as
    transferable, AND carries her real materials words under an id whose bank
    text is something else entirely. The second is the one that reached
    YouTube: the words in the script traced to nothing.
    """
    fails, examined = [], 0
    bank = bank_by_id()

    examined += 1
    absent = [a["pov_id"] for a in HISTORICAL_581FEEC
              if a["pov_id"] not in bank]
    if absent:
        fails.append(f"pov-{'/'.join(absent)} are no longer in "
                     f"pov/pov-bank.json, so this negative proof is not "
                     f"exercising the real defect any more — it would pass "
                     f"for the wrong reason")
        return fails, examined

    got = P.assignment_defects(rows=HISTORICAL_581FEEC)
    by_video = {}
    for d in got:
        by_video.setdefault(d["video"], set()).add(d["code"])

    for a in HISTORICAL_581FEEC:
        slug = a["video"]
        examined += 1
        codes = by_video.get(slug, set())
        if "LINE_TEXT_DISAGREES_WITH_BANK" not in codes:
            fails.append(
                f"{slug}: the row carries text that pov/pov-bank.json does "
                f"NOT hold under {a['pov_id']}, and that was not reported. "
                f"This is the words-on-YouTube half of 581feec — the channel "
                f"asserting she said something no interview records under "
                f"that id. Reported: {sorted(codes) or 'nothing at all'}.")
        if "TIER_DISAGREES_WITH_BANK" not in codes:
            fails.append(
                f"{slug}: the row records tier {a['tier']!r} while the bank "
                f"says {bank[a['pov_id']]['tier']!r}, and that was not "
                f"reported. Reported: {sorted(codes) or 'nothing at all'}.")

    # And the whole point: the pipeline must refuse them, not merely notice.
    examined += 1
    real_hand = P.hand_assignments
    try:
        P.hand_assignments = lambda: {a["video"]: a
                                      for a in HISTORICAL_581FEEC}
        slug = "how-strong-is-titanium"
        try:
            got2 = P.select(slug, "How strong is titanium?")
            fails.append(
                f"select() honoured the 581feec row for {slug} and returned "
                f"{got2['pov_id']} via {got2['matched_by']!r} — the defect is "
                f"detected but not refused, which is where it came in")
        except P.NoPovMatch as e:
            if "DISAGREES_WITH_BANK" not in str(e):
                fails.append(f"select() refused but named the wrong cause: {e}")
    finally:
        P.hand_assignments = real_hand

    return fails, examined


# ----------------------------------------------------------------- section E

def e_without_the_hardcoded_case():
    """The sibling test's one hardcoded slug must not be what saves us.

    test_pov_domains.py catches the 581feec mismatch with a single end-to-end
    case naming `how-strong-is-titanium`. That is one slug out of twenty-nine.
    Here the same mismatch is put on a DIFFERENT episode — one that case never
    looks at — and this guard must still find it.
    """
    fails, examined = [], 0
    rs = rows()
    deep = _a_specific_line_from(P.LEGACY_SPECIFIC_DOMAIN)
    hardcoded = "how-strong-is-titanium"

    others = [a for a in rs
              if a["video"] != hardcoded
              and P._domain_of(a["video"]) not in (None,               # noqa: SLF001
                                                   P.LEGACY_SPECIFIC_DOMAIN)]
    examined += 1
    if deep is None or not others:
        fails.append("no non-deep-sea episode other than the one "
                     "test_pov_domains.py hardcodes is assigned, so this "
                     "section cannot prove independence")
        return fails, examined

    for a in others[:3]:
        examined += 1
        doctored = copy.deepcopy(rs)
        for row in doctored:
            if row["video"] == a["video"]:
                row.update({"pov_id": deep["id"], "tier": deep["tier"],
                            "line": deep["line"]})
        got = [d for d in P.assignment_defects(rows=doctored)
               if d["video"] == a["video"]
               and d["code"] == "SPECIFIC_LINE_WRONG_DOMAIN"]
        if not got:
            fails.append(
                f"a deep-sea tier:specific line assigned to {a['video']} "
                f"({P._domain_of(a['video'])}) was not reported. "        # noqa: SLF001
                f"test_pov_domains.py only ever checks {hardcoded!r}, so with "
                f"this missing the mismatch would reach the channel silently "
                f"on every other episode.")
    return fails, examined


def main() -> int:
    total, allf = 0, []
    for name, fn in (("each defect detected", a_each_defect_is_detected),
                     ("the four consumers agree",
                      b_every_consumer_asks_the_same_question),
                     ("V40 and its zero-item guard", c_v40_over_the_real_file),
                     ("the real 581feec rows", d_the_real_581feec_rows),
                     ("independent of the hardcoded case",
                      e_without_the_hardcoded_case)):
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
    print("all green — a hand assignment is authoritative but not exempt, and "
          "all four consumers refuse the same wrong row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
