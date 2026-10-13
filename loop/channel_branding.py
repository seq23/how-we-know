"""The channel's own face: banner, About text, keywords and home shelves, for EVERY domain.

    .venv/bin/python loop/channel_branding.py --build       # banner PNG only, no network
    .venv/bin/python loop/channel_branding.py --dry-run     # read live, compose, write nothing
    .venv/bin/python loop/channel_branding.py               # apply, read back, record
    .venv/bin/python loop/channel_branding.py --candidate B # apply another candidate
    LOOP_DRY_RUN=1 ... refuses credentials (tests)

Owner instruction 2026-10-13: the banner said "bottom of the ocean" (deep sea
only) while the channel carries three domains. Owner rulings the same day:
  * KEEP THE LOGO. The mark is drawn by visuals/brand.py mark() and the
    wordmark set in design.F_DISPLAY, exactly as the 2048 banner was
    (channel/brand/banner_2048.png); the live banner as it was is kept at
    channel/branding/previous/. Nothing here re-draws a lookalike.
  * KEEP THE WORDS, minus the deep-sea-only clause, read as one thought:
    question -> answer -> cadence ("How we know what we know? We follow the
    evidence chain." / "NEW EPISODES WEEKLY . @howweknowdeep"). V51 holds the
    banner to "evidence chain" and "How we know what we know".
  * OPEN-ENDED. The words name no domain, so a new domain never needs new
    words; the panel row under them is a list in channel/branding/branding.json
    (one vivid image per domain, one warm-dark grade, soft fades) that the
    layout divides evenly. Three candidates (A, B, C) are built every run; the
    applied one is branding.json `applied`, or `--candidate X`.
  * The About text (channel/about.md, its one source) carries one generated
    line naming the channel's CURRENT domains; keywords are generated the
    same way.

THE DOMAIN LIST is not kept here. channel_domains() reads loop/config.json:
the owner's weekday rotation (cadence.rotation.weekdays) first, in weekday
order, then any allocated domain the rotation does not name. food-science is
on the rotation before it is in the taxonomy, and the owner wants it on the
channel's face now, so the rotation is the honest source. Every domain there
must have a `display` name and keywords in branding.json, or this refuses.

WHAT RUNNING IT DOES, idempotently (a re-run changes nothing and costs reads):
  1. builds the banner (Pillow, the thumbnail contract's one grade and type,
     rights-checked imagery re-hashed first) to channel/branding/banner.png
     and ~/Desktop/how-we-know-banner.png;
  2. uploads it with channelBanners.insert (50 units) ONLY if its sha256 is
     not the one already recorded live, then ONE channels.update
     part=brandingSettings (50 units) carrying the banner URL, the composed
     description and keywords, merged onto the live channel object (the
     REPLACE trap - loop/channel_about.py merge_branding);
  3. finds or creates each domain's playlist (loop/handoff.py PLAYLIST_TITLES,
     recorded in loop/state/playlists.json, where the handoff lane reads them)
     and one singlePlaylist channel section per domain in rotation order. A
     refusal by YouTube is recorded on the section, as the handoff lane does,
     never retried blindly;
  4. reads the channel back (channels.list, 1 unit), confirms the banner URL
     answers 200, and writes loop/state/channel_branding.json - the record
     validator V51 checks.
Quota is booked to lane "branding" in loop/state/quota.json, and nothing runs
that would eat into the Shorts lane's reserve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))
sys.path.insert(0, str(ROOT / "visuals"))

from common import config  # noqa: E402

SPEC_FILE = ROOT / "channel" / "branding" / "branding.json"
BANNER = ROOT / "channel" / "branding" / "banner.png"
CANDIDATE_PNG = ROOT / "channel" / "branding" / "candidates" / "banner_A.png"
CANDIDATES_DIR = Path.home() / "Desktop" / "how-we-know-banner-candidates"
DESKTOP = Path.home() / "Desktop" / "how-we-know-banner.png"
STATE = LOOP / "state" / "channel_branding.json"
LANE = "branding"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
DRY_RUN = os.environ.get("LOOP_DRY_RUN") == "1"

# YouTube's banner contract (Studio help, "Channel banner"): 2560x1440, under
# 6 MB, and only the centred 1546x423 is shown on every device.
W, H = 2560, 1440
SAFE_W, SAFE_H = 1546, 423
SAFE = ((W - SAFE_W) // 2, (H - SAFE_H) // 2,
        (W - SAFE_W) // 2 + SAFE_W, (H - SAFE_H) // 2 + SAFE_H)
MAX_BYTES = 6 * 1024 * 1024
KEYWORDS_MAX = 500           # brandingSettings.channel.keywords cap

UNITS = {"banner_insert": 50, "channel_update": 50, "read": 1,
         "playlist_insert": 50, "section_insert": 50}


class BrandingRefused(Exception):
    """A domain without branding, banner words that break the rules, or a
    banner that breaks YouTube's contract. Raised before any request."""


# ------------------------------------------------------------------ the spec

def spec() -> dict:
    return json.loads(SPEC_FILE.read_text())


def channel_domains(cfg: dict) -> list[str]:
    """The domains the channel carries, in shelf order: the rotation's
    weekday order, then allocated domains the rotation does not name."""
    rot = (((cfg.get("cadence") or {}).get("rotation") or {})
           .get("weekdays") or {})
    out: list[str] = []
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        d = rot.get(day)
        if d and d not in out:
            out.append(d)
    for d in ((cfg.get("domains") or {}).get("allocation") or {}):
        if d not in out:
            out.append(d)
    if not out:
        raise BrandingRefused("loop/config.json names no channel domain - "
                              "nothing to brand")
    return out


def _entry(sp: dict, d: str) -> dict:
    e = (sp.get("domains") or {}).get(d) or {}
    if not e.get("display") or not e.get("keywords"):
        raise BrandingRefused(
            f"DOMAIN_UNBRANDED: {d!r} is a channel domain (loop/config.json) "
            f"with no display name/keywords in {SPEC_FILE.relative_to(ROOT)}")
    return e


def display_names(cfg: dict, sp: dict | None = None) -> list[str]:
    sp = sp or spec()
    return [_entry(sp, d)["display"] for d in channel_domains(cfg)]


def domains_phrase(cfg: dict, sp: dict | None = None) -> str:
    """'the deep sea, the materials around you, and the food on your plate'."""
    names = display_names(cfg, sp)
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def description(cfg: dict) -> str:
    import channel_about as ca                             # noqa: PLC0415
    text = ca.read_about()
    ca.check_description(text)
    return text


def keywords(cfg: dict, sp: dict | None = None) -> str:
    """YouTube's keywords string: space-separated, multi-word terms quoted."""
    sp = sp or spec()
    terms = list(sp.get("channel_keywords") or [])
    for d in channel_domains(cfg):
        terms += _entry(sp, d)["keywords"]
    seen, out = set(), []
    for t in terms:
        k = t.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(f'"{t}"' if " " in t else t)
    s = " ".join(out)
    if len(s) > KEYWORDS_MAX:
        raise BrandingRefused(f"KEYWORDS_TOO_LONG: {len(s)} > {KEYWORDS_MAX}")
    return s


def candidate(sp: dict, name: str | None = None) -> tuple[str, dict]:
    name = name or sp.get("applied")
    cands = sp.get("candidates") or {}
    if name not in cands:
        raise BrandingRefused(f"no banner candidate {name!r}; have {sorted(cands)}")
    return name, cands[name]


def banner_text(cand: dict) -> str:
    """Every line under the logo, as one string - what V51 reads."""
    return " ".join(t for group in cand["lines"] for t in group)


def check_lines(text: str, sp: dict) -> list[str]:
    """The banner's words: the owner's two phrases present (case-insensitive,
    so the grammar may vary), the deep-sea-only clause absent."""
    bad = []
    low = (text or "").lower()
    if not low.strip():
        bad.append("the banner carries no text under the logo")
    for ph in sp.get("required_phrases") or []:
        if ph.lower() not in low:
            bad.append(f"banner text lacks {ph!r}")
    for w in sp.get("banned_wording") or []:
        if w.lower() in low:
            bad.append(f"banner text carries the deep-sea-only wording {w!r}")
    return bad


# ---------------------------------------------------------------- the banner

def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_record(sp: dict, key: str) -> dict:
    rec = (sp.get("images") or {}).get(key)
    if not rec:
        raise BrandingRefused(f"panel image {key!r} has no record in branding.json images")
    return rec


def panel_image(rec: dict):
    """Open a panel image only after its hash and its rights record check out."""
    from PIL import Image                                  # noqa: PLC0415
    path = (ROOT / rec["manifest"]).parent / rec["local_file"]
    if not path.exists():
        raise BrandingRefused(f"panel image missing: {path}")
    if _sha(path) != rec["sha256"]:
        raise BrandingRefused(f"panel image {path.name} does not match its "
                              f"recorded sha256 - refusing an unverified pixel")
    if rec["manifest"].endswith("branding.json"):
        r = rec.get("rights") or {}
        ok = bool(r.get("licence")) and r.get("commercial_use_permitted") is True
    else:
        man = json.loads((ROOT / rec["manifest"]).read_text())
        recs = man.get("assets") or man.get("index") or []
        ok = any(x.get("local_file") == rec["local_file"]
                 and x.get("sha256") == rec["sha256"] for x in recs)
    if not ok:
        raise BrandingRefused(f"{rec['local_file']} has no rights record in "
                              f"{rec['manifest']}")
    if not (rec.get("credit") or "").strip():
        raise BrandingRefused(f"{rec['local_file']}: no credit - attribution "
                              f"is never dropped")
    return Image.open(path).convert("RGB")


def _cover(im, box_w: int, box_h: int, fx: float, fy: float):
    """Scale `im` to cover box_w x box_h, centred as near (fx, fy) as the
    edges allow."""
    from PIL import Image                                  # noqa: PLC0415
    iw, ih = im.size
    s = max(box_w / iw, box_h / ih)
    big = im.resize((max(box_w, round(iw * s)), max(box_h, round(ih * s))),
                    Image.LANCZOS)
    x0 = min(max(0, round(fx * big.width - box_w / 2)), big.width - box_w)
    y0 = min(max(0, round(fy * big.height - box_h / 2)), big.height - box_h)
    return big.crop((x0, y0, x0 + box_w, y0 + box_h))


def layout(n: int) -> list[dict]:
    """Columns for n panels: the safe area split evenly; the first and last
    run out to the canvas edges so a TV sees picture, not black."""
    if n < 1:
        raise BrandingRefused("no banner panels")
    sx0, _, sx1, _ = SAFE
    edges = [sx0 + round(i * (sx1 - sx0) / n) for i in range(n + 1)]
    cols = []
    for i in range(n):
        ix0, ix1 = edges[i], edges[i + 1]
        cols.append({"col": (0 if i == 0 else ix0, 0, W if i == n - 1 else ix1, H),
                     "inner": (ix0, SAFE[1], ix1, SAFE[3])})
    return cols


# THE BANNER GRADE: one warm-dark, saturated treatment across every panel so
# the strip reads as one picture. Built on the thumbnail contract's split tone
# (visuals/thumb_contract.py GRADE: navy shadows, amber highlights) at a low
# mix, so a red jelly stays red and molten steel stays orange.
BANNER_GRADE = {"id": "hwk-banner-warm-dark-v1", "shadow": (8, 22, 40),
                "highlight": (255, 222, 168), "mix": 0.22, "contrast": 1.12,
                "saturation": 1.28, "exposure": 0.92}


def banner_grade(im):
    import thumb_contract as tc                            # noqa: PLC0415
    from PIL import ImageEnhance                           # noqa: PLC0415
    g = tc.grade(im, BANNER_GRADE)
    g = ImageEnhance.Color(g).enhance(BANNER_GRADE["saturation"])
    return ImageEnhance.Brightness(g).enhance(BANNER_GRADE["exposure"])


def _strip(sp: dict, cand: dict):
    """The panel strip: each image framed to its visible column, graded, and
    faded into its neighbour over FADE px; outside the safe area blurred and
    dimmed so nothing there reads as content a phone would crop."""
    import numpy as np                                     # noqa: PLC0415
    from PIL import Image, ImageFilter                     # noqa: PLC0415
    panels = cand["panels"]
    cols = layout(len(panels))
    fade = 90
    acc = np.zeros((H, W, 3), np.float32)
    wsum = np.zeros((H, W, 1), np.float32)
    art, credits = [], []
    for p, c in zip(panels, cols):
        rec = image_record(sp, p["image"])
        src = panel_image(rec)
        ix0, iy0, ix1, iy1 = c["inner"]
        cx0, _, cx1, _ = c["col"]
        x0, x1 = max(0, cx0 - fade), min(W, cx1 + fade)
        vis_w = (ix1 - ix0) + 2 * fade
        vis = _cover(src, vis_w, iy1 - iy0 + 2 * fade, *p["focus"])
        vis = np.asarray(banner_grade(vis)).astype(np.float32)
        # place the framed subject over its column; extend beyond with a
        # scaled copy so the canvas edge is covered on the outer columns
        layer = np.zeros((H, W, 3), np.float32)
        full = _cover(src, x1 - x0, H, *p["focus"])
        layer[:, x0:x1] = np.asarray(banner_grade(full)).astype(np.float32)
        vx0 = ix0 - fade
        sx_a, sx_b = max(0, vx0), min(W, vx0 + vis_w)
        layer[iy0 - fade:iy1 + fade, sx_a:sx_b] = vis[:, sx_a - vx0:sx_b - vx0]
        xs = np.arange(W, dtype=np.float32)
        left = cx0 if cx0 > 0 else -10**6
        right = cx1 if cx1 < W else 10**6
        w = np.clip((xs - (left - fade)) / (2 * fade), 0, 1) * \
            np.clip(((right + fade) - xs) / (2 * fade), 0, 1)
        acc += layer * w[None, :, None]
        wsum += np.broadcast_to(w[None, :, None], (H, W, 1))
        art.append(list(c["inner"]))
        credits.append((rec["credit"], c["inner"]))
    img = acc / np.maximum(wsum, 1e-6)
    sx0, sy0, sx1, sy1 = SAFE
    soft = np.asarray(Image.fromarray(img.clip(0, 255).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(22))).astype(np.float32) * 0.42
    yy, xx = np.mgrid[0:H, 0:W]
    dx = np.clip(np.maximum(sx0 - xx, xx - sx1) / 160.0, 0, 1)
    dy = np.clip(np.maximum(sy0 - yy, yy - sy1) / 160.0, 0, 1)
    out_w = np.maximum(dx, dy)[..., None]
    img = img * (1 - out_w) + soft * out_w
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB"), art, credits


def _lockup_metrics(d, cand: dict, k: float):
    """Fonts and line boxes for the logo lockup at scale k (k=1 is the
    original 2048 banner's geometry, visuals/brand.py)."""
    import design                                          # noqa: PLC0415
    from PIL import ImageFont                              # noqa: PLC0415
    word = ImageFont.truetype(design.F_DISPLAY, round(120 * k))
    sizes = [(round(46 * k), design.TEXT), (round(40 * k), design.MUTED)]
    groups = []
    for gi, group in enumerate(cand["lines"]):
        rows = []
        for li, t in enumerate(group):
            if gi == len(cand["lines"]) - 1:
                f = ImageFont.truetype(design.F_LABEL, round(31 * k))
                col = design.CYAN
            else:
                size, col = sizes[min(li, 1)]
                f = ImageFont.truetype(design.F_LABEL, size)
            rows.append((t, f, col))
        groups.append(rows)
    return word, groups


def build_banner(out: Path = BANNER, desktop: Path | None = DESKTOP,
                 name: str | None = None) -> dict:
    """Render one candidate. Returns the measured text and art boxes so the
    test checks pixels-as-built, not intentions."""
    from PIL import Image, ImageDraw                       # noqa: PLC0415
    import brand                                           # noqa: PLC0415
    import design                                          # noqa: PLC0415

    sp = spec()
    name, cand = candidate(sp, name)
    bad = check_lines(banner_text(cand), sp)
    if bad:
        raise BrandingRefused("; ".join(bad))
    canvas, art_boxes, credits = _strip(sp, cand)
    sx0, sy0, sx1, sy1 = SAFE
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    # Fit the ORIGINAL lockup (mark left, Georgia wordmark, label lines) to
    # the safe area: start at 1.25x the 2048 banner's geometry, shrink to fit.
    k = 1.06
    while True:
        word, groups = _lockup_metrics(probe, cand, k)
        wb = probe.textbbox((0, 0), "How We Know", font=word)
        rows_h, rows_w = [], [wb[2] - wb[0]]
        for gi, rows in enumerate(groups):
            for t, f, _ in rows:
                b = probe.textbbox((0, 0), t, font=f)
                rows_h.append((b, gi))
                rows_w.append(b[2] - b[0])
        gap_line, gap_group = round(10 * k), round(22 * k)
        text_h = (wb[3] - wb[1]) + gap_group + sum(b[3] - b[1] for b, _ in rows_h) \
            + gap_line * (len(rows_h) - 1) + gap_group * (len(groups) - 1)
        text_x_off = round(140 * k)              # brand.py: text at cx-330, mark at cx-470
        block_w = text_x_off + max(rows_w) + round(117 * k)
        if (text_h <= SAFE_H - 2 * 26 and block_w <= SAFE_W - 2 * 40) or k < 0.8:
            break
        k -= 0.02

    # dark scrim behind the lockup, so the type holds on any picture
    import numpy as np                                     # noqa: PLC0415
    bx0 = (W - block_w) // 2
    by0 = (H - text_h) // 2
    yy, xx = np.mgrid[0:H, 0:W]
    cxs, cys = bx0 + block_w / 2, by0 + text_h / 2
    rx, ry = block_w * 0.62, SAFE_H * 0.62
    r2 = ((xx - cxs) / rx) ** 2 + ((yy - cys) / ry) ** 2
    a = np.clip(1.15 - r2, 0, 1) ** 0.8 * 0.58
    ink = np.array(design.INK, np.float32)
    arr = np.asarray(canvas).astype(np.float32)
    arr = arr * (1 - a[..., None]) + ink * a[..., None]
    canvas = Image.fromarray(arr.clip(0, 255).astype(np.uint8)).convert("RGBA")

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    tx = bx0 + round(117 * k) + text_x_off
    y = by0 - wb[1]
    d.text((tx, y), "How We Know", font=word, fill=(*design.TEXT, 255))
    text_boxes = [{"text": "How We Know",
                   "box": [tx + wb[0], by0, tx + wb[2], by0 + wb[3] - wb[1]]}]
    word_mid = by0 + (wb[3] - wb[1]) / 2
    y = by0 + (wb[3] - wb[1]) + gap_group
    for gi, rows in enumerate(groups):
        if gi:
            y += gap_group - gap_line
        for t, f, col in rows:
            b = probe.textbbox((0, 0), t, font=f)
            d.text((tx - b[0] + round(4 * k), y - b[1]), t, font=f, fill=(*col, 240))
            text_boxes.append({"text": t, "box": [tx + round(4 * k), y,
                                                  tx + round(4 * k) + b[2] - b[0],
                                                  y + b[3] - b[1]]})
            y += (b[3] - b[1]) + gap_line
    # The mark, by visuals/brand.py's own mark(): same shapes, same palette.
    mcx = tx - text_x_off
    mcy = round((by0 + y) / 2)
    brand.mark(d, mcx, mcy, 1.5 * k)
    half = int(78 * 1.5 * k)
    mark_box = [mcx - half - 4, mcy - int(62 * 1.5 * k) - 6, mcx + half + 4,
                mcy + int(46 * 1.5 * k) + int(13 * 1.5 * k) + 4]
    text_boxes.append({"text": "logo mark", "box": mark_box})

    cf = ImageFont_truetype(design.F_LABEL, 17)
    for credit, (ix0, _, ix1, _) in credits:
        cb_ = d.textbbox((0, 0), credit, font=cf)
        x = ix0 + 12 - cb_[0]
        yb = sy1 - 10 - (cb_[3] - cb_[1]) - cb_[1]
        d.text((x, yb), credit, font=cf, fill=(235, 235, 235, 200),
               stroke_width=1, stroke_fill=(0, 0, 0, 160))
        text_boxes.append({"text": credit, "box": [x + cb_[0], yb + cb_[1],
                                                   x + cb_[2], yb + cb_[3]]})
    # a soft shadow of every glyph keeps the type legible on a phone without
    # a heavier scrim hiding the pictures
    from PIL import ImageFilter                            # noqa: PLC0415
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(ov.getchannel("A").filter(ImageFilter.GaussianBlur(6)).point(lambda v: min(255, int(v * 0.9))))
    canvas = Image.alpha_composite(canvas, sh)
    canvas = Image.alpha_composite(canvas, ov).convert("RGB")

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "PNG", optimize=True)
    if desktop is not None and desktop.parent.exists():
        canvas.save(desktop, "PNG", optimize=True)
    meta = {"candidate": name, "path": str(out), "size": list(canvas.size),
            "bytes": out.stat().st_size, "sha256": _sha(out),
            "text": banner_text(cand), "text_boxes": text_boxes,
            "art_boxes": art_boxes, "safe_area": list(SAFE), "scale": round(k, 2),
            "panels": [p["domain"] for p in cand["panels"]]}
    problems = check_banner_meta(meta)
    if problems:
        raise BrandingRefused("; ".join(problems))
    return meta


def ImageFont_truetype(path: str, size: int):
    from PIL import ImageFont                              # noqa: PLC0415
    return ImageFont.truetype(path, size)


def build_candidates(desktop_dir: Path | None = CANDIDATES_DIR) -> dict:
    """Every candidate to channel/branding/candidates/<X>.png (and the
    Desktop folder), the applied one also to banner.png."""
    sp = spec()
    out = {}
    for name in sorted(sp["candidates"]):
        dst = CANDIDATE_PNG.parent / f"banner_{name}.png"
        desk = (desktop_dir / f"how-we-know-banner-{name}.png") if desktop_dir else None
        if desk is not None:
            desk.parent.mkdir(parents=True, exist_ok=True)
        out[name] = build_banner(out=dst, desktop=desk, name=name)
    return out


def check_banner_meta(meta: dict) -> list[str]:
    bad = []
    if tuple(meta["size"]) != (W, H):
        bad.append(f"banner is {meta['size']}, not {W}x{H}")
    if meta["bytes"] >= MAX_BYTES:
        bad.append(f"banner is {meta['bytes']} bytes (YouTube max {MAX_BYTES})")
    sx0, sy0, sx1, sy1 = SAFE
    for b in meta["text_boxes"] + [{"text": "panel art", "box": a}
                                   for a in meta["art_boxes"]]:
        x0, y0, x1, y1 = b["box"]
        if x0 < sx0 or y0 < sy0 or x1 > sx1 or y1 > sy1:
            bad.append(f"{b['text']!r} at {b['box']} leaves the safe area {list(SAFE)}")
    return bad


# ----------------------------------------------------------- the live guard

def check_live(record: dict, cfg: dict, sp: dict | None = None) -> list[str]:
    """V51's core: what the channel shows must carry every channel domain.
    `record` is loop/state/channel_branding.json (or a live read shaped like
    it): banner_url, description, keywords, banner_text."""
    sp = sp or spec()
    bad: list[str] = []
    try:
        names = display_names(cfg, sp)
    except BrandingRefused as e:
        return [str(e)]
    if not (record.get("banner_url") or "").strip():
        bad.append("the channel has no banner URL (brandingSettings.image."
                   "bannerExternalUrl is empty)")
    desc = (record.get("description") or "").lower()
    for d, n in zip(channel_domains(cfg), names):
        if n.lower() not in desc:
            bad.append(f"the live channel description does not name {d} "
                       f"({n!r}) - re-run loop/channel_branding.py")
    if "how we know what we know" not in desc:
        bad.append("the live description does not carry 'How we know what we know'")
    kw = (record.get("keywords") or "").lower()
    for d in channel_domains(cfg):
        if not any(k.lower() in kw for k in _entry(sp, d)["keywords"]):
            bad.append(f"the live channel keywords carry none of {d}'s")
    for w in sp.get("banned_wording") or []:
        if w.lower() in desc:
            bad.append(f"the live description still says {w!r}")
    bad += [m for m in check_lines(record.get("banner_text") or "", sp)]
    return bad


# ------------------------------------------------------------------ the API

class Client:
    def __init__(self, token: str):
        self.token = token
        self.units = 0

    def call(self, method: str, url: str, params: dict | None = None,
             body=None, raw: bytes | None = None, ctype: str | None = None,
             units: int = 1) -> dict:
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None)
        hdr = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            hdr["Content-Type"] = ctype or "application/json; charset=UTF-8"
        req = urllib.request.Request(url + q, data=data, method=method, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = r.read()
        finally:
            self.units += units
        return json.loads(out) if out else {}


def _read_channel(c: Client) -> dict:
    data = c.call("GET", f"{API}/channels",
                  {"part": "brandingSettings,snippet", "mine": "true"})
    items = data.get("items") or []
    if not items:
        raise BrandingRefused("channels.list (mine=true) returned no channel")
    return items[0]


def _record_of(ch: dict, sp: dict, banner_sha: str | None,
               cand_name: str | None = None) -> dict:
    b = ch.get("brandingSettings") or {}
    return {"read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "channel_id": ch.get("id"),
            "banner_url": (b.get("image") or {}).get("bannerExternalUrl") or "",
            "banner_sha256": banner_sha,
            "banner_candidate": candidate(sp, cand_name)[0],
            "banner_text": banner_text(candidate(sp, cand_name)[1]),
            "description": (b.get("channel") or {}).get("description") or "",
            "keywords": (b.get("channel") or {}).get("keywords") or ""}


def _url_live(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0


def _ensure_playlists(c: Client, cfg: dict, dry: bool, log: list) -> dict:
    """Every channel domain's playlist, found by title before created, kept
    where the handoff lane reads it (loop/state/playlists.json)."""
    import handoff as ho                                   # noqa: PLC0415
    pl = ho.load_playlists()
    doms = channel_domains(cfg)
    missing = [d for d in doms if not (pl["playlists"].get(d) or {}).get("id")]
    for d in missing:
        if d not in ho.PLAYLIST_TITLES:
            raise BrandingRefused(f"{d} has no playlist title in loop/handoff.py "
                                  f"PLAYLIST_TITLES")
    mine, u = ho.list_all(_Adapter(c), "playlists", {"part": "snippet,status", "mine": "true"})
    by_id = {p["id"]: p for p in mine}
    by_title = {(p.get("snippet") or {}).get("title"): p["id"] for p in mine}
    for d in doms:
        rec = pl["playlists"].get(d) or {}
        if rec.get("id") and rec["id"] not in by_id:
            log.append(f"playlist {rec['id']} recorded for {d} is not on the "
                       f"channel - finding it again by title")
            rec = {}
        if rec.get("id"):
            continue
        title = ho.PLAYLIST_TITLES[d]
        if by_title.get(title):
            pl["playlists"][d] = {"id": by_title[title], "title": title,
                                  "adopted_at": _now()}
            log.append(f"adopted playlist {by_title[title]} for {d}")
            continue
        if dry:
            log.append(f"--dry-run: would create public playlist {title!r}")
            continue
        got = c.call("POST", f"{API}/playlists", {"part": "snippet,status"},
                     {"snippet": {"title": title,
                                  "description": ho.PLAYLIST_DESCRIPTIONS[d]},
                      "status": {"privacyStatus": "public"}},
                     units=UNITS["playlist_insert"])
        pl["playlists"][d] = {"id": got["id"], "title": title,
                              "created_at": _now(), "by": "channel_branding"}
        log.append(f"created public playlist {got['id']} {title!r} for {d}")
    if not dry:
        ho.write_json(ho.PLAYLISTS, pl)
    return pl


class _Adapter:
    """handoff.list_all speaks api_get; count its reads on our Client."""
    def __init__(self, c: Client):
        self.c = c

    def api_get(self, path: str, params: dict) -> dict:
        return self.c.call("GET", f"{API}/{path}", params)


def _ensure_sections(c: Client, cfg: dict, pl: dict, dry: bool, log: list) -> dict:
    """One singlePlaylist section per channel domain, rotation order. A
    section that already shows the playlist is kept; YouTube's refusal is
    recorded per domain (handoff's convention), never retried in a loop."""
    import handoff as ho                                   # noqa: PLC0415
    secs = c.call("GET", f"{API}/channelSections",
                  {"part": "snippet,contentDetails", "mine": "true"}).get("items") or []
    shown = {}
    for s in secs:
        for p in ((s.get("contentDetails") or {}).get("playlists") or []):
            shown[p] = s["id"]
    out = {}
    pos = len(secs)
    for d in channel_domains(cfg):
        pid = (pl["playlists"].get(d) or {}).get("id")
        if not pid:
            out[d] = {"skipped": "no playlist id"}
            continue
        if pid in shown:
            pl["sections"][d] = {"id": shown[pid], "playlist": pid, "at": _now()}
            out[d] = {"id": shown[pid]}
            continue
        if dry:
            out[d] = {"would_create": pid}
            continue
        try:
            got = c.call("POST", f"{API}/channelSections", {"part": "snippet,contentDetails"},
                         {"snippet": {"type": "singlePlaylist", "position": pos},
                          "contentDetails": {"playlists": [pid]}},
                         units=UNITS["section_insert"])
            pos += 1
            pl["sections"][d] = {"id": got["id"], "playlist": pid, "at": _now()}
            out[d] = {"id": got["id"]}
            log.append(f"created section {got['id']} for {d}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:600]
            reason = ""
            try:
                reason = json.loads(body)["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError, TypeError):
                pass
            pl["sections"][d] = {"refused": f"HTTP {e.code} {reason}".strip(),
                                 "playlist": pid, "at": _now(),
                                 "by": "channel_branding"}
            out[d] = {"refused": f"HTTP {e.code} {reason}".strip()}
            log.append(f"section for {d} refused: HTTP {e.code} {reason}")
    if not dry:
        ho.write_json(ho.PLAYLISTS, pl)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(dry: bool, cand: str | None = None) -> int:
    import quota as q                                      # noqa: PLC0415
    cfg = config()
    sp = spec()
    try:
        build_candidates()
        meta = build_banner(name=cand)
        desc = description(cfg)
        kw = keywords(cfg, sp)
    except BrandingRefused as e:
        print(f"FATAL [BRANDING_REFUSED]: {e}")
        return 1
    print(f"banner built: {meta['path']} ({meta['bytes']} bytes, sha {meta['sha256'][:12]})")
    if DRY_RUN:
        print("LOOP_DRY_RUN=1 - built and composed; no credential loaded, "
              "nothing sent.")
        return 0

    import upload as up                                    # noqa: PLC0415
    import tokens as auth                                  # noqa: PLC0415
    creds = up.load_credentials(cfg)
    if not creds or creds.get("unusable"):
        code, msg, unblock = up.credential_stop(creds, cfg)
        print(f"FATAL [{code}]: {msg}\n{unblock}")
        return 1
    token = up.access_token(creds)
    who = auth.channel(token)
    if not who["ok"] or not who["matches_expected"]:
        print("FATAL: the credential is not the expected channel; refusing.")
        return 1
    worst = (UNITS["banner_insert"] + UNITS["channel_update"]
             + UNITS["playlist_insert"] * len(channel_domains(cfg))
             + UNITS["section_insert"] * len(channel_domains(cfg)) + 10)
    if not dry and q.units_affordable(worst, 1, reserve=q.shorts_reserve()) < 1:
        print(f"QUOTA_DEFERRED: {worst} units would cut into the Shorts reserve "
              f"today; re-run after {q.next_reset()}.")
        return 1

    c = Client(token)
    log: list[str] = []
    try:
        live = _read_channel(c)
        prior = json.loads(STATE.read_text()) if STATE.exists() else {}
        branding = live.get("brandingSettings") or {}
        cur_url = (branding.get("image") or {}).get("bannerExternalUrl") or ""
        banner_url = cur_url
        if not (cur_url and prior.get("banner_sha256") == meta["sha256"]
                and prior.get("banner_url") == cur_url):
            if dry:
                log.append("--dry-run: would upload the banner (channelBanners.insert)")
            else:
                got = c.call("POST", f"{UPLOAD_API}/channelBanners/insert",
                             {"uploadType": "media"}, raw=BANNER.read_bytes(),
                             ctype="image/png", units=UNITS["banner_insert"])
                banner_url = got.get("url") or ""
                if not banner_url:
                    print("FATAL: channelBanners.insert returned no url")
                    return 1
                log.append("uploaded the banner")
        import channel_about as ca                         # noqa: PLC0415
        cur_ch = branding.get("channel") or {}
        merged = ca.merge_branding(cur_ch, desc)
        merged["keywords"] = kw
        need_update = (banner_url != cur_url
                       or (cur_ch.get("description") or "").strip() != desc.strip()
                       or (cur_ch.get("keywords") or "").strip() != kw)
        if need_update and not dry:
            c.call("PUT", f"{API}/channels", {"part": "brandingSettings"},
                   {"id": live["id"], "brandingSettings": {
                       "channel": merged,
                       "image": {"bannerExternalUrl": banner_url}}},
                   units=UNITS["channel_update"])
            log.append("channels.update brandingSettings: banner, description, keywords")
        elif need_update:
            log.append("--dry-run: would update brandingSettings")
        else:
            log.append("banner, description and keywords already live - no write")

        pl = _ensure_playlists(c, cfg, dry, log)
        sections = _ensure_sections(c, cfg, pl, dry, log)

        back = _read_channel(c)
        rec = _record_of(back, sp, meta["sha256"], meta["candidate"])
    finally:
        if not dry and c.units:
            q.spend(c.units, LANE)
    for line in log:
        print(" -", line)
    if dry:
        print(f"--dry-run: {c.units} read units; nothing written.")
        return 0
    rec["banner_http"] = _url_live(rec["banner_url"]) if rec["banner_url"] else 0
    rec["sections"] = sections
    rec["playlists"] = {d: (pl["playlists"].get(d) or {}).get("id")
                        for d in channel_domains(cfg)}
    rec["units_spent"] = c.units
    STATE.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    bad = check_live(rec, cfg, sp)
    if rec["banner_http"] != 200:
        bad.append(f"banner URL answered HTTP {rec['banner_http']}")
    if banner_url and rec["banner_url"] != banner_url and need_update:
        log.append("note: read-back banner URL differs from the uploaded one")
    print(f"read back: banner {rec['banner_url'][:60]}... HTTP {rec['banner_http']}; "
          f"{c.units} units booked to lane {LANE!r}")
    if bad:
        for b in bad:
            print("FAIL:", b)
        return 1
    print("VERIFIED: banner live, description and keywords name every channel domain.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="build the banner only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--candidate", help="apply this banner candidate (A, B, C) "
                    "instead of branding.json `applied`")
    a = ap.parse_args()
    if a.build:
        for n, m in build_candidates().items():
            print(n, json.dumps({k: m[k] for k in ("path", "bytes", "scale")}))
        m = build_banner(name=a.candidate)
        print("applied", m["candidate"], json.dumps({k: m[k] for k in ("path", "bytes", "sha256")}))
        return 0
    return run(dry=a.dry_run, cand=a.candidate)


if __name__ == "__main__":
    raise SystemExit(main())
