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

V1-V15 and V20-V23 are the RENDER GATE: `run_all(items)`, run by loop/draft.py in front
of the pipeline. V16-V19 are the REACH group: `run_reach()`, run by
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

Every validator **hard-fails when it examined zero items.** A validator that
passes an empty loop is the defect it is supposed to catch.

Any failure here is a `validator` trip cause for the circuit breaker.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger  # noqa: E402
from common import ROOT, config, now, read_json, write_json  # noqa: E402
import exclusions  # noqa: E402

PY = sys.executable

# Source-shaped names the narration in this niche actually cites. A name that
# appears in the prose but not in ## Sources is an unbacked attribution.
ORG_NAMES = [
    "NOAA", "MBARI", "WHOI", "NASA", "USGS", "NSF", "IHO", "GEBCO",
    "Woods Hole Oceanographic Institution", "Woods Hole", "Smithsonian",
    "Monterey Bay Aquarium Research Institute", "Schmidt Ocean Institute",
    "National Geographic", "Guinness World Records", "Ocean Census",
    "Census of Marine Life", "Scripps", "JAMSTEC", "NIWA", "Nature",
    "Science", "Royal Society", "British Antarctic Survey",
]


class Result:
    def __init__(self, name: str):
        self.name = name
        self.examined = 0
        self.failures: list[str] = []
        self.notes: list[str] = []
        # Set only by a validator that legitimately governs nothing this week.
        # Never set it to quiet a validator that SHOULD have found items.
        self.exempt = False

    def fail(self, msg: str):
        self.failures.append(msg)

    def note(self, msg: str):
        self.notes.append(msg)

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
        return "PASS" if not self.failures else f"FAIL({len(self.failures)})"

    def as_dict(self):
        return {"validator": self.name, "examined": self.examined,
                "status": self.status, "failures": self.failures,
                "notes": self.notes}


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


ALIAS = {"WHOI": "Woods Hole", "Woods Hole": "WHOI",
         "MBARI": "Monterey Bay Aquarium Research Institute",
         "Monterey Bay Aquarium Research Institute": "MBARI",
         "Smithsonian": "ocean.si.edu", "NOAA": "noaa.gov", "NASA": "nasa.gov"}


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
        named = [n for n in ORG_NAMES if re.search(rf"\b{re.escape(n)}\b", prose)]
        missing = []
        for n in named:
            if re.search(rf"\b{re.escape(n)}\b", srcs, re.I):
                continue
            alt = ALIAS.get(n)
            if alt and re.search(re.escape(alt), srcs, re.I):
                continue
            missing.append(n)
        it["sources_cited"] = named
        it["attribution_gaps"] = missing
        if missing:
            gaps.append({"slug": it["slug"], "missing_from_sources": missing})
            r.note(f"{it['slug']}: narration names {', '.join(missing)} with no "
                   f"matching ## Sources entry")
    write_json(ROOT / "loop" / "state" / "attribution_gaps.json",
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
    for row in _live_videos():
        r.examined += 1
        vid, slug = row["video_id"], row["slug"]
        srt = Path(REACH_CAPTIONS_DIR) / f"{slug}.srt"
        if not srt.exists():
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
                r.note(f"{slug}: no track yet — deferred {days:.1f}d ago for "
                       f"quota, .srt is ready, the daily lane will take it")
                continue
            r.fail(f"{slug} ({vid}) has been waiting for a caption track for "
                   f"{days if days is not None else '?'} day(s) on a "
                   f"QUOTA_DEFERRED excuse that expires at "
                   f"{DEFER_GRACE_DAYS}. The backfill has stalled — check "
                   f"whether the reach lane is running at all.")
            continue
        r.fail(f"{slug} ({vid}) is published with NO English caption track, so "
               f"YouTube cannot auto-translate its subtitles or audio"
               + (" — and the scope that used to excuse this is now granted"
                  if have_scope and blocked else ""))
    if r.examined == 0:
        r.fail("no live video in loop/state/ledger.json — this validator "
               "proved nothing")
    return r


def v17_localizations() -> Result:
    """Every live video carries all five localizations."""
    r = Result("V17 localizations")
    state = read_json(LOCALIZATIONS_STATE, default={"videos": {}})
    for row in _live_videos():
        r.examined += 1
        vid, slug = row["video_id"], row["slug"]
        rec = (state.get("videos") or {}).get(vid) or {}
        got = sorted(rec.get("languages") or [])
        missing = [l for l in REACH_LANGUAGES if l not in got]
        if missing:
            r.fail(f"{slug} ({vid}) has no localized title/description for "
                   f"{', '.join(missing)} — it cannot be found by a search in "
                   f"those languages")
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
        fresh = backfill.schedule_for(led, max(4, per_week * 2), per_week)
        for when in fresh:
            r.examined += 1
            stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if stamp in taken:
                r.fail(f"the slot allocator handed out {stamp}, which episode "
                       f"{[t['slug'] for t in tail if t['scheduled_publish_at'] == stamp]} "
                       f"already holds — raising cadence must never re-date or "
                       f"double-book a scheduled episode")
            if when <= last:
                r.fail(f"the allocator handed out {stamp}, at or before the "
                       f"last scheduled episode ({last:%Y-%m-%dT%H:%M:%SZ}). "
                       f"New slots must CONTINUE the run, not reopen it")
            if when.astimezone(backfill.PUBLISH_TZ).weekday() in {2, 3}:
                r.fail(f"{stamp} falls on a Wednesday or Thursday")
        r.note(f"{len(tail)} episode(s) dated through "
               f"{last:%Y-%m-%d}; the next {len(fresh)} slot(s) all fall after "
               f"it at {per_week}/week")
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


def run_reach() -> tuple[bool, list[dict]]:
    """The post-publish reach validators. Separate from the render gate."""
    results = [v16_caption_track(), v17_localizations(),
               v18_default_language(), v19_snippet_merge()]
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
    "the channel", "monetiz", "watch time", "topic intelligence",
    "editorial reason", "pinned comment can", "engagement while",
    "production queue", "follow-up episodes with a real editorial",
    "the audience gets", "the audience helps", "for a channel trying",
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
               v22_producer_notes_second_person(), v23_chapters_compliant()]
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
        for n in row["notes"]:
            print(f"    · {n}")
    print(json.dumps({"all_passed": ok}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
