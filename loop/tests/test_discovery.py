"""loop/discovery.py: subject extraction, mined-query honesty, and the
hashtag line's round trip.

Owner instruction, 2026-09-21: tags and hashtags are DERIVED per episode from
its own domain and subject, never invented and never one fixed list. This
proves the three things that make that true: `subject_of` never leaves a
question word leading and never returns empty, across every real script in
the repository (not a handful picked to look good); a mined-query tag is only
ever included when it actually occurs in that episode's own narration; and
`add_hashtag_line` / `strip_hashtag_line` round-trip exactly, which is what
`loop/localize.py:content_key` relies on to leave an unrelated hash unchanged
when a hashtag line is appended.

Hard-fails if it examines fewer than the real script count on disk.
"""
from __future__ import annotations

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)

import discovery                                                   # noqa: E402
import domains                                                     # noqa: E402
import localize                                                    # noqa: E402

QUESTION_WORDS = {"why", "how", "what", "when", "where", "which", "who"}

fails: list[str] = []
scripts = sorted(glob.glob(os.path.join(ROOT, "scripts", "*.md")))
if not scripts:
    print("FAIL: no scripts on disk — this test examined zero of them")
    sys.exit(1)

examined = 0

# ---------------------------------------------------- subject_of, every script
for path in scripts:
    examined += 1
    slug = os.path.basename(path)[:-3]
    text = open(path, encoding="utf-8").read()
    title = discovery._script_title(slug, text)
    subject = discovery.subject_of(title)
    if not subject.strip():
        fails.append(f"{slug}: subject_of({title!r}) is empty")
    first = subject.split()[0] if subject.split() else ""
    if first in QUESTION_WORDS:
        fails.append(f"{slug}: subject_of({title!r}) = {subject!r} still "
                     f"leads with the question stem {first!r}")

# ------------------------------------------------- mined tags only if in text
for path in scripts:
    slug = os.path.basename(path)[:-3]
    text = open(path, encoding="utf-8").read()
    domain = domains.domain_of_script(__import__("pathlib").Path(path))
    if not domain:
        continue
    examined += 1
    tags = discovery.tags_for(slug, text, domain)
    domain_tags = set(discovery._discovery_block(
        __import__("json").load(open(os.path.join(ROOT, "loop", "config.json"))),
        domain)[0])
    channel_tags = set(discovery._discovery_block(
        __import__("json").load(open(os.path.join(ROOT, "loop", "config.json"))),
        domain)[2])
    subject = discovery.subject_of(discovery._script_title(slug, text))
    narration = discovery._narration_text(text)
    for t in tags:
        if t == subject or t in domain_tags or t in channel_tags:
            continue
        # whatever is left must be a mined phrase that really occurs in the
        # narration — never invented.
        if t.lower() not in narration:
            fails.append(f"{slug}: tag {t!r} is not the subject, not a "
                         f"domain/channel tag, and does not occur in the "
                         f"episode's own narration — it would be invented")

    # the cap is respected
    total_len = sum(len(t) + 1 for t in tags)
    if total_len > discovery.TAG_TOTAL_MAX:
        fails.append(f"{slug}: total tag length {total_len} exceeds "
                     f"TAG_TOTAL_MAX ({discovery.TAG_TOTAL_MAX})")

    # hashtags: no more than HASHTAG_MAX, all well-formed
    hashtags = discovery.hashtags_for(slug, text, domain)
    examined += 1
    if len(hashtags) > discovery.HASHTAG_MAX:
        fails.append(f"{slug}: {len(hashtags)} hashtags exceeds "
                     f"HASHTAG_MAX ({discovery.HASHTAG_MAX})")
    if any(not h.startswith("#") or " " in h for h in hashtags):
        fails.append(f"{slug}: malformed hashtag(s) in {hashtags}")

# --------------------------------------------- the hashtag line round-trips
examined += 1
sample_desc = ("Answer.\n\nChapters\n0:00 Cold open\n\n"
              "Sources — every figure in this video traces to one of these:\n"
              "• NOAA — https://noaa.gov\n\n"
              "Evidence-first explainers.")
hts = ["#Titanium", "#MaterialsScience", "#Manufacturing", "#HowWeKnow"]
added = discovery.add_hashtag_line(sample_desc, hts)
if not added.endswith(discovery.hashtag_line(hts)):
    fails.append(f"add_hashtag_line did not put the hashtag line last: "
                 f"{added[-80:]!r}")
stripped = discovery.strip_hashtag_line(added)
if stripped != sample_desc:
    fails.append(f"strip_hashtag_line(add_hashtag_line(d)) != d: "
                 f"{stripped!r} != {sample_desc!r}")

# a description with no hashtag line is untouched by strip
examined += 1
if discovery.strip_hashtag_line(sample_desc) != sample_desc:
    fails.append("strip_hashtag_line changed a description with no "
                 "hashtag line")

# ------------------------------------- localize.content_key ignores the line
examined += 1
title = "How strong is titanium?"
key_plain = localize.content_key(title, sample_desc, "es")
key_with_hashtags = localize.content_key(title, added, "es")
if key_plain != key_with_hashtags:
    fails.append(f"localize.content_key changed when a hashtag line was "
                 f"appended: {key_plain!r} != {key_with_hashtags!r} — the "
                 f"backfill would re-translate every already-localized video")

if examined < len(scripts):
    fails.append(f"Rule 0: examined {examined}, fewer than the "
                 f"{len(scripts)} real script(s) on disk")

if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} check(s) across {len(scripts)} real script(s) — "
      f"subject extraction, mined-tag honesty, and the hashtag line's "
      f"round trip all hold")
