"""Validators the weekly queue must clear before anything is voiced.

These sit *in front of* the render pipeline. The pipeline already refuses to
draw an unsourced value (`tests/test_directive_truth.py`); these add the checks
that only make sense once a week has been selected:

  V1  directive-truth   the repo's own guard: no invented number or name on screen
  V2  planner           the repo's own planner regression tests
  V3  taxonomy          nothing in the queue touches a hard exclusion
  V4  pov               one bank-verbatim POV per video, no reuse inside 12
  V5  sources-present   no digit-bearing script ships without a real source list
  V6  attribution       every organisation the narration names appears in
                        ## Sources — SOFT: reported, does not halt publishing
  V7  plans             every queued script plans to real beats
  V8  source-urls       every source URL in a GENERATED script actually
                        resolves - a fabricated citation is an LLM's signature
                        failure and looks completely normal to a human skim
  V9  footage-window   every footage cut the assembler would make lies WHOLLY
                        inside one measured `clean_windows` span - a cut that
                        crosses a boundary puts a NOAA card or a DVR overlay on
                        screen
  V10 footage-crop     every clip whose `treatment` is `cropped` carries a crop
                        rect and actually gets it applied - those clips have a
                        permanent OCEAN EXPLORATION corner bug in every frame
  V11 footage-hash     every clip on disk still hashes to the sha256 its rights
                        decision was made about; a mismatch is refused, never
                        rendered
  V12 footage-scope    footage only ever replaces `ambient_drift` and matched
                        `species_image` beats - typography and still plates are
                        untouched
  V13 render-not-clipped  no finished render ends before its own narration does
  V14 shorts-attribution  every Short built from credited material shows that
                        credit, read back off the finished pixels with Vision.
                        The Short crops the master's burned caption band away and
                        the source credit goes with it, so the credit is redrawn
                        from the imagery manifests - this is the guard that it
                        actually reached the screen
  V15 shorts-caption-crop the crop really removed the burned captions: the
                        thrown-away source rows OCR as text, and the Short's
                        picture band fits the cropped master at least twice as
                        well as it fits the whole one
  V20 cadence-schedule  a cadence change cannot disturb a slot already on the
                        calendar. The allocator is re-run against the real
                        ledger and every date it hands out must fall strictly
                        after the last scheduled episode, never collide with
                        one, and never land on a measured-weak day. Also proves
                        both weekday ladders are long enough for the cadence and
                        that the queue-depth guard actually bounds the raise
  V21 no-boilerplate    no narrated sentence (8+ words) is byte-identical
                        across two different scripts — the guard against the
                        "generic template" signal a verbatim repeat produces
  V22 producer-notes-2p narration never talks ABOUT the channel's strategy
                        (monetisation, watch time, the pinned comment, the
                        production queue) in third person; the transparency
                        stays, addressed to the viewer instead
  V23 chapters-yt-compliant  every chapter list loop/upload.py would actually
                        send starts at 0:00, has no gap under 10s and never
                        contains a bare "Title card" entry — the three ways a
                        chapter list gets silently discarded by YouTube
  V24 render-duration-floor  no render outside
                        retention.runtime_floor_grandfathered is under the
                        owner's 10-minute hard floor, checked against the
                        RENDERED file, not the word count that predicts it

V1-V15 and V20-V24 are the RENDER GATE: `run_all(items)`, run by loop/draft.py in front
of the pipeline. V16-V19 and V26 are the REACH group: `run_reach()`, run by
`loop/validate.py --reach`, and they govern what a video looks like on YouTube
after it is published. They are deliberately kept out of the render gate — a
lagging translation lane must never be able to halt drafting and, through the
breaker, publishing.

  V16 caption-track    every live video carries an English caption track, which
                       is the SOURCE for auto-translated subtitles AND
                       auto-dubbed audio ("English subtitles are the default
                       source for auto-translation of subtitles and audio" —
                       YouTube Studio, 2026-09-02). A video may lack one only
                       while the credential is missing youtube.force-ssl, and
                       that exemption expires the moment the scope arrives
  V17 localizations    every live video carries all five localized titles and
                       descriptions (es, pt-BR, hi, id, de)
  V18 default-language snippet.defaultLanguage is set and is exactly `en`
                       everywhere - unset makes localizations impossible and
                       blanks the whole subtitle UI; `en` beside `en-US` is a
                       split nothing else would report
  V19 snippet-merge    no lane sends a PARTIAL snippet to videos.update, which
                       replaces rather than patches and would erase the title,
                       description, tags and categoryId of every live video
  V26 state-readable   every committed loop/state/*.json parses and carries no
                       git conflict marker. Several cloud lanes rebase onto
                       main within the same minute; on 2026-09-03 one left a
                       conflicted quota.json on disk and the next lane in the
                       same job died on it several steps later, with a
                       traceback naming neither the file nor git
  V41 discovery-metadata every allocated domain's tags and hashtags are
                       DERIVED (loop/discovery.py) rather than one fixed
                       list — a materials episode's tags carry none of deep
                       sea's, its description ends with a 1-60 hashtag line
                       ordered subject/domain/channel, and
                       loop/shorts_lane.py carries the same tags plus
                       "shorts". Owner instruction, 2026-09-21

V16 and V17 may report a QUOTA_DEFERRED video as a GREEN NAMED STOP rather
than a failure. That is not a softened assertion: the deferral must be
RECORDED, with the date it was FIRST made, by the lane that made it, and the
excuse expires after DEFER_GRACE_DAYS whether or not anyone is watching. A
video with no track and NO recorded reason stays a hard failure. The
distinction is the whole point — before 2026-09-03 eleven correctly-deferred
videos and one genuinely-forgotten one produced one indistinguishable red, so
the daily mail stopped being read.

Every validator **hard-fails when it examined zero items.** A validator that
passes an empty loop is the defect it is supposed to catch.

Any failure here is a `validator` trip cause for the circuit breaker.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger  # noqa: E402
import held as _held  # noqa: E402
from common import ROOT, config, now, read_json, write_json  # noqa: E402

# Module level so a test can point it at a scratch file. The suite must never
# rewrite committed state (loop/tests/run_all.py checks this after every run).
ATTRIBUTION_GAPS = ROOT / "loop" / "state" / "attribution_gaps.json"
from common import _stops_dir  # noqa: E402
import domain_sources  # noqa: E402
import domains  # noqa: E402
import exclusions  # noqa: E402

PY = sys.executable

# Source-shaped names the narration cites, PER DOMAIN — loop/domain_sources.py
# is now the one allowlist, shared with loop/author.py's prompt so a domain
# cannot be told to cite a body its own validator would not recognise. This
# used to be a single flat ORG_NAMES list here, which meant a materials
# script naming NIST or ASM International was invisible to v6_attribution —
# not a false failure, a false PASS: the guard could not reach what it was
# meant to govern. ORG_NAMES/ALIAS stay as names for backward compatibility
# (deep sea's own list, unchanged) but v6_attribution below looks up each
# item's OWN domain instead of reading these two names directly.
ORG_NAMES = domain_sources.for_domain("deep-sea-ocean-science")
ALIAS = domain_sources.alias_for("deep-sea-ocean-science")


class Result:
    def __init__(self, name: str):
        self.name = name
        self.examined = 0
        self.failures: list[str] = []
        self.notes: list[str] = []
        # NAMED STOPS. A legitimate, self-resolving halt -- "eleven videos are
        # waiting for tomorrow's quota, their .srt files are ready" -- is not a
        # failure and must not be reported as one. Before 2026-09-03 those
        # eleven were `notes`, printed with a dim `·` underneath a red FAIL
        # header caused by a twelfth, unrelated video; the daily mail read as
        # "twelve broken videos" and the lane got tuned out.
        #
        # A stop is GREEN and LOUD: it never affects `ok`, and it is never
        # allowed to hide a real failure -- `ok` still falls over on the first
        # entry in `failures`. That asymmetry is the point. This is a reporting
        # channel, not a severity dial.
        self.stops: list[dict] = []
        # Set only by a validator that legitimately governs nothing this week.
        # Never set it to quiet a validator that SHOULD have found items.
        self.exempt = False

    def fail(self, msg: str):
        self.failures.append(msg)

    def note(self, msg: str):
        self.notes.append(msg)

    def named_stop(self, code: str, msg: str, items: list[str] | None = None):
        """Record a legitimate, named, GREEN halt.

        Rule 0: this is the opposite of a silent skip. A deferral recorded
        here is printed in full, with its code and its count, every run --
        what it does not do is fail the job and page a human about a lane
        that is working exactly as designed.
        """
        self.stops.append({"code": code, "message": msg,
                           "items": sorted(items or [])})

    @property
    def ok(self) -> bool:
        # Zero examined is itself a failure: it means the validator could not
        # reach what it governs. The single exception is a validator that
        # governs generated scripts in a week that generated none.
        if self.exempt and self.examined == 0:
            return not self.failures
        return self.examined > 0 and not self.failures

    @property
    def status(self) -> str:
        if self.examined == 0:
            return "N/A(nothing generated)" if self.exempt else "FAIL(examined 0)"
        if self.failures:
            return f"FAIL({len(self.failures)})"
        # Green, and it says so -- but it does not read as an ordinary PASS,
        # because something really did stop.
        if self.stops:
            return f"PASS(STOP:{self.stops[0]['code']})"
        return "PASS"

    def as_dict(self):
        return {"validator": self.name, "examined": self.examined,
                "status": self.status, "failures": self.failures,
                "notes": self.notes, "stops": self.stops}


# ------------------------------------------------------------------ helpers

def narration(path) -> str:
    body = Path(path).read_text()
    if "## Narration" not in body:
        return ""
    body = body.split("## Narration", 1)[1]
    for stop in ("## Human fingerprint", "## Chapters", "## Sources",
                 "## Confidence", "## B-roll"):
        body = body.split(stop, 1)[0]
    return "\n".join(l for l in body.split("\n")
                     if not l.strip().startswith("{{"))


def spoken(path) -> str:
    """The words a viewer actually hears - narration() with headings, list
    bullets and the [HUMAN] marker itself stripped, matching
    voice/script_text.py's own rules. narration() alone over-reports:
    "### The audience gets to disagree" is a heading, dropped before TTS ever
    sees it, and a validator that scans it anyway invents a defect that was
    never spoken.
    """
    out = []
    for line in narration(path).split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(("-", "*", "+")):
            continue
        if re.match(r"^\*\*[^*]+:\*\*", s):
            continue
        out.append(s.replace("[HUMAN]", " "))
    return " ".join(out)


def sources_block(path) -> str:
    """Just the ## Sources list - stopping at the next ## heading.

    Ten of the twenty scripts carry a `## B-roll plan` AFTER `## Sources`, and
    taking everything to end-of-file swallowed it, so every B-roll line
    ("- 00:12 - source-card: original motion graphic") was read as a source
    entry with no URL. The bug only showed once a week drew on scripts 19 and
    20; scripts 01-04 happen to end at Sources.
    """
    body = Path(path).read_text()
    if "## Sources" not in body:
        return ""
    after = body.split("## Sources", 1)[1]
    return re.split(r"\n## ", after, maxsplit=1)[0]


def script_pov(path) -> str:
    body = Path(path).read_text()
    m = re.search(r"### Producer POV\s*\n+(.+?)(?:\n\s*\n|\Z)", body, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1).replace("[HUMAN]", "")).strip()


# --------------------------------------------------------------- validators

def v1_directive_truth() -> Result:
    r = Result("V1 directive-truth")
    p = subprocess.run([PY, str(ROOT / "tests" / "test_directive_truth.py")],
                       cwd=ROOT, capture_output=True, text=True)
    out = p.stdout + p.stderr
    m = re.search(r"inspected (\d+) v2 directives", out)
    r.examined = int(m.group(1)) if m else 0
    if p.returncode != 0:
        r.fail(f"tests/test_directive_truth.py exited {p.returncode}\n{out[-2000:]}")
    r.note(out.strip().splitlines()[-1] if out.strip() else "no output")
    return r


def v2_planner() -> Result:
    r = Result("V2 planner")
    p = subprocess.run([PY, str(ROOT / "tests" / "test_planner.py")],
                       cwd=ROOT, capture_output=True, text=True)
    out = p.stdout + p.stderr
    r.examined = 1
    if p.returncode != 0:
        r.fail(f"tests/test_planner.py exited {p.returncode}\n{out[-2000:]}")
    r.note(out.strip().splitlines()[-1] if out.strip() else "no output")
    return r


def v3_taxonomy(items) -> Result:
    r = Result("V3 taxonomy")
    for it in items:
        r.examined += 1
        d = exclusions.decide(it["question"])
        if not d.admitted:
            r.fail(f"{it['slug']}: question refused by the gate — {d.rule} "
                   f"(matched {d.matched!r})")
        text = narration(ROOT / it["script"])
        # Narration mode: advice-giving and false framing, not vocabulary.
        db = exclusions.decide_body(text)
        if not db.admitted:
            r.fail(f"{it['slug']}: narration refused by the gate — {db.rule} "
                   f"(matched {db.matched!r})")
        text = text.lower()
        # Prose-level check on the exclusions that a title would never reveal.
        for name, pat in (("Conspiracy, cryptid, paranormal, pseudoscience",
                           r"\b(mermaids are real|megalodon is alive|proves aliens)\b"),
                          ("Medical advice",
                           r"\b(you should take|we recommend taking|cures? your)\b"),
                          ("Financial advice",
                           r"\b(you should invest|buy this stock)\b")):
            if re.search(pat, text):
                r.fail(f"{it['slug']}: narration touches hard exclusion — {name}")
    return r


def v4_pov(items) -> Result:
    r = Result("V4 pov")
    bank = {l["id"]: l["line"].strip()
            for l in read_json(ROOT / "pov" / "pov-bank.json")["lines"]}
    bank_lines = set(bank.values())
    assigns = {a["video"]: a for a in
               read_json(ROOT / "pov" / "pov-assignments.json")["assignments"]}
    window = config()["pov"]["rotation_window"]
    recent = [row.get("pov_id") for row in ledger.load()["published"]][-window:]
    used_this_week: list[str] = []

    for it in items:
        r.examined += 1
        a = assigns.get(it["slug"])
        if not a and it.get("pov_id"):
            # Matched automatically by loop/pov_match.py. The bank IS the
            # owner's approved voice, so selecting from it needs no per-script
            # human decision - only the guarantee that the line is verbatim
            # from the bank, which is checked below like any other.
            a = {"pov_id": it["pov_id"],
                 "line": it.get("pov_line") or bank.get(it["pov_id"], "")}
        if not a:
            r.fail(f"{it['slug']}: no POV line assigned and none matched — "
                   f"the pipeline does not invent a POV line")
            continue
        pid = a["pov_id"]
        if pid not in bank:
            r.fail(f"{it['slug']}: pov_id {pid} is not in the POV bank")
            continue
        if a["line"].strip() != bank[pid]:
            r.fail(f"{it['slug']}: assigned line is not verbatim from the bank")
        if pid in recent or pid in used_this_week:
            r.fail(f"{it['slug']}: {pid} reused inside the {window}-video "
                   f"rotation window")
        used_this_week.append(pid)

        # The script's own Producer POV text. Where it differs from the bank
        # line this is NOT a failure — it is precisely what the owner confirms
        # in her 15 minutes. It is surfaced on the approval page instead.
        spoken = script_pov(ROOT / it["script"])
        if spoken and spoken not in bank_lines:
            r.note(f"{it['slug']}: script POV is an editorial paraphrase, not a "
                   f"bank line — owner confirmation required (this is the "
                   f"Monday 15-minute step, not a defect)")
            it["pov_needs_confirmation"] = True
        it["pov_id"] = pid
        it["pov_bank_line"] = bank[pid]
        it["pov_script_line"] = spoken
    return r


def v5_sources_present(items) -> Result:
    """HARD. A script that speaks numbers must carry a real source list.

    This is the queue-level counterpart of the pipeline's own rule that no
    unsourced value reaches the screen. It trips the breaker.
    """
    r = Result("V5 sources-present")
    for it in items:
        r.examined += 1
        path = ROOT / it["script"]
        prose = narration(path)
        srcs = sources_block(path)
        entries = [l for l in srcs.splitlines() if l.strip().startswith("-")]
        it["source_count"] = len(entries)
        if re.search(r"\d", prose) and len(entries) < 2:
            r.fail(f"{it['slug']}: narration states numbers but ## Sources has "
                   f"{len(entries)} entr(ies)")
        for e in entries:
            if "http" not in e:
                r.fail(f"{it['slug']}: source entry without a URL — {e.strip()[:70]}")
    return r


def v6_attribution(items) -> Result:
    """SOFT. Every organisation the narration names should appear in ## Sources.

    Reported, not breaker-tripping, and deliberately so. An organisation named
    in prose whose entry lives in the companion article rather than the script's
    own list is a provenance-record gap, not an invented value — the pipeline
    still cannot draw anything the narration does not speak. Halting a channel's
    publishing over a bibliography line would be the loop dying of friction.

    The gaps are written to `loop/state/attribution_gaps.json` and shown on the
    approval page, and this validator goes green by itself the moment the
    missing lines are added to the scripts.
    """
    r = Result("V6 attribution (soft)")
    gaps = []
    for it in items:
        r.examined += 1
        path = ROOT / it["script"]
        prose, srcs = narration(path), sources_block(path)
        # Per-item domain, not the flat deep-sea-only ORG_NAMES: a materials
        # script naming NIST or ASM International must be checked against
        # ITS OWN allowlist, or the check silently never fires for it.
        item_domain = it.get("domain") or domains.domain_of_slug(it["slug"]) \
            or "deep-sea-ocean-science"
        try:
            org_names = domain_sources.for_domain(item_domain)
            alias = domain_sources.alias_for(item_domain)
        except KeyError:
            org_names, alias = ORG_NAMES, ALIAS
        named = [n for n in org_names if re.search(rf"\b{re.escape(n)}\b", prose)]
        missing = []
        for n in named:
            if re.search(rf"\b{re.escape(n)}\b", srcs, re.I):
                continue
            alt = alias.get(n)
            if alt and re.search(re.escape(alt), srcs, re.I):
                continue
            missing.append(n)
        it["sources_cited"] = named
        it["attribution_gaps"] = missing
        if missing:
            gaps.append({"slug": it["slug"], "missing_from_sources": missing})
            r.note(f"{it['slug']}: narration names {', '.join(missing)} with no "
                   f"matching ## Sources entry")
    write_json(ATTRIBUTION_GAPS,
               {"checked": now(), "scripts_with_gaps": len(gaps), "gaps": gaps,
                "fix": "Add the named body's own URL to that script's ## Sources "
                       "list. This validator turns green on its own once it is "
                       "there."})
    return r


def v7_plans(items) -> Result:
    r = Result("V7 plans")
    for it in items:
        r.examined += 1
        p = subprocess.run(
            [PY, "-c",
             "import sys, json; sys.path.insert(0, 'visuals')\n"
             "try:\n import segments_ext2\nexcept Exception: pass\n"
             "import planner\n"
             f"pl = planner.plan({str(ROOT / it['script'])!r})\n"
             "beats = pl if isinstance(pl, list) else pl.get('beats', [])\n"
             "print('BEATS', len(beats))\n"],
            cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"BEATS (\d+)", p.stdout)
        if p.returncode != 0 or not m:
            r.fail(f"{it['slug']}: planner failed\n{(p.stderr or p.stdout)[-800:]}")
            continue
        n = int(m.group(1))
        if n < 5:
            r.fail(f"{it['slug']}: planner produced only {n} beats")
        it["planned_beats"] = n
    return r


def v8_source_urls(items) -> Result:
    """Fetch every source URL in a generated script. HARD.

    Only generated scripts are checked: the twenty human-authored scripts were
    sourced by a person, and putting a weekly network dependency in front of
    them would make the loop fail on a flaky connection rather than on a defect.
    A machine-written citation gets no such benefit of the doubt.

    404 / 410 / DNS failure  -> FAIL. The page does not exist.
    401 / 403 / 405          -> pass. Several real bodies (ocean.si.edu among
                                them) refuse scripted requests; that is
                                bot-blocking, not a fabricated URL.
    network unreachable      -> FAIL, reported as such. A validator that
                                silently passes when it cannot check is the
                                exact defect this suite exists to prevent.
    """
    r = Result("V8 source-urls")
    generated = [it for it in items
                 if str(it.get("script", "")).startswith("loop/drafts/")
                 or it.get("generated")]
    if not generated:
        # Nothing generated this week is a legitimate state, but the validator
        # must not then claim to have examined something. It reports zero and
        # run_all() treats a zero-item HARD validator as failing - so this one
        # is explicitly exempt when there is genuinely no generated script.
        r.examined = 0
        r.exempt = True
        r.note("no generated scripts this week; nothing to fetch")
        return r

    checked = 0
    for it in generated:
        path = ROOT / it["script"]
        if not path.exists():
            r.fail(f"{it['slug']}: {it['script']} does not exist")
            continue
        srcs = sources_block(path)
        urls = re.findall(r"https?://[^\s)>\]]+", srcs)
        if len(urls) < 3:
            r.fail(f"{it['slug']}: only {len(urls)} source URL(s)")
        for u in urls:
            checked += 1
            r.examined += 1
            code, why = probe(u)
            if code in (404, 410):
                r.fail(f"{it['slug']}: source URL does not exist "
                       f"(HTTP {code}) - {u}")
            elif code == 0:
                r.fail(f"{it['slug']}: source URL unreachable ({why}) - {u}")
            elif code in (401, 403, 405):
                r.note(f"{it['slug']}: {u} returned {code} (bot-blocked, "
                       f"treated as reachable)")
    if checked == 0:
        r.fail("a generated script was queued but no URL was examined")
    return r


# --------------------------------------------------------- footage validators
#
# These govern visuals/footage.py, which puts rights-cleared NOAA ROV footage on
# screen. Each examines every plan in plans/ against the live manifest, and each
# hard-fails when it examined zero items - a footage validator that passes
# because no clip matched anything is the "guard that cannot reach what it
# governs" defect.

FOOTAGE_SAFE_SEGMENTS = {"ambient_drift", "species_image"}


def _footage_not_on_this_machine(FT) -> bool:
    """True when this machine simply does not hold the footage.

    THE DISTINCTION MATTERS AND IS DELIBERATE. An ABSENT manifest means the
    clips live somewhere else - they are large video files kept on the Mac and
    in R2, never in git - so a cloud runner has nothing to govern and says so.
    A manifest that EXISTS but lists nothing, or lists clips whose files are
    gone, is a real defect and still hard-fails: that is the empty-loop case
    these validators were written to catch, and it is not touched here.

    Without this, V9 through V12 examined zero on every GitHub run, hard-failed
    correctly, tripped the breaker, and kept `loop · Mon 06:00` red - a guard
    failing not because anything was wrong but because it was pointed at the
    wrong machine.
    """
    return not os.path.exists(FT.MANIFEST)


def _footage_env():
    """(footage module, [(slug, plan, durations)]). Raises if unimportable."""
    sys.path.insert(0, str(ROOT / "visuals"))
    import footage as FT  # noqa: E402
    plans = []
    for path in sorted((ROOT / "plans").glob("*.json")):
        plan = json.loads(path.read_text())
        plans.append((path.stem, plan, [float(b["seconds"]) for b in plan]))
    return FT, plans


def v9_footage_window() -> Result:
    """HARD. A cut must lie wholly inside ONE clean window."""
    r = Result("V9 footage-window")
    try:
        FT, plans = _footage_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/footage.py could not be loaded: {e}")
        return r
    if _footage_not_on_this_machine(FT):
        r.exempt = True
        r.note("no footage manifest on this machine, so there is no\n               clip to govern. The clips are large video and live on the Mac\n               and in R2 by design, never in git.")
        return r
    assets = FT.usable_assets()
    for slug, plan, durs in plans:
        for cut in FT.assign(plan, durs, slug, assets):
            if cut is None:
                continue
            r.examined += 1
            a = cut["asset"]
            if not FT.inside_window(a, cut["start"], cut["end"]):
                r.fail(f"{slug} beat {cut['beat']}: cut "
                       f"{cut['start']}-{cut['end']}s of {a['title']!r} is not "
                       f"inside any clean window {FT.windows(a)}")
            w = cut["window"]
            if cut["start"] < w["start"] or cut["end"] > w["end"]:
                r.fail(f"{slug} beat {cut['beat']}: cut escapes the window it "
                       f"was placed in ({w})")
    r.note(f"{r.examined} footage cut(s) checked across {len(plans)} plan(s)")
    return r


def v10_footage_crop() -> Result:
    """HARD. `cropped` clips carry a permanent corner wordmark; the recorded
    rect must exist AND reach the render."""
    r = Result("V10 footage-crop")
    try:
        FT, plans = _footage_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/footage.py could not be loaded: {e}")
        return r
    if _footage_not_on_this_machine(FT):
        r.exempt = True
        r.note("no footage manifest on this machine, so there is no\n               clip to govern. The clips are large video and live on the Mac\n               and in R2 by design, never in git.")
        return r
    assets = FT.usable_assets()
    for a in assets:
        r.examined += 1
        chain = FT.vf_chain(a)
        if a.get("treatment") == "cropped":
            c = a.get("crop") or {}
            if not any(float(c.get(k, 0)) > 0 for k in
                       ("left", "top", "right", "bottom")):
                r.fail(f"{a['title']!r}: treatment 'cropped' but the rect "
                       f"removes nothing - the wordmark stays on screen")
                continue
            sw, sh = int(a["width"]), int(a["height"])
            cw = int(round((1 - float(c.get("left", 0)) - float(c.get("right", 0))) * sw))
            ch = int(round((1 - float(c.get("top", 0)) - float(c.get("bottom", 0))) * sh))
            if not chain.startswith(f"crop={cw}:{ch}:"):
                r.fail(f"{a['title']!r}: recorded crop rect is not applied - "
                       f"filter chain is {chain!r}")
        elif chain.startswith("crop=") and not chain.startswith(
                f"crop={FT.W}:{FT.H}"):
            r.fail(f"{a['title']!r}: treatment 'as-shot' but a source crop was "
                   f"applied - {chain!r}")
    r.note(f"{r.examined} clip(s); "
           f"{sum(1 for a in assets if a.get('treatment') == 'cropped')} cropped")
    return r


def v11_footage_hash() -> Result:
    """HARD. The bytes on disk must be the bytes the rights decision covers."""
    r = Result("V11 footage-hash")
    try:
        FT, _ = _footage_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/footage.py could not be loaded: {e}")
        return r
    if _footage_not_on_this_machine(FT):
        r.exempt = True
        r.note("no footage manifest on this machine, so there is no\n               clip to govern. The clips are large video and live on the Mac\n               and in R2 by design, never in git.")
        return r
    m = FT.load_manifest()
    for a in m.get("assets", []):
        r.examined += 1
        try:
            FT.verify(a)
        except FT.RightsRefusal as e:
            r.fail(str(e))
    r.note(f"{r.examined} clip(s) re-hashed against "
           f"channel/imagery/video_rights.json")
    return r


def v12_footage_scope() -> Result:
    """HARD. Footage never replaces a beat that carries information on screen."""
    r = Result("V12 footage-scope")
    try:
        FT, plans = _footage_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/footage.py could not be loaded: {e}")
        return r
    if _footage_not_on_this_machine(FT):
        r.exempt = True
        r.note("no footage manifest on this machine, so there is no\n               clip to govern. The clips are large video and live on the Mac\n               and in R2 by design, never in git.")
        return r
    assets = FT.usable_assets()
    for slug, plan, durs in plans:
        cuts = FT.assign(plan, durs, slug, assets)
        for i, b in enumerate(plan):
            r.examined += 1
            if cuts[i] is None:
                continue
            if b["segment"] not in FOOTAGE_SAFE_SEGMENTS:
                r.fail(f"{slug} beat {i}: footage placed over a "
                       f"{b['segment']!r} beat, which draws information on "
                       f"screen")
            if b["segment"] == "species_image":
                subj = (b.get("args") or {}).get("subject")
                if subj in FT.UNILLUSTRATABLE:
                    r.fail(f"{slug} beat {i}: footage placed on {subj!r}, which "
                           f"is declared unillustratable - "
                           f"{FT.UNILLUSTRATABLE[subj]}")
                elif subj not in FT.SUBJECT_FOOTAGE:
                    r.fail(f"{slug} beat {i}: footage placed on subject "
                           f"{subj!r} with no hand-checked clip mapping")
    r.note(f"{r.examined} beat(s) across {len(plans)} plan(s)")
    return r



def v13_render_not_clipped() -> Result:
    """HARD. No finished render ends before its own narration does.

    Beats render as round(seconds*FPS) FRAMES, and the mux uses -shortest, so a
    plan whose beats round down produces a video fractionally shorter than the
    audio - and ffmpeg then truncates the NARRATION to match. It is silent,
    it is small, and it lands on the last word of the episode. Episodes 10, 14
    and 18 all shipped clipped on 2026-08-31 (0.098s, 0.014s, 0.122s), with the
    lost audio measured at -14.4 dB against a -45 dB floor: speech, not silence.

    This checks the rendered artefact, not the intention, so it catches the bug
    however it is reintroduced.
    """
    import glob as _glob
    import os as _os
    import subprocess as _sp
    r = Result("V13 render-not-clipped")

    def _dur(path):
        out = _sp.run(["ffprobe", "-v", "error", "-show_entries",
                       "format=duration", "-of", "csv=p=0", path],
                      capture_output=True, text=True).stdout.strip()
        return float(out) if out else None

    for render in sorted(_glob.glob(str(ROOT / "renders" / "*-final.mp4"))):
        slug = _os.path.basename(render)[:-len("-final.mp4")]
        wavs = sorted(_glob.glob(str(ROOT / "audio" / slug / "*.wav")))
        if not wavs:
            continue                      # never narrated; nothing to clip
        plan = ROOT / "plans" / f"{slug}.json"
        if plan.exists():
            try:
                if len(json.loads(plan.read_text())) != len(wavs):
                    continue              # partial narration; not this check
            except Exception:             # noqa: BLE001
                pass
        r.examined += 1
        video = _dur(render)
        audio = sum(d for d in (_dur(w) for w in wavs) if d)
        if video is None:
            r.fail(f"{slug}: render could not be probed")
            continue
        # One frame of slack: a render may legitimately round up, never down.
        if video < audio - (1.0 / 30.0):
            r.fail(f"{slug}: render is {audio - video:.3f}s SHORTER than its "
                   f"narration ({video:.3f}s vs {audio:.3f}s) - -shortest is "
                   f"clipping the end of the last beat")
    if r.examined == 0 and not list((ROOT / "renders").glob("*.mp4")):
        # No rendered MP4 anywhere on this machine. Renders are hundreds of
        # megabytes and live on the Mac and in R2, never in git, so a cloud
        # runner has nothing to measure. A renders/ directory that HAS files
        # but yields no fully-narrated pair still fails below - that is the
        # case this guard exists for.
        r.exempt = True
        r.note("no rendered MP4 on this machine; renders live on the Mac and "
               "in R2 by design. The Mac run covers this.")
        return r
    if r.examined == 0:
        r.fail("examined 0 fully-narrated renders - this validator cannot see "
               "what it is meant to govern")
    r.note(f"{r.examined} fully-narrated render(s)")
    return r

# ---------------------------------------------------------- shorts validators
#
# visuals/shorts.py cuts a 9:16 Short out of a finished 16:9 master. The master
# carries burned-in captions, so the Short crops the caption band off the source
# frame before scaling it - and that crop also removes the source credit the
# renderer drew below the plate (segments_species.py at row 975, footage.py at
# 991-1038). The credit is therefore REDRAWN in the Short's own chrome from
# channel/imagery/rights.json and channel/imagery/video_rights.json.
#
# Both halves of that are guarded here, on the artefact:
#   V14 the credit that has to be on screen actually is, read back off the pixels
#   V15 the burned caption really was removed, and nothing else was

SHORTS_DIR = ROOT / "shorts"


def _shorts_env():
    """(shorts module, ocr fn, [(mp4, receipt)]). Raises if unimportable."""
    sys.path.insert(0, str(ROOT / "visuals"))
    sys.path.insert(0, str(ROOT / "research"))
    import shorts as SH  # noqa: E402
    import imagery_video as IV  # noqa: E402
    out = []
    for p in sorted(SHORTS_DIR.glob("*.mp4.short.json")):
        mp4 = Path(str(p)[: -len(".short.json")])
        if mp4.exists():
            out.append((mp4, json.loads(p.read_text())))
    return SH, IV.ocr, out


def _frame(path, t: float, out: Path, crop: str | None = None):
    """One frame at `t`, optionally cropped, as a PNG."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{float(t):.3f}", "-i", str(path)]
    if crop:
        cmd += ["-vf", crop]
    cmd += ["-frames:v", "1", "-y", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out)


def _ocr_words(ocr, path: str) -> str:
    """Every word Vision read, upper case, punctuation stripped, space joined."""
    items = ocr([path]).get(path, [])
    return " " + re.sub(r"[^A-Z0-9 ]+", " ",
                        " ".join(i["t"] for i in items).upper()) + " "


def _samples(rec: dict, n: int = 3) -> list[tuple[float, float]]:
    """(short_t, source_t) at the midpoint of the longest `n` beats."""
    segs = sorted(rec.get("segments") or [], key=lambda s: -s["seconds"])[:n]
    return [(s["short_start"] + s["seconds"] / 2,
             s["source_start"] + s["seconds"] / 2) for s in segs]


def v14_shorts_attribution() -> Result:
    """HARD. A Short built from a beat whose asset carries a credit SHOWS it.

    The credit is not taken from the Short's own receipt - that would be the
    receipt marking its own homework. It is re-resolved from the imagery
    manifests for the beats the receipt says were used, and then read back OFF
    THE PIXELS of the finished file with Apple Vision, inside the credit strip
    the chrome is supposed to have drawn it in.

    Stripping or omitting attribution is the one thing this pipeline may not do,
    so this examines every Short that uses credited material and hard-fails if
    it could examine none.
    """
    r = Result("V14 shorts-attribution")
    tmp = ROOT / "loop" / "state" / "_v14"
    try:
        SH, ocr, receipts = _shorts_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/shorts.py or the OCR helper could not be loaded: {e}")
        return r
    if not receipts and not os.path.isdir(SHORTS_DIR):
        r.exempt = True
        r.note("no shorts/ directory on this machine; cut Shorts and their "
               "receipts live on the Mac and in R2 by design. The Mac run "
               "covers this.")
        return r
    if not receipts:
        r.fail(f"no Short receipts in {SHORTS_DIR}/*.mp4.short.json - this "
               f"validator cannot see what it is meant to govern")
        return r
    tmp.mkdir(parents=True, exist_ok=True)
    uncredited = 0
    for mp4, rec in receipts:
        slug = rec["slug"]
        plan_path = ROOT / "plans" / f"{slug}.json"
        if not plan_path.exists():
            r.fail(f"{mp4.name}: plans/{slug}.json is gone; the credit its beats "
                   f"require cannot be re-resolved")
            continue
        plan = json.loads(plan_path.read_text())
        want, dropped = SH.resolve_credits(slug, plan, rec["beats"])
        if dropped:
            r.fail(f"{mp4.name}: kept beat(s) {sorted(dropped)} whose credit "
                   f"cannot be resolved: {list(dropped.values())[0]}")
        if not want:
            uncredited += 1
            continue
        r.examined += 1
        band_y, band_h = rec["band_y"], rec["band_h"]
        strip = f"crop={SH.OUT_W}:{SH.CREDIT_GAP}:0:{band_y + band_h}"
        seen = _ocr_words(ocr, _frame(mp4, _samples(rec, 1)[0][0],
                                      tmp / f"{mp4.stem}.credit.png", strip))
        for c in want:
            words = [w for w in re.findall(r"[A-Z0-9]+", c.upper()) if len(w) > 2]
            missing = [w for w in words if f" {w} " not in seen]
            if missing:
                r.fail(f"{mp4.name}: credit {c!r} is not on screen - Vision read "
                       f"{seen.strip()!r} in the credit strip, missing {missing}")
    if r.examined == 0:
        r.fail(f"examined 0 Shorts that carry credited material ({len(receipts)} "
               f"Short(s) present, {uncredited} using no credited asset) - this "
               f"validator cannot reach what it governs")
    r.note(f"{r.examined} Short(s) with credited material, {uncredited} without")
    return r


def v15_shorts_caption_crop() -> Result:
    """HARD. The burned caption band really is gone from a Short's picture.

    Proven on the artefact in two measurements per sampled beat, because either
    alone is weak:

      BEFORE - Vision OCRs the source rows the burned caption plate occupies.
      They must contain text, and the crop must end at or above the top of that
      plate. A sample where the master was not captioning at that instant proves
      nothing and is not counted; a validator that counted it would pass on an
      empty loop.

      AFTER  - the Short's picture band is compared pixel-for-pixel against two
      hypotheses rebuilt from that same master frame: the CROPPED source scaled
      to the band, and the WHOLE source scaled to the band. The cropped
      hypothesis must fit at least twice as well. It is a relative test, so it
      needs no absolute threshold and survives a change of scaler.

    Together: the caption is in the rows that were removed, and the band is the
    rows that were kept. OCR is used for the first half rather than the second
    because a Short's band legitimately contains the designer's own on-screen
    words, and several of them are the words the narration is speaking - an OCR
    test on the band would fail on a correct Short.
    """
    import numpy as np
    from PIL import Image
    r = Result("V15 shorts-caption-crop")
    tmp = ROOT / "loop" / "state" / "_v15"
    try:
        SH, ocr, receipts = _shorts_env()
    except Exception as e:                       # noqa: BLE001
        r.fail(f"visuals/shorts.py or the OCR helper could not be loaded: {e}")
        return r
    if not receipts and not os.path.isdir(SHORTS_DIR):
        r.exempt = True
        r.note("no shorts/ directory on this machine; cut Shorts and their "
               "receipts live on the Mac and in R2 by design. The Mac run "
               "covers this.")
        return r
    if not receipts:
        r.fail(f"no Short receipts in {SHORTS_DIR}/*.mp4.short.json - this "
               f"validator cannot see what it is meant to govern")
        return r
    tmp.mkdir(parents=True, exist_ok=True)
    for mp4, rec in receipts:
        src = ROOT / rec["source"]
        if not src.exists():
            r.fail(f"{mp4.name}: source {rec['source']} is gone")
            continue
        ch, by, bh = rec["source_crop_height"], rec["band_y"], rec["band_h"]
        top = SH.plate_top(rec["cap_lines"])
        plate = f"crop={SH.SRC_W}:{SH.SRC_H - SH.CAP.CAP_BOTTOM - top}:0:{top}"
        if ch > top:
            r.fail(f"{mp4.name}: crop keeps {ch} source rows but the "
                   f"{rec['cap_lines']}-line caption plate starts at row {top} - "
                   f"{ch - top} row(s) of burned caption reach the picture")
        for k, (t_short, t_src) in enumerate(_samples(rec)):
            removed = _frame(src, t_src, tmp / f"{mp4.stem}.{k}.cut.png", plate)
            if not _ocr_words(ocr, removed).strip():
                continue                 # master not captioning here; no evidence
            r.examined += 1
            m = np.asarray(Image.open(
                _frame(src, t_src, tmp / f"{mp4.stem}.{k}.src.png")
            ).convert("RGB"))
            s = np.asarray(Image.open(
                _frame(mp4, t_short, tmp / f"{mp4.stem}.{k}.short.png")
            ).convert("RGB")).astype(np.int16)[by:by + bh]

            def fit(rows):
                exp = np.asarray(Image.fromarray(m[:rows]).resize(
                    (SH.OUT_W, bh), Image.BICUBIC)).astype(np.int16)
                return float(np.abs(exp - s).mean())

            cropped, whole = fit(ch), fit(SH.SRC_H)
            if cropped * 2 >= whole:
                r.fail(f"{mp4.name} @{t_short:.1f}s: the band fits the UNCROPPED "
                       f"master about as well as the cropped one "
                       f"(cropped {cropped:.2f} vs whole {whole:.2f}) - the "
                       f"burned caption band was not removed")
    if r.examined == 0:
        r.fail("examined 0 captioned samples - every sampled master frame OCRed "
               "empty, so this validator proved nothing")
    r.note(f"{r.examined} captioned sample(s) across {len(receipts)} Short(s)")
    return r


# ------------------------------------------------------- REACH validators
#
# V16-V19 govern what a video looks like ON YOUTUBE after it is published, not
# what a script looks like before it is voiced. They are deliberately NOT part
# of `run_all`: that is the Monday gate in front of the render pipeline, and
# wiring post-publish state into it would let a lagging translation lane halt
# drafting and, through the breaker, publishing. A reach defect must never stop
# the channel shipping. They run as their own group:
#
#     .venv/bin/python loop/validate.py --reach
#
# Every one of them reads COMMITTED STATE rather than calling YouTube, so they
# run offline, in CI, and identically on both. The state files are only ever
# written by a lane that had an API answer in hand.

# Module-level so loop/tests/test_reach.py can point them at doctored copies
# and prove each validator FAILS on the broken state. A guard nobody has ever
# seen fail is a guard nobody knows works.
REACH_LOOP_DIR = ROOT / "loop"
REACH_STATE = ROOT / "loop" / "state"
CAPTIONS_STATE = REACH_STATE / "captions.json"
LOCALIZATIONS_STATE = REACH_STATE / "localizations.json"
UPLOAD_SRC = ROOT / "loop" / "upload.py"
REACH_CAPTIONS_DIR = ROOT / "captions"

CANONICAL_LANGUAGE = "en"
REACH_LANGUAGES = ["de", "es", "hi", "id", "pt-BR"]

# How long a caption gap may be excused by "the quota ran out today". The
# backfill is 450 units a video against a 10,000-unit day shared with uploads,
# so a few days is normal and a week is a stalled lane.
DEFER_GRACE_DAYS = 7


def _days_since(stamp: str | None) -> float | None:
    if not stamp:
        return None
    import datetime as _dt
    try:
        when = _dt.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return round((_dt.datetime.now(_dt.timezone.utc) - when).total_seconds()
                 / 86400, 1)


# A caption track must be on the video a full daily-lane cycle before it airs.
# 24h is that cycle plus margin: the reach lane runs once a day, so anything
# tighter cannot be met by the machinery that is supposed to meet it, and
# anything looser lets a video reach the public with no track and no warning.
_TRACK_DUE_HOURS = 24


def _airs_within(row: dict, hours: int) -> bool | None:
    """True if this row airs within `hours`, False if later, None if unknown.

    None means the ledger row carries no readable `scheduled_publish_at`, and
    an unreadable airdate is never an excuse: the caller treats it as due.
    """
    import datetime as _dt                                  # noqa: PLC0415
    stamp = row.get("scheduled_publish_at")
    if not stamp:
        return None
    try:
        when = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    now = _dt.datetime.now(_dt.timezone.utc)
    return when <= now + _dt.timedelta(hours=hours)


def _live_videos() -> list[dict]:
    sys.path.insert(0, str(ROOT / "loop"))
    import ytmeta                                        # noqa: PLC0415
    return ytmeta.live_videos()


def v16_caption_track() -> Result:
    """Every live video has an English caption track — or a named reason.

    The track is not a courtesy to readers. YouTube Studio: "English subtitles
    are the default source for auto-translation of subtitles and audio." No
    track means no auto-translated subtitles and no auto-dubbed audio, in any
    language.

    A video may be UNACCOUNTED only while the credential is missing
    youtube.force-ssl, which no lane can grant itself. The moment
    loop/state/captions.json records that the scope arrived, "blocked" stops
    being an acceptable answer and this fails — so the exemption cannot outlive
    the thing that justified it.
    """
    r = Result("V16 caption-track")
    state = read_json(CAPTIONS_STATE, default={"videos": {}, "blocked": {}})
    have_scope = bool(state.get("token_has_force_ssl"))
    deferred: list[str] = []
    escalated: list[str] = []
    before_air: list[str] = []
    # Identifiers another lane has ALREADY escalated to the owner, with an
    # issue number to prove it. See loop/held.py: this is not an exemption
    # list, it is yesterday's alarm, and it only ever contains things a human
    # has genuinely been told about.
    covered = _held.covering_hold(_stops_dir())
    for row in _live_videos():
        r.examined += 1
        vid, slug = row["video_id"], row["slug"]
        srt = Path(REACH_CAPTIONS_DIR) / f"{slug}.srt"
        if not srt.exists():
            hold = covered.get(slug)
            if hold:
                # The missing .srt is real and this validator is right about
                # it - but the upload lane already refused this episode, named
                # it, and opened issue #N about it hours ago. Failing here as
                # well is the same news in a second red mail. It goes red again
                # the moment that hold stops covering the slug, which happens
                # if the issue is closed or the lane stops raising it.
                escalated.append(
                    f"{slug}: captions/{slug}.srt does not exist — already "
                    f"escalated by the {hold.get('stage')} lane as "
                    f"[{hold.get('code')}] on "
                    f"{hold.get('first_reported_at')}, tracked by issue "
                    f"#{hold.get('issue')}")
                continue
            r.fail(f"{slug}: captions/{slug}.srt does not exist, so no track "
                   f"can ever be uploaded for it")
            continue
        rec = (state.get("videos") or {}).get(vid) or {}
        if rec.get("caption_id") and rec.get("track_kind") == "asr":
            # YouTube's own speech recognition, not our file. It is a track,
            # so a naive check passes; it is NOT the narration script, and the
            # channel's rule is that nothing invents text. Recorded as a real
            # track once, on 2026-09-02, which is why this is checked here and
            # not only in the lane.
            r.fail(f"{slug} ({vid}) has only YouTube's ASR track, not the "
                   f"timed .srt this repo generated — machine-transcribed "
                   f"text is not what this channel ships")
            continue
        if rec.get("caption_id"):
            continue
        blocked = (state.get("blocked") or {}).get(vid) or {}
        reason = blocked.get("reason")
        if reason == "CAPTIONS_SCOPE_MISSING" and not have_scope:
            r.note(f"{slug}: no track yet — blocked on the owner's force-ssl "
                   f"consent, .srt is ready")
            continue
        if reason == "QUOTA_DEFERRED":
            # captions.insert is 400 units, so a 15-video backfill spans days
            # by design. That is an acceptable reason for a gap TODAY and never
            # an acceptable reason for a permanent one, so the excuse expires.
            days = _days_since(blocked.get("since"))
            if days is not None and days <= DEFER_GRACE_DAYS:
                deferred.append(f"{slug}: deferred {days:.1f}d ago, .srt is "
                                f"ready ({vid})")
                continue
            r.fail(f"{slug} ({vid}) has been waiting for a caption track for "
                   f"{days if days is not None else '?'} day(s) on a "
                   f"QUOTA_DEFERRED excuse that expires at "
                   f"{DEFER_GRACE_DAYS}. The backfill has stalled — check "
                   f"whether the reach lane is running at all.")
            continue
        # NOT YET AIRED. `ytmeta.live_videos()` returns every row in the
        # ledger's `published` list, which since the cloud-upload lane began
        # scheduling includes videos uploaded PRIVATE with a publishAt weeks
        # away. Calling those "published with NO caption track" made this
        # validator red on the afternoon of every upload - CONFIRMED run
        # 34136862505, where xbmIX6n2OI8 was flagged four minutes after it was
        # uploaded private for 2026-09-28, an hour before the daily lane that
        # inserts the track next runs. Nothing was wrong.
        #
        # This is a DEADLINE, not a grace period, and it is stricter than what
        # it replaces: the track must be on the video a full lane cycle before
        # it airs. The moment `scheduled_publish_at` is inside 24 hours - and
        # of course the moment the video is actually public - a missing track
        # is a hard failure again, while there is still a day to fix it.
        due = _airs_within(row, hours=_TRACK_DUE_HOURS)
        if row.get("privacy") == "private" and due is False:
            before_air.append(
                f"{slug} ({vid}): no track yet, .srt is ready, and it does "
                f"not air until {row.get('scheduled_publish_at')} — the daily "
                f"reach lane inserts it before then, and this goes red if it "
                f"has not {_TRACK_DUE_HOURS}h before air")
            continue
        r.fail(f"{slug} ({vid}) is published with NO English caption track, so "
               f"YouTube cannot auto-translate its subtitles or audio"
               + (" — and the scope that used to excuse this is now granted"
                  if have_scope and blocked else ""))
    if escalated:
        r.named_stop(
            "CAPTION_SOURCE_HELD",
            f"{len(escalated)} of {r.examined} live video(s) have no "
            f"captions/<slug>.srt at all — a real gap, and one that only the "
            f"owner can close, because the .srt is derived from narration "
            f"audio that exists on her Mac and nowhere else. Every one of "
            f"them has ALREADY been named by the lane that found it first and "
            f"is tracked by an open issue, so this validator reports them "
            f"rather than raising a second alarm for the same fact. It fails "
            f"outright for any episode NOT covered by an open, issued hold.",
            items=escalated)
    if before_air:
        r.named_stop(
            "CAPTIONS_BEFORE_AIRDATE",
            f"{len(before_air)} of {r.examined} video(s) are uploaded PRIVATE "
            f"with a future airdate and have no caption track yet. Their .srt "
            f"files are ready and the daily reach lane inserts tracks in turn; "
            f"this stops being acceptable, and this validator goes red on its "
            f"own, {_TRACK_DUE_HOURS} hours before each one airs.",
            items=before_air)
    if deferred:
        r.named_stop(
            "CAPTIONS_QUOTA_DEFERRED",
            f"{len(deferred)} of {r.examined} live video(s) have no English "
            f"caption track YET because captions.insert costs "
            f"400 units against a day shared with the upload lane. Every one "
            f"of them has a checked, timed .srt on disk and a dated deferral "
            f"receipt, and the daily reach lane takes them in turn. This is "
            f"the backfill working as designed, not a gap — it stops being "
            f"acceptable, and this validator goes red on its own, "
            f"{DEFER_GRACE_DAYS} days after a video is FIRST deferred.",
            items=deferred)
    if r.examined == 0:
        r.fail("no live video in loop/state/ledger.json — this validator "
               "proved nothing")
    return r


def v17_localizations() -> Result:
    """Every live video carries all five localizations — or a named reason.

    Deliberately the SAME shape as V16, because the bug this fixes was the
    two being different. V16 has always read loop/state/captions.json's
    `blocked` map and stayed green on a video the lane had deliberately put
    off; V17 read only `videos` and had no way to express "put off" at all,
    so a video the localize lane had correctly deferred for quota was
    reported in the identical words as a video that had been published and
    forgotten. One of those needs a human at 10:00 and the other needs
    nobody, and the daily mail could not tell them apart.

    The excuse is bounded exactly as V16's is: `since` is the FIRST deferral
    and is never refreshed, so a stalled lane goes red by itself.

    And the airdate deadline is V16's, for the same reason and in the same
    words: a video uploaded PRIVATE for a date three weeks out is in the
    ledger's `published` list but is not published, and demanding five
    localizations on it within minutes of upload made this red on the
    afternoon of every upload. It is due 24 hours before it airs. Keeping the
    two validators the same shape is the entire point of this one's docstring
    and is not something to fix on one side only.
    """
    r = Result("V17 localizations")
    state = read_json(LOCALIZATIONS_STATE,
                      default={"videos": {}, "blocked": {}})
    deferred: list[str] = []
    before_air: list[str] = []
    for row in _live_videos():
        r.examined += 1
        vid, slug = row["video_id"], row["slug"]
        rec = (state.get("videos") or {}).get(vid) or {}
        got = sorted(rec.get("languages") or [])
        missing = [l for l in REACH_LANGUAGES if l not in got]
        if not missing:
            continue
        blocked = (state.get("blocked") or {}).get(vid) or {}
        if blocked.get("reason") == "QUOTA_DEFERRED":
            days = _days_since(blocked.get("since"))
            if days is not None and days <= DEFER_GRACE_DAYS:
                deferred.append(f"{slug}: deferred {days:.1f}d ago, missing "
                                f"{', '.join(missing)} ({vid})")
                continue
            r.fail(f"{slug} ({vid}) has been waiting for localizations for "
                   f"{days if days is not None else '?'} day(s) on a "
                   f"QUOTA_DEFERRED excuse that expires at "
                   f"{DEFER_GRACE_DAYS}. The lane has stalled — check whether "
                   f"the reach lane is running at all.")
            continue
        if (row.get("privacy") == "private"
                and _airs_within(row, hours=_TRACK_DUE_HOURS) is False):
            before_air.append(
                f"{slug} ({vid}): missing {', '.join(missing)}, and it does "
                f"not air until {row.get('scheduled_publish_at')}")
            continue
        # No localizations and NO STATED REASON. This is the case that must
        # stay red: it is exactly what _fQ3-YI63oQ looked like on 2026-09-03,
        # and it meant a published video nobody could find in five languages.
        r.fail(f"{slug} ({vid}) has no localized title/description for "
               f"{', '.join(missing)} and no recorded reason — it cannot be "
               f"found by a search in those languages")
    if before_air:
        r.named_stop(
            "LOCALIZE_BEFORE_AIRDATE",
            f"{len(before_air)} of {r.examined} video(s) are uploaded PRIVATE "
            f"with a future airdate and are not localized yet. The daily "
            f"localize lane takes them in turn; this validator goes red on "
            f"its own {_TRACK_DUE_HOURS} hours before each one airs, while "
            f"there is still a lane cycle left to fix it.",
            items=before_air)
    if deferred:
        r.named_stop(
            "LOCALIZE_QUOTA_DEFERRED",
            f"{len(deferred)} of {r.examined} live video(s) are not localized "
            f"YET because the day's YouTube allowance could not fund a "
            f"videos.update for them while keeping the upload lane's slot "
            f"back. Each carries a dated deferral receipt written by "
            f"loop/localize.py and the daily lane takes them in turn. This "
            f"validator goes red on its own {DEFER_GRACE_DAYS} days after a "
            f"video is FIRST deferred.",
            items=deferred)
    if r.examined == 0:
        r.fail("no live video in loop/state/ledger.json — this validator "
               "proved nothing")
    return r


def v18_default_language() -> Result:
    """`defaultLanguage` is set, and is exactly `en` everywhere.

    Two failures in one. Unset, and the API rejects localizations outright
    while Studio renders nothing but a "Set language" dropdown — the state all
    16 videos were in on 2026-09-02. Set inconsistently (`en` on some, `en-US`
    on others) and nothing anywhere reports it.
    """
    r = Result("V18 default-language")

    # the source of every future upload
    r.examined += 1
    src = Path(UPLOAD_SRC).read_text()
    payload = re.search(r"def build_payload.*?(?=\ndef )", src, re.S)
    body = payload.group(0) if payload else ""
    if f'"defaultLanguage": "{CANONICAL_LANGUAGE}"' not in body:
        r.fail(f'loop/upload.py build_payload does not set snippet.'
               f'defaultLanguage="{CANONICAL_LANGUAGE}", so every new upload '
               f'lands unable to hold localizations')
    # The VALUE, not the word: the surrounding comment names "en-US" precisely
    # to say it is wrong, and a naive substring search reads that as the bug.
    if re.search(r'"default(Audio)?Language"\s*:\s*"en-US"', body):
        r.fail('loop/upload.py build_payload sets a defaultLanguage of "en-US"; '
               'the canonical value for this channel is "en"')

    # the merge helper every write goes through
    r.examined += 1
    sys.path.insert(0, str(ROOT / "loop"))
    import ytmeta                                        # noqa: PLC0415
    if ytmeta.DEFAULT_LANGUAGE != CANONICAL_LANGUAGE:
        r.fail(f"loop/ytmeta.py DEFAULT_LANGUAGE is "
               f"{ytmeta.DEFAULT_LANGUAGE!r}, not {CANONICAL_LANGUAGE!r}")

    # and what actually shipped
    state = read_json(LOCALIZATIONS_STATE, default={"videos": {}})
    for vid, rec in (state.get("videos") or {}).items():
        r.examined += 1
        if rec.get("default_language") != CANONICAL_LANGUAGE:
            r.fail(f"{rec.get('slug', vid)} shipped with defaultLanguage="
                   f"{rec.get('default_language')!r}, not "
                   f"{CANONICAL_LANGUAGE!r}")
    if r.examined == 0:
        r.fail("examined nothing")
    return r


def v19_snippet_merge() -> Result:
    """No lane may send a partial snippet to videos.update.

    `videos.update` REPLACES the parts named in `part=`. A snippet-bearing
    update built from anything but the live snippet erases the title,
    description, tags and categoryId of a published video — fifteen of them
    here, in one loop, behind a 200 OK.

    Two proofs: no other module issues such a call, and the one helper that
    does refuses a snippet it cannot complete.
    """
    r = Result("V19 snippet-merge-safety")
    allowed = {"ytmeta.py"}
    for path in sorted(Path(REACH_LOOP_DIR).glob("*.py")):
        r.examined += 1
        text = path.read_text()
        for m in re.finditer(r"videos\?part=([A-Za-z,]+)", text):
            if "snippet" in m.group(1) and path.name not in allowed:
                r.fail(f"loop/{path.name} issues videos.update with "
                       f"part={m.group(1)} directly. Every snippet-bearing "
                       f"update must go through ytmeta.update_localizations, "
                       f"which merges onto the live snippet.")

    sys.path.insert(0, str(ROOT / "loop"))
    import ytmeta                                        # noqa: PLC0415

    # it refuses what it cannot complete
    for bad, why in ((None, "no snippet at all"),
                     ({}, "an empty snippet"),
                     ({"title": "x"}, "a snippet with no categoryId"),
                     ({"categoryId": "27"}, "a snippet with no title")):
        r.examined += 1
        try:
            ytmeta.merge_snippet(bad)
            r.fail(f"ytmeta.merge_snippet accepted {why} — it would have "
                   f"wiped a live video's metadata")
        except ytmeta.MergeRefused:
            pass
        except Exception as e:                            # noqa: BLE001
            r.fail(f"ytmeta.merge_snippet raised {type(e).__name__} rather "
                   f"than MergeRefused for {why}")

    # and it carries everything through
    r.examined += 1
    live = {"title": "Why is it dark?", "description": "Because.\nSources",
            "tags": ["deep sea", "ocean"], "categoryId": "27"}
    out = ytmeta.merge_snippet(dict(live))
    for k, v in live.items():
        if out.get(k) != v:
            r.fail(f"ytmeta.merge_snippet lost or changed {k!r}: "
                   f"{out.get(k)!r} != {v!r}")
    if out.get("defaultLanguage") != CANONICAL_LANGUAGE:
        r.fail(f"ytmeta.merge_snippet did not set defaultLanguage="
               f"{CANONICAL_LANGUAGE!r}")
    if r.examined == 0:
        r.fail("examined nothing")
    return r


def v20_cadence_schedule() -> Result:
    """The cadence raise cannot disturb anything already scheduled — proven.

    THE FAILURE THIS EXISTS TO CATCH LOOKS EXACTLY LIKE SUCCESS. Fourteen
    episodes are uploaded, private and dated, running Sunday and Tuesday at
    10:00 Central gaplessly through 2026-10-20. A cadence change that re-dated,
    re-ordered or doubled up one of those slots would produce a perfectly
    healthy-looking log and a channel that published twice on a Sunday and went
    silent the following week. Nothing else in the repo would notice.

    So this validator does not assert a policy; it re-derives the schedule and
    compares:

      * **Every dated row keeps its date.** The slot allocator is re-run against
        the real ledger at the CURRENT cadence, and no slot it hands out may
        collide with, precede, or duplicate a date already on the calendar.
      * **The new slots continue the run rather than restarting it.** The first
        newly-allocated slot must fall strictly after the last existing one.
      * **The weekday ladders are long enough for the cadence** — long-form and
        Shorts both — because wrapping round would stack two videos on one
        morning and call it a cadence increase.
      * **No slot lands on a measured-weak day.** Wednesday and Thursday
        underperform for long-form, and no cadence the ceiling allows may reach
        them.
      * **The queue-depth guard actually governs the raise**, and refuses when
        the queue is empty rather than passing an empty loop.

    Hard-fails when it examines zero items.
    """
    r = Result("V20 cadence-schedule")
    sys.path.insert(0, str(ROOT / "loop"))
    import backfill                                      # noqa: PLC0415
    import cadence as C                                  # noqa: PLC0415
    import shorts_lane                                   # noqa: PLC0415
    import ledger as L                                   # noqa: PLC0415
    from datetime import datetime, timezone              # noqa: PLC0415

    per_week = C.effective()
    cfg = config()
    ceiling = int(cfg["cadence"].get("ceiling", 4))

    # ---- the ladders are long enough, and never reach a weak day --------
    r.examined += 1
    try:
        days = backfill.weekdays_for(ceiling)
        weak = {2, 3}                       # Wednesday, Thursday
        on_weak = sorted(weak & set(days))
        if on_weak:
            r.fail(f"the publish ladder reaches weekday(s) {on_weak} at the "
                   f"{ceiling}/week ceiling; Wednesday and Thursday are the "
                   f"two measured-weak days and no cadence may use them")
    except backfill.CadenceExceedsLadder as e:
        r.fail(f"the publish weekday ladder cannot carry the {ceiling}/week "
               f"ceiling: {e}")

    r.examined += 1
    shorts_week = C.shorts_effective()
    try:
        rungs = shorts_lane.slot_ladder(shorts_week)
        if len(set(rungs)) != len(rungs):
            r.fail(f"the Shorts evening ladder repeats a rung at "
                   f"{shorts_week}/week: two Shorts would share one slot")
        outside = sorted({h for _, h in rungs if not 18 <= h <= 21})
        if outside:
            r.fail(f"Shorts slot hour(s) {outside} fall outside the 18:00-21:00 "
                   f"evening peak; a Short on the long-form schedule lands in "
                   f"the worst part of its own day")
        if backfill.PUBLISH_HOUR_LOCAL in {h for _, h in rungs}:
            r.fail("a Shorts slot uses the long-form publish hour")
    except shorts_lane.ShortsCadenceExceedsLadder as e:
        r.fail(f"the Shorts ladder cannot carry {shorts_week}/week: {e}")

    # ---- nothing already dated may move -------------------------------
    tail = C.scheduled_tail()
    taken = {row["scheduled_publish_at"] for row in tail}
    led = L.load()
    if tail:
        last = tail[-1]["when"]
        # ONE ALLOCATION PER DOMAIN, ON ITS OWN DAYS. This block used to draw
        # from the whole ladder and require every new slot to fall after the
        # LAST dated episode. That was right while one domain held every
        # publish day and became wrong the moment a second was woven in on days
        # the first never uses: a materials Monday in September legitimately
        # precedes the last deep-sea Sunday in October, and the old rule read
        # the weave as the run being reopened.
        #
        # The protection it was really giving is kept and made STRONGER: no
        # allocated slot may collide with a dated one, no slot may go to two
        # domains, each domain's slots must land on its OWN days, the day-sets
        # must be disjoint, nothing may reach Wednesday or Thursday, and the
        # minimum lead time must hold so the owner can still watch an episode
        # through before it airs.
        cfg_now = config()
        try:
            split = backfill.domain_weekdays(cfg_now, per_week)
        except Exception as e:                             # noqa: BLE001
            split = {}
            r.examined += 1
            r.fail(f"domain_weekdays failed at {per_week}/week: {e}")

        live = {d: days for d, days in split.items() if days}
        r.examined += 1
        if not live:
            r.fail(f"no domain holds a publish day at {per_week}/week")
        seen_days: dict[int, str] = {}
        for d, days in live.items():
            for wd in days:
                r.examined += 1
                if wd in seen_days and seen_days[wd] != d:
                    r.fail(f"weekday {wd} is assigned to both {seen_days[wd]} "
                           f"and {d}; two domains sharing a publish day is how "
                           f"they double-book each other")
                seen_days[wd] = d
                if wd in {2, 3}:
                    r.fail(f"{d} is assigned weekday {wd} (Wednesday/Thursday), "
                           f"the two measured-weak days")

        allocated: set[str] = set()
        for d, days in live.items():
            fresh = backfill.schedule_for(led, max(2, per_week), per_week,
                                          domain=d)
            for when in fresh:
                r.examined += 1
                stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if stamp in taken:
                    r.fail(f"the allocator handed {d} the slot {stamp}, which "
                           f"{[t['slug'] for t in tail if t['scheduled_publish_at'] == stamp]} "
                           f"already holds — a cadence change must never "
                           f"re-date or double-book a scheduled episode")
                if stamp in allocated:
                    r.fail(f"{stamp} was handed to two domains in one pass")
                allocated.add(stamp)
                wd = when.astimezone(backfill.PUBLISH_TZ).weekday()
                if wd not in days:
                    r.fail(f"{d} was given {stamp}, a weekday ({wd}) outside "
                           f"its own allocation {tuple(days)}")
                lead = (when - datetime.now(timezone.utc)).total_seconds() / 3600
                if lead < backfill.MIN_LEAD_HOURS - 1:
                    r.fail(f"{stamp} is only {lead:.1f}h away, inside the "
                           f"{backfill.MIN_LEAD_HOURS}h minimum lead — the "
                           f"owner cannot watch it through before it airs")
        r.note(f"{len(tail)} episode(s) dated through {last:%Y-%m-%d}; "
               f"{len(live)} domain(s) allocating on disjoint days "
               f"{ {d: tuple(v) for d, v in live.items()} } at {per_week}/week")
    else:
        # No dated tail is legitimate only when the channel has none. Do NOT
        # let that pass silently as zero examined.
        r.examined += 1
        if any(row.get("scheduled_publish_at") for row in led["published"]):
            r.fail("the ledger carries scheduled rows but none resolved as a "
                   "future slot — the tail reader is not reaching what it "
                   "governs")
        r.note("no episode is currently scheduled ahead")

    # ---- Shorts slots do not collide either ---------------------------
    sled = shorts_lane.load_ledger()
    s_taken = {row["scheduled_publish_at"] for row in sled["published"]
               if row.get("scheduled_publish_at")}
    for when in shorts_lane.schedule_for(sled, max(4, shorts_week)):
        r.examined += 1
        stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if stamp in s_taken:
            r.fail(f"the Shorts allocator handed out {stamp}, which a Short "
                   f"already holds")

    # ---- the queue-depth guard governs the raise ----------------------
    r.examined += 1
    src = (ROOT / "loop" / "cadence.py").read_text()
    seg = src.split("def effective")[1].split("\ndef ")[0]
    if "queue_supports" not in seg:
        r.fail("cadence.effective() does not consult queue_supports(); the "
               "cadence raise is ungated and would publish faster than the "
               "queue can refill")
    r.examined += 1
    ok, why = C.queue_supports(10_000)      # a cadence nothing could sustain
    if ok:
        r.fail("queue_supports() approved 10,000 videos a week — the "
               "queue-depth guard does not actually bound anything")
    if "floor" not in why and "ZERO" not in why:
        r.fail(f"the queue-depth refusal does not say why: {why!r}")

    if r.examined == 0:
        r.fail("examined ZERO cadence-schedule cases")
    return r


def v26_state_files_readable() -> Result:
    """Every committed loop/state/*.json parses, and carries no conflict marker.

    THE GAP THIS CLOSES. On 2026-09-03 (run 33783829147) a rebase conflict on
    loop/state/quota.json was committed to the working tree as a DIFF -- three
    lines of `<<<<<<<`, `=======`, `>>>>>>>` inside what every lane reads as
    JSON. Nothing in the repo looked at those files as a class, so the defect
    was found by the next lane crashing on it, several steps later, with a
    traceback that named neither the file nor git.

    bin/loop-stage.sh now aborts an unresolved rebase before it can leave that
    behind, which is the fix; this is the guard that proves the fix held. The
    two are deliberately different components -- a lane that stops producing
    corrupt state and a check that no corrupt state exists are not the same
    claim, and only the second one keeps being true after someone edits the
    first.
    """
    r = Result("V26 state-readable")
    state_dir = ROOT / "loop" / "state"
    for path in sorted(state_dir.rglob("*.json")):
        r.examined += 1
        try:
            text = path.read_text()
        except OSError as e:
            r.fail(f"loop/state/{path.relative_to(state_dir)} cannot be read: {e}")
            continue
        rel = path.relative_to(state_dir)
        marker = next((ln for ln in text.splitlines()
                       if ln.startswith(("<" * 7, "=" * 7, ">" * 7))), None)
        if marker is not None:
            r.fail(f"loop/state/{rel} contains a git conflict marker "
                   f"({marker[:12]!r}) — it is a diff, not JSON. Every lane "
                   f"that reads it will crash, and the lane that wrote it "
                   f"pushed a broken file to main.")
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            r.fail(f"loop/state/{rel} is not valid JSON: {e}")
    if r.examined == 0:
        r.fail("found no JSON under loop/state/ — this validator proved "
               "nothing, and loop/state/ is never legitimately empty in this "
               "repo")
    return r


def run_reach() -> tuple[bool, list[dict]]:
    """The post-publish reach validators. Separate from the render gate."""
    results = [v16_caption_track(), v17_localizations(),
               v18_default_language(), v19_snippet_merge(),
               v26_state_files_readable(), v41_discovery_metadata()]
    return all(r.ok for r in results), [r.as_dict() for r in results]


def probe(url: str, timeout: int = 20) -> tuple[int, str]:
    """Return (status_code, reason). 0 means the host could not be reached."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0 Safari/537.36"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 405 and method == "HEAD":
                continue          # some servers reject HEAD; retry with GET
            return e.code, "http error"
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, socket.gaierror):
                return 0, "DNS does not resolve - the domain does not exist"
            if method == "GET":
                return 0, f"{type(reason).__name__}"
        except Exception:
            if method == "GET":
                return 0, "unreachable"
    return 0, "unreachable"


# --------------------------------------------------- V21 no-boilerplate

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def v21_no_boilerplate() -> Result:
    """No narration sentence may be a VERBATIM repeat across two scripts.

    2026-09-03: ten of twenty scripts carried the identical sentence "The rest
    of this video follows that question through the actual environmental
    constraints described by NOAA, MBARI, Smithsonian, and Woods Hole sources
    in the companion article" - the only verbatim repeat in a 179-heading
    corpus where 169 headings are unique. It pointed at an off-platform
    article the viewer cannot click, and in five episodes it was not even
    true. That is exactly the "generic template / mass production" signal
    YouTube's 15 July 2025 inauthentic-content policy names.

    There was no single generator to patch - `author.py` does not emit this
    text, so the durable fix is this guard, not a template edit. Any sentence
    of 8+ words that is byte-identical across two different scripts' narration
    fails, before it ever reaches a render.

    Hard-fails when it examines zero scripts.
    """
    r = Result("V21 no-boilerplate")
    seen: dict[str, str] = {}
    for p in sorted((ROOT / "scripts").glob("*.md")):
        r.examined += 1
        text = re.sub(r"\s+", " ", spoken(p)).strip()
        for sent in _SENT_SPLIT.split(text):
            sent = sent.strip()
            words = sent.split()
            if len(words) < 8:
                continue
            if sent in seen and seen[sent] != p.name:
                r.fail(f"{p.name} and {seen[sent]} share a verbatim narrated "
                       f"sentence ({len(words)} words): {sent[:100]!r}")
            else:
                seen.setdefault(sent, p.name)
    return r


# ------------------------------------------------ V22 producer-notes-2p

_META_PHRASES = [
    # "the channel" alone is deliberately NOT here, 2026-09-03: it false-
    # positived on "the carrier mobility in the channel" — a MOSFET's own
    # physical channel, real materials-and-manufacturing vocabulary that
    # deep sea never had to share a word with. The specific ways ep09 talked
    # about the CHANNEL-AS-BUSINESS are still covered below; a guard that
    # cannot tell "the channel" (business) from "the channel" (a
    # semiconductor's own channel) is a guard that cannot reach a real
    # materials script at all.
    #
    # NOT "this channel": it is real prose in scripts/01 ("how this channel
    # avoids becoming a slideshow") that would newly fail V22 for an already
    # scheduled, protected episode (airs 2026-09-08). Catching it is
    # correct; fixing it is not this change's job — this repo's own rule is
    # that the 14 scheduled episodes are not re-edited, and a validator
    # expansion that starts failing protected content is worse than the gap
    # it closes. Left for a dedicated pass with the owner's sign-off.
    "our channel", "the channel's", "the channel gains",
    "the channel benefits", "for a channel trying", "channel strategy",
    "channel's business",
    "monetiz", "watch time", "topic intelligence",
    "editorial reason", "pinned comment can", "engagement while",
    "production queue", "follow-up episodes with a real editorial",
    "the audience gets", "the audience helps",
    "algorithm", "click-through", "subscriber count",
]


def v22_producer_notes_second_person() -> Result:
    """Narration never talks ABOUT the channel's strategy in third person.

    2026-09-02: ep09 alone spoke nine sentences of producer-facing channel
    strategy to the viewer - "That is the kind of monetization-minded choice
    worth keeping", "The channel gains engagement while reinforcing the
    scientific boundary." A narrator reading channel strategy aloud is a
    different defect from an unsourced number, but it is still something no
    viewer should be hearing.

    The fix keeps the transparency (it is the channel's voice) but requires it
    stay addressed to the viewer, not the production. This guard cannot verify
    grammatical person, but it can hard-ban the specific vocabulary that marks
    prose as being ABOUT the channel's business rather than FOR the person
    watching, and it is exactly the vocabulary the 2026-09-02 audit found.

    Hard-fails when it examines zero scripts.
    """
    r = Result("V22 producer-notes-second-person")
    for p in sorted((ROOT / "scripts").glob("*.md")):
        r.examined += 1
        text = spoken(p).lower()
        for phrase in _META_PHRASES:
            if phrase in text:
                r.fail(f"{p.name}: narration contains channel-strategy "
                       f"language {phrase!r} — rewrite it addressed to the "
                       f"viewer, not the production")
    return r


# ------------------------------------------- V23 chapters-yt-compliant

def v23_chapters_compliant() -> Result:
    """Every chapter list this repo would actually SEND to YouTube is legal.

    2026-09-02: `loop/upload.py` built its chapter list by regexing `##
    Chapters` out of the script and sending it as-is. Two defects: the
    timestamps are the script's ESTIMATE, not the render's real timing (ep08
    said 7:48 for a chapter the render actually reaches at 8:45), and 11 of 20
    scripts contained a sub-10-second "Title card" chapter — YouTube discards
    the ENTIRE list, not just the short entry, the moment one chapter is under
    10 seconds. `loop/upload.py:build_chapters()` now prefers
    `captions/<slug>.chapters.txt` (real timing) and falls back to a corrected
    derivation from the script that drops "Title card" and merges any
    remaining sub-10s gap. This validator proves the OUTPUT of that function
    is legal for every script in the repo, not just the code path that
    produces it.

    Hard-fails when it examines zero scripts.
    """
    r = Result("V23 chapters-yt-compliant")
    sys.path.insert(0, str(ROOT / "loop"))
    import upload as up                                   # noqa: PLC0415
    for p in sorted((ROOT / "scripts").glob("*.md")):
        r.examined += 1
        text = p.read_text(encoding="utf-8")
        chapters = up.build_chapters(p.stem, text)
        if not chapters:
            r.note(f"{p.name}: no ## Chapters section (nothing to check)")
            continue
        times = [up._parse_ts(c.split(" ", 1)[0]) for c in chapters]  # noqa: SLF001
        if times[0] != 0:
            r.fail(f"{p.name}: first chapter is not at 0:00 "
                   f"({chapters[0]!r}) — YouTube requires it")
        for a, b, label in zip(times, times[1:], (c.split(" ", 1)[1] for c in chapters)):
            if b - a < up.YT_MIN_CHAPTER_S:
                r.fail(f"{p.name}: {label!r} is only {b - a}s after the "
                       f"previous chapter — under the {up.YT_MIN_CHAPTER_S}s "
                       f"floor that makes YouTube discard the WHOLE list")
        if any(c.split(" ", 1)[1] == "Title card" for c in chapters):
            r.fail(f"{p.name}: chapter list still contains a bare 'Title "
                   f"card' entry")
    return r


# ------------------------------------------------- V24 render-duration-floor

def v24_render_duration_floor() -> Result:
    """No NEW render is under the owner's hard 10-minute floor.

    2026-09-03 decision: every episode from here exceeds 10 minutes, on
    RENDERED DURATION as well as narration word count — a word-count floor
    alone would not have caught the original defect, which was that a word
    count and a render can disagree once the wpm assumption feeding the word
    count is wrong. The existing 20 episodes (7.5-8.9 minutes, rendered
    2026-08-30, before this rule existed) are NOT re-rendered — that is the
    owner's decision, recorded in loop/config.json
    retention.runtime_floor_grandfathered by name, which is what lets this
    validator hold the line going forward without re-litigating the past.

    Exempt (examines zero, does not fail) when every render on disk is
    grandfathered — that is the honest state of a channel with no new
    long-form render yet, not a validator that cannot reach what it governs.
    Shorts are exempt outright: they never had a floor to begin with.
    """
    r = Result("V24 render-duration-floor")
    sys.path.insert(0, str(ROOT / "loop"))
    import durations as D                                 # noqa: PLC0415
    cfg = config()
    floor_min = float(cfg["retention"]["runtime_floor_minutes"])
    grandfathered = set(cfg["retention"]["runtime_floor_grandfathered"])
    any_new = False
    for p in sorted((ROOT / "renders").glob("*-final.mp4")) \
            if (ROOT / "renders").exists() else []:
        slug = p.name[:-len("-final.mp4")]
        if slug in grandfathered:
            continue
        any_new = True
        r.examined += 1
        secs = D.ffprobe_duration(p)
        if secs is None:
            r.fail(f"{slug}: could not read a duration from {p.name}")
            continue
        if secs < floor_min * 60:
            r.fail(f"{slug}: rendered {secs / 60:.2f} min, under the "
                   f"{floor_min}-minute hard floor")
    r.exempt = not any_new
    if r.exempt:
        r.note("every render on disk is grandfathered (predates the "
               "2026-09-03 floor) — nothing new to check yet")
    return r


def v25_domain_abstraction() -> Result:
    """HARD. No rendering path may reach a domain without a declared
    palette, structural device and source allowlist.

    2026-09-03, added when materials-and-manufacturing became a second
    published domain. Before this, `visuals/design.py` hardcoded the ocean
    palette as bare module constants and `loop/author.py` hardcoded the
    NOAA/MBARI source list — there was no domain concept for a validator to
    even check. This examines every domain the CHANNEL actually runs
    (`loop/config.json` `domains.allocation` — not the full 20-domain scored
    taxonomy, which includes niches nobody has decided to publish) and
    confirms three things hold for EACH one:

      1. `visuals/domains.py` declares a palette AND a structural device.
      2. `visuals/design.py`, imported as a subprocess with `HWK_DOMAIN` set
         to this domain, actually resolves to THAT domain's palette — not a
         silent fallback to deep sea's. This is the "no rendering path can
         reach a domain without..." half of the guard: it does not just read
         the registry, it proves the registry is actually wired to what
         renders a frame.
      3. `loop/domain_sources.py` declares a non-empty source allowlist.

    Hard-fails on zero domains examined — an empty `domains.allocation`
    would make this validator vacuously green, which is worse than not
    running it, per this repo's own Rule 0.
    """
    r = Result("V25 domain-abstraction")
    cfg = config()
    sys.path.insert(0, str(ROOT / "loop"))
    sys.path.insert(0, str(ROOT / "visuals"))
    import domains as loop_domains                        # noqa: PLC0415
    import domain_sources                                  # noqa: PLC0415
    active = list(loop_domains.config_domains(cfg)["allocation"])
    if not active:
        r.fail("loop/config.json domains.allocation is empty — no domain "
               "examined. This validator refuses to pass vacuously.")
        return r
    for name in active:
        r.examined += 1
        # 1. visuals/domains.py: palette + device declared.
        vis = subprocess.run(
            [PY, "-c",
             "import sys; sys.path.insert(0, 'visuals'); import domains as d; "
             f"d.require_declared({name!r})"],
            cwd=ROOT, capture_output=True, text=True)
        if vis.returncode != 0:
            r.fail(f"{name}: visuals/domains.py has no declared palette+device "
                   f"— {vis.stderr.strip().splitlines()[-1] if vis.stderr else 'error'}")
            continue
        # 2. visuals/design.py, imported for THIS domain via HWK_DOMAIN,
        #    resolves to this domain's own palette — proves the wiring, not
        #    just the registry.
        probe = subprocess.run(
            [PY, "-c",
             "import design; print(design.DOMAIN); print(design.INK)"],
            cwd=str(ROOT / "visuals"),
            env={**os.environ, "HWK_DOMAIN": name},
            capture_output=True, text=True)
        if probe.returncode != 0:
            r.fail(f"{name}: visuals/design.py failed to import under "
                   f"HWK_DOMAIN={name} — {probe.stderr.strip().splitlines()[-1] if probe.stderr else 'error'}")
            continue
        lines = probe.stdout.strip().splitlines()
        if not lines or lines[0] != name:
            r.fail(f"{name}: visuals/design.py resolved DOMAIN={lines[0] if lines else '?'} "
                   f"instead of {name} — a render for this domain would silently "
                   f"use the wrong palette")
            continue
        try:
            ink_seen = eval(lines[1])  # noqa: S307 -- our own stdout, a tuple literal
        except Exception:
            ink_seen = None
        # A fresh subprocess again, not an in-process import: `loop/domains.py`
        # is already cached in sys.modules under the name "domains" (imported
        # at the top of this file), and `visuals/domains.py` happens to share
        # that filename — an in-process `import domains` here would silently
        # return the WRONG module rather than raise, which is exactly the
        # kind of drift this validator exists to catch, not commit itself.
        expect = subprocess.run(
            [PY, "-c",
             f"import domains as d; print(tuple(d.palette({name!r})['INK']))"],
            cwd=str(ROOT / "visuals"), capture_output=True, text=True)
        expected_ink = None
        if expect.returncode == 0 and expect.stdout.strip():
            try:
                expected_ink = eval(expect.stdout.strip())  # noqa: S307
            except Exception:
                expected_ink = None
        if expected_ink is not None and ink_seen != expected_ink:
            r.fail(f"{name}: rendered INK {ink_seen} does not match the "
                   f"declared palette {expected_ink} — the registry and the "
                   f"renderer have drifted apart")
            continue
        # 3. loop/domain_sources.py: non-empty source allowlist.
        try:
            names = domain_sources.for_domain(name)
        except KeyError as e:
            r.fail(f"{name}: {e}")
            continue
        if not names:
            r.fail(f"{name}: loop/domain_sources.py allowlist is empty")
    return r


def v27_lanes_see_every_domain() -> Result:
    """Every lane that schedules or narrates must see EVERY domain's queue.

    RENUMBERED from V21 on 2026-09-04: main had already taken 21-26. The
    defect it guards is this repo's most persistent - a component reading
    `research/publish_order.json` by name, so a second domain's whole queue is
    invisible to it. It has now been found in six places: bin/batch-session.sh,
    bin/loop-stage.sh, cadence.publish_order() and three sites in
    loop/backfill.py, one of which only surfaced at runtime after a dry run
    had passed. The visible symptom was a runway reading "0 publishable
    episode(s) of 22 on disk" while eighteen scored, scripted and planned
    materials episodes sat on the shelf.

    Asserted BEHAVIOURALLY, not by grepping for the filename: a first attempt
    did grep loop/*.py and produced nine failures that were almost all
    docstring prose, and it would still have flagged cadence.PUBLISH_ORDER,
    which is legitimate - cadence reads the primary file for its staleness and
    shape checks and merges the rest on top. "Does this module name the file"
    is not the invariant. "Can it see a second domain" is.

    Hard-fails when it examines zero items.
    """
    r = Result("V27 lanes-see-domains")
    import json as _json                                   # noqa: PLC0415
    import importlib                                       # noqa: PLC0415

    files = sorted((ROOT / "research").glob("publish_order*.json"))
    r.examined += 1
    if not files:
        r.fail("no research/publish_order*.json files at all")
        return r

    # THE SHORTS LANE WAS THE HOLE. V27 asserted that cadence and backfill see
    # every domain and that no bin/*.sh names a single publish-order file, and
    # it never looked at loop/shorts_lane.py -- which read
    # research/publish_order.json by name. The result was a Shorts library of 51
    # on 2026-09-05, every one deep sea, while eleven rendered materials
    # episodes had none. A guard that governs three call sites out of four is
    # not a guard, so this checks the LANE'S OWN OUTPUT rather than its source.
    r.examined += 1
    try:
        import shorts_lane as _sl                          # noqa: PLC0415
        import domains as _dom                             # noqa: PLC0415
        # `have` is stubbed to True so this measures which slugs the lane can
        # SEE, not which have material cut on this particular machine.
        # SEEN, NOT PENDING. `pending()` excludes every episode whose Short is
        # already published, so a domain whose Shorts are all done - deep sea,
        # from 2026-09-14 - read as a domain the lane could not see, and the
        # breaker tripped on a finished job. What the lane can SEE is what it
        # iterates: its pending set plus the slugs its own ledger says are done.
        seen = {_dom.domain_of_slug(s)
                for s in _sl.pending(have=lambda _s: True)}
        seen |= {_dom.domain_of_slug(r_["slug"])
                 for r_ in _sl.load_ledger()["published"]}
        seen.discard(None)
        alloc = set(_dom.allocation(config()))
        missing = alloc - seen
        # A domain with nothing published yet legitimately contributes nothing.
        started = {_dom.domain_of_slug(s) for s in _dom.by_slug()}
        missing &= started
        if missing:
            r.fail(f"loop/shorts_lane.py cannot see any episode in "
                   f"{', '.join(sorted(missing))}. It is reading one domain's "
                   f"publish order rather than every domain's, so that niche "
                   f"gets no Shorts at all.")
    except Exception as e:                                 # never mask the rest
        r.fail(f"could not ask loop/shorts_lane.py which domains it sees: {e}")

    # AND THE R2 SHELF. loop/r2.py:_publish_slugs() drives BOTH the render push
    # and the Shorts push, and read one file by name too -- so nothing from
    # materials had ever been shelved, and the two cloud lanes that publish
    # from R2 were structurally incapable of ever seeing that niche. Third
    # instance of this defect in one afternoon, which is why the check is now
    # per-module rather than per-symptom.
    r.examined += 1
    try:
        import r2 as _r2                                   # noqa: PLC0415
        import domains as _dom2                            # noqa: PLC0415
        seen2 = {_dom2.domain_of_slug(s) for s in _r2._publish_slugs()}
        seen2.discard(None)
        gap = set(_dom2.allocation(config())) - seen2
        if gap:
            r.fail(f"loop/r2.py cannot shelve anything in "
                   f"{', '.join(sorted(gap))}. Both cloud lanes publish from "
                   f"R2, so that niche can never reach YouTube through them.")
    except Exception as e:
        r.fail(f"could not ask loop/r2.py which domains it shelves: {e}")

    per_file = {}
    for path in files:
        per_file[path.name] = {row.get("slug") for row in
                               (_json.loads(path.read_text()).get("queue") or [])
                               if row.get("slug")}

    # A ROW REFUSED ON READ WAS SEEN. Since 2026-09-25 (#127/#128)
    # batch_queue refuses a row that asks the same question as an episode
    # already made, or another channel's topic, and names every refusal in
    # refused_entries() with its reason. Such a row is absent from the merged
    # queue BY A DECISION, not because a lane reads one file by name - which
    # is the only thing this validator exists to catch. Without this, every
    # refusal read as a blind lane: V27 failed 20 times on 2026-09-26 over
    # rows the queue had correctly refused, and the next Monday would have
    # tripped the breaker on it. Each refused slug must still be NAMED with a
    # reason; a row that is merely missing still fails.
    try:
        import batch_queue as _bq_ref  # noqa: PLC0415 - every V27 probe imports lazily so one module that fails to import fails only its own probe
        refused_rows = _bq_ref.refused_entries()
    except Exception as e:  # noqa: BLE001 - reported as a V27 failure below; one broken probe must never mask the other validators
        refused_rows = []
        r.fail(f"loop/batch_queue.py could not list its refused rows: {e}")
    refused = set()
    for row in refused_rows:
        r.examined += 1
        if not row.get("slug") or not (row.get("why") or row.get("killed_by")):
            r.fail(f"a refused queue row carries no slug or no reason: "
                   f"{ {k: row.get(k) for k in ('slug', 'killed_by', 'why')} }")
            continue
        refused.add(row["slug"])
    per_file = {f: slugs - refused for f, slugs in per_file.items()}

    # ---- no bin/ script names a single publish-order file ----------------
    for sh in sorted((ROOT / "bin").glob("*.sh")):
        r.examined += 1
        bad = [n for n, line in enumerate(sh.read_text().splitlines(), 1)
               if "research/publish_order" in line
               and not line.lstrip().startswith("#")
               and "publish_order*" not in line]
        if bad:
            r.fail(f"{sh.name} line(s) {bad} name a single publish-order file; "
                   f"use loop/batch_queue.py or a publish_order*.json glob.")

    # ---- the merged queue is a superset of every file --------------------
    r.examined += 1
    try:
        import batch_queue                                 # noqa: PLC0415
        merged = set(batch_queue.queued_slugs())
        for fname, slugs in per_file.items():
            missing = slugs - merged
            if missing:
                r.fail(f"{fname}: {len(missing)} slug(s) absent from the merged "
                       f"queue, e.g. {sorted(missing)[:3]}")
    except Exception as e:                                 # noqa: BLE001
        r.fail(f"loop/batch_queue.py could not produce a merged queue: {e}")

    # ---- an empty glob must raise, not report an empty queue -------------
    r.examined += 1
    try:
        import batch_queue as _bq                          # noqa: PLC0415
        real = _bq.ROOT
        try:
            _bq.ROOT = ROOT / "loop" / "__no_such_root__"
            try:
                _bq.queued_slugs()
                r.fail("queued_slugs() returned normally with no publish-order "
                       "files; an empty queue must be distinguishable from a "
                       "missing one")
            except _bq.NoPublishOrder:
                pass
        finally:
            _bq.ROOT = real
    except Exception as e:                                 # noqa: BLE001
        r.fail(f"could not exercise the empty-glob guard: {e}")

    # ---- the SCHEDULING modules can actually see a second domain ---------
    r.examined += 1
    try:
        import cadence as _cad                             # noqa: PLC0415
        importlib.reload(_cad)
        seen = set(_cad.publish_order())
        for fname, slugs in per_file.items():
            missing = slugs - seen
            if missing:
                r.fail(f"cadence.publish_order() cannot see {len(missing)} "
                       f"slug(s) from {fname}, e.g. {sorted(missing)[:3]}. "
                       f"Every runway and cadence decision would be made as "
                       f"though that domain's queue did not exist.")
    except Exception as e:                                 # noqa: BLE001
        r.fail(f"cadence.publish_order() raised: {e}")

    r.examined += 1
    try:
        import backfill as _bf                             # noqa: PLC0415
        importlib.reload(_bf)
        for fname, slugs in per_file.items():
            if not slugs:
                continue
            probe = sorted(slugs)[0]
            try:
                _bf.question_for(probe)
            except Exception:                              # noqa: BLE001
                r.fail(f"backfill.question_for({probe!r}) fails for a slug from "
                       f"{fname}. That question becomes the video title, so the "
                       f"upload would fail after the render was paid for.")
    except Exception as e:                                 # noqa: BLE001
        r.fail(f"backfill could not be exercised: {e}")
    return r


def v28_lane_interpreters() -> Result:
    """Each lane is invoked with the interpreter that lane's packages live in.

    THE FAILURE THIS CATCHES READS AS A BROKEN NARRATOR. Voice has had its own
    environment since the lane was built - bin/run-batch.sh calls
    .venv-tts/bin/python, because torch, chatterbox-tts and soundfile are ~1.3
    GB and have no business in the render venv. bin/batch-session.sh called
    `$PY voice/narrate_all.py`, i.e. the RENDER venv, and narration died on
    `ModuleNotFoundError: No module named 'soundfile'`. CLAUDE.md's first named
    trap is exactly this; it has now cost PIL twice, numpy once and soundfile
    once.

    Asserted from the SCRIPT TEXT, not the filesystem: this also runs in
    Actions, where no .venv-tts exists and never should.

    Hard-fails when it examines zero items.
    """
    r = Result("V28 lane-interpreters")
    import re as _re                                       # noqa: PLC0415

    RENDER_VENV = ".venv/bin/python"
    TTS_VENV = ".venv-tts/bin/python"

    for sh in sorted((ROOT / "bin").glob("*.sh")):
        body = sh.read_text()
        lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("#")]
        r.examined += 1

        varmap = {}
        for ln in lines:
            m = _re.match(r"\s*([A-Z_][A-Z0-9_]*)=(\S*/bin/python\S*)\s*$", ln)
            if m:
                varmap[m.group(1)] = m.group(2)

        def interp(ln):
            m = _re.search(r"(?:\$\{?([A-Z_][A-Z0-9_]*)\}?|(\S*/bin/python\S*))\s+"
                           r"(\S+\.py)", ln)
            if not m:
                return None, None
            name = varmap.get(m.group(1)) if m.group(1) else m.group(2)
            return name, m.group(3)

        for ln in lines:
            path, script = interp(ln)
            if not path or not script:
                continue
            if script.startswith("voice/") and path.endswith(RENDER_VENV):
                r.fail(f"{sh.name} runs {script} with {path}, the RENDER venv. "
                       f"Voice needs torch/chatterbox-tts/soundfile from "
                       f"{TTS_VENV}; this fails as ModuleNotFoundError and "
                       f"reads as a broken narrator.")
            if script.startswith("visuals/") and TTS_VENV in path:
                r.fail(f"{sh.name} runs {script} with {path}, the VOICE venv. "
                       f"Rendering needs PIL and numpy from {RENDER_VENV}.")

        pass

    # ---- no cloud lane may hardcode a venv interpreter -------------------
    # loop/score.py bound `PY = ROOT/".venv"/"bin"/"python"` and ran in
    # Actions, so `loop · Sat 06:00 · score` died every Saturday on
    # FileNotFoundError: .venv/bin/python - a scheduled lane failing not
    # because the ranking was wrong but because it was told to use a binary
    # that only exists on the Mac. The rule is narrow on purpose: a venv path
    # ASSIGNED TO A NAME and handed to subprocess is a bug; the same string
    # inside an unblock message is correct, because that instruction really is
    # for the Mac (see captions_lane.RECONSENT).
    for py in sorted((ROOT / "loop").glob("*.py")):
        if py.name == "validate.py":
            continue
        pybody = py.read_text()
        if "subprocess" not in pybody:
            continue
        r.examined += 1
        if _re.search(r"^\s*[A-Za-z_]+\s*=\s*[^#\n]*\.venv[/\"']", pybody, _re.M) \
           and "sys.executable" not in pybody:
            r.fail(f"loop/{py.name} binds a .venv interpreter and runs "
                   f"subprocess without any sys.executable fallback. That path "
                   f"exists on the Mac and nowhere else, so a scheduled run "
                   f"dies on FileNotFoundError. Resolve it the way "
                   f"loop/tests/run_all.py does.")

    for sh in sorted((ROOT / "bin").glob("*.sh")):
        lines = [ln for ln in sh.read_text().splitlines()
                 if not ln.lstrip().startswith("#")]
        body = sh.read_text()
        varmap = {}
        for ln in lines:
            m = _re.match(r"\s*([A-Z_][A-Z0-9_]*)=(\S*/bin/python\S*)\s*$", ln)
            if m:
                varmap[m.group(1)] = m.group(2)
        if any(ln for ln in lines if "voice/" in ln and ".py" in ln):
            if not any(TTS_VENV in v for v in varmap.values()) and TTS_VENV not in body:
                r.fail(f"{sh.name} runs a voice/ entrypoint but never names "
                       f"{TTS_VENV}. The two environments are separate and the "
                       f"script that drives voice must say so.")
    return r


def v29_material_image_rights() -> Result:
    """No picture reaches a frame without a verified public-domain record.

    HARD, unlike V6. V6 is soft because a missing bibliography line is a
    provenance-record gap and the pipeline still cannot speak a number it was
    not given. This is different in kind: a `material_image` beat puts somebody
    else's photograph on a monetised channel, and CLAUDE.md's one absolute
    imagery rule is that stripping or omitting attribution is the thing this
    pipeline may not do.

    Every material_image beat must resolve to a record with a non-empty
    credit_line, item_url, licence and sha256; the licence must be a
    public-domain or CC0 tag (CC-BY is NOT a public-domain dedication and this
    channel is monetised); the file must still hash to what was rights-checked;
    and the on-screen label must be non-empty, because CONTRACT.md rule 1 is
    that the picture is captioned with a word the viewer is hearing.

    Hard-fails when it examines zero items.
    """
    r = Result("V29 material-image rights")
    import hashlib as _h                                   # noqa: PLC0415

    beats = []
    for path in sorted((ROOT / "plans").glob("*.json")):
        try:
            plan = read_json(path)
        except Exception as e:                             # noqa: BLE001
            r.examined += 1
            r.fail(f"{path.name}: unreadable ({e})")
            continue
        for i, b in enumerate(plan):
            if b.get("segment") == "material_image":
                beats.append((path.name, i, b))

    if not beats:
        r.examined += 1
        r.fail("no material_image beat in any plan, so this validator proved "
               "nothing. Either the materials image lane never ran "
               "(visuals/plan_materials_images.py --all --apply) or the plans "
               "were regenerated over it; an empty loop must not pass.")
        return r

    man_path = ROOT / "channel" / "imagery" / "materials.json"
    if not man_path.exists():
        r.examined += 1
        r.fail(f"{len(beats)} material_image beat(s) reference a manifest that "
               f"does not exist: {man_path}. Every one raises at render, after "
               f"narration was paid for.")
        return r
    man = read_json(man_path)
    by_subject = {}
    for rec in man.get("index", []):
        by_subject.setdefault(rec["subject"], []).append(rec)

    PD_OK = ("public domain", "pd-", "cc0", "no restrictions")
    checked = set()
    for name, i, b in beats:
        r.examined += 1
        args = b.get("args") or {}
        subj = args.get("subject")
        recs = by_subject.get(subj)
        if not recs:
            r.fail(f"{name} beat {i}: subject {subj!r} has no verified record "
                   f"in materials.json; this raises at render.")
            continue
        rec = recs[(args.get("pick") or 0) % len(recs)]
        if not (args.get("label") or "").strip():
            r.fail(f"{name} beat {i}: no on-screen label. The picture must be "
                   f"captioned with a word the narration uses.")
        for field in ("credit_line", "item_url", "licence", "sha256", "local_file"):
            if not rec.get(field):
                r.fail(f"{name} beat {i} [{subj}]: record is missing {field!r} "
                       f"- it may not be shown.")
        lic = (rec.get("licence") or "").lower()
        if lic and not any(k in lic for k in PD_OK):
            r.fail(f"{name} beat {i} [{subj}]: licence is {rec['licence']!r}, "
                   f"which is not a public-domain dedication. This channel is "
                   f"monetised and CC-BY does not qualify.")
        lf = rec.get("local_file")
        if lf and lf not in checked:
            checked.add(lf)
            fp = ROOT / "channel" / "imagery" / lf
            if not fp.exists():
                r.fail(f"[{subj}] {lf} is not on disk")
            elif rec.get("sha256"):
                if _h.sha256(fp.read_bytes()).hexdigest() != rec["sha256"]:
                    r.fail(f"[{subj}] {lf} changed since it was rights-checked "
                           f"(sha256 differs); it may not be shown.")
    return r


def v30_cloud_visibility() -> Result:
    """Every file a lane runs must be TRACKED BY GIT, and so must its imports.

    THE DEFECT THIS EXISTS TO CATCH COST A WHOLE DAY on 2026-09-04, and it never
    once presented as itself. `visuals/footage.py`, `visuals/shorts.py` and
    `visuals/captions.py` existed only on the Mac. Nothing said so. What the
    cloud reported instead was five validators hard-failing on zero items, a
    tripped breaker, a Monday lane that had been red since 31 August, a CI suite
    quietly running nineteen files while the Mac ran twenty-one, and - once
    `assemble.py` was resolved against a copy that never had the local edits -
    a nightly render that would have died on an unrecognised argument after
    paying for narration. Six symptoms, one cause: a file the cloud could not
    see.

    "Check `git status` now and then" is not a fix. It is a habit, it is
    advisory, and it competes with everything else a person could look at. This
    is the deterministic form of the same intent - it derives what the cloud
    NEEDS from what the lanes actually invoke, and asserts git can see all of
    it.

    Two rules, both mechanical:

      A. **The import closure of every entrypoint is tracked.** An entrypoint is
         any `.py` named in `.github/workflows/*.yml` or `bin/*.sh` - the things
         a lane genuinely runs. From each, local imports are resolved against
         this repo's own directories and walked transitively. Every file
         reached must appear in `git ls-files`. Third-party and stdlib imports
         resolve to no local file and are ignored, so the rule needs no
         allowlist to stay quiet.

      B. **A tracked manifest's assets are tracked.** If a rights manifest is in
         git, the files it names must be too - that is exactly how
         `channel/imagery/materials.json` shipped while its twelve images did
         not, leaving V29 to report eleven beats whose file "is not on disk".
         The converse is deliberately NOT asserted: an UNTRACKED manifest means
         the whole subject is machine-local by design - the footage clips are
         hundreds of megabytes and belong on the Mac and in R2 - and V9-V15
         already handle that by going N/A.

    Hard-fails when it examines zero items.
    """
    r = Result("V30 cloud-visibility")
    import ast as _ast                                     # noqa: PLC0415
    import subprocess as _sp                               # noqa: PLC0415

    tracked = set(_sp.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                          text=True).stdout.split())
    r.examined += 1
    if not tracked:
        r.fail("`git ls-files` returned nothing, so this validator cannot tell "
               "tracked from untracked and proves nothing here.")
        return r

    # ---- collect entrypoints from what the lanes actually invoke ---------
    ref = re.compile(r"([a-z_][a-z_0-9]*/[a-z_0-9]+\.py)")
    entry: set[str] = set()
    # THE ROOT ITSELF MUST BE TRACKED, not only what it imports. This walked
    # bin/*.sh to find their Python entrypoints and never asked whether the
    # shell script was in git at all -- so it dutifully verified the import
    # closure of two scripts that existed on one Mac and nowhere else.
    # bin/loop-backfill-daily.sh is the lane that uploads finished videos to
    # YouTube every morning; it had never been committed, and a disk failure
    # would have taken it with no trace of what it did.
    roots: list[pathlib.Path] = []
    for d, pat in ((ROOT / ".github" / "workflows", "*.yml"), (ROOT / "bin", "*.sh")):
        for f in sorted(d.glob(pat)) if d.exists() else []:
            roots.append(f)
            entry |= set(ref.findall(f.read_text()))
    entry = {e for e in entry if (ROOT / e).exists()}

    for f in roots:
        rel = str(f.relative_to(ROOT))
        r.examined += 1
        if rel not in tracked:
            r.fail(f"{rel} is a lane entrypoint and is NOT tracked by git, so "
                   f"it exists on this machine and nowhere else. Whatever it "
                   f"does is unbacked-up, unreviewable, and invisible to every "
                   f"cloud runner.")

    r.examined += 1
    if not entry:
        r.fail("no entrypoint .py was found in .github/workflows or bin/, so "
               "the import closure covers nothing. A guard that examined "
               "nothing has failed, not passed.")
        return r

    # ---- walk local imports transitively --------------------------------
    search = ["loop", "visuals", "research", "auth", "voice", "tests", ""]

    def resolve(name: str) -> str | None:
        head = name.split(".")[0]
        for d in search:
            rel = f"{d}/{head}.py" if d else f"{head}.py"
            if (ROOT / rel).exists():
                return rel
        return None

    seen: set[str] = set()
    queue = list(entry)
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        try:
            tree = _ast.parse((ROOT / rel).read_text())
        except Exception:                                  # noqa: BLE001
            continue                     # syntax is another validator's job
        for node in _ast.walk(tree):
            names = []
            if isinstance(node, _ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            for n in names:
                got = resolve(n)
                if got and got not in seen:
                    queue.append(got)

    for rel in sorted(seen):
        r.examined += 1
        if rel not in tracked:
            r.fail(f"{rel} is reachable from a lane this repo runs but is NOT "
                   f"tracked by git, so it does not exist for any cloud runner. "
                   f"Add it, or stop the lane depending on it.")

    # ---- a tracked manifest's assets must be tracked --------------------
    for rel in sorted(t for t in tracked if t.startswith("channel/")
                      and t.endswith(".json")):
        try:
            data = json.loads((ROOT / rel).read_text())
        except Exception:                                  # noqa: BLE001
            continue
        rows = []
        for key in ("index", "assets"):
            v = data.get(key) if isinstance(data, dict) else None
            if isinstance(v, list):
                rows += [x for x in v if isinstance(x, dict)]
        base = str(pathlib.PurePosixPath(rel).parent)
        for row in rows:
            lf = row.get("local_file")
            if not lf:
                continue
            r.examined += 1
            asset = f"{base}/{lf}"
            if asset not in tracked:
                r.fail(f"{rel} is tracked and names {lf}, which is not. A "
                       f"rights manifest in git whose asset is not in git is "
                       f"how eleven material_image beats reached the cloud "
                       f"with no file behind them.")
    return r


def v31_render_has_thumbnail() -> Result:
    """A finished render must carry the thumbnail that lets it be uploaded.

    backfill.local_assets() counts an episode as uploadable only when BOTH
    renders/<slug>-final.mp4 and channel/thumbnails/<slug>.jpg exist. Nothing
    asserted the second, and nothing built it. On 2026-09-05 that left NINE
    fully rendered episodes stuck: com.howweknow.backfill ran at 09:00 every
    morning, found "0 pending", and exited clean. Correct, silent, and useless
    - the whole backlog was waiting on a 200 KB JPEG nobody knew was missing.

    An episode that took ~1.2 hours of narration and a full render is the most
    expensive thing this pipeline makes. Letting one sit invisible behind a
    missing thumbnail is the costliest possible way to be quiet, so this makes
    it loud the same day rather than whenever someone next looks at the upload
    queue.

    Exempt when there are no renders at all - the MP4s live on the Mac and in
    R2, never in git, so a cloud runner has nothing to check. A renders/
    directory that HAS files and is missing a thumbnail still fails.
    """
    r = Result("V31 render-has-thumbnail")
    renders = sorted((ROOT / "renders").glob("*-final.mp4"))
    r.examined += 1
    if not renders:
        r.exempt = True
        r.note("no rendered MP4 on this machine; renders live on the Mac and "
               "in R2 by design. The Mac run covers this.")
        return r

    thumbs = ROOT / "channel" / "thumbnails"
    for mp4 in renders:
        slug = mp4.name[: -len("-final.mp4")]
        r.examined += 1
        if not (thumbs / f"{slug}.jpg").exists():
            r.fail(f"{slug} is rendered but has no "
                   f"channel/thumbnails/{slug}.jpg, so backfill will never "
                   f"count it as pending and it cannot be uploaded. Build it "
                   f"with visuals/thumbs_materials.py, or give its subject a "
                   f"verified public-domain image.")
    return r


def _bank_lines() -> list[dict]:
    try:
        return read_json(ROOT / "pov" / "pov-bank.json")["lines"]
    except Exception:                       # noqa: BLE001 - never break V32
        return []


def _dom_of(slug: str):
    try:
        import domains as _D                                # noqa: PLC0415
        return _D.domain_of_slug(slug, None)
    except Exception:                       # noqa: BLE001
        return None


def _human_beat(slug: str) -> str:
    """The [HUMAN] sentence as narrated, so the message names the actual claim.

    A validator that says "an untraced POV" and does not quote it makes the
    reader open the file to find out what is being asserted in her name.
    """
    try:
        import re as _re                                    # noqa: PLC0415
        t = (ROOT / "scripts" / f"{slug}.md").read_text()
        m = _re.search(r"\[HUMAN\]\s*(.+)", t)
        line = m.group(1).strip() if m else ""
        return (line[:160] + "...") if len(line) > 160 else line
    except Exception:                       # noqa: BLE001
        return ""


def v32_scheduled_pov_is_hers() -> Result:
    """Every SCHEDULED episode's Producer POV must trace to a line she said.

    V4 already checks POV - against `loop/render_queue.json`, which holds the
    two episodes THIS WEEK drafted. Nineteen are scheduled to air. The other
    seventeen were never examined, so V4 stayed green while three materials
    episodes sat on the calendar whose POV traces to nothing.

    WHAT THE RULE ACTUALLY IS, because a first attempt at this got it wrong and
    failed the entire catalogue. The bank is not the finished text. A POV line
    is MATCHED from `pov/pov-bank.json` and then given an editorial pass for
    the episode it sits in - the scripts say so themselves ("matched from POV
    BANK pov-046 before rewriting"). So the check is not whether the final
    sentence appears verbatim in the bank; it is whether the episode has an
    entry in `pov/pov-assignments.json` tracing it to a bank line at all.
    Sixteen scheduled episodes do. Three do not.

    loop/config.json states the reason those three cannot borrow one: entering
    a domain outside deep sea "requires a ~20 minute POV top-up interview
    before first publish, because tier:specific POV lines do not transfer."
    The `[HUMAN]` paragraph is the one beat where a person speaks as
    themselves. An unassigned line there is the channel asserting she said
    something she did not, in a domain she was never asked about.

    Two honest ways to clear it, neither of which a validator may do for her:
    she reads the line and it is recorded as hers, or the episode is re-cut
    without the beat.

    Hard-fails when it examines zero items.
    """
    r = Result("V32 scheduled-pov")
    import datetime as _dt                                 # noqa: PLC0415
    import ledger as _led                                  # noqa: PLC0415

    path = ROOT / "pov" / "pov-assignments.json"
    r.examined += 1
    if not path.exists():
        r.fail("pov/pov-assignments.json is missing, so no scheduled episode's "
               "POV can be traced to the owner's interview.")
        return r
    assigned = {a["video"] for a in read_json(path)["assignments"]}
    # AN ENTRY THAT IS WRONG IS NOT AN ENTRY. This validator asked only
    # whether a row EXISTS, so commit 581feec - three rows whose recorded tier
    # and line text both contradicted the bank - was "traced" as far as V32
    # could tell. The predicate lives in loop/pov_match.py so that this, the
    # pre-upload gate and select() itself all ask the identical question;
    # V40 below reports the same defects across the WHOLE file, including
    # episodes that have already aired and are past this one's horizon.
    import pov_match as _pov                                # noqa: PLC0415
    defective = _pov.defective_assignments()
    assigned -= set(defective)

    now = _dt.datetime.now(_dt.timezone.utc)
    pending = []
    for row in _led.load()["published"]:
        stamp = row.get("scheduled_publish_at")
        if not stamp or row.get("retired_at"):
            continue
        when = _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when > now:
            pending.append((row["slug"], row.get("video_id"), when))

    r.examined += 1
    if not pending:
        r.fail("no episode is scheduled ahead, so this examined nothing - "
               "either an empty calendar or a ledger it cannot read.")
        return r

    for slug, vid, when in sorted(pending, key=lambda x: x[2]):
        script = ROOT / "scripts" / f"{slug}.md"
        if not script.exists() or "[HUMAN]" not in script.read_text():
            continue                      # no POV beat is a different rule
        r.examined += 1
        if slug in defective:
            # AN ENTRY THAT IS WRONG IS NOT AN ENTRY - but it is also not a
            # MISSING one, and this validator's own rule is to say only what
            # it checked. "No entry" would send the reader to add a row that
            # is already there; the fix here is to correct the row.
            r.fail(f"{slug} airs {when:%Y-%m-%d} with an entry in "
                   f"pov/pov-assignments.json that this repo cannot honour, "
                   f"so its first-person beat still traces to nothing: "
                   + "; ".join(f"[{d['code']}] {d['why']}"
                               for d in defective[slug]))
            continue
        if slug not in assigned and (vid or "") not in assigned:
            # SAY WHY IT IS UNTRACED, AND DO NOT GUESS AT THE REASON. This
            # used to end "its domain has had no POV interview" - true when it
            # was written and STALE the next day: interview 3 landed on
            # 2026-09-05 (pov/answers-3.txt, Q11a-c) and put four
            # materials-and-manufacturing tier:specific lines in the bank
            # (pov-119..122). A failure message that asserts a reason it did
            # not check sends the reader after the wrong fix - here, after an
            # interview that already exists.
            #
            # The real and only claim this validator can make is the one it
            # actually tested: there is no entry. So it says that, names the
            # line, and reports whether the domain has bank lines to draw on.
            dom = _dom_of(slug)
            have = [l["id"] for l in _bank_lines()
                    if l.get("domain") == dom] if dom else []
            r.fail(f"{slug} airs {when:%Y-%m-%d} with a first-person Producer "
                   f"POV that has no entry in pov/pov-assignments.json, so "
                   f"nothing traces it to a line the owner said. Its [HUMAN] "
                   f"beat reads: {_human_beat(slug)!r}. Its domain "
                   f"({dom or 'unknown'}) has "
                   + (f"{len(have)} bank line(s) of its own ({', '.join(have)}) "
                      f"- but a bank line is not an assignment, and this "
                      f"episode is already rendered and uploaded, so the "
                      f"narrated words are the ones that need tracing, not a "
                      f"line that could have been chosen."
                      if have else
                      "no POV lines of its own, and config says tier-specific "
                      "lines do not transfer."))
    return r



def v40_pov_assignment_integrity() -> Result:
    """pov/pov-assignments.json must say only things pov/pov-bank.json agrees with.

    THE HOLE V32 LEFT. V32 asks whether a scheduled episode HAS an assignment.
    It never asked whether the assignment is right, and the file is otherwise
    trusted absolutely: `select()` returns a hand assignment without applying
    the domain rule `score()` applies to every other line, `untraced_pov()`
    counted mere presence as a trace, and `record_assignment()` appends to it
    unchecked.

    CONFIRMED, commit 581feec (2026-09-07): the owner's three approved
    materials lines were recorded under pov-102/103/104, ids that in the bank
    are tier:transferable lines with COMPLETELY DIFFERENT TEXT. Each row was
    wrong twice - a tier the bank contradicts, and a line the bank does not
    hold under that id - so the words that reached YouTube traced to nothing.
    Every presence check called those episodes traced. The one thing that
    caught it was a single hardcoded end-to-end case in
    loop/tests/test_pov_domains.py naming one slug; the same mistake on any of
    the other twenty-eight rows would have passed in silence.

    THE SCOPE IS THE FILE, NOT THE CALENDAR. V32 can only see episodes
    scheduled ahead, which is how three of these reached YouTube before
    anything noticed. This examines every row, including videos already
    public, because a wrong row is wrong whether or not the episode has aired.

    Hard-fails when it examines zero assignments: an empty or unreadable file
    is not a clean one.
    """
    r = Result("V40 pov-assignment-integrity")
    import pov_match as _pov                                # noqa: PLC0415

    path = ROOT / "pov" / "pov-assignments.json"
    if not path.exists():
        r.fail("pov/pov-assignments.json is missing, so nothing traces any "
               "episode's first-person beat to a line the owner said.")
        return r
    rows = read_json(path).get("assignments") or []
    r.examined = len(rows)

    by_video = {}
    for d in _pov.assignment_defects(rows=rows):
        by_video.setdefault(d["video"], []).append(d)
    for video in sorted(by_video):
        for d in by_video[video]:
            r.fail(f"[{d['code']}] {d['why']}")

    if r.examined == 0:
        r.fail("pov/pov-assignments.json lists ZERO assignments \u2014 this "
               "validator examined nothing, which is not the same as finding "
               "nothing wrong.")
        return r
    r.note(f"{r.examined} assignment(s) agree with pov/pov-bank.json on the "
           f"line, its tier and its domain, and no line is used twice")
    return r


def v33_every_domain_is_harvested() -> Result:
    """Every domain holding a weekly slot must have something harvesting for it.

    The Saturday harvest lane kept its own hardcoded tuple of two harvesters,
    both deep sea. materials-and-manufacturing went live on 2026-09-03 with
    two of the four weekly slots, and the lane that grows the cleared imagery
    pool never learned the domain existed: research/imagery_materials.py was
    invoked by nothing at all, and neither was research/imagery_species.py.
    That is this repo's named defect "two components each keeping their own
    list with no link between them", and the symptom is silent - the pipeline
    degrades gracefully into an illustrated episode, so a domain publishing on
    an un-topped-up pool looks exactly like one publishing on a full one.

    The fix removed the second list: a harvester declares its own domain in a
    module-level HARVESTER dict, and the lane asks loop/config.json which
    domains are running. This asserts the join BEHAVIOURALLY - it runs the
    lane's own selection over the live allocation - rather than grepping for a
    filename, which would pass on a lane that finds the file and never runs it.

    Also asserts each selected harvester still contains the rights gate it
    declares, because the cheapest way to grow a thin pool is to widen the gate
    and that is the one change this pipeline may not make.

    Hard-fails when it examines zero items.
    """
    r = Result("V33 domain-harvesters")
    import footage_lane as _fl                             # noqa: PLC0415

    cfg = config()
    alloc = _fl.domains.allocation(cfg)
    r.examined += 1
    if not alloc:
        r.fail("loop/config.json has an empty domain allocation, so this "
               "examined nothing.")
        return r

    picked, uncovered = _fl.harvesters_for(cfg)
    for d in uncovered:
        r.examined += 1
        r.fail(f"{d} holds {alloc[d]} weekly slot(s) and no research/"
               f"imagery*.py declares a scheduled HARVESTER for it. Its "
               f"cleared imagery pool cannot grow, so every episode it "
               f"publishes beyond the existing pool is illustrated by default "
               f"rather than by decision.")

    for h in picked:
        r.examined += 1
        if not h.get("gate"):
            r.fail(f"{h['rel']} declares no rights gate. A harvester with no "
                   f"named gate cannot be checked for having lost it.")
            continue
        src = (ROOT / h["rel"]).read_text(encoding="utf-8")
        if h["gate"] not in src:
            r.fail(f"{h['rel']} declares gate {h['gate']}() and no longer "
                   f"contains it. Nothing harvested through it may be used.")
    return r


def v34_niche_lifecycle_is_acted_on() -> Result:
    """A retired niche must change the allocation, not just the report.

    loop/monthly.py computed `exhausted_domains` and `next_domain` every month
    from 2026-08 and wrote them into prose. Nothing read them. A domain could
    decay to an empty queue and keep its weekly slots indefinitely, in a report
    that named it as finished - the "runs but inert" class, one level up: the
    decision was made, correctly, and then discarded.

    Asserted BEHAVIOURALLY on a constructed month, because the live channel has
    no decayed domain and a validator that only checks the healthy case proves
    nothing. It builds evidence in which one allocated domain is measured past
    the floor and its queue is empty, and requires that:

      * domains.lifecycle() returns applied, retiring that domain;
      * the promoted domain is the next-ranked unused one in the taxonomy;
      * the new allocation still sums to cadence.ceiling, so slots_at() cannot
        raise on the split it produced;
      * monthly.review()'s allocation decision IS the lifecycle decision when
        one applies - a retirement outranks a one-slot move, because moving a
        slot between two domains is meaningless if one of them is finished.

    Hard-fails when it examines zero items.
    """
    r = Result("V34 niche-lifecycle")
    import domains as _dom                                 # noqa: PLC0415
    import monthly as _mon                                 # noqa: PLC0415

    cfg = config()
    alloc = _dom.allocation(cfg)
    r.examined += 1
    if len(alloc) < 1:
        r.fail("no allocated domain, so this examined nothing.")
        return r

    victim = sorted(alloc)[0]
    need = _dom.min_episodes_to_judge(cfg)
    ev = {d: {"measured": need, "views": 100, "avd_s": 200.0, "avp": 30.0,
              "judgeable": True} for d in alloc}
    ev[victim]["avd_s"] = 10.0

    # A queue empty for `victim`, full for everyone else.
    real_depth = _dom.queue_depth
    real_ex = _dom.exhausted
    _dom.exhausted = lambda cfg, published=None: [victim]    # noqa: ARG005
    _dom.queue_depth = lambda: {d: (0 if d == victim else 20) for d in alloc}
    try:
        d = _dom.lifecycle(cfg, ev)
        r.examined += 1
        if not d.get("applied"):
            r.fail(f"a domain measured past the {need}-episode floor with an "
                   f"empty queue did NOT produce a retirement: "
                   f"{d.get('stop') or d.get('why', '')[:160]}")
            return r
        r.examined += 1
        if d["retired"] != victim:
            r.fail(f"retired {d['retired']}, expected the decayed domain "
                   f"{victim}")
        r.examined += 1
        expected = _dom.next_unused(list(alloc))
        if d["promoted"] != expected:
            r.fail(f"promoted {d['promoted']}, expected the next-ranked unused "
                   f"domain {expected}")
        r.examined += 1
        ceiling = int(cfg["cadence"]["ceiling"])
        if sum(d["allocation"].values()) != ceiling:
            r.fail(f"the post-retirement allocation sums to "
                   f"{sum(d['allocation'].values())}, not cadence.ceiling "
                   f"{ceiling}. domains.slots_at() raises on that, which would "
                   f"take the whole publishing lane down.")
        r.examined += 1
        if victim in d["allocation"]:
            r.fail(f"{victim} was retired and still holds slots in the new "
                   f"allocation.")

        # And the review must USE it rather than compute it beside the
        # reallocation and then apply the reallocation.
        real_re = _dom.reallocate
        real_pd = _mon.per_domain
        _dom.reallocate = lambda cfg, per: {                # noqa: ARG005
            "applied": False, "allocation": alloc,
            "why": "SENTINEL: reallocate was used instead of the lifecycle"}
        _mon.per_domain = lambda rows, cfg: ev              # noqa: ARG005
        try:
            rev = _mon.review([], cfg, _mon.month_id())
        finally:
            _dom.reallocate = real_re
            _mon.per_domain = real_pd
        r.examined += 1
        if "SENTINEL" in str((rev.get("allocation") or {}).get("why", "")):
            r.fail("monthly.review() applied the reallocation while a "
                   "retirement was available. A slot move computed against "
                   "the pre-retirement split would be applied on top of a "
                   "split that no longer exists.")
        r.examined += 1
        if not (rev.get("lifecycle") or {}).get("applied"):
            r.fail("monthly.review() did not carry the lifecycle decision, so "
                   "the monthly report cannot say a domain was retired.")
    finally:
        _dom.queue_depth = real_depth
        _dom.exhausted = real_ex
    return r


def v35_digest_reaches_her() -> Result:
    """The weekly digest must render, and its delivery must be able to email.

    The owner's instruction is that the system decides and she is told at
    intervals. Before 2026-09-05 the only things that reached her were a NAMED
    STOP and the monthly review, so a healthy week was completely silent - the
    channel could run for a month without saying so.

    Two ways a weekly email quietly stops being one, and both are checked:

      * the digest renders EMPTY, or fails to render at all, and the workflow's
        `if: always()` delivery step posts a file that says nothing;
      * the issue body has no `@` mention. GitHub's default notification
        setting for your own repositories is "Participating and @mentions", and
        an issue opened by Actions is neither, so an un-mentioned issue appears
        in the repo and no email is ever sent. bin/loop-stage.sh carries a long
        comment about this because it has already happened once.

    Renders the digest for real rather than checking that the file exists,
    because a digest that raises is exactly the case the delivery step's
    `if: always()` would paper over.

    Hard-fails when it examines zero items.
    """
    r = Result("V35 weekly-digest")
    import datetime as _dt                                 # noqa: PLC0415
    import digest as _dig                                  # noqa: PLC0415

    wf = ROOT / ".github" / "workflows" / "loop-sun-digest.yml"
    r.examined += 1
    if not wf.exists():
        r.fail("there is no .github/workflows/loop-sun-digest.yml, so nothing "
               "delivers a weekly digest and a healthy week is silent.")
        return r
    src = wf.read_text(encoding="utf-8")

    r.examined += 1
    if "loop/digest.py" not in src:
        r.fail("the Sunday digest workflow does not run loop/digest.py.")

    r.examined += 1
    if "@seq23" not in src:
        r.fail("the digest issue body contains no @-mention. GitHub's default "
               "notification setting is 'Participating and @mentions'; an "
               "issue opened by Actions is neither, so the digest would appear "
               "in the repo and email nobody.")

    r.examined += 1
    if "schedule:" not in src or "* * 0" not in src:
        r.fail("the digest workflow has no weekly Sunday cron, so it only ever "
               "runs when someone remembers to dispatch it.")

    body, counts = _dig.render("V35-probe",
                               _dt.datetime.now(_dt.timezone.utc))
    r.examined += 1
    if len(body.splitlines()) < 12:
        r.fail(f"the digest rendered {len(body.splitlines())} line(s) - it is "
               f"not reporting anything.")
    # "## Next up" became "## The calendar" on 2026-09-14, when the digest
    # gained the sections she asked for: what went INTO the queue this week,
    # the pipeline's health, and every empty slot ahead - with the verdict in
    # the subject line. A digest without those is the old digest, which read
    # a week of nine unshipped episodes as healthy.
    for heading in ("## Aired this week", "## Queued this week",
                    "## Pipeline health", "## The calendar", "## Runway",
                    "## Named stops"):
        r.examined += 1
        if heading not in body:
            r.fail(f"the digest is missing its {heading!r} section.")
    r.examined += 1
    if not (counts["aired"] or counts["scheduled"] or counts["queued"]):
        r.fail("the digest read no episode, no schedule and no queue. Every "
               "source it reads would have to be empty at once for that to be "
               "true, so this is a read failure, not a quiet week.")
    return r


# The four properties the editorial gate claims, and nothing else. Each is
# checkable, which is the whole reason the other two were removed.
GATE_BULLETS = ("Humanized cold open:", "First-person producer observation:",
                "Evidence uncertainty or limitation:", "Structural variation:",
                "Number-level source audit:")

# Claims of a human step that nobody performs. A hands-off channel that records
# "owner must confirm" on every script is not recording a gate, it is recording
# a debt to a person who was never going to be asked.
GATE_DEBT = re.compile(
    r"owner (must )?confirm|owner confirmation required|"
    r"final human watch-through|pending until", re.I)


def v36_editorial_gate_is_enforced() -> Result:
    """Every script's editorial gate must claim only what the build enforces.

    THE DECISION THIS ENCODES, taken deliberately on 2026-09-05 rather than
    left to decay. All 38 scripts carried a "Human fingerprint gate" section
    whose six bullets nothing read. Three of them asserted a human step - "owner
    must confirm it sounds natural read aloud", "owner confirmation required",
    "Final human watch-through: PENDING until the rendered MP4 exists" - on a
    channel explicitly designed to run without its owner. Those episodes aired.
    The confirmations never happened and were never going to.

    Two honest ways to resolve that. Start performing the review, which is the
    one thing the channel exists not to require; or stop claiming it. The claims
    are gone, and what is left is the four properties that ARE enforced:

      * the first-person observation traces to her voice        (V4, V32)
      * every number traces to a named public source            (V5, V6)
      * the episode states its own uncertainty                  (asserted here)
      * the structure is not the previous episode's             (asserted here)

    "Structural variation" is checkable in the strongest available sense: all 38
    labels are distinct, so a duplicate is a template reasserting itself.

    Hard-fails when it examines zero items.
    """
    r = Result("V36 editorial-gate")
    scripts = sorted((ROOT / "scripts").glob("*.md"))
    r.examined += 1
    if not scripts:
        r.fail("no scripts at all, so this examined nothing.")
        return r

    structures: dict[str, str] = {}
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        r.examined += 1
        if "## Editorial gate" not in text:
            if "## Human fingerprint gate" in text:
                r.fail(f"{path.name} still carries the old 'Human fingerprint "
                       f"gate' heading, whose bullets claim a human review "
                       f"this channel does not perform.")
            else:
                r.fail(f"{path.name} has no editorial gate section at all.")
            continue

        i = text.index("## Editorial gate")
        j = text.find("\n## ", i + 1)
        block = text[i:j if j > 0 else len(text)]

        m = GATE_DEBT.search(block)
        r.examined += 1
        if m:
            r.fail(f"{path.name}'s editorial gate claims a human step nobody "
                   f"performs ({m.group(0)!r}). Either the review happens or "
                   f"the claim goes; a hands-off channel cannot record a debt "
                   f"to a person who is never asked.")

        for bullet in GATE_BULLETS:
            r.examined += 1
            if bullet not in block:
                r.fail(f"{path.name}'s editorial gate is missing "
                       f"{bullet.rstrip(':')!r}.")

        for line in block.splitlines():
            if line.startswith("- Structural variation:"):
                label = line.split(":", 1)[1].strip().rstrip(".").lower()
                r.examined += 1
                if not label:
                    r.fail(f"{path.name} names no structure.")
                elif label in structures:
                    r.fail(f"{path.name} and {structures[label]} declare the "
                           f"SAME structure ({label[:60]!r}). Structural "
                           f"variation is the one claim in this gate that a "
                           f"template would break first.")
                else:
                    structures[label] = path.name
                break
    return r


def v37_runtime_target_and_self_heal() -> Result:
    """The runtime target, its tolerance band, and the self-heal that enforces it.

    Owner decision 2026-09-05: aim for 12 minutes, tolerate 15% either side,
    and anything under 10 minutes SELF-HEALS. Four things have to stay true for
    that to be a rule rather than a sentence in a config file, and each one was
    false before it was written:

      * **The band's lower edge must sit above the hard floor.** 15% under 12 is
        10.2, above the 10-minute floor, so "inside the band" and "over the
        floor" cannot disagree. A target set AT the floor is what produced four
        episodes at 8.6-9.7 minutes: authored to 10.5 with a floor of 10, every
        one of them missed low and there was nowhere to land.
      * **One copy of the number.** loop/author.py carried
        RUNTIME_TARGET_MINUTES = 10.5 as a literal while loop/config.json said
        the same thing. Raising the config alone would have left drafting at
        10.5 for ever, which is the duplicated-constant defect that module's own
        docstring describes at length.
      * **Something must run the self-heal.** A stage nothing invokes is the
        "exists but nothing invokes it" class - which is exactly what
        research/imagery_materials.py was.
      * **Something must refuse to ship a short render.** V24 runs where the
        renders are, which is the Mac; the cloud drafting lane that trips the
        breaker cannot see renders/ and exempts itself. Before 2026-09-05 the
        floor was consulted by nothing on the upload path at all.

    Hard-fails when it examines zero items.
    """
    r = Result("V37 runtime-target")
    cfg = config()["retention"]

    r.examined += 1
    target = float(cfg.get("runtime_minutes", 0))
    if target <= 0:
        r.fail("loop/config.json retention.runtime_minutes is missing or zero.")
        return r

    r.examined += 1
    tol = float(cfg.get("runtime_tolerance_pct", 0))
    if tol <= 0:
        r.fail("retention.runtime_tolerance_pct is missing. Without a stated "
               "tolerance, 'about 12 minutes' has no edges and every episode "
               "is either exactly right or a defect.")
        return r

    floor = float(cfg["runtime_floor_minutes"])
    band_min = target * (1 - tol / 100)
    r.examined += 1
    if band_min < floor:
        r.fail(f"the tolerance band starts at {band_min:.2f} min, BELOW the "
               f"{floor} min hard floor. An episode could sit inside the "
               f"allowed band and under the floor at the same time, which "
               f"makes the two rules contradict each other. Raise "
               f"runtime_minutes or narrow runtime_tolerance_pct.")

    import author as _a                                    # noqa: PLC0415
    r.examined += 1
    if abs(_a.RUNTIME_TARGET_MINUTES - target) > 1e-6:
        r.fail(f"loop/author.py drafts to {_a.RUNTIME_TARGET_MINUTES} min while "
               f"loop/config.json says {target}. Scripts would be written to "
               f"the old number indefinitely and nothing would say so.")
    r.examined += 1
    if "RUNTIME_TARGET_MINUTES = 10" in (ROOT / "loop" / "author.py").read_text():
        r.fail("loop/author.py hardcodes a runtime target again. The number "
               "lives in loop/config.json; a second copy is how three call "
               "sites came to agree on a guess.")

    heal = ROOT / "loop" / "extend.py"
    r.examined += 1
    if not heal.exists():
        r.fail("loop/extend.py is missing, so nothing heals a short episode "
               "and the floor is a stop that waits for a person.")
        return r

    # AN INVOCATION, NOT A MENTION. A first version of this searched the raw
    # file for "loop/extend.py". Removing the actual call left the explanatory
    # comment above it AND a print() inside a heredoc that names the file, and
    # the check still passed - so it would have gone on asserting the self-heal
    # was wired long after it had been unwired. It now requires a line that
    # RUNS it.
    batch = (ROOT / "bin" / "batch-session.sh").read_text()
    r.examined += 1
    if not re.search(r"^\s*(\$PY|python3?|\S*/python)\s+loop/extend\.py",
                     batch, re.M):
        r.fail("no lane runs loop/extend.py. A self-heal nothing invokes is "
               "the 'exists but nothing invokes it' defect, and the floor goes "
               "back to being a stop.")
    # THE CHECK LIVES IN loop/render_gate.py NOW (2026-09-13), which runs V24
    # and HOLDS the failing slug rather than refusing the whole batch. So the
    # assertion is behavioural in two halves: the batch must go through the
    # gate, and the gate must really consult V24. Grepping the batch script for
    # the validator's name - what stood here - tripped the breaker on
    # 2026-09-14 the morning after the gate moved, for a check that had not
    # weakened but relocated.
    r.examined += 1
    gate_src = (ROOT / "loop" / "render_gate.py").read_text() \
        if (ROOT / "loop" / "render_gate.py").exists() else ""
    if "v24_render_duration_floor" not in gate_src:
        r.fail("loop/render_gate.py does not run V24. The runtime floor is "
               "consulted by no gate on the upload path.")
    r.examined += 1
    # An INVOCATION, not a mention: a comment naming the gate is not a gate.
    runs_gate = lambda src: bool(re.search(r"^[^#\n]*loop/render_gate\.py", src, re.M))  # noqa: E731
    if not runs_gate(batch) and "v24_render_duration_floor" not in batch:
        r.fail("bin/batch-session.sh does not check V24 before pushing to R2 "
               "(neither directly nor through loop/render_gate.py). V24 runs "
               "only where renders exist - this Mac - and the cloud lane "
               "exempts itself, so without this check nothing on the upload "
               "path consults the runtime floor at all.")
    r.examined += 1
    daily = (ROOT / "bin" / "loop-backfill-daily.sh").read_text()
    if not runs_gate(daily):
        r.fail("bin/loop-backfill-daily.sh does not go through loop/render_gate.py, "
               "so a render that fails V24 can be uploaded from the Mac directly.")

    # And the heal must be able to tell a short episode from one the narrator
    # is halfway through, which is the difference between healing and padding.
    import extend as _e                                    # noqa: PLC0415
    r.examined += 1
    src = heal.read_text()
    if "narration incomplete" not in src:
        r.fail("loop/extend.py does not distinguish an episode that is SHORT "
               "from one the narrator has not finished. Partial audio measures "
               "as a short episode - what-is-concrete-made-of read as 5.09 min "
               "on 1,678 words - and would be padded for no reason.")
    r.examined += 1
    t, bmin, f = _e.band()
    if (t, round(bmin, 2), f) != (target, round(band_min, 2), floor):
        r.fail(f"loop/extend.py computes a different band ({t}, {bmin:.2f}, "
               f"{f}) than loop/config.json states ({target}, "
               f"{band_min:.2f}, {floor}).")
    return r


def v38_no_duplicate_or_zombie_schedule() -> Result:
    """One live row per slug, and a retired video must hold no publish date.

    TWO WAYS THE SAME EPISODE AIRS TWICE, both found live on 2026-09-05 while
    answering the question "when does the last video go out".

    ONE. Two upload lanes write one ledger -- backfill on the Mac at 09:00 and
    cloud-upload at 09:00 CT. On 2026-09-03 both uploaded
    02-how-deep-sea-creatures-survive-pressure, three hours apart, and gave the
    two different video ids the SAME 2026-10-25 15:00 slot. Two identical
    videos would have gone public in the same minute. This had happened once
    before (the ledger counting 16 videos) and the arbitration did not hold.

    TWO. Retiring the duplicate did not fix it. `retire.py` set the video
    private and verified private -- and its publishAt survived untouched, so
    YouTube would have made it public on 25 October anyway. A retired video
    with a live publish date un-retires itself, seven weeks later, with nothing
    watching. Neither omitting publishAt nor sending an explicit null clears
    it; both return 200 and change nothing.

    Checked against the LEDGER, which is cheap and offline. The live API is
    where the second condition was proven, but a validator that needs OAuth
    cannot run in the cloud lane that matters.

    Hard-fails when it examines zero items.
    """
    r = Result("V38 no-duplicate-airing")
    import ledger as _led                                  # noqa: PLC0415

    rows = _led.load()["published"]
    r.examined += 1
    if not rows:
        r.fail("the ledger holds no published rows, so this examined nothing.")
        return r

    live = [x for x in rows if not x.get("retired_at")]
    by_slug: dict = {}
    for x in live:
        by_slug.setdefault(x["slug"], []).append(x)
    for slug, group in sorted(by_slug.items()):
        r.examined += 1
        if len(group) > 1:
            ids = ", ".join(str(g.get("video_id")) for g in group)
            when = {g.get("scheduled_publish_at") for g in group}
            r.fail(f"{slug} has {len(group)} live ledger rows ({ids}). Two "
                   f"upload lanes share this ledger; if they also share a "
                   f"slot ({', '.join(sorted(str(w) for w in when))}) the same "
                   f"episode airs twice in the same minute.")

    # A retired row must not still be holding a future slot.
    import datetime as _dt                                 # noqa: PLC0415
    now = _dt.datetime.now(_dt.timezone.utc)
    for x in rows:
        if not x.get("retired_at"):
            continue
        stamp = x.get("scheduled_publish_at")
        if not stamp:
            continue
        r.examined += 1
        when = _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when > now and not x.get("schedule_cancelled_at"):
            r.fail(f"{x['slug']} ({x.get('video_id')}) is retired and still "
                   f"records a publish date of {when:%Y-%m-%d %H:%M}Z. If that "
                   f"date is still set on YouTube the video makes itself "
                   f"public then, undoing the retirement. loop/retire.py now "
                   f"cancels the schedule; this row predates that or the "
                   f"cancellation failed.")

    # And the fix itself must still be in the module, since the API's behaviour
    # here is counter-intuitive enough to be "simplified" away later.
    r.examined += 1
    if "cancel_schedule" not in (ROOT / "loop" / "retire.py").read_text():
        r.fail("loop/retire.py no longer cancels a pending publishAt. Setting "
               "a video private does NOT clear its publish date - it goes "
               "public on that date anyway.")
    return r


def v39_queue_depth_is_remaining_not_scored() -> Result:
    """Queue depth must count what is LEFT, not everything ever scored.

    research/publish_order*.json is the SCORED list, not the remaining list --
    a slug stays in it after its episode is made, because that is where its
    score and its gate verdict live. Counting those as inventory double-counted
    the entire catalogue: on 2026-09-05 deep sea reported 16 queued topics and
    8.0 weeks of runway while every one of those 16 was already uploaded and
    dated. Its true remaining queue was ZERO.

    That is the worst possible direction for this particular number to be wrong
    in. `runway.warn_weeks` exists to say "you are running out" before it
    happens, and it could not see the end coming -- the guard would have stayed
    green until the last scheduled episode aired and the queue was simply
    empty. The same number feeds `domains.exhausted()`, so a decayed niche
    could never be detected either.

    Asserted behaviourally against the ledger: no slug that has been uploaded
    may be counted as remaining inventory.

    Hard-fails when it examines zero items.
    """
    r = Result("V39 queue-depth-remaining")
    import domains as _dom                                 # noqa: PLC0415
    import ledger as _led                                  # noqa: PLC0415

    published = {x["slug"] for x in _led.load()["published"]}
    r.examined += 1
    if not published:
        r.fail("the ledger holds no uploaded slugs, so this examined nothing.")
        return r

    remaining = _dom.queue_depth()
    scored = _dom.queue_depth(include_published=True)
    r.examined += 1
    if sum(remaining.values()) > sum(scored.values()):
        r.fail(f"remaining queue ({sum(remaining.values())}) exceeds the total "
               f"ever scored ({sum(scored.values())}), which is arithmetically "
               f"impossible.")

    # The real check: walk the files and confirm no published slug survives.
    # A slug counts once however many files carry it, exactly as
    # queue_depth() counts it.
    counted, seen_slugs = [], set()
    for path in _dom._publish_order_files():
        for row in (_dom._read(path).get("queue") or []):
            slug = row.get("slug")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            if slug in published:
                counted.append(slug)
    # Rows loop/batch_queue.py refuses as the same question as one already
    # made or kept, or as naming another channel (2026-09-25), are not
    # inventory either: no lane can ever pick them. They leave the remaining
    # count exactly as a published slug does, and are asserted the same way.
    import batch_queue as _bq                              # noqa: PLC0415
    refused_by_dom: dict[str, int] = {}
    for row in _bq.refused_entries():
        slug = row["slug"]
        d = (_dom.domain_of_slug(slug) or row.get("domain")
             or _dom._read(_bq.ROOT / "research"
                           / row["_domain_file"]).get("domain"))
        if d in _dom.known():
            refused_by_dom[d] = refused_by_dom.get(d, 0) + 1
    r.note(f"{sum(refused_by_dom.values())} queued row(s) refused as a "
           f"repeated question or another channel's topic: {refused_by_dom}")
    r.examined += 1
    if not counted:
        r.note("no published slug appears in any publish-order file, so the "
               "double-count cannot occur here")
    # Those slugs exist in the files; they must NOT be in the depth. Exact
    # arithmetic per domain: scored = remaining + uploaded + refused.
    by_dom = {}
    for slug in counted:
        d = _dom.domain_of_slug(slug)
        if d:
            by_dom[d] = by_dom.get(d, 0) + 1
    for d in sorted(set(by_dom) | set(refused_by_dom)):
        n, x = by_dom.get(d, 0), refused_by_dom.get(d, 0)
        r.examined += 1
        if remaining.get(d, 0) + n + x != scored.get(d, 0):
            r.fail(f"{d}: {scored.get(d, 0)} scored minus {n} already "
                   f"uploaded minus {x} refused as a repeated question should "
                   f"leave {scored.get(d, 0) - n - x} remaining, but "
                   f"queue_depth() reports {remaining.get(d, 0)}. Something "
                   f"no lane can pick is being counted as inventory.")
    return r


def v41_discovery_metadata() -> Result:
    """Every allocated domain's tags and hashtags are DERIVED, not one list.

    Owner instruction, 2026-09-21: every video carried the same seven
    deep-sea tags and no hashtags — including the 18 materials episodes,
    tagged "marine biology". `loop/discovery.py` now derives both per
    episode, from `loop/config.json`'s `discovery` block plus the script's
    own subject and mined queries actually in its narration.

    Proved for EVERY allocated domain, on a real script of that domain,
    through the real builders — not by reading source text, the way V18
    checks `defaultLanguage`:

      * `loop/config.json` declares non-empty tags and hashtags for the
        domain, and for the channel.
      * `loop/upload.py:build_payload`'s tags carry at least one of this
        domain's own tags and NONE of any other allocated domain's — the
        exact shape of the bug this closes: a materials episode carrying
        "marine biology".
      * the description ends with a recognisable hashtag line of 1-60
        hashtags, whose first three are subject, domain, channel — the three
        YouTube shows above the title.
      * `loop/shorts_lane.py:build_payload` for the same episode carries
        "shorts" plus at least one of the domain's own tags.
      * the total tag length does not exceed `TAG_TOTAL_MAX`, and
        `loop/discovery.py` and `loop/upload.py` agree on what that limit is.

    And once, not per domain: `.github/workflows/loop-reach.yml` names
    `loop/tags_backfill.py`, so a future drift self-heals in the cloud
    rather than existing with nothing invoking it.

    Hard-fails when it examines zero allocated domains.
    """
    r = Result("V41 discovery-metadata")
    sys.path.insert(0, str(ROOT / "loop"))
    import discovery as _disc                              # noqa: PLC0415
    import shorts_lane as _sl                               # noqa: PLC0415
    import upload as _up                                    # noqa: PLC0415

    cfg = config()
    alloc = list(domains.allocation(cfg))
    r.examined += 1
    if not alloc:
        r.fail("loop/config.json domains.allocation names no domain — "
               "examined nothing")
        return r

    disc_cfg = cfg.get("discovery") or {}
    if not disc_cfg:
        r.fail("loop/config.json has no `discovery` block")
        return r

    r.examined += 1
    if not (disc_cfg.get("channel") or {}).get("tags"):
        r.fail("discovery.channel has no `tags`")
    if not (disc_cfg.get("channel") or {}).get("hashtags"):
        r.fail("discovery.channel has no `hashtags`")

    if _disc.TAG_TOTAL_MAX != _up.TAG_TOTAL_MAX:
        r.fail(f"loop/discovery.py TAG_TOTAL_MAX ({_disc.TAG_TOTAL_MAX}) != "
               f"loop/upload.py TAG_TOTAL_MAX ({_up.TAG_TOTAL_MAX}) — the "
               f"two must agree on YouTube's own tags-field limit")

    domain_tags = {}
    for name in alloc:
        r.examined += 1
        block = (disc_cfg.get("domains") or {}).get(name) or {}
        if not block.get("tags"):
            r.fail(f"{name}: discovery.domains has no `tags`")
        if not block.get("hashtags"):
            r.fail(f"{name}: discovery.domains has no `hashtags`")
        domain_tags[name] = set(block.get("tags") or [])

    # One real script per allocated domain — the first on disk that carries it.
    script_of: dict[str, Path] = {}
    for p in sorted((ROOT / "scripts").glob("*.md")):
        d = domains.domain_of_script(p)
        if d in alloc and d not in script_of:
            script_of[d] = p

    for name in alloc:
        p = script_of.get(name)
        r.examined += 1
        if not p:
            r.fail(f"{name}: no script on disk carries this domain — its "
                   f"tags cannot be proved against a real payload")
            continue
        slug = p.stem
        question = slug.split("-", 1)[-1].replace("-", " ")
        item = {"slug": slug, "script": str(p.relative_to(ROOT)),
               "question": question}
        payload = _up.build_payload(item)
        tags = payload["snippet"]["tags"]
        tagset = set(tags)

        r.examined += 1
        if not (domain_tags[name] & tagset):
            r.fail(f"{name}: {slug}'s tags carry none of this domain's own "
                   f"tags {sorted(domain_tags[name])}")
        for other, other_tags in domain_tags.items():
            if other == name:
                continue
            leaked = other_tags & tagset
            if leaked:
                r.fail(f"{name}: {slug}'s tags carry {sorted(leaked)} from "
                       f"{other} — the exact shape of the bug this closes")

        r.examined += 1
        total_len = sum(len(t) + 1 for t in tags)
        if total_len > _disc.TAG_TOTAL_MAX:
            r.fail(f"{name}: {slug}'s total tag length {total_len} exceeds "
                   f"TAG_TOTAL_MAX ({_disc.TAG_TOTAL_MAX})")

        r.examined += 1
        desc = payload["snippet"]["description"]
        last_line = desc.split("\n")[-1] if desc else ""
        if not _disc.is_hashtag_line(last_line):
            r.fail(f"{name}: {slug}'s description does not end with a "
                   f"recognisable hashtag line")
        else:
            hts = last_line.split()
            if not (1 <= len(hts) <= 60):
                r.fail(f"{name}: {slug}'s hashtag line carries {len(hts)} "
                       f"hashtag(s), outside YouTube's 1-60")
            script_text = p.read_text(encoding="utf-8")
            subject_ht = _disc._hashtag_word(
                _disc.subject_of(_disc._script_title(slug, script_text)))
            domain_ht = ((disc_cfg.get("domains") or {}).get(name) or {}) \
                .get("hashtags") or []
            channel_ht = (disc_cfg.get("channel") or {}).get("hashtags") or []
            want_first3 = [h for h in [subject_ht, *domain_ht, *channel_ht]
                           if h][:3]
            if hts[:len(want_first3)] != want_first3:
                r.fail(f"{name}: {slug}'s first hashtag(s) are {hts[:3]}, "
                       f"expected subject/domain/channel order "
                       f"{want_first3} — those are the ones YouTube shows "
                       f"above the title")

        r.examined += 1
        short_payload = _sl.build_payload(slug, question)
        short_tags = short_payload["snippet"]["tags"]
        if "shorts" not in short_tags:
            r.fail(f"{name}: shorts_lane.build_payload({slug!r}, ...) tags "
                   f"do not include 'shorts'")
        if not (domain_tags[name] & set(short_tags)):
            r.fail(f"{name}: shorts_lane.build_payload({slug!r}, ...) tags "
                   f"carry none of this domain's own tags")

    r.examined += 1
    workflow = ROOT / ".github" / "workflows" / "loop-reach.yml"
    if not workflow.exists() or "tags_backfill.py" not in workflow.read_text():
        r.fail("`.github/workflows/loop-reach.yml` does not name "
               "loop/tags_backfill.py — a future drift would never "
               "self-heal in the cloud")

    if r.examined == 0:
        r.fail("examined nothing")
    return r


def v43_queue_asks_distinct_questions(items) -> Result:
    """HARD. The publish queue, and every item this run hands the Mac, asks
    questions the channel has not already answered, once each, and names no
    other channel.

    2026-09-25. Week 2026-W39 picked "what lives in the depths of the ocean",
    "what lives in the deep" and "what lives in the sea" - one question three
    times, and all three already aired as episode 08, "What creatures live
    in the deep sea?". The materials queue held ten phrasings of "how are
    microchips made" (an episode already made), three naming another channel
    ("veritasium", "ted", "branch education"). loop/topic_identity.py is the
    rule; loop/batch_queue.py applies it on read. This checks the OUTCOME
    pairwise rather than re-running the filter, so it fails if the filter is
    removed, bypassed or reordered - not merely if it raises.

    Hard-fails when it examines zero queue rows.
    """
    r = Result("V43 distinct-questions")
    import batch_queue as _bq                              # noqa: PLC0415
    import topic_identity as T                             # noqa: PLC0415

    published = _bq._published_questions()
    anchors = [(q, T.question_key(q)) for q in published.values()]
    rows = [x for x in _bq.queued_entries() if x["slug"] not in published]
    subjects = [(f"queued {x['slug']}", x["slug"], _bq._question_of(x))
                for x in rows]
    for it in items or []:
        if it.get("slug") in published:
            continue
        subjects.append((f"this week's {it.get('slug')}", it.get("slug"),
                         it.get("question") or str(it.get("slug", ""))
                         .replace("-", " ")))
    r.examined += len(rows)
    if not rows:
        r.fail("the publish queue holds no unpublished row, so this examined "
               "nothing")
        return r
    for i, (label, slug, q) in enumerate(subjects):
        r.examined += 1 if label.startswith("this week") else 0
        ch = T.names_other_channel(q)
        if ch:
            r.fail(f"{label} ({q!r}) names another channel: {ch}")
        key = T.question_key(q)
        hit = T.first_same(key, anchors)
        if hit:
            r.fail(f"{label} ({q!r}) repeats an episode already made, "
                   f"{hit[0]!r}: {hit[1]}")
        for label2, slug2, q2 in subjects[:i]:
            if slug2 == slug:
                continue                  # the same slug, queued and picked
            why = T.why_same(key, T.question_key(q2))
            if why:
                r.fail(f"{label} ({q!r}) and {label2} ({q2!r}) are the same "
                       f"question: {why}")
    refused = _bq.refused_entries()
    r.note(f"{len(refused)} queued row(s) refused on read as a repeated "
           f"question or another channel's topic")
    return r


def v44_opening_payoff_first(items) -> Result:
    """HARD. Every script this run hands the Mac that was drafted under the
    opening rule (it carries `**Opening:** <variant>`, stamped by
    loop/author.py) says its answer inside the first 30 seconds, per
    loop/opening.py.problems(). Scripts drafted before the rule carry no
    marker and are exempt - published and pre-rule videos are never re-cut.

    2026-09-25: 6 of 10 measured videos lost the average viewer inside two
    minutes (loop/state/retention_finding.md). The author redrafts a buried
    answer inside its own retries; this is the same check one stage later,
    so a hand-edited or hand-written script cannot route around it.
    """
    r = Result("V44 opening-payoff-first")
    import opening as _op                                  # noqa: PLC0415
    marked = 0
    for it in items or []:
        r.examined += 1
        path = ROOT / it["script"]
        if not path.exists():
            r.fail(f"{it.get('slug')}: script {it['script']} does not exist")
            continue
        text = path.read_text(encoding="utf-8")
        m = _op.MARK_RE.search(text)
        if not m:
            continue
        marked += 1
        if m.group(1) not in _op.VARIANTS:
            r.fail(f"{it.get('slug')}: unknown opening variant {m.group(1)!r}")
            continue
        for p in _op.problems(text, m.group(1)):
            r.fail(f"{it.get('slug')}: {p}")
    if r.examined == 0:
        r.fail("examined nothing")
    elif marked == 0:
        r.note("every item predates the opening rule (no **Opening:** marker); "
               "nothing to hold to it this run")
    return r


def v45_nothing_waits_on_the_owner() -> Result:
    """HARD. Every stop kind is automated, a secret only she holds, or an
    error - and none asks her for a decision.

    Owner's rule, 2026-09-25, verbatim: "Nothing is supposed to wait on the
    owner." loop/stop_classes.py lists every stop kind the source can raise
    and every classified code; this fails on one with no class, an
    owner stop that names no credential/account/external service it holds,
    or decision wording in any policy text or stop message.

    Hard-fails when it examines zero stop kinds.
    """
    r = Result("V45 nothing-waits-on-owner")
    import stop_classes as _sc                             # noqa: PLC0415
    a = _sc.audit()
    r.examined += len(a["rows"])
    if not a["rows"]:
        r.fail("listed zero stop kinds")
        return r
    for p in a["problems"]:
        r.fail(p)
    r.note("stop kinds by class: " + ", ".join(
        f"{k} {v}" for k, v in sorted(a["counts"].items())))
    return r


def v42_authored_domain_is_allocated(items) -> Result:
    """HARD. No item this run hands to the Mac names a domain outside
    `loop/config.json` `domains.allocation`.

    2026-09-23 (domain-allocation gap, corrected scope). `loop/draft.py`'s
    `domains.allocation_gate()` now refuses to AUTHOR a topic outside
    `domains.allocation`, and `domains.row_domain()`'s result is threaded
    into every `author.draft(..., domain=...)` call so a generated script's
    own `**Domain:**` line can no longer default silently to deep sea
    (`author.DEFAULT_DOMAIN`) regardless of the topic — which is what
    happened to the four method-evidence/space scripts authored 2026-09-21
    (held in `loop/promotion_holds.json`, a separate, queue-shaped fix).

    This is the second half, guarding the OUTPUT rather than the call site:
    even a hand-authored script promoted straight into `scripts/`, or a
    future caller that bypasses the gate, cannot reach the Mac's render
    queue naming a domain with no publish slot, no
    `loop/domain_sources.py` allowlist and no `visuals/domains.py` palette.
    Every item must also carry a readable `**Domain:**` line at all — a
    script this validator cannot attribute to any domain cannot be proved
    against the allocation either, and is treated as a failure, not a pass.

    Hard-fails on zero items examined — this repo's Rule 0.
    """
    r = Result("V42 authored-domain-allocated")
    cfg = config()
    alloc = domains.allocation(cfg)
    for it in items:
        r.examined += 1
        script = it.get("script")
        p = ROOT / script if script else None
        dom = domains.domain_of_script(p) if p and p.exists() else None
        if dom is None:
            r.fail(f"{it['slug']}: {script or '<no script>'} carries no "
                   f"readable **Domain:** line — cannot be proved against "
                   f"domains.allocation")
        elif dom not in alloc:
            r.fail(f"{it['slug']}: domain {dom!r} is not in "
                   f"domains.allocation ({sorted(alloc)}) — no publish "
                   f"slot, no source allowlist and no palette for it")
    if r.examined == 0:
        r.fail("examined nothing")
    return r


# ------------------------------------------------------------------ runner

def run_all(items) -> tuple[bool, list[dict]]:
    """Run every validator. Returns (all_passed, report_rows).

    `items` is mutated: validators annotate each queue row with what they
    learned (pov line, source count, beat count), so the queue the Mac receives
    carries its own evidence.
    """
    results = [v1_directive_truth(), v2_planner(), v3_taxonomy(items),
               v4_pov(items), v5_sources_present(items), v6_attribution(items),
               v7_plans(items), v8_source_urls(items),
               v9_footage_window(), v10_footage_crop(), v11_footage_hash(),
               v12_footage_scope(), v13_render_not_clipped(),
               v14_shorts_attribution(), v15_shorts_caption_crop(),
               v20_cadence_schedule(), v21_no_boilerplate(),
               v22_producer_notes_second_person(), v23_chapters_compliant(),
               v24_render_duration_floor(), v25_domain_abstraction(),
               v27_lanes_see_every_domain(), v28_lane_interpreters(),
               v29_material_image_rights(), v30_cloud_visibility(),
               v31_render_has_thumbnail(),
               v32_scheduled_pov_is_hers(),
               v40_pov_assignment_integrity(),
               v33_every_domain_is_harvested(),
               v34_niche_lifecycle_is_acted_on(),
               v35_digest_reaches_her(),
               v36_editorial_gate_is_enforced(),
               v37_runtime_target_and_self_heal(),
               v38_no_duplicate_or_zombie_schedule(),
               v39_queue_depth_is_remaining_not_scored(),
               v42_authored_domain_is_allocated(items),
               v43_queue_asks_distinct_questions(items),
               v44_opening_payoff_first(items),
               v45_nothing_waits_on_the_owner()]
    rows = [r.as_dict() for r in results]
    return all(r.ok for r in results), rows


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--reach"]
    if "--reach" in sys.argv:
        ok, rows = run_reach()
    else:
        q = read_json(Path(argv[0]) if argv
                      else ROOT / "loop" / "render_queue.json")
        items = q["items"]
        ok, rows = run_all(items)
    for row in rows:
        print(f"{row['status']:<16} {row['validator']:<22} "
              f"examined {row['examined']}")
        for f in row["failures"]:
            print(f"    ✗ {f}")
        for st_ in row.get("stops") or []:
            print(f"    ■ NAMED STOP [{st_['code']}] {st_['message']}")
            for item in st_["items"]:
                print(f"        - {item}")
        for n in row["notes"]:
            print(f"    · {n}")
    print(json.dumps({"all_passed": ok}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
