"""No personal data in tracked text: street addresses, phone numbers,
personal mailboxes, SSN shapes.

WHAT THIS PINS.

  A. Every tracked text file in the repo is free of: a US street address
     line, a US phone number, a personal @gmail.com / @yahoo.com /
     @icloud.com mailbox, and an SSN-shaped number. The owner's postal
     address was found in docs/youtube-audit-application.md on 4 Oct 2026
     (committed 30 Aug) while the rest of the account's repos went public;
     this test is the guard that keeps it out, here and everywhere else.
  B. The negative proof: the same detector, fed a synthetic line of each
     kind, FIRES. A detector that cannot see the thing it guards is inert.

Hard-fails if it examined zero files.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
examined = 0
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")
    else:
        print(f"  ok   {name}")


STREET = re.compile(r"\b\d{2,5} [A-Z][a-z]+( [A-Z][a-z]+)? (Dr|Drive|St|Street|Ave|Avenue|Rd|Road|Blvd|Ln|Lane|Ct|Court|Way|Pl|Place|Cv|Cove)\b")
CITY_ZIP = re.compile(r"\b[A-Z][a-z]+, [A-Z]{2} \d{5}\b")
PHONE = re.compile(r"(?<![\w.-])\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\w.-])")
MAILBOX = re.compile(r"\b[\w.+-]+@(gmail|yahoo|icloud|hotmail|outlook)\.com\b", re.I)
SSN = re.compile(r"(?<![\w-])\d{3}-\d{2}-\d{4}(?![\w-])")
DETECTORS = {"street address": STREET, "city/state/zip": CITY_ZIP, "phone": PHONE, "personal mailbox": MAILBOX, "ssn": SSN}
SKIP_SUFFIX = {".srt", ".vtt", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp3", ".mp4", ".wav", ".m4a", ".pdf", ".lock", ".ico", ".woff", ".woff2"}
SELF = Path(__file__).resolve()

# ------------------------------------------------------------- A. the repo
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
scanned = 0
for rel in tracked:
    if not rel:
        continue
    p = ROOT / rel
    if p.suffix.lower() in SKIP_SUFFIX or not p.is_file() or p.resolve() == SELF:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    scanned += 1
    for kind, rx in DETECTORS.items():
        m = rx.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            check(f"A {rel}:{line} has no {kind}", False, f"{kind} pattern matched (value not printed)")
check("A scanned a real number of tracked text files", scanned >= 50, f"scanned={scanned}")
print(f"  scanned {scanned} tracked text files, no personal data" if not fails else "")

# ------------------------------------------------------------- B. negative proof
samples = {
    "street address": "ship to 1234 Elm Tree Dr please",
    "city/state/zip": "Springfield, IL 62704",
    "phone": "call (901) 555-0142 today",
    "personal mailbox": "owner: someone@gmail.com",
    "ssn": "id 123-45-6789 end",
}
for kind, rx in DETECTORS.items():
    check(f"B detector for {kind} fires on a synthetic line", bool(rx.search(samples[kind])))
    check(f"B detector for {kind} stays quiet on clean prose", not rx.search("The loop uploads one episode a day and records spend."))

if examined == 0:
    print("FAIL: examined zero cases")
    sys.exit(2)
if fails:
    print(f"\n{len(fails)} failure(s)")
    sys.exit(1)
print(f"\nall {examined} checks passed")
