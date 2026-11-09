#!/usr/bin/env python3
"""Rebuild the teaching lanes' book record from config/teacher_rights.json.

    python loop/tools/teacher_texts.py [--keep DIR]

For every quotable title with a `text_url`: download the public-domain text
(to a temp dir, never into the repo: the scans carry later publishers' front
matter), check every recorded quote of that title is in it word for word and
passes the plain-words and guardrail checks, and write the SAMPLED eight-word
run hashes (one in eight; no book text) to config/teacher_shingles.txt, which
the straight-reading check (loop/teachings.BOOK_READ) reads.

Any quote not found, or failing a check, is a NAMED STOP and nothing is
written. Prints an OUTPUT line.
"""
from __future__ import annotations

import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import teachings as T                                       # noqa: E402
import whisper_lane as WL                                   # noqa: E402
import whisper_words as W                                   # noqa: E402


def fetch(url: str, dest: Path) -> str:
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "how-we-know/teacher-texts"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dest.write_bytes(r.read())
    return dest.read_text(encoding="utf-8", errors="replace")


def _contains(hay: list[str], needle: list[str]) -> bool:
    n = len(needle)
    first = needle[0]
    return any(hay[i] == first and hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def main(argv: list[str]) -> int:
    keep = Path(argv[argv.index("--keep") + 1]) if "--keep" in argv else None
    r = T.rights()
    ok = T.quotable(r)
    runs: set[str] = set()
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        d = keep or Path(td)
        d.mkdir(parents=True, exist_ok=True)
        texts = {}
        for k, v in ok.items():
            if v.get("text_url"):
                texts[k] = fetch(v["text_url"], d / f"{k}.txt")
                runs |= T.sampled_runs(texts[k])
        for q in r["quotes"]:
            if q["title"] not in ok:
                bad.append(f"{q['id']}: {q['title']} is not quotable")
                continue
            if q["title"] not in texts:
                bad.append(f"{q['id']}: no text kept for {q['title']}")
                continue
            if not _contains(T.tokens(texts[q["title"]]), T.tokens(q["text"])):
                bad.append(f"{q['id']}: not found word for word in {q['title']}")
            probs = W.text_problems(q["text"], []) + WL.affirmation_problems(q["text"])
            if any(len(W.WORD.findall(s)) > 28 for s in WL.sentences(q["text"])):
                probs.append("a sentence over 28 words")
            if probs:
                bad.append(f"{q['id']}: {probs[:2]}")
    if bad:
        print(f"NAMED STOP [TEACHER_QUOTE_UNVERIFIED] {len(bad)} quote(s): " + "; ".join(bad[:8]))
        return 1
    T.SHINGLES.write_text("# sampled eight-word run hashes of the public-domain teacher texts "
                          "(loop/tools/teacher_texts.py); no book text is stored\n"
                          + "\n".join(sorted(runs)) + "\n")
    print(f"OUTPUT {len(r['quotes'])} quotes verified in {len(texts)} texts; {len(runs)} sampled runs written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
