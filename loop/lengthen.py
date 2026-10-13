"""The ten-minute extension, as a SPLICE: new hook + the untouched body + a real tail.

    .venv/bin/python loop/lengthen.py plan   --slugs a b        # budget only, no model
    .venv/bin/python loop/lengthen.py script --slugs a b [--dry-run]
    .venv/bin/python loop/lengthen.py splice [--slugs a b] [--dry-run]
    .venv/bin/python loop/lengthen.py status
    .venv/bin/python loop/lengthen.py bind                      # the Mac, in the batch
    .venv/bin/python loop/queue_reopen.py [--limit N] [--dry-run]  # the cloud lane

Owner decisions, 12-13 Oct 2026 (repackage job 1 of 3). Every long-form
QUEUED episode under 10:00 of narration (scripts/ and loop/drafts/, not yet
uploaded) is brought to
10:30-11:30 (TARGET_MIN..TARGET_MAX minutes; at the measured 144.58 wpm that is
>= 1,520 narrated words, loop/durations.py). Her question: "do u have to
re-render the entire videos, can't u just add something on the end". The
answer is this splice:

    (a) a NEW OPENING, freshly narrated and rendered under the stake-then-payoff
        hook rule (loop/opening.py), replacing the old `### Cold open`;
    (b) the EXISTING renders/<slug>-final.mp4 from the `### Title card` beat
        onward, UNTOUCHED - cut with `-c copy` at a keyframe (every beat is its
        own libx264 encode, concatenated by visuals/assemble.py, so each beat
        starts on one) and verified packet-for-packet with ffmpeg framemd5;
    (c) a NEW TAIL of real, sourced "how we know" evidence - what the evidence
        does not settle, a surprising leftover fact, the open question - and a
        pointer to the next episode, which is where the episode ends (the
        pipeline has no separate end-card beat; the tail's last line is it).

THE BOUNDARY comes from the measured timeline, not from a guess:
audio/<slug>/beats.json holds each beat's measured wav seconds (the same
durations assemble.py allocated frames from), plans/<slug>.json holds each
beat's `heading`. The title-card beat is the first whose heading is "Title
card"; its first frame is round(sum(seconds before it) * FPS) - exactly the
frame assemble.py's whole-episode allocation emitted there. The sidecar
renders/<slug>-final.mp4.render.json must agree (same beat count, audio_s
within SIDECAR_TOLERANCE_S of the summed beats) or the splice is refused and
the episode falls back to a FULL re-render (the nightly batch's normal path).

THE TAIL IS WRITTEN WITH WARMTH (owner instruction, 13 Oct 2026). A house rule
in TAIL_RULES, not a suggestion: real evidence, sourced like everything else,
written like the last three minutes of a good science YouTuber who likes their
audience. Examples of the register the prompt asks for (shape only):

  * "Here is the part nobody puts on the poster: we have measured the pressure
    down there to three significant figures, and we still cannot keep a
    snailfish alive long enough to ask it how it feels about that."
  * "So the honest answer is 'mostly'. Science is very comfortable with
    'mostly'. Science would like a word with anyone who is not."
  * "Next time: the fish that makes its own light, and why it might be the
    worst-kept secret in the ocean. Stay curious - it's cheaper than a
    submarine."

The humour is a prompt rule. What is CHECKED, mechanically (tail_problems):
the tail is not bare restatement - under TAIL_OVERLAP_MAX (30%) of its content
words come from the Direct-answer lock, and no single tail sentence is mostly
lock words; it ends with a next-episode pointer; it lands inside the word
budget; and the merged script still passes every gate the original did: the
hook (opening.problems, stake-then-payoff), the title truth guard
(longform_title), directive truth and parse (author), the exclusion gate, and
every new source URL fetched for real (author.dead_urls).

STATE, in loop/state/lengthen.json, per slug:
    scripted        new script written, plan re-derived, old body wavs moved
                    to their new indices; the nightly narrator voices only the
                    new opening and tail beats
    full_rerender   the splice was impossible (no usable sidecar / body beats
                    differ); the old render was moved aside and the batch
                    re-renders the whole episode
    spliced         the stitched render passed the 10-minute floor; the old
                    cut is recorded in loop/state/superseded_renders.json, the
                    slug is cleared from loop/state/render_hold.json and the
                    render ships through the normal upload lane

FORWARD ONLY (owner decision, 13 Oct 2026, later the same day). A PUBLISHED
episode is never re-rendered, re-uploaded, extended or privated: stage_script
refuses any slug in loop/state/ledger.json (`published_refused`), and nothing
in this repo uploads a second cut of a live video.

Model route: loop/llm_router.py via author.call_openrouter - her Claude
subscription when the lane carries it, the Gemini free tier, the $0 OpenRouter
list; never a paid model. Guarded by validator V49 and
loop/tests/test_lengthen.py (no live model call, no ffmpeg in the tests).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

SCRIPTS = ROOT / "scripts"
DRAFTS = LOOP / "drafts"
PLANS = ROOT / "plans"
AUDIO = ROOT / "audio"
RENDERS = ROOT / "renders"
CAPTIONS = ROOT / "captions"
STATE = LOOP / "state" / "lengthen.json"
SUPERSEDED = LOOP / "state" / "superseded_renders.json"
HOLD = LOOP / "state" / "render_hold.json"

FPS = 30                       # visuals/design.py FPS; pinned by the test
FLOOR_MIN = 10.0
TARGET_MIN = 10.5
TARGET_MID = 11.0
TARGET_MAX = 11.5
MIN_WORDS = 1520               # >= narration_words_for(TARGET_MIN) at 144.58 wpm
SIDECAR_TOLERANCE_S = 0.15
TAIL_OVERLAP_MAX = 0.30
SENTENCE_OVERLAP_MAX = 0.70
BUDGET_SLACK = 0.25            # tail words may land within +-25% of the budget
TITLE_CARD = "title card"
COLD_OPEN = "cold open"

NEXT_POINTER = re.compile(
    r"\b(next (?:episode|time|video|week|up)|in the next (?:episode|video)|"
    r"coming up next|see you next|join us next|on the next episode)\b", re.I)


HOOK_VARIANT = "stake-then-payoff"   # loop/opening.py, first and active


def hook_problems(text: str) -> list[str]:
    """Why this script's opening breaks the hook rule; [] when it holds."""
    import opening                                         # noqa: PLC0415
    return opening.problems(text, HOOK_VARIANT)


def needs_reopen(text: str) -> bool:
    """The hook rule (owner, 13 Oct 2026): every QUEUED long-form script
    opens stake-then-payoff. One that does not is re-opened: a new cold open
    only, the rest of the script untouched."""
    return bool(hook_problems(text))


class SpliceUnusable(Exception):
    """The measured timeline cannot locate the body; fall back to full."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wpm() -> float:
    import durations                                       # noqa: PLC0415
    return durations.wpm()


# ------------------------------------------------------------- arithmetic
def words_now(text: str) -> int:
    import durations                                       # noqa: PLC0415
    return durations.narration_words_of(text)


def minutes_of_words(words: int, wpm: float | None = None) -> float:
    return words / (wpm or _wpm())


def needs_lengthening(text: str, measured_s: float | None = None,
                      wpm: float | None = None) -> bool:
    """Under 10:00 of narration - by the render when measured, else by words."""
    if measured_s:
        return measured_s / 60.0 < FLOOR_MIN
    return minutes_of_words(words_now(text), wpm) < FLOOR_MIN


def budget(body_s: float, open_words: int, wpm: float | None = None) -> dict:
    """How many tail words put the stitched episode at TARGET_MID.

    body_s       measured seconds of the kept body (title card -> end)
    open_words   narrated words of the new opening
    Returns {tail_words, open_s, tail_s, total_min, in_band}; total words
    across opening + body + tail are never under MIN_WORDS."""
    w = wpm or _wpm()
    open_s = open_words / w * 60.0
    tail_s = max(0.0, TARGET_MID * 60.0 - body_s - open_s)
    tail_words = int(math.ceil(tail_s * w / 60.0))
    body_words = int(round(body_s * w / 60.0))
    short = MIN_WORDS - (open_words + body_words + tail_words)
    if short > 0:
        tail_words += short
        tail_s = tail_words / w * 60.0
    total_min = (body_s + open_s + tail_s) / 60.0
    return {"tail_words": tail_words, "open_s": round(open_s, 2),
            "tail_s": round(tail_s, 2), "total_min": round(total_min, 3),
            "in_band": TARGET_MIN <= total_min <= TARGET_MAX}


def frames_through(seconds: list[float], k: int, fps: int = FPS) -> int:
    """Frames visuals/assemble.py has emitted BEFORE beat k (its allocation:
    each beat ends at round(cumulative * fps), the last beat at ceil)."""
    if k <= 0:
        return 0
    if k >= len(seconds):
        return int(math.ceil(sum(seconds) * fps - 1e-9))
    return int(round(sum(seconds[:k]) * fps))


def boundary(plan: list[dict], beats: list[dict], sidecar: dict | None,
             fps: int = FPS) -> dict:
    """Where the kept body starts in the old render. Raises SpliceUnusable."""
    if not sidecar:
        raise SpliceUnusable("no renders/<slug>-final.mp4.render.json sidecar")
    if sidecar.get("timing") != "audio":
        raise SpliceUnusable(f"render timed by {sidecar.get('timing')!r}, "
                             f"not measured audio")
    if not beats or len(beats) != len(plan):
        raise SpliceUnusable(f"beats.json has {len(beats or [])} beats, the "
                             f"plan {len(plan)}")
    if int(sidecar.get("beats") or -1) != len(plan):
        raise SpliceUnusable(f"sidecar says {sidecar.get('beats')} beats, the "
                             f"plan {len(plan)}")
    secs = [float(b.get("seconds") or 0) for b in beats]
    if any(s <= 0 for s in secs):
        raise SpliceUnusable("a beat has no measured seconds")
    for i, (b, p) in enumerate(zip(beats, plan)):
        if (b.get("narration") or "").strip() != (p.get("narration") or "").strip():
            raise SpliceUnusable(f"beat {i}: beats.json narration differs from "
                                 f"the plan - the render is not this plan")
    total = sum(secs)
    audio_s = float(sidecar.get("audio_s") or sidecar.get("duration_s") or 0)
    if abs(audio_s - total) > SIDECAR_TOLERANCE_S:
        raise SpliceUnusable(f"sidecar audio {audio_s:.2f}s vs summed beats "
                             f"{total:.2f}s")
    k = next((i for i, p in enumerate(plan)
              if (p.get("heading") or "").strip().lower() == TITLE_CARD), None)
    if k is None or k == 0:
        raise SpliceUnusable("no '### Title card' beat after a cold open")
    bf = frames_through(secs, k, fps)
    tf = frames_through(secs, len(secs), fps)
    return {"k": k, "boundary_frames": bf, "total_frames": tf,
            "boundary_s": bf / fps, "body_frames": tf - bf,
            "body_s": (tf - bf) / fps, "open_s_old": sum(secs[:k]),
            "beats": len(plan)}


# ---------------------------------------------------------- script surgery
def _narration_span(text: str) -> tuple[int, int]:
    a = text.find("## Narration")
    if a < 0:
        raise ValueError("no '## Narration' section")
    b = text.find("\n## ", a + 1)
    return a, (b if b > 0 else len(text))


def cold_open(text: str) -> str:
    m = re.search(r"### Cold open\s*\n(.*?)(?=\n### |\n## |\Z)", text, re.S | re.I)
    return m.group(1).strip() if m else ""


def splice_script(text: str, new_open: str, tail_md: str,
                  sources: list[str] | None = None) -> str:
    """Replace the cold open's body, append the tail at the end of the
    narration (none for a hook-only re-open), add any new sources, and stamp
    the opening variant. Nothing else in the script moves."""
    import opening                                         # noqa: PLC0415
    m = re.search(r"(### Cold open\s*\n)(.*?)(?=\n### |\n## |\Z)", text, re.S | re.I)
    if not m:
        raise ValueError("no '### Cold open' section")
    out = text[: m.start(2)] + new_open.strip() + "\n" + text[m.end(2):]
    tail = (tail_md or "").strip()
    if tail:
        a, b = _narration_span(out)
        if not tail.startswith("### "):
            tail = "### " + tail.lstrip("# ").lstrip()
        out = out[:b].rstrip() + "\n\n" + tail + "\n" + out[b:]
    out = opening.mark(out, HOOK_VARIANT)
    if sources and "## Sources" in out:
        head, rest = out.split("## Sources", 1)
        nl = rest.find("\n")
        have = set(re.findall(r"https?://[^\s)>\]]+", rest))
        add = [u for u in sources if u not in have]
        if add:
            out = (head + "## Sources" + rest[:nl] + "\n"
                   + "\n".join(f"- {u}" for u in add) + rest[nl:])
    label = "Lengthened" if tail else "Reopened"
    stamp = (f"**{label}:** {_now()[:10]} (loop/lengthen.py "
             f"{'splice' if tail else 'reopen, hook rule'})")
    if re.search(rf"^\*\*{label}:\*\*.*$", out, re.M):
        out = re.sub(rf"^\*\*{label}:\*\*.*$", stamp, out, count=1, flags=re.M)
    else:
        mm = re.search(r"^\*\*Domain:\*\*.*$", out, re.M)
        if mm:
            out = out[: mm.end()] + "\n" + stamp + out[mm.end():]
    return out


def tail_sections(text: str, tail_md: str) -> list[str]:
    return re.findall(r"^### (.+)$", tail_md, re.M)


# --------------------------------------------------------------- the gates
def _content(s: str) -> list[str]:
    import opening                                         # noqa: PLC0415
    return opening._content(s)                             # noqa: SLF001


def tail_problems(tail_md: str, script: str, want_words: int | None = None) -> list[str]:
    """Mechanical checks on the tail. The humour is a prompt rule."""
    import opening                                         # noqa: PLC0415
    p: list[str] = []
    body = re.sub(r"\{\{.*?\}\}", " ", tail_md, flags=re.S)
    lines = [ln for ln in body.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    spoken = " ".join(lines).strip()
    if not spoken:
        return ["the tail has no narration"]
    lock = set(_content(opening.answer_sentence(script) + " " +
                        _lock_paragraph(script)))
    tw = set(_content(spoken))
    if tw and lock:
        share = len(tw & lock) / len(tw)
        if share >= TAIL_OVERLAP_MAX:
            p.append(f"the tail restates the Direct-answer lock: {share:.0%} of "
                     f"its content words come from it (max "
                     f"{TAIL_OVERLAP_MAX:.0%}) - add what the evidence does "
                     f"NOT settle, a leftover fact, the open question")
    for s in re.split(r"(?<=[.!?])\s+", spoken):
        sc = set(_content(s))
        if len(sc) >= 4 and lock and len(sc & lock) / len(sc) >= SENTENCE_OVERLAP_MAX:
            p.append(f"tail sentence is a restatement of the answer: {s[:100]!r}")
            break
    last = re.split(r"(?<=[.!?])\s+", spoken)[-2:]
    if not NEXT_POINTER.search(" ".join(last)):
        p.append("the tail does not end with a pointer to the next episode "
                 "('next time: ...', 'in the next episode ...')")
    if want_words:
        n = len(spoken.split())
        lo, hi = want_words * (1 - BUDGET_SLACK), want_words * (1 + BUDGET_SLACK)
        if not lo <= n <= hi:
            p.append(f"the tail is {n} narrated words; the budget is "
                     f"{want_words} (+-{BUDGET_SLACK:.0%})")
    return p


def _lock_paragraph(script: str) -> str:
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)(?:\n## |\Z)", script, re.S)
    return " ".join(m.group(1).split()) if m else ""


def merged_problems(merged: str, slug: str, check_urls: bool = True) -> list[str]:
    """Every gate the original draft passed, on the merged script."""
    import author                                          # noqa: PLC0415
    import exclusions                                      # noqa: PLC0415
    import longform_title                                  # noqa: PLC0415
    import opening                                         # noqa: PLC0415
    p = list(opening.problems(merged, "stake-then-payoff"))
    p += author.directive_truth_problems(merged)
    p += author.directive_parse_problems(merged)
    d = exclusions.decide_body(merged)
    if not d.admitted:
        p.append(f"merged text touches a hard exclusion: {d.rule}")
    t, why, _ = longform_title.title_for_upload(slug, merged)
    if t is None and longform_title.script_title(merged):
        p += [f"title no longer traceable: {w}" for w in why[:2]]
    if check_urls:
        p += author.dead_urls(merged)
    return p


# ------------------------------------------------------------ the drafting
TAIL_RULES = """HOUSE RULES FOR THE TAIL (all of them, every time):
- REAL CONTENT, never filler. Cover what the evidence does NOT settle, one
  surprising leftover fact the episode has not used, and the open question
  scientists are still chasing. Every figure is spoken in the narration and
  traceable to a named public source you list under SOURCES:.
- WARMTH AND WIT. Write it like the last three minutes of a good science
  YouTuber who likes their audience: a light touch, a well-placed joke or two,
  a gentle laugh at how little we know, a human sign-off that makes someone
  glad they stayed. Never dry, never a lecture, never a list.
- END with a tease of the next episode ("Next time: ...") and a short warm
  sign-off. That line is the end card.
- Do not restate the answer the episode already gave. Do not write a second
  conclusion. Second person sparingly, no hype words, no rhetorical-question
  pile-ups."""

PROMPT = """You are extending a finished evidence-first science episode so it \
runs {target} minutes. The middle of the episode is ALREADY RENDERED and will \
not change. You write two new pieces.

1. OPENING: a replacement for the cold open, about {open_words} words. \
{hook_rule}

2. TAIL: new narration that plays AFTER the existing ending, about \
{tail_words} words, as '### ' sections (two or three, each heading a claim).
{tail_rules}

{next_line}

Output EXACTLY this shape and nothing else:
OPENING:
<the new cold open paragraph(s)>
TAIL:
### <heading>
<paragraphs>
SOURCES:
- <one working URL per line, on the named body's own domain>

QUESTION: {question}

EXISTING SCRIPT:
{script}
"""


PROMPT_REOPEN = """You are re-opening a finished evidence-first science \
episode. Everything after the cold open is ALREADY WRITTEN (and may already be \
narrated and rendered) and will not change. You write ONE new piece.

OPENING: a replacement for the cold open, about {open_words} words. \
{hook_rule}

Every figure you speak must already be in the script below or come from a \
named public source you list under SOURCES:. Do not restate the title or the \
question as the first sentence. Second person sparingly, no hype words.

Output EXACTLY this shape and nothing else:
OPENING:
<the new cold open paragraph(s)>
SOURCES:
- <one working URL per line for any NEW source; leave empty if none>

QUESTION: {question}

EXISTING SCRIPT:
{script}
"""


def _ask(messages: list[dict]) -> tuple[str, str, str | None]:
    """One call on the $0 route: (text, model_used, finish_reason).
    Tests replace this; nothing here may reach a paid model."""
    import author                                          # noqa: PLC0415
    resp = author.call_openrouter(messages, author.configured_model(),
                                  author.api_key() or "")
    choice = (resp.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", text)
    return text, resp.get("model_used") or "", (
        choice.get("finish_reason") or choice.get("native_finish_reason"))


def parse_open_reply(text: str) -> tuple[str, list[str]]:
    m = re.search(r"OPENING:\s*\n(.*?)(?:\n\s*SOURCES:\s*\n?(.*))?\Z",
                  text.strip() + "\n", re.S)
    if not m or not m.group(1).strip() or re.search(r"^\s*TAIL:", m.group(1), re.M):
        raise ValueError("reply is not OPENING:/SOURCES: shaped")
    return m.group(1).strip(), re.findall(r"https?://[^\s)>\]]+", m.group(2) or "")


def parse_reply(text: str) -> tuple[str, str, list[str]]:
    m = re.search(r"OPENING:\s*\n(.*?)\n\s*TAIL:\s*\n(.*?)(?:\n\s*SOURCES:\s*\n(.*))?\Z",
                  text.strip() + "\n", re.S)
    if not m:
        raise ValueError("reply is not OPENING:/TAIL:/SOURCES: shaped")
    urls = re.findall(r"https?://[^\s)>\]]+", m.group(3) or "")
    return m.group(1).strip(), m.group(2).strip(), urls


def next_episode_hint(slug: str) -> str:
    """A real next episode to tease: the next queued script in this domain."""
    try:
        import batch_queue                                 # noqa: PLC0415
        import domains                                     # noqa: PLC0415
        dom = domains.domain_of_slug(slug)
        for q in batch_queue.queued_entries():
            if q.get("slug") != slug and q.get("query") and \
                    domains.domain_of_slug(q["slug"]) == dom:
                return (f"Tease THIS next episode by its subject: "
                        f"{q['query']!r}.")
    except Exception:                                      # noqa: BLE001
        pass
    return "Tease the next episode with a one-line hint of a related question."


def draft(slug: str, text: str, body_s: float, check_urls: bool = True,
          tail: bool = True) -> dict:
    """Draft opening + tail (tail=False: the opening alone - a hook-only
    re-open of a script already at the floor), gate the merge, retry with the
    problems fed back. Returns {applied, merged, problems, budget, model}."""
    import author                                          # noqa: PLC0415
    import opening                                         # noqa: PLC0415
    open_words = max(30, min(90, len(cold_open(text).split())))
    b = budget(body_s, open_words) if tail else {"tail_words": 0}
    q = opening.title_question(text)
    hook_rule = opening.prompt_text(HOOK_VARIANT)
    if tail:
        content = PROMPT.format(
            target=f"{TARGET_MIN}-{TARGET_MAX}", open_words=open_words,
            tail_words=b["tail_words"], hook_rule=hook_rule,
            tail_rules=TAIL_RULES, next_line=next_episode_hint(slug),
            question=q, script=text)
    else:
        content = PROMPT_REOPEN.format(open_words=open_words,
                                       hook_rule=hook_rule, question=q,
                                       script=text)
    messages = [{"role": "user", "content": content}]
    problems: list[str] = ["no attempt made"]
    merged, model = "", ""
    for attempt in range(1, author.MAX_ATTEMPTS + 1):
        reply, model, finish = _ask(messages)
        problems = []
        if finish and finish not in ("stop", "end_turn"):
            problems.append(f"output was cut off (finish_reason={finish!r})")
        try:
            if tail:
                new_open, tail_md, urls = parse_reply(reply)
                problems += tail_problems(tail_md, text, b["tail_words"])
            else:
                (new_open, urls), tail_md = parse_open_reply(reply), ""
            merged = splice_script(text, new_open, tail_md, urls)
            problems += merged_problems(merged, slug, check_urls)
            if not tail and needs_lengthening(merged) and \
                    not needs_lengthening(text):
                problems.append("the new opening took the script under the "
                                f"{FLOOR_MIN}-minute floor; keep it about "
                                f"{open_words} words")
        except ValueError as e:
            problems.append(str(e))
        if not problems:
            return {"applied": True, "merged": merged, "problems": [],
                    "budget": b, "model": model, "attempts": attempt,
                    "open_words": open_words}
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "Rejected by the automated checks:\n"
             + "\n".join(f"- {x}" for x in problems[:8])
             + ("\n\nRewrite both pieces so none of those is true. Same rules, "
                "same shape, same lengths. Do not drop a sourced claim to dodge "
                "a check." if tail else
                "\n\nRewrite the opening so none of those is true. Same rules, "
                "same shape, same length.")}]
    return {"applied": False, "merged": merged, "problems": problems[:8],
            "budget": b, "model": model, "attempts": author.MAX_ATTEMPTS}


# --------------------------------------------------------------- the state
def load(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or STATE).read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("episodes", {})
    return d


def save(doc: dict, path: Path | None = None) -> None:
    doc["updated"] = _now()
    p = path or STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_superseded(slug: str, old: Path, why: str,
                      path: Path | None = None) -> dict:
    p = path or SUPERSEDED
    sup = _read_json(p, {})
    prev = sup.get(slug)
    rec = {"sha256": sha256(old), "bytes": old.stat().st_size,
           "superseded_at": _now(), "why": why}
    if prev:
        rec["previous"] = ([prev] + list(prev.pop("previous", []) or []))[:5]
    sup[slug] = rec
    p.write_text(json.dumps(sup, indent=2) + "\n")
    return rec


def clear_hold(slug: str, path: Path | None = None) -> bool:
    p = path or HOLD
    h = _read_json(p, {"held": {}})
    if slug not in (h.get("held") or {}):
        return False
    h["held"].pop(slug)
    h["at"] = _now()
    p.write_text(json.dumps(h, indent=2) + "\n")
    return True



# ---------------------------------------------------------- stage: script
def remap_audio(slug: str, old_k: int, new_k: int, body_n: int,
                audio_root: Path | None = None) -> dict:
    """Move the kept body's wavs to their new plan indices; every other old
    wav (the old opening) goes to audio/<slug>/superseded/. Nothing deleted."""
    adir = (audio_root or AUDIO) / slug
    moved, retired = 0, []
    if not adir.is_dir():
        return {"moved": 0, "retired": []}
    stage = adir / ".remap"
    stage.mkdir(exist_ok=True)
    for wav in sorted(adir.glob("[0-9]*.wav")):
        wav.replace(stage / wav.name)
    keep = adir / "superseded"
    for wav in sorted(stage.glob("[0-9]*.wav")):
        i = int(wav.stem)
        if old_k <= i < old_k + body_n:
            wav.replace(adir / f"{new_k + (i - old_k):04d}.wav")
            moved += 1
        else:
            keep.mkdir(exist_ok=True)
            wav.replace(keep / f"pre-lengthen-{wav.name}")
            retired.append(wav.name)
    stage.rmdir()
    return {"moved": moved, "retired": retired}


def _plan_for(script_path: Path) -> list[dict]:
    sys.path.insert(0, str(ROOT / "visuals"))
    import planner                                         # noqa: PLC0415
    return planner.plan(str(script_path))


def _measured_s(slug: str) -> float | None:
    import durations                                       # noqa: PLC0415
    return durations.duration_s(slug)


def published_slugs() -> set[str]:
    import ledger                                          # noqa: PLC0415
    return {r["slug"] for r in ledger.load().get("published") or []
            if r.get("slug") and r.get("video_id")}


def script_path(slug: str) -> Path:
    """scripts/<slug>.md, else the not-yet-promoted loop/drafts/<slug>.md."""
    sp = SCRIPTS / f"{slug}.md"
    return sp if sp.exists() else DRAFTS / f"{slug}.md"


def _twins(slug: str) -> list[Path]:
    """Every copy of a queued script: scripts/<slug>.md and a carried-over
    loop/drafts/<slug>.md. draft.promote_to_scripts never overwrites
    scripts/, so a drafts twin is inert - but it is kept identical so no
    reader of loop/drafts/ sees the old opening."""
    return [p for p in (SCRIPTS / f"{slug}.md", DRAFTS / f"{slug}.md")
            if p.exists()]


def _kind(text: str, measured: float | None) -> str | None:
    if needs_lengthening(text, measured):
        return "extend"
    if needs_reopen(text):
        return "reopen"
    return None


def script_cloud(slug: str, dry_run: bool = False, doc: dict | None = None,
                 check_urls: bool = True) -> dict:
    """THE CLOUD HALF (loop-repackage, subscription route first): draft and
    gate the new opening (+ tail), write scripts/<slug>.md and its drafts
    twin, record `pending_bind` in loop/state/lengthen.json. Writes NOTHING
    else - plans/, audio/ and renders/ are the Mac's, and bind() there makes
    them agree. Kept free of every Mac-side write so the queue-reopen
    stage's write set is exactly what bin/loop-stage.sh commits."""
    if slug in published_slugs():
        return {"slug": slug, "status": "published_refused",
                "why": "published videos are never extended or re-uploaded "
                       "(owner decision, 13 Oct 2026: forward only)"}
    sp = script_path(slug)
    text = sp.read_text(encoding="utf-8")
    measured = _measured_s(slug)
    kind = _kind(text, measured)
    if kind is None:
        return {"slug": slug, "status": "not_short",
                "why": f"at the floor and the opening passes {HOOK_VARIANT}"}
    est_body_s = (measured or minutes_of_words(words_now(text)) * 60) \
        - minutes_of_words(len(cold_open(text).split())) * 60
    if dry_run:
        return {"slug": slug, "status": "dry_run", "kind": kind,
                "mode": "pending_bind"}
    r = draft(slug, text, est_body_s, check_urls=check_urls,
              tail=kind == "extend")
    if not r["applied"]:
        return {"slug": slug, "status": "rejected", "kind": kind,
                "problems": r["problems"], "mode": "pending_bind"}
    merged = r["merged"]
    rec = {"status": "scripted", "mode": "pending_bind", "kind": kind,
           "why_full": None, "words_before": words_now(text),
           "words_after": words_now(merged),
           "minutes_before": round(minutes_of_words(words_now(text)), 2),
           "minutes_after": round(minutes_of_words(words_now(merged)), 2),
           "hook_before": cold_open(text)[:240],
           "hook_after": cold_open(merged)[:240],
           "hook_problems_before": hook_problems(text)[:3],
           "budget": r["budget"], "model": r["model"],
           "attempts": r.get("attempts"), "scripted_at": _now(),
           "old_script_sha256": hashlib.sha256(text.encode()).hexdigest(),
           "new_script_sha256": hashlib.sha256(merged.encode()).hexdigest(),
           "old_render_sha256": None}
    # Both copies: draft.promote_to_scripts never overwrites scripts/, so a
    # carried-over loop/drafts/ twin is inert - kept identical anyway so no
    # reader of loop/drafts/ sees the old opening.
    if (SCRIPTS / f"{slug}.md").exists():
        (SCRIPTS / f"{slug}.md").write_text(merged, encoding="utf-8")
    if (DRAFTS / f"{slug}.md").exists():
        (DRAFTS / f"{slug}.md").write_text(merged, encoding="utf-8")
    d = doc if doc is not None else load()
    d["episodes"][slug] = rec
    if doc is None:
        save(d)
    return {"slug": slug, **rec}


def stage_script(slug: str, dry_run: bool = False, doc: dict | None = None,
                 check_urls: bool = True, cloud: bool = False) -> dict:
    """Bring one QUEUED script to the rules: under the floor -> new hook +
    tail ("extend"); at the floor but failing the hook rule -> new hook only
    ("reopen"). cloud=True (the CI lane, which holds the subscription route
    but none of the Mac's audio, plans or renders) writes the script and
    records `pending_bind`; the Mac's batch binds it (bind()) before it
    plans or narrates anything."""
    if slug in published_slugs():
        return {"slug": slug, "status": "published_refused",
                "why": "published videos are never extended or re-uploaded "
                       "(owner decision, 13 Oct 2026: forward only)"}
    sp = script_path(slug)
    text = sp.read_text(encoding="utf-8")
    measured = _measured_s(slug)
    kind = _kind(text, measured)
    if kind is None:
        return {"slug": slug, "status": "not_short",
                "why": f"{(measured or 0) / 60 or minutes_of_words(words_now(text)):.2f} "
                       f"min and the opening passes {HOOK_VARIANT}"}
    est_body_s = (measured or minutes_of_words(words_now(text)) * 60) \
        - minutes_of_words(len(cold_open(text).split())) * 60
    if cloud:
        return script_cloud(slug, dry_run, doc, check_urls)
    plan_p = PLANS / f"{slug}.json"
    old_plan = (_read_json(plan_p, None) if plan_p.exists() else None) \
        or _plan_for(sp)
    mode, why, bd = _decide_mode(slug, old_plan)
    body_s = bd["body_s"] if bd else est_body_s
    if dry_run:
        b = budget(body_s, max(30, min(90, len(cold_open(text).split()))))
        return {"slug": slug, "status": "dry_run", "mode": mode, "why": why,
                "kind": kind, "budget": b}
    r = draft(slug, text, body_s, check_urls=check_urls, tail=kind == "extend")
    if not r["applied"]:
        return {"slug": slug, "status": "rejected", "problems": r["problems"],
                "mode": mode, "kind": kind}
    merged = r["merged"]
    render = RENDERS / f"{slug}-final.mp4"
    rec = {"status": "scripted", "mode": mode, "kind": kind,
           "why_full": why or None,
           "words_before": words_now(text), "words_after": words_now(merged),
           "budget": r["budget"], "model": r["model"], "scripted_at": _now(),
           "old_render_sha256": sha256(render) if render.exists() else None}
    for p in _twins(slug):
        p.write_text(merged, encoding="utf-8")
    rec = _bind_local(slug, sp, old_plan, mode, bd, rec)
    d = doc if doc is not None else load()
    d["episodes"][slug] = {**(d["episodes"].get(slug) or {}), **rec}
    if doc is None:
        save(d)
    return {"slug": slug, **rec}


def _decide_mode(slug: str, old_plan: list[dict] | None):
    """('splice', '', boundary) when the render on this machine can keep its
    body; ('full', why, None) otherwise."""
    beats = _read_json(AUDIO / slug / "beats.json", [])
    side = _read_json(RENDERS / f"{slug}-final.mp4.render.json", None)
    try:
        if not (RENDERS / f"{slug}-final.mp4").exists():
            raise SpliceUnusable("no render on this machine")
        if not old_plan:
            raise SpliceUnusable("no plan the render was built from")
        return "splice", "", boundary(old_plan, beats, side)
    except SpliceUnusable as e:
        return "full", str(e), None


def _bind_local(slug: str, sp: Path, old_plan: list[dict] | None, mode: str,
                bd: dict | None, rec: dict) -> dict:
    """The new script is on disk. Make this machine's plan, wavs and render
    agree with it: keep the rendered body (splice) or retire what the old
    script produced (full). Nothing is deleted."""
    plan_p = PLANS / f"{slug}.json"
    render = RENDERS / f"{slug}-final.mp4"
    new_plan = _plan_for(sp)
    if mode == "splice":
        new_k = next((i for i, p in enumerate(new_plan)
                      if (p.get("heading") or "").strip().lower() == TITLE_CARD), None)
        body_old = old_plan[bd["k"]:]
        body_new = new_plan[new_k:new_k + len(body_old)] if new_k else []
        same = new_k is not None and len(body_new) == len(body_old) and all(
            (a.get("narration"), a.get("segment")) ==
            (b_.get("narration"), b_.get("segment"))
            for a, b_ in zip(body_old, body_new))
        if same:
            plan_p.write_text(json.dumps(new_plan, indent=1) + "\n")
            rm = remap_audio(slug, bd["k"], new_k, len(body_old))
            rec.update({"mode": "splice", "old_k": bd["k"], "new_k": new_k,
                        "body_beats": len(body_old),
                        "boundary_frames": bd["boundary_frames"],
                        "total_frames_old": bd["total_frames"],
                        "body_s": bd["body_s"], "audio_moved": rm["moved"]})
            return rec
        mode = "full"
        rec["why_full"] = ("the re-planned body does not reproduce the "
                           "rendered beats, so the render cannot be kept")
    import extend                                          # noqa: PLC0415
    import durations                                       # noqa: PLC0415
    rec["mode"] = "full"
    if old_plan:
        old_narr = {i: b.get("narration") for i, b in enumerate(old_plan)}
        extend.retire_stale_audio(slug, old_narr, new_plan=new_plan)
    if plan_p.exists():
        plan_p.unlink()
    if render.exists():
        rec["old_render_sha256"] = rec.get("old_render_sha256") or sha256(render)
        record_superseded(slug, render, f"lengthen {rec.get('kind') or 'extend'}: "
                          f"full re-render (new opening"
                          f"{' + tail' if rec.get('kind') != 'reopen' else ''})")
        keep = RENDERS / "superseded-short"
        keep.mkdir(exist_ok=True)
        shutil.move(str(render), str(keep / f"{slug}-final.pre-lengthen.mp4"))
        side = RENDERS / f"{slug}-final.mp4.render.json"
        if side.exists():
            shutil.move(str(side), str(keep / f"{slug}-final.pre-lengthen.mp4.render.json"))
        durations.forget(slug)
    extend.retire_shorts(slug)
    rec["status"] = "full_rerender"
    return rec


def bind(slug: str, doc: dict) -> dict:
    """THE MAC HALF of a cloud re-open/extension (`pending_bind`). The cloud
    lane wrote the new script and touched nothing else; plans/<slug>.json,
    audio/<slug>/ and renders/ on this Mac are still the OLD script's. Runs
    in bin/batch-session.sh BEFORE the batch plans or narrates, so a stale
    wav is never voiced into a new beat and a stale render never ships."""
    rec = dict(doc["episodes"].get(slug) or {})
    if rec.get("status") != "scripted" or rec.get("mode") != "pending_bind":
        return {"slug": slug, "status": "skip",
                "why": f"state is {rec.get('status')!r}/{rec.get('mode')!r}"}
    sp = script_path(slug)
    text = sp.read_text(encoding="utf-8") if sp.exists() else ""
    if hashlib.sha256(text.encode()).hexdigest() != rec.get("new_script_sha256"):
        return {"slug": slug, "status": "refused",
                "why": "the script on disk is not the one the cloud wrote - "
                       "pull first; nothing was moved"}
    plan_p = PLANS / f"{slug}.json"
    old_plan = _read_json(plan_p, None) if plan_p.exists() else None
    mode, why, bd = _decide_mode(slug, old_plan)
    if mode == "full":
        rec["why_full"] = why
    rec = _bind_local(slug, sp, old_plan, mode, bd, rec)
    rec["bound_at"] = _now()
    doc["episodes"][slug] = rec
    return {"slug": slug, **rec}


# ---------------------------------------------------------- stage: splice
def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def _assemble(plan_path: str, out: str, audio_dir: str) -> dict:
    sys.path.insert(0, str(ROOT / "visuals"))
    import assemble                                        # noqa: PLC0415
    return assemble.assemble(plan_path, out, audio_dir, burn_captions=True)


def _ffprobe_s(path: Path) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)])
    return float(r.stdout.strip())


def _video_md5s(path: Path) -> list[str]:
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
              "-map", "0:v:0", "-c", "copy", "-f", "framemd5", "-"])
    return [ln.rsplit(",", 1)[-1].strip() for ln in r.stdout.splitlines()
            if ln and not ln.startswith("#")]


def _segment(slug: str, plan: list[dict], first: int, n: int, out: Path,
             work: Path) -> Path:
    """Render plan[first:first+n] with its own wavs via visuals/assemble.py."""
    sub = work / f"{out.stem}.plan.json"
    sub.write_text(json.dumps(plan[first:first + n]))
    adir = work / f"{out.stem}.audio"
    adir.mkdir()
    for j in range(n):
        src = AUDIO / slug / f"{first + j:04d}.wav"
        os.symlink(src, adir / f"{j:04d}.wav")
    ASSEMBLE(str(sub), str(out), str(adir))
    return out


ASSEMBLE = _assemble          # tests replace these
THUMB_OUT: str | None = None  # None = channel/thumbnails (thumbs_for default)
RUN = _run


def stage_splice(slug: str, dry_run: bool = False, doc: dict | None = None) -> dict:
    d = doc if doc is not None else load()
    rec = d["episodes"].get(slug) or {}
    if rec.get("status") != "scripted" or rec.get("mode") != "splice":
        return {"slug": slug, "status": "skip",
                "why": f"state is {rec.get('status')!r}/{rec.get('mode')!r}"}
    plan = _read_json(PLANS / f"{slug}.json", [])
    missing = [i for i in range(len(plan))
               if not (AUDIO / slug / f"{i:04d}.wav").exists()]
    if missing:
        return {"slug": slug, "status": "waiting_narration",
                "why": f"{len(missing)} new beat(s) not narrated yet"}
    render = RENDERS / f"{slug}-final.mp4"
    if not render.exists() or sha256(render) != rec.get("old_render_sha256"):
        return {"slug": slug, "status": "refused",
                "why": "the render on disk is not the one the boundary was "
                       "measured on"}
    new_k, body_n = rec["new_k"], rec["body_beats"]
    tail_first = new_k + body_n
    if dry_run:
        return {"slug": slug, "status": "dry_run",
                "plan": {"open_beats": new_k, "body_beats": body_n,
                         "tail_beats": len(plan) - tail_first,
                         "cut_at_frame": rec["boundary_frames"]}}
    with tempfile.TemporaryDirectory(prefix=f"lengthen-{slug}-") as td:
        work = Path(td)
        opening = _segment(slug, plan, 0, new_k, work / "open.mp4", work)
        # A hook-only re-open has no tail: new opening + kept body.
        tail = (_segment(slug, plan, tail_first, len(plan) - tail_first,
                         work / "tail.mp4", work)
                if len(plan) > tail_first else None)
        body = work / "body.mp4"
        bs = rec["boundary_frames"] / FPS
        RUN(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{bs:.6f}", "-i", str(render), "-c", "copy",
             "-avoid_negative_ts", "make_zero", str(body)])
        old_md5 = _video_md5s(render)[rec["boundary_frames"]:]
        body_md5 = _video_md5s(body)
        if old_md5 != body_md5:
            return {"slug": slug, "status": "refused",
                    "why": f"the cut body is not byte-identical to the old "
                           f"render from frame {rec['boundary_frames']} "
                           f"({len(body_md5)} vs {len(old_md5)} packets)"}
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in (opening, body, tail)
                               if p is not None))
        out = work / f"{slug}-final.mp4"
        RUN(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f",
             "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
             "-movflags", "+faststart", str(out)])
        stitched_md5 = _video_md5s(out)
        n_open = len(_video_md5s(opening))
        if stitched_md5[n_open:n_open + len(body_md5)] != body_md5:
            return {"slug": slug, "status": "refused",
                    "why": "the stitched file does not carry the body "
                           "byte-identical"}
        secs = _ffprobe_s(out)
        if secs / 60.0 < FLOOR_MIN:
            return {"slug": slug, "status": "refused",
                    "why": f"stitched render is {secs / 60:.2f} min, under "
                           f"the {FLOOR_MIN}-minute floor"}
        finish_splice(slug, out, secs, rec, d)
    if doc is None:
        save(d)
    return {"slug": slug, "status": "spliced",
            "minutes": round(rec["new_seconds"] / 60, 2)}


def finish_splice(slug: str, stitched: Path, secs: float, rec: dict,
                  doc: dict) -> None:
    """Swap the render in, record everything, clear the hold."""
    import durations                                       # noqa: PLC0415
    import extend                                          # noqa: PLC0415
    render = RENDERS / f"{slug}-final.mp4"
    side = RENDERS / f"{slug}-final.mp4.render.json"
    keep = RENDERS / "superseded-short"
    keep.mkdir(exist_ok=True)
    record_superseded(slug, render, f"lengthen: spliced to {secs / 60:.2f} min "
                      f"(new opening + kept body + tail)")
    shutil.move(str(render), str(keep / f"{slug}-final.pre-lengthen.mp4"))
    if side.exists():
        shutil.move(str(side), str(keep / f"{slug}-final.pre-lengthen.mp4.render.json"))
    shutil.move(str(stitched), str(render))
    plan = _read_json(PLANS / f"{slug}.json", [])
    side.write_text(json.dumps({
        "output": f"renders/{slug}-final.mp4", "beats": len(plan),
        "duration_s": round(secs, 1), "audio": True, "timing": "audio",
        "captions_burned": True, "spliced": {
            "open_beats": rec["new_k"], "body_beats": rec["body_beats"],
            "tail_beats": len(plan) - rec["new_k"] - rec["body_beats"],
            "body_from_frame": rec["boundary_frames"]}}, indent=2) + "\n")
    # Captions and chapters are regenerated for the new timeline by the
    # batch's captions phase (loop/captions_build.py builds what is missing).
    for f in (CAPTIONS / f"{slug}.srt", CAPTIONS / f"{slug}.chapters.txt"):
        if f.exists():
            (CAPTIONS / "superseded").mkdir(exist_ok=True)
            shutil.move(str(f), str(CAPTIONS / "superseded" / f"pre-lengthen-{f.name}"))
    durations.forget(slug)
    durations.record(slug, secs, "render (spliced, ffprobe)",
                     words_now((SCRIPTS / f"{slug}.md").read_text(encoding="utf-8")))
    extend.retire_shorts(slug)        # local cuts timed on the old render only
    cleared = clear_hold(slug)
    try:
        sys.path.insert(0, str(ROOT / "visuals"))
        import thumbs_for                                  # noqa: PLC0415
        thumbs_for.build(slug, out_dir=THUMB_OUT)
    except Exception as e:                                 # noqa: BLE001
        rec["thumbnail_error"] = str(e)[:200]
    rec.update({"status": "spliced", "spliced_at": _now(),
                "new_seconds": round(secs, 3),
                "new_render_sha256": sha256(render), "hold_cleared": cleared})
    doc["episodes"][slug] = rec


# -------------------------------------------------------------------- cli
def _short_slugs() -> list[str]:
    """Queued scripts and drafts under the floor. Never a published slug."""
    out, done = [], published_slugs()
    for p in sorted(list(SCRIPTS.glob("*.md")) + list(DRAFTS.glob("*.md"))):
        if p.stem in done or p.stem in out or ".extended" in p.name:
            continue
        try:
            if needs_lengthening(p.read_text(encoding="utf-8"), _measured_s(p.stem)):
                out.append(p.stem)
        except Exception:                                  # noqa: BLE001
            continue
    return out


def upload_hold(slug: str) -> str | None:
    """Why the upload lanes must not ship this queued episode yet, or None.

    * a re-open/extension is scripted but not yet re-rendered: whatever cut
      exists (on the Mac or the R2 shelf) speaks the OLD opening;
    * the script itself breaks the hook rule: the repackage lane re-opens it
      first (owner, 13 Oct 2026 - every queued script opens stake-then-payoff).
    A full re-render's stale shelf cut is refused separately, by sha256, from
    loop/state/superseded_renders.json (loop/cloud_upload.py)."""
    rec = load()["episodes"].get(slug) or {}
    if rec.get("status") == "scripted":
        return (f"its new opening is scripted ({rec.get('mode')}) but not yet "
                f"rendered; the cut that exists speaks the old one")
    p = script_path(slug)
    if p.exists():
        bad = hook_problems(p.read_text(encoding="utf-8"))
        if bad:
            return f"its opening breaks the hook rule: {bad[0][:160]}"
    return None


def queue_slugs() -> list[str]:
    """Every QUEUED script (scripts/ and loop/drafts/, never a published slug)
    that breaks the floor or the hook rule, short ones first. The one list
    the cloud lane works and V49 holds."""
    out, done = [], published_slugs()
    doc = load()
    short, hook = [], []
    for p in sorted(list(SCRIPTS.glob("*.md")) + list(DRAFTS.glob("*.md"))):
        s = p.stem
        if s in done or s in out or s in short or s in hook or ".extended" in p.name:
            continue
        if (doc["episodes"].get(s) or {}).get("mode") == "pending_bind":
            continue                 # scripted in the cloud; the Mac binds it
        try:
            text = script_path(s).read_text(encoding="utf-8")
            k = _kind(text, _measured_s(s))
        except Exception:                                  # noqa: BLE001
            continue
        if k == "extend":
            short.append(s)
        elif k == "reopen":
            hook.append(s)
    return short + hook


def run_bind() -> int:
    """THE MAC: bind every `pending_bind` episode (see bind())."""
    doc = load()
    todo = sorted(s for s, r in doc["episodes"].items()
                  if r.get("status") == "scripted" and r.get("mode") == "pending_bind")
    if not todo:
        print("LENGTHEN_NOTHING_TO_BIND: no cloud re-open or extension awaits this Mac")
        return 0
    for s in todo:
        r = bind(s, doc)
        print(f"  {r['status']:<14} {r.get('mode', ''):<7} {s}  {r.get('why') or r.get('why_full') or ''}")
    save(doc)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("plan", "script", "splice", "status",
                                    "reopen", "bind"))
    ap.add_argument("--slugs", nargs="*")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cloud", action="store_true",
                    help="reopen on a machine without the Mac's audio/renders: "
                         "write the script, leave the binding to the Mac")
    a = ap.parse_args(argv)
    if a.cmd == "reopen":
        if a.cloud:
            import queue_reopen                            # noqa: PLC0415
            return queue_reopen.run(a.limit, a.dry_run, a.slugs or None)
        a.cmd = "script"             # on the Mac: re-open and bind in one go
    if a.cmd == "bind":
        return run_bind()
    doc = load()
    if a.cmd == "status":
        eps = doc["episodes"]
        if not eps:
            print("LENGTHEN_NOTHING_RECORDED: no episode has been lengthened yet")
            return 0
        for s, r in sorted(eps.items()):
            print(f"  {r.get('status'):<14} {r.get('mode', ''):<7} {s}")
        return 0
    if a.cmd == "splice":
        slugs = a.slugs or sorted(s for s, r in doc["episodes"].items()
                                  if r.get("status") == "scripted"
                                  and r.get("mode") == "splice")
        if not slugs:
            print("LENGTHEN_NOTHING_TO_SPLICE: no scripted episode awaits a splice")
            return 0
        done = 0
        for s in slugs[: a.limit or None]:
            r = stage_splice(s, a.dry_run, doc)
            done += r["status"] in ("spliced", "dry_run")
            print(f"  {r['status']:<18} {s}  {r.get('why') or r.get('minutes') or r.get('plan') or ''}")
        if not a.dry_run:
            save(doc)
        return 0
    slugs = a.slugs if a.slugs is not None and a.slugs else queue_slugs()
    if a.limit:
        slugs = slugs[: a.limit]
    if not slugs:
        print("LENGTHEN_NONE_SHORT: every script is at or over the "
              f"{FLOOR_MIN}-minute floor")
        return 0
    if a.cmd == "plan":
        for s in slugs:
            text = script_path(s).read_text(encoding="utf-8")
            w = words_now(text)
            print(f"  {s}: {w} narrated words ({minutes_of_words(w):.2f} min); "
                  f"needs >= {MIN_WORDS}")
        return 0
    done, refused = 0, []
    for s in slugs:
        r = stage_script(s, a.dry_run, doc)
        print(f"  {r['status']:<14} {s}  "
              + str(r.get("budget") or r.get("problems") or r.get("why") or ""))
        if r["status"] in ("scripted", "full_rerender", "dry_run"):
            done += 1
        elif r["status"] == "rejected":
            refused.append(s)
    if not a.dry_run:
        save(doc)
    if refused and not done:
        print(f"NAMED STOP LENGTHEN_REJECTED: {len(refused)} extension(s) failed "
              f"the gates after every attempt: {', '.join(refused)}. The scripts "
              f"are unchanged; an episode padded with filler is worse than a "
              f"short one.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
