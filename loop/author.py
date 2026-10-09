"""The authoring lane. Drafts a script from a ranked topic, via OpenRouter.

This is the one stage where a language model touches the pipeline, and it is
therefore the single most likely source of a fabricated number or a source that
does not exist. Two things follow, and neither is negotiable:

* **`visuals/CONTRACT.md` rule 1 still governs.** A directive may not put a
  value on screen that the narration does not speak. The prompt states it; the
  validators enforce it at **full strength** on generated scripts — they are not
  relaxed because a machine wrote it, they matter more.
* **A drafted script carries its own `## Sources`,** and `loop/validate.py` V8
  fetches every URL. A plausible-looking citation that 404s is exactly what an
  LLM produces and exactly what a human reviewer skims past.

Drafts land in `loop/drafts/`, not `scripts/`. `scripts/` is the human-authored
record; keeping generated work in its own directory means provenance is a path,
not a convention someone has to remember.

Spend is logged per draft to `loop/state/spend.json`, from OpenRouter's own
reported usage rather than an estimate.

Key: `.secrets/openrouter_key.txt` or `$OPENROUTER_API_KEY`. One key, no
rotation. It is never printed, never logged, and never placed in a file the
loop commits.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import domain_sources  # noqa: E402
import durations  # noqa: E402
import exclusions  # noqa: E402
import opening  # noqa: E402
import pov_match  # noqa: E402
from common import LOOP, ROOT, config, now, read_json, write_json  # noqa: E402

DEFAULT_DOMAIN = "deep-sea-ocean-science"

# The channel-identity half of the prompt, per domain. Everything else in
# HOUSE_RULES (the one-rule-that-overrides-everything, tone, the never-list)
# is domain-agnostic house style; only the subject line and the source
# allowlist actually name deep sea. This dict, plus
# `loop/domain_sources.py`'s allowlist, is the whole of what used to be
# hardcoded here.
DOMAIN_BRIEF: dict[str, dict[str, str]] = {
    "deep-sea-ocean-science": {
        "subject": "deep sea and ocean science",
        "example_urls": (
            "https://oceanexplorer.noaa.gov/facts/ or "
            "https://ocean.si.edu/ecosystems/deep-sea/deep-sea"),
    },
    "materials-and-manufacturing": {
        "subject": "materials science and manufacturing — how something is "
                   "made, why a material behaves the way it does, and how "
                   "either is actually known",
        "example_urls": (
            "https://www.nist.gov/ or "
            "https://www.asminternational.org/"),
    },
}


def domain_brief(domain: str) -> dict[str, str]:
    b = DOMAIN_BRIEF.get(domain)
    if not b:
        raise KeyError(
            f"{domain!r} has no entry in loop/author.py DOMAIN_BRIEF. Every "
            f"domain that can be authored needs one; {len(DOMAIN_BRIEF)} "
            f"declared: {sorted(DOMAIN_BRIEF)}.")
    return b

DRAFTS = LOOP / "drafts"
SPEND = LOOP / "state" / "spend.json"
KEY_FILE = ROOT / ".secrets" / "openrouter_key.txt"
API = "https://openrouter.ai/api/v1/chat/completions"

# Sonnet 4.5 for ~$0.07 a script. The sub-cent models exist, but this stage
# writes factual claims with citations and a cheap model that invents a
# plausible NOAA URL costs far more than six cents to catch.
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


def configured_model() -> str:
    """The model every lane sends. `$OPENROUTER_MODEL` overrides DEFAULT_MODEL
    only when it actually names something.

    An EMPTY variable is "not configured", not "the empty model". GitHub
    Actions expands an unset repository variable to "" rather than leaving
    the env var out, so `os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)`
    returned "" in the cloud and OpenRouter answered every authoring call
    with HTTP 400 "No models provided". The Mac never saw it: there the
    variable is absent and the default applied. Run 35587241167, 2026-09-21
    — four topics unauthored, NO_SCRIPTS, red Monday.
    """
    return os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL

# Owner decision, 2026-09-01 (runtime target) and 2026-09-03 (hard floor):
# every batch from here is >=10 minutes, 10-11 targeted. Long-form is where
# YouTube rewards a channel, and the Partner Programme threshold is 4,000
# watch HOURS from long-form only - so runtime is a direct multiplier on the
# metric that gates monetisation.
#
# 2026-09-03 CORRECTION. This used to say "measured across all 16 finished
# episodes: ~1,200 narration words renders to 8.1 minutes, an effective 150
# words/minute" and set TARGET_WORDS=2750 as a WHOLE-SCRIPT count while the
# prompt below said "words of narration" - two different quantities called
# the same name. Neither 150 wpm nor 2750 was ever measured against a real
# render; it was copied from the same guess three call sites agreed on
# (loop/config.json retention.runtime_minutes, this constant, and the FORMAT
# template's "at 145 WPM"), which is a different failure mode from being
# wrong once. `loop/durations.py` is now the one place a speaking rate is
# measured, from real renders via ffprobe: **144.58 wpm**, range 133.5-154.2,
# across the 17 finished episodes with both a narration word count and a
# measured render. Budgets below are DERIVED from that, every run, not typed
# in twice.
#
# NARRATION_TARGET_WORDS is what the prompt tells the model to aim for, and it
# names itself correctly: narration words, the only count that becomes
# runtime. WHOLE_SCRIPT_TARGET_WORDS (directives, headings, chapters, sources
# included) is derived from the measured script_ratio (whole-script words :
# narration words, currently ~1.81) purely for the word-count metadata line
# in FORMAT; nothing enforces against it, because enforcing against a
# whole-script count is how a narration budget silently became a different
# number in the first place.
try:
    _MODEL = durations.model()
    WPM = _MODEL["wpm"]
    SCRIPT_RATIO = _MODEL["script_ratio"]
except durations.NotMeasured:
    # No cached loop/state/runtime_model.json and nothing to derive it from
    # on this machine. There is no safe constant to fall back to - that is
    # the exact defect this module exists to delete - so drafting refuses
    # rather than guessing.
    raise RuntimeError(
        "loop/author.py cannot draft without a measured speaking rate. Run "
        "`.venv/bin/python loop/durations.py --refresh` on a machine that "
        "has renders/*-final.mp4, commit loop/state/runtime_model.json, and "
        "retry.") from None

# ONE COPY OF THE NUMBER, AND IT LIVES IN loop/config.json. These were typed
# here as 10.5 and 10.0 while the config said the same thing, which is the
# duplicated-constant failure the comment above describes -- three call sites
# agreeing on a guess is not the same as one measured value. When the owner
# raised the target to 12 minutes on 2026-09-05 this file would have gone on
# drafting to 10.5 and every new episode would have landed a minute and a half
# short of the new target while the config said otherwise.
_RET = config()["retention"]
RUNTIME_TARGET_MINUTES = float(_RET["runtime_minutes"])
RUNTIME_FLOOR_MINUTES = float(_RET["runtime_floor_minutes"])
RUNTIME_TOLERANCE_PCT = float(_RET.get("runtime_tolerance_pct", 15.0))

# The band an episode is allowed to land in. Its LOWER edge sits above the hard
# floor by construction, so "inside the band" and "over the floor" can never
# disagree.
RUNTIME_BAND_MIN = RUNTIME_TARGET_MINUTES * (1 - RUNTIME_TOLERANCE_PCT / 100)
RUNTIME_BAND_MAX = RUNTIME_TARGET_MINUTES * (1 + RUNTIME_TOLERANCE_PCT / 100)
NARRATION_TARGET_WORDS = durations.narration_words_for(RUNTIME_TARGET_MINUTES)
NARRATION_FLOOR_WORDS = durations.narration_words_for(RUNTIME_FLOOR_MINUTES)
WHOLE_SCRIPT_TARGET_WORDS = round(NARRATION_TARGET_WORDS * SCRIPT_RATIO)
# 2026-09-21: was 2. The first cloud run that actually authored (35604701442)
# lost two of four slots to DRAFT_FAILED_VALIDATION: attempt 1 cited a
# plausible dead page (whoi.edu/what-we-do/understand/climate/,
# mbari.org/research/), attempt 2 replaced it with ANOTHER plausible dead
# page, and the slot fell to AUTHOR_REQUIRED — a red run asking a human to
# write a script. Guessing a URL is what a language model does; two guesses
# is not enough chances to stop. Four attempts bound the worst case at
# ~$0.28 a slot, ~$1.10 a week, inside the $2.50/day cap, and dead_urls()
# now hands back a page that is KNOWN to exist so the retry converges
# instead of guessing again.
MAX_ATTEMPTS = 4


class AuthorStop(Exception):
    """A named, expected reason no draft was produced. Never a crash."""

    def __init__(self, code: str, message: str, unblock: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.unblock = code, message, unblock


# ------------------------------------------------------------------- the key

def api_key() -> str | None:
    """Resolve the key. Returns None if absent; never raises, never logs it."""
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env:
        return env
    # LOOP_DRY_RUN: behave exactly as an un-credentialed machine would (the
    # same contract as upload.py). LOOP_NO_KEYFILE: the test suite's "no key
    # anywhere" case. test_authoring.py had set LOOP_NO_KEYFILE=1 since it was
    # written and nothing read it, so on a Mac holding the key file the
    # "missing key" check made a REAL paid draft — two attempts, ~$0.12 —
    # on every local suite run (the `a-test-topic` rows in spend.json,
    # 2026-09-05 to 2026-09-21).
    if os.environ.get("LOOP_DRY_RUN") == "1" or os.environ.get("LOOP_NO_KEYFILE") == "1":
        return None
    if KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
        if k:
            return k
    return None


def redact_key(k: str | None) -> str:
    if not k:
        return "<absent>"
    return f"sk-or-…{'*' * 8} ({len(k)} chars)"


# -------------------------------------------------------------------- prompt

HOUSE_RULES = """You are drafting a narration script for the YouTube channel
"How We Know" (@howweknowdeep) — an evidence-first explainer channel. This
script is for its {subject} coverage.

THE ONE RULE THAT OVERRIDES EVERYTHING:
Never state a number, date, measurement or proper name you are not certain of,
and never write a visual directive containing a value the narration does not
already speak. The rendering pipeline mechanically refuses to display any value
absent from the narration, and an automated validator checks every number and
every proper name in every directive against the prose. An invented figure does
not get published — it fails the build and wastes the week.

If you are not confident in a figure, do not use a figure. Write the sentence
without it, or state the uncertainty explicitly ("estimates vary", "the
published range is wide"). Stating a limit of the evidence is house style, not
a weakness.

SOURCES:
Every digit-bearing sentence must trace to a named public body that genuinely
publishes on this topic — {source_list}. List them under ## Sources with REAL,
working URLs on those bodies' own domains. Every URL is fetched by an
automated validator; a URL that 404s fails the script. Prefer a small number
of stable landing pages you are certain exist (for example {example_urls})
over deep links you are guessing at. If you name a body in the narration, it
must appear in ## Sources. Do not cite a body from this channel's OTHER
coverage areas — a source that publishes nothing about this script's subject
is not a real citation even if the channel has used it elsewhere.

NEVER include: medical, health, dietary or supplement advice; financial,
investment or legal advice; adult content; conspiracy, cryptid or paranormal
material framed as real; true crime or identifiable victims; political
controversy; religion framed as true or false; anything morally grey.

TONE: calm, precise, second person occasionally, no hype, no "mind-blowing",
no rhetorical questions stacked up. Explain how a thing is known, not just what
is known. The narration under ## Narration must be roughly {narration_target}
words - that is the ONLY count that becomes runtime; directives, headings,
chapter lists and sources are not narration and do not count toward it. At
the measured {wpm} words per minute that is about {target_minutes} minutes;
never draft under {narration_floor} narration words, the owner's hard
{floor_minutes}-minute floor.

OPENING SHAPE: state the answer's load-bearing figure in the cold open, with
its source, and then immediately open the epistemic loop — what that figure
does NOT settle, or the assumption it overturns. Do not spend the cold open
reframing the question instead of answering it; answer first, complicate
second. Example shape (a different subject, quoted for the SHAPE only —
do not reuse its content): "Hydrothermal vent fluid can exceed 340 degrees
Celsius and remain liquid. The boiling point you learned at sea level is not
a universal switch. Pressure moves it." Figure, source, real question — in
well under fifty words."""


FORMAT = """OUTPUT FORMAT — reproduce this structure exactly. It is the format of
the twenty existing scripts and the pipeline parses it.

# <the question, as a title, ending in ?>

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** {domain}
**Word count:** <approximate>
**Estimated narration:** <m>m <s>s at {wpm} WPM (measured, loop/durations.py)

## YouTube title

<ONE line of about 70 characters, NOT a question. Lead with the most specific,
surprising TRUE thing from your Direct-answer lock; keep EVERY word of the
question's subject so it still matches the search; end with "— and how we
know". Any number in it must appear in the Direct-answer lock. Shape, for the
question "what is the deepest fish ever recorded": "The deepest fish ever
recorded was filmed 8,336 m down — and how we know". No clickbait words.>

## Direct-answer lock

<One paragraph, 2-3 sentences, answering the question directly and completely.>

## Narration

### Cold open

<directive>
<One paragraph that starts mid-thought, no greeting, no "welcome back".>

### Title card

<the question again, as a plain line>

### <a section heading that states a claim, not a topic>

<directive>
<paragraph>

<directive>
<paragraph>

### Producer POV

[HUMAN] {pov_line}

### <more sections — five to eight of them, each with a claim heading>

### What to notice in the edit

<directive>
<paragraph>

### Evidence limit

<directive>
<A paragraph stating plainly what this evidence does NOT establish.>

### Closing

<directive>
<One short paragraph. No call to action, no "subscribe".>

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see V36 in `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK ({pov_id})
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: <one line describing this script's shape>
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- <one line per ### section, with a plausible increasing timestamp>

## Sources

- <Body name>: <page title> — <real working URL>
- <at least four, all reachable>"""


# The domain-agnostic v2 directives — no ocean or materials content, usable
# by any domain's structural device. Kept as one block so a domain cannot
# quietly drift onto a different epistemic-visual vocabulary from another.
DIRECTIVES_SHARED = """{{stat: VALUE | UNIT | CAPTION | SOURCE}}      one held number
{{timeline: YEAR=LABEL | YEAR=LABEL}}          2-6 dated events
{{chain: TITLE | STAGE | STAGE | >CONCLUSION}} instrument to conclusion
{{uncertain: VALUE | UNIT | RANGE | CONFIDENCE | CAPTION}}  needs a STATED range
{{sources: TITLE | NAME=CLAIM | NAME=CLAIM}}   2-4 bodies named in the prose
{{steps: TITLE | STEP | STEP | >NOTE}}         2-6 stages of a method
{{contrast: TERM | is=X | not=Y}}              both sides required
{{magnitude: TITLE | UNIT | NAME=VALUE | ...}} one shared unit, true zero
{{define: TERM | MEANING | BOUNDARY | SOURCE}} a term and its edge
{{checklist: TITLE | +MET | -UNMET | ?OPEN}}   states asserted by the prose
{{text}}                                       a typographic beat
{{ambient}}                                    breathing room"""

# The structural-device directives — ocean depth for deep sea, the thermal
# scale for materials-and-manufacturing. A domain's own device only; do not
# offer another domain's device directives here, or a draft can reference a
# visual its own render pipeline never built for it (visuals/CONTRACT.md
# Contract v3, visuals/domains.py).
DEVICE_DIRECTIVES: dict[str, str] = {
    "deep-sea-ocean-science": """{{descent: TO_M | LABEL}}                      a fall with a live counter
{{compare: NAME=M | NAME=M}}                   exactly two, above/below sea level
{{zones: HIGHLIGHT}}                           five-zone cross-section
{{pressure: DEPTH_M}}                          dial, atm = 1 + m/10
{{light}}                                      wavelength attenuation
{{anatomy: TITLE | LABEL@X,Y | LABEL@X,Y}}     x,y are 0-1 fractions
{{ladder: NAME=M | NAME=M}}                    2-6 item size comparison""",
    "materials-and-manufacturing": """{{thermal: TO_C | LABEL}}                      a rise through the thermal scale, live °C counter
{{stages: HIGHLIGHT}}                          five-band thermal-scale cross-section (AMBIENT/TEMPER/FORGE/MELT/PLASMA)
{{magnitude: TITLE | UNIT | NAME=VALUE | ...}} strong for comparing two materials' properties directly""",
}


def directives_for(domain: str) -> str:
    device = DEVICE_DIRECTIVES.get(domain)
    if device is None:
        raise KeyError(
            f"{domain!r} has no directive menu in loop/author.py "
            f"DEVICE_DIRECTIVES; {sorted(DEVICE_DIRECTIVES)} declared.")
    return f"""VISUAL DIRECTIVES — one on its own line immediately BEFORE the
paragraph it governs. They are stripped before narration is synthesised.

Rule: every number, name, stage, bound, step, boundary and criterion inside a
directive MUST appear verbatim in that same script's narration. The directive
labels what the prose says; it never adds a fact.

{device}
{DIRECTIVES_SHARED}

Use {{{{contrast}}}}, {{{{checklist}}}}, {{{{chain}}}}, {{{{steps}}}} and
{{{{define}}}} freely — they carry epistemic prose, which is most of this
channel. Use {{{{stat}}}} and {{{{uncertain}}}} ONLY where the narration
states that exact figure. Alternate directive types between adjacent
paragraphs; never repeat one more than twice in a row. If a paragraph has
nothing concrete, {{{{text}}}} or {{{{ambient}}}} is the correct and honest
answer."""


def build_prompt(question: str, pov: dict, domain: str = DEFAULT_DOMAIN) -> list[dict]:
    brief = domain_brief(domain)
    system = (HOUSE_RULES.format(
                  subject=brief["subject"],
                  source_list=", ".join(domain_sources.for_domain(domain)),
                  example_urls=brief["example_urls"],
                  narration_target=NARRATION_TARGET_WORDS, wpm=WPM,
                  target_minutes=RUNTIME_TARGET_MINUTES,
                  narration_floor=NARRATION_FLOOR_WORDS,
                  floor_minutes=RUNTIME_FLOOR_MINUTES) + "\n\n" +
              opening.prompt_text() + "\n\n" +
              directives_for(domain) + "\n\n" +
              FORMAT.format(pov_line=pov["line"], pov_id=pov["pov_id"],
                           domain=domain, wpm=WPM))
    user = (
        f"Draft the full script for this question:\n\n"
        f"    {question}\n\n"
        f"The Producer POV section must contain EXACTLY this line, unchanged, "
        f"prefixed with [HUMAN]. It is the owner's own words from her "
        f"interview and must not be paraphrased, extended or trimmed:\n\n"
        f"    {pov['line']}\n\n"
        f"Output the script and nothing else — no preamble, no explanation, "
        f"no code fences.")
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


# ---------------------------------------------------------------- the call

# A transient API 500 is item 13a's textbook case: known, safe, deterministic
# remedy (wait briefly, retry the exact same request), never masking a real
# defect because it only fires for the specific server-side codes that mean
# "try again", never for anything this lane's own request caused (401, 402,
# 403, 404, 429 all skip straight past this and reach the caller unchanged).
TRANSIENT_HTTP_CODES = (500, 502, 503, 504)
TRANSIENT_RETRIES = 3
TRANSIENT_BACKOFF_S = 2.0


def call_openrouter(messages: list[dict], model: str, key: str,
                    timeout: int = 300, temperature: float = 0.4) -> dict:
    """The one HTTP client for OpenRouter. Every lane uses this; none forks it.

    `temperature` defaults to 0.4 — factual work, not creative writing. The
    localisation lane passes 0.0: there is exactly one right way to say
    "deepest" in Indonesian and any sampling at all is a chance to miss it.

    SELF-HEALS a transient server error or a dropped connection: up to
    TRANSIENT_RETRIES attempts, `TRANSIENT_BACKOFF_S * attempt` between them.
    Every attempt after the first prints `[self-heal]` so it shows up in
    whichever lane's log called this — draft.py, advise.py and localize.py
    all go through here, so the fix is shared once rather than three times.
    A retry that still fails after the budget is exhausted raises normally;
    it never swallows the error; the caller's existing NAMED STOP path is the
    escalation, unchanged. A heal that keeps firing on every call is visible
    in the log by construction — the same log a human already reads for
    st.note() lines — rather than being silently absorbed forever.
    """
    if not (model or "").strip():
        # Refuse before the network: OpenRouter's answer to this is a 400
        # that names nothing useful. Resolve through configured_model().
        raise ValueError("call_openrouter: model is empty — resolve it with "
                         "author.configured_model(), never straight from "
                         "$OPENROUTER_MODEL")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 16000,
        "temperature": temperature,
        "usage": {"include": True},  # ask OpenRouter to report real cost
    }).encode()
    req_headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/seq23/how-we-know",
        "X-Title": "How We Know - authoring lane",
    }
    last_err: Exception | None = None
    for attempt in range(1, TRANSIENT_RETRIES + 1):
        req = urllib.request.Request(API, data=body, method="POST",
                                     headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if attempt > 1:
                    print(f"[self-heal] OpenRouter call succeeded on attempt "
                         f"{attempt}/{TRANSIENT_RETRIES} after "
                         f"{last_err.__class__.__name__ if last_err else ''} "
                         f"— healed, continuing", flush=True)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in TRANSIENT_HTTP_CODES or attempt == TRANSIENT_RETRIES:
                raise
            last_err = e
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if attempt == TRANSIENT_RETRIES:
                raise
            last_err = e
        print(f"[self-heal] OpenRouter attempt {attempt}/{TRANSIENT_RETRIES} "
             f"failed ({last_err.__class__.__name__}: {last_err}); retrying "
             f"in {TRANSIENT_BACKOFF_S * attempt:.0f}s — a transient server "
             f"error is the known, safe, deterministic case this retries",
             flush=True)
        time.sleep(TRANSIENT_BACKOFF_S * attempt)
    raise last_err  # pragma: no cover - loop always returns or raises above


def record_spend(slug: str, model: str, usage: dict, cost: float | None,
                 attempt: int, ok: bool) -> dict:
    log = read_json(SPEND, default={"drafts": [], "total_usd": 0.0})
    row = {
        "at": now(), "slug": slug, "model": model, "attempt": attempt,
        "accepted": ok,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cost_usd": round(cost, 6) if cost is not None else None,
    }
    log["drafts"].append(row)
    log["total_usd"] = round(
        sum(d["cost_usd"] or 0 for d in log["drafts"]), 6)
    log["drafts_written"] = sum(1 for d in log["drafts"] if d["accepted"])
    log["average_usd_per_accepted_draft"] = (
        round(log["total_usd"] / log["drafts_written"], 6)
        if log.get("drafts_written") else None)
    log["updated"] = now()
    write_json(SPEND, log)
    return row


# --------------------------------------------------------------- validation

# WHERE NARRATION ENDS. The gate section after it was "## Human fingerprint
# gate" until 2026-09-05, when V36 (loop/validate.py) retired that heading
# for "## Editorial gate" in every script on disk - and this template kept
# writing the old one. Every script the Monday lane authored afterwards was
# promoted into scripts/ carrying a heading V36 fails, so the NEXT run's full
# validation tripped the breaker on the previous week's work (found
# 2026-09-26 on six scripts). The generator and the validator now name one
# heading; the old one still ends narration so an older draft is read right.
NARRATION_ENDS = ("## Editorial gate", "## Human fingerprint")


def narration_text(text: str) -> str:
    """The ## Narration section of a script, up to its gate section."""
    body = text.split("## Narration", 1)[-1]
    for stop in NARRATION_ENDS:
        body = body.split(stop, 1)[0]
    return body


REQUIRED_SECTIONS = ["## Direct-answer lock", "## Narration",
                     "## Editorial gate", "## Chapters", "## Sources"]


# Same rule as tests/test_directive_truth.py's V1 check ("a directive may not
# put a value on screen its own script does not speak"), reapplied HERE, one
# generation attempt earlier, so the model's own retry loop can fix it before
# the draft is ever written to disk. This is the self-heal item 13a asks for:
# extending the retry loop already in draft() rather than only catching the
# defect after the fact in the full validate.run_all() batch gate, where
# nothing retries and the draft is simply rejected wholesale.
_DIRECTIVE_KINDS = ("chain", "uncertain", "sources", "steps", "contrast",
                   "magnitude", "define", "checklist")
_PUNC = str.maketrans("", "", "“”\"'’‘()[]{},.;:!?")
_STRUCT = set("IS NOT AND OR OF TO IN ON AT FOR WITH FROM A AN THE".split())


def _stem(w: str) -> str:
    w = w.lower()
    for suf in ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s",
               "ly", "d"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def directive_parse_problems(text: str) -> list[str]:
    """Every v2 directive in the narration must parse AND render with the
    planner the Mac renders from. Mirrors tests/test_directive_truth.py's
    check_parses() against one in-memory draft, so a directive the planner
    would silently drop is redrafted inside the retry loop instead of failing
    V1 on next week's full validation."""
    if "## Narration" not in text:
        return []
    visuals = str(Path(__file__).resolve().parent.parent / "visuals")
    if visuals not in sys.path:
        sys.path.insert(0, visuals)
    # Imported here, not at module top: visuals/ is only on sys.path after the
    # insert above, and planner/segments_ext2 pull in PIL, which no other
    # author.py caller needs.
    import planner  # noqa: PLC0415 - visuals/ is on sys.path only from here
    import segments_ext2  # noqa: PLC0415 - same; importing it installs the v2 parser
    out = []
    for line in narration_text(text).split("\n"):
        line = line.strip()
        m = re.match(r"^\{\{\s*(\w+)\s*:?\s*(.*?)\s*\}\}$", line)
        if not (m and m.group(1).lower() in _DIRECTIVE_KINDS):
            continue
        got = planner.parse_directive(line)
        if got is None:
            out.append(f"the directive {line[:90]!r} does not parse, so the "
                       f"renderer would drop it silently. See "
                       f"visuals/CONTRACT.md for its arguments: a VALUE must "
                       f"be a number written in digits, an {{{{uncertain}}}} "
                       f"RANGE a +/- half-width or LOW to HIGH, and a number "
                       f"with no stated range is a {{{{stat}}}}.")
            continue
        seg, kw = got
        try:
            getattr(segments_ext2, seg)(0.7, **kw)
        except Exception as e:  # noqa: BLE001 - any renderer error is a draft defect to feed back, never a crash of the retry loop
            out.append(f"the directive {line[:90]!r} parses but does not "
                       f"render: {type(e).__name__}: {e}")
    return out


def directive_truth_problems(text: str) -> list[str]:
    """Every number and proper noun a v2 directive draws must already be in
    this script's own narration prose. Mirrors tests/test_directive_truth.py's
    check() exactly, against one in-memory draft rather than every file on
    disk, so it can run inside the retry loop before anything is written."""
    if "## Narration" not in text:
        return []
    body = narration_text(text)
    prose = " ".join(l for l in body.split("\n") if not l.strip().startswith("{{"))
    plow = prose.lower()
    flags = []
    for line in body.split("\n"):
        line = line.strip()
        m = re.match(r"^\{\{\s*(\w+)\s*:?\s*(.*?)\s*\}\}$", line)
        if not (m and m.group(1).lower() in _DIRECTIVE_KINDS):
            continue
        fields = m.group(2).split("|")
        for num in re.findall(r"\d[\d,\.]*", fields[0]):
            if num.lower() not in plow:
                flags.append(f"directive draws number {num!r} the narration "
                            f"never speaks: {line[:74]!r}")
        if m.group(1).lower() == "uncertain":
            flags += _uncertain_range_problems(fields, line)
        parts = re.split(r"[|=]", "|".join(fields[1:]))
        for part in parts:
            for num in re.findall(r"\d[\d,\.]*", part):
                if num.lower() not in plow:
                    flags.append(f"directive draws number {num!r} the "
                                f"narration never speaks: {line[:74]!r}")
            toks = part.split()
            for i, tok in enumerate(toks):
                t = tok.translate(_PUNC).lstrip("+-?>")
                if not t or not t[0].isupper() or i == 0:
                    continue
                if t.upper() in _STRUCT or t.lower() in plow:
                    continue
                if _stem(t) and _stem(t) in plow:
                    continue
                if t.endswith("s") and t[:-1].lower() + "'s" in plow:
                    continue
                flags.append(f"directive draws name {t!r} the narration "
                            f"never speaks: {line[:74]!r}")
    return flags


def _uncertain_range_problems(fields: list[str], line: str) -> list[str]:
    """`{{uncertain: VALUE | UNIT | RANGE | ...}}`'s RANGE must be a number.

    visuals/segments_ext2.py parses RANGE as the ± half-width (or `PLUS/MINUS`)
    and returns None - the beat is silently dropped from the render - when it
    is anything else. Run 36164079633 (2026-09-25) wrote
    `range 700000 to 2200000`, prose that no parser reads, and nothing before
    the render would have said so. The contract's rule 7 is the source.
    """
    if len(fields) < 3 or not fields[2].strip():
        return [f"uncertain directive has no RANGE field; visuals/CONTRACT.md "
                f"rule 7 requires a stated ± half-width: {line[:74]!r}"]
    rng = fields[2].strip().lstrip("±+")
    parts = [p.strip().lstrip("+-") for p in rng.partition("/")[::2]] \
        if "/" in rng else [rng]
    for p in parts:
        if not re.fullmatch(r"\d[\d,]*(\.\d+)?", p):
            return [f"uncertain directive's RANGE {fields[2].strip()!r} is not "
                    f"a number: write the ± half-width in the same unit as "
                    f"VALUE (e.g. `750000`, or `200000/1300000` for asymmetric "
                    f"bounds); the renderer drops a directive it cannot "
                    f"parse: {line[:74]!r}"]
    return []


# The rejection alone was not enough. On 2026-09-25 (run 36164079633) the
# model was told four times that `{{uncertain: 2000000 | ...}}` drew a number
# its prose never spoke, and four times answered with prose that said "2
# million" - a true statement of the same figure that is not the same string,
# on a screen that draws the string. The fault was named and the remedy never
# was; a retry loop that repeats a diagnosis without a fix is four paid
# attempts at the same mistake. This is the fix, stated once, whenever that
# class of problem is in the list.
DIRECTIVE_REMEDY = (
    "HOW TO FIX A 'directive draws ... the narration never speaks' REJECTION: "
    "a directive's VALUE, names and bounds are drawn on screen exactly as "
    "typed, so the narration paragraph it governs must contain the identical "
    "string - same digits, same separators, same spelling. Either write the "
    "figure in the prose the way the directive has it (`2,000,000` in both), "
    "or change the directive to the way the prose says it (`2 million` as the "
    "VALUE). Do not solve it by deleting the figure from the directive while "
    "the prose keeps it, and do not solve it by adding a number the sources "
    "do not support.")


def shape_problems(text: str, pov: dict) -> list[str]:
    """Cheap structural checks before the expensive ones. Not a substitute for
    loop/validate.py — that still runs at full strength afterwards."""
    p = []
    for s in REQUIRED_SECTIONS:
        if s not in text:
            p.append(f"missing section {s!r}")
    if not text.lstrip().startswith("# "):
        p.append("does not begin with a '# ' title")
    if "### Producer POV" not in text:
        p.append("missing '### Producer POV'")
    elif pov["line"].strip()[:60] not in text:
        p.append("the Producer POV line was altered; it must be verbatim from "
                 "the POV bank")
    src = text.split("## Sources")[-1] if "## Sources" in text else ""
    urls = re.findall(r"https?://[^\s)>\]]+", src)
    if len(urls) < 3:
        p.append(f"only {len(urls)} source URL(s); at least 3 required")
    # Truncation detection. The first real draft ended mid-URL with every
    # section present and four good citations - it looked completely fine.
    # finish_reason is the authoritative signal (checked by the caller); this
    # is the belt to that braces: the final source entry must be a COMPLETE
    # entry, not a title trailing off into a bare domain.
    if src.strip():
        last = [l for l in src.strip().splitlines() if l.strip()][-1]
        if not re.match(r"^\s*-\s+.+?\s+[-\u2014]{1,2}\s+https?://\S{12,}\s*$",
                        last):
            p.append(f"the last ## Sources entry is incomplete, so the draft "
                     f"looks truncated: {last.strip()[:80]!r}")
    nar = narration_text(text)
    words = len([w for w in re.sub(r"\{\{[^}]*\}\}", " ", nar).split()])
    # 2026-09-03: this used to reject under 1,400 words and call it "9.3
    # minutes" at an assumed 150 wpm. At the MEASURED rate (144.58 wpm, see
    # loop/durations.py) 1,400 words is 9.68 minutes, not 9.3 - close, but
    # the point of measuring is that no one has to eyeball "close enough"
    # again. NARRATION_FLOOR_WORDS is the owner's hard 10-minute floor,
    # derived from the same measurement every other call site now reads.
    if words < NARRATION_FLOOR_WORDS:
        p.append(f"narration is only {words} words; at the measured {WPM} wpm "
                 f"that is ~{words / WPM:.1f} minutes, under the "
                 f"{RUNTIME_FLOOR_MINUTES}-minute hard floor "
                 f"({NARRATION_FLOOR_WORDS} words minimum)")
    # The gate that carries the owner's judgement applies to generated text
    # too - in narration mode, which targets advice-giving and false framing
    # rather than vocabulary. The topic itself was already gated by decide().
    d = exclusions.decide_body(text)
    if not d.admitted:
        p.append(f"generated text touches a hard exclusion: {d.rule} "
                 f"(matched {d.matched!r})")
    # 2026-08-31: the one real authoring run failed the FULL validate.run_all()
    # gate on "V1 directive-truth FAIL(1)" — a directive drawing a number or
    # name its own narration never spoke. Nothing in the retry loop above
    # could have caught it, because it is the SAME rule loop/validate.py V1
    # enforces, checked one stage later where nothing retries. Checking it
    # here means a model that draws an inert directive gets the chance to fix
    # it inside its own MAX_ATTEMPTS attempts, the same as every other structural
    # problem in this function.
    p += directive_truth_problems(text)
    # AND THE OTHER HALF OF V1: every v2 directive must PARSE. Found
    # 2026-09-26 - three generated scripts in scripts/ carried an
    # {{uncertain}} whose VALUE or RANGE the planner cannot read (a prose
    # range, a number in words), which the truth check above cannot see: it
    # only asks whether the numbers were spoken. The full V1 caught them a
    # week later, where nothing retries and the breaker trips.
    p += directive_parse_problems(text)
    # THE OPENING RULE (loop/opening.py, 2026-09-25): the payoff inside the
    # first 30 seconds. A draft that buries its answer is fed back and
    # REDRAFTED inside MAX_ATTEMPTS like every other shape problem, never
    # held for a person.
    p += opening.problems(text, opening.active())
    return p


def nearest_live_ancestor(url: str, probe) -> str | None:
    """Walk a dead URL's path upward and return the first page that exists.

    `https://www.mbari.org/research/` is dead; `https://www.mbari.org/` is
    not. A model that guessed the deep page is told the shallow one is real,
    so its next draft can cite a page that exists instead of guessing a
    second deep page. Returns None when nothing up to the origin answers 200.
    """
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    segs = [x for x in parts.path.split("/") if x]
    while segs:
        segs.pop()
        cand = urlunsplit((parts.scheme, parts.netloc,
                           "/" + "/".join(segs) + ("/" if segs else ""), "", ""))
        code, _ = probe(cand)
        if code == 200:
            return cand
    return None


def dead_urls(text: str) -> list[str]:
    """Return a problem line for every source URL that does not resolve.

    Reuses loop/validate.py's probe so the drafting loop and the validator can
    never disagree about what "reachable" means. A dead URL's feedback names
    the nearest page on the same site that DOES exist, so the retry has a
    verified option and does not have to guess a second time.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate import probe
    src = text.split("## Sources")[-1] if "## Sources" in text else ""
    out = []
    for u in re.findall(r"https?://[^\s)>\]]+", src):
        code, why = probe(u)
        if code in (404, 410):
            live = nearest_live_ancestor(u, probe)
            hint = (f" The nearest page on that site that does exist is {live} "
                    f"- cite it ONLY if it genuinely supports the claim."
                    if live else "")
            out.append(f"source URL returns HTTP {code} and does not exist: {u}"
                       f" - replace it with a page you are certain of, or drop "
                       f"the claim it supports.{hint}")
        elif code == 0:
            out.append(f"source URL is unreachable ({why}): {u}")
    return out


# ------------------------------------------------------------------- public

def draft(question: str, slug: str, pov: dict, model: str | None = None,
          key: str | None = None, domain: str = DEFAULT_DOMAIN) -> dict:
    """Draft one script. Raises AuthorStop for every expected failure."""
    key = key or api_key()
    if not key:
        raise AuthorStop(
            "OPENROUTER_KEY_MISSING",
            "no OpenRouter key, so nothing could be authored",
            f"Put the key in {KEY_FILE} (gitignored) or set "
            f"$OPENROUTER_API_KEY.")
    model = model or configured_model()
    messages = build_prompt(question, pov, domain)
    DRAFTS.mkdir(parents=True, exist_ok=True)

    last: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = call_openrouter(messages, model, key)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            # Never let a key reach a log, even via an echoed request.
            detail = detail.replace(key, redact_key(key))
            if e.code in (401, 403):
                raise AuthorStop("OPENROUTER_UNAUTHORISED",
                                 f"OpenRouter rejected the key (HTTP {e.code})",
                                 "Check the key is current and the account is "
                                 "funded: https://openrouter.ai/settings/keys")
            if e.code == 402:
                raise AuthorStop("OPENROUTER_OUT_OF_CREDIT",
                                 "the OpenRouter account is out of credit",
                                 "Top up at https://openrouter.ai/credits")
            if e.code == 429:
                raise AuthorStop("OPENROUTER_RATE_LIMITED",
                                 "OpenRouter rate limited this request",
                                 "Re-run the stage later; the queue is unchanged.")
            raise AuthorStop("OPENROUTER_ERROR",
                             f"OpenRouter returned HTTP {e.code}", detail)
        except Exception as e:
            raise AuthorStop("OPENROUTER_UNREACHABLE",
                             f"{type(e).__name__} calling OpenRouter",
                             "Check network access and re-run.")

        choice = (resp.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason") or choice.get("native_finish_reason")
        usage = resp.get("usage") or {}
        cost = usage.get("cost")
        if cost is None and usage.get("cost_details"):
            cost = usage["cost_details"].get("upstream_inference_cost")

        text = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", text.strip())
        problems = shape_problems(text, pov)
        # Fetch every citation BEFORE accepting the draft. On the first real
        # run, two of five URLs from a frontier model were plausible-looking
        # 404s - which is precisely the failure a human reviewer skims past.
        # Feeding the dead URLs back is far cheaper than failing the week.
        problems += dead_urls(text)
        # A truncated draft is the failure mode that looks most like success:
        # it has every section, plausible sources, and simply stops mid-URL.
        # The first real draft did exactly this and the shape checks passed it.
        if finish and finish not in ("stop", "end_turn"):
            problems.insert(0, f"output was cut off (finish_reason={finish!r}); "
                               f"the draft is incomplete")
        record_spend(slug, model, usage, cost, attempt, not problems)

        if not problems:
            # Stamp the opening variant it was drafted and checked under, so
            # the Friday measure lane can put this video in its cohort.
            text = opening.mark(text, opening.active())
            path = DRAFTS / f"{slug}.md"
            path.write_text(text)
            return {"path": str(path.relative_to(ROOT)), "model": model,
                    "cost_usd": round(cost, 6) if cost is not None else None,
                    "attempt": attempt, "words": len(text.split()),
                    "usage": usage}

        last = problems
        remedy = ("\n\n" + DIRECTIVE_REMEDY
                  if any(p.startswith("directive draws") or
                         p.startswith("uncertain directive") for p in problems)
                  else "")
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user",
             "content": "That draft was rejected by the automated checks:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + remedy
                        + "\n\nOutput the corrected full script and nothing "
                          "else."}]

    raise AuthorStop(
        "DRAFT_FAILED_VALIDATION",
        f"{MAX_ATTEMPTS} attempts all failed structural checks: "
        + "; ".join(last),
        "Falls back to AUTHOR_REQUIRED: the brief stays in loop/briefs/ for a "
        "human. The week still ships whatever inventory covers.")


def draft_topic(topic: dict, used_pov: list[str] | None = None) -> dict:
    """Draft from a ranked topic row, matching a POV line automatically.

    Two different vocabularies both happen to be called "domain" in this
    repo, and `topic` may carry either or both:

      * `topic["domain"]`, an `loop/exclusions.py` ADMITTED_BUCKETS name
        (e.g. "deep-sea-biology", "method-evidence") — `research/filter.py`'s
        bucket taxonomy, older than and unrelated to the scored content
        taxonomy. Passed to `exclusions.decide` unchanged, exactly as
        before; `None` skips that particular check rather than failing it,
        which is correct for a domain (like materials) that predates the
        bucket taxonomy and fits none of its buckets.
      * `topic["content_domain"]`, a `research/proposed-taxonomy.json`
        `ranked_domains` name (e.g. "materials-and-manufacturing") — what
        `DOMAIN_BRIEF`/`domain_sources` need to write the right prompt and
        cite the right sources. Falls back to `DEFAULT_DOMAIN`
        (deep-sea-ocean-science) so every existing caller that has never
        heard of `content_domain` keeps authoring exactly as before.

    Conflating them (an earlier version of this function read
    `topic["domain"]` for both) passed bucket names like "deep-sea-biology"
    into the content-domain lookup, which would have raised for every real
    deep-sea topic loop/rank.py hands this function, not just an
    out-of-taxonomy smoke test.
    """
    question = topic["query"] if "query" in topic else topic["question"]
    content_domain = topic.get("content_domain") or DEFAULT_DOMAIN
    d = exclusions.decide(question, topic.get("domain"))
    if not d.admitted:
        raise AuthorStop("TOPIC_EXCLUDED",
                         f"refusing to author {question!r}: {d.reason}",
                         "The exclusion gate is the owner's standing judgement; "
                         "this is correct behaviour, not a bug.")
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:60]
    pov = pov_match.select(slug, question, used_pov or [])
    out = draft(question, slug, pov, domain=content_domain)
    out.update({"slug": slug, "question": question, "pov_id": pov["pov_id"],
                "pov_line": pov["line"], "domain": content_domain})
    return out


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "how do scientists measure the depth of the ocean"
    print(f"key   : {redact_key(api_key())}")
    print(f"model : {configured_model()}")
    print(f"topic : {q}\n")
    t0 = time.time()
    try:
        r = draft_topic({"query": q, "domain": "method-evidence"})
    except AuthorStop as e:
        print(f"\nNAMED STOP [{e.code}]\n  {e.message}\n  unblock: {e.unblock}")
        sys.exit(0)
    print(f"drafted {r['path']}  {r['words']} words  attempt {r['attempt']}")
    print(f"cost    ${r['cost_usd']}   in {time.time()-t0:.0f}s")
    print(f"pov     {r['pov_id']}")
