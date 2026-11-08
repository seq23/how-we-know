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
