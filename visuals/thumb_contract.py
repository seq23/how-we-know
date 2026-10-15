"""The long-form thumbnail CONTRACT, as code: three variants, one grade, variant A ships.

    python visuals/thumb_contract.py <slug> [<slug> ...]     build variants
    python visuals/thumb_contract.py --verify <slug> [...]   re-check what is on disk
    python visuals/thumb_contract.py --chosen <slug>         print variant A's path

Owner decision, 12-13 Oct 2026 (repackage job 1 of 3). LONG-FORM ONLY: Shorts
thumbnails are not touched by this module.

THE CONTRACT, every line of it checked by verify() on the real output:

  1. ONE BIG SUBJECT. A rights-verified photograph of the episode's own subject
     (a creature, an object, a process), cropped so the subject box measured by
     visuals/thumbs.py:subject_box() spans at least SUBJECT_FILL_MIN (60%) of
     the frame on its larger side, and the frame carries real subject energy
     (thumbs.MIN_SUBJECT_ENERGY of pixels at thumbs.SUBJECT_LEVEL saliency) -
     a crop of empty water does not pass by being large.
  2. HIGH CONTRAST, AT MOST THREE WORDS. Heavy white type with a black stroke,
     MAX_WORDS = 3, taken from the episode's long-form title (which
     loop/longform_title.py has already traced to the script) - a figure
     phrase first, then a contradiction/stake phrase, then the subject.
  3. ONE CONSTANT GRADE. GRADE below is the only colour treatment: a split tone
     of the channel's deep navy shadows and warm highlights, mixed with the
     photograph's own colour so a red shrimp stays red. Every long-form
     thumbnail carries it, so the channel is recognisable in a feed. verify()
     re-grades the recorded crop of the recorded source and compares it with
     the published pixels outside the text, so "grade applied" is measured,
     not asserted.
  4. THREE VARIANTS, ONE CHOOSER. A = the tightest subject crop with the
     primary text; B = a different crop (subject offset, the type beside it);
     C = A's crop with the alternative text (or a second image when the title
     yields one phrase only). Written to
         channel/thumbnails/variants/<slug>/{A,B,C}.jpg + contract.json
     chooser() names A for thumbnails.set; visuals/thumbs_for.py copies A to
     channel/thumbnails/<slug>.jpg, the path both upload lanes already attach.

IMAGERY. Only the two manifests this repo already rights-checks:
channel/imagery/rights.json (NOAA Ocean Exploration / public-domain plates) and
channel/imagery/materials.json (public domain / CC0, verified at the Commons
item page). The subject comes from the episode itself - the species_image /
material_image beats its own plan draws, then the deep-sea slot its slug and
hook name (visuals/thumbs_for.deep_sea_slot_for), then the hand-written
materials SPECS. Every file is re-hashed against the manifest's sha256 before a
pixel is used. The required credit is drawn small in the corner: it is
attribution, not headline text, and it is never dropped (CLAUDE.md). No
subject found = ContractRefused, named; nothing is borrowed and nothing paid.

Guarded by validator V48 (loop/validate.py) and
loop/tests/test_thumb_contract.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import numpy as np                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont                 # noqa: E402

IMAGERY = os.path.join(ROOT, "channel", "imagery")
RIGHTS = os.path.join(IMAGERY, "rights.json")
MATERIALS = os.path.join(IMAGERY, "materials.json")
SCRIPTS = os.path.join(ROOT, "scripts")
VARIANTS_DIR = os.path.join(ROOT, "channel", "thumbnails", "variants")

TW, TH = 1280, 720
MAX_WORDS = 4      # thumbnail words only (owner, 14 Oct 2026: a title echo); titles keep their own gate
SUBJECT_FILL_MIN = 0.60
VARIANT_NAMES = ("A", "B", "C")
CHOSEN = "A"
MIN_CROP_W = 480                      # never upscale a postage stamp past ~2.7x
GRADE_TOLERANCE = 9.0                 # mean |diff| per channel, JPEG q92 noise ~2-4

# THE ONE GRADE. Change it and every contract.json on disk fails verify() until
# rebuilt - which is the point: one look across the whole feed.
GRADE = {
    "id": "hwk-split-navy-amber-v1",
    "shadow": (8, 22, 40),
    "highlight": (255, 222, 168),
    "mix": 0.55,
    "contrast": 1.18,
}

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
_CREDIT_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

STOP = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
        "is", "are", "was", "were", "be", "it", "its", "that", "this", "with",
        "from", "by", "as", "into", "than", "so", "where", "when", "what",
        "why", "how", "which", "who", "has", "have", "had", "can", "do",
        "does", "did"}


class ContractRefused(Exception):
    """No rights-verified image of the episode's subject can meet the contract."""


def _font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ------------------------------------------------------------------ the grade
def grade(im: Image.Image, spec: dict | None = None) -> Image.Image:
    g = spec or GRADE
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    k = g["contrast"]
    curve = np.clip((lum - 0.5) * k + 0.5, 0, 1)[..., None]
    sh = np.array(g["shadow"], np.float32) / 255.0
    hi = np.array(g["highlight"], np.float32) / 255.0
    duo = sh * (1 - curve) + hi * curve
    own = np.clip((a - 0.5) * k + 0.5, 0, 1)
    out = g["mix"] * duo + (1 - g["mix"]) * own
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


# --------------------------------------------------------------- measurement
def _thumbs():
    import thumbs                                          # noqa: PLC0415
    return thumbs


def measure_fill(im: Image.Image) -> tuple[float, float]:
    """(fill, energy). fill = the subject box's larger side as a share of the
    frame; energy = share of pixels at thumbs.SUBJECT_LEVEL saliency."""
    T = _thumbs()
    x0, y0, x1, y1 = T.subject_box(im, keep=0.80)
    fill = max(x1 - x0, y1 - y0)
    energy = float((T.saliency_abs(im) >= T.SUBJECT_LEVEL).mean())
    return round(float(fill), 4), round(energy, 4)


# -------------------------------------------------------------------- imagery
def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _deep_records() -> list[dict]:
    if not os.path.exists(RIGHTS):
        return []
    return [a for a in json.load(open(RIGHTS))["assets"]
            if a.get("thumbnail_ok", True)]


def _mat_records() -> list[dict]:
    if not os.path.exists(MATERIALS):
        return []
    return list(json.load(open(MATERIALS)).get("index") or [])


def _record(rec: dict, manifest: str, subject: str) -> dict:
    credit = (rec.get("thumb_credit") or rec.get("required_credit")
              or rec.get("credit_line") or "")
    if " — " in credit and not rec.get("thumb_credit"):
        credit = credit.split(" — ")[-1]
    return {"path": os.path.join(IMAGERY, rec["local_file"]),
            "local_file": rec["local_file"], "sha256": rec.get("sha256"),
            "credit": credit.strip(), "crop": rec.get("crop"),
            "subject": subject, "manifest": manifest}


def _plan_subjects(slug: str, script_path: str) -> list[tuple[str, str]]:
    """[(kind, subject)] from the episode's own image beats, most used first."""
    beats = None
    plan_file = os.path.join(ROOT, "plans", f"{slug}.json")
    try:
        if os.path.exists(plan_file):
            beats = json.load(open(plan_file))
        elif os.path.exists(script_path):
            import planner                                 # noqa: PLC0415
            beats = planner.plan(script_path)
    except Exception:                                      # noqa: BLE001
        beats = None
    counts: dict[tuple[str, str], int] = {}
    for b in beats or []:
        seg = b.get("segment")
        subj = (b.get("args") or {}).get("subject")
        if seg in ("species_image", "material_image") and subj:
            k = ("deep" if seg == "species_image" else "mat", subj)
            counts[k] = counts.get(k, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def candidates(slug: str, script_path: str | None = None) -> list[dict]:
    """Rights-verified images of THIS episode's subject, best first."""
    sp = script_path or os.path.join(SCRIPTS, f"{slug}.md")
    deep, mat = _deep_records(), _mat_records()
    out: list[dict] = []

    def add_deep(slot):
        for r in deep:
            if r["slot"] == slot:
                out.append(_record(r, "rights.json", slot))

    def add_mat(subject):
        for r in mat:
            if r["subject"] == subject:
                out.append(_record(r, "materials.json", subject))

    for kind, subj in _plan_subjects(slug, sp):
        (add_deep if kind == "deep" else add_mat)(subj)
    if not out:
        import thumbs_for                                  # noqa: PLC0415
        hook = thumbs_for.hook_from_script(sp)
        slot, _why = thumbs_for.deep_sea_slot_for(
            slug, hook, sorted({r["slot"] for r in deep}))
        if slot:
            add_deep(slot)
    if not out:
        try:
            import thumbs_materials                        # noqa: PLC0415
            subj = (thumbs_materials.SPECS.get(slug) or {}).get("subject")
            if subj:
                add_mat(subj)
        except Exception:                                  # noqa: BLE001
            pass
    if not out:
        # FOOD (2026-10-13): the food preset's own rights/provenance
        # manifests - Commons PD/CC0 stills (food.json) and the Workers AI
        # stills (food_ai.json, credited "AI-GENERATED IMAGE") - in the
        # order visuals/food.THUMB_SUBJECTS names for this slug.
        try:
            import food                                    # noqa: PLC0415
            cat = food.catalogue()
            for key in food.THUMB_SUBJECTS.get(slug, []):
                r = cat.get(key)
                if r and r["kind"] != "clip":
                    out.append({"path": r["path"], "local_file": r["local_file"],
                                "sha256": r.get("sha256"), "credit": r["credit"],
                                "crop": r.get("crop"), "subject": key,
                                "manifest": "food_ai.json" if r["ai"] else "food.json"})
        except Exception:                                  # noqa: BLE001
            pass
    seen, uniq = set(), []
    for c in out:
        if c["local_file"] in seen or not os.path.exists(c["path"]):
            continue
        if not c["sha256"] or _sha(c["path"]) != c["sha256"]:
            continue                       # bytes are not what was cleared
        if not c["credit"]:
            continue                       # a credit we cannot draw: drop it
        seen.add(c["local_file"])
        uniq.append(c)
    return uniq


def _open_source(c: dict) -> Image.Image:
    im = Image.open(c["path"]).convert("RGB")
    if c.get("crop"):
        x0, y0, x1, y1 = c["crop"]
        w, h = im.size
        im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    return im


# ------------------------------------------------------------------- cropping
def crop_box(src: Image.Image, target: float, place=(0.5, 0.45)) -> tuple[int, int, int, int]:
    """A 16:9 window in `src` pixels where the subject box spans `target` of
    the frame on its larger side, its centre landing on `place`."""
    W, H = src.size
    bx0, by0, bx1, by1 = _thumbs().subject_box(src, keep=0.80)
    bw, bh = (bx1 - bx0) * W, (by1 - by0) * H
    cw = max(bw / target, bh / (target * 9 / 16), MIN_CROP_W)
    cw = min(cw, W, H * 16 / 9)
    ch = cw * 9 / 16
    sx, sy = (bx0 + bx1) / 2 * W, (by0 + by1) / 2 * H
    x0 = min(max(0.0, sx - place[0] * cw), W - cw)
    y0 = min(max(0.0, sy - place[1] * ch), H - ch)
    return (int(round(x0)), int(round(y0)), int(round(x0 + cw)),
            int(round(y0 + ch)))


def base_frame(src: Image.Image, box) -> Image.Image:
    return grade(src.crop(tuple(box)).resize((TW, TH), Image.LANCZOS))


def fit_crop(src: Image.Image, target: float, place) -> tuple[tuple, float, float]:
    """Tighten until the measured fill meets the contract, or give up."""
    t = target
    for _ in range(7):
        box = crop_box(src, min(t, 0.98), place)
        fill, energy = measure_fill(base_frame(src, box))
        if fill >= SUBJECT_FILL_MIN:
            return box, fill, energy
        t = min(0.98, t * 1.12)
    return box, fill, energy


# ----------------------------------------------------------------------- text
DANGLING = {"ever", "your", "you", "my", "per", "plus", "minus", "because", "up", "about", "but", "not",
            "no", "than", "at", "by", "of", "in", "on", "to", "from", "with",
            "without", "and", "or", "for", "into", "over", "under", "while",
            "that", "which", "a", "an", "the", "is", "are", "it", "its"}


# THE TITLE ECHO (owner, 14 Oct 2026; replaces the 13 Oct model-drafted
# "drama line"): the thumbnail text is a short echo of the title's own core
# phrase - "Can a Deep Sea Fish Eat a Human?" -> "FISH EAT A HUMAN?". Built
# deterministically from the title (text_options) and gated by ONE rule
# (text_problems). The drama line's bare negations ("NOT DEFINED", "NOT ONE
# ANGLERFISH", "FILMED NOT CAUGHT" - 12 of 25 cached sets) made no sense on
# the channel page; the model path, its prompt and its cache are gone.
# The TITLE itself stays the clear, short question (13 Oct lock); only the
# words on the picture changed.
QUESTION_LEAD = {"can", "could", "why", "how", "what", "what's", "is", "are",
                 "does", "do", "did", "makes", "make", "which", "who", "when",
                 "where", "will", "would", "should", "was", "were", "has", "have",
                 "must", "be", "been", "am"}
END_WEAK = DANGLING | {"does", "do", "did", "can", "could", "was", "were", "be",
                       "will", "would", "so", "very", "just", "much", "as",
                       "own", "must"}
_FIG = re.compile(r"^\d[\d,.]*%?$")


def _title_tokens(title: str) -> tuple[list[str], list[bool]]:
    toks = re.findall(r"[\w][\w,.'’%-]*[:;?!]?", title or "")
    clean = [t.strip(".,'’:;?!") for t in toks]
    ends = [bool(re.search(r"[,:;.!?]$", t)) for t in toks]
    return clean, ends


def _subject_stems(title: str, subject: set[str] | None) -> set[str]:
    """The episode's subject words plus the title's own subject words (its
    content words minus question words, stakes and negations)."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    tw = {w for w in LT.subject_words(title or "")
          if w not in LT.STAKE and w not in LT.CONTRADICTION
          and w not in QUESTION_LEAD}
    return {LT.stem(w) for w in set(subject or ()) | tw}


def _is_subject(word: str, ss: set[str]) -> bool:
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    return any(LT.stem(x) in ss for x in re.split(r"[-–]", word.lower()) if x)


def _figure_with_unit(words: list[str]) -> bool:
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    for i, w in enumerate(words):
        if not _FIG.match(w):
            continue
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w.endswith("%") or (re.fullmatch(r"[a-z]+", nxt or "-")
                               and nxt not in LT.STOP and nxt not in END_WEAK
                               and nxt not in LT.CONTRADICTION):
            return True
    return False


def text_problems(text: str, title: str, subject: set[str] | None = None) -> list[str]:
    """THE thumbnail-text rule - the one function every path reads.

    The text is the title's core phrase: 1-4 words in capitals, every word
    from the title, a trailing "?" only when the title is a question; it
    starts on the subject or a figure (never a riddle fragment), never ends
    on a word that needs the next one, holds NO negation (not / no / never /
    only / nothing / without ...), is never a stake word alone, and names
    the subject or a simple figure with its unit ("8,336 METERS")."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    p: list[str] = []
    t = (text or "").strip()
    q = t.endswith("?")
    body = t[:-1].rstrip() if q else t
    words = body.split()
    if not 1 <= len(words) <= MAX_WORDS:
        p.append(f"{len(words)} words (1 to {MAX_WORDS})")
    if re.search(r"[^A-Z0-9' %,.-]", body):
        p.append("not plain capitals")
    if q and not (title or "").rstrip().endswith("?"):
        p.append("a question mark on a title that asks nothing")
    low = [w.lower().strip(".,'") for w in words]
    have = {w.lower() for w in _title_tokens(title)[0]}
    missing = [w for w in low if w and w not in have]
    if missing:
        p.append(f"{missing[0]!r} is not in the title")
    neg = [w for w in low if w in LT.CONTRADICTION or w.endswith("n't")]
    if neg:
        p.append(f"a negation ({neg[0].upper()}) - a riddle on the channel "
                 f"page, never the plain subject or a figure")
    ss = _subject_stems(title, subject)
    if low and not (_is_subject(low[0], ss) or _FIG.match(low[0])):
        p.append(f"a riddle fragment: starts on {low[0].upper()!r}, not the "
                 f"subject or a figure")
    if low and low[0] in END_WEAK:
        p.append(f"starts on a word that needs the one before ({low[0].upper()})")
    if low and low[-1] in END_WEAK:
        p.append("ends on a word that needs the next one")
    inner = [w for w in low if w in QUESTION_LEAD]
    if inner:
        p.append(f"a question word inside the echo ({inner[0].upper()})")
    content = [w for w in low if w not in LT.STOP]
    if content and all(w in LT.STAKE for w in content):
        p.append("a stake word alone - names nothing")
    if not (any(_is_subject(w, ss) for w in low) or _figure_with_unit(low)):
        p.append("names neither the subject nor a figure with its unit")
    return p


def text_options(title: str, subject: set[str] | None = None) -> list[str]:
    """Up to three title echoes, best first, each passing text_problems.

    Windows of 1-4 consecutive title words inside one clause (a phrase never
    crosses a comma or a negation: "Steel fails at 0.4 gigapascals, graphene
    at 130" never prints 0.4 over GRAPHENE). With `subject` (the episode's
    subject words) only clauses that name it count. Ranked: holds a stake or
    a figure with its unit, then two words or more, then ends where the title
    ends (keeping its "?"), then starts on a figure, then longer. "Can a Deep Sea Fish Eat a Human?"
    -> "FISH EAT A HUMAN?"; "What Makes Steel So Strong?" -> "STEEL SO
    STRONG?"."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    clean, ends = _title_tokens(title)
    low = [w.lower() for w in clean]
    if not low:
        return []
    question = (title or "").rstrip().endswith("?")
    last = len(low) - 1
    ss = _subject_stems(title, subject)
    episode = {LT.stem(w) for w in (subject or ())}
    # segments: split at clause ends; a negation ENDS its clause's usable
    # words - what follows it is the opposite of the claim ("The Deep Sea Is
    # Not Empty" must never print EMPTY, "Concrete Does Not Dry" never DRY).
    # Only a question's leading contracted auxiliary ("Why Aren't Deep Sea
    # Fish Crushed?") is part of the asking and is skipped like "Why".
    segs, cur, dead = [], [], False
    for i, w in enumerate(low):
        neg = w in LT.CONTRADICTION or w.endswith("n't")
        if neg and question and i <= 1 and w.endswith("n't"):
            neg = False
        if neg:
            if cur:
                segs.append(cur)
            cur, dead = [], True
        elif not dead:
            cur.append(i)
        if ends[i]:
            if cur:
                segs.append(cur)
            cur, dead = [], False
    if cur:
        segs.append(cur)
    # clause ids for the episode-subject check (clauses end at punctuation)
    clause, k = [], 0
    for e in ends:
        clause.append(k)
        k += e
    named = {clause[i] for i, w in enumerate(low) if _is_subject(w, episode)}
    domain = set().union(*LT.DOMAIN_PLAIN.values())
    cands = []
    for seg in segs:
        for a in range(len(seg)):
            # never start inside a noun phrase ("SEA ANIMALS", "FIBER SO
            # STRONG", "STRONGER THAN STEEL"): the word before may only be a
            # question word, a stop word, or the domain's own "deep sea"
            # ahead of a new noun ("Deep Sea FISH EAT A HUMAN").
            if a:
                prev, w0 = low[seg[a - 1]], low[seg[a]]
                if (prev not in LT.STOP and prev not in QUESTION_LEAD
                        and not prev.endswith("n't")
                        and not (prev in domain and w0 not in domain)):
                    continue
            for b in range(a, min(a + MAX_WORDS, len(seg))):
                idx = seg[a:b + 1]
                if episode and clause[idx[0]] not in named:
                    continue
                ws = [low[i] for i in idx]
                txt = " ".join(clean[i] for i in idx).upper()
                at_end = idx[-1] == last
                if question and at_end:
                    txt += "?"
                if text_problems(txt, title, subject):
                    continue
                key = (any(w in LT.STAKE for w in ws) or _figure_with_unit(ws),
                       len(ws) >= 2, at_end, bool(_FIG.match(ws[0])), len(ws), -idx[0])
                cands.append((key, txt))
    out: list[str] = []
    for _, txt in sorted(cands, key=lambda c: c[0], reverse=True):
        if txt not in out:
            out.append(txt)
    return out[:3]


def draw(base: Image.Image, text: str, credit: str, side: str = "left") -> tuple[Image.Image, list, list]:
    words = text.split()
    if len(words) > MAX_WORDS:
        raise ValueError(f"{text!r} is {len(words)} words; the contract "
                         f"allows {MAX_WORDS}")
    im = base.copy()
    d = ImageDraw.Draw(im)
    pad = 56
    size = 168
    while size > 60:
        f = _font(_FONT_CANDIDATES, size)
        lines = [text] if d.textlength(text, font=f) <= TW * 0.80 else words
        widest = max(d.textlength(ln, font=f) for ln in lines)
        lead = int(size * 1.02)
        if widest <= TW * 0.80 and lead * len(lines) <= TH * 0.62:
            break
        size -= 8
    lead = int(size * 1.02)
    total = lead * len(lines)
    y = TH - pad - total
    stroke = max(6, size // 14)
    tb = [TW, TH, 0, 0]
    for ln in lines:
        w = d.textlength(ln, font=f)
        x = pad if side == "left" else TW - pad - w
        d.text((x, y), ln, font=f, fill=(255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0))
        bb = d.textbbox((x, y), ln, font=f, stroke_width=stroke)
        tb = [min(tb[0], bb[0]), min(tb[1], bb[1]), max(tb[2], bb[2]),
              max(tb[3], bb[3])]
        y += lead
    cf = _font(_CREDIT_FONTS, 18)
    cb = d.textbbox((0, 0), credit, font=cf)
    cx = TW - 16 - (cb[2] - cb[0]) if side == "left" else 16
    cy = 12
    d.text((cx, cy), credit, font=cf, fill=(235, 235, 235),
           stroke_width=2, stroke_fill=(0, 0, 0))
    cbb = list(d.textbbox((cx, cy), credit, font=cf, stroke_width=2))
    return im, [int(v) for v in tb], [int(v) for v in cbb]


# ---------------------------------------------------------------- the builder
def title_for(slug: str, script_text: str) -> str:
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    t, _why, _src = LT.title_for_upload(slug, script_text)
    if t:
        return t
    import thumbs_for                                      # noqa: PLC0415
    return thumbs_for.hook_from_script(os.path.join(SCRIPTS, f"{slug}.md"))


def _shorter(text: str) -> str:
    """A second, shorter phrasing of a one-phrase title: its longest prefix that
    does not end on a dangling word. The phrase itself when it cannot shrink."""
    w = text.split()
    for n in range(len(w) - 1, 0, -1):
        if w[n - 1].lower().strip(".,'?!") not in DANGLING:
            return " ".join(w[:n])
    return text


SLUG_STOP = {"what", "why", "how", "is", "are", "a", "an", "the", "of", "does", "do",
             "made", "so", "get", "in", "to", "it", "work", "when", "most", "many", "some"}


def _slug_phrase(slug: str) -> str:
    """The episode's subject in plain words, from its slug ("what-is-carbon-
    fiber-made-of" -> "CARBON FIBER"): the variant text of last resort."""
    w = [x for x in re.sub(r"^\d+-", "", slug).split("-") if x and x not in SLUG_STOP]
    return " ".join(w[:min(2, MAX_WORDS)]).upper()


def subject_for(slug: str, script: str) -> set[str]:
    """The episode's subject words (longform_title.subject_words of its
    question, plus the domain's plain words)."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    subject = LT.subject_words(LT._question_for(slug, script))  # noqa: SLF001
    dm = re.search(r"^\*\*Domain:\*\*\s*(\S+)", script, re.M)
    return subject | LT.DOMAIN_PLAIN.get(dm.group(1) if dm else "", set())


def build_variants(slug: str, out_root: str | None = None,
                   title: str | None = None,
                   script_path: str | None = None,
                   texts: list[str] | None = None,
                   keep_a: bool = False) -> dict:
    """Build A, B, C and contract.json. Raises ContractRefused, named.
    `texts` (owner-given thumbnail words, each <= MAX_WORDS) replace the phrases
    taken from the title - the food sample's "WHAT'S INSIDE?" is the owner's.
    `keep_a` keeps the set's existing A (the published variant: file, record,
    words) and rebuilds only B and C - the repair for a set whose B or C
    duplicates A (owner, 13 Oct 2026)."""
    return build_into(slug, os.path.join(out_root or VARIANTS_DIR, slug),
                      title=title, script_path=script_path, texts=texts, keep_a=keep_a)


def build_into(slug: str, final_dir: str, title: str | None = None,
               script_path: str | None = None,
               texts: list[str] | None = None, keep_a: bool = False) -> dict:
    """build_variants with the set's directory named by the caller (so the
    lane's write set is a path, not a slug - loop/tools/write_set.py)."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    sp = script_path or os.path.join(SCRIPTS, f"{slug}.md")
    text_src = open(sp, encoding="utf-8").read() if os.path.exists(sp) else ""
    title = title or title_for(slug, text_src)
    owner_texts = bool(texts)
    if texts and any(len(t.split()) > MAX_WORDS for t in texts):
        raise ContractRefused(f"{slug}: thumbnail text over {MAX_WORDS} words: {texts}")
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    subject = subject_for(slug, text_src) if text_src else None
    if texts:
        texts = [t.upper() for t in texts]
    else:
        texts = text_options(title, subject)
    if not texts and not text_src:
        raise ContractRefused(f"{slug}: no title or hook to take <= {MAX_WORDS} "
                              f"words from")
    cands = candidates(slug, sp)
    if not texts:
        raise ContractRefused(f"{slug}: no title or hook to take <= {MAX_WORDS} "
                              f"words from")
    if not cands:
        raise ContractRefused(
            f"{slug}: no rights-verified image of this episode's subject in "
            f"channel/imagery/rights.json or materials.json (plan beats, slug "
            f"and hook searched); the contract needs one big subject and this "
            f"module never borrows a lookalike")
    # A is the published variant and keeps its long-standing plan. B and C must
    # be GENUINELY different (owner, 13 Oct 2026: two of three food variants
    # were the same picture): each takes, in preference order, another
    # candidate image, then another crop/emphasis of the same one, and is kept
    # only when its pHash differs from every variant already made
    # (visuals/thumb_distinct.py). Texts are not all identical.
    import thumb_distinct as TD                            # noqa: PLC0415
    alt = texts[1] if len(texts) > 1 else _shorter(texts[0])
    if alt.upper() == texts[0].upper() or (
            not owner_texts and text_problems(alt, title, subject)):
        alt = _slug_phrase(slug) or alt
        if not owner_texts and text_problems(alt, title, subject):
            alt = texts[0]          # the one rule wins over variety
    alt2 = texts[2] if len(texts) > 2 else (texts[0] if alt != texts[0] else alt)
    crops = [(0.72, (0.66, 0.45), "left"), (0.95, (0.34, 0.5), "right"),
             (0.62, (0.5, 0.42), "left"), (0.9, (0.7, 0.5), "left"),
             (0.9, (0.3, 0.5), "right"), (0.98, (0.5, 0.25), "left"),
             (0.98, (0.5, 0.75), "right"), (0.55, (0.5, 0.5), "left")]
    plan = [("A", [0], [(0.85, (0.5, 0.42), "left")], texts[0]),
            ("B", [1, 0, 2], crops, alt),
            ("C", [2, 1, 0], crops[1:] + crops[:1], alt2)]
    # Built in a scratch directory and moved into place only when all three
    # variants pass: a refusal at B left A.jpg behind with no contract.json
    # (how-strong-is-graphene, 13 Oct 2026), and repackage apply shipped it.
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    import tempfile                                        # noqa: PLC0415
    import shutil                                          # noqa: PLC0415
    out_dir = tempfile.mkdtemp(prefix=".contract-", dir=os.path.dirname(final_dir))
    rec = {"slug": slug, "title": title, "grade": GRADE["id"],
           "chosen": CHOSEN, "variants": {}}
    srcs: dict[int, Image.Image] = {}
    made: dict[str, int] = {}
    if keep_a:
        old_dir = final_dir
        old = json.load(open(os.path.join(old_dir, "contract.json")))
        rec["title"] = old.get("title", rec["title"])
        rec["variants"]["A"] = old["variants"]["A"]
        shutil.copyfile(os.path.join(old_dir, "A.jpg"), os.path.join(out_dir, "A.jpg"))
        a = old["variants"]["A"]
        made["A"] = TD.phash(base_frame(_open_source({"path": os.path.join(IMAGERY, a["source"]),
                                                      "crop": a.get("crop")}), a["box"]))
        plan = plan[1:]
    for name, order, options, text in plan:
        order = [k for k in dict.fromkeys(order + list(range(len(cands)))) if k < len(cands)]
        ok, best, fill_seen = None, None, False
        for k in order:
            if k not in srcs:
                srcs[k] = _open_source(cands[k])
            for target, place, side in options:
                box, fill, energy = fit_crop(srcs[k], target, place)
                if fill < SUBJECT_FILL_MIN or energy < _thumbs().MIN_SUBJECT_ENERGY:
                    continue
                fill_seen = True
                base = base_frame(srcs[k], box)
                h = TD.phash(base)              # the PICTURE, before any type is drawn
                im, tb, cb = draw(base.copy(), text, cands[k]["credit"], side)
                dmin = min((TD.distance(h, x) for x in made.values()), default=64)
                if best is None or dmin > best[0]:
                    best = (dmin, k, box, fill, energy, im, tb, cb, h)
                if dmin >= TD.MIN_PHASH_DISTANCE:
                    ok = best = (dmin, k, box, fill, energy, im, tb, cb, h)
                    break
            if ok:
                break
        if ok is None:
            shutil.rmtree(out_dir, ignore_errors=True)
            if not fill_seen:
                raise ContractRefused(
                    f"{slug}: variant {name}: no candidate image reaches the "
                    f"{SUBJECT_FILL_MIN:.0%} subject fill with real subject "
                    f"energy ({len(cands)} tried)")
            raise ContractRefused(
                f"{slug}: variant {name}: every candidate crop is a near-duplicate of "
                f"another variant (best pHash distance {best[0]}, needs >= "
                f"{TD.MIN_PHASH_DISTANCE}) - a second rights-cleared image is needed")
        _d, k, box, fill, energy, im, tb, cb, h = ok
        made[name] = h
        path = os.path.join(out_dir, f"{name}.jpg")
        im.save(path, "JPEG", quality=92, optimize=True, progressive=True)
        rec["variants"][name] = {
            "file": f"{name}.jpg", "source": cands[k]["local_file"],
            "manifest": cands[k]["manifest"], "subject": cands[k]["subject"],
            "sha256": cands[k]["sha256"], "box": list(box),
            "crop": cands[k]["crop"], "text": text, "words": len(text.split()),
            "credit": cands[k]["credit"], "text_bbox": tb, "credit_bbox": cb,
            "fill": fill, "energy": energy}
    dup = TD.check(_pictures(rec), {n: rec["variants"][n]["text"] for n in VARIANT_NAMES})
    if dup:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise ContractRefused(f"{slug}: " + "; ".join(dup))
    with open(os.path.join(out_dir, "contract.json"), "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    if os.path.isdir(final_dir):
        shutil.rmtree(final_dir)
    os.replace(out_dir, final_dir)
    return {"dir": final_dir, "chosen": os.path.join(final_dir, f"{CHOSEN}.jpg"),
            "contract": rec}


def chooser(slug: str, root: str | None = None) -> str:
    """The variant thumbnails.set receives: always A."""
    return os.path.join(root or VARIANTS_DIR, slug, f"{CHOSEN}.jpg")


# ------------------------------------------------------------------- verifying
def verify(slug: str, root: str | None = None) -> list[str]:
    """Re-check the contract on the files on disk. [] = it holds."""
    d = os.path.join(root or VARIANTS_DIR, slug)
    cpath = os.path.join(d, "contract.json")
    if not os.path.exists(cpath):
        return [f"{slug}: no contract.json in {d}"]
    rec = json.load(open(cpath))
    if rec.get("layout") == "triptych":
        # The owner's multi-subject layout (13 Oct 2026) has its own contract.
        import thumb_triptych                              # noqa: PLC0415
        return thumb_triptych.verify_dir(d, rec)
    p: list[str] = []
    if rec.get("grade") != GRADE["id"]:
        p.append(f"{slug}: built with grade {rec.get('grade')!r}, not the "
                 f"channel's {GRADE['id']!r}")
    if rec.get("chosen") != CHOSEN:
        p.append(f"{slug}: chooser names {rec.get('chosen')!r}, not {CHOSEN}")
    T = _thumbs()
    for name in VARIANT_NAMES:
        v = (rec.get("variants") or {}).get(name)
        f = os.path.join(d, f"{name}.jpg")
        if not v or not os.path.exists(f):
            p.append(f"{slug}: variant {name} missing")
            continue
        if len(v["text"].split()) > MAX_WORDS:
            p.append(f"{slug}/{name}: text {v['text']!r} is over {MAX_WORDS} words")
        with Image.open(f) as im:
            if im.size != (TW, TH) or im.format != "JPEG":
                p.append(f"{slug}/{name}: {im.format} {im.size}, not a "
                         f"{TW}x{TH} JPEG")
                continue
            got = np.asarray(im.convert("RGB")).astype(np.float32)
        src_path = os.path.join(IMAGERY, v["source"])
        if not os.path.exists(src_path) or _sha(src_path) != v["sha256"]:
            p.append(f"{slug}/{name}: source {v['source']} missing or not the "
                     f"cleared bytes")
            continue
        src = _open_source({"path": src_path, "crop": v.get("crop")})
        base = base_frame(src, v["box"])
        fill, energy = measure_fill(base)
        if fill < SUBJECT_FILL_MIN:
            p.append(f"{slug}/{name}: subject fills {fill:.0%} of the frame, "
                     f"under {SUBJECT_FILL_MIN:.0%}")
        if energy < T.MIN_SUBJECT_ENERGY:
            p.append(f"{slug}/{name}: subject energy {energy:.3f} - the frame "
                     f"is mostly background")
        want = np.asarray(base).astype(np.float32)
        mask = np.ones((TH, TW), bool)
        for bb in (v["text_bbox"], v["credit_bbox"]):
            x0, y0, x1, y1 = bb
            mask[max(0, y0 - 4):y1 + 4, max(0, x0 - 4):x1 + 4] = False
        diff = float(np.abs(got - want)[mask].mean())
        if diff > GRADE_TOLERANCE:
            p.append(f"{slug}/{name}: published pixels differ from the graded "
                     f"crop by {diff:.1f} per channel - the channel grade is "
                     f"not what was applied")
    vs = rec.get("variants") or {}
    if all(n in vs for n in VARIANT_NAMES):
        import thumb_distinct as TD                        # noqa: PLC0415
        try:
            pics = _pictures(rec)
        except Exception as e:                             # noqa: BLE001
            return p + [f"{slug}: variant pictures could not be rebuilt: {e}"]
        p += [f"{slug}: {x}" for x in TD.check(pics, {n: vs[n].get("text", "") for n in VARIANT_NAMES})]
    return p


def _pictures(rec: dict) -> dict:
    """Each variant's picture as graded, BEFORE type: what the distinctness rule
    compares (two variants with one picture and different words are one picture)."""
    return {n: base_frame(_open_source({"path": os.path.join(IMAGERY, v["source"]),
                                        "crop": v.get("crop")}), v["box"])
            for n, v in (rec.get("variants") or {}).items()}




def contract_slugs(root: str | None = None) -> list[str]:
    r = root or VARIANTS_DIR
    if not os.path.isdir(r):
        return []
    return sorted(s for s in os.listdir(r)
                  if os.path.exists(os.path.join(r, s, "contract.json")))


def needed_slugs() -> list[str]:
    """Live long-form videos whose contract set is missing or was built for
    another title than today's (the lock re-titles; the words follow)."""
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import ledger                                          # noqa: PLC0415
    out = []
    for r in ledger.load()["published"]:
        slug = r.get("slug")
        if not r.get("video_id") or r.get("retired_at") or slug in out:
            continue
        sp = os.path.join(SCRIPTS, f"{slug}.md")
        if not os.path.exists(sp):
            continue
        title = title_for(slug, open(sp, encoding="utf-8").read())
        try:
            rec = json.load(open(os.path.join(VARIANTS_DIR, slug, "contract.json")))
        except (OSError, ValueError):
            rec = {}
        if rec.get("title") != title:
            out.append(slug)
    return out


def main(argv: list[str]) -> int:
    if "--chosen" in argv:
        for s in [a for a in argv if not a.startswith("--")]:
            print(chooser(s))
        return 0
    slugs = [a for a in argv if not a.startswith("--")]
    if "--verify" in argv:
        slugs = slugs or contract_slugs()
        if not slugs:
            print("NAMED STOP: no contract.json to verify")
            return 3
        bad = 0
        for s in slugs:
            pr = verify(s)
            bad += bool(pr)
            print(f"  {'OK  ' if not pr else 'FAIL'} {s}")
            for x in pr:
                print(f"       ✗ {x}")
        return 1 if bad else 0
    if not slugs:
        print(__doc__.split("\n\n", 1)[0])
        return 2
    made = 0
    for s in slugs:
        try:
            r = build_into(s, f"{VARIANTS_DIR}/{s}")
            made += 1
            c = r["contract"]["variants"]
            print(f"  OK   {s}: " + ", ".join(
                f"{n} {c[n]['text']!r} fill {c[n]['fill']:.0%}" for n in c))
        except ContractRefused as e:
            print(f"  REFUSED {e}")
    if not made:
        print("NAMED STOP: no variant set was built; each refusal above says why")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
