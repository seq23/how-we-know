#!/usr/bin/env python
"""audit_narration.py - prove the generated narration is usable, per episode.

"Exists and is non-zero" is not enough. A Chatterbox take can be a valid PCM
file and still be unusable: silence, a burst of clipping, a sentence dropped
mid-way, or a chunk that hit the model's ~40 s generation ceiling and was
truncated without an error. This audits every beat against the plan it was cut
from and names anything suspect rather than shipping it quietly.

Checks per beat
---------------
  silent      RMS <= -45 dBFS or peak <= 0.01              (listen-equivalent)
  clipped     >= 0.1% of samples at |x| >= 0.995
  truncated   duration >= 39 s (Chatterbox's 1000-token / 40 s hard ceiling)
  fast        seconds-per-word far BELOW the episode median -> words dropped
  slow        seconds-per-word far ABOVE it -> stall, babble or repeated phrase
  level       beat RMS more than 4 dB off the -23 dBFS target

Also lists technical terms (species, units, depths, instruments) that appear in
a script but are NOT covered by synth.LEXICON, since Chatterbox has no phoneme
input and those are exactly the words it mangles.

Usage:  audit_narration.py [--audio-dir audio] [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "visuals"))

from synth import LEXICON, rms_dbfs  # noqa: E402

SR = 24000
TARGET_DB = -23.0

SILENT_DB = -45.0
CLIP_FRAC = 0.001
TRUNC_S = 39.0
SPW_TOL = 2.2          # x the episode median seconds-per-word
LEVEL_TOL = 4.0        # dB off target


def beat_stats(path: Path):
    x, sr = sf.read(str(path), dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    return {
        "dur": len(x) / sr,
        "rms": rms_dbfs(x),
        "peak": float(np.abs(x).max()),
        "clip": float((np.abs(x) >= 0.995).mean()),
        "sr": sr,
    }


TECH = re.compile(
    r"\b("
    r"[A-Z][a-z]+(?:us|um|a|is|ae|ii)\b"          # latinate species/genus forms
    r"|[a-z]*pelagic|hadal|abyssal|bathyal|photic|benthic"
    r"|bioluminescen\w+|chemosynth\w+|osmolyt\w+|piezolyt\w+|trimethylamine"
    r"|siphonophore\w*|cephalopod\w*|amphipod\w*|copepod\w*|ctenophore\w*"
    r"|holothurian\w*|isopod\w*|polychaete\w*|foraminifer\w*"
    r"|bathymetr\w+|hydrotherm\w+|megapascal\w*|pascal\w*|atmosphere\w*"
    # materials-and-manufacturing (added 2026-09-21 with the second domain's
    # narration): phases, processes, instruments and the chemical names the
    # scripts actually use. A gap scan that only knows deep-sea words reports
    # a materials script as clean.
    r"|martensit\w*|austenit\w*|cementite|pearlite|ferrite|eutectoid|bainit\w*"
    r"|tempering|quenchant\w*|carburiz\w+|sintering|anneal\w+|nucleat\w+"
    r"|[a-z]*silane|[a-z]*silazane|polyacrylonitrile|pyrrolidone|terephthal\w+"
    r"|phenylene\w*|dicyclopentadiene|resorcinol|polyimide|polysilicon|alkoxide"
    r"|aluminide\w*|intermetallic\w*|interstitial\w*|stoichiometr\w+"
    r"|anisotrop\w+|adiabatic|autogenous|carbothermic|pyrophoric|pyrolysis"
    r"|[a-z]+ometry|[a-z]+lithography|ellipsometr\w+|nanoindentation"
    r"|thermogravimetric|molybdenum|ruthenium|vanadium|chromium|manganese"
    r"|hematite|magnetite|tobermorite|wootz|czochralski|leidenfrost|fraunhofer"
    r"|boltzmann|verhoeven|hall-petch|diels-alder|gettering|spinneret"
    r"|graphene|aerogel|kevlar|damascus"
    r"|[A-Z]{3,6}"                                  # acronyms: NOAA, MBARI, ROV
    r")\b")


# Ordinary English words that the latinate/acronym patterns would otherwise
# flag. A term list full of THE and WHAT is not a pronunciation report.
STOP = {"the","and","what","why","how","this","that","status","human","pov","pass",
        "not","but","for","are","was","has","its","all","one","two","new","see",
        "usa","uk","ai","era","sea","ice","air","oil","gas","data","area","idea",
        "extra","media","camera","formula","america","china","russia","india",
        "australia","asia","africa","europe","antarctica"}


def missing_lexicon(md: str):
    lex = {k.lower() for k in LEXICON}
    terms = {}
    for m in TECH.finditer(md):
        t = m.group(1)
        if t.lower() in lex or t.lower() in STOP:
            continue
        terms[t] = terms.get(t, 0) + 1
    return terms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default=str(ROOT / "audio"))
    ap.add_argument("--json", default=str(ROOT / "audio" / "narration_audit.json"))
    args = ap.parse_args()

    import planner
    audio = Path(args.audio_dir)
    scripts = sorted((ROOT / "scripts").glob("*.md"))
    if not scripts:
        print("error: no scripts - refusing to pass on an empty loop", file=sys.stderr)
        return 2

    episodes, inspected = [], 0
    print(f"{'episode':<50}{'beats':>6}{'have':>5}{'words':>7}{'mm:ss':>8}"
          f"{'wpm':>6}{'rms':>7}{'spread':>7}{'peak':>6}  flags")
    for sp in scripts:
        slug = sp.stem
        plan = planner.plan(str(sp))
        d = audio / slug
        beats, flags = [], []
        for i, b in enumerate(plan):
            f = d / f"{i:04d}.wav"
            words = len(b["narration"].split())
            if not f.exists() or f.stat().st_size < 100:
                beats.append({"i": i, "words": words, "missing": True})
                continue
            s = beat_stats(f)
            inspected += 1
            s.update(i=i, words=words, missing=False,
                     spw=s["dur"] / max(words, 1))
            beats.append(s)

        have = [b for b in beats if not b["missing"]]
        if not have:
            print(f"{slug:<50}{len(plan):>6}{0:>5}"
                  f"{sum(b['words'] for b in beats):>7}{'--':>8}{'--':>6}"
                  f"{'--':>7}{'--':>7}{'--':>6}  NOT GENERATED")
            episodes.append({"episode": slug, "beats": len(plan), "have": 0,
                             "flags": ["NOT GENERATED"]})
            continue

        med = float(np.median([b["spw"] for b in have]))
        for b in have:
            if b["rms"] <= SILENT_DB or b["peak"] <= 0.01:
                flags.append(f"#{b['i']:04d} SILENT ({b['rms']:.0f} dBFS)")
            if b["clip"] >= CLIP_FRAC:
                flags.append(f"#{b['i']:04d} CLIPPED ({b['clip']*100:.2f}%)")
            if b["dur"] >= TRUNC_S:
                flags.append(f"#{b['i']:04d} TRUNCATED ({b['dur']:.1f}s at the 40s ceiling)")
            if b["spw"] < med / SPW_TOL:
                flags.append(f"#{b['i']:04d} FAST ({b['spw']:.2f} vs {med:.2f} s/word "
                             f"- words may be dropped)")
            if b["spw"] > med * SPW_TOL:
                flags.append(f"#{b['i']:04d} SLOW ({b['spw']:.2f} vs {med:.2f} s/word "
                             f"- stall or repeat)")
            if abs(b["rms"] - TARGET_DB) > LEVEL_TOL:
                flags.append(f"#{b['i']:04d} LEVEL ({b['rms']:.1f} dBFS)")
            if b["sr"] != SR:
                flags.append(f"#{b['i']:04d} RATE ({b['sr']} Hz, assemble concats "
                             f"with -c copy and needs {SR})")

        total = sum(b["dur"] for b in have)
        # Words of the beats that EXIST. Dividing the whole episode's words by a
        # partial duration reports a nonsense wpm (570) and hides a real one.
        words = sum(b["words"] for b in have)
        rmss = [b["rms"] for b in have]
        m, s = divmod(int(total), 60)
        miss = len(plan) - len(have)
        tag = " ".join(x for x in [
            f"{miss} MISSING" if miss else "",
            f"{len(flags)} flagged" if flags else "clean",
        ] if x)
        print(f"{slug:<50}{len(plan):>6}{len(have):>5}{words:>7}{m:>5}:{s:02d}"
              f"{words/(total/60):>6.0f}{np.mean(rmss):>7.1f}"
              f"{max(rmss)-min(rmss):>7.1f}{max(b['peak'] for b in have):>6.2f}  {tag}")
        for fl in flags[:8]:
            print(f"      {fl}")
        if len(flags) > 8:
            print(f"      ... and {len(flags)-8} more")
        episodes.append({
            "episode": slug, "beats": len(plan), "have": len(have),
            "missing": miss, "words": words,
            "words_total": sum(b["words"] for b in beats),
            "duration_s": round(total, 1),
            "wpm": round(words / (total / 60), 1),
            "rms_mean": round(float(np.mean(rmss)), 1),
            "rms_spread": round(float(max(rmss) - min(rmss)), 1),
            "peak": round(float(max(b["peak"] for b in have)), 3),
            "median_spw": round(med, 3), "flags": flags,
        })

    print("\nTechnical terms present but NOT in synth.LEXICON "
          "(Chatterbox has no phoneme input; these are the likely mispronunciations):")
    allmiss = {}
    for sp in scripts:
        # Only the spoken prose. Scanning the raw file picks up headings,
        # {{directive}} bodies and **Status:** metadata - none of which is read
        # aloud - and buries the real terms under THE / WHAT / POV.
        spoken = " ".join(b["narration"] for b in planner.plan(str(sp)))
        for t, n in missing_lexicon(spoken).items():
            allmiss[t] = allmiss.get(t, 0) + n
    for t, n in sorted(allmiss.items(), key=lambda kv: -kv[1])[:40]:
        print(f"  {t:<28} x{n}")

    Path(args.json).write_text(json.dumps(
        {"episodes": episodes, "lexicon_gaps": allmiss}, indent=2))
    print(f"\n-> {args.json}")

    # Rule 0: an audit that inspected nothing must not report success.
    if inspected == 0:
        print("error: audited 0 beats - refusing to exit 0 having done nothing.",
              file=sys.stderr)
        return 2
    bad = [e for e in episodes if e.get("flags") or e.get("have", 0) != e["beats"]]
    print(f"\naudited {inspected} beats; {len(episodes)-len(bad)}/{len(episodes)} "
          f"episodes complete and clean")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
