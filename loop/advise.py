"""Ask a language model to read the month and say what it sees.

**Why this exists at all.** The monthly review's automatic decision is a handful
of thresholds. Thresholds can only find what was anticipated when they were
written. On the 1st of the month nothing intelligent is present - the loop runs
alone - so the honest comparison is not "a model versus me", it is "a model
versus a few if-statements". The owner made that argument on 2026-08-31 and she
was right.

**The split that keeps it safe.** This ADVISES. `monthly.py` DECIDES.

A model that can edit `loop/config.json` unattended is an unbounded actor with no
cooldown and no floor; a model that writes a paragraph a human reads is pure
upside. So nothing here touches configuration, and nothing downstream reads this
output as an instruction. It is appended to the emailed report, labelled, and
that is all.

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
            "Answer in at most 200 words:\n"
            "1. What, if anything, does this data actually support concluding?\n"
            "2. Is the automatic decision right? Say so if it is - agreement is "
            "a useful answer.\n"
            "3. One thing worth trying next, or 'nothing yet' if the data does "
            "not support one.\n"},
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
        return {"ok": True, "text": text[:MAX_ADVICE_CHARS],
                "cost": usage.get("cost"), "why": ""}
    except Exception as e:                      # noqa: BLE001 - never take the lane down
        return {"ok": False, "text": "", "cost": None,
                "why": f"{type(e).__name__}: {str(e)[:160]}"}
