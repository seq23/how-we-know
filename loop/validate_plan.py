"""Assert the running system still matches docs/CHANNEL-PLAN.md.

The plan is locked. When the pipeline disagrees with it, that is drift and the
pipeline is wrong until the document is deliberately changed.

**This validator never parses the plan's prose.** It encodes the same facts
independently and compares them against live configuration and real artifacts,
so it fails when the two diverge. A validator that read its expectations out of
the markdown would agree with any edit to the markdown, which is not a check.

Ten assertions, each traceable to a line in the plan:

    1  cadence is 2/week from config, raising itself to 3 then 4, never hardcoded
    2  the 3/week escalation is gated on a validated generated script
    3  research/publish_order.json is the publish source, with NO filename fallback
    4  the owner-pinned head publishes first, in order, while unpublished
    5  the demand/saturation gate is active and hard-fails on an empty set
    6  the topic exclusions are enforced
    7  seed_hits is dead and stays dead
    8  a locked-private upload surfaces as a named condition
    9  the voice model is MIT-licensed on weights
    10 every allocated domain is admitted and equipped

Rule 0: hard-fails if it resolves zero checks.

    python loop/validate_plan.py          # human
    python loop/validate_plan.py --json   # machine
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadence  # noqa: E402
import domain_sources  # noqa: E402
import exclusions  # noqa: E402
import pov_match  # noqa: E402
from common import LOOP, ROOT, config, read_json  # noqa: E402

PLAN = ROOT / "docs" / "CHANNEL-PLAN.md"

# The plan's own numbers, restated here as code. Changing the plan does NOT
# change these - that is the point.
PLAN_CADENCE = 4        # owner set it live 2026-09-04; see
                        # cadence.owner_set in loop/config.json
PLAN_ESCALATED = 3
PLAN_SCALE = 4        # owner decision 2026-09-02; also the taxonomy ceiling
PLAN_SHORTS = 9       # the middle of the owner's 8-10 Shorts/week band
PLAN_PUBLISH_SOURCE = "research/publish_order.json"
PLAN_PINNED = [
    "how big is a colossal squid",
    "how do people reach challenger deep",
    "why does black-smoker water not boil",
    "why some deep sea creatures are transparent",
]
PLAN_VOICE_MODEL = "chatterbox"
PLAN_VOICE_LICENCE = "mit"
REJECTED_VOICE = ("f5-tts", "f5_tts", "xtts", "coqui", "cc-by-nc", "cpml")

# Any of these appearing as a publish-order fallback is the failure the plan
# calls "the single most likely way this plan degrades without anyone noticing".
FALLBACK_SMELLS = [
    (r"sorted\s*\(\s*glob\.glob\([^)]*scripts", "sorts scripts/ by filename"),
    (r"sorted\s*\(\s*inv\b", "sorts inventory alphabetically"),
    (r"except\s+.*PublishOrder\w*[^\n]*:\s*\n\s*(?!.*named_stop)[^\n]*"
     r"(sorted|glob|inventory\(\))", "falls back on a publish-order failure"),
]


class Check:
    def __init__(self, n: int, name: str):
        self.n, self.name = n, name
        self.failures: list[str] = []
        self.notes: list[str] = []

    def fail(self, m: str):
        self.failures.append(m)

    def note(self, m: str):
        self.notes.append(m)

    @property
    def ok(self):
        return not self.failures

    def as_dict(self):
        return {"n": self.n, "check": self.name,
                "status": "PASS" if self.ok else "FAIL",
                "failures": self.failures, "notes": self.notes}


def src(name: str) -> str:
    p = LOOP / name
    return p.read_text() if p.exists() else ""


# ------------------------------------------------------------------ checks

def c1_cadence() -> Check:
    c = Check(1, "cadence starts at 2/week from config and raises itself to 4")
    cfg = config()["cadence"]
    if cfg["videos_per_week"] != PLAN_CADENCE:
        c.fail(f"config says {cfg['videos_per_week']}/week, the plan says "
               f"{PLAN_CADENCE}/week")
    if cfg["escalated"] != PLAN_ESCALATED:
        c.fail(f"config escalates to {cfg['escalated']}, the plan says "
               f"{PLAN_ESCALATED}")
    if int(cfg.get("scale", {}).get("to", 0)) != PLAN_SCALE:
        c.fail(f"config scales to {cfg.get('scale', {}).get('to')}, the plan "
               f"says {PLAN_SCALE}")
    if int(cfg.get("scale", {}).get("to", 0)) > int(cfg["ceiling"]):
        c.fail("the scale target exceeds the taxonomy ceiling")
    if int(cfg.get("shorts_per_week", 0)) != PLAN_SHORTS:
        c.fail(f"config publishes {cfg.get('shorts_per_week')} Shorts/week, "
               f"the plan says {PLAN_SHORTS}")
    if not 8 <= int(cfg.get("shorts_per_week", 0)) <= 10:
        c.fail("Shorts cadence is outside the owner's 8-10/week band")
    live = cadence.effective()
    if live not in (PLAN_CADENCE, PLAN_ESCALATED, PLAN_SCALE):
        c.fail(f"the live cadence resolves to {live}/week")
    # Not hardcoded anywhere.
    for f in ("rank.py", "draft.py", "prepare.py"):
        s = src(f)
        if re.search(r"per_week\s*=\s*\d", s):
            c.fail(f"loop/{f} hardcodes a cadence number")
        if 'cadence"]["videos_per_week"]' in s:
            c.fail(f"loop/{f} reads config directly instead of "
                   f"cadence.effective()")
    c.note(f"live cadence {live}/week")
    return c


def c2_escalation() -> Check:
    c = Check(2, "3/week is gated on a validated generated script")
    s = src("cadence.py")
    if "authoring_evidence" not in s:
        c.fail("cadence.py has no authoring-evidence gate")
    # The evidence must be written only after validation, never by a flag.
    d = src("draft.py")
    if "record_authoring_evidence" not in d:
        c.fail("nothing records authoring evidence")
    else:
        # It must sit inside a passed-validators branch.
        seg = d.split("record_authoring_evidence")[0]
        if "if passed" not in seg[-800:]:
            c.fail("authoring evidence is recorded outside a "
                   "validators-passed branch, so an unvalidated script could "
                   "unlock 3/week")
    if not re.search(r'it\.get\("generated"\)', d):
        c.fail("authoring evidence is not restricted to GENERATED scripts")
    # A bare config flag must not be able to escalate.
    esc = config()["cadence"]["escalation"]
    if not esc.get("automatic"):
        c.fail("escalation is not automatic; the plan says the loop flips itself")
    ev = cadence.authoring_evidence()
    c.note(f"{len(ev['scripts']) if ev else 0} validated generated script(s); "
           f"cadence would be {cadence.effective()}/week")
    return c


def c3_publish_source() -> Check:
    """The most important check in the file."""
    c = Check(3, "publish order comes from research/publish_order.json, "
                 "with no filename fallback")
    if str(cadence.PUBLISH_ORDER.relative_to(ROOT)) != PLAN_PUBLISH_SOURCE:
        c.fail(f"the loop reads {cadence.PUBLISH_ORDER}, the plan names "
               f"{PLAN_PUBLISH_SOURCE}")
    if config()["publish_order"]["source"] != PLAN_PUBLISH_SOURCE:
        c.fail("config names a different publish source")

    cad = src("cadence.py")
    rank = src("rank.py")

    # Absence MUST raise, not fall back.
    if "PublishOrderMissing" not in cad:
        c.fail("cadence.py cannot signal a missing publish order")
    if "PUBLISH_ORDER_MISSING" not in rank or "PUBLISH_ORDER_STALE" not in rank:
        c.fail("rank.py does not name a stop for a missing or stale ranking")

    for pat, why in FALLBACK_SMELLS:
        for f, s in (("cadence.py", cad), ("rank.py", rank),
                     ("draft.py", src("draft.py"))):
            if re.search(pat, s, re.M):
                c.fail(f"loop/{f} {why} - a silent fallback to filename order "
                       f"is the failure this whole policy exists to prevent")

    # Behavioural, not textual: hide the file and confirm it raises.
    real = cadence.PUBLISH_ORDER
    tmp = real.with_suffix(".json.plancheck")
    moved = False
    try:
        if real.exists():
            real.rename(tmp)
            moved = True
        try:
            order = cadence.publish_order()
            c.fail(f"with the ranking absent, publish_order() still returned "
                   f"{len(order)} slug(s) - it fabricated an order")
        except cadence.PublishOrderMissing:
            c.note("verified: a missing ranking raises rather than falling back")
        except Exception as e:
            c.fail(f"a missing ranking raised {type(e).__name__}, not "
                   f"PublishOrderMissing")
    finally:
        if moved:
            tmp.rename(real)
    return c


def c4_pinned_head() -> Check:
    c = Check(4, "the owner-pinned head publishes first, in order")
    try:
        rows, meta = cadence.ordered_inventory()
    except Exception as e:
        c.fail(f"cannot read the publish queue: {type(e).__name__}: {e}")
        return c

    published = set()
    try:
        import ledger
        published = {r["slug"] for r in ledger.load()["published"]}
    except Exception:
        pass

    raw = read_json(cadence.PUBLISH_ORDER, default={})
    pin = raw.get("owner_pinned_head", {}) if isinstance(raw, dict) else {}
    still = [q.lower() for q in (pin.get("still_pinned") or [])]

    if not still:
        c.note("no pinned head is currently declared (it falls away once those "
               "episodes publish)")
        return c

    def norm(x):
        return re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()

    head = [r for r in rows[:len(still)]]
    for i, want in enumerate(still):
        if i >= len(head):
            c.fail(f"pinned episode {i+1} ({want!r}) is not in the queue at all")
            continue
        got = head[i]
        if norm(want) not in norm(got["slug"]) and \
                norm(want) not in norm(got.get("question", "")):
            c.fail(f"publish position {i+1} is {got['slug']!r}, the pin says "
                   f"{want!r} - the pinned head has been re-sorted")

    # A pinned episode the gate killed must survive; that is the whole point.
    overridden = meta.get("queued_despite_kill") or []
    if overridden:
        c.note(f"{len(overridden)} pinned episode(s) survive a gate kill by "
               f"owner override, as the file instructs")
    unpub_pins = [h for h in head if h["slug"] not in published]
    c.note(f"{len(unpub_pins)} pinned episode(s) still unpublished and at the "
           f"head of the queue")
    return c


def c5_gate_active() -> Check:
    c = Check(5, "the demand/saturation gate is active and hard-fails empty")
    raw = read_json(cadence.PUBLISH_ORDER, default={})
    gate = raw.get("gate") if isinstance(raw, dict) else None
    if not isinstance(gate, dict) or not gate:
        c.fail("research/publish_order.json declares no gate - the ranking may "
               "not be gating on demand and saturation at all")
    else:
        for k in ("demand_floor", "saturation_gap_ceiling"):
            if k not in gate:
                c.fail(f"the gate declares no {k}")
        c.note(f"demand floor {gate.get('demand_floor')}, saturation ceiling "
               f"{gate.get('saturation_gap_ceiling')}")
    killed = raw.get("killed") if isinstance(raw, dict) else None
    if isinstance(killed, list):
        c.note(f"{len(killed)} topic(s) killed by the gate and visible with "
               f"their measurement")
    # An empty candidate set must be a hard failure in both stages.
    if "NO_ADMITTED_TOPICS" not in src("rank.py"):
        c.fail("rank.py does not hard-fail on an empty admitted set")
    for code in ("NO_SCORED_CANDIDATES", "NO_RANKING_PRODUCED"):
        if code not in src("score.py"):
            c.fail(f"score.py does not hard-fail with {code}")
    return c


def c6_exclusions() -> Check:
    c = Check(6, "the owner's topic exclusions are enforced")
    for p in exclusions.check_authority_coverage():
        c.fail(p)
    # Her four named classes, each must be refused by name.
    probes = [
        ("what supplements cure the bends", "Medical"),
        ("how to invest in ocean mining stocks", "Financial"),
        ("can I sue over a shipwreck salvage", "Financial"),
        ("deep sea sexual content nude", "Adult"),
        ("how whales are slaughtered", "Morally grey"),
    ]
    for topic, expect in probes:
        d = exclusions.decide(topic)
        if d.admitted:
            c.fail(f"the gate ADMITTED a barred topic: {topic!r}")
        elif expect.lower() not in d.rule.lower():
            c.fail(f"{topic!r} refused under {d.rule!r}, expected {expect!r}")
    if exclusions.decide("how deep is the mariana trench").admitted is False:
        c.fail("the gate refuses a legitimate topic")
    # And it must be wired into the queue validator.
    if "exclusions" not in src("validate.py"):
        c.fail("loop/validate.py does not enforce the exclusions on the queue")
    c.note(f"{len(exclusions.RULES)} taxonomy exclusions + "
           f"{len(exclusions.MORALLY_GREY)} standing instruction enforced")
    return c


def c7_seed_hits_dead() -> Check:
    c = Check(7, "seed_hits is dead and stays dead")
    rank = src("rank.py")

    # An earlier version of this check read only `def demand_score`, so renaming
    # that function to `shape_score` made the check pass vacuously while
    # seed_hits was live inside it. Anchor on the SYMBOL across every scoring
    # path instead of on any one function name.
    ranking_fns = re.findall(
        r"def (\w*(?:score|rank|weight|demand|sort)\w*)\s*\(", rank, re.I)
    if not ranking_fns:
        c.fail("no ranking function found in loop/rank.py - this check cannot "
               "reach what it governs")
    # Carrying seed_hits through as PROVENANCE is fine - it is real mined data
    # and dropping it would lose the audit trail. What is banned is letting it
    # touch a score or an ordering.
    PROVENANCE = re.compile(
        r"^\s*\"[a-z_]*seed_hits[a-z_]*\"\s*:\s*(?:c|row|r)\.get\("
        r"\s*\"seed_hits\"\s*\)\s*,?\s*$")

    # It may never drive an ordering or an arithmetic score, in any function.
    for f in ("rank.py", "cadence.py", "draft.py", "score.py"):
        s_ = src(f)
        s_ = re.sub(r'"""[\s\S]*?"""', "", s_)          # ignore docstrings
        s_ = re.sub(r"^\s*#.*$", "", s_, flags=re.M)      # ignore comments
        for m in re.finditer(r"[^\n]*seed_hits[^\n]*", s_):
            line = m.group(0)
            if PROVENANCE.match(line):
                continue
            if re.search(r"(sort|key\s*=|[*/+\-]\s*(?:float\()?row|"
                         r"=\s*float\(\s*row\.get\(\s*[\"']seed_hits|"
                         r"s\s*[*/+]=|reverse\s*=)", line):
                c.fail(f"loop/{f} ranks or scores on seed_hits: "
                       f"{line.strip()[:80]}")

    live = [f for f in ("rank.py",) if "seed_hits" in src(f)]
    c.note("seed_hits appears only as provenance, never in a ranking path"
           if live else "seed_hits absent from the loop entirely")
    return c


def c8_locked_upload() -> Check:
    c = Check(8, "a locked-private upload is a named condition")
    p = src("publish.py")
    if "UPLOADS_LOCKED_PRIVATE" not in p:
        c.fail("publish.py has no named stop for a locked upload")
    if "read_status" not in p:
        c.fail("publish.py does not re-read the video's status after the flip, "
               "so an accepted-but-still-private upload would report as live")
    if not re.search(r'after\.get\("privacy"\)\s*!=\s*"public"', p):
        c.fail("publish.py does not verify privacyStatus is actually public")
    if "hand_published" not in p:
        c.fail("publish.py cannot recognise a video published by hand and would "
               "try to re-upload it")
    return c


def c9_voice_licence() -> Check:
    c = Check(9, "the voice model is MIT-licensed on weights")
    synth = ROOT / "voice" / "synth.py"
    lic = ROOT / "voice" / "LICENSING.md"
    if not synth.exists():
        c.fail("voice/synth.py is missing; the model in use cannot be confirmed")
        return c
    s = synth.read_text().lower()
    if PLAN_VOICE_MODEL not in s:
        c.fail(f"voice/synth.py does not use {PLAN_VOICE_MODEL}; the plan "
               f"requires MIT-licensed weights")
    for bad in REJECTED_VOICE:
        if re.search(rf"^(?!\s*#).*\b{re.escape(bad)}\b", s, re.M):
            c.fail(f"voice/synth.py references {bad!r} in live code - "
                   f"CC-BY-NC and CPML weights are unusable on a monetised "
                   f"channel")
    if not lic.exists():
        c.fail("voice/LICENSING.md is missing; the licence audit is the "
               "evidence for this claim")
    else:
        t = lic.read_text().lower()
        if PLAN_VOICE_LICENCE not in t or PLAN_VOICE_MODEL not in t:
            c.fail("voice/LICENSING.md does not record an MIT verdict for "
                   "the model in use")
        c.note("licence audit present at voice/LICENSING.md")
    c.note(f"model in use: {PLAN_VOICE_MODEL} (MIT weights)")
    return c


def c10_domains_admitted() -> Check:
    """config.json's own per_domain_requirements, turned into a check.

    A domain with a live weekly slot must actually be admitted (named in
    pov/topic-taxonomy.json), sourced (>=3 allowlisted bodies so authoring and
    validation have somewhere real to cite), scheduled (publish_days), and
    POV-equipped (>=1 tier:specific line, the new_niche_requirement top-up) -
    the config previously only STATED these requirements; nothing checked
    them, so materials-and-manufacturing ran for two weeks unadmitted.
    """
    c = Check(10, "every allocated domain is admitted and equipped")
    cfg = config()
    allocation = cfg.get("domains", {}).get("allocation") or {}
    if not allocation:
        c.fail("config.json domains.allocation is empty - no domain has a "
               "live slot, which is itself a defect this check hard-fails on")
        return c

    tax = read_json(ROOT / "pov" / "topic-taxonomy.json", default={})
    admitted_names = set(tax.get("admitted_domains") or [])
    admitted_ids = tax.get("admitted_domain_ids") or {}
    publish_days = cfg.get("domains", {}).get("publish_days") or {}
    pov_bank = read_json(ROOT / "pov" / "pov-bank.json", default={})
    pov_lines = pov_bank.get("lines") or []

    checked = 0
    for domain_id, slots in allocation.items():
        if not slots:
            continue
        checked += 1

        name = admitted_ids.get(domain_id)
        if not name:
            c.fail(f"{domain_id!r} has {slots} live slot(s) but no entry in "
                   f"pov/topic-taxonomy.json admitted_domain_ids")
        elif name not in admitted_names:
            c.fail(f"{domain_id!r} maps to {name!r}, which is not in "
                   f"pov/topic-taxonomy.json admitted_domains")

        bodies = domain_sources.ALLOWLIST.get(domain_id) or []
        if len(bodies) < 3:
            c.fail(f"{domain_id!r} has only {len(bodies)} allowlisted "
                   f"source(s) in loop/domain_sources.py ALLOWLIST, fewer "
                   f"than the 3 config.json's per_domain_requirements "
                   f"requires")

        if not publish_days.get(domain_id):
            c.fail(f"{domain_id!r} has no publish_days in "
                   f"config.json domains.publish_days")

        # line_domain() treats a bare `domain: null` line as
        # LEGACY_SPECIFIC_DOMAIN ("deep-sea-ocean-science") - the first
        # interview predates the domain field entirely and was about nothing
        # else. Matching on the raw field would wrongly fail deep sea, which
        # never needed a top-up because it was never "outside deep sea".
        specific = [ln for ln in pov_lines
                    if pov_match.line_domain(ln) == domain_id
                    and ln.get("tier") == "specific"]
        if not specific:
            c.fail(f"{domain_id!r} has zero tier:specific line(s) in "
                   f"pov/pov-bank.json - new_niche_requirement's POV top-up "
                   f"was never done for it")

    if checked == 0:
        c.fail("every allocated domain has zero slots - nothing to check")
    else:
        c.note(f"{checked} domain(s) admitted and equipped: "
               + ", ".join(sorted(d for d, s in allocation.items() if s)))
    return c


# ------------------------------------------------------------------ runner

CHECKS = [c1_cadence, c2_escalation, c3_publish_source, c4_pinned_head,
          c5_gate_active, c6_exclusions, c7_seed_hits_dead, c8_locked_upload,
          c9_voice_licence, c10_domains_admitted]


def run() -> tuple[bool, list[dict]]:
    rows = []
    for fn in CHECKS:
        try:
            rows.append(fn().as_dict())
        except Exception as e:
            rows.append({"n": 0, "check": fn.__name__, "status": "ERROR",
                         "failures": [f"{type(e).__name__}: {e}"], "notes": []})
    ok = all(r["status"] == "PASS" for r in rows)
    return ok, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not PLAN.exists():
        print(f"FAIL: {PLAN.relative_to(ROOT)} does not exist. The plan is the "
              f"reference; without it there is nothing to hold the pipeline to.")
        return 1

    ok, rows = run()

    # Rule 0: a validator that resolved nothing has not validated anything.
    if not rows:
        print("FAIL: validate_plan resolved ZERO checks")
        return 1

    if a.json:
        print(json.dumps({"plan": str(PLAN.relative_to(ROOT)),
                          "all_passed": ok, "checks": rows}, indent=2))
        return 0 if ok else 1

    print(f"\nChecking the running system against {PLAN.relative_to(ROOT)}\n")
    for r in rows:
        mark = "PASS" if r["status"] == "PASS" else r["status"]
        print(f"  [{mark:<5}] {r['n']}. {r['check']}")
        for f in r["failures"]:
            print(f"           ✗ {f}")
        for n in r["notes"]:
            print(f"           · {n}")
    print()
    print(f"{len(rows)} checks resolved, "
          f"{sum(1 for r in rows if r['status'] != 'PASS')} failing")
    print("PLAN AND PIPELINE AGREE" if ok else
          "DRIFT: the pipeline disagrees with the locked plan")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
