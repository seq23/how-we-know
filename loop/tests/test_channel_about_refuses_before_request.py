"""Prove channel_about.py refuses a bad description BEFORE any request,
naming the number or the character — never a bare 400 from Google.

Root cause (2026-09-21): the pushed About body was 1,006 UTF-16 units against
YouTube's 1,000-unit cap on brandingSettings.channel.description; the < and >
in channel/about.md's HTML markers are never sent, so length alone caused the
400 that stopped rc_m32h8ze2a4hk37pc's post-land step. This asserts
check_description() catches both failure modes named in the instruction (over
length, angle brackets) before merge_branding ever builds a request body, and
that the repo's own channel/about.md passes so it cannot regress past the cap.

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOOP_DRY_RUN", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import channel_about as ca  # noqa: E402

CURRENT = {"title": "How We Know", "description": "old", "keywords": "x",
          "country": "US"}


def check() -> list[str]:
    fails, examined = [], 0

    # -- too long: 1,001 clean ASCII characters ----------------------------
    examined += 1
    too_long = "a" * 1001
    try:
        ca.check_description(too_long)
        fails.append("1,001-character description was not refused")
    except ca.MergeRefused as e:
        if "1001" not in str(e) or "1000" not in str(e):
            fails.append(f"too-long refusal did not name both numbers: {e}")

    # -- merge_branding refuses too, before building a body ----------------
    examined += 1
    try:
        ca.merge_branding(CURRENT, too_long)
        fails.append("merge_branding let a 1,001-character description through")
    except ca.MergeRefused:
        pass

    # -- contains '<' -------------------------------------------------------
    examined += 1
    try:
        ca.check_description("clean text with a < in it")
        fails.append("a description containing '<' was not refused")
    except ca.MergeRefused as e:
        if "<" not in str(e):
            fails.append(f"'<' refusal did not name the character: {e}")

    # -- contains '>' -------------------------------------------------------
    examined += 1
    try:
        ca.check_description("clean text with a > in it")
        fails.append("a description containing '>' was not refused")
    except ca.MergeRefused as e:
        if ">" not in str(e):
            fails.append(f"'>' refusal did not name the character: {e}")

    # -- astral character counts as 2 UTF-16 units --------------------------
    # 999 ASCII + one 4-byte character (U+1F600, outside the BMP) = 1,001
    # UTF-16 units, one over the cap that a naive len() would miss.
    examined += 1
    astral = ("a" * 999) + "\U0001F600"
    if len(astral) != 1000:
        fails.append("test setup error: astral fixture is not 1,000 code points")
    try:
        ca.check_description(astral)
        fails.append("an astral character pushing the UTF-16 count to 1,001 "
                     "was not refused")
    except ca.MergeRefused as e:
        if "1001" not in str(e):
            fails.append(f"astral refusal did not name 1,001 units: {e}")

    # -- exactly 1,000 clean characters merges, carrying the rest ------------
    examined += 1
    exactly = "a" * 1000
    try:
        merged = ca.merge_branding(CURRENT, exactly)
        if merged.get("description") != exactly:
            fails.append("merge_branding did not carry the description through")
        for k in ("title", "keywords", "country"):
            if merged.get(k) != CURRENT[k]:
                fails.append(f"merge_branding dropped {k!r} at exactly 1,000 units")
    except ca.MergeRefused as e:
        fails.append(f"exactly-1,000-unit description was wrongly refused: {e}")

    # -- the repo's own channel/about.md body passes -------------------------
    examined += 1
    try:
        ca.check_description(ca.read_about())
    except ca.MergeRefused as e:
        fails.append(f"channel/about.md's own body is refused: {e} — the "
                     f"live file has regressed past the cap")

    if examined == 0:
        fails.append("examined ZERO cases")
    print(f"examined {examined} description-refusal case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - channel_about.py refuses a bad description before "
          "any request" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
