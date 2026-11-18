#!/usr/bin/env python3
"""Build config/kjv/kjv.json: the King James text Psalm Nights reads from.

    python loop/tools/kjv_bundle.py [--zip PATH]

Downloads eBible.org's King James Version (the 1769 standard text, marked
"Public Domain" on https://ebible.org/eng-kjv/copr.htm) in its
verse-per-line form, to a temp dir, and keeps the WHOLE Book of Psalms plus
every other chapter a night in config/whisper_almanac.json `psalms.nights`
names. Square brackets (the KJV's italic supplied words) and paragraph marks
are dropped; the words are kept exactly. The source URL, its licence wording
and the archive's sha256 are recorded in the file.

Every configured passage must resolve in the bundle, or it is the NAMED
STOP KJV_PASSAGE_MISSING and nothing is written. Prints an OUTPUT line.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import psalms as PS                                         # noqa: E402
import whisper_lane as WL                                   # noqa: E402

URL = "https://ebible.org/Scriptures/eng-kjv_vpl.zip"
LICENCE_URL = "https://ebible.org/eng-kjv/copr.htm"
LICENCE = ("The King James Version or Authorized Version of the Holy Bible, using the standardized "
           "text of 1769 ... Public Domain. ... This royal decree has no effect outside of the UK, "
           "where this work is firmly in the Public Domain. ... You may copy the King James Version "
           "of the Holy Bible freely.")
NAMES = {"PSA": "Psalms", "PRO": "Proverbs", "ISA": "Isaiah", "MAT": "Matthew", "JOH": "John",
         "PHI": "Philippians", "LAM": "Lamentations", "NUM": "Numbers"}
LINE = re.compile(r"^(?P<book>[1-3]?[A-Z]{2,3}) (?P<ch>\d+):(?P<v>\d+) (?P<text>.+)$")


def clean(text: str) -> str:
    text = text.replace("¶", " ").replace("[", "").replace("]", "")
    return re.sub(r"\s+", " ", text).strip()


def read_zip(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.endswith("_vpl.txt"))
        return z.read(name).decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", help="a downloaded eng-kjv_vpl.zip (default: download it)")
    a = ap.parse_args(argv)
    if a.zip:
        data = Path(a.zip).read_bytes()
    else:                                  # held in memory, never written into the repo
        req = urllib.request.Request(URL, headers={"User-Agent": "how-we-know/kjv-bundle"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    c = WL.cfg()
    want: dict[str, set[int]] = {"PSA": set()}            # PSA: every chapter
    for n in PS.nights(c).values():
        for ref in PS.night_refs(n):
            book, ch, _, _ = PS.parse_ref(ref)
            if book != "PSA":
                want.setdefault(book, set()).add(ch)
    books: dict[str, dict] = {}
    for line in read_zip(data).splitlines():
        m = LINE.match(line.strip())
        if not m or m.group("book") not in want:
            continue
        bk, ch = m.group("book"), int(m.group("ch"))
        if bk != "PSA" and ch not in want[bk]:
            continue
        b = books.setdefault(bk, {"name": NAMES.get(bk, bk), "chapters": {}})
        b["chapters"].setdefault(str(ch), {})[m.group("v")] = clean(m.group("text"))
    out = {"_source": {"text": "King James Version (Authorized Version), standardized text of 1769",
                       "status": "public domain in the US",
                       "url": URL, "licence_url": LICENCE_URL, "licence_words": LICENCE,
                       "sha256": hashlib.sha256(data).hexdigest(),
                       "built": f"{_dt.date.today():%Y-%m-%d}",
                       "kept": "the whole Book of Psalms, and each other chapter a night names",
                       "why": "Her spec 18 Nov 2026: Psalm Nights reads the KJV only, word for word from this "
                              "file, never from a model's memory and never a copyrighted translation. Built by "
                              "loop/tools/kjv_bundle.py; read by loop/psalms.py."},
           "books": books}
    missing = []
    for k, n in PS.nights(c).items():
        for ref in PS.night_refs(n):
            try:
                PS.verses(ref, out)
            except KeyError as e:
                missing.append(f"{k}: {e.args[0]}")
    if missing or len(books.get("PSA", {}).get("chapters", {})) != 150:
        print(f"NAMED STOP [KJV_PASSAGE_MISSING] {len(missing)} passage(s) not in the KJV download "
              f"({len(books.get('PSA', {}).get('chapters', {}))} psalms read): {missing[:3]}", file=sys.stderr)
        return 2
    PS.KJV.parent.mkdir(parents=True, exist_ok=True)
    PS.KJV.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    nv = sum(len(ch) for b in books.values() for ch in b["chapters"].values())
    print(f"OUTPUT {nv} KJV verses in {sum(len(b['chapters']) for b in books.values())} chapters "
          f"written to {PS.KJV.relative_to(WL.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
