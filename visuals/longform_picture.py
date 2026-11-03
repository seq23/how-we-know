"""The long-form picture: ONLY moving imagery of the subject named in the title.

Owner ruling, 2026-11-03, after watching "Why are deep-sea creatures so big?"
(10 of 12 sampled frames were particle filler, text cards and diagrams): "it
should just be a video with moving imagery of large deep-sea creatures and
thats it nothing else". Then: "cant u just make images move as long as u
want?!" - an episode is never held for a footage shortfall.

So the long-form picture is a list of SHOTS, built here from the episode's
subject pool, and nothing else reaches the screen. In fill order:

  1. Real clips of the subject, at speed, each clean span once.
  2. The same clips again, slowed (0.75x then 0.5x), with a different crop or
     pan each time. A span is on screen at most 3 times; the same clip is never
     shown back to back.
  3. Licence-checked PHOTOGRAPHS of the subject, moving: a slow pan (Ken Burns),
     8-15 s each.

Never: text cards, diagrams, title or chapter cards, particle or abstract
filler, engravings or plates, burned-in captions or burned-in credits
(captions go to YouTube as a soft track - loop/captions_lane.py; credits go in
the description - loop/upload.py:footage_credits). `check()` refuses any shot
that is not footage or a photograph of the subject.

The one stop: zero footage AND zero photos of the subject (NAMED STOP
NO_SUBJECT_PICTURE). The narration stays exactly as it is.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
IMAGERY_DIR = os.path.join(ROOT, "channel", "imagery")
sys.path.insert(0, HERE)
from design import W, H, FPS  # noqa: E402
import disk_guard  # noqa: E402

KINDS = ("footage", "photo")
SHOT_S = 8.0               # one footage shot at speed
MIN_SHOT_S = 2.0
SLOW = (0.75, 0.5)         # speeds for the 2nd and 3rd showing of a span
MAX_SHOWINGS = 1 + len(SLOW)
PHOTO_S = (8.0, 15.0)
PHOTO_TARGET_S = 12.0
SAFETY_PAD = 0.25          # same margin footage.py keeps inside a clean window
# Still treatments that are not photographs (engravings, plates, charts, old
# archive prints, drawn cards). Never on screen in a long-form video.
NOT_A_PHOTO = {"plate", "chart", "archive", "drawn", "card", "illustration"}
# Per showing, a different framing: (zoom, pan from x, pan to x).
FRAMINGS = [(1.0, 0.5, 0.5), (1.12, 0.15, 0.85), (1.18, 0.85, 0.15),
            (1.1, 0.5, 0.5)]


class NoSubjectPicture(RuntimeError):
    """NAMED STOP NO_SUBJECT_PICTURE: no footage and no photo of the subject."""
    code = "NO_SUBJECT_PICTURE"


class NotSubjectPicture(ValueError):
    """A shot that is not moving imagery of the subject reached the plan."""


# ------------------------------------------------------------------ the pools

def subject_pattern(slug: str) -> str | None:
    """What the picture must show: the episode's SHOT LIST (visuals/shot_list.py,
    picture first), else its hand-written NOAA pattern, else its stock phrases.
    A subject no honest footage exists for (footage.UNILLUSTRATABLE: giant and
    colossal squid ...) is left out: anything matching it is a lookalike."""
    sys.path.insert(0, os.path.join(ROOT, "research"))
    import shot_list as SL               # noqa: PLC0415
    import footage as FT                 # noqa: PLC0415
    subs = [x for x in SL.subjects(slug)
            if x.replace(" ", "_") not in FT.UNILLUSTRATABLE]
    if subs:
        return "|".join(r"\b" + re.escape(x).replace(r"\ ", r"[\s-]+") + r"s?\b"
                        for x in subs)
    import imagery_video as IV          # noqa: PLC0415
    import imagery_stock_video as STOCK  # noqa: PLC0415
    if IV.SUBJECTS.get(slug):
        return IV.SUBJECTS[slug]
    phrases = STOCK.episode_phrases(slug)
    return "|".join(re.escape(p) for p in phrases) if phrases else None


def _lead(text: str) -> str:
    """The first sentence: what a clip or photo is OF, not what it mentions."""
    return re.split(r"(?<=[.!?])\s", str(text or "").strip(), maxsplit=1)[0]


def subject_clips(slug: str, assets: list[dict] | None = None) -> list[dict]:
    """Rights-verified clips that SHOW the subject: NOAA clips whose title or
    lead sentence names it (not a caption that mentions it in passing), then
    licence-checked stock clips harvested for the subject's own phrases."""
    import footage as FT                 # noqa: PLC0415
    assets = FT.usable_assets() if assets is None else assets
    pat = subject_pattern(slug)
    pool = []
    if pat:
        pool = [a for a in assets if not FT.STOCK.is_stock(a) and re.search(
            pat, f"{a.get('title', '')} {_lead(a.get('caption'))}", re.I)]
    pool += FT.stock_pool(slug, assets)
    return [a for a in pool if FT.windows(a)]


def _still_manifests() -> list[dict]:
    out = []
    for name in ("rights.json", "species.json", "materials.json"):
        p = os.path.join(IMAGERY_DIR, name)
        if os.path.exists(p):
            out += json.load(open(p)).get("assets") or []
    return out


def subject_photos(slug: str, stills: list[dict] | None = None) -> list[dict]:
    """Rights-cleared PHOTOGRAPHS whose title names the subject. Engravings,
    plates, charts and drawn cards are refused, whatever they show."""
    pat = subject_pattern(slug)
    if not pat:
        return []
    stills = _still_manifests() if stills is None else stills
    out, seen = [], set()
    for s in stills:
        if str(s.get("treatment") or "photo") in NOT_A_PHOTO:
            continue
        if s.get("commercial_use_permitted") not in (True, "True", "true"):
            continue
        rel = s.get("local_file") or ""
        if not rel or rel in seen:
            continue
        if not re.search(pat, f"{s.get('title', '')} {s.get('subject', '')}".replace("_", " "), re.I):
            continue
        seen.add(rel)
        out.append(s)
    return out


# ------------------------------------------------------------------- the plan

def _spans(asset: dict) -> list[tuple[float, float]]:
    import footage as FT                 # noqa: PLC0415
    out = []
    for w in FT.windows(asset):
        lo, hi = float(w["start"]) + SAFETY_PAD, float(w["end"]) - SAFETY_PAD
        t = lo
        while hi - t >= MIN_SHOT_S:
            e = min(t + SHOT_S, hi)
            if hi - e < MIN_SHOT_S:      # fold a scrap into this span
                e = hi
            out.append((round(t, 3), round(e, 3)))
            t = e
    return out


def _key(a: dict) -> str:
    return str(a.get("post_id") or a.get("local_file"))


def _credit(a: dict) -> str:
    return str(a.get("required_credit") or a.get("credit_line")
               or a.get("source_org") or "")


# VARIETY (owner 2026-11-03: "We need like a new image every 30 sec at least
# or 20"). A new distinct shot at least every NEW_SHOT_EVERY s (distinct = a
# different clip, or the same clip more than DISTINCT_GAP_S apart in the
# source); a source moment repeats only after REUSE_GAP_S of screen time; no
# subject over SHARE_CAP of screen time while another subject has material.
NEW_SHOT_EVERY = 20.0
MAX_SHOT_S = 18.0          # under NEW_SHOT_EVERY, so no 20 s sample sees one shot twice
DISTINCT_GAP_S = 10.0
REUSE_GAP_S = 180.0
SHARE_CAP = 0.25
SHARE_TOLERANCE = 0.03     # "about 25%": the check fails above 28%


# One animal, one subject: size words and synonyms do not make a second one
# (owner 2026-11-03: "grenadier = one"; splitting it gamed the share cap).
SIZE_WORDS = {"giant", "great", "big", "colossal", "large", "huge", "japanese"}
ALIASES = {"sleeper shark": "greenland shark", "somniosus": "greenland shark",
           "bathynomus": "isopod", "albatrossia": "grenadier", "tubeworm": "tube worm",
           "riftia": "tube worm", "pycnogonid": "sea spider", "scotoplanes": "sea pig",
           "flapjack octopus": "dumbo octopus", "grimpoteuthis": "dumbo octopus",
           "architeuthis": "squid", "regalecus": "oarfish", "haliphron": "seven-arm octopus"}


def animal(phrase: str) -> str:
    """The common animal a subject phrase names: 'great grenadier' and 'giant
    grenadier' are one grenadier."""
    p = re.sub(r"[^a-z0-9 \-']", "", str(phrase or "").lower()).strip()
    p = ALIASES.get(p, p)
    words = [w for w in p.split() if w not in SIZE_WORDS] or p.split()
    p = " ".join(words)
    p = ALIASES.get(p, p)
    return re.sub(r"s$", "", p) if not p.endswith("ss") else p


SUBJECTS_PER_10_MIN = 8


def floors(total_s: float) -> tuple[int, int]:
    """(distinct subjects, distinct source moments) a picture of this length
    needs: 8 subjects per 10 minutes, one new moment per 20 s."""
    import math                                         # noqa: PLC0415
    return (max(1, math.ceil(SUBJECTS_PER_10_MIN * total_s / 600.0 - 1e-9)),
            max(1, math.ceil(total_s / NEW_SHOT_EVERY - 1e-9)))


def tag_subjects(slug: str, assets: list[dict]) -> list[dict]:
    """Stamp each clip or photo with the shot-list subject it shows (`_subject`),
    the unit the share cap is counted in."""
    import shot_list as SL                              # noqa: PLC0415
    subs = SL.subjects(slug)
    for a in assets:
        blob = f"{a.get('title', '')} {_lead(a.get('caption'))} {a.get('subject') or ''}"
        hit = next((x for x in sorted(subs, key=len, reverse=True)
                    if re.search(r"\b" + re.escape(x).replace(r"\ ", r"[\s-]+") + r"s?\b",
                                 blob, re.I)), None)
        a["_subject"] = animal(hit or str(a.get("subject") or a.get("title") or "subject"))
    return assets


def _subject(a: dict) -> str:
    return str(a.get("_subject") or a.get("subject") or _key(a))


def _candidates(clips, photos, allowed):
    """Every shot that may be used, in fill order: clip spans at speed, the
    same spans slowed (0.75x, 0.5x), then moving photographs (up to 3 each)."""
    spans = [(a, sp) for a in clips for sp in _spans(a)
             if allowed is None or (_key(a), sp[0]) in allowed]
    out = []
    for showing in range(MAX_SHOWINGS):
        speed = 1.0 if showing == 0 else SLOW[showing - 1]
        for a, (s, e) in spans:
            out.append({"kind": "footage", "key": _key(a), "asset": a, "title": a.get("title"),
                        "credit": _credit(a), "subject": _subject(a), "start": s,
                        "span": round(e - s, 3), "speed": speed, "showing": showing + 1,
                        "seconds": round(min((e - s) / speed, MAX_SHOT_S), 3)})
    for showing in range(MAX_SHOWINGS):
        for p in photos:
            out.append({"kind": "photo", "key": _key(p), "asset": p, "title": p.get("title"),
                        "credit": _credit(p), "subject": _subject(p), "start": 0.0,
                        "span": 0.0, "speed": 1.0, "showing": showing + 1,
                        "seconds": PHOTO_TARGET_S})
    return out


def build(total_s: float, clips: list[dict], photos: list[dict],
          allowed: set | None = None) -> list[dict]:
    """Shots covering exactly `total_s` seconds. Deterministic.

    WHICH shots: fill order (footage, slowed reuse, photos), round-robin across
    subjects, no subject past SHARE_CAP while another still has material.
    WHERE they go: order() - a new distinct shot every <=20 s, no source moment
    again inside 3 minutes. `allowed` (from vet()) limits footage to spans a
    vision check has seen the subject in."""
    if not clips and not photos:
        raise NoSubjectPicture(
            "NO_SUBJECT_PICTURE: no rights-cleared footage and no photograph of "
            "this episode's subject; the footage lane widens the harvest "
            "(research/imagery_stock_video.py, research/imagery.py) and the "
            "next batch renders it.")
    cands = _candidates(clips, photos, allowed)
    if not cands:
        raise NoSubjectPicture("NO_SUBJECT_PICTURE: the subject's clips carry no "
                               "usable span and there is no photograph")
    cap = SHARE_CAP * total_s
    chosen, used, per = [], set(), {}
    left = float(total_s)

    def take(enforce_cap: bool) -> None:
        nonlocal left
        while left > 1e-6:
            # The next tier still holding any candidate, then round-robin by
            # the subject with the least screen time so far.
            pick = None
            for tier in sorted({(c["kind"] == "photo", c["showing"]) for c in cands}):
                pool = [i for i, c in enumerate(cands) if i not in used
                        and (c["kind"] == "photo", c["showing"]) == tier
                        and (not enforce_cap or per.get(c["subject"], 0) + min(c["seconds"], left)
                             <= cap + 1e-6)]
                if pool:
                    pick = min(pool, key=lambda i: (per.get(cands[i]["subject"], 0), i))
                    break
            if pick is None:
                return
            used.add(pick)
            c = dict(cands[pick])
            secs = min(c["seconds"], left)
            if 0 < left - secs < MIN_SHOT_S:     # never leave a sliver
                secs = max(MIN_SHOT_S, secs - MIN_SHOT_S)
            c["seconds"] = round(secs, 6)
            c["src_seconds"] = round(secs * c["speed"], 3)
            chosen.append(c)
            per[c["subject"]] = per.get(c["subject"], 0) + secs
            left = round(left - secs, 6)

    take(enforce_cap=len({c["subject"] for c in cands}) > 1)
    waived = sorted(s for s, v in per.items() if v > cap + 1e-6)
    if left > 1e-6:                        # nothing else is left: the cap gives way
        before = dict(per)
        take(enforce_cap=False)
        waived = sorted(s for s, v in per.items() if v > cap + 1e-6 and v > before.get(s, 0))
    k = 0
    while left > 1e-6:                     # every candidate used: round again, slowest
        c = dict(cands[k % len(cands)])
        if c["kind"] == "footage":
            c["speed"] = SLOW[-1]
        secs = round(min(left, MAX_SHOT_S, (c["span"] / c["speed"]) if c["span"] else PHOTO_TARGET_S), 6)
        c.update(seconds=secs, src_seconds=round(secs * c["speed"], 3),
                 showing=MAX_SHOWINGS + 1 + k // len(cands), over_cap=True)
        chosen.append(c)
        left = round(left - secs, 6)
        k += 1
    shots = _polish(order(chosen))
    for i, sh in enumerate(shots):
        z, x0, x1 = FRAMINGS[0] if sh["showing"] == 1 and sh["kind"] == "footage" \
            else FRAMINGS[1 + (i + sh["showing"]) % (len(FRAMINGS) - 1)]
        sh.update(zoom=max(z, 1.15) if sh["kind"] == "photo" else z,
                  pan=[x0, x1] if i % 2 == 0 else [x1, x0])
        sh["share_cap_waived"] = waived
    check(shots, total_s)
    return shots


def _distinct(a: dict, b: dict) -> bool:
    """Different clip, or the same clip more than DISTINCT_GAP_S apart."""
    return a["key"] != b["key"] or abs(float(a["start"]) - float(b["start"])) > DISTINCT_GAP_S


def order(shots: list[dict]) -> list[dict]:
    """Screen order. Greedy in time: the next shot is distinct from the last,
    does not repeat a source moment shown in the last REUSE_GAP_S, and comes
    from the subject with the least screen time so far (then the earliest
    fill order). Each constraint gives way only when nothing satisfies it."""
    left = list(shots)
    out: list[dict] = []
    t = 0.0
    last_seen: dict[tuple, float] = {}
    per: dict[str, float] = {}
    while left:
        def ok(c, strict_reuse=True):
            # distinct from everything still on screen in the last 20+ s, so
            # two 20 s samples never land on the same moment of one clip
            back, k = 0.0, len(out) - 1
            while k >= 0 and (back < NEW_SHOT_EVERY + DISTINCT_GAP_S or k == len(out) - 1):
                if not _distinct(out[k], c):
                    return False
                back += float(out[k]["seconds"])
                k -= 1
            if strict_reuse:
                seen = last_seen.get((c["key"], c["start"]))
                if seen is not None and t - seen < REUSE_GAP_S:
                    return False
            return True
        pool = [c for c in left if ok(c)] or [c for c in left if ok(c, False)] or left
        c = min(pool, key=lambda c: (per.get(c["subject"], 0.0), c["showing"]))
        left.remove(c)
        out.append(c)
        t += float(c["seconds"])
        last_seen[(c["key"], c["start"])] = t
        per[c["subject"]] = per.get(c["subject"], 0.0) + float(c["seconds"])
    return _repair(out)


def _polish(shots: list[dict], rounds: int = 300) -> list[dict]:
    """Swap pairs while that lowers what variety_problems() finds (the greedy
    order can still corner itself at the tail). Deterministic."""
    best = len(variety_problems(shots))
    n = len(shots)
    for _ in range(rounds):
        if not best:
            break
        improved = False
        for i in range(n - 1, 0, -1):
            for j in range(n):
                if i == j:
                    continue
                shots[i], shots[j] = shots[j], shots[i]
                got = len(variety_problems(shots))
                if got < best and all(_distinct(shots[k - 1], shots[k]) for k in range(1, n)):
                    best, improved = got, True
                    break
                shots[i], shots[j] = shots[j], shots[i]
            if improved:
                break
        if not improved:
            break
    return shots


def _repair(out: list[dict]) -> list[dict]:
    """The greedy order can corner itself at the tail (the last shots all from
    one clip). Move each such shot to the nearest earlier gap whose neighbours
    it is distinct from."""
    i = 1
    while i < len(out):
        if _distinct(out[i - 1], out[i]):
            i += 1
            continue
        sh = out.pop(i)
        for j in range(len(out) - 1, 0, -1):
            if _distinct(out[j - 1], sh) and _distinct(sh, out[j]):
                out.insert(j, sh)
                break
        else:
            out.insert(i, sh)                   # nowhere better: one clip only
            i += 1
        i = max(1, min(i, len(out) - 1)) if i < len(out) else i
    return out


def check(shots: list[dict], total_s: float | None = None) -> None:
    """Refuse a plan with anything on screen but moving imagery of the subject."""
    if not shots:
        raise NotSubjectPicture("the long-form picture has no shots")
    for i, sh in enumerate(shots):
        kind = sh.get("kind")
        if kind not in KINDS:
            raise NotSubjectPicture(
                f"shot {i} is {kind or sh.get('segment')!r}: a long-form picture "
                f"is only footage or a moving photograph of the subject "
                f"(owner 2026-11-03) - no cards, diagrams, filler or captions")
        a = sh.get("asset") or {}
        if kind == "photo" and str(a.get("treatment") or "photo") in NOT_A_PHOTO:
            raise NotSubjectPicture(f"shot {i} is a {a.get('treatment')}, not a photograph")
        if sh.get("captions") or sh.get("overlay") or sh.get("text"):
            raise NotSubjectPicture(f"shot {i} burns text into the picture")
        if float(sh.get("seconds") or 0) <= 0:
            raise NotSubjectPicture(f"shot {i} has no length")
    if len({s["key"] for s in shots}) > 1:
        for i in range(1, len(shots)):
            if not _distinct(shots[i - 1], shots[i]):
                raise NotSubjectPicture(f"shots {i - 1} and {i} are the same moment of the "
                                        f"same clip back to back")
    if total_s is not None:
        got = sum(float(s["seconds"]) for s in shots)
        if abs(got - total_s) > 0.05:
            raise NotSubjectPicture(f"the shots cover {got:.2f}s of {total_s:.2f}s")


def variety_problems(shots: list[dict], every: float = 20.0) -> list[str]:
    """What the variety rule (owner 2026-11-03) finds wrong with a finished
    picture, read from its shot record ({kind, key, start, speed, subject,
    seconds} in screen order): two consecutive 20 s samples on the same shot or
    the same source moment, a source moment again inside 3 minutes, or a
    subject over its share while the record says another had material."""
    probs: list[str] = []
    edges, t = [], 0.0
    for s in shots:
        edges.append((t, t + float(s["seconds"]), s))
        t += float(s["seconds"])
    total = t

    def at(x):
        for i, (a, b, s) in enumerate(edges):
            if a <= x < b:
                return i, s, x - a
        return len(edges) - 1, edges[-1][2], 0.0
    prev = None
    x = 1.0
    while x < total:
        i, s, off = at(x)
        src = float(s.get("start") or 0) + off * float(s.get("speed") or 1)
        if prev is not None:
            pi, ps, psrc = prev
            if pi == i:
                probs.append(f"{int(x // 60)}:{int(x % 60):02d} same shot as 20 s earlier")
            elif ps["key"] == s["key"] and s["kind"] == "footage" \
                    and abs(psrc - src) <= DISTINCT_GAP_S:
                probs.append(f"{int(x // 60)}:{int(x % 60):02d} same moment of "
                             f"{s.get('title')!r} as 20 s earlier")
        prev = (i, s, src)
        x += every
    seen: dict[tuple, float] = {}
    for a, b, s in edges:
        k = (s["key"], s.get("start"))
        if k in seen and a - seen[k] < REUSE_GAP_S and not s.get("over_cap"):
            probs.append(f"{int(a // 60)}:{int(a % 60):02d} repeats a moment of "
                         f"{s.get('title')!r} after {a - seen[k]:.0f} s (< 3 min)")
        seen[k] = b
    share: dict[str, float] = {}
    for s in shots:
        k = animal(s.get("subject") or s["key"])
        share[k] = share.get(k, 0) + float(s["seconds"])
    need_subjects, need_moments = floors(total)
    moments = {(s["key"], round(float(s.get("start") or 0), 1)) for s in shots}
    if len(share) < need_subjects:
        probs.append(f"only {len(share)} distinct animal(s)/subject(s) on screen; a "
                     f"{total / 60:.1f}-min video needs at least {need_subjects}")
    if len(moments) < need_moments:
        probs.append(f"only {len(moments)} distinct source moment(s); a "
                     f"{total / 60:.1f}-min video needs at least {need_moments}")
    waived = set((shots[0].get("share_cap_waived") or []) if shots else [])
    if len(share) > 1:
        for subj, secs in share.items():
            if secs > (SHARE_CAP + SHARE_TOLERANCE) * total and subj not in waived:
                probs.append(f"{subj!r} holds {secs / total:.0%} of the screen (cap ~25%)")
    return probs


VERDICTS = os.path.join(IMAGERY_DIR, "clips", ".span_verdicts.json")


def vet(clips: list[dict], photos: list[dict], subject: str, judge=None,
        store: str | None = None) -> tuple[set, list[dict]]:
    """Look before placing: one frame from the middle of every clip span, and
    every photo, judged by frame_check's vision reader ("is this real footage
    of <subject>, no text or graphics?"). Returns (allowed spans, photos that
    pass). Verdicts are kept per subject on this Mac, so a span is judged once.
    No vision model answering raises FrameCheckUnavailable (never a pass)."""
    import tempfile                                     # noqa: PLC0415
    import frame_check as FC                            # noqa: PLC0415
    import footage as FT                                # noqa: PLC0415
    judge = judge or FC.gemini_judge
    store = store or VERDICTS
    try:
        kept = json.load(open(store))
    except (OSError, ValueError):
        kept = {}
    mine = kept.setdefault(subject, {})
    work = tempfile.mkdtemp(prefix="hwk-vet-")
    todo = []                                           # (id, jpg)
    try:
        for a in clips:
            for s, e in _spans(a):
                # Three looks per span (near each end and the middle): a span
                # that wanders onto ROV hardware or empty seafloor fails.
                for j, t in enumerate((s + 0.4, (s + e) / 2, e - 0.4)):
                    vid = f"{_key(a)}@{s}#{j}"
                    if vid in mine:
                        continue
                    jpg = os.path.join(work, f"{len(todo):04d}.jpg")
                    subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel",
                                    "error", "-y", "-ss", f"{t:.2f}", "-i", FT.verify(a),
                                    "-frames:v", "1", "-vf", f"{FT.crop_filter(a)}scale=768:-2",
                                    "-q:v", "4", jpg], check=True)
                    todo.append((vid, jpg))
        for p in photos:
            vid = f"photo:{_key(p)}"
            src = os.path.join(IMAGERY_DIR, p.get("local_file") or "")
            if vid in mine or not os.path.exists(src):
                continue
            jpg = os.path.join(work, f"{len(todo):04d}.jpg")
            subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-y", "-i", src, "-frames:v", "1", "-vf", "scale=768:-2",
                            "-q:v", "4", jpg], check=True)
            todo.append((vid, jpg))
        for i in range(0, len(todo), FC.BATCH):
            chunk = todo[i:i + FC.BATCH]
            verdicts = judge([j for _, j in chunk], subject)
            if verdicts is None:
                raise FC.FrameCheckUnavailable(
                    "FRAME_CHECK_UNAVAILABLE: no free vision model answered while "
                    "vetting the clips; the next batch asks again")
            for (vid, _), (ok, why) in zip(chunk, verdicts):
                mine[vid] = {"pass": bool(ok), "why": why}
            os.makedirs(os.path.dirname(store), exist_ok=True)
            json.dump(kept, open(store, "w"), indent=1, sort_keys=True)
    finally:
        import shutil                                   # noqa: PLC0415
        shutil.rmtree(work, ignore_errors=True)
    allowed = {(_key(a), s) for a in clips for s, _ in _spans(a)
               if all((mine.get(f"{_key(a)}@{s}#{j}") or {}).get("pass") for j in range(3))}
    good_photos = [p for p in photos if (mine.get(f"photo:{_key(p)}") or {}).get("pass")]
    return allowed, good_photos


def summarise(shots: list[dict]) -> dict:
    foot = [s for s in shots if s["kind"] == "footage"]
    return {"shots": len(shots), "footage_shots": len(foot),
            "footage_seconds": round(sum(s["seconds"] for s in foot), 1),
            "slowed_shots": sum(1 for s in foot if s["speed"] < 1),
            "photo_shots": sum(1 for s in shots if s["kind"] == "photo"),
            "photo_seconds": round(sum(s["seconds"] for s in shots
                                       if s["kind"] == "photo"), 1),
            "clips": sorted({str(s["title"]) for s in foot}),
            "credits": sorted({s["credit"] for s in shots if s["credit"]})}


# --------------------------------------------------------------------- render

def _pan_crop(seconds: float, x0: float, x1: float) -> str:
    d = max(seconds, 1e-3)
    return (f"crop={W}:{H}:x='(iw-{W})*({x0}+({x1 - x0})*min(t/{d:.3f},1))'"
            f":y='(ih-{H})/2'")


def render_shot(shot: dict, out_clip: str, frames: int) -> str:
    """One shot to a silent clip of exactly `frames` frames. Nothing drawn on it."""
    disk_guard.preflight(os.path.dirname(out_clip))
    a = shot["asset"]
    z = float(shot.get("zoom") or 1.0)
    cw, ch = int(round(W * z / 2) * 2), int(round(H * z / 2) * 2)
    cover = f"scale={cw}:{ch}:force_original_aspect_ratio=increase"
    secs = frames / FPS
    if shot["kind"] == "footage":
        import footage as FT             # noqa: PLC0415
        src = FT.verify(a)               # sha256 + stock licence, every render
        end = shot["start"] + shot["src_seconds"]
        if not FT.inside_window(a, shot["start"], end):
            raise FT.RightsRefusal(f"{a.get('title')!r}: {shot['start']}-{end}s "
                                   f"leaves its clean window")
        speed = float(shot["speed"])
        vf = (f"{FT.crop_filter(a)}setpts=PTS/{speed},fps={FPS},{cover},"
              f"{_pan_crop(secs, *shot['pan'])},setsar=1,format=yuv420p")
        cmd = ["-ss", f"{shot['start']:.3f}", "-i", src]
    else:
        src = os.path.join(IMAGERY_DIR, a["local_file"])
        if not os.path.exists(src):
            raise FileNotFoundError(f"photo missing: {src}")
        vf = (f"{cover},{_pan_crop(secs, *shot['pan'])},setsar=1,format=yuv420p")
        cmd = ["-loop", "1", "-framerate", str(FPS), "-i", src]
    subprocess.run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-y", *cmd, "-an", "-vf", vf, "-r", str(FPS), "-frames:v", str(frames),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", out_clip],
                   check=True)
    got = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-count_packets", "-show_entries", "stream=nb_read_packets",
                          "-of", "default=nw=1:nk=1", out_clip],
                         capture_output=True, text=True).stdout.strip()
    if got != str(frames):
        raise RuntimeError(f"shot {shot.get('title')!r}: {got} frame(s) rendered, "
                           f"{frames} allocated")
    return out_clip


def allocate(shots: list[dict], total_frames: int) -> list[int]:
    """Whole frames per shot, cumulative, summing to exactly `total_frames`."""
    out, emitted, due = [], 0, 0.0
    for i, s in enumerate(shots):
        due += float(s["seconds"])
        want = total_frames if i == len(shots) - 1 else int(round(due * FPS))
        out.append(max(1, want - emitted))
        emitted += out[-1]
    return out


def beat_credits(shots: list[dict], frames: list[int],
                 beat_frames: list[int]) -> dict[int, str | None]:
    """{beat: the credit(s) of every shot on screen during it} - what a Short
    cut from this master credits (visuals/shorts.py reads this record)."""
    edges, t = [], 0
    for s, n in zip(shots, frames):
        edges.append((t, t + n, s["credit"]))
        t += n
    out, t = {}, 0
    for b, n in enumerate(beat_frames):
        lines = []
        for a0, a1, c in edges:
            if a0 < t + n and a1 > t and c and c not in lines:
                lines.append(c)
        out[b] = " / ".join(lines) or None
        t += n
    return out
