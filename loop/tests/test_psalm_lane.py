"""Psalm Nights (her yes 18 Nov 2026): KJV only, word for word, on Friday.

  a. a well-formed Psalm night script (every night in config) passes every
     rule, fits an hour, and its kit meets the title rules (so the rules can pass);
  b. a passage in a modern translation's words (NIV Psalm 23:1), with a word
     added or dropped, or a verse invented, is refused PASSAGE_NOT_VERBATIM;
     a reference the bundle does not hold is refused PASSAGE_NOT_IN_KJV;
  c. a passage the night does not name, or segments out of the night's plan,
     is refused;
  d. scripture quoted in the framing (from a model's memory) is refused, and
     so are quotation marks, a health claim and a promised result;
  e. the same night within the last 12 Psalm scripts is refused, and the
     rotation never picks one: 40 weeks of picks never repeat within 12;
  f. the week: Friday is Psalm Nights' upload day (ocean no longer takes it),
     the mix gives Psalm 1 a week, and the author writes for the psalm lane;
  g. the bundle: the whole Book of Psalms from a recorded public-domain
     source, and every configured passage resolves in it.
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"

import psalms as PS  # noqa: E402
import whisper_lane as WL  # noqa: E402
import whisper_upload as WU  # noqa: E402

fails: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


c = WL.cfg()
SENTS = ["Let your shoulders soften into the bed.", "Breathe in slowly, and let the breath go.",
         "There is nothing you need to hold tonight.", "The room is quiet, and the light is low.",
         "Let your hands rest, open and easy.", "You can let the day drift away from you now.",
         "Your breath is slow, and your face is calm.", "The pillow is cool and soft beneath you."]


def framing(n_words: int, seed: int) -> list[str]:
    out, para, k, i = [], [], 0, seed
    while k < n_words:
        s = SENTS[i % len(SENTS)]
        para.append(s)
        k, i = k + len(s.split()), i + 3
        if len(para) == 4:
            out.append(" ".join(para))
            para = []
    return out + ([" ".join(para)] if para else [])


def parts_for(key: str, seed: int = 0) -> list[tuple[str, list[str]]]:
    n = PS.nights(c)[key]
    out = []
    for i, src in enumerate(PS.plan(n)):
        if PS.is_passage(src):
            out.append((src, [PS.spoken(v) for v in PS.verses(src[len(PS.PREFIX):])]))
        else:
            w = c["psalms"][{"welcome": "welcome_words", "rest": "rest_words"}.get(src, "reflect_words")]
            out.append((src, framing(w, seed + i)))
    return out


def build(d: Path, name: str, key: str, parts=None, written="2026-11-18") -> Path:
    parts = parts or parts_for(key)
    f = d / f"{name}.md"
    meta = {"Night": key}
    f.write_text(WL.render_script(name, WL.PSALM, "t", [], [], parts, meta))
    scale = WL.fit_pause_scale(WL.parse(f), goal_s=3780)
    text = WL.render_script(name, WL.PSALM, "t", [], [], parts, {**meta, "Pause scale": scale})
    f.write_text(text.replace("**Written:** 2026-", f"**Written:** {written}\n**Was:** 2026-", 1)
                 if written else text)
    return f


def probs(f: Path, others=None) -> list[str]:
    return WL.script_problems(f, others=others or [])


def swap(parts, ref, paras):
    return [(s, paras if s == PS.PREFIX + ref else p) for s, p in parts]


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # a. every configured night, well formed, passes; its kit meets the rules
    for key in PS.nights(c):
        f = build(td, f"good-{key}", key)
        got = probs(f)
        check(got == [], f"(a) the well-formed {key} script fails: {got[:3]}")
        p = WL.parse(f)
        est = WL.estimate_seconds(p, c)
        t = WL.title(p, est, c)
        d = WL.description(p, est, c)
        m = {"title": t, "lane": WL.lane_of(p, c), "description": d, "body": WL.upload_body(t, d, c, WL.tag_key(p, c))}
        check(WL.meta_problems(m, est, c) == [], f"(a) the {key} kit fails: {WL.meta_problems(m, est, c)}")
        check("King James Version" in d and "public domain" in d and c["channel"]["ai_voice_line"] in d,
              f"(a) the {key} description lacks the KJV line or the AI-voice line")
        check(m["body"]["status"]["containsSyntheticMedia"] is True, f"(a) {key} is not marked altered/synthetic")
        check(m["lane"] == "psalm" and "bible verses for sleep" in m["body"]["snippet"]["tags"],
              f"(a) {key} is not in the psalm lane with its tags: {m['lane']}")

    key = "psalm-23"
    base = parts_for(key)
    # b. modern-translation wording, a word dropped, an invented verse, a missing reference
    niv = ["The Lord is my shepherd, I lack nothing."] + [PS.spoken(v) for v in PS.verses("PSA.23.2-6")]
    dropped = [PS.spoken(v) for v in PS.verses("PSA.23.1-6")]
    dropped[3] = dropped[3].replace("I will fear no evil", "I fear no evil")
    invented = [PS.spoken(v) for v in PS.verses("PSA.23.1-6")] + ["And the Lord shall give thee sweet sleep this night."]
    for name, paras in (("niv", niv), ("dropped", dropped), ("invented", invented)):
        got = probs(build(td, name, key, swap(base, "PSA.23.1-6", paras)))
        check(any("PASSAGE_NOT_VERBATIM" in x for x in got), f"(b) {name} wording was not refused: {got[:3]}")
    night = {**PS.nights(c)[key], "main": ["PSA.23.1-9"]}
    try:
        PS.verses("PSA.23.1-9")
        check(False, "(b) Psalm 23:7-9 (verses that do not exist) resolved in the bundle")
    except KeyError as e:
        check("PASSAGE_NOT_IN_KJV" in e.args[0], f"(b) a missing verse is not PASSAGE_NOT_IN_KJV: {e}")
    cfg2 = {**c, "psalms": {**c["psalms"], "nights": {**PS.nights(c), key: night}}}
    got = WL.script_problems(build(td, "missing", key, [(s.replace("PSA.23.1-6", "PSA.23.1-9"), p) for s, p in base]),
                             others=[], c=cfg2)
    check(any("PASSAGE_NOT_IN_KJV" in x for x in got), f"(b) a reference the bundle lacks was not refused: {got[:3]}")

    # c. a passage the night does not name; segments out of plan
    other = [PS.spoken(v) for v in PS.verses("PSA.91.1-16")]
    got = probs(build(td, "wrongpassage", key, [(PS.PREFIX + "PSA.91.1-16", other) if s == PS.PREFIX + "JOH.14.27"
                                                else (s, p) for s, p in base]))
    check(any("PASSAGE_NOT_IN_NIGHT" in x for x in got) and any("PLAN" in x for x in got),
          f"(c) a passage the night does not name was not refused: {got[:3]}")
    got = probs(build(td, "noplan", key, [x for x in base if x[0] != "reflect-2"]))
    check(any(x.startswith("PLAN") for x in got), f"(c) a script out of the night's plan was not refused: {got[:3]}")

    # d. scripture from memory in the framing; quotes; claims
    for name, para, code in (
            ("memory", "Rest now. He maketh me to lie down in green pastures: he leadeth me beside the still waters.",
             "SCRIPTURE_OUTSIDE_PASSAGE"),
            ("quoted", "Rest now, and hear the words “be still” in the quiet of the room tonight.", "QUOTE_MARKS"),
            ("health", "This reading cures insomnia, and you will fall asleep within minutes tonight.", "SLEEP_CLAIM"),
            ("heal", "Let these words heal your body as you rest in the quiet room tonight.", "HEALTH_CLAIM")):
        bad = [(s, (p + [para]) if s == "reflect-1" else p) for s, p in base]
        got = probs(build(td, name, key, bad))
        check(any(code in x for x in got), f"(d) {name} framing was not refused with {code}: {got[:3]}")

    # e. no night within the last 12 Psalm scripts; the rotation never repeats within 12
    first = build(td, "first", key, written="2026-11-01")
    got = probs(build(td, "again", key, parts_for(key, seed=5)), others=[first])
    check(any("NIGHT_REPEATED" in x for x in got), f"(e) the same night twice in a row was not refused: {got[:3]}")
    made: list[dict] = []
    for week in range(40):
        k = PS.next_night(c, made)
        made.append({"kind": "psalm", "slug": f"w{week:02d}",
                     "meta": {"night": k, "written": f"2026-{(week // 28) + 1:02d}-{(week % 28) + 1:02d}"}})
    seq = [m["meta"]["night"] for m in made]
    check(seq[0] == "psalm-91", f"(e) the first Psalm night is not Psalm 91: {seq[0]}")
    for i, k in enumerate(seq):
        check(k not in seq[max(0, i - PS.RECENT):i], f"(e) {k} repeats within {PS.RECENT} weeks at week {i}: {seq[:i + 1]}")

# f. the week: Friday is Psalm Nights; the mix; the author writes it
MON = dt.datetime(2026, 11, 17, 3, 0, tzinfo=dt.timezone.utc)          # Mon 16 Nov 21:00 CST
k = {"kind": "psalm", "lane": "psalm"}
slot = WU.next_slot(WU.days_for(k, c, {}), {}, MON, c)
check(slot.strftime("%a %H:%M") == "Fri 20:00", f"(f) a Psalm upload lands on {slot:%a %H:%M}, not Fri 20:00 CT")
for lane in c["upload"]["days"]:
    if lane not in ("psalm", "sleep"):
        check("fri" not in c["upload"]["days"][lane], f"(f) {lane} still takes Friday, Psalm Nights' slot")
mix, _ = WL.weekly_mix(c, {})
check(mix.get("psalm") == 1 and mix.get("ocean") == 0 and sum(mix.values()) == 5,
      f"(f) the week is not 5 with Psalm Nights 1 and ocean 0: {mix}")
import whisper_author as WA  # noqa: E402
check(WA.next_in_lane("psalm", c)[0] == "psalm", "(f) the author does not write the psalm lane")
check(WL.footage_set({"kind": "psalm", "slug": "x", "meta": {}}, c) == "calm-night"
      and "psalm" not in c["paint"]["lanes"], "(f) Psalm Nights is not on calm night footage, outside the paint trial")

# g. the bundle
b = PS.bundle()
check(len(b["books"].get("PSA", {}).get("chapters", {})) == 150, "(g) the bundle does not hold all 150 psalms")
check("public domain" in b["_source"]["status"].lower() and b["_source"]["sha256"] and b["_source"]["url"],
      "(g) the bundle does not record its public-domain source")
check(PS.verses("PSA.91.1")[0].startswith("He that dwelleth in the secret place of the most High"),
      "(g) Psalm 91:1 is not the King James text")

if fails:
    print("FAIL test_psalm_lane")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"ok test_psalm_lane: {len(PS.nights(c))} nights pass; KJV word for word, no scripture from memory, "
      f"no claims, no repeat within {PS.RECENT}, Friday 20:00 CT is Psalm Nights")
