"""The opening rule: the payoff lands in the first 30 seconds, and it is measured.

THE FINDING (loop/state/retention_finding.md, 2026-09-25). 1m53s average view
duration across 10 videos against a 146s floor; 6 of 10 lose the average
viewer inside the first two minutes. The structure, not the topics: viewers
leave before the first real explanation lands.

THE DECISION, made for the owner (her rule: nothing waits on her; a finding
becomes an action with a measurement, never a question). Every script drafted
from 2026-09-28 on opens with the PAYOFF - the actual answer or the most
surprising true fact - inside the first 30 seconds of narration, and only
then walks the "how we know" chain. Published videos are untouched: never
re-cut, never deleted.

HOW IT IS HELD TO THAT:
  * `prompt_text()` is the opening instruction every draft's prompt carries
    (loop/author.py HOUSE_RULES) and every hand-authoring brief carries
    (loop/draft.py brief_for);
  * `problems()` is the draft gate: a script whose answer is not inside the
    first ANSWER_WITHIN_WORDS narrated words is rejected and REDRAFTED inside
    the author's own retry loop (loop/author.py shape_problems), not held;
  * `mark()` stamps the variant on the script (`**Opening:** <id>`), so the
    Friday measure lane can tag every measured video with the rule it was
    drafted under (`variant_of`), pre-rule videos as PRE_RULE;
  * `evaluate()` runs in the Friday measure lane: once the active variant has
    had COMPARE_AFTER_DAYS and MIN_COHORT measured videos, its average view
    duration is compared with the cohort before it. Not above it -> the lane
    switches to the next variant in VARIANTS by itself and logs why. No stop
    either way.

THE HOOK (owner instruction, 13 Oct 2026: "a hook, not an encyclopaedia
opening"). `stake-then-payoff` is FIRST in VARIANTS and in force from
HOOK_START: the first narrated sentence is at most 15 words, states a concrete
stake, contradiction or figure, and shares under half its content words with
the title and with the question; the payoff (the Direct-answer lock's first
sentence) is still inside the first 75 words; then the "how we know" chain.
problems() gates all three; a failing draft is redrafted inside the author's
retry loop as before. The 28-day AVD measurement and the auto-switch work
unchanged with it active (its baseline is the pre-rule cohort; losing switches
to cold-open-payoff). Published videos: their titles and thumbnails are now
governed by the repackage job (loop/longform_title.py, visuals/thumb_contract.py,
loop/repackage.py apply); their cuts are never edited in place, never
re-uploaded and never extended - forward only (owner, 13 Oct 2026).

The answer check is mechanical, not a judgement: the Direct-answer lock's
first sentence is the answer; at least ANSWER_SHARE of its content words (and
at least ANSWER_MIN_HITS of them) must be spoken in the first
ANSWER_WITHIN_WORDS words. (Figures are not matched digit-for-digit: the
narration spells numbers out for the voice.) 75 words is 31 seconds at the measured 144.58 wpm
(loop/durations.py).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "loop" / "state" / "opening_variant.json"
SCRIPTS = ROOT / "scripts"

RULE_START = "2026-09-28"          # drafts from this Monday on
HOOK_START = "2026-10-13"          # stake-then-payoff in force from here
PRE_RULE = "pre-rule"
ANSWER_WITHIN_WORDS = 75           # ~31 s at 144.58 wpm
ANSWER_SHARE = 0.5
ANSWER_MIN_HITS = 3
COMPARE_AFTER_DAYS = 28
MIN_COHORT = 3

# Ordered. The first is the rule in force from RULE_START; each later one is
# what the lane switches to if the one before it does not beat its baseline.
VARIANTS = {
    # Owner instruction, 13 Oct 2026: a hook, not an encyclopaedia opening.
    "stake-then-payoff": {
        "prompt": (
            "OPENING RULE (stake-then-payoff, in force for every script): the "
            "FIRST narrated sentence is a hook of at most {first} words that "
            "states a concrete stake, contradiction or figure - something "
            "that is lost, broken, impossible or surprising, from this "
            "episode's own evidence. It must NOT restate the title or the "
            "question (share fewer than half its content words with either). "
            "Then the PAYOFF: the Direct-answer lock's first sentence must be "
            "recognisably spoken inside the first {within} words. Only then "
            "the 'how we know' chain: where the evidence comes from, what it "
            "does and does not settle. Example shape (a different subject, "
            "for the SHAPE only): 'At the bottom of the Mariana Trench, a "
            "styrofoam cup shrinks to the size of a thimble.' - then the "
            "answer - then the evidence."),
        "question_within": None,
        "answer_within": ANSWER_WITHIN_WORDS,
        "first_sentence_max": 15,
        "title_overlap_max": 0.5,
    },
    "cold-open-payoff": {
        "prompt": (
            "OPENING RULE (cold-open-payoff, in force for every script): the "
            "first thirty seconds of narration - the first {within} words - "
            "must deliver the PAYOFF: the actual answer to the title question, "
            "or the single most surprising true fact that answers it, stated "
            "plainly with its figure if it has one. Only after the payoff do "
            "you open the 'how we know' chain: where the evidence comes from, "
            "what it does and does not settle. The Direct-answer lock's first "
            "sentence must be recognisably spoken inside those first {within} "
            "words. Do not open by restating the question, by scene-setting, "
            "or by promising an answer later."),
        "question_within": None,
        "answer_within": ANSWER_WITHIN_WORDS,
    },
    "question-first-teaser": {
        "prompt": (
            "OPENING RULE (question-first-teaser, in force for every script): "
            "the first ten seconds - the first {teaser} words - pose the title "
            "question in plain words together with a one-line teaser of the "
            "surprising answer (not the full answer). The full answer, the "
            "Direct-answer lock's first sentence, must then be spoken inside "
            "the first {within} words (about a minute). Then the 'how we know' "
            "chain follows."),
        "question_within": 25,
        "answer_within": 150,
    },
}

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
         "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
         "these", "those", "with", "from", "by", "as", "into", "than", "so",
         "do", "does", "did", "how", "why", "what", "which", "who", "when",
         "where", "can", "could", "will", "would", "has", "have", "had", "not",
         "no", "each", "other", "they", "their", "there", "we", "you", "our"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _content(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP]


def narration_words(script: str) -> list[str]:
    """The spoken words, in order: ## Narration up to the next ## section,
    minus headings and {{directives}}."""
    if "## Narration" not in script:
        return []
    body = script.split("## Narration", 1)[1]
    body = re.split(r"\n## ", body, maxsplit=1)[0]
    body = re.sub(r"\{\{.*?\}\}", " ", body, flags=re.S)
    lines = [ln for ln in body.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return " ".join(lines).split()


def answer_sentence(script: str) -> str:
    m = re.search(r"## Direct-answer lock\s*\n+(.+?)(?:\n\s*\n|\n## )",
                  script + "\n\n", re.S)
    if not m:
        return ""
    para = " ".join(m.group(1).split())
    return re.split(r"(?<=[.!?])\s+", para, maxsplit=1)[0]


def title_question(script: str) -> str:
    m = re.search(r"^# (.+)$", script, re.M)
    return m.group(1).strip() if m else ""


def first_sentence(script: str) -> str:
    """The first narrated sentence (directives and headings removed)."""
    spoken = " ".join(narration_words(script))
    return re.split(r"(?<=[.!?])\s+", spoken, maxsplit=1)[0] if spoken else ""


def youtube_title(script: str) -> str:
    m = re.search(r"^## YouTube title\s*\n+(.+?)\s*$", script, re.M)
    return m.group(1).strip().strip('"') if m else ""


def problems(script: str, variant: str) -> list[str]:
    """Why this script breaks the opening rule `variant`; [] when it holds."""
    spec = VARIANTS[variant]
    spoken = narration_words(script)
    if not spoken:
        return ["no ## Narration to check the opening of"]
    ans = answer_sentence(script)
    if not ans:
        return ["no Direct-answer lock sentence to check the opening against"]
    within = spec["answer_within"]
    head = " ".join(spoken[:within])
    head_toks = set(_content(head))
    want = list(dict.fromkeys(_content(ans)))
    hits = [t for t in want if t in head_toks]
    out = []
    need = max(ANSWER_MIN_HITS, int(len(want) * ANSWER_SHARE + 0.999))
    need = min(need, len(want))
    if len(hits) < need:
        out.append(
            f"opening rule {variant}: the answer is not in the first {within} "
            f"narrated words (~{within * 60 // 145}s). Only {len(hits)} of the "
            f"{len(want)} content words of the Direct-answer lock's first "
            f"sentence are spoken there (need {need}). Move the payoff - "
            f"{ans[:120]!r} - into the cold open, before the evidence chain.")
    fmax = spec.get("first_sentence_max")
    if fmax:
        first = first_sentence(script)
        n = len(first.split())
        if n > fmax:
            out.append(
                f"opening rule {variant}: the first narrated sentence is {n} "
                f"words; the hook must be at most {fmax} - one concrete "
                f"stake, contradiction or figure: {first[:120]!r}")
        fc = set(_content(first))
        omax = spec.get("title_overlap_max", 0.5)
        for label, ref in (("title", youtube_title(script)),
                           ("question", title_question(script))):
            rc = set(_content(ref or ""))
            if fc and rc and len(fc & rc) / len(fc) >= omax:
                out.append(
                    f"opening rule {variant}: the first sentence restates the "
                    f"{label} ({len(fc & rc)} of its {len(fc)} content words "
                    f"are in {ref!r}); open on the stake instead")
    qw = spec.get("question_within")
    if qw:
        q = set(_content(title_question(script)))
        first = set(_content(" ".join(spoken[:qw])))
        if q and len(q & first) < max(1, int(len(q) * 0.6 + 0.999)):
            out.append(
                f"opening rule {variant}: the title question is not posed in "
                f"the first {qw} words (~10s).")
    return out


def prompt_text(variant: str | None = None) -> str:
    v = variant or active()
    spec = VARIANTS[v]
    return spec["prompt"].format(within=spec["answer_within"],
                                 teaser=spec.get("question_within") or 0,
                                 first=spec.get("first_sentence_max") or 0)


# ------------------------------------------------------------ the marker

MARK_RE = re.compile(r"^\*\*Opening:\*\*\s*(\S+)", re.M)


def mark(script: str, variant: str) -> str:
    """Stamp the opening variant on a drafted script (after **Domain:**)."""
    line = f"**Opening:** {variant}"
    if MARK_RE.search(script):
        return MARK_RE.sub(line, script, count=1)
    m = re.search(r"^\*\*Domain:\*\*.*$", script, re.M)
    if m:
        return script[: m.end()] + "\n" + line + script[m.end():]
    m = re.search(r"^# .+$", script, re.M)
    at = m.end() if m else 0
    return script[:at] + "\n\n" + line + script[at:]


def variant_of(slug: str) -> str:
    """The opening rule a script was drafted under; PRE_RULE when unmarked."""
    for path in (SCRIPTS / f"{slug}.md",):
        if path.exists():
            m = MARK_RE.search(path.read_text(encoding="utf-8"))
            if m and m.group(1) in VARIANTS:
                return m.group(1)
    return PRE_RULE


def stamp_on_assembly(path: Path, variant: str | None = None) -> tuple[str, list[str]]:
    """Stamp an unmarked script entering the week's queue with the active
    rule, when its opening already satisfies that rule's mechanical check.

    WHY (audit, 2026-10-12). author.draft() stamps every script it writes,
    but by 2026-10-12 it had written ONE since the rule came into force: the
    week's queue is assembled mostly from scripts/ inventory, and anything
    hand-authored from a brief_for() brief lands there unmarked too. So
    videos produced under the rule were measured as "pre-rule" and the
    experiment starved. Assembly is the one door every script passes through
    on its way to a render, so the stamp is applied there. A script whose
    opening does NOT pass the check is left unmarked and stays in the
    baseline - it is not what the rule asks for, and stamping it would
    poison the cohort the rule is judged on.

    Returns (outcome, problems): "marked" (already carried a marker),
    "stamped" (written now), or "nonconforming" (left as is).
    """
    text = path.read_text(encoding="utf-8")
    if MARK_RE.search(text):
        return "marked", []
    v = variant or active()
    why = problems(text, v)
    if why:
        return "nonconforming", why
    path.write_text(mark(text, v), encoding="utf-8")
    return "stamped", []


# ------------------------------------------------------------ the state

def _now() -> datetime:
    return datetime.now(timezone.utc)


def load(path: Path | None = None) -> dict:
    p = path or STATE
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError):
        doc = {}
    doc.setdefault("active", next(iter(VARIANTS)))
    doc.setdefault("since", RULE_START)
    doc.setdefault("history", [])
    return doc


def active(path: Path | None = None) -> str:
    v = load(path)["active"]
    return v if v in VARIANTS else next(iter(VARIANTS))


def cohorts(videos: list[dict]) -> dict[str, dict]:
    """variant -> {n, avd_s} over measured videos that carry `opening`."""
    acc: dict[str, list[float]] = {}
    for v in videos:
        d = v.get("average_view_duration_s")
        if d is None:
            continue
        acc.setdefault(v.get("opening") or PRE_RULE, []).append(float(d))
    return {k: {"n": len(x), "avd_s": round(sum(x) / len(x), 1)}
            for k, x in acc.items()}


def _day(s: str) -> datetime:
    return datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)


def compare_date(act: str, videos: list[dict],
                 aired: dict[str, list[str]] | None = None) -> datetime | None:
    """COMPARE_AFTER_DAYS after the MIN_COHORT-th video drafted under `act`
    went public; None while fewer than MIN_COHORT have an airing date.

    WHY NOT A FIXED DATE (audit, 2026-10-12). The date used to be `since` +
    28 days - 2026-10-26 for the first rule - but a rule's videos are not
    watched from the day it comes into force: the runway was 44 pre-rule
    scripts already uploaded and scheduled through 2026-11-08, so on its fixed
    date the rule had ONE marked video, airing two weeks later. A date counted
    from airings cannot arrive before the evidence does. `aired` is
    variant -> airing dates of every published video (measured or not, from
    the ledger); measured rows' own `aired_at` fill in when it is absent.
    """
    dates = set((aired or {}).get(act) or [])
    dates |= {v["aired_at"][:10] for v in videos
              if v.get("opening") == act and v.get("aired_at")}
    dates = sorted(dates)
    if len(dates) < MIN_COHORT:
        return None
    return _day(dates[MIN_COHORT - 1]) + timedelta(days=COMPARE_AFTER_DAYS)


def evaluate(videos: list[dict], now: datetime | None = None,
             path: Path | None = None, write: bool = True,
             aired: dict[str, list[str]] | None = None) -> dict:
    """Compare the active variant with its baseline and switch if it lost.

    Returns {"action": "wait"|"keep"|"switch", "why": ..., "decidable": bool,
    ...}. Never raises a stop. Baseline: the variant before the active one in
    VARIANTS, or PRE_RULE for the first. The comparison date is
    compare_date(): 28 days after the 3rd video drafted under the active rule
    AIRS. Until three have an airing date it is not yet decidable, and says so
    by name (the lane logs OPENING_NOT_YET_DECIDABLE).
    """
    now = now or _now()
    doc = load(path)
    act = doc["active"] if doc["active"] in VARIANTS else next(iter(VARIANTS))
    order = list(VARIANTS)
    base = PRE_RULE if order.index(act) == 0 else order[order.index(act) - 1]
    due = compare_date(act, videos, aired)
    c = cohorts(videos)
    new, old = c.get(act), c.get(base)
    res = {"active": act, "baseline": base, "cohorts": c,
           "compare_on": due.date().isoformat() if due else None,
           "decidable": True}
    if due is None:
        n = len(set((aired or {}).get(act) or []) |
                {v["aired_at"][:10] for v in videos
                 if v.get("opening") == act and v.get("aired_at")})
        return {**res, "action": "wait", "decidable": False,
                "why": f"not yet decidable: {n} published video(s) carry "
                       f"{act} (in force since {doc['since']}); the comparison "
                       f"with {base} is set {COMPARE_AFTER_DAYS} days after the "
                       f"{MIN_COHORT}rd one airs, and every newly authored "
                       f"script carries it"}
    if now < due:
        return {**res, "action": "wait",
                "why": f"{act} in force since {doc['since']}; its "
                       f"{MIN_COHORT}rd video airs "
                       f"{(due - timedelta(days=COMPARE_AFTER_DAYS)).date()}; "
                       f"compared with {base} on {due.date().isoformat()}"}
    if not new or new["n"] < MIN_COHORT or not old:
        return {**res, "action": "wait", "decidable": False,
                "why": f"{act} has {new['n'] if new else 0} measured video(s) "
                       f"(need {MIN_COHORT}) or no {base} baseline; compared "
                       f"again next Friday"}
    if new["avd_s"] > old["avd_s"]:
        return {**res, "action": "keep",
                "why": f"{act} averages {new['avd_s']}s against {base}'s "
                       f"{old['avd_s']}s; it stays"}
    nxt_i = order.index(act) + 1
    # Every variant tried and none beat its baseline: settle on the best
    # measured variant, and record that the list is exhausted.
    if nxt_i >= len(order):
        best = max((k for k in order if k in c), key=lambda k: c[k]["avd_s"])
        nxt, why_n = best, "every variant tried; settling on the best measured"
    else:
        nxt, why_n = order[nxt_i], "next variant in loop/opening.py VARIANTS"
    if nxt == act:
        return {**res, "action": "keep",
                "why": f"{act} is already the best measured variant"}
    stamp = now.isoformat(timespec="seconds")
    doc["history"].append({"from": act, "to": nxt, "at": stamp,
                           "why": f"{act} averaged {new['avd_s']}s over "
                                  f"{new['n']} video(s), not above {base}'s "
                                  f"{old['avd_s']}s over {old['n']}"})
    doc["active"], doc["since"] = nxt, stamp
    if write:
        (path or STATE).parent.mkdir(parents=True, exist_ok=True)
        (path or STATE).write_text(json.dumps(doc, indent=2) + "\n")
    return {**res, "action": "switch", "to": nxt,
            "why": doc["history"][-1]["why"] + f"; switched to {nxt} ({why_n})"}
