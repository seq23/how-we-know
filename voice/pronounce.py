"""pronounce.py - the pronunciation layer every narration passes through before TTS.

Why this exists (2026-10-24). A viewer commented on "Why Is Deep Sea Light
Blue?" (13-how-does-bioluminescence-work-in-the-deep-sea, published as
EFimztjj_j8): "AI had a stroke trying to say 'bioluminescence.'" Local Whisper
(whisper.cpp, ggml-small.en) on that episode's own beat wavs heard
"Biolu Min ESS Ents", "bai, olu, mine, ESS, ensay", "Bio-Lumen ESS Ents-Ents".
Those beats were voiced on 2026-08-31 with the OLD dictionary-style lexicon
("bye-oh-loo-min-ESS-ence"), which Chatterbox reads as separate words and
letters. PR #99 (2026-09-21) removed that style, but nothing:

  * re-checked hard words that were never probed - `bioluminescence` had no
    proof at all, only an absence;
  * checked each NEW script's hard words before voicing it - a new niche
    (Food, materials) brings words nobody has listened to;
  * stopped Shorts from re-using the 2026-08-31 audio verbatim
    (bin/make-shorts.sh cuts audio/<slug>/*.wav, never regenerates it).

What this module does (stdlib only - CI and the render venv can import it):

  hard_words(text)      rule-based scan for long or rare (Greek/Latin) words
  effective_lexicon()   curated synth.LEXICON + respellings learned on the Mac
  prepare(text)         the exact text handed to model.generate()
  job_check(...)        per-job: classify every hard word, probe the unproven
                        ones with the LOADED voice model + local whisper.cpp
                        ($0), learn a respelling from respell_candidates() when
                        the raw word is mangled, and write the per-job log
                        audio/<slug>/pronunciation.json
  stale_legacy_beat()   a beat voiced before #99 with an old-style respelling;
                        visuals/shorts.py drops it rather than re-air it

Proof lives in two files, both read by loop/tests/test_pronunciation_layer.py:
  voice/tests/pronunciation_probe.json   committed, human-run probe ("terms" =
                                         curated entries, "raw_ok" = hard words
                                         the model says right with no entry)
  loop/state/pronunciation_learned.json  written by the Mac batch, pushed by
                                         loop/mac_sync.py with the batch state
"""
from __future__ import annotations

import ast
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SYNTH = HERE / "synth.py"
PIN = HERE / "tests" / "pronunciation_probe.json"
LEARNED = ROOT / "loop" / "state" / "pronunciation_learned.json"
LEGACY = HERE / "lexicon_legacy.json"

# Local, free transcription. whisper.cpp from Homebrew; the model is a public
# download from the whisper.cpp HuggingFace repo, cached outside the repo.
WHISPER_CLI = os.environ.get("HWK_WHISPER_CLI") or shutil.which("whisper-cli") \
    or "/opt/homebrew/bin/whisper-cli"
WHISPER_MODEL = Path(os.environ.get("HWK_WHISPER_MODEL") or
                     Path.home() / "Library/Caches/how-we-know/ggml-small.en.bin")
WHISPER_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"

CARRIERS = (
    "Scientists have studied {t} for decades.",
    "The {t} is what the survey measured first.",
)
MATCH_RATIO = 0.9
MAX_PROBES_PER_JOB = 12      # ~2 carriers x ~30 s each: minutes, beside ~1.2 h of narration

# ---------------------------------------------------------------- hard words
# A word is HARD when it is long, or shaped like Greek/Latin scientific
# vocabulary. Ordinary long English words also match; that is fine - the
# probe clears them once into raw_ok and they never cost anything again.
_TOKEN = re.compile(r"[A-Za-zÀ-ÿĀ-ž]+(?:'[a-z]+)?")
_GRECO = re.compile(
    r"(ph|chl|chr|rh|ps[aeiouy]|pt[aeiouy]|[^aeiou]y[^aeiou]|ae|oe|eu[^r]|"
    r"escen|ferin|phore|plankton|pelagic|thermal|synth|zoic|morph|cephal|"
    r"gnath|ichthy|ceae|idae|oid|ium$|ae$|us$|is$)")
# Everyday words the rule would otherwise flag on every script. Short list on
# purpose: anything else is cheap to clear once by probing.
COMMON = frozenset("""
understanding temperature temperatures scientists scientific researchers
everything something different difference information photograph photographs
photographed physical physically especially experience experiences experiment
experiments international environment environmental themselves throughout
approximately communication interesting important particularly independently
measurements measurement description descriptions surprisingly organisms
organism thousands hundreds millions conditions condition themselves
""".split())


def _vowel_groups(w: str) -> int:
    return len(re.findall(r"[aeiouy]+", w.lower()))


def is_hard(word: str) -> bool:
    w = word.lower().split("'")[0]
    if len(w) < 7 or w in COMMON:
        return False
    if re.search(r"[À-ÿĀ-ž]", word):
        return True
    if len(w) >= 13 or _vowel_groups(w) >= 6:
        return True
    if re.search(r"(aill|eau|oux|ieu|eaux|ois$|ier$)", w):
        return True            # French loans: Maillard, gâteau - English rules misread them
    return len(w) >= 9 and bool(_GRECO.search(w))


def hard_words(text: str) -> list[str]:
    """Distinct hard words in `text`, in first-seen order, original casing."""
    seen, out = set(), []
    for m in _TOKEN.finditer(text):
        w = m.group(0).split("'")[0]
        if is_hard(w) and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


# ---------------------------------------------------------------- lexicons
def curated() -> dict[str, str]:
    """synth.LEXICON, read with ast so this module never imports soundfile."""
    tree = ast.parse(SYNTH.read_text(), filename=str(SYNTH))
    for node in ast.walk(tree):
        tgt = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(tgt, ast.Name) and tgt.id == "LEXICON" and node.value is not None:
            return ast.literal_eval(node.value)
    raise AssertionError("voice/synth.py has no LEXICON")


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def learned() -> dict:
    d = _read(LEARNED)
    return {"respell": d.get("respell") or {}, "raw_ok": d.get("raw_ok") or {},
            "unresolved": d.get("unresolved") or {}}


def effective_lexicon() -> dict[str, str]:
    lex = {k: v["respelling"] for k, v in learned()["respell"].items()
           if v.get("ok") is True}
    lex.update(curated())            # a curated entry always wins
    return lex


def known_raw() -> set[str]:
    pin = _read(PIN).get("raw_ok") or {}
    return {k.lower() for k, v in pin.items() if v.get("ok") is True} | \
        {k.lower() for k, v in learned()["raw_ok"].items() if v.get("ok") is True}


def apply(text: str, lex: dict[str, str]) -> str:
    for term in sorted(lex, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(term)}\b", lex[term], text, flags=re.IGNORECASE)
    return text


def prepare(text: str, lex: dict[str, str] | None = None) -> str:
    """The text the voice model is given. Every TTS call site uses this."""
    return apply(text, effective_lexicon() if lex is None else lex)


def classify(words: list[str]) -> dict[str, str]:
    lex = {k.lower() for k in effective_lexicon()}
    cur = {k.lower() for k in curated()}
    raw = known_raw()
    out = {}
    for w in words:
        lw = w.lower()
        out[w] = ("curated" if lw in cur else "learned" if lw in lex
                  else "raw_ok" if lw in raw else "unproven")
    return out


# ---------------------------------------------------------------- respelling
# Respellings follow loop/tests/test_lexicon_respellings.py: lowercase
# pseudo-words, spaces only at a real boundary, no hyphens, no CAPS.
_MORPH = ("bio", "photo", "phyto", "chloro", "zoo", "hydro", "thermo", "chemo",
          "cephalo", "ichthyo", "bathy", "abysso", "meso", "epi", "luci", "cyano",
          "micro", "macro", "proto", "ferro", "electro", "poly", "mono", "hexa",
          "lumin", "plankton", "pelagic", "phore", "phyll", "escence", "escent",
          "ferin", "genesis", "synthesis", "synthetic", "morph", "pod", "pods")
_SOUNDS = ((r"ph", "f"), (r"^ps", "s"), (r"^pt", "t"), (r"chl", "kl"),
           (r"chr", "kr"), (r"ch(?=[aeiou])", "k"), (r"ae", "ee"), (r"oe", "ee"),
           (r"eu", "yoo"), (r"(?<=[^aeiou])y(?=[^aeiou])", "i"), (r"rh", "r"),
           (r"escen", "essen"), (r"yll$", "il"), (r"x", "ks"), (r"aill", "ai y"))


def _split_morphs(w: str) -> list[str]:
    parts, rest = [], w
    while rest:
        for m in sorted(_MORPH, key=len, reverse=True):
            if rest.startswith(m) and len(rest) > len(m) + 2:
                parts.append(m)
                rest = rest[len(m):]
                break
        else:
            parts.append(rest)
            break
    return parts


def _syllable_chunks(w: str, per: int = 2) -> str:
    """Split after every `per` vowel groups, at a consonant: 'fora mini fera'."""
    groups = list(re.finditer(r"[aeiouy]+", w))
    cuts = []
    for k in range(per, len(groups), per):
        end_prev, start_next = groups[k - 1].end(), groups[k].start()
        gap = start_next - end_prev
        cuts.append(end_prev + (gap // 2 if gap > 1 else gap))
    parts, last = [], 0
    for c in cuts:
        parts.append(w[last:c])
        last = c
    parts.append(w[last:])
    return " ".join(p for p in parts if p)


def respell_candidates(term: str) -> list[str]:
    w = term.lower()
    w = re.sub(r"[^a-z]", "", __import__("unicodedata").normalize("NFKD", w))
    sounded = w
    for a, b in _SOUNDS:
        sounded = re.sub(a, b, sounded)
    cands = []
    for c in (" ".join(_split_morphs(w)), " ".join(_split_morphs(sounded)), sounded,
              _syllable_chunks(sounded)):
        if c and c != term.lower() and c not in cands and style_ok(c):
            cands.append(c)
    return cands


def style_ok(respelling: str) -> bool:
    return bool(re.fullmatch(r"[a-z]+(?: [a-z]+)*", respelling))


# ---------------------------------------------------------------- hearing
def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def heard(intended: str, transcript: str, aliases: tuple[str, ...] = ()) -> tuple[bool, float]:
    have = norm(transcript)
    best = 0.0
    for want in [norm(intended)] + [norm(a) for a in aliases]:
        if not want:
            continue
        if want in have:
            return True, 1.0
        n = len(want)
        for width in range(max(1, n - 2), n + 4):
            for i in range(0, max(1, len(have) - width + 1)):
                best = max(best, difflib.SequenceMatcher(None, want, have[i:i + width]).ratio())
    return best >= MATCH_RATIO, best


def whisper_ready(download: bool = True) -> str | None:
    """None when local transcription can run, else why not."""
    if not (WHISPER_CLI and os.path.exists(WHISPER_CLI)):
        return "whisper-cli not installed (brew install whisper-cpp)"
    if not WHISPER_MODEL.exists() and download:
        WHISPER_MODEL.parent.mkdir(parents=True, exist_ok=True)
        tmp = WHISPER_MODEL.with_suffix(".part")
        try:
            urllib.request.urlretrieve(WHISPER_URL, tmp)
            tmp.rename(WHISPER_MODEL)
        except OSError as e:
            return f"could not fetch {WHISPER_URL}: {e}"
    if not WHISPER_MODEL.exists():
        return f"no whisper model at {WHISPER_MODEL}"
    return None


def transcribe_file(wav_path: str) -> str:
    r = subprocess.run([WHISPER_CLI, "-m", str(WHISPER_MODEL), "-f", wav_path,
                        "-nt", "-np", "-l", "en"], capture_output=True, text=True,
                       timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"whisper-cli exited {r.returncode}: {r.stderr[-200:]}")
    return " ".join(r.stdout.split())


def listen(say, term: str, spoken: str) -> dict:
    """Synthesise `spoken` in both carriers with `say(text) -> path.wav` and
    report whether whisper heard `term`."""
    readings = []
    for c in CARRIERS:
        path = say(c.format(t=spoken))
        got = transcribe_file(path)
        ok, ratio = heard(term, got)
        readings.append({"carrier": c.format(t=term), "spoken_text": c.format(t=spoken),
                         "heard": got, "ratio": round(ratio, 3), "ok": ok})
    return {"ok": all(r["ok"] for r in readings), "readings": readings}


def learn(say, term: str) -> dict:
    """Raw first; only a mangled raw reading earns a respelling."""
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    raw = listen(say, term, term)
    if raw["ok"]:
        return {"kind": "raw_ok", "at": now, **raw}
    tried = [{"respelling": term, **raw}]
    for cand in respell_candidates(term):
        r = listen(say, term, cand)
        if r["ok"]:
            return {"kind": "respell", "respelling": cand, "at": now, **r}
        tried.append({"respelling": cand, **r})
    return {"kind": "unresolved", "at": now, "tried": tried}


def save_learned(results: dict[str, dict]) -> None:
    d = learned()
    for term, r in results.items():
        kind = r["kind"]
        for k in ("respell", "raw_ok", "unresolved"):
            d[k].pop(term, None)
        d[kind][term] = {k: v for k, v in r.items() if k != "kind"}
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    LEARNED.write_text(json.dumps({k: dict(sorted(v.items())) for k, v in d.items()},
                                  indent=1, ensure_ascii=False) + "\n")


def job_check(slug: str, texts: list[str], say=None, out_dir: Path | None = None,
              probe: bool = True) -> dict:
    """Classify every hard word of one job, probe the unproven ones when a
    voice is available, and write the per-job log. Returns the log."""
    words: list[str] = []
    for t in texts:
        for w in hard_words(t):
            if w.lower() not in {x.lower() for x in words}:
                words.append(w)
    status = classify(words)
    unproven = [w for w, s in status.items() if s == "unproven"]
    already = {k.lower() for k in learned()["unresolved"]}
    queue = [w for w in unproven if w.lower() not in already][:MAX_PROBES_PER_JOB]
    probed, why_not = {}, None
    if probe and say is not None and queue:
        why_not = whisper_ready()
        if why_not is None:
            for w in queue:
                try:
                    probed[w] = learn(say, w)
                except Exception as e:  # noqa: BLE001 - one word never stops a job
                    probed[w] = {"kind": "unresolved", "error": str(e)[:200],
                                 "at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
            save_learned(probed)
            status = classify(words)
    log = {"slug": slug, "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "hard_words": len(words), "status": status,
           "probed": {w: r["kind"] if "kind" in r else "?" for w, r in probed.items()},
           "learned_respellings": {w: r["respelling"] for w, r in probed.items()
                                   if r.get("kind") == "respell"},
           "still_unproven": [w for w, s in status.items() if s == "unproven"],
           "probe_unavailable": why_not}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pronunciation.json").write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")
    n_un = len(log["still_unproven"])
    print(f"  pronunciation {slug}: {len(words)} hard word(s); probed {len(probed)}; "
          f"learned {len(log['learned_respellings'])} respelling(s); {n_un} unproven"
          + (f" ({', '.join(log['still_unproven'][:6])})" if n_un else "")
          + (f"; PROBE UNAVAILABLE: {why_not}" if why_not else ""), flush=True)
    return log


def model_sayer(model, sf, sr: int, params: dict, seed: int = 1234):
    """A say(text)->wav-path callable over an already-conditioned Chatterbox."""
    import torch  # noqa: PLC0415 - only on the TTS venv
    tmp = Path(tempfile.mkdtemp(prefix="hwk-pron-"))
    n = [0]

    def say(text: str) -> str:
        n[0] += 1
        torch.manual_seed(seed + n[0])
        w = model.generate(text, audio_prompt_path=None, **params)
        p = tmp / f"{n[0]:03d}.wav"
        sf.write(str(p), w.squeeze(0).detach().cpu().numpy(), sr)
        return str(p)
    return say


# ---------------------------------------------------------------- legacy audio
def _legacy() -> dict:
    return _read(LEGACY)


def stale_legacy_beat(narration: str, wav_path: str) -> list[str]:
    """Old-style respellings this beat's wav was voiced with, if any.

    A wav written before the 2026-09-21 lexicon rewrite was voiced through
    voice/lexicon_legacy.json; every term there whose respelling differs from
    what prepare() says today was spoken in a style the model mangles."""
    leg = _legacy()
    try:
        mtime = os.path.getmtime(wav_path)
    except OSError:
        return []
    cut = dt.datetime.fromisoformat(leg["replaced_at"]).timestamp()
    if mtime >= cut:
        return []
    now = effective_lexicon()
    hits = []
    for term, old in (leg.get("lexicon") or {}).items():
        if re.search(rf"\b{re.escape(term)}\b", narration, re.IGNORECASE) \
                and now.get(term) != old:
            hits.append(term)
    return hits
