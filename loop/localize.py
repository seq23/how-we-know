"""Translated titles and descriptions, so the episodes exist in non-English search.

    .venv/bin/python loop/localize.py                # translate and apply
    .venv/bin/python loop/localize.py --limit 4
    .venv/bin/python loop/localize.py --dry-run      # translate, apply nothing

## What this is for

The channel is banking watch hours against a Partner Programme threshold that
doubles from 4,000 to 8,000 on 2026-02-01. Non-English reach is the cheapest
hours available and costs nothing but quota. A video with English-only metadata
is invisible to a Spanish-language search no matter how good its captions are:
YouTube indexes the localized title and description it was given, and if it was
given none, there is nothing to match.

Five languages: **es, pt-BR, hi, id, de** — YouTube's "Expressive Speech"
auto-dub set, so localized metadata and any auto-dub reinforce each other rather
than pointing at different audiences.

## What it does NOT do

It does not create a second channel and it does not synthesise translated
narration audio. Both were considered and rejected.

## Two API traps, both load-bearing

**1. `videos.update` REPLACES the parts you name.** Sending
`part=snippet,localizations` with a partial snippet erases the title,
description, tags and categoryId of a live video. Every write here goes through
`loop/ytmeta.py`, which reads the current snippet, merges, and sends it back
whole — and refuses rather than truncating. `loop/validate.py` V19 fails the
build if any other module in `loop/` issues a snippet-bearing update.

**2. `snippet.defaultLanguage` must be set or localizations are rejected.**
This lane sets it to exactly `"en"` on every video it touches, which is also
the fix for something observed directly in the owner's Studio on 2026-09-02:
with the video language unset — as it was on all 16 videos — the per-video
Languages page renders nothing but a "Set language" dropdown and a disabled
Confirm. No subtitle upload, no translations table, no dubbing control. Unset
language gates the entire translation surface in the UI as well as in the API.
One video was set by hand; this lane sets the rest, to `en` and never `en-US`,
because a channel split between the two is an inconsistency nothing reports.

## Why the description is not simply handed to the model

The description carries chapter timestamps and a `Sources` block of real URLs.
An LLM asked to "translate this" will cheerfully reformat a timestamp and
invent a plausible NOAA link — the one failure this repo has already been
burned by (`loop/validate.py` V8 exists because of it). So the description is
split first. Bulleted sources and any line carrying a URL are held back and
re-emitted **byte for byte** — the model never sees them. A chapter line is
split: the `0:00` timestamp is held and re-emitted from the original string
(a model that "helpfully" reformats it to `00:00` breaks YouTube's chapter
parser) while its label IS translated, because an English chapter list down a
Spanish description helps nobody. What is sent goes as a numbered list whose
length must come back unchanged; a translation that returns a different number
of lines is refused, not patched up.

The title gets a second, short model call that back-checks it for a wrong core
noun or adjective and either corrects it or refuses the language. That is not
belt-and-braces: on the first run Sonnet rendered "deepest" into Indonesian as
*terlaut*, which is not a word, and nothing else in this pipeline could have
noticed.

## Cost and idempotence

`videos.list` 1 unit + `videos.update` 50 = 51 units a video; fifteen live
videos is 765 units of a 10,000-unit day. Translations are cached by content
hash in `loop/state/translations.json`, and what has shipped is recorded in
`loop/state/localizations.json`, so a second run makes no model call and no API
write and says so.

Scopes: `videos.update` is covered by the plain
`https://www.googleapis.com/auth/youtube` scope, which this channel's token was
granted and which was confirmed present on 2026-09-02. **This lane is not
blocked on anything.** It does not need `force-ssl`; only captions do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "auth"))

import tokens as auth                             # noqa: E402
import author                                     # noqa: E402
import quota                                      # noqa: E402
import upload as up                               # noqa: E402
import ytmeta                                     # noqa: E402
from common import (STATE, Stage, config, now, read_json,  # noqa: E402
                    week_id, write_json)

LANE = "localize"
STATE_FILE = STATE / "localizations.json"
CACHE_FILE = STATE / "translations.json"

DRY_RUN = os.environ.get("LOOP_DRY_RUN") == "1"

# YouTube's "Expressive Speech" auto-dub set. The BCP-47 codes are what the API
# keys `localizations` by; pt-BR is deliberately regional (Brazilian Portuguese
# is the audience) while the rest are not.
LANGUAGES = {
    "es": "Spanish (neutral Latin American, not Castilian-specific)",
    "pt-BR": "Brazilian Portuguese",
    "hi": "Hindi, in Devanagari script",
    "id": "Indonesian",
    "de": "German",
}

TITLE_MAX, DESC_MAX = 100, 5000

# A line that must survive byte for byte: a bulleted source, or anything
# carrying a URL. An LLM asked to "translate this" will reformat a link or
# invent a plausible one, which is the failure V8 exists to catch.
VERBATIM = re.compile(r"https?://|^\s*•")

# A chapter line: `0:00 Cold open`. The LABEL is worth translating — it is what
# a non-English viewer reads down the description — but the TIMESTAMP is not,
# and a model that "helpfully" reformats 0:00 to 00:00 breaks YouTube's chapter
# parser. So the timestamp is split off, held, and re-emitted from the original
# string; only the label ever reaches the model.
CHAPTER = re.compile(r"^(\s*\d{1,2}:\d{2}(?::\d{2})?\s+)(.+)$")


# ------------------------------------------------------------------- state

def load_state() -> dict:
    d = read_json(STATE_FILE, default={"videos": {}, "updated": None})
    d.setdefault("videos", {})
    return d


def load_cache() -> dict:
    return read_json(CACHE_FILE, default={"entries": {}, "updated": None})


def save(path, d) -> None:
    d["updated"] = now()
    write_json(path, d)


def content_key(title: str, description: str, lang: str) -> str:
    """Cache key. Content-addressed, so an edited English title re-translates
    and an unchanged one never does."""
    h = hashlib.sha256((title + "\x00" + description).encode("utf-8")).hexdigest()
    return f"{lang}:{h[:32]}"


# --------------------------------------------------------------- the split

def split_description(description: str) -> tuple[list[str], list[tuple[int, str]]]:
    """Return (what to translate, [(line index, timestamp prefix)]).

    Everything not returned — every URL, every bulleted source, every blank
    line, and every chapter timestamp — is held back and re-emitted from the
    original string. The model never sees them and so can never damage them.
    """
    lines = description.split("\n")
    send, keep = [], []
    for i, ln in enumerate(lines):
        if not ln.strip() or VERBATIM.search(ln):
            continue
        m = CHAPTER.match(ln)
        if m:
            send.append(m.group(2))
            keep.append((i, m.group(1)))
        else:
            send.append(ln)
            keep.append((i, ""))
    return send, keep


def rebuild_description(description: str, keep: list[tuple[int, str]],
                        translated: list[str]) -> str:
    lines = description.split("\n")
    for (i, prefix), t in zip(keep, translated):
        lines[i] = prefix + t
    return "\n".join(lines)[:DESC_MAX]


# ---------------------------------------------------------------- the model

SYSTEM = """You localize YouTube metadata for an evidence-first deep-ocean
science channel. You are NOT a literal translator.

Your job is search-phrase localization. The title must be the phrase a native
speaker would actually TYPE INTO YOUTUBE to find this video — the idiomatic
question as it is really asked in that language and that market, not a
word-for-word rendering of the English. If the natural search phrase differs
from the literal translation, use the search phrase.

Rules that are not negotiable:
- Get the CORE NOUN AND ADJECTIVE of the title exactly right, and re-read the
  title before you return it to check them. A near-miss on the key word makes
  the title unsearchable and misdescribes the video: "deepest" must not become
  "longest", "biggest" must not become "heaviest", "transparent" must not
  become "invisible". This is the single most damaging error you can make here.
- The title MUST be 100 characters or fewer. Count them.
- Keep the question form if the English is a question; that is how these are
  searched for.
- Numbers, units and organisation names (NOAA, MBARI, WHOI, JAMSTEC) stay as
  they are. Convert nothing. Invent nothing. If the English states a figure,
  the translation states the same figure.
- No transliteration of Latin-script proper nouns into other scripts.
- Return the same number of description lines you were given, in order.
- Return STRICT JSON and nothing else: no prose before or after, no code fence.
"""


def prompt_for(lang: str, title: str, prose: list[str]) -> list[dict]:
    numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(prose))
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content":
            f"Target language: {LANGUAGES[lang]} (BCP-47 code `{lang}`).\n\n"
            f"ENGLISH TITLE:\n{title}\n\n"
            f"ENGLISH DESCRIPTION LINES ({len(prose)} of them):\n{numbered}\n\n"
            f'Return exactly this JSON:\n'
            f'{{"title": "<the localized search phrase, <=100 chars>", '
            f'"lines": [<{len(prose)} localized strings, in order>]}}'},
    ]


def parse(raw: str, want_lines: int) -> tuple[str, list[str]]:
    """Parse the model's answer, or raise. Never repairs a bad shape.

    A translation that came back the wrong length means the model dropped or
    merged a line, and silently reassembling around that is how a description
    ends up with a sources block glued to a sentence.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n|\n```$", "", text).strip()
    obj = json.loads(text)
    title = (obj.get("title") or "").strip()
    lines = obj.get("lines")
    if not title:
        raise ValueError("no title in the response")
    if not isinstance(lines, list) or len(lines) != want_lines:
        raise ValueError(f"expected {want_lines} description line(s), got "
                         f"{len(lines) if isinstance(lines, list) else 'none'}")
    if len(title) > TITLE_MAX:
        raise ValueError(f"title is {len(title)} chars, over YouTube's "
                         f"{TITLE_MAX}")
    return title, [str(x) for x in lines]


CHECK_SYSTEM = """You are checking one YouTube title translation for a single
kind of error: a wrong core noun or adjective.

The title is a search phrase, so a near-miss on the key word makes the video
unfindable AND misdescribes it. Judge meaning, not style: idiomatic word order,
a different register, or a rephrased question are all FINE. What is not fine is
the subject or its defining adjective being a different concept - "deepest"
rendered as "longest", "biggest" as "heaviest", or a word that is not actually
a word in the target language.

Return STRICT JSON, nothing else, no code fence:
{"ok": true|false, "why": "<short>", "better": "<a corrected title, or null>"}
"""


def check_title(lang: str, en_title: str, localized: str, key: str,
                model: str) -> tuple[str, str, float]:
    """Back-check one localized title. Returns (title, note, cost).

    This exists because it caught a real defect on the first run: Sonnet
    rendered "What is the deepest part of the ocean?" into Indonesian as "Apa
    bagian terlaut di samudra?" - and *terlaut* is not a word. Nothing else in
    this pipeline could have noticed. The check is one short call against a
    fifteen-word string, so it costs a fraction of the translation it guards,
    and it either corrects the title or refuses the language. It never ships
    the version it just called wrong.
    """
    out = author.call_openrouter(
        [{"role": "system", "content": CHECK_SYSTEM},
         {"role": "user", "content":
             f"Target language: {LANGUAGES[lang]} (`{lang}`).\n"
             f"ENGLISH: {en_title}\nPROPOSED: {localized}"}],
        model, key, timeout=90, temperature=0.0)
    cost = (out.get("usage") or {}).get("cost") or 0.0
    text = (out["choices"][0]["message"]["content"] or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n|\n```$", "", text).strip()
    verdict = json.loads(text)
    if verdict.get("ok"):
        return localized, "", cost
    better = (verdict.get("better") or "").strip()
    if not better or len(better) > TITLE_MAX:
        raise ValueError(
            f"the back-check rejected the {lang} title "
            f"({verdict.get('why', 'no reason given')}) and offered no usable "
            f"replacement — refusing to ship it")
    return better, f"back-check corrected it: {verdict.get('why', '')}", cost


def translate(lang: str, title: str, description: str, key: str,
              model: str) -> dict:
    """One language for one video. Returns {'title':…, 'description':…}."""
    prose, keep = split_description(description)
    if not prose:
        raise ValueError("the description has no translatable prose line")
    out = author.call_openrouter(prompt_for(lang, title, prose), model, key,
                                 timeout=180, temperature=0.0)
    raw = (out["choices"][0]["message"]["content"] or "")
    t, lines = parse(raw, len(prose))
    cost = (out.get("usage") or {}).get("cost") or 0.0
    t, note, check_cost = check_title(lang, title, t, key, model)
    return {"title": t,
            "description": rebuild_description(description, keep, lines),
            "note": note,
            "cost_usd": cost + check_cost}


# ---------------------------------------------------------------- the lane

def run(limit: int = 15, dry_run: bool = False,
        languages: list[str] | None = None) -> int:
    cfg = config()
    langs = languages or list(LANGUAGES)
    state, cache = load_state(), load_cache()
    model = os.environ.get("OPENROUTER_MODEL", author.DEFAULT_MODEL)

    with Stage(LANE, week_id(),
               zero_work_hint="Every live video already carries all five "
                              "localizations and its defaultLanguage, so "
                              "there was nothing to translate or write.") as st:
        live = ytmeta.live_videos()
        if not live:
            st.named_stop("NOTHING_PUBLISHED",
                          "loop/state/ledger.json lists no live video",
                          unblock="This lane runs after the upload lane.")

        pending = [r for r in live
                   if sorted(state["videos"].get(r["video_id"], {})
                             .get("languages", [])) != sorted(langs)
                   or state["videos"].get(r["video_id"], {})
                   .get("default_language") != ytmeta.DEFAULT_LANGUAGE]
        st.note(f"{len(live)} live video(s); {len(pending)} need work; "
                f"languages {', '.join(langs)}")
        if not pending:
            st.named_stop(
                "LOCALIZATIONS_UP_TO_DATE",
                f"all {len(live)} live video(s) already carry "
                f"{len(langs)} localizations and defaultLanguage="
                f"{ytmeta.DEFAULT_LANGUAGE}. Nothing was translated and "
                f"nothing was written — a re-run costs nothing, which is the "
                f"design.",
                detail={"videos": [r["slug"] for r in live]},
                unblock="Nothing to do. This stop means the lane is finished, "
                        "not broken. It will do real work again when a new "
                        "episode is uploaded or an English title changes.")

        # ---- credentials ---------------------------------------------------
        creds = up.load_credentials(cfg)
        if not creds or creds.get("unusable"):
            code, msg, unblock = up.credential_stop(creds, cfg)
            st.named_stop(code,
                          f"{len(pending)} video(s) need localized metadata "
                          f"but " + msg,
                          detail={"pending": [r["slug"] for r in pending]},
                          unblock=unblock)

        api_key = author.api_key()
        if not api_key:
            st.named_stop(
                "OPENROUTER_KEY_MISSING",
                f"{len(pending)} video(s) need translating and there is no "
                f"OpenRouter key on this machine",
                unblock="Put the key in .secrets/openrouter_key.txt (Mac) or "
                        "set $OPENROUTER_API_KEY (Actions). It is the same key "
                        "loop/author.py and loop/advise.py already use.")

        token = up.access_token(creds)
        ch = auth.channel(token)
        if not ch["ok"] or not ch["matches_expected"]:
            st.named_stop(
                "WRONG_CHANNEL" if ch["ok"] else "CHANNEL_UNREADABLE",
                "refusing to rewrite metadata: "
                + (f"the credential authorises '{ch.get('title')}', not "
                   f"{auth.EXPECTED_HANDLE}" if ch["ok"] else ch["detail"]),
                unblock="Run: .venv/bin/python auth/check_auth.py")

        # BOTH irreversible lanes - see loop/quota.deferrable_reserve().
        reserve = quota.deferrable_reserve()
        afford = quota.units_affordable(quota.PER_LOCALIZE,
                                        min(limit, len(pending)),
                                        reserve=reserve)
        if afford == 0:
            st.named_stop(
                "QUOTA_EXHAUSTED",
                f"{len(pending)} video(s) need localizing but today's "
                f"allowance cannot fund one at {quota.PER_LOCALIZE} units "
                f"while keeping {quota.PER_VIDEO} back for the upload lane. "
                f"{quota.report()}",
                unblock="Nothing to do; the allowance resets at midnight "
                        "Pacific and this lane runs daily.")
        if afford < len(pending):
            st.note(f"quota funds {afford} of {len(pending)} today "
                    f"({quota.PER_LOCALIZE} units each)")

        written, spent, cost = 0, 0, 0.0

        for row in pending[:afford]:
            vid, slug = row["video_id"], row["slug"]

            # The CURRENT server-side snippet, every time. Merging onto the
            # repo's cached copy would revert a manual Studio edit.
            try:
                video = ytmeta.get_video(token, vid)
                spent += quota.VIDEO_READ
            except urllib.error.HTTPError as e:
                st.note(f"{slug}: videos.list failed {e.code}")
                continue
            if video is None:
                st.note(f"{slug}: {vid} is not on the channel — skipped")
                continue

            snippet = video.get("snippet") or {}
            en_title = snippet.get("title") or ""
            en_desc = snippet.get("description") or ""
            if not en_title:
                st.note(f"{slug}: the live snippet has no title — skipped "
                        f"rather than merged, which would blank it")
                continue

            existing = dict(video.get("localizations") or {})
            loc, missing = {}, []
            for lang in langs:
                key = content_key(en_title, en_desc, lang)
                hit = cache["entries"].get(key)
                if hit:
                    loc[lang] = {"title": hit["title"],
                                 "description": hit["description"]}
                    continue
                missing.append((lang, key))

            # --dry-run still TRANSLATES. It means "make no irreversible
            # external write", and a translation is neither irreversible nor
            # external to us: it lands in the cache, which is the expensive
            # half, so the real run afterwards costs nothing at the model and
            # writes exactly what was reviewed. LOOP_DRY_RUN=1 is the other
            # thing entirely - it refuses the credential outright, upstream of
            # here, so no model call and no API call happens at all.
            for lang, key in missing:
                try:
                    got = translate(lang, en_title, en_desc, api_key, model)
                except Exception as e:                      # noqa: BLE001
                    # One language failing must not cost the other four, and
                    # must never take the lane down.
                    st.note(f"{slug} [{lang}]: {type(e).__name__}: "
                            f"{str(e)[:140]}")
                    continue
                cost += got.pop("cost_usd", None) or 0.0
                check_note = got.pop("note", "")
                cache["entries"][key] = {"title": got["title"],
                                         "description": got["description"],
                                         "lang": lang, "model": model,
                                         "back_check": check_note or "clean",
                                         "at": now()}
                loc[lang] = got
                st.work(f"{slug} [{lang}]: localized the search phrase — "
                        f"{got['title'][:60]}"
                        + (f"  [{check_note}]" if check_note else ""))
            save(CACHE_FILE, cache)

            if not loc:
                st.note(f"{slug}: nothing translated, so nothing written")
                continue

            # Keep any language somebody added by hand in Studio.
            merged_loc = {**existing,
                          **{k: v for k, v in loc.items()}}

            body = ytmeta.update_localizations(token, vid, snippet, merged_loc,
                                               dry_run=dry_run)
            if dry_run:
                st.work(f"{slug}: composed a COMPLETE snippet "
                        f"({len(body['snippet'])} properties, title/description"
                        f"/tags/categoryId all present) plus "
                        f"{len(merged_loc)} localization(s) — sent nothing")
                continue

            spent += quota.VIDEO_UPDATE
            state["videos"][vid] = {
                "slug": slug,
                "languages": sorted(k for k in merged_loc if k in langs),
                "all_languages": sorted(merged_loc),
                "default_language": body["snippet"]["defaultLanguage"],
                "en_title": en_title,
                "source_hash": content_key(en_title, en_desc, "en")
                .split(":", 1)[1],
                "applied_at": now(),
            }
            written += 1
            st.work(f"{slug}: wrote {len(merged_loc)} localization(s) and "
                    f"defaultLanguage={body['snippet']['defaultLanguage']}, "
                    f"with the English title, description, "
                    f"{len(body['snippet'].get('tags') or [])} tag(s) and "
                    f"categoryId sent back whole")

        save(STATE_FILE, state)
        # Booked even under --dry-run: the videos.list reads really happened
        # and really cost units. A dry run that under-reports the day's spend
        # is how the next lane finds the allowance smaller than the account says.
        if spent:
            quota.spend(spent, LANE)
            st.note(f"spent {spent} quota units. {quota.report()}")
        if cost:
            st.note(f"translation cost ${cost:.4f} at OpenRouter ({model})")

        if written == 0 and not dry_run:
            st.named_stop(
                "LOCALIZE_INERT",
                f"the lane authenticated and wrote localizations to no video "
                f"at all ({len(pending)} were pending).",
                detail={"pending": [r["slug"] for r in pending]},
                unblock="Read the [note] lines above: either the model "
                        "refused every language, or videos.list returned no "
                        "snippet. Neither is a state to pass green.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--languages", default=",".join(LANGUAGES),
                    help="comma-separated BCP-47 codes")
    ap.add_argument("--dry-run", action="store_true",
                    help="translate from cache and compose the body; write "
                         "nothing to YouTube")
    a = ap.parse_args()
    langs = [x.strip() for x in a.languages.split(",") if x.strip()]
    unknown = [x for x in langs if x not in LANGUAGES]
    if unknown:
        print(f"unknown language(s): {unknown}. Known: {list(LANGUAGES)}")
        return 2
    return run(limit=a.limit, dry_run=a.dry_run, languages=langs)


if __name__ == "__main__":
    raise SystemExit(main())
