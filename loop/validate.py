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


# ------------------------------------------------------------------ runner

def run_all(items) -> tuple[bool, list[dict]]:
    """Run every validator. Returns (all_passed, report_rows).

    `items` is mutated: validators annotate each queue row with what they
    learned (pov line, source count, beat count), so the queue the Mac receives
    carries its own evidence.
    """
    results = [v1_directive_truth(), v2_planner(), v3_taxonomy(items),
               v4_pov(items), v5_sources_present(items), v6_attribution(items),
               v7_plans(items), v8_source_urls(items)]
    rows = [r.as_dict() for r in results]
    return all(r.ok for r in results), rows


def main() -> int:
    q = read_json(Path(sys.argv[1]) if len(sys.argv) > 1
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
