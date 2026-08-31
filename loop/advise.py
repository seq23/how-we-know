"""Ask a language model to read the month and say what it sees.

**Why this exists at all.** The monthly review's automatic decision is a handful
of thresholds. Thresholds can only find what was anticipated when they were
written. On the 1st of the month nothing intelligent is present - the loop runs
alone - so the honest comparison is not "a model versus me", it is "a model
versus a few if-statements". The owner made that argument on 2026-08-31 and she
was right.

**The split that keeps it safe.** The model decides WHAT; the fence decides WHAT
IS ALLOWED.

Owner instruction, 2026-08-31: *"i want it to decide advise email and follow
advice as a default. and if i have an issue with the advice ill step in."* So the
recommendation is APPLIED, not merely printed - but through exactly the same
bounds the deterministic rules use: a floor, a ceiling, one change per month, and
a cooldown after any change.

That boundary is the whole safety argument. A model that can set any value in
`loop/config.json` has no floor and no memory of last month; a model that can
only move a named parameter inside a stated range cannot run away, however wrong
it is. It may also propose things outside the fence - a different cadence, a new
topic domain - and those are REPORTED and not applied, because they are
irreversible in a way runtime length is not.

When the model and the rules disagree, the model wins. That is the instruction,
and it is defensible precisely because the fence holds either way.

**It is additive, never a dependency.** No key, no credit, an API error, a
timeout, a refusal - any of them and the review still runs, still decides, still
emails. A missing advisory is a line in the report, not a failed stage. That
matters more than the advice does: the measurement lane took a day to make
trustworthy and one flaky third-party call should not be able to take it down.

**The prompt carries the aims, because a model without them gives generic YouTube
advice** - post more, use better thumbnails, hook in three seconds. What makes an
answer useful here is knowing that watch hours are the constraint rather than
views, that the channel's identity is evidence rather than spectacle, and that on
a channel this young most numbers are noise. Those are stated, and the model is
told plainly when to say "not enough signal" instead of manufacturing a finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

import author  # noqa: E402  - reuse its key handling and HTTP client

MODEL = "anthropic/claude-sonnet-4.5"
MAX_ADVICE_CHARS = 4000

AIMS = """\
You are advising on a YouTube channel called How We Know (@howweknowdeep).

WHAT IT IS
Evidence-first explainers. Each video answers one question and shows the
instrument, the proxy, or the observation behind every figure - and says plainly
where the evidence stops. Currently deep-sea topics. The channel is a METHOD, not
a subject: deep sea is the beachhead, not the ceiling.

WHAT WE ARE OPTIMISING
YouTube Partner Programme: 1,000 subscribers and 4,000 watch HOURS in a rolling
12 months. Watch hours, not views. A longer video that holds attention is worth
more than a short one that does not. Views matter only as a route to hours.

HOW TOPICS ARE CHOSEN
Automatically, by measured demand divided by competition, both hard gates. The
strongest signal is "title gap" - the share of the top 20 search results whose
titles do not actually answer the query. A high gap means nobody has made the
definitive video. Saturated topics are killed outright, not ranked low.

CONSTRAINTS THAT ARE NOT UP FOR DEBATE
- Public-domain imagery only; the channel is monetised.
- No invented figures. Every number on screen is stated in the narration and
  traced to a named public source.
- No medical, financial or legal advice; nothing adult; nothing morally grey.
- Publishing is autonomous, twice a week, spaced. Nothing waits on a human.

WHAT ONLY A HUMAN DECIDES
Abandoning deep sea, changing cadence, and anything that publishes or unpublishes.
You may recommend these; they will not be applied automatically.

HOW TO ANSWER
Be specific and short. Name the number you are reasoning from. If the data is too
thin to support a conclusion - which it will be for the first several months -
say so plainly and stop. A confident recommendation from three data points is
worse than silence, because it will be acted on. Do not give generic YouTube
advice; assume the obvious has been considered.
"""


def build_prompt(report: dict, cfg: dict, videos: list[dict]) -> list[dict]:
    facts = {
        "month": report.get("month"),
        "videos_measured": report.get("videos_measured"),
        "total_views": report.get("views"),
        "avg_view_percentage": report.get("avg_view_percentage"),
        "avg_view_duration_s": report.get("avg_view_duration_s"),
        "current_runtime_minutes": cfg["retention"].get("runtime_minutes"),
        "retention_floor_pct": cfg["retention"].get("floor_pct"),
        "videos_per_week": cfg["cadence"].get("videos_per_week"),
        "automatic_findings": report.get("findings"),
        "automatic_changes_applied": report.get("changes"),
        "per_video": videos,
    }
    return [
        {"role": "system", "content": AIMS},
        {"role": "user", "content":
            "Here is this month's measurement and what the automatic rules did "
            "with it.\n\n```json\n" + json.dumps(facts, indent=2) + "\n```\n\n"
            "Your recommendation will be APPLIED automatically, so be "
            "conservative and say so when the data does not support acting.\n\n"
            "Reply with a JSON object and nothing else:\n"
            "{\n"
            '  "conclusion": "<what this data supports, <=80 words>",\n'
            '  "automatic_decision_right": true|false,\n'
            '  "change": {"key": "retention.runtime_minutes", "to": <number>} '
            "or null,\n"
            '  "reasoning": "<why, naming the numbers, <=80 words>",\n'
            '  "for_the_owner": "<anything outside the fence that only a human '
            'should decide, or empty>"\n'
            "}\n\n"
            "`change` is the ONLY key you may set, and it will be clamped to "
            "4.0-12.0 minutes and refused if anything was changed last month. "
            "Use null when the data is too thin or no change is warranted - null "
            "is the correct answer more often than not on a young channel.\n"},
    ]


def advise(report: dict, cfg: dict, videos: list[dict]) -> dict:
    """Return {'ok': bool, 'text': str, 'cost': float|None, 'why': str}.

    Never raises. Every failure path returns a reason that is printed in the
    report, so a missing advisory is visible rather than silently absent.
    """
    key = author.api_key()
    if not key:
        return {"ok": False, "text": "", "cost": None,
                "why": "no OpenRouter key in .secrets/openrouter_key.txt or "
                       "$OPENROUTER_API_KEY - advisory skipped, review unaffected"}
    try:
        out = author.call_openrouter(build_prompt(report, cfg, videos),
                                     MODEL, key, timeout=120)
        text = (out["choices"][0]["message"]["content"] or "").strip()
        if not text:
            return {"ok": False, "text": "", "cost": None,
                    "why": "the model returned an empty response"}
        usage = out.get("usage") or {}
        parsed, parse_note = _parse(text)
        return {"ok": True, "text": text[:MAX_ADVICE_CHARS],
                "proposal": parsed, "parse_note": parse_note,
                "cost": usage.get("cost"), "why": ""}
    except Exception as e:                      # noqa: BLE001 - never take the lane down
        return {"ok": False, "text": "", "cost": None,
                "why": f"{type(e).__name__}: {str(e)[:160]}"}


def _parse(text: str) -> tuple[dict | None, str]:
    """Pull the JSON object out of the reply.

    Models fence JSON in markdown often enough that refusing to handle it would
    make the lane fail on formatting rather than on substance. But a reply that
    cannot be parsed applies NOTHING - it is reported as prose and the
    deterministic rules stand. Silently guessing at a malformed recommendation is
    exactly how an automatic actor does something nobody intended.
    """
    import re
    blob = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", blob, re.S)
    if m:
        blob = m.group(1)
    else:
        i, j = blob.find("{"), blob.rfind("}")
        if i == -1 or j <= i:
            return None, "no JSON object in the reply; nothing applied"
        blob = blob[i:j + 1]
    try:
        d = json.loads(blob)
    except json.JSONDecodeError as e:
        return None, f"reply was not valid JSON ({e.msg}); nothing applied"
    if not isinstance(d, dict):
        return None, "reply parsed but was not an object; nothing applied"
    ch = d.get("change")
    if ch is not None:
        if not isinstance(ch, dict) or "key" not in ch or "to" not in ch:
            return d, "change field malformed; nothing applied"
        try:
            float(ch["to"])
        except (TypeError, ValueError):
            return d, f"change.to is not a number ({ch['to']!r}); nothing applied"
    return d, ""
