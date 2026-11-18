#!/usr/bin/env python3
"""PSALM NIGHTS: whispered King James scripture for sleep, its rules in code.

    python loop/psalms.py rotation     # the nights, the next one first, and the bundle's state

Her yes 18 Nov 2026 (spry brain, Settled decisions, "PSALM NIGHTS LANE"):
whispered scripture for sleep (Psalm 91, Psalm 23, other psalms and
scripture for sleep) in her cloned whisper voice, built like the Neville
lane (same nightly narrator lock, render, Shorts and upload path), on the
Friday 8 PM CT slot.

  * THE TEXT IS THE KING JAMES VERSION ONLY (1769, public domain in the US),
    read word for word from the bundled text config/kjv/kjv.json
    (loop/tools/kjv_bundle.py builds it from eBible.org's public-domain
    KJV and records the source, its licence wording and its hash). A verse
    is never taken from a model's memory and never from a modern
    translation (NIV, ESV, NLT and the rest are copyrighted).
  * A night (config `psalms.nights`) names its passages; the script reads
    them in a fixed plan (`plan`): a welcome, the main passage, a short
    reflection, the companion passages, a second reflection, the main
    passage again, slower, and a closing rest. Only the welcome, the
    reflections and the rest are written by the free-model author, in
    plain words, with no health claim and no promised outcome.
  * The rotation never repeats a night within the last RECENT Psalm scripts
    (about 12 weeks at one a week).

What this file refuses (loop/whisper_lane.script_problems calls it for the
kind `psalm`; loop/tests/test_psalm_lane.py proves each one negatively):

  PASSAGE_NOT_IN_KJV      a passage the bundled KJV does not hold
  PASSAGE_NOT_VERBATIM    a passage segment that is not, word for word, the
                          bundled KJV text of its reference (a modern
                          translation's wording, a word added or dropped)
  PASSAGE_NOT_IN_NIGHT    a passage the night does not name
  PLAN                    the segments are not the night's plan
  SCRIPTURE_OUTSIDE_PASSAGE
                          eight words of scripture in the framing (quoted
                          from a model's memory instead of the bundle)
  QUOTE_MARKS, HEALTH_CLAIM, GUARANTEED_OUTCOME, SLEEP_CLAIM
                          in the framing: no quoting, no claims
  NIGHT_REPEATED          the night was read in the last RECENT Psalm scripts
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import whisper_words as W                                   # noqa: E402

KJV = ROOT / "config" / "kjv" / "kjv.json"
KIND = "psalm"
RECENT = 12                # a night may not repeat within the last 12 Psalm scripts (~12 weeks)
PREFIX = "kjv:"            # a passage segment's source: kjv:PSA.91.1-16
FRAMING = ("welcome", "reflect", "rest")
REF_RX = re.compile(r"^(?P<book>[1-3]?[A-Z]{2,3})\.(?P<ch>\d+)\.(?P<a>\d+)(?:-(?P<b>\d+))?$")
# In the framing only (the scripture itself is read as written): a sleep or
# health promise is a claim the channel never makes (her spec 18 Nov 2026:
# no "cures insomnia", no guaranteed result).
SLEEP_CLAIM = re.compile(
    r"\b(?:insomnia|sleep disorders?|anxiety|panic attacks?|stress relief|cures?|guaranteed|"
    r"you will (?:fall asleep|sleep|be (?:healed|protected|safe))|will (?:protect|keep) you safe|"
    r"promises? (?:you|that you))\b", re.I)


# ------------------------------------------------------------- the bundled text
_BUNDLE: dict | None = None


def bundle() -> dict:
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = json.loads(KJV.read_text()) if KJV.exists() else {"books": {}}
    return _BUNDLE


def parse_ref(ref: str) -> tuple[str, int, int, int]:
    m = REF_RX.match(ref)
    if not m:
        raise KeyError(f"PASSAGE_NOT_IN_KJV {ref!r} is not a reference like PSA.91.1-16")
    a = int(m.group("a"))
    return m.group("book"), int(m.group("ch")), a, int(m.group("b") or a)


def verses(ref: str, b: dict | None = None) -> list[str]:
    """The bundled KJV verses of a reference, in order, as printed. KeyError
    (PASSAGE_NOT_IN_KJV) for any verse the bundle does not hold."""
    b = b or bundle()
    book, ch, a, z = parse_ref(ref)
    chap = (b["books"].get(book) or {}).get("chapters", {}).get(str(ch))
    if not chap or z < a:
        raise KeyError(f"PASSAGE_NOT_IN_KJV {ref} is not in the bundled King James text")
    out = []
    for v in range(a, z + 1):
        if str(v) not in chap:
            raise KeyError(f"PASSAGE_NOT_IN_KJV {ref}: verse {v} is not in the bundled King James text")
        out.append(chap[str(v)])
    return out


def spoken(verse: str) -> str:
    """A verse as the voice reads it: LORD and GOD (small capitals in print)
    in ordinary case so the voice never spells them. The words are the KJV's."""
    return re.sub(r"\b([A-Z])([A-Z]+)\b", lambda m: m.group(1) + m.group(2).lower(), verse)


def tokens(text: str) -> list[str]:
    """Words, lowercased, letters only: case, punctuation and the curly
    apostrophe never decide whether a verse matches."""
    return [t for t in (re.sub(r"[^a-z]", "", w.lower()) for w in W.WORD.findall(text)) if t]


def label(ref: str, b: dict | None = None) -> str:
    """'PSA.91.1-16' -> 'Psalm 91:1-16' (for the description)."""
    b = b or bundle()
    book, ch, a, z = parse_ref(ref)
    name = (b["books"].get(book) or {}).get("name", book)
    name = "Psalm" if name == "Psalms" else name
    return f"{name} {ch}:{a}" + (f"-{z}" if z != a else "")


_RUNS: set[str] | None = None


def _hash(run: list[str]) -> str:
    return hashlib.blake2b(" ".join(run).encode(), digest_size=5).hexdigest()


def scripture_runs() -> set[str]:
    """Every eight-word run of the bundled KJV (hashed): framing that holds
    one is scripture quoted from memory, not from the bundle."""
    global _RUNS
    if _RUNS is None:
        _RUNS = set()
        for bk in bundle()["books"].values():
            for chap in bk["chapters"].values():
                t = tokens(" ".join(chap[k] for k in sorted(chap, key=int)))
                _RUNS.update(_hash(t[i:i + 8]) for i in range(max(0, len(t) - 7)))
    return _RUNS


def scripture_hits(text: str) -> int:
    t = tokens(text)
    return sum(1 for i in range(max(0, len(t) - 7)) if _hash(t[i:i + 8]) in scripture_runs())


# ------------------------------------------------------------- the nights
def nights(c: dict) -> dict[str, dict]:
    return c["psalms"]["nights"]


def plan(night: dict) -> list[str]:
    """The segment sources of a night's script, in order: framing parts and
    kjv:<ref> passages (the main passage read twice, the second time near
    sleep)."""
    main = [PREFIX + r for r in night["main"]]
    comp = [PREFIX + r for r in night["companions"]]
    return ["welcome", *main, "reflect-1", *comp, "reflect-2", *main, "rest"]


def is_passage(source: str) -> bool:
    return source.startswith(PREFIX)


def night_refs(night: dict) -> list[str]:
    return list(dict.fromkeys(night["main"] + night["companions"]))


def recent_nights(others: list[dict], n: int = RECENT) -> list[str]:
    ps = sorted((o for o in others if o.get("kind") == KIND),
                key=lambda o: (o["meta"].get("written", ""), o.get("slug", "")), reverse=True)
    return [o["meta"].get("night", "") for o in ps[:n]]


def next_night(c: dict, others: list[dict]) -> str:
    """The rotation: the night read least, in config order, never one of the
    last RECENT Psalm scripts' nights (so none repeats within ~12 weeks)."""
    keys = list(nights(c))
    used = [o["meta"].get("night", "") for o in others if o.get("kind") == KIND]
    recent = set(recent_nights(others))
    free = [k for k in keys if k not in recent]
    if not free:
        raise LookupError(f"PSALM_ROTATION_EXHAUSTED every one of the {len(keys)} nights was read in the "
                          f"last {RECENT} Psalm scripts; add nights to config `psalms.nights`")
    return min(free, key=lambda k: (used.count(k), keys.index(k)))


def framing_text(p: dict) -> str:
    """Everything the free model wrote (the welcome, reflections and rest):
    what makes one Psalm night distinct from another reading the same psalm."""
    return "\n\n".join(x for s in p["segments"] if not is_passage(s["source"]) for x in s["paragraphs"])


def allowed_names(night: dict) -> str:
    """Names the framing may say: the passages' own words, the books, and the Bible's name."""
    b = bundle()
    words = ["Psalm Psalms King James Bible Version Lord God Amen"]
    for r in night_refs(night):
        try:
            words += verses(r, b)
        except KeyError:
            pass
        book = parse_ref(r)[0]
        words.append((b["books"].get(book) or {}).get("name", ""))
    return " ".join(words)


def framing_problems(text: str, night: dict) -> list[str]:
    """The framing's own rules (no quoting, no claims, no new names); the
    plain-words check runs on it in loop/whisper_lane.script_problems."""
    import whisper_lane as WL                               # noqa: PLC0415
    out = []
    if re.search(r"[“”\"]", text):
        out.append("QUOTE_MARKS no quotation marks in the framing: scripture is read only in its passage")
    hits = scripture_hits(text)
    if hits:
        out.append(f"SCRIPTURE_OUTSIDE_PASSAGE {hits} eight-word run(s) of scripture in the framing: "
                   f"verses are read only from the bundled King James text, in a passage segment")
    out += WL.affirmation_problems(text)
    out += [f"SLEEP_CLAIM {m.group(0)!r}" for m in SLEEP_CLAIM.finditer(text)]
    out += [x.replace("is not in the source script", "is not in the night's passages")
            for x in W.fact_problems(text, allowed_names(night))]
    return out


def psalm_problems(p: dict, others: list[dict], c: dict) -> list[str]:
    """Every Psalm Nights rule on a parsed script (see the module doc)."""
    out: list[str] = []
    key = p["meta"].get("night", "")
    night = nights(c).get(key)
    if night is None:
        return [f"NIGHT {key!r} is not one of config `psalms.nights`"]
    want = plan(night)
    got = [s["source"] for s in p["segments"]]
    if got != want:
        out.append(f"PLAN the segments are {got}, the night {key!r} reads {want}")
    named = set(night_refs(night))
    b = bundle()
    if not b["books"]:
        out.append("KJV_BUNDLE_MISSING config/kjv/kjv.json is empty: no passage could be checked "
                   "(run loop/tools/kjv_bundle.py)")
    n_passages = 0
    for s in p["segments"]:
        src = s["source"]
        if not is_passage(src):
            continue
        n_passages += 1
        ref = src[len(PREFIX):]
        where = f"segment {s['n']} ({ref})"
        if ref not in named:
            out.append(f"{where}: PASSAGE_NOT_IN_NIGHT {ref} is not one of the night's passages")
        try:
            kjv = tokens(" ".join(verses(ref, b)))
        except KeyError as e:
            out.append(f"{where}: {e.args[0]}")
            continue
        mine = tokens(" ".join(s["paragraphs"]))
        if mine != kjv:
            i = next((j for j, (x, y) in enumerate(zip(mine, kjv)) if x != y), min(len(mine), len(kjv)))
            out.append(f"{where}: PASSAGE_NOT_VERBATIM differs from the King James text at word {i + 1} "
                       f"({' '.join(mine[i:i + 4])!r}, the KJV reads {' '.join(kjv[i:i + 4])!r})")
    if not n_passages:
        out.append("PASSAGE_NONE no passage segment examined")
    framing = "\n\n".join(x for s in p["segments"] if not is_passage(s["source"])
                          for j, x in enumerate(s["paragraphs"])
                          if not (s is p["segments"][0] and j == 0))   # the spoken promise
    if not framing.strip():
        out.append("FRAMING_NONE no framing examined")
    else:
        out += framing_problems(framing, night)
    if key in recent_nights(others):
        out.append(f"NIGHT_REPEATED {key!r} was read in the last {RECENT} Psalm scripts")
    return out


def credits(p: dict, c: dict) -> list[str]:
    """The description's scripture lines: every passage read, and its text's status."""
    night = nights(c).get(p["meta"].get("night", ""), {"main": [], "companions": []})
    refs = "; ".join(label(r) for r in night_refs(night))
    return [f"Read tonight: {refs}.",
            "Scripture text: the King James Version (1769), public domain in the US, read word for word.",
            "Scripture to rest with, not a promise of any outcome."]


def main(argv: list[str]) -> int:
    if argv[:1] == ["rotation"]:
        import whisper_lane as WL                           # noqa: PLC0415
        c = WL.cfg()
        others = [WL.parse(f) for f in WL.all_scripts()]
        b = bundle()
        bad = 0
        for k, n in nights(c).items():
            probs = []
            for r in night_refs(n):
                try:
                    verses(r, b)
                except KeyError as e:
                    probs.append(e.args[0])
            bad += bool(probs)
            print(f"{k:22} {', '.join(label(r) for r in night_refs(n))[:90]}"
                  + (f"  PROBLEM {probs[0]}" if probs else ""))
        try:
            nxt = next_night(c, others)
        except LookupError as e:
            nxt = str(e)
        print(f"OUTPUT {len(nights(c))} nights, next {nxt}, {sum(len(x['chapters']) for x in b['books'].values())} "
              f"bundled KJV chapters, {bad} night(s) with a passage not in the bundle")
        return 0 if nights(c) and b["books"] and not bad else 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
