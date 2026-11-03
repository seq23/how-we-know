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


def _interleave(clips: list[dict], allowed: set | None = None
                ) -> list[tuple[dict, tuple[float, float]]]:
    per = [[(a, s) for s in _spans(a) if allowed is None or (_key(a), s[0]) in allowed]
           for a in clips]
    out, k = [], 0
    while any(per):
        for lst in per:
            if k < len(lst):
                out.append(lst[k])
        k += 1
        if all(k >= len(lst) for lst in per):
            break
    return out


def _key(a: dict) -> str:
    return str(a.get("post_id") or a.get("local_file"))


def _credit(a: dict) -> str:
    return str(a.get("required_credit") or a.get("credit_line")
               or a.get("source_org") or "")


def build(total_s: float, clips: list[dict], photos: list[dict],
          allowed: set | None = None) -> list[dict]:
    """Shots covering exactly `total_s` seconds, footage first. Deterministic.
    `allowed` ({(clip key, span start)}, from vet()) limits footage to spans a
    vision check has seen the subject in."""
    if not clips and not photos:
        raise NoSubjectPicture(
            "NO_SUBJECT_PICTURE: no rights-cleared footage and no photograph of "
            "this episode's subject; the footage lane widens the harvest "
            "(research/imagery_stock_video.py, research/imagery.py) and the "
            "next batch renders it.")
    shots: list[dict] = []
    left = float(total_s)
    spans = _interleave(clips, allowed)

    def fits(a_key: str, first: bool = False) -> bool:
        # At speed, a clip's spans may follow one another (it is one take);
        # a reuse or a photo never follows the same clip.
        return first or not shots or shots[-1]["key"] != a_key

    def add(shot: dict) -> None:
        nonlocal left
        shots.append(shot)
        left = round(left - shot["seconds"], 6)

    def take(want: float, lo: float) -> float:
        """How much of `want` to use, never leaving a tail under `lo`."""
        t = min(want, left)
        if 0 < left - t < lo:
            t = left if left <= want * 1.5 else left - lo
        return round(t, 6)

    # 1 + 2: footage, at speed and then slowed; a span at most MAX_SHOWINGS.
    for showing in range(MAX_SHOWINGS):
        speed = 1.0 if showing == 0 else SLOW[showing - 1]
        queue = list(spans)
        while queue and left > 1e-6:
            i = next((j for j, (a, _) in enumerate(queue)
                      if fits(_key(a), showing == 0 and (not shots or shots[-1]["showing"] == 1))), None)
            if i is None:
                break
            a, (s, e) = queue.pop(i)
            out_max = (e - s) / speed
            secs = take(out_max, MIN_SHOT_S)
            if secs > out_max + 1e-6:              # tail longer than the span
                secs = round(out_max, 6)
            z, x0, x1 = FRAMINGS[1 + (showing + len(shots)) % (len(FRAMINGS) - 1)] \
                if showing else FRAMINGS[0]
            add({"kind": "footage", "key": _key(a), "asset": a,
                 "title": a.get("title"), "credit": _credit(a),
                 "start": s, "src_seconds": round(secs * speed, 3),
                 "speed": speed, "showing": showing + 1, "seconds": secs,
                 "zoom": z, "pan": [x0, x1]})
        if left <= 1e-6:
            break

    # 3: photographs of the subject, moving, 8-15 s each.
    k = 0
    while left > 1e-6 and photos:
        p = photos[k % len(photos)]
        if not fits(_key(p)) and len(photos) > 1:
            k += 1
            p = photos[k % len(photos)]
        z, x0, x1 = FRAMINGS[1 + (k // max(1, len(photos))) % 2]
        secs = take(PHOTO_TARGET_S, PHOTO_S[0])
        if secs > PHOTO_S[1] and left > PHOTO_S[1]:
            secs = PHOTO_S[1]
        add({"kind": "photo", "key": _key(p), "asset": p, "title": p.get("title"),
             "showing": 1 + k // len(photos),
             "credit": _credit(p), "seconds": secs, "zoom": max(z, 1.15),
             "pan": [x0, x1] if k % 2 == 0 else [x1, x0]})
        k += 1

    # No photos and every span shown its three times: the clips go round
    # again, slowest, rather than hold the episode (owner 2026-11-03).
    extra = 0
    while left > 1e-6:
        if not spans:
            raise NoSubjectPicture("NO_SUBJECT_PICTURE: the subject's clips "
                                   "carry no usable clean span")
        a, (s, e) = spans[extra % len(spans)]
        if not fits(_key(a)) and len(spans) > 1:
            extra += 1
            a, (s, e) = spans[extra % len(spans)]
        out_max = (e - s) / SLOW[-1]
        secs = min(take(out_max, MIN_SHOT_S), round(out_max, 6))
        z, x0, x1 = FRAMINGS[1 + extra % (len(FRAMINGS) - 1)]
        add({"kind": "footage", "key": _key(a), "asset": a, "title": a.get("title"),
             "credit": _credit(a), "start": s, "src_seconds": round(secs * SLOW[-1], 3),
             "speed": SLOW[-1], "showing": MAX_SHOWINGS + 1 + extra // len(spans),
             "seconds": secs, "zoom": z, "pan": [x0, x1], "over_cap": True})
        extra += 1
    shots = spread(shots)
    check(shots, total_s)
    return shots


def spread(shots: list[dict]) -> list[dict]:
    """Re-order for variety: the fill order decides WHICH shots are used (clips,
    then slowed reuse, then photos); the screen order deals them out so one
    long clip never fills a whole stretch. Greedy: the asset with the most
    shots left goes next, never the same asset twice running; each asset's
    shots keep their own order (a span at speed before its slowed reuse)."""
    from collections import OrderedDict
    queues: "OrderedDict[str, list[dict]]" = OrderedDict()
    for sh in shots:
        queues.setdefault(sh["key"], []).append(sh)
    out: list[dict] = []
    last = None
    while queues:
        keys = sorted(queues, key=lambda k: -len(queues[k]))
        k = next((k for k in keys if k != last), keys[0])
        out.append(queues[k].pop(0))
        if not queues[k]:
            del queues[k]
        last = k
    # the last shot carries the remainder; lengths are unchanged, only order
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
    for i in range(1, len(shots)):
        reuse = shots[i].get("showing", 1) > 1 or shots[i - 1].get("showing", 1) > 1 \
            or shots[i]["kind"] == "photo"
        if reuse and shots[i]["key"] == shots[i - 1]["key"] and len({s["key"] for s in shots}) > 1:
            raise NotSubjectPicture(f"shots {i - 1} and {i} show the same clip back to back")
    if total_s is not None:
        got = sum(float(s["seconds"]) for s in shots)
        if abs(got - total_s) > 0.05:
            raise NotSubjectPicture(f"the shots cover {got:.2f}s of {total_s:.2f}s")


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
