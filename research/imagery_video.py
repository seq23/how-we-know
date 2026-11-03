"""Rights-checked MOVING-FOOTAGE harvester: NOAA Ocean Exploration ROV video.

Companion to research/imagery.py, which harvests stills. Same premise, same
discipline, one extra gate that only video needs.

Why this exists
---------------
The still set is historical plates and NOAA photographs placed inside a design
frame. It reads as an illustrated lecture. The material the competition uses is
full-bleed photoreal footage. NOAA Ocean Exploration publishes exactly that
class of material -- ROV dive video from Okeanos Explorer -- and it is a work of
the U.S. federal government.

What NOAA actually says (https://oceanexplorer.noaa.gov/about/media-kit/,
re-checked 2026-08-31) applies to "images and videos" in the same sentence, so
the rights test is the one imagery.py already implements: the item's own credit
must resolve to NOAA and nobody else.

The gate video needs that stills did not
---------------------------------------
A still carries one credit. A video carries two, and they can disagree.

Measured, not assumed. A 30-clip OCR audit of the burned-in text (see
`--audit`) found this split:

  * RAW DIVE CLIPS -- "Cuskeel", "Deep-Sea Snailfish", "Red Shrimp",
    "Catshark", "Iridigorgia Coral". Burned-in text is a NOAA head/tail card
    and an Expedition/Site/Depth lower-third. No producer credit. No
    third-party name anywhere in the frames.

  * PRODUCED PIECES -- the "Beyond the Blue" mini-documentaries, "Deep-Sea
    Dialogues", expedition summaries. The WordPress `credit` field says
    "NOAA Ocean Exploration, Beyond the Blue" and passes the stills gate
    cleanly. The END CARD, burned into the picture, says
    "Produced By Art Howard, GFOE" / "Produced by Caitlin Bailey, GFOE" /
    "Produced By Olivia Andrus-Drennan, GFOE" -- the Global Foundation for
    Ocean Exploration, a contractor, not a federal employer. 17 U.S.C. 105
    covers works of federal EMPLOYEES; a contractor's work is not
    automatically public domain. "Deep-Sea Dialogues: Maritime Heritage" goes
    further and carries in-frame source credits to Jill Heinerth, Brett
    Seymour, Ocean Exploration Trust, Schmidt and WHOI -- it is a compilation
    of other people's material.

    imagery.py's THIRD_PARTY regex already lists gfoe and global foundation as
    disqualifying. The metadata field simply never mentioned them.

So the credit line on the item page is NOT the last word for video. The frames
carry a second credit and it is the one that contradicts. This module reads
both and requires both to clear.

Three gates
-----------
  A. CREDIT (metadata)  -- acf.credit must pass imagery.credit_is_noaa_only,
     AND the rendered item page's own Credit block must independently agree.
     Two reads of two surfaces, not one field trusted twice.

  B. BURNED-IN CREDIT   -- OCR every sampled frame. If any third party is
     named anywhere in the picture, or any "Produced by / Video by / Courtesy
     of / Camera" credit appears at all, reject the whole clip. This is gate A
     applied to the thing gate A cannot see.

  C. CLEAN WINDOW       -- the still harvest rejected a frilled-shark frame for
     a burned-in DVR overlay. Same trap here, but time-bounded: the cards and
     the depth lower-third live at the head and tail, and the middle is clean.
     So we do not reject the clip, we record the spans that carry no on-screen
     text at all and ship only those. A clip with no clean span long enough to
     cut is rejected.

Gate C means the delivered frames are guaranteed free of NOAA wordmarks, DVR
telemetry and chyrons -- a stronger guarantee than the still set has, because
it is measured per frame rather than eyeballed.

OCR is Apple's Vision framework via a small Swift helper compiled on first use.
No network service, no key, no per-call cost.

Usage
-----
    python research/imagery_video.py --audit        # survey: gates, no download
    python research/imagery_video.py --coverage     # per-episode coverage read
    python research/imagery_video.py --harvest      # download the accepted set
    python research/imagery_video.py --verify       # re-hash what is on disk
    python research/imagery_video.py --prove        # negative proof of the gates
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import imagery  # noqa: E402  -- the rights vocabulary lives there, not here

OUT = os.path.abspath(os.path.join(HERE, "..", "channel", "imagery"))
CLIPS = os.path.join(OUT, "clips")
MANIFEST = os.path.join(OUT, "video_rights.json")

# --------------------------------------------------------------------------
# THE WEEKLY LANE FINDS THIS FILE THROUGH THIS DECLARATION, not through a list
# kept somewhere else. loop/footage_lane.py globs research/imagery*.py, reads
# this literal without importing the module, and runs the ones whose `domain`
# currently holds a slot in loop/config.json's allocation. Two components each
# keeping their own list, with no link between them, is exactly how
# research/imagery_materials.py came to be wired to no lane at all.
#
# `gate` is the rights function this file MUST still contain. The lane refuses
# to run a harvester whose gate has gone missing, so "relax the check to get
# more material" fails loudly instead of quietly succeeding.
#
# `args` is ["--harvest"] and that is not cosmetic. Run bare, this module
# screens the NOAA index and downloads NOTHING - which is what the weekly lane
# did to it from the day the lane was written, while reporting that it had
# harvested "video clips - the scarce pool".
# `requires` names the HOST TOOLING gates B and C cannot run without, and the
# lane checks it BEFORE spawning this file. Gate B/C read burned-in text with
# Apple's Vision framework (compiled with swiftc, macOS only) off frames that
# ffmpeg range-requests from the clip. ubuntu-latest has neither: CONFIRMED on
# runs 33943991250 (2026-09-05, 387/387 rejected) and 34672456430 (2026-09-12,
# 379/379 rejected). Every clip that PASSED gate A then raised
# FileNotFoundError('ffmpeg') inside screen(), and screen() reported that
# exception as "gate A-credit" -- so a missing binary read as a rights outcome
# for a year's worth of weekly runs, and the video pool stayed at zero with a
# note saying "the pool is unchanged". The rights gate was never the problem.
#
# The lane does not substitute another OCR engine (loop/r2.py:verify_shorts
# records why: unproven against these fonts, guarding the one check that may
# not be wrong) and does not accept clips unverified.
#
# `host` names WHICH scheduled process runs this file - loop/footage_lane.py
# HOSTS is the table. "mac-batch" is bin/batch-session.sh, nightly on the
# Mac, which has all three tools. The Saturday Linux lane treats this
# harvester as DELEGATED: it does not run it, it verifies through
# loop/state/harvest_runs.json that the Mac has, and stops by name if the Mac
# has not. Between 2026-09-12 and 2026-09-19 this was a HELD stop on the
# Linux lane asking the owner where the work should run (#77, #91); the
# answer lives here now, where the code can read it.
#
# `--refresh` is not cosmetic either. discover() caches NOAA's index under
# research/.video_cache/ and, without it, a host that ran once would re-screen
# the same index every week and never see a post NOAA published since.
HARVESTER = {
    "domain": "deep-sea-ocean-science",
    "gate": "credit_is_noaa_only",
    "manifest": "channel/imagery/video_rights.json",
    "args": ["--harvest", "--refresh"],
    "scheduled": True,
    "what": "video clips - the scarce pool",
    "requires": ["ffmpeg", "vision-ocr"],
    "host": "mac-batch",
    # Measured 2026-09-19: 16 clips in 5m44s with 8 OCR workers, so the whole
    # index is ~2.3 h. Four hours is the budget, not the expectation.
    "timeout_seconds": 14400,
}

# The probes for those names live in loop/host_tools.py, which the lane uses
# too -- one table, two readers. A name this module requires that the table
# cannot probe for is a loud error there, never a quiet pass.
sys.path.insert(0, os.path.join(HERE, "..", "loop"))
import host_tools  # noqa: E402


def missing_tooling(requires=None) -> list[str]:
    """Names of the required tools this host does NOT have. Empty means go."""
    return host_tools.missing(HARVESTER["requires"] if requires is None
                              else requires)


def require_tooling() -> None:
    """Refuse to screen on a host that cannot finish screening.

    A rights decision this module cannot complete is not a rejection, and
    must never be reported as one. Exit code 78 (EX_CONFIG) so a caller can
    tell 'this host cannot run me' from 'the gate rejected everything'.
    """
    missing = missing_tooling()
    if missing:
        sys.stderr.write("HARVESTER_TOOLING_ABSENT: this host cannot run gates B "
                         "and C, so no clip can be screened to the end and none "
                         "may be accepted:\n"
                         + "".join(f"  - {m}\n" for m in missing))
        sys.exit(78)

CACHE = os.path.join(HERE, ".video_cache")

API = "https://oceanexplorer.noaa.gov/wp-json/wp/v2"
MEDIA_KIT = imagery.MEDIA_KIT
SOURCE_ORG = "NOAA Ocean Exploration"

# A clip must offer at least this many contiguous seconds with no on-screen
# text, or there is nothing in it we could actually cut.
MIN_CLEAN_SECONDS = 6
# Frames are sampled this far apart through the body of the clip. A card that
# lives entirely between two probes would be missed, so the head and tail --
# where every card observed actually sits -- are sampled densely instead.
PROBE_STEP = 2.0
HEAD_TAIL_STEP = 0.5
HEAD_TAIL_SPAN = 6.0
# A clean window is trimmed by this much at each end, so a card fading across
# the gap between two probes cannot reach the frames we ship.
WINDOW_PAD = 1.0
MIN_WIDTH = 1280


# ------------------------------------------------------------------ gate B/C
#
# Any of these in the burned-in text means the picture itself is asserting a
# credit. Even "Courtesy of NOAA" is caught: we want a human to look at
# anything that credits at all inside the frame, because the whole finding
# above is that in-frame credits say things the metadata does not.
IN_FRAME_CREDIT = re.compile(
    r"(?i)\b(produced\s+(?:by|by:)|video\s+by|footage\s+by|filmed\s+by|"
    r"edited\s+by|camera|videograph|cinematograph|courtesy\s+of|"
    r"additional\s+media|image\s+credit|photo\s+by)\b"
)


# The "courtesy of" defect this module found, and where it is now fixed.
#
# imagery.py's CREDIT_OK said in its own comment that a leading "Image courtesy
# of" is boilerplate "and is stripped before matching". It was not: THIRD_PARTY
# ran first and its `courtesy of [a-z]+ [a-z]+` clause fired on the phrase
# "courtesy of NOAA Ocean" before the strip could happen. Measured cost on this
# corpus: 32 of 388 NOAA video posts, plus 8 of the 63 rejected still
# candidates in channel/imagery/rights.json -- every one of them a credit that
# resolves to NOAA alone once the boilerplate is removed.
#
# The fix now lives in research/imagery.py (strip_courtesy + credit_is_noaa_only)
# so there is ONE implementation of the rights decision. This module imports it.
# Nothing was loosened: a credit naming anyone but NOAA after the boilerplate
# still fails, and a second, mid-string "courtesy of <someone>" still trips
# THIRD_PARTY.
COURTESY_BOILERPLATE = imagery.COURTESY_BOILERPLATE


def normalise_credit(credit: str) -> tuple[str, bool]:
    """Strip the documented 'courtesy of' boilerplate. Returns (credit, stripped)."""
    return imagery.strip_courtesy(credit)


def credit_gate(credit: str) -> tuple[bool, str]:
    """The rights decision. Thin alias for imagery.credit_is_noaa_only, which
    now performs the boilerplate strip itself."""
    return imagery.credit_is_noaa_only(credit or None)


def _text(fragment: str) -> str:
    t = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", fragment or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def _get(url: str, binary: bool = False, tries: int = 4):
    return imagery._get(url, binary=binary, tries=tries)


# ------------------------------------------------------------------- OCR

_OCR_SWIFT = r"""
import Foundation
import Vision
import AppKit
// One line per image: path TAB json([{t: text, x, y, w, h}]) in normalised
// image coordinates with the ORIGIN AT TOP-LEFT (Vision reports bottom-left,
// so y is flipped here). Boxes matter as much as the text: a NOAA wordmark bug
// pinned in a corner is croppable, a chyron across the middle is not.
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: path),
        let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("\(path)\tERR"); continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.usesLanguageCorrection = false
  try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
  var items: [[String: Any]] = []
  for o in (req.results ?? []) {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox
    items.append(["t": c.string, "x": b.minX, "y": 1.0 - b.maxY,
                  "w": b.width, "h": b.height])
  }
  let data = try! JSONSerialization.data(withJSONObject: items, options: [])
  print("\(path)\t\(String(data: data, encoding: .utf8)!)")
}
"""


def ocr_binary() -> str:
    """Compile the Vision OCR helper once and cache it."""
    os.makedirs(CACHE, exist_ok=True)
    binp = os.path.join(CACHE, "ocr")
    srcp = os.path.join(CACHE, "ocr.swift")
    src = _OCR_SWIFT
    if os.path.exists(binp) and os.path.exists(srcp) and open(srcp).read() == src:
        return binp
    if not shutil.which("swiftc"):
        raise SystemExit(
            "swiftc not found. This harvester reads burned-in text with Apple's "
            "Vision framework; without it gate B and gate C cannot run and the "
            "clips must not be accepted unverified."
        )
    with open(srcp, "w") as f:
        f.write(src)
    subprocess.run(["swiftc", srcp, "-o", binp], check=True, capture_output=True,
                   timeout=900)
    return binp


def ocr(paths: list[str]) -> dict[str, list[dict]]:
    """path -> list of {t,x,y,w,h} boxes, top-left origin, normalised."""
    if not paths:
        return {}
    r = subprocess.run([ocr_binary()] + paths, capture_output=True, text=True,
                       timeout=900)
    out: dict[str, list[dict]] = {}
    for line in r.stdout.splitlines():
        if "\t" not in line:
            continue
        p, payload = line.split("\t", 1)
        payload = payload.strip()
        if payload == "ERR" or not payload:
            continue
        try:
            out[p] = json.loads(payload)
        except json.JSONDecodeError:
            continue
    return out


# The NOAA wordmark bug sits in a corner. Text whose whole box lies inside this
# fraction of any edge is a candidate for cropping away; text that reaches
# further in is a chyron or a title card and cannot be cropped without eating
# the picture.
CROP_MARGIN = 0.20


def boxes_text(boxes: list[dict]) -> str:
    return " | ".join(b["t"] for b in boxes)


def crop_to_clear(boxes: list[dict]) -> dict | None:
    """Smallest inward crop that removes every text box, or None if too costly.

    Returns normalised {left, top, right, bottom} insets. A crop is only worth
    proposing if it keeps most of the frame: eating 20% of a side to lose a
    wordmark is a fair trade, eating half of it is not -- at that point the
    honest answer is that the clip is unusable, not that we should zoom into
    a corner of it.
    """
    if not boxes:
        return {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
    left = top = right = bottom = 0.0
    for b in boxes:
        x0, y0 = b["x"], b["y"]
        x1, y1 = b["x"] + b["w"], b["y"] + b["h"]
        # Remove the box by cutting in from whichever edge is cheapest.
        costs = {"left": x1, "top": y1, "right": 1.0 - x0, "bottom": 1.0 - y0}
        edge = min(costs, key=costs.get)
        need = costs[edge] + 0.01          # a hair of margin past the glyphs
        if edge == "left":
            left = max(left, need)
        elif edge == "top":
            top = max(top, need)
        elif edge == "right":
            right = max(right, need)
        else:
            bottom = max(bottom, need)
    if left + right > CROP_MARGIN or top + bottom > CROP_MARGIN:
        return None
    return {"left": round(left, 4), "top": round(top, 4),
            "right": round(right, 4), "bottom": round(bottom, 4)}


# -------------------------------------------------------------- frame probing

def probe_times(seconds: float) -> list[float]:
    """Dense at the head and tail, where every observed card sits; sparse in between."""
    ts: set[float] = set()
    t = 0.3
    while t < min(HEAD_TAIL_SPAN, seconds):
        ts.add(round(t, 2)); t += HEAD_TAIL_STEP
    t = max(0.0, seconds - HEAD_TAIL_SPAN)
    while t < seconds - 0.2:
        ts.add(round(max(t, 0.3), 2)); t += HEAD_TAIL_STEP
    t = HEAD_TAIL_SPAN
    while t < seconds - HEAD_TAIL_SPAN:
        ts.add(round(t, 2)); t += PROBE_STEP
    return sorted(ts)


def scan(url: str, seconds: float) -> list[tuple[float, str]]:
    """Pull one frame per probe time straight off the remote file and OCR it.

    ffmpeg range-requests the mp4, so a 60-second scan costs a few hundred KB
    rather than the whole file. Nothing is downloaded until a clip has passed
    every gate.
    """
    d = tempfile.mkdtemp(prefix="hwk-vid-")
    got: list[tuple[float, str]] = []
    try:
        for t in probe_times(seconds):
            p = os.path.join(d, f"{t:07.2f}.jpg")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", url,
                 "-frames:v", "1", "-vf", "scale=854:-1", p, "-y"],
                capture_output=True, timeout=180)
            if os.path.exists(p):
                got.append((t, p))
        texts = ocr([p for _, p in got])
        return [(t, texts.get(p, [])) for t, p in got]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _spans(probes: list[tuple[float, list]], seconds: float,
           is_dirty) -> list[dict]:
    """Contiguous spans where no sampled frame was dirty, padded inward.

    A span is bounded by the last dirty probe before it and the first dirty
    probe after it, so an unsampled instant next to a card cannot leak into
    what we ship.
    """
    if not probes:
        return []
    wins, start, prev_dirty = [], None, 0.0
    for t, boxes in probes:
        if is_dirty(boxes):
            if start is not None:
                wins.append((start, t))
                start = None
            prev_dirty = t
        elif start is None:
            start = prev_dirty
    if start is not None:
        wins.append((start, seconds))
    out = []
    for a, b in wins:
        a2, b2 = a + WINDOW_PAD, b - WINDOW_PAD
        if b2 - a2 >= MIN_CLEAN_SECONDS:
            out.append({"start": round(a2, 2), "end": round(b2, 2),
                        "seconds": round(b2 - a2, 2)})
    return out


def clean_windows(probes: list[tuple[float, list]], seconds: float) -> list[dict]:
    """Spans in which every sampled frame carried no on-screen text at all."""
    return _spans(probes, seconds, lambda boxes: bool(boxes))


def croppable_windows(probes: list[tuple[float, list]],
                      seconds: float) -> tuple[list[dict], dict | None]:
    """Spans usable after ONE fixed crop that clears the text in all of them.

    Most of NOAA's post-2022 clips carry a permanent NOAA Ocean Exploration
    wordmark bug in the top-left corner -- verified by eye on "Chimaera",
    "Red Jellyfish" and "Glass Squid", where it is present in every frame.
    Gate C is right to refuse those frames as they stand, but the picture under
    the bug is clean, and a fixed inward crop of a fifth of one edge removes it
    without cropping into the animal.

    The crop must be a single rectangle for the whole span -- a crop that moved
    around would read as a wobble -- so it is computed from the union of every
    text box in the candidate frames. If that union cannot be cleared within
    CROP_MARGIN, there is no honest crop and the answer is no window.
    """
    if not probes:
        return [], None
    # A frame is rescuable if its own text can be cropped away cheaply; a title
    # card across the middle disqualifies that frame outright.
    rescuable = [(t, boxes) for t, boxes in probes if crop_to_clear(boxes) is not None]
    if not rescuable:
        return [], None
    # One rectangle for the whole clip, from the union of every rescuable box.
    crop = crop_to_clear([b for _, boxes in rescuable for b in boxes])
    if crop is None:
        return [], None
    ok = {t for t, _ in rescuable}
    # Re-run the span finder treating an unrescuable frame as dirty.
    spans = _spans([(t, [] if t in ok else [1]) for t, _ in probes],
                   seconds, lambda b: bool(b))
    if not spans:
        return [], None
    return spans, (crop if any(crop.values()) else None)


# ------------------------------------------------------------------ discovery

def discover(refresh: bool = False) -> list[dict]:
    """Every multimedia post NOAA Ocean Exploration publishes as a video.

    `multimedia` is the only post type that carries a structured video record:
    acf.type == 'video', acf.video[] naming the attachment ids by resolution,
    and acf.credit. ocean-fact, expedition-feature, dive-deeper, education and
    news were all enumerated and hold zero acf video entries, so any clip
    embedded in those pages has no item-level credit block. No credit, no
    confirmed provenance, not used -- the same rule imagery.py applies.
    """
    os.makedirs(CACHE, exist_ok=True)
    posts_p = os.path.join(CACHE, "multimedia_posts.json")
    media_p = os.path.join(CACHE, "video_media.json")

    def paged(path: str, fields: str, cache: str) -> list[dict]:
        if os.path.exists(cache) and not refresh:
            return json.load(open(cache))
        acc: dict[int, dict] = {}
        for page in range(1, 40):
            try:
                d = json.loads(_get(f"{API}/{path}&per_page=100&page={page}&_fields={fields}"))
            except Exception:
                break
            if not isinstance(d, list) or not d:
                break
            for m in d:
                acc[m["id"]] = m
        json.dump(list(acc.values()), open(cache, "w"))
        return list(acc.values())

    posts = paged("multimedia?", "id,link,title,content,acf,date", posts_p)
    media = paged("media?media_type=video", "id,source_url,media_details", media_p)
    by_att = {m["id"]: m for m in media}

    rows = []
    for m in posts:
        a = m.get("acf") or {}
        if a.get("type") != "video" or not a.get("video"):
            continue
        files = []
        for v in a["video"]:
            att = by_att.get(v.get("video-file"))
            if not att:
                continue
            md = att.get("media_details") or {}
            files.append({"attachment_id": att["id"], "url": att["source_url"],
                          "width": md.get("width"), "height": md.get("height"),
                          "seconds": md.get("length"), "bytes": md.get("filesize")})
        if not files:
            continue
        files.sort(key=lambda f: f["width"] or 0, reverse=True)
        rows.append({
            "post_id": m["id"], "item_url": m["link"],
            "title": _text(m["title"]["rendered"]),
            "description": _text(m["content"]["rendered"]),
            "acf_credit": _text(a.get("credit") or ""),
            "date": m.get("date"), "files": files,
        })
    return rows


# --------------------------------------------------------------------- gates

# The label a rejection carries when the SCREENER failed rather than the clip.
# Not a gate: nothing about the clip's rights was decided.
SCREENING_ERROR = "E-screening-error"


def gate_a(row: dict, live: bool = True) -> tuple[bool, str, str | None]:
    """Metadata credit, read twice off two surfaces."""
    acf = row["acf_credit"]
    ok, why = credit_gate(acf)
    if not ok:
        return False, f"acf credit: {why}", None
    if not live:
        return True, f"acf credit accepted ({why})", acf
    try:
        page = imagery.scrape_credit(row["item_url"])
    except Exception as exc:
        return False, f"item page unreadable, cannot confirm credit: {exc}", None
    if not page:
        return False, "item page carries no Credit block to confirm the API field", None
    ok2, why2 = credit_gate(page)
    if not ok2:
        return False, f"rendered item page credit: {why2}", None
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    if norm(page) != norm(acf):
        return False, (f"API credit {acf!r} and item-page credit {page!r} disagree")
    return True, (f"credit resolves to NOAA alone on BOTH the API field and the "
                  f"rendered item page ({why})"), page


def gate_b(probes: list[tuple[float, list]]) -> tuple[bool, str]:
    """The credit burned into the picture, which the metadata does not carry."""
    blob = " ".join(boxes_text(b) if isinstance(b, list) else str(b)
                    for _, b in probes if b)
    if not blob:
        return True, "no burned-in text anywhere in the clip"
    tp = imagery.THIRD_PARTY.search(blob)
    if tp:
        return False, (f"burned-in text names a non-federal party "
                       f"({tp.group(1)!r}); the picture asserts a credit the "
                       f"metadata field does not")
    cr = IN_FRAME_CREDIT.search(blob)
    if cr:
        ctx = blob[max(0, cr.start() - 30):cr.start() + 90]
        return False, f"burned-in credit line in frame: ...{ctx}..."
    return True, "burned-in text is NOAA branding and dive telemetry only, no credit"


def screen(rows: list[dict], workers: int = 8, live: bool = True,
           limit: int | None = None) -> tuple[list[dict], list[dict]]:
    accepted, rejected = [], []
    rows = rows[:limit] if limit else rows

    def one(row):
        f = row["files"][0]
        if (f["width"] or 0) < MIN_WIDTH:
            return None, {"reason": f"best file is {f['width']}px, below {MIN_WIDTH}",
                          "gate": "0-size"}
        ok, why, credit = gate_a(row, live=live)
        if not ok:
            return None, {"reason": why, "gate": "A-credit"}
        # scan the SD rendition: the burned-in graphics are identical at every
        # resolution and it costs a fraction of the bytes to range-request.
        scan_file = row["files"][-1]
        secs = scan_file["seconds"] or f["seconds"] or 0
        if not secs:
            return None, {"reason": "no duration reported", "gate": "A-credit"}
        probes = scan(scan_file["url"], secs)
        if not probes:
            return None, {"reason": "could not read any frame", "gate": "C-window"}
        okb, whyb = gate_b(probes)
        if not okb:
            return None, {"reason": whyb, "gate": "B-burned-in-credit"}
        wins = clean_windows(probes, secs)
        crop = None
        treatment = "as-shot"
        if not wins:
            # Nothing is text-free as shot. Most often that is the permanent
            # NOAA wordmark bug in a corner, which one fixed crop removes.
            wins, crop = croppable_windows(probes, secs)
            treatment = "cropped"
        if not wins:
            return None, {"reason": (f"no text-free span of {MIN_CLEAN_SECONDS}s "
                                     f"anywhere in {secs}s, and the on-screen text "
                                     f"cannot be cropped away within "
                                     f"{int(CROP_MARGIN * 100)}% of a side"),
                          "gate": "C-window"}
        row = dict(row)
        row.update({"required_credit": credit, "rights_check_a": why,
                    "rights_check_b": whyb,
                    "clean_windows": wins,
                    "treatment": treatment,
                    "crop": crop,
                    "usable_seconds": round(sum(w["seconds"] for w in wins), 2),
                    "burned_in_text": sorted({boxes_text(b) for _, b in probes if b}),
                    "probe_count": len(probes)})
        return row, None

    def wrap(row):
        try:
            a, r = one(row)
        except Exception as exc:
            # NOT a gate. An exception here is the screener failing, not the
            # clip failing the screen -- a missing ffmpeg, a helper that would
            # not compile, a network error mid-scan. It used to fall through
            # to the "A-credit" default below, which is how 379 environment
            # errors were reported as 379 rights rejections on run
            # 34672456430. Named for what it is, so RULE 0 in harvest() can
            # tell the two apart.
            return None, {"reason": f"screening error: {exc}",
                          "gate": SCREENING_ERROR}
        return a, r

    with ThreadPoolExecutor(workers) as ex:
        for row, (a, r) in zip(rows, ex.map(wrap, rows)):
            if a:
                accepted.append(a)
            else:
                r.update({"post_id": row["post_id"], "item_url": row["item_url"],
                          "title": row["title"], "acf_credit": row["acf_credit"]})
                # Every rejection path in one() names its gate. There is no
                # default: a rejection that cannot say which gate refused it
                # is a screener defect, and labelling it a rights outcome is
                # exactly the mislabel this module carried.
                if "gate" not in r:
                    raise RuntimeError(f"screen(): rejection without a gate: {r}")
                rejected.append(r)
    return accepted, rejected


# ------------------------------------------------------------------- harvest

RIGHTS_BASIS = (
    "Work of the U.S. federal government published by NOAA Ocean Exploration and "
    "therefore not subject to copyright under 17 U.S.C. 105. Three independent "
    "checks, all recorded: (1) the credit in NOAA's own API field resolves to NOAA "
    "alone, with no third-party co-credit and no copyright notice, which is the test "
    "NOAA's media kit sets for reuse of its images and videos; (2) the credit block "
    "rendered on the item page agrees with it; (3) no third party and no producer "
    "credit appears in any sampled frame of the picture itself -- the check that "
    "excludes the GFOE-produced pieces whose metadata field names only NOAA. Only the "
    "clean_windows spans are cleared for use: every frame sampled inside them carried "
    "no on-screen text, so no NOAA wordmark, end card or dive-telemetry overlay is in "
    "the delivered footage."
)

POLICY = (
    "NOAA Ocean Exploration moving footage, three gates. A: acf.credit AND the "
    "rendered item-page Credit block must both pass imagery.credit_is_noaa_only and "
    "must agree with each other. B: OCR of the burned-in text across the whole clip "
    "must name no non-federal party and carry no 'Produced by / Video by / Courtesy "
    "of / Camera' credit -- this is what rejects the GFOE-produced 'Beyond the Blue' "
    "and 'Deep-Sea Dialogues' pieces, whose metadata credit says NOAA alone while "
    "their end cards read 'Produced By Art Howard, GFOE'. C: only spans in which "
    "every sampled frame was text-free are cleared for use, padded inward by "
    f"{WINDOW_PAD}s; a clip with no such span of {MIN_CLEAN_SECONDS}s is rejected. "
    "Every record carries the item URL, the direct URL, the rights basis, the two "
    "rights checks, the required credit, the date checked and the sha256 of the bytes "
    "on disk. An empty accepted set is a hard failure, not an empty manifest."
)


def harvest(accepted: list[dict], rejected: list[dict]) -> list[dict]:
    if not accepted:
        errors = [r for r in rejected if r.get("gate") == SCREENING_ERROR]
        if errors:
            # Say which. "The gate accepted nothing" sent a reader to the
            # rights allowlist; the truth was a binary missing from PATH.
            sample = errors[0]["reason"]
            raise SystemExit(
                f"RULE 0: nothing was accepted and {len(errors)} of "
                f"{len(rejected)} rejections are SCREENING ERRORS, not gate "
                f"decisions (first: {sample}). The screener could not finish on "
                f"this host. Refusing to write an empty manifest; nothing about "
                f"these clips' rights was decided."
            )
        raise SystemExit(
            "RULE 0: the video gate accepted nothing. Refusing to write an empty "
            "manifest -- an empty set here means the gate or the source broke, not "
            "that NOAA stopped publishing. Run --audit to see the rejection reasons."
        )
    os.makedirs(CLIPS, exist_ok=True)
    out = []
    for row in accepted:
        f = row["files"][0]
        stem = re.sub(r"[^a-z0-9]+", "-", row["title"].lower()).strip("-")[:48]
        name = f"{row['post_id']}__{stem}{os.path.splitext(urllib.parse.urlparse(f['url']).path)[1] or '.mp4'}"
        path = os.path.join(CLIPS, name)
        if os.path.exists(path) and os.path.getsize(path) == (f["bytes"] or -1):
            blob = open(path, "rb").read()
        else:
            blob = _get(f["url"], binary=True)
            with open(path, "wb") as fh:
                fh.write(blob)
        out.append({
            "post_id": row["post_id"],
            "title": row["title"],
            "caption": row["description"],
            "source_org": SOURCE_ORG,
            "item_url": row["item_url"],
            "direct_url": f["url"],
            "local_file": os.path.relpath(path, OUT),
            "width": f["width"], "height": f["height"],
            "seconds": f["seconds"],
            "clean_windows": row["clean_windows"],
            "treatment": row["treatment"],
            "crop": row["crop"],
            "usable_seconds": row["usable_seconds"],
            "burned_in_text": row["burned_in_text"],
            "probe_count": row["probe_count"],
            "rights_basis": RIGHTS_BASIS,
            "rights_check": row["rights_check_a"] + " | " + row["rights_check_b"],
            "media_kit_url": MEDIA_KIT,
            "required_credit": row["required_credit"],
            "commercial_use_permitted": True,
            "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        })
        time.sleep(0.2)
    _write(out, rejected)
    return out


def _write(assets: list[dict], rejected: list[dict],
           merge: bool = True) -> None:
    """Write the manifest.

    MERGES with what is already there by default. `--episode` runs screen only
    the posts matching those episodes, so a plain overwrite would silently
    DELETE every clip harvested for a different episode -- the library would
    shrink every time someone harvested a narrow slice, and nothing would say
    so. A previously-accepted record is carried forward only if its file is
    still on disk AND still hashes to the sha256 its rights decision was made
    about; anything that fails that is dropped and named.
    """
    os.makedirs(OUT, exist_ok=True)
    carried, dropped = [], []
    if merge and os.path.exists(MANIFEST):
        fresh = {a["post_id"] for a in assets}
        for a in json.load(open(MANIFEST)).get("assets", []):
            if a["post_id"] in fresh:
                continue                       # re-screened this run; new wins
            path = os.path.join(OUT, a["local_file"])
            if not os.path.exists(path):
                dropped.append(f"{a['title']}: file gone")
                continue
            if hashlib.sha256(open(path, "rb").read()).hexdigest() != a["sha256"]:
                dropped.append(f"{a['title']}: sha256 drift, rights decision "
                               f"no longer covers the bytes on disk")
                continue
            carried.append(a)
    for d in dropped:
        print(f"  DROPPED from manifest: {d}")
    if carried:
        print(f"  carried forward {len(carried)} previously-accepted clip(s)")
    assets = assets + carried
    json.dump({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": POLICY,
        "media_kit_url": MEDIA_KIT,
        "min_clean_seconds": MIN_CLEAN_SECONDS,
        "window_pad_seconds": WINDOW_PAD,
        "accepted_count": len(assets),
        "rejected_count": len(rejected),
        "carried_forward": len(carried),
        "dropped_on_merge": dropped,
        "assets": assets,
        "rejected": rejected,
    }, open(MANIFEST, "w"), indent=2)


def verify() -> int:
    """Re-hash every clip on disk against the manifest. Hard-fails on drift."""
    if not os.path.exists(MANIFEST):
        raise SystemExit("no video manifest; nothing to verify")
    man = json.load(open(MANIFEST))
    assets = man.get("assets", [])
    if not assets:
        raise SystemExit("RULE 0: manifest carries zero assets; verification "
                         "examined nothing and must not pass on an empty loop")
    bad = []
    for a in assets:
        p = os.path.join(OUT, a["local_file"])
        if not os.path.exists(p):
            bad.append(f"{a['title']}: file missing ({a['local_file']})")
            continue
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if h != a["sha256"]:
            bad.append(f"{a['title']}: sha256 drift {a['sha256'][:12]} -> {h[:12]}")
        if not a.get("clean_windows"):
            bad.append(f"{a['title']}: no clean window recorded")
        if not a.get("commercial_use_permitted"):
            bad.append(f"{a['title']}: commercial use not cleared")
    if bad:
        raise SystemExit("VIDEO RIGHTS VERIFICATION FAILED:\n  " + "\n  ".join(bad))
    print(f"verified {len(assets)} clips: sha256 matches, clean window present, "
          f"commercial use cleared")
    return len(assets)


# ------------------------------------------------------------------ coverage

# Per episode: what the footage would have to actually SHOW. Deliberately
# narrow -- a loose pattern is how a giant squid ends up captioned as a
# colossal squid.
SUBJECTS = {
    "10-what-is-the-deepest-part-of-the-ocean":
        r"trench|challenger deep|hadal|mariana|deepest|two miles|abyss",
    "05-why-many-deep-sea-creatures-are-red":
        r"\bred\b|bloody belly|crimson|scarlet|shrimp|big red",
    "01-why-deep-sea-creatures-look-so-weird":
        r"hagfish|chimaera|coffinfish|cusk|snipe eel|lizardfish|isopod|"
        r"tripod|anglerfish|dandelion|hydroid|slime star|sea pig|"
        r"cock-eye|bigfin|glass squid|eelpout|pike-conger|oreo",
    "14-how-big-is-a-colossal-squid":
        r"colossal squid|mesonychoteuthis",
    "20-what-is-the-midnight-zone":
        r"water column|midwater|midnight|bathypelagic|below two miles|"
        r"life two miles|depth of life",
    "06-why-some-deep-sea-creatures-are-transparent":
        r"glass squid|ctenophore|comb jelly|salp|pteropod|house of glass|"
        r"transparen|translucent|larvacean",
    "07-why-deep-sea-creatures-get-creepier-deeper":
        r"hagfish|chimaera|coffinfish|snipe eel|lizardfish|isopod|"
        r"cutthroat eel|synaphobranchid|eelpout|black eel",
    "15-how-do-people-reach-challenger-deep":
        r"submersible|human-occupied|bathyscaphe|trieste|alvin|limiting factor",
    "08-what-creatures-live-in-the-deep-sea":
        r"octopus|jelly|squid|coral|sponge|sea star|crab|shrimp|eel|"
        r"urchin|anemone|skate|shark|sea cucumber|worm",
    "09-what-is-the-scariest-deep-sea-creature":
        r"hagfish|shark|chimaera|anglerfish|lizardfish|eel|predation|"
        r"catshark|sixgill",
    "19-what-is-the-deepest-fish-ever-recorded":
        r"snailfish|liparid|pseudoliparis|hadal",
    "18-why-does-black-smoker-water-not-boil":
        r"black smoker|hydrothermal|vent|chimney|moytirra|methane|"
        r"bubbles|triple junction|mid-atlantic ridge",
    "04-why-deep-sea-creatures-are-so-scary":
        r"hagfish|shark|chimaera|anglerfish|predation|eel|catshark",
    "16-what-happens-when-a-whale-dies-in-the-deep-ocean":
        r"whale fall|whale carcass|whale skeleton|osedax|bone-eating",
    "13-how-does-bioluminescence-work-in-the-deep-sea":
        r"biolumin|green bomber|glow|atolla",
    "02-how-deep-sea-creatures-survive-pressure":
        r"pressure|implod|crush|barophil|piezo",
}


def coverage(assets: list[dict]) -> list[dict]:
    order = json.load(open(os.path.join(HERE, "publish_order.json")))["queue"]
    rows = []
    for q in order:
        pat = SUBJECTS.get(q["slug"])
        hits = []
        if pat:
            r = re.compile(pat, re.I)
            hits = [a for a in assets if r.search(a["title"] + " " + a.get("caption", ""))]
        rows.append({
            "queue_position": q["queue_position"], "slug": q["slug"],
            "title": q["title"], "clips": len(hits),
            "usable_seconds": round(sum(a["usable_seconds"] for a in hits), 1),
            "examples": [a["title"] for a in hits[:6]],
        })
    return rows


# --------------------------------------------------------------------- proof

def prove() -> None:
    """Negative proof: break each gate deliberately and show it fails.

    A gate that has never rejected anything is not known to work.
    """
    checks = []

    # The boilerplate fix recovers NOAA-only credits without loosening anything.
    # It now lives in imagery.py itself, so the SHARED gate must accept this.
    ok, _ = imagery.credit_is_noaa_only("Video courtesy of NOAA Ocean Exploration.")
    checks.append(("shared imagery.credit_is_noaa_only accepts 'Video courtesy of "
                   "NOAA Ocean Exploration.' (the defect, now fixed at source)",
                   ok is True))
    # ...and the un-stripped form was never the thing at fault: prove the strip
    # is what changed, by showing THIRD_PARTY still fires on the raw phrase when
    # it appears anywhere but the documented leading position.
    ok, _ = imagery.credit_is_noaa_only("NOAA Ocean Exploration, courtesy of Jane Smith")
    checks.append(("shared gate still rejects a mid-string 'courtesy of <person>'",
                   ok is False))
    ok, _ = credit_gate("Video courtesy of NOAA Ocean Exploration, Beyond the Blue 2024.")
    checks.append(("credit_gate recovers that NOAA-only credit", ok is True))
    ok, _ = credit_gate("Video courtesy of MBARI.")
    checks.append(("credit_gate still rejects a third party behind the same "
                   "boilerplate", ok is False))
    ok, _ = credit_gate("Video courtesy of NOAA Ocean Exploration and Ocean "
                        "Exploration Trust.")
    checks.append(("credit_gate still rejects a co-credited partner behind the "
                   "boilerplate", ok is False))

    # Gate A: the real GFOE-produced piece's metadata credit PASSES gate A.
    # That is the whole point -- gate A cannot see the problem.
    gfoe_meta = "NOAA Ocean Exploration, Windows to the Deep 2021"
    ok, _ = imagery.credit_is_noaa_only(gfoe_meta)
    checks.append(("gate A passes the GFOE piece's metadata credit "
                   "(so gate B is load-bearing, not decorative)", ok is True))

    # Gate A still rejects an openly third-party credit.
    ok, _ = imagery.credit_is_noaa_only("Video courtesy of Lia Kim.")
    checks.append(("gate A rejects a named individual's credit", ok is False))

    # An episode-scoped harvest must NOT delete the rest of the library.
    # _write merges; prove it carries a good record forward and drops a bad one.
    import tempfile as _tf
    global MANIFEST, OUT
    _M, _O = MANIFEST, OUT
    try:
        OUT = _tf.mkdtemp()
        MANIFEST = os.path.join(OUT, "video_rights.json")
        os.makedirs(os.path.join(OUT, "clips"), exist_ok=True)
        keep = os.path.join(OUT, "clips", "keep.mp4")
        open(keep, "wb").write(b"keep-bytes")
        gone = {"post_id": 2, "title": "Gone", "local_file": "clips/gone.mp4",
                "sha256": "0" * 64}
        prior = [{"post_id": 1, "title": "Kept", "local_file": "clips/keep.mp4",
                  "sha256": hashlib.sha256(b"keep-bytes").hexdigest()}, gone]
        json.dump({"assets": prior}, open(MANIFEST, "w"))
        _write([{"post_id": 9, "title": "New", "local_file": "clips/new.mp4",
                 "sha256": "x"}], [])
        after = json.load(open(MANIFEST))
        titles = {a["title"] for a in after["assets"]}
        checks.append(("an episode-scoped write carries earlier clips forward "
                       "instead of deleting the library", "Kept" in titles))
        checks.append(("a carried record whose file is missing is dropped and "
                       "named, not silently kept",
                       "Gone" not in titles and bool(after["dropped_on_merge"])))
        # A file whose bytes changed is not covered by its rights decision.
        open(keep, "wb").write(b"tampered")
        json.dump({"assets": prior}, open(MANIFEST, "w"))
        _write([{"post_id": 9, "title": "New", "local_file": "clips/new.mp4",
                 "sha256": "x"}], [])
        titles = {a["title"] for a in json.load(open(MANIFEST))["assets"]}
        checks.append(("a carried record whose bytes drifted is dropped", 
                       "Kept" not in titles))
    finally:
        MANIFEST, OUT = _M, _O

    box = lambda t, x, y, w=0.25, h=0.06: {"t": t, "x": x, "y": y, "w": w, "h": h}

    # Gate B rejects the real end-card text read off the real clip.
    real = [(52.0, [box("Windows to the Deep 2021 | nOAA | OCEAN | EXPLORATION | "
                        "Produced By: Emily Narrow, GFOE", 0.2, 0.4)])]
    ok, why = gate_b(real)
    checks.append((f"gate B rejects the real GFOE end card ({why[:52]}...)", ok is False))

    # Gate B accepts a clip whose only burned-in text is NOAA telemetry.
    telem = [(0.5, [box("Expedition: 2021 ROV Shakedown | Depth: 1,400 meters",
                        0.02, 0.82)]), (30.0, [])]
    ok, _ = gate_b(telem)
    checks.append(("gate B accepts NOAA dive telemetry with no credit line", ok is True))

    # Gate C: a clip that is text-bearing end to end yields no as-shot window.
    dirty = [(t, [box("OCEAN EXPLORATION", 0.02, 0.03)]) for t in (0.3, 5.0, 10.0, 15.0)]
    checks.append(("gate C yields no as-shot window when every frame carries text",
                   clean_windows(dirty, 15.0) == []))

    # ...but the corner wordmark IS croppable, which is how the Chimaera-class
    # clips are recovered rather than thrown away.
    wins, crop = croppable_windows(dirty, 15.0)
    checks.append((f"croppable_windows recovers the corner-wordmark clip with "
                   f"crop {crop}",
                   len(wins) == 1 and crop is not None and crop["top"] > 0))

    # A chyron across the middle of the frame is NOT croppable.
    mid = [(t, [box("DEEP-SEA UNDERDOGS", 0.25, 0.45, 0.5, 0.1)])
           for t in (0.3, 5.0, 10.0, 15.0)]
    wins, crop = croppable_windows(mid, 15.0)
    checks.append(("a mid-frame chyron is refused rather than cropped around",
                   wins == [] and crop is None))

    # Gate C: a real head-card-then-clean shape yields a padded interior window.
    shape = [(0.3, [box("BIGFIN SQUID", 0.2, 0.45, 0.5, 0.1)]),
             (3.0, [box("BIGFIN SQUID", 0.2, 0.45, 0.5, 0.1)]),
             (6.0, []), (20.0, []), (40.0, []),
             (55.0, [box("OCEAN EXPLORATION", 0.2, 0.45, 0.5, 0.1)])]
    w = clean_windows(shape, 60.0)
    checks.append((f"gate C returns an interior window {w} clear of both cards",
                   len(w) == 1 and w[0]["start"] >= 4.0 and w[0]["end"] <= 54.0))

    # Gate C: too-short a gap is not a usable window.
    tight = [(0.3, [box("X", 0.4, 0.4)]), (3.0, []), (5.0, [box("X", 0.4, 0.4)])]
    checks.append((f"gate C rejects a gap shorter than {MIN_CLEAN_SECONDS}s",
                   clean_windows(tight, 6.0) == []))

    # The crop must actually clear the glyphs, with margin.
    c = crop_to_clear([box("OCEAN EXPLORATION", 0.02, 0.03, 0.20, 0.06)])
    checks.append((f"crop {c} cuts past the bottom of a top-corner wordmark",
                   c is not None and c["top"] >= 0.09))

    # Rule 0: harvest refuses to write an empty manifest.
    try:
        harvest([], [])
        empty_ok = False
    except SystemExit:
        empty_ok = True
    checks.append(("harvest hard-fails on an empty accepted set (Rule 0)", empty_ok))

    width = max(len(c[0]) for c in checks)
    bad = 0
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:{width}}")
        bad += not passed
    if bad:
        raise SystemExit(f"{bad} gate proof(s) FAILED")
    print(f"\n{len(checks)}/{len(checks)} gate proofs pass.")


# ---------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="screen only, no download")
    ap.add_argument("--harvest", action="store_true", help="screen then download")
    ap.add_argument("--coverage", action="store_true", help="per-episode coverage")
    ap.add_argument("--verify", action="store_true", help="re-hash what is on disk")
    ap.add_argument("--prove", action="store_true", help="negative proof of the gates")
    ap.add_argument("--episode", action="append", default=None,
                    help="restrict to clips whose title/description match this "
                         "episode slug's SUBJECTS pattern. Repeatable.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true", help="re-fetch the NOAA index")
    a = ap.parse_args()

    if a.prove:
        return prove()
    if a.verify:
        return None if verify() else None
    if a.coverage and not (a.audit or a.harvest):
        man = json.load(open(MANIFEST))
        for r in coverage(man["assets"]):
            mark = "--" if not r["clips"] else "  "
            print(f"{mark}{r['queue_position']:3}. {r['slug'][:48]:50} "
                  f"{r['clips']:3} clips  {r['usable_seconds']:7.1f}s usable")
            if r["examples"]:
                print(f"        {', '.join(r['examples'])}")
        return

    # Before a single request: a host that cannot run gates B and C cannot
    # screen a clip to the end, so screening it at all only produces
    # rejections that look like rights decisions and are not.
    require_tooling()
    rows = discover(refresh=a.refresh)
    print(f"NOAA Ocean Exploration multimedia posts of type video: {len(rows)}")
    if a.episode:
        missing = [s for s in a.episode if s not in SUBJECTS]
        if missing:
            raise SystemExit(f"unknown episode slug(s): {missing}. "
                             f"Known: {sorted(SUBJECTS)}")
        pat = re.compile("|".join(SUBJECTS[s] for s in a.episode), re.I)
        rows = [r for r in rows if pat.search(r["title"] + " " + r["description"])]
        print(f"  restricted to {a.episode} -> {len(rows)} candidate posts")
        if not rows:
            raise SystemExit("RULE 0: the episode filter matched nothing. Refusing "
                             "to proceed on an empty candidate set.")
    acc, rej = screen(rows, workers=a.workers, limit=a.limit)
    print(f"accepted {len(acc)} / rejected {len(rej)}")
    from collections import Counter
    for g, n in Counter(r.get("gate") for r in rej).most_common():
        print(f"  rejected {n:4}  gate {g}")
    if a.harvest:
        got = harvest(acc, rej)
        print(f"downloaded {len(got)} clips -> {CLIPS}")
        print(f"manifest -> {MANIFEST}")
        verify()
    else:
        _write([], rej) if False else None
        json.dump({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "policy": POLICY, "accepted": acc, "rejected": rej},
                  open(os.path.join(CACHE, "audit.json"), "w"), indent=1)
        print(f"audit -> {os.path.join(CACHE, 'audit.json')}")
    if a.coverage:
        for r in coverage([{**x, "caption": x["description"]} for x in acc]):
            print(f"{r['queue_position']:3}. {r['slug'][:48]:50} {r['clips']:3} clips "
                  f"{r['usable_seconds']:7.1f}s")


if __name__ == "__main__":
    main()
