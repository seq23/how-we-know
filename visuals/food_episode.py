"""A full food episode: rendered as PIECES and stitched, never in one 30-minute pass.

    .venv/bin/python visuals/food_episode.py plans  SCRIPT OUT_DIR
    <tts python>     voice/food_voice.py OUT_DIR/plan-<piece>.json VOICE_ROOT/<piece> --reference REF.wav
    .venv/bin/python visuals/food_episode.py render SCRIPT VOICE_ROOT WORK_DIR [--pieces open,chocolate]
    .venv/bin/python visuals/food_episode.py stitch SCRIPT VOICE_ROOT WORK_DIR FINAL.mp4
    .venv/bin/python visuals/food_episode.py check  FINAL.mp4        # the episode contract, on the file
    .venv/bin/python visuals/food_episode.py describe SCRIPT         # the description template's record

THE FORMAT (docs/CHANNEL-PLAN.md, "A third domain: food science"; owner,
13 Oct 2026, approving the round-2 chocolate sample: "MUCH better"): one
hooked ~90-second cold open for the whole video, a title card, three ~9-minute
segments each opening by SAYING its question plainly (so the question is in the
captions), the warm funny tail with a next-episode tease; 28-32 minutes. The
script names its sections "<Food>: <heading>" (visuals/food.segment_of).

THE PIECES. Each of open / chocolate / bread / steak / tail is rendered by
visuals/food.render with its own voice directory and must pass the preset's own
contract (food.check: cadence, grade, composites, real-video share, licences,
captions) on its own. The pieces share one encoder setting, so they stitch with
ffmpeg's concat demuxer and NO re-encode; the stitch is refused unless every
piece's video packets reappear byte-identical in the stitched file - the same
proof loop/lengthen.py's splice (#191) uses. Durations come from ffprobe.

THE EPISODE SPEC (channel/specs/<slug>.json) is written from the stitched
render: every piece's shot list, the merged screen time (real video, hands),
per-segment clip counts and sources, clip licences, the one-voice measurement
across the whole episode, the sound measurement per piece, the chapters
(captions/<slug>.chapters.txt, which loop/upload.py reads), the merged .srt, an
attribution read back off the pixels (Apple Vision, the V14 method), and the
not-clipped proof (V13's rule: no piece's picture ends before its narration).
check_episode() is the contract on that spec; loop/backfill.food_hold() runs it
in the upload lane, so a failing food video cannot ship by any path.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "voice"))
import food  # noqa: E402

SPECS = ROOT / "channel" / "specs"
CAPTIONS = ROOT / "captions"
PIECE_ORDER = ("open", *food.SEGMENTS, "tail")
EPISODE_MINUTES = (28.0, 32.0)          # the first-video format; owner, 13 Oct 2026
MIN_CLIPS_PER_SEGMENT = 10
ATTRIBUTION_READ_SHARE_MIN = 0.8
YT_MIN_CHAPTER_S = 10.0


def slug_of(script: Path) -> str:
    m = re.search(r"^\*\*Episode:\*\*\s*(\S+)", script.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else script.stem


# ------------------------------------------------------------------ plans
def plans(script: Path, out: Path) -> dict[str, int]:
    paras = food.parse(script)
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for piece, idx in food.pieces(paras).items():
        plan = [{"text": paras[i]["text"], "register": "standard",
                 "section": paras[i]["section"]} for i in idx]
        (out / f"plan-{piece}.json").write_text(json.dumps(plan, indent=1))
        made[piece] = len(plan)
    return made


# ----------------------------------------------------------------- render
def render_pieces(script: Path, voice_root: Path, work: Path,
                  only: list[str] | None = None) -> dict[str, list[str]]:
    paras = food.parse(script)
    pcs = food.pieces(paras)
    work.mkdir(parents=True, exist_ok=True)
    problems = {}
    for piece in [p for p in PIECE_ORDER if p in pcs]:
        if only and piece not in only:
            continue
        out = work / f"{piece}.mp4"
        print(f"=== piece {piece}: beats {pcs[piece][0]}-{pcs[piece][-1]}", flush=True)
        food.render(script, voice_root / piece, out, pcs[piece])
        problems[piece] = food.check(out)
        print("\n".join(problems[piece]) or f"{piece}: food preset contract holds", flush=True)
    return problems


# ----------------------------------------------------------------- stitch
def ffprobe_s(path: Path, stream: str | None = None) -> float:
    args = ["ffprobe", "-v", "error"]
    if stream:
        args += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        args += ["-show_entries", "format=duration"]
    r = subprocess.run(args + ["-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip().splitlines()[0])


def video_md5s(path: Path) -> list[str]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                        "-map", "0:v:0", "-c", "copy", "-f", "framemd5", "-"],
                       capture_output=True, text=True, check=True)
    return [ln.rsplit(",", 1)[-1].strip() for ln in r.stdout.splitlines()
            if ln and not ln.startswith("#")]


def stitch_files(pieces: list[Path], final: Path) -> dict:
    """Concat without re-encoding; refuse unless every piece is byte-identical inside."""
    with tempfile.TemporaryDirectory() as td:
        lst = Path(td) / "concat.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in pieces))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart",
                        str(final)], check=True)
    whole = video_md5s(final)
    at = 0
    for p in pieces:
        own = video_md5s(p)
        if whole[at:at + len(own)] != own:
            final.unlink(missing_ok=True)
            raise RuntimeError(f"stitch refused: {p.name} is not byte-identical inside "
                               f"{final.name} from packet {at}")
        at += len(own)
    if at != len(whole):
        final.unlink(missing_ok=True)
        raise RuntimeError(f"stitch refused: {len(whole)} packets stitched, {at} in the pieces")
    return {"packets": len(whole), "byte_identical": True}


def combine_voice(measures: list[dict], offsets: list[float]) -> dict:
    """One voice measurement across the whole episode (food_voice.measure's shape)."""
    beats, k = [], 0
    for m, off in zip(measures, offsets):
        for b in m.get("beats") or []:
            beats.append({**b, "index": k, "start_s": round(off + b["start_s"], 2)})
            k += 1
    total = max((b["start_s"] + b["total_s"] for b in beats), default=0.0)
    thirds = []
    for j in range(3):
        lo, hi = total * j / 3, total * (j + 1) / 3
        w = s_ = 0.0
        for b in beats:
            a0, a1 = b["start_s"], b["start_s"] + b["total_s"]
            ov = max(0.0, min(a1, hi) - max(a0, lo))
            if ov > 0:
                w += b["words"] * ov / b["total_s"]
                s_ += ov
        thirds.append(round(w / (s_ / 60.0), 1) if s_ else None)
    f0s = [b["median_f0_hz"] for b in beats if b.get("median_f0_hz")]
    return {"register": sorted({b.get("register", "standard") for b in beats}),
            "beats": beats, "total_s": round(total, 2), "pace_wpm_by_third": thirds,
            "median_f0_hz": round(float(np.median(f0s)), 1) if f0s else None,
            "words": sum(b["words"] for b in beats)}


def _srt_spans(srt_text: str) -> list[tuple[float, float, str]]:
    def secs(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    out = []
    for block in re.split(r"\n\s*\n", srt_text.strip()):
        lines = block.strip().splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            a, b = [x.strip() for x in lines[1].split("-->")]
            out.append((secs(a), secs(b), " ".join(lines[2:])))
    return out


def attribution_read(final: Path, pieces_meta: list[dict], per_piece: int = 4) -> dict:
    """Read the credit line back off the stitched file's pixels (Apple Vision,
    research/imagery_video.ocr - the V14 method) at sampled clip shots."""
    sys.path.insert(0, str(ROOT / "research"))
    try:
        import imagery_video as IV                              # noqa: PLC0415
    except Exception as e:                                      # noqa: BLE001
        return {"examined": 0, "read": 0, "error": f"OCR unavailable: {e}"}
    examined, read, misses = 0, 0, []
    with tempfile.TemporaryDirectory() as td:
        for pm in pieces_meta:
            shots = [s for s in pm["shots"] if s.get("kind") == "picture" and s.get("dur", 0) >= 3]
            pick = shots[:: max(1, len(shots) // per_piece)][:per_piece]
            for s in pick:
                credit = pm["credits"].get(s["asset"]) or ""
                if not credit:
                    continue
                t = pm["start_s"] + s["start"] + min(1.5, s["dur"] / 2)
                png = Path(td) / f"{pm['piece']}-{examined}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(final),
                                "-vf", f"crop=1100:70:{food.W - 1100}:0,scale=2200:140",
                                "-frames:v", "1", "-y", str(png)], check=True, capture_output=True)
                items = IV.ocr([str(png)]).get(str(png), [])
                got = " ".join((x.get("text") if isinstance(x, dict) else str(x)) for x in items).upper()
                want = [w for w in re.findall(r"[A-Z]{4,}", credit.upper())]
                hit = sum(1 for w in want if w in got)
                examined += 1
                if want and hit / len(want) >= 0.5:
                    read += 1
                else:
                    misses.append({"t": round(t, 1), "credit": credit, "read": got[:120]})
    return {"examined": examined, "read": read, "misses": misses[:10]}


def stitch(script: Path, voice_root: Path, work: Path, final: Path) -> dict:
    slug = slug_of(script)
    paras = food.parse(script)
    pcs = food.pieces(paras)
    order = [p for p in PIECE_ORDER if p in pcs]
    files = [work / f"{p}.mp4" for p in order]
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"{f} is not rendered")
    info = stitch_files(files, final)
    pieces_meta, offset, measures, offsets, srt_all = [], 0.0, [], [], []
    for p, f in zip(order, files):
        ps = json.loads(f.with_suffix(".food.json").read_text())
        dur = ffprobe_s(f)
        voice_s = float((ps.get("voice") or {}).get("total_s") or 0.0)
        audio_s = ffprobe_s(f, "a:0")
        video_s = ffprobe_s(f, "v:0")
        first = paras[pcs[p][0]]["text"]
        pieces_meta.append({
            "piece": p, "file": f.name, "start_s": round(offset, 3), "duration_s": round(dur, 3),
            "video_s": round(video_s, 3), "audio_s": round(audio_s, 3), "voice_s": round(voice_s, 3),
            "beats": [pcs[p][0], pcs[p][-1]], "opens_with": first,
            "shots": ps["shots"], "screen_time": ps["screen_time"],
            "composites": ps.get("composites") or [], "credits": ps.get("credits") or {},
            "ai_assets": ps.get("ai_assets") or [], "real_assets": ps.get("real_assets") or [],
            "clip_licences": ps.get("clip_licences") or {}, "sound": ps.get("sound") or {},
            "voice": ps.get("voice") or {}, "captions": ps.get("captions") or {},
            "hands_notes": ps.get("hands_notes") or [], "piece_role": ps.get("piece"),
            "preset_problems": food.check_spec(ps),
        })
        measures.append(ps.get("voice") or {})
        offsets.append(offset)
        srt_p = f.with_suffix(".srt")
        if srt_p.exists():
            srt_all += [(a + offset, b + offset, t) for a, b, t in _srt_spans(srt_p.read_text())]
        offset += dur
    total = ffprobe_s(final)
    all_shots = [{**s, "start": round(pm["start_s"] + s["start"], 3), "piece": pm["piece"]}
                 for pm in pieces_meta for s in pm["shots"]]
    st = food.screen_time({"shots": all_shots})
    chapters = []
    for pm in pieces_meta:
        label = ("Cold open" if pm["piece"] == "open" else
                 "Closing" if pm["piece"] == "tail" else pm["opens_with"])
        chapters.append({"t": round(pm["start_s"], 2), "label": label})
    clips_by_seg = {}
    for pm in pieces_meta:
        if pm["piece"] in food.SEGMENTS:
            used = sorted({s["asset"] for s in pm["shots"] if s["asset"] in pm["clip_licences"]})
            by_src: dict[str, int] = {}
            for k in used:
                src = pm["clip_licences"][k].get("source") or "?"
                by_src[src] = by_src.get(src, 0) + 1
            clips_by_seg[pm["piece"]] = {"count": len(used), "by_source": by_src, "clips": used}
    ai = sorted({a for pm in pieces_meta for a in pm["ai_assets"]})
    out = CAPTIONS / f"{slug}.srt"
    CAPTIONS.mkdir(exist_ok=True)
    out.write_text(food.srt(srt_all))
    (CAPTIONS / f"{slug}.chapters.txt").write_text(
        "".join(f"{_ts(c['t'])} {c['label']}\n" for c in chapters))
    prior_p = SPECS / f"{slug}.json"
    prior = json.loads(prior_p.read_text()) if prior_p.exists() else {}
    spec = {
        **{k: v for k, v in prior.items() if k in ("_why", "slug", "domain", "parts",
                                                    "title_owner", "segments", "altered_content_why",
                                                    "demand_note")},
        "kind": "food-episode", "slug": slug, "domain": "food-science",
        "episode_script": str(script.relative_to(ROOT)) if script.is_relative_to(ROOT) else str(script),
        "preset": food.PRESET["id"], "grade": food.FOOD_GRADE["id"],
        "duration_s": round(total, 3), "render_sha256": _sha256(final),
        "render_bytes": final.stat().st_size, "stitch": info,
        "pieces": pieces_meta, "piece_order": order,
        "screen_time": st, "hands_notes": food.hands_notes({"shots": all_shots}),
        "clips_per_segment": clips_by_seg,
        "ai_assets": ai, "altered_content": bool(ai), "ai_video_clips": 0,
        "captions": {"burned_in": all(pm["captions"].get("burned_in") for pm in pieces_meta),
                     "sidecar": f"captions/{slug}.srt"},
        "chapters": chapters, "chapters_file": f"captions/{slug}.chapters.txt",
        "voice": combine_voice(measures, offsets),
        "attribution_ocr": attribution_read(final, pieces_meta),
    }
    spec["voice_problems"] = __import__("food_voice").check(spec["voice"])
    spec["episode_problems"] = check_episode(spec)
    prior_p.write_text(json.dumps(spec, indent=1) + "\n")
    export_episode_proof(work, order, SPECS / f"{slug}.proof.npz")
    return spec


def _ts(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def export_episode_proof(work: Path, order: list[str], out: Path) -> Path:
    """Proof frames for the whole episode: each piece's own (ungraded, decoded
    final, mask) sample, concatenated - what check_frames re-grades in CI."""
    U, F, M = [], [], []
    for p in order:
        mp4 = work / f"{p}.mp4"
        tmp = mp4.with_suffix(".work") / "proof.npz"
        food.export_proof(mp4, tmp)
        z = np.load(tmp)
        n = len(z["ungraded"])
        keep = list(range(0, n, max(1, math.ceil(n / 6))))
        U += [z["ungraded"][i] for i in keep]
        F += [z["final"][i] for i in keep]
        M += [z["masks"][i] for i in keep]
    np.savez_compressed(out, ungraded=np.stack(U), final=np.stack(F), masks=np.stack(M))
    return out


# --------------------------------------------------------------- describe
def describe(script: Path, chapter_labels: list[str] | None = None, suggest=None) -> dict:
    """The shared description template's record (loop/describe.py, its own
    state file and its own functions) for a food episode, whose script lives in
    scripts/food/ where `describe.py prepare` does not look. 4-8 phrasings,
    each one the script answers (describe.answered), led by each segment's own
    question; chapters named as questions by describe.chapter_questions."""
    sys.path.insert(0, str(ROOT / "loop"))
    import describe as DS                                      # noqa: PLC0415
    import longform_title as LT                                # noqa: PLC0415
    slug = slug_of(script)
    text = script.read_text(encoding="utf-8")
    paras = food.parse(script)
    pcs = food.pieces(paras)
    seg_qs = [paras[pcs[s][0]]["text"] for s in food.SEGMENTS if s in pcs]
    title, why, _src = LT.title_for_upload(slug, text, None)
    if not title:
        raise ValueError(f"no passing title: {why}")
    per = max(1, (DS.MAX_QUESTIONS - len(seg_qs)) // max(1, len(seg_qs)))
    qs: list[str] = []
    for q in seg_qs:
        found = DS.search_questions(q.rstrip("?").lower(), q, suggest=suggest, script=text)
        # answered by the script, and a whole question (an autocomplete stub
        # like "how chocolate melt" is a search string, not a phrasing to show)
        keep = [x for x in found if not DS.answered(x, text) and len(x.split()) >= 4
                and x.split()[0].lower() == q.split()[0].lower()]
        for x in [q] + [x for x in keep if x.lower() != q.lower()][:per]:
            if x.lower() not in {y.lower() for y in qs} and len(qs) < DS.MAX_QUESTIONS:
                qs.append(x)
    if len(qs) < DS.MIN_QUESTIONS:
        raise ValueError(f"only {len(qs)} script-answered phrasings")
    labels = chapter_labels or (["Cold open"] + seg_qs + ["Closing"])
    names = DS.chapter_questions(title, labels) or {}
    doc = DS.load()
    doc["episodes"][slug] = {"questions": qs, "chapter_names": names,
                             "subject": "bread steak chocolate", "title": title,
                             "prepared_at": DS._now(),               # noqa: SLF001
                             "prepared_by": "visuals/food_episode.py describe "
                                            "(scripts/food/, per-segment phrasings)"}
    DS.save(doc)
    return doc["episodes"][slug]


# ------------------------------------------------------------------ check
def check_episode(spec: dict) -> list[str]:
    """The owner's locked food contract on a full episode spec. [] = it ships.
    Notes (hands above 15 %) are in spec["hands_notes"], not here."""
    p: list[str] = []
    if spec.get("kind") != "food-episode":
        return ["not a food-episode spec (visuals/food_episode.py stitch writes one)"]
    pieces = spec.get("pieces") or []
    order = [x["piece"] for x in pieces]
    if not pieces:
        return ["no pieces - an episode spec with nothing in it proves nothing"]
    segs = [x for x in order if x in food.SEGMENTS]
    if order[:1] != ["open"] or order[-1:] != ["tail"] or len(segs) < 1:
        p.append(f"pieces {order}: an episode is the cold open, its segments, then the tail")
    if len(segs) != len(set(segs)):
        p.append(f"a segment appears twice: {order}")
    lo, hi = EPISODE_MINUTES
    mins = float(spec.get("duration_s") or 0) / 60
    if not lo <= mins <= hi:
        p.append(f"episode runs {mins:.1f} min, outside {lo:.0f}-{hi:.0f}")
    for pm in pieces:
        role_spec = {"shots": pm.get("shots") or [], "piece": pm["piece"] if pm["piece"] in
                     ("open", "tail", *food.SEGMENTS) else "sample",
                     "ai_assets": pm.get("ai_assets") or [], "clip_licences": pm.get("clip_licences") or {},
                     "credits": pm.get("credits") or {}, "captions": pm.get("captions") or {},
                     "altered_content": spec.get("altered_content")}
        for x in food.check_spec(role_spec):
            p.append(f"{pm['piece']}: {x}")
        # V13's rule: the picture never ends before the narration it carries
        if pm.get("voice_s") and pm.get("video_s", 0) + 1 / food.FPS < pm["voice_s"] - 0.05:
            p.append(f"{pm['piece']}: picture {pm['video_s']:.2f}s ends before its narration "
                     f"{pm['voice_s']:.2f}s - clipped")
        snd = pm.get("sound") or {}
        sys.path.insert(0, str(HERE))
        import food_sound                                       # noqa: PLC0415
        for x in (food_sound.check(snd) if snd else ["no sound measurement"]):
            p.append(f"{pm['piece']}: sound: {x}")
        if pm["piece"] in food.SEGMENTS:
            q = (pm.get("opens_with") or "").strip()
            if not q.endswith("?") or len(q.split()) > 16:
                p.append(f"{pm['piece']}: does not open by saying its question plainly "
                         f"(first beat {q[:60]!r})")
    for seg, c in (spec.get("clips_per_segment") or {}).items():
        if c.get("count", 0) < MIN_CLIPS_PER_SEGMENT:
            p.append(f"{seg}: {c.get('count')} real clips on screen, fewer than {MIN_CLIPS_PER_SEGMENT}")
    for seg in segs:
        if seg not in (spec.get("clips_per_segment") or {}):
            p.append(f"{seg}: no clip count recorded")
    st = spec.get("screen_time") or {}
    if st.get("real_video_share", 0) < food.REAL_VIDEO_SHARE_MIN:
        p.append(f"real video is {st.get('real_video_share', 0):.0%} of the episode, under "
                 f"{food.REAL_VIDEO_SHARE_MIN:.0%}")
    if st.get("hands_share", 0) > food.HANDS_FAIL_SHARE:
        p.append(f"hands visible on {st['hands_share']:.0%} of the episode, over "
                 f"{food.HANDS_FAIL_SHARE:.0%}")
    if "hands_share" not in st:
        p.append("hands-visible screen time was not measured")
    if spec.get("ai_assets") and not spec.get("altered_content"):
        p.append("AI stills on screen but altered_content is not set")
    if not (spec.get("captions") or {}).get("burned_in"):
        p.append("captions are not on in every piece")
    v = spec.get("voice") or {}
    import food_voice                                           # noqa: PLC0415
    for x in food_voice.check(v):
        p.append(f"voice: {x}")
    ch = spec.get("chapters") or []
    if len(ch) < 3 or ch[0].get("t") != 0:
        p.append("chapters: need >= 3, the first at 0:00")
    for a, b in zip(ch, ch[1:]):
        if b["t"] - a["t"] < YT_MIN_CHAPTER_S:
            p.append(f"chapter {b['label'][:30]!r} is {b['t'] - a['t']:.1f}s after the last; "
                     f"YouTube drops chapter lists with one under {YT_MIN_CHAPTER_S:.0f}s")
    ao = spec.get("attribution_ocr") or {}
    if not ao.get("examined"):
        p.append("attribution was not read back off the pixels (examined zero frames)")
    elif ao.get("read", 0) / ao["examined"] < ATTRIBUTION_READ_SHARE_MIN:
        p.append(f"credit line read back on only {ao['read']}/{ao['examined']} sampled frames")
    if not (spec.get("stitch") or {}).get("byte_identical"):
        p.append("the stitch was not proven byte-identical to its pieces")
    return p


def check_episode_files(spec_p: Path) -> list[str]:
    """check_episode plus the proof frames beside the spec (grade re-applied,
    subject coverage) - what the upload lane runs in CI, where no render is."""
    spec = json.loads(Path(spec_p).read_text())
    p = check_episode(spec)
    proof = Path(spec_p).with_suffix(".proof.npz")
    if not proof.exists():
        return p + [f"no proof frames at {proof.name}"]
    z = np.load(proof)
    _n, fp = food.check_frames(z["ungraded"], z["final"], z["masks"])
    return p + fp


def check(final: Path) -> list[str]:
    slug = final.name.removesuffix("-final.mp4").removesuffix(".mp4")
    spec_p = SPECS / f"{slug}.json"
    if not spec_p.exists():
        return [f"no episode spec at {spec_p}"]
    spec = json.loads(spec_p.read_text())
    p = check_episode_files(spec_p)
    if spec.get("render_sha256") and _sha256(final) != spec["render_sha256"]:
        p.append("the render on disk is not the one the spec was written from")
    got = ffprobe_s(final)
    if abs(got - float(spec.get("duration_s") or 0)) > 0.5:
        p.append(f"ffprobe says {got:.1f}s, the spec {spec.get('duration_s')}s")
    return p


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.split("\n\n")[0])
        return 2
    cmd = argv[0]
    if cmd == "plans":
        print(json.dumps(plans(Path(argv[1]), Path(argv[2]))))
        return 0
    if cmd == "render":
        only = argv[argv.index("--pieces") + 1].split(",") if "--pieces" in argv else None
        probs = render_pieces(Path(argv[1]), Path(argv[2]), Path(argv[3]), only)
        return 1 if any(probs.values()) else 0
    if cmd == "stitch":
        spec = stitch(Path(argv[1]), Path(argv[2]), Path(argv[3]), Path(argv[4]))
        print(json.dumps({k: spec[k] for k in ("duration_s", "screen_time", "clips_per_segment",
                                               "hands_notes", "attribution_ocr")}, indent=1))
        probs = spec["episode_problems"]
        print("\n".join(probs) or "food episode contract holds")
        return 1 if probs else 0
    if cmd == "describe":
        print(json.dumps(describe(Path(argv[1])), indent=1))
        return 0
    if cmd == "check":
        probs = check(Path(argv[1]))
        print("\n".join(probs) or "food episode contract holds")
        return 1 if probs else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
