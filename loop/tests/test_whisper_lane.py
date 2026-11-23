"""Whisper Almanac: the rules are behaviour, and each is proven negatively.

  a. the plain-words check fails an acronym, a number of more than 3 digits,
     units, an equation, a jargon string (its own --self-test), and a real
     How We Know script fails it unrewritten - so a rewrite is required;
  b. a script that passes is refused when one acronym, one long number, one
     invented name or one invented number is put back in, when it is too
     short, and when it copies another script (distinct, no loops);
  c. affirmations: a guaranteed outcome, a money figure or a health claim fails;
  d. the upload kit: the AI-voice line must sit in the first 3 description
     lines, the altered-content flag must be set, the title's length must be
     the REAL one (rounded down), and the upload is private;
  e. the Mac night with no whisper sample is the GREEN owner_action stop
     WHISPER_SAMPLE_MISSING that names the exact place to drop the file -
     and the same night with a sample present goes past that stop;
  b2. a script without the opening promise (the real length, whispered, for
     sleep, a whole thought, at most ~10 s) fails the check;
  d2. the kit makes 3 thumbnail variants, each 1280x720, dark, distinct.
  d3. each thumbnail shows the video's own picture (its painting, or a frame of
     its footage once rendered; the candle glow before that), with words and a
     subline readable at feed size, the subline true to the lane, and a
     published video's thumbnails never remade;
  d4. chapters skip the opening promise, never repeat, never cut a word.

Every committed script in scripts/whisper/ must pass (zero scripts = fail).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ["LOOP_DRY_RUN"] = "1"

import whisper_lane as WL  # noqa: E402
import whisper_words as W  # noqa: E402

fails: list[str] = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


# -- a. the check itself ------------------------------------------------------
r = subprocess.run([sys.executable, str(LOOP / "whisper_words.py"), "--self-test"],
                   capture_output=True, text=True)
check(r.returncode == 0 and "SELF-TEST OK" in r.stdout, f"(a) self-test: {r.stdout}{r.stderr}")
raw = WL.source_narration("20-what-is-the-midnight-zone")
check(any(p.split()[0] in {"ACRONYM", "LONG_NUMBER"} for p in W.text_problems(raw, [])),
      "(a) an unrewritten How We Know script passes the plain-words check")

# -- b. a passing script, then each rule broken -------------------------------
c = WL.cfg()
src = "20-what-is-the-midnight-zone"
para = ("Far down in the sea, the last of the sunlight fades away. The water there is dark and "
        "cold, and it stays dark all the time. Many animals drift through it slowly, and some "
        "of them make their own soft light.")
paras = []
for i in range(190):
    paras.append(para.replace("Far down", f"Far down {'and down ' * (i % 7)}")
                 .replace("slowly", ["slowly", "gently", "quietly", "calmly", "softly"][i % 5])
                 + f" You can rest here {'for a while ' * (i % 4)}now.")
# a distinct paragraph per beat so the script is not a loop of itself
paras = [p + " " + " ".join(["the", "deep", "is", "quiet"][: (i % 4) + 1]) + "."
         for i, p in enumerate(paras)]
segs = [(src, paras[k:k + 19]) for k in range(0, 190, 19)]

with tempfile.TemporaryDirectory() as td:
    td = Path(td)

    def write(name, s, kind="sleep"):
        f = td / f"{name}.md"
        f.write_text(WL.render_script(name, kind, "t", [src], [], s))
        return f

    good = write("good", segs)
    base = WL.script_problems(good, others=[])
    real = [x for x in base if "INVENTED" not in x and "NOT_DISTINCT" not in x]
    check(not real, f"(b) the clean fixture fails: {real[:4]}")

    def broken(label, s2, code, others=None):
        f = write(label, s2)
        probs = WL.script_problems(f, others=others if others is not None else [])
        check(any(code in p for p in probs), f"(b) {label}: {code} not caught: {probs[:3]}")

    def put(text):
        s2 = [list(x) for x in segs]
        s2[3] = (src, [s2[3][1][0] + " " + text] + s2[3][1][1:])
        return s2

    broken("acronym", put("Scientists at NOAA say so."), "ACRONYM")
    broken("long-number", put("It sits at 4000 meters."), "LONG_NUMBER")
    broken("invented-name", put("A sailor named Bartholomew saw it."), "INVENTED_NAME")
    broken("invented-number", put("It took 7 days."), "INVENTED_NUMBER")
    broken("too-short", segs[:2], "LENGTH")
    twin = write("twin", segs)
    broken("copy", segs, "NOT_DISTINCT", others=[twin])

    # the opening promise (owner, 8 Nov 2026): a script that starts mid-thought,
    # without the plain promise naming what it is and its real length, fails
    good_open = WL.parse(good)["segments"][0]["paragraphs"][0]
    check(not [x for x in base if x.startswith("OPENING")], f"(b) a script with the promise fails: {base[:3]}")
    for label, swap in (("no-opening", None),
                        ("wrong-length", good_open.replace("Two hours", "Three hours")),
                        ("not-named", "Two hours of the deep sea."),
                        ("too-long", good_open + " " + " ".join(["The water is calm and dark."] * 4))):
        txt = good.read_text()
        txt = txt.replace(good_open + "\n\n", "" if swap is None else swap + "\n\n", 1)
        bad = td / f"{label}.md"
        bad.write_text(txt)
        probs = WL.script_problems(bad, others=[])
        check(any(x.startswith("OPENING") for x in probs), f"(b) {label}: the opening rule is not enforced: {probs[:3]}")
    check(WL.spoken_length(2 * 3600 + 4 * 60) == "two hours" and WL.spoken_length(48 * 60) == "forty-five minutes",
          "(b) the promise's length is not the real one, rounded down")

# -- c. affirmations guardrail -----------------------------------------------
for bad in ("You will get $10,000 by Friday.", "Your ex will text you tonight.",
            "My body heals itself as I sleep."):
    check(WL.affirmation_problems(bad), f"(c) not caught: {bad!r}")
check(not WL.affirmation_problems("I am safe, and good things find their way to me."),
      "(c) a plain affirmation is refused")

# -- d. the upload kit --------------------------------------------------------
p = {"slug": "the-deep-ocean-at-night", "kind": "sleep", "title": "t", "meta": {},
     "segments": [{"source": src, "paragraphs": ["a"]}]}
secs = 2 * 3600 + 47 * 60
t = WL.title(p, secs, c)
check("(2.5 hr" in t, f"(d) 2 h 47 min must be titled 2.5 hr (rounded down): {t}")
d = WL.description(p, secs, c)
meta = {"title": t, "description": d, "body": WL.upload_body(t, d, c)}
check(not WL.meta_problems(meta, secs, c), f"(d) a correct kit fails: {WL.meta_problems(meta, secs, c)}")
moved = dict(meta, description="a\nb\nc\n" + d)
check(any("AI_LINE" in x for x in WL.meta_problems(moved, secs, c)), "(d) AI line below line 3 passes")
off = json.loads(json.dumps(meta))
off["body"]["status"]["containsSyntheticMedia"] = False
check(any("ALTERED" in x for x in WL.meta_problems(off, secs, c)), "(d) altered-content off passes")
check(any("LENGTH_NOT_REAL" in x for x in WL.meta_problems(meta, 3 * 3600 + 5, c)),
      "(d) a title whose length is not the measured one passes")
pub = json.loads(json.dumps(meta))
pub["body"]["status"]["privacyStatus"] = "public"
check(any("PRIVATE" in x for x in WL.meta_problems(pub, secs, c)), "(d) a public upload passes")

# -- d2. three thumbnail variants (owner, 8 Nov 2026), each in the brand ---
with tempfile.TemporaryDirectory() as td:
    ep = WL.parse(WL.SCRIPTS / "the-deep-ocean-at-night.md")
    thumbs = WL.thumbnails(ep, WL.estimate_seconds(ep, c), Path(td), c)
    check(len(thumbs) == 3 and thumbs[0].name == "thumbnail.png",
          f"(d2) the kit does not make 3 variants with A as thumbnail.png: {[t.name for t in thumbs]}")
    check(not WL.thumbnail_problems(thumbs, c), f"(d2) a variant breaks the brand: {WL.thumbnail_problems(thumbs, c)}")
    check(any("THUMB_SAME" in x for x in WL.thumbnail_problems([thumbs[0]] * 3, c)),
          "(d2) three copies of one picture pass as three variants")
    check(any("THUMB_VARIANTS" in x for x in WL.thumbnail_problems(thumbs[:1], c)),
          "(d2) one thumbnail passes as three variants")

# -- d3. thumbnails show the video's own picture, readable, lane-true (23 Nov 2026 review)
import copy  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(ROOT / "visuals"))
import whisper_paint as WP  # noqa: E402

_real = (WL.KITS, WL.WORK)
with tempfile.TemporaryDirectory() as td:
    WL.KITS, WL.WORK = Path(td) / "kits", Path(td) / "work"      # no real kit or render decides anything
    hexc = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731

    def rows(f, col, x1=1280, y0=0):
        a = np.asarray(Image.open(f).convert("RGB"), np.int32)[y0:, :x1]
        r = np.where((np.abs(a - np.array(col)).sum(-1) < 40).sum(1) > 0)[0]
        return int(r.max() - r.min() + 1) if len(r) else 0

    # a painted video: each variant's backdrop IS its painting (the render's own seed and lane)
    money = WL.parse(WL.SCRIPTS / "affirmations-money-fast-2026-w47.md")
    check(WL.picture_for(money["slug"], money, c) == "paint", "(d3) a new money video is not painted")
    bd = WL.backdrops(money, 60.0, c)
    want = WP.stills(money["slug"], [60.0 * v[1] for v in WL.VARIANTS.values()], "money")
    check(all(bd[v] is not None and np.array_equal(np.asarray(bd[v]), w) for v, w in zip(WL.VARIANTS, want)),
          "(d3) a painted video's thumbnail backdrop is not its own painting")
    thumbs = WL.thumbnails(money, 60.0, Path(td) / "money", c)
    check(not WL.thumbnail_problems(thumbs, c), f"(d3) the painted thumbnails break the brand: "
          f"{WL.thumbnail_problems(thumbs, c)}")
    # the still the thumbnail shows is the frame the video shows (stills == frames, same draws)
    t_hold = None
    sent = 0
    for buf, n in WP.frames(money["slug"], 40.0, "money"):
        sent += n
        if n > 1 and t_hold is None:
            t_hold = (sent - 1) / WP.FPS, buf
    check(t_hold is not None and WP.stills(money["slug"], [t_hold[0]], "money")[0].tobytes() == t_hold[1],
          "(d3) a painting still is not the frame the video shows at that time")

    # a footage video not rendered yet: the candle glow, three distinct variants, each with its flame
    ocean = WL.parse(WL.SCRIPTS / "the-deep-ocean-at-night.md")
    check(all(x is None for x in WL.backdrops(ocean, 3000.0, c).values()),
          "(d3) an unrendered footage video claims a picture of its own")
    fb = WL.thumbnails(ocean, 3000.0, Path(td) / "ocean", c)
    check(not WL.thumbnail_problems(fb, c), f"(d3) the candle fallback breaks the brand: {WL.thumbnail_problems(fb, c)}")
    # ...and the flame is really there, where its candle stands (the ember subline alone is not a candle)
    for f, (cx, cy) in zip(fb, ((960, 250), (1010, 470), (880, 230))):
        a = np.asarray(Image.open(f).convert("RGB"), np.int32)[cy - 120:cy + 120, cx - 120:cx + 120]
        flame = int(((a[..., 0] > 200) & (a[..., 0] - a[..., 2] > 80)).sum())
        check(flame >= 150, f"(d3) {f.name}: no candle flame at its candle ({flame} flame pixels)")

    # the subline names the video's lane: never "sleep science" on a deep-sea video
    subs = {slug: WL.subline(WL.parse(WL.SCRIPTS / f"{slug}.md"), 3000.0, c) for slug in
            ("the-deep-ocean-at-night", "how-we-learned-why-bread-rises", "neville-law-of-assumption-01",
             "affirmations-money-fast-2026-w47", "psalm-nights-psalm-23-01")}
    check("deep sea" in subs["the-deep-ocean-at-night"] and "science" not in subs["the-deep-ocean-at-night"],
          f"(d3) the deep-sea subline is wrong: {subs['the-deep-ocean-at-night']}")
    check("food history" in subs["how-we-learned-why-bread-rises"], f"(d3) food subline: {subs}")
    check("neville goddard" in subs["neville-law-of-assumption-01"], f"(d3) neville subline: {subs}")
    check("money" in subs["affirmations-money-fast-2026-w47"], f"(d3) money subline: {subs}")
    check(len(set(subs.values())) == len(subs), f"(d3) two lanes share a subline: {subs}")

    # readable at feed size: the words and the subline keep their size (old: ~110 / ~136 / ~40 px)
    dark = Image.new("RGB", (1280, 720), (10, 8, 6))
    theme = money["meta"].get("theme", "money")
    for words, floor in (("sleep", 125), ("let every quiet money thought settle softly tonight", 170)):
        cc = copy.deepcopy(c)
        cc["affirmations"]["topics"][theme]["thumb_words"] = words
        f = WL.thumbnail(money, 3000.0, Path(td) / "size.png", cc, "a", dark)
        h = rows(f, hexc(c["brand"]["ink"]), y0=150)
        check(h >= floor, f"(d3) the words {words!r} stand {h} px tall, under {floor}")
        sh = rows(f, hexc(c["brand"]["ember"]), x1=900)
        check(sh >= 46, f"(d3) the subline stands {sh} px tall, under 46")

    # forward-only: a published kit keeps the thumbnails it went out with
    slug = "the-deep-ocean-at-night"
    (WL.KITS / slug).mkdir(parents=True)
    for name in WL.VARIANT_FILES.values():
        dark.save(WL.KITS / slug / name)
    before = {n: (WL.KITS / slug / n).read_bytes() for n in WL.VARIANT_FILES.values()}
    (WL.KITS / slug / "kit.json").write_text(json.dumps({"slug": slug, "video_id": "PUB1", "length_s": 3000.0}))
    check(WL.refresh_thumbnails(slug, c) == [], "(d3) refresh_thumbnails remade a published video's thumbnails")
    WL.kit(slug, c=c)
    check(all((WL.KITS / slug / n).read_bytes() == b for n, b in before.items()),
          "(d3) a rewritten kit replaced a published video's thumbnails")

    # after a footage render: the thumbnails are remade on frames of the video itself
    slug = "the-bottom-of-the-ocean"
    v = WL.video_path(slug)
    v.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=1280x720:r=10:d=12,eq=brightness=-0.35", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(v)], check=True)
    (WL.KITS / slug).mkdir(parents=True)
    (WL.KITS / slug / "kit.json").write_text(json.dumps({"slug": slug, "length_s": 12.0}))
    got = WL.refresh_thumbnails(slug, c)
    ep = WL.parse(WL.SCRIPTS / f"{slug}.md")
    candle = WL.thumbnail(ep, 12.0, Path(td) / "candle.png", c, "a", None)
    frame = WL._frame_at(v, 12.0 * WL.VARIANTS["a"][1])
    framed = WL.thumbnail(ep, 12.0, Path(td) / "framed.png", c, "a", frame)
    check(len(got) == 3 and frame is not None and got[0].read_bytes() == framed.read_bytes()
          and got[0].read_bytes() != candle.read_bytes(),
          "(d3) after a footage render the thumbnail is not drawn on a frame of the video")
    check("thumbnail_problems" in json.loads((WL.KITS / slug / "kit.json").read_text()),
          "(d3) refresh_thumbnails did not record the thumbnail check")
WL.KITS, WL.WORK = _real

# -- d4. chapters: the opening promise skipped, whole words, no repeats -------
seg = lambda src, *ps: {"source": src, "paragraphs": list(ps)}  # noqa: E731
long_first = ("Far below the waves the water turns black and the animals there carry their own small "
              "lights through the cold. More follows.")
pc = {"slug": "x", "kind": "sleep", "meta": {}, "segments": [
    seg("a", "This is two hours of soft whispering, made to help you fall asleep.",
        "The sea is quiet tonight. It rolls in slowly."),
    seg("b", "The SEA is quiet tonight. Then more."),
    seg("c", long_first)]}
ch = WL.chapters(pc, [0.0, 600.0, 1200.0])
names = [x.split(" ", 1)[1] for x in ch]
check(ch and ch[0].startswith("0:00:00 ") and names[0] == "The sea is quiet tonight",
      f"(d4) chapter 1 is not named from the words after the opening promise: {ch}")
check(len(names) == 2 and len({n.lower() for n in names}) == len(names), f"(d4) a chapter name repeats: {ch}")
check(len(names[-1]) <= 60 and long_first.startswith(names[-1]) and long_first[len(names[-1])] == " "
      and names[-1][-1].isalnum(), f"(d4) a long chapter name is cut mid-word or ends on punctuation: {ch}")
ch2 = WL.chapters({"slug": "x", "kind": "sleep", "meta": {}, "segments": [seg("a", "..."), seg("b", "Quiet water.")]},
                  [0.0, 600.0])
check(ch2 == ["0:00:00 Quiet water"], f"(d4) YouTube chapters must start at 0:00:00: {ch2}")
for text, n, want in (("whispered sleep stories for you", 12, "whispered"), ("affirm, then rest", 7, "affirm"),
                      ("a calm night.", 40, "a calm night"), ("one  two\nthree", 40, "one two three")):
    check(WL.clip_words(text, n) == want, f"(d4) clip_words({text!r}, {n}) = {WL.clip_words(text, n)!r}, not {want!r}")

# -- e. the Mac night ---------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, WHISPER_SAMPLE_DIR=str(Path(td) / "asmr-voice"),
               LOOP_STOPS_DIR=str(Path(td) / "stops"))
    r = subprocess.run([sys.executable, str(LOOP / "whisper_lane.py"), "night", "--dry-run"],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    out = r.stdout + r.stderr
    if WL.queue():
        check(r.returncode == 0, f"(e) the missing-sample stop is not green: rc={r.returncode}")
        check("WHISPER_SAMPLE_MISSING" in out and f"{td}/asmr-voice/whisper-sample.m4a" in out,
              f"(e) the stop does not name the file to drop: {out[-400:]}")
        (Path(td) / "asmr-voice").mkdir()
        sample = Path(td) / "asmr-voice" / "whisper-sample.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=22:a=0.05",
                        "-ar", "24000", "-ac", "1", str(sample)], check=True)
        r = subprocess.run([sys.executable, str(LOOP / "whisper_lane.py"), "night", "--dry-run"],
                           capture_output=True, text=True, env=env, cwd=ROOT)
        out = r.stdout + r.stderr
        check("WHISPER_SAMPLE_MISSING" not in out and "would voice" in out,
              f"(e) with a sample present the night still stops: {out[-400:]}")
    else:
        fails.append("(e) no whisper script is ready for voice, so the night was not exercised")

# -- f. footage of the subject named, part by part ---------------------------
sys.path.insert(0, str(ROOT / "visuals"))
import whisper_reel as REEL  # noqa: E402


def clip(name):
    return {"local_file": f"clips/{name}.mp4", "title": name, "clean_windows": [{"start": 0, "end": 600}]}


rich = [clip(f"vent-{i}") for i in range(20)]
pools = {"vents": rich, "galaxies": []}
try:
    REEL.plan_reel([("vents", 600.0), ("galaxies", 600.0)], rich, pool_of=lambda s: pools[s])
    fails.append("(f) a part with no footage of its own subject borrowed another part's footage")
except REEL.FootageThin:
    pass
shots = REEL.plan_reel([("vents", 600.0)], rich, pool_of=lambda s: pools[s])
check(not REEL.reel_problems(shots, 600.0), f"(f) a well-pictured part breaks the footage rules: {REEL.reel_problems(shots, 600.0)[:2]}")
check(all(s["asset"] in rich for s in shots), "(f) a part showed footage that is not its own")

# -- every committed script passes -------------------------------------------
scripts = WL.all_scripts()
check(scripts, "no committed whisper script examined")
for f in scripts:
    probs = WL.script_problems(f)
    check(not probs, f"{f.name}: {probs[:3]}")

if fails:
    print("FAIL test_whisper_lane")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"ok test_whisper_lane: rules proven negatively; {len(scripts)} committed script(s) pass")
