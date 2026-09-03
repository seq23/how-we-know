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

import durations  # noqa: E402
import exclusions  # noqa: E402
import pov_match  # noqa: E402
from common import LOOP, ROOT, now, read_json, write_json  # noqa: E402

DRAFTS = LOOP / "drafts"
SPEND = LOOP / "state" / "spend.json"
KEY_FILE = ROOT / ".secrets" / "openrouter_key.txt"
API = "https://openrouter.ai/api/v1/chat/completions"

# Sonnet 4.5 for ~$0.07 a script. The sub-cent models exist, but this stage
# writes factual claims with citations and a cheap model that invents a
# plausible NOAA URL costs far more than six cents to catch.
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

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

RUNTIME_TARGET_MINUTES = 10.5
RUNTIME_FLOOR_MINUTES = 10.0        # owner's hard floor, 2026-09-03
NARRATION_TARGET_WORDS = durations.narration_words_for(RUNTIME_TARGET_MINUTES)
NARRATION_FLOOR_WORDS = durations.narration_words_for(RUNTIME_FLOOR_MINUTES)
WHOLE_SCRIPT_TARGET_WORDS = round(NARRATION_TARGET_WORDS * SCRIPT_RATIO)
MAX_ATTEMPTS = 2


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
"How We Know" (@howweknowdeep) — an evidence-first explainer channel about deep
sea and ocean science.

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
publishes on this topic — NOAA, NOAA Ocean Exploration, MBARI, Woods Hole
Oceanographic Institution, Smithsonian Ocean, USGS, NASA, Schmidt Ocean
Institute. List them under ## Sources with REAL, working URLs on those domains.
Every URL is fetched by an automated validator; a URL that 404s fails the
script. Prefer a small number of stable landing pages you are certain exist
(for example https://oceanexplorer.noaa.gov/facts/ or
https://ocean.si.edu/ecosystems/deep-sea/deep-sea) over deep links you are
guessing at. If you name a body in the narration, it must appear in ## Sources.

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
{floor_minutes}-minute floor."""


FORMAT = """OUTPUT FORMAT — reproduce this structure exactly. It is the format of
the twenty existing scripts and the pipeline parses it.

# <the question, as a title, ending in ?>

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Word count:** <approximate>
**Estimated narration:** <m>m <s>s at {wpm} WPM (measured, loop/durations.py)

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

## Human fingerprint gate

- Humanized cold open: DRAFTED — owner must confirm it sounds natural read aloud.
- First-person producer observation: FROM POV BANK ({pov_id}) — owner-approved voice.
- Evidence uncertainty or limitation: <COMPLETE or PENDING>
- Structural variation: <one line describing this script's shape>
- Number-level source audit: <COMPLETE or PENDING>
- Final human watch-through: PENDING until the rendered MP4 exists.

## Chapters

- 00:00 Cold open
- <one line per ### section, with a plausible increasing timestamp>

## Sources

- <Body name>: <page title> — <real working URL>
- <at least four, all reachable>"""


DIRECTIVES = """VISUAL DIRECTIVES — one on its own line immediately BEFORE the
paragraph it governs. They are stripped before narration is synthesised.

Rule: every number, name, stage, bound, step, boundary and criterion inside a
directive MUST appear verbatim in that same script's narration. The directive
labels what the prose says; it never adds a fact.

{{stat: VALUE | UNIT | CAPTION | SOURCE}}      one held number
{{descent: TO_M | LABEL}}                      a fall with a live counter
{{compare: NAME=M | NAME=M}}                   exactly two, above/below sea level
{{zones: HIGHLIGHT}}                           five-zone cross-section
{{pressure: DEPTH_M}}                          dial, atm = 1 + m/10
{{light}}                                      wavelength attenuation
{{timeline: YEAR=LABEL | YEAR=LABEL}}          2-6 dated events
{{anatomy: TITLE | LABEL@X,Y | LABEL@X,Y}}     x,y are 0-1 fractions
{{ladder: NAME=M | NAME=M}}                    2-6 item size comparison
{{chain: TITLE | STAGE | STAGE | >CONCLUSION}} instrument to conclusion
{{uncertain: VALUE | UNIT | RANGE | CONFIDENCE | CAPTION}}  needs a STATED range
{{sources: TITLE | NAME=CLAIM | NAME=CLAIM}}   2-4 bodies named in the prose
{{steps: TITLE | STEP | STEP | >NOTE}}         2-6 stages of a method
{{contrast: TERM | is=X | not=Y}}              both sides required
{{magnitude: TITLE | UNIT | NAME=VALUE | ...}} one shared unit, true zero
{{define: TERM | MEANING | BOUNDARY | SOURCE}} a term and its edge
{{checklist: TITLE | +MET | -UNMET | ?OPEN}}   states asserted by the prose
{{text}}                                       a typographic beat
{{ambient}}                                    breathing room

Use {{contrast}}, {{checklist}}, {{chain}}, {{steps}} and {{define}} freely —
they carry epistemic prose, which is most of this channel. Use {{stat}} and
{{uncertain}} ONLY where the narration states that exact figure. Alternate
directive types between adjacent paragraphs; never repeat one more than twice
in a row. If a paragraph has nothing concrete, {{text}} or {{ambient}} is the
correct and honest answer."""


def build_prompt(question: str, pov: dict) -> list[dict]:
    system = (HOUSE_RULES.format(
                  narration_target=NARRATION_TARGET_WORDS, wpm=WPM,
                  target_minutes=RUNTIME_TARGET_MINUTES,
                  narration_floor=NARRATION_FLOOR_WORDS,
                  floor_minutes=RUNTIME_FLOOR_MINUTES) + "\n\n" +
              DIRECTIVES + "\n\n" +
              FORMAT.format(pov_line=pov["line"], pov_id=pov["pov_id"], wpm=WPM))
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

REQUIRED_SECTIONS = ["## Direct-answer lock", "## Narration",
                     "## Human fingerprint gate", "## Chapters", "## Sources"]


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


def directive_truth_problems(text: str) -> list[str]:
    """Every number and proper noun a v2 directive draws must already be in
    this script's own narration prose. Mirrors tests/test_directive_truth.py's
    check() exactly, against one in-memory draft rather than every file on
    disk, so it can run inside the retry loop before anything is written."""
    if "## Narration" not in text:
        return []
    body = text.split("## Narration", 1)[1].split("## Human fingerprint", 1)[0]
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
    nar = text.split("## Narration", 1)[-1].split("## Human fingerprint", 1)[0]
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
    # it inside its own two attempts, the same as every other structural
    # problem in this function.
    p += directive_truth_problems(text)
    return p


def dead_urls(text: str) -> list[str]:
    """Return a problem line for every source URL that does not resolve.

    Reuses loop/validate.py's probe so the drafting loop and the validator can
    never disagree about what "reachable" means.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate import probe
    src = text.split("## Sources")[-1] if "## Sources" in text else ""
    out = []
    for u in re.findall(r"https?://[^\s)>\]]+", src):
        code, why = probe(u)
        if code in (404, 410):
            out.append(f"source URL returns HTTP {code} and does not exist: {u}"
                       f" - replace it with a page you are certain of, or drop "
                       f"the claim it supports")
        elif code == 0:
            out.append(f"source URL is unreachable ({why}): {u}")
    return out


# ------------------------------------------------------------------- public

def draft(question: str, slug: str, pov: dict, model: str | None = None,
          key: str | None = None) -> dict:
    """Draft one script. Raises AuthorStop for every expected failure."""
    key = key or api_key()
    if not key:
        raise AuthorStop(
            "OPENROUTER_KEY_MISSING",
            "no OpenRouter key, so nothing could be authored",
            f"Put the key in {KEY_FILE} (gitignored) or set "
            f"$OPENROUTER_API_KEY.")
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    messages = build_prompt(question, pov)
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
            path = DRAFTS / f"{slug}.md"
            path.write_text(text)
            return {"path": str(path.relative_to(ROOT)), "model": model,
                    "cost_usd": round(cost, 6) if cost is not None else None,
                    "attempt": attempt, "words": len(text.split()),
                    "usage": usage}

        last = problems
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user",
             "content": "That draft was rejected by the automated checks:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\n\nOutput the corrected full script and nothing "
                          "else."}]

    raise AuthorStop(
        "DRAFT_FAILED_VALIDATION",
        f"{MAX_ATTEMPTS} attempts all failed structural checks: "
        + "; ".join(last),
        "Falls back to AUTHOR_REQUIRED: the brief stays in loop/briefs/ for a "
        "human. The week still ships whatever inventory covers.")


def draft_topic(topic: dict, used_pov: list[str] | None = None) -> dict:
    """Draft from a ranked topic row, matching a POV line automatically."""
    question = topic["query"] if "query" in topic else topic["question"]
    d = exclusions.decide(question, topic.get("domain"))
    if not d.admitted:
        raise AuthorStop("TOPIC_EXCLUDED",
                         f"refusing to author {question!r}: {d.reason}",
                         "The exclusion gate is the owner's standing judgement; "
                         "this is correct behaviour, not a bug.")
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:60]
    pov = pov_match.select(slug, question, used_pov or [])
    out = draft(question, slug, pov)
    out.update({"slug": slug, "question": question, "pov_id": pov["pov_id"],
                "pov_line": pov["line"]})
    return out


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "how do scientists measure the depth of the ocean"
    print(f"key   : {redact_key(api_key())}")
    print(f"model : {os.environ.get('OPENROUTER_MODEL', DEFAULT_MODEL)}")
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
