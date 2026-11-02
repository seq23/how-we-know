"""Stock moving footage (Pixabay, Mixkit; Pexels when it has a key) for the
deep-sea and materials-and-manufacturing episodes.

    python research/imagery_stock_video.py --sources      # each source: usable, or its named stop
    python research/imagery_stock_video.py --phrases SLUG # the subject words an episode is matched on
    python research/imagery_stock_video.py --harvest      # search, licence-check, download, merge
    python research/imagery_stock_video.py --verify       # licence + sha256 of every stock record

THE OWNER'S RULING (2 Nov 2026, spry brain, "Yes, all topics"): moving footage
from Pixabay, Pexels and Mixkit may be used in EVERY domain, not only food, on
the food terms - commercial use with no attribution required, each clip's
licence wording stored and re-checked, still credited on screen. Still photos
inside videos stay PD/CC0. "A clip that doesn't show the subject is worse than
none."

WHAT THIS FILE DOES. The adapters, their licence checks and their rate rules
are research/food_footage.py's (Pixabay's API result says `type: film` and not
AI; Mixkit's item page is re-read for the FREE licence before each download).
This file only decides WHICH episodes need clips, WHAT a clip must show, and
writes the accepted clips into the one footage manifest visuals/footage.py
places from - channel/imagery/video_rights.json, beside the NOAA clips, which
stay and are preferred wherever they match.

THE SUBJECT GATE. An episode's subject words come from its own slug
(`episode_phrases`), with question words and generic ocean words removed, so
"what-does-a-goblin-shark-look-like" asks for "goblin shark" and never for
"shark", and adjectives ("red", "transparent") are never subjects. A clip is
accepted only when its own words say it IS that subject (`phrase_in`: the
head of its first Pixabay tag, or of a noun phrase early in its Mixkit title).
A pig on a beach is not a sea pig; a heavy-metal band is not metal.

THE LICENCE GATE (`stock_licence_ok`) is re-run on every record by
visuals/footage.verify immediately before a render, so a record that requires
attribution or forbids commercial use is REFUSED in any episode, not dropped
quietly. loop/tests/test_stock_footage_all_domains.py proves it on a deep-sea
episode.

TEXT. A stock clip carries no burned-in captions, so its whole length is
recorded as its clean window (the brief of 2 Nov 2026); visuals/footage.py
still pads every cut 0.25 s inside it.

PEXELS has no key, and Pexels paused new API keys on 2026-10-13. It is the
NAMED STOP `PEXELS_KEY_ABSENT`, printed on every run and recorded in the
manifest's `stock_source_stops`; this repo never creates an account. A key
dropped at ~/.config/how-we-know/pexels.key (mode 600) turns it on with no
code change.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMAGERY = ROOT / "channel" / "imagery"
CLIPS = IMAGERY / "clips"
MANIFEST = IMAGERY / "video_rights.json"
SCRIPTS = ROOT / "scripts"
RENDERS = ROOT / "renders"

# The weekly lane finds this file through this declaration (loop/footage_lane.py
# reads it with ast, never imports it). `domains` names every domain it feeds;
# `gate` is the licence function the lane refuses to run without. The Pixabay
# key lives on the Mac (~/.config/how-we-know/pixabay.key), so the Mac's
# nightly batch runs it and the Linux lane verifies its stamp.
HARVESTER = {
    "domain": "deep-sea-ocean-science",
    "domains": ["deep-sea-ocean-science", "materials-and-manufacturing"],
    "gate": "stock_licence_ok",
    "manifest": "channel/imagery/video_rights.json",
    "args": ["--harvest"],
    "scheduled": True,
    "what": "stock video clips (Pixabay, Mixkit; Pexels when keyed) - "
            "commercial use, no attribution required, still credited",
    "requires": ["ffmpeg"],
    "host": "mac-batch",
    "timeout_seconds": 3600,
}
DOMAINS = tuple(HARVESTER["domains"])

STOCK_SOURCES = ("pixabay", "pexels", "mixkit")
MIN_SECONDS = 6.0           # same floor as a NOAA clean window
MAX_PER_EPISODE = 4
MAX_PER_RUN = 20            # downloads per night (Mixkit's terms: no mass download)

# Per source: the licence name, the wording committed under channel/imagery/
# licences/, and the phrases in that wording that grant commercial use with no
# attribution. A record is cleared only when its stored wording still contains
# them. Pexels has no wording committed: until it does, a Pexels record cannot
# pass, which is the right answer while Pexels has no key.
LICENCES = {
    "pixabay": {"licence": "Pixabay Content License",
                "licence_url": "https://pixabay.com/service/license-summary/",
                "licence_text": "licences/pixabay-content-license-summary.txt",
                "grants": ["Use Content without having to attribute the author"]},
    "mixkit": {"licence": "Mixkit Stock Video Free License",
               "licence_url": "https://mixkit.co/license/#videoFree",
               "licence_text": "licences/mixkit-stock-video-free-license.txt",
               "grants": ["Commercial projects", "Attribution is not required"]},
    "pexels": {"licence": "Pexels License",
               "licence_url": "https://www.pexels.com/license/",
               "licence_text": None, "grants": []},
}

# Wording that ends the matter whatever else a record says.
REFUSE_WORDING = re.compile(
    r"attribution (?:is )?required|must (?:give|provide|include) "
    r"(?:credit|attribution)|non-?commercial|not for commercial|editorial use only"
    r"|\bCC[- ]?BY\b|creativecommons\.org/licenses/by|Restricted License",
    re.I)


def stock_licence_ok(rec: dict) -> tuple[bool, str]:
    """(cleared, why) for one stock record. No network, no bytes: the rights
    fields and the committed licence wording only, so a render and CI run it."""
    src = rec.get("source")
    lic = LICENCES.get(src or "")
    if src not in STOCK_SOURCES or not lic:
        return False, f"source {src!r} is not a stock library this channel may use"
    if rec.get("attribution_required") is not False:
        return False, "the licence requires attribution (or the record does not say it does not)"
    if rec.get("commercial_use_permitted") is not True:
        return False, "commercial use is not permitted (or not recorded as permitted)"
    if rec.get("licence") != lic["licence"]:
        return False, f"licence {rec.get('licence')!r} is not {src}'s {lic['licence']!r}"
    if not lic["licence_text"] or rec.get("licence_text") != lic["licence_text"]:
        return False, f"no {src} licence wording is stored for this record"
    path = IMAGERY / lic["licence_text"]
    if not path.exists():
        return False, f"{lic['licence_text']} is not committed"
    wording = path.read_text()
    stored = str(rec.get("licence_wording") or "")
    for g in lic["grants"]:
        if g not in wording:
            return False, f"{lic['licence_text']} no longer says {g!r}"
        if g not in stored:
            return False, f"the clip's stored licence wording lacks {g!r}"
    for text in (stored, str(rec.get("licence_basis") or "")):
        m = REFUSE_WORDING.search(text)
        if m:
            return False, f"licence wording says {m.group(0)!r}"
    return True, f"{lic['licence']}: {'; '.join(lic['grants'])}"


def is_stock(rec: dict) -> bool:
    return rec.get("source") in STOCK_SOURCES or str(rec.get("post_id", "")).split(":")[0] in STOCK_SOURCES


# ------------------------------------------------------------ subject words
STOP = set("""
a an the of in on to for and or vs versus is are was were be been does do did can could should would
what why how when where which who whom whose it its it's this that these those there their they we you
your my our if than then so much many most more very really actually ever just only also
get gets got make makes made making work works working look looks like real know knows known
tell keep keeping happen happens happened live lives living die dies brought reach go goes come
strong stronger strongest good better best big bigger biggest small weird scary scariest creepier
creepy creepers deeper deepest clear hot old new inside about from with at by into out up down
something someone people scientists edible formed form forms surfacing occur occurs dive dives brought
some other not survive pressure designed harden hardened rusting shatter red transparent part recorded
""".split())
# Words that never name a subject on their own and never make a phrase alone:
# a clip of "the sea" does not show a deep-sea episode's subject.
GENERIC = set("""
deep sea seas ocean oceans water underwater fish creature creatures life animal animals depth depths
surface marine thing things
""".split())


def _sing(w: str) -> str:
    w = w.lower()
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_sing(w) for w in re.findall(r"[a-z0-9]+", text.lower())]


def episode_phrases(slug: str) -> list[str]:
    """The subject phrases an episode's footage must show, longest first.

    Runs of content words in the slug; a run of several words yields only its
    sub-phrases of two or more words (a "goblin shark" episode never takes a
    "shark" clip); a phrase made only of GENERIC words is never one."""
    words = re.sub(r"^\d+-", "", slug).split("-")
    runs, cur = [], []
    for w in words:
        if w in STOP or not w:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(_sing(w))
    if cur:
        runs.append(cur)
    out: list[str] = []
    for run in runs:
        lo = 1 if len(run) == 1 else 2
        for n in range(len(run), lo - 1, -1):
            for i in range(len(run) - n + 1):
                p = run[i:i + n]
                if all(x in GENERIC for x in p):
                    continue
                s = " ".join(p)
                if s not in out:
                    out.append(s)
    return sorted(out, key=lambda s: -len(s.split()))


# A sentence-style title (Mixkit) names its subject early, and the subject is
# the HEAD of its noun phrase: followed by nothing, or by one of these.
FOLLOW = set("""
being is are was in on at with of and from under over into through for by while during
""".split())
TITLE_HEAD_WORDS = 5


def phrase_in(phrase: str, text: str) -> bool:
    """True only when the clip IS the phrase, as far as its own words say.

    Tag lists (Pixabay, comma-separated): the FIRST tag must END with the
    phrase - "window glass" is glass; "glass maker" is a person, "diamond
    pigeon" a bird, "red poppy" a flower. Sentence titles (Mixkit): the phrase
    must start within the first TITLE_HEAD_WORDS words and be the head of its
    noun phrase - "molten glass being shaped" yes, "a diamond engagement
    ring" and "multicolor diamond lights" no.

    Measured 2026-11-02 on a full live run under the earlier any-of-three-tags
    rule: 37 clips, among them roses for "red", club dancers for "recorded",
    a dolphin pool for "whale" and a pigeon for "diamond". A clip that does
    not show the subject is worse than none, so this errs toward none."""
    want = phrase.split()
    n = len(want)
    if "," in str(text or ""):
        first = _words(str(text).split(",")[0])
        if n == 1:
            # One word is ambiguous at the end of a tag ("heavy metal" is a
            # rock band, measured 2026-11-02): the first tag must BE it.
            return first == want
        return len(first) >= n and first[-n:] == want
    ws = _words(str(text or ""))
    for i in range(min(TITLE_HEAD_WORDS, len(ws) - n + 1)):
        if ws[i:i + n] == want and (i + n == len(ws) or ws[i + n] in FOLLOW):
            return True
    return False


def domain_of(slug: str) -> str | None:
    p = SCRIPTS / f"{slug}.md"
    if not p.exists():
        return None
    m = re.search(r"^\*\*Domain:\*\*\s*([a-z-]+)", p.read_text(), re.M)
    return m.group(1) if m else None


def targets(all_episodes: bool = False) -> list[str]:
    """Deep-sea and materials episodes not yet rendered (with --all, every one)."""
    out = []
    for p in sorted(SCRIPTS.glob("*.md")):
        if domain_of(p.stem) not in DOMAINS:
            continue
        if not all_episodes and (RENDERS / f"{p.stem}-final.mp4").exists():
            continue
        out.append(p.stem)
    return out


# ---------------------------------------------------------------- sources
def _ff():
    sys.path.insert(0, str(HERE))
    import food_footage as FF                       # noqa: PLC0415
    return FF


def source_status() -> tuple[dict, list[dict]]:
    """({source: 'usable' or why not}, [named stops])."""
    FF = _ff()
    status, stops = {}, []
    for name in STOCK_SOURCES:
        ok, why = FF.BY_NAME[name].enabled()
        status[name] = "usable" if ok else why
        if name == "pexels" and not ok and "no key" in why:
            stops.append({
                "code": "PEXELS_KEY_ABSENT",
                "message": "Pexels has no API key and Pexels paused new API keys "
                           "on 2026-10-13; Pixabay and Mixkit carry the stock "
                           "footage meanwhile. This repo never creates an account.",
                "unblock": "When a Pexels key exists, save it to "
                           "~/.config/how-we-know/pexels.key (chmod 600). No code change.",
            })
    return status, stops


def candidates_for(phrase: str, cands: list[dict], FF) -> list[dict]:
    return [c for c in cands if not FF.banned(c) and phrase_in(phrase, c.get("title") or "")]


# ---------------------------------------------------------------- manifest
def load() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"assets": []}


def record(pick: dict, phrase: str, slug: str, meta: dict, blob: bytes, info: dict) -> dict:
    lic = LICENCES[pick["source"]]
    wording = (IMAGERY / lic["licence_text"]).read_text() if lic["licence_text"] else ""
    stored = "\n".join(line for line in wording.splitlines()
                       if any(g in line for g in lic["grants"]))
    who = str(meta.get("source_org") or pick["source"])
    secs = float(info["duration_s"])
    return {
        "post_id": f"{pick['source']}:{pick['id']}",
        "source": pick["source"], "source_id": str(pick["id"]),
        "title": str(pick.get("title") or ""),
        "caption": f"{phrase} - {pick.get('title') or ''}",
        "subject": phrase, "episodes": [slug], "domain": domain_of(slug),
        "source_org": who, "item_url": pick.get("item_url"),
        "direct_url": meta["download_url"], "local_file": f"clips/{pick['_fname']}",
        "width": info["width"], "height": info["height"], "seconds": secs,
        # A stock clip carries no burned-in text: its whole length is clean.
        "clean_windows": [{"start": 0.0, "end": secs}],
        "treatment": "as-shot", "crop": None, "usable_seconds": secs,
        "burned_in_text": [], "probe_count": 0,
        "licence": lic["licence"], "licence_url": lic["licence_url"],
        "licence_text": lic["licence_text"], "licence_wording": stored,
        "licence_basis": meta.get("licence_basis"),
        "rights_basis": f"{lic['licence']}: commercial use, no attribution required "
                        f"(owner ruling 2026-11-02, every domain); credited on screen anyway.",
        "rights_check": meta.get("licence_basis"),
        "attribution_required": False, "commercial_use_permitted": True,
        "ai_generated": False,
        "required_credit": f"FOOTAGE: {who[:30]} / {pick['source'].upper()}",
        "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
    }


def merge(new: list[dict], stops: list[dict], status: dict) -> dict:
    """Write stock records into video_rights.json beside the NOAA records.

    NOAA records and every top-level key are kept exactly. A stock record is
    carried forward only while its file hashes to its sha256 AND it still
    passes stock_licence_ok; anything else is dropped and named."""
    man = load()
    fresh = {r["post_id"] for r in new}
    kept, dropped = [], []
    for a in man.get("assets", []):
        if not is_stock(a):
            kept.append(a)
            continue
        if a["post_id"] in fresh:
            continue
        ok, why = stock_licence_ok(a)
        path = IMAGERY / a.get("local_file", "")
        if not ok:
            dropped.append(f"{a['post_id']}: {why}")
        elif not phrase_in(str(a.get("subject") or ""), a.get("title", "")):
            dropped.append(f"{a['post_id']}: its tags no longer show {a.get('subject')!r} "
                           f"under the subject gate")
        elif not path.exists():
            dropped.append(f"{a['post_id']}: file gone")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != a.get("sha256"):
            dropped.append(f"{a['post_id']}: sha256 drift")
        else:
            kept.append(a)
    man["assets"] = kept + new
    man["accepted_count"] = len(man["assets"])
    man["stock_generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    man["stock_sources"] = status
    man["stock_source_stops"] = stops
    man["stock_dropped"] = dropped
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(man, indent=2))
    return man


def harvest(slugs: list[str] | None = None) -> dict:
    FF = _ff()
    status, stops = source_status()
    for s in stops:
        print(f"NAMED STOP {s['code']}: {s['message']} {s['unblock']}")
    live = [n for n in STOCK_SOURCES if status[n] == "usable"]
    have = [a for a in load().get("assets", []) if is_stock(a)]
    used = {a["post_id"] for a in have}
    eps = slugs if slugs is not None else targets()
    if not live:
        raise SystemExit("RULE 0: no stock source is usable on this host "
                         f"({status}); nothing can be searched")
    if not eps and not have:
        raise SystemExit("RULE 0: no deep-sea or materials episode is waiting "
                         "for a render and no stock clip is on record")
    new, fetched, misses = [], 0, []
    for slug in eps:
        phrases = episode_phrases(slug)
        n_have = sum(1 for a in have + new if a.get("subject") in phrases)
        if n_have >= MAX_PER_EPISODE or not phrases:
            continue
        for phrase in phrases:
            for name in live:
                if n_have >= MAX_PER_EPISODE or fetched >= MAX_PER_RUN:
                    break
                a = FF.BY_NAME[name]
                try:
                    cands = a.search(phrase)
                except Exception as e:                   # noqa: BLE001 - 404 = no category
                    print(f"  {name} {phrase!r}: search failed ({str(e)[:80]})")
                    continue
                for c in candidates_for(phrase, cands, FF):
                    uid = f"{name}:{c['id']}"
                    if uid in used or n_have >= MAX_PER_EPISODE or fetched >= MAX_PER_RUN:
                        continue
                    if c.get("duration") and float(c["duration"]) < MIN_SECONDS:
                        continue
                    try:
                        meta, blob = a.download(c)
                    except Exception as e:               # noqa: BLE001 - licence or file refused
                        print(f"  refused {uid}: {str(e)[:100]}")
                        continue
                    stem = re.sub(r"[^a-z0-9]+", "-", str(c.get("title") or "").lower()).strip("-")[:40]
                    c = {**c, "source": name,
                         "_fname": f"stock__{name}-{re.sub(r'[^A-Za-z0-9]+', '-', str(c['id']))}__{stem}.mp4"}
                    CLIPS.mkdir(parents=True, exist_ok=True)
                    path = CLIPS / c["_fname"]
                    path.write_bytes(blob)
                    info = FF.probe(path)
                    if info["duration_s"] < MIN_SECONDS or info["width"] < 1280:
                        path.unlink()
                        continue
                    rec = record(c, phrase, slug, meta, blob, info)
                    ok, why = stock_licence_ok(rec)
                    if not ok:
                        path.unlink()
                        print(f"  refused {uid}: {why}")
                        continue
                    new.append(rec)
                    used.add(uid)
                    fetched += 1
                    n_have += 1
                    print(f"  CLIP {slug[:44]:<44} {phrase!r:<24} {uid}")
        if not any(a.get("subject") in phrases for a in have + new):
            misses.append(slug)
    man = merge(new, stops, status)
    stock = [a for a in man["assets"] if is_stock(a)]
    print(f"stock footage: {len(new)} new clip(s), {len(stock)} on record, "
          f"{len(misses)} episode(s) with no clip that shows the subject "
          f"(drawn / NOAA treatment stands): {', '.join(misses[:12])}")
    for d in man["stock_dropped"]:
        print(f"  DROPPED: {d}")
    return man


def verify() -> int:
    stock = [a for a in load().get("assets", []) if is_stock(a)]
    bad = []
    for a in stock:
        ok, why = stock_licence_ok(a)
        if not ok:
            bad.append(f"{a['post_id']}: {why}")
        p = IMAGERY / a.get("local_file", "")
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != a.get("sha256"):
            bad.append(f"{a['post_id']}: bytes missing or changed")
    if bad:
        raise SystemExit("STOCK FOOTAGE VERIFICATION FAILED:\n  " + "\n  ".join(bad))
    print(f"verified {len(stock)} stock clip(s): licence wording re-checked, sha256 matches")
    return len(stock)


def main(argv: list[str]) -> int:
    if "--sources" in argv:
        status, stops = source_status()
        print(json.dumps({"sources": status, "named_stops": stops}, indent=1))
        return 0
    if "--phrases" in argv:
        for s in argv[argv.index("--phrases") + 1:]:
            print(f"{s}: {episode_phrases(s)}")
        return 0
    if "--verify" in argv:
        verify()
        return 0
    if "--harvest" in argv:
        eps = argv[argv.index("--episode") + 1].split(",") if "--episode" in argv else None
        harvest(eps)
        verify()
        return 0
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
