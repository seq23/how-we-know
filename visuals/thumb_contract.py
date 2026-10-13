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
MAX_WORDS = 3
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


# THE DRAMA LINE (owner's lock, 13 Oct 2026): "thumbnail text (<=3 words)
# carries the drama/subject; the title stays clear and short". A question
# title yields fragments ("FISH LIVE", "STEEL STRONG"), so the words are
# drafted on the $0 route from the script's own answer and gated here:
# <=3 words, every word traceable to the script, short common words, and
# the subject, a simple figure or a contradiction in it. Cached per slug in
# loop/state/thumb_text.json; text_options() is the fallback.
THUMB_TEXT = os.path.join(ROOT, "loop", "state", "thumb_text.json")
DRAMA_PROMPT = """Write {n} candidate thumbnail texts for a science video, one \
per line, nothing else. Each is 1 to 3 words, in capitals, the most dramatic \
TRUE thing the script's answer says - the surprise, a simple figure, or what \
is NOT so. Short common words a 12-year-old knows; every word must be in the \
script below; never repeat the title's question; no punctuation except an \
apostrophe. Shapes (other videos): "NOT STRONGER", "NO SUNLIGHT", "5 MILES DOWN".

TITLE: {title}
SUBJECT: {subject}
DIRECT-ANSWER LOCK: {answer}
SCRIPT EXCERPT: {excerpt}
"""


def drama_problems(text: str, script: str, subject: set[str]) -> list[str]:
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    p: list[str] = []
    words = text.split()
    if not 1 <= len(words) <= MAX_WORDS:
        p.append(f"{len(words)} words")
    if re.search(r"[^A-Z0-9' %-]", text):
        p.append("not plain capitals")
    ev = LT.evidence_text(script)
    have = {LT.stem(w) for w in LT.content_words(ev)}
    ss = {LT.stem(w) for w in subject}
    for w in LT.content_words(text.lower()):
        if not LT._match(LT.stem(w), have) and w not in LT.CONTRADICTION:  # noqa: SLF001
            p.append(f"{w!r} is not in the script")
        if LT._syllables(w) > LT.MAX_SYLLABLES and LT.stem(w) not in ss:  # noqa: SLF001
            p.append(f"{w!r} is a long word")
    low_ = text.lower().split()
    if low_ and (low_[-1] in DANGLING or low_[-1] == "than"):
        p.append("ends on a word that needs the next one")
    if sum(1 for w in low_ if w in LT.NUMBER_WORDS or w in ("point", "to")) >= 2:
        p.append("a spelled-out figure or a range - one simple figure in digits")
    nums = re.findall(r"\d[\d,.]*", text)
    if any(not LT._simple_number(n) for n in nums):        # noqa: SLF001
        p.append("a figure that is not simple")
    bad = [n for n in LT._numbers_in_title(text.lower())   # noqa: SLF001
           if n not in set(LT.figures(ev))]
    if bad:
        p.append("a figure the script never states")
    toks = {LT.stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())}
    if not (toks & ss or nums or toks & {LT.stem(w) for w in LT.CONTRADICTION}
            or toks & {LT.stem(w) for w in LT.STAKE}):
        p.append("names neither the subject, a figure nor a contradiction")
    return p


def drama_text(slug: str, title: str, script: str, subject: set[str],
               ask=None) -> list[str]:
    """Cached, gated drama lines for one slug (newest title wins)."""
    try:
        cache = json.load(open(THUMB_TEXT))
    except (OSError, ValueError):
        cache = {}
    rec = cache.get(slug) or {}
    if rec.get("title") == title and rec.get("texts"):
        return [t for t in rec["texts"] if not drama_problems(t, script, subject)]
    if ask is None:
        return []
    sys.path.insert(0, os.path.join(ROOT, "loop"))
    import longform_title as LT                            # noqa: PLC0415
    msg = DRAMA_PROMPT.format(n=6, title=title, subject=", ".join(sorted(subject)),
                              answer=LT.answer_lock(script),
                              excerpt=LT._excerpt(script, 400))  # noqa: SLF001
    try:
        reply, model = ask([{"role": "user", "content": msg}])
    except Exception:                                      # noqa: BLE001
        return []
    out = []
    for ln in (reply or "").splitlines():
        t = re.sub(r"^\s*(?:[-*]|\d{1,2}[.)])\s+", "", ln).strip().strip('"').upper()
        if t and t not in out and not drama_problems(t, script, subject):
            out.append(t)
    cache[slug] = {"title": title, "texts": out[:3], "model": model}
    with open(THUMB_TEXT, "w") as fh:
        json.dump(cache, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out[:3]


def text_options(title: str, subject: set[str] | None = None) -> list[str]:
    """Up to three <=3-word phrases from the (already truth-guarded) title.

    With `subject` (longform_title.subject_words of the episode's question)
    the PLAINNESS rule holds (owner, 13 Oct 2026): every phrase is the plain
    subject or a figure with its unit, never a riddle fragment ("NOT FISH",
    "NOT SEEN"); the subject phrase comes first, so variant A names it."""
    import longform_title as LT                            # noqa: PLC0415
    toks = [t for t in re.findall(r"[\w][\w,.'%-]*[:;]?", title or "")]
    clean = [t.strip(".,'':;") for t in toks]
    low = [t.lower() for t in clean]
    # A phrase never crosses a clause boundary: "Steel fails at 0.4
    # gigapascals, graphene at 130" gave "0.4 GIGAPASCALS GRAPHENE" (13 Oct
    # 2026) - steel's figure printed over graphene's name.
    ends = [bool(re.search(r"[,:;]$", t)) for t in toks]
    opts: list[list[str]] = []

    def phrase_from(i):
        ph = [clean[i]]
        j = i + 1
        while j < len(clean) and len(ph) < MAX_WORDS and not ends[j - 1]:
            if low[j] not in STOP:
                ph.append(clean[j])
            elif len(ph) >= 2:
                break
            j += 1
        return ph

    subj = {LT.stem(w) for w in (subject or ())}

    def names_subject(ph):
        return any(LT.stem(x) in subj for w in ph
                   for x in re.split(r"[-\u2013]", w.lower()) if x)

    if subj:
        for i, t in enumerate(clean):
            if names_subject([t]):
                opts.append(phrase_from(i))
                break
    for i, t in enumerate(clean):
        if re.search(r"\d", t):
            ph = phrase_from(i)
            if not subj or len(ph) >= 2:      # a bare number is a riddle too
                opts.append(ph)
            break
    for i, t in enumerate(low):
        if t in LT.CONTRADICTION or t in LT.STAKE:
            opts.append(phrase_from(i))
            break
    if subj:
        # a figure counts only inside a clause that names the subject:
        # "Steel fails at 0.4 gigapascals, graphene at 130" -> 0.4 is steel's
        clause, k = [], 0
        for e in ends:
            clause.append(k)
            k += e
        subj_clauses = {clause[i] for i, t in enumerate(clean)
                        if names_subject([t])}

        def figure_ok(o):
            return any(re.search(r"\d", w) and clause[clean.index(w)] in subj_clauses
                       for w in o if w in clean)
        opts = [o for o in opts if names_subject(o) or figure_ok(o)]
    content: list[str] = []
    for c, lo, e in zip(clean, low, ends):
        if lo not in STOP:
            content.append(c)
        if e and content:
            break                       # the first clause only
    if content and (not subj or names_subject(content[:MAX_WORDS])):
        opts.append(content[:MAX_WORDS])
    out = []
    for ph in opts:
        ph = list(ph[:MAX_WORDS])
        # Never end on a word that needs the next one ("100 DEGREES PER",
        # "10,935 METERS PLUS", "NOT FLATTENED BECAUSE" - all built on
        # 2026-10-13 before this trim).
        while len(ph) > 1 and ph[-1].lower() in DANGLING:
            ph.pop()
        s = " ".join(ph).upper()
        if s and s not in out:
            out.append(s)
    return out


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


DRAMA_ASK = None     # set by the CLI (the $0 route); tests pass a fixture


def build_variants(slug: str, out_root: str | None = None,
                   title: str | None = None,
                   script_path: str | None = None,
                   texts: list[str] | None = None) -> dict:
    """Build A, B, C and contract.json. Raises ContractRefused, named.
    `texts` (owner-given thumbnail words, each <= MAX_WORDS) replace the phrases
    taken from the title - the food sample's "WHAT'S INSIDE?" is the owner's."""
    return build_into(slug, os.path.join(out_root or VARIANTS_DIR, slug),
                      title=title, script_path=script_path, texts=texts)


def build_into(slug: str, final_dir: str, title: str | None = None,
               script_path: str | None = None,
               texts: list[str] | None = None) -> dict:
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
    subject = None
    if text_src:
        subject = LT.subject_words(LT._question_for(slug, text_src))  # noqa: SLF001
        dm = re.search(r"^\*\*Domain:\*\*\s*(\S+)", text_src, re.M)
        subject |= LT.DOMAIN_PLAIN.get(dm.group(1) if dm else "", set())
    if texts:
        texts = [t.upper() for t in texts]
    else:
        texts = text_options(title, subject)
    if not texts and not text_src:
        raise ContractRefused(f"{slug}: no title or hook to take <= {MAX_WORDS} "
                              f"words from")
    cands = candidates(slug, sp)
    if cands and text_src and not owner_texts:
        # the drama line only for an episode that has a picture to carry it
        drama = drama_text(slug, title, text_src, subject or set(), ask=DRAMA_ASK)
        texts = list(dict.fromkeys(drama + texts))[:3]
    if not texts:
        raise ContractRefused(f"{slug}: no title or hook to take <= {MAX_WORDS} "
                              f"words from")
    if not cands:
        raise ContractRefused(
            f"{slug}: no rights-verified image of this episode's subject in "
            f"channel/imagery/rights.json or materials.json (plan beats, slug "
            f"and hook searched); the contract needs one big subject and this "
            f"module never borrows a lookalike")
    plan = [("A", 0, 0.85, (0.5, 0.42), texts[0], "left"),
            ("B", 0, 0.72, (0.66, 0.45), texts[0], "left"),
            ("C", 0, 0.85, (0.5, 0.42),
             texts[1] if len(texts) > 1 else texts[0], "left")]
    if len(texts) == 1:
        # One phrase only: C differs by image when there is a second one, by
        # crop (tighter, centred, type on the right) when there is not.
        plan[2] = (("C", 1, 0.85, (0.5, 0.42), texts[0], "left")
                   if len(cands) > 1 else
                   ("C", 0, 0.95, (0.42, 0.5), texts[0], "right"))
    # Built in a scratch directory and moved into place only when all three
    # variants pass: a refusal at B left A.jpg behind with no contract.json
    # (how-strong-is-graphene, 13 Oct 2026), and repackage apply shipped it.
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    import tempfile                                        # noqa: PLC0415
    out_dir = tempfile.mkdtemp(prefix=".contract-", dir=os.path.dirname(final_dir))
    rec = {"slug": slug, "title": title, "grade": GRADE["id"],
           "chosen": CHOSEN, "variants": {}}
    srcs: dict[int, Image.Image] = {}
    for name, ci, target, place, text, side in plan:
        tried = list(range(ci, len(cands))) + list(range(0, ci))
        ok = None
        for k in tried:
            if k not in srcs:
                srcs[k] = _open_source(cands[k])
            box, fill, energy = fit_crop(srcs[k], target, place)
            if fill >= SUBJECT_FILL_MIN and energy >= _thumbs().MIN_SUBJECT_ENERGY:
                ok = (k, box, fill, energy)
                break
        if ok is None:
            import shutil                                  # noqa: PLC0415
            shutil.rmtree(out_dir, ignore_errors=True)
            raise ContractRefused(
                f"{slug}: variant {name}: no candidate image reaches the "
                f"{SUBJECT_FILL_MIN:.0%} subject fill with real subject "
                f"energy ({len(cands)} tried)")
        k, box, fill, energy = ok
        im, tb, cb = draw(base_frame(srcs[k], box), text, cands[k]["credit"],
                          side)
        path = os.path.join(out_dir, f"{name}.jpg")
        im.save(path, "JPEG", quality=92, optimize=True, progressive=True)
        rec["variants"][name] = {
            "file": f"{name}.jpg", "source": cands[k]["local_file"],
            "manifest": cands[k]["manifest"], "subject": cands[k]["subject"],
            "sha256": cands[k]["sha256"], "box": list(box),
            "crop": cands[k]["crop"], "text": text, "words": len(text.split()),
            "credit": cands[k]["credit"], "text_bbox": tb, "credit_bbox": cb,
            "fill": fill, "energy": energy}
    with open(os.path.join(out_dir, "contract.json"), "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    if os.path.isdir(final_dir):
        import shutil                                      # noqa: PLC0415
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
    return p


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
    global DRAMA_ASK
    if "--drama" in argv:
        # Draft drama lines on the repo's $0 route (subscription first, then
        # the free tiers; never paid): loop/longform_title._ask.
        sys.path.insert(0, os.path.join(ROOT, "loop"))
        import longform_title as LT                        # noqa: PLC0415
        DRAMA_ASK = LT._ask                                # noqa: SLF001
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
